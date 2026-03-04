import os
from models import db, Question, User
from flask import Flask, render_template, request, session, redirect, url_for
import random
from questions_data import questions

from flask_login import LoginManager, login_required, current_user

app = Flask(__name__)

@app.get("/setup-db")
def setup_db():
    db.create_all()
    return "DB tables created."

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///quiz.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

# Login manager
login_manager = LoginManager()
login_manager.login_view = "home"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def get_categories():
    return sorted({q["Category"] for q in questions})


def normalize_correct(q):
    return q["Correct"] if isinstance(q["Correct"], list) else [q["Correct"]]


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

    selected = [q for q in questions if q.get("Category") == category]
    if not selected:
        return render_template("home.html", categories=categories, error="Geen vragen in deze categorie.")

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

    return render_template("result.html", category=category, score=score, total=len(order), results=results)


# =====================
# ADMIN ROUTES
# =====================

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
            error = "Vul alle velden in."

        elif correct not in ["A", "B", "C", "D"]:
            error = "Correct moet A, B, C of D zijn."

        elif db.session.query(Question.id).filter_by(qid=qid).first():
            error = f"Vraag bestaat al: {qid}"

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
                image_url=image_url
            )

            db.session.add(q)
            db.session.commit()

            success = "Vraag toegevoegd!"

    return render_template(
        "admin_new_question.html",
        error=error,
        success=success
    )


# =====================
@app.route("/create-admin")
def create_admin():

    email = "admin@example.com"
    password = "admin123"

    if User.query.filter_by(email=email).first():
        return "Admin bestaat al."

    admin = User(
        email=email,
        is_admin=True
    )

    admin.set_password(password)

    db.session.add(admin)
    db.session.commit()

    return "Admin user created!"
    
if __name__ == "__main__":
    app.run(debug=True, port=5001)