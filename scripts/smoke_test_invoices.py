"""Isolated invoice/letter tests. Temporary database and mocked mail only."""
import io,json,os,re,sys,tempfile,uuid
from datetime import date,datetime,timedelta
from pathlib import Path
from unittest.mock import patch

fixture=tempfile.TemporaryDirectory(prefix='invoice-tests-')
os.environ.update(PRACTICE_PROFILE='wirc',WIRC_DATABASE_URL='sqlite:///'+str(Path(fixture.name)/'invoices.db'),
 DATABASE_URL='sqlite:///never-use-former.db',SECRET_KEY='invoice-test-only',PUBLIC_SITE_MODE='active',APPOINTMENT_BOOKING_ENABLED='1',
 APPOINTMENT_PRACTICE_ADDRESS='Adresse fictive du cabinet',GOOGLE_OAUTH_CLIENT_ID='test-client',GOOGLE_OAUTH_CLIENT_SECRET='test-secret',GOOGLE_OAUTH_REDIRECT_URI='https://wirc.be/auth/google/callback')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app,db,appointment_report_key
from models import (User,Appointment,AppointmentHold,HistoricalDossier,GmailConnection,PatientInvoice,InvoiceSettings,InvoiceSequence,InvoiceDelivery,AppointmentSlotOverride)
from invoice_pdf import create_invoice_pdf
from pypdf import PdfReader
from report_mail import ReportMailError

app.config['TESTING']=True
base='/admin/appointments/invoices'
try:
 with app.app_context():
  db.create_all()
  owner=User(email='y@bymed.be',is_admin=True);owner.set_password('test-password');db.session.add(owner)
  other=User(email='student@example.invalid',is_admin=False);other.set_password('test-password');db.session.add(other);db.session.flush()
  db.session.add(GmailConnection(user_id=owner.id,email=owner.email,google_subject='test-subject',encrypted_refresh_token='never-used'))
  past=Appointment(starts_at=datetime(2026,11,14,8),patient_name='Patient Fictif',patient_email='patient@example.invalid',appointment_type='459712',inami_code='459712')
  future=Appointment(starts_at=datetime(2026,12,3,8),patient_name='Patient Futur',patient_email='',appointment_type='459712',inami_code='459712')
  history=HistoricalDossier(creation_key='fixture',patient_name='Patient Historique',national_number='00123456789',billing_code='459734',examined_on=date(2026,11,14),examination='Échographie urinaire')
  db.session.add_all([past,future,history]);db.session.commit();aid,fid,hid=past.id,future.id,history.id
 owner=app.test_client();anon=app.test_client();student=app.test_client()
 assert owner.post('/login',data={'email':'y@bymed.be','password':'test-password'}).status_code==302
 assert owner.get('/admin/appointments').status_code==200
 with owner.session_transaction() as session:csrf=session['agenda_token']
 def post(url,**values):return owner.post(url,data={'csrf_token':csrf,**values})
 assert anon.get(base).status_code==302 and anon.post(base).status_code==302
 assert anon.get(base+'/tariff/459712').status_code==302
 assert anon.post(base+'/patients/search',data={'q':'Patient'}).status_code==302
 assert owner.get(base+'/tariff/459712').json['insurance_cents']==6598
 assert owner.get(base+'/tariff/461974').status_code==404
 assert post(base,appointment_id=aid,csrf_token='bad').status_code==400
 # Unapproved WIRC users cannot even establish a private session.
 student.post('/login',data={'email':'student@example.invalid','password':'test-password'})
 assert student.get(base).status_code in {302,403}
 assert student.post(base+'/patients/search',data={'q':'Patient'}).status_code in {302,403}
 assert post(base+'/patients/search',q='Patient',csrf_token='bad').status_code==400
 assert post(base+'/patients/search',q='P').json['patients']==[]
 assert post(base+'/patients/search',q='x'*121).status_code==400
 # Search returns distinct exams, including reservations and old dossiers,
 # without downloading scans/reports or treating SQL wildcards as a name.
 stamp=datetime(2026,12,3,10)
 with app.app_context():
  twin=Appointment(starts_at=stamp+timedelta(hours=1),patient_name='Patient Fictif',patient_email='',appointment_type='459734',inami_code='459734')
  db.session.add(twin)
  db.session.add_all([
   AppointmentHold(starts_at=stamp,token='search-test',expires_at=stamp,draft_data=json.dumps({'patient_name':'Patient Réservé','inami_code':'459712'})),
   AppointmentHold(starts_at=stamp+timedelta(minutes=10),token='empty-search',expires_at=stamp,draft_data='{}'),
   AppointmentHold(starts_at=stamp+timedelta(minutes=20),token='old-search',expires_at=stamp,draft_data='not valid JSON')])
  db.session.commit();twin_id=twin.id
 found=post(base+'/patients/search',q='  patient  ').json['patients']
 assert len(found)==5 and len({row['patient_name'] for row in found})==4
 assert any(row.get('historical_id')==hid for row in found)
 assert any(row.get('reservation_start')=='2026-12-03T10:00' for row in found)
 assert all('report_text' not in row and 'national_number' not in row and 'patient_email' not in row for row in found)
 repeated=post(base+'/patients/search',q='  FICTIF   patient ').json['patients']
 assert len(repeated)==2 and repeated[0]['appointment_id']==aid and repeated[0]['starts_at']!=repeated[1]['starts_at']
 assert post(base+'/patients/search',q='%_').json['patients']==[]
 assert post(base+'/patients/search',q='Absent Inconnu').json['patients']==[]
 with app.app_context():
  AppointmentHold.query.filter(AppointmentHold.starts_at>=stamp).delete();db.session.commit()
  Appointment.query.filter_by(id=twin_id).delete();db.session.commit()
 settings=owner.get(base+'/settings').json
 assert settings['settings']['default_patient_cents']==2000 and settings['missing']
 created=post(base,appointment_id=aid)
 assert created.status_code==200,created.data
 inv=created.json['invoice'];iid=inv['id'];url=base+'/'+iid
 assert inv['state']=='draft' and not inv['number'] and inv['data']['patient_cents']==2000
 assert post(base,appointment_id=aid).json['invoice']['id']==iid
 found=post(base+'/patients/search',q='patient fictif')
 assert found.headers['Cache-Control']=='private, no-store'
 assert found.json['patients'][0]['invoice_id']==iid
 assert owner.get(base).status_code==200
 assert post(url+'/issue',revision=inv['revision'],performed='1',verified='1').status_code==400
 # Protect every invoice endpoint, including raw PDF and sending controls.
 for suffix in ('','/pdf','/issue','/email','/payment','/delivery/reset'):
  response=anon.get(url+suffix) if suffix in ('','/pdf') else anon.post(url+suffix)
  assert response.status_code==302,(suffix,response.status_code)
 assert anon.get('/agenda').status_code==200
 public=anon.get('/agenda').text
 for value in ('Factures patients','invoice-editor','Patient Fictif','patient@example.invalid','2000'):
  assert value not in public,value
 issuer=dict(revision=0,legal_name='Cabinet Fictif - Exemple',display_name='WIRC - Exemple',address='Rue Exemple 12\n1000 Bruxelles',enterprise_number='01234567'+str(97-int('01234567')%97).zfill(2),
  doctor_name='Dr Médecin Fictif',doctor_inami='12345678901',account_holder='Compte de démonstration',iban='BE68 5390 0754 7034',bic='',email='cabinet@example.invalid',phone='',vat_note='',default_patient_amount='20',convention_status='non_conventionne')
 assert post(base+'/settings',**dict(issuer,iban='BE001234')).status_code==400
 saved=post(base+'/settings',**issuer)
 assert saved.status_code==200,saved.data
 issuer_revision=saved.json['revision']
 assert post(base+'/settings',**issuer).status_code==409
 data=dict(inv['data']);payload={k:str(v) for k,v in data.items() if isinstance(v,str)}
 payload.update(patient_street='Rue du Patient 7, boîte 2',patient_postcode='1000',patient_city='Bruxelles',patient_country='Belgique',doctor_name=issuer['doctor_name'],doctor_inami=issuer['doctor_inami'],mutuality='Mutualité fictive',insurance_status='normal',patient_amount='20.00',ticket_amount='2.48',insurance_amount='65.98')
 assert post(url,revision=inv['revision'],**dict(payload,patient_amount='nan')).status_code==400
 updated=post(url,revision=inv['revision'],**payload)
 assert updated.status_code==200,updated.data
 inv=updated.json['invoice']
 assert inv['data']['patient_cents']==2000 and inv['data']['insurance_cents']==6598
 assert post(url,revision=1,**payload).status_code==409
 draft=owner.get(url+'/pdf')
 assert draft.status_code==200 and draft.data.startswith(b'%PDF-')
 draft_text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(draft.data)).pages)
 assert 'BROUILLON' in draft_text and '20,00 EUR' in draft_text
 assert post(url+'/issue',revision=inv['revision'],performed='1',verified='1').status_code==400 # supplement must be confirmed
 # BIM never silently receives the proposed 20 EUR as a supplement.
 bim=post(url,revision=inv['revision'],**dict(payload,insurance_status='bim')).json['invoice']
 assert post(url+'/issue',revision=bim['revision'],performed='1',verified='1',supplement_confirmed='1').status_code==400
 inv=post(url,revision=bim['revision'],**payload).json['invoice']
 issued=post(url+'/issue',revision=inv['revision'],performed='1',verified='1',supplement_confirmed='1')
 assert issued.status_code==200,issued.data
 inv=issued.json['invoice'];assert inv['state']=='issued' and inv['number'].endswith('-00001')
 assert date.fromisoformat(inv['due_date'])-date.fromisoformat(inv['invoice_date'])==timedelta(days=30)
 assert post(url+'/issue',revision=inv['revision'],performed='1',verified='1',supplement_confirmed='1').json['invoice']['number']==inv['number']
 assert post(url,revision=inv['revision'],**payload).status_code==409
 final=owner.get(url+'/pdf');assert final.headers['Cache-Control']=='private, no-store'
 final_text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(final.data)).pages)
 for value in ('20,00 EUR','65,98 EUR','17,52 EUR','85,98 EUR','459712','Rue du Patient','BE68539007547034',inv['number']):assert value in final_text,value
 assert 'BROUILLON' not in final_text
 # Updating issuer/account details affects new drafts, never an issued PDF.
 assert post(base+'/settings',**dict(issuer,revision=issuer_revision,account_holder='Nouveau titulaire fictif')).status_code==200
 assert owner.get(url+'/pdf').data==final.data
 # All Gmail traffic is stubbed. Repeat tokens and accidental second sends do not duplicate mail.
 sent=[]
 def send(**kwargs):sent.append(kwargs);return 'fake-gmail-id'
 token=str(uuid.uuid4());mail=dict(recipient='patient@example.invalid',delivery_token=token,patient_agreement='1')
 with patch('app.send_gmail_invoice',side_effect=send):
  assert post(url+'/email',**dict(mail,recipient='a,b@example.invalid')).status_code==400
  assert post(url+'/email',**dict(mail,patient_agreement='0')).status_code==400
  first=post(url+'/email',**mail);assert first.status_code==200,first.data
  assert post(url+'/email',**mail).status_code==200
  assert post(url+'/email',**dict(mail,delivery_token=str(uuid.uuid4()))).status_code==409
 assert len(sent)==1 and sent[0]['pdf']==final.data and sent[0]['recipient']=='patient@example.invalid'
 # Inspect the actual Gmail MIME envelope without contacting Google.
 from types import SimpleNamespace
 from unittest.mock import MagicMock
 from email import policy
 from email.parser import BytesParser
 import base64
 from gmail_reporting import send_gmail_invoice
 credentials=MagicMock();credentials.token='test-access-token'
 response=MagicMock();response.json.return_value={'id':'test-message-id'}
 cipher=MagicMock();cipher.decrypt.return_value=b'test-refresh-token'
 with patch('gmail_reporting.token_cipher',return_value=cipher),patch('gmail_reporting.Credentials',return_value=credentials),patch('gmail_reporting.requests.post',return_value=response) as transport:
  assert send_gmail_invoice(connection=SimpleNamespace(email='y@bymed.be',encrypted_refresh_token='test'),secret='test',recipient='patient@example.invalid',pdf=final.data,number=inv['number'],message_key='test-invoice')=='test-message-id'
  mime=BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(transport.call_args.kwargs['json']['raw']))
  assert str(mime['To'])=='patient@example.invalid' and inv['number'] in str(mime['Subject'])
  assert 'Compte rendu' not in str(mime['Subject'])
  attachment=list(mime.iter_attachments())[0]
  assert attachment.get_filename()=='facture-'+inv['number']+'.pdf' and attachment.get_payload(decode=True)==final.data
 with patch('app.send_gmail_invoice',side_effect=ReportMailError('Test : envoi non confirmé')):
  uncertain=post(url+'/email',**dict(mail,delivery_token=str(uuid.uuid4()),resend_confirmed='1'))
  assert uncertain.status_code==502
  assert post(url+'/email',**dict(mail,delivery_token=str(uuid.uuid4()),resend_confirmed='1')).status_code==409
  assert post(url+'/delivery/reset',verified_not_sent='0').status_code==400
  assert post(url+'/delivery/reset',verified_not_sent='1').status_code==200
 current=owner.get(url).json['invoice']
 assert post(url+'/payment',revision=current['revision'],paid_on=current['invoice_date']).status_code==200
 assert post(url+'/payment',revision=current['revision'],paid_on='').status_code==409
 # One person can have different exams/invoices. Historical records remain billable.
 historical=post(base,historical_id=hid)
 assert historical.status_code==200 and historical.json['invoice']['id']!=iid
 assert historical.json['invoice']['data']['national_number']=='00123456789'
 future_inv=post(base,appointment_id=fid).json['invoice'];future_url=base+'/'+future_inv['id']
 future_payload=dict(payload,patient_name='Patient Futur',examination_date='2026-12-03')
 future_inv=post(future_url,revision=future_inv['revision'],**future_payload).json['invoice']
 assert post(future_url+'/issue',revision=future_inv['revision'],performed='1',verified='1',supplement_confirmed='1').status_code==400
 # Draft association follows a move and does not create another invoice.
 with app.app_context():
  record=db.session.get(Appointment,fid);key=appointment_report_key(record)
 move=post('/admin/appointments/move',appointment_id=fid,expected_start='2026-12-03T08:00:00',expected_key=key,target_start='2026-12-03T08:10',move_token=str(uuid.uuid4()))
 assert move.status_code==200,move.data
 assert post(base,appointment_id=fid).json['invoice']['id']==future_inv['id']
 moved=post(base+'/patients/search',q='patient futur').json['patients'][0]
 assert moved['starts_at']=='2026-12-03T08:10' and moved['invoice_id']==future_inv['id']
 # Parallel clicks and concurrent issuance cannot create duplicate drafts or numbers.
 from concurrent.futures import ThreadPoolExecutor
 from threading import Barrier
 with app.app_context():
  parallel=Appointment(starts_at=datetime(2026,11,14,9),patient_name='Patient Parallèle',patient_email='',appointment_type='459712',inami_code='459712')
  db.session.add(parallel);db.session.commit();parallel_id=parallel.id
 clients=[]
 for _ in range(2):
  client=app.test_client();client.post('/login',data={'email':'y@bymed.be','password':'test-password'});client.get('/admin/appointments')
  with client.session_transaction() as session:token_value=session['agenda_token']
  clients.append((client,token_value))
 barrier=Barrier(2)
 def create_parallel(args):
  client,token_value=args;barrier.wait();return client.post(base,data={'csrf_token':token_value,'appointment_id':parallel_id})
 with ThreadPoolExecutor(max_workers=2) as pool:created_parallel=list(pool.map(create_parallel,clients))
 assert all(r.status_code==200 for r in created_parallel),[r.status_code for r in created_parallel]
 assert len({r.json['invoice']['id'] for r in created_parallel})==1
 parallel_invoice=created_parallel[0].json['invoice'];parallel_url=base+'/'+parallel_invoice['id']
 parallel_invoice=post(parallel_url,revision=parallel_invoice['revision'],**dict(payload,patient_name='Patient Parallèle')).json['invoice']
 barrier=Barrier(2)
 def issue_parallel(args):
  client,token_value=args;barrier.wait();return client.post(parallel_url+'/issue',data=dict(csrf_token=token_value,revision=parallel_invoice['revision'],performed='1',verified='1',supplement_confirmed='1'))
 with ThreadPoolExecutor(max_workers=2) as pool:issued_parallel=list(pool.map(issue_parallel,clients))
 assert any(r.status_code==200 for r in issued_parallel),[r.status_code for r in issued_parallel]
 assert all(r.status_code in {200,409,503} for r in issued_parallel),[r.status_code for r in issued_parallel]
 assert owner.get(parallel_url).json['invoice']['number'].endswith('-00002')
 with app.app_context():
  assert PatientInvoice.query.count()==4 and InvoiceSequence.query.one().next_value==2
  assert InvoiceDelivery.query.count()==2
 # Optional local preview is synthetic; provider remains unavailable for real sending.
 if '--pdf-example' in sys.argv:
  example_data=dict(inv['data'],_example=True)
  output=Path('output/pdf/facture-exemple-wirc.pdf');output.parent.mkdir(parents=True,exist_ok=True)
  output.write_bytes(create_invoice_pdf(data=example_data,issuer=issuer,number='WIRC-EXEMPLE-001',invoice_date=date(2026,11,15)))
 if '--serve' in sys.argv:
  # Never connect a preview to a real account. Remove the dummy Gmail connection.
  with app.app_context():
   GmailConnection.query.delete()
   db.session.add(Appointment(starts_at=datetime(2026,11,15,10),patient_name='Test Test',patient_email='',appointment_type='459734',inami_code='459734'))
   db.session.commit()
  app.jinja_env.auto_reload=True
  app.jinja_env.cache=None
  app.run(host='127.0.0.1',port=5059,debug=False)
 print('PASS: private patient search (repeat exams, historical dossiers, reservations, matching existing invoices), draft deduplication, editable patient amount, BIM/supplement guards, immutable numbered PDF, 30-day due date, provider settings snapshots, future exam guard, Gmail idempotency/uncertain-send recovery, payment tracking and move continuity.')
finally:
 with app.app_context():db.session.remove();db.engine.dispose()
 fixture.cleanup()
