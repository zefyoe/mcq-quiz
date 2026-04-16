import os
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from questions_data import questions


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ANATOMY_CATEGORY = "Anatomy"
ANATOMY_RUNTIME_FOLDER_CATEGORIES = {
    "GU": "Anatomy - Genito-Urinary",
    "HN": "Anatomy - Head and Neck",
}


def build_structure_title(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    return " ".join(part for part in stem.replace("_", " ").replace("-", " ").split()).strip() or "Imported image question"


def get_default_correct_choice(seed: str | None) -> str:
    letters = ["A", "B", "C", "D"]
    normalized_seed = (seed or "").strip()
    if not normalized_seed:
        return "A"
    return letters[sum(ord(char) for char in normalized_seed) % len(letters)]


def get_runtime_image_category_for_path(path: Path, images_root: Path) -> str:
    relative_path = path.relative_to(images_root)
    first_part = relative_path.parts[0]
    if len(relative_path.parts) > 1 and first_part in ANATOMY_RUNTIME_FOLDER_CATEGORIES:
        return ANATOMY_RUNTIME_FOLDER_CATEGORIES[first_part]
    return ANATOMY_CATEGORY


def list_runtime_image_files(images_root: Path) -> list[Path]:
    image_paths = []
    for root, _, filenames in os.walk(images_root):
        for filename in sorted(filenames):
            if Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
                image_paths.append(Path(root) / filename)
    return sorted(image_paths)


def build_rows() -> list[list[str]]:
    rows = [[
        "Question ID",
        "Category",
        "Question",
        "Answer A",
        "Answer B",
        "Answer C",
        "Answer D",
        "Filename",
        "Correct",
    ]]

    for question in questions:
        category = (question.get("Category") or "").strip()
        if not category.lower().startswith("anatomy"):
            continue

        correct = question.get("Correct", "")
        if isinstance(correct, list):
            correct = ",".join(correct)

        rows.append([
            str(question.get("ID", "")),
            category,
            str(question.get("Vraag", "")),
            str(question.get("A", "")),
            str(question.get("B", "")),
            str(question.get("C", "")),
            str(question.get("D", "")),
            "",
            str(correct),
        ])

    images_root = Path("static/images")
    for index, path in enumerate(list_runtime_image_files(images_root), start=1):
        qid = f"IMG{index:03d}"
        title = build_structure_title(path.name)
        correct_choice = get_default_correct_choice(qid)
        answers = {"A": "", "B": "", "C": "", "D": ""}
        answers[correct_choice] = title
        rows.append([
            qid,
            get_runtime_image_category_for_path(path, images_root),
            "Which anatomical structure is depicted?",
            answers["A"],
            answers["B"],
            answers["C"],
            answers["D"],
            path.name,
            correct_choice,
        ])

    return rows


def column_name(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def inline_cell(ref: str, value: str) -> str:
    safe_value = escape(value or "")
    return (
        f'<c r="{ref}" t="inlineStr">'
        f"<is><t>{safe_value}</t></is>"
        f"</c>"
    )


def build_sheet_xml(rows: list[list[str]]) -> str:
    xml_rows = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            ref = f"{column_name(col_idx)}{row_idx}"
            cells.append(inline_cell(ref, value))
        xml_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(xml_rows)
        + "</sheetData></worksheet>"
    )


def write_xlsx(output_path: Path, rows: list[list[str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Anatomy Answers" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""

    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""

    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
</Properties>"""

    core_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Anatomy Answers Export</dc:title>
  <dc:creator>Codex</dc:creator>
</cp:coreProperties>"""

    with ZipFile(output_path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", build_sheet_xml(rows))
        zf.writestr("docProps/app.xml", app_xml)
        zf.writestr("docProps/core.xml", core_xml)


def main() -> None:
    rows = build_rows()
    output_path = Path("exports/anatomy_answers_export.xlsx")
    write_xlsx(output_path, rows)
    print(output_path)
    print(len(rows) - 1)


if __name__ == "__main__":
    main()
