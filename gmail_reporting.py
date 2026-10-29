"""Google sign-in and Gmail sending, with encrypted server-side credentials."""
import base64
import hashlib
import os
from email.message import EmailMessage
from functools import partial

from cryptography.fernet import Fernet, InvalidToken
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google.auth.exceptions import GoogleAuthError
import requests

from report_mail import ReportMailError

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", GMAIL_SCOPE]


def google_oauth_configured():
    return all(os.environ.get(key, "").strip() for key in (
        "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI"))


def google_flow(*, state=None, verifier=None):
    return Flow.from_client_config({"web": {
        "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}, scopes=SCOPES, state=state,
        redirect_uri=os.environ["GOOGLE_OAUTH_REDIRECT_URI"],
        code_verifier=verifier, autogenerate_code_verifier=verifier is None)


def verified_google_identity(credentials, nonce):
    if not credentials.id_token:
        raise ValueError("Google identity is missing")
    claims = id_token.verify_oauth2_token(credentials.id_token, partial(GoogleRequest(), timeout=20),
                                        os.environ["GOOGLE_OAUTH_CLIENT_ID"])
    if claims.get("nonce") != nonce or claims.get("email_verified") is not True or not claims.get("sub"):
        raise ValueError("Google identity was not verified")
    return claims


def token_cipher(secret):
    key = hashlib.sha256(("gmail-reporting-token:" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def send_gmail_report(*, connection, secret, recipient, pdf, message_key):
    try:
        refresh_token = token_cipher(secret).decrypt(connection.encrypted_refresh_token.encode()).decode()
        credentials = Credentials(token=None, refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"], scopes=SCOPES)
        credentials.refresh(partial(GoogleRequest(), timeout=20))
    except (InvalidToken, GoogleAuthError, requests.RequestException, ValueError, KeyError):
        raise ReportMailError("La connexion Gmail a expiré. Reconnectez votre compte Google.") from None
    message = EmailMessage()
    message["From"] = connection.email
    message["To"] = recipient
    message["Subject"] = "Compte rendu radiologique - Bymed"
    message["Message-ID"] = f"<{message_key}@bymed.be>"
    message.set_content("Bonjour,\n\nVeuillez trouver en pièce jointe le compte rendu radiologique.\n\nBymed Radiologie")
    message.add_attachment(pdf, maintype="application", subtype="pdf", filename="compte-rendu-radiologique.pdf")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        response = requests.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": "Bearer " + credentials.token}, json={"raw": raw}, timeout=20)
        response.raise_for_status()
        result = response.json()
        if not result.get("id"):
            raise ValueError("missing Gmail message id")
    except (requests.RequestException, ValueError):
        raise ReportMailError("Gmail n’a pas confirmé l’envoi. Vérifiez les messages envoyés avant de réessayer.") from None
    return result["id"]
