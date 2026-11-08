"""Disposable atomic rescheduling checks, including document/key preservation."""
import io
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

fixture=tempfile.TemporaryDirectory(prefix="appointment-move-tests-")
os.environ.update(DATABASE_URL="sqlite:///"+str(Path(fixture.name)/"test.db"),SECRET_KEY="move-tests-only",PUBLIC_SITE_MODE="active")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app, db, agenda_now, appointment_report_key, bookable_appointment_slots
from models import User, Appointment, AppointmentHold, AppointmentReport, AppointmentPatientDetails, InternalRegisterExclusion, AppointmentMoveReceipt
from pypdf import PdfWriter
from sqlalchemy.exc import OperationalError

app.config["TESTING"]=True
day=(agenda_now()+timedelta(days=14)).replace(hour=18,minute=30,second=0,microsecond=0)
day+=timedelta(days=(1-day.weekday())%7)
thu=day+timedelta(days=2)
target=thu.replace(hour=19,minute=0)
pdf=PdfWriter();pdf.add_blank_page(width=595,height=842);buffer=io.BytesIO();pdf.write(buffer);scan=buffer.getvalue()
route="/admin/appointments/move"
def authenticate(email="y@bymed.be"):
    client=app.test_client();client.post("/login",data={"email":email,"password":"test-password"})
    client.get("/agenda?date="+day.date().isoformat())
    client.get("/admin/appointments?date="+day.date().isoformat())
    with client.session_transaction() as session: token=session["agenda_token"]
    return client,token
try:
    with app.app_context():
        db.create_all()
        for email,role in (("y@bymed.be",True),("student@example.invalid",False)):
            user=User(email=email,is_admin=role);user.set_password("test-password");db.session.add(user)
        a=Appointment(starts_at=day,patient_name="PATIENT FICTIF",patient_email="private@example.invalid",patient_phone="TEST",insurance_status="bim",notes="Texte privé fictif",appointment_type="459712",inami_code="459712",inami_invoice_total_cents=10295,duration_minutes=20,prescription_filename="demande.pdf",prescription_mimetype="application/pdf",prescription_data=scan)
        b=Appointment(starts_at=thu,patient_name="AUTRE PATIENT",patient_email="",appointment_type="460095")
        hold=AppointmentHold(starts_at=thu+timedelta(minutes=10),token="owner-token",expires_at=thu+timedelta(days=365),draft_data=json.dumps({"patient_name":"RESERVATION FICTIVE","inami_code":"459712","insurance_status":"bim","patient_phone":"PRIVATE"}),prescription_filename="hold.pdf",prescription_mimetype="application/pdf",prescription_data=scan)
        db.session.add_all([a,b,hold]);db.session.flush();aid,bid=a.id,b.id;old_key=appointment_report_key(a);hold_key=appointment_report_key(hold)
        for record,key in ((a,old_key),(hold,hold_key)):
            db.session.add(AppointmentReport(context_key=key,patient_name="FICTIF",examination="Examen fictif",starts_at=record.starts_at,report_date=day.date(),report_text="Rapport fictif à conserver.",radiologist="Dr Test"))
            db.session.add(AppointmentPatientDetails(context_key=key,national_number="00123456789",billing_code="459712"))
        db.session.add(InternalRegisterExclusion(context_key=old_key,is_removed=True,updated_by=1));db.session.commit()
        hold_snapshot=(hold.token,hold.expires_at,hold.draft_data,hold.prescription_filename,hold.prescription_mimetype,hold.prescription_data)
    admin,csrf=authenticate();student,student_csrf=authenticate("student@example.invalid");public=app.test_client()
    payload=dict(csrf_token=csrf,move_token=str(uuid4()),appointment_id=aid,reservation_start="",expected_start=day.isoformat(),expected_key=old_key,target_start=target.isoformat(timespec="minutes"))
    assert public.post(route,data=payload).status_code==302
    assert student.post(route,data=dict(payload,csrf_token=student_csrf)).status_code==403
    assert admin.post(route,data={}).status_code==400
    for bad,status in ((dict(target_start=thu.isoformat()),409),(dict(target_start=(thu+timedelta(minutes=10)).isoformat()),409),(dict(target_start=(day+timedelta(days=1)).isoformat()),409),(dict(target_start=day.isoformat()),400),(dict(target_start="2000-01-01T18:30"),400),(dict(expected_key="0"*64),409),(dict(appointment_id=999999),404)):
        response=admin.post(route,data=dict(payload,**bad));assert response.status_code==status,(bad,response.status_code,response.data)
    duplicate_client,duplicate_csrf=authenticate()
    with ThreadPoolExecutor(max_workers=2) as pool:
        duplicates=list(pool.map(lambda pair:pair[0].post(route,data=pair[1]),[(admin,payload),(duplicate_client,dict(payload,csrf_token=duplicate_csrf))]))
    assert any(result.status_code==200 for result in duplicates)
    assert all(result.status_code in {200,503} for result in duplicates),[result.data for result in duplicates]
    moved=admin.post(route,data=payload);assert moved.status_code==200,moved.data
    with app.app_context():
        record=db.session.get(Appointment,aid);new_key=appointment_report_key(record)
        assert record.starts_at==target and record.id==aid and record.created_at is not None
        assert record.prescription_data==scan and record.patient_email=="private@example.invalid" and record.patient_phone=="TEST"
        assert record.insurance_status=="bim" and record.notes=="Texte privé fictif" and record.inami_invoice_total_cents==10295
        assert db.session.get(AppointmentPatientDetails,old_key) is None
        assert db.session.get(AppointmentPatientDetails,new_key).national_number=="00123456789"
        assert db.session.get(AppointmentPatientDetails,new_key).billing_code=="459712"
        report=AppointmentReport.query.filter_by(context_key=new_key).one()
        assert report.report_text=="Rapport fictif à conserver." and report.report_date==day.date() and report.radiologist=="Dr Test" and report.starts_at==target
        assert db.session.get(InternalRegisterExclusion,new_key).is_removed is True
        assert AppointmentHold.query.count()==1 and AppointmentMoveReceipt.query.count()==1
        assert bookable_appointment_slots(day.date())[:2]==(day,day+timedelta(minutes=10))
    assert admin.post(route,data=payload).status_code==200  # Lost response retry is idempotent.
    assert admin.post(route,data=dict(payload,target_start=target.replace(minute=30).isoformat())).status_code==409
    assert admin.post(route,data=dict(payload,move_token=str(uuid4()),target_start=target.replace(minute=30).isoformat())).status_code==409
    for value in ("PATIENT FICTIF","00123456789","private@example.invalid","Rapport fictif","Texte privé fictif"):
        assert value not in public.get("/agenda?date="+day.date().isoformat()).text
    next_payload=dict(payload,move_token=str(uuid4()),expected_start=target.isoformat(),expected_key=new_key,target_start=target.replace(minute=30).isoformat())
    with patch.object(db.session,"commit",side_effect=OperationalError("test",{},Exception("offline"))):
        assert admin.post(route,data=next_payload).status_code==503
    with app.app_context():
        assert db.session.get(Appointment,aid).starts_at==target and AppointmentHold.query.count()==1 and AppointmentMoveReceipt.query.count()==1
        assert db.session.get(AppointmentPatientDetails,new_key).national_number=="00123456789"
    # Two independent admin sessions race for an overlapping destination. Only
    # one may commit; a transient SQLite lock is retryable and cannot overwrite.
    other,other_csrf=authenticate()
    with app.app_context(): bkey=appointment_report_key(db.session.get(Appointment,bid))
    race_time=thu.replace(hour=20,minute=0)
    one=dict(next_payload,target_start=race_time.isoformat())
    two=dict(payload,csrf_token=other_csrf,move_token=str(uuid4()),appointment_id=bid,expected_start=thu.isoformat(),expected_key=bkey,target_start=race_time.isoformat())
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda pair: pair[0].post(route,data=pair[1]),[(admin,one),(other,two)]))
    assert sorted(result.status_code for result in outcomes) in ([200,409],[200,503]),[result.data for result in outcomes]
    loser=0 if outcomes[0].status_code!=200 else 1
    assert (admin if loser==0 else other).post(route,data=(one if loser==0 else two)).status_code==409
    with app.app_context():
        assert Appointment.query.filter_by(starts_at=race_time).count()==1
        assert Appointment.query.count()==2 and AppointmentHold.query.count()==1
        assert AppointmentReport.query.count()==2 and AppointmentPatientDetails.query.count()==2
    # Move a persistent reservation with its attachment, draft, token and report.
    hold_target=thu.replace(hour=19,minute=40)
    hold_payload=dict(csrf_token=csrf,move_token=str(uuid4()),appointment_id="",reservation_start=(thu+timedelta(minutes=10)).isoformat(),expected_start=(thu+timedelta(minutes=10)).isoformat(),expected_key=hold_key,target_start=hold_target.isoformat())
    response=admin.post(route,data=hold_payload);assert response.status_code==200,response.data
    assert admin.post(route,data=hold_payload).status_code==200
    with app.app_context():
        record=db.session.get(AppointmentHold,hold_target);key=appointment_report_key(record)
        assert (record.token,record.expires_at,record.draft_data,record.prescription_filename,record.prescription_mimetype,record.prescription_data)==hold_snapshot
        assert db.session.get(AppointmentHold,thu+timedelta(minutes=10)) is None
        assert AppointmentReport.query.filter_by(context_key=key).one().report_text=="Rapport fictif à conserver."
        assert db.session.get(AppointmentPatientDetails,key).national_number=="00123456789"
        assert AppointmentHold.query.count()==1
        demo=Appointment(starts_at=day.replace(hour=19,minute=10),patient_name="PATIENT DEMONSTRATION",patient_email="",appointment_type="459712")
        db.session.add(demo);db.session.commit()
    fragment=admin.get("/admin/appointments?date="+day.date().isoformat()+"&fragment=calendar").json
    assert "patient_list_html" in fragment and "day_summary_html" in fragment and 'data-move-card' in fragment["html"]
    print("PASS: atomic appointment/reservation moves, all patient/document/report/billing data preserved, context/exclusion migration, stale requests, race protection, idempotency, rollback, privacy and refreshed lists.",flush=True)
    if "--serve" in sys.argv:
        print("Synthetic preview date:",day.date().isoformat(),flush=True)
        app.run(host="127.0.0.1",port=5057,debug=False)
finally:
    with app.app_context():db.session.remove();db.engine.dispose()
    fixture.cleanup()
