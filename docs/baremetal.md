# Bare-Metal systemd Deployment Guide

Deploy services directly on bare-metal or virtual machines with idempotent configuration and generic systemd units.

## Highlights

- Packages installed via non-interactive APT (`DEBIAN_FRONTEND=noninteractive`).
- Configuration files defined in the service contract render exactly once and trigger handlers when changed.
- Generated units inherit defaults from `templates/baremetal.yml.j2`, keeping runtime-agnostic settings consistent.

## Prerequisites

```bash
sudo apt update
sudo apt install systemd
ansible-galaxy collection install community.general
```

## Workflow

1. Render the systemd unit (`templates/baremetal.yml.j2`) using the shared contract.
2. Apply with `roles/common/apply_runtime/tasks/baremetal.yml`, which:
   - Installs required packages via APT when declared.
   - Writes configuration files with their requested permissions.
   - Places the rendered unit at `/etc/systemd/system/<service_id>.service`.
   - Enables and starts the service, then runs the shared health command.

## Variables

- `service_unit` – override description, dependencies, or the `[Service]` stanza for advanced workloads.
- `service_packages` – list of packages to install before enabling the unit.
- `secrets.shred_after_apply` – defaults to `true` to keep rendered secrets ephemeral; set it to `false` only when you require persisted artifacts.

## Validation

After rendering:

```bash
systemd-analyze verify /tmp/ansible-runtime/sample-service/baremetal.yml
```

Run the playbook and rely on the shared health command for a final check:

```bash
ansible-playbook playbooks/deploy-sample.yml -e runtime=baremetal -e "health.cmd=['/bin/sh','-c','exit 0']"
```
