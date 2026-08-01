import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus


CORE_SECTIONS = (
    {"key": "chest", "label": "Chest Imaging", "label_nl": "Thoraxbeeldvorming"},
    {"key": "neuroradiology", "label": "Neuroradiology", "label_nl": "Neuroradiologie"},
    {"key": "pediatric", "label": "Pediatric Imaging", "label_nl": "Pediatrische beeldvorming"},
    {"key": "interventional", "label": "Interventional Radiology", "label_nl": "Interventieradiologie"},
    {"key": "genitourinary", "label": "Genitourinary Radiology", "label_nl": "Urogenitale radiologie"},
    {"key": "gastrointestinal", "label": "Gastrointestinal Imaging", "label_nl": "Gastro-intestinale beeldvorming"},
    {"key": "body-mri", "label": "Body MRI", "label_nl": "MRI van het lichaam"},
    {"key": "musculoskeletal", "label": "Musculoskeletal Imaging", "label_nl": "Musculoskeletale beeldvorming"},
    {"key": "emergency", "label": "Emergency Radiology", "label_nl": "Spoedradiologie"},
    {"key": "cardiac", "label": "Cardiac Imaging", "label_nl": "Cardiale beeldvorming"},
    {"key": "breast", "label": "Breast Imaging", "label_nl": "Borstbeeldvorming"},
    {"key": "labralis", "label": "LABRALIS", "label_nl": "LABRALIS", "placeholder_count": 1, "is_beta_demo": True},
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
    "findings": re.compile(r"^(Findings|Bevindingen)$", re.IGNORECASE),
    "differential": re.compile(r"^(Differential Diagnosis|Differentiaaldiagnose)$", re.IGNORECASE),
    "teaching": re.compile(r"^(Teaching Points|Kernpunten)$", re.IGNORECASE),
    "management": re.compile(r"^(Management|Beleid)$", re.IGNORECASE),
    "references": re.compile(r"^(Further Readings?|Referenties)$", re.IGNORECASE),
}

GU_DIFFERENTIAL_OVERRIDES_NL = {
    "CORE-GU-001": ["Heldercellig niercelcarcinoom", "Urotheelcarcinoom", "Lymfoom", "Oncocytoom"],
    "CORE-GU-002": ["Urotheelcarcinoom van het nierbekken", "Niercelcarcinoom", "Lymfoom"],
    "CORE-GU-003": ["Lymfoom", "Sarcoom", "Retroperitoneale fibrose", "Perinefrisch hematoom"],
    "CORE-GU-004": ["Lymfoom", "Metastasen", "Pyelonefritis"],
    "CORE-GU-005": ["Lymfoom", "Diabetes mellitus", "Acute glomerulonefritis", "Systemische lupus erythematodes", "Polyarteritis nodosa", "Granulomatose met polyangiitis"],
    "CORE-GU-006": ["Heldercellig niercelcarcinoom", "Papillair niercelcarcinoom", "Chromofoob niercelcarcinoom", "Oncocytoom", "Vetarm angiomyolipoom"],
    "CORE-GU-007": ["Urotheelcarcinoom", "Bloedstolsel"],
    "CORE-GU-015": ["Retroperitoneaal liposarcoom", "Groot exofytisch renaal angiomyolipoom"],
    "CORE-GU-016": ["Acute pyelonefritis", "Urinewegobstructie", "Nierveentrombose", "Niercontusie", "Vasculitis", "Hypotensie"],
    "CORE-GU-017": ["Niercyste", "Nierabces"],
    "CORE-GU-021": ["Diabetes mellitus", "Acute glomerulonefritis", "Vasculitis", "Lymfoom", "HIV-geassocieerde nefropathie"],
    "CORE-GU-022": ["Lymfoom", "Multifocaal papillair niercelcarcinoom", "Metastasen", "Infectie", "Sarcoïdose", "Granulomatose met polyangiitis"],
    "CORE-GU-023": ["Xanthogranulomateuze pyelonefritis", "Tuberculose"],
    "CORE-GU-024": ["Bosniak III-cyste", "Nierabces", "Renale hydatidecyste"],
    "CORE-GU-025": ["Medullaire nefrocalcinose", "Jichtnefropathie"],
    "CORE-GU-028": ["Eenvoudige niercyste", "Calyxdivertikel"],
    "CORE-GU-031": ["Atherosclerotische nierarteriestenose", "Fibromusculaire dysplasie"],
    "CORE-GU-032": ["Atherosclerotische nierarteriestenose", "Fibromusculaire dysplasie"],
    "CORE-GU-035": ["Perinefrisch hematoom", "Urinoom", "Lymfocele", "Abces"],
    "CORE-GU-039": ["Transplantaatafstoting", "Acute tubulusnecrose", "Nierveentrombose"],
    "CORE-GU-040": ["Hematoom", "Urinoom", "Lymfocele", "Abces"],
    "CORE-GU-041": ["Acute tubulusnecrose", "Acute transplantaatafstoting", "Chronische transplantaatafstoting", "Nierveentrombose"],
    "CORE-GU-044": ["Bloedstolsel in het pyelocaliceale systeem", "Urotheelcarcinoom"],
    "CORE-GU-045": ["Retroperitoneale fibrose", "Retroperitoneaal lymfoom"],
    "CORE-GU-046": ["Liposarcoom", "Lipoom", "Exofytisch renaal angiomyolipoom", "Teratoom"],
    "CORE-GU-048": ["Lymfoom", "Retroperitoneale fibrose", "Retroperitoneaal sarcoom"],
    "CORE-GU-050": ["Tuberculose", "Mycobacterium avium-complexinfectie", "Schimmelinfectie", "Necrotische lymfekliermetastasen", "Ziekte van Whipple"],
    "CORE-GU-051": ["Cystische degeneratie in een solide tumor", "Behandelingsgerelateerde tumornecrose", "Lymfangioom", "Cystisch teratoom"],
    "CORE-GU-052": ["Blande trombus", "Tumortrombus"],
    "CORE-GU-057": ["Lipiderijk bijnieradenoom", "Myelolipoom", "Bijnierbloeding"],
    "CORE-GU-063": ["Bijniermetastase", "Bijnieradenoom"],
    "CORE-GU-064": ["Endotheliale bijniercyste", "Bijnierpseudocyste", "Cystisch gedegenereerde bijniertumor"],
    "CORE-GU-067": ["Traumatische perinefrische collectie", "Postoperatieve collectie", "Perinefrisch abces"],
    "CORE-GU-069": ["Urotheelcarcinoom", "Bloedstolsel"],
    "CORE-GU-070": ["Blaassteen", "Bloedstolsel", "Urotheelcarcinoom"],
    "CORE-GU-072": ["Recente instrumentatie", "Enterovesicale fistel", "Emfysemateuze cystitis"],
    "CORE-GU-075": ["Bekkenorgaanprolaps", "Neuromusculaire aandoening", "Bindweefselziekte", "Inflammatoire darmziekte"],
    "CORE-GU-076": ["Urotheelcarcinoom", "Schistosomiasis", "Tuberculose", "Cyclofosfamidecystitis", "Radiatiecystitis"],
    "CORE-GU-080": ["Utriculuscyste", "Cyste van de ductus Müllerianus", "Cyste van de ductus ejaculatorius", "Cystische benigne prostaathyperplasie", "Prostaatabces"],
    "CORE-GU-087": ["Urethradivertikel", "Gartnergangcyste", "Bartholin-kliercyste", "Skene-kliercyste", "Naboth-cyste"],
    "CORE-GU-088": ["Urethradivertikel", "Skene-kliercyste", "Gartnergangcyste", "Bartholin-kliercyste"],
    "CORE-GU-092": ["Primaire testistumor", "Lymfoom", "Epidermoïdcyste", "Granulomateuze aandoening"],
    "CORE-GU-093": ["Kiemceltumor", "Lymfoom", "Sarcoïdose"],
    "CORE-GU-094": ["Epididymo-orchitis", "Testistorsie", "Torsie van een testisappendix"],
    "CORE-GU-097": ["Kiemceltumor", "Testiculair lymfoom"],
    "CORE-GU-098": ["Kiemceltumor", "Testiculair lymfoom", "Sarcoïdose"],
    "CORE-GU-099": ["Spermatocele", "Epididymiscyste"],
    "CORE-GU-100": ["Epididymo-orchitis", "Testistorsie"],
    "CORE-GU-101": ["Epididymo-orchitis", "Testistorsie", "Ingeklemde liesbreuk", "Cellulitis", "Gangreen van Fournier"],
    "CORE-GU-104": ["Endometriumhyperplasie", "Endometriumcarcinoom", "Endometriumpoliep", "Submuceus uterusmyoom"],
    "CORE-GU-105": ["Endometriumpoliep", "Endometriumhyperplasie", "Endometriumcarcinoom", "Submuceus uterusmyoom"],
    "CORE-GU-107": ["Hematometra", "Pyometra", "Hydrometra"],
    "CORE-GU-109": ["Endometriumpoliep", "Submuceus uterusmyoom", "Intra-uteriene synechieën"],
    "CORE-GU-110": ["Arcuaire uterus", "Septate uterus", "Bicornuate uterus", "Uterus didelphys"],
    "CORE-GU-112": ["Ovariumcyste", "Hydrosalpinx"],
    "CORE-GU-114": ["Endometriumhyperplasie", "Endometriumpoliep", "Endometriumcarcinoom", "Tamoxifengerelateerde verandering"],
    "CORE-GU-115": ["Zeer vroege intra-uteriene zwangerschap", "Anembryonale zwangerschap", "Pseudogestationele zak bij ectopische zwangerschap"],
    "CORE-GU-116": ["Arterioveneuze malformatie", "Veneuze obstructie", "Pelvien congestiesyndroom", "Asymptomatische anatomische variant"],
    "CORE-GU-119": ["Hemorragische ovariumcyste", "Maligne ovariumneoplasma"],
    "CORE-GU-120": [
        "Hemorragische ovariumcyste",
        "Endometrioom",
        "Dermoïdcyste",
        "Goedaardige of kwaadaardige ovariumtumor",
    ],
    "CORE-GU-122": ["Hemorragische ovariumcyste", "Endometrioom", "Hydrosalpinx", "Dermoïdcyste", "Ovariumcarcinoom"],
    "CORE-GU-124": ["Primair ovariumcarcinoom", "Ovariële metastasen", "Endometrioom"],
    "CORE-GU-126": ["Tubo-ovarieel abces", "Ovariumneoplasma", "Hemorragische ovariumcyste", "Endometrioom"],
    "CORE-GU-128": ["Ovariumtorsie", "Ovariumtumor", "Ovarieel hyperstimulatiesyndroom"],
}
CARDIAC_QUESTION_DEFAULT = "What is the abnormality on the images below?"
CARDIAC_QUESTION_DEFAULT_NL = "Wat is de afwijking op onderstaande beelden?"
MISSING_CLINICAL_HISTORY = {
    "",
    "none",
    "n/a",
    "na",
    "not available",
    "clinical information not available",
    "no clinical history",
}
FIGURE_WORD = r"(?:fig(?:uren|ures|uur|ure|s)?|afb(?:eeldingen|eelding)?)\.?"
FIGURE_LABEL = r"(?:\d+(?:[.,]\d+)?[a-z]?|(?-i:[A-Z]))\b"
FIGURE_REFERENCE = re.compile(
    rf"\(?\b{FIGURE_WORD}\s*{FIGURE_LABEL}"
    r"(?:\s*(?:,|&|and|en|to|tot|[-–])\s*"
    rf"(?:{FIGURE_WORD})?\s*{FIGURE_LABEL})*\s*\)?",
    re.IGNORECASE,
)
FIGURE_PARENTHETICAL = re.compile(
    rf"\([^()]*\b{FIGURE_WORD}\s*{FIGURE_LABEL}"
    r"(?:\s*(?:,|&|and|en|to|tot|[-–])\s*"
    rf"(?:{FIGURE_WORD})?\s*{FIGURE_LABEL})*[^()]*\)",
    re.IGNORECASE,
)
NUMERIC_FIGURE_LABEL = r"\d{1,3}[.,]\d{1,3}[a-z]?"
FIGURE_POINTER = r"(?:arrow|arrows|pijl|pijlen|asterisk)"
ORPHAN_FIGURE_PARENTHETICAL = re.compile(
    rf"\(\s*(?:{FIGURE_POINTER}\s+(?:in\s+)?)?"
    rf"{NUMERIC_FIGURE_LABEL}(?:\s+{FIGURE_POINTER})?"
    rf"(?:\s*(?:,\s*(?:(?:and|en)\s+)?|(?:and|en)\s+)"
    rf"(?:{FIGURE_POINTER}\s+(?:in\s+)?)?"
    rf"{NUMERIC_FIGURE_LABEL}(?:\s+{FIGURE_POINTER})?)*\s*\)",
    re.IGNORECASE,
)
DANGLING_FIGURE_SUFFIX = re.compile(
    rf",?\s*(?:and|en)\s+{NUMERIC_FIGURE_LABEL}"
    rf"(?:\s+{FIGURE_POINTER})?\s*\)",
    re.IGNORECASE,
)


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


def _strip_figure_references(value):
    value = FIGURE_PARENTHETICAL.sub("", value)
    value = FIGURE_REFERENCE.sub("", value)
    value = ORPHAN_FIGURE_PARENTHETICAL.sub("", value)
    value = DANGLING_FIGURE_SUFFIX.sub("", value)
    value = re.sub(r"\(\s*\)", "", value)
    value = re.sub(r"\s+([,.;:])", r"\1", value)
    value = re.sub(r"^[\s,.;:–-]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _capitalize_initial(value):
    value = (value or "").strip()
    for index, character in enumerate(value):
        if character.isalpha():
            return value[:index] + character.upper() + value[index + 1:]
    return value


_DUTCH_TEXT_REPLACEMENTS = (
    (r"(?m)^Findings$", "Bevindingen"),
    (r"(?m)^Differential Diagnosis$", "Differentiaaldiagnose"),
    (r"(?m)^Teaching Points$", "Kernpunten"),
    (r"(?m)^Management$", "Beleid"),
    (r"(?m)^Further Readings?$", "Referenties"),
    (r"\bTrue Disease Extent Demonstrated on MR Imaging\b", "werkelijke ziekte-uitbreiding aangetoond met MRI"),
    (r"\b(?:niet-contrast|noncontrast|onverbeterde) (?:berekende |gecomputeerde )?tomografie\s*\(CT\)", "CT zonder contrast"),
    (r"\b(?:niet-contrast|noncontrast|onverbeterde) CT\b", "CT zonder contrast"),
    (r"\bsingle[- ](?:photon|foton)[- ]?emissie (?:berekende|gecomputeerde) tomografie\b", "SPECT"),
    (r"\bcontrast[- ]versterkte\b", "contrastversterkte"),
    (r"\bcontrast[- ]versterkt\b", "contrastversterkt"),
    (r"\bcross[- ]sectionele imaging\b", "doorsnedebeeldvorming"),
    (r"\bcross[- ]sectional imaging\b", "doorsnedebeeldvorming"),
    (r"\bplain film\b", "conventionele radiografie"),
    (r"\bgecomputeerde tomografie\b", "computertomografie"),
    (r"\bberekende tomografie\b", "computertomografie"),
    (r"\bberekend tomografie\b", "computertomografie"),
    (r"\bonverbeterde\b", "ongecontrasteerde"),
    (r"\bultrageluid[- ]geleide\b", "echogeleide"),
    (r"\bultrasound[- ]guided\b", "echogeleide"),
    (r"\bultrageluid\b", "echografie"),
    (r"\bultrasound\b", "echografie"),
    (r"\bimaging findings\b", "beeldvormingsbevindingen"),
    (r"\bbeeldvorming-bevindingen\b", "beeldvormingsbevindingen"),
    (r"\bCT findings\b", "CT-bevindingen"),
    (r"\bMR imaging\b", "MRI"),
    (r"\bfluid attenuation\b", "vloeistofattenuatie"),
    (r"\bfluid verzachting\b", "vloeistofattenuatie"),
    (r"\bfluid demping\b", "vloeistofattenuatie"),
    (r"\bfluid[- ]fill(?:ed)?\b", "vloeistofgevuld"),
    (r"\blucht-fluid niveaus?\b", "lucht-vloeistofniveau"),
    (r"\bconservative management\b", "conservatieve behandeling"),
    (r"\bmanagement\b", "beleid"),
    (r"\bworkup\b", "diagnostische evaluatie"),
    (r"\bfill-in\b", "opvulling"),
    (r"\bup to\b", "tot"),
    (r"\bfindings\b", "bevindingen"),
    (r"\bfinding\b", "bevinding"),
    (r"\bimaging\b", "beeldvorming"),
    (r"\bfluid\b", "vloeistof"),
    (r"\bpresent\b", "aanwezig"),
    (r"\bnonspecific\b", "niet-specifiek"),
    (r"\bspecific\b", "specifiek"),
    (r"\bfixed\b", "vast"),
    (r"\bcontrast fills\b", "contrastmiddel vult"),
    (r"\bTumor\b", "tumor"),
    (r"\bholge\b", "holle"),
    (r"\baftrekken angiogram\b", "subtractieangiogram"),
    (r"\bbehoefte aspiratie\b", "naaldaspiratie"),
    (r"\bcutoffvan\b", "onderbreking van"),
    (r"\bHeterogenely\b", "heterogeen"),
    (r"\bsirty-shadowing\b", "vuileschaduwartefact"),
    (r"\bubareolaire\b", "subareolaire"),
    (r"\bmammografief\b", "mammografisch"),
    (r"\blumbometrie\b", "lumpectomie"),
    (r"\bHet icoken van\b", "Verdikking van"),
)


def _polish_dutch_text(value):
    text = value or ""
    for pattern, replacement in _DUTCH_TEXT_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _cap_learning_points(chunks, maximum):
    if len(chunks) <= maximum:
        return chunks
    group_size = (len(chunks) + maximum - 1) // maximum
    return [
        " ".join(chunks[index:index + group_size]).strip()
        for index in range(0, len(chunks), group_size)
    ][:maximum]


def _split_learning_points(section_key, lines):
    if section_key == "references":
        # References are line-based citations. Splitting on every number-dot
        # sequence breaks page ranges such as "1473-1505." into fake items.
        chunks = []
        reference_start = re.compile(
            r"^(?:\d{1,2}\.\s+|[A-Z][A-Za-z'’-]+\s+[A-Z]{1,4}[.,])"
        )
        for raw_line in lines:
            line = _clean_extracted_text(raw_line.strip())
            if not line:
                continue
            if re.match(r"^Case\s+\d+\b", line, re.IGNORECASE):
                break
            if not chunks or reference_start.match(line):
                chunks.append(line)
            else:
                chunks[-1] = f"{chunks[-1]} {line}".strip()
    elif section_key == "differential":
        # Differential diagnoses are already line-based in the source data.
        # Keep each line separate instead of joining names into one paragraph.
        chunks = []
        for raw_line in lines:
            for part in re.split(r"\s*■\s*", raw_line.strip()):
                line = _strip_figure_references(
                    _clean_extracted_text(part.strip())
                )
                if line:
                    chunks.append(line)
    else:
        text = " ".join(line.strip() for line in lines if line.strip())
        text = re.sub(r"\s+", " ", text).strip()
        text = _strip_figure_references(_clean_extracted_text(text))
        if not text:
            return []
        chunks = re.split(r"(?<=[.!?])\s+(?=[A-Za-zÀ-ÖØ-öø-ÿ0-9])", text)

    if section_key == "teaching":
        chunks = _cap_learning_points(chunks, 6)

    items = []
    for chunk in chunks:
        chunk = _capitalize_initial(chunk.strip())
        if not chunk:
            continue
        if re.fullmatch(
            r"\d+(?:[.,]\d+)?[a-z]?(?:\s*,\s*\d+(?:[.,]\d+)?[a-z]?)*\)?[.!]?",
            chunk,
            re.IGNORECASE,
        ):
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
        item = {"lead": lead, "text": body}
        if section_key == "differential" and lead:
            item["radiopaedia_url"] = (
                f"https://radiopaedia.org/search?q={quote_plus(lead)}"
            )
        items.append(item)
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


def _compact_gu_differential(card_id, correct_diagnosis):
    has_override = card_id in GU_DIFFERENTIAL_OVERRIDES_NL
    candidates = list(GU_DIFFERENTIAL_OVERRIDES_NL.get(card_id, []))

    cleaned = []
    for candidate in candidates:
        candidate = re.sub(
            r"^(?:zoals|waaronder)\s+",
            "",
            candidate.strip(" .;:"),
            flags=re.IGNORECASE,
        )
        candidate = _capitalize_initial(candidate)
        if not candidate or len(candidate) > 120:
            continue
        normalized = re.sub(r"\W+", "", candidate.lower())
        if normalized and all(
            normalized != re.sub(r"\W+", "", existing.lower())
            for existing in cleaned
        ):
            cleaned.append(candidate)

    if not cleaned:
        cleaned = [_capitalize_initial(correct_diagnosis)]
    elif not has_override and not any(
        re.sub(r"\W+", "", correct_diagnosis.lower())
        in re.sub(r"\W+", "", candidate.lower())
        or re.sub(r"\W+", "", candidate.lower())
        in re.sub(r"\W+", "", correct_diagnosis.lower())
        for candidate in cleaned
    ):
        cleaned.insert(0, _capitalize_initial(correct_diagnosis))

    return [{
        "lead": "",
        "text": candidate,
        "radiopaedia_url": f"https://radiopaedia.org/search?q={quote_plus(candidate)}",
    } for candidate in cleaned[:6]]


def _compact_gu_differential_section(
    card_id,
    sections,
    correct_diagnosis,
):
    compact_items = _compact_gu_differential(
        card_id,
        correct_diagnosis,
    )
    updated = []
    replaced = False
    for section in sections:
        if section["key"] == "differential":
            updated.append({**section, "items": compact_items})
            replaced = True
        else:
            updated.append(section)
    if not replaced:
        updated.insert(1 if updated else 0, {
            "key": "differential",
            "label": ANSWER_SECTION_LABELS["differential"],
            "items": compact_items,
        })
    return updated


@lru_cache(maxsize=None)
def load_core_translations(section_key, language):
    data_path = DATA_DIRECTORY / f"core_{section_key}_{language}.json"
    if not data_path.exists():
        return {}
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    return payload


@lru_cache(maxsize=None)
def load_core_section(section_key):
    data_path = DATA_DIRECTORY / f"core_{section_key}.json"
    if not data_path.exists():
        return []
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    dutch_translations = load_core_translations(section_key, "nl")
    dutch_histories = dutch_translations.get("histories", {})
    dutch_diagnoses = dutch_translations.get("diagnoses", {})
    dutch_answer_details = dutch_translations.get("answer_details", {})
    cards = []
    for card in payload.get("cards", []):
        diagnosis = _capitalize_initial(
            card.get("diagnosis") or "Diagnosis unavailable"
        )
        diagnosis_nl = _capitalize_initial(
            _polish_dutch_text(_clean_extracted_text(
                dutch_diagnoses.get(card["id"], diagnosis)
            ))
        )
        answer_details = card.get("answer_details") or ""
        answer_details_nl = _polish_dutch_text(
            _clean_extracted_text(
                dutch_answer_details.get(card["id"], answer_details)
            )
        )
        source_history = (card.get("history") or "").strip()
        cardiac_history_missing = (
            section_key == "cardiac"
            and source_history.lower() in MISSING_CLINICAL_HISTORY
        )
        history = (
            CARDIAC_QUESTION_DEFAULT
            if cardiac_history_missing
            else source_history or "Review the imaging case and formulate the diagnosis."
        )
        history_nl = _polish_dutch_text(
            _clean_extracted_text(
                CARDIAC_QUESTION_DEFAULT_NL
                if cardiac_history_missing
                else dutch_histories.get(card["id"], history)
            )
        )
        answer_sections_nl = parse_answer_details(answer_details_nl)
        if section_key == "genitourinary":
            answer_sections_nl = _compact_gu_differential_section(
                card["id"],
                answer_sections_nl,
                diagnosis_nl,
            )
        question_images = card.get("question_images") or (
            [card["question_image"]] if card.get("question_image") else []
        )
        answer_images = card.get("answer_images") or (
            [card["answer_image"]] if card.get("answer_image") else []
        )
        cards.append({
            "ID": card["id"],
            "Category": "CORE Radiology",
            "Vraag": history,
            "Vraag_nl": history_nl,
            "Correct": [diagnosis],
            "Correct_nl": [
                diagnosis_nl
            ],
            "A": "",
            "B": "",
            "C": "",
            "D": "",
            "image_url": (
                f"/static/core/{section_key}/{question_images[0]}"
                if question_images else None
            ),
            "image_urls": [
                f"/static/core/{section_key}/{filename}"
                for filename in question_images
            ],
            "answer_image_url": (
                f"/static/core/{section_key}/{answer_images[0]}"
                if answer_images else None
            ),
            "answer_image_urls": [
                f"/static/core/{section_key}/{filename}"
                for filename in answer_images
            ],
            "answer_details": answer_details,
            "answer_sections": parse_answer_details(answer_details),
            "answer_details_nl": answer_details_nl,
            "answer_sections_nl": answer_sections_nl,
            "radiopaedia_url": f"https://radiopaedia.org/search?q={quote_plus(diagnosis)}",
            "case_label": card.get("label") or card["id"],
            "core_section": section_key,
            "question_key": f"core:{section_key}:{card['id']}",
        })
    return cards


def get_core_sections():
    sections = []
    for section in CORE_SECTIONS:
        count = len(load_core_section(section["key"]))
        if section.get("is_beta_demo"):
            count = section.get("placeholder_count", 1)
        sections.append({
            **section,
            "count": count,
            "display_count": count or section.get("placeholder_count", 0),
            "is_placeholder": count == 0,
        })
    return sections


def get_core_section(section_key):
    return next(
        (section for section in get_core_sections() if section["key"] == section_key),
        None,
    )
