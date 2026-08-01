import argparse
import html
import json
import re
from pathlib import Path

import fitz
import genanki


CASE_COUNT = 143
FIRST_CASE_PAGE_INDEX = 17


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
    }
    for source, replacement in replacements.items():
        value = value.replace(source, replacement)
    value = re.sub(r"\bTh\s+e\b", "The", value)
    value = re.sub(r"\b([A-Za-z]*f(?:i|l|f))\s+([a-z])", r"\1\2", value)
    value = re.sub(r"\bDi\s*ff\s*erential diagnosis\b", "Differential Diagnosis", value, flags=re.I)
    value = re.sub(r"\bTeaching points\b", "Teaching Points", value, flags=re.I)
    value = re.sub(r"\bFurther reading\b", "Further Reading", value, flags=re.I)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def page_lines(page):
    return [
        clean_text(line)
        for line in page.get_text("text").splitlines()
        if clean_text(line) and not line.startswith("http://medical.dentalebooks.com")
    ]


def is_image_label(line):
    return bool(re.fullmatch(r"[A-Z](?:\s+[A-Z]){0,8}", line.strip()))


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
        return "Review the MRI case and formulate the diagnosis."

    collected = []
    for line in lines[history_index + 1 :]:
        if line == str(case_number) or line == f"Case {case_number}":
            continue
        if is_image_label(line):
            break
        if re.match(r"^[A-Z]\s*\.", line):
            break
        collected.append(line)

    history = clean_text(" ".join(collected))
    history = re.sub(rf"\bCase\s+{case_number}\b.*$", "", history).strip()
    return history or "Review the MRI case and formulate the diagnosis."


def extract_diagnosis(answer_text, case_number):
    lines = [line for line in answer_text.splitlines() if line.strip()]
    diagnosis_lines = []
    collecting = False
    for line in lines:
        match = re.match(rf"^Case\s+{case_number}\s+(.+)$", line.strip())
        if match:
            diagnosis_lines = [match.group(1)]
            collecting = True
            continue
        if collecting:
            if line.startswith("http://medical.dentalebooks.com"):
                break
            if is_answer_heading(line) or is_image_label(line):
                break
            diagnosis_lines.append(line)
    if not diagnosis_lines:
        return "Diagnosis unavailable"
    diagnosis = clean_text(" ".join(diagnosis_lines))
    diagnosis = re.sub(r"http://medical\.dentalebooks\.com.*$", "", diagnosis).strip()
    diagnosis = re.sub(r"(?:\s+[A-Z]){2,10}\s*$", "", diagnosis).strip()
    diagnosis = re.sub(r"\s+", " ", diagnosis).strip()
    return diagnosis or "Diagnosis unavailable"


def answer_text_before_diagnosis(answer_page, case_number):
    text = clean_text(answer_page.get_text("text"))
    text = re.sub(r"http://medical\.dentalebooks\.com", "", text)
    lines = []
    skipping_case_title = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line == str((case_number * 2)):
            continue
        if re.match(rf"^Case\s+{case_number}\b", line):
            skipping_case_title = True
            continue
        if skipping_case_title:
            if is_answer_heading(line):
                skipping_case_title = False
                lines.append(line)
            continue
        if is_image_label(line):
            continue
        lines.append(line)
    return clean_text("\n".join(lines))


def split_answer_sections(answer_text):
    headings = {
        "Findings": "Findings",
        "Differential Diagnosis": "Differential Diagnosis",
        "Teaching Points": "Teaching Points",
        "Management": "Management",
        "Further Reading": "Further Reading",
    }
    sections = {field: "" for field in headings}
    current = None
    buffers = {field: [] for field in headings}

    for line in answer_text.splitlines():
        heading = headings.get(line.strip())
        if heading:
            current = heading
            continue
        if current:
            buffers[current].append(line)

    for heading, lines in buffers.items():
        sections[heading] = clean_text("\n".join(lines))
    return sections


def render_page(page, output_path, zoom):
    page_rect = page.rect
    clip = fitz.Rect(
        page_rect.x0 + 24,
        page_rect.y0 + 24,
        page_rect.x1 - 24,
        page_rect.y1 - 85,
    )
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(output_path)


def image_html(filename):
    return f'<img src="{html.escape(filename)}">'


def build_deck(cards, media_files, apkg_output):
    model = genanki.Model(
        1928742013,
        "CORE Body MRI Case",
        fields=[
            {"name": "CaseNum"},
            {"name": "Section"},
            {"name": "History"},
            {"name": "QImages"},
            {"name": "Diagnosis"},
            {"name": "AImages"},
            {"name": "Findings"},
            {"name": "Differential"},
            {"name": "TeachingPoints"},
            {"name": "Management"},
            {"name": "FurtherReading"},
        ],
        templates=[
            {
                "name": "Body MRI Case",
                "qfmt": "<h2>Case {{CaseNum}}</h2><p>{{History}}</p>{{QImages}}",
                "afmt": "{{FrontSide}}<hr><h2>{{Diagnosis}}</h2>{{AImages}}"
                "<h3>Findings</h3><p>{{Findings}}</p>"
                "<h3>Differential Diagnosis</h3><p>{{Differential}}</p>"
                "<h3>Teaching Points</h3><p>{{TeachingPoints}}</p>"
                "<h3>Management</h3><p>{{Management}}</p>"
                "<h3>Further Reading</h3><p>{{FurtherReading}}</p>",
            }
        ],
    )
    deck = genanki.Deck(1928742014, "CORE Radiology::Body MRI Cases")
    for card in cards:
        deck.add_note(
            genanki.Note(
                model=model,
                fields=[
                    str(card["case_number"]),
                    "Body MRI",
                    card["history"],
                    image_html(card["question_image"]),
                    card["diagnosis"],
                    image_html(card["answer_image"]),
                    card["sections"]["Findings"],
                    card["sections"]["Differential Diagnosis"],
                    card["sections"]["Teaching Points"],
                    card["sections"]["Management"],
                    card["sections"]["Further Reading"],
                ],
            )
        )
    genanki.Package(deck, media_files=[str(path) for path in media_files]).write_to_file(apkg_output)


def build(pdf_path, media_output, json_output, apkg_output, zoom):
    document = fitz.open(pdf_path)
    if len(document) < FIRST_CASE_PAGE_INDEX + CASE_COUNT * 2:
        raise ValueError(f"Expected at least {FIRST_CASE_PAGE_INDEX + CASE_COUNT * 2} pages, got {len(document)}")

    media_output.mkdir(parents=True, exist_ok=True)
    cards = []
    media_files = []
    for case_number in range(1, CASE_COUNT + 1):
        question_page = document[FIRST_CASE_PAGE_INDEX + (case_number - 1) * 2]
        answer_page = document[FIRST_CASE_PAGE_INDEX + (case_number - 1) * 2 + 1]
        question_image = f"body_mri_{case_number:03d}_q.png"
        answer_image = f"body_mri_{case_number:03d}_a.png"
        question_output = media_output / question_image
        answer_output = media_output / answer_image
        render_page(question_page, question_output, zoom)
        render_page(answer_page, answer_output, zoom)
        media_files.extend([question_output, answer_output])

        answer_text = clean_text(answer_page.get_text("text"))
        discussion_text = answer_text_before_diagnosis(answer_page, case_number)
        sections = split_answer_sections(discussion_text)
        card = {
            "id": f"CORE-BMRI-{case_number:03d}",
            "case_number": case_number,
            "source_pdf_question_page": FIRST_CASE_PAGE_INDEX + (case_number - 1) * 2 + 1,
            "source_pdf_answer_page": FIRST_CASE_PAGE_INDEX + (case_number - 1) * 2 + 2,
            "label": f"Case {case_number}",
            "history": extract_history(question_page, case_number),
            "diagnosis": extract_diagnosis(answer_text, case_number),
            "question_images": [question_image],
            "answer_images": [answer_image],
            "answer_details": "\n".join(
                f"{heading}\n{content}"
                for heading, content in sections.items()
                if content
            ),
            "sections": sections,
        }
        card["question_image"] = question_image
        card["answer_image"] = answer_image
        cards.append(card)

    json_cards = []
    for card in cards:
        json_card = {key: value for key, value in card.items() if key not in {"case_number", "sections"}}
        json_cards.append(json_card)

    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(
            {
                "product": "CORE Radiology",
                "section": "Body MRI",
                "section_key": "body-mri",
                "source": Path(pdf_path).name,
                "card_count": len(json_cards),
                "cards": json_cards,
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    apkg_output.parent.mkdir(parents=True, exist_ok=True)
    build_deck(cards, media_files, apkg_output)
    return cards


def main():
    parser = argparse.ArgumentParser(description="Build CORE Body MRI cards and APKG from the Body MRI Cases PDF.")
    parser.add_argument("pdf_path")
    parser.add_argument("--media-output", default="static/core/body-mri")
    parser.add_argument("--json-output", default="data/core_body-mri.json")
    parser.add_argument("--apkg-output", default="exports/CORE_Body_MRI_Cases.apkg")
    parser.add_argument("--zoom", type=float, default=1.7)
    args = parser.parse_args()

    cards = build(
        Path(args.pdf_path).expanduser().resolve(),
        Path(args.media_output).resolve(),
        Path(args.json_output).resolve(),
        Path(args.apkg_output).resolve(),
        args.zoom,
    )
    missing_diagnoses = [card["id"] for card in cards if card["diagnosis"] == "Diagnosis unavailable"]
    missing_details = [card["id"] for card in cards if not card["answer_details"]]
    if missing_diagnoses or missing_details:
        raise RuntimeError(
            f"Build completed with parsing gaps: diagnoses={missing_diagnoses}, details={missing_details}"
        )
    print(f"Built {len(cards)} Body MRI cards.")


if __name__ == "__main__":
    main()
