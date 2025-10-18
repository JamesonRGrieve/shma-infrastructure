# Proxmox LXC Deployment Guide

Deploy services as LXC containers on Proxmox VE with predictable networking and runtime-agnostic provisioning.

## Key changes

- Templates emit `container_ip`, removing brittle IP parsing in Ansible tasks.
- Ansible waits for SSH on `container_ip` (120 seconds) before running delegate tasks.
- Package installation inside the container uses non-interactive APT with per-package pinning and applies any rendered configuration or command hooks.
- API access now uses scoped Proxmox API tokens (`proxmox_api_token_id`/`proxmox_api_token_secret`) instead of passwords.

## Prerequisites

### Proxmox VE

- Proxmox VE 7.0 or newer with API access.
- Scoped API token (`user@realm!tokenid`) with only the permissions required for LXC lifecycle operations.
- Ubuntu 24.04 container template (defaults to `local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst`).
- Network bridge with reachable gateway.

### Ansible collections

```bash
ansible-galaxy collection install community.general
```

`community.general.proxmox` manages LXC lifecycle actions.

## Template snippets

`templates/proxmox.yml.j2` produces output similar to:

```yaml
---
container_ip: "192.0.2.50"
container:
  vmid: "200"
  hostname: "sample-service"
  ostemplate: "local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
  disk: "5"
  cores: "1"
  memory: "512"
  swap: "512"
  netif:
    net0: "name=eth0,bridge=vmbr0,ip=192.0.2.50/24,gw=192.0.2.1"
  onboot: yes
  unprivileged: yes
setup:
  packages:
    - name: nginx
      version: 1.24.0-2ubuntu1
  config:
    - path: /etc/sample-service/runtime.env
      content: |
        APP_MODE=production
        APP_FEATURE_FLAG=true
      mode: '0640'
  services:
    - name: sample-service
      enabled: true
      state: started
```

## Execution flow

1. Render the template (see `tests/render.yml`).
2. `roles/common/apply_runtime/tasks/proxmox.yml`:
   - Creates or updates the container with any explicitly declared features.
   - Waits for SSH on `container_ip:22`.
   - Installs packages via non-interactive APT when requested.
   - Copies configuration files and enables systemd services declared in `setup.services`.
   - Runs any additional shell commands listed in `setup.commands` inside the guest.

## Security notes

- Explicit IP assignments keep host firewalls predictable.
- Use Proxmox firewall rules or host-level filtering for exposed ports.
- Keep `features` minimal; the template no longer enables `nesting`/`keyctl` unless you request them.

## Troubleshooting

- **Delegation errors** – confirm `container_ip` resolves and SSH is reachable. Increase the `wait_for` timeout for large templates.
- **Package installation failures** – ensure the container has outbound network access, `DEBIAN_FRONTEND=noninteractive` is accepted, and declared versions exist in your repositories.
