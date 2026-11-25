"""Calendar consent and mirror checks without contacting Google or a real database."""
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit


with tempfile.TemporaryDirectory(prefix="wirc-calendar-tests-") as directory:
    os.environ.pop("RENDER", None)
    os.environ.update(
        PRACTICE_PROFILE="wirc",
        WIRC_DATABASE_URL="sqlite:///" + str(Path(directory) / "calendar.db"),
        SECRET_KEY="calendar-tests-only",
        PUBLIC_SITE_MODE="active", APPOINTMENT_BOOKING_ENABLED="1",
        APPOINTMENT_PRACTICE_ADDRESS="Adresse fictive",
        GOOGLE_OAUTH_CLIENT_ID="fake-google-client", GOOGLE_OAUTH_CLIENT_SECRET="test-secret",
        GOOGLE_OAUTH_REDIRECT_URI="https://wirc.be/auth/google/callback",
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import app, user_has_admin_access
    from gmail_reporting import GMAIL_SCOPE, token_cipher
    from models import Appointment, GmailConnection, GoogleCalendarConnection, GoogleCalendarEvent, User, db
    from wirc_google_calendar import CALENDAR_SCOPE, CalendarError, sync_google_calendar

    app.config["TESTING"] = True
    base = "https://wirc.be"
    start_url = "/auth/google/calendar/start"
    pause_url = "/admin/appointments/google-calendar/pause"
    now = datetime(2026, 12, 1, 10)
    with app.app_context():
        admin = User(email="y@bymed.be", is_admin=True)
        admin.set_password("test-password")
        db.session.add(admin)
        db.session.flush()
        db.session.add(GmailConnection(user_id=admin.id, email=admin.email,
            google_subject="same-google-account", encrypted_refresh_token="unchanged-gmail"))
        db.session.commit()

    admin, public = app.test_client(), app.test_client()
    admin.post("/login", base_url=base, data={"email": "y@bymed.be", "password": "test-password"})
    page = admin.get("/admin/appointments", base_url=base)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
    assert "Google Agenda" in page.text and "Notifications Gmail" in page.text
    assert public.post(start_url, base_url=base).status_code == 302
    assert admin.post(start_url, base_url=base, data={"csrf_token": "incorrect"}).status_code == 400
    start = admin.post(start_url, base_url=base, data={"csrf_token": csrf})
    params = parse_qs(urlsplit(start.location).query)
    assert CALENDAR_SCOPE in params["scope"][0].split() and GMAIL_SCOPE not in params["scope"][0].split()
    assert params["access_type"] == ["offline"]
    callback = "/auth/google/callback?code=fake&state=" + params["state"][0]
    flow = MagicMock()
    flow.credentials = SimpleNamespace(granted_scopes=[CALENDAR_SCOPE], refresh_token="new-calendar-token")
    claims = {"email": "y@bymed.be", "sub": "same-google-account"}
    with patch("app.google_flow", return_value=flow), patch("app.verified_google_identity", return_value=claims):
        assert admin.get(callback, base_url=base).status_code == 302
        assert admin.get(callback, base_url=base).status_code == 400
    with app.app_context():
        connection = db.session.get(GoogleCalendarConnection, 1)
        assert token_cipher(app.secret_key).decrypt(connection.encrypted_refresh_token.encode()) == b"new-calendar-token"
        assert GmailConnection.query.one().encrypted_refresh_token == "unchanged-gmail"
        appt = Appointment(starts_at=datetime(2026, 12, 3, 9), appointment_type="459712",
            patient_name="Confidential Test Patient", patient_email="patient@example.invalid", duration_minutes=10)
        db.session.add(appt)
        db.session.commit()
        snapshot = {column.name: getattr(appt, column.name) for column in Appointment.__table__.columns}

    calls = []
    fail_insert = True
    def google(token, method, path, *, body=None):
        global fail_insert
        calls.append((method, path, body))
        if path == "/calendars":
            return {"id": "test@group.calendar.google.com"}
        if method == "POST" and fail_insert:
            fail_insert = False
            raise CalendarError("retry")  # Simulate a successful insert with a lost response.
        if method == "POST" and len(calls) == 3:
            raise CalendarError("retry", 409)
        return {}

    def sync():
        sync_google_calendar(secret=app.secret_key, can_use_account=user_has_admin_access, now=lambda: now)

    with app.app_context(), patch("wirc_google_calendar.calendar_access_token", return_value="fake"), \
            patch("wirc_google_calendar.calendar_request", side_effect=google):
        sync()
        event = GoogleCalendarEvent.query.one()
        event_id = event.event_id
        assert not event.synced
        sync()
        assert GoogleCalendarEvent.query.one().synced
        assert [call[0] for call in calls] == ["POST", "POST", "POST", "PATCH"]
        assert calls[1][2]["id"] == calls[2][2]["id"] == event_id
        assert calls[3][2] == {
            "summary": "Rendez-vous WIRC", "visibility": "private", "reminders": {"useDefault": False},
            "start": {"dateTime": "2026-12-03T09:00:00+01:00", "timeZone": "Europe/Brussels"},
            "end": {"dateTime": "2026-12-03T09:10:00+01:00", "timeZone": "Europe/Brussels"},
        }
        sync()
        assert len(calls) == 4  # A steady state makes no Google API request.
        record = Appointment.query.one()
        record.starts_at = datetime(2026, 12, 3, 10)
        db.session.commit()
        sync()
        assert calls[-1][0] == "PATCH" and event_id in calls[-1][1]
        assert "T10:00:00" in calls[-1][2]["start"]["dateTime"]
        db.session.delete(Appointment.query.one())
        db.session.commit()
        sync()
        assert calls[-1][0] == "DELETE" and event_id in calls[-1][1]
        db.session.add(Appointment(**snapshot))
        db.session.commit()
        sync()
        assert calls[-1][0] == "POST" and calls[-1][2]["id"] != event_id
        event = GoogleCalendarEvent.query.one()
        assert event.synced

    assert admin.post(pause_url, base_url=base, data={"csrf_token": csrf}).status_code == 302
    with app.app_context(), patch("wirc_google_calendar.calendar_access_token") as token:
        sync()
        token.assert_not_called()
        assert db.session.get(GoogleCalendarConnection, 1).status == "paused"
        assert GmailConnection.query.one().encrypted_refresh_token == "unchanged-gmail"
        db.engine.dispose()
    assert "Google Agenda" not in public.get("/agenda", base_url=base).text
    print("PASS: optional Calendar consent, separate Gmail credentials, private events, idempotent sync, moves, cancellations, restores and pause.")
