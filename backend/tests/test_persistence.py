from fastapi.testclient import TestClient

from app.auth import PUBLIC_KEY
from app.main import create_app


def test_accounts_sessions_and_tokens_survive_restart(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'persistent.db').as_posix()}"
    monkeypatch.setenv("BLUEPRINT_DATABASE_URL", database_url)
    key_headers = {"apikey": PUBLIC_KEY}

    with TestClient(create_app()) as first:
        demo = first.post("/auth/v1/token?grant_type=password", headers=key_headers, json={
            "email": "demo@example.com", "password": "DemoPass123!",
        }).json()
        demo_headers = {**key_headers, "Authorization": f"Bearer {demo['access_token']}"}
        demo_rows = first.get("/rest/v1/interview_sessions", headers=demo_headers).json()
        assert len(demo_rows) == 2
        assert first.delete("/rest/v1/interview_sessions", headers=demo_headers,
                            params={"id": f"eq.{demo_rows[0]['id']}"}).status_code == 204

        signup = first.post("/auth/v1/signup", headers=key_headers, json={
            "email": "persistent@example.com", "password": "PersistentPass123!",
        })
        assert signup.status_code == 200
        auth = signup.json()
        headers = {**key_headers, "Authorization": f"Bearer {auth['access_token']}"}
        created = first.post("/rest/v1/interview_sessions?select=id", headers=headers, json={
            "owner_id": auth["user"]["id"], "title": "Saved interview",
            "prompt": "Design a durable queue", "duration_minutes": 45,
        })
        assert created.status_code == 201
        session_id = created.json()["id"]
        updated = first.patch("/rest/v1/interview_sessions", headers=headers,
                              params={"id": f"eq.{session_id}", "select": "*"},
                              json={"status": "live"})
        assert updated.status_code == 200
        invitation = updated.json()["candidate_token"]
        canvas = {"elements": [{"id": "note-1", "kind": "text", "text": "persisted"}]}
        assert first.post("/rest/v1/rpc/save_canvas_by_token", headers=key_headers,
                          json={"_token": invitation, "_canvas": canvas}).json() is True

    with TestClient(create_app()) as second:
        assert len(second.get("/rest/v1/interview_sessions", headers=demo_headers).json()) == 1
        # The signing key and refresh token also survive the process restart.
        assert second.get("/auth/v1/user", headers=headers).status_code == 200
        refreshed = second.post("/auth/v1/token?grant_type=refresh_token", headers=key_headers,
                                json={"refresh_token": auth["refresh_token"]})
        assert refreshed.status_code == 200
        rows = second.get("/rest/v1/interview_sessions", headers=headers).json()
        assert len(rows) == 1
        assert rows[0]["id"] == session_id
        assert rows[0]["canvas"] == canvas
        guest = second.post("/rest/v1/rpc/get_session_by_token", headers=key_headers,
                            json={"_token": invitation})
        assert guest.json()[0]["canvas"] == canvas
        assert second.app.state.store.database_url == database_url
