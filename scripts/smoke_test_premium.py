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

from app import app, capitalize_initial, db, get_questions_by_ids  # noqa: E402
from core_radiology import get_core_sections, load_core_section, parse_answer_details  # noqa: E402
from models import QuizAttempt, User  # noqa: E402
from sqlalchemy import inspect  # noqa: E402


def assert_ok(response, label):
    assert response.status_code == 200, f"{label}: HTTP {response.status_code}"


parsed_notes = parse_answer_details(
    "Findings\nThere is infl ammatory change and a defi nite fi stula.\n"
    "Differential Diagnosis\nAbscess: a fl uid collection.\n"
    "Teaching Points\nThis is oft en visible on CT.\n"
    "Management\nDrainage may be necessary.\n"
    "Further Reading\n1. Example reference.\nCase 1 Example"
)
assert [section["key"] for section in parsed_notes] == [
    "findings",
    "differential",
    "teaching",
    "management",
    "references",
]
assert "inflammatory" in parsed_notes[0]["items"][0]["text"]
assert "definite fistula" in parsed_notes[0]["items"][0]["text"]
assert parsed_notes[1]["items"][0]["lead"] == "Abscess"
assert parsed_notes[1]["items"][0]["radiopaedia_url"].endswith("q=Abscess")
assert parsed_notes[-1]["items"][0]["text"] == "Example reference."
parsed_references = parse_answer_details(
    "Findings\nA finding.\nFurther Reading\n"
    "Koeller KK, Sandberg GD. Example paper. Radiographics. 2002;22:1473-1505.\n"
    "Meyers SP, Khademian ZP. Second paper. Neuroradiology. 2004;46:770-780."
)
reference_items = parsed_references[-1]["items"]
assert len(reference_items) == 2
assert "1473-1505" in reference_items[0]["text"]
assert reference_items[1]["text"].startswith("Meyers SP")
parsed_differential = parse_answer_details(
    "Differential Diagnosis\nDiagnosis one\nDiagnosis two\nDiagnosis three"
)
assert [item["text"] for item in parsed_differential[0]["items"]] == [
    "Diagnosis one",
    "Diagnosis two",
    "Diagnosis three",
]
parsed_teaching = parse_answer_details(
    "Teaching Points\n" + "\n".join(f"Point {index}." for index in range(1, 18))
)
assert len(parsed_teaching[0]["items"]) <= 6

core_cards = load_core_section("gastrointestinal")
assert len(core_cards) == 171
assert all(card["Vraag_nl"] for card in core_cards)
assert sum(card["Vraag_nl"] != card["Vraag"] for card in core_cards) == 171
assert core_cards[0]["Vraag_nl"] == "68-jarige man met dysfagie."
assert all(card["answer_sections_nl"] for card in core_cards)
assert all(
    card["answer_details_nl"] != card["answer_details"]
    for card in core_cards
)
assert capitalize_initial("lowercase answer") == "Lowercase answer"
assert capitalize_initial("MRI finding") == "MRI finding"

core_gu_cards = load_core_section("genitourinary")
assert len(core_gu_cards) == 129
assert all(card["Vraag_nl"] for card in core_gu_cards)
assert all(card["Correct_nl"][0] for card in core_gu_cards)
assert sum(card["Vraag_nl"] != card["Vraag"] for card in core_gu_cards) == 129
assert sum(card["Correct_nl"] != card["Correct"] for card in core_gu_cards) == 126
assert core_gu_cards[0]["Vraag_nl"] == "63-jarige man met gewichtsverlies."
assert core_gu_cards[0]["Correct_nl"] == [
    "Niercelcarcinoom: heldercellig subtype"
]
assert len(core_gu_cards[0]["image_urls"]) == 3
assert len(core_gu_cards[0]["answer_image_urls"]) == 2
assert all(card["answer_sections_nl"] for card in core_gu_cards)

core_breast_cards = load_core_section("breast")
assert len(core_breast_cards) == 100
assert all(card["Vraag_nl"] != card["Vraag"] for card in core_breast_cards)
assert sum(card["Correct_nl"] != card["Correct"] for card in core_breast_cards) >= 95
assert all(card["answer_sections_nl"] for card in core_breast_cards)

core_chest_cards = load_core_section("chest")
assert len(core_chest_cards) == 137
assert core_chest_cards[0]["ID"] == "CORE-CH-001"
assert len(core_chest_cards[0]["image_urls"]) == 1
assert len(core_chest_cards[0]["answer_image_urls"]) == 2
assert all(card["answer_sections"] for card in core_chest_cards)

core_pediatric_cards = load_core_section("pediatric")
assert len(core_pediatric_cards) == 150
assert core_pediatric_cards[0]["ID"] == "CORE-PED-001"
assert len(core_pediatric_cards[0]["image_urls"]) == 1
assert len(core_pediatric_cards[0]["answer_image_urls"]) == 1
assert all(card["answer_sections"] for card in core_pediatric_cards)

core_interventional_cards = load_core_section("interventional")
assert len(core_interventional_cards) == 103
assert core_interventional_cards[0]["ID"] == "CORE-IR-001"
assert len(core_interventional_cards[0]["image_urls"]) == 3
assert len(core_interventional_cards[0]["answer_image_urls"]) == 3
assert all(card["answer_sections"] for card in core_interventional_cards)

core_neuro_cards = load_core_section("neuroradiology")
assert len(core_neuro_cards) == 192
assert core_neuro_cards[0]["ID"] == "CORE-NR-001"
assert len(core_neuro_cards[0]["image_urls"]) == 3
assert len(core_neuro_cards[0]["answer_image_urls"]) == 3
assert all(card["answer_sections"] for card in core_neuro_cards)
assert all(card["Vraag_nl"] != card["Vraag"] for card in core_neuro_cards)
assert sum(card["Correct_nl"] != card["Correct"] for card in core_neuro_cards) >= 188
assert all(card["answer_details_nl"] != card["answer_details"] for card in core_neuro_cards)
assert all(card["answer_sections_nl"] for card in core_neuro_cards)
assert all(
    not any(
        f"\n{heading}\n" in card["answer_details_nl"]
        for heading in (
            "Findings",
            "Differential Diagnosis",
            "Teaching Points",
            "Management",
            "Further Reading",
        )
    )
    for card in core_neuro_cards
)

core_body_mri_cards = load_core_section("body-mri")
assert len(core_body_mri_cards) == 143
assert core_body_mri_cards[0]["ID"] == "CORE-BMRI-001"
assert len(core_body_mri_cards[0]["image_urls"]) == 3
assert len(core_body_mri_cards[0]["answer_image_urls"]) == 0
assert all(card["answer_sections"] for card in core_body_mri_cards)
assert all(card["Vraag_nl"] != card["Vraag"] for card in core_body_mri_cards)
assert all(card["answer_details_nl"] for card in core_body_mri_cards)

core_cardiac_cards = load_core_section("cardiac")
assert len(core_cardiac_cards) == 115
assert core_cardiac_cards[0]["ID"] == "CORE-CARD-001"
assert len(core_cardiac_cards[0]["image_urls"]) == 2
assert len(core_cardiac_cards[0]["answer_image_urls"]) == 0
assert all(card["answer_sections"] for card in core_cardiac_cards)
assert all(card["Vraag_nl"] for card in core_cardiac_cards)
assert all(card["answer_details_nl"] for card in core_cardiac_cards)

core_emergency_cards = load_core_section("emergency")
assert len(core_emergency_cards) == 164
assert core_emergency_cards[0]["ID"] == "CORE-ER-001"
assert len(core_emergency_cards[0]["image_urls"]) == 4
assert len(core_emergency_cards[0]["answer_image_urls"]) == 0
assert all(card["answer_sections"] for card in core_emergency_cards)
assert all(card["Vraag_nl"] for card in core_emergency_cards)
assert all(card["answer_details_nl"] for card in core_emergency_cards)

core_msk_cards = load_core_section("musculoskeletal")
assert len(core_msk_cards) == 145
assert core_msk_cards[0]["ID"] == "CORE-MSK-001"
assert len(core_msk_cards[0]["image_urls"]) == 2
assert len(core_msk_cards[0]["answer_image_urls"]) == 4
assert all(card["answer_sections"] for card in core_msk_cards)
assert all(card["Vraag_nl"] for card in core_msk_cards)
assert all(card["answer_details_nl"] for card in core_msk_cards)


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
assert b'class="product-switcher"' in response.data
assert b"/switch-product/core" in response.data
with client.session_transaction() as language_session:
    language_session["language"] = "en"
response = client.get("/switch-product/core")
assert response.status_code == 302
assert response.headers["Location"] == "https://core.bymed.be/core"
response = client.get("/switch-product/anatomy")
assert response.status_code == 302
assert response.headers["Location"] == "https://bymed.be/"
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
assert b"Rapport / PDF" in response.data or b"Report / PDF" in response.data

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
assert b"Bymed BV" in response.data
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
assert b"Bymed BV" in response.data
assert b'class="product-switcher"' in response.data
assert b'product-option active' in response.data
assert b"Chest Imaging" in response.data
assert b"PACS CASES (BETA)" in response.data
assert response.data.count(b'class="product-category-row') == len(
    [section for section in get_core_sections() if not section.get("is_beta_demo")]
)
assert b"product-category-count" not in response.data
assert b"Anatomy" in response.data
assert b"core-nav-product-link" not in response.data
assert b">CORE Gastro-intestinal</a>" not in response.data

response = client.get("/core/chest")
assert_ok(response, "CORE chest setup")
assert b"137" in response.data
response = client.get("/core/chest/study?pool=all&count=2")
assert_ok(response, "CORE chest study")
assert b"/static/core/chest/" in response.data

response = client.get("/core/pediatric")
assert_ok(response, "CORE pediatric setup")
assert b"150" in response.data
response = client.get("/core/pediatric/study?pool=all&count=2")
assert_ok(response, "CORE pediatric study")
assert b"/static/core/pediatric/" in response.data

response = client.get("/core/interventional")
assert_ok(response, "CORE interventional setup")
assert b"103" in response.data
response = client.get("/core/interventional/study?pool=all&count=2")
assert_ok(response, "CORE interventional study")
assert b"/static/core/interventional/" in response.data

response = client.get("/core/neuroradiology")
assert_ok(response, "CORE neuroradiology setup")
assert b"192" in response.data
response = client.get("/core/neuroradiology/study?pool=all&count=2")
assert_ok(response, "CORE neuroradiology study")
assert b"/static/core/neuroradiology/" in response.data
with client.session_transaction() as neuro_language_session:
    neuro_language_session["language"] = "nl"
response = client.get("/core/neuroradiology/study?resume=1")
assert_ok(response, "Dutch CORE neuroradiology study")
with client.session_transaction() as neuro_session:
    neuro_order = list(neuro_session["order"])
neuro_by_id = {card["ID"]: card for card in core_neuro_cards}
for qid in neuro_order:
    assert neuro_by_id[qid]["Vraag_nl"].encode("utf-8") in response.data
    assert neuro_by_id[qid]["Correct_nl"][0].encode("utf-8") in response.data
assert b"Bevindingen" in response.data
assert b"Differentiaaldiagnose" in response.data
with client.session_transaction() as neuro_language_session:
    neuro_language_session["language"] = "en"

response = client.get("/core/body-mri")
assert_ok(response, "CORE body MRI setup")
assert b"143" in response.data
response = client.get("/core/body-mri/study?pool=all&count=2")
assert_ok(response, "CORE body MRI study")
assert b"/static/core/body-mri/" in response.data

response = client.get("/core/cardiac")
assert_ok(response, "CORE cardiac setup")
assert b"115" in response.data
response = client.get("/core/cardiac/study?pool=all&count=2")
assert_ok(response, "CORE cardiac study")
assert b"/static/core/cardiac/" in response.data

response = client.get("/core/emergency")
assert_ok(response, "CORE emergency setup")
assert b"164" in response.data
response = client.get("/core/emergency/study?pool=all&count=2")
assert_ok(response, "CORE emergency study")
assert b"/static/core/emergency/" in response.data

response = client.get("/core/musculoskeletal")
assert_ok(response, "CORE musculoskeletal setup")
assert b"145" in response.data
response = client.get("/core/musculoskeletal/study?pool=all&count=2")
assert_ok(response, "CORE musculoskeletal study")
assert b"/static/core/musculoskeletal/" in response.data

response = client.get("/core/gastrointestinal")
assert_ok(response, "CORE GI setup")
assert b"ANKI ONLY" in response.data

response = client.get("/core/genitourinary")
assert_ok(response, "CORE GU setup")
assert b"129" in response.data
response = client.get("/core/genitourinary/study?pool=all&count=2")
assert_ok(response, "CORE GU study")
assert b"/static/core/genitourinary/" in response.data
assert b"core-media-collection" in response.data
assert b"\xc2\xa9 UZ Brussel Radiologie" in response.data
with client.session_transaction() as core_gu_language_session:
    core_gu_language_session["language"] = "nl"
response = client.get("/core/genitourinary/study?resume=1")
assert_ok(response, "Dutch CORE GU study")
with client.session_transaction() as core_gu_session:
    core_gu_order = list(core_gu_session["order"])
core_gu_by_id = {card["ID"]: card for card in core_gu_cards}
for qid in core_gu_order:
    assert core_gu_by_id[qid]["Vraag_nl"].encode("utf-8") in response.data
    assert core_gu_by_id[qid]["Correct_nl"][0].encode("utf-8") in response.data
with client.session_transaction() as core_gu_language_session:
    core_gu_language_session["language"] = "en"

response = client.get("/core/breast")
assert_ok(response, "CORE breast setup")
assert b"100" in response.data
response = client.get("/core/breast/study?pool=all&count=2")
assert_ok(response, "CORE breast study")
assert b"/static/core/breast/" in response.data
assert b"Diagnosis unavailable" not in response.data

response = client.get("/core/gastrointestinal/study?pool=all&count=2")
assert_ok(response, "CORE GI study")
assert b"Show answer" in response.data
assert b"MCQ" not in response.data
assert b'class="core-learning-notes"' in response.data
assert b"Explore on Radiopaedia" in response.data
assert b"note-differential" in response.data
assert b"core-differential-link" in response.data
assert b"What the images show" not in response.data
assert b"core-note-index" not in response.data
assert response.data.index(b"data-reveal-answer") < response.data.index(b"data-question-image")
assert response.data.index(b"data-answer-image") < response.data.index(b"flashcard-rating-grid-top")
assert response.data.index(b"flashcard-rating-grid-top") < response.data.index(b"core-learning-notes")
assert b"Bymed BV" in response.data
assert response.data.count(b'data-src="/static/core/') == 4
assert response.data.count(b' src="/static/core/') == 1
assert b'rel="preload" as="image"' in response.data
with client.session_transaction() as core_session:
    core_order = list(core_session["order"])
assert len(core_order) == 2
assert all(qid.startswith("CORE-GI-") for qid in core_order)

with client.session_transaction() as core_language_session:
    core_language_session["language"] = "nl"
response = client.get("/core/gastrointestinal/study?resume=1")
assert_ok(response, "Dutch CORE GI study")
core_cards_by_id = {card["ID"]: card for card in core_cards}
for qid in core_order:
    assert core_cards_by_id[qid]["Vraag_nl"].encode("utf-8") in response.data
    assert core_cards_by_id[qid]["Correct_nl"][0].encode("utf-8") in response.data
assert b"Toon antwoord" in response.data
assert b"Bevindingen en kernpunten" in response.data
assert b"Casebespreking" in response.data
assert b"Alle rechten voorbehouden." in response.data
with client.session_transaction() as core_language_session:
    core_language_session["language"] = "en"

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
assert b"detectCoreImagePanels" in response.data
assert_ok(client.get("/static/core/gastrointestinal/c1_q_0.png"), "CORE media")
style_response = client.get("/static/style.css")
assert_ok(style_response, "static stylesheet")
assert "max-age=604800" in style_response.headers.get("Cache-Control", "")
assert b".core-product .flashcard-image-frame" in style_response.data
assert b".core-image-grid.panel-count-1" in style_response.data
assert b"width: 72%" in style_response.data
assert b".core-media-collection.media-count-2" in style_response.data
assert b".core-learning-header" in style_response.data
assert b".core-note-section.note-teaching" in style_response.data
assert b".core-differential-link" in style_response.data
assert b".site-footer" in style_response.data
assert b".flashcard-panel > .flashcard-reveal-button" in style_response.data
assert b"grid-template-columns: repeat(2, minmax(0, 1fr))" in style_response.data
assert b"object-view-box: none" in style_response.data

anonymous_client = app.test_client()
response = anonymous_client.get("/", base_url="https://core.bymed.be")
assert response.status_code == 302
assert response.headers["Location"].endswith("/core")

client.get("/logout")
response = client.get("/login")
assert_ok(response, "login page")
assert b"login-rx-background.jpg" in response.data
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
