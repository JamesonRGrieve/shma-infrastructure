# Podman Quadlet Deployment Guide

Deploy services using Podman Quadlets for systemd-native containerized applications with automatic restarts and dependencies.

## Prerequisites

```bash
# Install Podman (4.4+)
apt install podman

# Verify quadlet support
podman --version  # Should be 4.4.0 or higher
```

## What are Quadlets?

Quadlets are systemd unit files that automatically generate Podman containers/pods/volumes. They provide:
- **Systemd integration**: Native service management
- **Automatic startup**: Containers start with system boot
- **Dependency management**: Start containers in correct order
- **Rootless containers**: Run without root privileges

## Configuration

### Environment Variables

```bash
# .env file
RUNTIME=quadlet

MARIADB_ROOT_PASSWORD=secure_password
MARIADB_USER=app
MARIADB_USER_PASSWORD=user_password
MARIADB_DATABASE=appdb
MARIADB_VERSION=10.11
```

## Deployment

### Basic Deployment

```bash
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=quadlet
```

Ansible will:
1. Generate `.container` file
2. Copy to `/etc/containers/systemd/` (system) or `~/.config/containers/systemd/` (user)
3. Reload systemd daemon
4. Enable and start service

## Quadlet Template Structure

```ini
# mariadb.container
[Unit]
Description=MariaDB Database
After=network-online.target
Wants=network-online.target

[Container]
Image=docker.io/library/mariadb:{{ version }}
ContainerName={{ hostname }}
AutoUpdate=registry

Environment=MYSQL_ROOT_PASSWORD={{ root_password }}
Environment=MYSQL_DATABASE={{ database }}
Environment=MYSQL_USER={{ user }}
Environment=MYSQL_PASSWORD={{ user_password }}

Volume=mariadb-data.volume:/var/lib/mysql:Z
PublishPort={{ ip }}:3306:3306

HealthCmd=mysqladmin ping -h localhost
HealthInterval={{ health.interval }}
HealthTimeout={{ health.timeout }}
HealthRetries={{ health.retries }}

[Service]
Restart=always
TimeoutStartSec=900

[Install]
WantedBy=multi-user.target default.target
```

## Quadlet Unit Types

### Container Units (`.container`)

```ini
[Container]
Image=registry.example.com/app:latest
ContainerName=myapp
Volume=app-data:/data
PublishPort=8080:8080
```

### Volume Units (`.volume`)

```ini
# mariadb-data.volume
[Volume]
Driver=local

[Install]
WantedBy=multi-user.target
```

### Network Units (`.network`)

```ini
# app-network.network
[Network]
Driver=bridge
Subnet=10.89.0.0/24

[Install]
WantedBy=multi-user.target
```

### Kube Units (`.kube`)

```ini
# Deploy Kubernetes YAML with Podman
[Kube]
Yaml=/path/to/deployment.yaml

[Install]
WantedBy=multi-user.target
```

## Service Management

### Systemd Commands

```bash
# Status
systemctl status mariadb

# Start/Stop
systemctl start mariadb
systemctl stop mariadb

# Enable/Disable autostart
systemctl enable mariadb
systemctl disable mariadb

# View logs
journalctl -u mariadb -f

# Restart
systemctl restart mariadb
```

### Container Management

```bash
# List containers (even those managed by systemd)
podman ps -a

# Execute commands
podman exec -it mariadb bash
podman exec mariadb mysqladmin ping

# View logs
podman logs -f mariadb
```

## Advanced Configuration

### Rootless Containers (User Mode)

```bash
# Deploy to user systemd
mkdir -p ~/.config/containers/systemd/

# Copy quadlet file
cp mariadb.container ~/.config/containers/systemd/

# Reload user systemd
systemctl --user daemon-reload

# Enable linger (start services without login)
loginctl enable-linger $USER

# Manage with user systemd
systemctl --user start mariadb
systemctl --user enable mariadb
```

### Multi-Container Dependencies

```ini
# app.container
[Unit]
Description=Application
Requires=mariadb.service
After=mariadb.service

[Container]
Image=myapp:latest
Environment=DB_HOST=mariadb
```

### Secret Management

```ini
[Container]
Secret=db-password,type=env,target=MYSQL_ROOT_PASSWORD

# Create secret
podman secret create db-password /path/to/secret/file
```

### Resource Limits

```ini
[Service]
# CPU limit (in CPU cores)
CPUQuota=200%

# Memory limit
MemoryMax=2G
MemoryHigh=1.5G
```

### Custom Networks

```bash
# Create network quadlet
cat > app-network.network <<EOF
[Network]
Driver=bridge
Subnet=172.20.0.0/16

[Install]
WantedBy=multi-user.target
EOF

# Use in container
[Container]
Network=app-network.network
```

## Troubleshooting

### Quadlet Not Generating Service

```bash
# Check systemd generator
/usr/lib/systemd/system-generators/podman-system-generator --dryrun

# Verify quadlet syntax
podman quadlet --dryrun
```

### Container Fails to Start

```bash
# Check systemd status
systemctl status mariadb

# View detailed logs
journalctl -xe -u mariadb

# Check Podman directly
podman logs mariadb
```

### Permission Denied (Rootless)

```bash
# Check subuid/subgid ranges
cat /etc/subuid
cat /etc/subgid

# Should show entries like:
# username:100000:65536

# If missing, add:
sudo usermod --add-subuids 100000-165535 username
sudo usermod --add-subgids 100000-165535 username
```

### Volume Mount Issues

```bash
# For rootless, use :Z or :z for SELinux context
Volume=./data:/data:Z

# Or disable SELinux for container
[Container]
SecurityLabelDisable=true
```

## Backup and Restore

### Volume Backup

```bash
# Stop service
systemctl stop mariadb

# Backup volume
sudo podman volume export mariadb-data > mariadb-backup.tar

# Restore volume
sudo podman volume import mariadb-data < mariadb-backup.tar

# Start service
systemctl start mariadb
```

### Container Image Backup

```bash
# Save image
podman save -o mariadb-image.tar mariadb:10.11

# Load image
podman load -i mariadb-image.tar
```

## Migration

### From Docker Compose

```bash
# Use podman-compose (compatible with docker-compose.yml)
pip3 install podman-compose
podman-compose up -d

# Or convert to Quadlets manually
```

### From Docker

```bash
# Pull image from Docker Hub
podman pull docker.io/library/mariadb:10.11

# Import existing Docker volumes
docker volume export myvolume | podman volume import myvolume
```

## Auto-Updates

```ini
[Container]
AutoUpdate=registry  # Check for updates and pull automatically

# Enable auto-update timer
systemctl enable --now podman-auto-update.timer

# Manual update check
podman auto-update
```

## Monitoring

### Health Checks

```ini
[Container]
HealthCmd=curl -f http://localhost:8080/health || exit 1
HealthInterval=30s
HealthTimeout=10s
HealthRetries=3
HealthStartPeriod=60s
```

### Resource Monitoring

```bash
# Monitor resource usage
podman stats mariadb

# Container events
podman events --filter container=mariadb
```

## Security

### Read-Only Root

```ini
[Container]
ReadOnly=true
Tmpfs=/tmp
Tmpfs=/run
```

### Drop Capabilities

```ini
[Container]
DropCapability=ALL
AddCapability=CHOWN
AddCapability=DAC_OVERRIDE
AddCapability=SETGID
AddCapability=SETUID
```

### User Namespace

```ini
[Container]
# Run as specific UID/GID inside container
User=mysql:mysql
```

## Examples

### WordPress + MariaDB

**mariadb.container**:
```ini
[Unit]
Description=MariaDB for WordPress
After=network-online.target

[Container]
Image=docker.io/library/mariadb:10.11
ContainerName=wp-mariadb
Volume=wp-mariadb-data.volume:/var/lib/mysql:Z
Environment=MYSQL_ROOT_PASSWORD=rootpass
Environment=MYSQL_DATABASE=wordpress
Environment=MYSQL_USER=wpuser
Environment=MYSQL_PASSWORD=wppass
Network=wordpress.network

[Service]
Restart=always

[Install]
WantedBy=multi-user.target
```

**wordpress.container**:
```ini
[Unit]
Description=WordPress
Requires=mariadb.service
After=mariadb.service

[Container]
Image=docker.io/library/wordpress:latest
ContainerName=wordpress
Volume=wp-data.volume:/var/www/html:Z
PublishPort=80:80
Environment=WORDPRESS_DB_HOST=wp-mariadb
Environment=WORDPRESS_DB_USER=wpuser
Environment=WORDPRESS_DB_PASSWORD=wppass
Environment=WORDPRESS_DB_NAME=wordpress
Network=wordpress.network

[Service]
Restart=always

[Install]
WantedBy=multi-user.target
```

**wordpress.network**:
```ini
[Network]
Driver=bridge

[Install]
WantedBy=multi-user.target
```

## Best Practices

1. **Use rootless when possible**: Better security isolation
2. **Enable auto-updates**: Keep containers current
3. **Set resource limits**: Prevent resource exhaustion
4. **Use health checks**: Detect and restart failing containers
5. **Separate data volumes**: Easy backup and migration
6. **Enable lingering**: Services survive logout
7. **Use secrets**: Don't hardcode passwords
8. **Monitor logs**: `journalctl -u servicename`

## Next Steps

- [Kubernetes Deployment](deployment-k8s.md)
- [Bare-Metal Systemd Deployment](deployment-baremetal.md)
- [Service Contract Reference](service-contracts.md)