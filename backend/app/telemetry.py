"""OpenTelemetry tracing for the FastAPI application."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import json
import logging
import os
from time import monotonic_ns

# Stable HTTP conventions provide the route template used after target redaction.
os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = "http"

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor
from opentelemetry.trace import Span


DEFAULT_SERVICE_NAME = "blueprint-backend"
_OTLP_SIGNAL_ENDPOINT = {
    "traces": "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "metrics": "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "logs": "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
}


def resource_attributes(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build required resource attributes from the deployment's existing values."""
    values = os.environ if environ is None else environ
    return {
        "service.name": values.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME),
        "deployment.environment.name": values.get("BLUEPRINT_ENV", "production"),
        "service.version": values.get("BLUEPRINT_REVISION", "unknown"),
    }


def signal_export_configured(signal: str, environ: Mapping[str, str] | None = None) -> bool:
    """Return whether one signal has an explicit OTLP destination."""
    values = os.environ if environ is None else environ
    if signal not in _OTLP_SIGNAL_ENDPOINT:
        raise ValueError(f"Unsupported OpenTelemetry signal: {signal}")
    if values.get(f"OTEL_{signal.upper()}_EXPORTER", "").strip().lower() == "none":
        return False
    return bool(
        values.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        or values.get(_OTLP_SIGNAL_ENDPOINT[signal], "").strip()
    )


def otlp_export_configured(environ: Mapping[str, str] | None = None) -> bool:
    """Backward-compatible trace export check used by focused tests."""
    return signal_export_configured("traces", environ)


def _redact_request_target(span: Span, scope: dict) -> None:
    """Keep route-level observability without exporting concrete URLs."""
    scope["_blueprint_otel_started_ns"] = monotonic_ns()
    if not span or not span.is_recording():
        return
    span.set_attribute("url.path", "/redacted")
    if scope.get("query_string"):
        span.set_attribute("url.query", "[REDACTED]")


class _SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def _request_logger(app: FastAPI, logger_provider: LoggerProvider, export_logs: bool) -> logging.Logger:
    logger = logging.getLogger(f"blueprint.http.{id(app)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    stream = logging.StreamHandler()
    stream.setFormatter(_SafeJsonFormatter())
    logger.addHandler(stream)
    if export_logs:
        logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))
    return logger


def _response_log_hook(logger: logging.Logger):
    def emit_response_log(_span: Span, scope: dict, message: dict) -> None:
        if message.get("type") != "http.response.start":
            return
        route = getattr(scope.get("route"), "path", "unmatched")
        started_ns = scope.get("_blueprint_otel_started_ns", monotonic_ns())
        context = trace.get_current_span().get_span_context()
        fields = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": "INFO",
            "event": "http.request.completed",
            "http.method": scope.get("method", "UNKNOWN"),
            "http.route": route,
            "http.status_code": int(message.get("status", 0)),
            "duration_ms": round((monotonic_ns() - started_ns) / 1_000_000, 3),
            "trace_id": f"{context.trace_id:032x}" if context.is_valid else None,
            "span_id": f"{context.span_id:016x}" if context.is_valid else None,
        }
        logger.info(
            json.dumps(fields, separators=(",", ":"), ensure_ascii=True),
            extra={
                "http_method": fields["http.method"],
                "http_route": route,
                "http_status_code": fields["http.status_code"],
                "duration_ms": fields["duration_ms"],
            },
        )

    return emit_response_log


def _metric_interval(values: Mapping[str, str]) -> int:
    try:
        return max(1_000, int(values.get("OTEL_METRIC_EXPORT_INTERVAL", "10000")))
    except ValueError:
        return 10_000


def configure_telemetry(
    app: FastAPI,
    *,
    environ: Mapping[str, str] | None = None,
    span_processor: SpanProcessor | None = None,
    metric_reader: MetricReader | None = None,
) -> TracerProvider:
    """Instrument FastAPI, SQLAlchemy, metrics and safe correlated logs."""
    values = os.environ if environ is None else environ
    resource = Resource.create(resource_attributes(values))
    provider = TracerProvider(resource=resource)

    trace_export = signal_export_configured("traces", values)
    if span_processor is not None:
        provider.add_span_processor(span_processor)
    elif trace_export:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    readers = [metric_reader] if metric_reader is not None else []
    metric_export = signal_export_configured("metrics", values)
    if metric_reader is None and metric_export:
        readers.append(PeriodicExportingMetricReader(
            OTLPMetricExporter(),
            export_interval_millis=_metric_interval(values),
        ))
    meter_provider = MeterProvider(resource=resource, metric_readers=readers)

    log_export = signal_export_configured("logs", values)
    logger_provider = LoggerProvider(resource=resource)
    if log_export:
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    request_logger = _request_logger(app, logger_provider, log_export)

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        meter_provider=meter_provider,
        server_request_hook=_redact_request_target,
        client_response_hook=_response_log_hook(request_logger),
        http_capture_headers_server_request=[],
        http_capture_headers_server_response=[],
        http_capture_headers_sanitize_fields=[".*"],
        # Keep send hooks enabled so response status/duration logs are emitted.
        exclude_spans=["receive"],
        excluded_urls=r"/realtime/v1/websocket,/health/ready",
    )

    sqlalchemy = SQLAlchemyInstrumentor()
    if hasattr(app.state, "store") and not sqlalchemy.is_instrumented_by_opentelemetry:
        sqlalchemy.instrument(
            engine=app.state.store.engine,
            tracer_provider=provider,
            meter_provider=meter_provider,
            enable_commenter=False,
            enable_attribute_commenter=False,
        )

    app.state.otel_tracer_provider = provider
    app.state.otel_meter_provider = meter_provider
    app.state.otel_logger_provider = logger_provider
    app.state.otel_request_logger = request_logger
    app.state.otel_exporter_configured = trace_export or metric_export or log_export
    return provider


def shutdown_telemetry(app: FastAPI) -> None:
    """Flush exporters without making shutdown depend on a Collector."""
    for handler in app.state.otel_request_logger.handlers:
        handler.close()
    app.state.otel_request_logger.handlers.clear()
    app.state.otel_logger_provider.shutdown()
    app.state.otel_meter_provider.shutdown()
    app.state.otel_tracer_provider.shutdown()
