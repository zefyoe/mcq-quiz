import json
import sys
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"m": NAMESPACE}


def cell_value(cell):
    inline = cell.find("m:is", NS)
    if inline is not None:
        return "".join(inline.itertext()).strip()
    return cell.findtext("m:v", default="", namespaces=NS).strip()


def read_workbook(path):
    with ZipFile(path) as workbook_zip:
        workbook = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        relationships = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        targets = {
            relation.attrib["Id"]: relation.attrib["Target"].lstrip("/")
            for relation in relationships
        }
        sheets = {}
        for sheet in workbook.findall(".//m:sheet", NS):
            sheet_name = sheet.attrib["name"]
            relation_id = sheet.attrib[f"{{{REL_NAMESPACE}}}id"]
            root = ET.fromstring(workbook_zip.read(targets[relation_id]))
            rows = []
            for row in root.findall(".//m:sheetData/m:row", NS):
                values = {
                    cell.attrib["r"][0]: cell_value(cell)
                    for cell in row.findall("m:c", NS)
                }
                if values.get("A", "").startswith(("GI", "CT")):
                    rows.append(values)
            sheets[sheet_name] = rows
        return sheets


def update_json(data_path, rows, expected_prefix, expected_count):
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    cards = payload.get("cards", [])
    rows_by_id = {row["A"]: row for row in rows}
    if len(rows) != expected_count or len(cards) != expected_count:
        raise ValueError(
            f"{expected_prefix}: expected {expected_count} rows/cards, "
            f"got {len(rows)}/{len(cards)}"
        )
    if set(rows_by_id) != {card["id"] for card in cards}:
        raise ValueError(f"{expected_prefix}: workbook IDs do not match source data")

    for card in cards:
        row = rows_by_id[card["id"]]
        options = {key: row[key] for key in "EFGH"}
        options = dict(zip("ABCD", options.values()))
        correct_choice = row["I"].upper()
        if correct_choice not in options or any(not value for value in options.values()):
            raise ValueError(f"{card['id']}: missing MCQ option or invalid correct choice")
        card["options"] = options
        card["correct_choice"] = correct_choice
        card["answer_nl"] = options[correct_choice]

    data_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: apply_anatomy_mcq_workbook.py /path/to/anatomy_mcq_ingevuld.xlsx")
    workbook_path = Path(sys.argv[1]).expanduser().resolve()
    sheets = read_workbook(workbook_path)
    update_json(
        ROOT / "data/gastrointestinal_anatomy_flashcards.json",
        sheets.get("GI - Anatomy", []),
        "GI",
        248,
    )
    update_json(
        ROOT / "data/cardiothoracic_flashcards.json",
        sheets.get("Cardiothoracaal", []),
        "CT",
        258,
    )
    print("Applied MCQ options for 248 GI and 258 cardiothoracic cards.")


if __name__ == "__main__":
    main()
