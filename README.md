# mcq-quiz

## Local run

```bash
cd /Users/dr.youssef/python-quiz-web
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Render auto-deploy

This repo includes [render.yaml](/Users/dr.youssef/python-quiz-web/render.yaml) so Render can create the web service and Postgres database from the repo itself.

Steps:

1. Push this repo to GitHub.
2. In Render, click `New +` -> `Blueprint`.
3. Select this GitHub repo.
4. Render will read `render.yaml`, create the web service and database, and enable `autoDeploy`.
5. Every later push to `main` will trigger a new deploy automatically.

Current service settings from `render.yaml`:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Auto deploy: enabled
- Database: Postgres linked to `DATABASE_URL`

## Internal report e-mail

### Internal patient workspace

**XIMEO-RIZIV** shows all agenda patients/reservations and paper-era records in
one chronological document workspace. The separate **Liste RIZIV** remains
available with the same records. Agenda entries open their existing patient
workspace and retain their original requests, reports and identifiers; displaying
them here does not copy records or create historical dossiers.

**Ajouter un ancien dossier** registers paper-era records
in separate additive `historical_dossier` / `historical_document` tables. These
records never create, occupy or reopen a booking slot. Enter the actual historical
examination date (not a future date), name and examination. The national-register
number is the patient-facing dossier number and is required for new historical
records (11 digits). It is deliberately not unique: several examinations of the
same patient retain separate records and documents with the same dossier number.
Older records without a number remain editable so they can be completed.
A scanned request and scanned original report can each be
uploaded as an unencrypted PDF (10 MiB / 200 pages maximum). Original files are
kept separately in the private database and are not overwritten. Repeat uploads
of identical bytes are safe. Word originals should be exported to PDF before upload.

The same panel also has an editable plain-text report field: paste text recognized
by the user's phone app, correct it, enter the actual report date and save. No OCR
service is called by this app and no clinical findings are generated. A saved text
opens read-only with an explicit edit action. Copy, print and download support
manual transfer. Generating a text-based PDF requires the user's review checkbox;
editing the text/date/radiologist clears that checkbox. The historical PDF displays
the examination date only: no invented appointment time. The original scan is
retained alongside the text, not replaced by the reconstructed PDF.

Manual workflow flags are **À compléter**, **Prêt à transférer** and **Transféré
manuellement**. The latter two require the request scan plus either an original
report PDF or a reviewed text report. The flags do not send anything or prove that
another system received data. Historical entries are included chronologically in
the total RIZIV overview/export, explicitly labelled historical and with a blank
time column. No tariffs/revenue are invented for them. Metadata/report saves use
revision checks and creation retry keys; unsaved text stays in memory with an exit
warning, never browser storage. All document access is admin-only and no-store.

Historical flow checks: `python scripts/smoke_test_historical_dossiers.py`.
Use `--serve` for a disposable localhost preview with synthetic data; `--pdf-preview`
writes a synthetic report to `/private/tmp/historical-dossier-pdf-qa/` for rendering.

The private agenda has **Agenda** and **Liste patients** views. The patient list
is chronological within the selected week. Clicking a patient opens a side panel;
on desktop the calendar remains usable beside it, and on phones the panel uses
the available screen. Existing reports open read-only; editing is explicit.
**Copier le texte**, PDF/print/download and previous/next patient support manual
transfer to another system. No transfer to another medical application is automatic.

**Liste RIZIV · Tous les patients** loads an administrator-only chronological
overview across all dates, independent of the current week. It includes registered
appointments and reservations, including future dates, with one row per booking
(repeat visits are not deduplicated by name). A stale hold at an already confirmed
timestamp is not counted twice. This is an internal register, not proof that an
examination was performed and not a validated official submission format.
Patient names open the same side-panel dossier, with previous/next navigation
scoped to the currently selected list. Editing an identifier updates both lists.
**Imprimer** prints just this overview; **Télécharger le CSV** exports its current
all-time database contents in chronological order. CSV uses UTF-8 with BOM and
semicolon separators; identifier digits (including initial zeroes) remain intact
in the file, so import that column as text in spreadsheet software. Names and exam
labels are protected against spreadsheet formula injection. No prices, BIM status,
e-mails, phone numbers, report text or attachments are included. The app does not
send the register to RIZIV/INAMI or to any other recipient automatically.

Each booking (including an existing reservation) can store one private examination
request. **Scanner / importer la demande** imports a PDF produced by the scanner's
own software; it does not directly operate scanner hardware. New imports are limited
to a readable, unencrypted PDF of at most 10 MiB / 200 pages, stored in the existing
database binary fields, never under public static files. Once present, the upload
action becomes **Voir la demande** / **Télécharger la demande**. Existing image
prescriptions remain accessible. Replacing an existing request is deliberately
not allowed. The optional national-register number is entered manually in the
private panel (11 digits; format validation only, not identity verification),
stored per booking in the additive `appointment_patient_details` table. It is
not added to public pages, e-mails or PDFs.

Date headers open quick day controls. Closing/reopening is asynchronous and only
changes future unoccupied slots, preserving confirmed appointments and reservations.
Reopening uses the usual consultation hours plus previously configured custom
slots; it does not open 24 hours or bypass Saturday / 18:10–18:20 restrictions.

Saving has a 25-second client timeout, retains the editor's text on failure, and
allows safe retries of identical content after a lost response. Version conflicts
never silently overwrite another editor's changes. Edits made while a save is
pending remain marked unsaved. There is no browser localStorage/sessionStorage
copy of patient documents; unsaved text exists only in the open page, so the exit
warning must not be ignored. The week overview defers prescription binary data
until an individual patient's request is opened.

Isolated checks (temporary SQLite DB, synthetic patients only, no real e-mails):
`python scripts/smoke_test_internal_workspace.py`.
Add `--serve` for a localhost-only synthetic preview on port 5057; test login
`y@bymed.be` / `test-password` exists only in that disposable preview database.

The internal reporting window can send a saved report as a PDF attachment to one
manually entered recipient. Sending first saves unsaved changes. Only administrators
can use this action; nothing is sent automatically when saving a report.

### Google login and Gmail (preferred)

An additional Google login is available for existing administrator accounts in
`ADMIN_EMAILS`; normal password login remains available. A successful Google login
also connects that administrator's own Gmail mailbox. The app never creates or
promotes a user based on a Google login. A verified Google identity is required,
with Gmail send permission. Google refresh tokens are encrypted in the database
using the existing persistent `SECRET_KEY`; keep that key stable across deploys.

One-time Google Cloud setup:

1. Enable the Gmail API in the practice's Google Cloud project.
2. Configure the OAuth consent screen for the practice and create a **Web application** client.
3. Register the exact callback URL, for example `https://bymed.be/auth/google/callback`.
4. Set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and
   `GOOGLE_OAUTH_REDIRECT_URI` in Render. The last value must exactly match the registered callback.
5. Open the website and select **Se connecter avec Google · Admin** using `y@bymed.be`.
   Grant Gmail sending permission once. An administrator already logged in with a password
   can also select **Connecter Google / Gmail** in the internal agenda.

The requested scopes are OpenID/email identity and `gmail.send`, not mailbox reading.
Google OAuth apps in external Testing mode can have expiring grants; configure the
appropriate production consent status for lasting use. Follow Google's
[web-server OAuth setup](https://developers.google.com/identity/protocols/oauth2/web-server).
Do not paste client secrets or refresh tokens into chat, source files or browser storage.
If the site secret changes, reconnect Gmail. Individual administrators cannot use
another administrator's Gmail connection. A Gmail request is never retried automatically;
if a network error leaves the result uncertain, check Gmail's Sent folder first.

### Optional Resend fallback

If no Gmail account is connected, delivery can use the [Resend HTTPS API](https://resend.com/docs/api-reference/emails/send-email).
In the Render web service's Environment settings, configure:

- `RESEND_API_KEY`: a sending API key for the practice's Resend account.
- `REPORT_EMAIL_FROM`: a verified sender, for example `Bymed Radiologie <radiologie@bymed.be>`.

Verify the sender domain in Resend before enabling real sending. Keep the API key
in Render's secret environment settings, never in Git or chat. The Resend fallback
stays disabled until both settings exist. No SMTP configuration is necessary.
Render Free services [block the usual SMTP ports](https://render.com/docs/free#other-limitations).

The response confirms acceptance by the sending service, not delivery to the
recipient's inbox. Network failures keep the report saved. Repeating an uncertain
Resend attempt from the same open window within 24 hours reuses an idempotency key to avoid duplicates;
after a successful send, a new click is a new intentional send.
