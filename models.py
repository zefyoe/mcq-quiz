from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=True)
    university = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    daily_question_goal = db.Column(db.Integer, nullable=False, default=20)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True, index=True)
    last_login_at = db.Column(db.DateTime, nullable=True, index=True)
    quiz_attempts = db.relationship("QuizAttempt", backref="user", lazy=True, cascade="all, delete-orphan")
    question_progress = db.relationship("QuestionProgress", backref="user", lazy=True, cascade="all, delete-orphan")
    login_events = db.relationship("LoginEvent", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, pw: str):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw: str) -> bool:
        return check_password_hash(self.password_hash, pw)


class LoginEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    logged_in_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class Appointment(db.Model):
    """A booked ultrasound appointment in the private-practice agenda."""

    id = db.Column(db.Integer, primary_key=True)
    starts_at = db.Column(db.DateTime, nullable=False, unique=True, index=True)
    patient_name = db.Column(db.String(255), nullable=False)
    patient_email = db.Column(db.String(255), nullable=False)
    patient_phone = db.Column(db.String(80), nullable=True)
    referring_doctor = db.Column(db.String(255), nullable=True)
    insurance_status = db.Column(db.String(16), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False, default=10)
    appointment_type = db.Column(db.String(120), nullable=False, default="Consultatie")
    inami_code = db.Column(db.String(12), nullable=True, index=True)
    inami_consult_code = db.Column(db.String(12), nullable=True)
    inami_n_value = db.Column(db.String(20), nullable=True)
    inami_exam_reimbursement_cents = db.Column(db.Integer, nullable=True)
    inami_exam_patient_share_cents = db.Column(db.Integer, nullable=True)
    inami_exam_total_cents = db.Column(db.Integer, nullable=True)
    inami_consult_reimbursement_cents = db.Column(db.Integer, nullable=True)
    inami_consult_patient_share_cents = db.Column(db.Integer, nullable=True)
    inami_consult_total_cents = db.Column(db.Integer, nullable=True)
    inami_invoice_total_cents = db.Column(db.Integer, nullable=True)
    inami_tariff_effective_date = db.Column(db.String(10), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    prescription_filename = db.Column(db.String(255), nullable=True)
    prescription_mimetype = db.Column(db.String(120), nullable=True)
    prescription_data = db.Column(db.LargeBinary, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class AppointmentMoveReceipt(db.Model):
    """Atomic move receipt: safe retries and the previous scheduling position."""
    token = db.Column(db.String(36), primary_key=True)
    fingerprint = db.Column(db.String(64), nullable=False)
    source_kind = db.Column(db.String(12), nullable=False)
    appointment_id = db.Column(db.Integer, nullable=True)
    previous_start = db.Column(db.DateTime, nullable=False)
    target_start = db.Column(db.DateTime, nullable=False)
    context_key = db.Column(db.String(64), nullable=False)
    requested_by = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AppointmentTrash(db.Model):
    """Recoverable internal cancellation; original documents remain private."""
    token = db.Column(db.String(36), primary_key=True)
    fingerprint = db.Column(db.String(64), nullable=False)
    source_kind = db.Column(db.String(12), nullable=False)
    context_key = db.Column(db.String(64), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    record_data = db.deferred(db.Column(db.Text, nullable=False))
    prescription_data = db.deferred(db.Column(db.LargeBinary, nullable=True))
    deleted_by = db.Column(db.Integer, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    restored_at = db.Column(db.DateTime, nullable=True)


class AppointmentHold(db.Model):
    starts_at = db.Column(db.DateTime, primary_key=True)
    token = db.Column(db.String(80), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    draft_data = db.Column(db.Text, nullable=True)
    prescription_filename = db.Column(db.String(255), nullable=True)
    prescription_mimetype = db.Column(db.String(120), nullable=True)
    prescription_data = db.Column(db.LargeBinary, nullable=True)

    @property
    def draft(self):
        import json
        try:
            return json.loads(self.draft_data or "{}")
        except (TypeError, ValueError):
            return {}


class GmailConnection(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    google_subject = db.Column(db.String(255), nullable=False)
    encrypted_refresh_token = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AppointmentReport(db.Model):
    """Private report linked to a specific booking, with an identity snapshot."""
    id = db.Column(db.Integer, primary_key=True)
    context_key = db.Column(db.String(64), nullable=False, unique=True)
    patient_name = db.Column(db.String(255), nullable=False)
    examination = db.Column(db.String(1000), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    report_text = db.Column(db.Text, nullable=False)
    radiologist = db.Column(db.String(255), nullable=False, default="")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    revision = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": revision}


class AppointmentPatientDetails(db.Model):
    """Optional identifiers, private to a specific booking, never public."""
    context_key = db.Column(db.String(64), primary_key=True)
    national_number = db.Column(db.String(11), nullable=False, default="")
    billing_code = db.Column(db.String(6), nullable=False, default="")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AppointmentSlotOverride(db.Model):
    """Admin controlled, date-specific public availability for a 10-minute slot."""
    starts_at = db.Column(db.DateTime, primary_key=True)
    is_open = db.Column(db.Boolean, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class HistoricalDossier(db.Model):
    """Manually entered legacy examination; never occupies a calendar slot."""
    id = db.Column(db.Integer, primary_key=True)
    creation_key = db.Column(db.String(80), nullable=False, unique=True)
    patient_name = db.Column(db.String(255), nullable=False)
    national_number = db.Column(db.String(11), nullable=False, default="")
    billing_code = db.Column(db.String(6), nullable=False, default="")
    examined_on = db.Column(db.Date, nullable=False, index=True)
    examination = db.Column(db.String(255), nullable=False)
    transfer_status = db.Column(db.String(16), nullable=False, default="todo")
    report_text = db.deferred(db.Column(db.Text, nullable=False, default=""))
    report_date = db.Column(db.Date, nullable=True)
    radiologist = db.Column(db.String(255), nullable=False, default="")
    report_reviewed = db.Column(db.Boolean, nullable=False, default=False)
    revision = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    documents = db.relationship("HistoricalDocument", lazy="selectin", backref="dossier")
    __mapper_args__ = {"version_id_col": revision}


class InternalRegisterExclusion(db.Model):
    """Recoverable removal from both administrative lists, not the agenda."""
    context_key = db.Column(db.String(64), primary_key=True)
    is_removed = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, nullable=False)


class HistoricalDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey("historical_dossier.id"), nullable=False, index=True)
    kind = db.Column(db.String(12), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    data = db.deferred(db.Column(db.LargeBinary, nullable=False))
    sha256 = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("dossier_id", "kind", name="uq_historical_document_kind"),)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    qid = db.Column(db.String(50), unique=True, nullable=False)      # bv Q011
    category = db.Column(db.String(80), nullable=False)
    text = db.Column(db.Text, nullable=False)

    a = db.Column(db.Text, nullable=False)
    b = db.Column(db.Text, nullable=False)
    c = db.Column(db.Text, nullable=False)
    d = db.Column(db.Text, nullable=False)

    correct = db.Column(db.String(1), nullable=False)               # A/B/C/D
    image_url = db.Column(db.Text, nullable=True)                   # later voor JPEG


class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category = db.Column(db.String(120), nullable=False)
    subgroup = db.Column(db.String(80), nullable=True)
    quiz_mode = db.Column(db.String(20), nullable=False, default="test")
    study_format = db.Column(db.String(20), nullable=False, default="mcq")
    title = db.Column(db.String(160), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    question_ids_json = db.Column(db.Text, nullable=False)
    results_json = db.Column(db.Text, nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class QuestionProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    question_key = db.Column(db.String(500), nullable=False)
    subgroup = db.Column(db.String(80), nullable=True, index=True)
    times_seen = db.Column(db.Integer, nullable=False, default=0)
    times_correct = db.Column(db.Integer, nullable=False, default=0)
    correct_streak = db.Column(db.Integer, nullable=False, default=0)
    last_was_correct = db.Column(db.Boolean, nullable=True)
    is_marked = db.Column(db.Boolean, nullable=False, default=False, index=True)
    flashcard_rating = db.Column(db.String(24), nullable=True, index=True)
    flashcard_times_seen = db.Column(db.Integer, nullable=False, default=0)
    flashcard_rated_at = db.Column(db.DateTime, nullable=True)
    last_answered_at = db.Column(db.DateTime, nullable=True)
    next_review_at = db.Column(db.DateTime, nullable=True, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "question_key", name="uq_question_progress_user_key"),
    )
