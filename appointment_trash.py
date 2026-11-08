"""Recoverable cancellations, kept separate from the public calendar."""
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta

from flask import abort, jsonify, request
from flask_login import current_user
from sqlalchemy import DateTime
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import load_only

from appointment_moves import is_empty_legacy_claim
from models import db, Appointment, AppointmentHold, AppointmentReport, AppointmentPatientDetails, InternalRegisterExclusion, AppointmentTrash


def register_appointment_trash(app, *, admin_required, ensure_schema, csrf_token, now, claim_slot, record_key):
    def guard(write=False):
        denied=admin_required()
        if denied:
            return denied
        if write and not secrets.compare_digest(request.form.get("csrf_token", ""),csrf_token()):
            abort(400)
        ensure_schema()

    def fail(message,status=409):
        db.session.rollback()
        return jsonify(error=message),status

    @app.get("/admin/appointments/trash")
    def admin_appointment_trash_list():
        denied=guard()
        if denied:
            return denied
        rows=AppointmentTrash.query.filter_by(restored_at=None).order_by(AppointmentTrash.deleted_at.desc()).all()
        items=[]
        for row in rows:
            data=json.loads(row.record_data)
            if row.source_kind=="appointment":
                name=data.get("patient_name")
            else:
                try:
                    draft=json.loads(data.get("draft_data") or "{}")
                    name=draft.get("patient_name") if isinstance(draft,dict) else None
                except (TypeError,ValueError):
                    name=None
            items.append(dict(token=row.token,patient_name=name or "Réservation",starts_at=row.starts_at.isoformat(timespec="minutes")))
        return jsonify(ok=True,items=items)

    @app.post("/admin/appointments/trash")
    def admin_trash_appointment():
        denied=guard(True)
        if denied:
            return denied
        values=request.form
        token=values.get("move_token", "")
        aid=values.get("appointment_id",type=int)
        reservation=values.get("reservation_start", "")
        key=values.get("expected_key", "")
        try:
            expected=datetime.fromisoformat(values.get("expected_start", ""))
            if expected.tzinfo is not None:
                raise ValueError()
        except ValueError:
            return jsonify(error="L’horaire initial est invalide. Actualisez l’agenda."),400
        if not re.fullmatch(r"[0-9a-fA-F-]{36}",token) or not re.fullmatch(r"[0-9a-f]{64}",key) or bool(aid)==bool(reservation):
            return jsonify(error="Choisissez un rendez-vous valide."),400
        fingerprint=hashlib.sha256(json.dumps([aid,reservation,expected.isoformat(),key],separators=(",",":")).encode()).hexdigest()

        def completed():
            receipt=db.session.get(AppointmentTrash,token)
            if receipt:
                if receipt.fingerprint!=fingerprint or receipt.deleted_by!=current_user.id:
                    return jsonify(error="Cette demande correspond à une autre opération."),409
                if receipt.restored_at:
                    return jsonify(error="Ce rendez-vous a déjà été rétabli. Actualisez l’agenda."),409
                return jsonify(ok=True,trash_token=token,previous_start=expected.isoformat(timespec="minutes"))

        try:
            result=completed()
            if result:
                return result
            if aid:
                record=Appointment.query.filter_by(id=aid).with_for_update().first()
            else:
                record=AppointmentHold.query.filter_by(starts_at=expected).with_for_update().first() if reservation==expected.isoformat() else None
                # Calendar sources may omit seconds.
                if record is None and reservation==expected.isoformat(timespec="minutes"):
                    record=AppointmentHold.query.filter_by(starts_at=expected).with_for_update().first()
            result=completed()
            if result:
                return result
            if record is None or record.starts_at!=expected or record_key(record)!=key:
                return fail("Ce rendez-vous a changé. Actualisez l’agenda avant de le retirer.")
            if aid:
                source_claim=AppointmentHold.query.filter_by(starts_at=expected).with_for_update().first()
                if source_claim:
                    if not is_empty_legacy_claim(source_claim,record_key):
                        return fail("Une réservation distincte contient encore des données à cet horaire. Aucune information n’a été supprimée.")
                    db.session.delete(source_claim)
            snapshot={}
            for column in record.__table__.columns:
                if column.name=="prescription_data":
                    continue
                value=getattr(record,column.name)
                snapshot[column.name]=value.isoformat() if isinstance(value,datetime) else value
            db.session.add(AppointmentTrash(token=token,fingerprint=fingerprint,source_kind="appointment" if aid else "reservation",
                context_key=key,starts_at=expected,record_data=json.dumps(snapshot,ensure_ascii=False),
                prescription_data=record.prescription_data,deleted_by=current_user.id))
            if aid:
                count=Appointment.query.filter_by(id=aid,starts_at=expected).delete(synchronize_session=False)
            else:
                count=AppointmentHold.query.filter_by(starts_at=expected,token=record.token).delete(synchronize_session=False)
            if count!=1:
                return fail("Ce rendez-vous vient de changer. Actualisez l’agenda.")
            db.session.expunge(record)
            db.session.commit()
            return jsonify(ok=True,trash_token=token,previous_start=expected.isoformat(timespec="minutes"))
        except SQLAlchemyError:
            db.session.rollback()
            result=completed()
            if result:
                return result
            return fail("Retrait non confirmé. Réessayez : les données restent conservées.",503)

    @app.post("/admin/appointments/trash/<token>/restore")
    def admin_restore_trashed_appointment(token):
        denied=guard(True)
        if denied:
            return denied
        try:
            row=AppointmentTrash.query.filter_by(token=token).with_for_update().first()
            if row is None:
                return fail("Ce rendez-vous n’est pas dans la corbeille.",404)
            if row.restored_at:
                return jsonify(ok=True,starts_at=row.starts_at.isoformat(timespec="minutes"))
            model=Appointment if row.source_kind=="appointment" else AppointmentHold
            values=json.loads(row.record_data)
            for column in model.__table__.columns:
                if isinstance(column.type,DateTime) and values.get(column.name):
                    values[column.name]=datetime.fromisoformat(values[column.name])
            start=row.starts_at
            duration=values["duration_minutes"] if model is Appointment else 10
            finish=start+timedelta(minutes=duration)
            stamps=[start+timedelta(minutes=offset) for offset in range(0,duration,10)]
            for stamp in stamps:
                if not claim_slot(stamp,"restore:"+token):
                    return fail("L’ancien créneau est occupé. Libérez-le avant de rétablir ce rendez-vous.")
            occupied=Appointment.query.options(load_only(Appointment.starts_at,Appointment.duration_minutes)).filter(Appointment.starts_at<finish).all()
            if any(item.starts_at+timedelta(minutes=item.duration_minutes)>start for item in occupied):
                return fail("L’ancien créneau est occupé. Aucun rendez-vous n’a été remplacé.")
            if model is Appointment:
                # SQLite may reuse a deleted id. Never replace its new owner.
                if db.session.get(Appointment,values["id"]) is not None:
                    values.pop("id")
                record=Appointment(**values,prescription_data=row.prescription_data)
                db.session.add(record)
                AppointmentHold.query.filter(AppointmentHold.starts_at.in_(stamps),AppointmentHold.token=="restore:"+token).delete(synchronize_session=False)
            else:
                record=db.session.get(AppointmentHold,start)
                for name,value in values.items():
                    setattr(record,name,value)
                record.prescription_data=row.prescription_data
            db.session.flush()
            new_key=record_key(record)
            if new_key!=row.context_key:
                report=AppointmentReport.query.filter_by(context_key=row.context_key).with_for_update().first()
                details=db.session.get(AppointmentPatientDetails,row.context_key)
                exclusion=db.session.get(InternalRegisterExclusion,row.context_key)
                for item in (report,details,exclusion):
                    if item:
                        item.context_key=new_key
            row.restored_at=now()
            db.session.commit()
            return jsonify(ok=True,starts_at=start.isoformat(timespec="minutes"))
        except SQLAlchemyError:
            return fail("Rétablissement non confirmé. Réessayez : les données restent dans la corbeille.",503)
