import json
import os
import sys
import tempfile
from pathlib import Path


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "french-interface-smoke-test"
os.environ["ENABLE_LANGUAGE_SWITCHER"] = "1"
os.environ["PUBLIC_SITE_MODE"] = "active"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app, db  # noqa: E402
from models import User  # noqa: E402


def assert_ok(response, label):
    assert response.status_code == 200, f"{label}: HTTP {response.status_code}"


def assert_contains(response, *values):
    page = response.get_data(as_text=True)
    for value in values:
        assert value in page, f"Missing French interface text: {value!r}"


try:
    with app.app_context():
        db.create_all()
        student = User(
            name="Étudiante Test",
            university="Université de Bruxelles",
            email="etudiante@example.com",
            is_admin=False,
        )
        student.set_password("mot-de-passe-solide")
        db.session.add(student)
        db.session.commit()

    client = app.test_client()

    language_response = client.get("/language/fr?next=/login")
    assert language_response.status_code == 302
    assert language_response.headers["Location"].endswith("/login?_lang=1")

    login_page = client.get("/login")
    assert_ok(login_page, "French login")
    assert_contains(
        login_page,
        '<html lang="fr">',
        "Se connecter",
        "Mot de passe",
        "Créer un compte",
        '>FR</a>',
    )

    register_page = client.get("/register")
    assert_ok(register_page, "French registration")
    assert_contains(
        register_page,
        "Créer un compte",
        "Votre nom complet",
        "Votre université",
        "Confirmer le mot de passe",
    )
    invalid_registration = client.post(
        "/register",
        data={"name": "", "university": "", "email": "", "password": "court"},
    )
    assert_ok(invalid_registration, "French registration validation")
    assert_contains(
        invalid_registration,
        "Saisissez votre nom.",
        "Saisissez votre université.",
        "Saisissez votre adresse e-mail.",
        "Utilisez au moins 8 caractères.",
    )

    invalid_login = client.post(
        "/login",
        data={"email": "etudiante@example.com", "password": "incorrect"},
    )
    assert_ok(invalid_login, "French invalid login")
    assert_contains(invalid_login, "Adresse e-mail ou mot de passe incorrect.")

    login_response = client.post(
        "/login",
        data={
            "email": "etudiante@example.com",
            "password": "mot-de-passe-solide",
        },
        follow_redirects=True,
    )
    assert_ok(login_response, "French dashboard")
    assert_contains(
        login_response,
        '<html lang="fr">',
        "Bienvenue",
        "Questions disponibles",
        "Sections d’anatomie",
    )

    sections_page = client.get("/anatomy")
    assert_ok(sections_page, "French anatomy sections")
    assert_contains(
        sections_page,
        "Choisissez une section anatomique",
        "Anatomie musculosquelettique",
        "Anatomie de la tête et du cou",
        "Anatomie de l’appareil urogénital",
    )

    setup_page = client.get("/anatomy/msk")
    assert_ok(setup_page, "French anatomy setup")
    assert_contains(
        setup_page,
        "Méthode d’étude",
        "Toutes les questions",
        "Révision intelligente",
        "Commencer les flashcards",
        "Commencer le quiz",
    )

    quiz_page = client.get("/quiz/Anatomy?subgroup=msk&count=1&mode=test")
    assert_ok(quiz_page, "French anatomy quiz")
    assert_contains(
        quiz_page,
        "Quiz en cours",
        "Quelle structure anatomique est représentée ?",
        "Enregistrer la réponse",
        "Mode concentration",
    )
    with client.session_transaction() as student_session:
        quiz_order = list(student_session["order"])
    assert len(quiz_order) == 1
    quiz_result = client.post(
        "/quiz/Anatomy?subgroup=msk&count=1&mode=test",
        data={f"ans_{quiz_order[0]}": "A", "duration_seconds": "20"},
    )
    assert_ok(quiz_result, "French anatomy quiz result")
    assert_contains(
        quiz_result,
        "Quiz terminé",
        "Bonne réponse",
        "Refaire ce test",
    )

    flashcards_page = client.get("/flashcards/Anatomy?subgroup=msk&count=1")
    assert_ok(flashcards_page, "French anatomy flashcards")
    assert_contains(
        flashcards_page,
        "SÉRIE ACTIVE",
        "Trouvez la réponse avant de l’afficher",
        "Afficher la réponse",
        "Terminer la session",
    )
    assert "Anki" not in flashcards_page.get_data(as_text=True)

    with client.session_transaction() as student_session:
        flashcard_order = list(student_session["order"])
    assert len(flashcard_order) == 1
    flashcard_result = client.post(
        "/flashcards/Anatomy?subgroup=msk&count=1",
        data={
            "subgroup": "msk",
            "ratings_json": json.dumps({flashcard_order[0]: "easy"}),
            "duration_seconds": "30",
        },
    )
    assert_ok(flashcard_result, "French anatomy flashcard result")
    assert_contains(
        flashcard_result,
        "SESSION TERMINÉE",
        "Nouvelle série de flashcards",
        "Cette session",
        "Disponible dans cette catégorie",
    )
    assert "Anki" not in flashcard_result.get_data(as_text=True)

    profile_page = client.get("/profile")
    assert_ok(profile_page, "French profile")
    assert_contains(
        profile_page,
        "PARAMÈTRES PERSONNELS",
        "Profil et objectif d’étude",
        "Sécurité du compte",
    )

    history_page = client.get("/previous-tests")
    assert_ok(history_page, "French test history")
    assert_contains(history_page, "Mes tests précédents", "Tentatives enregistrées", "Anatomie - MSK")
finally:
    os.unlink(database_file.name)

print("French student interface smoke test passed.")
