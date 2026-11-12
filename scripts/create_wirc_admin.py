"""Interactive, WIRC-only bootstrap. Never imports old users or passwords."""
import getpass
import os
import sys
from pathlib import Path

if os.environ.get("PRACTICE_PROFILE") != "wirc":
    raise SystemExit("Run only in the separate WIRC service with PRACTICE_PROFILE=wirc.")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app, db, is_admin_email
from models import User

email=input("Administrator email: ").strip().lower()
if not is_admin_email(email):
    raise SystemExit("This email is not in the application's administrator allowlist.")
password=getpass.getpass("New WIRC password (at least 12 characters): ")
if len(password)<12 or password!=getpass.getpass("Repeat new WIRC password: "):
    raise SystemExit("Password too short or confirmation did not match. Nothing changed.")
with app.app_context():
    if User.query.filter_by(email=email).first():
        raise SystemExit("This account already exists. No password was changed.")
    user=User(email=email,is_admin=True)
    user.set_password(password)
    db.session.add(user);db.session.commit()
print("WIRC administrator created. No former patients, users or Gmail tokens were imported.")
