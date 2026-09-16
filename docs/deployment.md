# Battle March Deployment Notes

This app is a small FastAPI, Jinja2, SQLAlchemy league scoreboard. The cheapest sensible production shape is:

- one hosted Python web service running `uvicorn app.main:app`
- one managed PostgreSQL database
- environment variables for database URL, admin password hash, and session secret
- no production data stored in local SQLite or local files
- public read-only league pages
- protected `/admin` pages

## Recommended Architecture

Use a platform that can run a plain Python web process and attach a managed PostgreSQL database without requiring Docker.

Recommended first choice: **Render**.

Why:

- Simple GitHub-based deploys.
- Can run this app from `requirements.txt` with no Dockerfile.
- Managed PostgreSQL is available on the same platform.
- Environment variables are straightforward.
- Good fit for a small private league where operational simplicity matters more than maximum control.

Other reasonable options:

- **Railway**: very quick setup, simple PostgreSQL provisioning, often pleasant for small apps.
- **Fly.io**: inexpensive and flexible, but PostgreSQL and operations are a little more hands-on.
- **PythonAnywhere**: simple Python hosting, but FastAPI/ASGI deployment can be less direct than Render or Railway.
- **A VPS**: cheapest at scale, but more operational work: OS updates, process manager, reverse proxy, TLS, backups.

I would start with Render or Railway, then only move to something more manual if cost or control becomes a real issue.

## SQLite Assumptions Reviewed

The code has been updated so local SQLite is now the development default, not the production assumption.

### 1. Database URL is hard-coded

`app/database.py` reads `DATABASE_URL` from the environment. If it is missing, local development falls back to:

```python
DATABASE_PATH = Path(__file__).resolve().parent.parent / "battle_march.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
```

Production should set:

```text
DATABASE_URL=postgresql+psycopg://...
```

Render sometimes provides URLs starting with `postgresql://`; the app normalizes those to `postgresql+psycopg://` for SQLAlchemy.

### 2. SQLite-only engine option

The app now only passes:

```python
connect_args={"check_same_thread": False}
```

when the URL starts with `sqlite`.

### 3. PostgreSQL driver is missing

`requirements.txt` now includes:

```text
psycopg[binary]
```

### 4. Tables are created on application startup

Application startup now only auto-creates tables outside production by default. Production should use Alembic:

```bash
PYTHONPATH=. alembic upgrade head
```

The initial migration lives in `migrations/versions/20260916_0001_initial_schema.py`.

### 5. The seed script drops all tables

`scripts/seed.py` calls:

```python
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
```

That is useful locally and dangerous in production. It now refuses to run when `BATTLE_MARCH_ENV=production`.

### 6. Development import route is public

The app now has protected admin import at:

```text
/admin/army-lists
```

The older public development import route has been removed:

```text
/dev/army-lists/import
```

Use `/admin/army-lists` instead.

### 7. Public league creation endpoints remain open

These temporary endpoints have been removed:

```text
POST /leagues
GET /leagues/{league_id}
```

League creation is not exposed publicly.

### 8. One-league assumption

Several pages use the most recently created league as the current league. That is fine for a single private league, but it should be treated as an explicit product assumption.

If the app will host only one league, this is acceptable. If it might host multiple leagues, routing should include a league slug or ID later.

## Environment Variables

Production should provide:

```text
BATTLE_MARCH_ENV=production
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
BATTLE_MARCH_ADMIN_PASSWORD_HASH=pbkdf2_sha256$...
BATTLE_MARCH_SESSION_SECRET=long-random-secret
BATTLE_MARCH_SECURE_COOKIES=true
```

Generate the password hash locally:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.hash_password
```

The hash contains `$` separators. In Render's environment variable editor, paste the generated hash exactly as printed, without surrounding quotes. If testing locally with `export`, wrap the value in single quotes so your shell does not treat `$...` as variable expansion:

```bash
export BATTLE_MARCH_ADMIN_PASSWORD_HASH='pbkdf2_sha256$260000$...'
```

You can verify a configured hash locally:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.verify_admin_password
```

Generate a session secret locally:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Do not commit either value.

## Recommended Deployment Process On Render

These steps assume you have chosen Render and created an account.

1. Push the repository to GitHub.

1. Create a Render PostgreSQL database.

1. Copy Render's internal database URL.

1. Create a Render Web Service from the GitHub repository.

1. Use the Python environment.

1. Set the build command:

```bash
pip install -r requirements.txt
```

1. Set the start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

1. Add environment variables:

```text
BATTLE_MARCH_ENV=production
DATABASE_URL=<Render PostgreSQL internal URL converted to SQLAlchemy format>
BATTLE_MARCH_ADMIN_PASSWORD_HASH=<generated hash>
BATTLE_MARCH_SESSION_SECRET=<generated secret>
BATTLE_MARCH_SECURE_COOKIES=true
```

1. Run migrations from a one-off shell/job:

```bash
PYTHONPATH=. alembic upgrade head
```

1. Deploy the web service.

1. Visit public pages:

```text
/
/players
/rounds
```

1. Visit `/admin/login` and confirm the admin password works.

1. Import a real Old World Builder JSON list through `/admin/army-lists`.

1. Confirm the imported list appears from a public player profile and at `/army-lists/{id}`.

## Recommended Code Changes Before Deployment

Completed:

1. Add `DATABASE_URL` support in `app/database.py` and add `psycopg[binary]`.
1. Remove `/dev/army-lists/import`.
1. Remove `POST /leagues`.
1. Add a production guard to `scripts/seed.py`.
1. Add Alembic migrations.

Still useful before going live:

1. Add a short production smoke test/checklist.
1. Decide how the first real production league row should be created.
1. Consider a basic database backup/restore note once the platform is chosen.

## Deployment Readiness Summary

The app is now much closer to deployable for a small private league. It no longer hard-codes SQLite for all environments and no longer exposes the old public development write routes.

The lowest-friction path is to deploy to Render with managed PostgreSQL, run Alembic migrations, log into `/admin`, then create/import the league data through protected admin pages.
