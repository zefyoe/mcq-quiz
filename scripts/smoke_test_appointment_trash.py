"""Disposable checks for recoverable agenda removal; never uses real patients."""
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

fixture=tempfile.TemporaryDirectory(prefix="appointment-trash-tests-")
os.environ.update(DATABASE_URL="sqlite:///"+str(Path(fixture.name)/"test.db"),SECRET_KEY="trash-tests-only",PUBLIC_SITE_MODE="active",APPOINTMENT_BOOKING_ENABLED="1")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app, db, agenda_now, appointment_report_key, bookable_appointment_slots
from models import User, Appointment, AppointmentHold, AppointmentReport, AppointmentPatientDetails, InternalRegisterExclusion, AppointmentTrash
from sqlalchemy.exc import OperationalError

app.config["TESTING"]=True
day=(agenda_now()+timedelta(days=14)).replace(hour=18,minute=30,second=0,microsecond=0)
day+=timedelta(days=(1-day.weekday())%7)
route="/admin/appointments/trash"
scan=b"%PDF-1.4 synthetic original request"
def authenticate(email="y@bymed.be"):
    client=app.test_client();client.post("/login",data={"email":email,"password":"test-password"})
    client.get("/agenda?date="+day.date().isoformat())
    client.get("/admin/appointments?date="+day.date().isoformat())
    with client.session_transaction() as session: csrf=session["agenda_token"]
    return client,csrf
def payload_for(record,csrf):
    return dict(csrf_token=csrf,move_token=str(uuid4()),appointment_id=record.id if isinstance(record,Appointment) else "",
        reservation_start="" if isinstance(record,Appointment) else record.starts_at.isoformat(),expected_start=record.starts_at.isoformat(),expected_key=appointment_report_key(record))
def assert_free(client,start):
    fragment=client.get("/admin/appointments?date="+day.date().isoformat()+"&fragment=calendar").json
    cell=fragment["html"].split('data-start="'+start.isoformat(timespec="minutes")+'"',1)[1].split('</div>',1)[0]
    assert 'data-drop-state="free"' in cell and 'data-move-card' not in cell
try:
    with app.app_context():
        db.create_all()
        for email,role in (("y@bymed.be",True),("student@example.invalid",False)):
            user=User(email=email,is_admin=role);user.set_password("test-password");db.session.add(user)
        appointment=Appointment(starts_at=day,patient_name="PATIENT FICTIF",patient_email="private@example.invalid",patient_phone="PRIVATE",insurance_status="bim",
            appointment_type="459712",inami_code="459712",inami_invoice_total_cents=12345,duration_minutes=20,prescription_filename="original.pdf",prescription_mimetype="application/pdf",prescription_data=scan)
        hold=AppointmentHold(starts_at=day+timedelta(minutes=40),token="persistent-owner",expires_at=day+timedelta(days=365),
            draft_data=json.dumps({"patient_name":"RESERVATION FICTIVE","insurance_status":"bim","inami_code":"459712"}),prescription_filename="original.pdf",prescription_mimetype="application/pdf",prescription_data=scan)
        legacy=AppointmentHold(starts_at=day,token="legacy-empty-lock",expires_at=day+timedelta(days=365))
        db.session.add_all([appointment,hold,legacy]);db.session.flush();aid=appointment.id
        akey=appointment_report_key(appointment);hkey=appointment_report_key(hold)
        for record,key in ((appointment,akey),(hold,hkey)):
            db.session.add(AppointmentReport(context_key=key,patient_name="FICTIF",examination="Examen fictif",starts_at=record.starts_at,report_date=day.date(),report_text="Rapport privé fictif",radiologist="Dr Test"))
            db.session.add(AppointmentPatientDetails(context_key=key,national_number="00123456789",billing_code="459712"))
        db.session.add(InternalRegisterExclusion(context_key=akey,is_removed=True,updated_by=1));db.session.commit()
        acreated=appointment.created_at
        apayload=payload_for(appointment,"");hpayload=payload_for(hold,"")
        original_hold=(hold.token,hold.expires_at,hold.draft_data)
    admin,csrf=authenticate();other,other_csrf=authenticate();student,student_csrf=authenticate("student@example.invalid");public=app.test_client()
    apayload["csrf_token"]=csrf;hpayload["csrf_token"]=csrf
    assert public.get(route).status_code==302 and student.get(route).status_code==403
    assert student.post(route,data=dict(apayload,csrf_token=student_csrf)).status_code==403
    assert admin.post(route,data={}).status_code==400
    assert admin.post(route,data=dict(apayload,expected_key="0"*64)).status_code==409
    assert admin.post(route,data=dict(apayload,move_token="bad")).status_code==400
    with patch.object(db.session,"commit",side_effect=OperationalError("test",{},Exception("offline"))):
        assert admin.post(route,data=apayload).status_code==503
    with app.app_context():
        assert db.session.get(Appointment,aid) is not None and db.session.get(AppointmentHold,day) is not None
        assert AppointmentTrash.query.count()==0
    # Identical concurrent deliveries must produce one archived booking only.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda pair:pair[0].post(route,data=pair[1]),[(admin,apayload),(other,dict(apayload,csrf_token=other_csrf))]))
    assert any(result.status_code==200 for result in results)
    assert all(result.status_code in {200,503} for result in results),[r.data for r in results]
    assert admin.post(route,data=apayload).status_code==200
    assert admin.post(route,data=dict(apayload,expected_key="0"*64)).status_code==409
    with app.app_context():
        assert db.session.get(Appointment,aid) is None and db.session.get(AppointmentHold,day) is None
        assert AppointmentTrash.query.count()==1
        assert db.session.get(AppointmentTrash,apayload["move_token"]).prescription_data==scan
        assert AppointmentReport.query.filter_by(context_key=akey).one().report_text=="Rapport privé fictif"
        assert db.session.get(AppointmentPatientDetails,akey).national_number=="00123456789"
        assert bookable_appointment_slots(day.date())[:2]==(day,day+timedelta(minutes=10))
    assert_free(admin,day);assert_free(admin,day+timedelta(minutes=10))
    items=admin.get(route).json["items"]
    assert len(items)==1 and items[0]["patient_name"]=="PATIENT FICTIF"
    for private in ("PATIENT FICTIF","private@example.invalid","00123456789","Rapport privé fictif"):
        assert private not in public.get("/agenda?date="+day.date().isoformat()).text
    restore=route+"/"+apayload["move_token"]+"/restore"
    assert student.post(restore,data={"csrf_token":student_csrf}).status_code==403
    assert admin.post(restore,data={}).status_code==400
    # Restoring may not replace another appointment or overlap its duration.
    with app.app_context():
        blocker=Appointment(id=aid,starts_at=day+timedelta(minutes=10),patient_name="AUTRE PATIENT",patient_email="",appointment_type="459712")
        db.session.add(blocker);db.session.commit()
    assert admin.post(restore,data={"csrf_token":csrf}).status_code==409
    with app.app_context():
        assert db.session.get(Appointment,aid).patient_name=="AUTRE PATIENT"
        # Keep the reused id occupied, at a different hour, during restoration.
        db.session.get(Appointment,aid).starts_at=day+timedelta(minutes=70);db.session.commit()
    assert admin.post(restore,data={"csrf_token":csrf}).status_code==200
    assert admin.post(restore,data={"csrf_token":csrf}).status_code==200
    assert admin.post(route,data=apayload).status_code==409 # old retry cannot re-delete restored record
    with app.app_context():
        restored=Appointment.query.filter_by(patient_name="PATIENT FICTIF").one();new_key=appointment_report_key(restored)
        assert restored.id!=aid and restored.created_at==acreated and restored.starts_at==day and restored.duration_minutes==20
        assert restored.prescription_data==scan and restored.insurance_status=="bim" and restored.inami_invoice_total_cents==12345
        assert restored.patient_email=="private@example.invalid" and restored.patient_phone=="PRIVATE"
        assert AppointmentReport.query.filter_by(context_key=new_key).one().report_text=="Rapport privé fictif"
        assert db.session.get(AppointmentPatientDetails,new_key).national_number=="00123456789"
        assert db.session.get(AppointmentPatientDetails,new_key).billing_code=="459712"
        assert db.session.get(InternalRegisterExclusion,new_key).is_removed is True
        assert db.session.get(AppointmentPatientDetails,akey) is None
        assert AppointmentHold.query.count()==1
    assert admin.get(route).json["items"]==[]
    # Reservations retain their exact original draft, token, request and report.
    assert admin.post(route,data=hpayload).status_code==200
    assert admin.post(route,data=hpayload).status_code==200
    assert_free(admin,day+timedelta(minutes=40))
    hrestore=route+"/"+hpayload["move_token"]+"/restore"
    with patch.object(db.session,"commit",side_effect=OperationalError("test",{},Exception("offline"))):
        assert admin.post(hrestore,data={"csrf_token":csrf}).status_code==503
    assert len(admin.get(route).json["items"])==1
    assert admin.post(hrestore,data={"csrf_token":csrf}).status_code==200
    with app.app_context():
        restored=db.session.get(AppointmentHold,day+timedelta(minutes=40))
        assert (restored.token,restored.expires_at,restored.draft_data)==original_hold and restored.prescription_data==scan
        assert AppointmentReport.query.filter_by(context_key=hkey).one().report_text=="Rapport privé fictif"
        assert db.session.get(AppointmentPatientDetails,hkey).national_number=="00123456789"
        assert AppointmentHold.query.count()==1 and AppointmentTrash.query.filter_by(restored_at=None).count()==0
    print("PASS: recoverable appointment/reservation trash, legacy source release, full private data/document preservation, id reuse, overlapping restore protection, CSRF/admin/privacy, rollback, concurrent retries and idempotency.",flush=True)
finally:
    with app.app_context():db.session.remove();db.engine.dispose()
    fixture.cleanup()
