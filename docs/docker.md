# Docker Compose Deployment Guide

Deploy services using Docker Compose with secret-aware environment files and Compose v2 tooling.

## What's new

- Secrets defined in the service contract populate a dedicated `./<service>.env` file; sensitive values no longer appear inline.
- File-based secrets render into `secrets/` and are attached via Compose `secrets` blocks.
- `community.docker.docker_compose_v2` drives deployments to align with the modern Docker CLI plugin.
- Health probes come directly from `health.cmd` ensuring parity with other runtimes.

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
version: '3.8'

services:
  sample-service:
    image: docker.io/library/nginx:1.27
    container_name: sample-service
    restart: unless-stopped
    env_file:
      - ./sample-service.env
    environment:
      APP_MODE: production
      APP_FEATURE_FLAG: "true"
    volumes:
      - sample-service-config:/etc/sample-service
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

volumes:
  sample-service-config:
    driver: local

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
