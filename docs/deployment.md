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

## Current SQLite Assumptions To Fix

Before production, the code should stop assuming local SQLite.

### 1. Database URL is hard-coded

Current code in `app/database.py` always uses:

```python
DATABASE_PATH = Path(__file__).resolve().parent.parent / "battle_march.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
```

Production should read from an environment variable:

```text
DATABASE_URL=postgresql+psycopg://...
```

Local development can still default to SQLite when `DATABASE_URL` is missing.

### 2. SQLite-only engine option

Current code passes:

```python
connect_args={"check_same_thread": False}
```

That option is SQLite-specific. For PostgreSQL, the engine should only include it when the URL starts with `sqlite`.

### 3. PostgreSQL driver is missing

`requirements.txt` currently has SQLAlchemy but no PostgreSQL driver. Add one before deployment:

```text
psycopg[binary]
```

### 4. Tables are created on application startup

Current startup uses:

```python
Base.metadata.create_all(bind=engine)
```

This is acceptable for early local development. For production, it is better to run migrations explicitly. The next production-readiness step should add Alembic or a deliberately simple one-time initialization command.

Recommendation: add Alembic before real production data exists.

### 5. The seed script drops all tables

`scripts/seed.py` calls:

```python
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
```

That is useful locally and dangerous in production. Keep it as a development-only command and never run it with the production `DATABASE_URL`.

Before deployment, add a guard so it refuses to run when `BATTLE_MARCH_ENV=production`.

### 6. Development import route is public

The app now has protected admin import at:

```text
/admin/army-lists
```

But the older development import route still exists and is public:

```text
/dev/army-lists/import
```

Before deployment, remove it or protect it behind admin authentication. For production, prefer removing it.

### 7. Public league creation endpoints remain open

These temporary endpoints still exist:

```text
POST /leagues
GET /leagues/{league_id}
```

`POST /leagues` is a public write endpoint. Before deployment, remove it or move it behind `/admin`.

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

Generate a session secret locally:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Do not commit either value.

## Recommended Deployment Process On Render

These steps assume the code has first been updated to support `DATABASE_URL` and PostgreSQL.

1. Push the repository to GitHub.

2. Create a Render PostgreSQL database.

3. Copy Render's internal database URL.

4. Create a Render Web Service from the GitHub repository.

5. Use the Python environment.

6. Set the build command:

```bash
pip install -r requirements.txt
```

7. Set the start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

8. Add environment variables:

```text
BATTLE_MARCH_ENV=production
DATABASE_URL=<Render PostgreSQL internal URL converted to SQLAlchemy format>
BATTLE_MARCH_ADMIN_PASSWORD_HASH=<generated hash>
BATTLE_MARCH_SESSION_SECRET=<generated secret>
BATTLE_MARCH_SECURE_COOKIES=true
```

9. Run migrations or the chosen production schema initialization command.

10. Deploy the web service.

11. Visit public pages:

```text
/
/players
/rounds
```

12. Visit `/admin/login` and confirm the admin password works.

13. Import a real Old World Builder JSON list through `/admin/army-lists`.

14. Confirm the imported list appears from a public player profile and at `/army-lists/{id}`.

## Recommended Code Changes Before Deployment

Do these in small increments:

1. Add `DATABASE_URL` support in `app/database.py` and add `psycopg[binary]`.
2. Protect or remove `/dev/army-lists/import`.
3. Remove or protect `POST /leagues`.
4. Add a production guard to `scripts/seed.py`.
5. Add Alembic migrations.
6. Add a short production smoke test/checklist.

## Deployment Readiness Summary

The app is close to deployable for a small private league, but it should not be deployed as-is because it still hard-codes SQLite and leaves development write routes available publicly.

The lowest-friction path is to make the code read `DATABASE_URL`, remove/protect the development endpoints, add PostgreSQL driver support, then deploy to Render with managed PostgreSQL.