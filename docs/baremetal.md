# Bare-Metal systemd Deployment Guide

Deploy MariaDB directly on bare-metal or virtual machines with idempotent configuration and secure defaults.

## Highlights

- Packages installed via non-interactive APT (`DEBIAN_FRONTEND=noninteractive`).
- `/etc/mysql/mariadb.conf.d/99-custom.cnf` is managed to bind MariaDB to `mariadb_bind_address`.
- Handlers restart MariaDB whenever configuration or unit files change.
- Database provisioning uses `community.mysql` modules for password, database, and user management—no shell commands.
- `mariadb_allowed_hosts` must list specific client hosts; `%` is rejected.

## Prerequisites

```bash
sudo apt update
sudo apt install mariadb-server python3-pymysql
ansible-galaxy collection install community.mysql
```

## Workflow

1. Render the systemd unit (`templates/baremetal.yml.j2`) using the shared contract.
2. Apply with `roles/common/apply_runtime/tasks/baremetal.yml`, which:
   - Sets `service_ip` based on `mariadb_bind_address`.
   - Installs required packages.
   - Writes `99-custom.cnf` and triggers the shared handler on change.
   - Places the rendered unit at `/etc/systemd/system/<service_id>.service`.
   - Enables and starts the service.
   - Secures the root account and grants users access via `community.mysql`.

## Variables

- `mariadb_bind_address` – defaults to the host’s primary address; override to constrain network exposure.
- `mariadb_allowed_hosts` – list of client addresses. Provide a list (e.g. `['10.0.0.10']`).

## Validation

After rendering:

```bash
systemd-analyze verify /tmp/ansible-runtime/mariadb/baremetal.yml
```

Run the playbook and rely on the shared health command for a final check:

```bash
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=baremetal -e "health.cmd=['mysqladmin','ping','-h','127.0.0.1']"
```
