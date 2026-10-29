"""Create printable radiology reports without persisting their contents."""
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def create_radiology_report_pdf(*, patient_name, examination, starts_at,
                                report_date, report_text, radiologist, practice_address):
    output = BytesIO()
    # Stable PDF bytes let the mail service deduplicate retries of the same report.
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=20*mm,
        leftMargin=20*mm, topMargin=66*mm, bottomMargin=22*mm,
        title="Compte rendu radiologique", author=radiologist or "Bymed Radiologie", invariant=True)
    body_style = ParagraphStyle("report", fontName="Helvetica", fontSize=11,
                               leading=16, spaceAfter=8, splitLongWords=True)
    meta_style = ParagraphStyle("metadata", fontName="Helvetica", fontSize=10, leading=14)
    heading_style = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=15,
                                  leading=19, textColor=colors.HexColor("#172b49"))
    address = Paragraph(escape(practice_address), meta_style)
    _, address_height = address.wrap(A4[0]-40*mm, A4[1])
    metadata = Paragraph(
        f"<b>Patient :</b> {escape(patient_name)}<br/>"
        f"<b>Examen :</b> {escape(examination)}<br/>"
        f"<b>Rendez-vous :</b> {starts_at.strftime('%d/%m/%Y à %H:%M')}", meta_style)
    _, metadata_height = metadata.wrap(A4[0]-40*mm, A4[1])
    metadata_top = A4[1]-max(39*mm, 33*mm+address_height)
    document.topMargin = A4[1]-metadata_top+metadata_height+9*mm

    def header_footer(page, doc):
        page.saveState()
        width, height = A4
        page.setFillColor(colors.HexColor("#172b49"))
        page.setFont("Helvetica-Bold", 18)
        page.drawString(20*mm, height-23*mm, "BYMED - RADIOLOGIE")
        address.drawOn(page, 20*mm, height-28*mm-address_height)
        metadata.drawOn(page, 20*mm, metadata_top-metadata_height)
        page.setStrokeColor(colors.HexColor("#d3dfed"))
        page.line(20*mm, 17*mm, width-20*mm, 17*mm)
        page.setFillColor(colors.HexColor("#60718a"))
        page.setFont("Helvetica", 8)
        page.drawString(20*mm, 12*mm, f"Compte rendu du {report_date.strftime('%d/%m/%Y')}")
        page.drawRightString(width-20*mm, 12*mm, f"Page {doc.page}")
        page.restoreState()

    story = [Paragraph("COMPTE RENDU RADIOLOGIQUE", heading_style), Spacer(1, 6*mm)]
    # Escape pasted content: it is text, never HTML. Preserve line breaks and pages.
    for block in report_text.replace('\r\n', '\n').replace('\r', '\n').split('\n\n'):
        if block.strip():
            story.append(Paragraph(escape(block).replace('\n', '<br/>'), body_style))
        else:
            story.append(Spacer(1, 3*mm))
    if radiologist:
        story.extend([Spacer(1, 8*mm), Paragraph(escape(radiologist), body_style)])
    document.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return output.getvalue()
