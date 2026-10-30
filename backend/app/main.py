"""Application factory with a configurable SQLAlchemy database."""

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.auth import ApiError, AuthService
from app.routers import auth, realtime, rpc, sessions
from app.store import DatabaseStore


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.store.close()

    app = FastAPI(title="Blueprint local backend", version="0.1.0", lifespan=lifespan)
    app.state.store = DatabaseStore(database_url)
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

    @app.get("/health/ready", include_in_schema=False)
    def ready() -> JSONResponse:
        try:
            app.state.store.check_ready()
        except SQLAlchemyError:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return JSONResponse(content={"status": "ready"})

    static_dir = Path(os.getenv("BLUEPRINT_STATIC_DIR", Path(__file__).resolve().parents[1] / "static"))
    shell = static_dir / "_shell.html"
    if shell.is_file():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="frontend-assets")

        @app.get("/favicon.ico", include_in_schema=False)
        def favicon() -> FileResponse:
            return FileResponse(static_dir / "favicon.ico")

        @app.get("/robots.txt", include_in_schema=False)
        def robots() -> FileResponse:
            return FileResponse(static_dir / "robots.txt")

        @app.get("/", include_in_schema=False)
        @app.get("/auth", include_in_schema=False)
        @app.get("/dashboard", include_in_schema=False)
        @app.get("/sessions/{session_id}", include_in_schema=False)
        @app.get("/join/{token}", include_in_schema=False)
        def frontend_shell() -> FileResponse:
            return FileResponse(shell, media_type="text/html")

    return app


app = create_app()
