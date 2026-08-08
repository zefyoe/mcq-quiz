import re

try:
    from filled_latin_terms import FILLED_LATIN_TERMS
except ImportError:
    FILLED_LATIN_TERMS = {}

try:
    from sourced_latin_terms import SOURCED_LATIN_SOURCES, SOURCED_LATIN_TERMS
except ImportError:
    SOURCED_LATIN_SOURCES = {}
    SOURCED_LATIN_TERMS = {}


SUPPORTED_LANGUAGES = {"en", "nl"}
DEFAULT_LANGUAGE = "nl"


DUTCH_TRANSLATIONS = {
    "Anatomy": "Anatomie",
    "Anatomy QBank": "Anatomie-vragenbank",
    "Anatomy Quiz": "Anatomiequiz",
    "Anatomy sections": "Anatomiesecties",
    "Anatomy Dashboard": "Anatomiedashboard",
    "ADMIN ROLE": "ADMINROL",
    "Back": "Terug",
    "Choose an anatomy subgroup": "Kies een anatomische subgroep",
    "Choose how many questions to include in this quiz.": "Kies hoeveel vragen je in deze quiz wilt opnemen.",
    "Cardiothoracic": "Cardiothoracaal",
    "Cardiothoracic anatomy": "Cardiothoracale anatomie",
    "Choose one answer below, then click Save answer. Once saved, the answer is locked.": "Kies hieronder één antwoord en klik daarna op Antwoord opslaan. Na het opslaan wordt het antwoord vergrendeld.",
    "Choose A, B, C, or D and save to move to the next question. You can still go back before submitting.": "Kies A, B, C of D en sla op om automatisch naar de volgende vraag te gaan. Je kunt vóór het indienen nog teruggaan.",
    "Choose A, B, C, or D, save your answer, and see the correct answer immediately.": "Kies A, B, C of D, sla je antwoord op en bekijk meteen het juiste antwoord.",
    "Completed": "Voltooid",
    "Complete quizzes consistently to build a streak.": "Maak regelmatig quizzen om een reeks op te bouwen.",
    "Continue Learning": "Verder leren",
    "Correct": "Juist",
    "Correct answer:": "Juiste antwoord:",
    "Current quiz": "Huidige quiz",
    "Dashboard": "Dashboard",
    "Define the A/B/C/D choices, pick the correct one, and save to lock it in.": "Vul de keuzes A/B/C/D in, selecteer het juiste antwoord en sla dit op.",
    "Email": "E-mail",
    "Exam Phase": "Examenmodus",
    "Focused review": "Gerichte herhaling",
    "Genito-Urinary": "Urogenitaal",
    "Genito-urinary anatomy": "Anatomie van het urogenitale stelsel",
    "Good job — keep practicing": "Goed gedaan — blijf oefenen",
    "Head and Neck": "Hoofd en hals",
    "Head and neck anatomy": "Anatomie van hoofd en hals",
    "History": "Geschiedenis",
    "Home": "Home",
    "How many questions do you want?": "Hoeveel vragen wil je?",
    "Incorrect": "Onjuist",
    "Last Activity": "Laatste activiteit",
    "Last Quiz": "Laatste quiz",
    "Log out": "Uitloggen",
    "Login": "Inloggen",
    "Medical quiz": "Medische quiz",
    "Mixed": "Gemengd",
    "Mixed Difficulty": "Gemengde moeilijkheid",
    "Musculoskeletal anatomy": "Anatomie van het bewegingsapparaat",
    "My Previous Tests": "Mijn eerdere toetsen",
    "Name": "Naam",
    "Needs improvement — review carefully": "Verbetering nodig — bekijk de antwoorden zorgvuldig",
    "New Anatomy Quiz": "Nieuwe anatomiequiz",
    "New Quiz": "Nieuwe quiz",
    "Next": "Volgende",
    "No correct answer available.": "Geen juist antwoord beschikbaar.",
    "No previous anatomy tests yet.": "Nog geen eerdere anatomietoetsen.",
    "No questions found.": "Geen vragen gevonden.",
    "No questions found in this subgroup yet.": "Er zijn nog geen vragen in deze subgroep.",
    "No score yet": "Nog geen score",
    "Not saved": "Niet opgeslagen",
    "Number of questions": "Aantal vragen",
    "Open Anatomy": "Anatomie openen",
    "Open the anatomy subgroups and begin a new session.": "Open de anatomische subgroepen en begin een nieuwe sessie.",
    "Password": "Wachtwoord",
    "Previous": "Vorige",
    "Previous Tests": "Eerdere toetsen",
    "Progress": "Voortgang",
    "Question": "Vraag",
    "Question count": "Aantal vragen",
    "Question Score": "Vragenscore",
    "QBank Usage": "Aantal beschikbare Qbank elementen",
    "Quiz completed": "Quiz voltooid",
    "Quiz Mode": "Quizmodus",
    "Quiz phase": "Quizmodus",
    "Quiz setup": "Quiz instellen",
    "Randomized from all anatomy groups": "Willekeurig samengesteld uit alle anatomiegroepen",
    "Register": "Registreren",
    "Retake Last Test": "Laatste toets opnieuw maken",
    "Retake This Test": "Deze toets opnieuw maken",
    "Review History": "Geschiedenis bekijken",
    "Review Questions": "Vragen nakijken",
    "Review Retakes": "Toetsen opnieuw maken",
    "Right answer:": "Juiste antwoord:",
    "Save answer": "Antwoord opslaan",
    "Saved": "Opgeslagen",
    "Saved and locked": "Opgeslagen en vergrendeld",
    "Score": "Score",
    "Select a subgroup": "Kies een subgroep",
    "Signed in": "Ingelogd",
    "Start Anatomy Quiz": "Anatomiequiz starten",
    "Start anatomy quiz": "Anatomiequiz starten",
    "Start First Quiz": "Eerste quiz starten",
    "Start Now": "Nu starten",
    "Start Quiz": "Quiz starten",
    "Study Planner": "Studieplanner",
    "Submit Quiz": "Quiz indienen",
    "Test Count": "Aantal toetsen",
    "Test History": "Toetsgeschiedenis",
    "Test Phase": "Oefenmodus",
    "Timed Exam Mode": "Getimede examenmodus",
    "Timer": "Timer",
    "University": "Universiteit",
    "View All Tests": "Alle toetsen bekijken",
    "Welcome": "Welkom",
    "Which anatomical structure is depicted?": "Welke anatomische structuur is afgebeeld?",
    "Your answer:": "Jouw antwoord:",
    "Your history": "Jouw geschiedenis",
    "Your learning journey starts here.": "Jouw leertraject begint hier.",
    "Your private medical question bank.": "Jouw persoonlijke medische vragenbank.",
    "Incorrect email or password.": "Onjuist e-mailadres of wachtwoord.",
    "Name is required.": "Naam is verplicht.",
    "University is required.": "Universiteit is verplicht.",
    "Email is required.": "E-mail is verplicht.",
    "Password must be at least 8 characters.": "Het wachtwoord moet minimaal 8 tekens bevatten.",
    "Passwords do not match.": "De wachtwoorden komen niet overeen.",
    "An account with that email already exists.": "Er bestaat al een account met dit e-mailadres.",
}


LATIN_EXACT = {
    "acromioclavicular joint": "Articulatio acromioclavicularis",
    "anatomical neck of humerus": "Collum anatomicum humeri",
    "anterior cerebral artery": "Arteria cerebri anterior",
    "anterior cruciate ligament": "Ligamentum cruciatum anterius",
    "anterior longitudinal ligament": "Ligamentum longitudinale anterius",
    "anterior tibial artery": "Arteria tibialis anterior",
    "axillary artery": "Arteria axillaris",
    "axillary lymph node": "Nodus lymphoideus axillaris",
    "axillary nerve": "Nervus axillaris",
    "basilar artery": "Arteria basilaris",
    "body of uterus": "Corpus uteri",
    "brachial artery": "Arteria brachialis",
    "brachial plexus": "Plexus brachialis",
    "carpal tunnel": "Canalis carpi",
    "cerebral aqueduct of sylvius": "Aqueductus mesencephali",
    "cervical canal": "Canalis cervicis uteri",
    "common femoral artery": "Arteria femoralis communis",
    "common femoral vein": "Vena femoralis communis",
    "coracoid process": "Processus coracoideus",
    "coronoid process of mandible": "Processus coronoideus mandibulae",
    "coronoid process of ulna": "Processus coronoideus ulnae",
    "dorsalis pedis artery": "Arteria dorsalis pedis",
    "external carotid artery": "Arteria carotis externa",
    "external iliac artery": "Arteria iliaca externa",
    "external iliac vein": "Vena iliaca externa",
    "external oblique": "Musculus obliquus externus abdominis",
    "external urethral sphincter": "Musculus sphincter urethrae externus",
    "femoral artery": "Arteria femoralis",
    "femoral head": "Caput femoris",
    "femoral neck": "Collum femoris",
    "fibular head": "Caput fibulae",
    "fourth ventricle": "Ventriculus quartus",
    "frontal bone": "Os frontale",
    "fundus of uterus": "Fundus uteri",
    "glenohumeral joint": "Articulatio glenohumeralis",
    "great cerebral vein": "Vena magna cerebri",
    "greater trochanter": "Trochanter major",
    "head of fibula": "Caput fibulae",
    "inferior vena cava": "Vena cava inferior",
    "internal carotid artery": "Arteria carotis interna",
    "internal iliac artery": "Arteria iliaca interna",
    "internal jugular vein": "Vena jugularis interna",
    "internal urethral sphincter": "Musculus sphincter urethrae internus",
    "intervertebral disc": "Discus intervertebralis",
    "lateral meniscus": "Meniscus lateralis",
    "lesser trochanter": "Trochanter minor",
    "medial meniscus": "Meniscus medialis",
    "middle cerebral artery": "Arteria cerebri media",
    "muscular wall of urinary bladder": "Tunica muscularis vesicae urinariae",
    "optic chiasm": "Chiasma opticum",
    "optic nerve": "Nervus opticus",
    "posterior cerebral artery": "Arteria cerebri posterior",
    "posterior cruciate ligament": "Ligamentum cruciatum posterius",
    "posterior longitudinal ligament": "Ligamentum longitudinale posterius",
    "posterior tibial artery": "Arteria tibialis posterior",
    "pubic symphysis": "Symphysis pubica",
    "renal artery": "Arteria renalis",
    "renal cortex": "Cortex renalis",
    "renal pelvis": "Pelvis renalis",
    "renal vein": "Vena renalis",
    "sacroiliac joint": "Articulatio sacroiliaca",
    "seminal vesicle": "Glandula vesiculosa",
    "spinal cord": "Medulla spinalis",
    "spinous process": "Processus spinosus",
    "subclavian artery": "Arteria subclavia",
    "superficial femoral artery": "Arteria femoralis superficialis",
    "superior vena cava": "Vena cava superior",
    "transverse process": "Processus transversus",
    "urinary bladder": "Vesica urinaria",
    "vertebral artery": "Arteria vertebralis",
    "vertebral body": "Corpus vertebrae",
}


ALREADY_LATIN = {
    "acetabulum", "acromion", "calcaneus", "capitate", "capitellum", "coccyx",
    "cuboid", "deltoid", "epiglottis", "hamate", "ilium", "ischium", "lunate",
    "navicular", "patella", "pisiform", "radius", "sacrum", "scaphoid", "talus",
    "trapezium", "trapezoid", "triquetrum", "trochlea", "ulna",
}


def translate_ui(text: str, language: str) -> str:
    if language != "nl":
        return text
    return DUTCH_TRANSLATIONS.get(text, text)


def _clean_term(text: str) -> str:
    cleaned = re.sub(r"[_`]+", " ", (text or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+\d+$", "", cleaned)
    return cleaned.strip()


def _side_suffix(side: str, latin_term: str) -> str:
    first = latin_term.split(" ", 1)[0].casefold()
    feminine = {"arteria", "vena", "glandula", "fissura", "fascia", "lamina", "pelvis", "tuba"}
    neuter = {"corpus", "caput", "collum", "ligamentum", "foramen", "os", "cornu"}
    if side == "right":
        adjective = "dextrum" if first in neuter else "dextra" if first in feminine else "dexter"
    else:
        adjective = "sinistrum" if first in neuter else "sinistra" if first in feminine else "sinister"
    return f"{latin_term} {adjective}"


def latinize_anatomy_term(text: str) -> str:
    cleaned = _clean_term(text)
    if not cleaned:
        return cleaned

    normalized = cleaned.casefold()
    if normalized in FILLED_LATIN_TERMS:
        return FILLED_LATIN_TERMS[normalized]
    if normalized in LATIN_EXACT:
        return LATIN_EXACT[normalized]
    if normalized in SOURCED_LATIN_TERMS:
        return SOURCED_LATIN_TERMS[normalized]
    if normalized in ALREADY_LATIN:
        return cleaned[:1].upper() + cleaned[1:]

    side = None
    for candidate in ("right", "left"):
        prefix = f"{candidate} "
        if normalized.startswith(prefix):
            side = candidate
            cleaned = cleaned[len(prefix):]
            normalized = cleaned.casefold()
            break

    if normalized in FILLED_LATIN_TERMS:
        translated = FILLED_LATIN_TERMS[normalized]
    elif normalized in LATIN_EXACT:
        translated = LATIN_EXACT[normalized]
    elif normalized in SOURCED_LATIN_TERMS:
        translated = SOURCED_LATIN_TERMS[normalized]
    else:
        return cleaned

    return _side_suffix(side, translated) if side else translated


def get_latin_term_source(text: str) -> str | None:
    return SOURCED_LATIN_SOURCES.get(_clean_term(text).casefold())
