"""Verify private WIRC booking alerts using an isolated database and fake Gmail."""
import base64
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser
import os
from pathlib import Path
import re
import sys
import tempfile
from unittest.mock import MagicMock, patch


with tempfile.TemporaryDirectory(prefix="wirc-booking-alerts-") as directory:
    os.environ.update(
        PRACTICE_PROFILE="wirc",
        WIRC_DATABASE_URL="sqlite:///" + str(Path(directory) / "alerts.db"),
        APPOINTMENT_PRACTICE_ADDRESS="Adresse fictive",
        APPOINTMENT_BOOKING_ENABLED="1",
        PUBLIC_SITE_MODE="active",
        SECRET_KEY="booking-alert-test-only",
        GOOGLE_OAUTH_CLIENT_ID="test",
        GOOGLE_OAUTH_CLIENT_SECRET="test",
        GOOGLE_OAUTH_REDIRECT_URI="https://wirc.be/auth/google/callback",
    )
    os.environ.pop("RENDER", None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import app, user_has_admin_access
    from booking_alerts import deliver_booking_alert
    from models import Appointment, BookingAlert, GmailConnection, User, db

    app.config["TESTING"] = True
    base = "https://wirc.be"
    settings_url = "/admin/appointments/booking-alerts"
    with app.app_context():
        user = User(email="y@bymed.be", is_admin=True)
        user.set_password("test-password")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    admin, public = app.test_client(), app.test_client()
    admin.post("/login", base_url=base, data={"email": "y@bymed.be", "password": "test-password"})
    with patch("app.agenda_now", return_value=datetime(2026, 11, 26, 12)):
        initial = admin.get("/admin/appointments", base_url=base)
        admin_csrf = re.search(r'name="csrf_token" value="([^"]+)"', initial.text)[1]
        page = public.get("/agenda", base_url=base)
        public_csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]

        def configure(enabled, csrf=admin_csrf):
            return admin.post(settings_url, base_url=base,
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={"enabled": enabled, "csrf_token": csrf, "recipient": "other@example.invalid"})

        def book(stamp):
            return public.post("/agenda/book", base_url=base, data={
                "csrf_token": public_csrf, "slot_start": stamp,
                "patient_name": "Patient Strictement Fictif", "patient_email": "patient@example.invalid",
                "inami_code": "459712",
            })

        assert "Notifications Gmail" in initial.text and "Notifications Gmail" not in page.text
        assert public.post(settings_url, base_url=base).status_code == 302
        assert configure("1", "incorrect").status_code == 400
        assert configure("1").status_code == 409
        assert book("2026-12-03T08:00").mimetype == "application/pdf"
        with app.app_context():
            assert BookingAlert.query.count() == 0
            db.session.add(GmailConnection(user_id=user_id, email="y@bymed.be",
                google_subject="verified-test-account", encrypted_refresh_token="test"))
            db.session.commit()
        assert configure("1").json["email"] == "y@bymed.be"
        assert configure("1").json["email"] == "y@bymed.be"  # Repeat activation is harmless.
        assert book("2026-12-03T08:10").mimetype == "application/pdf"
        assert book("2026-12-03T08:10").status_code == 409
        with app.app_context():
            assert BookingAlert.query.count() == 1
            assert Appointment.query.count() == 2

        # Process the queued notice with no logged-in Flask request.
        credentials = MagicMock(token="test-access")
        cipher = MagicMock()
        cipher.decrypt.return_value = b"test-refresh"
        response = MagicMock()
        response.json.return_value = {"id": "fake-gmail-message"}
        with app.app_context(), patch("gmail_reporting.Credentials", return_value=credentials), \
                patch("gmail_reporting.token_cipher", return_value=cipher), \
                patch("gmail_reporting.requests.post", return_value=response) as transport:
            assert deliver_booking_alert(secret=app.secret_key, can_use_account=user_has_admin_access)
            assert not deliver_booking_alert(secret=app.secret_key, can_use_account=user_has_admin_access)
            assert transport.call_count == 1
            payload = transport.call_args.kwargs["json"]["raw"]
            mail = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(payload))
            assert mail["To"] == mail["From"] == "y@bymed.be"
            body = mail.get_body().get_content()
            assert "03/12/2026 à 08:10" in body and "https://wirc.be/admin/appointments" in body
            assert all(value not in body for value in ("Fictif", "459712", "patient@example.invalid"))
            assert list(mail.iter_attachments()) == []
            assert BookingAlert.query.one().status == "sent"

        # A provider timeout must leave booking intact and must not trigger a second send.
        from report_mail import ReportMailError
        assert book("2026-12-03T08:20").mimetype == "application/pdf"
        with app.app_context(), patch("booking_alerts.send_gmail_booking_alert", side_effect=ReportMailError("timeout")) as send:
            assert deliver_booking_alert(secret=app.secret_key, can_use_account=user_has_admin_access)
            assert not deliver_booking_alert(secret=app.secret_key, can_use_account=user_has_admin_access)
            assert send.call_count == 1
            assert BookingAlert.query.filter_by(status="unconfirmed").count() == 1
            assert Appointment.query.count() == 3
        assert "Dernier envoi non confirmé" in admin.get("/admin/appointments", base_url=base).text

        # A disabled subscription cannot deliver queued alerts after reactivation.
        assert book("2026-12-03T08:30").mimetype == "application/pdf"
        assert configure("0").json["email"] is None
        assert configure("1").json["email"] == "y@bymed.be"
        with app.app_context(), patch("booking_alerts.send_gmail_booking_alert") as send:
            assert not deliver_booking_alert(secret=app.secret_key, can_use_account=user_has_admin_access)
            send.assert_not_called()
        assert configure("0").json["email"] is None

    with app.app_context():
        db.engine.dispose()
    print("PASS: private opt-in, only confirmed public bookings, durable dispatch, verified self-mail, no patient details or duplicate sends, and disable/re-enable.")
