"""Emit controlled validation metrics to a local OTLP/HTTP Collector."""

import time

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource


reader = PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=1_000)
provider = MeterProvider(
    resource=Resource.create({
        "service.name": "blueprint-backend",
        "deployment.environment.name": "validation",
        "service.version": "controlled-test",
    }),
    metric_readers=[reader],
)
meter = provider.get_meter("blueprint.validation")
duration = meter.create_histogram("http.server.request.duration", unit="s")
failures = meter.create_counter("blueprint.canvas.component_creation.errors", unit="{error}")

attributes = {
    "http.request.method": "POST",
    "http.route": "/validation/{case}",
    "http.response.status_code": 500,
}
for _ in range(15):
    for _ in range(10):
        duration.record(2.0, attributes)
    failures.add(1)
    provider.force_flush()
    time.sleep(5)
provider.shutdown()
