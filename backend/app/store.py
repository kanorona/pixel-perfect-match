"""Process-local users and interviews. Restarting the server restores seed data."""

from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import token_hex
from threading import RLock
from uuid import uuid4, uuid5, NAMESPACE_DNS

from pwdlib import PasswordHash

from app.models import SessionCreate

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "DemoPass123!"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    token_version: int = 0

    def public(self) -> dict[str, str]:
        return {"id": self.id, "email": self.email, "aud": "authenticated", "role": "authenticated"}


class MemoryStore:
    def __init__(self) -> None:
        self.lock = RLock()
        self.passwords = PasswordHash.recommended()
        self.users: dict[str, User] = {}
        self.sessions: dict[str, dict] = {}
        self.refresh_tokens: dict[str, str] = {}
        self._seed()

    def _seed(self) -> None:
        user = User(
            id=str(uuid5(NAMESPACE_DNS, "blueprint-demo-user")),
            email=DEMO_EMAIL,
            password_hash=self.passwords.hash(DEMO_PASSWORD),
        )
        self.users[user.email] = user
        for title, status, prompt in (
            ("Design a URL shortener", "live", "Design a short-link service for a million users."),
            ("Design a chat system", "draft", "Discuss messages, delivery and scaling."),
        ):
            row = self.create_session(
                SessionCreate(owner_id=user.id, title=title, prompt=prompt, duration_minutes=60)
            )
            row["status"] = status
            if status == "live":
                row["started_at"] = now()

    def create_session(self, data: SessionCreate) -> dict:
        with self.lock:
            timestamp = now()
            row = {
                "id": str(uuid4()),
                "owner_id": data.owner_id,
                "title": data.title,
                "prompt": data.prompt,
                "duration_minutes": data.duration_minutes,
                "status": "draft",
                "candidate_token": token_hex(18),
                "candidate_editing_locked": False,
                "canvas": data.canvas or {"elements": []},
                "started_at": None,
                "ended_at": None,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            self.sessions[row["id"]] = row
            return row

    def owned_sessions(self, owner_id: str) -> list[dict]:
        with self.lock:
            return [s.copy() for s in self.sessions.values() if s["owner_id"] == owner_id]

    def owned_session(self, owner_id: str, session_id: str) -> dict | None:
        with self.lock:
            row = self.sessions.get(session_id)
            return row.copy() if row and row["owner_id"] == owner_id else None

    def update_session(self, owner_id: str, session_id: str, patch: dict) -> dict | None:
        with self.lock:
            row = self.sessions.get(session_id)
            if not row or row["owner_id"] != owner_id:
                return None
            row.update(patch)
            row["updated_at"] = now()
            return row.copy()

    def delete_session(self, owner_id: str, session_id: str) -> bool:
        with self.lock:
            if not self.owned_session(owner_id, session_id):
                return False
            del self.sessions[session_id]
            return True

    def by_candidate_token(self, token: str) -> dict | None:
        if len(token) < 24:
            return None
        with self.lock:
            return next((row.copy() for row in self.sessions.values() if row["candidate_token"] == token), None)

    def save_candidate_canvas(self, token: str, canvas: dict) -> bool:
        with self.lock:
            row = next((r for r in self.sessions.values() if r["candidate_token"] == token), None)
            if not row or row["status"] != "live" or row["candidate_editing_locked"]:
                return False
            row["canvas"] = canvas
            row["updated_at"] = now()
            return True
