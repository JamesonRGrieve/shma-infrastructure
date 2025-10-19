"""Shared helpers for building HAProxy payloads across edge providers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from ansible.errors import AnsibleFilterError


def _ensure_mapping(
    value: Mapping[str, Any] | None, *, context: str
) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AnsibleFilterError(
            f"{context} must be a mapping, received {type(value)!r}"
        )
    return value


def _normalize_binds(binds: Iterable[Mapping[str, Any]] | None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for bind in binds or []:
        address = str(bind.get("address", ""))
        port = str(bind.get("port", ""))
        if not address or not port:
            continue
        entry = {
            "address": address,
            "port": port,
            "tls": bool(bind.get("tls")),
        }
        if entry not in normalized:
            normalized.append(entry)
    return normalized


def _normalize_backend(backend: Mapping[str, Any]) -> Dict[str, Any]:
    exports = _ensure_mapping(backend.get("exports"), context="backend['exports']")
    host = exports.get("APP_FQDN")
    backend_ip = exports.get("APP_BACKEND_IP")
    backend_port = exports.get("APP_PORT")
    service_id = backend.get("service_id")
    router_name = backend.get("router_name")
    scheme = backend.get("scheme", "http")

    required = {
        "APP_FQDN": host,
        "APP_BACKEND_IP": backend_ip,
        "APP_PORT": backend_port,
        "service_id": service_id,
        "router_name": router_name,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        joined = ", ".join(sorted(missing))
        raise AnsibleFilterError(
            f"edge ingress backends must define {joined} before building HAProxy payloads"
        )

    path_prefix = backend.get("path_prefix") or "/"
    middlewares = backend.get("middlewares") or []
    websocket_enabled = "websocket" in middlewares

    return {
        "service_id": str(service_id),
        "router_name": str(router_name),
        "host": str(host),
        "backend_ip": str(backend_ip),
        "backend_port": str(backend_port),
        "scheme": str(scheme or "http"),
        "path_prefix": str(path_prefix),
        "tls_enabled": bool(backend.get("tls")),
        "preserve_host": bool(backend.get("preserve_host", False)),
        "websocket": websocket_enabled,
    }


def haproxy_payloads(
    backends: Sequence[Mapping[str, Any]] | None,
    binds: Sequence[Mapping[str, Any]] | None = None,
    *,
    provider: str,
    certificate_ref: str | None = None,
) -> Dict[str, List[Mapping[str, Any]]]:
    """Build provider specific HAProxy payloads for edge devices."""

    provider_key = provider.lower().strip()
    if provider_key not in {"pfsense", "opnsense"}:
        raise AnsibleFilterError(
            f"Unsupported HAProxy payload provider {provider!r}. Expected 'pfsense' or 'opnsense'."
        )

    normalized_binds = _normalize_binds(binds)
    normalized_backends = [_normalize_backend(entry) for entry in backends or []]

    provider_backends: List[Mapping[str, Any]] = []
    provider_frontends: List[Mapping[str, Any]] = []

    for backend in normalized_backends:
        service_id = backend["service_id"]
        router_name = backend["router_name"]
        check_path = backend["path_prefix"] if backend["path_prefix"] != "/" else "/"

        if provider_key == "pfsense":
            provider_backends.append(
                {
                    "name": service_id,
                    "balance": "roundrobin",
                    "health_check_enabled": True,
                    "health_check_method": "GET",
                    "health_check_path": check_path,
                    "servers": [
                        {
                            "name": f"{service_id}-primary",
                            "address": backend["backend_ip"],
                            "port": backend["backend_port"],
                            "ssl": backend["scheme"].lower() == "https",
                        }
                    ],
                }
            )

            rules: List[MutableMapping[str, Any]] = [
                {"type": "host", "value": backend["host"]}
            ]
            if backend["path_prefix"] != "/":
                rules.append({"type": "path_beg", "value": backend["path_prefix"]})

            provider_frontends.append(
                {
                    "name": router_name,
                    "listen_addresses": [
                        {
                            "address": bind["address"],
                            "port": bind["port"],
                            "ssl": bind["tls"],
                        }
                        for bind in normalized_binds
                    ],
                    "rules": rules,
                    "default_backend": service_id,
                    "tls_enabled": backend["tls_enabled"],
                    "tls_certificate_ref": certificate_ref or "",
                }
            )
        else:  # opnsense
            provider_backends.append(
                {
                    "name": service_id,
                    "mode": "http",
                    "retries": 3,
                    "httpcheck_method": "GET",
                    "httpcheck_path": check_path,
                    "servers": [
                        {
                            "name": f"{service_id}-primary",
                            "address": backend["backend_ip"],
                            "port": backend["backend_port"],
                            "ssl": (
                                "true"
                                if backend["scheme"].lower() == "https"
                                else "false"
                            ),
                            "verify": "false",
                        }
                    ],
                }
            )

            rules: List[MutableMapping[str, Any]] = [
                {"type": "Host", "value": backend["host"]}
            ]
            if backend["path_prefix"] != "/":
                rules.append({"type": "PathPrefix", "value": backend["path_prefix"]})

            provider_frontends.append(
                {
                    "name": router_name,
                    "mode": "http",
                    "default_backend": service_id,
                    "rules": rules,
                    "binds": [
                        {
                            "address": bind["address"],
                            "port": bind["port"],
                            "ssl": "true" if bind["tls"] else "false",
                        }
                        for bind in normalized_binds
                    ],
                    "tls_enabled": "true" if backend["tls_enabled"] else "false",
                    "tls_certificate": certificate_ref or "",
                }
            )

    return {"backends": provider_backends, "frontends": provider_frontends}


class FilterModule:
    """Expose the shared HAProxy payload builders."""

    def filters(self) -> Dict[str, Any]:
        return {
            "haproxy_payloads": haproxy_payloads,
        }
