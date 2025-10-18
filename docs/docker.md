# Docker Compose Deployment Guide

Deploy services using Docker Compose for simple, portable containerized applications.

## Prerequisites

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose plugin
apt install docker-compose-plugin

# Install Ansible Docker collection
ansible-galaxy collection install community.docker
pip3 install docker docker-compose
```

## Configuration

### Environment Variables

```bash
# .env file
RUNTIME=compose

# Service configuration
MARIADB_ROOT_PASSWORD=secure_password
MARIADB_USER=app
MARIADB_USER_PASSWORD=user_password
MARIADB_DATABASE=appdb
MARIADB_VERSION=10.11
MARIADB_IP=192.168.0.200
```

### Docker Network

```bash
# Create shared network for services
docker network create app-network
```

## Deployment

### Basic Deployment

```bash
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=compose
```

### Custom Compose File Location

```bash
ansible-playbook playbooks/deploy-mariadb.yml \
  -e runtime=compose \
  -e compose_project_path=/opt/services/mariadb
```

### Deploy Multiple Services

```bash
# Deploy full stack
ansible-playbook playbooks/deploy-stack.yml -e runtime=compose
```

## Compose Template Structure

```yaml
version: '3.8'

services:
  {{ service_id }}:
    image: {{ image }}:{{ version }}
    container_name: {{ hostname }}
    restart: unless-stopped
    
    environment:
      ENV_VAR: {{ value }}
    
    volumes:
      - {{ service_id }}-data:{{ storage_path }}
    
    ports:
      - "{{ host_ip }}:{{ host_port }}:{{ container_port }}"
    
    networks:
      - app-network
    
    healthcheck:
      test: {{ health.cmd }}
      interval: {{ health.interval }}
      timeout: {{ health.timeout }}
      retries: {{ health.retries }}

volumes:
  {{ service_id }}-data:
    driver: local

networks:
  app-network:
    external: true
```

## Advanced Configuration

### Volume Management

**Named volumes**:
```yaml
volumes:
  mariadb-data:
    driver: local
```

**Bind mounts**:
```yaml
volumes:
  - /opt/data/mariadb:/var/lib/mysql
```

**NFS volumes**:
```yaml
volumes:
  mariadb-data:
    driver: local
    driver_opts:
      type: nfs
      o: addr=nas.local,rw
      device: ":/export/mariadb"
```

### Resource Limits

```yaml
services:
  mariadb:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

### Custom Networks

```yaml
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true  # No external access
```

### Environment Files

```yaml
services:
  mariadb:
    env_file:
      - .env
      - .env.production
```

## Service Management

### Start/Stop Services

```bash
# Start
docker-compose -f /path/to/compose.yml up -d

# Stop
docker-compose -f /path/to/compose.yml stop

# Restart
docker-compose -f /path/to/compose.yml restart

# Remove
docker-compose -f /path/to/compose.yml down
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f mariadb

# Last 100 lines
docker-compose logs --tail=100 mariadb
```

### Execute Commands

```bash
# Interactive shell
docker-compose exec mariadb bash

# Run command
docker-compose exec mariadb mysqladmin ping
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs mariadb

# Check events
docker events --filter container=mariadb

# Inspect container
docker inspect mariadb
```

### Port Conflicts

```bash
# Check what's using the port
lsof -i :3306
netstat -tulpn | grep 3306

# Change port in compose file
ports:
  - "3307:3306"  # Use different host port
```

### Volume Permission Issues

```bash
# Fix ownership inside container
docker-compose exec mariadb chown -R mysql:mysql /var/lib/mysql

# Or use user mapping
services:
  mariadb:
    user: "1000:1000"
```

### Network Issues

```bash
# Recreate network
docker network rm app-network
docker network create app-network

# Check network connectivity
docker-compose exec mariadb ping other-service
```

## Backup and Restore

### Database Backup

```bash
# MySQL/MariaDB dump
docker-compose exec mariadb mysqldump \
  -u root -p"${MARIADB_ROOT_PASSWORD}" \
  --all-databases > backup.sql

# Restore
docker-compose exec -T mariadb mysql \
  -u root -p"${MARIADB_ROOT_PASSWORD}" \
  < backup.sql
```

### Volume Backup

```bash
# Stop service
docker-compose stop mariadb

# Backup volume
docker run --rm \
  -v mariadb_mariadb-data:/source \
  -v /backup:/backup \
  alpine tar czf /backup/mariadb-$(date +%Y%m%d).tar.gz -C /source .

# Restore volume
docker run --rm \
  -v mariadb_mariadb-data:/target \
  -v /backup:/backup \
  alpine tar xzf /backup/mariadb-20241016.tar.gz -C /target

# Start service
docker-compose start mariadb
```

## Security Best Practices

### Secrets Management

```yaml
# Use Docker secrets (Swarm mode)
services:
  mariadb:
    secrets:
      - db_root_password

secrets:
  db_root_password:
    external: true
```

### Read-Only Root Filesystem

```yaml
services:
  mariadb:
    read_only: true
    tmpfs:
      - /tmp
      - /run
```

### Drop Capabilities

```yaml
services:
  mariadb:
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - DAC_OVERRIDE
      - SETGID
      - SETUID
```

### Network Isolation

```yaml
# Backend services not exposed to host
services:
  mariadb:
    networks:
      - backend  # No ports published

  app:
    ports:
      - "80:80"  # Only app exposed
    networks:
      - frontend
      - backend
```

## Monitoring

### Health Checks

```yaml
healthcheck:
  test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### Prometheus Integration

```yaml
services:
  mariadb:
    labels:
      - "prometheus.scrape=true"
      - "prometheus.port=9104"
  
  mysql-exporter:
    image: prom/mysqld-exporter
    environment:
      DATA_SOURCE_NAME: "exporter:password@(mariadb:3306)/"
    ports:
      - "9104:9104"
```

## Performance Tuning

### Logging Drivers

```yaml
services:
  mariadb:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Build Cache

```bash
# Use BuildKit for faster builds
DOCKER_BUILDKIT=1 docker-compose build

# Enable BuildKit permanently
echo '{"features": {"buildkit": true}}' > /etc/docker/daemon.json
systemctl restart docker
```

## Examples

### WordPress + MariaDB Stack

```yaml
version: '3.8'

services:
  wordpress:
    image: wordpress:latest
    depends_on:
      mariadb:
        condition: service_healthy
    environment:
      WORDPRESS_DB_HOST: mariadb
      WORDPRESS_DB_USER: wordpress
      WORDPRESS_DB_PASSWORD: ${WP_DB_PASSWORD}
      WORDPRESS_DB_NAME: wordpress
    ports:
      - "80:80"
    volumes:
      - wordpress-data:/var/www/html
    networks:
      - app-network

  mariadb:
    image: mariadb:10.11
    environment:
      MYSQL_ROOT_PASSWORD: ${MARIADB_ROOT_PASSWORD}
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wordpress
      MYSQL_PASSWORD: ${WP_DB_PASSWORD}
    volumes:
      - mariadb-data:/var/lib/mysql
    networks:
      - app-network
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  wordpress-data:
  mariadb-data:

networks:
  app-network:
    driver: bridge
```

## Migration

### From Docker Run to Compose

```bash
# Export running container config
docker inspect mariadb > container.json

# Convert to compose format (manual)
# Or use tools like composerize
```

### To Kubernetes

```bash
# Use kompose to convert
kompose convert -f docker-compose.yml
```

## Next Steps

- [Podman Quadlet Deployment](deployment-quadlet.md)
- [Kubernetes Deployment](deployment-k8s.md)
- [Creating Services](creating-services.md)