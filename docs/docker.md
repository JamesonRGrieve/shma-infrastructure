# Docker Compose Deployment Guide

Deploy services using Docker Compose with secret-aware environment injection and Compose v2 tooling.

## What's new

- Secrets defined in the service contract travel via the Compose CLI environment. Values are staged on disk during deployment and shredded afterward when `secrets.shred_after_apply` remains `true`.
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
      SHMA_SECRETS_ROTATION: "2024-01-01T00:00:00Z"
      SAMPLE_SERVICE_TOKEN: ${SAMPLE_SERVICE_TOKEN}
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

- `secrets.env` entries become environment variables supplied directly to the Compose CLI; values stay in-memory during deployment.
- `secrets.files` entries create files in `secrets/<name>` and populate the Compose `secrets` map.
- `secrets.shred_after_apply` defaults to `true`, removing rendered secrets after deployment. When you must retain the artifacts,
  set `secrets.shred_after_apply: false` and record the rationale in `secrets.shred_waiver_reason`.
- `secrets.rotation_timestamp` (optional) forces Compose to recreate containers whenever you bump the value—use it to rotate credentials without editing unrelated settings.
- `service_ports` control host bindings; publish only the ports you intend to expose.
- `service_volumes.host_path` mounts host directories directly, which keeps containers ephemeral while the data persists on the host. Omit the key to fall back to managed named volumes.
- `mounts.persistent_volumes` names directories that require backups, while `mounts.ephemeral_mounts` defines tmpfs-backed paths for runtimes that support them.
- `service_security` customises the default non-root, read-only security posture when a workload needs explicit relaxations.
- `service_image` values should be pinned by digest; promote a new digest only after it passes your CI scanning gates.
- `service_resources.connections_per_second` propagates to a `CONNECTIONS_PER_SECOND` environment variable so nginx/envoy
  sidecars can enforce per-pod limits in front of the workload.

## Validating the render

After running `ansible-playbook tests/render.yml -e runtime=docker`, verify the manifest:

```bash
docker compose -f /tmp/ansible-runtime/sample-service/docker.yml config
```

## Deployment with Ansible

`roles/common/apply_runtime/tasks/docker.yml`:

1. Prepares the optional `secrets/` directory for file-based secrets.
2. Invokes `community.docker.docker_compose_v2` with `pull: always`, injecting secret environment variables through Ansible's `environment` parameter.
3. Shreds rendered secrets by default; set `secrets.shred_after_apply: false` only with a documented `secrets.shred_waiver_reason`
   that justifies the risk of keeping plaintext artifacts on disk.

### Secret transport differences

Docker injects `secrets.env` values directly into the Compose execution environment while the containers start. Kubernetes, by
contrast, materialises secrets as mounted files, and Podman Quadlet follows the Docker behaviour. When migrating from Docker or
Podman to Kubernetes, convert any secrets that workloads read from environment variables into file-based reads or populate the
same values in ConfigMaps/Secrets mounted under `secrets.files`. The reverse migration—Kubernetes to Docker/Podman—requires you
to shift file consumers to read from environment variables or render the desired files with `secrets.files` during deploy time.
4. Sets `service_ip` for the unified health gate.
5. Recreates containers automatically whenever `secrets.rotation_timestamp` changes.

Use the shared health command to run a post-deploy verification:

```bash
ansible-playbook playbooks/deploy-sample.yml -e runtime=docker -e "health.cmd=['/bin/sh','-c','exit 0']"
```
