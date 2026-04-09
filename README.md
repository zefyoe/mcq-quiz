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
