from app.store import normalize_database_url


def test_standard_postgres_url_uses_psycopg_driver():
    configured = "postgresql://sdip:sdip@localhost:5432/sdip"

    assert normalize_database_url(configured) == "postgresql+psycopg://sdip:sdip@localhost:5432/sdip"


def test_explicit_driver_and_sqlite_urls_are_unchanged():
    psycopg_url = "postgresql+psycopg://user:password@db:5432/app"
    sqlite_url = "sqlite:///./blueprint.db"

    assert normalize_database_url(psycopg_url) == psycopg_url
    assert normalize_database_url(sqlite_url) == sqlite_url
