# Pixel Perfect Match

Implement exactly the screenshot and nothing else

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/cdb5ec2e-984e-4388-8710-9dc19ade17fd).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
cd frontend
npm i
npm run dev
```

The frontend's current backend contract is in [`openapi.yaml`](openapi.yaml).
For the reasoning behind the project structure and contract, see
[`docs/spec.md`](docs/spec.md).

For the local Python implementation and demo login, see
[`backend/README.md`](backend/README.md).

## Run both local servers with Make

From the repository root, with GNU Make, Python, `uv` (available as
`python -m uv`), Node.js, and npm installed:

```sh
make setup
```

In development, `frontend/.env.development` points the existing Supabase SDK
client to the local FastAPI backend at port 8001. The backend implements the
authentication, session, guest RPC, and Realtime routes that client calls.
An existing `frontend/.env.local` takes precedence over `.env.development`, so
check its URL if the frontend connects elsewhere. Start each server in its own
terminal:

```sh
make backend
```

```sh
make frontend
```

Open `http://127.0.0.1:8081/` for the frontend and
`http://127.0.0.1:8001/docs` for the backend API reference. Run `make test` to
check both applications. On Windows, `make` requires GNU Make to be installed;
the commands in [`backend/README.md`](backend/README.md) also work directly in
PowerShell. For a local login, use `demo@example.com` / `DemoPass123!`.
