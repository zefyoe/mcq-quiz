import os
import sys
import tempfile
from pathlib import Path


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "anatomy-latin-smoke-test"
os.environ["ENABLE_LANGUAGE_SWITCHER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import session  # noqa: E402
from flask_login import login_user  # noqa: E402

from app import app, db, localize_question_for_display  # noqa: E402
from models import User  # noqa: E402
from sourced_latin_terms import SOURCED_LATIN_SOURCES, SOURCED_LATIN_TERMS  # noqa: E402


try:
    with app.app_context():
        admin = User(
            name="Test Admin",
            university="Test University",
            email="y@bymed.be",
            is_admin=True,
        )
        admin.set_password("strong-password")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    with app.test_request_context("/anatomy/msk"):
        admin = db.session.get(User, admin_id)
        login_user(admin)
        session["language"] = "nl"
        localized = localize_question_for_display({
            "Category": "Anatomy - MSK",
            "Vraag": "Which anatomical structure is depicted?",
            "A": "femoral artery",
            "B": "common femoral vein",
            "C": "femoral head",
            "D": "femoral neck",
        })

        assert localized["Vraag"] == "Welke anatomische structuur is afgebeeld?"
        assert localized["A"] == "Arteria femoralis"
        assert localized["B"] == "Vena femoralis communis"
        assert localized["C"] == "Caput femoris"
        assert localized["D"] == "Collum femoris"

        session["language"] = "fr"
        localized_fr = localize_question_for_display({
            "Category": "Anatomy - MSK",
            "Vraag": "Which anatomical structure is depicted?",
            "A": "femoral artery",
            "B": "common femoral vein",
            "C": "femoral head",
            "D": "femoral neck",
        })

        assert localized_fr["Vraag"] == "Quelle structure anatomique est représentée ?"
        assert localized_fr["A"] == "Arteria femoralis"
        assert localized_fr["B"] == "Vena femoralis communis"
        assert localized_fr["C"] == "Caput femoris"
        assert localized_fr["D"] == "Collum femoris"

    assert len(SOURCED_LATIN_TERMS) == len(SOURCED_LATIN_SOURCES)
    assert len(SOURCED_LATIN_TERMS) >= 450
    assert SOURCED_LATIN_TERMS["femoral artery"] == "Arteria femoralis"
    assert SOURCED_LATIN_SOURCES["femoral artery"].startswith("https://en.wikipedia.org/")
finally:
    os.unlink(database_file.name)

print("Anatomy Latin terminology smoke test passed.")
