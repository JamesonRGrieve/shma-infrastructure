# Kubernetes Deployment Guide

Render Kubernetes manifests with Secret integration, readiness probes, hostPath-aware volumes, and resource requests derived from the shared contract.

## Updates

- `templates/kubernetes.yml.j2` emits separate Secrets for environment variables and file-backed material to keep RBAC scopes narrow.
- Containers mount secret files via a dedicated volume and consume environment variables via `valueFrom`.
- Liveness and readiness probes originate from `health.cmd`, keeping checks consistent across runtimes.
- Volume definitions now support `service_volumes.host_path`, which renders a `hostPath` mount when you want container filesystems to remain ephemeral while data persists on the node. Set `host_path_type` when you need a specific Kubernetes `hostPath` strategy.
- Pin `service_image` values by digest; the rendered Deployment references that immutable identifier so rollouts remain deliberate.
- `service_resources.connections_per_second` emits a `CONNECTIONS_PER_SECOND` environment variable that rate-limiting sidecars
  (nginx/envoy) can use to clamp per-pod connection bursts.

## Prerequisites

```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
ansible-galaxy collection install kubernetes.core
```

## Rendered resources

`templates/kubernetes.yml.j2` emits:

- `Secret` – named `<service_id>-env`, containing keys for every `secrets.env` entry.
- `Secret` – named `<service_id>-files`, storing the rendered secret files.
- `PersistentVolumeClaim` – sized from `service_storage_gb` or `service_storage_size`. Skipped automatically when `service_volumes.host_path` is provided.
- `emptyDir` – emitted for each `mounts.ephemeral_mounts` entry that applies to Kubernetes, defaulting to `medium: Memory`.
- `Deployment` – references the Secret for env vars, mounts secret files, configures probes/resources, and enforces non-root security defaults.
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
          securityContext:
            runAsUser: 65532
            runAsGroup: 65532
            runAsNonRoot: true
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
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
            - name: data
              mountPath: /etc/sample-service
            - name: runtime-run
              mountPath: /run/sample-service
              readOnly: false
          livenessProbe:
            exec:
              command: ["/bin/sh", "-c", "exit 0"]
            periodSeconds: 10
          readinessProbe:
            exec:
              command: ["/bin/sh", "-c", "exit 0"]
            initialDelaySeconds: 10
            periodSeconds: 10

      volumes:
        - name: secret-files
          secret:
            secretName: sample-service-files
        - name: data
          hostPath:
            path: /srv/sample-service/config
            type: DirectoryOrCreate
        - name: runtime-run
          emptyDir:
            medium: Memory
            sizeLimit: 64Mi
```

## Validation

Render and validate locally:

```bash
ansible-playbook tests/render.yml -e runtime=kubernetes -e @tests/sample_service.yml
kubectl apply --dry-run=client --validate=true -f /tmp/ansible-runtime/sample-service/kubernetes.yml
```

## Deployment tips

- Ensure the referenced namespace (`k8s_namespace`) exists before applying.
- Use the generated `<service_id>-files` Secret for only the workloads that truly need those files; other deployments can skip mounting the `secret-files` volume entirely.
- Adjust `service_replicas` to scale deployments and rely on the readiness probe before routing traffic.
