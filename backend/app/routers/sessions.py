"""PostgREST-compatible interview session operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from app.auth import ApiError, require_user, store_from
from app.models import SessionCreate, SessionPatch
from app.store import User

router = APIRouter(prefix="/rest/v1", tags=["Sessions"])
OBJECT_MEDIA = "application/vnd.pgrst.object+json"


def parse_id_filter(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.startswith("eq.") or len(value) < 4:
        raise ApiError(400, "Expected id=eq.<uuid>", "invalid_filter")
    return value[3:]


def not_single() -> ApiError:
    return ApiError(406, "JSON object requested, multiple (or no) rows returned", "PGRST116")


def wants_object(request: Request) -> bool:
    return OBJECT_MEDIA in request.headers.get("accept", "")


@router.get("/interview_sessions")
def list_sessions(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    id: str | None = None,
    select: str | None = None,
    order: str | None = None,
) -> Response:
    rows = store_from(request).owned_sessions(user.id)
    session_id = parse_id_filter(id)
    if session_id:
        rows = [row for row in rows if row["id"] == session_id]
    if order == "updated_at.desc":
        rows.sort(key=lambda row: row["updated_at"], reverse=True)
    if select and select != "*":
        fields = [name.strip() for name in select.split(",")]
        if any(name not in rows[0] for name in fields) if rows else False:
            raise ApiError(400, "Unknown selected field", "invalid_select")
        rows = [{name: row[name] for name in fields} for row in rows]
    if wants_object(request):
        if len(rows) != 1:
            raise not_single()
        return JSONResponse(rows[0], media_type=OBJECT_MEDIA)
    return JSONResponse(rows)


@router.post("/interview_sessions", status_code=201)
def create_session(
    request: Request,
    body: SessionCreate,
    user: Annotated[User, Depends(require_user)],
    select: str = Query("id"),
) -> Response:
    if body.owner_id != user.id:
        raise ApiError(403, "Cannot create another user's session", "forbidden")
    row = store_from(request).create_session(body)
    data = {"id": row["id"]} if select == "id" else row
    return JSONResponse(data, status_code=201, media_type=OBJECT_MEDIA if wants_object(request) else "application/json")


@router.patch("/interview_sessions")
def patch_session(
    request: Request,
    body: SessionPatch,
    user: Annotated[User, Depends(require_user)],
    id: str = Query(...),
    select: str | None = None,
) -> Response:
    session_id = parse_id_filter(id)
    patch = body.model_dump(mode="json", exclude_unset=True)
    if not patch:
        raise ApiError(400, "Empty patch", "invalid_patch")
    if "candidate_token" in patch:
        existing = store_from(request).by_candidate_token(patch["candidate_token"])
        if existing and existing["id"] != session_id:
            raise ApiError(400, "Candidate token already in use", "duplicate_token")
    row = store_from(request).update_session(user.id, session_id, patch)
    if select:
        if not row:
            raise not_single()
        return JSONResponse(row, media_type=OBJECT_MEDIA if wants_object(request) else "application/json")
    return Response(status_code=204)


@router.delete("/interview_sessions", status_code=204)
def delete_session(request: Request, user: Annotated[User, Depends(require_user)], id: str = Query(...)) -> Response:
    store_from(request).delete_session(user.id, parse_id_filter(id))
    return Response(status_code=204)
