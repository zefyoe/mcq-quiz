import argparse
import html
import json
import re
from pathlib import Path

import fitz
import genanki


def clean_text(value):
    replacements = {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\u2013": "-",
        "\u2014": "-",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u25b6": "",
        "\u00a0": " ",
    }
    for source, replacement in replacements.items():
        value = value.replace(source, replacement)
    value = re.sub(r"\bTh\s+e\b", "The", value)
    value = re.sub(r"\b([A-Za-z]*f(?:i|l|f))\s+([a-z])", r"\1\2", value)
    value = re.sub(r"\bDi\s*ff\s*erential diagnosis\b", "Differential Diagnosis", value, flags=re.I)
    value = re.sub(r"\bTeaching points\b", "Teaching Points", value, flags=re.I)
    value = re.sub(r"\bFurther readings?\b", "Further Reading", value, flags=re.I)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def page_lines(page):
    return [
        clean_text(line)
        for line in page.get_text("text").splitlines()
        if clean_text(line) and not line.startswith("http://medical.dentalebooks.com")
    ]


def is_answer_heading(line):
    return line.strip() in {
        "Findings",
        "Differential Diagnosis",
        "Teaching Points",
        "Management",
        "Further Reading",
    }


def extract_history(question_page, case_number):
    lines = page_lines(question_page)
    history_index = next(
        (index for index, line in enumerate(lines) if line.lower() == "history"),
        None,
    )
    if history_index is None:
        return "Review the imaging case and formulate the diagnosis."

    collected = []
    for line in lines[history_index + 1 :]:
        if line == str(case_number) or line == f"Case {case_number}":
            continue
        if line.startswith("Figure ") or line.startswith("Fig. "):
            break
        if re.match(r"^[A-Z]\s*\.", line):
            break
        collected.append(line)
    history = clean_text(" ".join(collected))
    history = re.sub(rf"\bCase\s+{case_number}\b.*$", "", history).strip()
    return history or "Review the imaging case and formulate the diagnosis."


def extract_diagnosis(answer_page, case_number):
    lines = page_lines(answer_page)
    for index, line in enumerate(lines):
        match = re.match(rf"^Case\s*{case_number}\s*(.*)$", line, flags=re.I)
        if not match:
            continue
        diagnosis = match.group(1).strip()
        if diagnosis:
            return diagnosis
        for following in lines[index + 1 :]:
            if is_answer_heading(following):
                break
            if following and not following.isdigit():
                return following.strip()
    return "Diagnosis unavailable"


def extract_answer_sections(answer_page):
    sections = {
        "Findings": "",
        "Differential Diagnosis": "",
        "Teaching Points": "",
        "Management": "",
        "Further Reading": "",
    }
    current = None
    buffers = {heading: [] for heading in sections}
    for line in page_lines(answer_page):
        if is_answer_heading(line):
            current = line
            continue
        if current:
            buffers[current].append(line)
    for heading, lines in buffers.items():
        sections[heading] = clean_text("\n".join(lines))
    return sections


def render_image_region(page, image_info, output_path, zoom):
    rect = fitz.Rect(image_info["bbox"])
    padding = 2
    clip = fitz.Rect(
        max(page.rect.x0, rect.x0 - padding),
        max(page.rect.y0, rect.y0 - padding),
        min(page.rect.x1, rect.x1 + padding),
        min(page.rect.y1, rect.y1 + padding),
    )
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(output_path)


def image_html(filename):
    filenames = filename if isinstance(filename, (list, tuple)) else [filename]
    return "".join(
        f'<img src="{html.escape(name)}">'
        for name in filenames
        if name
    )


def build_apkg(cards, media_files, output_path, deck_label, model_id, deck_id):
    model = genanki.Model(
        model_id,
        f"CORE {deck_label} Case",
        fields=[
            {"name": "CaseNum"}, {"name": "Section"}, {"name": "History"},
            {"name": "QImages"}, {"name": "Diagnosis"}, {"name": "AImages"},
            {"name": "Findings"}, {"name": "Differential"},
            {"name": "TeachingPoints"}, {"name": "Management"},
            {"name": "FurtherReading"},
        ],
        templates=[{
            "name": f"{deck_label} Case",
            "qfmt": "<h2>Case {{CaseNum}}</h2><p>{{History}}</p>{{QImages}}",
            "afmt": "{{FrontSide}}<hr><h2>{{Diagnosis}}</h2>{{AImages}}"
            "<h3>Findings</h3><p>{{Findings}}</p>"
            "<h3>Differential Diagnosis</h3><p>{{Differential}}</p>"
            "<h3>Teaching Points</h3><p>{{TeachingPoints}}</p>"
            "<h3>Management</h3><p>{{Management}}</p>"
            "<h3>Further Reading</h3><p>{{FurtherReading}}</p>",
        }],
    )
    deck = genanki.Deck(deck_id, f"CORE Radiology::{deck_label} Cases")
    for card in cards:
        sections = card["sections"]
        deck.add_note(genanki.Note(
            model=model,
            fields=[
                str(card["case_number"]), html.escape(deck_label), html.escape(card["history"]),
                image_html(card["question_images"]), html.escape(card["diagnosis"]),
                image_html(card["answer_images"]), html.escape(sections["Findings"]),
                html.escape(sections["Differential Diagnosis"]), html.escape(sections["Teaching Points"]),
                html.escape(sections["Management"]), html.escape(sections["Further Reading"]),
            ],
        ))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck, media_files=[str(path) for path in media_files]).write_to_file(output_path)


def build(pdf_path, section_key, section_label, case_count, first_case_page_index,
          id_prefix, media_output, json_output, apkg_output, zoom):
    document = fitz.open(pdf_path)
    question_pages = []
    for page_index in range(first_case_page_index, len(document)):
        lines = page_lines(document[page_index])
        if any(line.lower() == "history" for line in lines):
            question_pages.append(page_index)
    if len(question_pages) < case_count:
        raise ValueError(f"Expected {case_count} question pages, found {len(question_pages)}")
    question_pages = question_pages[:case_count]

    media_output.mkdir(parents=True, exist_ok=True)
    cards = []
    media_files = []
    for case_number in range(1, case_count + 1):
        question_page_index = question_pages[case_number - 1]
        question_page = document[question_page_index]
        answer_page = document[question_page_index + 1]
        question_infos = question_page.get_image_info(xrefs=True)
        answer_infos = answer_page.get_image_info(xrefs=True)
        question_images = []
        answer_images = []
        for image_index, image_info in enumerate(question_infos):
            filename = f"{section_key}_{case_number:03d}_q_{image_index}.png"
            output = media_output / filename
            render_image_region(question_page, image_info, output, zoom)
            question_images.append(filename)
            media_files.append(output)
        for image_index, image_info in enumerate(answer_infos):
            filename = f"{section_key}_{case_number:03d}_a_{image_index}.png"
            output = media_output / filename
            render_image_region(answer_page, image_info, output, zoom)
            answer_images.append(filename)
            media_files.append(output)
        sections = extract_answer_sections(answer_page)
        cards.append({
            "id": f"{id_prefix}-{case_number:03d}",
            "case_number": case_number,
            "source_pdf_question_page": question_page_index + 1,
            "source_pdf_answer_page": question_page_index + 2,
            "label": f"Case {case_number}",
            "history": extract_history(question_page, case_number),
            "diagnosis": extract_diagnosis(answer_page, case_number),
            "question_images": question_images,
            "answer_images": answer_images,
            "answer_details": "\n".join(
                f"{heading}\n{content}" for heading, content in sections.items() if content
            ),
            "sections": sections,
            "question_image": question_images[0] if question_images else None,
            "answer_image": answer_images[0] if answer_images else None,
        })

    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps({
        "product": "CORE Radiology",
        "section": section_label,
        "section_key": section_key,
        "source": Path(pdf_path).name,
        "card_count": len(cards),
        "cards": [
            {key: value for key, value in card.items() if key not in {"case_number", "sections"}}
            for card in cards
        ],
    }, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    build_apkg(cards, media_files, apkg_output, section_label,
               model_id=1900000000 + len(section_key), deck_id=1901000000 + len(section_key))
    return cards


def main():
    parser = argparse.ArgumentParser(description="Build a CORE casebook deck from a Cases in Radiology PDF.")
    parser.add_argument("pdf_path")
    parser.add_argument("section_key")
    parser.add_argument("section_label")
    parser.add_argument("case_count", type=int)
    parser.add_argument("first_case_page_index", type=int)
    parser.add_argument("id_prefix")
    parser.add_argument("--media-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--apkg-output", required=True)
    parser.add_argument("--zoom", type=float, default=1.7)
    args = parser.parse_args()
    cards = build(
        Path(args.pdf_path).expanduser().resolve(), args.section_key, args.section_label,
        args.case_count, args.first_case_page_index, args.id_prefix,
        Path(args.media_output).resolve(), Path(args.json_output).resolve(),
        Path(args.apkg_output).resolve(), args.zoom,
    )
    missing = [card["id"] for card in cards if card["diagnosis"] == "Diagnosis unavailable" or not card["answer_details"]]
    if missing:
        raise RuntimeError(f"Parsing gaps in {len(missing)} cards: {missing[:10]}")
    print(f"Built {len(cards)} {args.section_label} cards.")


if __name__ == "__main__":
    main()
