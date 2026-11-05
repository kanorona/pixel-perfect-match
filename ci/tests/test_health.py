import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('health', ROOT / 'ci/check_health.py')
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class Response(io.BytesIO):
    status = 200


class HealthChecks(unittest.TestCase):
    def test_old_healthy_revision_cannot_satisfy_deployment(self):
        with patch.object(health.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response(b'{"status":"ready","revision":"old"}')) as request:
            with self.assertRaises(RuntimeError):
                health.check('https://example.com', 'new', attempts=2, delay=0)
            self.assertEqual(request.call_count, 2)

    def test_retries_network_failure_then_requires_the_expected_revision(self):
        with patch.object(health.urllib.request, 'urlopen', side_effect=[urllib.error.URLError('unavailable'), Response(b'{"status":"ready","revision":"new"}')]) as request:
            health.check('https://example.com', 'new', attempts=2, delay=0)
            self.assertEqual(request.call_args.args[0], 'https://example.com/health/ready')
            # No custom insecure SSL context is ever supplied.
            self.assertNotIn('context', request.call_args.kwargs)

    def test_insecure_public_url_is_rejected_before_request(self):
        with patch.object(health.urllib.request, 'urlopen') as request:
            with self.assertRaises(ValueError):
                health.check('http://example.com', 'new')
            request.assert_not_called()
