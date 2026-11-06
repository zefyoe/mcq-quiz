"""Synthetic-only checks for legacy scans, pasted text and manual transfer status."""
import csv
import io
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

fixture = tempfile.TemporaryDirectory(prefix="historical-dossier-tests-")
db_path = Path(fixture.name)/"test.db"
os.environ.update(DATABASE_URL="sqlite:///"+str(db_path),SECRET_KEY="history-tests-only",PUBLIC_SITE_MODE="active")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app, db, agenda_now
from models import Appointment, AppointmentHold, AppointmentSlotOverride, HistoricalDossier, HistoricalDocument, User
from pypdf import PdfReader, PdfWriter
from sqlalchemy.exc import OperationalError

app.config["TESTING"]=True
writer=PdfWriter(); writer.add_blank_page(width=595,height=842)
buffer=io.BytesIO(); writer.write(buffer); scan=buffer.getvalue()
scan_path=Path(fixture.name)/"scan-fictif.pdf"; scan_path.write_bytes(scan)
url="/admin/appointments/history"
try:
    with app.app_context():
        db.create_all()
        for email,role in [("y@bymed.be",True),("student@example.invalid",False)]:
            user=User(email=email,is_admin=role); user.set_password("test-password"); db.session.add(user)
        db.session.add(Appointment(starts_at=agenda_now()+timedelta(days=7),patient_name="PATIENT CALENDRIER",patient_email="",appointment_type="459712"))
        db.session.commit()
    admin,student,anonymous=app.test_client(),app.test_client(),app.test_client()
    for client,email in [(admin,"y@bymed.be"),(student,"student@example.invalid")]:
        client.post("/login",data={"email":email,"password":"test-password"})
    assert admin.get("/admin/appointments").status_code==200
    with admin.session_transaction() as session: csrf=session["agenda_token"]
    before=anonymous.get("/agenda").data
    for route in [url,url+"/999",url+"/999/documents/request",url+"/999/report.pdf"]:
        assert anonymous.get(route).status_code==302
        assert student.get(route).status_code==403
    assert admin.post(url,data={}).status_code==400
    payload=dict(csrf_token=csrf,creation_key=str(uuid4()),revision="0",patient_name="Jo Jao",
        national_number="00123456789",examined_on="2026-01-14",examination="Échographie abdominale",
        report_text="",report_date="",radiologist="",transfer_status="todo")
    assert admin.post(url,data=dict(payload,examined_on="")).status_code==400
    assert admin.post(url,data=dict(payload,examined_on=(date.today()+timedelta(days=30)).isoformat())).status_code==400
    assert admin.post(url,data=dict(payload,national_number="123")).status_code==400
    assert admin.post(url,data=dict(payload,transfer_status="ready")).status_code==400
    created=admin.post(url,data=payload)
    assert created.status_code==200,created.data
    original=created.json["dossier"]; did=original["id"]
    assert original["national_number"]=="00123456789" and original["revision"]==1
    assert admin.post(url,data=payload).json["dossier"]["id"]==did
    assert admin.get(url+f"/{did}/report.pdf").status_code==400
    text="Texte de démonstration uniquement.\n\nConclusion : document fictif pour tester la mise en page."
    edit=dict(payload,dossier_id=did,revision=1,report_text=text)
    assert admin.post(url,data=edit).status_code==400  # No invented report date.
    edit["report_date"]="2026-01-14"
    written=admin.post(url,data=edit)
    assert written.status_code==200,written.data
    edit["revision"]=written.json["dossier"]["revision"]
    assert admin.get(url+f"/{did}/report.pdf").status_code==400  # OCR text needs human review.
    edit["report_reviewed"]="1"
    reviewed=admin.post(url,data=edit); assert reviewed.status_code==200
    edit["revision"]=reviewed.json["dossier"]["revision"]
    pdf=admin.get(url+f"/{did}/report.pdf")
    assert pdf.status_code==200 and pdf.data.startswith(b"%PDF-")
    pdf_text="\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.data)).pages)
    assert "14/01/2026" in pdf_text and "00:00" not in pdf_text and "Rendez-vous" not in pdf_text
    assert "00123456789" not in pdf_text and "document fictif" in pdf_text
    def upload(kind,data=scan,name="scan-fictif.pdf"):
        return admin.post(url+f"/{did}/documents/{kind}",data={"csrf_token":csrf,"file":(io.BytesIO(data),name)},content_type="multipart/form-data")
    assert upload("request",b"not PDF").status_code==400
    assert upload("request",b"%PDF-1.7\ninvalid").status_code==400
    assert upload("request",scan,"scan.docx").status_code==400
    assert upload("request",b"%PDF-"+b"a"*(10*1024*1024)).status_code==400
    assert admin.post(url+f"/{did}/documents/request",data={"file":(io.BytesIO(scan),"scan.pdf")}).status_code==400
    accepted=upload("request"); assert accepted.status_code==200,accepted.data
    assert upload("request").status_code==200  # Retry doesn't duplicate or overwrite.
    # A reviewed text report can be used instead of retyping a paper report again.
    ready=admin.post(url,data=dict(edit,transfer_status="ready"))
    assert ready.status_code==200,ready.data
    edit["revision"]=ready.json["dossier"]["revision"]
    transferred=admin.post(url,data=dict(edit,transfer_status="transferred"))
    assert transferred.status_code==200
    edit.update(revision=transferred.json["dossier"]["revision"],transfer_status="transferred")
    assert upload("report").status_code==200  # Original scan coexists with editable text.
    other=PdfWriter(); other.add_blank_page(width=600,height=842); out=io.BytesIO(); other.write(out)
    assert upload("request",out.getvalue()).status_code==409
    assert upload("unknown").status_code==404
    saved=admin.get(url+f"/{did}").json["dossier"]
    assert saved["report_text"]==text and set(saved["documents"])=={"request","report"}
    for document in saved["documents"].values():
        for key,disposition in [("view_url","inline"),("download_url","attachment")]:
            response=admin.get(document[key]); assert response.data==scan
            assert response.headers["Content-Disposition"].startswith(disposition)
            assert response.headers["Cache-Control"]=="private, no-store"
            assert anonymous.get(document[key]).status_code==302
    assert admin.post(url,data=dict(edit,revision=0,report_text="Another version")).status_code==409
    with patch.object(db.session,"commit",side_effect=OperationalError("test",{},Exception("offline"))):
        failed=admin.post(url,data=dict(edit,examination="Examen modifié"))
    assert failed.status_code==503
    assert admin.get(url+f"/{did}").json["dossier"]["examination"]=="Échographie abdominale"
    second=admin.post(url,data=dict(payload,creation_key=str(uuid4())))
    assert second.status_code==200 and second.json["dossier"]["id"]!=did
    with app.app_context():
        assert HistoricalDossier.query.count()==2 and HistoricalDocument.query.count()==2
        assert Appointment.query.count()==1 and AppointmentHold.query.count()==0 and AppointmentSlotOverride.query.count()==0
    assert anonymous.get("/agenda").data==before  # No fake appointment/availability side effects.
    listing=admin.get(url); assert listing.json["total"]==2 and b"Jo Jao" in listing.data
    assert listing.headers["Cache-Control"]=="private, no-store"
    all_patients=admin.get("/admin/appointments/riziv").json
    assert all_patients["total"]==3 and "Dossier historique" in all_patients["html"]
    exported=admin.get("/admin/appointments/riziv.csv")
    rows=list(csv.reader(io.StringIO(exported.data.decode("utf-8-sig")),delimiter=";"))
    assert rows[1][2]=="" and rows[1][4]=="00123456789" and "historique" in rows[1][-1]
    assert "Texte de démonstration" not in exported.data.decode("utf-8-sig")
    assert b"Jo Jao" not in anonymous.get("/agenda").data
    if "--pdf-preview" in sys.argv:
        preview=Path("/private/tmp/historical-dossier-pdf-qa")
        preview.mkdir(exist_ok=True)
        (preview/"historical-report.pdf").write_bytes(pdf.data)
        print("Synthetic PDF preview:",preview/"historical-report.pdf")
    print("PASS: historical dossiers, pasted/reviewed text, original PDF scans, idempotency/conflicts/outage, private access, manual workflow, date-only PDF and RIZIV integration without booking side effects.")
    if "--serve" in sys.argv:
        print("Synthetic upload fixture:",scan_path,flush=True)
        print("Local preview: http://127.0.0.1:5057/admin/appointments",flush=True)
        app.run(host="127.0.0.1",port=5057,debug=False)
finally:
    with app.app_context(): db.session.remove(); db.engine.dispose()
    fixture.cleanup()
