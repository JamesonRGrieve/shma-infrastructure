# Backup strategy

Persistent data is declared in each service contract through `mounts.persistent_volumes`.
Every runtime adapter exposes those directories on the host so they can be backed
up without reverse-engineering container layouts. This guide shows how to locate
those paths per runtime and how to couple them with a Restic-based backup
pipeline.

## Core principles

1. **Back up the host paths, not container paths.** The adapters bind the
   declared volumes into the workload. Use the host-side source when scheduling
   backups.
2. **Leverage `service_volumes` for bind mounts.** Host paths declared under
   `service_volumes` align with the persistent volume list; keep them in sync so
   the documentation doubles as a recovery plan.
3. **Record retention and prune policies.** Restic handles deduplication and
   pruning, but it still needs explicit `forget --prune` policies. Bake them into
   timers or CI pipelines.

## Runtime-specific guidance

### Docker Compose

- Host bind mounts: defined directly in `service_volumes`. Back up the host paths
  (for example `/srv/<service>/config`).
- Named volumes: when `service_volumes` is omitted, Compose falls back to
  managed volumes under `/var/lib/docker/volumes/<volume>/_data`. Use `docker
  volume inspect` to confirm the path before scheduling backups.
- Example Restic invocation:

  ```bash
  RESTIC_REPOSITORY=s3:https://s3.example.com/infrastructure \
  RESTIC_PASSWORD_FILE=/etc/restic/password \
  restic backup /srv/sample-service/config
  ```

### Podman Quadlet

- Quadlet binds the same `service_volumes` entries under `/srv` (or the host path
  you declare). Back them up directly.
- Named volumes live under `/var/lib/containers/storage/volumes/<volume>/_data`.
  Use `podman volume inspect` to retrieve the path before calling Restic.
- Example systemd timer excerpt using Restic:

  ```ini
  [Unit]
  Description=Restic backup for sample-service

  [Service]
  Type=oneshot
  Environment=RESTIC_REPOSITORY=s3:https://s3.example.com/infrastructure
  Environment=RESTIC_PASSWORD_FILE=/etc/restic/password
  ExecStart=/usr/local/bin/restic backup /srv/sample-service/config

  [Install]
  WantedBy=timers.target
  ```

### Kubernetes

- Persistent data is expressed via `PersistentVolumeClaim`s sized from
  `service_storage_gb` or `service_storage_size`. When `service_volumes.host_path`
  is present the adapters wire the node path directly.
- Backup options:
  - Use a CSI snapshot/restore workflow if the storage class supports it.
  - Pair the cluster with [Velero](https://velero.io/) and enable its Restic
    integration for file-level backups of each PVC.
  - For hostPath mounts, schedule Restic on the node to back up the declared
    directories.
- Example Restic DaemonSet snippet targeting hostPath-backed workloads:

  ```yaml
  apiVersion: apps/v1
  kind: DaemonSet
  metadata:
    name: restic-backup
  spec:
    template:
      spec:
        serviceAccountName: restic
        containers:
          - name: restic
            image: ghcr.io/restic/restic:0.16.4
            envFrom:
              - secretRef:
                  name: restic-credentials
            volumeMounts:
              - name: data
                mountPath: /data
            command: ["/bin/sh","-c","restic backup /data"]
        volumes:
          - name: data
            hostPath:
              path: /srv/sample-service/config
  ```

### Proxmox LXC

- LXC containers can mount directories from the Proxmox host when `service_volumes`
  is populated. Back up the host directories or use `vzdump` snapshots for
  container-level protection.
- Combine `vzdump` with Restic by exporting the resulting tarballs:

  ```bash
  vzdump 105 --dumpdir /var/backups/lxc
  RESTIC_REPOSITORY=rest:http://backup-gateway:8000/infra restic backup /var/backups/lxc
  ```

### Bare-metal systemd

- Bare-metal adapters create directories listed in `mounts.persistent_volumes`
  directly on the target host. Schedule Restic timers targeting those paths.
- Example Ansible snippet that renders a shared timer for all services:

  ```yaml
  - name: Configure Restic backups
    include_role:
      name: restic
    vars:
      restic_backup_paths: "{{ mounts.persistent_volumes | map(attribute='path') | list }}"
  ```

## Restic integration checklist

1. Create a `restic` user or systemd service account with access to every
   persistent path.
2. Store credentials (`RESTIC_PASSWORD`, repository credentials) in Ansible
   vaults or secret stores; surface them as environment files during runtime.
3. Schedule both `restic backup` and `restic forget --prune` operations. Use
   timers on bare metal/Quadlet hosts or Kubernetes CronJobs.
4. Regularly run `restic check` to detect repository corruption early.
5. Document restore commands alongside each service so on-call engineers can
   rehearse recovery without trawling through inventories.

The combination of declarative volume metadata and Restic automation keeps data
portable across runtimes and simplifies disaster recovery drills.
