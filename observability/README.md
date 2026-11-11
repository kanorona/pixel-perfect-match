# Local observability

Start independently with `docker compose -f observability/docker-compose.yaml up -d`.
Grafana is available only on `http://127.0.0.1:3000` (`admin` / `admin`). The
local exercise retains data for seven days and binds every published port to
loopback. Set the application's `OTEL_EXPORTER_OTLP_ENDPOINT` to
`http://host.docker.internal:4318` in Docker or `http://127.0.0.1:4318` on the host.
For the local application Compose, use
`docker compose --env-file observability/local.env up -d --build db app`.

Prometheus evaluates the three alert rules in `prometheus/rules/alerts.yaml`.
Initial thresholds are 10% HTTP errors, one-second P95 latency, and three canvas
failures in five minutes. Tune them only after observing a representative traffic
baseline. `on_call.py` reads local metrics, logs and traces and produces an
evidence report; it never calls a model or mutates the application.
