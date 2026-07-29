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
        value = "".join(
            character
            for character in value
            if character in "\n\t" or ord(character) >= 32
        )
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
    cleaned = re.sub(
        r"<b>\s*Diagnosis:\s*.*?</b>",
        "",
        cleaned,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"<img[^>]*>", "", cleaned, flags=re.IGNORECASE)
    return html_to_text(cleaned)


def labeled_bold_value(value, label):
    match = re.search(
        rf"<b>\s*{re.escape(label)}:\s*(.*?)</b>",
        value or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html_to_text(match.group(1)) if match else ""


def history_value(value):
    text = html_to_text(value)
    match = re.search(
        r"(?:^|\n)History:\s*(.*?)(?:\n{2,}|What do the images show)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def field_map(model, fields):
    names = [
        field["name"]
        for field in sorted(model.get("flds", []), key=lambda item: item["ord"])
    ]
    values = fields.split(FIELD_SEPARATOR)
    return {
        name: values[index] if index < len(values) else ""
        for index, name in enumerate(names)
    }


def import_apkg(source, output_json, media_output, section_key, section_label, id_prefix):
    source = Path(source).expanduser().resolve()
    output_json = Path(output_json).resolve()
    media_output = Path(media_output).resolve()

    with tempfile.TemporaryDirectory(prefix="core-apkg-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        with zipfile.ZipFile(source) as archive:
            archive.extractall(temporary_path)

        media_map = json.loads((temporary_path / "media").read_text(encoding="utf-8"))
        connection = sqlite3.connect(temporary_path / "collection.anki2")
        models = json.loads(connection.execute("SELECT models FROM col").fetchone()[0])
        rows = connection.execute("SELECT id, mid, flds FROM notes ORDER BY id").fetchall()
        connection.close()

        media_output.mkdir(parents=True, exist_ok=True)
        cards = []
        copied_media = set()

        for index, (note_id, model_id, fields) in enumerate(rows, start=1):
            model = models[str(model_id)]
            mapped_fields = field_map(model, fields)
            if {"History", "Diagnosis", "QImages", "AImages"} <= mapped_fields.keys():
                question_images = image_sources(mapped_fields["QImages"])
                answer_images = image_sources(mapped_fields["AImages"])
                details = "\n".join(
                    f"{heading}\n{html_to_text(mapped_fields.get(field_name, ''))}"
                    for field_name, heading in (
                        ("Findings", "Findings"),
                        ("Differential", "Differential Diagnosis"),
                        ("TeachingPoints", "Teaching Points"),
                        ("Management", "Management"),
                        ("FurtherReading", "Further Reading"),
                    )
                    if mapped_fields.get(field_name)
                )
                card = {
                    "id": f"{id_prefix}-{index:03d}",
                    "source_note_id": str(note_id),
                    "label": f"Case {mapped_fields.get('CaseNum') or index}",
                    "history": html_to_text(mapped_fields["History"]),
                    "diagnosis": re.sub(
                        r"\s+Figures?\s+\d+(?:\.\d+)?(?:\s+Figures?\s+\d+(?:\.\d+)?)*$",
                        "",
                        html_to_text(mapped_fields["Diagnosis"]),
                    ),
                    "question_images": question_images,
                    "answer_images": answer_images,
                    "answer_details": details,
                    "source_section": html_to_text(mapped_fields.get("Section", "")),
                }
            else:
                question_html, answer_html = (fields.split(FIELD_SEPARATOR, 1) + [""])[:2]
                question_images = image_sources(question_html)
                answer_images = image_sources(answer_html)
                card = {
                    "id": f"{id_prefix}-{index:03d}",
                    "source_note_id": str(note_id),
                    "label": class_content(question_html, "label") or f"Case {index}",
                    "history": (
                        class_content(question_html, "hist")
                        or history_value(question_html)
                    ),
                    "diagnosis": (
                        class_content(answer_html, "diag")
                        or labeled_bold_value(answer_html, "Diagnosis")
                    ),
                    "question_images": question_images,
                    "answer_images": answer_images,
                    "answer_details": answer_details(answer_html),
                }

            card["question_image"] = question_images[0] if question_images else None
            card["answer_image"] = answer_images[0] if answer_images else None
            cards.append(card)

            for filename in (*question_images, *answer_images):
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
                "section": section_label,
                "section_key": section_key,
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
    parser.add_argument("--section-key", required=True)
    parser.add_argument("--section-label", required=True)
    parser.add_argument("--id-prefix", required=True)
    arguments = parser.parse_args()
    import_apkg(
        arguments.source,
        arguments.output_json,
        arguments.media_output,
        arguments.section_key,
        arguments.section_label,
        arguments.id_prefix,
    )


if __name__ == "__main__":
    main()
