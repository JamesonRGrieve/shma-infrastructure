# Troubleshooting guide

Use this checklist when a deployment fails. Each section outlines common
symptoms, commands to confirm the root cause, and remediation guidance.

## Secret validation failures

**Symptoms**
- `ci/validate_schema.py` or `edge_ingress` tasks report missing secret keys.
- `ansible-playbook` aborts with `Undefined variable` when templating
  `secrets.env` or `secrets.files` entries.

**Debugging steps**
- Run `ansible-playbook tests/render.yml -e service_definition_file=<file>` to
  reproduce the render locally with verbose output.
- Inspect `secrets.env` and `secrets.files` arrays; confirm every item contains a
  `name` and `value` (and `target` for file entries).
- Verify inventory group_vars define each templated secret or that the CI
  environment injects them via `ANSIBLE_VAULT_PASSWORD_FILE`.

**Fix**
- Add missing variables to the inventory or vault.
- Set `secrets.shred_after_apply: false` temporarily (and document
  `secrets.shred_waiver_reason`) to inspect rendered secret files under
  `/tmp/ansible-runtime/<service>/`.

## Image pull errors

**Symptoms**
- Runtime adapters fail with `image pull` errors.
- CI logs show `manifest unknown` or authentication failures from registries.

**Debugging steps**
- Confirm the image digest in `service_image` exists (`skopeo inspect` or `podman
  pull`).
- Ensure the runtime host has credentials for private registries. Compose and
  Quadlet read from `~/.docker/config.json`; Kubernetes uses image pull secrets.
- For Proxmox LXC, verify the template is mirrored locally or accessible through
  `pveam`.

**Fix**
- Promote new image digests intentionally and update `service_image`.
- Sync credential helpers or Kubernetes secrets before rerunning the playbook.

## Dependency resolution loops

**Symptoms**
- `edge_ingress` or service-specific roles hang while waiting for dependencies to
  appear.
- Logs show repeated attempts to resolve `dependency_exports` entries.

**Debugging steps**
- Check `requires` in the service definition; ensure every dependency is listed
  in the registry consumed by `dependency_exports`.
- Use `ansible-inventory --graph` to confirm the dependency service is assigned
  to a host and rendered successfully.
- Inspect the exported `.env` files to confirm they contain the expected keys
  (`APP_FQDN`, `APP_PORT`, `APP_BACKEND_IP`).

**Fix**
- Add missing dependencies to the registry file.
- Re-run the upstream service deployment before rerunning the dependent one.

## Health check timeouts

**Symptoms**
- CI or post-deploy hooks fail with `health check timed out`.
- Kubernetes readiness probes stay in a failing state; Compose reports unhealthy
  containers.

**Debugging steps**
- Verify `health.cmd` is executable inside the container or host.
- Run the command manually (`docker compose exec <service> /bin/sh -c ...`).
- Confirm the service listens on the port declared in `APP_PORT` and that TLS
  expectations match (`scheme` vs actual protocol).
- Inspect runtime logs for startup failures (systemd `journalctl`, Kubernetes
  `kubectl logs`).

**Fix**
- Adjust the health command to wait for application boot (add retries or
  `sleep`).
- Ensure the service exposes the declared port and scheme.
- Increase health timeout thresholds per runtime when necessary (for example
  `health.timeout` in Compose or `failureThreshold` in Kubernetes).

Documenting the investigation keeps on-call engineers aligned across runtimes.
Pair this guide with the backup strategy to build a full remediation playbook.
