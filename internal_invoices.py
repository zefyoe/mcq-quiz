"""Private draft -> immutable fee invoice -> PDF/Gmail workflow.

This module never submits claims to health insurers. All money uses integer cents.
"""
import json
import re
import secrets
import uuid
from email.utils import parseaddr
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from flask import abort, jsonify, make_response, render_template, request, url_for
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from models import (db, Appointment, AppointmentHold, AppointmentPatientDetails, HistoricalDossier,
                    InvoiceSettings, PatientInvoice, InvoiceSequence, InvoiceDelivery)
from practice_settings import PRACTICE_NAME, PRACTICE_SHORT_NAME, practice_address
from inami_ultrasound_catalog import INAMI_ULTRASOUND_BY_CODE, INTERNAL_INAMI_CODES, INTERNAL_INAMI_CHOICES
from invoice_pdf import create_invoice_pdf, euro
from report_mail import ReportMailError

SETTINGS_FIELDS = {'legal_name':255,'display_name':120,'address':700,'enterprise_number':30,
    'doctor_name':255,'doctor_inami':40,'account_holder':255,'iban':50,'bic':20,'email':254,'phone':80,'vat_note':500}
DATA_FIELDS = {'patient_name':255,'patient_email':254,'patient_street':255,'patient_postcode':20,
    'patient_city':120,'patient_country':80,'national_number':15,'examination':1000,'examination_date':10,
    'billing_code':6,'doctor_name':255,'doctor_inami':40,'prescriber_name':255,'mutuality':150,'insurance_status':16}


def unpack(value):
    return json.loads(value or '{}')


def money(value):
    try:
        amount=Decimal(str(value).strip().replace(',','.'))
        if not amount.is_finite() or amount<0 or amount>10000 or amount*100 != (amount*100).to_integral():
            raise ValueError()
        return int(amount*100)
    except (ValueError, InvalidOperation):
        raise ValueError('Indiquez un montant de 0 à 10 000 EUR avec deux décimales maximum.') from None


def valid_email(value):
    return (len(value)<=254 and not re.search(r'[\s,;<>()[\]]',value)
            and bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value))
            and parseaddr(value)==('',value))


def valid_iban(value):
    if not re.fullmatch(r'[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}',value):
        return False
    return int(''.join(str(ord(c)-55) if c.isalpha() else c for c in value[4:]+value[:4]))%97==1


def settings_data():
    row=db.session.get(InvoiceSettings,1)
    result=dict(display_name=PRACTICE_NAME,legal_name='',address=practice_address(),enterprise_number='',
        doctor_name='',doctor_inami='',account_holder='',iban='',bic='',email='',phone='',vat_note='',
        default_patient_cents=2000,convention_status='unconfirmed')
    if row: result.update(unpack(row.data_json))
    return result,row.revision if row else 0


def settings_missing(data):
    return [name for name in ('legal_name','address','enterprise_number','doctor_name','doctor_inami','account_holder','iban') if not data.get(name)]


def invoice_payload(item):
    return dict(id=item.id,state=item.state,revision=item.revision,number=item.number or '',data=unpack(item.data_json),
        issuer=unpack(item.issuer_json) if item.state=='issued' else settings_data()[0],
        invoice_date=item.invoice_date.isoformat() if item.invoice_date else '',due_date=item.due_date.isoformat() if item.due_date else '',
        paid_on=item.paid_on.isoformat() if item.paid_on else '',email_state=item.email_state,
        last_recipient=item.last_recipient,last_sent_at=item.last_sent_at.isoformat() if item.last_sent_at else '',
        pdf_url=url_for('admin_invoice_pdf',invoice_id=item.id))


def register_internal_invoices(app, *, admin_required, ensure_schema, csrf_token, now, record_key, gmail_connection, send_invoice):
    def authorize(write=False):
        denied=admin_required()
        if denied: return denied
        if write and not secrets.compare_digest(request.form.get('csrf_token',''),csrf_token()): abort(400)
        ensure_schema()

    def item_or_404(invoice_id,lock=False):
        query=PatientInvoice.query.filter_by(id=invoice_id)
        item=(query.with_for_update() if lock else query).first()
        if item is None: abort(404)
        return item

    def stale(item):
        return request.form.get('revision',type=int)!=item.revision

    def failure(message,status=400):
        db.session.rollback()
        return jsonify(ok=False,error=message),status

    @app.get('/admin/appointments/invoices')
    def admin_invoice_list():
        denied=authorize()
        if denied: return denied
        page=max(1,request.args.get('page',1,type=int));size=40
        status=request.args.get('status','all')
        if status not in {'all','draft','outstanding','paid'}:status='all'
        query=PatientInvoice.query
        counts=dict(all=query.count(),draft=query.filter_by(state='draft').count(),
            outstanding=query.filter(PatientInvoice.state=='issued',PatientInvoice.paid_on.is_(None)).count(),
            paid=query.filter(PatientInvoice.paid_on.is_not(None)).count())
        if status=='draft':query=query.filter_by(state='draft')
        elif status=='outstanding':query=query.filter(PatientInvoice.state=='issued',PatientInvoice.paid_on.is_(None))
        elif status=='paid':query=query.filter(PatientInvoice.paid_on.is_not(None))
        total=counts[status]
        page=min(page,max(1,(total+size-1)//size))
        items=query.order_by(PatientInvoice.created_at.desc(),PatientInvoice.id).offset((page-1)*size).limit(size).all()
        listing=dict(invoices=[invoice_payload(item) for item in items],page=page,total=total,page_size=size,
            invoice_status=status,invoice_counts=counts,today=now().date(),euro=euro)
        if request.args.get('fragment')=='1':
            return jsonify(ok=True,html=render_template('_invoice_list.html',**listing))
        settings,revision=settings_data()
        return render_template('internal_invoices.html',internal_agenda=True,billing_page=True,
            **listing,csrf_token=csrf_token(),invoice_settings=settings,settings_revision=revision,
            invoice_settings_missing=settings_missing(settings),gmail_ready=bool(gmail_connection()),
            billing_choices=INTERNAL_INAMI_CHOICES)

    @app.route('/admin/appointments/invoices/settings',methods=['GET','POST'])
    def admin_invoice_settings():
        denied=authorize(request.method=='POST')
        if denied:return denied
        settings,revision=settings_data()
        if request.method=='GET':return jsonify(ok=True,settings=settings,revision=revision,missing=settings_missing(settings))
        if request.form.get('revision',type=int)!=revision:return failure('Les coordonnées ont changé. Rechargez-les avant de sauvegarder.',409)
        for name,limit in SETTINGS_FIELDS.items():
            value=request.form.get(name,'').strip()
            if len(value)>limit:return failure('Le champ '+name+' est trop long.')
            settings[name]=value
        settings['iban']=re.sub(r'\s','',settings['iban']).upper()
        settings['doctor_inami']=re.sub(r'[ .-]','',settings['doctor_inami'])
        settings['enterprise_number']=re.sub(r'[ .-]','',settings['enterprise_number'])
        if settings['iban'] and not valid_iban(settings['iban']):return failure('Le numéro IBAN est invalide.')
        if settings['doctor_inami'] and not re.fullmatch(r'\d{11}',settings['doctor_inami']):return failure('Le numéro INAMI du médecin doit contenir 11 chiffres.')
        enterprise=settings['enterprise_number']
        if enterprise and (not re.fullmatch(r'\d{10}',enterprise) or 97-int(enterprise[:8])%97!=int(enterprise[8:])):
            return failure('Le numéro BCE est invalide. Vérifiez les 10 chiffres et la clé de contrôle.')
        if settings['email'] and not valid_email(settings['email']):return failure('Adresse e-mail du cabinet invalide.')
        status=request.form.get('convention_status','unconfirmed')
        if status not in {'unconfirmed','conventionne','non_conventionne','partiel'}:return failure('Choisissez le statut de conventionnement.')
        settings['convention_status']=status
        try:settings['default_patient_cents']=money(request.form.get('default_patient_amount','20.00'))
        except ValueError as error:return failure(str(error))
        row=db.session.get(InvoiceSettings,1)
        if row is None:row=InvoiceSettings(id=1);db.session.add(row)
        row.data_json=json.dumps(settings,ensure_ascii=False)
        try:db.session.commit()
        except (IntegrityError,StaleDataError):return failure('Les coordonnées ont changé. Rechargez la page.',409)
        return jsonify(ok=True,settings=settings,revision=row.revision,missing=settings_missing(settings))

    @app.get('/admin/appointments/invoices/tariff/<code>')
    def admin_invoice_tariff(code):
        denied=authorize()
        if denied:return denied
        if code not in INTERNAL_INAMI_CODES:abort(404)
        tariff=INAMI_ULTRASOUND_BY_CODE[code]
        return jsonify(ok=True,code=code,label=tariff['label_fr'],ticket_cents=tariff['exam_patient_share_cents'],
            insurance_cents=tariff['exam_reimbursement_cents'],reference='2026-01-01')

    @app.post('/admin/appointments/invoices/patients/search')
    def admin_invoice_patient_search():
        denied=authorize(True)
        if denied:return denied
        # Keep patient search terms out of URLs and access logs. Fetch only
        # identity/exam columns; scans and report contents are never loaded.
        term=' '.join(request.form.get('q','').split())
        if len(term)>120:return failure('La recherche est trop longue.')
        if len(term)<2:return jsonify(ok=True,patients=[],limited=False)
        words=term.split();limit=40;matches=[]
        appointments=db.session.query(Appointment.id,Appointment.starts_at,Appointment.patient_name,
            Appointment.inami_code,Appointment.appointment_type,Appointment.created_at)
        history=db.session.query(HistoricalDossier.id,HistoricalDossier.examined_on,
            HistoricalDossier.patient_name,HistoricalDossier.examination)
        for word in words:
            appointments=appointments.filter(Appointment.patient_name.icontains(word,autoescape=True))
            history=history.filter(HistoricalDossier.patient_name.icontains(word,autoescape=True))
        for record in appointments.order_by(Appointment.starts_at,Appointment.id).limit(limit+1):
            code=record.inami_code or record.appointment_type
            key=record_key(Appointment(id=record.id,starts_at=record.starts_at,patient_name=record.patient_name,created_at=record.created_at))
            matches.append(dict(appointment_id=record.id,context_key=key,
                patient_name=record.patient_name,starts_at=record.starts_at.isoformat(timespec='minutes'),
                examination=INAMI_ULTRASOUND_BY_CODE.get(code,{}).get('label_fr') or record.appointment_type or 'Examen échographique',
                kind='Rendez-vous'))
        for record in history.order_by(HistoricalDossier.examined_on,HistoricalDossier.id).limit(limit+1):
            matches.append(dict(historical_id=record.id,context_key='historical:'+str(record.id),
                patient_name=record.patient_name,starts_at=record.examined_on.isoformat(),
                examination=record.examination,kind='Ancien dossier'))
        # Older reservations store names in JSON text. Read that small field
        # safely, including legacy malformed entries, and ignore booking claims.
        booked=db.session.query(Appointment.id).filter(Appointment.starts_at==AppointmentHold.starts_at).exists()
        holds=db.session.query(AppointmentHold.starts_at,AppointmentHold.token,AppointmentHold.draft_data).filter(~booked).order_by(AppointmentHold.starts_at)
        found=0
        for stamp,token,raw in holds.yield_per(200):
            try:draft=unpack(raw)
            except (ValueError,TypeError):continue
            if not isinstance(draft,dict):continue
            name=str(draft.get('patient_name') or '')
            if not name.strip() or not all(word.casefold() in name.casefold() for word in words):continue
            code=draft.get('inami_code','')
            matches.append(dict(reservation_start=stamp.isoformat(timespec='minutes'),
                context_key=record_key(AppointmentHold(starts_at=stamp,token=token)),patient_name=name,
                starts_at=stamp.isoformat(timespec='minutes'),
                examination=INAMI_ULTRASOUND_BY_CODE.get(code,{}).get('label_fr') or 'Examen échographique',kind='Rendez-vous'))
            found+=1
            if found>limit:break
        matches.sort(key=lambda item:(item['starts_at'],item['patient_name'],item['context_key']))
        limited=len(matches)>limit;matches=matches[:limit]
        keys=[item['context_key'] for item in matches]
        invoices={item.context_key:item for item in PatientInvoice.query.filter(PatientInvoice.context_key.in_(keys)).all()} if keys else {}
        for item in matches:
            existing=invoices.get(item.pop('context_key'))
            if existing:item.update(invoice_id=existing.id,invoice_number=existing.number or '',invoice_state=existing.state)
        return jsonify(ok=True,patients=matches,limited=limited)

    @app.post('/admin/appointments/invoices')
    def admin_invoice_create():
        denied=authorize(True)
        if denied:return denied
        values=request.form;source={};settings,_=settings_data()
        if values.get('historical_id'):
            record=HistoricalDossier.query.filter_by(id=values.get('historical_id',type=int)).with_for_update().first()
            if record is None:abort(404)
            key='historical:'+str(record.id)
            source=dict(patient_name=record.patient_name,examination=record.examination,
                examination_date=record.examined_on.isoformat(),billing_code=record.billing_code,national_number=record.national_number)
        else:
            aid=values.get('appointment_id',type=int)
            if aid:
                record=Appointment.query.filter_by(id=aid).with_for_update().first()
                if record is None:abort(404)
                source=dict(patient_name=record.patient_name,patient_email=record.patient_email,
                    examination_date=record.starts_at.date().isoformat(),billing_code=record.inami_code or record.appointment_type,
                    prescriber_name=record.referring_doctor or '',insurance_status=record.insurance_status or '')
            else:
                try:stamp=datetime.fromisoformat(values.get('reservation_start',''))
                except ValueError:abort(400)
                record=AppointmentHold.query.filter_by(starts_at=stamp).with_for_update().first()
                if record is None:abort(404)
                source=dict(record.draft,examination_date=record.starts_at.date().isoformat(),billing_code=record.draft.get('inami_code',''))
            key=record_key(record)
            details=db.session.get(AppointmentPatientDetails,key)
            if details:
                source.update(national_number=details.national_number,billing_code=details.billing_code or source.get('billing_code',''))
        existing=PatientInvoice.query.filter_by(context_key=key).first()
        if existing:return jsonify(ok=True,invoice=invoice_payload(existing),existing=True)
        code=source.get('billing_code','');tariff=INAMI_ULTRASOUND_BY_CODE.get(code,{}) if code in INTERNAL_INAMI_CODES else {}
        data={name:str(source.get(name,'') or '') for name in DATA_FIELDS}
        data.update(examination=source.get('examination') or tariff.get('label_fr','Examen échographique'),
            patient_country='Belgique',doctor_name=settings['doctor_name'],doctor_inami=settings['doctor_inami'],
            patient_cents=settings['default_patient_cents'],ticket_cents=tariff.get('exam_patient_share_cents',0),
            insurance_cents=tariff.get('exam_reimbursement_cents',0),tariff_reference='2026-01-01' if tariff else '')
        item=PatientInvoice(id=str(uuid.uuid4()),context_key=key,data_json=json.dumps(data,ensure_ascii=False))
        db.session.add(item)
        try:db.session.commit()
        except IntegrityError:
            db.session.rollback();item=PatientInvoice.query.filter_by(context_key=key).first()
            if item is None:return failure('Facture non créée. Réessayez.',409)
        return jsonify(ok=True,invoice=invoice_payload(item))

    @app.route('/admin/appointments/invoices/<invoice_id>',methods=['GET','POST'])
    def admin_invoice_detail(invoice_id):
        denied=authorize(request.method=='POST')
        if denied:return denied
        item=item_or_404(invoice_id)
        if request.method=='GET':return jsonify(ok=True,invoice=invoice_payload(item),gmail_ready=bool(gmail_connection()),missing=settings_missing(settings_data()[0]))
        if item.state!='draft':return failure('Une facture émise est figée. Les coordonnées et montants ne peuvent plus être modifiés.',409)
        if stale(item):return failure('Ce brouillon a changé dans une autre fenêtre. Rechargez-le avant de modifier.',409)
        data=unpack(item.data_json)
        for name,limit in DATA_FIELDS.items():
            value=request.form.get(name,'').strip()
            if len(value)>limit:return failure('Le champ '+name+' est trop long.')
            data[name]=value
        if data['patient_email'] and not valid_email(data['patient_email']):return failure('Adresse e-mail du patient invalide.')
        data['national_number']=re.sub(r'[ .-]','',data['national_number'])
        if data['national_number'] and not re.fullmatch(r'\d{11}',data['national_number']):return failure('Le numéro de dossier doit contenir 11 chiffres.')
        data['doctor_inami']=re.sub(r'[ .-]','',data['doctor_inami'])
        if data['billing_code'] and data['billing_code'] not in INTERNAL_INAMI_CODES:return failure('Choisissez un code INAMI de la liste.')
        try:
            data.update({name+'_cents':money(request.form.get(name+'_amount','')) for name in ('patient','insurance','ticket')})
        except ValueError as error:return failure(str(error))
        if data['ticket_cents']>data['patient_cents']:return failure('Le ticket modérateur ne peut pas dépasser le montant total demandé au patient.')
        item.data_json=json.dumps(data,ensure_ascii=False);item.updated_at=datetime.utcnow()
        try:db.session.commit()
        except StaleDataError:return failure('Le brouillon a changé. Vos saisies restent dans le formulaire.',409)
        return jsonify(ok=True,invoice=invoice_payload(item))

    @app.post('/admin/appointments/invoices/<invoice_id>/issue')
    def admin_invoice_issue(invoice_id):
        denied=authorize(True)
        if denied:return denied
        item=item_or_404(invoice_id,True)
        if item.state=='issued':return jsonify(ok=True,invoice=invoice_payload(item))
        if item.state!='draft' or stale(item):return failure('Rechargez le dernier brouillon avant de l’émettre.',409)
        issuer,_=settings_data();data=unpack(item.data_json)
        if settings_missing(issuer):return failure('Complétez les coordonnées de facturation du cabinet dans Paramètres.')
        required=('patient_name','patient_street','patient_postcode','patient_city','examination','examination_date','billing_code','doctor_name','doctor_inami','mutuality')
        if any(not data.get(name) for name in required):return failure('Complétez le patient, son adresse, le médecin, la mutualité et l’examen avant d’émettre.')
        if len([c for c in data['patient_name'] if c.isalpha()])<5 or len(data['patient_name'].split())<2:return failure('Indiquez le prénom et le nom complets du patient.')
        if data['billing_code'] not in INTERNAL_INAMI_CODES or not re.fullmatch(r'\d{11}',data['doctor_inami']):return failure('Vérifiez le code de l’examen et le numéro INAMI du médecin.')
        try:exam_date=date.fromisoformat(data['examination_date'])
        except ValueError:return failure('Date de l’examen invalide.')
        today=now().date()
        if exam_date>today:return failure('Vous pouvez préparer le brouillon maintenant et l’émettre après réalisation de l’examen.')
        if data.get('insurance_status') not in {'normal','bim'}:return failure('Vérifiez l’assurabilité : statut normal ou BIM.')
        supplement=data['patient_cents']-data['ticket_cents']
        if supplement<0:return failure('Répartition patient invalide.')
        if supplement and data['insurance_status']=='bim':return failure('Un supplément pour cet examen remboursable n’est pas autorisé pour un patient BIM. Adaptez le montant patient au ticket applicable.')
        if supplement and (issuer.get('convention_status') not in {'non_conventionne','partiel'} or request.form.get('supplement_confirmed')!='1'):
            return failure('Vérifiez votre conventionnement et confirmez que le supplément est autorisé pour cette prestation.')
        if request.form.get('verified')!='1' or request.form.get('performed')!='1':return failure('Confirmez la réalisation de l’examen et la vérification des codes, tarifs et droits du patient.')
        # Allocate a number atomically in the same transaction as the immutable PDF.
        try:
            db.session.execute(text('INSERT INTO invoice_sequence (year,next_value) VALUES (:year,0) ON CONFLICT (year) DO NOTHING'),{'year':today.year})
            sequence=db.session.execute(text('UPDATE invoice_sequence SET next_value=next_value+1 WHERE year=:year RETURNING next_value'),{'year':today.year}).scalar_one()
            item.number=f'{PRACTICE_SHORT_NAME.upper()}-{today.year}-{sequence:05d}'
            item.invoice_date=today;item.due_date=today+timedelta(days=30);item.state='issued'
            item.issuer_json=json.dumps(issuer,ensure_ascii=False)
            item.pdf_data=create_invoice_pdf(data=data,issuer=issuer,number=item.number,invoice_date=today)
            item.updated_at=datetime.utcnow();db.session.commit()
        except (IntegrityError,StaleDataError):return failure('La facture vient de changer. Rechargez-la : aucun second numéro n’a été attribué.',409)
        except SQLAlchemyError:return failure('Émission non confirmée. Réessayez sans recréer le brouillon.',503)
        return jsonify(ok=True,invoice=invoice_payload(item))

    @app.get('/admin/appointments/invoices/<invoice_id>/pdf')
    def admin_invoice_pdf(invoice_id):
        denied=authorize()
        if denied:return denied
        item=item_or_404(invoice_id)
        if item.state=='issued':pdf=item.pdf_data
        else:pdf=create_invoice_pdf(data=unpack(item.data_json),issuer=settings_data()[0],number='BROUILLON-'+item.id[:8],invoice_date=now().date(),draft=True)
        response=make_response(pdf);response.headers['Content-Type']='application/pdf'
        response.headers['Content-Disposition']=('attachment' if request.args.get('download')=='1' else 'inline')+'; filename="facture-'+(item.number or item.id)+'.pdf"'
        response.headers['X-Content-Type-Options']='nosniff';response.headers['Cache-Control']='private, no-store'
        return response

    @app.post('/admin/appointments/invoices/<invoice_id>/email')
    def admin_invoice_email(invoice_id):
        denied=authorize(True)
        if denied:return denied
        item=item_or_404(invoice_id,True)
        if item.state!='issued':return failure('Émettez la facture avant son envoi.',409)
        connection=gmail_connection()
        if not connection:return failure('Connectez Gmail depuis l’agenda pour envoyer la facture.',503)
        recipient=request.form.get('recipient','').strip();token=request.form.get('delivery_token','')
        if not valid_email(recipient) or not re.fullmatch(r'[0-9a-f-]{36}',token):return failure('Vérifiez le destinataire et rechargez la facture.')
        if request.form.get('patient_agreement')!='1':return failure('Confirmez l’accord du patient et l’adresse du destinataire.')
        existing=db.session.get(InvoiceDelivery,token)
        if existing:
            if existing.invoice_id!=item.id or existing.recipient!=recipient:return failure('Cet envoi correspond à une autre opération.',409)
            if existing.status=='sent':return jsonify(ok=True,invoice=invoice_payload(item),message='Envoi déjà confirmé. Aucun doublon envoyé.')
            return failure('Cet envoi est en cours ou non confirmé. Vérifiez les messages envoyés avant un nouvel essai.',409)
        if item.email_state=='sent' and request.form.get('resend_confirmed')!='1':
            return failure('La facture a déjà été envoyée. Confirmez explicitement le renvoi pour envoyer un second message.',409)
        claimed=PatientInvoice.query.filter(PatientInvoice.id==item.id,PatientInvoice.email_state.notin_(['sending','uncertain'])).update({PatientInvoice.email_state:'sending'},synchronize_session=False)
        if claimed!=1:return failure('Un envoi est en cours ou reste à vérifier dans Gmail.',409)
        delivery=InvoiceDelivery(token=token,invoice_id=item.id,recipient=recipient)
        db.session.add(delivery)
        try:db.session.commit()
        except IntegrityError:return failure('Cette demande d’envoi existe déjà. Rechargez la facture.',409)
        try:
            provider_id=send_invoice(connection=connection,secret=app.secret_key,recipient=recipient,
                pdf=item.pdf_data,number=item.number,message_key='invoice-'+token)
        except ReportMailError as error:
            item=db.session.get(PatientInvoice,invoice_id);item.email_state='uncertain'
            delivery.status='uncertain';delivery.updated_at=datetime.utcnow();db.session.commit()
            return failure(str(error)+' Vérifiez les messages envoyés avant de réactiver l’envoi.',502)
        item=db.session.get(PatientInvoice,invoice_id);item.email_state='sent';item.last_recipient=recipient;item.last_sent_at=datetime.utcnow()
        delivery.status='sent';delivery.provider_id=provider_id;delivery.updated_at=datetime.utcnow()
        try:db.session.commit()
        except SQLAlchemyError:return failure('Gmail a accepté le message, mais le suivi local reste à vérifier. Ne renvoyez pas la facture sans vérifier Gmail.',503)
        return jsonify(ok=True,invoice=invoice_payload(item),message='La facture a été confiée à Gmail pour '+recipient+'.')

    @app.post('/admin/appointments/invoices/<invoice_id>/delivery/reset')
    def admin_invoice_delivery_reset(invoice_id):
        denied=authorize(True)
        if denied:return denied
        item=item_or_404(invoice_id,True)
        if item.email_state not in {'sending','uncertain'} or request.form.get('verified_not_sent')!='1':return failure('Vérifiez les messages envoyés avant de réactiver l’envoi.')
        # Pending requests older than two minutes may have lost their response.
        pending=InvoiceDelivery.query.filter_by(invoice_id=item.id).filter(InvoiceDelivery.status.in_(['pending','uncertain'])).all()
        if any(d.status=='pending' and datetime.utcnow()-d.created_at<timedelta(minutes=2) for d in pending):return failure('Attendez la fin de l’envoi en cours.',409)
        for delivery in pending:delivery.status='reviewed';delivery.updated_at=datetime.utcnow()
        item.email_state='idle';db.session.commit()
        return jsonify(ok=True,invoice=invoice_payload(item))

    @app.post('/admin/appointments/invoices/<invoice_id>/payment')
    def admin_invoice_payment(invoice_id):
        denied=authorize(True)
        if denied:return denied
        item=item_or_404(invoice_id,True)
        if item.state!='issued' or stale(item):return failure('Rechargez une facture émise avant de modifier son paiement.',409)
        raw=request.form.get('paid_on','')
        try:paid=date.fromisoformat(raw) if raw else None
        except ValueError:return failure('Date de paiement invalide.')
        if paid and not item.invoice_date<=paid<=now().date():return failure('Le paiement doit se situer entre la date de facture et aujourd’hui.')
        item.paid_on=paid;db.session.commit()
        return jsonify(ok=True,invoice=invoice_payload(item))
