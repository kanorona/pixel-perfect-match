import os

import pytest
from fastapi.testclient import TestClient

from app.auth import PUBLIC_KEY
from app.main import create_app
from app.store import DEMO_EMAIL, DEMO_PASSWORD


POSTGRES_URL = os.getenv("BLUEPRINT_TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="set BLUEPRINT_TEST_POSTGRES_URL to run PostgreSQL integration")
def test_postgres_auth_and_session_crud():
    with TestClient(create_app(POSTGRES_URL)) as client:
        key_headers = {"apikey": PUBLIC_KEY}
        login = client.post(
            "/auth/v1/token?grant_type=password",
            headers=key_headers,
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        )
        assert login.status_code == 200, login.text
        auth = login.json()
        headers = {**key_headers, "Authorization": f"Bearer {auth['access_token']}"}

        created = client.post(
            "/rest/v1/interview_sessions?select=id",
            headers=headers,
            json={
                "owner_id": auth["user"]["id"],
                "title": "PostgreSQL integration check",
                "prompt": "Temporary test session",
                "duration_minutes": 15,
            },
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["id"]

        rows = client.get(
            "/rest/v1/interview_sessions",
            headers=headers,
            params={"id": f"eq.{session_id}"},
        )
        assert rows.status_code == 200
        assert rows.json()[0]["title"] == "PostgreSQL integration check"

        deleted = client.delete(
            "/rest/v1/interview_sessions",
            headers=headers,
            params={"id": f"eq.{session_id}"},
        )
        assert deleted.status_code == 204
        assert client.app.state.store.engine.url.drivername == "postgresql+psycopg"
