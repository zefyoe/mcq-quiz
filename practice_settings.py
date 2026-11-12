"""Deployment identity. WIRC uses a separate database, never a patient import."""
import os

AGENDA_ONLY = os.environ.get("PRACTICE_PROFILE", "legacy").strip().lower() == "wirc"
PRACTICE_NAME = os.environ.get("PRACTICE_NAME", "WIRC · Cabinet de radiologie" if AGENDA_ONLY else "Bymed Radiologie").strip()
PRACTICE_SHORT_NAME = os.environ.get("PRACTICE_SHORT_NAME", "WIRC" if AGENDA_ONLY else "Bymed").strip()
PRACTICE_ENGLISH_NAME = os.environ.get("PRACTICE_ENGLISH_NAME", "").strip()
PRACTICE_ADDRESS = os.environ.get("APPOINTMENT_PRACTICE_ADDRESS", "").strip()
PUBLIC_CLOSURE_MESSAGE = "Le cabinet est temporairement fermé. La date de reprise des consultations et la nouvelle adresse seront communiquées prochainement."
PUBLIC_BOOKING_ENABLED = os.environ.get("APPOINTMENT_BOOKING_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
if AGENDA_ONLY and PUBLIC_BOOKING_ENABLED and not PRACTICE_ADDRESS:
    raise RuntimeError("Set WIRC's new APPOINTMENT_PRACTICE_ADDRESS before opening public bookings.")


def practice_address():
    return PRACTICE_ADDRESS or "Adresse des prochaines consultations à confirmer"
