# Podman Quadlet Deployment Guide

Deploy services using Podman Quadlets with environment files, optional user scope, and secret-aware mounts.

## Enhancements

- `quadlet_scope` selects system-wide (`/etc/containers/systemd`) or per-user (`~/.config/containers/systemd`) installation.
- Secrets from the contract populate a dedicated environment file (for `secrets.env`) and optional `secrets/` directory, mounted read-only into the container.
- Health checks map directly to `HealthCmd/HealthInterval/HealthTimeout/HealthRetries` derived from `health.cmd`.
- Host policy defaults to rejecting unsigned/unknown registries and the local Docker engine, keeping pulls scoped to approved sources.
- `service_volumes.host_path` entries render as direct bind mounts so containers remain ephemeral while state lives on the host.
- `service_image` entries should be digest-pinned; combine with `quadlet_auto_update: none` to ensure only vetted images run.
- `mounts.ephemeral_mounts` entries become `Tmpfs=` declarations hardened with `nosuid`, `nodev`, and `noexec` so containers only write to explicitly allowed paths.
- Containers default to `User=65532:65532`, `ReadOnly=true`, `NoNewPrivileges=true`, `DropCapability=ALL`, and omit `CapabilityBoundingSet` unless you provide an explicit allow-list through `service_security.capability_bounding_set`. Override with `service_security` only when workloads need extra permissions.
- Set `service_security.user_namespace` to wire Podman's `UserNS=` quadlet directive (for example `keep-id` or `auto`).
- `secrets.rotation_timestamp` (optional) is written as an inline environment variable so Quadlet restarts the container whenever you bump the value.

- `service_resources.connections_per_second` surfaces as a `CONNECTIONS_PER_SECOND` variable so an nginx/envoy sidecar can
  enforce per-pod rate limits in front of the workload.

## Requirements

```bash
sudo apt install podman
ansible-galaxy collection install community.general
```

Ensure Quadlet is supported:

```bash
podman info | grep -i quadlet
```

## Template output

`templates/podman.yml.j2` renders (system scope shown):

```ini
[Unit]
Description=Managed container for sample-service
After=network-online.target
Wants=network-online.target

[Container]
Image=docker.io/library/nginx@sha256:2ed85f18cb2c6b49e191bcb6bf12c0c07d63f3937a05d9f5234170d4f8df5c94
ContainerName=sample-service
AutoUpdate=none
User=65532:65532
ReadOnly=true
NoNewPrivileges=true
DropCapability=ALL
Environment=APP_MODE=production
Environment=APP_FEATURE_FLAG=true
Environment=SHMA_SECRETS_ROTATION=2024-01-01T00:00:00Z
EnvironmentFile=/etc/containers/systemd/sample-service.env
Volume=/srv/sample-service/config:/etc/sample-service:Z
Tmpfs=/run/sample-service:nosuid,nodev,noexec,size=64Mi,mode=0755
Tmpfs=/tmp/sample-service:nosuid,nodev,noexec,size=64Mi
PublishPort=192.0.2.50:8080:8080
Volume=/etc/containers/systemd/secrets/tls-cert:/etc/sample-service/certs/tls.crt:ro,Z
HealthCmd=/bin/sh -c exit 0
HealthInterval=10s
HealthTimeout=5s
HealthRetries=3

[Service]
Restart=always
TimeoutStartSec=900
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target default.target
```

For `quadlet_scope: user`, the `.container` unit and environment file live under `~/.config/containers/systemd/`, while secret files are staged in `~/.config/containers/systemd/secrets/`. Enable lingering or ensure user services start at boot so the unit remains active.

## Deployment workflow

`roles/common/apply_runtime/tasks/podman.yml`:

1. Computes the target directories based on `quadlet_scope`.
2. Writes the env file for `secrets.env` entries and optional secret files (with `0400` default permissions).
3. Copies the `.container` unit.
4. Executes `systemd` tasks with the correct scope and reloads daemons.
5. Shreds rendered secrets by default; set `secrets.shred_after_apply: false` only when you provide a `secrets.shred_waiver_reason`
   documenting the business case for retaining them.
6. Sets `service_ip` for the post-deploy health gate.
7. Bounces the unit automatically whenever `secrets.rotation_timestamp` changes.

Control automatic image refreshes with `quadlet_auto_update`. The default `none` avoids surprise upgrades; set it to `registry` only when you have a signing/rollout process that validates digests in CI first.

Ensure lingering is enabled when deploying user-scoped units:

```bash
loginctl enable-linger $USER
systemctl --user daemon-reload
systemctl --user enable sample-service
systemctl --user start sample-service
```

## Registry policy

`roles/podman_host/templates/policy.json.j2` now renders from `podman_host_policy_default` and `podman_host_policy_transports`.

- The default policy rejects every transport, including `docker-daemon`, unless you opt in.
- Allow trusted registries by adding entries such as:

  ```yaml
  podman_host_policy_transports:
    docker:
      "registry.example.com/team/":
        - type: sigstoreSigned
          keyPath: /etc/containers/policy.d/team.pub
  ```

  Use `signedBy` (GPG) or `sigstoreSigned` rules so Podman verifies content instead of blindly trusting TLS alone.
- Keep `docker-daemon` denied unless you must ingest images from the local engine; if so, override the transport mapping explicitly for that host.
### Secret transport differences

Quadlet mirrors Docker's behaviour: `secrets.env` are exported as environment variables during the `systemd` start, while
`secrets.files` create transient files. Kubernetes mounts everything as files. When moving a workload from Podman to Kubernetes,
convert environment consumers to read from mounted files or replicate the values under `secrets.files`. Moving from Kubernetes
back to Podman requires turning file-based reads into environment variables or continuing to use `secrets.files` so Quadlet
renders the expected payloads.
