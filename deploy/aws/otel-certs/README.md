# Runtime OpenTelemetry certificates

This tracked directory is an empty mount target for environments where OTLP is
disabled. Development overrides `OTEL_CERTIFICATE_HOST_DIR` with a protected
host directory populated through SSM. Never add certificates or private keys
here or to a container image.
