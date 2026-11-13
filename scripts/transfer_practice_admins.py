"""One-time encrypted transfer of the two owner-approved administrator logins.

Never exports patients, documents, quiz history, sessions or Gmail tokens.
Run interactively in the former service (export) and WIRC service (import).
The temporary encryption key and envelope must not be saved in Git or chat.
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet, InvalidToken

PURPOSE="wirc-administrators-v1"


def export_accounts(key):
    from app import ADMIN_EMAILS
    from models import User
    from practice_settings import AGENDA_ONLY
    if AGENDA_ONLY:
        raise ValueError("Export only from the former practice service.")
    users=User.query.filter(User.email.in_(ADMIN_EMAILS)).order_by(User.email).all()
    records=[dict(email=user.email,password_hash=user.password_hash) for user in users]
    if not records:
        raise ValueError("No approved administrator accounts were found.")
    return Fernet(key).encrypt(json.dumps(dict(purpose=PURPOSE,accounts=records)).encode()).decode()


def import_accounts(key,envelope):
    from app import ADMIN_EMAILS
    from models import db, User
    from practice_settings import AGENDA_ONLY
    if not AGENDA_ONLY:
        raise ValueError("Import only into the separate WIRC service.")
    try:
        payload=json.loads(Fernet(key).decrypt(envelope.encode(),ttl=900))
    except (InvalidToken,ValueError,TypeError):
        raise ValueError("Invalid or expired administrator transfer. Nothing was imported.") from None
    records=payload.get("accounts",[]) if isinstance(payload,dict) else []
    if not records or len(records)>len(ADMIN_EMAILS) or payload.get("purpose")!=PURPOSE:
        raise ValueError("This envelope is not an approved administrator transfer.")
    seen=set()
    for item in records:
        email=item.get("email","") if isinstance(item,dict) else ""
        password_hash=item.get("password_hash","") if isinstance(item,dict) else ""
        if (email not in ADMIN_EMAILS or email in seen or not isinstance(password_hash,str)
                or not password_hash.startswith(("scrypt:","pbkdf2:")) or not 50<len(password_hash)<=255):
            raise ValueError("The transfer contains an unapproved account or password hash.")
        seen.add(email)
    try:
        for item in records:
            existing=User.query.filter_by(email=item["email"]).with_for_update().first()
            if existing and existing.password_hash!=item["password_hash"]:
                raise ValueError("A WIRC account already has a different password. Nothing was overwritten.")
            if existing:
                existing.is_admin=True
            else:
                db.session.add(User(email=item["email"],password_hash=item["password_hash"],is_admin=True))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return sorted(seen)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("export","import"))
    args=parser.parse_args()
    from app import app
    key=getpass.getpass("Temporary transfer key: ").encode()
    with app.app_context():
        if args.action=="export":
            print("WIRC_ADMIN_ENVELOPE="+export_accounts(key),flush=True)
        else:
            envelope=getpass.getpass("Encrypted administrator envelope: ")
            emails=import_accounts(key,envelope)
            print("Administrator logins preserved: "+", ".join(emails),flush=True)
