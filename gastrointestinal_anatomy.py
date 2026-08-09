import json
from functools import lru_cache
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parent / "data" / "gastrointestinal_anatomy_flashcards.json"


@lru_cache(maxsize=1)
def load_gastrointestinal_anatomy_questions():
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return [
        {
            "ID": card["id"],
            "Category": card["category"],
            "Vraag": card["question"],
            "Vraag_nl": card["question_nl"],
            "A": card.get("options", {}).get("A", ""),
            "B": card.get("options", {}).get("B", ""),
            "C": card.get("options", {}).get("C", ""),
            "D": card.get("options", {}).get("D", ""),
            "Correct": card.get("correct_choice", [card["answer"]]),
            "Correct_nl": [card["answer_nl"]],
            "image_url": f"/static/images/{card['image']}",
            "question_key": f"gastrointestinal:{card['id']}",
            "compact_options": False,
            "flashcard_only": False,
        }
        for card in payload.get("cards", [])
    ]
