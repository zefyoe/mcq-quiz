import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus


CORE_SECTIONS = (
    {"key": "chest", "label": "Chest Imaging"},
    {"key": "neuroradiology", "label": "Neuroradiology"},
    {"key": "pediatric", "label": "Pediatric Imaging"},
    {"key": "interventional", "label": "Interventional Radiology"},
    {"key": "genitourinary", "label": "Genitourinary Radiology"},
    {"key": "gastrointestinal", "label": "Gastrointestinal Imaging"},
    {"key": "body-mri", "label": "Body MRI"},
    {"key": "musculoskeletal", "label": "Musculoskeletal Imaging"},
    {"key": "emergency", "label": "Emergency Radiology"},
    {"key": "cardiac", "label": "Cardiac Imaging"},
    {"key": "breast", "label": "Breast Imaging"},
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
        items.append({"lead": lead, "text": body})
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
def load_core_section(section_key):
    data_path = DATA_DIRECTORY / f"core_{section_key}.json"
    if not data_path.exists():
        return []
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    cards = []
    for card in payload.get("cards", []):
        diagnosis = card.get("diagnosis") or "Diagnosis unavailable"
        answer_details = card.get("answer_details") or ""
        cards.append({
            "ID": card["id"],
            "Category": "CORE Radiology",
            "Vraag": card.get("history") or "Review the imaging case and formulate the diagnosis.",
            "Correct": [diagnosis],
            "A": "",
            "B": "",
            "C": "",
            "D": "",
            "image_url": (
                f"/static/core/{section_key}/{card['question_image']}"
                if card.get("question_image") else None
            ),
            "answer_image_url": (
                f"/static/core/{section_key}/{card['answer_image']}"
                if card.get("answer_image") else None
            ),
            "answer_details": answer_details,
            "answer_sections": parse_answer_details(answer_details),
            "radiopaedia_url": f"https://radiopaedia.org/search?q={quote_plus(diagnosis)}",
            "case_label": card.get("label") or card["id"],
            "core_section": section_key,
            "question_key": f"core:{section_key}:{card['id']}",
        })
    return cards


def get_core_sections():
    return [
        {
            **section,
            "count": len(load_core_section(section["key"])),
        }
        for section in CORE_SECTIONS
    ]


def get_core_section(section_key):
    return next(
        (section for section in get_core_sections() if section["key"] == section_key),
        None,
    )
