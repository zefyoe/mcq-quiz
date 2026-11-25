"""Mirror confirmed WIRC appointments into one calendar created by the app."""
from datetime import datetime, time, timedelta, timezone
from functools import partial
from hashlib import sha256
import os
from threading import Event, Thread
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

from cryptography.fernet import InvalidToken
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
import requests
from sqlalchemy import or_, select, update

from gmail_reporting import token_cipher
from models import Appointment, GoogleCalendarConnection, GoogleCalendarEvent, User, db

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.app.created"
CALENDAR_SCOPES = ("openid", "https://www.googleapis.com/auth/userinfo.email", CALENDAR_SCOPE)
CALENDAR_NAME = "WIRC · Rendez-vous"
BRUSSELS = ZoneInfo("Europe/Brussels")
API = "https://www.googleapis.com/calendar/v3"
BATCH_SIZE = 10
_wakeup = Event()


class CalendarError(Exception):
    def __init__(self, state, status_code=None):
        super().__init__(state)
        self.state = state
        self.status_code = status_code


def calendar_connection():
    return db.session.get(GoogleCalendarConnection, 1)


def store_calendar_consent(*, user_id, email, subject, encrypted_refresh_token):
    connection = calendar_connection()
    if connection is None:
        connection = GoogleCalendarConnection(id=1, user_id=user_id, email=email, google_subject=subject)
        db.session.add(connection)
    elif (connection.user_id, connection.email, connection.google_subject) != (user_id, email, subject):
        raise CalendarError("account")
    connection.encrypted_refresh_token = encrypted_refresh_token
    if connection.status not in {"creating", "creation_unknown"}:
        connection.status = "pending"
    db.session.commit()
    _wakeup.set()


def calendar_access_token(encrypted, secret):
    try:
        refresh = token_cipher(secret).decrypt(encrypted.encode()).decode()
        credentials = Credentials(token=None, refresh_token=refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"], scopes=CALENDAR_SCOPES)
        credentials.refresh(partial(GoogleRequest(), timeout=10))
        return credentials.token
    except (InvalidToken, KeyError, ValueError):
        raise CalendarError("reconnect") from None
    except GoogleAuthError as error:
        raise CalendarError("retry" if error.retryable else "reconnect") from None
    except requests.RequestException:
        raise CalendarError("retry") from None


def calendar_request(token, method, path, *, body=None):
    try:
        response = requests.request(method, API + path,
            headers={"Authorization": "Bearer " + token}, json=body, timeout=10)
    except requests.RequestException:
        raise CalendarError("retry") from None
    if response.status_code >= 400:
        try:
            error = response.json().get("error", {})
            reasons = {item.get("reason") for item in error.get("errors", []) + error.get("details", [])}
        except (ValueError, AttributeError, TypeError):
            reasons = set()
        if reasons & {"accessNotConfigured", "SERVICE_DISABLED"}:
            state = "api_disabled"
        elif response.status_code == 401 or reasons & {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}:
            state = "reconnect"
        else:
            state = "retry"
        raise CalendarError(state, response.status_code)
    if response.status_code == 204:
        return {}
    try:
        result = response.json()
        if isinstance(result, dict):
            return result
    except ValueError:
        pass
    raise CalendarError("retry")


def event_body(starts_at, duration):
    return {
        "summary": "Rendez-vous WIRC",
        "start": {"dateTime": starts_at.replace(tzinfo=BRUSSELS).isoformat(), "timeZone": BRUSSELS.key},
        "end": {"dateTime": (starts_at + timedelta(minutes=duration)).replace(tzinfo=BRUSSELS).isoformat(),
                "timeZone": BRUSSELS.key},
        "visibility": "private",
        "reminders": {"useDefault": False},
    }


def pending_changes(today_start):
    rows = db.session.execute(select(Appointment.id, Appointment.created_at, Appointment.starts_at,
        Appointment.duration_minutes).where(Appointment.starts_at >= today_start)
        .order_by(Appointment.starts_at, Appointment.id))
    desired = {sha256(f"{row.id}:{row.created_at}".encode()).hexdigest(): (row.starts_at, row.duration_minutes)
               for row in rows}
    existing = {item.booking_key: item for item in db.session.scalars(select(GoogleCalendarEvent))}
    # Prioritize removals so cancelled appointments are cleared promptly.
    changes = [(key, None) for key, item in existing.items()
               if key not in desired and item.starts_at >= today_start]
    changes.extend((key, timing) for key, timing in desired.items()
        if key not in existing or not existing[key].synced
        or (existing[key].starts_at, existing[key].duration_minutes) != timing)
    return changes


def lease_is_active(lease):
    return db.session.scalar(select(GoogleCalendarConnection.id).where(
        GoogleCalendarConnection.id == 1, GoogleCalendarConnection.lease_id == lease,
        GoogleCalendarConnection.encrypted_refresh_token.is_not(None))) is not None


def sync_event(token, calendar_id, key, timing):
    path = "/calendars/" + quote(calendar_id, safe="") + "/events"
    item = db.session.get(GoogleCalendarEvent, key)
    if item is None:
        item = GoogleCalendarEvent(booking_key=key, event_id=uuid4().hex,
            starts_at=timing[0], duration_minutes=timing[1], synced=False)
        db.session.add(item)
        # Persist the event ID before making the first remote request.
        db.session.commit()
    event_id, was_synced = item.event_id, item.synced
    db.session.remove()
    target = f"{path}/{event_id}?sendUpdates=none"
    if timing is None:
        try:
            calendar_request(token, "DELETE", target)
        except CalendarError as error:
            if error.status_code not in {404, 410}:
                raise
        db.session.delete(db.session.get(GoogleCalendarEvent, key))
    else:
        body = event_body(*timing)
        if was_synced:
            try:
                calendar_request(token, "PATCH", target, body=body)
            except CalendarError as error:
                if error.status_code not in {404, 410}:
                    raise
                # An event deleted manually can leave a Google tombstone.
                item = db.session.get(GoogleCalendarEvent, key)
                item.event_id, item.synced = uuid4().hex, False
                db.session.commit()
                return False
        else:
            try:
                calendar_request(token, "POST", path + "?sendUpdates=none", body={**body, "id": event_id})
            except CalendarError as error:
                if error.status_code != 409:
                    raise
                # The insert may have succeeded before a previous request timed out.
                calendar_request(token, "PATCH", target, body=body)
        item = db.session.get(GoogleCalendarEvent, key)
        item.starts_at, item.duration_minutes = timing
        item.synced = True
    db.session.commit()
    return True


def sync_google_calendar(*, secret, can_use_account, now):
    instant = datetime.now(timezone.utc).replace(tzinfo=None)
    lease = uuid4().hex
    claimed = db.session.execute(update(GoogleCalendarConnection).where(
        GoogleCalendarConnection.id == 1, GoogleCalendarConnection.encrypted_refresh_token.is_not(None),
        GoogleCalendarConnection.status.notin_(("creation_unknown", "reconnect")),
        or_(GoogleCalendarConnection.lease_until.is_(None), GoogleCalendarConnection.lease_until < instant),
    ).values(lease_id=lease, lease_until=instant + timedelta(minutes=6))).rowcount
    db.session.commit()
    if not claimed:
        return
    state = "retry"
    try:
        connection = calendar_connection()
        owner = db.session.get(User, connection.user_id)
        if not can_use_account(owner) or owner.email.strip().lower() != connection.email:
            state = "reconnect"
            return
        if connection.status == "creating" and not connection.calendar_id:
            state = "creation_unknown"
            return
        calendar_id, encrypted = connection.calendar_id, connection.encrypted_refresh_token
        changes = pending_changes(datetime.combine(now().date(), time.min))
        db.session.remove()
        if calendar_id and not changes:
            state = "synced"
            return
        token = calendar_access_token(encrypted, secret)
        if not calendar_id:
            if not lease_is_active(lease):
                return
            db.session.execute(update(GoogleCalendarConnection).where(
                GoogleCalendarConnection.id == 1, GoogleCalendarConnection.lease_id == lease,
            ).values(status="creating"))
            db.session.commit()
            state = "creation_unknown"
            try:
                calendar_id = calendar_request(token, "POST", "/calendars",
                    body={"summary": CALENDAR_NAME, "timeZone": BRUSSELS.key}).get("id")
            except CalendarError as error:
                if error.status_code is None or error.status_code >= 500:
                    raise CalendarError("creation_unknown") from None
                raise
            if not calendar_id:
                raise CalendarError("creation_unknown")
            db.session.execute(update(GoogleCalendarConnection).where(
                GoogleCalendarConnection.id == 1, GoogleCalendarConnection.lease_id == lease,
            ).values(calendar_id=calendar_id))
            db.session.commit()
            state = "retry"
        has_pending = len(changes) > BATCH_SIZE
        for key, timing in changes[:BATCH_SIZE]:
            if not lease_is_active(lease):
                return
            if not sync_event(token, calendar_id, key, timing):
                has_pending = True
        state = "pending" if has_pending else "synced"
    except CalendarError as error:
        state = error.state
    finally:
        db.session.rollback()
        owned = update(GoogleCalendarConnection).where(
            GoogleCalendarConnection.id == 1, GoogleCalendarConnection.lease_id == lease)
        db.session.execute(owned.where(GoogleCalendarConnection.encrypted_refresh_token.is_not(None)).values(status=state))
        db.session.execute(owned.where(
            GoogleCalendarConnection.encrypted_refresh_token.is_(None), GoogleCalendarConnection.status == "creating",
        ).values(status="creation_unknown" if state == "creation_unknown" else "paused"))
        db.session.execute(owned.values(lease_id=None, lease_until=None))
        db.session.commit()


def start_calendar_worker(app, can_use_account, now):
    def run():
        while True:
            _wakeup.clear()
            try:
                with app.app_context():
                    sync_google_calendar(secret=app.secret_key, can_use_account=can_use_account, now=now)
            except Exception:
                app.logger.warning("WIRC Google Calendar sync interrupted; will retry.")
            _wakeup.wait(timeout=30)

    Thread(target=run, name="wirc-google-calendar", daemon=True).start()
