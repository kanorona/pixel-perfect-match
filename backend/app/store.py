"""SQLAlchemy persistence behind the API's existing store methods."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex, token_urlsafe
from uuid import NAMESPACE_DNS, uuid4, uuid5

from pwdlib import PasswordHash
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.models import SessionCreate

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "DemoPass123!"
DEFAULT_DATABASE_URL = f"sqlite:///{(Path(__file__).resolve().parents[1] / 'blueprint.db').as_posix()}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    token_version: Mapped[int] = mapped_column(Integer, default=0)


class SessionRow(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    prompt: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    candidate_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    candidate_editing_locked: Mapped[bool] = mapped_column(Boolean)
    canvas: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))

    def public(self) -> dict:
        return {name: getattr(self, name) for name in (
            "id", "owner_id", "title", "prompt", "duration_minutes", "status",
            "candidate_token", "candidate_editing_locked", "canvas", "started_at",
            "ended_at", "created_at", "updated_at",
        )}


class RefreshTokenRow(Base):
    __tablename__ = "refresh_tokens"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)


class SettingRow(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    token_version: int = 0

    def public(self) -> dict[str, str]:
        return {"id": self.id, "email": self.email, "aud": "authenticated", "role": "authenticated"}


def _user(row: UserRow | None) -> User | None:
    return User(row.id, row.email, row.password_hash, row.token_version) if row else None


class DatabaseStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("BLUEPRINT_DATABASE_URL", DEFAULT_DATABASE_URL)
        connect_args = {"check_same_thread": False} if make_url(self.database_url).get_backend_name() == "sqlite" else {}
        self.engine = create_engine(self.database_url, connect_args=connect_args, pool_pre_ping=True)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self.passwords = PasswordHash.recommended()
        Base.metadata.create_all(self.engine)
        self._seed()

    def close(self) -> None:
        self.engine.dispose()

    def _seed(self) -> None:
        with self.Session.begin() as db:
            if db.scalar(select(UserRow.id).where(UserRow.email == DEMO_EMAIL)):
                return
            user_id = str(uuid5(NAMESPACE_DNS, "blueprint-demo-user"))
            db.add(UserRow(id=user_id, email=DEMO_EMAIL,
                           password_hash=self.passwords.hash(DEMO_PASSWORD), token_version=0))
            for title, status, prompt in (
                ("Design a URL shortener", "live", "Design a short-link service for a million users."),
                ("Design a chat system", "draft", "Discuss messages, delivery and scaling."),
            ):
                row = self._new_session(SessionCreate(
                    owner_id=user_id, title=title, prompt=prompt, duration_minutes=60,
                ))
                row.status = status
                if status == "live":
                    row.started_at = now()
                db.add(row)

    def signing_secret(self) -> str:
        with self.Session.begin() as db:
            setting = db.get(SettingRow, "jwt_secret")
            if setting is None:
                setting = SettingRow(key="jwt_secret", value=token_urlsafe(48))
                db.add(setting)
            return setting.value

    def user_by_email(self, email: str) -> User | None:
        with self.Session() as db:
            return _user(db.scalar(select(UserRow).where(UserRow.email == email.lower())))

    def user_by_id(self, user_id: str | None) -> User | None:
        with self.Session() as db:
            return _user(db.get(UserRow, user_id)) if user_id else None

    def create_user(self, email: str, password_hash: str) -> User:
        user = User(id=str(uuid4()), email=email.lower(), password_hash=password_hash)
        try:
            with self.Session.begin() as db:
                db.add(UserRow(**vars(user)))
        except IntegrityError as exc:
            raise ValueError("User already registered") from exc
        return user

    def save_refresh_token(self, token: str, user_id: str) -> None:
        with self.Session.begin() as db:
            db.add(RefreshTokenRow(token=token, user_id=user_id))

    def consume_refresh_token(self, token: str) -> User | None:
        with self.Session.begin() as db:
            row = db.get(RefreshTokenRow, token)
            if row is None:
                return None
            user = _user(db.get(UserRow, row.user_id))
            db.delete(row)
            return user

    def revoke_user_sessions(self, user_id: str) -> None:
        with self.Session.begin() as db:
            user = db.get(UserRow, user_id)
            if user:
                user.token_version += 1
                db.execute(delete(RefreshTokenRow).where(RefreshTokenRow.user_id == user_id))

    @staticmethod
    def _new_session(data: SessionCreate) -> SessionRow:
        timestamp = now()
        return SessionRow(
            id=str(uuid4()), owner_id=data.owner_id, title=data.title, prompt=data.prompt,
            duration_minutes=data.duration_minutes, status="draft", candidate_token=token_hex(18),
            candidate_editing_locked=False, canvas=data.canvas or {"elements": []},
            started_at=None, ended_at=None, created_at=timestamp, updated_at=timestamp,
        )

    def create_session(self, data: SessionCreate) -> dict:
        with self.Session.begin() as db:
            row = self._new_session(data)
            db.add(row)
            return row.public()

    def owned_sessions(self, owner_id: str) -> list[dict]:
        with self.Session() as db:
            rows = db.scalars(select(SessionRow).where(SessionRow.owner_id == owner_id)).all()
            return [row.public() for row in rows]

    def owned_session(self, owner_id: str, session_id: str) -> dict | None:
        with self.Session() as db:
            row = db.get(SessionRow, session_id)
            return row.public() if row and row.owner_id == owner_id else None

    def update_session(self, owner_id: str, session_id: str, patch: dict) -> dict | None:
        with self.Session.begin() as db:
            row = db.get(SessionRow, session_id)
            if not row or row.owner_id != owner_id:
                return None
            for name, value in patch.items():
                setattr(row, name, value)
            row.updated_at = now()
            return row.public()

    def delete_session(self, owner_id: str, session_id: str) -> bool:
        with self.Session.begin() as db:
            row = db.get(SessionRow, session_id)
            if not row or row.owner_id != owner_id:
                return False
            db.delete(row)
            return True

    def by_candidate_token(self, token: str) -> dict | None:
        if len(token) < 24:
            return None
        with self.Session() as db:
            row = db.scalar(select(SessionRow).where(SessionRow.candidate_token == token))
            return row.public() if row else None

    def save_candidate_canvas(self, token: str, canvas: dict) -> bool:
        with self.Session.begin() as db:
            row = db.scalar(select(SessionRow).where(SessionRow.candidate_token == token))
            if not row or row.status != "live" or row.candidate_editing_locked:
                return False
            row.canvas = canvas
            row.updated_at = now()
            return True

    def session_exists(self, session_id: str) -> bool:
        with self.Session() as db:
            return db.scalar(select(SessionRow.id).where(SessionRow.id == session_id)) is not None
