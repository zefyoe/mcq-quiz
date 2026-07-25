import os
import random
import re
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request, session, redirect, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import func, inspect, text
from werkzeug.utils import secure_filename

from localization import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    latinize_anatomy_term,
    translate_ui,
)
from models import QuestionProgress, QuizAttempt, db, Question, User
from questions_data import questions

try:
    from anatomy_answer_bank import IMAGE_QUESTION_OVERRIDES, STATIC_QUESTION_OVERRIDES
except ImportError:
    IMAGE_QUESTION_OVERRIDES = {}
    STATIC_QUESTION_OVERRIDES = {}


# -------------------------
# App + DB config
# -------------------------

def build_database_uri() -> str:
    uri = os.environ.get("DATABASE_URL", "sqlite:///quiz.db")

    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    if uri.startswith("postgresql://") and not uri.startswith("postgresql+psycopg://"):
        uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)

    return uri


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = build_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["UPLOAD_FOLDER"] = os.path.join(app.static_folder, "uploads", "questions")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

if os.environ.get("RENDER") or os.environ.get("FLASK_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True

db.init_app(app)

AUTO_IMAGE_CATEGORY = os.environ.get("AUTO_IMAGE_CATEGORY", "Anatomy")
STANDARD_IMAGE_PROMPT = "Which anatomical structure is depicted?"
ADMIN_EMAIL = "y@bymed.be"
ANATOMY_CATEGORY = "Anatomy"
ANATOMY_SUBGROUPS = {
    "msk": {
        "label": "MSK",
        "description": "Musculoskeletal anatomy",
    },
    "genito-urinary": {
        "label": "Genito-Urinary",
        "description": "Genito-urinary anatomy",
    },
    "head-and-neck": {
        "label": "Head and Neck",
        "description": "Head and neck anatomy",
    },
    "mixed": {
        "label": "Mixed",
        "description": "Randomized from all anatomy groups",
    },
}
MAX_QUIZ_QUESTIONS = 50
ANATOMY_RUNTIME_FOLDER_CATEGORIES = {
    "GU": "Anatomy - Genito-Urinary",
    "HN": "Anatomy - Head and Neck",
}
QUIZ_MODES = {
    "test": {
        "label": "Test Phase",
        "description": "Show the correct answer after each saved question.",
    },
    "exam": {
        "label": "Exam Phase",
        "description": "Auto-move to the next question after saving and show a timer.",
    },
}
QUIZ_POOLS = {
    "all": {
        "label": "All questions",
        "description": "A balanced random selection from this anatomy section.",
    },
    "due": {
        "label": "Smart review",
        "description": "Questions that are ready for another repetition.",
    },
    "incorrect": {
        "label": "Previously incorrect",
        "description": "Focus on questions you answered incorrectly before.",
    },
    "unseen": {
        "label": "Unseen questions",
        "description": "Only questions you have not answered yet.",
    },
    "marked": {
        "label": "Marked questions",
        "description": "Build a quiz from questions you saved for later.",
    },
}
DISABLED_CATEGORIES = {"physics"}


# -------------------------
# Login setup
# -------------------------

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except:
        return None


# -------------------------
# Helpers
# -------------------------

def normalize_correct(q: dict) -> list[str]:
    correct = q["Correct"] if isinstance(q["Correct"], list) else [q["Correct"]]
    return sorted([(c or "").strip().upper() for c in correct if c])


def get_default_correct_choice(seed: str | None) -> str:
    letters = ["A", "B", "C", "D"]
    normalized_seed = (seed or "").strip()
    if not normalized_seed:
        return "A"
    index = sum(ord(char) for char in normalized_seed) % len(letters)
    return letters[index]


def normalize_text_answer(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def normalize_category(s: str) -> str:
    return (s or "").strip().lower()


def get_current_language() -> str:
    language = (session.get("language") or DEFAULT_LANGUAGE).strip().lower()
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def tr(text: str) -> str:
    return translate_ui(text, get_current_language())


def localize_quiz_title(title: str) -> str:
    if get_current_language() != "nl":
        return title

    replacements = {
        "Anatomy - MSK": "Anatomie - MSK",
        "Anatomy - Genito-Urinary": "Anatomie - Urogenitaal",
        "Anatomy - Head and Neck": "Anatomie - Hoofd en hals",
        "Anatomy - Mixed": "Anatomie - Gemengd",
        "Anatomy": "Anatomie",
    }
    return replacements.get(title, translate_ui(title, "nl"))


def localize_question_for_display(question: dict) -> dict:
    localized = dict(question)
    if (
        get_current_language() != "nl"
        or not is_anatomy_category_name(question.get("Category"))
        or (current_user.is_authenticated and current_user.is_admin)
    ):
        return localized

    prompt = question.get("Vraag") or ""
    localized["Vraag"] = translate_ui(prompt, "nl")
    for key in ("A", "B", "C", "D"):
        localized[key] = latinize_anatomy_term(question.get(key) or "")
    if question.get("structure_title"):
        localized["structure_title"] = latinize_anatomy_term(question["structure_title"])
    return localized


def localize_quiz_results(results: list[dict]) -> list[dict]:
    if get_current_language() != "nl":
        return results

    localized_results = []
    for result in results:
        localized = dict(result)
        localized["Vraag"] = translate_ui(result.get("Vraag") or "", "nl")
        if is_anatomy_category_name(result.get("Category")):
            localized["correct_texts"] = [
                latinize_anatomy_term(answer) for answer in result.get("correct_texts", [])
            ]
            localized["options"] = {
                key: latinize_anatomy_term(value)
                for key, value in result.get("options", {}).items()
            }
        localized_results.append(localized)
    return localized_results


@app.context_processor
def inject_language_helpers():
    return {
        "language": get_current_language(),
        "tr": tr,
        "localize_quiz_title": localize_quiz_title,
    }


def normalize_anatomy_subgroup(subgroup: str | None) -> str:
    return normalize_category(subgroup).replace("_", "-").replace(" ", "-")


def is_anatomy_category_name(category: str | None) -> bool:
    cat_norm = normalize_category(category)
    return cat_norm == normalize_category(ANATOMY_CATEGORY) or cat_norm.startswith("anatomy -")


def get_anatomy_subgroup_for_category(category: str | None) -> str | None:
    cat_norm = normalize_category(category)

    if cat_norm == normalize_category(ANATOMY_CATEGORY):
        return "msk"

    if not is_anatomy_category_name(category):
        return None

    if "musculoskeletal" in cat_norm or "msk" in cat_norm:
        return "msk"
    if "genito" in cat_norm or "urinary" in cat_norm:
        return "genito-urinary"
    if "head" in cat_norm and "neck" in cat_norm:
        return "head-and-neck"

    return None


def get_runtime_image_category_for_path(path: str) -> str:
    images_root = os.path.abspath(os.path.join(app.root_path, "static/images"))
    absolute_path = os.path.abspath(path)
    relative_path = os.path.relpath(absolute_path, images_root)
    first_part = relative_path.split(os.sep, 1)[0]

    if first_part in ANATOMY_RUNTIME_FOLDER_CATEGORIES:
        return ANATOMY_RUNTIME_FOLDER_CATEGORIES[first_part]

    return ANATOMY_CATEGORY


def get_quiz_display_title(category: str, subgroup: str | None = None) -> str:
    if normalize_category(category) != normalize_category(ANATOMY_CATEGORY):
        return category

    subgroup_key = normalize_anatomy_subgroup(subgroup)
    subgroup_meta = ANATOMY_SUBGROUPS.get(subgroup_key)
    if subgroup_meta:
        return f"{ANATOMY_CATEGORY} - {subgroup_meta['label']}"

    return ANATOMY_CATEGORY


def is_admin_email(email: str) -> bool:
    return (email or "").strip().lower() == ADMIN_EMAIL


def user_has_admin_access(user: User | None) -> bool:
    return bool(user and user.is_authenticated and is_admin_email(getattr(user, "email", "")))


def sync_user_admin_flag(user: User | None) -> bool:
    if not user:
        return False

    should_be_admin = is_admin_email(user.email)
    if user.is_admin != should_be_admin:
        user.is_admin = should_be_admin
        db.session.commit()
        return True

    return False


def enforce_single_admin_account():
    changed = False

    for user in User.query.all():
        should_be_admin = is_admin_email(user.email)
        if user.is_admin != should_be_admin:
            user.is_admin = should_be_admin
            changed = True

    if changed:
        db.session.commit()


def ensure_quiz_attempt_schema():
    inspector = inspect(db.engine)
    if "quiz_attempt" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("quiz_attempt")}
    if "quiz_mode" in column_names:
        return

    db.session.execute(text("ALTER TABLE quiz_attempt ADD COLUMN quiz_mode VARCHAR(20) NOT NULL DEFAULT 'test'"))
    db.session.commit()


def ensure_user_profile_schema():
    inspector = inspect(db.engine)
    user_table_name = User.__table__.name

    if user_table_name not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns(user_table_name)}
    statements = []

    if "name" not in column_names:
        statements.append('ALTER TABLE "user" ADD COLUMN name VARCHAR(255)')
    if "university" not in column_names:
        statements.append('ALTER TABLE "user" ADD COLUMN university VARCHAR(255)')

    for statement in statements:
        db.session.execute(text(statement))

    if statements:
        db.session.commit()


def is_placeholder_option(value: str) -> bool:
    return (value or "").strip().upper() in {"A", "B", "C", "D", "OPTION A", "OPTION B", "OPTION C", "OPTION D"}


def use_compact_answer_buttons(q: dict) -> bool:
    if not q.get("image_url"):
        return False

    option_values = [q.get("A"), q.get("B"), q.get("C"), q.get("D")]
    return all(is_placeholder_option(value or "") for value in option_values)


def get_image_display_title(image_url: str | None) -> str | None:
    if not image_url:
        return None

    filename = os.path.basename(image_url)
    if not filename:
        return None

    return build_structure_title(filename)


def db_question_to_dict(q: Question) -> dict:
    return {
        "ID": q.qid,
        "Category": q.category,
        "Vraag": q.text,
        "A": q.a,
        "B": q.b,
        "C": q.c,
        "D": q.d,
        "Correct": [q.correct],
        "image_url": q.image_url,
        "structure_title": get_image_display_title(q.image_url),
        "compact_options": use_compact_answer_buttons({
            "A": q.a,
            "B": q.b,
            "C": q.c,
            "D": q.d,
            "image_url": q.image_url,
        }),
    }


def get_correct_answer_texts(q: dict) -> list[str]:
    if q.get("structure_title"):
        return [q["structure_title"]]

    correct_keys = normalize_correct(q)
    answers = []

    if correct_keys == ["T"]:
        for key in ["A", "B", "C", "D"]:
            option_text = (q.get(key) or "").strip()
            if option_text:
                answers.append(option_text)
        return answers

    for key in correct_keys:
        if len(key) == 1 and key in {"A", "B", "C", "D"}:
            option_text = (q.get(key) or "").strip()
            if option_text:
                answers.append(option_text)
        elif key:
            answers.append(key)

    return answers


def get_display_answer_option(q: dict, key: str) -> str:
    option_text = (q.get(key) or "").strip()

    if key == "A" and q.get("structure_title") and use_compact_answer_buttons(q):
        return q["structure_title"]

    return option_text


def get_effective_correct_choice(q: dict) -> str:
    normalized_correct = normalize_correct(q)
    if normalized_correct and normalized_correct[0] in {"A", "B", "C", "D"}:
        if q.get("structure_title") and use_compact_answer_buttons(q):
            return get_default_correct_choice(q.get("ID") or q.get("image_url"))
        return normalized_correct[0]

    return get_default_correct_choice(q.get("ID") or q.get("image_url"))


def get_effective_answer_options(q: dict) -> dict[str, str]:
    if q.get("structure_title") and use_compact_answer_buttons(q):
        correct_choice = get_effective_correct_choice(q)
        return {
            "A": q["structure_title"] if correct_choice == "A" else "",
            "B": q["structure_title"] if correct_choice == "B" else "",
            "C": q["structure_title"] if correct_choice == "C" else "",
            "D": q["structure_title"] if correct_choice == "D" else "",
        }

    return {
        "A": get_display_answer_option(q, "A"),
        "B": get_display_answer_option(q, "B"),
        "C": get_display_answer_option(q, "C"),
        "D": get_display_answer_option(q, "D"),
    }


def merge_question_lists(*question_lists: list[dict]) -> list[dict]:
    merged = []
    seen_keys = set()

    for question_list in question_lists:
        for question in question_list:
            dedupe_key = question.get("image_url") or question.get("ID")
            if not dedupe_key or dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            merged.append(question)

    return merged


def apply_static_question_override(question: dict) -> dict:
    qid = (question.get("ID") or "").strip()
    override = STATIC_QUESTION_OVERRIDES.get(qid)
    if not override:
        return dict(question)

    merged = dict(question)
    merged.update(override)
    return merged


def get_categories() -> list[str]:
    cats = set()
    has_anatomy = False

    for (c,) in db.session.query(Question.category).distinct().all():
        if c:
            if is_anatomy_category_name(c):
                has_anatomy = True
            else:
                cats.add(c.strip())

    for q in questions:
        category = (apply_static_question_override(q).get("Category") or "").strip()
        if not category:
            continue
        if is_anatomy_category_name(category):
            has_anatomy = True
        else:
            cats.add(category)

    if build_runtime_image_questions(AUTO_IMAGE_CATEGORY):
        has_anatomy = True

    if has_anatomy:
        cats.add(ANATOMY_CATEGORY)

    return sorted(category for category in cats if normalize_category(category) not in DISABLED_CATEGORIES)


def get_questions_for_category(category: str, subgroup: str | None = None) -> list[dict]:
    cat_norm = normalize_category(category)

    if cat_norm == normalize_category(ANATOMY_CATEGORY):
        return get_questions_for_anatomy_subgroup(subgroup)

    db_qs = (
        Question.query
        .filter(func.lower(func.trim(Question.category)) == cat_norm)
        .all()
    )

    db_questions = [db_question_to_dict(q) for q in db_qs]
    runtime_image_questions = build_runtime_image_questions(category)
    static_questions = [
        apply_static_question_override(q)
        for q in questions
        if normalize_category(apply_static_question_override(q).get("Category")) == cat_norm
    ]

    return merge_question_lists(db_questions, runtime_image_questions, static_questions)


def get_all_anatomy_questions() -> list[dict]:
    db_qs = Question.query.all()
    db_questions = [
        db_question_to_dict(q)
        for q in db_qs
        if is_anatomy_category_name(q.category)
    ]
    static_questions = [
        apply_static_question_override(q)
        for q in questions
        if is_anatomy_category_name(apply_static_question_override(q).get("Category"))
    ]
    runtime_image_questions = build_runtime_image_questions(ANATOMY_CATEGORY)

    return merge_question_lists(db_questions, static_questions, runtime_image_questions)


def get_questions_for_anatomy_subgroup(subgroup: str | None) -> list[dict]:
    subgroup_key = normalize_anatomy_subgroup(subgroup)
    if subgroup_key not in ANATOMY_SUBGROUPS:
        return []

    anatomy_questions = get_all_anatomy_questions()

    if subgroup_key == "mixed":
        return anatomy_questions

    return [
        question for question in anatomy_questions
        if get_anatomy_subgroup_for_category(question.get("Category")) == subgroup_key
    ]


def get_anatomy_subgroup_cards() -> list[dict]:
    cards = []

    for key, meta in ANATOMY_SUBGROUPS.items():
        count = len(get_questions_for_anatomy_subgroup(key))
        cards.append({
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "count": count,
        })

    return cards


def get_question_key(question: dict) -> str:
    return (question.get("image_url") or question.get("ID") or "").strip()


def normalize_quiz_pool(pool: str | None) -> str:
    pool_key = normalize_category(pool)
    return pool_key if pool_key in QUIZ_POOLS else "all"


def get_user_progress_by_key(user_id: int) -> dict[str, QuestionProgress]:
    return {
        progress.question_key: progress
        for progress in QuestionProgress.query.filter_by(user_id=user_id).all()
    }


def filter_questions_for_pool(
    question_list: list[dict],
    user_id: int,
    pool: str | None,
) -> list[dict]:
    pool_key = normalize_quiz_pool(pool)
    if pool_key == "all":
        return list(question_list)

    progress_by_key = get_user_progress_by_key(user_id)
    now = datetime.utcnow()
    filtered = []

    for question in question_list:
        progress = progress_by_key.get(get_question_key(question))
        if pool_key == "unseen" and (progress is None or progress.times_seen == 0):
            filtered.append(question)
        elif pool_key == "incorrect" and progress and progress.times_seen > progress.times_correct:
            filtered.append(question)
        elif pool_key == "marked" and progress and progress.is_marked:
            filtered.append(question)
        elif (
            pool_key == "due"
            and progress
            and progress.times_seen > 0
            and progress.next_review_at
            and progress.next_review_at <= now
        ):
            filtered.append(question)

    return filtered


def get_quiz_pool_counts(question_list: list[dict], user_id: int) -> dict[str, int]:
    return {
        pool_key: len(filter_questions_for_pool(question_list, user_id, pool_key))
        for pool_key in QUIZ_POOLS
    }


def get_learning_dashboard(user_id: int) -> dict:
    all_questions = get_all_anatomy_questions()
    progress_by_key = get_user_progress_by_key(user_id)
    current_question_keys = {get_question_key(question) for question in all_questions}
    now = datetime.utcnow()
    seen = [
        progress for key, progress in progress_by_key.items()
        if key in current_question_keys and progress.times_seen > 0
    ]
    due = [
        progress for progress in seen
        if progress.next_review_at and progress.next_review_at <= now
    ]
    mastered = [
        progress for progress in seen
        if progress.correct_streak >= 3
        and progress.times_correct / progress.times_seen >= 0.8
    ]

    subgroup_stats = []
    for subgroup_key in ("msk", "genito-urinary", "head-and-neck"):
        questions_in_subgroup = [
            question for question in all_questions
            if get_anatomy_subgroup_for_category(question.get("Category")) == subgroup_key
        ]
        progress_rows = [
            progress_by_key[get_question_key(question)]
            for question in questions_in_subgroup
            if get_question_key(question) in progress_by_key
            and progress_by_key[get_question_key(question)].times_seen > 0
        ]
        answered = sum(progress.times_seen for progress in progress_rows)
        correct = sum(progress.times_correct for progress in progress_rows)
        subgroup_stats.append({
            "key": subgroup_key,
            "label": ANATOMY_SUBGROUPS[subgroup_key]["label"],
            "total": len(questions_in_subgroup),
            "seen": len(progress_rows),
            "accuracy": round(correct / answered * 100) if answered else None,
            "coverage": round(len(progress_rows) / len(questions_in_subgroup) * 100)
            if questions_in_subgroup else 0,
        })

    return {
        "total": len(all_questions),
        "seen": len(seen),
        "unseen": max(0, len(all_questions) - len(seen)),
        "due": len(due),
        "marked": sum(
            1 for key, progress in progress_by_key.items()
            if key in current_question_keys and progress.is_marked
        ),
        "mastered": len(mastered),
        "coverage": round(len(seen) / len(all_questions) * 100) if all_questions else 0,
        "subgroups": subgroup_stats,
    }


def get_active_quiz_summary() -> dict | None:
    order = session.get("order") or []
    category = session.get("category")
    subgroup = session.get("subgroup")
    if not order or normalize_category(category) != normalize_category(ANATOMY_CATEGORY):
        return None

    subgroup_meta = ANATOMY_SUBGROUPS.get(normalize_anatomy_subgroup(subgroup))
    title = get_quiz_display_title(category, subgroup)
    return {
        "title": title,
        "count": len(order),
        "mode": normalize_quiz_mode(session.get("quiz_mode")),
        "pool": normalize_quiz_pool(session.get("quiz_pool")),
        "subgroup_label": subgroup_meta["label"] if subgroup_meta else ANATOMY_CATEGORY,
        "resume_url": url_for(
            "quiz",
            category=category,
            subgroup=subgroup,
            resume="1",
        ),
    }


def get_question_limit(requested_count: str | int | None, available_count: int) -> int:
    try:
        count = int(requested_count or 0)
    except (TypeError, ValueError):
        count = 0

    if available_count <= 0:
        return 0

    if count <= 0:
        count = min(MAX_QUIZ_QUESTIONS, available_count)

    return max(1, min(count, MAX_QUIZ_QUESTIONS, available_count))


def get_category_question_count(category: str) -> int:
    if normalize_category(category) == normalize_category(ANATOMY_CATEGORY):
        return len(get_all_anatomy_questions())
    return len(get_questions_for_category(category))


def get_category_icon(category: str) -> str:
    icon_map = {
        "anatomy": "AN",
        "cardiology": "CD",
        "respiratory": "RS",
        "pathology": "PT",
        "pharmacology": "PH",
        "physiology": "FY",
        "microbiology": "MB",
        "biochemistry": "BC",
    }
    return icon_map.get(normalize_category(category), "MC")


def build_home_category_cards(categories: list[str]) -> list[dict]:
    difficulty_by_category = {
        "anatomy": "Mixed Difficulty",
        "physiology": "Intermediate",
        "pharmacology": "Intermediate",
        "pathology": "Intermediate",
        "microbiology": "Beginner",
        "biochemistry": "Beginner",
    }

    cards = []
    for category in categories:
        if normalize_category(category) != normalize_category(ANATOMY_CATEGORY):
            continue
        cards.append({
            "name": category,
            "icon": get_category_icon(category),
            "count": get_category_question_count(category),
            "difficulty": difficulty_by_category.get(normalize_category(category), "Mixed Difficulty"),
            "description": f"Practice MCQs in {category}",
            "available": True,
        })
    return cards


def get_last_quiz_attempt(user_id: int) -> QuizAttempt | None:
    return (
        QuizAttempt.query
        .filter_by(user_id=user_id)
        .order_by(QuizAttempt.created_at.desc())
        .first()
    )


def normalize_quiz_mode(mode: str | None) -> str:
    mode_key = normalize_category(mode)
    return mode_key if mode_key in QUIZ_MODES else "test"


def get_all_questions() -> list[dict]:
    db_questions = [db_question_to_dict(q) for q in Question.query.all()]
    static_questions = list(questions)
    runtime_image_questions = build_runtime_image_questions(ANATOMY_CATEGORY)
    return merge_question_lists(db_questions, static_questions, runtime_image_questions)


def get_questions_by_ids(question_ids: list[str]) -> list[dict]:
    questions_by_id = {q["ID"]: q for q in get_all_questions()}
    selected = []

    for qid in question_ids:
        question = questions_by_id.get(qid)
        if question:
            selected.append(question)

    return selected


def get_runtime_image_database_rows() -> list[dict]:
    rows = []

    for question in build_runtime_image_questions(ANATOMY_CATEGORY):
        image_url = question.get("image_url") or ""
        relative_path = image_url.removeprefix("/static/") if image_url.startswith("/static/") else image_url
        rows.append({
            "qid": question.get("ID", ""),
            "filename": os.path.basename(relative_path),
            "relative_path": relative_path,
            "category": question.get("Category", ""),
        })

    return rows


def get_question_overview_rows() -> list[dict]:
    rows = []

    for question in get_all_questions():
        image_url = question.get("image_url") or ""
        correct_choice = get_effective_correct_choice(question)
        effective_answers = get_effective_answer_options(question)
        rows.append({
            "qid": question.get("ID", ""),
            "category": question.get("Category", ""),
            "text": question.get("Vraag", ""),
            "filename": os.path.basename(image_url) if image_url else "",
            "image_url": image_url,
            "answer_a": effective_answers["A"],
            "answer_b": effective_answers["B"],
            "answer_c": effective_answers["C"],
            "answer_d": effective_answers["D"],
            "correct_choice": correct_choice,
        })

    return sorted(rows, key=lambda row: extract_qid_number(row["qid"]) if row["qid"] else 0)


def get_admin_question_form_data(qid: str | None = None, image_url: str | None = None, category: str | None = None) -> dict:
    form_data = {
        "qid": "",
        "category": "",
        "text": STANDARD_IMAGE_PROMPT,
        "a": "",
        "b": "",
        "c": "",
        "d": "",
        "image_url": "",
        "existing_image_url": "",
        "correct_choice": "A",
    }

    db_question = None
    if qid:
        db_question = Question.query.filter_by(qid=qid).first()

    if db_question is None and image_url and category:
        db_question = Question.query.filter_by(image_url=image_url, category=category).first()

    if db_question:
        form_data.update({
            "qid": db_question.qid,
            "category": db_question.category,
            "text": db_question.text,
            "a": db_question.a,
            "b": db_question.b,
            "c": db_question.c,
            "d": db_question.d,
            "image_url": db_question.image_url or "",
            "existing_image_url": db_question.image_url or "",
            "correct_choice": db_question.correct if db_question.correct in {"A", "B", "C", "D"} else get_default_correct_choice(db_question.qid or db_question.image_url),
        })
        return form_data

    if qid or image_url:
        for question in get_all_questions():
            question_image_url = question.get("image_url") or ""
            if qid and question.get("ID") != qid:
                continue
            if image_url and question_image_url != image_url:
                continue
            if category and (question.get("Category") or "") != category:
                continue

            effective_answers = get_effective_answer_options(question)
            form_data.update({
                "qid": question.get("ID", ""),
                "category": question.get("Category", ""),
                "text": question.get("Vraag", STANDARD_IMAGE_PROMPT),
                "a": effective_answers["A"],
                "b": effective_answers["B"],
                "c": effective_answers["C"],
                "d": effective_answers["D"],
                "image_url": question_image_url,
                "existing_image_url": question_image_url,
                "correct_choice": get_effective_correct_choice(question),
            })
            break

    return form_data


def serialize_question_ids(question_ids: list[str]) -> str:
    return json.dumps(question_ids)


def parse_question_ids(raw_value: str | None) -> list[str]:
    try:
        parsed = json.loads(raw_value or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []

    if not isinstance(parsed, list):
        return []

    return [str(item).strip() for item in parsed if str(item).strip()]


def save_quiz_attempt(
    *,
    user_id: int,
    category: str,
    subgroup: str | None,
    quiz_mode: str,
    title: str,
    score: int,
    total_questions: int,
    question_ids: list[str],
) -> QuizAttempt:
    attempt = QuizAttempt(
        user_id=user_id,
        category=category,
        subgroup=subgroup,
        quiz_mode=normalize_quiz_mode(quiz_mode),
        title=title,
        score=score,
        total_questions=total_questions,
        question_ids_json=serialize_question_ids(question_ids),
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


def get_user_quiz_stats(user_id: int) -> tuple[int, int | None, int]:
    attempts = (
        QuizAttempt.query
        .filter_by(user_id=user_id)
        .order_by(QuizAttempt.created_at.desc())
        .all()
    )

    total_quizzes = len(attempts)
    if not attempts:
        return 0, None, 0

    total_answered = sum(attempt.total_questions for attempt in attempts)
    total_correct = sum(attempt.score for attempt in attempts)
    accuracy = round((total_correct / total_answered) * 100) if total_answered else None

    attempt_days = sorted({attempt.created_at.date() for attempt in attempts}, reverse=True)
    streak_days = 0
    current_day = datetime.utcnow().date()

    for day in attempt_days:
        if day == current_day:
            streak_days += 1
            current_day -= timedelta(days=1)
        elif streak_days == 0 and day == current_day - timedelta(days=1):
            streak_days += 1
            current_day = day - timedelta(days=1)
        else:
            break

    return total_quizzes, accuracy, streak_days


def build_attempt_summary(attempt: QuizAttempt) -> dict:
    percent = round((attempt.score / attempt.total_questions) * 100) if attempt.total_questions else 0
    return {
        "id": attempt.id,
        "title": localize_quiz_title(attempt.title),
        "quiz_mode": normalize_quiz_mode(getattr(attempt, "quiz_mode", "test")),
        "score": attempt.score,
        "total_questions": attempt.total_questions,
        "percent": percent,
        "created_at": attempt.created_at,
    }


def grade_quiz_submission(order: list[str], selected_by_id: dict[str, dict], form_data) -> tuple[list[dict], int]:
    results = []
    score = 0

    for qid in order:
        q = selected_by_id.get(qid)
        if not q:
            continue

        correct = normalize_correct(q)
        correct_texts = get_correct_answer_texts(q)
        user_text = (form_data.get(f"ans_{qid}") or "").strip()
        user_answers = [user_text] if user_text else []

        normalized_user = normalize_text_answer(user_text)
        normalized_correct_texts = {normalize_text_answer(text) for text in correct_texts if text}
        normalized_correct_keys = {normalize_text_answer(value) for value in correct}

        is_correct = bool(
            normalized_user and (
                normalized_user in normalized_correct_texts
                or normalized_user in normalized_correct_keys
            )
        )

        if is_correct:
            score += 1

        results.append({
            "ID": q["ID"],
            "question_key": get_question_key(q),
            "Category": q.get("Category", ""),
            "Vraag": q["Vraag"],
            "user": user_answers,
            "correct": correct,
            "correct_texts": correct_texts,
            "is_correct": is_correct,
            "options": {
                "A": q["A"],
                "B": q["B"],
                "C": q["C"],
                "D": q["D"],
            },
        })

    return results, score


def record_question_results(user_id: int, results: list[dict], subgroup: str | None) -> None:
    now = datetime.utcnow()
    keys = [result["question_key"] for result in results if result.get("question_key")]
    existing = {
        progress.question_key: progress
        for progress in QuestionProgress.query.filter(
            QuestionProgress.user_id == user_id,
            QuestionProgress.question_key.in_(keys),
        ).all()
    } if keys else {}

    for result in results:
        question_key = result.get("question_key")
        if not question_key:
            continue

        progress = existing.get(question_key)
        if progress is None:
            progress = QuestionProgress(user_id=user_id, question_key=question_key)
            db.session.add(progress)
            existing[question_key] = progress

        progress.subgroup = (
            normalize_anatomy_subgroup(subgroup)
            if subgroup
            else get_anatomy_subgroup_for_category(result.get("Category"))
        )
        progress.times_seen = (progress.times_seen or 0) + 1
        progress.last_answered_at = now
        progress.last_was_correct = bool(result["is_correct"])

        if result["is_correct"]:
            progress.times_correct = (progress.times_correct or 0) + 1
            progress.correct_streak = (progress.correct_streak or 0) + 1
            review_days = 2 if progress.correct_streak == 1 else 7 if progress.correct_streak == 2 else 21 if progress.correct_streak == 3 else 45
        else:
            progress.correct_streak = 0
            review_days = 1

        progress.next_review_at = now + timedelta(days=review_days)

    db.session.commit()


def clear_active_quiz_session() -> None:
    for key in ("order", "category", "subgroup", "question_limit", "quiz_mode", "quiz_pool", "quiz_run_id"):
        session.pop(key, None)


def render_quiz_page(
    *,
    display_title: str,
    selected: list[dict],
    order: list[str],
    back_url: str,
    quiz_mode: str,
    form_action: str | None = None,
):
    display_questions = [localize_question_for_display(q) for q in selected]
    questions_by_id = {q["ID"]: q for q in display_questions}
    correct_feedback_by_id = {
        qid: {
            "texts": get_correct_answer_texts(question),
            "keys": normalize_correct(question),
        }
        for qid, question in questions_by_id.items()
    }
    progress_by_key = get_user_progress_by_key(current_user.id)
    marked_by_id = {
        qid: bool(
            progress_by_key.get(get_question_key(question))
            and progress_by_key[get_question_key(question)].is_marked
        )
        for qid, question in questions_by_id.items()
    }
    return render_template(
        "quiz.html",
        category=localize_quiz_title(display_title),
        questions_by_id=questions_by_id,
        correct_feedback_by_id=correct_feedback_by_id,
        marked_by_id=marked_by_id,
        order=order,
        back_url=back_url,
        quiz_mode=normalize_quiz_mode(quiz_mode),
        quiz_run_id=session.get("quiz_run_id") or "quiz",
        form_action=form_action,
    )


def extract_qid_number(qid: str) -> int:
    match = re.search(r"(\d+)$", qid or "")
    return int(match.group(1)) if match else 0


def get_next_qid() -> str:
    all_ids = [q.get("ID", "") for q in questions]
    all_ids.extend(qid for (qid,) in db.session.query(Question.qid).all())
    next_number = max((extract_qid_number(qid) for qid in all_ids), default=0) + 1
    return f"Q{next_number:03d}"


def build_structure_title(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    cleaned = re.sub(r"[_-]+", " ", stem).strip()
    return cleaned or "Imported image question"


def build_upload_subdir(category: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_category(category)).strip("-")
    return slug or "general"


def save_question_image(file_storage, category: str) -> str:
    upload_root = app.config["UPLOAD_FOLDER"]
    subdir = build_upload_subdir(category)
    target_dir = os.path.join(upload_root, subdir)
    os.makedirs(target_dir, exist_ok=True)

    original_name = secure_filename(file_storage.filename or "")
    if not original_name:
        raise ValueError("Missing filename.")

    name, ext = os.path.splitext(original_name)
    candidate = original_name
    counter = 1

    while os.path.exists(os.path.join(target_dir, candidate)):
        candidate = f"{name}-{counter}{ext}"
        counter += 1

    file_storage.save(os.path.join(target_dir, candidate))
    return f"/static/uploads/questions/{subdir}/{candidate}"


def is_supported_image(filename: str) -> bool:
    return os.path.splitext(filename.lower())[1] in {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def list_existing_image_files(folder_path: str) -> list[str]:
    if not folder_path:
        return []

    absolute_folder = os.path.abspath(os.path.join(app.root_path, folder_path))
    static_root = os.path.abspath(app.static_folder)

    if not os.path.isdir(absolute_folder):
        raise ValueError("Folder does not exist.")

    if not absolute_folder.startswith(static_root):
        raise ValueError("Folder must be inside the static directory.")

    return [
        os.path.join(absolute_folder, name)
        for name in sorted(os.listdir(absolute_folder))
        if is_supported_image(name)
    ]


def list_existing_image_choices(folder_path: str = "static/images") -> list[dict[str, str]]:
    choices = []
    for path in list_existing_image_files(folder_path):
        filename = os.path.basename(path)
        relative_path = os.path.relpath(path, app.static_folder).replace(os.sep, "/")
        choices.append({
            "label": build_structure_title(filename),
            "filename": filename,
            "url": f"/static/{relative_path}",
        })
    return choices


def list_runtime_image_files(folder_path: str = "static/images") -> list[str]:
    if not folder_path:
        return []

    absolute_folder = os.path.abspath(os.path.join(app.root_path, folder_path))
    static_root = os.path.abspath(app.static_folder)

    if not os.path.isdir(absolute_folder):
        raise ValueError("Folder does not exist.")

    if not absolute_folder.startswith(static_root):
        raise ValueError("Folder must be inside the static directory.")

    image_paths = []
    for root, _, filenames in os.walk(absolute_folder):
        for filename in sorted(filenames):
            if is_supported_image(filename):
                image_paths.append(os.path.join(root, filename))

    return sorted(image_paths)


def build_runtime_image_questions(category: str) -> list[dict]:
    if normalize_category(category) != normalize_category(AUTO_IMAGE_CATEGORY):
        return []

    image_paths = list_runtime_image_files("static/images")
    generated_questions = []

    for index, path in enumerate(image_paths, start=1):
        filename = os.path.basename(path)
        relative_path = os.path.relpath(path, app.static_folder).replace(os.sep, "/")
        override = IMAGE_QUESTION_OVERRIDES.get(filename, {})
        answer_a = (override.get("A") or "").strip() or build_structure_title(filename)
        answer_b = (override.get("B") or "").strip()
        answer_c = (override.get("C") or "").strip()
        answer_d = (override.get("D") or "").strip()
        correct_choice = (override.get("Correct") or "").strip().upper()
        if correct_choice not in {"A", "B", "C", "D"}:
            correct_choice = "A"
        generated_questions.append({
            "ID": f"IMG{index:03d}",
            "Category": (override.get("Category") or get_runtime_image_category_for_path(path)).strip() or get_runtime_image_category_for_path(path),
            "Vraag": (override.get("Vraag") or STANDARD_IMAGE_PROMPT).strip() or STANDARD_IMAGE_PROMPT,
            "structure_title": build_structure_title(filename),
            "A": answer_a,
            "B": answer_b,
            "C": answer_c,
            "D": answer_d,
            "Correct": correct_choice,
            "image_url": f"/static/{relative_path}",
            "compact_options": False,
        })

    return generated_questions


def parse_answer_key(raw_value: str) -> dict[str, str]:
    answer_key = {}

    for line in (raw_value or "").splitlines():
        line = line.strip()
        if not line:
            continue

        if "=" not in line:
            continue

        filename, answer = line.split("=", 1)
        answer = (answer or "").strip().upper()
        if answer in {"A", "B", "C", "D"}:
            answer_key[secure_filename(filename.strip())] = answer

    return answer_key


def admin_required():
    if not current_user.is_authenticated:
        return redirect(url_for("login", next=request.path))
    if not user_has_admin_access(current_user):
        abort(403)
    return None


def upsert_question_answer(
    *,
    qid: str,
    category: str,
    text: str,
    image_url: str | None,
    answer_text: str | None = None,
    answer_values: list[str] | None = None,
    correct_choice: str | None = None,
) -> Question:
    values = list((answer_values or [])[:4])
    while len(values) < 4:
        values.append("")

    if answer_text is not None and not values[0]:
        values[0] = answer_text

    normalized_choice = (correct_choice or "").strip().upper()
    if normalized_choice not in {"A", "B", "C", "D"}:
        normalized_choice = "A" if values[0] else "T"

    question = None

    if qid and not qid.startswith("IMG"):
        question = Question.query.filter_by(qid=qid).first()

    if question is None and image_url:
        question = Question.query.filter_by(category=category, image_url=image_url).first()

    if question is None:
        question = Question(
            qid=get_next_qid(),
            category=category,
            text=text or STANDARD_IMAGE_PROMPT,
            image_url=image_url,
            a=values[0],
            b=values[1],
            c=values[2],
            d=values[3],
            correct=normalized_choice,
        )
        db.session.add(question)
    else:
        question.category = category
        question.text = text or question.text or STANDARD_IMAGE_PROMPT
        question.image_url = image_url
        question.a = values[0]
        question.b = values[1]
        question.c = values[2]
        question.d = values[3]
        question.correct = normalized_choice

    db.session.commit()
    return question


def safe_redirect_target(target: str, fallback_endpoint: str = "home") -> str:
    if not target:
        return url_for(fallback_endpoint)

    parsed = urlparse(target)

    if parsed.scheme or parsed.netloc:
        return url_for(fallback_endpoint)

    if not target.startswith("/"):
        return url_for(fallback_endpoint)

    return target


# -------------------------
# Routes
# -------------------------

@app.route("/language/<language_code>")
def set_language(language_code):
    language_code = (language_code or "").strip().lower()
    if language_code in SUPPORTED_LANGUAGES:
        session["language"] = language_code

    target = safe_redirect_target(request.args.get("next"), "home").rstrip("?")
    separator = "&" if "?" in target else "?"
    target = f"{target}{separator}_lang=1"
    return redirect(target)


@app.route("/", methods=["GET", "POST"])
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))

    categories = get_categories()
    category_cards = build_home_category_cards(categories)
    total_quizzes, accuracy, streak_days = get_user_quiz_stats(current_user.id)
    last_attempt = get_last_quiz_attempt(current_user.id)
    learning_dashboard = get_learning_dashboard(current_user.id)
    active_quiz = get_active_quiz_summary()

    if request.method == "POST":
        category = (request.form.get("category") or "").strip()

        if category not in categories:
            return render_template(
                "home.html",
                categories=categories,
                category_cards=category_cards,
                error="Invalid category.",
                total_quizzes=total_quizzes,
                accuracy=accuracy,
                streak_days=streak_days,
                last_attempt=last_attempt,
                learning_dashboard=learning_dashboard,
                active_quiz=active_quiz,
            )

        if normalize_category(category) == normalize_category(ANATOMY_CATEGORY):
            return redirect(url_for("anatomy_sections"))

        return redirect(url_for("quiz", category=category))

    return render_template(
        "home.html",
        categories=categories,
        category_cards=category_cards,
        error=None,
        total_quizzes=total_quizzes,
        accuracy=accuracy,
        streak_days=streak_days,
        last_attempt=last_attempt,
        learning_dashboard=learning_dashboard,
        active_quiz=active_quiz,
    )


@app.route("/anatomy")
@login_required
def anatomy_sections():
    subgroup_cards = get_anatomy_subgroup_cards()
    return render_template("anatomy_sections.html", subgroup_cards=subgroup_cards)


@app.route("/previous-tests")
@login_required
def previous_tests():
    attempts = (
        QuizAttempt.query
        .filter_by(user_id=current_user.id)
        .order_by(QuizAttempt.created_at.desc())
        .all()
    )
    attempt_summaries = [build_attempt_summary(attempt) for attempt in attempts]
    return render_template("previous_tests.html", attempts=attempt_summaries)


@app.route("/stocks")
@login_required
def stocks():
    return render_template("stocks.html")


@app.route("/anatomy/<subgroup>")
@login_required
def anatomy_subgroup_setup(subgroup):
    subgroup_key = normalize_anatomy_subgroup(subgroup)
    subgroup_meta = ANATOMY_SUBGROUPS.get(subgroup_key)
    if not subgroup_meta:
        return redirect(url_for("anatomy_sections"))

    selected = get_questions_for_anatomy_subgroup(subgroup_key)
    pool_counts = get_quiz_pool_counts(selected, current_user.id)
    selected_pool = normalize_quiz_pool(request.args.get("pool"))
    available_count = pool_counts[selected_pool]
    suggested_count = get_question_limit(request.args.get("count"), available_count)

    return render_template(
        "anatomy_quiz_setup.html",
        subgroup_key=subgroup_key,
        subgroup_label=subgroup_meta["label"],
        subgroup_description=subgroup_meta["description"],
        available_count=available_count,
        max_quiz_questions=MAX_QUIZ_QUESTIONS,
        suggested_count=suggested_count,
        quiz_modes=QUIZ_MODES,
        selected_mode=normalize_quiz_mode(request.args.get("mode")),
        quiz_pools=QUIZ_POOLS,
        pool_counts=pool_counts,
        selected_pool=selected_pool,
    )


@app.route("/questions/mark", methods=["POST"])
@login_required
def toggle_question_mark():
    payload = request.get_json(silent=True) or {}
    question_key = (payload.get("question_key") or "").strip()
    valid_keys = {get_question_key(question) for question in get_all_anatomy_questions()}
    if not question_key or question_key not in valid_keys:
        return jsonify({"error": "Invalid question."}), 400

    progress = QuestionProgress.query.filter_by(
        user_id=current_user.id,
        question_key=question_key,
    ).first()
    if progress is None:
        progress = QuestionProgress(
            user_id=current_user.id,
            question_key=question_key,
            is_marked=True,
        )
        db.session.add(progress)
    else:
        progress.is_marked = not progress.is_marked

    db.session.commit()
    return jsonify({"marked": progress.is_marked})


@app.route("/previous-tests/<int:attempt_id>/retake", methods=["GET", "POST"])
@login_required
def retake_previous_test(attempt_id):
    attempt = QuizAttempt.query.filter_by(id=attempt_id, user_id=current_user.id).first()
    if not attempt:
        abort(404)

    order = parse_question_ids(attempt.question_ids_json)
    if not order:
        return redirect(url_for("previous_tests"))

    selected = get_questions_by_ids(order)
    selected_by_id = {q["ID"]: q for q in selected}
    available_ids = set(selected_by_id)
    order = [qid for qid in order if qid in available_ids]

    if not order:
        return redirect(url_for("previous_tests"))

    if request.method == "POST":
        results, score = grade_quiz_submission(order, selected_by_id, request.form)
        quiz_mode = normalize_quiz_mode(getattr(attempt, "quiz_mode", "test"))
        new_attempt = save_quiz_attempt(
            user_id=current_user.id,
            category=attempt.category,
            subgroup=attempt.subgroup,
            quiz_mode=quiz_mode,
            title=attempt.title,
            score=score,
            total_questions=len(order),
            question_ids=order,
        )
        record_question_results(current_user.id, results, attempt.subgroup)
        clear_active_quiz_session()
        return render_template(
            "result.html",
            category=localize_quiz_title(attempt.title),
            score=score,
            total=len(order),
            results=localize_quiz_results(results),
            back_url=url_for("previous_tests"),
            attempt_id=new_attempt.id,
        )

    session["order"] = order
    session["category"] = attempt.category
    session["subgroup"] = attempt.subgroup
    session["question_limit"] = len(order)
    session["quiz_mode"] = normalize_quiz_mode(getattr(attempt, "quiz_mode", "test"))
    session["quiz_pool"] = "all"
    session["quiz_run_id"] = os.urandom(8).hex()

    return render_quiz_page(
        display_title=attempt.title,
        selected=selected,
        order=order,
        back_url=url_for("previous_tests"),
        quiz_mode=normalize_quiz_mode(getattr(attempt, "quiz_mode", "test")),
        form_action=url_for("retake_previous_test", attempt_id=attempt.id),
    )


@app.route("/quiz/<category>", methods=["GET", "POST"])
@login_required
def quiz(category):
    categories = get_categories()

    if category not in categories:
        return redirect(url_for("home"))

    subgroup = None
    question_limit = None
    quiz_mode = normalize_quiz_mode(request.args.get("mode"))
    quiz_pool = normalize_quiz_pool(request.args.get("pool"))
    if normalize_category(category) == normalize_category(ANATOMY_CATEGORY):
        subgroup = normalize_anatomy_subgroup(request.args.get("subgroup"))
        if subgroup not in ANATOMY_SUBGROUPS:
            return redirect(url_for("anatomy_sections"))

    all_selected = get_questions_for_category(category, subgroup)
    selected = (
        filter_questions_for_pool(all_selected, current_user.id, quiz_pool)
        if request.method == "GET" and subgroup
        else all_selected
    )
    display_title = get_quiz_display_title(category, subgroup)
    back_url = url_for("anatomy_sections") if subgroup else url_for("home")

    if not selected:
        total_quizzes, accuracy, streak_days = get_user_quiz_stats(current_user.id)
        template_name = "anatomy_sections.html" if subgroup else "home.html"
        template_kwargs = {
            "error": "No questions found.",
        }
        if subgroup:
            template_kwargs["subgroup_cards"] = get_anatomy_subgroup_cards()
        else:
            template_kwargs.update({
                "categories": categories,
                "total_quizzes": total_quizzes,
                "accuracy": accuracy,
                "streak_days": streak_days,
            })
        return render_template(template_name, **template_kwargs)

    if request.method == "GET":
        preserve_current_quiz = (
            request.args.get("_lang") == "1" or request.args.get("resume") == "1"
        ) and (
            session.get("category") == category
            and session.get("subgroup") == subgroup
            and bool(session.get("order"))
        )
        if preserve_current_quiz:
            available_ids = {question["ID"] for question in selected}
            order = [qid for qid in session["order"] if qid in available_ids]
            if order:
                return render_quiz_page(
                    display_title=display_title,
                    selected=selected,
                    order=order,
                    back_url=back_url,
                    quiz_mode=normalize_quiz_mode(session.get("quiz_mode")),
                )

        if subgroup:
            question_limit = get_question_limit(request.args.get("count"), len(selected))
            if not question_limit:
                return redirect(url_for("anatomy_subgroup_setup", subgroup=subgroup))
        else:
            question_limit = len(selected)

        order = [q["ID"] for q in selected]
        random.shuffle(order)
        order = order[:question_limit]

        session["order"] = order
        session["category"] = category
        session["subgroup"] = subgroup
        session["question_limit"] = question_limit
        session["quiz_mode"] = quiz_mode
        session["quiz_pool"] = quiz_pool
        session["quiz_run_id"] = os.urandom(8).hex()

        return render_quiz_page(
            display_title=display_title,
            selected=selected,
            order=order,
            back_url=back_url,
            quiz_mode=quiz_mode,
        )

    order = session.get("order", [])
    quiz_mode = normalize_quiz_mode(session.get("quiz_mode"))
    selected_by_id = {q["ID"]: q for q in selected}
    results, score = grade_quiz_submission(order, selected_by_id, request.form)

    attempt = save_quiz_attempt(
        user_id=current_user.id,
        category=category,
        subgroup=subgroup,
        quiz_mode=quiz_mode,
        title=display_title,
        score=score,
        total_questions=len(order),
        question_ids=order,
    )
    record_question_results(current_user.id, results, subgroup)
    clear_active_quiz_session()

    return render_template(
        "result.html",
        category=localize_quiz_title(display_title),
        score=score,
        total=len(order),
        results=localize_quiz_results(results),
        back_url=back_url,
        attempt_id=attempt.id,
    )


@app.route("/admin")
def admin_home():
    admin_redirect = admin_required()
    if admin_redirect:
        return admin_redirect

    question_count = db.session.query(func.count(Question.id)).scalar() or 0
    return render_template("admin_home.html", question_count=question_count)


@app.route("/admin/database")
def admin_database():
    admin_redirect = admin_required()
    if admin_redirect:
        return admin_redirect

    rows = get_question_overview_rows()
    anatomy_rows = [row for row in rows if is_anatomy_category_name(row.get("category"))]
    physics_rows = [row for row in rows if normalize_category(row.get("category")) == "physics"]
    return render_template(
        "admin_database.html",
        anatomy_rows=anatomy_rows,
        physics_rows=physics_rows,
        question_count=len(rows),
    )


@app.route("/admin/questions/save-answer", methods=["POST"])
@login_required
def admin_save_question_answer():
    if not user_has_admin_access(current_user):
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    qid = (payload.get("qid") or "").strip()
    category = (payload.get("category") or "").strip()
    text = (payload.get("text") or "").strip()
    image_url = (payload.get("image_url") or "").strip() or None
    answer_text = (payload.get("answer") or "").strip()
    answer_values = [
        (value or "").strip()
        for value in (payload.get("answers") or [])
    ]
    correct_choice = (payload.get("correct_choice") or "").strip().upper()

    if not category:
        return jsonify({"error": "Category is required."}), 400
    if not answer_text and not any(answer_values):
        return jsonify({"error": "At least one answer is required."}), 400
    if any(answer_values) and correct_choice not in {"A", "B", "C", "D"}:
        return jsonify({"error": "Please choose the correct answer."}), 400

    try:
        question = upsert_question_answer(
            qid=qid,
            category=category,
            text=text or STANDARD_IMAGE_PROMPT,
            image_url=image_url,
            answer_text=answer_text,
            answer_values=answer_values,
            correct_choice=correct_choice,
        )
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Could not save answer: {exc}"}), 500

    return jsonify({
        "ok": True,
        "qid": question.qid,
        "answers": [question.a, question.b, question.c, question.d],
        "correct_choice": question.correct,
    })


@app.route("/admin/questions/new", methods=["GET", "POST"])
def admin_new_question():
    admin_redirect = admin_required()
    if admin_redirect:
        return admin_redirect

    error = None
    success = None
    image_choices = list_existing_image_choices()
    form_data = get_admin_question_form_data(
        qid=(request.args.get("qid") or "").strip() or None,
        image_url=(request.args.get("image_url") or "").strip() or None,
        category=(request.args.get("category") or "").strip() or None,
    )

    if request.method == "POST":
        form_data = {
            "qid": (request.form.get("qid") or "").strip(),
            "category": (request.form.get("category") or "").strip(),
            "text": (request.form.get("text") or "").strip(),
            "a": (request.form.get("a") or "").strip(),
            "b": (request.form.get("b") or "").strip(),
            "c": (request.form.get("c") or "").strip(),
            "d": (request.form.get("d") or "").strip(),
            "image_url": (request.form.get("image_url") or "").strip(),
            "existing_image_url": (request.form.get("existing_image_url") or "").strip(),
            "correct_choice": (request.form.get("correct_choice") or "").strip().upper(),
        }
        category = form_data["category"]
        text = form_data["text"]
        correct_choice = form_data["correct_choice"]

        option_map = {
            "a": form_data["a"],
            "b": form_data["b"],
            "c": form_data["c"],
            "d": form_data["d"],
        }
        option_map_upper = {key.upper(): value for key, value in option_map.items()}

        submitted_qid = form_data["qid"]
        image_url = form_data["image_url"] or form_data["existing_image_url"] or None
        existing_question = None

        if submitted_qid and not submitted_qid.startswith("IMG"):
            existing_question = Question.query.filter_by(qid=submitted_qid).first()
        if existing_question is None and image_url:
            existing_question = Question.query.filter_by(category=category, image_url=image_url).first()

        if not text and image_url:
            text = STANDARD_IMAGE_PROMPT
            form_data["text"] = text

        if not category or not text:
            error = "Category and question text are required."
        elif not option_map["a"]:
            error = "Please provide the correct answer."
        elif correct_choice not in {"A", "B", "C", "D"}:
            error = "Please choose the correct answer option."
        elif not option_map_upper.get(correct_choice):
            error = "The selected correct answer must have text."
        else:
            if existing_question is None:
                existing_question = Question(
                    qid=get_next_qid(),
                    category=category,
                    text=text,
                    a=option_map["a"],
                    b=option_map["b"],
                    c=option_map["c"],
                    d=option_map["d"],
                    correct=correct_choice,
                    image_url=image_url,
                )
                db.session.add(existing_question)
            else:
                existing_question.category = category
                existing_question.text = text
                existing_question.a = option_map["a"]
                existing_question.b = option_map["b"]
                existing_question.c = option_map["c"]
                existing_question.d = option_map["d"]
                existing_question.correct = correct_choice
                existing_question.image_url = image_url

            db.session.commit()
            success = f"Question {existing_question.qid} saved."
            form_data = get_admin_question_form_data(qid=existing_question.qid)

    return render_template(
        "admin_new_question.html",
        error=error,
        success=success,
        image_choices=image_choices,
        form_data=form_data,
        standard_image_prompt=STANDARD_IMAGE_PROMPT,
    )


@app.route("/admin/questions/import-images", methods=["GET", "POST"])
def admin_import_images():
    admin_redirect = admin_required()
    if admin_redirect:
        return admin_redirect

    error = None
    success = None
    imported_questions = []

    if request.method == "POST":
        category = (request.form.get("category") or "").strip()
        answer_key = parse_answer_key(request.form.get("answer_key") or "")
        files = [file for file in request.files.getlist("images") if file and file.filename]
        existing_folder = (request.form.get("existing_folder") or "").strip()

        if not category:
            error = "Category is required."
        else:
            try:
                if files:
                    for file in files:
                        filename = secure_filename(file.filename or "")
                        if not filename or not is_supported_image(filename):
                            continue

                        image_url = save_question_image(file, category)
                        if Question.query.filter_by(category=category, image_url=image_url).first():
                            continue
                        correct = answer_key.get(filename, "A")
                        qid = get_next_qid()
                        question = Question(
                            qid=qid,
                            category=category,
                            text=STANDARD_IMAGE_PROMPT,
                            a=build_structure_title(filename),
                            b="",
                            c="",
                            d="",
                            correct="T",
                            image_url=image_url,
                        )
                        db.session.add(question)
                        imported_questions.append({
                            "qid": qid,
                            "filename": filename,
                            "correct": correct,
                            "image_url": image_url,
                        })
                else:
                    image_paths = list_existing_image_files(existing_folder or "static/images")

                    for path in image_paths:
                        filename = os.path.basename(path)
                        relative_path = os.path.relpath(path, app.static_folder).replace(os.sep, "/")
                        image_url = f"/static/{relative_path}"
                        if Question.query.filter_by(category=category, image_url=image_url).first():
                            continue
                        correct = answer_key.get(filename, "A")
                        qid = get_next_qid()
                        question = Question(
                            qid=qid,
                            category=category,
                            text=STANDARD_IMAGE_PROMPT,
                            a=build_structure_title(filename),
                            b="",
                            c="",
                            d="",
                            correct="T",
                            image_url=image_url,
                        )
                        db.session.add(question)
                        imported_questions.append({
                            "qid": qid,
                            "filename": filename,
                            "correct": correct,
                            "image_url": image_url,
                        })

                if not imported_questions:
                    raise ValueError("No supported image files were found.")

                db.session.commit()

                defaulted = sum(1 for item in imported_questions if item["filename"] not in answer_key)
                success = (
                    f"Imported {len(imported_questions)} image question(s). "
                    f"{defaulted} used the default correct answer A."
                )
            except Exception as exc:
                db.session.rollback()
                error = f"Import failed: {exc}"

    return render_template(
        "admin_import_images.html",
        error=error,
        success=success,
        imported_questions=imported_questions,
    )


# -------------------------
# Auth
# -------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    error = None
    next_url = safe_redirect_target(request.args.get("next"), "home")

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            error = "Incorrect email or password."
        else:
            sync_user_admin_flag(user)
            login_user(user)
            return redirect(next_url)

    return render_template("login.html", error=error, next=next_url)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    error = None
    form_data = {
        "name": "",
        "university": "",
        "email": "",
    }

    if request.method == "POST":
        form_data = {
            "name": (request.form.get("name") or "").strip(),
            "university": (request.form.get("university") or "").strip(),
            "email": (request.form.get("email") or "").strip().lower(),
        }
        name = form_data["name"]
        university = form_data["university"]
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not name:
            error = "Name is required."
        elif not university:
            error = "University is required."
        elif not email:
            error = "Email is required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif User.query.filter_by(email=email).first():
            error = "An account with that email already exists."
        else:
            user = User(
                name=name,
                university=university,
                email=email,
                is_admin=is_admin_email(email),
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("home"))

    return render_template("register.html", error=error, form_data=form_data)


@app.route("/logout")
@login_required
def logout():
    language = get_current_language()
    logout_user()
    session.clear()
    session["language"] = language
    return redirect(url_for("login"))


# -------------------------
# Main
# -------------------------

with app.app_context():
    db.create_all()
    ensure_quiz_attempt_schema()
    ensure_user_profile_schema()
    enforce_single_admin_account()

if __name__ == "__main__":
    app.run(debug=True)
