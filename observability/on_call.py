"""Read-only local incident evidence collector for a human or coding agent."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


PROMETHEUS_QUERIES = {
    "HTTP request rate": "sum(rate(http_server_request_duration_seconds_count[5m]))",
    "HTTP error ratio": "sum(rate(http_server_request_duration_seconds_count{http_response_status_code=~\"4..|5..\"}[5m])) / clamp_min(sum(rate(http_server_request_duration_seconds_count[5m])), 0.001)",
    "HTTP P95 latency": "histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket[5m])))",
    "Canvas failures": "sum(increase(blueprint_canvas_component_creation_errors_total[15m]))",
    "Firing alerts": "ALERTS{alertstate=\"firing\"}",
}


def _json_get(base: str, path: str, params: dict | None = None) -> dict:
    url = f"{base.rstrip('/')}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def collect_evidence(prometheus: str, loki: str, tempo: str, minutes: int) -> dict:
    end = datetime.now(UTC)
    start = end - timedelta(minutes=minutes)
    metrics = {
        name: _json_get(prometheus, "/api/v1/query", {"query": query}).get("data", {}).get("result", [])
        for name, query in PROMETHEUS_QUERIES.items()
    }
    logs = _json_get(loki, "/loki/api/v1/query_range", {
        "query": '{service_name="blueprint-backend"} | json',
        "start": str(int(start.timestamp() * 1_000_000_000)),
        "end": str(int(end.timestamp() * 1_000_000_000)),
        "limit": "20",
        "direction": "backward",
    }).get("data", {}).get("result", [])
    traces = _json_get(tempo, "/api/search", {
        "tags": "service.name=blueprint-backend",
        "limit": "20",
        "start": str(int(start.timestamp())),
        "end": str(int(end.timestamp())),
    }).get("traces", [])
    return {
        "generated_at": end.isoformat(),
        "window_minutes": minutes,
        "metrics": metrics,
        "logs": logs,
        "traces": traces,
    }


def render_report(evidence: dict) -> str:
    lines = [
        "# Incident evidence report",
        "",
        f"Generated: {evidence['generated_at']}",
        f"Window: last {evidence['window_minutes']} minutes",
        "",
        "## Metrics and alerts",
    ]
    for name, result in evidence["metrics"].items():
        lines.append(f"- {name}: `{json.dumps(result, separators=(',', ':'))}`")
    lines.extend([
        "",
        "## Correlated logs",
        f"- Streams returned: {len(evidence['logs'])}",
        f"- Evidence: `{json.dumps(evidence['logs'], separators=(',', ':'))}`",
        "",
        "## Traces",
        f"- Traces returned: {len(evidence['traces'])}",
        f"- Evidence: `{json.dumps(evidence['traces'], separators=(',', ':'))}`",
        "",
        "## Safety",
        "Read-only collection only. No application mutation, commit, deployment, or model call was performed.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=15)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence = collect_evidence(
        os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090"),
        os.getenv("LOKI_URL", "http://127.0.0.1:3100"),
        os.getenv("TEMPO_URL", "http://127.0.0.1:3200"),
        args.minutes,
    )
    report = render_report(evidence)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
