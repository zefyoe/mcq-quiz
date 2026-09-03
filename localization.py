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

try:
    from sourced_french_terms import SOURCED_FRENCH_SOURCES, SOURCED_FRENCH_TERMS
except ImportError:
    SOURCED_FRENCH_SOURCES = {}
    SOURCED_FRENCH_TERMS = {}


SUPPORTED_LANGUAGES = {"en", "fr", "nl"}
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
    "Gastrointestinal": "Gastro-intestinaal",
    "Gastrointestinal anatomy": "Gastro-intestinale anatomie",
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


FRENCH_TRANSLATIONS = {
    "Anatomy": "Anatomie",
    "Anatomy QBank": "Banque de questions d’anatomie",
    "Anatomy Quiz": "Quiz d’anatomie",
    "Anatomy sections": "Sections d’anatomie",
    "Anatomy Dashboard": "Tableau de bord d’anatomie",
    "ADMIN ROLE": "RÔLE ADMIN",
    "Back": "Retour",
    "Choose an anatomy subgroup": "Choisissez une section anatomique",
    "Choose how many questions to include in this quiz.": "Choisissez le nombre de questions à inclure dans ce quiz.",
    "Cardiothoracic": "Cardiothoracique",
    "Cardiothoracic anatomy": "Anatomie cardiothoracique",
    "Gastrointestinal": "Gastro-intestinal",
    "Gastrointestinal anatomy": "Anatomie gastro-intestinale",
    "Choose one answer below, then click Save answer. Once saved, the answer is locked.": "Choisissez une réponse ci-dessous, puis cliquez sur Enregistrer la réponse. Une fois enregistrée, la réponse est verrouillée.",
    "Choose A, B, C, or D and save to move to the next question. You can still go back before submitting.": "Choisissez A, B, C ou D et enregistrez votre réponse pour passer à la question suivante. Vous pouvez encore revenir en arrière avant l’envoi.",
    "Choose A, B, C, or D, save your answer, and see the correct answer immediately.": "Choisissez A, B, C ou D, enregistrez votre réponse et affichez immédiatement la bonne réponse.",
    "Completed": "Terminé",
    "Complete quizzes consistently to build a streak.": "Effectuez régulièrement des quiz pour maintenir votre série.",
    "Continue Learning": "Continuer l’apprentissage",
    "Correct": "Correct",
    "Correct answer:": "Bonne réponse :",
    "Current quiz": "Quiz en cours",
    "Dashboard": "Tableau de bord",
    "Define the A/B/C/D choices, pick the correct one, and save to lock it in.": "Définissez les choix A/B/C/D, sélectionnez la bonne réponse et enregistrez-la.",
    "Email": "E-mail",
    "Exam Phase": "Mode examen",
    "Focused review": "Révision ciblée",
    "Genito-Urinary": "Urogénital",
    "Genito-urinary anatomy": "Anatomie de l’appareil urogénital",
    "Good job — keep practicing": "Bon travail — continuez à vous entraîner",
    "Head and Neck": "Tête et cou",
    "Head and neck anatomy": "Anatomie de la tête et du cou",
    "History": "Historique",
    "Home": "Accueil",
    "How many questions do you want?": "Combien de questions souhaitez-vous ?",
    "Incorrect": "Incorrect",
    "Last Activity": "Dernière activité",
    "Last Quiz": "Dernier quiz",
    "Log out": "Se déconnecter",
    "Login": "Se connecter",
    "Medical quiz": "Quiz médical",
    "Mixed": "Mixte",
    "Mixed Difficulty": "Difficulté mixte",
    "Musculoskeletal anatomy": "Anatomie musculosquelettique",
    "My Previous Tests": "Mes tests précédents",
    "Name": "Nom",
    "Needs improvement — review carefully": "À améliorer — révisez attentivement",
    "New Anatomy Quiz": "Nouveau quiz d’anatomie",
    "New Quiz": "Nouveau quiz",
    "Next": "Suivant",
    "No correct answer available.": "Aucune bonne réponse disponible.",
    "No previous anatomy tests yet.": "Aucun test d’anatomie précédent.",
    "No questions found.": "Aucune question trouvée.",
    "No questions found in this subgroup yet.": "Aucune question n’est encore disponible dans cette section.",
    "No score yet": "Aucun score",
    "Not saved": "Non enregistré",
    "Number of questions": "Nombre de questions",
    "Open Anatomy": "Ouvrir l’anatomie",
    "Open the anatomy subgroups and begin a new session.": "Ouvrez les sections anatomiques et commencez une nouvelle session.",
    "Password": "Mot de passe",
    "Previous": "Précédent",
    "Previous Tests": "Tests précédents",
    "Progress": "Progression",
    "Question": "Question",
    "Question count": "Nombre de questions",
    "Question Score": "Score aux questions",
    "QBank Usage": "Questions disponibles",
    "Quiz completed": "Quiz terminé",
    "Quiz Mode": "Mode du quiz",
    "Quiz phase": "Mode du quiz",
    "Quiz setup": "Configuration du quiz",
    "Randomized from all anatomy groups": "Sélection aléatoire dans toutes les sections anatomiques",
    "Register": "Créer un compte",
    "Retake Last Test": "Refaire le dernier test",
    "Retake This Test": "Refaire ce test",
    "Review History": "Consulter l’historique",
    "Review Questions": "Revoir les questions",
    "Review Retakes": "Tests à refaire",
    "Right answer:": "Bonne réponse :",
    "Save answer": "Enregistrer la réponse",
    "Saved": "Enregistré",
    "Saved and locked": "Enregistré et verrouillé",
    "Score": "Score",
    "Select a subgroup": "Sélectionnez une section",
    "Signed in": "Connecté",
    "Start Anatomy Quiz": "Commencer le quiz d’anatomie",
    "Start anatomy quiz": "Commencer le quiz d’anatomie",
    "Start First Quiz": "Commencer le premier quiz",
    "Start Now": "Commencer",
    "Start Quiz": "Commencer le quiz",
    "Study Planner": "Planificateur d’étude",
    "Submit Quiz": "Envoyer le quiz",
    "Test Count": "Nombre de tests",
    "Test History": "Historique des tests",
    "Test Phase": "Mode entraînement",
    "Timed Exam Mode": "Mode examen chronométré",
    "Timer": "Chronomètre",
    "University": "Université",
    "View All Tests": "Voir tous les tests",
    "Welcome": "Bienvenue",
    "Which anatomical structure is depicted?": "Quelle structure anatomique est représentée ?",
    "Your answer:": "Votre réponse :",
    "Your history": "Votre historique",
    "Your learning journey starts here.": "Votre parcours d’apprentissage commence ici.",
    "Your private medical question bank.": "Votre banque privée de questions médicales.",
    "Incorrect email or password.": "Adresse e-mail ou mot de passe incorrect.",
    "Name is required.": "Le nom est obligatoire.",
    "University is required.": "L’université est obligatoire.",
    "Email is required.": "L’adresse e-mail est obligatoire.",
    "Password must be at least 8 characters.": "Le mot de passe doit contenir au moins 8 caractères.",
    "Passwords do not match.": "Les mots de passe ne correspondent pas.",
    "An account with that email already exists.": "Un compte associé à cette adresse e-mail existe déjà.",
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

FRENCH_TERMS_BY_COMPACT_KEY = {
    re.sub(r"[^a-z0-9]", "", key.casefold()): value
    for key, value in SOURCED_FRENCH_TERMS.items()
}


def translate_ui(text: str, language: str) -> str:
    translations = {
        "nl": DUTCH_TRANSLATIONS,
        "fr": FRENCH_TRANSLATIONS,
    }.get(language)
    return translations.get(text, text) if translations else text


def _clean_term(text: str) -> str:
    cleaned = re.sub(r"[_`]+", " ", (text or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+\d+$", "", cleaned)
    return cleaned.strip()


def _capitalize_initial(text: str) -> str:
    """Capitalize the first letter without changing anatomical Latin casing."""
    for index, character in enumerate(text):
        if character.isalpha():
            return text[:index] + character.upper() + text[index + 1:]
    return text


def _lowercase_initial(text: str) -> str:
    for index, character in enumerate(text):
        if character.isalpha():
            return text[:index] + character.lower() + text[index + 1:]
    return text


def _side_suffix(side: str, latin_term: str) -> str:
    first = latin_term.split(" ", 1)[0].casefold()
    feminine = {"arteria", "vena", "glandula", "fissura", "fascia", "lamina", "pelvis", "tuba"}
    neuter = {"corpus", "caput", "collum", "ligamentum", "foramen", "os", "cornu"}
    if side == "right":
        adjective = "dextrum" if first in neuter else "dextra" if first in feminine else "dexter"
    else:
        adjective = "sinistrum" if first in neuter else "sinistra" if first in feminine else "sinister"
    return f"{latin_term} {adjective}"


def _french_side_suffix(side: str, french_term: str) -> str:
    if side == "left":
        adjective = "gauche"
    else:
        feminine_starts = (
            "artère ", "veine ", "glande ", "fissure ", "fosse ", "face ",
            "branche ", "tête ", "queue ", "lame ", "membrane ", "zone ",
            "cavité ", "bourse ", "capsule ", "cochlée ", "moelle ", "trompe ",
            "épine ", "crête ", "suture ", "racine ", "partie ", "paroi ",
            "aile ", "articulation ", "scissure ", "loge ",
        )
        adjective = "droite" if french_term.casefold().startswith(feminine_starts) else "droit"
    return f"{french_term} {adjective}"


def frenchize_anatomy_term(text: str) -> str:
    cleaned = _clean_term(text)
    if not cleaned:
        return cleaned

    normalized = cleaned.casefold()
    if re.fullmatch(r"\d+(?:[.,]\d+)?", normalized):
        return cleaned
    if normalized.startswith("attachment of "):
        structure = re.sub(
            r"^(the|a|an)\s+",
            "",
            cleaned[len("attachment of "):].strip(),
            flags=re.IGNORECASE,
        )
        translated = frenchize_anatomy_term(structure)
        return _capitalize_initial(f"Insertion de {_lowercase_initial(translated)}")

    if normalized in SOURCED_FRENCH_TERMS:
        return _capitalize_initial(SOURCED_FRENCH_TERMS[normalized])

    compact_key = re.sub(r"[^a-z0-9]", "", normalized)
    if compact_key in FRENCH_TERMS_BY_COMPACT_KEY:
        return _capitalize_initial(FRENCH_TERMS_BY_COMPACT_KEY[compact_key])

    for side in ("right", "left"):
        prefix = f"{side} "
        if normalized.startswith(prefix):
            base_source = cleaned[len(prefix):]
            base_key = base_source.casefold()
            base = SOURCED_FRENCH_TERMS.get(base_key)
            if not base:
                base = FRENCH_TERMS_BY_COMPACT_KEY.get(
                    re.sub(r"[^a-z0-9]", "", base_key)
                )
            if base:
                return _capitalize_initial(_french_side_suffix(side, base))
            break

    # Keep the verified Latin terminology as the fallback whenever Wikipedia
    # or Wikidata has no suitable French anatomical name.
    return latinize_anatomy_term(cleaned, language="nl")


def latinize_anatomy_term(text: str, language: str = "nl") -> str:
    if language == "fr":
        return frenchize_anatomy_term(text)

    cleaned = _clean_term(text)
    if not cleaned:
        return cleaned

    normalized = cleaned.casefold()
    if normalized.startswith("attachment of "):
        attached_structure = cleaned[len("attachment of "):].strip()
        attached_structure = re.sub(r"^(the|a|an)\s+", "", attached_structure, flags=re.IGNORECASE)
        translated_structure = latinize_anatomy_term(attached_structure, language=language)
        attachment_prefix = "Insertion de" if language == "fr" else "Aanhechting van"
        return _capitalize_initial(
            f"{attachment_prefix} {_lowercase_initial(translated_structure)}"
        )

    if normalized in FILLED_LATIN_TERMS:
        return _capitalize_initial(FILLED_LATIN_TERMS[normalized])
    if normalized in LATIN_EXACT:
        return _capitalize_initial(LATIN_EXACT[normalized])
    if normalized in SOURCED_LATIN_TERMS:
        return _capitalize_initial(SOURCED_LATIN_TERMS[normalized])
    if normalized in ALREADY_LATIN:
        return _capitalize_initial(cleaned)

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
        return _capitalize_initial(cleaned)

    result = _side_suffix(side, translated) if side else translated
    return _capitalize_initial(result)


def get_latin_term_source(text: str) -> str | None:
    return SOURCED_LATIN_SOURCES.get(_clean_term(text).casefold())
