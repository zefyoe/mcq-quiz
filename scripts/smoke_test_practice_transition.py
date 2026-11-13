"""Closure and clean WIRC deployment checks, using temporary databases only."""
import io
import os
import subprocess
import sys
import tempfile
import re
from datetime import timedelta
from pathlib import Path

fixture=tempfile.TemporaryDirectory(prefix="practice-transition-")
wirc="--wirc" in sys.argv
uri="sqlite:///"+str(Path(fixture.name)/"preview.db")
os.environ.update(SECRET_KEY="transition-preview-only",PUBLIC_SITE_MODE="active",
    PRACTICE_PROFILE="wirc" if wirc else "legacy",APPOINTMENT_BOOKING_ENABLED="0",
    APPOINTMENT_PRACTICE_ADDRESS="Adresse fictive WIRC" if wirc else "")
if wirc:
    os.environ.update(WIRC_DATABASE_URL=uri,DATABASE_URL=os.environ.get("TEST_LEGACY_DATABASE_URL","sqlite:///unused-former.db"))
else:
    os.environ["DATABASE_URL"]=uri
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app, db, agenda_now, build_database_uri, appointment_slot_is_open
from models import User, Appointment, AppointmentHold, AppointmentReport, AppointmentPatientDetails, HistoricalDossier, GmailConnection
from practice_settings import PRACTICE_NAME
from radiology_report import create_radiology_report_pdf
from appointment_confirmation import create_appointment_confirmation_pdf
from pypdf import PdfReader

app.config["TESTING"]=True
day=(agenda_now()+timedelta(days=14)).replace(hour=18,minute=30,second=0,microsecond=0)
day+=timedelta(days=(1-day.weekday())%7)
try:
    with app.app_context():
        db.create_all()
        if wirc:
            assert build_database_uri()==uri
            for model in (User,Appointment,AppointmentHold,AppointmentReport,AppointmentPatientDetails,HistoricalDossier,GmailConnection):
                assert model.query.count()==0,model.__name__
        user=User(email="y@bymed.be",is_admin=True);user.set_password("test-password");db.session.add(user)
        if not wirc:
            db.session.add(Appointment(starts_at=day,patient_name="PATIENT ARCHIVE FICTIF",patient_email="",appointment_type="459712",prescription_data=b"ORIGINAL-FICTIF"))
        db.session.commit()
    public=app.test_client();base="https://wirc.be" if wirc else "https://bymed.be"
    page=public.get("/agenda",base_url=base)
    assert page.status_code==200 and '<html lang="fr">' in page.text
    assert "temporairement fermé" in page.text and "La prise de rendez-vous est suspendue" in page.text
    assert "2027" not in page.text and "Gaillait" not in page.text and "Pavillon" not in page.text
    assert "data-slot=" not in page.text and "<form" not in page.text
    assert "PATIENT ARCHIVE" not in page.text and page.headers["Cache-Control"]=="private, no-store"
    if not wirc:
        assert "wirc.be" not in page.text.lower() and "Woluwe" not in page.text and "Location" not in page.headers
    for route in ("/agenda/hold","/agenda/draft","/agenda/book"):
        response=public.post(route,base_url=base,data={"slot_start":day.isoformat(),"patient_name":"STALE FORM"})
        assert response.status_code==423 and response.json["ok"] is False
        assert "temporairement fermé" in response.json["error"]
    assert public.get("/health",base_url=base).json=={"status":"ok"}
    admin=app.test_client()
    login=admin.post("/login",base_url=base,data={"email":"y@bymed.be","password":"test-password"})
    assert login.status_code==302
    internal=admin.get("/admin/appointments?date="+day.date().isoformat(),base_url=base)
    assert internal.status_code==200 and "Agenda interne" in internal.text
    if wirc:
        assert "WIRC" in internal.text and "PATIENT ARCHIVE" not in internal.text
        assert PRACTICE_NAME in public.get("/login",base_url=base).text
        for route in ("/anatomy","/core","/register","/admin/database","/admin/users","/admin/payments"):
            assert admin.get(route,base_url=base).status_code==404,route
        assert public.get("/",base_url=base).headers["Location"]=="/agenda"
        assert admin.get("/",base_url=base).headers["Location"]=="/admin/appointments"
        with app.test_request_context(base_url=base):
            assert app.session_interface.get_cookie_domain(app) is None
        # Distinct setting is required, including when old DATABASE_URL exists.
        with __import__('unittest.mock',fromlist=['patch']).patch.dict(os.environ,{"WIRC_DATABASE_URL":""}):
            try: build_database_uri()
            except RuntimeError: pass
            else: raise AssertionError("WIRC silently fell back to the former database")
        pdf=create_radiology_report_pdf(patient_name="PATIENT FICTIF WIRC",examination="Examen fictif",starts_at=day,
            report_date=day.date(),report_text="Rapport fictif.",radiologist="Dr Test",practice_address="Adresse fictive WIRC")
        report=PdfReader(io.BytesIO(pdf));text="\n".join(p.extract_text() for p in report.pages)
        assert PRACTICE_NAME in text and "Gaillait" not in text and "BYMED" not in text
        confirmation=PdfReader(io.BytesIO(create_appointment_confirmation_pdf(patient_name="PATIENT FICTIF WIRC",starts_at=day,
            examination="Examen fictif",practice_address="Adresse fictive WIRC")))
        assert "WIRC" in confirmation.pages[0].extract_text() and confirmation.metadata.author==PRACTICE_NAME
        # WIRC opens Thursday mornings, with the existing two-adjacent-slot
        # policy and ten-minute visits. Other former practice hours stay shut.
        thursday=(day+timedelta(days=2)).replace(hour=8,minute=0)
        with app.app_context():
            assert all(appointment_slot_is_open(thursday+timedelta(minutes=10*i)) for i in range(24))
            assert not appointment_slot_is_open(thursday.replace(hour=12))
            assert not appointment_slot_is_open(day)
            assert not appointment_slot_is_open(day+timedelta(days=4))
        app.config["APPOINTMENT_BOOKING_ENABLED"]=True
        # WIRC starts on 3 December. Neither crafted requests nor an explicit
        # older-week URL may book the earlier Thursday, even with an override.
        from datetime import datetime
        from unittest.mock import patch
        from models import AppointmentSlotOverride
        with patch('app.agenda_now',return_value=datetime(2026,11,14,9,0)):
            assert '2026-12-03T08:00' in public.get('/agenda',base_url=base).text
            assert 'value="2026-12-03"' in admin.get('/admin/appointments',base_url=base).text
        early=datetime(2026,11,26,8,0)
        with app.app_context():
            db.session.add(AppointmentSlotOverride(starts_at=early,is_open=True));db.session.commit()
            assert not appointment_slot_is_open(early)
            db.session.delete(db.session.get(AppointmentSlotOverride,early));db.session.commit()
        early_page=public.get('/agenda?date=2026-11-26',base_url=base)
        assert 'data-slot=' not in early_page.text and 'data-slot-choice=' not in early_page.text
        early_csrf=re.search(r'name="csrf_token" value="([^"]+)"',early_page.text)[1]
        assert public.post('/agenda/book',base_url=base,data=dict(csrf_token=early_csrf,
            slot_start=early.isoformat(),patient_name='Patient Trop Tot',inami_code='459712')).status_code==400
        opened=public.get("/agenda?date="+thursday.date().isoformat(),base_url=base)
        assert opened.status_code==200 and 'Choisissez une disponibilité' in opened.text
        assert re.findall(r'data-slot="([^"]+)"',opened.text)==[
            thursday.isoformat(timespec="minutes"),(thursday+timedelta(minutes=10)).isoformat(timespec="minutes")]
        assert 'Adresse fictive WIRC' in opened.text and '18:30' not in opened.text
        assert 'Gaillait' not in opened.text and 'Pavillon' not in opened.text
        assert 'Woluwe Imaging Radiology' in opened.text
        assert 'Premières consultations' not in opened.text and '<aside class="agenda-rail"' not in opened.text
        assert 'Après-midi' in opened.text and '12:00–20:00' in opened.text
        # An exceptional afternoon opened internally must never be labelled shut.
        afternoon=thursday.replace(hour=13)
        with app.app_context():
            db.session.add(AppointmentSlotOverride(starts_at=afternoon,is_open=True));db.session.commit()
        assert '12:00–20:00' not in public.get('/agenda?date='+thursday.date().isoformat(),base_url=base).text
        with app.app_context():
            db.session.delete(db.session.get(AppointmentSlotOverride,afternoon));db.session.commit()
        assert 'name="insurance_status"' not in opened.text
        assert 'name="insurance_status"' not in internal.text
        assert re.findall(r'data-slot-choice="([^"]+)"',opened.text)==re.findall(r'data-slot="([^"]+)"',opened.text)
        csrf=re.search(r'name="csrf_token" value="([^"]+)"',opened.text)[1]
        booked=public.post('/agenda/book',base_url=base,data=dict(csrf_token=csrf,slot_start=thursday.isoformat(),
            patient_name='PATIENT FICTIF WIRC',inami_code='459712'))
        assert booked.status_code==200 and booked.mimetype=='application/pdf'
        assert 'Adresse fictive WIRC' in PdfReader(io.BytesIO(booked.data)).pages[0].extract_text()
        assert 'PATIENT FICTIF WIRC' not in public.get('/agenda?date='+thursday.date().isoformat(),base_url=base).text
        with app.app_context():
            record=Appointment.query.one();assert record.starts_at==thursday and record.duration_minutes==10
            assert record.insurance_status is None
            db.session.delete(record);db.session.commit()
            # The one-time credential transfer preserves password hashes only
            # for the two allowlisted admins, rejects other users, and is safe
            # to repeat. Patient records and Gmail connections stay empty.
            from scripts.transfer_practice_admins import import_accounts,PURPOSE
            from cryptography.fernet import Fernet
            import json
            key=Fernet.generate_key();cipher=Fernet(key)
            original_hash=User.query.filter_by(email='y@bymed.be').one().password_hash
            def envelope(accounts):
                return cipher.encrypt(json.dumps(dict(purpose=PURPOSE,accounts=accounts)).encode()).decode()
            accounts=[dict(email=email,password_hash=original_hash) for email in ('y@bymed.be','ybahkani@gmail.com')]
            try:
                import_accounts(key,envelope([dict(email='unapproved@example.invalid',password_hash=original_hash)]))
            except ValueError: pass
            else: raise AssertionError('Unapproved account was imported')
            assert import_accounts(key,envelope(accounts))==['y@bymed.be','ybahkani@gmail.com']
            assert import_accounts(key,envelope(accounts))==['y@bymed.be','ybahkani@gmail.com']
            assert User.query.count()==2 and all(u.check_password('test-password') and u.is_admin for u in User.query.all())
            assert GmailConnection.query.count()==0 and Appointment.query.count()==0
    else:
        assert "PATIENT ARCHIVE FICTIF" in internal.text
    with app.app_context():
        assert Appointment.query.count()==(0 if wirc else 1)
        assert AppointmentHold.query.count()==0 and AppointmentReport.query.count()==0
        if not wirc:
            assert Appointment.query.one().prescription_data==b"ORIGINAL-FICTIF"
    print("PASS: "+("isolated empty WIRC database, French branding/PDFs, host-only sessions and agenda-only routes" if wirc else "French closure without date/link/redirect, blocked stale booking writes and intact internal records"),flush=True)
    if not wirc and "--serve" not in sys.argv:
        result=subprocess.run([sys.executable,__file__,"--wirc"],env=dict(os.environ,TEST_LEGACY_DATABASE_URL=uri))
        assert result.returncode==0
        with app.app_context():assert Appointment.query.one().patient_name=="PATIENT ARCHIVE FICTIF"
    if "--serve" in sys.argv:
        app.run(host="127.0.0.1",port=5058,debug=False)
finally:
    with app.app_context():db.session.remove();db.engine.dispose()
    fixture.cleanup()
