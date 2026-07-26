import os
import random
import re
import json
from datetime import datetime, timedelta
from functools import lru_cache
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
from whitenoise import WhiteNoise
from werkzeug.utils import secure_filename

from core_radiology import get_core_section, get_core_sections, load_core_section
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
database_uri = build_database_uri()
app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["UPLOAD_FOLDER"] = os.path.join(app.static_folder, "uploads", "questions")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(days=7)
app.config["STATIC_ASSET_VERSION"] = str(
    int(os.path.getmtime(os.path.join(app.static_folder, "style.css")))
)

if database_uri.startswith("postgresql+psycopg://"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 3,
        "max_overflow": 2,
        "pool_timeout": 10,
        "connect_args": {"connect_timeout": 10},
    }

if os.environ.get("RENDER") or os.environ.get("FLASK_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True

app.wsgi_app = WhiteNoise(
    app.wsgi_app,
    root=app.static_folder,
    prefix="static/",
    max_age=7 * 24 * 60 * 60,
    autorefresh=not bool(os.environ.get("RENDER")),
)

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
STUDY_FORMATS = {"mcq", "flashcard"}
FLASHCARD_RATINGS = {
    "very_difficult": {
        "label": "Very difficult",
        "review_days": 0,
    },
    "difficult": {
        "label": "Difficult",
        "review_days": 1,
    },
    "easy": {
        "label": "Easy",
        "review_days": 4,
    },
    "very_easy": {
        "label": "Very easy",
        "review_days": 10,
    },
}
DISABLED_CATEGORIES = {"physics"}


# -------------------------
# Login setup
# -------------------------

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@app.before_request
def route_core_domain():
    hostname = request.host.split(":", 1)[0].lower()
    if hostname == "core.bymed.be" and request.path == "/":
        return redirect(url_for("core_home"))
    return None


@app.get("/health")
def health():
    return {"status": "ok"}


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
        flashcard_rating = normalize_flashcard_rating(result.get("flashcard_rating"))
        if flashcard_rating:
            localized["user"] = [{
                "very_difficult": "Zeer moeilijk",
                "difficult": "Moeilijk",
                "easy": "Gemakkelijk",
                "very_easy": "Zeer gemakkelijk",
            }[flashcard_rating]]
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
        "asset_version": app.config["STATIC_ASSET_VERSION"],
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
    promoted = (
        User.query
        .filter(
            func.lower(func.trim(User.email)) == ADMIN_EMAIL,
            User.is_admin.is_not(True),
        )
        .update({User.is_admin: True}, synchronize_session=False)
    )
    demoted = (
        User.query
        .filter(
            func.lower(func.trim(User.email)) != ADMIN_EMAIL,
            User.is_admin.is_(True),
        )
        .update({User.is_admin: False}, synchronize_session=False)
    )

    if promoted or demoted:
        db.session.commit()


def ensure_quiz_attempt_schema():
    inspector = inspect(db.engine)
    if "quiz_attempt" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("quiz_attempt")}
    statements = []
    if "quiz_mode" not in column_names:
        statements.append("ALTER TABLE quiz_attempt ADD COLUMN quiz_mode VARCHAR(20) NOT NULL DEFAULT 'test'")
    if "study_format" not in column_names:
        statements.append("ALTER TABLE quiz_attempt ADD COLUMN study_format VARCHAR(20) NOT NULL DEFAULT 'mcq'")
    if "results_json" not in column_names:
        statements.append("ALTER TABLE quiz_attempt ADD COLUMN results_json TEXT")
    if "duration_seconds" not in column_names:
        statements.append("ALTER TABLE quiz_attempt ADD COLUMN duration_seconds INTEGER")

    for statement in statements:
        db.session.execute(text(statement))

    if statements:
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
    if "daily_question_goal" not in column_names:
        statements.append('ALTER TABLE "user" ADD COLUMN daily_question_goal INTEGER NOT NULL DEFAULT 20')

    for statement in statements:
        db.session.execute(text(statement))

    if statements:
        db.session.commit()


def ensure_question_progress_schema():
    inspector = inspect(db.engine)
    if "question_progress" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("question_progress")}
    statements = []
    if "flashcard_rating" not in column_names:
        statements.append("ALTER TABLE question_progress ADD COLUMN flashcard_rating VARCHAR(24)")
    if "flashcard_times_seen" not in column_names:
        statements.append("ALTER TABLE question_progress ADD COLUMN flashcard_times_seen INTEGER NOT NULL DEFAULT 0")
    if "flashcard_rated_at" not in column_names:
        statements.append("ALTER TABLE question_progress ADD COLUMN flashcard_rated_at TIMESTAMP")

    for statement in statements:
        db.session.execute(text(statement))

    if statements:
        db.session.commit()


def ensure_performance_indexes():
    statements = (
        "CREATE INDEX IF NOT EXISTS ix_question_category ON question (category)",
        "CREATE INDEX IF NOT EXISTS ix_quiz_attempt_user_created "
        "ON quiz_attempt (user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_quiz_attempt_user_format_created "
        "ON quiz_attempt (user_id, study_format, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_quiz_attempt_user_category_format_created "
        "ON quiz_attempt (user_id, category, study_format, created_at DESC)",
    )
    for statement in statements:
        db.session.execute(text(statement))
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


def get_anatomy_subgroup_cards(
    anatomy_questions: list[dict] | None = None,
) -> list[dict]:
    cards = []
    if anatomy_questions is None:
        anatomy_questions = get_all_anatomy_questions()

    for key, meta in ANATOMY_SUBGROUPS.items():
        count = (
            len(anatomy_questions)
            if key == "mixed"
            else sum(
                1 for question in anatomy_questions
                if get_anatomy_subgroup_for_category(question.get("Category")) == key
            )
        )
        cards.append({
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "count": count,
        })

    return cards


def get_question_key(question: dict) -> str:
    return (
        question.get("question_key")
        or question.get("image_url")
        or question.get("ID")
        or ""
    ).strip()


def normalize_quiz_pool(pool: str | None) -> str:
    pool_key = normalize_category(pool)
    return pool_key if pool_key in QUIZ_POOLS else "all"


def normalize_study_format(study_format: str | None) -> str:
    value = normalize_category(study_format)
    return value if value in STUDY_FORMATS else "mcq"


def normalize_flashcard_rating(rating: str | None) -> str | None:
    value = (rating or "").strip().lower().replace("-", "_").replace(" ", "_")
    return value if value in FLASHCARD_RATINGS else None


def get_user_progress_by_key(user_id: int) -> dict[str, QuestionProgress]:
    return {
        progress.question_key: progress
        for progress in QuestionProgress.query.filter_by(user_id=user_id).all()
    }


def filter_questions_for_pool(
    question_list: list[dict],
    user_id: int,
    pool: str | None,
    progress_by_key: dict[str, QuestionProgress] | None = None,
) -> list[dict]:
    pool_key = normalize_quiz_pool(pool)
    if pool_key == "all":
        return list(question_list)

    if progress_by_key is None:
        progress_by_key = get_user_progress_by_key(user_id)
    now = datetime.utcnow()
    filtered = []

    for question in question_list:
        progress = progress_by_key.get(get_question_key(question))
        total_seen = (
            (progress.times_seen or 0) + (progress.flashcard_times_seen or 0)
            if progress else 0
        )
        if pool_key == "unseen" and total_seen == 0:
            filtered.append(question)
        elif pool_key == "incorrect" and progress and progress.times_seen > progress.times_correct:
            filtered.append(question)
        elif pool_key == "marked" and progress and progress.is_marked:
            filtered.append(question)
        elif (
            pool_key == "due"
            and progress
            and total_seen > 0
            and progress.next_review_at
            and progress.next_review_at <= now
        ):
            filtered.append(question)

    return filtered


def filter_questions_for_flashcard_rating(
    question_list: list[dict],
    user_id: int,
    rating: str | None,
    progress_by_key: dict[str, QuestionProgress] | None = None,
) -> list[dict]:
    rating_key = normalize_flashcard_rating(rating)
    if not rating_key:
        return list(question_list)
    if progress_by_key is None:
        progress_by_key = get_user_progress_by_key(user_id)
    return [
        question for question in question_list
        if progress_by_key.get(get_question_key(question))
        and progress_by_key[get_question_key(question)].flashcard_rating == rating_key
    ]


def get_flashcard_rating_counts(
    question_list: list[dict],
    user_id: int,
    progress_by_key: dict[str, QuestionProgress] | None = None,
) -> dict[str, int]:
    if progress_by_key is None:
        progress_by_key = get_user_progress_by_key(user_id)
    counts = {rating: 0 for rating in FLASHCARD_RATINGS}
    for question in question_list:
        progress = progress_by_key.get(get_question_key(question))
        if progress and progress.flashcard_rating in counts:
            counts[progress.flashcard_rating] += 1
    return counts


def get_quiz_pool_counts(
    question_list: list[dict],
    user_id: int,
    progress_by_key: dict[str, QuestionProgress] | None = None,
) -> dict[str, int]:
    if progress_by_key is None:
        progress_by_key = get_user_progress_by_key(user_id)
    counts = {pool_key: 0 for pool_key in QUIZ_POOLS}
    counts["all"] = len(question_list)
    now = datetime.utcnow()

    for question in question_list:
        progress = progress_by_key.get(get_question_key(question))
        total_seen = (
            (progress.times_seen or 0) + (progress.flashcard_times_seen or 0)
            if progress else 0
        )
        if total_seen == 0:
            counts["unseen"] += 1
        if progress and progress.times_seen > progress.times_correct:
            counts["incorrect"] += 1
        if progress and progress.is_marked:
            counts["marked"] += 1
        if (
            progress
            and total_seen > 0
            and progress.next_review_at
            and progress.next_review_at <= now
        ):
            counts["due"] += 1

    return counts


def get_learning_dashboard(
    user_id: int,
    all_questions: list[dict] | None = None,
    progress_by_key: dict[str, QuestionProgress] | None = None,
) -> dict:
    if all_questions is None:
        all_questions = get_all_anatomy_questions()
    if progress_by_key is None:
        progress_by_key = get_user_progress_by_key(user_id)
    current_question_keys = {get_question_key(question) for question in all_questions}
    now = datetime.utcnow()
    seen = [
        progress for key, progress in progress_by_key.items()
        if key in current_question_keys
        and ((progress.times_seen or 0) + (progress.flashcard_times_seen or 0)) > 0
    ]
    due = [
        progress for progress in seen
        if progress.next_review_at and progress.next_review_at <= now
    ]
    mastered = [
        progress for progress in seen
        if (
            (
                progress.times_seen > 0
                and progress.correct_streak >= 3
                and progress.times_correct / progress.times_seen >= 0.8
            )
            or progress.flashcard_rating == "very_easy"
        )
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
            and (
                (progress_by_key[get_question_key(question)].times_seen or 0)
                + (progress_by_key[get_question_key(question)].flashcard_times_seen or 0)
            ) > 0
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
    study_format = normalize_study_format(session.get("study_format"))
    resume_endpoint = "flashcards" if study_format == "flashcard" else "quiz"
    return {
        "title": title,
        "count": len(order),
        "mode": normalize_quiz_mode(session.get("quiz_mode")),
        "pool": normalize_quiz_pool(session.get("quiz_pool")),
        "study_format": study_format,
        "subgroup_label": subgroup_meta["label"] if subgroup_meta else ANATOMY_CATEGORY,
        "resume_url": url_for(
            resume_endpoint,
            category=category,
            subgroup=subgroup,
            resume="1",
        ),
    }


def get_active_core_session() -> dict | None:
    order = session.get("order") or []
    if (
        not order
        or normalize_category(session.get("category")) != "core radiology"
        or normalize_study_format(session.get("study_format")) != "flashcard"
    ):
        return None
    section = get_core_section(session.get("subgroup"))
    if not section:
        return None
    return {
        "count": len(order),
        "section": section,
        "resume_url": url_for(
            "core_study",
            section_key=section["key"],
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


def build_home_category_cards(
    categories: list[str],
    anatomy_questions: list[dict] | None = None,
) -> list[dict]:
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
            "count": (
                len(anatomy_questions)
                if anatomy_questions is not None
                else get_category_question_count(category)
            ),
            "difficulty": difficulty_by_category.get(normalize_category(category), "Mixed Difficulty"),
            "description": f"Practice MCQs in {category}",
            "available": True,
        })
    return cards


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
    results: list[dict] | None = None,
    duration_seconds: int | None = None,
    study_format: str = "mcq",
) -> QuizAttempt:
    attempt = QuizAttempt(
        user_id=user_id,
        category=category,
        subgroup=subgroup,
        quiz_mode=normalize_quiz_mode(quiz_mode),
        study_format=normalize_study_format(study_format),
        title=title,
        score=score,
        total_questions=total_questions,
        question_ids_json=serialize_question_ids(question_ids),
        results_json=json.dumps(results, ensure_ascii=True) if results else None,
        duration_seconds=duration_seconds,
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


def get_attempt_stat_rows(user_id: int):
    return (
        db.session.query(
            QuizAttempt.id,
            QuizAttempt.title,
            QuizAttempt.created_at,
            QuizAttempt.study_format,
            QuizAttempt.score,
            QuizAttempt.total_questions,
        )
        .filter(QuizAttempt.user_id == user_id)
        .order_by(QuizAttempt.created_at.desc())
        .all()
    )


def calculate_quiz_stats(attempts) -> tuple[int, int | None, int]:
    total_quizzes = len(attempts)
    if not attempts:
        return 0, None, 0

    mcq_attempts = [
        attempt for attempt in attempts
        if normalize_study_format(getattr(attempt, "study_format", "mcq")) == "mcq"
    ]
    total_answered = sum(attempt.total_questions for attempt in mcq_attempts)
    total_correct = sum(attempt.score for attempt in mcq_attempts)
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


def get_user_quiz_stats(user_id: int) -> tuple[int, int | None, int]:
    return calculate_quiz_stats(get_attempt_stat_rows(user_id))


def get_home_attempt_data(user_id: int) -> tuple[int, int | None, int, object | None, dict]:
    attempts = get_attempt_stat_rows(user_id)
    total_quizzes, accuracy, streak_days = calculate_quiz_stats(attempts)
    mcq_attempts = [
        attempt for attempt in attempts
        if normalize_study_format(attempt.study_format) == "mcq"
    ]
    trend = [
        {
            "percent": round(attempt.score / attempt.total_questions * 100)
            if attempt.total_questions else 0,
            "label": attempt.created_at.strftime("%d/%m"),
        }
        for attempt in reversed(mcq_attempts[:8])
    ]
    today = datetime.utcnow().date()
    completed_today = sum(
        attempt.total_questions
        for attempt in attempts
        if attempt.created_at.date() == today
    )
    goal = max(5, min(int(current_user.daily_question_goal or 20), 100))
    activity = {
        "trend": trend,
        "completed_today": completed_today,
        "daily_goal": goal,
        "goal_percent": min(round(completed_today / goal * 100), 100),
    }
    return (
        total_quizzes,
        accuracy,
        streak_days,
        attempts[0] if attempts else None,
        activity,
    )


def build_attempt_summary(attempt: QuizAttempt) -> dict:
    percent = round((attempt.score / attempt.total_questions) * 100) if attempt.total_questions else 0
    rating_counts = {rating: 0 for rating in FLASHCARD_RATINGS}
    for result in get_attempt_results(attempt):
        rating = normalize_flashcard_rating(result.get("flashcard_rating"))
        if rating:
            rating_counts[rating] += 1
    return {
        "id": attempt.id,
        "title": localize_quiz_title(attempt.title),
        "category": attempt.category,
        "quiz_mode": normalize_quiz_mode(getattr(attempt, "quiz_mode", "test")),
        "study_format": normalize_study_format(getattr(attempt, "study_format", "mcq")),
        "score": attempt.score,
        "total_questions": attempt.total_questions,
        "percent": percent,
        "duration_seconds": getattr(attempt, "duration_seconds", None),
        "rating_counts": rating_counts,
        "created_at": attempt.created_at,
    }


def get_attempt_results(attempt: QuizAttempt) -> list[dict]:
    try:
        parsed = json.loads(getattr(attempt, "results_json", None) or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def get_submission_duration(form_data) -> int | None:
    try:
        duration = int(form_data.get("duration_seconds") or 0)
    except (TypeError, ValueError):
        return None
    return min(max(duration, 0), 24 * 60 * 60) or None


def get_dashboard_activity(user_id: int) -> dict:
    attempts = (
        QuizAttempt.query
        .filter_by(user_id=user_id, study_format="mcq")
        .order_by(QuizAttempt.created_at.desc())
        .limit(8)
        .all()
    )
    trend = [
        {
            "percent": round(attempt.score / attempt.total_questions * 100)
            if attempt.total_questions else 0,
            "label": attempt.created_at.strftime("%d/%m"),
        }
        for attempt in reversed(attempts)
    ]
    today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
    completed_today = (
        db.session.query(func.coalesce(func.sum(QuizAttempt.total_questions), 0))
        .filter(
            QuizAttempt.user_id == user_id,
            QuizAttempt.created_at >= today_start,
        )
        .scalar()
        or 0
    )
    goal = max(5, min(int(current_user.daily_question_goal or 20), 100))
    return {
        "trend": trend,
        "completed_today": completed_today,
        "daily_goal": goal,
        "goal_percent": min(round(completed_today / goal * 100), 100),
    }


def get_core_dashboard(user_id: int) -> dict:
    sections = get_core_sections()
    all_questions = [
        question
        for section in sections
        for question in load_core_section(section["key"])
    ]
    progress_by_key = get_user_progress_by_key(user_id)
    now = datetime.utcnow()
    section_rows = []

    for section in sections:
        questions = load_core_section(section["key"])
        progress_rows = [
            progress_by_key[get_question_key(question)]
            for question in questions
            if get_question_key(question) in progress_by_key
        ]
        seen = [
            progress for progress in progress_rows
            if (progress.flashcard_times_seen or 0) > 0
        ]
        section_rows.append({
            **section,
            "seen": len(seen),
            "coverage": round(len(seen) / len(questions) * 100) if questions else 0,
            "mastered": sum(1 for progress in seen if progress.flashcard_rating == "very_easy"),
        })

    relevant_progress = [
        progress_by_key[get_question_key(question)]
        for question in all_questions
        if get_question_key(question) in progress_by_key
    ]
    seen_progress = [
        progress for progress in relevant_progress
        if (progress.flashcard_times_seen or 0) > 0
    ]
    latest_attempt_row = (
        db.session.query(
            QuizAttempt,
            func.count(QuizAttempt.id).over().label("session_count"),
        )
        .filter_by(user_id=user_id, category="CORE Radiology", study_format="flashcard")
        .order_by(QuizAttempt.created_at.desc())
        .first()
    )
    last_attempt = latest_attempt_row[0] if latest_attempt_row else None
    session_count = latest_attempt_row.session_count if latest_attempt_row else 0
    rating_counts = {rating: 0 for rating in FLASHCARD_RATINGS}
    for progress in relevant_progress:
        if progress.flashcard_rating in rating_counts:
            rating_counts[progress.flashcard_rating] += 1

    return {
        "sections": section_rows,
        "total": len(all_questions),
        "seen": len(seen_progress),
        "coverage": round(len(seen_progress) / len(all_questions) * 100) if all_questions else 0,
        "mastered": sum(
            1 for progress in seen_progress
            if progress.flashcard_rating == "very_easy"
        ),
        "due": sum(
            1 for progress in seen_progress
            if progress.next_review_at and progress.next_review_at <= now
        ),
        "rating_counts": rating_counts,
        "session_count": session_count,
        "last_attempt": build_attempt_summary(last_attempt) if last_attempt else None,
    }


def get_core_pool_counts(
    question_list: list[dict],
    user_id: int,
    progress_by_key: dict[str, QuestionProgress] | None = None,
) -> dict[str, int]:
    if progress_by_key is None:
        progress_by_key = get_user_progress_by_key(user_id)
    counts = {
        "all": len(question_list),
        "unseen": len(filter_questions_for_pool(
            question_list, user_id, "unseen", progress_by_key
        )),
        "due": len(filter_questions_for_pool(
            question_list, user_id, "due", progress_by_key
        )),
    }
    counts.update(get_flashcard_rating_counts(question_list, user_id, progress_by_key))
    return counts


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


def record_flashcard_rating(
    user_id: int,
    question: dict,
    rating: str,
    subgroup: str | None,
) -> QuestionProgress:
    rating_key = normalize_flashcard_rating(rating)
    if not rating_key:
        raise ValueError("Invalid flashcard rating.")

    question_key = get_question_key(question)
    progress = QuestionProgress.query.filter_by(
        user_id=user_id,
        question_key=question_key,
    ).first()
    if progress is None:
        progress = QuestionProgress(user_id=user_id, question_key=question_key)
        db.session.add(progress)

    now = datetime.utcnow()
    if normalize_category(question.get("Category")) == "core radiology":
        progress.subgroup = (subgroup or question.get("core_section") or "").strip()
    else:
        actual_subgroup = get_anatomy_subgroup_for_category(question.get("Category"))
        progress.subgroup = (
            actual_subgroup
            if normalize_anatomy_subgroup(subgroup) == "mixed"
            else normalize_anatomy_subgroup(subgroup) if subgroup else actual_subgroup
        )
    progress.flashcard_rating = rating_key
    progress.flashcard_times_seen = (progress.flashcard_times_seen or 0) + 1
    progress.flashcard_rated_at = now
    progress.last_answered_at = now
    review_days = FLASHCARD_RATINGS[rating_key]["review_days"]
    progress.next_review_at = (
        now + timedelta(minutes=10)
        if rating_key == "very_difficult"
        else now + timedelta(days=review_days)
    )
    db.session.commit()
    return progress


def build_flashcard_results(
    order: list[str],
    selected_by_id: dict[str, dict],
    ratings_by_id: dict[str, str],
) -> tuple[list[dict], int, dict[str, int]]:
    results = []
    counts = {rating: 0 for rating in FLASHCARD_RATINGS}
    score = 0
    for qid in order:
        question = selected_by_id.get(qid)
        rating = normalize_flashcard_rating(ratings_by_id.get(qid))
        if not question or not rating:
            continue
        counts[rating] += 1
        is_confident = rating in {"easy", "very_easy"}
        if is_confident:
            score += 1
        results.append({
            "ID": qid,
            "question_key": get_question_key(question),
            "Category": question.get("Category", ""),
            "Vraag": question["Vraag"],
            "user": [FLASHCARD_RATINGS[rating]["label"]],
            "correct": normalize_correct(question),
            "correct_texts": get_correct_answer_texts(question),
            "is_correct": is_confident,
            "flashcard_rating": rating,
            "image_url": question.get("image_url"),
            "answer_image_url": question.get("answer_image_url"),
            "case_label": question.get("case_label"),
            "options": {
                "A": question["A"],
                "B": question["B"],
                "C": question["C"],
                "D": question["D"],
            },
        })
    return results, score, counts


def clear_active_quiz_session() -> None:
    for key in (
        "order", "category", "subgroup", "question_limit", "quiz_mode",
        "quiz_pool", "quiz_run_id", "study_format", "flashcard_rating_filter",
    ):
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
        switch_to_flashcard_url=url_for(
            "flashcards",
            category=session.get("category") or ANATOMY_CATEGORY,
            subgroup=session.get("subgroup"),
            resume="1",
        ),
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
    clear_runtime_question_caches()
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


@lru_cache(maxsize=4)
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


@lru_cache(maxsize=4)
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


def clear_runtime_question_caches() -> None:
    list_runtime_image_files.cache_clear()
    build_runtime_image_questions.cache_clear()


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

    anatomy_questions = get_all_anatomy_questions()
    subgroup_cards = get_anatomy_subgroup_cards(anatomy_questions)
    progress_by_key = get_user_progress_by_key(current_user.id)
    categories = get_categories()
    category_cards = build_home_category_cards(categories, anatomy_questions)
    (
        total_quizzes,
        accuracy,
        streak_days,
        last_attempt,
        dashboard_activity,
    ) = get_home_attempt_data(current_user.id)
    learning_dashboard = get_learning_dashboard(
        current_user.id,
        anatomy_questions,
        progress_by_key,
    )
    active_quiz = get_active_quiz_summary()

    if request.method == "POST":
        category = (request.form.get("category") or "").strip()

        if category not in categories:
            return render_template(
                "home.html",
                categories=categories,
                category_cards=category_cards,
                subgroup_cards=subgroup_cards,
                error="Invalid category.",
                total_quizzes=total_quizzes,
                accuracy=accuracy,
                streak_days=streak_days,
                last_attempt=last_attempt,
                learning_dashboard=learning_dashboard,
                dashboard_activity=dashboard_activity,
                active_quiz=active_quiz,
            )

        if normalize_category(category) == normalize_category(ANATOMY_CATEGORY):
            return redirect(url_for("anatomy_sections"))

        return redirect(url_for("quiz", category=category))

    return render_template(
        "home.html",
        categories=categories,
        category_cards=category_cards,
        subgroup_cards=subgroup_cards,
        error=None,
        total_quizzes=total_quizzes,
        accuracy=accuracy,
        streak_days=streak_days,
        last_attempt=last_attempt,
        learning_dashboard=learning_dashboard,
        dashboard_activity=dashboard_activity,
        active_quiz=active_quiz,
    )


@app.route("/anatomy")
@login_required
def anatomy_sections():
    subgroup_cards = get_anatomy_subgroup_cards()
    return render_template("anatomy_sections.html", subgroup_cards=subgroup_cards)


@app.route("/core")
@login_required
def core_home():
    return render_template(
        "core_home.html",
        core_dashboard=get_core_dashboard(current_user.id),
        dashboard_activity=get_dashboard_activity(current_user.id),
        active_core_session=get_active_core_session(),
    )


@app.route("/core/history")
@login_required
def core_history():
    attempts = (
        QuizAttempt.query
        .filter_by(
            user_id=current_user.id,
            category="CORE Radiology",
            study_format="flashcard",
        )
        .order_by(QuizAttempt.created_at.desc())
        .all()
    )
    return render_template(
        "previous_tests.html",
        attempts=[build_attempt_summary(attempt) for attempt in attempts],
        product="core",
        home_url=url_for("core_home"),
    )


@app.route("/core/<section_key>")
@login_required
def core_section_setup(section_key):
    section = get_core_section(section_key)
    if not section:
        return redirect(url_for("core_home"))
    questions = load_core_section(section_key)
    if not questions:
        return render_template("core_empty_section.html", section=section)

    progress_by_key = get_user_progress_by_key(current_user.id)
    pool_counts = get_core_pool_counts(questions, current_user.id, progress_by_key)
    requested_pool = (
        normalize_flashcard_rating(request.args.get("pool"))
        or normalize_category(request.args.get("pool"))
    )
    selected_pool = requested_pool if requested_pool in pool_counts else "all"
    available_count = pool_counts[selected_pool]
    return render_template(
        "core_section_setup.html",
        section=section,
        pool_counts=pool_counts,
        selected_pool=selected_pool,
        available_count=available_count,
        suggested_count=get_question_limit(request.args.get("count"), available_count),
        max_questions=MAX_QUIZ_QUESTIONS,
        ratings=FLASHCARD_RATINGS,
    )


@app.route("/core/rate", methods=["POST"])
@login_required
def rate_core_flashcard():
    payload = request.get_json(silent=True) or {}
    section_key = (payload.get("subgroup") or "").strip()
    qid = (payload.get("qid") or "").strip()
    rating = normalize_flashcard_rating(payload.get("rating"))
    questions = load_core_section(section_key)
    question = next((item for item in questions if item["ID"] == qid), None)
    if not question or not rating:
        return jsonify({"error": "Invalid CORE flashcard rating."}), 400

    progress = record_flashcard_rating(
        current_user.id,
        question,
        rating,
        section_key,
    )
    return jsonify({
        "ok": True,
        "qid": qid,
        "rating": progress.flashcard_rating,
        "counts": get_flashcard_rating_counts(questions, current_user.id),
    })


@app.route("/core/<section_key>/study", methods=["GET", "POST"])
@login_required
def core_study(section_key):
    section = get_core_section(section_key)
    all_questions = load_core_section(section_key)
    if not section or not all_questions:
        return redirect(url_for("core_home"))

    if request.method == "POST":
        order = [qid for qid in session.get("order", []) if qid]
        selected_by_id = {question["ID"]: question for question in all_questions}
        try:
            ratings_by_id = json.loads(request.form.get("ratings_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            ratings_by_id = {}
        if not isinstance(ratings_by_id, dict):
            ratings_by_id = {}

        results, score, session_rating_counts = build_flashcard_results(
            order,
            selected_by_id,
            ratings_by_id,
        )
        if not order or len(results) != len(order):
            return redirect(url_for(
                "core_study",
                section_key=section_key,
                resume="1",
            ))

        attempt = save_quiz_attempt(
            user_id=current_user.id,
            category="CORE Radiology",
            subgroup=section_key,
            quiz_mode="test",
            study_format="flashcard",
            title=f"CORE Radiology - {section['label']}",
            score=score,
            total_questions=len(order),
            question_ids=order,
            results=results,
            duration_seconds=get_submission_duration(request.form),
        )
        bucket_counts = get_flashcard_rating_counts(all_questions, current_user.id)
        retest_urls = {
            rating: url_for(
                "core_study",
                section_key=section_key,
                pool=rating,
                count=min(count, MAX_QUIZ_QUESTIONS),
            )
            for rating, count in bucket_counts.items()
            if count
        }
        clear_active_quiz_session()
        return render_template(
            "flashcard_result.html",
            category=f"CORE Radiology - {section['label']}",
            total=len(order),
            rating_counts=bucket_counts,
            session_rating_counts=session_rating_counts,
            ratings=FLASHCARD_RATINGS,
            attempt_id=attempt.id,
            subgroup=section_key,
            product="core",
            home_url=url_for("core_home"),
            new_session_url=url_for("core_section_setup", section_key=section_key),
            history_url=url_for("core_history"),
            retest_urls=retest_urls,
        )

    pool = (
        normalize_flashcard_rating(request.args.get("pool"))
        or normalize_category(request.args.get("pool"))
    )
    progress_by_key = get_user_progress_by_key(current_user.id)
    if pool in FLASHCARD_RATINGS:
        selected = filter_questions_for_flashcard_rating(
            all_questions,
            current_user.id,
            pool,
            progress_by_key,
        )
    elif pool in {"due", "unseen"}:
        selected = filter_questions_for_pool(
            all_questions,
            current_user.id,
            pool,
            progress_by_key,
        )
    else:
        pool = "all"
        selected = list(all_questions)
    if not selected:
        return redirect(url_for("core_section_setup", section_key=section_key))

    preserve_current = (
        request.args.get("resume") == "1" or request.args.get("_lang") == "1"
    ) and (
        session.get("category") == "CORE Radiology"
        and session.get("subgroup") == section_key
        and bool(session.get("order"))
    )
    if preserve_current:
        available_ids = {question["ID"] for question in all_questions}
        order = [qid for qid in session["order"] if qid in available_ids]
    else:
        question_limit = get_question_limit(request.args.get("count"), len(selected))
        if not question_limit:
            return redirect(url_for("core_section_setup", section_key=section_key))
        order = [question["ID"] for question in selected]
        random.shuffle(order)
        order = order[:question_limit]
        session["order"] = order
        session["category"] = "CORE Radiology"
        session["subgroup"] = section_key
        session["question_limit"] = question_limit
        session["quiz_pool"] = pool
        session["quiz_run_id"] = os.urandom(8).hex()

    session["study_format"] = "flashcard"
    questions_by_id = {question["ID"]: question for question in all_questions}
    current_ratings = {
        qid: (
            progress_by_key[get_question_key(questions_by_id[qid])].flashcard_rating
            if get_question_key(questions_by_id[qid]) in progress_by_key
            else None
        )
        for qid in order
    }
    return render_template(
        "flashcards.html",
        category=f"CORE Radiology - {section['label']}",
        raw_category="CORE Radiology",
        subgroup=section_key,
        questions_by_id=questions_by_id,
        correct_answers_by_id={
            qid: get_correct_answer_texts(questions_by_id[qid]) for qid in order
        },
        order=order,
        current_ratings=current_ratings,
        ratings=FLASHCARD_RATINGS,
        rating_counts=get_flashcard_rating_counts(
            all_questions,
            current_user.id,
            progress_by_key,
        ),
        back_url=url_for("core_section_setup", section_key=section_key),
        quiz_run_id=session.get("quiz_run_id") or "core-flashcards",
        switch_to_mcq_url=None,
        rate_url=url_for("rate_core_flashcard"),
        home_url=url_for("core_home"),
        product="core",
        product_name="CORE Radiology",
        product_label=section["label"],
    )


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


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    message = None
    error = None

    if request.method == "POST":
        action = (request.form.get("action") or "profile").strip()
        if action == "password":
            current_password = request.form.get("current_password") or ""
            new_password = request.form.get("new_password") or ""
            confirm_password = request.form.get("confirm_password") or ""
            if not current_user.check_password(current_password):
                error = "Het huidige wachtwoord is niet correct." if get_current_language() == "nl" else "The current password is incorrect."
            elif len(new_password) < 8:
                error = "Het nieuwe wachtwoord moet minimaal 8 tekens bevatten." if get_current_language() == "nl" else "The new password must contain at least 8 characters."
            elif new_password != confirm_password:
                error = "De nieuwe wachtwoorden komen niet overeen." if get_current_language() == "nl" else "The new passwords do not match."
            else:
                current_user.set_password(new_password)
                db.session.commit()
                message = "Wachtwoord veilig bijgewerkt." if get_current_language() == "nl" else "Password updated securely."
        else:
            name = (request.form.get("name") or "").strip()
            university = (request.form.get("university") or "").strip()
            try:
                daily_goal = int(request.form.get("daily_question_goal") or 20)
            except ValueError:
                daily_goal = 20

            if not name or not university:
                error = "Naam en universiteit zijn verplicht." if get_current_language() == "nl" else "Name and university are required."
            elif len(name) > 255 or len(university) > 255:
                error = "Naam en universiteit mogen maximaal 255 tekens bevatten." if get_current_language() == "nl" else "Name and university may contain at most 255 characters."
            elif not 5 <= daily_goal <= 100:
                error = "Kies een dagelijks doel tussen 5 en 100 vragen." if get_current_language() == "nl" else "Choose a daily goal between 5 and 100 questions."
            else:
                current_user.name = name
                current_user.university = university
                current_user.daily_question_goal = daily_goal
                db.session.commit()
                message = "Profiel bijgewerkt." if get_current_language() == "nl" else "Profile updated."

    total_quizzes, accuracy, streak_days = get_user_quiz_stats(current_user.id)
    return render_template(
        "profile.html",
        message=message,
        error=error,
        total_quizzes=total_quizzes,
        accuracy=accuracy,
        streak_days=streak_days,
    )


@app.route("/previous-tests/<int:attempt_id>/report")
@login_required
def attempt_report(attempt_id):
    attempt = QuizAttempt.query.filter_by(id=attempt_id, user_id=current_user.id).first()
    if not attempt:
        abort(404)
    summary = build_attempt_summary(attempt)
    return render_template(
        "attempt_report.html",
        attempt=attempt,
        summary=summary,
        results=localize_quiz_results(get_attempt_results(attempt)),
    )


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
    progress_by_key = get_user_progress_by_key(current_user.id)
    pool_counts = get_quiz_pool_counts(selected, current_user.id, progress_by_key)
    flashcard_rating_counts = get_flashcard_rating_counts(
        selected,
        current_user.id,
        progress_by_key,
    )
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
        selected_format=normalize_study_format(request.args.get("format")),
        flashcard_ratings=FLASHCARD_RATINGS,
        flashcard_rating_counts=flashcard_rating_counts,
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


@app.route("/flashcards/rate", methods=["POST"])
@login_required
def rate_flashcard():
    payload = request.get_json(silent=True) or {}
    qid = (payload.get("qid") or "").strip()
    rating = normalize_flashcard_rating(payload.get("rating"))
    subgroup = normalize_anatomy_subgroup(payload.get("subgroup"))
    questions_found = get_questions_by_ids([qid])
    question = questions_found[0] if questions_found else None
    if not question or not is_anatomy_category_name(question.get("Category")) or not rating:
        return jsonify({"error": "Invalid flashcard rating."}), 400

    progress = record_flashcard_rating(current_user.id, question, rating, subgroup)
    subgroup_questions = get_questions_for_anatomy_subgroup(subgroup)
    return jsonify({
        "ok": True,
        "qid": qid,
        "rating": progress.flashcard_rating,
        "counts": get_flashcard_rating_counts(subgroup_questions, current_user.id),
    })


@app.route("/flashcards/<category>", methods=["GET", "POST"])
@login_required
def flashcards(category):
    if category not in get_categories() or normalize_category(category) != normalize_category(ANATOMY_CATEGORY):
        return redirect(url_for("home"))

    subgroup = normalize_anatomy_subgroup(
        request.args.get("subgroup") or request.form.get("subgroup") or session.get("subgroup")
    )
    if subgroup not in ANATOMY_SUBGROUPS:
        return redirect(url_for("anatomy_sections"))

    all_selected = get_questions_for_category(category, subgroup)
    display_title = get_quiz_display_title(category, subgroup)
    back_url = url_for("anatomy_sections")

    if request.method == "POST":
        order = [qid for qid in session.get("order", []) if qid]
        selected_by_id = {question["ID"]: question for question in all_selected}
        try:
            submitted_ratings = json.loads(request.form.get("ratings_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            submitted_ratings = {}
        if not isinstance(submitted_ratings, dict):
            submitted_ratings = {}

        results, score, rating_counts = build_flashcard_results(
            order,
            selected_by_id,
            submitted_ratings,
        )
        if not order or len(results) != len(order):
            return redirect(url_for(
                "flashcards",
                category=category,
                subgroup=subgroup,
                resume="1",
            ))

        attempt = save_quiz_attempt(
            user_id=current_user.id,
            category=category,
            subgroup=subgroup,
            quiz_mode="test",
            study_format="flashcard",
            title=display_title,
            score=score,
            total_questions=len(order),
            question_ids=order,
            results=results,
            duration_seconds=get_submission_duration(request.form),
        )
        bucket_counts = get_flashcard_rating_counts(all_selected, current_user.id)
        clear_active_quiz_session()
        return render_template(
            "flashcard_result.html",
            category=localize_quiz_title(display_title),
            total=len(order),
            rating_counts=bucket_counts,
            session_rating_counts=rating_counts,
            ratings=FLASHCARD_RATINGS,
            attempt_id=attempt.id,
            subgroup=subgroup,
            product="anatomy",
            home_url=url_for("home"),
            new_session_url=url_for(
                "anatomy_subgroup_setup",
                subgroup=subgroup,
                format="flashcard",
            ),
            history_url=url_for("previous_tests"),
            retest_urls={
                rating: url_for(
                    "flashcards",
                    category="Anatomy",
                    subgroup=subgroup,
                    rating=rating,
                    count=min(count, MAX_QUIZ_QUESTIONS),
                )
                for rating, count in bucket_counts.items()
                if count
            },
        )

    rating_filter = normalize_flashcard_rating(request.args.get("rating"))
    quiz_pool = normalize_quiz_pool(request.args.get("pool"))
    progress_by_key = get_user_progress_by_key(current_user.id)
    selected = (
        filter_questions_for_flashcard_rating(
            all_selected,
            current_user.id,
            rating_filter,
            progress_by_key,
        )
        if rating_filter
        else filter_questions_for_pool(
            all_selected,
            current_user.id,
            quiz_pool,
            progress_by_key,
        )
    )
    if not selected:
        return redirect(url_for(
            "anatomy_subgroup_setup",
            subgroup=subgroup,
            format="flashcard",
        ))

    preserve_current = (
        request.args.get("resume") == "1" or request.args.get("_lang") == "1"
    ) and (
        session.get("category") == category
        and session.get("subgroup") == subgroup
        and bool(session.get("order"))
    )
    if preserve_current:
        available_ids = {question["ID"] for question in all_selected}
        order = [qid for qid in session["order"] if qid in available_ids]
    else:
        question_limit = get_question_limit(request.args.get("count"), len(selected))
        if not question_limit:
            return redirect(url_for(
                "anatomy_subgroup_setup",
                subgroup=subgroup,
                format="flashcard",
            ))
        order = [question["ID"] for question in selected]
        random.shuffle(order)
        order = order[:question_limit]
        session["order"] = order
        session["category"] = category
        session["subgroup"] = subgroup
        session["question_limit"] = question_limit
        session["quiz_pool"] = quiz_pool
        session["quiz_run_id"] = os.urandom(8).hex()

    session["study_format"] = "flashcard"
    session["flashcard_rating_filter"] = rating_filter
    display_questions = [localize_question_for_display(question) for question in all_selected]
    questions_by_id = {question["ID"]: question for question in display_questions}
    current_ratings = {
        qid: (
            progress_by_key.get(get_question_key(questions_by_id[qid])).flashcard_rating
            if progress_by_key.get(get_question_key(questions_by_id[qid]))
            else None
        )
        for qid in order
        if qid in questions_by_id
    }
    return render_template(
        "flashcards.html",
        category=localize_quiz_title(display_title),
        raw_category=category,
        subgroup=subgroup,
        questions_by_id=questions_by_id,
        correct_answers_by_id={
            qid: get_correct_answer_texts(questions_by_id[qid])
            for qid in order
            if qid in questions_by_id
        },
        order=order,
        current_ratings=current_ratings,
        ratings=FLASHCARD_RATINGS,
        rating_counts=get_flashcard_rating_counts(
            all_selected,
            current_user.id,
            progress_by_key,
        ),
        back_url=back_url,
        quiz_run_id=session.get("quiz_run_id") or "flashcards",
        switch_to_mcq_url=url_for(
            "quiz",
            category=category,
            subgroup=subgroup,
            resume="1",
        ),
        rate_url=url_for("rate_flashcard"),
        home_url=url_for("home"),
        product="anatomy",
        product_name="Rady",
        product_label="Anki Flashcards",
    )


@app.route("/previous-tests/<int:attempt_id>/retake", methods=["GET", "POST"])
@login_required
def retake_previous_test(attempt_id):
    attempt = QuizAttempt.query.filter_by(id=attempt_id, user_id=current_user.id).first()
    if not attempt:
        abort(404)

    order = parse_question_ids(attempt.question_ids_json)
    if not order:
        return redirect(url_for("previous_tests"))

    if normalize_study_format(getattr(attempt, "study_format", "mcq")) == "flashcard":
        session["order"] = order
        session["category"] = attempt.category
        session["subgroup"] = attempt.subgroup
        session["question_limit"] = len(order)
        session["quiz_pool"] = "all"
        session["study_format"] = "flashcard"
        session["quiz_run_id"] = os.urandom(8).hex()
        if normalize_category(attempt.category) == "core radiology":
            return redirect(url_for(
                "core_study",
                section_key=attempt.subgroup,
                resume="1",
            ))
        return redirect(url_for(
            "flashcards",
            category=attempt.category,
            subgroup=attempt.subgroup,
            resume="1",
        ))

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
            results=results,
            duration_seconds=get_submission_duration(request.form),
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
    session["study_format"] = "mcq"
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
    if request.method == "GET" and normalize_study_format(request.args.get("format")) == "flashcard":
        flashcard_args = request.args.to_dict(flat=True)
        flashcard_args.pop("format", None)
        return redirect(url_for("flashcards", category=category, **flashcard_args))

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
                session["study_format"] = "mcq"
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
        session["study_format"] = "mcq"
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
        results=results,
        duration_seconds=get_submission_duration(request.form),
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
    search_query = (request.args.get("q") or "").strip()
    category_filter = (request.args.get("category") or "").strip()
    correct_filter = (request.args.get("correct") or "").strip().upper()
    table_filter = (request.args.get("table") or "all").strip().lower()
    available_categories = sorted({
        row.get("category", "")
        for row in rows
        if row.get("category")
    })

    if search_query:
        needle = normalize_text_answer(search_query)
        rows = [
            row for row in rows
            if needle in normalize_text_answer(" ".join(
                str(row.get(field) or "")
                for field in (
                    "qid", "category", "text", "answer_a", "answer_b",
                    "answer_c", "answer_d", "filename",
                )
            ))
        ]
    if category_filter:
        rows = [
            row for row in rows
            if normalize_category(row.get("category")) == normalize_category(category_filter)
        ]
    if correct_filter in {"A", "B", "C", "D"}:
        rows = [
            row for row in rows
            if (row.get("correct_choice") or "").upper() == correct_filter
        ]

    anatomy_rows = [row for row in rows if is_anatomy_category_name(row.get("category"))]
    physics_rows = [row for row in rows if normalize_category(row.get("category")) == "physics"]
    if table_filter == "anatomy":
        physics_rows = []
    elif table_filter == "physics":
        anatomy_rows = []

    return render_template(
        "admin_database.html",
        anatomy_rows=anatomy_rows,
        physics_rows=physics_rows,
        question_count=len(anatomy_rows) + len(physics_rows),
        available_categories=available_categories,
        filters={
            "q": search_query,
            "category": category_filter,
            "correct": correct_filter,
            "table": table_filter,
        },
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

def initialize_database_schema():
    with app.app_context():
        db.create_all()
        ensure_quiz_attempt_schema()
        ensure_user_profile_schema()
        ensure_question_progress_schema()
        ensure_performance_indexes()
        enforce_single_admin_account()
        db.engine.dispose()


# Render already has the production schema. Avoid blocking every web deploy on
# DDL locks before Gunicorn can serve its health check.
if not os.environ.get("RENDER") or os.environ.get("RUN_STARTUP_MIGRATIONS") == "1":
    initialize_database_schema()

if __name__ == "__main__":
    app.run(debug=True)
