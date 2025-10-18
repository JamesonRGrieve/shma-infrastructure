# Docker Compose Deployment Guide

Deploy services using Docker Compose with secret-aware environment files and Compose v2 tooling.

## What's new

- Secrets defined in the service contract populate a dedicated `./<hostname>.env` file; sensitive values no longer appear inline.
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

`templates/docker.yml.j2` now outputs:

```yaml
version: '3.8'

services:
  mariadb:
    image: mariadb:10.11
    container_name: mariadb-sample
    restart: unless-stopped
    env_file:
      - ./mariadb-sample.env
    environment:
      MYSQL_DATABASE: sampledb
      MYSQL_USER: sample
    volumes:
      - mariadb-data:/var/lib/mysql
    ports:
      - "192.0.2.50:3306:3306"
    networks:
      - app-network
    healthcheck:
      test: ["mysqladmin", "ping", "-h", "127.0.0.1", "-P", "3306"]
      interval: 10s
      timeout: 5s
      retries: 3
    secrets:
      - source: ca-cert
        target: /etc/mysql/certs/ca.pem
        mode: '0400'

volumes:
  mariadb-data:
    driver: local

secrets:
  ca-cert:
    file: ./secrets/ca-cert

networks:
  app-network:
    driver: bridge
```

## Contract inputs

- `secrets.env` entries feed the env file.
- `secrets.files` entries create files in `secrets/<name>` and populate the Compose `secrets` map.
- `mariadb_ip` controls host binding; avoid `0.0.0.0` unless firewalled.

## Validating the render

After running `ansible-playbook tests/render.yml -e runtime=docker`, verify the manifest:

```bash
docker compose -f /tmp/ansible-runtime/mariadb/docker.yml config
```

## Deployment with Ansible

`roles/common/apply_runtime/tasks/docker.yml`:

1. Builds the env file and optional `secrets/` directory under the render output.
2. Invokes `community.docker.docker_compose_v2` with `pull: always` to keep images fresh.
3. Sets `service_ip` for the unified health gate.

Use the shared health command to run a post-deploy verification:

```bash
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=docker -e "health.cmd=['mysqladmin','ping','-h','192.0.2.50']"
```
