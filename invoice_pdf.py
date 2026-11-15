"""A4 fee letters with an explicit patient/insurer split; no insurer submission."""
from datetime import timedelta
from html import escape
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


def euro(cents):
    return f"{int(cents)/100:,.2f}".replace(',', ' ').replace('.', ',') + ' EUR'


def create_invoice_pdf(*, data, issuer, number, invoice_date, draft=False):
    output = BytesIO()
    ink = colors.HexColor('#243e36'); muted = colors.HexColor('#697c72')
    green = colors.HexColor('#236b59'); border = colors.HexColor('#dfe7e1')
    styles = {
        'body': ParagraphStyle('invoice-body',fontName='Helvetica',fontSize=9.5,leading=14,textColor=ink),
        'small': ParagraphStyle('invoice-small',fontName='Helvetica',fontSize=8,leading=12,textColor=muted),
        'label': ParagraphStyle('invoice-label',fontName='Helvetica-Bold',fontSize=8,leading=12,textColor=muted),
        'title': ParagraphStyle('invoice-title',fontName='Helvetica-Bold',fontSize=20,leading=25,textColor=ink),
        'right': ParagraphStyle('invoice-right',fontName='Helvetica',fontSize=9.5,leading=14,textColor=ink,alignment=TA_RIGHT),
        'total': ParagraphStyle('invoice-total',fontName='Helvetica-Bold',fontSize=12,leading=17,textColor=green),
        'total_right': ParagraphStyle('invoice-total-right',fontName='Helvetica-Bold',fontSize=12,leading=17,textColor=green,alignment=TA_RIGHT),
    }
    def p(value,style='body'):
        value=str(value or '').replace('—','-').replace('–','-').replace('‑','-').replace('≥','>=').replace('≤','<=')
        return Paragraph(escape(value).replace('\n','<br/>'),styles[style])
    def row_table(rows,widths,commands=()):
        table=Table(rows,colWidths=widths,hAlign='LEFT')
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
            ('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),*commands]))
        return table
    due=invoice_date+timedelta(days=30)
    doc=SimpleDocTemplate(output,pagesize=A4,leftMargin=20*mm,rightMargin=20*mm,
        topMargin=18*mm,bottomMargin=25*mm,title=('Brouillon - ' if draft else '')+'Facture '+number,
        author=issuer.get('legal_name',''),invariant=True)
    width=170*mm
    story=[row_table([[p(issuer.get('display_name','WIRC'),'title'),p('BROUILLON' if draft else "FACTURE D’HONORAIRES",'right')]], [100*mm,70*mm]),
        p(issuer.get('legal_name',''),'label'),p(issuer.get('address',''),'small'),
        p('BCE : '+(issuer.get('enterprise_number') or 'À compléter')+'   |   INAMI : '+(issuer.get('doctor_inami') or 'À compléter'),'small'),
        Spacer(1,11*mm)]
    recipient='\n'.join(v for v in (data.get('patient_name'),data.get('patient_street'),
        ' '.join(v for v in (data.get('patient_postcode'),data.get('patient_city')) if v),data.get('patient_country','Belgique')) if v)
    meta=f"Référence : {number}\nDate de facturation : {invoice_date.strftime('%d/%m/%Y')}\nÉchéance : {due.strftime('%d/%m/%Y')} (30 jours)"
    story.extend([row_table([[p(meta),p(recipient)]],[85*mm,85*mm]),Spacer(1,8*mm),
        p('Madame, Monsieur,'),Spacer(1,3*mm),p('Veuillez trouver ci-dessous le détail des honoraires relatifs à votre examen radiologique.'),Spacer(1,5*mm)])
    examination_date=data.get('examination_date','')
    try:
        from datetime import date
        examination_date=date.fromisoformat(examination_date).strftime('%d/%m/%Y')
    except ValueError:
        pass
    story.append(row_table([[p('DATE','label'),p('CODE INAMI','label'),p('EXAMEN RÉALISÉ','label')],
        [p(examination_date),p(data.get('billing_code','')),p(data.get('examination',''))]],
        [27*mm,28*mm,115*mm],[('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eef4ef')),
        ('LINEBELOW',(0,1),(-1,1),.5,border),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    doctor=data.get('doctor_name') or issuer.get('doctor_name') or ''
    story.extend([Spacer(1,4*mm),p('Radiologue : '+doctor+' | INAMI : '+(data.get('doctor_inami') or issuer.get('doctor_inami','')),'small')])
    if data.get('prescriber_name'):
        story.append(p('Médecin prescripteur : '+data['prescriber_name'],'small'))
    if data.get('mutuality'):
        story.append(p('Organisme assureur : '+data['mutuality'],'small'))
    if data.get('national_number'):
        story.append(p('N° dossier (registre national) : '+data['national_number'],'small'))
    patient=int(data.get('patient_cents',0)); ticket=int(data.get('ticket_cents',0)); insurance=int(data.get('insurance_cents',0))
    supplement=patient-ticket
    totals=[['Honoraires totaux',euro(patient+insurance)],['Part de la mutualité (tiers payant)',euro(insurance)],
        ['Ticket modérateur',euro(ticket)],['Supplément à charge du patient',euro(supplement)]]
    summary=row_table([[p(label),p(amount,'right')] for label,amount in totals]+
        [[p('À PAYER PAR LE PATIENT','total'),p(euro(patient),'total_right')]], [125*mm,45*mm],
        [('LINEABOVE',(0,4),(-1,4),1,green),('BACKGROUND',(0,4),(-1,4),colors.HexColor('#eef5ef'))])
    payment=[Spacer(1,7*mm),summary,Spacer(1,6*mm),p('Paiement par virement bancaire','label'),
        p('IBAN : '+(issuer.get('iban') or 'À compléter')),
        p('Bénéficiaire : '+(issuer.get('account_holder') or 'À compléter')),
        p('Communication : '+number),p('Merci de régler '+euro(patient)+' au plus tard le '+due.strftime('%d/%m/%Y')+'.' if patient else 'Aucun montant à payer par le patient.'),
        Spacer(1,3*mm),p('La part de la mutualité ne doit pas être versée par le patient.','small')]
    if issuer.get('bic'):
        payment.insert(4,p('BIC : '+issuer['bic']))
    story.append(KeepTogether(payment))
    if issuer.get('vat_note'):
        story.extend([Spacer(1,4*mm),p(issuer['vat_note'],'small')])
    if draft:
        story.extend([Spacer(1,5*mm),p('BROUILLON - document de travail, non émis et non payable.','label')])
    def footer(canvas,document):
        canvas.saveState();canvas.setStrokeColor(border);canvas.line(20*mm,19*mm,A4[0]-20*mm,19*mm)
        if data.get('_example'):
            canvas.setFillColor(colors.HexColor('#bc4450'));canvas.setFont('Helvetica-Bold',9)
            canvas.drawCentredString(A4[0]/2,23*mm,'EXEMPLE - DONNEES FICTIVES - NE PAS PAYER')
        canvas.setFont('Helvetica',7.5);canvas.setFillColor(muted)
        contact=' | '.join(v for v in (issuer.get('email'),issuer.get('phone')) if v)
        canvas.drawString(20*mm,14*mm,contact[:110]);canvas.drawRightString(A4[0]-20*mm,10*mm,f'{number} - Page {document.page}')
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
