# Network Edge Automation

The `edge_*` roles extend the shared service contract to firewalls, routers, and
stand-alone reverse proxies. Services publish an *ingress contract* through
`exports.env` so edge devices can discover backends without bespoke wiring.

## Ingress contract

Every service that needs external exposure should add the following keys to its
`exports.env` payload:

- `APP_FQDN` – the fully-qualified domain clients should use.
- `APP_PORT` – the internal port exposed by the workload.
- `APP_BACKEND_IP` – the address (usually the service IP provided by the
  runtime adapter) clients should reach.

Additional metadata (for example `APP_PATH_PREFIX`) can be layered on per
service, but the three keys above are required for the stock roles. The
`edge_ingress` role consolidates those exports into `edge_ingress_backends`, a
normalised structure consumed by the runtime-specific edge roles.

Example inventory snippet combining dependency exports with additional metadata:

```yaml
vars:
  dependency_exports:
    auth-service:
      APP_FQDN: auth.internal.example
      APP_PORT: "8443"
      APP_BACKEND_IP: 10.10.12.8
  edge_ingress_contracts:
    - service_id: auth-service
      exports: "{{ dependency_exports['auth-service'] }}"
      tls: true
      tls_certresolver: production
      path_prefix: /
```

When services publish `exports.env` on disk instead of directly through
`dependency_exports`, the contract can be pointed at the rendered file by
setting `exports_env_path`. The role reads the file on the target host, parses
it, and merges it into the consolidated backend map.

## Roles

### `edge_ingress`

Normalises the ingress contract for all downstream roles. It validates the
required keys, applies defaults (HTTP scheme, `/` path prefix, and the `web`
Traefik entrypoint), and exposes a structured `edge_ingress_backends` variable.

### `edge_proxy_traefik`

Renders a file-provider configuration at `/etc/traefik/dynamic/ingress.yml`. The
configuration builds one router and service per backend and honours TLS and
middleware hints from the contract. Reloads are issued via `systemctl reload
traefik` by default.

### `edge_proxy_haproxy`

Produces an HAProxy configuration that binds to HTTP and (optionally) HTTPS
frontends and wires host/path ACLs to the generated backends. Health checks are
issued using the path prefix (or `/` by default). The generated configuration is
suitable for a dedicated HAProxy host or FreeBSD-based appliances that honour
`/usr/local/etc/haproxy/ingress.cfg`.

### `edge_opnsense`

Pushes the normalised ingress contract into an OPNsense HAProxy instance via the
`/api/haproxy/service/bulkImport` API endpoint. Each backend becomes a HAProxy
“backend” with an HTTP health check and a single server definition derived from
the contract. Frontends are generated for every declared backend and reuse the
inventory-provided bind addresses. When `opnsense_apply_changes` is `true`
(default) the role calls `/api/haproxy/service/reconfigure` to activate the new
configuration.

### `edge_pfsense`

Targets pfSense installations that expose the `/api/v1/services/haproxy/*` API.
Backends and frontends mirror the OPNsense semantics: backends define one
server per workload with HTTP health checks, and frontends bind to the declared
listen addresses with host/path matchers. A follow-up call to
`/api/v1/services/haproxy/apply` commits the change when
`pfsense_apply_changes` is enabled.

## Security considerations

- API credentials (`opnsense_api_key`/`opnsense_api_secret` and
  `pfsense_api_token`) must be scoped to the HAProxy subsystem. Avoid granting
  general configuration access when issuing tokens.
- TLS termination defaults to disabled; the ingress contract can toggle TLS on a
  per-service basis and provide certificate identifiers. OPNsense and pfSense
  both allow referencing existing certificate stores without embedding secrets
  in playbooks.
- Always pair edge automation with digest-pinned upstream services. The
  generated backends reference the runtime-assigned IP address, so drift in the
  upstream deployment is immediately reflected at the edge once new manifests
  are applied.

## Workflow summary

1. Application repository exports ingress metadata (FQDN, port, backend IP).
2. The infrastructure inventory feeds those exports into `edge_ingress`.
3. Choose an edge adapter (`edge_proxy_traefik`, `edge_proxy_haproxy`,
   `edge_opnsense`, or `edge_pfsense`) depending on the environment.
4. Apply the playbook; the adapter renders configuration and reloads or
   reconfigures the edge proxy automatically.

This closes the gap between the runtime adapters and the network edge while
keeping the ingress contract declarative and portable.
