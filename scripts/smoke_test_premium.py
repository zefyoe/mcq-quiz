import os
import json
import re
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
from markupsafe import escape  # noqa: E402
from sqlalchemy import inspect  # noqa: E402


def assert_ok(response, label):
    assert response.status_code == 200, f"{label}: HTTP {response.status_code}"


def assert_rendered_text(response, value):
    assert str(escape(value)).encode("utf-8") in response.data


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
parsed_figure_findings = parse_answer_details(
    "Bevindingen\nBorstradiografie (Fig. 79.4) toont een verbreed mediastinum.\n\n"
    "Axiale beelden (fig. 79.5 en 79.6) tonen een aortaletsel.\n\n"
    "Figuur 79,7 toont het letsel vóór behandeling (Figuur 79,8)."
)
figure_findings = parsed_figure_findings[0]["items"]
assert len(figure_findings) == 3
assert all(
    not re.search(r"\b(?:fig|figs|figure|figures|figuur|figuren)\b", item["text"], re.I)
    for item in figure_findings
)
assert figure_findings[0]["text"].startswith("Borstradiografie toont")
parsed_plural_figure_reference = parse_answer_details(
    "Bevindingen\nDopplerbeelden (figuren 102.1 en 102.2) tonen een varicocèle."
)[0]["items"]
assert parsed_plural_figure_reference == [{
    "lead": "",
    "text": "Dopplerbeelden tonen een varicocèle.",
}]
parsed_pointer_figure_reference = parse_answer_details(
    "Bevindingen\nCT-beelden (witte pijlen in figuren 22.1 en 22.2) tonen een massa."
)[0]["items"]
assert parsed_pointer_figure_reference == [{
    "lead": "",
    "text": "CT-beelden tonen een massa.",
}]
preserved_medical_preposition = parse_answer_details(
    "Differentiaaldiagnose\nEen urotheelcarcinoom neemt contrast op, een stolsel niet."
)[0]["items"]
assert preserved_medical_preposition[0]["text"].startswith(
    "Een urotheelcarcinoom neemt contrast op,"
)
parsed_orphaned_figure_references = parse_answer_details(
    "Bevindingen\nCT-beelden (5.1, 5.2 en 5.4) tonen afwijkingen. "
    "MRI-beelden, en 11.3) bevestigen dit. "
    "De resistieve index blijft verhoogd (RI = 1,0)."
)[0]["items"]
assert [item["text"] for item in parsed_orphaned_figure_references] == [
    "CT-beelden tonen afwijkingen.",
    "MRI-beelden bevestigen dit.",
    "De resistieve index blijft verhoogd (RI = 1,0).",
]
orphaned_figure_numbers = parse_answer_details(
    "Bevindingen\nEen volledige bevinding.\n13.3, 13.4.\nNog een bevinding."
)[0]["items"]
assert [item["text"] for item in orphaned_figure_numbers] == [
    "Een volledige bevinding.",
    "Nog een bevinding.",
]

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
for card in core_gu_cards:
    differential = next(
        section
        for section in card["answer_sections_nl"]
        if section["key"] == "differential"
    )
    assert 1 <= len(differential["items"]) <= 6
    assert all(len(item["text"]) <= 120 for item in differential["items"])
    assert all(item.get("radiopaedia_url") for item in differential["items"])
gu_020 = next(card for card in core_gu_cards if card["ID"] == "CORE-GU-020")
gu_020_findings = next(
    section for section in gu_020["answer_sections_nl"] if section["key"] == "findings"
)["items"]
assert gu_020_findings[0]["text"].startswith(
    "De blanco CT toont gas in het parenchym van de transplantatienier."
)
assert all("20." not in item["text"] for item in gu_020_findings)
gu_102 = next(card for card in core_gu_cards if card["ID"] == "CORE-GU-102")
gu_102_findings = next(
    section for section in gu_102["answer_sections_nl"] if section["key"] == "findings"
)["items"]
assert len(gu_102_findings) == 1
assert gu_102_findings[0]["text"].startswith(
    "Grijswaarden- en kleuren-Doppleronderzoek van het linker scrotum"
)
assert "102.1" not in gu_102_findings[0]["text"]
assert "102.2" not in gu_102_findings[0]["text"]
gu_044 = next(card for card in core_gu_cards if card["ID"] == "CORE-GU-044")
gu_044_findings = next(
    section for section in gu_044["answer_sections_nl"] if section["key"] == "findings"
)["items"]
assert gu_044_findings[0]["text"].startswith(
    "Op de blanco CT van de eerste patiënt is hyperdens materiaal zichtbaar"
)
assert all("44." not in item["text"] for item in gu_044_findings)
gu_120 = next(card for card in core_gu_cards if card["ID"] == "CORE-GU-120")
gu_120_differential = next(
    section for section in gu_120["answer_sections_nl"]
    if section["key"] == "differential"
)["items"]
assert [item["text"] for item in gu_120_differential] == [
    "Hemorragische ovariumcyste",
    "Endometrioom",
    "Dermoïdcyste",
    "Goedaardige of kwaadaardige ovariumtumor",
]

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
assert all(card["Vraag_nl"] for card in core_chest_cards)
assert all(card["Vraag_nl"] != card["Vraag"] for card in core_chest_cards)
assert all(card["answer_details_nl"] != card["answer_details"] for card in core_chest_cards)
chest_hypertension = next(card for card in core_chest_cards if card["ID"] == "CORE-CH-069")
assert chest_hypertension["Vraag_nl"] == (
    "35-jarige man met ongecontroleerde hypertensie bij wie beeldvorming wordt verricht."
)

core_pediatric_cards = load_core_section("pediatric")
assert len(core_pediatric_cards) == 150
assert core_pediatric_cards[0]["ID"] == "CORE-PED-001"
assert len(core_pediatric_cards[0]["image_urls"]) == 1
assert len(core_pediatric_cards[0]["answer_image_urls"]) == 1
assert all(card["answer_sections"] for card in core_pediatric_cards)
assert all(card["Vraag_nl"] for card in core_pediatric_cards)
assert all(card["Vraag_nl"] != card["Vraag"] for card in core_pediatric_cards)
assert all(card["answer_details_nl"] != card["answer_details"] for card in core_pediatric_cards)
pediatric_cards_by_id = {card["ID"]: card for card in core_pediatric_cards}
pediatric_diagnosis_overrides = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "data"
        / "core_pediatric_diagnosis_overrides_nl.json"
    ).read_text(encoding="utf-8")
)
for card_id, expected_diagnosis in pediatric_diagnosis_overrides.items():
    assert pediatric_cards_by_id[card_id]["Correct_nl"] == [expected_diagnosis]

untranslated_pediatric_diagnosis = re.compile(
    r"\b(?:anomaly|aspired|bone cyst|clubfoot|deficency|foreign body|"
    r"mainstem bronchus|radial ray|air leak phenomena|plain radiographics)\b",
    re.IGNORECASE,
)
for card in core_pediatric_cards:
    assert not untranslated_pediatric_diagnosis.search(card["Correct_nl"][0]), card["ID"]

broken_pediatric_history = re.compile(
    r"(?:\n|-->|\bddx\b|\bsectional\b|\bbilious\b|\bUTI\b|"
    r"onbeschofte|juiste proptose|Rt Nier|SMHz|\bfant\b|\bStor\b)",
    re.IGNORECASE,
)
for card in core_pediatric_cards:
    assert not broken_pediatric_history.search(card["Vraag_nl"]), card["ID"]

ped_001 = pediatric_cards_by_id["CORE-PED-001"]
assert ped_001["Vraag_nl"] == (
    "Een zuigeling van 5 maanden met een afwijkende thoraxfoto."
)
assert ped_001["Correct_nl"] == [
    "Tetralogie van Fallot met afwezige pulmonalisklep"
]
ped_001_sections = {
    section["key"]: section["items"]
    for section in ped_001["answer_sections_nl"]
}
assert len(ped_001_sections["differential"]) == 3
assert len(ped_001_sections["teaching"]) == 6
assert len(ped_001_sections["references"]) == 2
ped_001_visible_text = " ".join(
    item["text"]
    for section in ped_001["answer_sections_nl"]
    if section["key"] != "references"
    for item in section["items"]
)
for broken_phrase in (
    "joeose",
    "het aantal spreuken",
    "in de kinderschoenen",
    "bevindingen van TOR",
):
    assert broken_phrase not in ped_001_visible_text

ped_072 = pediatric_cards_by_id["CORE-PED-072"]
assert ped_072["Vraag_nl"] == (
    "Een 10-jarige jongen met pubertas praecox. Het eerste beeld toont de "
    "rechtertestis en het tweede de linkertestis."
)
assert ped_072["Correct_nl"] == [
    "Testiculaire bijnierresten bij congenitale bijnierhyperplasie"
]
ped_072_sections = {
    section["key"]: section["items"]
    for section in ped_072["answer_sections_nl"]
}
assert len(ped_072_sections["differential"]) == 3
assert len(ped_072_sections["teaching"]) <= 6
assert len(ped_072_sections["references"]) == 2
ped_072_visible_text = " ".join(
    item["text"]
    for section in ped_072["answer_sections_nl"]
    if section["key"] != "references"
    for item in section["items"]
)
for broken_phrase in (
    "Stor",
    "overseminatie",
    "precocious puberteit",
    "Voorste akoestisch",
):
    assert broken_phrase not in ped_072_visible_text

ped_063 = next(card for card in core_pediatric_cards if card["ID"] == "CORE-PED-063")
assert ped_063["Vraag_nl"] == (
    "Jongen van 8 dagen met persisterend vochtverlies uit de navel."
)
assert ped_063["Correct_nl"] == ["Patente urachus"]
assert [section["key"] for section in ped_063["answer_sections_nl"]] == [
    "findings",
    "differential",
    "teaching",
    "management",
    "references",
]
ped_063_sections = {
    section["key"]: section["items"]
    for section in ped_063["answer_sections_nl"]
}
assert len(ped_063_sections["findings"]) == 1
assert "blaaskoepel met de navel verbindt" in ped_063_sections["findings"][0]["text"]
assert len(ped_063_sections["differential"]) == 2
assert len(ped_063_sections["teaching"]) == 6
assert len(ped_063_sections["management"]) == 2
assert len(ped_063_sections["references"]) == 2
ped_063_visible_text = " ".join(
    item["text"]
    for section in ped_063["answer_sections_nl"]
    if section["key"] != "references"
    for item in section["items"]
)
for broken_phrase in (
    "oc a7",
    "voortdurend drainerende navel",
    "Afwatering van de urachus",
    "omfalomesenteric",
    "gesloten aan de blaas einde",
    "vloeistof gevangen tussen",
):
    assert broken_phrase not in ped_063_visible_text

ped_086 = next(card for card in core_pediatric_cards if card["ID"] == "CORE-PED-086")
assert ped_086["Vraag_nl"] == "2-jarige met een ontwikkelingsachterstand."
assert ped_086["Correct_nl"] == ["Dandy-Walkermalformatie"]
assert [section["key"] for section in ped_086["answer_sections_nl"]] == [
    "findings",
    "differential",
    "teaching",
    "management",
    "references",
]
ped_086_sections = {
    section["key"]: section["items"]
    for section in ped_086["answer_sections_nl"]
}
assert len(ped_086_sections["findings"]) == 2
assert "hypoplastisch en craniaal geroteerd" in ped_086_sections["findings"][1]["text"]
assert len(ped_086_sections["differential"]) == 3
assert len(ped_086_sections["teaching"]) == 6
assert len(ped_086_sections["management"]) == 2
assert len(ped_086_sections["references"]) == 2
ped_086_visible_text = " ".join(
    item["text"]
    for section in ped_086["answer_sections_nl"]
    if section["key"] != "references"
    for item in section["items"]
)
for broken_phrase in (
    "2-jarige met vertraging",
    "Dandy-Walker misvorming",
    "Het verschil omvat",
    "Blake Magendie",
    "De term \"Dandy-Walker De term",
    "het rangschikken van de posterior fossa",
):
    assert broken_phrase not in ped_086_visible_text

ped_133 = next(card for card in core_pediatric_cards if card["ID"] == "CORE-PED-133")
assert ped_133["Vraag_nl"] == (
    "Jongen van 13 maanden met verkorting en een standsafwijking van het linker been."
)
assert ped_133["Correct_nl"] == ["Proximale focale femurdeficiëntie (PFFD)"]
assert [section["key"] for section in ped_133["answer_sections_nl"]] == [
    "findings",
    "differential",
    "teaching",
    "management",
    "references",
]
ped_133_sections = {
    section["key"]: section["items"]
    for section in ped_133["answer_sections_nl"]
}
assert len(ped_133_sections["findings"]) == 3
assert len(ped_133_sections["differential"]) == 2
assert len(ped_133_sections["teaching"]) == 6
assert len(ped_133_sections["management"]) == 2
assert len(ped_133_sections["references"]) == 2
ped_133_visible_text = " ".join(
    item["text"]
    for section in ped_133["answer_sections_nl"]
    if section["key"] != "references"
    for item in section["items"]
)
for broken_phrase in (
    "PFED",
    "Deficency",
    "lagere ledematen misvorming",
    "fibrillaire hemimelia",
    "cartilaginous",
    "anterior deficiëntie",
    "tekort is posterior",
    "proefschrift",
):
    assert broken_phrase not in ped_133_visible_text

ped_145 = next(card for card in core_pediatric_cards if card["ID"] == "CORE-PED-145")
assert ped_145["Vraag_nl"] == (
    "12-jarige patiënt met een Salter-Harris-IV-fractuur van de proximale tibia "
    "in de voorgeschiedenis."
)
assert ped_145["Correct_nl"] == [
    "Posttraumatische fysebrug van de proximale tibia"
]
assert [section["key"] for section in ped_145["answer_sections_nl"]] == [
    "findings",
    "differential",
    "teaching",
    "management",
    "references",
]
ped_145_sections = {
    section["key"]: section["items"]
    for section in ped_145["answer_sections_nl"]
}
assert len(ped_145_sections["findings"]) == 1
assert "hypointense benige brug" in ped_145_sections["findings"][0]["text"]
assert len(ped_145_sections["differential"]) == 1
assert len(ped_145_sections["teaching"]) == 6
assert len(ped_145_sections["management"]) == 2
assert len(ped_145_sections["references"]) == 2
ped_145_visible_text = " ".join(
    item["text"]
    for section in ped_145["answer_sections_nl"]
    if section["key"] != "references"
    for item in section["items"]
)
for broken_phrase in (
    "juiste proximale scheenbeen",
    "verwende gradiënt",
    "lichamelijk letsel",
    "Bony brug",
    "lichaamsplaat",
    "gerecupereerd",
):
    assert broken_phrase not in ped_145_visible_text

core_interventional_cards = load_core_section("interventional")
assert len(core_interventional_cards) == 103
assert core_interventional_cards[0]["ID"] == "CORE-IR-001"
assert len(core_interventional_cards[0]["image_urls"]) == 3
assert len(core_interventional_cards[0]["answer_image_urls"]) == 3
assert all(card["answer_sections"] for card in core_interventional_cards)
assert all(card["Vraag_nl"] for card in core_interventional_cards)
assert all(card["Vraag_nl"] != card["Vraag"] for card in core_interventional_cards)
assert all(card["answer_details_nl"] != card["answer_details"] for card in core_interventional_cards)
ir_079 = next(card for card in core_interventional_cards if card["ID"] == "CORE-IR-079")
assert ir_079["Vraag_nl"] == "50-jarige vrouw na een verkeersongeval met hoge snelheid."
assert next(
    card for card in core_interventional_cards if card["ID"] == "CORE-IR-078"
)["Vraag_nl"].startswith("25-jarige man, per ambulance binnengebracht")
ir_079_findings = next(
    section for section in ir_079["answer_sections_nl"] if section["key"] == "findings"
)["items"]
assert len(ir_079_findings) == 4
assert all(
    not re.search(r"\b(?:fig|figs|figure|figures|figuur|figuren)\b", item["text"], re.I)
    for item in ir_079_findings
)

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
cardiac_without_history = [
    card for card in core_cardiac_cards
    if card["Vraag"] == "What is the abnormality on the images below?"
]
assert len(cardiac_without_history) == 63
assert all(
    card["Vraag_nl"] == "Wat is de afwijking op onderstaande beelden?"
    for card in cardiac_without_history
)

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

obvious_translation_error = re.compile(
    r"\b(?:ultrageluid|ultrasound|berekende tomografie|gecomputeerde tomografie|"
    r"onverbeterde CT|imaging|findings?|fluid|plain film|management|workup|up to|"
    r"holge|cutoffvan|behoefte aspiratie|heterogenely|ubareolaire|mammografief|"
    r"lumbometrie)\b",
    re.IGNORECASE,
)
english_question_fragment = re.compile(
    r"\b(?:year-old|presents with|undergoes imaging|motor vehicle collision|"
    r"what is the|history of)\b",
    re.IGNORECASE,
)
prominent_english_fragment = re.compile(
    r"\b(?:year-old|woman|female|male|boy|girl|with|undergoes|presents?|history|"
    r"computed tomography|incidental|preoperative|motor vehicle|collision|"
    r"following|status post|due to|patient|lesion|collapse|lobe|nerve|sheath|"
    r"fractures?|dislocation|injury|rupture|disease|mass|chest|blunt|cardiac|"
    r"left|right|upper|lower|benign|malignant|anomalous|artery|tailgut|"
    r"smooth muscle|uncertain potential|teardrop|flail|demonstrated|associated|"
    r"related|and)\b",
    re.IGNORECASE,
)
visible_figure_reference = re.compile(
    r"\b(?:fig(?:uur|uren)?|figure|figures|afb\.)\s*\d",
    re.IGNORECASE,
)
for section in get_core_sections():
    if section.get("is_beta_demo"):
        continue
    section_cards = load_core_section(section["key"])
    assert len(section_cards) == section["display_count"]
    for card in section_cards:
        assert card["Vraag_nl"]
        assert card["Correct_nl"][0]
        dutch_visible_text = " ".join(
            [card["Vraag_nl"], *card["Correct_nl"], card["answer_details_nl"]]
        )
        assert "boogschutter" not in dutch_visible_text.lower(), card["ID"]
        for visible_text in (card["Vraag_nl"], card["Correct_nl"][0]):
            assert "  " not in visible_text, card["ID"]
            assert visible_text.count("(") == visible_text.count(")"), card["ID"]
            assert visible_text[-1:] not in ",;:", card["ID"]
        assert len(card["Correct_nl"][0]) <= 180, card["ID"]
        assert not english_question_fragment.search(card["Vraag_nl"]), card["ID"]
        assert not prominent_english_fragment.search(card["Vraag_nl"]), card["ID"]
        assert not prominent_english_fragment.search(card["Correct_nl"][0]), card["ID"]
        assert not obvious_translation_error.search(card["Vraag_nl"]), card["ID"]
        assert not obvious_translation_error.search(card["Correct_nl"][0]), card["ID"]
        assert not visible_figure_reference.search(card["Vraag_nl"]), card["ID"]
        for answer_section in card["answer_sections_nl"]:
            if answer_section["key"] == "teaching":
                assert len(answer_section["items"]) <= 6, card["ID"]
            if answer_section["key"] == "references":
                continue
            for item in answer_section["items"]:
                item_text = f"{item.get('lead', '')} {item['text']}"
                assert not obvious_translation_error.search(item_text), card["ID"]
                assert not visible_figure_reference.search(item_text), card["ID"]


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
assert b"Radius" in response.data
assert b"CORE Radius" in response.data
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
assert b"const autoCompleteOnLastRating = false;" in response.data
assert b"Question ID:" in response.data
assert b'<a href="/" class="brand brand-link">Radius</a>' in response.data
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
active_core_sections = [
    section for section in get_core_sections() if not section.get("is_beta_demo")
]
assert response.data.count(b'class="product-category-count"') == len(active_core_sections)
for section in active_core_sections:
    progress_label = f"0/{section['display_count']} questions".encode()
    assert progress_label in response.data
assert b"Anatomy" in response.data
assert b"core-nav-product-link" not in response.data
assert b">CORE Gastro-intestinal</a>" not in response.data

with client.session_transaction() as core_dashboard_language_session:
    core_dashboard_language_session["language"] = "nl"
response = client.get("/core")
assert_ok(response, "Dutch CORE dashboard")
for section in active_core_sections:
    progress_label = f"0/{section['display_count']} vragen".encode()
    assert progress_label in response.data
assert b"Beschikbare vragen" in response.data
assert b"VRAGENBIBLIOTHEEK" in response.data
expected_core_total = sum(section["display_count"] for section in active_core_sections)
assert f"0/{expected_core_total} vragen gezien".encode() in response.data

response = client.get("/core/chest")
assert_ok(response, "Dutch CORE chest setup")
assert b"CORE THORAXBEELDVORMING" in response.data
assert b"Alle vragen" in response.data
assert b"137 vragen" in response.data
assert b"Aantal vragen" in response.data
assert b"Start sessie" in response.data
assert b"CORE GASTRO-INTESTINAL" not in response.data
assert b"flashcards met open antwoord" in response.data
assert b"Alle cases" not in response.data
with client.session_transaction() as core_dashboard_language_session:
    core_dashboard_language_session["language"] = "en"

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
with client.session_transaction() as pediatric_case_session:
    pediatric_case_session["language"] = "nl"
    pediatric_case_session["category"] = "CORE Radiology"
    pediatric_case_session["subgroup"] = "pediatric"
    pediatric_case_session["order"] = ["CORE-PED-145"]
    pediatric_case_session["question_limit"] = 1
    pediatric_case_session["quiz_pool"] = "all"
response = client.get("/core/pediatric/study?resume=1")
assert_ok(response, "Dutch CORE pediatric case 145")
assert b'<a href="/core" class="brand brand-link">CORE Radius</a>' in response.data
assert b'<div class="topbar-badge">Pediatrische beeldvorming</div>' in response.data
assert response.data.find(b'class="language-switcher"') < response.data.find(
    b'class="topbar-link topbar-home"'
)
assert ped_145["Vraag_nl"].encode("utf-8") in response.data
assert ped_145["Correct_nl"][0].encode("utf-8") in response.data
assert b"hypointense benige brug" in response.data
assert b"Acuut fyseletsel zonder brugvorming" in response.data
assert b"operatieve planning" in response.data
assert "verwende gradiënt".encode("utf-8") not in response.data
assert b"lichamelijk letsel" not in response.data
with client.session_transaction() as pediatric_case_session:
    pediatric_case_session["order"] = ["CORE-PED-063"]
response = client.get("/core/pediatric/study?resume=1")
assert_ok(response, "Dutch CORE pediatric case 063")
assert ped_063["Vraag_nl"].encode("utf-8") in response.data
assert ped_063["Correct_nl"][0].encode("utf-8") in response.data
assert b"blaaskoepel met de navel verbindt" in response.data
assert b"Persisterende ductus omphalomesentericus" in response.data
assert b"ligamentum umbilicale medianum" in response.data
assert b"oc a7" not in response.data
assert b"omfalomesenteric" not in response.data
with client.session_transaction() as pediatric_case_session:
    pediatric_case_session["order"] = ["CORE-PED-086"]
response = client.get("/core/pediatric/study?resume=1")
assert_ok(response, "Dutch CORE pediatric case 086")
assert ped_086["Vraag_nl"].encode("utf-8") in response.data
assert ped_086["Correct_nl"][0].encode("utf-8") in response.data
assert b"hypoplastisch en craniaal geroteerd" in response.data
assert b"Blake-pouchcyste" in response.data
assert b"Dandy-Walkervariant" in response.data
assert b"Het verschil omvat" not in response.data
assert b"het rangschikken van de posterior fossa" not in response.data
with client.session_transaction() as pediatric_case_session:
    pediatric_case_session["order"] = ["CORE-PED-133"]
response = client.get("/core/pediatric/study?resume=1")
assert_ok(response, "Dutch CORE pediatric case 133")
assert ped_133["Vraag_nl"].encode("utf-8") in response.data
assert ped_133["Correct_nl"][0].encode("utf-8") in response.data
assert b"kraakbenige verbinding" in response.data
assert b"Femur-fibula-ulnasyndroom" in response.data
assert b"prothetische revalidatie" in response.data
assert b"cartilaginous" not in response.data
assert b"proefschrift" not in response.data
with client.session_transaction() as pediatric_case_session:
    pediatric_case_session["order"] = ["CORE-PED-001"]
response = client.get("/core/pediatric/study?resume=1")
assert_ok(response, "Dutch CORE pediatric case 001")
assert_rendered_text(response, ped_001["Vraag_nl"])
assert_rendered_text(response, ped_001["Correct_nl"][0])
assert b"afwezige pulmonalisklep" in response.data
assert b"joeose" not in response.data
assert b"het aantal spreuken" not in response.data
with client.session_transaction() as pediatric_case_session:
    pediatric_case_session["order"] = ["CORE-PED-072"]
response = client.get("/core/pediatric/study?resume=1")
assert_ok(response, "Dutch CORE pediatric case 072")
assert_rendered_text(response, ped_072["Vraag_nl"])
assert_rendered_text(response, ped_072["Correct_nl"][0])
assert b"pubertas praecox" in response.data
assert b"Een jongen van tien met puberteit" not in response.data
assert b"overseminatie" not in response.data
with client.session_transaction() as pediatric_case_session:
    pediatric_case_session["language"] = "en"

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
    assert_rendered_text(response, neuro_by_id[qid]["Vraag_nl"])
    assert_rendered_text(response, neuro_by_id[qid]["Correct_nl"][0])
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
assert b"ANKI ONLY" not in response.data

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
assert b"const autoCompleteOnLastRating = true;" in response.data
assert b"if (autoCompleteOnLastRating &amp;&amp; allCardsRated())" not in response.data
assert b"if (autoCompleteOnLastRating && allCardsRated())" in response.data
assert b"finishButton.addEventListener(\"click\", completeSession)" in response.data
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

with client.session_transaction() as core_progress_language_session:
    core_progress_language_session["language"] = "nl"
response = client.get("/core")
assert_ok(response, "CORE section progress")
assert b"2/171 vragen" in response.data
with client.session_transaction() as core_progress_language_session:
    core_progress_language_session["language"] = "en"

response = client.post(
    "/core/gastrointestinal/study",
    data={
        "subgroup": "gastrointestinal",
        "ratings_json": json.dumps(core_ratings),
        "duration_seconds": "73",
    },
)
assert_ok(response, "CORE completion")
assert b"CORE Radius - Gastrointestinal Imaging" in response.data

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
