import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "on_call", Path(__file__).resolve().parents[1] / "on_call.py"
)
on_call = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(on_call)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_collects_read_only_evidence_and_renders_report():
    urls = []

    def response(url, timeout):
        urls.append((url, timeout))
        if "/api/search" in url:
            return Response({"traces": [{"traceID": "abc"}]})
        return Response({"data": {"result": []}})

    with patch.object(on_call, "urlopen", side_effect=response):
        evidence = on_call.collect_evidence("http://prom", "http://loki", "http://tempo", 10)

    report = on_call.render_report(evidence)
    assert len(urls) == len(on_call.PROMETHEUS_QUERIES) + 2
    assert all(timeout == 5 for _, timeout in urls)
    assert "No application mutation" in report
    assert "abc" in report
