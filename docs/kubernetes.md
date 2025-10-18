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
- `PersistentVolumeClaim` – sized from `service_storage_gb` or `service_storage_size`.
- `Deployment` – references the Secret for env vars, mounts secret files, and configures probes/resources.
- `Service` – exposes declared `service_ports` within the cluster.

Snippet:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sample-service
spec:
  template:
    spec:
      containers:
        - name: sample-service
          env:
            - name: SAMPLE_SERVICE_TOKEN
              valueFrom:
                secretKeyRef:
                  name: sample-service-secrets
                  key: SAMPLE_SERVICE_TOKEN
          volumeMounts:
            - name: secret-files
              mountPath: /etc/sample-service/certs/tls.crt
              subPath: tls-cert
              readOnly: true
          livenessProbe:
            exec:
              command: ["/bin/sh", "-c", "exit 0"]
            periodSeconds: 10
          readinessProbe:
            exec:
              command: ["/bin/sh", "-c", "exit 0"]
            initialDelaySeconds: 10
            periodSeconds: 10
```

## Validation

Render and validate locally:

```bash
ansible-playbook tests/render.yml -e runtime=kubernetes -e @tests/sample_service.yml
kubectl apply --dry-run=client --validate=true -f /tmp/ansible-runtime/sample-service/kubernetes.yml
```

## Deployment tips

- Ensure the referenced namespace (`k8s_namespace`) exists before applying.
- Consider separate Secrets when mounting large binary blobs; extend `secrets.files` as needed.
- Adjust `service_replicas` to scale deployments and rely on the readiness probe before routing traffic.
