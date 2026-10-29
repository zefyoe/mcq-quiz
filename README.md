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

The internal reporting window can send a saved report as a PDF attachment to one
manually entered recipient. Sending first saves unsaved changes. Only administrators
can use this action; nothing is sent automatically when saving a report.

Delivery uses the [Resend HTTPS API](https://resend.com/docs/api-reference/emails/send-email).
In the Render web service's Environment settings, configure:

- `RESEND_API_KEY`: a sending API key for the practice's Resend account.
- `REPORT_EMAIL_FROM`: a verified sender, for example `Bymed Radiologie <radiologie@bymed.be>`.

Verify the sender domain in Resend before enabling real sending. Keep the API key
in Render's secret environment settings, never in Git or chat. The e-mail form
stays disabled until both settings exist. No SMTP configuration is necessary.
Render Free services [block the usual SMTP ports](https://render.com/docs/free#other-limitations).

The response confirms acceptance by the sending service, not delivery to the
recipient's inbox. Network failures keep the report saved. Repeating an uncertain
attempt from the same open window within 24 hours reuses an idempotency key to avoid duplicates;
after a successful send, a new click is a new intentional send.
