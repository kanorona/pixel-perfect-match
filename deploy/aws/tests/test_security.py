"""Local deployment checks. These tests never invoke AWS APIs.

Run with the Python environment containing cfn-lint (and therefore PyYAML).
Set BLUEPRINT_RUN_DOCKER_TESTS=1 to build an isolated, disposable Compose stack.
"""

import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[3]


class CloudFormationLoader(yaml.SafeLoader):
    pass


def intrinsic(loader, tag, node):
    key = {"Ref": "Ref", "Sub": "Fn::Sub"}.get(tag, tag)
    if isinstance(node, yaml.ScalarNode):
        return {key: loader.construct_scalar(node)}
    return {key: loader.construct_sequence(node)}


CloudFormationLoader.add_multi_constructor("!", intrinsic)


class BootstrapSignals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bash = shutil.which("bash")
        if os.name == "nt":
            git_bash = Path("C:/Program Files/Git/bin/bash.exe")
            cls.bash = str(git_bash) if git_bash.exists() else None
        if not cls.bash:
            raise unittest.SkipTest("Bash is required for the signaling harness")
        template = yaml.load((ROOT / "deploy/aws/blueprint-stack.yaml").read_text(), Loader=CloudFormationLoader)
        cls.script = template["Resources"]["Instance"]["Properties"]["UserData"]["Fn::Base64"]["Fn::Sub"]

    def run_wrapper(self, payload, delivery_failures=0):
        # Replace only the bootstrap payload. Exercise the real EXIT handler,
        # timeout and cfn-signal invocation, with a local signaling executable.
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            signals = temp / "signals"
            helper = temp / "cfn-signal"
            helper.write_text(
                '#!/usr/bin/env bash\n'
                f'printf "%s\\n" "$2" >> "{signals.as_posix()}"\n'
                f'test "$(wc -l < "{signals.as_posix()}")" -gt {delivery_failures}\n',
                encoding="utf-8", newline="\n",
            )
            helper.chmod(0o700)
            script = self.script.replace("/var/log/blueprint-bootstrap.log", (temp / "bootstrap.log").as_posix())
            script = script.replace("/run/blueprint-origin.curl", (temp / "origin.curl").as_posix())
            script = script.replace("/opt/aws/bin/cfn-signal", f'"{helper.as_posix()}"')
            script = script.replace("'${AWS::StackName}'", "'local-test'")
            script = script.replace("'${AWS::Region}'", "'us-east-2'")
            script = script.replace("1440 bash", "1 bash")
            start = script.index("set -euo pipefail", script.index("<<'BOOTSTRAP'"))
            end = script.rindex("BOOTSTRAP")
            script = script[:start] + payload + "\n" + script[end:]
            # Retry backoff is unnecessary in a local transport-failure test.
            script = script.replace("sleep 5", ":")
            result = subprocess.run([self.bash, "-s"], input=script, text=True, encoding="utf-8",
                                    errors="replace", capture_output=True, timeout=15)
            sent = signals.read_text().splitlines() if signals.exists() else []
            return result.returncode, sent

    def test_success_is_signaled_after_payload_succeeds(self):
        self.assertEqual(self.run_wrapper("exit 0"), (0, ["0"]))

    def test_userdata_shell_syntax(self):
        result = subprocess.run([self.bash, "-n"], input=self.script, text=True, encoding="utf-8",
                                errors="replace", capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failure_is_not_reported_as_success(self):
        self.assertEqual(self.run_wrapper("exit 7"), (7, ["7"]))

    def test_timeout_sends_failure(self):
        status, signals = self.run_wrapper("sleep 3")
        self.assertEqual(status, 124)
        self.assertEqual(signals, ["124"])

    def test_signal_delivery_retries(self):
        self.assertEqual(self.run_wrapper("exit 0", delivery_failures=2), (0, ["0", "0", "0"]))

    def test_signal_delivery_failure_is_bounded(self):
        self.assertEqual(self.run_wrapper("exit 0", delivery_failures=10), (1, ["0"] * 5))


@unittest.skipUnless(os.getenv("BLUEPRINT_RUN_DOCKER_TESTS") == "1", "Docker checks require explicit opt-in")
class OriginIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.project = "blueprint-security-" + uuid.uuid4().hex[:10]
        cls.token = secrets.token_hex(32)
        cls.password = secrets.token_hex(32)
        cls.env = {**os.environ, "POSTGRES_USER": "validation", "POSTGRES_DB": "validation",
                   "POSTGRES_PASSWORD": cls.password, "BLUEPRINT_ORIGIN_TOKEN": cls.token}
        override = Path(cls.directory.name) / "override.yaml"
        override.write_text(
            'services:\n'
            '  caddy:\n'
            '    ports: !override ["127.0.0.1:0:80"]\n'
            '  postgres:\n'
            '    ports: ["127.0.0.1:0:5432"]\n', encoding="utf-8",
        )
        cls.command = ["docker", "compose", "--project-name", cls.project,
                       "--env-file", os.devnull, "-f", str(ROOT / "docker-compose.aws.yaml"), "-f", str(override)]
        cls.addClassCleanup(lambda: cls.compose("down", "--volumes", "--remove-orphans"))
        cls.compose("build", "app", timeout=1200)
        cls.compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "150", timeout=180)
        cls.address = cls.compose("port", "caddy", "80").strip()
        cls.database_address = cls.compose("port", "postgres", "5432").strip()

    @classmethod
    def compose(cls, *arguments, timeout=60, env=None):
        result = subprocess.run(cls.command + list(arguments), cwd=ROOT, env=env or cls.env,
                                text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout)
        if result.returncode:
            details = (result.stdout + result.stderr).replace(cls.token, "[REDACTED]").replace(cls.password, "[REDACTED]")
            raise AssertionError(f"Compose {arguments[0]} failed:\n{details[-5000:]}")
        return result.stdout

    def request(self, path, token=None, data=None, headers=None):
        request_headers = dict(headers or {})
        if token is not None:
            request_headers["X-Blueprint-Origin-Token"] = token
        if data is not None:
            data = json.dumps(data).encode()
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request("http://" + self.address + path, data=data, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as response:
            return response.code, response.read()

    def test_missing_and_wrong_tokens_are_rejected(self):
        for path in ["/", "/health/ready", "/auth/v1/signup", "/realtime/v1/websocket"]:
            for token in [None, "invalid", secrets.token_hex(32)]:
                self.assertEqual(self.request(path, token=token)[0], 403)

    def test_valid_token_reaches_frontend_and_database_readiness(self):
        self.assertEqual(self.request("/health/ready", token=self.token)[0], 200)
        status, body = self.request("/", token=self.token)
        self.assertEqual(status, 200)
        self.assertIn(b"<html", body.lower())

    def test_known_demo_login_is_absent_in_production(self):
        # Public development examples are test input, never deployment secrets.
        self.assertEqual(self.request(
            "/auth/v1/token?grant_type=password", token=self.token,
            headers={"apikey": "sb_publishable_local_demo"},
            data={"email": "demo@example.com", "password": "DemoPass123!"},
        )[0], 400)

    def test_valid_token_preserves_websocket_upgrade(self):
        host, port = self.address.rsplit(":", 1)
        with socket.create_connection((host, int(port)), timeout=5) as connection:
            websocket_key = base64.b64encode(secrets.token_bytes(16)).decode()
            request = (
                "GET /realtime/v1/websocket?apikey=sb_publishable_local_demo HTTP/1.1\r\n"
                f"Host: {self.address}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {websocket_key}\r\nSec-WebSocket-Version: 13\r\n"
                f"X-Blueprint-Origin-Token: {self.token}\r\n\r\n"
            )
            connection.sendall(request.encode())
            self.assertEqual(connection.recv(4096).split(b"\r\n", 1)[0], b"HTTP/1.1 101 Switching Protocols")

    def test_compose_rejects_missing_origin_configuration(self):
        env = dict(self.env)
        env.pop("BLUEPRINT_ORIGIN_TOKEN")
        result = subprocess.run(self.command + ["config", "--quiet"], cwd=ROOT, env=env,
                                text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BLUEPRINT_ORIGIN_TOKEN", result.stderr)

    def test_caddy_denies_when_server_token_is_empty_or_malformed(self):
        script = (
            'caddy run --config /etc/caddy/Caddyfile >/dev/null 2>&1 &\n'
            'for attempt in $(seq 1 20); do\n'
            '  status=$(wget -S -O /dev/null --header "X-Blueprint-Origin-Token: $BLUEPRINT_ORIGIN_TOKEN" '
            'http://127.0.0.1/ 2>&1 | awk \'/HTTP/ {print $2; exit}\')\n'
            '  if [ "$status" = 403 ]; then exit 0; fi\n'
            '  sleep 0.2\n'
            'done\nexit 1\n'
        )
        for value in ["", "invalid"]:
            with self.subTest(configuration="empty" if not value else "malformed"):
                self.compose("run", "--rm", "--no-deps", "-T", "-e", "BLUEPRINT_ORIGIN_TOKEN=" + value,
                             "caddy", "sh", "-c", script)

    def test_origin_token_is_removed_before_proxying(self):
        # Run the actual Caddyfile against a local echo upstream in a one-off
        # container. Compare an empty body without printing a received token.
        script = (
            "sed 's/app:8001/127.0.0.1:8002/' /etc/caddy/Caddyfile >/tmp/origin-test\n"
            "printf '\\n:8002 {\\n respond \"{http.request.header.X-Blueprint-Origin-Token}\"\\n}\\n' "
            ">>/tmp/origin-test\n"
            "caddy validate --adapter caddyfile --config /tmp/origin-test >/dev/null || exit 1\n"
            "caddy run --adapter caddyfile --config /tmp/origin-test >/dev/null 2>&1 &\n"
            'for attempt in $(seq 1 20); do\n'
            '  body=$(wget -q -O - --header "X-Blueprint-Origin-Token: $BLUEPRINT_ORIGIN_TOKEN" '
            'http://127.0.0.1/)\n'
            '  status=$?\n'
            '  if [ "$status" = 0 ]; then test -z "$body"; exit $?; fi\n'
            '  sleep 0.2\n'
            'done\nexit 1\n'
        )
        self.compose("run", "--rm", "--no-deps", "-T", "caddy", "sh", "-c", script)

    def test_postgres_backend_integration(self):
        self.compose("exec", "-T", "postgres", "psql", "-U", "validation", "-d", "validation",
                     "-c", "CREATE DATABASE backend_integration")
        env = {**os.environ, "BLUEPRINT_TEST_POSTGRES_URL":
               f"postgresql://validation:{self.password}@{self.database_address}/backend_integration"}
        result = subprocess.run(
            ["uv", "--cache-dir", str(ROOT / ".uv-cache"), "run", "--no-sync", "python", "-m", "pytest",
             "tests/test_postgres.py", "-q", "--basetemp", str(Path(self.directory.name) / "pytest")],
            cwd=ROOT / "backend", env=env, text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).replace(self.password, "[REDACTED]"))


if __name__ == "__main__":
    unittest.main()
