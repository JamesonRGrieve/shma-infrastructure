# Self-Hosted Infrastructure Framework

A runtime-agnostic infrastructure-as-code framework for deploying self-hosted applications across **Proxmox LXC**, **Docker Compose**, **Podman Quadlets**, **Kubernetes**, and **bare-metal systemd** from a single service contract.

## Key Features

- **Write Once, Deploy Anywhere** – render the same service definition into runtime-specific manifests and unit files.
- **Portable Secrets Handling** – ship environment and file-based secrets with runtime-appropriate permissions, optionally shredding rendered material after adapters finish.
- **Declarative Service Exports** – advertise connection details (for example URLs, ports, or credentials) through `exports.env` so downstream apps can consume them without service-specific wiring in this repository.
- **Unified Health Contract** – a single `health.cmd` drives Compose healthchecks, Quadlet probes, Kubernetes readiness/liveness probes, and a post-deploy gate.
- **Continuous Validation** – GitHub Actions lint Ansible/YAML, render every runtime, and verify the generated artifacts with the runtime CLIs.

## Quick Start

### Install toolchain

```bash
python3 -m pip install -r ci/requirements.txt
ansible-galaxy collection install -r ci/collections-stable.yml
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

Every service definition must provide identifiers, runtime templates, health checks, storage, and exports. A minimal example using the bundled `sample_service.yml` looks like:

```yaml
service_id: sample-service
service_image: registry.example.com/sample/service:1.27
service_image_digest: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
runtime_templates:
  docker: templates/docker.yml.j2
  podman: templates/podman.yml.j2
  proxmox: templates/proxmox.yml.j2
  kubernetes: templates/kubernetes.yml.j2
  baremetal: templates/baremetal.yml.j2

exports:
  env:
    - name: SAMPLE_SERVICE_URL
      value: https://sample-service.internal
      description: Base URL consumers should call.

secrets:
  shred_after_apply: true
  env:
    - name: SAMPLE_SERVICE_TOKEN
      value: "{{ sample_service_token }}"
  files:
    - name: tls-cert
      target: /etc/sample-service/certs/tls.crt
      value: "{{ sample_service_tls_cert }}"
```

Downstream applications consume these exports by resolving them through a dependency registry shared between repositories. Provide the registry as a list of known dependencies either inline (`dependency_registry`) or via `dependency_registry_file`:

```yaml
# dependency-registry.yml
dependencies:
  - sample-service
  - shared-cache
```

A dependent service can then declare its expectations and map resolved values (for example through a `dependency_exports` variable populated from the registry and exported environment files):

```yaml
requires:
  - sample-service

service_env:
  - name: UPSTREAM_URL
    value: "{{ dependency_exports['sample-service'].SAMPLE_SERVICE_URL }}"
```

The registry keeps validation decoupled from the Ansible inventory while ensuring every declared dependency is fulfilled by an exported contract.

## Additional Options

- `quadlet_scope` – set to `system` (default) or `user` to control where Quadlet units are installed. When using `quadlet_scope: user`, make sure lingering is enabled for the target user or user services are explicitly started at boot.
- `secrets.shred_after_apply` – defaults to `true` and removes rendered secret files and env files immediately after the runtime adapter applies changes, leaving only in-memory material behind.
- `hardening_enable_cockpit` – opt-in installation of Cockpit packages; when enabled, Cockpit binds to `hardening_cockpit_bind_address` (`127.0.0.1` by default) instead of exposing 9090 broadly.

## Continuous Integration

`.github/workflows/ci.yml` performs the following on every push and pull request:

1. Lint YAML (`yamllint`) and Ansible (`ansible-lint`).
2. Validate `schemas/service.schema.yml` with `jsonschema`.
3. Render sample manifests for each runtime via `tests/render.yml` and `tests/sample_service.yml`.
4. Validate the generated artifacts against tooling and a throwaway Kind cluster:
   - `yamllint` for Proxmox config.
   - `docker compose config` for Compose.
   - `systemd-analyze verify` for Quadlet and bare-metal service units.
   - `kubectl apply --dry-run=server --validate=true` for Kubernetes manifests.

Use the same steps locally before submitting changes to keep CI green.
