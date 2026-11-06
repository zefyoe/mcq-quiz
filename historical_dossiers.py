"""Private paper-to-digital intake. No OCR, booking, mailing or external transfer."""
import hashlib
import re
from datetime import date, datetime, time
from io import BytesIO

from flask import abort, jsonify, render_template, request, url_for
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from werkzeug.utils import secure_filename

from models import db, HistoricalDossier, HistoricalDocument
from radiology_report import create_radiology_report_pdf

STATUS_LABELS = {"todo": "À compléter", "ready": "Prêt à transférer", "transferred": "Transféré manuellement"}
MAX_SCAN_BYTES = 10 * 1024 * 1024


def dossier_payload(record, include_text=True):
    documents = {item.kind: {"filename": item.filename,
        "view_url": url_for("admin_historical_document", dossier_id=record.id, kind=item.kind, inline="1"),
        "download_url": url_for("admin_historical_document", dossier_id=record.id, kind=item.kind)}
        for item in record.documents}
    result = dict(id=record.id, patient_name=record.patient_name, national_number=record.national_number,
        examined_on=record.examined_on.isoformat(), examination=record.examination,
        transfer_status=record.transfer_status, status_label=STATUS_LABELS[record.transfer_status],
        revision=record.revision, report_date=record.report_date.isoformat() if record.report_date else "",
        radiologist=record.radiologist, report_reviewed=record.report_reviewed,
        updated_at=record.updated_at.isoformat()+"Z", documents=documents,
        pdf_url=url_for("admin_historical_report_pdf", dossier_id=record.id),
        report_available="report" in documents or record.report_reviewed)
    if include_text:
        result["report_text"] = record.report_text
    return result


def historical_riziv_rows():
    return [dict(historical_id=record.id, appointment_id="", reservation_start="",
        starts_at=datetime.combine(record.examined_on, time.min), date_only=True,
        name=record.patient_name, examination=record.examination, national_number=record.national_number,
        registration_label="Dossier historique — date saisie", has_prescription=False, has_report=False)
        for record in HistoricalDossier.query.order_by(HistoricalDossier.examined_on, HistoricalDossier.id).all()]


def register_historical_dossiers(app, *, admin_required, ensure_schema, csrf_token, now, valid_name, practice_address):
    def authorize(write=False):
        denied = admin_required()
        if denied:
            return denied
        if write:
            import secrets
            if not secrets.compare_digest(request.form.get("csrf_token", ""), csrf_token()):
                abort(400)
        ensure_schema()

    def record_or_404(dossier_id):
        record = db.session.get(HistoricalDossier, dossier_id)
        if record is None:
            abort(404)
        return record

    @app.route("/admin/appointments/history", methods=["GET", "POST"])
    def admin_historical_dossiers():
        denied = authorize(request.method == "POST")
        if denied:
            return denied
        if request.method == "GET":
            records = HistoricalDossier.query.order_by(HistoricalDossier.examined_on, HistoricalDossier.id).all()
            rows = [dossier_payload(record, include_text=False) for record in records]
            return jsonify(ok=True, total=len(rows), html=render_template("_historical_patient_table.html", dossiers=rows))
        values = request.form
        dossier_id = values.get("dossier_id", type=int)
        record = record_or_404(dossier_id) if dossier_id else None
        creation_key = values.get("creation_key", "")
        if not record:
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", creation_key):
                return jsonify(error="Réouvrez le formulaire pour créer ce dossier."), 400
            record = HistoricalDossier.query.filter_by(creation_key=creation_key).first()
        patient_name = (values.get("patient_name") or "").strip()
        number = re.sub(r"[ .-]", "", values.get("national_number", "").strip())
        examination = (values.get("examination") or "").strip()
        report_text = (values.get("report_text") or "").strip()
        radiologist = (values.get("radiologist") or "").strip()
        reviewed = values.get("report_reviewed") == "1" and bool(report_text)
        status = values.get("transfer_status", "todo")
        try:
            examined_on = date.fromisoformat(values.get("examined_on", ""))
            report_date = date.fromisoformat(values["report_date"]) if values.get("report_date") else None
        except ValueError:
            return jsonify(error="Indiquez la date réelle de l’ancien examen et une date de compte rendu valide."), 400
        if examined_on > now().date() or (report_date and report_date > now().date()):
            return jsonify(error="Un dossier historique ne peut pas porter une date future."), 400
        if not valid_name(patient_name) or len(patient_name) > 255:
            return jsonify(error="Indiquez le prénom et le nom complets (au moins 5 lettres)."), 400
        if (number and not re.fullmatch(r"[0-9]{11}", number)) or not examination or len(examination) > 255:
            return jsonify(error="Vérifiez l’examen et le registre national (11 chiffres ou vide)."), 400
        if len(report_text) > 50000 or len(radiologist) > 255 or (report_text and not report_date):
            return jsonify(error="Le texte est limité à 50 000 caractères. Indiquez aussi la date du compte rendu."), 400
        kinds = {document.kind for document in record.documents} if record else set()
        complete = "request" in kinds and ("report" in kinds or reviewed)
        if status not in STATUS_LABELS or (status != "todo" and not complete):
            return jsonify(error="Ajoutez la demande et un compte rendu (PDF ou texte relu) avant de marquer le dossier prêt ou transféré."), 400
        incoming = dict(patient_name=patient_name, national_number=number, examined_on=examined_on,
            examination=examination, report_text=report_text, report_date=report_date,
            radiologist=radiologist, report_reviewed=reviewed, transfer_status=status)
        if record and all(getattr(record, key) == value for key, value in incoming.items()):
            return jsonify(ok=True, dossier=dossier_payload(record))
        if record and values.get("revision", type=int) != record.revision:
            return jsonify(error="Ce dossier a changé dans une autre fenêtre. Conservez votre texte et rechargez la version enregistrée."), 409
        if record is None:
            record = HistoricalDossier(creation_key=creation_key)
            db.session.add(record)
        for key, value in incoming.items():
            setattr(record, key, value)
        record.updated_at = datetime.utcnow()
        try:
            db.session.commit()
        except (IntegrityError, StaleDataError):
            db.session.rollback()
            return jsonify(error="Enregistrement concurrent. Conservez votre texte puis réessayez."), 409
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify(error="Dossier non enregistré. Votre texte reste dans le panneau : réessayez."), 503
        return jsonify(ok=True, dossier=dossier_payload(record))

    @app.get("/admin/appointments/history/<int:dossier_id>")
    def admin_historical_dossier(dossier_id):
        denied = authorize()
        if denied:
            return denied
        return jsonify(ok=True, dossier=dossier_payload(record_or_404(dossier_id)))

    @app.route("/admin/appointments/history/<int:dossier_id>/documents/<kind>", methods=["GET", "POST"])
    def admin_historical_document(dossier_id, kind):
        denied = authorize(request.method == "POST")
        if denied:
            return denied
        if kind not in {"request", "report"}:
            abort(404)
        record = record_or_404(dossier_id)
        document = next((item for item in record.documents if item.kind == kind), None)
        if request.method == "POST":
            upload = request.files.get("file")
            filename = secure_filename(upload.filename or "") if upload else ""
            if not filename.lower().endswith(".pdf") or len(filename) > 255:
                return jsonify(error="Choisissez un scan PDF de 10 Mo maximum."), 400
            data = upload.read(MAX_SCAN_BYTES + 1)
            try:
                if not data.startswith(b"%PDF-") or len(data) > MAX_SCAN_BYTES:
                    raise ValueError()
                reader = PdfReader(BytesIO(data), strict=True)
                if reader.is_encrypted or not 1 <= len(reader.pages) <= 200:
                    raise ValueError()
            except (ValueError, PdfReadError, OSError, RecursionError):
                return jsonify(error="PDF invalide ou protégé. Maximum : 10 Mo et 200 pages."), 400
            digest = hashlib.sha256(data).hexdigest()
            if document:
                if document.sha256 == digest:
                    return jsonify(ok=True, dossier=dossier_payload(record))
                return jsonify(error="Un document est déjà conservé ici. Il ne sera pas écrasé."), 409
            db.session.add(HistoricalDocument(dossier_id=record.id, kind=kind, filename=filename, data=data, sha256=digest))
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return jsonify(error="Un document vient déjà d’être ajouté. Actualisez le dossier."), 409
            except SQLAlchemyError:
                db.session.rollback()
                return jsonify(error="Document non enregistré. Réessayez sans fermer ce dossier."), 503
            # The relationship may already have been loaded before the insert.
            db.session.expire(record, ["documents"])
            return jsonify(ok=True, dossier=dossier_payload(record))
        if document is None:
            abort(404)
        response = app.response_class(document.data, mimetype="application/pdf")
        disposition = "inline" if request.args.get("inline") == "1" else "attachment"
        response.headers["Content-Disposition"] = f'{disposition}; filename="{document.filename}"'
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'; base-uri 'none'"
        return response

    @app.get("/admin/appointments/history/<int:dossier_id>/report.pdf")
    def admin_historical_report_pdf(dossier_id):
        denied = authorize()
        if denied:
            return denied
        record = record_or_404(dossier_id)
        if not record.report_text or not record.report_reviewed or not record.report_date:
            return jsonify(error="Enregistrez et relisez le texte avant de produire le PDF."), 400
        pdf = create_radiology_report_pdf(patient_name=record.patient_name, examination=record.examination,
            starts_at=record.examined_on, date_only=True, report_date=record.report_date,
            report_text=record.report_text, radiologist=record.radiologist, practice_address=practice_address)
        response = app.response_class(pdf, mimetype="application/pdf")
        response.headers["Content-Disposition"] = f'inline; filename="compte-rendu-historique-{record.id}.pdf"'
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
