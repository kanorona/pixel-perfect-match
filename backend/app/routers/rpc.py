"""Guest operations keyed by the secret invitation token."""

import json

from fastapi import APIRouter, Depends, Request

from app.auth import ApiError, require_api_key, store_from
from app.models import CanvasSaveRequest, TokenRequest

router = APIRouter(prefix="/rest/v1/rpc", tags=["Candidate"], dependencies=[Depends(require_api_key)])
GUEST_FIELDS = (
    "id", "title", "prompt", "duration_minutes", "status",
    "candidate_editing_locked", "canvas", "started_at",
)


@router.post("/get_session_by_token")
def get_session_by_token(body: TokenRequest, request: Request) -> list[dict]:
    row = store_from(request).by_candidate_token(body.token)
    return [{field: row[field] for field in GUEST_FIELDS}] if row else []


@router.post("/save_canvas_by_token")
def save_canvas_by_token(body: CanvasSaveRequest, request: Request) -> bool:
    if len(json.dumps(body.canvas, separators=(",", ":")).encode("utf-8")) > 2_000_000:
        request.app.state.metrics.component_creation_errors.add(1)
        raise ApiError(400, "Canvas too large", "canvas_too_large")
    saved, created_elements = store_from(request).save_candidate_canvas(body.token, body.canvas)
    if saved:
        if created_elements:
            request.app.state.metrics.canvas_elements_created.add(created_elements)
    else:
        request.app.state.metrics.component_creation_errors.add(1)
    return saved
