# Kubernetes Deployment Guide

Render Kubernetes manifests with Secret integration, readiness probes, and resource requests derived from the shared contract.

## Updates

- `templates/kubernetes.yml.j2` generates a single Secret that stores both environment variables and file-based secrets.
- Containers mount secret files via a dedicated volume and consume environment variables via `valueFrom`.
- Liveness and readiness probes originate from `health.cmd`, keeping checks consistent across runtimes.

## Prerequisites

```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
ansible-galaxy collection install kubernetes.core
```

## Rendered resources

`templates/kubernetes.yml.j2` emits:

- `Secret` – named `<service_id>-secrets`, containing keys for every `secrets.env` entry plus file secrets.
- `PersistentVolumeClaim` – sized via `mariadb_storage_gb`.
- `Deployment` – references the Secret for env vars, mounts secret files, and configures probes/resources.
- `Service` – cluster-internal exposure on port 3306.

Snippet:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mariadb
spec:
  template:
    spec:
      containers:
        - name: mariadb
          env:
            - name: MYSQL_ROOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: mariadb-secrets
                  key: MYSQL_ROOT_PASSWORD
          volumeMounts:
            - name: secret-files
              mountPath: /etc/mysql/certs/ca.pem
              subPath: ca-cert
              readOnly: true
          livenessProbe:
            exec:
              command: ["mysqladmin", "ping", "-h", "127.0.0.1", "-P", "3306"]
            periodSeconds: 10
          readinessProbe:
            exec:
              command: ["mysqladmin", "ping", "-h", "127.0.0.1", "-P", "3306"]
            initialDelaySeconds: 10
            periodSeconds: 10
```

## Validation

Render and validate locally:

```bash
ansible-playbook tests/render.yml -e runtime=kubernetes -e @tests/sample_service.yml
kubectl apply --dry-run=client --validate=true -f /tmp/ansible-runtime/mariadb/kubernetes.yml
```

## Deployment tips

- Ensure the referenced namespace (`k8s_namespace`) exists before applying.
- Consider separate Secrets when mounting large binary blobs; the template can be extended by adding entries to `secrets.files`.
- Adjust `mariadb_replicas` to scale deployments and rely on the readiness probe before routing traffic.
