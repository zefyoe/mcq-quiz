import os
import random
from datetime import timedelta
from urllib.parse import urlparse

from flask import Flask, render_template, request, session, redirect, url_for, abort
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
    if uri.startswith("postgresql://") and not uri.startswith("postgresql+psycopg://"):
        uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)

    return uri


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = build_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# En production, SECRET_KEY doit exister sur Render
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me-please-set-secret-key")

# Si Render est derrière HTTPS, sécurise le cookie en prod
if os.environ.get("RENDER") or os.environ.get("FLASK_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True

db.init_app(app)


# -------------------------
# Login setup
# -------------------------

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = None
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


# -------------------------
# Helpers
# -------------------------

def normalize_correct(q: dict) -> list[str]:
    correct = q["Correct"] if isinstance(q["Correct"], list) else [q["Correct"]]
    return sorted([(c or "").strip().upper() for c in correct if c])


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

    cats |= {q["Category"].strip() for q in questions if q.get("Category")}
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


def is_safe_next_url(target: str) -> bool:
    if not target:
        return False

    ref_url = urlparse(request.host_url)
    test_url = urlparse(url_for("home", _external=True) if target == "" else request.host_url.rstrip("/") + "/")

    redirect_url = urlparse(target if "://" in target else url_for("home", _external=True).replace(urlparse(url_for("home", _external=True)).path, "") + target)

    return (
        redirect_url.scheme in ("http", "https")
        and ref_url.netloc == redirect_url.netloc
    )


def safe_redirect_target(target: str, fallback_endpoint: str = "home") -> str:
    if not target:
        return url_for(fallback_endpoint)

    parsed = urlparse(target)

    # Autorise seulement les chemins relatifs locaux
    if parsed.scheme or parsed.netloc:
        return url_for(fallback_endpoint)

    if not target.startswith("/"):
        return url_for(fallback_endpoint)

    return target


# -------------------------
# Response headers
# -------------------------

@app.after_request
def add_no_cache_headers(response):
    # Évite les comportements de cache indésirables sur les pages dynamiques
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# -------------------------
# Health route
# -------------------------

@app.get("/health")
def health():
    return "ok", 200


# -------------------------
# Optional DB setup route
# -------------------------

@app.get("/setup-db")
def setup_db():
    token_required = os.environ.get("SETUP_DB_TOKEN")

    if not token_required:
        return "Setup route disabled.", 403

    if request.args.get("token") != token_required:
        return "Forbidden", 403

    db.create_all()
    return "Database tables created.", 200


# -------------------------
# Routes
# -------------------------

@app.route("/", methods=["GET", "POST"])
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))

    categories = get_categories()

    if request.method == "POST":
        category = (request.form.get("category") or "").strip()
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
        return render_template(
            "home.html",
            categories=categories,
            error="No questions found in this category."
        )

    if request.method == "GET":
        order = [q["ID"] for q in selected]
        random.shuffle(order)
        session["order"] = order
        session["category"] = category
        session.permanent = True

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

        is_correct = user_answers == correct
        if is_correct:
            score += 1

        results.append({
            "ID": q["ID"],
            "Vraag": q["Vraag"],
            "user": user_answers,
            "correct": correct,
            "is_correct": is_correct,
            "options": {
                "A": q["A"],
                "B": q["B"],
                "C": q["C"],
                "D": q["D"],
            },
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
    next_url = safe_redirect_target(request.args.get("next"), "home")

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        next_url = safe_redirect_target(request.form.get("next"), "home")

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            error = "Incorrect email or password."
        else:
            login_user(user)
            session.permanent = True
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
            session.permanent = True
            return redirect(url_for("home"))

    return render_template("register.html", error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
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
# Main
# -------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)