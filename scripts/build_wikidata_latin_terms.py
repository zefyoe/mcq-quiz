"""Build a static TA98 Latin terminology map from Wikipedia/Wikidata.

The generated file is committed with the application, so production does not
need network access. Each entry keeps the source page used for verification.
"""

from __future__ import annotations

import json
import os
import pprint
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from anatomy_answer_bank import IMAGE_QUESTION_OVERRIDES, STATIC_QUESTION_OVERRIDES


ENDPOINT = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "RadyAnatomyQBank/1.0 (https://github.com/zefyoe/mcq-quiz)"
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "sourced_latin_terms.py")
SSL_CONTEXT = ssl.create_default_context(cafile="/etc/ssl/cert.pem")


TERM_ALIASES = {
    "4mt": "fourth metatarsal",
    "abdpollongus": "abductor pollicis longus",
    "abductorhallucis": "abductor hallucis",
    "acjoint": "acromioclavicular joint",
    "addmagnus": "adductor magnus",
    "adductorminimus": "adductor minimus",
    "adductortubercle": "adductor tubercle",
    "annulusfibrosus": "annulus fibrosus",
    "antarc c1": "anterior arch of atlas",
    "antlonglig": "anterior longitudinal ligament",
    "baseof1mc": "base of first metacarpal bone",
    "baseof2": "base of second metatarsal bone",
    "baseof2nd": "base of second metatarsal bone",
    "basilicvein": "basilic vein",
    "bicepsfe": "biceps femoris",
    "bicepsshorthead": "short head of biceps brachii",
    "bodypubis": "body of pubis",
    "capepiphysis": "epiphysis of capitate",
    "capitellumepi": "epiphysis of capitulum of humerus",
    "colanat": "anatomical neck of humerus",
    "coracoidproc": "coracoid process",
    "coracoidprocess": "coracoid process",
    "coronoidmandible": "coronoid process of mandible",
    "coronoidprocessulna": "coronoid process of ulna",
    "costotransvers": "costotransverse joint",
    "cub": "cuboid bone",
    "cuboidd": "cuboid bone",
    "cuneiformmedial": "medial cuneiform bone",
    "deepprofart": "deep femoral artery",
    "distalradioulnarjoint": "distal radioulnar joint",
    "distaltibiaepi": "distal epiphysis of tibia",
    "distcl": "distal clavicle",
    "dorsalped": "dorsalis pedis artery",
    "ecrl": "extensor carpi radialis longus",
    "epiph1stmetaca": "epiphysis of first metacarpal bone",
    "erecteurdurachis": "erector spinae",
    "erector": "erector spinae",
    "exitingnerve": "exiting spinal nerve",
    "extensordig": "extensor digitorum",
    "extensordigtendon": "extensor digitorum tendon",
    "facetjoint": "zygapophyseal joint",
    "femneck": "neck of femur",
    "femoralhead": "head of femur",
    "femveinleft": "left femoral vein",
    "fibulaa": "fibula",
    "fibulahead": "head of fibula",
    "firstrib": "first rib",
    "fossaolecranon": "olecranon fossa",
    "frontalsinus": "frontal sinus",
    "glenohu": "glenohumeral joint",
    "grac": "gracilis muscle",
    "headgastro": "head of gastrocnemius muscle",
    "hiatusadductor": "adductor hiatus",
    "hookhamate": "hook of hamate",
    "hookofhamate": "hook of hamate",
    "hookofhm": "hook of hamate",
    "iliaccrest": "iliac crest",
    "iliacwing": "wing of ilium",
    "iliumcrest": "iliac crest",
    "infarticularprocess": "inferior articular process",
    "infborderscap": "inferior border of scapula",
    "intercondyl": "intercondylar fossa",
    "intercondylaremi": "intercondylar eminence",
    "intercondyle": "intercondylar fossa",
    "intervertebralspace": "intervertebral disc",
    "laminal3": "lamina of third lumbar vertebra",
    "latepi": "lateral epicondyle",
    "latepicondyl": "lateral epicondyle",
    "lateraltibiaplateau": "lateral condyle of tibia",
    "latmal": "lateral malleolus",
    "leftcommonfem": "left common femoral artery",
    "leftdeepfemart": "left deep femoral artery",
    "lister": "dorsal tubercle of radius",
    "longheadofbiceps": "long head of biceps brachii",
    "lumbarverte": "lumbar vertebra",
    "manubriumsternum": "manubrium of sternum",
    "maxillarysinus": "maxillary sinus",
    "medialclavicle": "sternal end of clavicle",
    "medialcondyle": "medial condyle",
    "medialepicondyle": "medial epicondyle",
    "medialtibiaplateau": "medial condyle of tibia",
    "metaphystibia": "metaphysis of tibia",
    "middlecuneiform": "intermediate cuneiform bone",
    "middlethirdclavicle": "middle third of clavicle",
    "nuclpulp": "nucleus pulposus",
    "obtex": "obturator externus muscle",
    "obtext": "obturator externus muscle",
    "obturatorexternuss": "obturator externus muscle",
    "obturatorinter": "obturator internus muscle",
    "obturatorintern": "obturator internus muscle",
    "orbitalfloor": "floor of orbit",
    "pectmaj": "pectoralis major muscle",
    "pectmajor": "pectoralis major muscle",
    "pediclel5": "pedicle of fifth lumbar vertebra",
    "petittubercle": "lesser tubercle of humerus",
    "petroustemporalbone": "petrous part of temporal bone",
    "poplitealart": "popliteal artery",
    "poplitealarteryy": "popliteal artery",
    "poplitealartt": "popliteal artery",
    "poplitealgroove": "popliteal groove",
    "posteriorlonglig": "posterior longitudinal ligament",
    "posteriorsuperioriliacspine": "posterior superior iliac spine",
    "posttibialartery": "posterior tibial artery",
    "processcoronoidulna": "coronoid process of ulna",
    "processstyloidradii": "styloid process of radius",
    "proculna": "proximal ulna",
    "profundafemartery": "deep femoral artery",
    "prostate central": "central zone of prostate",
    "proxfemur": "proximal femur",
    "psoasm": "psoas major muscle",
    "psoasmaj": "psoas major muscle",
    "psoasmajor": "psoas major muscle",
    "quadratuslomborum": "quadratus lumborum muscle",
    "quadricepstendon": "quadriceps tendon",
    "radialhead": "head of radius",
    "radialneck": "neck of radius",
    "rhomboidmajor": "rhomboid major muscle",
    "rightcomfem": "right common femoral artery",
    "rotundum": "foramen rotundum",
    "s1promontory": "sacral promontory",
    "sacralala": "sacral ala",
    "sacralfor": "sacral foramen",
    "sacroil": "sacroiliac joint",
    "sacroiliacjoint": "sacroiliac joint",
    "sagittalsut": "sagittal suture",
    "scaph": "scaphoid bone",
    "semimembr": "semimembranosus muscle",
    "sesamoid": "sesamoid bone",
    "spinalcord": "spinal cord",
    "spinascapulae": "spine of scapula",
    "spinous": "spinous process",
    "spinousprocess": "spinous process",
    "spinousprocessc7": "spinous process of seventh cervical vertebra",
    "ster": "sternum",
    "suparticprocess": "superior articular process",
    "superficialarteryfem": "superficial femoral artery",
    "suppubramus": "superior ramus of pubis",
    "suprapate": "suprapatellar fat pad",
    "suprapatellarfatpad": "suprapatellar fat pad",
    "supras": "supraspinatus muscle",
    "symphysispubis": "pubic symphysis",
    "talarneck": "neck of talus",
    "tensorfascia": "tensor fasciae latae muscle",
    "tfcc": "triangular fibrocartilage complex",
    "thecalsac12": "thecal sac",
    "thoracicintervertebralforamen": "thoracic intervertebral foramen",
    "tibialpostart": "posterior tibial artery",
    "tibialposteriorart": "posterior tibial artery",
    "tibiofibularistrunk": "tibiofibular trunk",
    "transproce": "transverse process",
    "transversabd": "transversus abdominis muscle",
    "transversec1": "transverse process of atlas",
    "transversepr": "transverse process",
    "transverseprocess": "transverse process",
    "triquetrumm": "triquetral bone",
    "tuberositetibia": "tibial tuberosity",
    "vastuslateralis": "vastus lateralis muscle",
    "zygoap": "zygapophyseal joint",
    "zygoapophyseal": "zygapophyseal joint",
    "zygoapophysealjoint": "zygapophyseal joint",
    "zygomaticofrontalsuture": "frontozygomatic suture",
}


def clean_term(value: str) -> str:
    value = re.sub(r"[_`]+", " ", (value or "").strip())
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+\d+$", "", value)
    return value.strip()


def split_side(value: str) -> tuple[str | None, str]:
    normalized = value.casefold()
    for side in ("right", "left"):
        if normalized.startswith(f"{side} "):
            return side, value[len(side) + 1:]
    return None, value


def side_suffix(side: str | None, latin_term: str) -> str:
    if not side:
        return latin_term
    first = latin_term.split(" ", 1)[0].casefold()
    feminine = {"arteria", "vena", "glandula", "fissura", "fascia", "lamina", "pelvis", "tuba"}
    neuter = {"corpus", "caput", "collum", "ligamentum", "foramen", "os", "cornu"}
    if side == "right":
        adjective = "dextrum" if first in neuter else "dextra" if first in feminine else "dexter"
    else:
        adjective = "sinistrum" if first in neuter else "sinistra" if first in feminine else "sinister"
    return f"{latin_term} {adjective}"


def collect_terms() -> dict[str, tuple[str | None, str]]:
    raw_terms = set()
    for bank in (IMAGE_QUESTION_OVERRIDES, STATIC_QUESTION_OVERRIDES):
        for row in bank.values():
            raw_terms.update((row.get(key) or "").strip() for key in "ABCD")
    raw_terms.update(os.path.splitext(filename)[0] for filename in IMAGE_QUESTION_OVERRIDES)

    result = {}
    for raw_term in raw_terms:
        cleaned = clean_term(raw_term)
        if not cleaned:
            continue
        side, base = split_side(cleaned)
        canonical = TERM_ALIASES.get(base.casefold(), base)
        result[cleaned.casefold()] = (side, canonical.casefold())
    return result


def sparql_query() -> dict:
    query = """
    SELECT ?name ?item ?latin ?article WHERE {
      ?item wdt:P3982 ?latin.
      ?item rdfs:label ?name.
      FILTER(LANG(?name) = "en")
      OPTIONAL {
        ?article schema:about ?item;
                 schema:isPartOf <https://en.wikipedia.org/>.
      }
    }
    LIMIT 30000
    """
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    request = urllib.request.Request(
        f"{ENDPOINT}?{params}",
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=60, context=SSL_CONTEXT) as response:
        return json.load(response)


def wikipedia_query(titles: list[str]) -> dict:
    params = urllib.parse.urlencode({
        "action": "query",
        "format": "json",
        "redirects": "1",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "titles": "|".join(titles),
    })
    request = urllib.request.Request(
        f"{WIKIPEDIA_API}?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=60, context=SSL_CONTEXT) as response:
        return json.load(response)


def clean_wikipedia_latin(value: str) -> str | None:
    value = re.sub(r"<!--.*?-->", "", value)
    value = re.sub(r"<ref\b[^>]*>.*?</ref>", "", value, flags=re.IGNORECASE)
    value = re.sub(r"<ref\b[^>]*/>", "", value, flags=re.IGNORECASE)
    value = re.split(r"<br\s*/?>", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", value)

    def replace_template(match: re.Match) -> str:
        parts = [part.strip() for part in match.group(1).split("|")]
        values = [part for part in parts[1:] if part and part.casefold() not in {"la", "latin"} and "=" not in part]
        return values[-1] if values else ""

    for _ in range(3):
        value = re.sub(r"\{\{([^{}]+)\}\}", replace_template, value)
    value = re.sub(r"'{2,}", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ,;")
    if not value or not re.search(r"[A-Za-z]", value):
        return None
    return normalize_latin_term(value)


def extract_wikipedia_latin(wikitext: str) -> str | None:
    match = re.search(r"^\|\s*Latin\s*=\s*(.*?)\s*$", wikitext, flags=re.IGNORECASE | re.MULTILINE)
    if match:
        return clean_wikipedia_latin(match.group(1))

    match = re.search(r"\bLatin:\s*([^<\n.;]+)", wikitext, flags=re.IGNORECASE)
    return clean_wikipedia_latin(match.group(1)) if match else None


def page_is_specific_enough(canonical: str, page_title: str) -> bool:
    generic_tokens = {"a", "an", "the", "of"}
    canonical_tokens = {
        token for token in re.findall(r"[a-z0-9]+", canonical.casefold())
        if token not in generic_tokens
    }
    page_tokens = {
        token for token in re.findall(r"[a-z0-9]+", page_title.casefold())
        if token not in generic_tokens
    }
    return canonical_tokens.issubset(page_tokens)


def fetch_wikipedia_terms(canonical_terms: set[str]) -> dict[str, dict]:
    results = {}
    ordered = sorted(canonical_terms)
    for offset in range(0, len(ordered), 10):
        batch = ordered[offset:offset + 10]
        requested_titles = [term[:1].upper() + term[1:] for term in batch]
        for attempt in range(3):
            try:
                payload = wikipedia_query(requested_titles)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

        title_aliases = {title.casefold(): title.casefold() for title in requested_titles}
        for item in payload.get("query", {}).get("normalized", []):
            title_aliases[item["from"].casefold()] = item["to"].casefold()
        for item in payload.get("query", {}).get("redirects", []):
            title_aliases[item["from"].casefold()] = item["to"].casefold()

        pages = {
            page["title"].casefold(): page
            for page in payload.get("query", {}).get("pages", {}).values()
            if "missing" not in page
        }
        for canonical, requested_title in zip(batch, requested_titles):
            resolved = requested_title.casefold()
            for _ in range(4):
                next_title = title_aliases.get(resolved, resolved)
                if next_title == resolved:
                    break
                resolved = next_title
            page = pages.get(resolved)
            if not page:
                continue
            if not page_is_specific_enough(canonical, page["title"]):
                continue
            revisions = page.get("revisions", [])
            if not revisions:
                continue
            wikitext = revisions[0].get("slots", {}).get("main", {}).get("*", "")
            latin = extract_wikipedia_latin(wikitext)
            if not latin:
                continue
            results[canonical] = {
                "latin": latin,
                "source": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page['title'].replace(' ', '_'))}",
            }

        print(f"Wikipedia checked {min(offset + len(batch), len(ordered))}/{len(ordered)}", flush=True)
        time.sleep(0.1)
    return results


def fetch_official_terms(canonical_terms: set[str]) -> dict[str, dict]:
    results = {}
    for attempt in range(3):
        try:
            payload = sparql_query()
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    for binding in payload["results"]["bindings"]:
        key = binding["name"]["value"].casefold()
        if key not in canonical_terms:
            continue
        source = binding.get("article", binding["item"])["value"]
        results.setdefault(key, {
            "latin": binding["latin"]["value"],
            "source": source,
        })
    print(f"Matched {len(results)}/{len(canonical_terms)} canonical terms", flush=True)
    return results


def normalize_latin_term(value: str) -> str | None:
    suspicious = (" or ", " o només ", " ou ", " et/ou ")
    if any(fragment in value.casefold() for fragment in suspicious):
        return None
    if re.search(r"[àèìòù]", value.casefold()):
        return None

    expansions = (
        (r"^m\.\s+", "Musculus "),
        (r"^mm\.\s+", "Musculi "),
        (r"^n\.\s+", "Nervus "),
        (r"^nn\.\s+", "Nervi "),
        (r"^v\.\s+", "Vena "),
        (r"^vv\.\s+", "Venae "),
        (r"^a\.\s+", "Arteria "),
        (r"^aa\.\s+", "Arteriae "),
        (r"^lig\.\s+", "Ligamentum "),
        (r"^ligg\.\s+", "Ligamenta "),
    )
    normalized = value.strip()
    for pattern, replacement in expansions:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return normalized[:1].upper() + normalized[1:]


def main() -> None:
    original_terms = collect_terms()
    canonical_terms = {canonical for _, canonical in original_terms.values()}
    wikipedia_terms = fetch_wikipedia_terms(canonical_terms)
    wikidata_terms = fetch_official_terms(canonical_terms - set(wikipedia_terms))
    official = {**wikidata_terms, **wikipedia_terms}
    mapped = {}
    sources = {}

    for original, (side, canonical) in sorted(original_terms.items()):
        match = official.get(canonical)
        if not match:
            continue
        normalized_latin = normalize_latin_term(match["latin"])
        if not normalized_latin:
            continue
        mapped[original] = side_suffix(side, normalized_latin)
        sources[original] = match["source"]

    header = (
        "# Generated by scripts/build_wikidata_latin_terms.py.\n"
        "# Exact English Wikipedia infobox terms are preferred; missing terms use\n"
        "# Wikidata property P3982 (TA98 Latin term). Every value retains its source.\n\n"
    )
    with open(OUTPUT_PATH, "w", encoding="utf-8") as output:
        output.write(header)
        output.write("SOURCED_LATIN_TERMS = ")
        output.write(pprint.pformat(mapped, width=120, sort_dicts=True))
        output.write("\n\nSOURCED_LATIN_SOURCES = ")
        output.write(pprint.pformat(sources, width=120, sort_dicts=True))
        output.write("\n")

    print(f"Wrote {len(mapped)} sourced terms to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
