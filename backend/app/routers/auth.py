"""Subset of GoTrue Auth used by the frontend."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.auth import ApiError, AuthService, auth_from, require_api_key, require_user
from app.models import Credentials, RefreshRequest
from app.store import User

router = APIRouter(prefix="/auth/v1", tags=["Auth"], dependencies=[Depends(require_api_key)])


@router.post("/signup")
def sign_up(body: Credentials, request: Request, redirect_to: str | None = None) -> dict:
    # Local mock accounts are active immediately; no email delivery is simulated.
    auth = auth_from(request)
    user = auth.sign_up(body.email, body.password)
    return auth.password_login(user.email, body.password)


@router.post("/token")
def issue_token(request: Request, grant_type: str = Query(...), body: dict | None = None) -> dict:
    auth: AuthService = auth_from(request)
    body = body or {}
    if grant_type == "password":
        credentials = Credentials.model_validate(body)
        return auth.password_login(credentials.email, credentials.password)
    if grant_type == "refresh_token":
        refresh = RefreshRequest.model_validate(body)
        return auth.refresh(refresh.refresh_token)
    raise ApiError(400, "Unsupported grant type", "unsupported_grant_type")


@router.get("/user")
def get_user(user: Annotated[User, Depends(require_user)]) -> dict:
    return user.public()


@router.post("/logout", status_code=204)
def sign_out(request: Request, user: Annotated[User, Depends(require_user)], scope: str = "global") -> Response:
    if scope != "global":
        raise ApiError(400, "Unsupported logout scope", "invalid_scope")
    auth_from(request).sign_out(user)
    return Response(status_code=204)
