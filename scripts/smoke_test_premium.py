import os
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
connection = sqlite3.connect(database_file.name)
connection.execute(
    'CREATE TABLE "user" ('
    "id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE, "
    "password_hash VARCHAR(255) NOT NULL, is_admin BOOLEAN DEFAULT 0)"
)
connection.execute(
    "CREATE TABLE quiz_attempt ("
    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, category VARCHAR(120) NOT NULL, "
    "subgroup VARCHAR(80), title VARCHAR(160) NOT NULL, score INTEGER NOT NULL, "
    "total_questions INTEGER NOT NULL, question_ids_json TEXT NOT NULL, created_at DATETIME NOT NULL)"
)
connection.execute(
    "CREATE TABLE question_progress ("
    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, question_key VARCHAR(500) NOT NULL, "
    "subgroup VARCHAR(80), times_seen INTEGER NOT NULL DEFAULT 0, "
    "times_correct INTEGER NOT NULL DEFAULT 0, correct_streak INTEGER NOT NULL DEFAULT 0, "
    "last_was_correct BOOLEAN, is_marked BOOLEAN NOT NULL DEFAULT 0, "
    "last_answered_at DATETIME, next_review_at DATETIME, updated_at DATETIME NOT NULL)"
)
connection.commit()
connection.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "premium-smoke-test"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app, db, get_questions_by_ids  # noqa: E402
from models import QuizAttempt, User  # noqa: E402
from sqlalchemy import inspect  # noqa: E402


def assert_ok(response, label):
    assert response.status_code == 200, f"{label}: HTTP {response.status_code}"


with app.app_context():
    user_columns = {column["name"] for column in inspect(db.engine).get_columns("user")}
    attempt_columns = {column["name"] for column in inspect(db.engine).get_columns("quiz_attempt")}
    progress_columns = {column["name"] for column in inspect(db.engine).get_columns("question_progress")}
    assert {"name", "university", "daily_question_goal"} <= user_columns
    assert {"quiz_mode", "study_format", "results_json", "duration_seconds"} <= attempt_columns
    assert {"flashcard_rating", "flashcard_times_seen", "flashcard_rated_at"} <= progress_columns
    db.drop_all()
    db.create_all()
    student = User(
        name="Test Student",
        university="VUB",
        email="student@example.com",
        daily_question_goal=20,
    )
    student.set_password("strong-password")
    admin = User(
        name="Test Admin",
        university="VUB",
        email="y@bymed.be",
        is_admin=True,
    )
    admin.set_password("strong-password")
    db.session.add_all([student, admin])
    db.session.commit()
    student_id = student.id

client = app.test_client()
response = client.post(
    "/login",
    data={"email": "student@example.com", "password": "strong-password"},
    follow_redirects=True,
)
assert_ok(response, "student login")
assert_ok(client.get("/profile"), "profile")
response = client.post(
    "/profile",
    data={
        "action": "profile",
        "name": "Updated Student",
        "university": "Vrije Universiteit Brussel",
        "daily_question_goal": "30",
    },
)
assert_ok(response, "profile update")
assert b"30" in response.data

response = client.get("/quiz/Anatomy?subgroup=mixed&count=2&mode=exam")
assert_ok(response, "quiz")
assert response.data.count(b' src="/static/images/') == 1
assert b'rel="preload" as="image"' in response.data
assert b"style.css?v=" in response.data
with client.session_transaction() as quiz_session:
    order = list(quiz_session["order"])

with app.app_context():
    selected = {question["ID"]: question for question in get_questions_by_ids(order)}
answers = {
    f"ans_{qid}": (
        question["Correct"][0]
        if isinstance(question["Correct"], list)
        else question["Correct"]
    )
    for qid, question in selected.items()
}
answers["duration_seconds"] = "91"
response = client.post("/quiz/Anatomy?subgroup=mixed", data=answers)
assert_ok(response, "quiz submission")
assert b"Report / PDF" in response.data

with app.app_context():
    attempt = QuizAttempt.query.filter_by(user_id=student_id).one()
    assert attempt.duration_seconds == 91
    assert attempt.results_json
    attempt_id = attempt.id

response = client.get(f"/previous-tests/{attempt_id}/report")
assert_ok(response, "attempt report")
assert b"1m 31s" in response.data
assert_ok(client.get("/previous-tests"), "history")
response = client.get("/")
assert_ok(response, "dashboard")
assert response.data.count(b'class="product-category-row"') == 4
assert b'href="/anatomy/msk"' in response.data
assert b'href="/anatomy/genito-urinary"' in response.data
assert b'href="/anatomy/head-and-neck"' in response.data
assert b'href="/anatomy/mixed"' in response.data
assert b'href="/" class="dashboard-sidebar-brand"' in response.data

response = client.get(
    "/quiz/Anatomy?subgroup=mixed&count=2&format=flashcard",
    follow_redirects=True,
)
assert_ok(response, "flashcard session")
assert b"Show answer" in response.data
assert b"MCQ" in response.data
assert b"Question ID:" in response.data
assert b'<a href="/" class="brand brand-link">Rady</a>' in response.data
with client.session_transaction() as flashcard_session:
    flashcard_order = list(flashcard_session["order"])
response = client.get("/quiz/Anatomy?subgroup=mixed&resume=1")
assert_ok(response, "switch flashcard to MCQ")
assert b"Anki" in response.data
with client.session_transaction() as switched_session:
    assert switched_session["order"] == flashcard_order
response = client.get("/flashcards/Anatomy?subgroup=mixed&resume=1")
assert_ok(response, "switch MCQ to flashcard")
with client.session_transaction() as switched_session:
    assert switched_session["order"] == flashcard_order
ratings = {
    flashcard_order[0]: "very_difficult",
    flashcard_order[1]: "easy",
}
for qid, rating in ratings.items():
    response = client.post(
        "/flashcards/rate",
        json={"qid": qid, "rating": rating, "subgroup": "mixed"},
    )
    assert response.status_code == 200
    assert response.get_json()["rating"] == rating

response = client.post(
    "/flashcards/Anatomy",
    data={
        "subgroup": "mixed",
        "ratings_json": json.dumps(ratings),
        "duration_seconds": "45",
    },
)
assert_ok(response, "flashcard completion")
assert b"SESSION COMPLETE" in response.data
assert b"Study these again" in response.data

with app.app_context():
    flashcard_attempt = QuizAttempt.query.filter_by(
        user_id=student_id,
        study_format="flashcard",
    ).one()
    assert flashcard_attempt.duration_seconds == 45
    assert flashcard_attempt.score == 1
    flashcard_attempt_id = flashcard_attempt.id

response = client.get(
    f"/previous-tests/{flashcard_attempt_id}/retake",
    follow_redirects=True,
)
assert_ok(response, "flashcard history retake")
assert b"Show answer" in response.data
with client.session_transaction() as flashcard_session:
    assert flashcard_session["order"] == flashcard_order

response = client.get(
    "/flashcards/Anatomy?subgroup=mixed&rating=very_difficult&count=10",
)
assert_ok(response, "very difficult retest")
with client.session_transaction() as flashcard_session:
    assert flashcard_session["order"] == [flashcard_order[0]]
response = client.post(
    "/flashcards/rate",
    json={
        "qid": flashcard_order[0],
        "rating": "easy",
        "subgroup": "mixed",
    },
)
assert response.status_code == 200
assert response.get_json()["counts"]["very_difficult"] == 0
assert response.get_json()["counts"]["easy"] == 2
with client.session_transaction() as language_session:
    language_session["language"] = "nl"
assert b"Anki-flashcards" in client.get("/anatomy/mixed?format=flashcard").data
assert b"Toon antwoord" in client.get("/flashcards/Anatomy?subgroup=mixed&resume=1").data
with client.session_transaction() as language_session:
    language_session["language"] = "en"

response = client.get("/core")
assert_ok(response, "CORE dashboard")
assert b"171" in response.data
assert b"Chest Imaging" in response.data
assert response.data.count(b'class="product-category-row') == 11
assert b"Anatomy QBank" in response.data
assert b">CORE Gastro-intestinal</a>" not in response.data
assert_ok(client.get("/core/chest"), "empty CORE section")
assert b"0/0" in client.get("/core/chest").data
response = client.get("/core/gastrointestinal")
assert_ok(response, "CORE GI setup")
assert b"ANKI ONLY" in response.data

response = client.get("/core/gastrointestinal/study?pool=all&count=2")
assert_ok(response, "CORE GI study")
assert b"Show answer" in response.data
assert b"MCQ" not in response.data
assert response.data.count(b'data-src="/static/core/') == 4
assert response.data.count(b' src="/static/core/') == 1
assert b'rel="preload" as="image"' in response.data
with client.session_transaction() as core_session:
    core_order = list(core_session["order"])
assert len(core_order) == 2
assert all(qid.startswith("CORE-GI-") for qid in core_order)

core_ratings = {
    core_order[0]: "difficult",
    core_order[1]: "very_easy",
}
for qid, rating in core_ratings.items():
    response = client.post(
        "/core/rate",
        json={"qid": qid, "rating": rating, "subgroup": "gastrointestinal"},
    )
    assert response.status_code == 200

response = client.post(
    "/core/gastrointestinal/study",
    data={
        "subgroup": "gastrointestinal",
        "ratings_json": json.dumps(core_ratings),
        "duration_seconds": "73",
    },
)
assert_ok(response, "CORE completion")
assert b"CORE Radiology - Gastrointestinal Imaging" in response.data

with app.app_context():
    core_attempt = QuizAttempt.query.filter_by(
        user_id=student_id,
        category="CORE Radiology",
        study_format="flashcard",
    ).one()
    assert core_attempt.duration_seconds == 73
    core_attempt_id = core_attempt.id

assert_ok(client.get("/core/history"), "CORE history")
assert_ok(client.get(f"/previous-tests/{core_attempt_id}/report"), "CORE report")
response = client.get(
    f"/previous-tests/{core_attempt_id}/retake",
    follow_redirects=True,
)
assert_ok(response, "CORE history retake")
assert b"Show answer" in response.data
assert_ok(client.get("/static/core/gastrointestinal/c1_q_0.png"), "CORE media")
style_response = client.get("/static/style.css")
assert_ok(style_response, "static stylesheet")
assert "max-age=604800" in style_response.headers.get("Cache-Control", "")
assert b".core-product .flashcard-image-frame" in style_response.data
assert b"max-height: 540px" in style_response.data

anonymous_client = app.test_client()
response = anonymous_client.get("/", base_url="https://core.bymed.be")
assert response.status_code == 302
assert response.headers["Location"].endswith("/core")

client.get("/logout")
response = client.post(
    "/login",
    data={"email": "y@bymed.be", "password": "strong-password"},
    follow_redirects=True,
)
assert_ok(response, "admin login")
response = client.get("/admin/database?q=anatomical&table=anatomy&correct=A")
assert_ok(response, "admin filters")
assert b"Apply filters" in response.data

os.unlink(database_file.name)
print("Premium smoke test passed.")
