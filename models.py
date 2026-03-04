from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

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