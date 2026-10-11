"""Request models and shared response shapes."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthUser(BaseModel):
    id: str
    email: EmailStr
    aud: str = "authenticated"
    role: str = "authenticated"


class SessionCreate(BaseModel):
    owner_id: str
    title: str = Field(max_length=120)
    prompt: str = Field(max_length=5000)
    duration_minutes: int = Field(ge=10, le=240)
    canvas: dict[str, Any] | None = None


class SessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["draft", "live", "ended"] | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    candidate_token: str | None = None
    candidate_editing_locked: bool | None = None
    canvas: dict[str, Any] | None = None

    @model_validator(mode="after")
    def reject_non_nullable_nulls(self):
        for name in ("status", "candidate_token", "candidate_editing_locked", "canvas"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class TokenRequest(BaseModel):
    token: str = Field(alias="_token")


class CanvasSaveRequest(BaseModel):
    token: str = Field(alias="_token")
    canvas: dict[str, Any] = Field(alias="_canvas")


class BroadcastMessage(BaseModel):
    topic: str
    event: Literal["op", "sync-req", "sync", "cursor", "session"]
    payload: dict[str, Any]
    private: bool = False


class BroadcastRequest(BaseModel):
    messages: list[BroadcastMessage]
