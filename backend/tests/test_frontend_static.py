from fastapi.testclient import TestClient

from app.auth import PUBLIC_KEY
from app.main import create_app


def test_fastapi_serves_spa_and_keeps_api_routes(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    assets = static_dir / "assets"
    assets.mkdir(parents=True)
    (static_dir / "_shell.html").write_text("<!doctype html><title>Blueprint</title>", encoding="utf-8")
    (static_dir / "favicon.ico").write_bytes(b"icon")
    (static_dir / "robots.txt").write_text("User-agent: *", encoding="utf-8")
    (assets / "app.js").write_text("console.log('blueprint')", encoding="utf-8")
    monkeypatch.setenv("BLUEPRINT_STATIC_DIR", str(static_dir))
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"

    with TestClient(create_app(database_url)) as client:
        for path in ("/", "/auth", "/dashboard", "/sessions/123", "/join/invite"):
            response = client.get(path)
            assert response.status_code == 200
            assert "Blueprint" in response.text
            assert response.headers["content-type"].startswith("text/html")

        assert "blueprint" in client.get("/assets/app.js").text
        assert client.get("/favicon.ico").content == b"icon"
        assert client.get("/robots.txt").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/rest/v1/interview_sessions", headers={"apikey": PUBLIC_KEY}).status_code == 401
        assert client.get("/unknown").status_code == 404
