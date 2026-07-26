import argparse
import html
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path


FIELD_SEPARATOR = "\x1f"


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "div", "p", "li", "hr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"div", "p", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        value = html.unescape("".join(self.parts)).replace("\xa0", " ")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        return re.sub(r"\n{3,}", "\n\n", value).strip()


def html_to_text(value):
    parser = TextExtractor()
    parser.feed(value or "")
    return parser.text()


def class_content(value, class_name):
    match = re.search(
        rf'<div\s+class=["\']{re.escape(class_name)}["\']>(.*?)</div>',
        value or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html_to_text(match.group(1)) if match else ""


def image_sources(value):
    return re.findall(
        r'<img[^>]+src=["\']([^"\']+)["\']',
        value or "",
        flags=re.IGNORECASE,
    )


def answer_details(value):
    cleaned = re.sub(
        r'<div\s+class=["\']diag["\']>.*?</div>',
        "",
        value or "",
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"<img[^>]*>", "", cleaned, flags=re.IGNORECASE)
    return html_to_text(cleaned)


def import_apkg(source, output_json, media_output):
    source = Path(source).expanduser().resolve()
    output_json = Path(output_json).resolve()
    media_output = Path(media_output).resolve()

    with tempfile.TemporaryDirectory(prefix="core-apkg-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        with zipfile.ZipFile(source) as archive:
            archive.extractall(temporary_path)

        media_map = json.loads((temporary_path / "media").read_text(encoding="utf-8"))
        connection = sqlite3.connect(temporary_path / "collection.anki2")
        rows = connection.execute("SELECT id, flds FROM notes ORDER BY id").fetchall()
        connection.close()

        media_output.mkdir(parents=True, exist_ok=True)
        cards = []
        copied_media = set()

        for index, (note_id, fields) in enumerate(rows, start=1):
            question_html, answer_html = (fields.split(FIELD_SEPARATOR, 1) + [""])[:2]
            question_images = image_sources(question_html)
            answer_images = image_sources(answer_html)
            question_image = question_images[0] if question_images else None
            answer_image = answer_images[0] if answer_images else None

            cards.append({
                "id": f"CORE-GI-{index:03d}",
                "source_note_id": str(note_id),
                "label": class_content(question_html, "label") or f"Case {index}",
                "history": class_content(question_html, "hist"),
                "diagnosis": class_content(answer_html, "diag"),
                "question_image": question_image,
                "answer_image": answer_image,
                "answer_details": answer_details(answer_html),
            })

            for filename in (question_image, answer_image):
                if not filename or filename in copied_media:
                    continue
                archive_key = next(
                    (key for key, mapped_name in media_map.items() if mapped_name == filename),
                    None,
                )
                if archive_key is None:
                    raise ValueError(f"Media file not found in APKG mapping: {filename}")
                shutil.copy2(temporary_path / archive_key, media_output / filename)
                copied_media.add(filename)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(
            {
                "product": "CORE Radiology",
                "section": "Gastrointestinal Imaging",
                "source": source.name,
                "card_count": len(cards),
                "cards": cards,
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Imported {len(cards)} cards and {len(copied_media)} media files.")


def main():
    parser = argparse.ArgumentParser(description="Import a CORE Radiology Anki deck.")
    parser.add_argument("source", help="Path to the APKG file")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--media-output", required=True)
    arguments = parser.parse_args()
    import_apkg(arguments.source, arguments.output_json, arguments.media_output)


if __name__ == "__main__":
    main()
