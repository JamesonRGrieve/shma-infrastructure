# Docker Compose Deployment Guide

Deploy services using Docker Compose with secret-aware environment files and Compose v2 tooling.

## What's new

- Secrets defined in the service contract populate a dedicated `./<service>.env` file; sensitive values no longer appear inline.
- File-based secrets render into `secrets/` and are attached via Compose `secrets` blocks.
- `community.docker.docker_compose_v2` drives deployments to align with the modern Docker CLI plugin.
- Health probes come directly from `health.cmd` ensuring parity with other runtimes.
- Host bind mounts are first-class: specify `service_volumes.host_path` to keep container filesystems disposable while state persists on the host.
- Ephemeral tmpfs mounts defined under `mounts.ephemeral_mounts` render via Compose `tmpfs` entries so only declared paths remain writable.
- Containers default to running as UID/GID `65532`, drop all capabilities, run as read-only, enforce `no-new-privileges`, and attach the Docker `apparmor=docker-default` profile. Override with `service_security` when a workload needs explicit grants or to supply a different AppArmor profile.

## Prerequisites

```bash
sudo apt install docker.io docker-compose-plugin
ansible-galaxy collection install community.docker
```

Verify the plugin version:

```bash
docker compose version
```

## Template highlights

`templates/docker.yml.j2` renders a service similar to the bundled sample:

```yaml
services:
  sample-service:
    image: docker.io/library/nginx@sha256:2ed85f18cb2c6b49e191bcb6bf12c0c07d63f3937a05d9f5234170d4f8df5c94
    container_name: sample-service
    restart: unless-stopped
    user: 65532:65532
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
      - apparmor=docker-default
    env_file:
      - ./sample-service.env
    environment:
      APP_MODE: production
      APP_FEATURE_FLAG: "true"
    volumes:
      - /srv/sample-service/config:/etc/sample-service
    tmpfs:
      - "/run/sample-service:size=64Mi,mode=0755"
      - "/tmp/sample-service:size=64Mi"
    ports:
      - "192.0.2.50:8080:8080"
    networks:
      - app-network
    healthcheck:
      test: ["/bin/sh", "-c", "exit 0"]
      interval: 10s
      timeout: 5s
      retries: 3
    secrets:
      - source: tls-cert
        target: /etc/sample-service/certs/tls.crt
        mode: '0400'
secrets:
  tls-cert:
    file: ./secrets/tls-cert

networks:
  app-network:
    driver: bridge
```

## Contract inputs

- `secrets.env` entries feed the env file.
- `secrets.files` entries create files in `secrets/<name>` and populate the Compose `secrets` map.
- `secrets.shred_after_apply` defaults to `true`, removing rendered secrets after deployment unless you explicitly opt out.
- `service_ports` control host bindings; publish only the ports you intend to expose.
- `service_volumes.host_path` mounts host directories directly, which keeps containers ephemeral while the data persists on the host. Omit the key to fall back to managed named volumes.
- `mounts.persistent_volumes` names directories that require backups, while `mounts.ephemeral_mounts` defines tmpfs-backed paths for runtimes that support them.
- `service_security` customises the default non-root, read-only security posture when a workload needs explicit relaxations.
- `service_image` values should be pinned by digest; promote a new digest only after it passes your CI scanning gates.

## Validating the render

After running `ansible-playbook tests/render.yml -e runtime=docker`, verify the manifest:

```bash
docker compose -f /tmp/ansible-runtime/sample-service/docker.yml config
```

## Deployment with Ansible

`roles/common/apply_runtime/tasks/docker.yml`:

1. Builds the env file and optional `secrets/` directory under the render output.
2. Invokes `community.docker.docker_compose_v2` with `pull: always` to keep images fresh.
3. Shreds rendered secrets by default; set `secrets.shred_after_apply: false` for workloads that must retain them on disk.
4. Sets `service_ip` for the unified health gate.

Use the shared health command to run a post-deploy verification:

```bash
ansible-playbook playbooks/deploy-sample.yml -e runtime=docker -e "health.cmd=['/bin/sh','-c','exit 0']"
```
