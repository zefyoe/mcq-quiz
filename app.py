import os
import random

from flask import Flask, render_template, request, session, redirect, url_for
from flask_login import (
    LoginManager,
    login_required,
    current_user,
    login_user,
    logout_user,
)

from sqlalchemy import func

from models import db, Question, User
from questions_data import questions


# -------------------------
# App + DB config
# -------------------------

def build_database_uri() -> str:
    uri = os.environ.get("DATABASE_URL", "sqlite:///quiz.db")

    # Render sometimes gives postgres://, SQLAlchemy expects postgresql://
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    # Force psycopg v3 driver
    if uri.startswith("postgresql://"):
        uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)

    return uri


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = build_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

db.init_app(app)


# -------------------------
# Login setup
# -------------------------

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# -------------------------
# Helpers
# -------------------------

def normalize_correct(q: dict) -> list[str]:
    return q["Correct"] if isinstance(q["Correct"], list) else [q["Correct"]]


def normalize_category(s: str) -> str:
    return (s or "").strip().lower()


def db_question_to_dict(q: Question) -> dict:
    return {
        "ID": q.qid,
        "Category": q.category,
        "Vraag": q.text,
        "A": q.a,
        "B": q.b,
        "C": q.c,
        "D": q.d,
        "Correct": [q.correct],
        "image_url": q.image_url,
    }


def get_categories() -> list[str]:
    cats = set()

    for (c,) in db.session.query(Question.category).distinct().all():
        if c:
            cats.add(c.strip())

    cats |= {q["Category"] for q in questions}

    return sorted(cats)


def get_questions_for_category(category: str) -> list[dict]:
    cat_norm = normalize_category(category)

    db_qs = (
        Question.query
        .filter(func.lower(func.trim(Question.category)) == cat_norm)
        .all()
    )
    if db_qs:
        return [db_question_to_dict(q) for q in db_qs]

    return [q for q in questions if normalize_category(q.get("Category")) == cat_norm]


# -------------------------
# Routes
# -------------------------

@app.get("/setup-db")
def setup_db():
    token_required = os.environ.get("SETUP_DB_TOKEN")
    if token_required and request.args.get("token") != token_required:
        return "Forbidden", 403

    with app.app_context():
        db.create_all()

    return "Database tables created."


@app.route("/", methods=["GET", "POST"])
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))

    categories = get_categories()

    if request.method == "POST":
        category = request.form.get("category")
        if category not in categories:
            return render_template("home.html", categories=categories, error="Invalid category.")
        return redirect(url_for("quiz", category=category))

    return render_template("home.html", categories=categories, error=None)


@app.route("/quiz/<category>", methods=["GET", "POST"])
@login_required
def quiz(category):
    categories = get_categories()
    if category not in categories:
        return redirect(url_for("home"))

    selected = get_questions_for_category(category)
    if not selected:
        return render_template("home.html", categories=categories, error="No questions found in this category.")

    if request.method == "GET":
        order = [q["ID"] for q in selected]
        random.shuffle(order)
        session["order"] = order
        session["category"] = category

        return render_template(
            "quiz.html",
            category=category,
            questions_by_id={q["ID"]: q for q in selected},
            order=order
        )

    order = session.get("order", [])
    if not order or session.get("category") != category:
        return redirect(url_for("quiz", category=category))

    selected_by_id = {q["ID"]: q for q in selected}

    results = []
    score = 0

    for qid in order:
        q = selected_by_id.get(qid)
        if not q:
            continue

        correct = normalize_correct(q)

        user_multi = request.form.getlist(f"ans_{qid}")
        user_single = request.form.get(f"ans_{qid}")

        if user_multi:
            user_answers = sorted([a.strip().upper() for a in user_multi if a.strip()])
        else:
            user_answers = [user_single.strip().upper()] if user_single else []

        is_correct = sorted(user_answers) == sorted(correct)
        if is_correct:
            score += 1

        results.append({
            "ID": q["ID"],
            "Vraag": q["Vraag"],
            "user": user_answers,
            "correct": correct,
            "is_correct": is_correct,
            "options": {"A": q["A"], "B": q["B"], "C": q["C"], "D": q["D"]},
        })

    return render_template(
        "result.html",
        category=category,
        score=score,
        total=len(order),
        results=results
    )


# -------------------------
# Auth routes
# -------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    error = None
    next_url = request.args.get("next") or url_for("home")

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        next_url = request.form.get("next") or url_for("home")

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            error = "Incorrect email or password."
        else:
            login_user(user)
            return redirect(next_url)

    return render_template("login.html", error=error, next=next_url)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    error = None

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not email or not password or not confirm_password:
            error = "Please fill in all fields."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif len(password) < 8:
            error = "Password must be at least 8 characters long."
        elif User.query.filter_by(email=email).first():
            error = "An account with this email already exists."
        else:
            user = User(email=email, is_admin=False)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            login_user(user)
            return redirect(url_for("home"))

    return render_template("register.html", error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# -------------------------
# Admin routes
# -------------------------

@app.route("/admin")
@login_required
def admin_home():
    if not getattr(current_user, "is_admin", False):
        return "Forbidden", 403
    return render_template("admin_home.html")


@app.route("/admin/questions/new", methods=["GET", "POST"])
@login_required
def admin_new_question():
    if not getattr(current_user, "is_admin", False):
        return "Forbidden", 403

    error = None
    success = None

    if request.method == "POST":
        qid = (request.form.get("qid") or "").strip()
        category = (request.form.get("category") or "").strip()
        text = (request.form.get("text") or "").strip()

        a = (request.form.get("a") or "").strip()
        b = (request.form.get("b") or "").strip()
        c = (request.form.get("c") or "").strip()
        d = (request.form.get("d") or "").strip()

        correct = (request.form.get("correct") or "").strip().upper()
        image_url = (request.form.get("image_url") or "").strip() or None

        if not all([qid, category, text, a, b, c, d, correct]):
            error = "Please fill in all required fields."
        elif correct not in ["A", "B", "C", "D"]:
            error = "Correct answer must be A, B, C, or D."
        elif db.session.query(Question.id).filter_by(qid=qid).first():
            error = f"Question already exists: {qid}"
        else:
            q = Question(
                qid=qid,
                category=category,
                text=text,
                a=a,
                b=b,
                c=c,
                d=d,
                correct=correct,
                image_url=image_url,
            )
            db.session.add(q)
            db.session.commit()
            success = "Question added successfully."

    return render_template("admin_new_question.html", error=error, success=success)


# -------------------------
# Temporary: change admin password (REMOVE AFTER USE)
# -------------------------

@app.route("/change-admin-password")
def change_admin_password():
    email = "admin@example.com"
    new_password = "MyNewStrongPassword123"

    user = User.query.filter_by(email=email).first()
    if not user:
        return "Admin not found.", 404

    user.set_password(new_password)
    db.session.commit()
    return "Admin password changed."


if __name__ == "__main__":
    app.run(debug=True, port=5001)