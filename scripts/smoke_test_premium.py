import os
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
    assert {"name", "university", "daily_question_goal"} <= user_columns
    assert {"quiz_mode", "results_json", "duration_seconds"} <= attempt_columns
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
assert_ok(client.get("/"), "dashboard")

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
