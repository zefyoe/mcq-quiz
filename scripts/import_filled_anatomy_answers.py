import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "anatomy_answer_bank.py"
NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def col_to_num(col: str) -> int:
    value = 0
    for char in col:
        value = value * 26 + ord(char) - 64
    return value


def parse_xlsx_rows(path: Path) -> list[list[str]]:
    with ZipFile(path) as zf:
        shared_strings = []
        sst = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in sst.findall("a:si", NS):
            texts = [node.text or "" for node in si.findall(".//a:t", NS)]
            shared_strings.append("".join(texts))

        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.find("a:sheetData", NS):
            values = []
            current = 1
            for cell in row.findall("a:c", NS):
                ref = cell.attrib["r"]
                col = re.match(r"[A-Z]+", ref).group(0)
                idx = col_to_num(col)
                while current < idx:
                    values.append("")
                    current += 1

                raw_value = cell.find("a:v", NS)
                if raw_value is None:
                    values.append("")
                elif cell.attrib.get("t") == "s":
                    values.append(shared_strings[int(raw_value.text)])
                else:
                    values.append(raw_value.text or "")
                current += 1

            rows.append((values + [""] * 9)[:9])
    return rows


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/import_filled_anatomy_answers.py /path/to/file.xlsx")

    xlsx_path = Path(sys.argv[1]).expanduser().resolve()
    rows = parse_xlsx_rows(xlsx_path)
    header, body = rows[0], rows[1:]

    if header[:9] != ["Question ID", "Category", "Question", "Answer A", "Answer B", "Answer C", "Answer D", "Filename", "Correct"]:
        raise SystemExit("Unexpected workbook format")

    static_overrides = {}
    image_overrides = {}

    for qid, category, question, a, b, c, d, filename, correct in body:
        payload = {
            "Category": category,
            "Vraag": question,
            "A": a,
            "B": b,
            "C": c,
            "D": d,
            "Correct": correct,
        }
        if filename:
            image_overrides[filename] = payload
        else:
            static_overrides[qid] = payload

    content = (
        "# Generated from filled anatomy workbook.\n"
        f"STATIC_QUESTION_OVERRIDES = {repr(static_overrides)}\n\n"
        f"IMAGE_QUESTION_OVERRIDES = {repr(image_overrides)}\n"
    )
    OUTPUT.write_text(content, encoding="utf-8")
    print(OUTPUT)
    print(f"static={len(static_overrides)} image={len(image_overrides)}")


if __name__ == "__main__":
    main()
