import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.auth import PUBLIC_KEY
from app.main import create_app
from app.store import DEMO_EMAIL, DEMO_PASSWORD, SessionRow, UserRow


@pytest.mark.parametrize("environment", [None, "production", "development"])
def test_demo_is_disabled_without_explicit_opt_in(tmp_path, monkeypatch, environment):
    monkeypatch.delenv("BLUEPRINT_SEED_DEMO", raising=False)
    if environment is None:
        monkeypatch.delenv("BLUEPRINT_ENV", raising=False)
    else:
        monkeypatch.setenv("BLUEPRINT_ENV", environment)
    with TestClient(create_app(f"sqlite:///{(tmp_path / 'app.db').as_posix()}")) as client:
        with client.app.state.store.Session() as db:
            assert db.scalar(select(func.count()).select_from(UserRow)) == 0
            assert db.scalar(select(func.count()).select_from(SessionRow)) == 0
        assert client.post(
            "/auth/v1/token?grant_type=password", headers={"apikey": PUBLIC_KEY},
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        ).status_code == 400
        # A fresh deployment remains usable through ordinary user registration.
        assert client.post(
            "/auth/v1/signup", headers={"apikey": PUBLIC_KEY},
            json={"email": "new@example.com", "password": "TestOnlyRegistration123!"},
        ).status_code == 200


@pytest.mark.parametrize("environment", [None, "production", "staging", "Development"])
def test_demo_opt_in_is_rejected_outside_development(tmp_path, monkeypatch, environment):
    if environment is None:
        monkeypatch.delenv("BLUEPRINT_ENV", raising=False)
    else:
        monkeypatch.setenv("BLUEPRINT_ENV", environment)
    with pytest.raises(ValueError, match="only allowed"):
        create_app(f"sqlite:///{(tmp_path / 'app.db').as_posix()}")
    assert not (tmp_path / "app.db").exists()


def test_demo_flag_rejects_ambiguous_values(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEPRINT_SEED_DEMO", "yes")
    with pytest.raises(ValueError, match="true or false"):
        create_app(f"sqlite:///{(tmp_path / 'app.db').as_posix()}")


def test_readiness_checks_database_and_hides_failure_details(client, monkeypatch):
    monkeypatch.setenv("BLUEPRINT_REVISION", "a" * 40)
    assert client.get("/health/ready").json() == {"status": "ready", "revision": "a" * 40}

    def unavailable():
        raise OperationalError("SELECT 1", {}, Exception("private database details"))

    monkeypatch.setattr(client.app.state.store, "check_ready", unavailable)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
