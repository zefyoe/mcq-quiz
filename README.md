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
