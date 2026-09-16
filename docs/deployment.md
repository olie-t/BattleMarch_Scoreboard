# Battle March Deployment Notes

This app is intended to run as a small FastAPI web service with a managed PostgreSQL database.

## Recommended Architecture

- Render Web Service running the FastAPI app.
- Render PostgreSQL database for production data.
- Environment variables for configuration and secrets.
- Public read-only pages for players, rounds, and army lists.
- Password-protected `/admin` pages for league management.

This keeps deployment simple and avoids Docker for now.

## Render Build And Start Commands

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Environment Variables

Set these in the Render Web Service environment settings:

```text
BATTLE_MARCH_ENV=production
DATABASE_URL=<Render PostgreSQL internal database URL>
BATTLE_MARCH_ADMIN_PASSWORD_HASH=<generated hash>
BATTLE_MARCH_SESSION_SECRET=<generated secret>
BATTLE_MARCH_SECURE_COOKIES=true
BATTLE_MARCH_AUTO_CREATE_TABLES=false
```

Use Render's **Internal Database URL** for `DATABASE_URL`.

Generate the admin password hash locally:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.hash_password
```

Paste the generated hash into Render exactly as printed, without surrounding quotes.

If testing locally with `export`, wrap the hash in single quotes because it contains `$` separators:

```bash
export BATTLE_MARCH_ADMIN_PASSWORD_HASH='pbkdf2_sha256$260000$...'
```

Verify a configured hash locally:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.verify_admin_password
```

Generate a session secret locally:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Do not commit secrets.

## Database Migrations

After creating the Render PostgreSQL database and setting `DATABASE_URL`, run:

```bash
PYTHONPATH=. alembic upgrade head
```

Run this from a Render shell or one-off job before using the admin area for real data.

## First Production Setup

1. Deploy the Render Web Service.
1. Run the Alembic migration.
1. Visit `/admin/login`.
1. Log in with the configured admin password.
1. Create the league at `/admin/leagues`.
1. Add rounds at `/admin/rounds`.
1. Add players at `/admin/players`.
1. Add matches and scores at `/admin/matches`.
1. Import Old World Builder JSON lists at `/admin/army-lists`.
1. Confirm public pages render correctly:

```text
/
/players
/rounds
/army-lists/{army_list_id}
```

## Remaining Operational Checks

Before treating the site as live, confirm:

- Render PostgreSQL backups are enabled or understood.
- Admin login works after a redeploy.
- Data persists after a redeploy.
- Public pages do not require login.
- `/admin` redirects to login when logged out.
- The seed script is not used against production.
