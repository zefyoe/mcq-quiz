"""Send report PDFs through Resend's HTTPS API; no SMTP ports required."""
import base64
import json
import os
import re
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ReportMailError(Exception):
    pass


def report_mail_configured():
    sender = os.environ.get("REPORT_EMAIL_FROM", "").strip()
    return bool(os.environ.get("RESEND_API_KEY", "").strip()
                and '\n' not in sender and '\r' not in sender
                and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", parseaddr(sender)[1]))


def send_report_pdf(*, recipient, pdf, idempotency_key):
    if not report_mail_configured():
        raise ReportMailError("L’envoi par e-mail n’est pas encore activé.")
    payload = {
        "from": os.environ["REPORT_EMAIL_FROM"].strip(),
        "to": [recipient],
        "subject": "Compte rendu radiologique - Bymed",
        "text": "Bonjour,\n\nVeuillez trouver en pièce jointe le compte rendu radiologique.\n\nBymed Radiologie\nCentre Echographie de Pavillon, Rue Gaillait 35",
        "attachments": [{"filename": "compte-rendu-radiologique.pdf",
                         "content": base64.b64encode(pdf).decode("ascii")}],
    }
    request = Request("https://api.resend.com/emails", method="POST",
        data=json.dumps(payload).encode("utf-8"), headers={
            "Authorization": "Bearer " + os.environ["RESEND_API_KEY"].strip(),
            "Content-Type": "application/json", "User-Agent": "Bymed-Reporting/1.0",
            "Idempotency-Key": idempotency_key,
        })
    try:
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
        if not isinstance(result, dict) or not result.get("id"):
            raise ValueError("missing message id")
    except HTTPError as error:
        error.close()
        raise ReportMailError("Le service d’envoi a refusé la demande. Vérifiez la configuration de l’expéditeur ou réessayez plus tard.") from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise ReportMailError("L’envoi n’a pas pu être confirmé. Vérifiez auprès du destinataire avant de réessayer.") from None
    return result["id"]
