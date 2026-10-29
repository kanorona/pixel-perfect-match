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

## Run both apps in Docker

From the repository root, with Docker installed:

```powershell
docker build -t blueprint .
docker run --rm --name blueprint -p 8001:8001 -v blueprint-data:/data blueprint
```

Open `http://127.0.0.1:8001/`. FastAPI serves the frontend and the API on the
same port; the browser also uses that same origin for HTTP and WebSocket calls.
The Dockerfile first builds a static single-page app (SPA) with Node, then copies
only its browser files into the Python image. Node is not needed at runtime.
The named volume `blueprint-data` keeps SQLite data when the container is removed.
To use another database, pass `BLUEPRINT_DATABASE_URL` to `docker run` and install
its Python driver in the backend dependencies before building.

The Docker build installs frontend packages for Linux from `package.json`.
It uses the local demo publishable key; replace that configuration before
exposing the app publicly.

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

### PostgreSQL for local development

Start PostgreSQL from the repository root. This container is only the database;
the named volume preserves its files when the container is replaced:

```powershell
docker run -d --name interview-canvas-db -e POSTGRES_USER=sdip -e POSTGRES_PASSWORD=sdip -e POSTGRES_DB=sdip -p 5433:5432 -v interview-canvas-pgdata:/var/lib/postgresql/data postgres:16-alpine
```

Then point the locally running backend at it:

```powershell
$env:BLUEPRINT_DATABASE_URL = "postgresql://sdip:sdip@localhost:5433/sdip"
make run
```

If GNU Make is not installed, use the backend's Python environment instead:

```powershell
python -m uv sync --directory backend
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8001
```

`psycopg` is the PostgreSQL driver. A standard `postgresql://` URL is converted
internally to SQLAlchemy's `postgresql+psycopg://` form. Tables and demo data are
created on the first connection. SQLite and PostgreSQL remain separate databases;
switching the URL does not copy existing SQLite records into PostgreSQL.

The `localhost` URL above is for a backend running directly on Windows. A backend
inside a Docker container must use a Docker-accessible hostname such as
`host.docker.internal` or the PostgreSQL container name on a shared network.
This workstation already has a Windows PostgreSQL service on port 5432, so the
Docker database is published as port 5433. If 5432 is free on another machine,
`-p 5432:5432` and `localhost:5432` work as in the original exercise.

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

With the local PostgreSQL container running on port 5433, run the optional
integration test with:

```powershell
$env:BLUEPRINT_TEST_POSTGRES_URL = "postgresql://sdip:sdip@localhost:5433/sdip"
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_postgres.py -q
```

## Modules

- `app/models.py`: request shapes and validation.
- `app/store.py`: SQLAlchemy tables and database operations.
- `app/auth.py`: password hashing, signed tokens, and access checks.
- `app/routers/`: HTTP and WebSocket routes.

This is an exercise backend. For deployment, configure durable database storage,
backups, a managed signing secret, schema migrations, and the public Realtime
room policy.
