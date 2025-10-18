# Kubernetes Deployment Guide

Deploy services to Kubernetes for scalable, highly-available containerized applications with built-in orchestration.

## Prerequisites

```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Install Ansible Kubernetes collection
ansible-galaxy collection install kubernetes.core
pip3 install kubernetes openshift
```

### Kubernetes Cluster

You need access to a running Kubernetes cluster:
- Managed: EKS, GKE, AKS
- Self-hosted: kubeadm, k3s, RKE
- Local: minikube, kind, k3d

```bash
# Verify cluster access
kubectl cluster-info
kubectl get nodes
```

## Configuration

### Environment Variables

```bash
# .env file
RUNTIME=k8s

# Kubernetes configuration
K8S_NAMESPACE=production
K8S_CONTEXT=my-cluster  # Optional, uses current context if not set

# Service configuration
MARIADB_ROOT_PASSWORD=secure_password
MARIADB_USER=app
MARIADB_USER_PASSWORD=user_password
MARIADB_DATABASE=appdb
MARIADB_VERSION=10.11
MARIADB_STORAGE_GB=50
MARIADB_MEMORY=2048
MARIADB_CORES=2
```

### Kubeconfig

```bash
# Set kubeconfig location
export KUBECONFIG=~/.kube/config

# Or specify in playbook
ansible-playbook playbooks/deploy.yml \
  -e runtime=k8s \
  -e kubeconfig_path=/path/to/kubeconfig
```

## Deployment

### Basic Deployment

```bash
# Create namespace
kubectl create namespace production

# Deploy service
ansible-playbook playbooks/deploy-mariadb.yml \
  -e runtime=k8s \
  -e k8s_namespace=production
```

### Multi-Environment Deployment

```bash
# Development
ansible-playbook playbooks/deploy-mariadb.yml \
  -e runtime=k8s \
  -e k8s_namespace=development \
  -e mariadb_replicas=1

# Production
ansible-playbook playbooks/deploy-mariadb.yml \
  -e runtime=k8s \
  -e k8s_namespace=production \
  -e mariadb_replicas=3
```

## Kubernetes Template Structure

Services generate these resources:

**Secret**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: {{ service_id }}-secrets
  namespace: {{ k8s_namespace }}
type: Opaque
stringData:
  root-password: {{ root_password }}
  user-password: {{ user_password }}
```

**PersistentVolumeClaim**:
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ service_id }}-data
  namespace: {{ k8s_namespace }}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: {{ storage_gb }}Gi
  storageClassName: {{ storage_class }}
```

**Deployment**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ service_id }}
  namespace: {{ k8s_namespace }}
spec:
  replicas: {{ replicas }}
  selector:
    matchLabels:
      app: {{ service_id }}
  template:
    metadata:
      labels:
        app: {{ service_id }}
    spec:
      containers:
      - name: {{ service_id }}
        image: {{ image }}:{{ version }}
        env:
        - name: VAR_NAME
          valueFrom:
            secretKeyRef:
              name: {{ service_id }}-secrets
              key: var-name
        ports:
        - containerPort: {{ port }}
        volumeMounts:
        - name: data
          mountPath: {{ mount_path }}
        livenessProbe:
          exec:
            command: {{ health.cmd }}
          initialDelaySeconds: 30
          periodSeconds: {{ health.interval }}
        resources:
          requests:
            memory: {{ memory }}Mi
            cpu: {{ cores }}
          limits:
            memory: {{ memory }}Mi
            cpu: {{ cores }}
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: {{ service_id }}-data
```

**Service**:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ service_id }}
  namespace: {{ k8s_namespace }}
spec:
  selector:
    app: {{ service_id }}
  ports:
  - port: {{ port }}
    targetPort: {{ port }}
  type: ClusterIP
```

## Advanced Configuration

### High Availability

```yaml
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  
  # Anti-affinity: spread pods across nodes
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
            - key: app
              operator: In
              values:
              - mariadb
          topologyKey: kubernetes.io/hostname
```

### StatefulSet for Databases

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mariadb
spec:
  serviceName: mariadb-headless
  replicas: 3
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 50Gi
```

### ConfigMaps

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mariadb-config
data:
  my.cnf: |
    [mysqld]
    max_connections = 200
    innodb_buffer_pool_size = 1G
---
spec:
  containers:
  - name: mariadb
    volumeMounts:
    - name: config
      mountPath: /etc/mysql/conf.d
  volumes:
  - name: config
    configMap:
      name: mariadb-config
```

### Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - app.example.com
    secretName: app-tls
  rules:
  - host: app.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: app
            port:
              number: 80
```

### Resource Quotas

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: namespace-quota
  namespace: production
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
    persistentvolumeclaims: "10"
```

## Service Management

### Kubectl Commands

```bash
# Get resources
kubectl get pods -n production
kubectl get deployments -n production
kubectl get services -n production
kubectl get pvc -n production

# Describe resources
kubectl describe pod mariadb-xxx -n production
kubectl describe deployment mariadb -n production

# Logs
kubectl logs -f mariadb-xxx -n production
kubectl logs -f deployment/mariadb -n production

# Execute commands
kubectl exec -it mariadb-xxx -n production -- bash
kubectl exec -it mariadb-xxx -n production -- mysqladmin ping

# Port forwarding
kubectl port-forward service/mariadb 3306:3306 -n production

# Scale
kubectl scale deployment/mariadb --replicas=5 -n production

# Restart
kubectl rollout restart deployment/mariadb -n production

# Rollback
kubectl rollout undo deployment/mariadb -n production
```

## Troubleshooting

### Pod Won't Start

```bash
# Check pod status
kubectl get pod mariadb-xxx -n production -o yaml

# Check events
kubectl get events -n production --sort-by='.lastTimestamp'

# Describe pod
kubectl describe pod mariadb-xxx -n production
```

**Common issues**:
- Image pull errors
- Insufficient resources
- PVC binding issues
- Config/secret not found

### CrashLoopBackOff

```bash
# Check logs
kubectl logs mariadb-xxx -n production --previous

# Check liveness/readiness probes
kubectl describe pod mariadb-xxx -n production | grep -A 5 Liveness
```

### Networking Issues

```bash
# Test from another pod
kubectl run -it --rm debug --image=busybox --restart=Never -- sh
# Inside pod:
nslookup mariadb.production.svc.cluster.local
telnet mariadb 3306

# Check service endpoints
kubectl get endpoints mariadb -n production
```

### Storage Issues

```bash
# Check PVC status
kubectl get pvc -n production

# Describe PVC
kubectl describe pvc mariadb-data -n production

# Check PV
kubectl get pv
```

## Backup and Restore

### Using Velero

```bash
# Install Velero
velero install --provider aws --bucket backups \
  --secret-file ./credentials-velero

# Backup namespace
velero backup create production-backup --include-namespaces production

# Restore
velero restore create --from-backup production-backup
```

### Manual Backup

```bash
# Database dump
kubectl exec mariadb-xxx -n production -- \
  mysqldump -u root -p"${MARIADB_ROOT_PASSWORD}" \
  --all-databases > backup.sql

# PVC snapshot (if storage class supports)
kubectl create -f - <<EOF
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: mariadb-snapshot
  namespace: production
spec:
  source:
    persistentVolumeClaimName: mariadb-data
EOF
```

## Monitoring

### Prometheus + Grafana

```yaml
# ServiceMonitor for Prometheus Operator
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: mariadb
  namespace: production
spec:
  selector:
    matchLabels:
      app: mariadb
  endpoints:
  - port: metrics
    interval: 30s
```

### Metrics Server

```bash
# Install metrics server
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# View metrics
kubectl top nodes
kubectl top pods -n production
```

## Security

### Pod Security Standards

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

### Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mariadb-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: mariadb
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: wordpress
    ports:
    - protocol: TCP
      port: 3306
  egress:
  - to:
    - podSelector: {}
    ports:
    - protocol: TCP
      port: 53  # DNS
```

### RBAC

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: mariadb
  namespace: production
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: mariadb
  namespace: production
rules:
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: mariadb
  namespace: production
subjects:
- kind: ServiceAccount
  name: mariadb
roleRef:
  kind: Role
  name: mariadb
  apiGroup: rbac.authorization.k8s.io
```

## CI/CD Integration

### GitOps with ArgoCD

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: mariadb
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/yourorg/manifests
    targetRevision: HEAD
    path: production/mariadb
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

## Migration

### From Docker Compose

```bash
# Use Kompose
kompose convert -f docker-compose.yml

# Deploy generated manifests
kubectl apply -f .
```

### From VMs

1. Containerize application
2. Create Kubernetes manifests
3. Deploy to dev/staging
4. Test thoroughly
5. Deploy to production
6. Update DNS/load balancer

## Next Steps

- [Bare-Metal Systemd Deployment](deployment-baremetal.md)
- [Creating Services](creating-services.md)
- [Service Contracts](service-contracts.md)