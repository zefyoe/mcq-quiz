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
MANUAL_HISTORY_TRANSLATIONS = {
    "CORE-IR-008": "74-jarige man, status na resectie van een niet-kleincellig longcarcinoom in de linker bovenkwab, met een nieuwe anteroposteriore vensterlymfeklier op CT waarvoor biopsie nodig is. Is er een toegangsweg tot deze laesie waarbij het longparenchym wordt gespaard?",
    "CORE-IR-011": "Twee verschillende patiënten met longkanker, status na resectie van de contralaterale long, verwezen voor biopsie van bijniermassa's. Hoe minimaliseert u het risico op een pneumothorax in de resterende solitaire long?",
    "CORE-IR-014": "Na beenmergtransplantatie, trombocytopenie en verhoogde leverfunctietests. De druk gemeten met de katheter was 10 mmHg in figuur 14.1 en 24 mmHg in figuur 14.2. De rechteratriumdruk was 6-8 mmHg.",
    "CORE-IR-022": "60-jarige man met gemetastaseerd coloncarcinoom, recent status na pulmonale metastasectomie, verwezen met de PET/CT-scans in figuren 22.1 en 22.2. Wat zijn de behandelingsopties voor deze patiënt?",
    "CORE-IR-028": "Koorts en leukocytose twee weken na embolisatie van de arteria hepatica. Figuur 28.3 is één week na embolisatie; figuur 28.4 twee weken erna.",
    "CORE-IR-031": "Niercelcarcinoom, status na een val.",
    "CORE-IR-038": "Koorts en leukocytose één week na gastrectomie, gecompliceerd door een abces. Na verwijdering van de draineringskatheter werd de patiënt hypotensief en tachycard, waarna een CT werd verricht (figuur 38.3).",
    "CORE-IR-047": "Blaascarcinoom, status na cystectomie en ileumconduit, gecompliceerd door bilaterale uretero-enterische anastomosestricturen. Welke katheters zijn zichtbaar in figuur 47.3?",
    "CORE-IR-051": "65-jarige vrouw met cervixcarcinoom, status na radiotherapie, met lekkage van urine uit het rectum.",
    "CORE-IR-053": "Slokdarmcarcinoom, status na gastric pull-up, met een proximale dunnedarmobstructie. Toegang voor enterale voeding is noodzakelijk.",
    "CORE-IR-061": "Coloncarcinoom, status na plaatsing van een biliaire wandstent vier maanden geleden, presenteert zich met koorts en leukocytose.",
    "CORE-IR-070": "45-jarige vrouw, recent status na resectie van een craniopharyngeoom, met een postoperatieve longembolie, verwezen voor plaatsing van een vena-cava-inferiorfilter. Figuren 70.1 en 70.2 tonen twee verschillende patiënten. Wat is het verschil?",
    "CORE-IR-071": "Therapieresistente buikpijn, status na plaatsing van een vena-cava-inferiorfilter.",
    "CORE-IR-072": "60-jarige vrouw met een permanent aanwezige vena-cava-inferiorfilter, zes jaar eerder geplaatst, met een voorgeschiedenis van enkele maanden met chronische bilaterale zwelling van de benen en één week acute verergering. Is er op basis van figuren 72.1-72.5 een mogelijke behandeling?",
    "CORE-IR-077": "84-jarige man met hypertensie en diabetes, status na endovasculaire reparatie van een infrarenaal abdominaal aorta-aneurysma van 6 cm, drie jaar geleden.",
    "CORE-IR-096": "34-jarige man, status na een verkeersongeval, met zwelling van de linkerdij. In de collectie op figuur 96.1 werd percutaan een drain geplaatst. Deze bleef twee weken ter plaatse met een aanhoudende seromelkachtige productie van 30-40 cc per dag. Figuur 96.2 toont een contrastonderzoek via de aanwezige drain. Wat zijn de behandelingsopties?",
    "CORE-IR-099": "67-jarige man, twee weken status na distale oesofagectomie en gedeeltelijke gastrectomie, met nieuwe koorts en leukocytose. De volgende onderzoeken werden verricht.",
    "CORE-PED-078": "Premature baby van 28 weken, één week oud.",
    "CORE-PED-081": "Premature jongen van 28 weken, één week oud (eerste afbeelding). De tweede afbeelding is acht weken later gemaakt.",
    "CORE-PED-082": "6-jarige met hoofdpijn en een veranderde mentale toestand.",
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
    (r"\bPresents\b", "presenteert zich"),
    (r"\bNeeds\b", "heeft behoefte aan"),
    (r"\bPelvic Mass\b", "bekkenmassa"),
    (r"\bPelvic\b", "bekken"),
    (r"\bColon Cancer\b", "coloncarcinoom"),
    (r"\bStatus Post\b", "status na"),
    (r"\bBiliaire Wand stent Plaatsing 4 Maanden Ago\b", "plaatsing van een biliaire wandstent vier maanden geleden"),
    (r"\bBiliaire Wand stent Plaatsing\b", "plaatsing van een biliaire wandstent"),
    (r"\bSeveral-Month History of Chronische Bilaterale Leg Swelling met 1 Week of Acute Verergering\b", "voorgeschiedenis van enkele maanden met chronische bilaterale zwelling van de benen en één week acute verergering"),
    (r"\bInwoning Permanente Inferior Vena Cava Filter geplaatst 6 jaar Prior\b", "een permanent aanwezige vena-cava-inferiorfilter, zes jaar eerder geplaatst"),
    (r"\bLeg Swelling\b", "zwelling van de benen"),
    (r"\bSeveral-Month History\b", "voorgeschiedenis van enkele maanden"),
    (r"\bHistory of\b", "voorgeschiedenis van"),
    (r"\bPrior\b", "eerder"),
    (r"\bAgo\b", "geleden"),
    (r"\bAccess Device\b", "toegangssysteem"),
    (r"\bVascular Access\b", "vasculaire toegang"),
    (r"\bmislukte Ureterale stent\b", "mislukte plaatsing van een ureterstent"),
    (r"\bInferior Vena Cava stent Acute bij chronische trombose\b", "stent in de vena cava inferior bij acute trombose bovenop chronische trombose"),
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
            MANUAL_HISTORY_TRANSLATIONS.get(card_id)
            or existing.get("histories", {}).get(card_id)
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
