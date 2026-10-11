"""Application factory keeps tests isolated from each other's in-memory data."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import ApiError, AuthService
from app.routers import auth, realtime, rpc, sessions
from app.store import MemoryStore


def create_app() -> FastAPI:
    app = FastAPI(title="Blueprint local backend", version="0.1.0")
    app.state.store = MemoryStore()
    app.state.auth = AuthService(app.state.store)
    app.state.hub = realtime.RoomHub()

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(status_code=error.status, content={"code": error.code, "message": error.message})

    app.include_router(auth.router)
    app.include_router(sessions.router)
    app.include_router(rpc.router)
    app.include_router(realtime.router)
    return app


app = create_app()
