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
export BLUEPRINT_ENV=development
export BLUEPRINT_SEED_DEMO=true
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In Windows PowerShell, if `uv` is not recognized but `python -m uv --version`
works, run these commands from `backend/` instead:

```powershell
python -m uv sync
$env:BLUEPRINT_ENV = "development"
$env:BLUEPRINT_SEED_DEMO = "true"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

`app.main:app` refers to the `app` object in `backend/app/main.py` when the
current directory is `backend/`. `--reload` restarts the server after code edits.
The interactive API reference is at `http://127.0.0.1:8001/docs`.

## Run both apps in Docker

From the repository root, with Docker installed:

```powershell
docker build -t blueprint .
docker run --rm --name blueprint -p 127.0.0.1:8001:8001 -e BLUEPRINT_ENV=development -e BLUEPRINT_SEED_DEMO=true -v blueprint-data:/data blueprint
```

Open `http://127.0.0.1:8001/`. FastAPI serves the frontend and the API on the
same port; the browser also uses that same origin for HTTP and WebSocket calls.
The Dockerfile first builds a static single-page app (SPA) with Node, then copies
only its browser files into the Python image. Node is not needed at runtime.
The named volume `blueprint-data` keeps SQLite data when the container is removed.
To use another database, pass `BLUEPRINT_DATABASE_URL` to `docker run` and install
its Python driver in the backend dependencies before building.

The Docker build installs frontend packages for Linux from `package.json`.
The publishable key is public client configuration, not an authentication secret.
The image defaults to production mode with demo seeding disabled. Only enable the
development flags on a local development server.

### Run the application stack with Docker Compose

The repository-level `docker-compose.yaml` defines both services required by
the application. `db` runs PostgreSQL and stores its files in the named volume
`interview-canvas-pgdata`. `app` builds the frontend and FastAPI image, then
connects to PostgreSQL over Compose's private network using the hostname `db`.

From the repository root:

```powershell
docker compose up --build
```

Open `http://127.0.0.1:8100/`. Compose shows logs from both services in the same
terminal; press `Ctrl+C` to stop them. To run in the background, add `-d` and
later use `docker compose down`. `down` removes the containers and network but
keeps the named database volume; `docker compose down -v` also deletes the
database data.

This local Compose file explicitly enables development demo data and binds its
published ports to `127.0.0.1`. The AWS Compose file forces production mode and
disables demo seeding.

PostgreSQL has a health check based on `pg_isready`. The `app` service has a
`depends_on` health condition, so FastAPI starts only after PostgreSQL reports
that it accepts connections. Port 5433 remains available for backend processes
running directly on Windows; containers use `db:5432` internally.

## Database connection

`BLUEPRINT_DATABASE_URL` selects the database. From `backend/` in PowerShell,
you can choose another SQLite file before starting the server:

```powershell
$env:BLUEPRINT_DATABASE_URL = "sqlite:///./my-interviews.db"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

If the variable is unset, the server uses `backend/blueprint.db` regardless of
the current working directory. SQLAlchemy creates missing tables at startup and
seeds the demo account and two interviews only when **both**
`BLUEPRINT_ENV=development` and `BLUEPRINT_SEED_DEMO=true`, and the demo account
does not exist. Defaults are `production` and `false`. Enabling demo seeding
outside development fails startup before connecting to the database. The database URL can later select another SQLAlchemy-supported database;
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
internally to SQLAlchemy's `postgresql+psycopg://` form. Tables are created on the
first connection; demo data requires both development flags. SQLite and PostgreSQL remain separate databases;
switching the URL does not copy existing SQLite records into PostgreSQL.

The `localhost` URL above is for a backend running directly on Windows. A backend
inside a Docker container must use a Docker-accessible hostname such as
`host.docker.internal` or the PostgreSQL container name on a shared network.
This workstation already has a Windows PostgreSQL service on port 5432, so the
Docker database is published as port 5433. If 5432 is free on another machine,
`-p 5432:5432` and `localhost:5432` work as in the original exercise.

The local-only seeded interviewer account is `demo@example.com` / `DemoPass123!`.
Both credentials and the default public key `sb_publishable_local_demo` are
development examples. The password is hashed with Argon2 in the database, and login
returns a signed bearer token. **Bearer token** means the caller proves its
login by sending that token in the `Authorization` header.

The frontend's tracked `.env.development` points its Supabase JavaScript client
to this local backend. The client is an SDK (a library that sends HTTP and
WebSocket requests); this backend implements the API shapes it expects. An
existing `frontend/.env.local` overrides the tracked development settings.
Start both servers before opening the dashboard.

Production starts with no demo users or example interviews. Create an individual
user through the registration screen. Disabling seeding does not delete users
already stored in an existing database; do not reuse a development database for
deployment. `make backend` and `make run` enable both local demo flags explicitly.

`GET /health/ready` executes a database query and returns 200 when ready or a
generic 503 on a database error. It never returns connection details. Docker
health checks and the AWS startup check use this endpoint.

## OpenTelemetry

FastAPI HTTP requests are traced with the required resource attributes. The
existing `BLUEPRINT_ENV` supplies `deployment.environment.name`, and the image's
existing `BLUEPRINT_REVISION` supplies `service.version`. `service.name` defaults
to `blueprint-backend` and may be overridden with `OTEL_SERVICE_NAME`.

No exporter is attached unless `OTEL_EXPORTER_OTLP_ENDPOINT` or
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is explicitly set. The OTLP/HTTP exporter
also reads the standard `OTEL_EXPORTER_OTLP_*` variables for headers,
certificates, compression and timeouts. For example, a Collector accepting the
standard OTLP/HTTP path can later be configured with:

```powershell
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"
```

For a trace-specific endpoint, include the signal path, for example
`http://localhost:4318/v1/traces`. Set `OTEL_TRACES_EXPORTER=none` to explicitly
disable export even when an endpoint exists. Request/response bodies and HTTP
headers are not captured. Concrete URL paths and query strings are redacted;
the stable route template remains available as `http.route`.

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
