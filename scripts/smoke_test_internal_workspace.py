"""Isolated integration checks; never touches the practice database or sends mail."""
import io
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

fd, database_path = tempfile.mkstemp(prefix="internal-workspace-", suffix=".db")
os.close(fd)
os.environ.update(DATABASE_URL="sqlite:///" + database_path, SECRET_KEY="workspace-tests-only", PUBLIC_SITE_MODE="active",APPOINTMENT_BOOKING_ENABLED="1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app, db, appointment_report_key, ensure_appointment_schema
from models import Appointment, AppointmentHold, AppointmentReport, AppointmentSlotOverride, AppointmentPatientDetails, User
from pypdf import PdfWriter
from sqlalchemy.exc import OperationalError

app.config["TESTING"] = True
pdf_buffer = io.BytesIO()
writer = PdfWriter(); writer.add_blank_page(width=595, height=842); writer.write(pdf_buffer)
pdf_bytes = pdf_buffer.getvalue()
day = (datetime.now() + timedelta(days=14)).replace(hour=18, minute=30, second=0, microsecond=0)
day += timedelta(days=(1-day.weekday()) % 7)
date_string = day.date().isoformat()

try:
    with app.app_context():
        db.create_all(); ensure_appointment_schema()
        for email, admin in [("y@bymed.be", True), ("student@example.invalid", False)]:
            user = User(email=email, is_admin=admin); user.set_password("test-password"); db.session.add(user)
        appointment = Appointment(starts_at=day, patient_name="PATIENT FICTIF", patient_email="", appointment_type="459712", inami_code="459712")
        second = Appointment(starts_at=day+timedelta(minutes=30), patient_name="AUTRE FICTIF", patient_email="", appointment_type="459712")
        db.session.add_all([appointment, second]); db.session.commit(); aid, second_id = appointment.id, second.id
        hold = AppointmentHold(starts_at=day+timedelta(minutes=10), token="reserved", expires_at=day,
            draft_data=json.dumps({"patient_name":"RESERVATION FICTIVE", "inami_code":"459712"}))
        db.session.add(hold); db.session.commit()
    admin, student, anonymous = app.test_client(), app.test_client(), app.test_client()
    for client, email in [(admin,"y@bymed.be"), (student,"student@example.invalid")]:
        assert client.post("/login", data={"email":email,"password":"test-password"}).status_code == 302
    page = admin.get("/admin/appointments?date="+date_string)
    assert page.status_code == 200
    for marker in [b'patient-list', b'data-day-action="open"', b'report-drawer', 'Créer un compte rendu'.encode(), b'data-report-action="request"']:
        assert marker in page.data, marker
    with admin.session_transaction() as session:
        csrf = session["agenda_token"]
    context = {"appointment_id":aid}
    payload = dict(context, csrf_token=csrf, revision="0", report_date=date_string, radiologist="Dr Test", report_text="Compte rendu fictif.\nConclusion normale.")
    report_url = "/admin/appointments/report"
    patient_url = "/admin/appointments/patient"
    upload_url = patient_url + "/prescription"
    for url in [report_url, patient_url, upload_url]:
        assert anonymous.get(url, query_string=context).status_code == 302
        assert student.get(url, query_string=context).status_code == 403
        assert admin.post(url, data=context).status_code == 400
    assert admin.get(report_url, query_string=context).json["report"] is None
    saved = admin.post(report_url, data=payload)
    assert saved.status_code == 200, saved.data
    revision = saved.json["revision"]
    # A retry after a lost response is idempotent, even with the old revision.
    retry = admin.post(report_url, data=payload)
    assert retry.status_code == 200 and retry.json["revision"] == revision
    assert admin.post(report_url, data=dict(payload,report_text="Un autre texte",revision=0)).status_code == 409
    updated = admin.post(report_url, data=dict(payload,report_text="Version mise à jour",revision=revision))
    assert updated.status_code == 200 and updated.json["revision"] > revision
    # A DB outage returns a recoverable JSON error rather than a stuck/HTML editor.
    with patch.object(db.session, "commit", side_effect=OperationalError("test", {}, Exception("offline"))):
        failed = admin.post(report_url, data=dict(payload,report_text="Texte à conserver",revision=updated.json["revision"]))
    assert failed.status_code == 503 and failed.is_json
    assert admin.get(report_url, query_string=context).json["report"]["report_text"] == "Version mise à jour"
    generated = admin.post("/admin/appointments/report/pdf", data=dict(payload,report_text="Version mise à jour"))
    assert generated.status_code == 200 and generated.data.startswith(b"%PDF-")
    assert admin.post(patient_url, data=dict(context,csrf_token=csrf,national_number="123")).status_code == 400
    assert admin.post(patient_url, data=dict(context,csrf_token=csrf,national_number="12.34.56-789.01")).json["national_number"] == "12345678901"
    assert admin.get(patient_url, query_string=context).json["national_number"] == "12345678901"
    def upload(content, name="demande.pdf", ctx=context):
        return admin.post(upload_url, data=dict(ctx,csrf_token=csrf,prescription_file=(io.BytesIO(content),name)), content_type="multipart/form-data")
    assert upload(b"not a pdf").status_code == 400
    assert upload(b"%PDF-1.7\nnot actually a PDF").status_code == 400
    assert upload(b"%PDF-"+b"a"*(10*1024*1024)).status_code == 400
    accepted = upload(pdf_bytes)
    assert accepted.status_code == 200, accepted.data
    prescription = accepted.json["prescription"]
    assert upload(pdf_bytes).status_code == 409
    for key, disposition in [("view_url","inline"), ("download_url","attachment")]:
        response = admin.get(prescription[key]); assert response.data == pdf_bytes
        assert response.headers["Content-Disposition"].startswith(disposition)
        assert response.headers["Cache-Control"] == "private, no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert anonymous.get(prescription[key]).status_code == 302
    hold_context = {"reservation_start": (day+timedelta(minutes=10)).isoformat(timespec="minutes")}
    anonymous.get("/agenda?date="+date_string)
    with anonymous.session_transaction() as session:
        patient_token = session["agenda_token"]
    with app.app_context():
        db.session.get(AppointmentHold, day+timedelta(minutes=10)).token = patient_token
        db.session.commit()
    assert upload(pdf_bytes, ctx=hold_context).status_code == 200
    assert admin.post(patient_url, data=dict(hold_context,csrf_token=csrf,national_number="11111111111")).status_code == 200
    closed = admin.post("/admin/appointments/availability/day", data={"csrf_token":csrf,"day":date_string,"is_open":"0"}, headers={"X-Requested-With":"XMLHttpRequest"})
    assert closed.status_code == 200 and len(closed.json["closed_slots"]) == 7, closed.data
    assert closed.json["protected_count"] == 3
    reopened = admin.post("/admin/appointments/availability/day", data={"csrf_token":csrf,"day":date_string,"is_open":"1"}, headers={"X-Requested-With":"XMLHttpRequest"})
    assert reopened.status_code == 200 and len(reopened.json["opened_slots"]) == 7
    assert all(stamp[11:16] not in ("18:10","18:20") for stamp in reopened.json["opened_slots"])
    with app.app_context():
        assert Appointment.query.count() == 2 and AppointmentHold.query.count() == 1
        assert AppointmentReport.query.count() == 1
        assert AppointmentPatientDetails.query.count() == 2
    public = anonymous.get("/agenda?date="+date_string)
    for private in [b"PATIENT FICTIF", b"12345678901", b"demande.pdf", b"Version mise"]:
        assert private not in public.data
    assert admin.get(patient_url, query_string={"appointment_id":999999}).status_code == 404
    # Report/read-only indicators and private identifiers survive a full reload.
    page = admin.get("/admin/appointments?date="+date_string)
    assert b"12345678901" in page.data and b"Voir le compte rendu" in page.data
    assert b"Voir la demande" in page.data and b"RESERVATION FICTIVE" in page.data
    # Requests, report and identifiers survive reservation -> confirmed booking.
    assert admin.post(report_url, data=dict(payload,appointment_id="",**hold_context,report_text="Rapport de réservation")).status_code == 200
    confirmed = anonymous.post("/agenda/book", data={"csrf_token":patient_token,
        "slot_start":hold_context["reservation_start"],"patient_name":"RESERVATION FICTIVE",
        "inami_code":"459712","insurance_status":"normal"})
    assert confirmed.status_code == 200, confirmed.data
    with app.app_context():
        booked_hold = Appointment.query.filter_by(starts_at=day+timedelta(minutes=10)).one()
        assert booked_hold.prescription_data == pdf_bytes
        assert db.session.get(AppointmentPatientDetails,appointment_report_key(booked_hold)).national_number == "11111111111"
        assert AppointmentReport.query.filter_by(context_key=appointment_report_key(booked_hold)).one().report_text == "Rapport de réservation"
    # The RIZIV overview is truly all-time, not tied to the selected day/week.
    for route in ("/admin/appointments/riziv", "/admin/appointments/riziv.csv"):
        assert anonymous.get(route).status_code == 302
        assert student.get(route).status_code == 403
    with app.app_context():
        old = Appointment(starts_at=day-timedelta(days=60),patient_name="PATIENT FICTIF",patient_email="private@example.invalid",appointment_type="459712",insurance_status="bim")
        future = Appointment(starts_at=day+timedelta(days=70),patient_name="=2+2",patient_email="",appointment_type="459712")
        escaped = Appointment(starts_at=day+timedelta(days=71),patient_name='<img src=x onerror="alert(1)">',patient_email="",appointment_type="459712")
        db.session.add_all([old,future,escaped]); db.session.flush(); old_id, future_id, escaped_id = old.id, future.id, escaped.id
        db.session.add(AppointmentPatientDetails(context_key=appointment_report_key(old),national_number="00123456789"))
        db.session.add(AppointmentHold(starts_at=day-timedelta(days=30),token="historical",expires_at=day,
            draft_data=json.dumps({"patient_name":"RESERVATION HORS SEMAINE","inami_code":"459712"})))
        # A leftover hold at an already confirmed timestamp must not duplicate it.
        db.session.add(AppointmentHold(starts_at=old.starts_at,token="stale",expires_at=day,draft_data='{"patient_name":"DOUBLON CACHE"}'))
        db.session.commit()
    listing = admin.get("/admin/appointments/riziv?date="+date_string)
    assert listing.status_code == 200 and listing.json["total"] == 7
    assert listing.headers["Cache-Control"] == "private, no-store"
    html = listing.json["html"]
    assert html.index(f'data-appointment="{old_id}"') < html.index(f'data-appointment="{aid}"')
    assert html.count('>PATIENT FICTIF</button>') == 2  # Repeat examinations remain separate.
    assert "RESERVATION HORS SEMAINE" in html and "DOUBLON CACHE" not in html
    assert '<img src=x' not in html and '&lt;img' in html
    assert "private@example.invalid" not in html and "BIM" not in html
    week_page = admin.get("/admin/appointments?date="+date_string)
    assert f'data-appointment="{old_id}"'.encode() not in week_page.data
    assert b"Liste RIZIV" in week_page.data
    exported = admin.get("/admin/appointments/riziv.csv")
    assert exported.status_code == 200 and exported.headers["Content-Disposition"].startswith("attachment;")
    assert exported.headers["Cache-Control"] == "private, no-store"
    csv_rows = list(csv.reader(io.StringIO(exported.data.decode("utf-8-sig")),delimiter=";"))
    assert len(csv_rows) == 8 and csv_rows[1][4] == "00123456789"
    assert csv_rows[1][3] == "PATIENT FICTIF" and csv_rows[-2][3] == "'=2+2"
    assert "private@example.invalid" not in exported.data.decode("utf-8-sig")
    assert len({tuple(row) for row in csv_rows[1:]}) == 7
    assert b"RESERVATION HORS SEMAINE" not in anonymous.get("/agenda?date="+date_string).data
    if "--serve" not in sys.argv:
        with app.app_context():
            history = [Appointment(starts_at=day+timedelta(days=100+i),patient_name=f"HISTORIQUE FICTIF {i}",
                patient_email="",appointment_type="459712") for i in range(501)]
            db.session.add_all(history); db.session.flush()
            db.session.add(AppointmentPatientDetails(context_key=appointment_report_key(history[-1]),national_number="00000000000"))
            db.session.commit()
        large_list = admin.get("/admin/appointments/riziv")
        assert large_list.json["total"] == 508 and "00000000000" in large_list.json["html"]
    print("PASS: private uploads/identifiers, saved reports/retries/conflicts/outage, PDF, day open/close, holds, public isolation.")
    print("PASS: all-time RIZIV list/export, chronological order, repeat visits, historical reservations, access control, escaping, leading-zero identifiers and CSV formula protection.")
    if "--serve" in sys.argv:
        with app.app_context():
            db.session.get(Appointment, future_id).patient_name = "PATIENT FUTUR FICTIF"
            db.session.get(Appointment, escaped_id).patient_name = "PATIENT DEMONSTRATION"
            db.session.commit()
        print("Fictional preview: http://127.0.0.1:5057/admin/appointments?date="+date_string, flush=True)
        app.run(host="127.0.0.1", port=5057, debug=False)
finally:
    with app.app_context():
        db.session.remove(); db.engine.dispose()
    os.unlink(database_path)
