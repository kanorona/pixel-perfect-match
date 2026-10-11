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

On a machine where `uv` is installed as a Python module but its command is not
on `PATH`, use `python -m uv sync` and `python -m uv run python -m uvicorn ...`.
The interactive API reference is at `http://127.0.0.1:8001/docs`.

The seeded interviewer account is `demo@example.com` / `DemoPass123!`.
Both credentials and the default public key `sb_publishable_local_demo` are
development examples. The password is hashed with Argon2 in memory, and login
returns a signed bearer token. **Bearer token** means the caller proves its
login by sending that token in the `Authorization` header.

To connect the frontend, copy `frontend/.env.local.example` to
`frontend/.env.local`, then restart `npm run dev` inside `frontend/`. The
`.env.local` file is ignored by Git. The frontend continues using its Supabase
JavaScript client, while this backend implements the API shapes that client
expects. Start both servers before opening the dashboard.

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
