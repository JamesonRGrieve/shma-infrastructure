"""Custom filters for building OPNsense edge payloads."""

from __future__ import annotations

from typing import Iterable, List, Mapping, MutableMapping, Sequence

from ansible.errors import AnsibleFilterError


def _ensure_mapping(
    value: Mapping[str, object] | None, name: str
) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AnsibleFilterError(f"{name} must be a mapping, got {type(value)!r}")
    return value


def _as_listener_entries(binds: Iterable[Mapping[str, object]] | None) -> List[str]:
    listeners: List[str] = []
    for bind in binds or []:
        address = str(bind.get("address", ""))
        port = str(bind.get("port", ""))
        if not address or not port:
            continue
        listener = f"{address}:{port}"
        if listener not in listeners:
            listeners.append(listener)
    return listeners


def opnsense_caddy_configuration(
    backends: Sequence[Mapping[str, object]] | None,
    binds: Sequence[Mapping[str, object]] | None = None,
) -> Mapping[str, object]:
    """Build the Caddy configuration payload for OPNsense.

    Args:
        backends: Sequence of ingress backend dictionaries.
        binds: Bind definitions including address/port/tls flags.

    Returns:
        Mapping matching the JSON payload expected by the OPNsense Caddy API.
    """

    listeners = _as_listener_entries(binds)
    routes: List[MutableMapping[str, object]] = []
    tls_policies: List[Mapping[str, object]] = []

    for backend in backends or []:
        exports = _ensure_mapping(backend.get("exports"), "backend['exports']")
        host = exports.get("APP_FQDN")
        backend_ip = exports.get("APP_BACKEND_IP")
        backend_port = exports.get("APP_PORT")
        if not all([host, backend_ip, backend_port]):
            raise AnsibleFilterError(
                "edge ingress backends must define exports.APP_FQDN, APP_BACKEND_IP, and APP_PORT"
            )

        match_block: MutableMapping[str, object] = {"host": [host]}
        path_prefix = backend.get("path_prefix")
        if path_prefix and path_prefix not in {"", "/"}:
            match_block["path"] = [path_prefix]

        route: MutableMapping[str, object] = {
            "match": [match_block],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [
                        {
                            "dial": f"{backend_ip}:{backend_port}",
                        }
                    ],
                }
            ],
            "terminal": True,
        }
        routes.append(route)

        if backend.get("tls"):
            policy = {"match": {"sni": [host]}}
            if policy not in tls_policies:
                tls_policies.append(policy)

    return {
        "apps": {
            "http": {
                "servers": {
                    "ingress": {
                        "listen": listeners,
                        "routes": routes,
                        "tls_connection_policies": tls_policies,
                    }
                }
            }
        }
    }


def opnsense_nginx_payloads(
    backends: Sequence[Mapping[str, object]] | None,
    binds: Sequence[Mapping[str, object]] | None = None,
    certificate_id: str | None = None,
) -> Mapping[str, Sequence[Mapping[str, object]]]:
    """Build upstream and server payloads for the OPNsense Nginx API."""

    listener_http: List[Mapping[str, object]] = []
    listener_https: List[Mapping[str, object]] = []
    for bind in binds or []:
        address = str(bind.get("address", ""))
        port = str(bind.get("port", ""))
        if not address or not port:
            continue
        target = {"address": address, "port": port}
        if bind.get("tls"):
            listener_https.append(target)
        else:
            listener_http.append(target)

    upstreams: List[Mapping[str, object]] = []
    servers: List[Mapping[str, object]] = []

    for backend in backends or []:
        exports = _ensure_mapping(backend.get("exports"), "backend['exports']")
        host = exports.get("APP_FQDN")
        backend_ip = exports.get("APP_BACKEND_IP")
        backend_port = exports.get("APP_PORT")
        service_id = backend.get("service_id")
        router_name = backend.get("router_name")
        scheme = backend.get("scheme")
        if not all([host, backend_ip, backend_port, service_id, router_name, scheme]):
            raise AnsibleFilterError(
                "edge ingress backends must define service_id, router_name, scheme, and exports.APP_* values"
            )

        path_prefix = backend.get("path_prefix") or "/"
        websocket_enabled = "websocket" in (backend.get("middlewares") or [])

        upstreams.append(
            {
                "name": service_id,
                "description": router_name,
                "server": backend_ip,
                "port": backend_port,
                "protocol": scheme,
                "health_check_path": path_prefix if path_prefix != "/" else "/",
                "websocket": websocket_enabled,
            }
        )

        server_payload: MutableMapping[str, object] = {
            "server_name": host,
            "locations": [
                {
                    "path": path_prefix if path_prefix != "/" else "/",
                    "upstream": service_id,
                    "preserve_host": backend.get("preserve_host", False),
                    "websocket": websocket_enabled,
                }
            ],
            "listen_http": bool(listener_http),
            "listen_https": bool(listener_https),
            "http_bind": listener_http,
            "https_bind": listener_https,
        }

        if backend.get("tls") and certificate_id:
            server_payload["certificate_id"] = certificate_id

        servers.append(server_payload)

    return {"upstreams": upstreams, "servers": servers}


class FilterModule:
    """Expose OPNsense helper filters."""

    def filters(self):
        return {
            "opnsense_caddy_configuration": opnsense_caddy_configuration,
            "opnsense_nginx_payloads": opnsense_nginx_payloads,
        }
