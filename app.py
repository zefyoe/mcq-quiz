import os
import random

from flask import Flask, render_template, request, session, redirect, url_for

from models import db
from questions_data import questions


def build_database_uri() -> str:
    """
    - Gebruikt DATABASE_URL als die bestaat (Render Postgres).
    - Anders fallback naar lokale SQLite.
    - Fix voor Render: postgres:// -> postgresql://
    - Forceer psycopg v3 driver: postgresql+psycopg:// (als je psycopg[binary] gebruikt)
    """
    uri = os.environ.get("DATABASE_URL", "sqlite:///quiz.db")

    # Render/Heroku geven soms postgres://, SQLAlchemy verwacht postgresql://
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    # Als we Postgres gebruiken: forceer psycopg v3 driver
    if uri.startswith("postgresql://"):
        uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)

    return uri


app = Flask(__name__)

# --- Config eerst ---
app.config["SQLALCHEMY_DATABASE_URI"] = build_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")  # nodig voor session

# --- DB init daarna ---
db.init_app(app)


def get_categories():
    return sorted({q["Category"] for q in questions})


def normalize_correct(q):
    # Zorg dat correct altijd een lijst is (ook bij 1 antwoord)
    return q["Correct"] if isinstance(q["Correct"], list) else [q["Correct"]]


@app.get("/setup-db")
def setup_db():
    """
    Maak tabellen aan.
    TIP: zet SETUP_TOKEN als env var op Render en roep aan met:
    /setup-db?token=JOUW_TOKEN
    """
    token_required = os.environ.get("SETUP_TOKEN")
    if token_required:
        provided = request.args.get("token")
        if provided != token_required:
            return "Forbidden", 403

    with app.app_context():
        db.create_all()
    return "DB tables created."


@app.route("/", methods=["GET", "POST"])
def home():
    categories = get_categories()

    if request.method == "POST":
        category = request.form.get("category")
        if category not in categories:
            return render_template("home.html", categories=categories, error="Ongeldige categorie.")
        return redirect(url_for("quiz", category=category))

    return render_template("home.html", categories=categories, error=None)


@app.route("/quiz/<category>", methods=["GET", "POST"])
def quiz(category):
    categories = get_categories()
    if category not in categories:
        return redirect(url_for("home"))

    # Filter vragen op categorie
    selected = [q for q in questions if q.get("Category") == category]
    if not selected:
        return render_template("home.html", categories=categories, error="Geen vragen in deze categorie.")

    if request.method == "GET":
        # Maak een willekeurige volgorde en bewaar die in session
        order = [q["ID"] for q in selected]
        random.shuffle(order)
        session["order"] = order
        session["category"] = category
        return render_template(
            "quiz.html",
            category=category,
            questions_by_id={q["ID"]: q for q in selected},
            order=order,
        )

    # POST: antwoorden nakijken
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

        # Bij multiple correct sturen we checkbox values -> lijst
        # Bij single correct sturen we radio value -> string
        user_multi = request.form.getlist(f"ans_{qid}")
        user_single = request.form.get(f"ans_{qid}")

        if user_multi:
            user_answers = sorted([a.strip().upper() for a in user_multi if a.strip()])
        else:
            user_answers = [user_single.strip().upper()] if user_single else []

        is_correct = sorted(user_answers) == sorted(correct)
        if is_correct:
            score += 1

        results.append(
            {
                "ID": q["ID"],
                "Vraag": q["Vraag"],
                "user": user_answers,
                "correct": correct,
                "is_correct": is_correct,
                "options": {"A": q["A"], "B": q["B"], "C": q["C"], "D": q["D"]},
            }
        )

    return render_template("result.html", category=category, score=score, total=len(order), results=results)


if __name__ == "__main__":
    app.run(debug=True, port=5002)