"""Private Gmail alerts for committed online bookings."""
from datetime import datetime, timedelta
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from gmail_reporting import GmailConnectionError, send_gmail_booking_alert
from models import BookingAlert, BookingAlertSettings, GmailConnection, User, db
from report_mail import ReportMailError

_wakeup = Event()


def alert_settings():
    return db.session.get(BookingAlertSettings, 1)


def set_alert_mailbox(connection):
    """Enable the current verified mailbox, or disable future deliveries."""
    if connection is None:
        db.session.execute(delete(BookingAlertSettings).where(BookingAlertSettings.id == 1))
        return

    db.session.execute(text(
        "INSERT INTO booking_alert_settings (id, subscription, user_id, google_subject, email) "
        "VALUES (1, :subscription, :user_id, :google_subject, :email) "
        "ON CONFLICT (id) DO NOTHING"
    ), dict(subscription=str(uuid4()), user_id=connection.user_id,
            google_subject=connection.google_subject, email=connection.email))


def alert_status(settings):
    if settings is None:
        return None
    return db.session.scalar(
        select(BookingAlert.status)
        .where(BookingAlert.subscription == settings.subscription)
        .order_by(BookingAlert.created_at.desc(), BookingAlert.id.desc())
        .limit(1)
    )


def queue_booking_alert(starts_at):
    """Add a notice to the same transaction as the confirmed appointment."""
    settings = alert_settings()
    if settings is None:
        return False
    db.session.add(BookingAlert(id=str(uuid4()), subscription=settings.subscription, starts_at=starts_at))
    return True


def wake_booking_alert_worker():
    _wakeup.set()


def deliver_booking_alert(*, secret, can_use_account):
    now = datetime.utcnow()
    # If a process stopped after claiming a send, Gmail may already have it.
    # Mark those attempts unconfirmed instead of sending a second email.
    db.session.execute(update(BookingAlert).where(
        BookingAlert.status == "sending",
        BookingAlert.attempted_at < now - timedelta(minutes=3),
    ).values(status="unconfirmed"))
    settings = alert_settings()
    active_subscription = (
        select(BookingAlertSettings.subscription).where(BookingAlertSettings.id == 1)
    )
    alert = None
    if settings is not None:
        alert = db.session.scalar(select(BookingAlert).where(
            BookingAlert.subscription == settings.subscription, BookingAlert.status == "pending"
        ).order_by(BookingAlert.created_at, BookingAlert.id).limit(1))
    if alert is None:
        db.session.commit()
        return False

    alert_id, starts_at, subscription = alert.id, alert.starts_at, alert.subscription
    connection = db.session.get(GmailConnection, settings.user_id)
    owner = db.session.get(User, settings.user_id)
    valid = (connection is not None and can_use_account(owner)
             and settings.email == connection.email
             and settings.google_subject == connection.google_subject
             and owner.email.lower() == connection.email.lower())
    # Claim atomically across requests, worker restarts and overlapping deploys.
    claimed = db.session.execute(update(BookingAlert).where(
        BookingAlert.id == alert_id,
        BookingAlert.status == "pending",
        BookingAlert.subscription.in_(active_subscription),
    ).values(status="sending" if valid else "reconnect", attempted_at=now)).rowcount
    mailbox = SimpleNamespace(email=connection.email, encrypted_refresh_token=connection.encrypted_refresh_token) if valid else None
    db.session.commit()
    db.session.remove()
    if not claimed:
        return False
    if mailbox is None:
        return True

    try:
        send_gmail_booking_alert(connection=mailbox, secret=secret, starts_at=starts_at, alert_id=alert_id)
        status = "sent"
    except GmailConnectionError:
        status = "reconnect"
    except ReportMailError:
        status = "unconfirmed"
    db.session.execute(update(BookingAlert).where(
        BookingAlert.id == alert_id, BookingAlert.subscription == subscription
    ).values(status=status))
    db.session.commit()
    return True


def start_booking_alert_worker(app, can_use_account):
    def run():
        while True:
            _wakeup.clear()
            try:
                with app.app_context():
                    while deliver_booking_alert(secret=app.secret_key, can_use_account=can_use_account):
                        pass
            except SQLAlchemyError:
                app.logger.warning("Booking alert storage unavailable; will check again.")
            except Exception:
                app.logger.error("Booking alert stopped mid-attempt; delivery status will be checked.")
            _wakeup.wait(timeout=15)

    Thread(target=run, name="booking-alerts", daemon=True).start()
