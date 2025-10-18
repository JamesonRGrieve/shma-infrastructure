# Self-Hosted Infrastructure Framework

A runtime-agnostic infrastructure-as-code framework for deploying self-hosted applications across **Proxmox LXC**, **Docker Compose**, **Podman Quadlets**, **Kubernetes**, and **bare-metal systemd** from a single service definition.

## Key Features

- **Write Once, Deploy Anywhere** – shared service contract rendered into runtime-specific manifests.
- **Runtime-Aware Secrets Delivery** – environment secrets use Compose env files, Quadlet environment files, Kubernetes Secrets, and Ansible modules for MariaDB provisioning.
- **Safety-First Defaults** – LXC containers declare `container_ip`, bind MariaDB to that address, and restrict database users to explicit hosts.
- **Unified Health Contract** – one `health.cmd` entry drives Compose healthchecks, Quadlet probes, Kubernetes readiness/liveness probes, and a post-deploy gate.
- **Continuous Validation** – GitHub Actions lint Ansible/YAML, render every runtime, and verify the generated artifacts.

## Quick Start

### Install toolchain

```bash
pip install ansible ansible-lint yamllint jsonschema pyyaml
ansible-galaxy collection install community.general community.docker community.mysql kubernetes.core
```

### Render a runtime locally

```bash
ansible-playbook tests/render.yml -e runtime=docker -e @tests/sample_service.yml
```

The rendered manifest is written to `/tmp/ansible-runtime/<service_id>/<runtime>.yml` and can be validated with the same commands used in CI (for example `docker compose -f … config`).

## Runtime Guides

- [Proxmox LXC](proxmox.md)
- [Docker Compose](docker.md)
- [Podman Quadlet](podman.md)
- [Kubernetes](kubernetes.md)
- [Bare-Metal systemd](baremetal.md)

## Service Contract Essentials

Service defaults should include a `secrets` block so the renderer can deliver runtime-specific secret material. Example:

```yaml
service_id: mariadb
runtime_templates:
  docker: templates/docker.yml.j2
  podman: templates/podman.yml.j2
  proxmox: templates/proxmox.yml.j2
  kubernetes: templates/kubernetes.yml.j2
  baremetal: templates/baremetal.yml.j2

secrets:
  env:
    - name: MYSQL_ROOT_PASSWORD
      value: "{{ mariadb_root_password }}"
    - name: MYSQL_PASSWORD
      value: "{{ mariadb_user_password }}"
  files:
    - name: ca-cert
      target: /etc/mysql/certs/ca.pem
      value: "{{ mariadb_ca_certificate }}"
```

Additional variables consumed by the adapters include:

- `mariadb_allowed_hosts` – list of hostnames or IPs granted access (defaults to the service bind address).
- `mariadb_bind_address` – explicit bind address for MariaDB; defaults to the rendered `container_ip` for LXC.
- `quadlet_scope` – `system` (default) or `user` to control where Quadlet units are installed.

## Continuous Integration

`.github/workflows/ci.yml` performs the following on every push and pull request:

1. Lint YAML (`yamllint`) and Ansible (`ansible-lint`).
2. Validate `schemas/service.schema.yml` with `jsonschema`.
3. Render sample manifests for each runtime via `tests/render.yml` and `tests/sample_service.yml`.
4. Validate the generated artifacts:
   - `yamllint` for Proxmox config.
   - `docker compose config` for Compose.
   - `systemd-analyze verify` for Quadlet and bare-metal service units.
   - `kubectl apply --dry-run=client --validate=true` for Kubernetes manifests.

Use the same steps locally before submitting changes to keep CI green.
