# Self-Hosted Infrastructure Framework

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Ansible](https://img.shields.io/badge/ansible-2.15%2B-red.svg)](https://www.ansible.com/)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Documentation](https://img.shields.io/badge/docs-passing-success.svg)](docs/)

A runtime-agnostic infrastructure-as-code framework for deploying self-hosted applications across **Proxmox LXC**, **Docker Compose**, **Podman Quadlets**, **Kubernetes**, and **bare-metal systemd** from a single service definition.

## 🎯 Key Features

- **Write Once, Deploy Anywhere**: Define your service once, deploy to any runtime
- **Runtime Agnostic**: Supports 5 deployment targets from the same codebase
- **Service Contracts**: Explicit dependencies, exports, storage, and health checks
- **DRY Architecture**: No duplicated YAML across runtimes
- **Production Ready**: Built-in health checks, secrets management, and validation
- **Extensible**: Easy to add new services and runtime adapters

## 🚀 Quick Start

### Prerequisites

```bash
# Install Ansible
apt install ansible python3-pip

# Install required collections
ansible-galaxy collection install community.general community.docker kubernetes.core
pip3 install proxmoxer requests
```

### Deploy Your First Service

```bash
# Clone the repository
git clone https://github.com/yourusername/infra-framework
cd infra-framework

# Create environment configuration
cat > .env <<EOF
RUNTIME=lxc
MARIADB_ROOT_PASSWORD=secure_password
MARIADB_USER_PASSWORD=user_password
PROXMOX_API_HOST=proxmox.local
PROXMOX_API_USER=root@pam
PROXMOX_API_PASSWORD=your_password
PROXMOX_NODE=pve
EOF

# Deploy MariaDB
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=lxc
```

### Switch Runtime Targets

```bash
# Deploy to Docker Compose instead
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=compose

# Deploy to Kubernetes
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=k8s -e k8s_namespace=production

# Deploy to Podman Quadlet
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=quadlet

# Deploy to bare-metal systemd
ansible-playbook playbooks/deploy-mariadb.yml -e runtime=baremetal
```

## 📋 Architecture

```
infrastructure/
├── roles/
│   └── common/
│       ├── validate_schema/    # Contract validation
│       ├── render_runtime/     # Template rendering
│       └── apply_runtime/      # Runtime deployment
│           ├── lxc.yml
│           ├── compose.yml
│           ├── quadlet.yml
│           ├── k8s.yml
│           └── baremetal.yml
├── schemas/
│   └── service.schema.yml      # Service contract schema
│
svc-{service}/
├── roles/service/
│   ├── defaults/main.yml       # Service contract + configuration
│   ├── templates/
│   │   ├── lxc.yml.j2
│   │   ├── compose.yml.j2
│   │   ├── quadlet.container.j2
│   │   ├── k8s.yml.j2
│   │   └── systemd.service.j2
│   └── tasks/main.yml
└── README.md
```

## 📚 Documentation

- [Architecture Overview](docs/architecture.md) - System design and flow diagrams
- [Proxmox LXC Deployment](docs/deployment-lxc.md)
- [Docker Compose Deployment](docs/deployment-compose.md)
- [Podman Quadlet Deployment](docs/deployment-quadlet.md)
- [Kubernetes Deployment](docs/deployment-k8s.md)
- [Bare-Metal Systemd Deployment](docs/deployment-baremetal.md)
- [Creating New Services](docs/creating-services.md)
- [Service Contract Reference](docs/service-contracts.md)

## 🔧 Available Services

| Service    | Status    | LXC | Compose | Quadlet | K8s | Baremetal |
| ---------- | --------- | --- | ------- | ------- | --- | --------- |
| MariaDB    | ✅ Stable  | ✅   | ✅       | ✅       | ✅   | ✅         |
| ERPNext    | 🚧 WIP     | ✅   | ✅       | ✅       | ✅   | ⏳         |
| Redis      | 📋 Planned | -   | -       | -       | -   | -         |
| PostgreSQL | 📋 Planned | -   | -       | -       | -   | -         |

## 🎓 Example: Service Contract

```yaml
# svc-mariadb/roles/service/defaults/main.yml
service_id: mariadb
version: "10.11"

requires: []

exports:
  env:
    - name: MARIADB_HOST
      value: "{{ ansible_default_ipv4.address }}"
    - name: MARIADB_PORT
      value: "3306"

storage:
  - name: data
    path: /var/lib/mysql
    size_gb: 50

health:
  cmd: ["mysqladmin", "ping", "-h", "localhost"]
  interval: 10s
  retries: 3

runtime_templates:
  lxc: templates/lxc.yml.j2
  compose: templates/compose.yml.j2
  quadlet: templates/quadlet.container.j2
  k8s: templates/k8s.yml.j2
  baremetal: templates/systemd.service.j2
```

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

### Adding a New Service

1. Create service repository: `svc-yourservice/`
2. Define service contract in `defaults/main.yml`
3. Create templates for each runtime
4. Test across all supported runtimes
5. Submit PR with documentation

### Adding a New Runtime

1. Create adapter in `infrastructure/roles/common/apply_runtime/tasks/`
2. Update service templates to support new runtime
3. Add documentation
4. Test with existing services

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by the need for truly portable infrastructure-as-code
- Built with [Ansible](https://www.ansible.com/)
- Supports [Proxmox VE](https://www.proxmox.com/), [Docker](https://www.docker.com/), [Podman](https://podman.io/), [Kubernetes](https://kubernetes.io/)

## 📞 Support

- 📫 Issues: [GitHub Issues](https://github.com/yourusername/infra-framework/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/yourusername/infra-framework/discussions)
- 📖 Documentation: [docs/](docs/)

---

**Made with ❤️ for infrastructure engineers who value portability**