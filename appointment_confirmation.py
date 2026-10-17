"""Generate an A4 confirmation for one public appointment, in memory only."""

from datetime import datetime, timedelta
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


NAVY = colors.HexColor("#172b49")
BLUE = colors.HexColor("#2c67ba")
MUTED = colors.HexColor("#5f7089")
LIGHT = colors.HexColor("#edf4fb")


def create_appointment_confirmation_pdf(
    *, patient_name: str, starts_at: datetime, examination: str,
    practice_address: str, email: str = "", phone: str = "",
    prescription_attached: bool = False,
) -> bytes:
    """Return a private PDF without tariff, INAMI code or insurance details."""
    output = BytesIO()
    page = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    page.setTitle("Confirmation de rendez-vous - Bymed Radiologie")
    page.setAuthor("Bymed Radiologie")
    width, height = A4
    margin = 54

    def paragraph(value: str, x: float, top: float, available_width: float,
                  *, size: int = 11, leading: int = 16,
                  color=NAVY, bold: bool = False) -> float:
        style = ParagraphStyle(
            "confirmation", fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size, leading=leading, textColor=color, alignment=TA_LEFT,
        )
        text = Paragraph(escape(value).replace("\n", "<br/>"), style)
        _, used_height = text.wrap(available_width, height)
        text.drawOn(page, x, top - used_height)
        return top - used_height

    page.setFillColor(NAVY)
    page.rect(0, height - 116, width, 116, fill=1, stroke=0)
    paragraph("BYMED", margin, height - 42, width - 2 * margin,
              size=24, leading=28, color=colors.white, bold=True)
    paragraph("CABINET PRIVÉ DE RADIOLOGIE", margin, height - 75,
              width - 2 * margin, size=9, leading=13, color=colors.HexColor("#c7daef"))

    y = height - 156
    y = paragraph("Confirmation de rendez-vous", margin, y, width - 2 * margin,
                  size=21, leading=27, bold=True) - 16
    y = paragraph(f"Bonjour {patient_name},", margin, y, width - 2 * margin,
                  size=12, leading=18) - 8
    y = paragraph("Votre rendez-vous est confirmé. Vous trouverez les détails ci-dessous.",
                  margin, y, width - 2 * margin, size=11, leading=17) - 24

    box_top = y
    box_height = 206
    page.setFillColor(LIGHT)
    page.roundRect(margin, box_top - box_height, width - 2 * margin,
                   box_height, 12, fill=1, stroke=0)
    x = margin + 22
    inner_width = width - 2 * margin - 44
    cursor = box_top - 22
    details = [
        ("PATIENT", patient_name),
        ("EXAMEN", examination),
        ("DATE ET HEURE", starts_at.strftime("%d/%m/%Y à %H:%M")),
        ("LIEU", practice_address or "Cabinet Bymed Radiologie"),
    ]
    for label, value in details:
        cursor = paragraph(label, x, cursor, inner_width, size=8, leading=11,
                           color=BLUE, bold=True) - 3
        cursor = paragraph(value, x, cursor, inner_width, size=11, leading=15,
                           bold=True) - 12
    y = box_top - box_height - 27

    if email or phone or prescription_attached:
        y = paragraph("Informations communiquées", margin, y, width - 2 * margin,
                      size=11, leading=15, bold=True) - 10
        if email:
            y = paragraph(f"E-mail : {email}", margin, y, width - 2 * margin,
                          size=10, leading=15) - 5
        if phone:
            y = paragraph(f"Téléphone : {phone}", margin, y, width - 2 * margin,
                          size=10, leading=15) - 5
        if prescription_attached:
            y = paragraph("Ordonnance : jointe lors de la réservation", margin, y,
                          width - 2 * margin, size=10, leading=15) - 5

    end_at = starts_at + timedelta(minutes=10)
    paragraph(f"Durée du créneau : {starts_at.strftime('%H:%M')} - {end_at.strftime('%H:%M')}.",
              margin, y - 22, width - 2 * margin, size=10, leading=15, color=MUTED)
    page.setStrokeColor(colors.HexColor("#dbe5ef"))
    page.line(margin, 83, width - margin, 83)
    paragraph("Veuillez présenter cette confirmation lors de votre rendez-vous.",
              margin, 69, width - 2 * margin, size=9, leading=13, color=MUTED)
    page.showPage()
    page.save()
    return output.getvalue()
