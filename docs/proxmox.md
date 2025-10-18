# Proxmox LXC Deployment Guide

Deploy services as LXC containers on Proxmox VE with predictable networking and hardened MariaDB defaults.

## Key changes

- Templates now emit `container_ip`, removing brittle IP parsing in Ansible tasks.
- LXC containers declare `features: nesting=1,keyctl=1` so Docker/Podman workloads function inside the guest when required.
- Ansible waits for SSH on `container_ip` (120 seconds) before running delegate tasks.
- Package installation inside the container uses non-interactive APT and triggers handlers when configuration files change.
- MariaDB is configured with Ansible modules instead of shell, binding to the container IP and granting access only to `mariadb_allowed_hosts`.

## Prerequisites

### Proxmox VE

- Proxmox VE 7.0 or newer with API access.
- Ubuntu 24.04 container template (defaults to `local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst`).
- Network bridge with reachable gateway.

### Ansible collections

```bash
ansible-galaxy collection install community.general community.mysql
```

`community.mysql` provides the `mysql_user` and `mysql_db` modules used during provisioning.

## Template snippets

`templates/proxmox.yml.j2` now produces:

```yaml
---
container_ip: "192.0.2.50"
container:
  vmid: "200"
  hostname: "mariadb"
  ostemplate: "local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
  disk: "10"
  cores: "1"
  memory: "512"
  swap: "512"
  netif:
    net0: "name=eth0,bridge=vmbr0,ip=192.0.2.50/24,gw=192.0.2.1"
  onboot: yes
  unprivileged: yes
  features: "nesting=1,keyctl=1"

setup:
  packages:
    - mariadb-server
    - mariadb-client
    - python3-pymysql
  config:
    - path: /etc/mysql/mariadb.conf.d/99-custom.cnf
      content: |
        [mysqld]
        bind-address = 192.0.2.50
        max_connections = 200
  services:
    - name: mariadb
      enabled: true
      state: started
```

## Runtime variables

- `mariadb_bind_address` – override the bind address if the container uses multiple interfaces.
- `mariadb_allowed_hosts` – list of remote hosts granted database access. Defaults to `[container_ip]`; `%` is rejected by the role.

## Execution flow

1. Render the template (see `tests/render.yml`).
2. `roles/common/apply_runtime/tasks/proxmox.yml`:
   - Creates/starts the container with the declared features.
   - Waits for `container_ip:22`.
   - Installs packages via non-interactive APT.
   - Copies config files and notifies the shared handler to restart MariaDB when changed.
   - Enables systemd services defined in `setup.services`.
   - Uses `community.mysql` modules to secure the root account, create the database, and grant users access to the specified hosts.

## Security notes

- MariaDB binds to the LXC IP instead of `0.0.0.0`.
- Database users must be explicitly listed in `mariadb_allowed_hosts`.
- Use Proxmox firewall rules or host-level filtering if exposing the port beyond the bridge.

## Troubleshooting

- **Handler not firing** – ensure templates write to `/etc/mysql/mariadb.conf.d/99-custom.cnf`. The handler listens on `Restart MariaDB`.
- **Delegation errors** – confirm `container_ip` resolves and SSH is reachable. Increase the `wait_for` timeout if provisioning a large template.
