from app.store import DEMO_EMAIL


def test_auth_and_seeded_dashboard(client, key_headers, signed_in):
    session, headers = signed_in
    assert session["user"]["email"] == DEMO_EMAIL
    assert client.get("/auth/v1/user", headers=headers).json()["id"] == session["user"]["id"]

    response = client.get(
        "/rest/v1/interview_sessions",
        params={"select": "id,title,prompt,status,duration_minutes,created_at,updated_at,candidate_token,canvas",
                "order": "updated_at.desc"},
        headers=headers,
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"draft", "live"}
    assert all(set(row) == {"id", "title", "prompt", "status", "duration_minutes",
                                "created_at", "updated_at", "candidate_token", "canvas"} for row in rows)


def test_session_lifecycle_and_guest_token(client, signed_in, key_headers):
    session, headers = signed_in
    created = client.post(
        "/rest/v1/interview_sessions?select=id",
        json={"owner_id": session["user"]["id"], "title": "New interview",
              "prompt": "Design a queue", "duration_minutes": 45},
        headers={**headers, "Accept": "application/vnd.pgrst.object+json"},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]
    detail = client.get(
        "/rest/v1/interview_sessions", params={"select": "*", "id": f"eq.{session_id}"},
        headers={**headers, "Accept": "application/vnd.pgrst.object+json"},
    )
    assert detail.status_code == 200
    token = detail.json()["candidate_token"]
    guest = client.post("/rest/v1/rpc/get_session_by_token", json={"_token": token}, headers=key_headers)
    assert guest.status_code == 200
    assert guest.json()[0]["id"] == session_id
    assert "owner_id" not in guest.json()[0]

    canvas = {"elements": [{"id": "one", "kind": "text", "u": 1, "x": 10, "y": 20, "text": "hello"}]}
    save = lambda: client.post("/rest/v1/rpc/save_canvas_by_token",
                               json={"_token": token, "_canvas": canvas}, headers=key_headers).json()
    assert save() is False  # Draft sessions are read-only for guests.
    changed = client.patch(
        "/rest/v1/interview_sessions", params={"id": f"eq.{session_id}", "select": "*"},
        json={"status": "live"}, headers={**headers, "Accept": "application/vnd.pgrst.object+json"},
    )
    assert changed.status_code == 200
    assert changed.json()["status"] == "live"
    assert save() is True
    assert client.patch("/rest/v1/interview_sessions", params={"id": f"eq.{session_id}"},
                        json={"candidate_editing_locked": True}, headers=headers).status_code == 204
    assert save() is False
    assert client.delete("/rest/v1/interview_sessions", params={"id": f"eq.{session_id}"},
                         headers=headers).status_code == 204
    assert client.post("/rest/v1/rpc/get_session_by_token", json={"_token": token},
                       headers=key_headers).json() == []


def test_auth_guards_ownership_refresh_and_logout(client, key_headers, signed_in):
    session, headers = signed_in
    assert client.get("/rest/v1/interview_sessions").status_code == 401
    assert client.get("/rest/v1/interview_sessions", headers=key_headers).status_code == 401
    assert client.post("/auth/v1/token?grant_type=password",
                       json={"email": DEMO_EMAIL, "password": "WrongPass123!"},
                       headers=key_headers).status_code == 400

    signup = client.post("/auth/v1/signup", json={"email": "other@example.com", "password": "OtherPass123!"},
                         headers=key_headers)
    assert signup.status_code == 200
    other = client.post("/auth/v1/token?grant_type=password",
                        json={"email": "other@example.com", "password": "OtherPass123!"},
                        headers=key_headers).json()
    other_headers = {**key_headers, "Authorization": f"Bearer {other['access_token']}"}
    assert client.get("/rest/v1/interview_sessions", headers=other_headers).json() == []
    owned_id = client.get("/rest/v1/interview_sessions", headers=headers).json()[0]["id"]
    assert client.get("/rest/v1/interview_sessions", params={"id": f"eq.{owned_id}"},
                      headers={**other_headers, "Accept": "application/vnd.pgrst.object+json"}).status_code == 406
    assert client.patch("/rest/v1/interview_sessions", params={"id": f"eq.{owned_id}", "select": "*"},
                        json={"status": "ended"}, headers=other_headers).status_code == 406
    assert client.get("/rest/v1/interview_sessions", params={"id": f"eq.{owned_id}"},
                      headers={**headers, "Accept": "application/vnd.pgrst.object+json"}).json()["status"] != "ended"
    forbidden = client.post("/rest/v1/interview_sessions?select=id",
                            json={"owner_id": session["user"]["id"], "title": "Wrong owner",
                                  "prompt": "", "duration_minutes": 60}, headers=other_headers)
    assert forbidden.status_code == 403

    refreshed = client.post("/auth/v1/token?grant_type=refresh_token",
                            json={"refresh_token": session["refresh_token"]}, headers=key_headers)
    assert refreshed.status_code == 200
    assert client.post("/auth/v1/logout?scope=global", headers=headers).status_code == 204
    assert client.get("/auth/v1/user", headers=headers).status_code == 401
    assert client.get("/auth/v1/user", headers={**key_headers,
        "Authorization": f"Bearer {refreshed.json()['access_token']}"}).status_code == 401


def test_canvas_limit_and_realtime_fallback(client, key_headers, signed_in):
    _, headers = signed_in
    rows = client.get("/rest/v1/interview_sessions", headers=headers).json()
    live = next(row for row in rows if row["status"] == "live")
    too_big = client.post("/rest/v1/rpc/save_canvas_by_token", headers=key_headers,
                          json={"_token": live["candidate_token"],
                                "_canvas": {"elements": [], "padding": "x" * 2_000_000}})
    assert too_big.status_code == 400
    fallback = client.post("/realtime/v1/api/broadcast", headers=key_headers,
                           json={"messages": [{"topic": f"room:{live['id']}", "event": "sync-req",
                                               "payload": {}, "private": False}]})
    assert fallback.status_code == 200


def test_browser_preflight_and_signup_session(client, key_headers):
    origin = "http://127.0.0.1:8081"
    preflight = client.options(
        "/auth/v1/token?grant_type=password",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "apikey,content-type"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin

    signup = client.post("/auth/v1/signup", headers=key_headers,
                         json={"email": "new@example.com", "password": "NewPass123!"})
    assert signup.status_code == 200
    assert signup.json()["access_token"]
    assert signup.json()["user"]["email"] == "new@example.com"
