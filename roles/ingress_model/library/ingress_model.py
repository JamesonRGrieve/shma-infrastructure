from __future__ import annotations

import hashlib
import json
import ssl
from pathlib import Path
from typing import Any, Dict, List

import yaml
from ansible.module_utils.basic import AnsibleModule
from jsonschema import Draft202012Validator


def load_schema(schema_path: Path) -> dict:
    try:
        return yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Ingress schema not found at {schema_path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Invalid ingress schema YAML at {schema_path}: {exc}"
        ) from exc


def normalize_health(health: dict | None) -> dict:
    base = {
        "path": "/",
        "interval": "30s",
        "timeout": "5s",
    }
    if not health:
        return base

    normalized = base.copy()
    for key in ("path", "interval", "timeout", "method", "expected_status"):
        if key in health and health[key] is not None:
            normalized[key] = health[key]
    return normalized


def normalize_tls(tls: dict | None) -> dict:
    base = {
        "mode": "auto",
        "hsts": True,
        "alpn": ["h2", "http/1.1"],
        "redirect_http_to_https": True,
    }
    if tls is None:
        return base

    normalized = base.copy()

    for key in ("mode", "hsts", "alpn", "redirect_http_to_https"):
        if key in tls and tls[key] is not None:
            normalized[key] = tls[key]

    acme_defaults = {
        "challenge": "dns",
        "wildcard": False,
    }
    acme = tls.get("acme")
    if acme is not None:
        acme_normalized = acme_defaults.copy()
        for key, value in acme.items():
            if value is not None:
                acme_normalized[key] = value
        normalized["acme"] = acme_normalized

    for optional in ("certificate_secret", "key_secret", "chain_secret"):
        if optional in tls and tls[optional] is not None:
            normalized[optional] = tls[optional]

    return normalized


def normalize_headers(headers: dict | None) -> dict:
    if not headers:
        return {"set": [], "remove": []}

    normalized = {
        "set": headers.get("set", []) or [],
        "remove": headers.get("remove", []) or [],
    }
    return normalized


def normalize_rate_limit(rate_limit: dict | None) -> dict:
    if not rate_limit:
        return {}

    normalized: dict[str, Any] = {}
    if (
        "requests_per_minute" in rate_limit
        and rate_limit["requests_per_minute"] is not None
    ):
        normalized["requests_per_minute"] = rate_limit["requests_per_minute"]
    if "burst" in rate_limit and rate_limit["burst"] is not None:
        normalized["burst"] = rate_limit["burst"]
    return normalized


def normalize_route(route: dict) -> dict:
    normalized = {
        "host": route["host"],
        "port": route["port"],
        "path_prefix": route.get("path_prefix", "/") or "/",
        "websocket": bool(route.get("websocket", False)),
        "sticky": route.get("sticky", "none"),
        "allow_http": bool(route.get("allow_http", False)),
    }

    normalized["health"] = normalize_health(route.get("health"))
    normalized["tls"] = normalize_tls(route.get("tls"))
    normalized["headers"] = normalize_headers(route.get("headers"))
    rate_limit = normalize_rate_limit(route.get("rate_limit"))
    if rate_limit:
        normalized["rate_limit"] = rate_limit

    if "basic_auth" in route and route["basic_auth"]:
        normalized["basic_auth"] = route["basic_auth"]
    if "mtls" in route and route["mtls"]:
        normalized["mtls"] = route["mtls"]

    return normalized


def normalize_ingress(ingress: dict) -> dict:
    normalized_routes = [normalize_route(route) for route in ingress.get("routes", [])]
    return {
        "enabled": ingress.get("enabled", True),
        "routes": normalized_routes,
    }


def build_edge_config(
    service: dict, normalized: dict, metadata: dict[str, Any]
) -> List[Dict[str, Any]]:
    if not normalized.get("enabled", True):
        return []

    service_id = service.get("service_id", "service")
    primary_ip = service.get("service_ip")
    if not primary_ip:
        ports = service.get("service_ports", []) or []
        if ports:
            first_port = ports[0]
            primary_ip = first_port.get("host_ip")
    upstream_host = primary_ip or "127.0.0.1"

    edge_entries: List[Dict[str, Any]] = []
    for index, route in enumerate(normalized.get("routes", [])):
        port = route["port"]
        backend_name = f"{service_id}-{port}"
        upstream_address = f"{upstream_host}:{port}"
        upstream = {
            "name": backend_name,
            "host": upstream_host,
            "port": port,
            "address": upstream_address,
            "health": route.get("health", {}),
        }

        entry_metadata = metadata | {
            "route_index": index,
            "route_host": route["host"],
            "route_port": port,
        }

        edge_entry: Dict[str, Any] = {
            "hostname": route["host"],
            "path_prefix": route.get("path_prefix", "/"),
            "tls": route.get("tls", {}),
            "upstreams": [upstream],
            "websocket": route.get("websocket", False),
            "sticky": route.get("sticky", "none"),
            "headers": route.get("headers", {}),
            "metadata": entry_metadata,
            "allow_http": route.get("allow_http", False),
        }

        if "rate_limit" in route:
            edge_entry["rate_limit"] = route["rate_limit"]
        if "basic_auth" in route:
            edge_entry["basic_auth"] = route["basic_auth"]
        if "mtls" in route:
            edge_entry["mtls"] = route["mtls"]

        edge_entries.append(edge_entry)

    return edge_entries


def compute_metadata(
    managed_by: str, owner: str, service: dict, normalized: dict
) -> dict[str, Any]:
    spec_hash = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    metadata = {
        "managed_by": managed_by,
        "owner": owner,
        "service_id": service.get("service_id"),
        "spec_hash": spec_hash,
    }
    return metadata


def collect_secret_values(service: dict) -> dict[str, str]:
    secrets = service.get("secrets") or {}
    secret_values: dict[str, str] = {}

    for file_secret in secrets.get("files", []) or []:
        name = file_secret.get("name")
        if not name:
            continue
        value = file_secret.get("value")
        if value is None:
            value = file_secret.get("content")
        if value is None:
            continue
        secret_values[name] = str(value)

    for env_secret in secrets.get("env", []) or []:
        name = env_secret.get("name")
        if not name:
            continue
        value = env_secret.get("value")
        if value is None:
            continue
        secret_values[name] = str(value)

    return secret_values


def validate_pem_certificate(secret_name: str, pem_data: str) -> None:
    pem_text = pem_data.strip()
    if "BEGIN CERTIFICATE" not in pem_text:
        raise ValueError(
            f"Secret '{secret_name}' does not contain a PEM certificate block"
        )
    chunks = []
    for block in pem_text.split("-----END CERTIFICATE-----"):
        block = block.strip()
        if not block:
            continue
        if "-----BEGIN CERTIFICATE-----" not in block:
            continue
        chunks.append(block + "\n-----END CERTIFICATE-----\n")
    if not chunks:
        raise ValueError(
            f"Secret '{secret_name}' does not contain a PEM certificate block"
        )
    for cert in chunks:
        try:
            ssl.PEM_cert_to_DER_cert(cert)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"Secret '{secret_name}' contains an invalid PEM certificate"
            ) from exc


def validate_private_key(secret_name: str, key_data: str) -> None:
    key_text = key_data.strip()
    if "BEGIN" not in key_text or "PRIVATE KEY" not in key_text:
        raise ValueError(f"Secret '{secret_name}' does not contain a PEM private key")


def validate_tls_assets(service: dict, normalized: dict) -> None:
    secret_values = collect_secret_values(service)
    errors: list[str] = []

    for index, route in enumerate(normalized.get("routes", [])):
        host = route.get("host", f"route-{index}")
        tls = route.get("tls", {})
        if tls.get("mode") == "provided":
            for field, validator in (
                ("certificate_secret", validate_pem_certificate),
                ("key_secret", validate_private_key),
                ("chain_secret", validate_pem_certificate),
            ):
                secret_name = tls.get(field)
                if field in ("certificate_secret", "key_secret") and not secret_name:
                    errors.append(
                        f"Ingress route '{host}' requires '{field}' when tls.mode is 'provided'"
                    )
                    continue
                if not secret_name:
                    continue
                secret_value = secret_values.get(secret_name)
                if not secret_value:
                    errors.append(
                        f"Secret '{secret_name}' referenced by '{field}' for ingress route '{host}' was not found in service secrets"
                    )
                    continue
                try:
                    validator(secret_name, secret_value)
                except ValueError as exc:
                    errors.append(str(exc))

        mtls = route.get("mtls") or {}
        if mtls:
            ca_secret = mtls.get("ca_secret")
            if not ca_secret:
                errors.append(
                    f"Ingress route '{host}' defines mTLS but omits 'ca_secret'"
                )
            else:
                ca_value = secret_values.get(ca_secret)
                if not ca_value:
                    errors.append(
                        f"Secret '{ca_secret}' referenced by mTLS for ingress route '{host}' was not found in service secrets"
                    )
                else:
                    try:
                        validate_pem_certificate(ca_secret, ca_value)
                    except ValueError as exc:
                        errors.append(str(exc))

    if errors:
        raise ValueError("; ".join(errors))


def run_module() -> None:
    module = AnsibleModule(
        argument_spec={
            "service": {"type": "dict", "required": True},
            "schema_path": {"type": "path", "required": True},
            "managed_by": {"type": "str", "required": True},
            "owner": {"type": "str", "required": True},
        },
        supports_check_mode=True,
    )

    service: dict = module.params["service"] or {}
    ingress_spec = service.get("ingress")

    if not ingress_spec or not ingress_spec.get("enabled", True):
        module.exit_json(
            changed=False,
            ingress_enabled=False,
            normalized_ingress={},
            edge_config=[],
            metadata={},
        )

    schema_path = Path(module.params["schema_path"]).expanduser().resolve()
    try:
        schema = load_schema(schema_path)
    except ValueError as exc:
        module.fail_json(msg=str(exc))

    validator = Draft202012Validator(schema)
    try:
        validator.validate(ingress_spec)
    except Exception as exc:  # pragma: no cover - jsonschema gives detailed errors
        module.fail_json(msg=f"Ingress spec failed validation: {exc}")

    normalized = normalize_ingress(ingress_spec)
    try:
        validate_tls_assets(service, normalized)
    except ValueError as exc:
        module.fail_json(msg=str(exc))
    metadata = compute_metadata(
        module.params["managed_by"], module.params["owner"], service, normalized
    )
    edge_config = build_edge_config(service, normalized, metadata)

    module.exit_json(
        changed=False,
        ingress_enabled=True,
        normalized_ingress=normalized,
        edge_config=edge_config,
        metadata=metadata,
    )


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
