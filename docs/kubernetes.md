# Kubernetes Deployment Guide

Render Kubernetes manifests with Secret integration, readiness probes, and resource requests derived from the shared contract.

## Updates

- `templates/kubernetes.yml.j2` separates environment and file secrets (`<service_id>-env` and `<service_id>-files`).
- Containers mount secret files via a dedicated volume and consume environment variables via `valueFrom` pointing to the env Secret.
- Liveness and readiness probes originate from `health.cmd`, keeping checks consistent across runtimes.

## Prerequisites

```bash
KUBECTL_VERSION=v1.29.3
curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl.sha256"
echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check -
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
ansible-galaxy collection install kubernetes.core
```

## Rendered resources

`templates/kubernetes.yml.j2` emits:

- `Secret` – named `<service_id>-env` and `<service_id>-files`, containing env vars and file-backed secrets respectively.
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
                  name: sample-service-env
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
kubectl apply --dry-run=server --validate=true -f /tmp/ansible-runtime/sample-service/kubernetes.yml
```

## Deployment tips

- Ensure the referenced namespace (`k8s_namespace`) exists before applying.
- Adjust secret naming conventions through the template if a workload requires different boundaries (for example, per-mount Secrets).
- Adjust `service_replicas` to scale deployments and rely on the readiness probe before routing traffic.
