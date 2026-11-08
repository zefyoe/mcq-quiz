"""Private, transactional rescheduling. Patient documents never get recreated."""
import hashlib
import json
import re
from datetime import datetime, time, timedelta

from flask import abort, jsonify, request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm import load_only

from models import db, Appointment, AppointmentHold, AppointmentReport, AppointmentPatientDetails, InternalRegisterExclusion, AppointmentMoveReceipt


def is_empty_legacy_claim(claim, record_key):
    if (claim.draft_data or "").strip() not in {"", "{}", "null"} or any((
            claim.prescription_data,claim.prescription_filename,claim.prescription_mimetype)):
        return False
    key=record_key(claim)
    return (AppointmentReport.query.filter_by(context_key=key).first() is None
            and db.session.get(AppointmentPatientDetails,key) is None
            and db.session.get(InternalRegisterExclusion,key) is None)


def register_appointment_moves(app, *, admin_required, ensure_schema, csrf_token, now, parse_slot, slot_open, claim_slot, record_key):
    def receipt_payload(receipt):
        return dict(ok=True, starts_at=receipt.target_start.isoformat(timespec="minutes"),
            previous_start=receipt.previous_start.isoformat(timespec="minutes"), kind=receipt.source_kind,
            appointment_id=receipt.appointment_id or "", context_key=receipt.context_key)

    @app.post("/admin/appointments/move")
    def admin_move_appointment():
        denied = admin_required()
        if denied:
            return denied
        import secrets
        if not secrets.compare_digest(request.form.get("csrf_token", ""), csrf_token()):
            abort(400)
        ensure_schema()
        values=request.form
        target=parse_slot(values.get("target_start"))
        token=values.get("move_token", "")
        expected_key=values.get("expected_key", "")
        aid=values.get("appointment_id", type=int)
        reservation=values.get("reservation_start", "")
        try:
            expected=datetime.fromisoformat(values.get("expected_start", ""))
            if expected.tzinfo is not None:
                raise ValueError()
        except ValueError:
            return jsonify(error="L’horaire initial est invalide. Actualisez l’agenda."),400
        if not target or not re.fullmatch(r"[0-9a-fA-F-]{36}",token) or not re.fullmatch(r"[0-9a-f]{64}",expected_key) or bool(aid)==bool(reservation):
            return jsonify(error="Choisissez un rendez-vous et un créneau valides."),400
        fingerprint=hashlib.sha256(json.dumps([aid,reservation,expected.isoformat(),expected_key,target.isoformat()],separators=(",",":")).encode()).hexdigest()
        receipt=db.session.get(AppointmentMoveReceipt,token)
        if receipt:
            if receipt.fingerprint!=fingerprint or receipt.requested_by!=current_user.id:
                return jsonify(error="Cette demande de déplacement correspond à une autre opération."),409
            return jsonify(**receipt_payload(receipt))

        def fail(message,status=409):
            db.session.rollback()
            if status==409:
                # A concurrent same-token request may only become visible after
                # releasing this transaction's stale snapshot (notably SQLite).
                completed=db.session.get(AppointmentMoveReceipt,token)
                if completed and completed.fingerprint==fingerprint and completed.requested_by==current_user.id:
                    return jsonify(**receipt_payload(completed))
            return jsonify(error=message),status

        try:
            if aid:
                record=Appointment.query.filter_by(id=aid).with_for_update().first()
            else:
                source=parse_slot(reservation)
                record=AppointmentHold.query.filter_by(starts_at=source).with_for_update().first() if source else None
            # A same-token retry may have waited for the first move's row lock.
            # Recheck its committed receipt before reporting a stale source.
            receipt=db.session.get(AppointmentMoveReceipt,token)
            if receipt:
                if receipt.fingerprint!=fingerprint or receipt.requested_by!=current_user.id:
                    return fail("Cette demande correspond à une autre opération.")
                return jsonify(**receipt_payload(receipt))
            if record is None:
                return fail("Le rendez-vous n’existe plus. Actualisez l’agenda.",404)
            if record.starts_at!=expected or record_key(record)!=expected_key:
                return fail("Ce rendez-vous a déjà changé dans une autre fenêtre. Actualisez l’agenda.")
            if target==record.starts_at:
                return fail("Choisissez un autre créneau.",400)
            if target<=now():
                return fail("Choisissez un créneau futur.",400)
            source_claim=None
            if aid:
                source_claim=AppointmentHold.query.filter_by(starts_at=expected).with_for_update().first()
                if source_claim:
                    # Older manual bookings retained an empty booking lock at
                    # their start. It must leave with the appointment, or the
                    # calendar exposes a phantom reservation at the old time.
                    # A separate populated reservation is never discarded.
                    if not is_empty_legacy_claim(source_claim,record_key):
                        return fail("Une réservation distincte contient encore des données à cet horaire. Le déplacement n’a pas été effectué afin de conserver ces informations.")
            duration=record.duration_minutes if aid else 10
            finish=target+timedelta(minutes=duration)
            if duration<=0 or finish>datetime.combine(target.date(),time(21)):
                return fail("La durée du rendez-vous dépasse les horaires disponibles.",400)
            stamps=[target+timedelta(minutes=offset) for offset in range(0,duration,10)]
            if not all(slot_open(stamp) for stamp in stamps):
                return fail("Ce créneau est fermé. Ouvrez toute la plage nécessaire avant de déplacer le rendez-vous.")
            # Claim every occupied 10-minute unit, using the same unique lock as
            # public bookings. Overlapping moves cannot both acquire the target.
            for stamp in stamps:
                if not claim_slot(stamp,"move:"+token):
                    return fail("Ce créneau est déjà occupé ou réservé. Choisissez une case libre.")
            occupied=Appointment.query.options(load_only(Appointment.starts_at,Appointment.duration_minutes)).filter(Appointment.starts_at<finish).all()
            if any(item.starts_at+timedelta(minutes=item.duration_minutes)>target for item in occupied):
                return fail("Ce créneau est déjà occupé. Le rendez-vous n’a pas été déplacé.")
            old_key=record_key(record)
            report=AppointmentReport.query.filter_by(context_key=old_key).with_for_update().first()
            details=db.session.get(AppointmentPatientDetails,old_key)
            exclusion=db.session.get(InternalRegisterExclusion,old_key)
            if aid:
                count=Appointment.query.filter_by(id=aid,starts_at=expected).update({Appointment.starts_at:target},synchronize_session=False)
                if count!=1:
                    return fail("Ce rendez-vous vient d’être déplacé. Actualisez l’agenda.")
                db.session.refresh(record)
                new_key=record_key(record)
                if source_claim:
                    db.session.delete(source_claim)
                AppointmentHold.query.filter(AppointmentHold.starts_at.in_(stamps),AppointmentHold.token=="move:"+token).delete(synchronize_session=False)
            else:
                # The claimed target row becomes the original reservation, with
                # its original token, draft, attachment bytes and expiry intact.
                destination=db.session.get(AppointmentHold,target)
                destination.token=record.token
                destination.expires_at=record.expires_at
                destination.draft_data=record.draft_data
                destination.prescription_filename=record.prescription_filename
                destination.prescription_mimetype=record.prescription_mimetype
                destination.prescription_data=record.prescription_data
                count=AppointmentHold.query.filter_by(starts_at=expected,token=record.token).delete(synchronize_session=False)
                if count!=1:
                    return fail("Cette réservation vient de changer. Actualisez l’agenda.")
                db.session.expunge(record)
                new_key=record_key(destination)
            if report:
                report.context_key=new_key
                report.starts_at=target
            if details:
                details.context_key=new_key
            if exclusion:
                exclusion.context_key=new_key
            receipt=AppointmentMoveReceipt(token=token,fingerprint=fingerprint,source_kind="appointment" if aid else "reservation",
                appointment_id=aid,previous_start=expected,target_start=target,context_key=new_key,requested_by=current_user.id)
            db.session.add(receipt)
            db.session.commit()
            return jsonify(**receipt_payload(receipt))
        except (IntegrityError,StaleDataError):
            return fail("Le rendez-vous ou le créneau a changé pendant le déplacement. Actualisez l’agenda.")
        except SQLAlchemyError:
            return fail("Déplacement non confirmé. Réessayez : les données restent conservées.",503)
