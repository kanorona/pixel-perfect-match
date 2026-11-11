from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.telemetry import (
    configure_telemetry,
    otlp_export_configured,
    resource_attributes,
    shutdown_telemetry,
)


def test_resource_attributes_reuse_existing_environment_and_revision():
    attributes = resource_attributes({
        "BLUEPRINT_ENV": "development",
        "BLUEPRINT_REVISION": "a" * 40,
    })

    assert attributes == {
        "service.name": "blueprint-backend",
        "deployment.environment.name": "development",
        "service.version": "a" * 40,
    }


def test_otlp_export_requires_an_explicit_endpoint():
    assert otlp_export_configured({}) is False
    assert otlp_export_configured({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318"}) is True
    assert otlp_export_configured({
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://collector:4318/v1/traces",
    }) is True
    assert otlp_export_configured({
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
        "OTEL_TRACES_EXPORTER": "none",
    }) is False


def test_fastapi_request_span_uses_route_template_without_sensitive_values():
    exporter = InMemorySpanExporter()
    app = FastAPI()

    @app.post("/items/{item_id}")
    def create_item(item_id: str, body: dict) -> dict:
        return {"item_id": item_id, "accepted": bool(body)}

    provider = configure_telemetry(
        app,
        environ={"BLUEPRINT_ENV": "test", "BLUEPRINT_REVISION": "test-sha"},
        span_processor=SimpleSpanProcessor(exporter),
    )
    try:
        response = TestClient(app).post(
            "/items/private-item?token=query-secret",
            headers={"Authorization": "Bearer header-secret"},
            json={"password": "body-secret"},
        )
        assert response.status_code == 200

        spans = exporter.get_finished_spans()
        route_spans = [
            candidate
            for candidate in spans
            if candidate.attributes.get("http.route") == "/items/{item_id}"
        ]
        assert len(route_spans) == 1
        span = route_spans[0]
        assert span.attributes["http.route"] == "/items/{item_id}"
        assert span.attributes["url.path"] == "/redacted"
        assert span.attributes["url.query"] == "[REDACTED]"
        serialized = repr([
            (candidate.name, candidate.attributes, candidate.events)
            for candidate in spans
        ])
        for secret in ("private-item", "query-secret", "header-secret", "body-secret"):
            assert secret not in serialized
    finally:
        provider.shutdown()


def test_request_succeeds_when_collector_is_unavailable(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.05")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_LOGS_EXPORTER", "none")
    app = FastAPI()

    @app.get("/available")
    def available() -> dict[str, bool]:
        return {"ok": True}

    configure_telemetry(app)
    try:
        response = TestClient(app).get("/available")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
    finally:
        shutdown_telemetry(app)
