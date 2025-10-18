# Podman Quadlet Deployment Guide

Deploy services using Podman Quadlets with environment files, optional user scope, and secret-aware mounts.

## Enhancements

- `quadlet_scope` selects system-wide (`/etc/containers/systemd`) or per-user (`~/.config/containers/systemd`) installation.
- Secrets from the contract populate an environment file and optional `secrets/` directory, mounted read-only into the container.
- Health checks map directly to `HealthCmd/HealthInterval/HealthTimeout/HealthRetries` derived from `health.cmd`.

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
Image=docker.io/library/nginx:1.27
ContainerName=sample-service
AutoUpdate=registry
Environment=APP_MODE=production
Environment=APP_FEATURE_FLAG=true
EnvironmentFile=/etc/containers/systemd/sample-service.env
Volume=sample-service-config.volume:/etc/sample-service:Z
PublishPort=192.0.2.50:8080:8080
Volume=/etc/containers/systemd/secrets/tls-cert:/etc/sample-service/certs/tls.crt:ro,Z
HealthCmd=/bin/sh -c exit 0
HealthInterval=10s
HealthTimeout=5s
HealthRetries=3

[Service]
Restart=always
TimeoutStartSec=900

[Install]
WantedBy=multi-user.target default.target
```

For `quadlet_scope: user`, the environment file and secrets live under `~/.config/containers/systemd/`. Enable lingering or ensure user services start at boot so the unit remains active.

## Deployment workflow

`roles/common/apply_runtime/tasks/podman.yml`:

1. Computes the target directories based on `quadlet_scope`.
2. Writes the env file and optional secret files (with `0400` default permissions).
3. Copies the `.container` unit.
4. Executes `systemd` tasks with the correct scope and reloads daemons.
5. Optionally shreds rendered secrets when `secrets.shred_after_apply` is enabled.
6. Sets `service_ip` for the post-deploy health gate.

Ensure lingering is enabled when deploying user-scoped units:

```bash
loginctl enable-linger $USER
systemctl --user daemon-reload
systemctl --user enable sample-service
systemctl --user start sample-service
```
