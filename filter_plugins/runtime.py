"""Runtime helpers shared across service templates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


DEFAULT_APPLY_TARGETS = [
    "docker",
    "podman",
    "kubernetes",
    "proxmox",
    "baremetal",
]


def _get_value(source: Any | None, key: str, default: Any) -> Any:
    if source is None:
        return default

    if isinstance(source, Mapping):
        return source.get(key, default)

    return getattr(source, key, default)


def _as_iterable(value: Any | None) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, Iterable):
        return list(value)

    return [value]


def normalize_security(service_security: Any | None) -> dict[str, Any]:
    run_user = int(_get_value(service_security, "run_as_user", 65532))
    run_group = int(_get_value(service_security, "run_as_group", run_user))
    read_only_root = bool(
        _get_value(service_security, "read_only_root_filesystem", True)
    )
    no_new_privs = bool(_get_value(service_security, "no_new_privileges", True))

    allow_priv = _get_value(service_security, "allow_privilege_escalation", None)
    if allow_priv is None:
        allow_priv = not no_new_privs
    else:
        allow_priv = bool(allow_priv)

    drop_caps = [
        str(cap)
        for cap in _as_iterable(
            _get_value(service_security, "capabilities_drop", ["ALL"])
        )
    ]
    compose_user = _get_value(service_security, "user", f"{run_user}:{run_group}")
    apparmor = _get_value(service_security, "apparmor_profile", "docker-default")
    bounding = [
        str(cap)
        for cap in _as_iterable(
            _get_value(service_security, "capability_bounding_set", [])
        )
    ]

    return {
        "run_as_user": run_user,
        "run_as_group": run_group,
        "read_only_root_filesystem": read_only_root,
        "allow_privilege_escalation": allow_priv,
        "no_new_privileges": no_new_privs,
        "capabilities_drop": drop_caps,
        "compose_user": compose_user,
        "apparmor_profile": apparmor,
        "capability_bounding_set": bounding,
    }


def select_mounts(
    mounts: Any | None, target: str, default_targets: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    if not mounts:
        return []

    selected: list[dict[str, Any]] = []
    default_targets = list(default_targets or DEFAULT_APPLY_TARGETS)

    for raw in mounts:
        if isinstance(raw, Mapping):
            apply_to = raw.get("apply_to", default_targets)
            if target not in _as_iterable(apply_to):
                continue
            selected.append(dict(raw))
            continue

        apply_to = getattr(raw, "apply_to", default_targets)
        if target in _as_iterable(apply_to):
            selected.append(dict(raw.__dict__))

    return selected


def normalize_secrets(secrets: Any | None, service_name: str) -> dict[str, Any]:
    env_items = _as_iterable(_get_value(secrets, "env", []))
    file_items = _as_iterable(_get_value(secrets, "files", []))
    rotation = _get_value(secrets, "rotation_timestamp", None)

    return {
        "env": env_items,
        "files": file_items,
        "has_env": len(env_items) > 0,
        "has_files": len(file_items) > 0,
        "env_secret_name": f"{service_name}-env",
        "file_secret_name": f"{service_name}-files",
        "rotation_timestamp": rotation,
    }


def merge_environment(
    inline_env: Iterable[Mapping[str, Any]] | None,
    extra: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    names: list[str] = []

    def _append(entry: Mapping[str, Any]) -> None:
        name = str(entry.get("name", "")).strip()
        if not name or name in names:
            return

        items.append({"name": name, "value": str(entry.get("value", ""))})
        names.append(name)

    for source in (inline_env, extra):
        if not source:
            continue

        for entry in source:
            if isinstance(entry, Mapping):
                _append(entry)

    return {"items": items, "names": names}


class FilterModule:
    """Expose runtime helpers to Ansible."""

    def filters(self) -> dict[str, Any]:
        return {
            "normalize_security": normalize_security,
            "select_mounts": select_mounts,
            "normalize_secrets": normalize_secrets,
            "merge_environment": merge_environment,
        }
