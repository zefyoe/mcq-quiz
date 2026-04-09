import os
import random
import re
from datetime import timedelta
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request, session, redirect, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import func
from werkzeug.utils import secure_filename

from models import db, Question, User
from questions_data import questions


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


def normalize_text_answer(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def normalize_category(s: str) -> str:
    return (s or "").strip().lower()


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


def is_placeholder_option(value: str) -> bool:
    return (value or "").strip().upper() in {"A", "B", "C", "D", "OPTION A", "OPTION B", "OPTION C", "OPTION D"}


def use_compact_answer_buttons(q: dict) -> bool:
    if not q.get("image_url"):
        return False

    option_values = [q.get("A"), q.get("B"), q.get("C"), q.get("D")]
    return all(is_placeholder_option(value or "") for value in option_values)


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


def get_categories() -> list[str]:
    cats = set()

    for (c,) in db.session.query(Question.category).distinct().all():
        if c:
            cats.add(c.strip())

    cats |= {q["Category"].strip() for q in questions if q.get("Category")}

    if build_runtime_image_questions(AUTO_IMAGE_CATEGORY):
        cats.add(AUTO_IMAGE_CATEGORY)

    return sorted(cats)


def get_questions_for_category(category: str) -> list[dict]:
    cat_norm = normalize_category(category)

    db_qs = (
        Question.query
        .filter(func.lower(func.trim(Question.category)) == cat_norm)
        .all()
    )

    db_questions = [db_question_to_dict(q) for q in db_qs]
    runtime_image_questions = build_runtime_image_questions(category)
    static_questions = [q for q in questions if normalize_category(q.get("Category")) == cat_norm]

    return merge_question_lists(db_questions, runtime_image_questions, static_questions)


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


def build_runtime_image_questions(category: str) -> list[dict]:
    if normalize_category(category) != normalize_category(AUTO_IMAGE_CATEGORY):
        return []

    image_paths = list_existing_image_files("static/images")
    generated_questions = []

    for index, path in enumerate(image_paths, start=1):
        filename = os.path.basename(path)
        relative_path = os.path.relpath(path, app.static_folder).replace(os.sep, "/")
        generated_questions.append({
            "ID": f"IMG{index:03d}",
            "Category": AUTO_IMAGE_CATEGORY,
            "Vraag": STANDARD_IMAGE_PROMPT,
            "structure_title": build_structure_title(filename),
            "A": "A",
            "B": "B",
            "C": "C",
            "D": "D",
            "Correct": "A",
            "image_url": f"/static/{relative_path}",
            "compact_options": True,
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
    answer_text: str,
) -> Question:
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
            a=answer_text,
            b="",
            c="",
            d="",
            correct="T",
        )
        db.session.add(question)
    else:
        question.category = category
        question.text = text or question.text or STANDARD_IMAGE_PROMPT
        question.image_url = image_url
        question.a = answer_text
        question.b = ""
        question.c = ""
        question.d = ""
        question.correct = "T"

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

@app.route("/", methods=["GET", "POST"])
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))

    categories = get_categories()

    # ✅ FIXED: no fake stats anymore
    total_quizzes = 0
    accuracy = None
    streak_days = 0

    if request.method == "POST":
        category = (request.form.get("category") or "").strip()

        if category not in categories:
            return render_template(
                "home.html",
                categories=categories,
                error="Invalid category.",
                total_quizzes=total_quizzes,
                accuracy=accuracy,
                streak_days=streak_days,
            )

        return redirect(url_for("quiz", category=category))

    return render_template(
        "home.html",
        categories=categories,
        error=None,
        total_quizzes=total_quizzes,
        accuracy=accuracy,
        streak_days=streak_days,
    )


@app.route("/quiz/<category>", methods=["GET", "POST"])
@login_required
def quiz(category):
    categories = get_categories()

    if category not in categories:
        return redirect(url_for("home"))

    selected = get_questions_for_category(category)

    if not selected:
        return render_template(
            "home.html",
            categories=categories,
            error="No questions found.",
            total_quizzes=0,
            accuracy=None,
            streak_days=0,
        )

    if request.method == "GET":
        order = [q["ID"] for q in selected]
        random.shuffle(order)

        session["order"] = order
        session["category"] = category

        return render_template(
            "quiz.html",
            category=category,
            questions_by_id={q["ID"]: q for q in selected},
            order=order
        )

    order = session.get("order", [])
    selected_by_id = {q["ID"]: q for q in selected}

    results = []
    score = 0

    for qid in order:
        q = selected_by_id.get(qid)
        if not q:
            continue

        correct = normalize_correct(q)
        correct_texts = get_correct_answer_texts(q)
        user_text = (request.form.get(f"ans_{qid}") or "").strip()
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

    return render_template(
        "result.html",
        category=category,
        score=score,
        total=len(order),
        results=results
    )


@app.route("/admin")
def admin_home():
    admin_redirect = admin_required()
    if admin_redirect:
        return admin_redirect

    question_count = db.session.query(func.count(Question.id)).scalar() or 0
    return render_template("admin_home.html", question_count=question_count)


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

    if not category:
        return jsonify({"error": "Category is required."}), 400
    if not answer_text:
        return jsonify({"error": "Answer is required."}), 400

    try:
        question = upsert_question_answer(
            qid=qid,
            category=category,
            text=text or STANDARD_IMAGE_PROMPT,
            image_url=image_url,
            answer_text=answer_text,
        )
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Could not save answer: {exc}"}), 500

    return jsonify({
        "ok": True,
        "qid": question.qid,
        "answer": question.a,
    })


@app.route("/admin/questions/new", methods=["GET", "POST"])
def admin_new_question():
    admin_redirect = admin_required()
    if admin_redirect:
        return admin_redirect

    error = None
    success = None
    image_choices = list_existing_image_choices()
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
    }

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
        }
        category = form_data["category"]
        text = form_data["text"]

        option_map = {
            "a": form_data["a"],
            "b": form_data["b"],
            "c": form_data["c"],
            "d": form_data["d"],
        }

        qid = form_data["qid"] or get_next_qid()
        image_url = form_data["image_url"] or form_data["existing_image_url"] or None

        if not text and image_url:
            text = STANDARD_IMAGE_PROMPT
            form_data["text"] = text

        if not category or not text:
            error = "Category and question text are required."
        elif not option_map["a"]:
            error = "Please provide the correct answer."
        elif Question.query.filter_by(qid=qid).first():
            error = "That QID already exists."
        else:
            question = Question(
                qid=qid,
                category=category,
                text=text,
                a=option_map["a"],
                b=option_map["b"],
                c=option_map["c"],
                d=option_map["d"],
                correct="T",
                image_url=image_url,
            )
            db.session.add(question)
            db.session.commit()
            success = f"Question {qid} saved."
            form_data = {
                "qid": "",
                "category": category,
                "text": STANDARD_IMAGE_PROMPT,
                "a": "",
                "b": "",
                "c": "",
                "d": "",
                "image_url": "",
                "existing_image_url": "",
            }

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

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not email:
            error = "Email is required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif User.query.filter_by(email=email).first():
            error = "An account with that email already exists."
        else:
            user = User(email=email, is_admin=is_admin_email(email))
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("home"))

    return render_template("register.html", error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("login"))


# -------------------------
# Main
# -------------------------

with app.app_context():
    db.create_all()
    enforce_single_admin_account()

if __name__ == "__main__":
    app.run(debug=True)
