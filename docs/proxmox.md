# Proxmox LXC Deployment Guide

Deploy services as LXC containers on Proxmox VE with predictable networking and runtime-agnostic provisioning.

## Key changes

- Templates emit `container_ip`, removing brittle IP parsing in Ansible tasks.
- LXC features derive exclusively from the service contract. Nested container flags such as `nesting=1,keyctl=1` appear only when you explicitly set `service_container.features`.
- Ansible waits for SSH on `container_ip` (120 seconds) before running delegate tasks.
- Package installation inside the container uses non-interactive APT and applies any rendered configuration or command hooks.

## Prerequisites

### Proxmox VE

- Proxmox VE 7.0 or newer with API access.
- Ubuntu 24.04 container template (defaults to `local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst`).
- Network bridge with reachable gateway.
- API token (`api_token_id`/`api_token_secret`) scoped to LXC operations on the target node or pool.

### API tokens

Configure `proxmox_api_host`, `proxmox_api_token_id`, `proxmox_api_token_secret`, and `proxmox_node` in your inventory or playbook vars. Grant the token only the permissions necessary to manage LXC guests on the desired node or resource pool.

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
  # features emitted only when explicitly configured on the service contract
  features: "nesting=1,keyctl=1"

setup:
  packages:
    - nginx
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
   - Creates or updates the container with the declared features.
   - Waits for SSH on `container_ip:22`.
   - Installs packages via non-interactive APT when requested.
   - Copies configuration files and enables systemd services declared in `setup.services`.
   - Runs any additional shell commands listed in `setup.commands` inside the guest.

## Security notes

- Explicit IP assignments keep host firewalls predictable.
- Use Proxmox firewall rules or host-level filtering for exposed ports.
- Keep `features` minimal; remove `nesting` when containerized workloads are not required.
- Prefer API tokens with only the `vms:read`/`vms:write` and `nodes:read` permissions the playbook needs. Bind them to the specific node or pool that hosts the managed LXCs instead of granting full-cluster rights.

## Troubleshooting

- **Delegation errors** – confirm `container_ip` resolves and SSH is reachable. Increase the `wait_for` timeout for large templates.
- **Package installation failures** – ensure the container has outbound network access and `DEBIAN_FRONTEND=noninteractive` is accepted.
