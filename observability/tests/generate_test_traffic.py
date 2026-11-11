"""Generate disposable local application traffic for observability validation."""

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import websockets


BASE_URL = os.getenv("VALIDATION_BASE_URL", "http://app:8001")
API_KEY = "sb_publishable_local_demo"


def request(path, *, method="GET", payload=None, access_token=None):
    headers = {"apikey": API_KEY, "Accept": "application/vnd.pgrst.object+json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE_URL + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as response:
        raw = response.read()
        return response.code, json.loads(raw) if raw else None


async def join_once(session_id):
    ws_url = BASE_URL.replace("http://", "ws://") + f"/realtime/v1/websocket?apikey={API_KEY}&vsn=2.0.0"
    async with websockets.connect(ws_url) as socket:
        await socket.send(json.dumps(["1", "1", f"room:{session_id}", "phx_join", {"config": {}}]))
        await socket.recv()


status, login = request(
    "/auth/v1/token?grant_type=password",
    method="POST",
    payload={"email": "demo@example.com", "password": "DemoPass123!"},
)
assert status == 200
token = login["access_token"]
owner_id = login["user"]["id"]
status, created = request(
    "/rest/v1/interview_sessions?select=id",
    method="POST",
    access_token=token,
    payload={"owner_id": owner_id, "title": "Observability validation", "prompt": "Disposable", "duration_minutes": 15},
)
assert status == 201
session_id = created["id"]

try:
    query = urllib.parse.urlencode({"id": f"eq.{session_id}", "select": "*"})
    status, session = request(
        f"/rest/v1/interview_sessions?{query}",
        method="PATCH",
        access_token=token,
        payload={"status": "live"},
    )
    assert status == 200
    candidate_token = session["candidate_token"]
    status, result = request(
        "/rest/v1/rpc/save_canvas_by_token",
        method="POST",
        payload={"_token": candidate_token, "_canvas": {"elements": [{"id": "validation-element", "kind": "text"}]}},
    )
    assert status == 200 and result is True
    status, _ = request(
        "/rest/v1/rpc/save_canvas_by_token",
        method="POST",
        payload={"_token": candidate_token, "_canvas": {"elements": [], "padding": "x" * 2_000_000}},
    )
    assert status == 400
    asyncio.run(join_once(session_id))
finally:
    query = urllib.parse.urlencode({"id": f"eq.{session_id}"})
    request(f"/rest/v1/interview_sessions?{query}", method="DELETE", access_token=token)

print("Controlled application traffic: OK")
