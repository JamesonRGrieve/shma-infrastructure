# Proxmox LXC Deployment Guide

Deploy services as LXC containers on Proxmox VE for efficient, isolated, and lightweight virtualization.

## Prerequisites

### Proxmox VE Setup
- Proxmox VE 7.0 or higher
- API access configured
- Container templates downloaded
- Network bridge configured
- Storage pool available

### Ansible Requirements
```bash
pip3 install proxmoxer requests
ansible-galaxy collection install community.general
```

## Configuration

### Environment Variables

Create `.env` file:

```bash
# Proxmox Connection
PROXMOX_API_HOST=proxmox.example.com
PROXMOX_API_USER=root@pam
PROXMOX_API_PASSWORD=your_secure_password
PROXMOX_NODE=pve

# Network Configuration
GATEWAY=192.168.0.1
PROXMOX_TEMPLATE=local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst

# Service-Specific (example: MariaDB)
MARIADB_ROOT_PASSWORD=secure_root_password
MARIADB_USER_PASSWORD=secure_user_password
MARIADB_CONTAINER_ID=200
MARIADB_IP=192.168.0.200
MARIADB_HOSTNAME=mariadb
MARIADB_MEMORY=2048
MARIADB_CORES=2
MARIADB_STORAGE_GB=50
```

### Proxmox API Token (Recommended)

Instead of password, use API tokens:

```bash
# Create token in Proxmox UI: Datacenter > Permissions > API Tokens
PROXMOX_API_TOKEN_ID=root@pam!ansible
PROXMOX_API_TOKEN_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Update playbook to use tokens:

```yaml
api_token_id: "{{ lookup('env', 'PROXMOX_API_TOKEN_ID') }}"
api_token_secret: "{{ lookup('env', 'PROXMOX_API_TOKEN_SECRET') }}"
```

## Deployment

### Basic Deployment

```bash
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=lxc
```

### Custom Container ID Range

```bash
# Deploy multiple instances
ansible-playbook playbooks/deploy-mariadb.yml \
  -e runtime=lxc \
  -e mariadb_container_id=201 \
  -e mariadb_ip=192.168.0.201 \
  -e mariadb_hostname=mariadb-dev
```

### Privileged Containers

```yaml
# In service defaults/main.yml
mariadb_unprivileged: no  # Use privileged container
```

⚠️ **Security Warning**: Only use privileged containers when absolutely necessary.

## LXC Template Structure

Services define LXC configuration in `templates/lxc.yml.j2`:

```yaml
container:
  vmid: "{{ service_container_id }}"
  hostname: "{{ service_hostname }}"
  ostemplate: "{{ proxmox_template }}"
  disk: "{{ service_storage_gb }}"
  cores: "{{ service_cores }}"
  memory: "{{ service_memory }}"
  swap: "{{ service_memory }}"
  netif:
    net0: "name=eth0,bridge=vmbr0,ip={{ service_ip }}/24,gw={{ gateway }}"
  onboot: yes
  unprivileged: yes

setup:
  packages:
    - package1
    - package2
  
  config:
    - path: /etc/app/config.conf
      content: |
        key=value
  
  commands:
    - systemctl enable service
    - systemctl start service
```

## Advanced Configuration

### Multiple Network Interfaces

```yaml
netif:
  net0: "name=eth0,bridge=vmbr0,ip=192.168.0.200/24,gw=192.168.0.1"
  net1: "name=eth1,bridge=vmbr1,ip=10.0.0.200/24"
```

### Custom Storage Backend

```bash
# Use different storage
ansible-playbook playbooks/deploy.yml \
  -e runtime=lxc \
  -e lxc_storage=local-zfs
```

### Bind Mounts

```yaml
# In service template
mounts:
  mp0: "/mnt/data,mp=/data,shared=1"
```

### Resource Limits

```yaml
# CPU limits
cpulimit: 2          # Limit to 2 cores worth of CPU time
cpuunits: 1024       # Relative CPU weight

# Memory limits
memory: 2048         # 2GB RAM
swap: 2048           # 2GB swap

# Disk I/O limits
diskio_read_mbps: 100
diskio_write_mbps: 100
```

## Networking

### Static IP Assignment

```yaml
netif:
  net0: "name=eth0,bridge=vmbr0,ip=192.168.0.200/24,gw=192.168.0.1"
```

### DHCP

```yaml
netif:
  net0: "name=eth0,bridge=vmbr0,ip=dhcp"
```

### Multiple VLANs

```yaml
netif:
  net0: "name=eth0,bridge=vmbr0,ip=192.168.0.200/24,gw=192.168.0.1,tag=10"
  net1: "name=eth1,bridge=vmbr0,ip=192.168.1.200/24,tag=20"
```

## Storage Management

### Automatic Disk Resize

```bash
# Increase container disk
pct resize <vmid> rootfs +10G
```

### Backup Volumes

```yaml
# In service template
setup:
  commands:
    - mkdir -p /backup
    - mount --bind /mnt/backup-storage /backup
```

### ZFS Datasets

```bash
# Create dedicated dataset
zfs create rpool/containers/mariadb-data

# Use in template
mounts:
  mp0: "rpool/containers/mariadb-data,mp=/var/lib/mysql"
```

## Troubleshooting

### Container Creation Fails

**Issue**: Template not found
```bash
# List available templates
pveam list local

# Download Ubuntu template
pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst
```

**Issue**: Insufficient permissions
```bash
# Check user permissions in Proxmox UI
# Required: VM.Allocate, VM.Config.Disk, VM.Config.Network
```

### Container Won't Start

**Check logs**:
```bash
pct start <vmid>
journalctl -xe | grep pve-container
```

**Common causes**:
- Port conflicts
- IP address conflicts
- Insufficient resources
- Corrupted container filesystem

### Network Issues

**Container can't reach internet**:
```bash
# Inside container
ping 8.8.8.8           # Test connectivity
cat /etc/resolv.conf   # Check DNS
ip route               # Check routes
```

**Fix DNS**:
```bash
# In container
echo "nameserver 8.8.8.8" > /etc/resolv.conf
```

### SSH Access Issues

**Enable SSH in container**:
```bash
pct enter <vmid>
apt install openssh-server
systemctl enable --now ssh

# Set root password
passwd
```

**SSH from Ansible fails**:
- Verify container IP is reachable
- Check firewall rules
- Ensure SSH key is authorized
- Increase `wait_for` timeout in playbook

## Performance Tuning

### CPU Pinning

```yaml
# Pin to specific CPU cores
cpuunits: 2048
cores: 4
```

### Memory Ballooning

```yaml
# Disable memory ballooning for consistent performance
balloon: 0
```

### I/O Priority

```yaml
# Higher I/O priority (lower number = higher priority)
ioprio: 4
```

## Security Best Practices

### Unprivileged Containers

Always use unprivileged containers unless privileged access is required:

```yaml
unprivileged: yes
```

### AppArmor Profiles

```bash
# Apply AppArmor profile
pct set <vmid> -features nesting=1,keyctl=0
```

### Limited Capabilities

```bash
# Restrict container capabilities
pct set <vmid> -features keyctl=0,mknod=0
```

### Network Isolation

Use separate VLANs for different security zones:
- Public services: VLAN 10
- Internal services: VLAN 20
- Management: VLAN 30

## Backup and Restore

### Manual Backup

```bash
# Backup container
vzdump <vmid> --storage local --mode snapshot

# Restore from backup
pct restore <vmid> /var/lib/vz/dump/vzdump-lxc-<vmid>-*.tar.gz
```

### Automated Backups

```yaml
# In Proxmox UI or via API
# Datacenter > Backup > Add
schedule: "daily at 2:00 AM"
mode: snapshot
storage: backup-storage
retention: 7
```

## Migration

### Live Migration

```bash
# Migrate to another node
pct migrate <vmid> <target-node>
```

### Offline Migration

```bash
# Stop container
pct stop <vmid>

# Migrate
pct migrate <vmid> <target-node>

# Start on new node
pct start <vmid>
```

## Monitoring

### Resource Usage

```bash
# Check container stats
pct status <vmid>
pct config <vmid>

# Live resource monitoring
pct exec <vmid> -- top
```

### Integration with Prometheus

```yaml
# Add Prometheus node exporter to containers
setup:
  packages:
    - prometheus-node-exporter
  commands:
    - systemctl enable prometheus-node-exporter
```

## Examples

### WordPress on LXC

```bash
ansible-playbook playbooks/deploy-wordpress.yml \
  -e runtime=lxc \
  -e wordpress_container_id=210 \
  -e wordpress_ip=192.168.0.210 \
  -e wordpress_memory=4096 \
  -e wordpress_cores=4
```

### Database Cluster

```bash
# Deploy MariaDB primary
ansible-playbook playbooks/deploy-mariadb.yml \
  -e runtime=lxc \
  -e mariadb_container_id=200 \
  -e mariadb_role=primary

# Deploy MariaDB replicas
ansible-playbook playbooks/deploy-mariadb.yml \
  -e runtime=lxc \
  -e mariadb_container_id=201 \
  -e mariadb_role=replica \
  -e mariadb_primary_host=192.168.0.200
```

## FAQ

**Q: Can I run Docker inside LXC?**
A: Yes, enable nesting: `pct set <vmid> -features nesting=1`

**Q: How do I access container console?**
A: `pct enter <vmid>` or via Proxmox web UI

**Q: Can I convert VM to LXC?**
A: Not directly - must redeploy application in new LXC container

**Q: What's the maximum number of containers?**
A: Depends on host resources - hundreds possible on adequate hardware

**Q: How do I upgrade container OS?**
A: Use standard package manager inside container (`apt upgrade`)

## Next Steps

- [Docker Compose Deployment](deployment-compose.md)
- [Creating Custom Services](creating-services.md)
- [Service Contract Reference](service-contracts.md)