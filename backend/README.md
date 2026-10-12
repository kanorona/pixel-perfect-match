# Local FastAPI backend

This implements the Supabase-shaped routes in
[`../openapi.yaml`](../openapi.yaml). **FastAPI** exposes HTTP and WebSocket
routes in Python. **SQLAlchemy** maps users, interviews, refresh tokens, and
the signing key to database tables. The default SQLite file is
`backend/blueprint.db`; data survives a server restart.

## Run

From `backend/`:

```sh
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In Windows PowerShell, if `uv` is not recognized but `python -m uv --version`
works, run these commands from `backend/` instead:

```powershell
python -m uv sync
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

`app.main:app` refers to the `app` object in `backend/app/main.py` when the
current directory is `backend/`. `--reload` restarts the server after code edits.
The interactive API reference is at `http://127.0.0.1:8001/docs`.

## Database connection

`BLUEPRINT_DATABASE_URL` selects the database. From `backend/` in PowerShell,
you can choose another SQLite file before starting the server:

```powershell
$env:BLUEPRINT_DATABASE_URL = "sqlite:///./my-interviews.db"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

If the variable is unset, the server uses `backend/blueprint.db` regardless of
the current working directory. SQLAlchemy creates missing tables at startup and
seeds the demo account and two interviews only when the demo account does not
exist. The database URL can later select another SQLAlchemy-supported database;
its driver must also be installed with `uv`. Schema changes to an existing
database will need migrations; `create_all` only creates missing tables.

SQLite database files in `backend/` are ignored by Git. Keep the file if you
want to preserve your interviews. An optional `BLUEPRINT_JWT_SECRET` overrides
the signing key saved in the database; changing it invalidates existing access
tokens.

The seeded interviewer account is `demo@example.com` / `DemoPass123!`.
Both credentials and the default public key `sb_publishable_local_demo` are
development examples. The password is hashed with Argon2 in the database, and login
returns a signed bearer token. **Bearer token** means the caller proves its
login by sending that token in the `Authorization` header.

The frontend's tracked `.env.development` points its Supabase JavaScript client
to this local backend. The client is an SDK (a library that sends HTTP and
WebSocket requests); this backend implements the API shapes it expects. An
existing `frontend/.env.local` overrides the tracked development settings.
Start both servers before opening the dashboard.

## Test

```sh
uv run python -m pytest -q
```

The tests create a fresh temporary SQLite database for each case and cover
authentication, session ownership, guest tokens, canvas rules, Realtime, and
data surviving a restart. The local backend
does not send confirmation email: new accounts are active immediately.

## Modules

- `app/models.py`: request shapes and validation.
- `app/store.py`: SQLAlchemy tables and database operations.
- `app/auth.py`: password hashing, signed tokens, and access checks.
- `app/routers/`: HTTP and WebSocket routes.

This is an exercise backend. For deployment, configure durable database storage,
backups, a managed signing secret, schema migrations, and the public Realtime
room policy.
