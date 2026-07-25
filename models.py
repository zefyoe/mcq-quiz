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
    quiz_attempts = db.relationship("QuizAttempt", backref="user", lazy=True, cascade="all, delete-orphan")
    question_progress = db.relationship("QuestionProgress", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, pw: str):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw: str) -> bool:
        return check_password_hash(self.password_hash, pw)

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
    last_answered_at = db.Column(db.DateTime, nullable=True)
    next_review_at = db.Column(db.DateTime, nullable=True, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "question_key", name="uq_question_progress_user_key"),
    )
