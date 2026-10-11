"""Local publishable key, Argon2 passwords, and signed bearer tokens."""

import os
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from uuid import uuid4

import jwt
from fastapi import Header, Request

from app.store import MemoryStore, User

PUBLIC_KEY = os.getenv("BLUEPRINT_PUBLIC_KEY", "sb_publishable_local_demo")


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str = "api_error") -> None:
        self.status = status
        self.message = message
        self.code = code


def require_api_key(apikey: str | None = Header(default=None)) -> None:
    if apikey != PUBLIC_KEY:
        raise ApiError(401, "Invalid API key", "invalid_api_key")


def store_from(request: Request) -> MemoryStore:
    return request.app.state.store


class AuthService:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.secret = token_urlsafe(48)

    def sign_up(self, email: str, password: str) -> User:
        email = email.lower()
        with self.store.lock:
            if email in self.store.users:
                raise ApiError(400, "User already registered", "user_already_exists")
            user = User(id=str(uuid4()), email=email,
                        password_hash=self.store.passwords.hash(password))
            self.store.users[email] = user
            return user

    def password_login(self, email: str, password: str) -> dict:
        with self.store.lock:
            user = self.store.users.get(email.lower())
            if not user or not self.store.passwords.verify(password, user.password_hash):
                raise ApiError(400, "Invalid login credentials", "invalid_credentials")
            return self._issue(user)

    def refresh(self, refresh_token: str) -> dict:
        with self.store.lock:
            user_id = self.store.refresh_tokens.pop(refresh_token, None)
            user = next((u for u in self.store.users.values() if u.id == user_id), None)
            if not user:
                raise ApiError(400, "Invalid refresh token", "invalid_refresh_token")
            return self._issue(user)

    def _issue(self, user: User) -> dict:
        issued = datetime.now(timezone.utc)
        expires = issued + timedelta(hours=1)
        access = jwt.encode({
            "sub": user.id,
            "email": user.email,
            "role": "authenticated",
            "aud": "authenticated",
            "iat": int(issued.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": token_urlsafe(16),
            "version": user.token_version,
        }, self.secret, algorithm="HS256")
        refresh = token_urlsafe(48)
        self.store.refresh_tokens[refresh] = user.id
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": 3600,
            "expires_at": int(expires.timestamp()),
            "user": user.public(),
        }

    def current_user(self, authorization: str | None) -> User:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(401, "Missing bearer token", "unauthorized")
        try:
            claims = jwt.decode(authorization[7:], self.secret,
                                algorithms=["HS256"], audience="authenticated")
        except jwt.PyJWTError as exc:
            raise ApiError(401, "Invalid bearer token", "unauthorized") from exc
        with self.store.lock:
            user = next((u for u in self.store.users.values() if u.id == claims.get("sub")), None)
            if not user or user.token_version != claims.get("version"):
                raise ApiError(401, "Session revoked", "unauthorized")
            return user

    def sign_out(self, user: User) -> None:
        with self.store.lock:
            user.token_version += 1
            for token, user_id in list(self.store.refresh_tokens.items()):
                if user_id == user.id:
                    del self.store.refresh_tokens[token]


def auth_from(request: Request) -> AuthService:
    return request.app.state.auth


def require_user(request: Request, authorization: str | None = Header(default=None)) -> User:
    require_api_key(request.headers.get("apikey"))
    return auth_from(request).current_user(authorization)
