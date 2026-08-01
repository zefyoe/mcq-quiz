import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus


CORE_SECTIONS = (
    {"key": "chest", "label": "Chest Imaging", "label_nl": "Thoraxbeeldvorming"},
    {"key": "neuroradiology", "label": "Neuroradiology", "label_nl": "Neuroradiologie"},
    {"key": "pediatric", "label": "Pediatric Imaging", "label_nl": "Pediatrische beeldvorming"},
    {"key": "interventional", "label": "Interventional Radiology", "label_nl": "Interventieradiologie"},
    {"key": "genitourinary", "label": "Genitourinary Radiology", "label_nl": "Urogenitale radiologie"},
    {"key": "gastrointestinal", "label": "Gastrointestinal Imaging", "label_nl": "Gastro-intestinale beeldvorming"},
    {"key": "body-mri", "label": "Body MRI", "label_nl": "MRI van het lichaam"},
    {"key": "musculoskeletal", "label": "Musculoskeletal Imaging", "label_nl": "Musculoskeletale beeldvorming"},
    {"key": "emergency", "label": "Emergency Radiology", "label_nl": "Spoedradiologie"},
    {"key": "cardiac", "label": "Cardiac Imaging", "label_nl": "Cardiale beeldvorming"},
    {"key": "breast", "label": "Breast Imaging", "label_nl": "Borstbeeldvorming"},
    {"key": "labralis", "label": "LABRALIS", "label_nl": "LABRALIS", "placeholder_count": 1, "is_beta_demo": True},
)

DATA_DIRECTORY = Path(__file__).resolve().parent / "data"

ANSWER_SECTION_LABELS = {
    "findings": "Findings",
    "differential": "Differential Diagnosis",
    "teaching": "Teaching Points",
    "management": "Management",
    "references": "References",
}
ANSWER_SECTION_HEADINGS = {
    "findings": re.compile(r"^Findings$", re.IGNORECASE),
    "differential": re.compile(r"^Differential Diagnosis$", re.IGNORECASE),
    "teaching": re.compile(r"^Teaching Points$", re.IGNORECASE),
    "management": re.compile(r"^Management$", re.IGNORECASE),
    "references": re.compile(r"^Further Readings?$", re.IGNORECASE),
}


def _section_key(line):
    for key, pattern in ANSWER_SECTION_HEADINGS.items():
        if pattern.match(line):
            return key
    return None


def _clean_extracted_text(value):
    value = re.sub(
        r"\b([A-Za-z]*(?:fi|fl|ff))\s+(?=[a-z])",
        r"\1",
        value,
    )
    return value.replace("oft en", "often").replace("aft er", "after")


def _capitalize_initial(value):
    value = (value or "").strip()
    for index, character in enumerate(value):
        if character.isalpha():
            return value[:index] + character.upper() + value[index + 1:]
    return value


def _split_learning_points(section_key, lines):
    text = " ".join(line.strip() for line in lines if line.strip())
    text = re.sub(r"\s+", " ", text).strip()
    text = _clean_extracted_text(text)
    if not text:
        return []

    if section_key == "references":
        text = re.sub(r"\s+Case\s+\d+\b.*$", "", text).strip()
        chunks = re.split(r"(?=\d+\.\s)", text)
    elif section_key == "differential":
        chunks = re.split(
            r"(?<=[.!?])\s+(?=[A-Z][A-Za-z0-9 ()/,+'-]{1,70}:)",
            text,
        )
    else:
        chunks = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)

    items = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lead = ""
        body = chunk
        if section_key == "references":
            match = re.match(r"^(\d+\.)\s*(.*)$", chunk)
            if match:
                lead, body = match.groups()
        else:
            match = re.match(r"^([^:]{1,75}):\s*(.+)$", chunk)
            if match:
                lead, body = match.groups()
        item = {"lead": lead, "text": body}
        if section_key == "differential" and lead:
            item["radiopaedia_url"] = (
                f"https://radiopaedia.org/search?q={quote_plus(lead)}"
            )
        items.append(item)
    return items


def parse_answer_details(value):
    sections = []
    current_key = None
    current_lines = []

    def append_current():
        if not current_key:
            return
        items = _split_learning_points(current_key, current_lines)
        if items:
            sections.append({
                "key": current_key,
                "label": ANSWER_SECTION_LABELS[current_key],
                "items": items,
            })

    for raw_line in (value or "").splitlines():
        line = raw_line.strip()
        next_key = _section_key(line)
        if next_key:
            append_current()
            current_key = next_key
            current_lines = []
        elif current_key:
            current_lines.append(line)
    append_current()
    return sections


@lru_cache(maxsize=None)
def load_core_translations(section_key, language):
    data_path = DATA_DIRECTORY / f"core_{section_key}_{language}.json"
    if not data_path.exists():
        return {}
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    return payload


@lru_cache(maxsize=None)
def load_core_section(section_key):
    data_path = DATA_DIRECTORY / f"core_{section_key}.json"
    if not data_path.exists():
        return []
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    dutch_translations = load_core_translations(section_key, "nl")
    dutch_histories = dutch_translations.get("histories", {})
    dutch_diagnoses = dutch_translations.get("diagnoses", {})
    dutch_answer_details = dutch_translations.get("answer_details", {})
    cards = []
    for card in payload.get("cards", []):
        diagnosis = _capitalize_initial(
            card.get("diagnosis") or "Diagnosis unavailable"
        )
        answer_details = card.get("answer_details") or ""
        answer_details_nl = dutch_answer_details.get(card["id"], answer_details)
        history = card.get("history") or "Review the imaging case and formulate the diagnosis."
        question_images = card.get("question_images") or (
            [card["question_image"]] if card.get("question_image") else []
        )
        answer_images = card.get("answer_images") or (
            [card["answer_image"]] if card.get("answer_image") else []
        )
        cards.append({
            "ID": card["id"],
            "Category": "CORE Radiology",
            "Vraag": history,
            "Vraag_nl": dutch_histories.get(card["id"], history),
            "Correct": [diagnosis],
            "Correct_nl": [
                _capitalize_initial(dutch_diagnoses.get(card["id"], diagnosis))
            ],
            "A": "",
            "B": "",
            "C": "",
            "D": "",
            "image_url": (
                f"/static/core/{section_key}/{question_images[0]}"
                if question_images else None
            ),
            "image_urls": [
                f"/static/core/{section_key}/{filename}"
                for filename in question_images
            ],
            "answer_image_url": (
                f"/static/core/{section_key}/{answer_images[0]}"
                if answer_images else None
            ),
            "answer_image_urls": [
                f"/static/core/{section_key}/{filename}"
                for filename in answer_images
            ],
            "answer_details": answer_details,
            "answer_sections": parse_answer_details(answer_details),
            "answer_details_nl": answer_details_nl,
            "answer_sections_nl": parse_answer_details(answer_details_nl),
            "radiopaedia_url": f"https://radiopaedia.org/search?q={quote_plus(diagnosis)}",
            "case_label": card.get("label") or card["id"],
            "core_section": section_key,
            "question_key": f"core:{section_key}:{card['id']}",
        })
    return cards


def get_core_sections():
    sections = []
    for section in CORE_SECTIONS:
        count = len(load_core_section(section["key"]))
        if section.get("is_beta_demo"):
            count = section.get("placeholder_count", 1)
        sections.append({
            **section,
            "count": count,
            "display_count": count or section.get("placeholder_count", 0),
            "is_placeholder": count == 0,
        })
    return sections


def get_core_section(section_key):
    return next(
        (section for section in get_core_sections() if section["key"] == section_key),
        None,
    )
