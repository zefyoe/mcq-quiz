"""Disposable schedule exceptions: admin control, public availability and privacy."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

fixture = tempfile.TemporaryDirectory(prefix="schedule-exception-tests-")
os.environ.update(DATABASE_URL="sqlite:///"+str(Path(fixture.name)/"test.db"), SECRET_KEY="schedule-tests-only", PUBLIC_SITE_MODE="active")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app, db, agenda_now, appointment_slot_is_open, bookable_appointment_slots
from models import User, Appointment, AppointmentHold, AppointmentSlotOverride
from sqlalchemy.exc import OperationalError

app.config["TESTING"]=True
wed=(agenda_now()+timedelta(days=14)).replace(hour=10,minute=0,second=0,microsecond=0)
wed+=timedelta(days=(2-wed.weekday())%7)
thu=wed+timedelta(days=1)
sat=wed+timedelta(days=3)
day_url="/admin/appointments/internal/availability/day"
slot_url="/admin/appointments/internal/availability"
try:
    with app.app_context():
        db.create_all()
        for email,role in (("y@bymed.be",True),("student@example.invalid",False)):
            user=User(email=email,is_admin=role);user.set_password("test-password");db.session.add(user)
        db.session.add(Appointment(starts_at=thu.replace(hour=18,minute=40),patient_name="PATIENT PRIVE",patient_email="private@example.invalid",appointment_type="459712",insurance_status="bim",notes="note confidentielle"))
        db.session.add(AppointmentHold(starts_at=thu.replace(hour=18,minute=50),token="private-hold",expires_at=thu,
            draft_data=json.dumps({"patient_name":"RESERVATION PRIVEE","inami_code":"459712","insurance_status":"bim"})))
        db.session.commit()
    admin,student,public=app.test_client(),app.test_client(),app.test_client()
    for client,email in ((admin,"y@bymed.be"),(student,"student@example.invalid")):
        client.post("/login",data={"email":email,"password":"test-password"})
    initial=admin.get("/admin/appointments?date="+wed.date().isoformat())
    assert initial.status_code==200
    assert b'day-hours-dialog' in initial.data
    with admin.session_transaction() as session: csrf=session["agenda_token"]
    data=dict(csrf_token=csrf,day=wed.date().isoformat(),action="replace",start_time="10:00",end_time="12:00")
    for route in (day_url,slot_url):
        assert public.post(route,data=data).status_code==302
        assert student.post(route,data=data).status_code==403
        assert admin.post(route,data={}).status_code==400
    for invalid in (dict(start_time="12:00",end_time="10:00"),dict(start_time="10:05"),dict(end_time="22:00"),dict(day="invalid"),dict(day="2000-01-01"),dict(action="unknown")):
        assert admin.post(day_url,data=dict(data,**invalid)).status_code==400
    with app.app_context(): assert not appointment_slot_is_open(wed)
    opened=admin.post(day_url,data=data)
    assert opened.status_code==200,opened.data
    assert opened.json["scope"]=="shared" and len(opened.json["changed_slots"])==12
    assert admin.post(day_url,data=data).json["changed_slots"]==[]
    with app.app_context():
        assert appointment_slot_is_open(wed)
        assert bookable_appointment_slots(wed.date())==(wed,wed+timedelta(minutes=10))
    public_page=public.get("/agenda?date="+wed.date().isoformat())
    assert wed.isoformat(timespec="minutes").encode() in public_page.data
    closed=admin.post(day_url,data=dict(csrf_token=csrf,day=thu.date().isoformat(),action="close"))
    assert closed.status_code==200 and closed.json["protected_count"]==2
    with app.app_context(): assert bookable_appointment_slots(thu.date())==()
    # Authenticated JSON refresh supplies new day cells and compact columns.
    fragment=admin.get("/admin/appointments?date="+wed.date().isoformat()+"&fragment=calendar")
    assert fragment.is_json and fragment.status_code==200
    assert f'data-slot="{wed.isoformat(timespec="minutes")}"' in fragment.json["html"]
    assert "PATIENT PRIVE" in fragment.json["html"] and "RESERVATION PRIVEE" in fragment.json["html"]
    assert public.get("/admin/appointments?fragment=calendar").status_code==302
    # A private manual booking on the exceptional day needs no email.
    booked=admin.post("/admin/appointments/book",data=dict(csrf_token=csrf,slot_start=wed.isoformat(timespec="minutes"),week_date=wed.date().isoformat(),patient_name="NOUVEAU PATIENT",inami_code="459712"))
    assert booked.status_code==302 and "error=" not in booked.location,booked.location
    with app.app_context():
        assert Appointment.query.filter_by(starts_at=wed).one().patient_email==""
        assert bookable_appointment_slots(wed.date())==(wed+timedelta(minutes=10),wed+timedelta(minutes=20))
    assert admin.post(slot_url,data=dict(csrf_token=csrf,slot_start=wed.isoformat(timespec="minutes"),is_open="0")).status_code==409
    for text in ("PATIENT PRIVE","RESERVATION PRIVEE","NOUVEAU PATIENT","private@example.invalid","note confidentielle"):
        assert text not in public.get("/agenda?date="+wed.date().isoformat()).text, text
    # Exceptions override the normal Saturday cutoff and previously fixed slots.
    custom=dict(csrf_token=csrf,day=sat.date().isoformat(),action="open",start_time="14:00",end_time="15:00")
    assert admin.post(day_url,data=custom).status_code==200
    with app.app_context(): assert appointment_slot_is_open(sat.replace(hour=14))
    early=thu.replace(hour=18,minute=10)
    assert admin.post(slot_url,data=dict(csrf_token=csrf,slot_start=early.isoformat(timespec="minutes"),is_open="1")).status_code==200
    with app.app_context(): assert appointment_slot_is_open(early)
    # Validation/DB failures don't leave a partial replacement applied.
    with app.app_context(): before_count=AppointmentSlotOverride.query.count()
    with patch.object(db.session,"commit",side_effect=OperationalError("test",{},Exception("offline"))):
        assert admin.post(day_url,data=dict(data,start_time="09:00",end_time="11:00")).status_code==503
    with app.app_context():
        assert AppointmentSlotOverride.query.count()==before_count
        assert not appointment_slot_is_open(wed.replace(hour=9))
    assert admin.post(day_url,data=dict(csrf_token=csrf,day=sat.date().isoformat(),action="reset")).status_code==200
    with app.app_context():
        assert not appointment_slot_is_open(sat.replace(hour=14))
        assert Appointment.query.count()==2 and AppointmentHold.query.count()==1
    # The quick Open button also works on a Wednesday with no existing hours,
    # and a patient can actually book the published opening.
    quick=wed+timedelta(days=7)
    opened=admin.post(day_url,data=dict(csrf_token=csrf,day=quick.date().isoformat(),action="open"))
    assert opened.status_code==200 and len(opened.json["changed_slots"])==10
    public.get("/agenda?date="+quick.date().isoformat())
    with public.session_transaction() as session: patient_csrf=session["agenda_token"]
    stamp=quick.replace(hour=18,minute=30)
    confirmed=public.post("/agenda/book",data=dict(csrf_token=patient_csrf,slot_start=stamp.isoformat(timespec="minutes"),
        patient_name="PATIENT EXTERNE",inami_code="459712",insurance_status="normal"))
    assert confirmed.status_code==200 and confirmed.data.startswith(b"%PDF-"),confirmed.data
    assert admin.post(day_url,data=dict(csrf_token=csrf,day=quick.date().isoformat(),action="close")).status_code==200
    with app.app_context():
        assert bookable_appointment_slots(quick.date())==()
        assert Appointment.query.filter_by(starts_at=stamp).one().patient_name=="PATIENT EXTERNE"
        assert Appointment.query.count()==3 and AppointmentHold.query.count()==1
    assert "PATIENT EXTERNE" not in public.get("/agenda?date="+quick.date().isoformat()).text
    print("PASS: exceptional Wednesday opening, Thursday closure, custom ranges/cutoffs, reset, protected bookings, no-email manual booking, live calendar fragment, public two-slot policy/privacy, permissions/CSRF, retries and rollback.",flush=True)
    if "--serve" in sys.argv:
        print("Synthetic preview date:",wed.date().isoformat(),flush=True)
        app.run(host="127.0.0.1",port=5057,debug=False)
finally:
    with app.app_context():db.session.remove();db.engine.dispose()
    fixture.cleanup()
