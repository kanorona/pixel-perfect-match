import pytest
from fastapi.testclient import TestClient

from app.auth import PUBLIC_KEY
from app.main import create_app
from app.store import DEMO_EMAIL, DEMO_PASSWORD


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def key_headers():
    return {"apikey": PUBLIC_KEY}


@pytest.fixture
def signed_in(client, key_headers):
    response = client.post(
        "/auth/v1/token?grant_type=password",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        headers=key_headers,
    )
    assert response.status_code == 200, response.text
    session = response.json()
    return session, {**key_headers, "Authorization": f"Bearer {session['access_token']}"}
