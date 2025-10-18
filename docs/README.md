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
python -m pip install --requirement requirements.txt
ansible-galaxy collection install -r ci/collections-stable.yml
pre-commit install
```

### Render a runtime locally

```bash
ansible-playbook tests/render.yml -e runtime=docker -e @tests/sample_service.yml
```

The rendered manifest is written to `/tmp/ansible-runtime/<service_id>/<runtime>.yml` and can be validated with the same commands used in CI (for example `docker compose -f … config`).

## Compatibility Matrix

| Component | Tested versions | Notes |
| --- | --- | --- |
| Python | 3.11.x | Provisioned via `actions/setup-python` and verified during CI. |
| Ansible | Ansible 9.5.1 (core 2.16.x) | Locked in `requirements.txt` and exercised across every adapter lane. |
| Kubernetes CLI | kubectl v1.29.3 (stable lane), v1.31.1 (latest lane) | Both versions render and validate manifests in the matrix build. |
| kind | v0.22.0 | Used for server-side Kubernetes validation. |

## Runtime Guides

- [Proxmox LXC](proxmox.md)
- [Docker Compose](docker.md)
- [Podman Quadlet](podman.md)
- [Kubernetes](kubernetes.md)
- [Bare-Metal systemd](baremetal.md)
- [Network Edge Automation](edge.md)

## Operations Guides

- [Backup strategy](backup.md)
- [Troubleshooting](troubleshooting.md)

## Service Contract Essentials

Every service definition must provide identifiers, runtime templates, health checks, mounts, and exports. A minimal example using the bundled `sample_service.yml` looks like:

```yaml
service_id: sample-service
runtime_templates:
  docker: templates/docker.yml.j2
  podman: templates/podman.yml.j2
  proxmox: templates/proxmox.yml.j2
  kubernetes: templates/kubernetes.yml.j2
  baremetal: templates/baremetal.yml.j2

service_volumes:
  - name: config
    host_path: /srv/sample-service/config
    host_path_type: DirectoryOrCreate
    target: /etc/sample-service

mounts:
  persistent_volumes:
    - name: config
      path: /etc/sample-service
  ephemeral_mounts:
    - name: runtime-run
      path: /run/sample-service
      apply_to: [docker, podman, kubernetes, proxmox, baremetal]
      medium: Memory

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

> **Note:** Always declare host mounts with `service_volumes` (plural). The legacy `service_volume` key is deprecated and retained only for backward compatibility with older inventories.

Downstream applications consume these exports by resolving them through a dependency registry shared between repositories. Provide the registry as a list of known dependencies either inline (`dependency_registry`) or via `dependency_registry_file`:


```yaml
# dependency-registry.yml
dependencies:
  sample-service:
    version: "1.27.0"
    exports:
      env:
        - name: SAMPLE_SERVICE_URL
          value: https://sample-service.internal
    requires:
      - name: shared-cache
        version: "2024.05"
  shared-cache:
    exports:
      env:
        - name: SHARED_CACHE_URL
          value: redis://shared-cache.internal:6379
```

A dependent service can then declare its expectations and map resolved values (for example through a `dependency_exports` variable populated from the registry and exported environment files):

```yaml
requires:
  - name: sample-service
    version: "1.27.0"

service_env:
  - name: UPSTREAM_URL
    value: "{{ dependency_exports['sample-service'].SAMPLE_SERVICE_URL }}"

The `requires` entries can also include an `exports_hash` if downstream services need
to assert exact contract signatures instead of semantic versions.
```

The registry keeps validation decoupled from the Ansible inventory while ensuring every declared dependency is fulfilled by an exported contract.

## Additional Options

- `quadlet_scope` – set to `system` (default) or `user` to control where Quadlet units are installed. When using `quadlet_scope: user`, make sure lingering is enabled for the target user or user services are explicitly started at boot.
- `quadlet_auto_update` – defaults to `none` so Quadlet units do not pull image updates behind your back. Promote new digests intentionally or override per-service when a signed registry orchestrates rollouts.
- `service_volumes.host_path` – bind-mounts host directories into containers across Compose, Quadlet, and Kubernetes. Pair with `host_path_type` (default `DirectoryOrCreate`) to choose the Kubernetes `hostPath` strategy.
- `mounts.persistent_volumes` – declare directories that persist across restarts and inform backup tooling.
- `mounts.ephemeral_mounts` – enumerate tmpfs-backed paths for each runtime so only the declared directories remain writable.
- `secrets.shred_after_apply` – defaults to `true` so rendered secret files and env files are shredded once adapters finish.
  Override with `false` only when persistent copies are required and record your justification in `secrets.shred_waiver_reason`.
- `secrets.rotation_timestamp` – optional marker that, when changed, forces every runtime to recreate containers/pods and refresh secret material without a full service refactor.
- `service_security` – tune the default non-root, read-only container posture when a workload needs additional capabilities.
- `hardening_enable_cockpit` – opt-in toggle that installs Cockpit, binds it to `hardening_cockpit_listen_address` (defaults to `127.0.0.1`), and optionally opens UFW 9090 to the addresses listed in `hardening_cockpit_allowed_sources`.
- `hardening_cockpit_passwordless_sudo` – defaults to `false`. Enable only if Cockpit must issue privileged commands without prompting.
- `hardening_enable_ipv6` – defaults to `true`, keeping dual-stack networks intact. Disable only when upstream networking prohibits IPv6 entirely.
- `system_hardening_allowed_ports` – list of `port/protocol` entries (for example `443/tcp`) that should stay reachable after the
  firewall defaults to a deny-first policy.
- `edge_ingress_contracts` – list of ingress exports the edge roles consume. Pair with one or more `edge_proxy_*`, `edge_opnsense*`, or `edge_pfsense*` roles to automate reverse proxies (Traefik, HAProxy, Nginx, Caddy) and firewall integrations (HAProxy and Squid).

## Continuous Integration

`.github/workflows/ci.yml` performs the following on every push and pull request:

1. Lints and policy checks via `pre-commit`, `yamllint`, `ansible-lint`, `conftest`, `gitleaks`, and `actionlint`.
2. Validates the service schema and the curated sample definitions.
3. Renders each runtime for every sample service and verifies the generated artifacts with the runtime CLIs, including Compose, Quadlet, Kubernetes (client and server dry-runs), and Proxmox schema validation.
4. Runs security gates such as Trivy vulnerability scanning and cosign availability checks.

Enable branch protection on `main` (require pull requests, forbid bypass, and enforce the CI workflow) to keep the pipeline authoritative.

Use the same steps locally before submitting changes to keep CI green.
