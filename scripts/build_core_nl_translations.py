import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from argostranslate import translate


ROOT = Path(__file__).resolve().parents[1]
SECTION_HEADINGS = {
    "Findings": "findings",
    "Differential Diagnosis": "differential",
    "Teaching Points": "teaching",
    "Management": "management",
    "Further Reading": "references",
    "Further Readings": "references",
}
SECTION_HEADINGS_NL = {
    "findings": "Bevindingen",
    "differential": "Differentiaaldiagnose",
    "teaching": "Kernpunten",
    "management": "Beleid",
    "references": "Referenties",
}
MAX_CHUNK_LENGTH = 3500
MEDICAL_REPLACEMENTS = (
    (r"\bSEH is\b", "Er is"),
    (r"\bThis\b", "Dit"),
    (r"\bThese\b", "Deze"),
    (r"\bThose\b", "Die"),
    (r"\bIn patients\b", "Bij patiënten"),
    (r"\bpatients\b", "patiënten"),
    (r"\bPatient\b", "Patiënt"),
    (r"\bpatient\b", "patiënt"),
    (r"\bfeatures\b", "kenmerken"),
    (r"\bfeature\b", "kenmerk"),
    (r"\bfindings\b", "bevindingen"),
    (r"\bmanagement\b", "beleid"),
    (r"\bdiagnosis\b", "diagnose"),
    (r"\bHypothalamic Hamartoma\b", "Hypothalamisch hamartoom"),
    (r"\bDysembryoplastic Neuroepithelial Tumor\b", "Dysembryoplastische neuro-epitheliale tumor"),
    (r"\bHemimegalencephaly\b", "Hemimegalencefalie"),
    (r"\bChoroid Plexus Carcinoma\b", "Choroïdplexuscarcinoom"),
    (r"\bGliomatosis Cerebri\b", "Gliomatosis cerebri"),
    (r"\bTrigeminal Schwannoma\b", "Trigeminusschannoom"),
    (r"\bDirect Carotid-Cavernous Fistula\b", "Directe carotis-caverneuze fistel"),
    (r"\bLissencephaly\b", "Lissencefalie"),
    (r"\bHoloprosencephaly\b", "Holoprosencefalie"),
    (r"\bBand Heterotopia\b", "Bandheterotopie"),
    (r"\bEpidermoid Cyst\b", "Epidermoïdcyste"),
    (r"\bCavernous Malformation\b", "Caverneuze malformatie"),
    (r"\bHydranencephaly\b", "Hydranencefalie"),
    (r"\bSchizencephaly\b", "Schizencefalie"),
    (r"\bVon Hippel-Lindau Disease\b", "Ziekte van Von Hippel-Lindau"),
    (r"\bAcute Transverse Myelitis\b", "Acute transversale myelitis"),
    (r"\bDorsal Dermal Sinus\b", "Dorsale dermale sinus"),
    (r"\bSyringohydromyelia\b", "Syringohydromyelie"),
    (r"\bDiastematomyelia\b", "Diastematomyelie"),
    (r"\bCoalescent Mastoiditis\b", "Confluente mastoïditis"),
    (r"\bAntrochoanal Polyp\b", "Antrochoanale poliep"),
    (r"\bOcular Globe Rupture\b", "Ruptuur van de oogbol"),
    (r"\bCarotid Body Paraganglioma\b", "Paraganglioom van het carotislichaam"),
    (r"\bThyroglossal Duct Cyst\b", "Cyste van de ductus thyroglossus"),
    (r"\bOrbit Hemangioma\b", "Hemangioom van de orbita"),
    (r"\bLabyrinthitis Ossificans\b", "Ossificerende labyrintitis"),
    (r"\bOptic Neuritis\b", "Opticusneuritis"),
    (r"\bInflammatory Adenitis, Mycobacterium Avium Complex\b", "Inflammatoire adenitis door het Mycobacterium avium-complex"),
    (r"\bBrachial Plexus Neurofibroma\b", "Neurofibroom van de plexus brachialis"),
    (r"\bSEH is\b", "Er is"),
    (r"\bSEH zijn\b", "Er zijn"),
    (r"\bInverted papilloma\b", "Invers papilloom"),
    (r"\bFocal gliomas\b", "Focale gliomen"),
    (r"\bOverall\b", "Over het algemeen"),
    (r"\btumors\b", "tumoren"),
    (r"\bfreebase form\b", "freebasevorm"),
    (r"\bFindings\b", "Bevindingen"),
    (r"\bDifferential Diagnosis\b", "Differentiaaldiagnose"),
    (r"\bTeaching Points\b", "Kernpunten"),
    (r"\bManagement\b", "Beleid"),
    (r"\bFurther Readings?\b", "Referenties"),
    (r"\bHerpes Encephalitis\b", "Herpesencefalitis"),
    (r"\bCerebral Venous Thrombosis and Infarction\b", "Cerebrale veneuze trombose en infarcering"),
    (r"\bEncephalitis\b", "Encefalitis"),
    (r"\bencephalitis\b", "encefalitis"),
    (r"\bhemorrhage\b", "bloeding"),
    (r"\bischemia\b", "ischemie"),
    (r"\binfarction\b", "infarcering"),
    (r"\binfarct\b", "infarct"),
    (r"\bFindings\b", "Bevindingen"),
    (r"\bImaging\b", "Beeldvorming"),
    (r"\bimage\b", "beeld"),
    (r"\bimages\b", "beelden"),
    (r"\bpresents to the (?:ED|ER)\b", "presenteert zich op de SEH"),
    (r"\bpresenting to the (?:ED|ER)\b", "met presentatie op de SEH"),
    (r"\bto the (?:ED|ER)\b", "op de SEH"),
    (r"\bThere is\b", "Er is"),
    (r"\bThere are\b", "Er zijn"),
    (r"\bwith\b", "met"),
    (r"\band\b", "en"),
    (r"\bthe\b", "de"),
    (r"\bof the\b", "van de"),
    (r"\bright\b", "rechter"),
    (r"\bleft\b", "linker"),
    (r"\bsmall\b", "kleine"),
    (r"\blarge\b", "grote"),
    (r"\bnormal\b", "normale"),
    (r"\bacute\b", "acute"),
    (r"\bchronic\b", "chronische"),
    (r"\bconsistent with\b", "passend bij"),
    (r"\bassociated with\b", "geassocieerd met"),
    (r"\bdue to\b", "als gevolg van"),
    (r"\bcan be seen\b", "kan worden gezien"),
    (r"\bshows\b", "toont"),
    (r"\bdemonstrates\b", "toont"),
    (r"\breveals\b", "toont"),
    (r"\bdiagnosis\b", "diagnose"),
    (r"\bdiagnostic\b", "diagnostische"),
    (r"\bmanagement\b", "beleid"),
    (r"\bTumor\b", "Tumor"),
    (r"\bPineoblastomas\b", "Pineoblastomen"),
    (r"\bPineoblastoma\b", "Pineoblastoom"),
    (r"\bPineocytoma\b", "Pineocytoom"),
    (r"\bMeningioma\b", "Meningeoom"),
    (r"\bGlioma\b", "Glioom"),
    (r"\bLymphoma\b", "Lymfoom"),
    (r"\bCerebral\b", "Cerebrale"),
    (r"\bvenous\b", "veneuze"),
    (r"\bthrombosis\b", "trombose"),
    (r"\bseizures\b", "epileptische aanvallen"),
    (r"\bseizure\b", "epileptische aanval"),
    (r"\bberekeningen\b", "verkalkingen"),
    (r"\bberekening\b", "verkalking"),
    (r"\bcalculatory['’]?s\b", "verkalkingen"),
    (r"\binvlouerende\b", "involuerende"),
    (r"\bfibrodenomas\b", "fibroadenomen"),
    (r"\bfibrodenoom\b", "fibroadenoom"),
    (r"\bfibradenomen\b", "fibroadenomen"),
    (r"\bductal carcinoom\b", "ductaal carcinoom"),
    (r"\bductalcarcinoom\b", "ductaal carcinoom"),
    (r"\bductaalcarcinoom\b", "ductaal carcinoom"),
    (r"\bkanaalcarcinoom\b", "ductaal carcinoom"),
    (r"\bdarmkanker\b", "ductaal carcinoom"),
    (r"\baxillary\b", "axillair"),
    (r"\bokillaire\b", "axillaire"),
    (r"\bokillary\b", "axillaire"),
    (r"\blymf knooppunt\b", "lymfeklier"),
    (r"\blymf knoop\b", "lymfeklier"),
    (r"\blymfknoop\b", "lymfeklier"),
    (r"\blumbectomie\b", "lumpectomie"),
    (r"\blumbecomy\b", "lumpectomie"),
    (r"\bclombectomie\b", "lumpectomie"),
    (r"\bmammagram\b", "mammogram"),
    (r"\bmammagram\b", "mammogram"),
    (r"\bgeheime verkalkingen\b", "secretoire verkalkingen"),
    (r"\bsarcoma\b", "sarcoom"),
    (r"\bsternalis muscle\b", "musculus sternalis"),
    (r"\bsebaceous cyst\b", "talgcyste"),
    (r"\bSEH is\b", "Er is"),
    (r"\bSEH zijn\b", "Er zijn"),
)


def preserve_initial_case(source, replacement):
    return replacement[:1].upper() + replacement[1:] if source[:1].isupper() else replacement


def polish_translation(text):
    polished = text or ""
    for pattern, replacement in MEDICAL_REPLACEMENTS:
        polished = re.sub(
            pattern,
            lambda match: preserve_initial_case(match.group(0), replacement),
            polished,
            flags=re.IGNORECASE,
        )
    return polished


def split_chunks(text):
    if len(text) <= MAX_CHUNK_LENGTH:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > MAX_CHUNK_LENGTH:
        split_at = max(
            remaining.rfind("\n", 0, MAX_CHUNK_LENGTH),
            remaining.rfind(". ", 0, MAX_CHUNK_LENGTH),
        )
        if split_at < MAX_CHUNK_LENGTH // 2:
            split_at = MAX_CHUNK_LENGTH
        else:
            split_at += 1
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def translate_text(text):
    text = (text or "").strip()
    if not text:
        return ""
    translated = "\n".join(
        translate.translate(chunk, "en", "nl")
        for chunk in split_chunks(text)
    )
    translated = translated[:1].upper() + translated[1:] if translated else translated
    return polish_translation(translated)


def translate_answer_details(text):
    sections = []
    current_heading = None
    current_lines = []

    def append_section():
        if not current_heading:
            return
        content = "\n".join(current_lines).strip()
        section_key = SECTION_HEADINGS[current_heading]
        translated = content if section_key == "references" else translate_text(content)
        sections.append(f"{SECTION_HEADINGS_NL[section_key]}\n{translated}".strip())

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        matched_heading = next(
            (heading for heading in SECTION_HEADINGS if line.lower() == heading.lower()),
            None,
        )
        if matched_heading:
            append_section()
            current_heading = matched_heading
            current_lines = []
        elif current_heading:
            current_lines.append(raw_line)
    append_section()
    return "\n".join(sections)


def translate_card(card, existing):
    card_id = card["id"]
    return card_id, {
        "history": polish_translation(
            existing.get("histories", {}).get(card_id)
            or translate_text(card.get("history", ""))
        ),
        "diagnosis": polish_translation(
            existing.get("diagnoses", {}).get(card_id)
            or translate_text(card.get("diagnosis", ""))
        ),
        "answer_details": (
            existing.get("answer_details", {}).get(card_id)
            or translate_answer_details(card.get("answer_details", ""))
        ),
    }


def write_output(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def translate_section(section_key, workers):
    source_path = ROOT / "data" / f"core_{section_key}.json"
    output_path = ROOT / "data" / f"core_{section_key}_nl.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    existing = (
        json.loads(output_path.read_text(encoding="utf-8"))
        if output_path.exists()
        else {}
    )
    output = {
        "histories": dict(existing.get("histories", {})),
        "diagnoses": dict(existing.get("diagnoses", {})),
        "answer_details": dict(existing.get("answer_details", {})),
    }
    cards = source.get("cards", [])

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(translate_card, card, existing): card["id"]
            for card in cards
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            card_id, translated = future.result()
            output["histories"][card_id] = translated["history"]
            output["diagnoses"][card_id] = translated["diagnosis"]
            output["answer_details"][card_id] = translated["answer_details"]
            if completed % 10 == 0 or completed == len(cards):
                write_output(output_path, output)
                print(f"{section_key}: {completed}/{len(cards)}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Build complete Dutch translations for CORE case content."
    )
    parser.add_argument(
        "sections",
        nargs="*",
        default=["gastrointestinal", "genitourinary", "breast"],
    )
    parser.add_argument("--workers", type=int, default=4)
    arguments = parser.parse_args()
    for section in arguments.sections:
        translate_section(section, max(1, min(arguments.workers, 6)))


if __name__ == "__main__":
    main()
