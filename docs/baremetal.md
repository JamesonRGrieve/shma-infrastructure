# Bare-Metal Systemd Deployment Guide

Deploy services directly on bare-metal or virtual machines using systemd for traditional infrastructure management with maximum control and performance.

## Prerequisites

### Operating System
- Ubuntu 20.04+ / Debian 11+
- RHEL 8+ / Rocky Linux 8+
- Systemd 240+

### System Requirements
```bash
# Install dependencies
apt update
apt install systemd python3-apt
```

## Configuration

### Environment Variables

```bash
# .env file
RUNTIME=baremetal

# Service configuration
MARIADB_ROOT_PASSWORD=secure_password
MARIADB_USER=app
MARIADB_USER_PASSWORD=user_password
MARIADB_DATABASE=appdb
MARIADB_VERSION=10.11
```

### Inventory Setup

```ini
# inventory/hosts.ini
[database_servers]
db01.example.com ansible_host=192.168.0.10
db02.example.com ansible_host=192.168.0.11

[database_servers:vars]
ansible_user=ubuntu
ansible_become=yes
```

## Deployment

### Basic Deployment

```bash
ansible-playbook playbooks/deploy-mariadb.yml \
  -e runtime=baremetal \
  -i inventory/hosts.ini
```

### Multi-Server Deployment

```bash
# Deploy to all database servers
ansible-playbook playbooks/deploy-mariadb.yml \
  -e runtime=baremetal \
  -i inventory/hosts.ini \
  --limit database_servers
```

## Systemd Template Structure

```ini
# /etc/systemd/system/mariadb.service
[Unit]
Description={{ service_description }}
After=network.target

[Service]
Type=notify
User={{ service_user }}
Group={{ service_group }}

# Environment
Environment="VAR_NAME=value"
EnvironmentFile=-/etc/default/{{ service_id }}

# Execution
ExecStartPre={{ pre_start_commands }}
ExecStart={{ start_command }}
ExecReload={{ reload_command }}
ExecStop={{ stop_command }}

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadOnlyPaths=/etc /usr

# Restart policy
Restart=on-failure
RestartSec=5s

# Resource limits
LimitNOFILE=65535
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
```

## Service Management

### Systemd Commands

```bash
# Status
systemctl status mariadb

# Start/Stop/Restart
systemctl start mariadb
systemctl stop mariadb
systemctl restart mariadb
systemctl reload mariadb

# Enable/Disable autostart
systemctl enable mariadb
systemctl disable mariadb

# Logs
journalctl -u mariadb -f
journalctl -u mariadb --since "1 hour ago"

# Check if enabled
systemctl is-enabled mariadb

# Check if running
systemctl is-active mariadb
```

### Service Dependencies

```ini
[Unit]
Requires=network.target mariadb.service
After=network.target mariadb.service

# Start before other service
Before=application.service

# Bind lifecycle to another unit
BindsTo=mount-data.service
```

## Advanced Configuration

### Environment Files

```bash
# /etc/default/mariadb
MYSQL_ROOT_PASSWORD=secure_password
MYSQL_DATADIR=/var/lib/mysql
MYSQL_LOG_ERROR=/var/log/mysql/error.log
MYSQL_PID_FILE=/var/run/mysqld/mysqld.pid
```

```ini
[Service]
EnvironmentFile=/etc/default/mariadb
```

### Resource Limits

```ini
[Service]
# CPU
CPUQuota=200%
CPUWeight=100

# Memory
MemoryMax=2G
MemoryHigh=1.5G
MemorySwapMax=0

# Tasks
TasksMax=4096

# File descriptors
LimitNOFILE=65535

# Processes
LimitNPROC=4096
```

### Security Hardening

```ini
[Service]
# Restrict privileges
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

# Restrict network
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

# Restrict namespaces
RestrictNamespaces=true

# System calls
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM

# Filesystem
ReadWritePaths=/var/lib/mysql /var/log/mysql
ReadOnlyPaths=/etc/mysql

# Capabilities
CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE CAP_SETGID CAP_SETUID
AmbientCapabilities=CAP_CHOWN CAP_DAC_OVERRIDE CAP_SETGID CAP_SETUID
```

### Timer Units (Cron Alternative)

```ini
# /etc/systemd/system/mariadb-backup.service
[Unit]
Description=MariaDB Backup

[Service]
Type=oneshot
ExecStart=/usr/local/bin/backup-mariadb.sh
```

```ini
# /etc/systemd/system/mariadb-backup.timer
[Unit]
Description=Daily MariaDB Backup

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# Enable timer
systemctl enable --now mariadb-backup.timer

# List timers
systemctl list-timers
```

## Installation Process

### Package Installation

```yaml
# Ansible tasks
- name: Install MariaDB packages
  apt:
    name:
      - mariadb-server
      - mariadb-client
      - python3-pymysql
    state: present
    update_cache: yes

- name: Create systemd unit file
  template:
    src: mariadb.service.j2
    dest: /etc/systemd/system/mariadb.service
    mode: '0644'

- name: Reload systemd daemon
  systemd:
    daemon_reload: yes

- name: Enable and start service
  systemd:
    name: mariadb
    enabled: yes
    state: started
```

### Configuration Management

```yaml
- name: Create config directory
  file:
    path: /etc/mysql/conf.d
    state: directory
    owner: mysql
    group: mysql
    mode: '0755'

- name: Deploy custom config
  template:
    src: custom.cnf.j2
    dest: /etc/mysql/conf.d/99-custom.cnf
    owner: mysql
    group: mysql
    mode: '0644'
  notify: restart mariadb

- name: Create data directory
  file:
    path: /var/lib/mysql
    state: directory
    owner: mysql
    group: mysql
    mode: '0750'
```

## Troubleshooting

### Service Won't Start

```bash
# Check service status
systemctl status mariadb

# View full logs
journalctl -xe -u mariadb

# Check configuration
systemctl show mariadb

# Verify binary exists
which mysqld
ls -la /usr/sbin/mysqld
```

### Permission Issues

```bash
# Check file ownership
ls -la /var/lib/mysql
ls -la /var/log/mysql

# Fix ownership
chown -R mysql:mysql /var/lib/mysql
chown -R mysql:mysql /var/log/mysql

# Check SELinux (RHEL/CentOS)
getenforce
ausearch -m avc -ts recent
```

### Port Conflicts

```bash
# Check what's using port
lsof -i :3306
netstat -tulpn | grep 3306
ss -tulpn | grep 3306

# Change port in config
# /etc/mysql/conf.d/custom.cnf
[mysqld]
port = 3307
```

### Resource Exhaustion

```bash
# Check resource limits
systemctl show mariadb | grep -i limit

# Increase limits
systemctl edit mariadb
# Add override:
[Service]
LimitNOFILE=100000

# Reload
systemctl daemon-reload
systemctl restart mariadb
```

## Backup and Restore

### Automated Backups

```bash
# /usr/local/bin/backup-mariadb.sh
#!/bin/bash
BACKUP_DIR=/backup/mariadb
DATE=$(date +%Y%m%d-%H%M%S)

mysqldump --all-databases \
  --single-transaction \
  --quick \
  --lock-tables=false \
  | gzip > "$BACKUP_DIR/mariadb-$DATE.sql.gz"

# Keep last 7 days
find "$BACKUP_DIR" -name "mariadb-*.sql.gz" -mtime +7 -delete
```

```bash
# Make executable
chmod +x /usr/local/bin/backup-mariadb.sh

# Test backup
/usr/local/bin/backup-mariadb.sh
```

### Restore from Backup

```bash
# Stop service
systemctl stop mariadb

# Restore database
gunzip < /backup/mariadb-20241016.sql.gz | mysql -u root -p

# Start service
systemctl start mariadb
```

## Monitoring

### Systemd Journal

```bash
# Follow logs
journalctl -u mariadb -f

# Logs since boot
journalctl -u mariadb -b

# Logs from last hour
journalctl -u mariadb --since "1 hour ago"

# Logs with priority
journalctl -u mariadb -p err
```

### Health Checks

```bash
# Create health check script
cat > /usr/local/bin/check-mariadb.sh <<'EOF'
#!/bin/bash
mysqladmin ping -h localhost --silent
exit $?
EOF

chmod +x /usr/local/bin/check-mariadb.sh
```

### Integration with Monitoring

```ini
# Expose metrics for Prometheus
[Unit]
Description=MariaDB Exporter
After=mariadb.service

[Service]
Type=simple
ExecStart=/usr/local/bin/mysqld_exporter \
  --config.my-cnf=/etc/mysql/.mysqld_exporter.cnf

[Install]
WantedBy=multi-user.target
```

## High Availability

### Database Replication

**Primary server**:
```sql
CREATE USER 'replicator'@'%' IDENTIFIED BY 'password';
GRANT REPLICATION SLAVE ON *.* TO 'replicator'@'%';
FLUSH PRIVILEGES;
```

**Replica server**:
```sql
CHANGE MASTER TO
  MASTER_HOST='192.168.0.10',
  MASTER_USER='replicator',
  MASTER_PASSWORD='password',
  MASTER_LOG_FILE='mysql-bin.000001',
  MASTER_LOG_POS=154;
START SLAVE;
```

### Keepalived (VIP)

```bash
# /etc/keepalived/keepalived.conf
vrrp_instance VI_1 {
    state MASTER
    interface eth0
    virtual_router_id 51
    priority 100
    virtual_ipaddress {
        192.168.0.100/24
    }
}
```

## Migration

### From Docker/Containers

```bash
# Export data from container
docker exec mariadb mysqldump --all-databases > dump.sql

# Import to bare-metal
mysql -u root -p < dump.sql
```

### From Another Server

```bash
# On source server
mysqldump --all-databases | gzip > /tmp/dump.sql.gz

# Transfer
scp /tmp/dump.sql.gz target:/tmp/

# On target server
gunzip < /tmp/dump.sql.gz | mysql -u root -p
```

## Performance Tuning

### System Limits

```bash
# /etc/security/limits.conf
mysql soft nofile 65535
mysql hard nofile 65535
mysql soft nproc 4096
mysql hard nproc 4096
```

### Kernel Parameters

```bash
# /etc/sysctl.d/99-mariadb.conf
vm.swappiness = 1
net.ipv4.tcp_max_syn_backlog = 4096
net.core.somaxconn = 1024
```

```bash
# Apply
sysctl --system
```

## Security

### Firewall

```bash
# UFW
ufw allow from 192.168.0.0/24 to any port 3306

# firewalld
firewall-cmd --permanent --add-rich-rule='
  rule family="ipv4"
  source address="192.168.0.0/24"
  port protocol="tcp" port="3306" accept'
firewall-cmd --reload
```

### AppArmor/SELinux

**AppArmor**:
```bash
# Ubuntu/Debian
aa-enforce /etc/apparmor.d/usr.sbin.mysqld
```

**SELinux**:
```bash
# RHEL/CentOS
setsebool -P mysql_connect_any on
semanage port -a -t mysqld_port_t -p tcp 3307
```

## Next Steps

- [Creating Custom Services](creating-services.md)
- [Service Contract Reference](service-contracts.md)
- [Architecture Overview](architecture.md)