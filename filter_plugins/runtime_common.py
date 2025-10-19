"""Shared filter helpers for runtime template rendering."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from ansible.errors import AnsibleFilterError

from .health import get_health_command


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _unique(items: Iterable[Any]) -> List[Any]:
    seen = set()
    result: List[Any] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def ensure_env_entries(value: Any, *, context: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if value is None:
        return entries
    if isinstance(value, Mapping):
        for name, val in value.items():
            entries.append({"name": name, "value": val})
        return entries
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            if not isinstance(item, Mapping):
                raise AnsibleFilterError(
                    f"{context} entries must be dictionaries with 'name' and 'value' keys"
                )
            if "name" not in item:
                raise AnsibleFilterError(
                    f"{context} entry {item!r} is missing the required 'name' key"
                )
            entries.append(
                {
                    "name": item["name"],
                    "value": item.get("value"),
                }
            )
        return entries
    raise AnsibleFilterError(
        f"{context} must be a sequence or mapping, received {type(value).__name__}"
    )


def normalize_security(security: Any | None) -> Dict[str, Any]:
    src: Mapping[str, Any] = security or {}
    drop_caps = src.get("capabilities_drop", ["ALL"])
    drop_caps_list = _as_list(drop_caps)
    bounding_set = _as_list(src.get("capability_bounding_set", []))
    allowed_apparmor = _as_list(
        src.get("allowed_apparmor_profiles", ["docker-default", "unconfined"])
    )

    run_user = src.get("run_as_user", 65532)
    run_group = src.get("run_as_group", run_user)

    defaults = {
        "run_user": run_user,
        "run_group": run_group,
        "read_only_root": src.get("read_only_root_filesystem", True),
        "capabilities_drop": drop_caps_list,
        "no_new_privileges": src.get("no_new_privileges", True),
        "allow_privilege_escalation": src.get(
            "allow_privilege_escalation",
            not src.get("no_new_privileges", True),
        ),
        "apparmor_profile": src.get("apparmor_profile", "docker-default"),
        "allowed_apparmor_profiles": allowed_apparmor,
        "compose_user": src.get("user"),
        "capability_bounding_set": bounding_set,
        "user_namespace": src.get("user_namespace"),
        "init": src.get("init"),
    }
    return defaults


def _normalise_secret_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    secret_type = item.get("type") or item.get("kind")
    if secret_type is None:
        if "target" in item or "mode" in item or "content" in item:
            secret_type = "file"
        else:
            secret_type = "env"

    secret_type = str(secret_type).lower()
    if secret_type not in {"env", "file"}:
        raise AnsibleFilterError(f"Unsupported secret type {secret_type!r}")

    name = item.get("name")
    if not name:
        raise AnsibleFilterError("Secret entries must define a non-empty name")

    base: Dict[str, Any] = {
        "name": str(name),
        "type": secret_type,
    }

    if secret_type == "env":
        base["value"] = item.get("value")
    else:
        base["target"] = item.get("target")
        base["mode"] = item.get("mode")
        base["content"] = item.get("content", item.get("value"))
    return base


def normalize_secrets(secrets: Any | None) -> Dict[str, Any]:
    if secrets is None:
        secrets = {}

    if isinstance(secrets, Mapping):
        source = secrets
    else:
        # Support attribute access objects by copying attrs into a dict.
        source = {k: getattr(secrets, k) for k in dir(secrets) if not k.startswith("_")}

    items: List[Dict[str, Any]] = []

    def add_env(entry: Mapping[str, Any]) -> None:
        normalized = _normalise_secret_item({"type": "env", **entry})
        if normalized["name"] not in env_names:
            env_items.append(normalized)
            env_names.add(normalized["name"])
            items.append(normalized)

    def add_file(entry: Mapping[str, Any]) -> None:
        normalized = _normalise_secret_item({"type": "file", **entry})
        if normalized["name"] not in file_names:
            file_items.append(normalized)
            file_names.add(normalized["name"])
            items.append(normalized)

    env_items: List[Dict[str, Any]] = []
    env_names: set[str] = set()
    file_items: List[Dict[str, Any]] = []
    file_names: set[str] = set()

    for entry in source.get("items", []) or []:
        normalized = _normalise_secret_item(entry)
        if normalized["type"] == "env":
            add_env(normalized)
        else:
            add_file(normalized)

    for entry in source.get("env", []) or []:
        add_env(entry)

    for entry in source.get("files", []) or []:
        add_file(entry)

    rotation = source.get("rotation_timestamp")
    shred = source.get("shred_after_apply", True)

    return {
        "items": items,
        "env": env_items,
        "files": file_items,
        "catalog": {
            "env_names": sorted(env_names),
            "file_names": sorted(file_names),
        },
        "rotation_timestamp": rotation,
        "shred_after_apply": bool(shred),
    }


def secrets_env_map(secret_context: Mapping[str, Any]) -> Dict[str, Any]:
    env_items = secret_context.get("env", []) if secret_context else []
    mapping: Dict[str, Any] = {}
    for item in env_items:
        name = item.get("name")
        if name and name not in mapping:
            mapping[name] = item.get("value")
    return mapping


def normalize_mounts(mounts: Any | None) -> Dict[str, Any]:
    src: Mapping[str, Any] = mounts or {}
    ephemeral_raw = src.get("ephemeral_mounts") or []
    normalized: List[Dict[str, Any]] = []

    for entry in ephemeral_raw:
        if not isinstance(entry, Mapping):
            raise AnsibleFilterError("ephemeral_mounts entries must be mappings")
        name = entry.get("name") or f"ephemeral-{len(normalized) + 1}"
        path = entry.get("path")
        if not path:
            raise AnsibleFilterError(f"ephemeral mount {name!r} must define a path")
        runtimes = entry.get("runtimes") or entry.get("apply_to") or []
        normalized.append(
            {
                "name": str(name),
                "path": str(path),
                "medium": entry.get("medium"),
                "size": entry.get("size"),
                "mode": entry.get("mode"),
                "read_only": bool(entry.get("read_only", False)),
                "runtimes": list(runtimes) if runtimes else [],
            }
        )

    return {"ephemeral": normalized}


def select_ephemeral_mounts(
    mounts: Any, runtime: str | None = None
) -> List[Dict[str, Any]]:
    candidates = mounts or []
    if runtime is None:
        return list(candidates)

    selected: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()
    for entry in candidates:
        runtimes = entry.get("runtimes", [])
        if runtimes and runtime not in runtimes:
            continue
        path = entry.get("path")
        if path in seen_paths:
            continue
        seen_paths.add(path)
        selected.append(entry)
    return selected


def compose_environment(
    inline_env: Any,
    secret_env: Sequence[Mapping[str, Any]],
    *,
    rotation_timestamp: Optional[str],
    service_name: Optional[str],
    primary_service_name: Optional[str],
    connections_per_second: Optional[Any],
) -> List[Dict[str, Any]]:
    inline_entries = ensure_env_entries(inline_env, context="environment")
    environment: List[Dict[str, Any]] = []
    names: set[str] = set()

    def add_entry(name: str, value: Any) -> None:
        if name in names:
            return
        environment.append({"name": name, "value": value})
        names.add(name)

    for entry in inline_entries:
        add_entry(entry["name"], entry.get("value"))

    if connections_per_second is not None and service_name == primary_service_name:
        add_entry("CONNECTIONS_PER_SECOND", str(connections_per_second))

    if rotation_timestamp is not None:
        add_entry("SHMA_SECRETS_ROTATION", rotation_timestamp)

    for entry in secret_env:
        name = entry.get("name")
        if not name:
            continue
        add_entry(name, f"${{{name}}}")

    return environment


def merge_inline_environment(
    inline_env: Any,
    *,
    rotation_timestamp: Optional[str],
    connections_per_second: Optional[Any],
    service_name: Optional[str],
    primary_service_name: Optional[str],
) -> List[Dict[str, Any]]:
    inline_entries = ensure_env_entries(inline_env, context="environment")
    merged: List[Dict[str, Any]] = []
    names: set[str] = set()

    def add_entry(name: str, value: Any) -> None:
        if name in names:
            return
        merged.append({"name": name, "value": value})
        names.add(name)

    for entry in inline_entries:
        add_entry(entry["name"], entry.get("value"))

    if connections_per_second is not None and service_name == primary_service_name:
        add_entry("CONNECTIONS_PER_SECOND", str(connections_per_second))

    if rotation_timestamp is not None:
        add_entry("SHMA_SECRETS_ROTATION", rotation_timestamp)

    return merged


def health_spec(health: Any | None) -> Dict[str, Any]:
    command = get_health_command(health)
    src: Mapping[str, Any] = health or {}
    spec = {
        "command": command,
        "interval": src.get("interval", "10s"),
        "timeout": src.get("timeout", "5s"),
        "retries": src.get("retries", 3),
    }
    if isinstance(src, Mapping) and src.get("start_period") is not None:
        spec["start_period"] = src.get("start_period")
    return spec


class FilterModule:
    def filters(self) -> Dict[str, Any]:
        return {
            "as_list": _as_list,
            "unique": _unique,
            "ensure_env_entries": ensure_env_entries,
            "normalize_security": normalize_security,
            "normalize_secrets": normalize_secrets,
            "secrets_env_map": secrets_env_map,
            "normalize_mounts": normalize_mounts,
            "select_ephemeral_mounts": select_ephemeral_mounts,
            "compose_environment": compose_environment,
            "merge_inline_environment": merge_inline_environment,
            "health_spec": health_spec,
        }
