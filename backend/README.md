# Local FastAPI backend

This is an in-memory implementation of the Supabase-shaped routes in
[`../openapi.yaml`](../openapi.yaml). **FastAPI** exposes HTTP and WebSocket
routes in Python. The in-memory store starts with two example interviews and
resets whenever the process restarts; it is not persistent storage.

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

The seeded interviewer account is `demo@example.com` / `DemoPass123!`.
Both credentials and the default public key `sb_publishable_local_demo` are
development examples. The password is hashed with Argon2 in memory, and login
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

The tests create a fresh store for each case and cover authentication, session
ownership, guest tokens, canvas rules, and Realtime messages. The local backend
does not send confirmation email: new accounts are active immediately.

## Modules

- `app/models.py`: request shapes and validation.
- `app/store.py`: in-memory users, sessions, and seeded data.
- `app/auth.py`: password hashing, signed tokens, and access checks.
- `app/routers/`: HTTP and WebSocket routes.

This is an exercise backend. Its data and token-signing secret disappear on
restart. For deployment, replace the in-memory store and key management with
persistent services, and review the public Realtime room policy.
