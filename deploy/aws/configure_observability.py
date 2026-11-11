"""Configure the observability EC2 host and validate private mTLS from Development.

Uses the authenticated AWS CLI and SSM Run Command. It never retrieves the
Grafana password, CA private key, or Development client private key.
"""

from __future__ import annotations

import argparse
import base64
import json
import shlex
import subprocess
import time
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
REMOTE_ROOT = PurePosixPath("/opt/pixel-perfect-observability")
FILES = (
    "observability/docker-compose.ec2.yaml",
    "observability/otel-collector/config-aws.yaml",
    "observability/prometheus/prometheus.yaml",
    "observability/prometheus/rules/alerts.yaml",
    "observability/loki/config.yaml",
    "observability/tempo/config.yaml",
    "observability/grafana/provisioning/datasources/datasources.yaml",
    "observability/grafana/provisioning/dashboards/dashboards.yaml",
    "observability/grafana/dashboards/application-overview.json",
)


class CommandError(RuntimeError):
    pass


def aws(profile: str, region: str, *args: str) -> str:
    command = ["aws", *args, "--profile", profile, "--region", region]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode:
        raise CommandError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def run_ssm(profile: str, region: str, instance_id: str, commands: list[str]) -> str:
    command_id = aws(
        profile,
        region,
        "ssm",
        "send-command",
        "--instance-ids",
        instance_id,
        "--document-name",
        "AWS-RunShellScript",
        "--parameters",
        json.dumps({"commands": commands}, separators=(",", ":")),
        "--query",
        "Command.CommandId",
        "--output",
        "text",
    )
    try:
        aws(
            profile,
            region,
            "ssm",
            "wait",
            "command-executed",
            "--command-id",
            command_id,
            "--instance-id",
            instance_id,
        )
    except CommandError:
        # A failed remote command makes the waiter fail too; retrieve the
        # invocation below so the actual remote stderr is reported.
        pass
    invocation = json.loads(
        aws(
            profile,
            region,
            "ssm",
            "get-command-invocation",
            "--command-id",
            command_id,
            "--instance-id",
            instance_id,
            "--output",
            "json",
        )
    )
    if invocation["Status"] != "Success":
        raise CommandError(
            f"SSM command failed: {invocation['StatusDetails']}\n"
            f"{invocation.get('StandardErrorContent', '').strip()}"
        )
    return invocation.get("StandardOutputContent", "").strip()


def upload_file(profile: str, region: str, instance_id: str, source: Path) -> None:
    relative = source.relative_to(ROOT / "observability")
    destination = REMOTE_ROOT.joinpath(*relative.parts)
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    quoted_destination = shlex.quote(str(destination))
    commands = [
        f"install -d -m 0755 {shlex.quote(str(destination.parent))}",
        f": > {quoted_destination}",
    ]
    for offset in range(0, len(encoded), 3000):
        chunk = encoded[offset : offset + 3000]
        commands.append(f"printf '%s' '{chunk}' | base64 -d >> {quoted_destination}")
    commands.append(f"chmod 0644 {quoted_destination}")
    run_ssm(profile, region, instance_id, commands)


def configure_host(profile: str, region: str, instance_id: str) -> str:
    bootstrap = run_ssm(
        profile,
        region,
        instance_id,
        [
            "test -f /var/lib/observability-bootstrap-ready",
            "findmnt -n /opt/observability-data",
            "docker compose version",
            "systemctl is-active amazon-cloudwatch-agent",
        ],
    )
    for relative in FILES:
        upload_file(profile, region, instance_id, ROOT / relative)
    run_ssm(
        profile,
        region,
        instance_id,
        [
            "chown 10001:10001 /opt/observability-data/pki/server.key /opt/observability-data/pki/server.crt /opt/observability-data/pki/ca.crt",
            "chmod 0640 /opt/observability-data/pki/server.key",
            "chmod 0600 /opt/observability-data/pki/ca.key",
            f"cd {REMOTE_ROOT} && docker compose --env-file /opt/observability-data/secrets/grafana.env -f docker-compose.ec2.yaml config --quiet",
            f"cd {REMOTE_ROOT} && docker compose --env-file /opt/observability-data/secrets/grafana.env -f docker-compose.ec2.yaml pull",
            f"cd {REMOTE_ROOT} && docker compose --env-file /opt/observability-data/secrets/grafana.env -f docker-compose.ec2.yaml up -d",
        ],
    )
    health = run_ssm(
        profile,
        region,
        instance_id,
        [
            "test $(docker ps --filter name=pixel-perfect-observability --format '{{.Names}}' | wc -l) -eq 5",
            "curl -fsS http://127.0.0.1:13133/",
            "curl -fsS http://127.0.0.1:9090/-/ready",
            "curl -fsS http://127.0.0.1:3100/ready",
            "curl -fsS http://127.0.0.1:3200/ready",
            "curl -fsS http://127.0.0.1:3000/api/health",
            "docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}'",
            "df -h /opt/observability-data",
            "test $(docker ps --filter name=pixel-perfect-observability --format '{{.Names}}' | wc -l) -eq 5",
        ],
    )
    return f"{bootstrap}\n{health}"


def configure_development_mtls(
    profile: str, region: str, observability_instance: str, development_instance: str
) -> str:
    csr_b64 = run_ssm(
        profile,
        region,
        development_instance,
        [
            "install -d -m 0700 /opt/blueprint/otel",
            "test -f /opt/blueprint/otel/client.key || openssl genrsa -out /opt/blueprint/otel/client.key 2048",
            "openssl req -new -key /opt/blueprint/otel/client.key -subj '/CN=blueprint-interviews-development' -out /opt/blueprint/otel/client.csr",
            "chmod 0600 /opt/blueprint/otel/client.key",
            "base64 -w0 /opt/blueprint/otel/client.csr",
        ],
    ).splitlines()[-1]
    signed_output = run_ssm(
        profile,
        region,
        observability_instance,
        [
            f"printf '%s' '{csr_b64}' | base64 -d >/tmp/development-client.csr",
            "printf 'extendedKeyUsage=clientAuth\\n' >/tmp/development-client.ext",
            "openssl x509 -req -in /tmp/development-client.csr -CA /opt/observability-data/pki/ca.crt -CAkey /opt/observability-data/pki/ca.key -CAcreateserial -out /tmp/development-client.crt -days 825 -sha256 -extfile /tmp/development-client.ext",
            "base64 -w0 /tmp/development-client.crt",
            "echo",
            "base64 -w0 /opt/observability-data/pki/ca.crt",
        ],
    ).splitlines()
    public_material = [line for line in signed_output if line and "Certificate request" not in line]
    client_cert_b64, ca_cert_b64 = public_material[-2:]
    now_ns = time.time_ns()
    trace_id = "11" * 16
    otlp_payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "development-connectivity-test"}},
                        {"key": "deployment.environment.name", "value": {"stringValue": "development"}},
                        {"key": "service.version", "value": {"stringValue": "validation"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "deployment-validation"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": "22" * 8,
                                "name": "private-mtls-validation",
                                "kind": 1,
                                "startTimeUnixNano": str(now_ns),
                                "endTimeUnixNano": str(now_ns + 1_000_000),
                                "status": {"code": 1},
                            }
                        ],
                    }
                ],
            }
        ]
    }
    payload_b64 = base64.b64encode(json.dumps(otlp_payload).encode()).decode("ascii")
    run_ssm(
        profile,
        region,
        development_instance,
        [
            f"printf '%s' '{client_cert_b64}' | base64 -d >/opt/blueprint/otel/client.crt",
            f"printf '%s' '{ca_cert_b64}' | base64 -d >/opt/blueprint/otel/ca.crt",
            "chmod 0644 /opt/blueprint/otel/client.crt /opt/blueprint/otel/ca.crt",
            f"printf '%s' '{payload_b64}' | base64 -d | curl --fail --silent --show-error --cacert /opt/blueprint/otel/ca.crt --cert /opt/blueprint/otel/client.crt --key /opt/blueprint/otel/client.key -H 'Content-Type: application/json' --data-binary @- https://10.44.0.10:4318/v1/traces",
        ],
    )
    trace_result = run_ssm(
        profile,
        region,
        observability_instance,
        [
            f"sleep 3; curl --fail --silent http://127.0.0.1:3200/api/traces/{trace_id} >/dev/null",
        ],
    )
    return trace_result


def enable_development_export(profile: str, region: str, development_instance: str) -> None:
    update_env = r"""python3 - <<'PY'
from pathlib import Path

path = Path('/opt/blueprint/.env')
updates = {
    'OTEL_EXPORTER_OTLP_ENDPOINT': 'https://10.44.0.10:4318',
    'OTEL_EXPORTER_OTLP_PROTOCOL': 'http/protobuf',
    'OTEL_EXPORTER_OTLP_CERTIFICATE': '/run/otel/ca.crt',
    'OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE': '/run/otel/client.crt',
    'OTEL_EXPORTER_OTLP_CLIENT_KEY': '/run/otel/client.key',
    'OTEL_EXPORTER_OTLP_TIMEOUT': '3',
    'OTEL_METRIC_EXPORT_INTERVAL': '10000',
    'OTEL_CERTIFICATE_HOST_DIR': '/opt/blueprint/otel',
}
output = []
seen = set()
for line in path.read_text().splitlines():
    key = line.split('=', 1)[0] if '=' in line else ''
    if key in updates:
        output.append(f'{key}={updates[key]}')
        seen.add(key)
    else:
        output.append(line)
output.extend(f'{key}={value}' for key, value in updates.items() if key not in seen)
temporary = path.with_name('.env.otel-next')
temporary.write_text('\n'.join(output) + '\n')
temporary.chmod(0o600)
temporary.replace(path)
PY"""
    run_ssm(
        profile,
        region,
        development_instance,
        [
            "test -f /opt/blueprint/otel/ca.crt -a -f /opt/blueprint/otel/client.crt -a -f /opt/blueprint/otel/client.key",
            "test -f /opt/blueprint/.env && test $(stat -c %a /opt/blueprint/.env) = 600",
            "chown 1000:1000 /opt/blueprint/otel/ca.crt /opt/blueprint/otel/client.crt /opt/blueprint/otel/client.key",
            "chmod 0444 /opt/blueprint/otel/ca.crt /opt/blueprint/otel/client.crt",
            "chmod 0400 /opt/blueprint/otel/client.key",
            update_env,
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="blueprint-dev")
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--observability-instance", required=True)
    parser.add_argument("--development-instance", required=True)
    parser.add_argument("--production-instance")
    parser.add_argument("--diagnose-only", action="store_true")
    parser.add_argument("--mtls-only", action="store_true")
    parser.add_argument("--final-checks", action="store_true")
    parser.add_argument("--enable-development-export", action="store_true")
    args = parser.parse_args()

    if args.diagnose_only:
        print(
            run_ssm(
                args.profile,
                args.region,
                args.observability_instance,
                [
                    "docker ps -a --filter name=pixel-perfect-observability --format '{{.Names}}|{{.Status}}'",
                    "docker port pixel-perfect-observability-otel-collector-1",
                    "ss -ltnp | grep -E ':(4318|13133)' || true",
                    "docker logs --tail 30 pixel-perfect-observability-otel-collector-1 2>&1",
                ],
            )
        )
        return

    if args.mtls_only:
        configure_development_mtls(
            args.profile,
            args.region,
            args.observability_instance,
            args.development_instance,
        )
        print("Development private mTLS OTLP request: success")
        return

    if args.final_checks:
        if not args.production_instance:
            parser.error("--production-instance is required with --final-checks")
        print(
            run_ssm(
                args.profile,
                args.region,
                args.observability_instance,
                [
                    "docker ps --filter name=pixel-perfect-observability --format '{{.Names}}|{{.Status}}'",
                    "docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}'",
                    "free -m",
                    "df -h /opt/observability-data",
                    "test $(docker ps --filter name=pixel-perfect-observability --format '{{.Names}}' | wc -l) -eq 5",
                ],
            )
        )
        for label, instance_id in (
            ("Development", args.development_instance),
            ("Production", args.production_instance),
        ):
            run_ssm(
                args.profile,
                args.region,
                instance_id,
                ["docker ps --filter name=app --filter health=healthy --format '{{.Names}}' | grep -q ."],
            )
            print(f"{label} application health: success")
        return

    if args.enable_development_export:
        enable_development_export(args.profile, args.region, args.development_instance)
        print("Development OTLP mTLS environment: configured")
        return

    print(configure_host(args.profile, args.region, args.observability_instance))
    configure_development_mtls(
        args.profile,
        args.region,
        args.observability_instance,
        args.development_instance,
    )
    print("Development private mTLS OTLP request: success")


if __name__ == "__main__":
    main()
