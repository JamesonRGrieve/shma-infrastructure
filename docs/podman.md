# Podman Quadlet Deployment Guide

Deploy services using Podman Quadlets with environment files, optional user scope, and secret-aware mounts.

## Enhancements

- `quadlet_scope` selects system-wide (`/etc/containers/systemd`) or per-user (`~/.config/containers/systemd`) installation.
- Secrets from the contract populate an environment file and optional `secrets/` directory, mounted read-only into the container.
- Health checks map directly to `HealthCmd/HealthInterval/HealthTimeout/HealthRetries` derived from `health.cmd`.
- Host policy defaults to rejecting unsigned/unknown registries and the local Docker engine, keeping pulls scoped to approved sources.
- `service_volumes.host_path` entries render as direct bind mounts so containers remain ephemeral while state lives on the host.
- `service_image` entries should be digest-pinned; combine with `quadlet_auto_update: none` to ensure only vetted images run.

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
Environment=APP_MODE=production
Environment=APP_FEATURE_FLAG=true
EnvironmentFile=/etc/containers/systemd/sample-service.env
Volume=/srv/sample-service/config:/etc/sample-service:Z
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
5. Shreds rendered secrets by default; set `secrets.shred_after_apply: false` only when you need to retain them for debugging.
6. Sets `service_ip` for the post-deploy health gate.

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
