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

Keep the exports file limited to connection metadata—never embed application
secrets. The role reads the file with `no_log` enabled so ingress automation
does not leak sensitive values into Ansible output.

Additional metadata (for example `APP_PATH_PREFIX`) can be layered on per
service, but the three keys above are required for the stock roles. The
`edge_ingress` role consolidates those exports into `edge_ingress_backends`, a
normalised structure consumed by the runtime-specific edge roles.

### `exports.env` examples

Common services can share a predictable layout so adapters stay generic. These
snippets show how the contract looks for two workloads:

```dotenv
# redis/exports.env
APP_FQDN=redis.internal.example
APP_PORT=6379
APP_BACKEND_IP=10.10.15.23
```

```dotenv
# erpnext/exports.env
APP_FQDN=erp.internal.example
APP_PORT=8080
APP_BACKEND_IP=10.10.19.41
APP_PATH_PREFIX=/desk
```

The same pattern applies to every service—no runtime-specific wiring is
required.

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
validated with `haproxy -c -f` before the service reloads, ensuring syntax
errors never reach production. The handler then reloads HAProxy using the
configured command.

### `edge_opnsense`

Pushes the normalised ingress contract into an OPNsense HAProxy instance via the
`/api/haproxy/service/bulkImport` API endpoint. Each backend becomes a HAProxy
“backend” with an HTTP health check and a single server definition derived from
the contract. Frontends are generated for every declared backend and reuse the
inventory-provided bind addresses. When `opnsense_apply_changes` is `true`
(default) the role calls `/api/haproxy/service/reconfigure` to activate the new
configuration.

### `edge_opnsense_nginx`

Configures the OPNsense Nginx plugin using the same ingress model. Upstreams map
directly to backend services and Nginx server blocks bind to the declared edge
addresses. TLS certificate identifiers can be supplied via
`opnsense_nginx_tls_certificate_id`. The role pushes the configuration through
`/api/nginx/service/bulkImport` and optionally reconfigures Nginx when
`opnsense_nginx_apply_changes` is true (default).

### `edge_opnsense_caddy`

Generates a Caddy HTTP application payload from the ingress contract. Listener
bindings follow `opnsense_ingress_bind_addresses` and each route becomes a
reverse-proxy handle that targets the exported backend dial address. TLS SNI
policies are emitted automatically when the contract references pre-provisioned
secrets. Configuration is sent to `/api/caddy/service/bulkImport` and activated
when `opnsense_caddy_apply_changes` is true (default).

### `edge_pfsense`

Targets pfSense installations that expose the `/api/v1/services/haproxy/*` API.
Backends and frontends mirror the OPNsense semantics: backends define one
server per workload with HTTP health checks, and frontends bind to the declared
listen addresses with host/path matchers. A follow-up call to
`/api/v1/services/haproxy/apply` commits the change when
`pfsense_apply_changes` is enabled (default).

### `edge_pfsense_squid`

Drives the pfSense Squid reverse-proxy API to publish backend services without
manual configuration drift. Each ingress backend becomes a Squid origin peer and
an associated reverse-proxy mapping keyed by FQDN and path prefix. The
configuration posts to `/api/v1/services/squid/reverse_proxy` and applies with
the standard `/api/v1/services/squid/apply` endpoint when
`pfsense_squid_apply_changes` is true (default).

### `edge_proxy_traefik`

Renders a file-provider configuration at `/etc/traefik/dynamic/ingress.yml`. The
configuration builds one router and service per backend and honours TLS and
middleware hints from the contract. Reloads are issued via `systemctl reload
traefik` by default and are now preceded by `traefik --validate=true` to catch
syntax errors before the service restarts.

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
