import json
from functools import lru_cache
from pathlib import Path


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


@lru_cache(maxsize=None)
def load_core_section(section_key):
    data_path = DATA_DIRECTORY / f"core_{section_key}.json"
    if not data_path.exists():
        return []
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    cards = []
    for card in payload.get("cards", []):
        cards.append({
            "ID": card["id"],
            "Category": "CORE Radiology",
            "Vraag": card.get("history") or "Review the imaging case and formulate the diagnosis.",
            "Correct": [card.get("diagnosis") or "Diagnosis unavailable"],
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
            "answer_details": card.get("answer_details") or "",
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
