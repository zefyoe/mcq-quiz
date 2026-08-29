import os
import sqlite3
import sys
import tempfile
from pathlib import Path


os.environ["PUBLIC_SITE_MODE"] = "active"

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
connection = sqlite3.connect(database_file.name)
connection.execute(
    'CREATE TABLE "user" ('
    "id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE, "
    "password_hash VARCHAR(255) NOT NULL, is_admin BOOLEAN DEFAULT 0)"
)
connection.commit()
connection.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "core-access-smoke-test"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app, db  # noqa: E402
from models import QuizAttempt, User  # noqa: E402


def add_user(email, *, is_admin=False):
    user = User(
        name=email.split("@", 1)[0],
        university="Test University",
        email=email,
        is_admin=is_admin,
    )
    user.set_password("strong-password")
    db.session.add(user)
    return user


def login(client, email):
    return client.post(
        "/login",
        data={"email": email, "password": "strong-password"},
        follow_redirects=True,
    )


try:
    with app.app_context():
        db.drop_all()
        db.create_all()
        student = add_user("student@example.com")
        rogue_admin = add_user("rogue-admin@example.com", is_admin=True)
        primary_admin = add_user("y@bymed.be")
        second_admin = add_user("ybahkani@gmail.com")
        db.session.flush()
        core_attempt = QuizAttempt(
            user_id=student.id,
            category="CORE Radiology",
            subgroup="chest",
            quiz_mode="test",
            study_format="flashcard",
            title="Restricted CORE attempt",
            score=0,
            total_questions=1,
            question_ids_json='["CORE-CH-001"]',
        )
        db.session.add(core_attempt)
        db.session.commit()
        core_attempt_id = core_attempt.id

    client = app.test_client()
    response = login(client, "student@example.com")
    assert response.status_code == 200
    assert b"/switch-product/core" not in response.data
    assert client.get("/switch-product/core").status_code == 403
    assert client.get("/core").status_code == 403
    assert client.get("/core/chest").status_code == 403
    assert client.post("/core/rate", json={}).status_code == 403
    history = client.get("/previous-tests")
    assert history.status_code == 200
    assert b"Restricted CORE attempt" not in history.data
    assert client.get(f"/previous-tests/{core_attempt_id}/report").status_code == 403
    assert client.get(f"/previous-tests/{core_attempt_id}/retake").status_code == 403
    client.get("/logout")

    response = login(client, "rogue-admin@example.com")
    assert response.status_code == 200
    assert client.get("/core").status_code == 403
    with app.app_context():
        assert User.query.filter_by(email="rogue-admin@example.com").one().is_admin is False
    client.get("/logout")

    for email in ("y@bymed.be", "ybahkani@gmail.com"):
        response = login(client, email)
        assert response.status_code == 200
        assert b"/switch-product/core" in response.data
        assert client.get("/core").status_code == 200
        assert client.get("/admin").status_code == 200
        switch_response = client.get("/switch-product/core")
        assert switch_response.status_code == 302
        assert switch_response.headers["Location"] == "https://core.bymed.be/core"
        with app.app_context():
            assert User.query.filter_by(email=email).one().is_admin is True
        client.get("/logout")
finally:
    os.unlink(database_file.name)

print("CORE access smoke test passed.")
