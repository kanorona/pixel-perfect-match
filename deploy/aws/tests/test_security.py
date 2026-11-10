"""Local deployment checks. These tests never invoke AWS APIs.

Run with the Python environment containing cfn-lint (and therefore PyYAML).
Set BLUEPRINT_RUN_DOCKER_TESTS=1 to build an isolated, disposable Compose stack.
"""

import base64
import io
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[3]
PERMISSIONS_FIX = "RUN chmod -R a+rX /app/backend/app /app/backend/static"
_restricted_images = None


def restricted_context(destination, dockerfile):
    """Send real root-owned 0700/0600 Linux metadata to the Docker daemon.

    A Windows bind mount cannot reproduce the permissions of the EC2 checkout.
    Use an explicit allowlist so private .env files never enter the context.
    """
    files = {
        "Dockerfile": dockerfile.encode(),
        ".dockerignore": (ROOT / ".dockerignore").read_bytes(),
        "backend/pyproject.toml": (ROOT / "backend/pyproject.toml").read_bytes(),
        "backend/uv.lock": (ROOT / "backend/uv.lock").read_bytes(),
    }
    excluded = {"node_modules", "dist", ".output", ".tanstack", ".nitro", ".vinxi", "__pycache__"}
    for source in [ROOT / "backend/app", ROOT / "frontend"]:
        for directory, directories, filenames in os.walk(source):
            directories[:] = [name for name in directories if name not in excluded]
            for name in filenames:
                if name.startswith(".env") or name.endswith(".pyc") or name == "package-lock.json":
                    continue
                path = Path(directory) / name
                if path.is_symlink():
                    raise AssertionError("Regression context must not include symlinks")
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    directories = {"."}
    for name in files:
        directories.update(parent.as_posix() for parent in Path(name).parents if parent.as_posix() != ".")
    with tarfile.open(destination, "w") as archive:
        for name in sorted(directories, key=lambda value: (value.count("/"), value)):
            entry = tarfile.TarInfo(name)
            entry.type = tarfile.DIRTYPE
            entry.mode = 0o700
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = "root"
            archive.addfile(entry)
        for name, content in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.mode = 0o600
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = "root"
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    with tarfile.open(destination) as archive:
        entries = archive.getmembers()
        assert all(entry.uid == entry.gid == 0 for entry in entries)
        assert all(entry.mode == (0o700 if entry.isdir() else 0o600) for entry in entries)
        assert not any(Path(entry.name).name.startswith(".env") for entry in entries)


def restricted_images():
    global _restricted_images
    if _restricted_images is not None:
        return _restricted_images
    suffix = uuid.uuid4().hex[:10]
    images = {name: f"blueprint-permissions-{suffix}-{name}:local" for name in ["baseline", "fixed"]}
    unittest.addModuleCleanup(lambda: subprocess.run(
        ["docker", "image", "rm", *images.values()], capture_output=True, check=True,
    ))
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert dockerfile.count(PERMISSIONS_FIX) == 1, "Update the negative-control fixture when the fix changes"
    with tempfile.TemporaryDirectory() as directory:
        for name in images:
            source = dockerfile if name == "fixed" else dockerfile.replace(PERMISSIONS_FIX, "")
            context = Path(directory) / f"{name}.tar"
            restricted_context(context, source)
            with context.open("rb") as stream:
                result = subprocess.run(
                    ["docker", "build", "--tag", images[name], "-"], stdin=stream,
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200,
                )
            if result.returncode:
                raise AssertionError(f"Restricted-context {name} image build failed:\n{result.stderr[-5000:]}")
    _restricted_images = images
    return images


@unittest.skipUnless(os.getenv("BLUEPRINT_RUN_DOCKER_TESTS") == "1", "Docker checks require explicit opt-in")
class RestrictedPermissions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = restricted_images()

    def test_negative_control_reproduces_permission_error(self):
        result = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", self.images["baseline"],
             "python", "-c", "import app.main"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PermissionError", result.stderr)
        self.assertIn("/app/backend/app", result.stderr)

    def test_appuser_can_import_and_read_all_runtime_files(self):
        probe = '''import importlib, json, os, pathlib, pwd, sys
assert os.geteuid() != 0
assert pwd.getpwuid(os.geteuid()).pw_name == "appuser"
for root in [pathlib.Path("/app/backend/app"), pathlib.Path("/app/backend/static")]:
    for path in [root, *root.rglob("*")]:
        assert path.stat().st_uid == 0, "Runtime source ownership changed"
        assert os.access(path, os.R_OK), "Runtime file is unreadable"
        if path.is_dir():
            assert os.access(path, os.X_OK), "Runtime directory is not traversable"
        assert not os.access(path, os.W_OK), "Runtime user should not modify source"
sys.path.insert(0, "/app")
for name in ["app.main", "backend.app.main"]:
    module = importlib.import_module(name)
    module.app.state.store.close()
assert not pathlib.Path("/app/backend/.env").exists()
assert not pathlib.Path("/app/.env").exists()
print(json.dumps({"user":"appuser","imports":"ok","runtime_access":"ok","source_writable":False}))
'''
        result = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", self.images["fixed"], "python", "-c", probe],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["user"], "appuser")
        self.assertNotIn("PermissionError", result.stderr)

    def test_fastapi_starts_as_default_nonroot_user(self):
        name = "blueprint-permissions-server-" + uuid.uuid4().hex[:10]
        try:
            subprocess.run(
                ["docker", "run", "-d", "--name", name, "-p", "127.0.0.1::8001", self.images["fixed"]],
                check=True, capture_output=True, timeout=30,
            )
            address = subprocess.run(
                ["docker", "port", name, "8001"], check=True, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            for attempt in range(40):
                try:
                    with urllib.request.urlopen("http://" + address + "/health/ready", timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.25)
            else:
                self.fail("Restricted-context FastAPI did not become ready")
            with urllib.request.urlopen("http://" + address + "/", timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"<html", response.read().lower())
            result = subprocess.run(
                ["docker", "exec", name, "id", "-un"], check=True, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.stdout.strip(), "appuser")
            logs = subprocess.run(
                ["docker", "logs", name], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            )
            self.assertNotIn("PermissionError", logs.stdout + logs.stderr)
        finally:
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=30)


class CloudFormationLoader(yaml.SafeLoader):
    pass


def intrinsic(loader, tag, node):
    key = {"Ref": "Ref", "Sub": "Fn::Sub"}.get(tag, tag)
    if isinstance(node, yaml.ScalarNode):
        return {key: loader.construct_scalar(node)}
    return {key: loader.construct_sequence(node)}


CloudFormationLoader.add_multi_constructor("!", intrinsic)


class EnvironmentIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_path = ROOT / "deploy/aws/blueprint-stack.yaml"
        cls.template_text = cls.template_path.read_text(encoding="utf-8")
        cls.template = yaml.load(cls.template_text, Loader=CloudFormationLoader)
        cls.environments = {}
        for name in ["development", "production"]:
            path = ROOT / f"deploy/aws/environments/{name}.parameters.example.json"
            values = json.loads(path.read_text(encoding="utf-8"))
            cls.environments[name] = {item["ParameterKey"]: item["ParameterValue"] for item in values}

    def test_environment_parameter_is_constrained(self):
        parameter = self.template["Parameters"]["EnvironmentName"]
        self.assertEqual(parameter["Default"], "development")
        self.assertEqual(parameter["AllowedValues"], ["development", "production"])
        self.assertIn("EnvironmentNetworkIsolation", self.template["Rules"])

    def test_examples_use_distinct_networks_and_invalid_secret_placeholders(self):
        development = self.environments["development"]
        production = self.environments["production"]
        self.assertEqual(development["EnvironmentName"], "development")
        self.assertEqual(production["EnvironmentName"], "production")
        self.assertNotEqual(development["VpcCidr"], production["VpcCidr"])
        self.assertNotEqual(development["PublicSubnetCidr"], production["PublicSubnetCidr"])
        networks = []
        for values in [development, production]:
            vpc = ipaddress.ip_network(values["VpcCidr"])
            subnet = ipaddress.ip_network(values["PublicSubnetCidr"])
            self.assertTrue(vpc.is_private)
            self.assertTrue(subnet.subnet_of(vpc))
            networks.append(vpc)
            self.assertTrue(values["OriginVerifyToken"].startswith("REPLACE_"))
            self.assertNotRegex(values["OriginVerifyToken"], r"^[a-f0-9]{64}$")
            self.assertNotRegex(values["RepoRef"], r"^[a-f0-9]{40}$")
        self.assertFalse(networks[0].overlaps(networks[1]))

    def test_database_is_generated_inside_each_stack(self):
        script = self.template["Resources"]["Instance"]["Properties"]["UserData"]["Fn::Base64"]["Fn::Sub"]
        self.assertIn('POSTGRES_DB=blueprint_${EnvironmentName}', script)
        self.assertIn('POSTGRES_PASSWORD=$(openssl rand -hex 32)', script)
        self.assertIn('BLUEPRINT_ENV=${EnvironmentName}', script)
        self.assertIn('BLUEPRINT_REVISION=${RepoRef}', script)
        compose = (ROOT / "docker-compose.aws.yaml").read_text(encoding="utf-8")
        self.assertIn('BLUEPRINT_REVISION: ${BLUEPRINT_REVISION:-unknown}', compose)
        self.assertNotIn("BLUEPRINT_DATABASE_URL", self.template["Parameters"])
        self.assertNotIn("Fn::ImportValue", self.template_text)
        self.assertNotIn("!ImportValue", self.template_text)

    def test_global_and_iam_names_are_stack_generated(self):
        resources = self.template["Resources"]
        self.assertNotIn("RoleName", resources["InstanceRole"]["Properties"])
        self.assertNotIn("InstanceProfileName", resources["InstanceProfile"]["Properties"])
        distribution = resources["CloudFrontDistribution"]["Properties"]["DistributionConfig"]
        self.assertNotIn("Aliases", distribution)
        self.assertNotIn("Name", resources["ElasticIp"]["Properties"])

    def test_security_controls_remain_per_environment(self):
        resources = self.template["Resources"]
        metadata = resources["Instance"]["Properties"]["MetadataOptions"]
        self.assertEqual(metadata, {"HttpEndpoint": "enabled", "HttpTokens": "required"})
        ingress = resources["SecurityGroup"]["Properties"]["SecurityGroupIngress"]
        self.assertEqual(ingress[0]["SourcePrefixListId"], {"Ref": "CloudFrontPrefixListId"})
        policies = resources["InstanceRole"]["Properties"]["ManagedPolicyArns"]
        self.assertEqual(policies, ["arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"])
        self.assertTrue(self.template["Parameters"]["OriginVerifyToken"]["NoEcho"])


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
        image = restricted_images()["fixed"]
        override = Path(cls.directory.name) / "override.yaml"
        override.write_text(
            'services:\n'
            f'  app:\n    image: {image}\n'
            '  caddy:\n'
            '    ports: !override ["127.0.0.1:0:80"]\n'
            '  postgres:\n'
            '    ports: ["127.0.0.1:0:5432"]\n', encoding="utf-8",
        )
        cls.command = ["docker", "compose", "--project-name", cls.project,
                       "--env-file", os.devnull, "-f", str(ROOT / "docker-compose.aws.yaml"), "-f", str(override)]
        cls.addClassCleanup(lambda: cls.compose("down", "--volumes", "--remove-orphans"))
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
