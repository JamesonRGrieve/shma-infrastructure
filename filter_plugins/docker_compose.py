"""Jinja2 filters for Docker Compose template rendering."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ansible.errors import AnsibleFilterError


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


def _ensure_env_entries(value: Any, *, context: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if value is None:
        return entries
    if isinstance(value, dict):
        for name, val in value.items():
            entries.append({"name": name, "value": val})
        return entries
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            if not isinstance(item, dict):
                raise AnsibleFilterError(
                    f"{context} entries must be dictionaries with 'name' and 'value' keys"
                )
            if "name" not in item:
                raise AnsibleFilterError(
                    f"{context} entry {item!r} is missing the required 'name' key"
                )
            entries.append({"name": item["name"], "value": item.get("value")})
        return entries
    raise AnsibleFilterError(
        f"{context} must be a sequence or mapping, received {type(value).__name__}"
    )


def _validate_apparmor_profile(
    profile: str, allowed_profiles: Iterable[str], service_name: str
) -> None:
    profile = profile.strip()
    if not profile:
        raise AnsibleFilterError(
            f"service {service_name!r} apparmor profile must be a non-empty string"
        )
    allowed = {item.strip() for item in allowed_profiles if item}
    if allowed and profile not in allowed:
        raise AnsibleFilterError(
            f"service {service_name!r} apparmor profile {profile!r} is not permitted; "
            f"allowed profiles: {sorted(allowed)}"
        )


def _normalise_env(
    inline_env: List[Dict[str, Any]],
    secret_env: List[Dict[str, Any]],
    *,
    rotation_timestamp: Optional[str],
    service_name: str,
    connections_per_second: Optional[Any],
    primary_service_name: Optional[str],
) -> List[Dict[str, Any]]:
    environment: List[Dict[str, Any]] = []
    names = set()

    def add_entry(name: str, value: Any) -> None:
        if name in names:
            return
        environment.append({"name": name, "value": value})
        names.add(name)

    for entry in inline_env:
        add_entry(entry["name"], entry.get("value"))

    if connections_per_second is not None and service_name == primary_service_name:
        add_entry("CONNECTIONS_PER_SECOND", str(connections_per_second))

    if rotation_timestamp is not None:
        add_entry("SHMA_SECRETS_ROTATION", rotation_timestamp)

    for entry in secret_env:
        add_entry(entry["name"], f"${{{entry['name']}}}")

    return environment


def docker_compose_prepare_services(
    services: Sequence[Dict[str, Any]],
    defaults: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    defaults = defaults or {}
    compose_user_default = defaults.get("compose_user_default")
    read_only_default = defaults.get("read_only_root")
    drop_caps_default = _as_list(defaults.get("cap_drop_default"))
    no_new_privs = defaults.get("no_new_privs", True)
    default_apparmor = defaults.get("default_apparmor")
    allowed_apparmor_profiles = _as_list(
        defaults.get("allowed_apparmor_profiles", ["docker-default"])
    )
    docker_tmpfs_defaults = _as_list(defaults.get("docker_tmpfs"))
    secret_env_default = _ensure_env_entries(
        defaults.get("secret_env"), context="secret_env"
    )
    file_secrets_default = defaults.get("file_secrets", []) or []
    connections_per_second = defaults.get("connections_per_second")
    primary_service_name = defaults.get("primary_service_name")
    rotation_timestamp = defaults.get("rotation_timestamp")
    default_init = defaults.get("default_init")

    prepared: List[Dict[str, Any]] = []

    for service in services:
        svc = copy.deepcopy(service)
        service_name = svc.get("name") or svc.get("container_name")
        if not service_name:
            raise AnsibleFilterError(
                "Each service must define a name or container_name"
            )

        svc_user = svc.get("user", compose_user_default)
        svc_read_only = svc.get("read_only", read_only_default)
        svc_cap_drop = svc.get("cap_drop")
        if svc_cap_drop is None:
            svc_cap_drop = drop_caps_default
        else:
            svc_cap_drop = _as_list(svc_cap_drop)

        security_opts_input = _as_list(svc.get("security_opt"))
        security_opts: List[str] = []
        has_apparmor = False
        for opt in security_opts_input:
            opt_str = str(opt)
            if opt_str.startswith("apparmor="):
                has_apparmor = True
                _validate_apparmor_profile(
                    opt_str.split("=", 1)[1], allowed_apparmor_profiles, service_name
                )
            if opt_str not in security_opts:
                security_opts.append(opt_str)

        if no_new_privs and "no-new-privileges:true" not in security_opts:
            security_opts.append("no-new-privileges:true")

        svc_apparmor = svc.get("apparmor_profile", default_apparmor)
        if svc_apparmor not in (None, ""):
            _validate_apparmor_profile(
                str(svc_apparmor), allowed_apparmor_profiles, service_name
            )
            apparmor_opt = f"apparmor={svc_apparmor}"
            if apparmor_opt not in security_opts:
                security_opts.append(apparmor_opt)
            has_apparmor = True

        if not has_apparmor:
            raise AnsibleFilterError(
                f"service {service_name!r} must define an apparmor profile"
            )

        svc_tmpfs = _unique(_as_list(svc.get("tmpfs")) + docker_tmpfs_defaults)

        svc_env_file = _unique(_as_list(svc.get("env_file")))

        svc_secret_env = _ensure_env_entries(
            svc.get("secret_env", secret_env_default), context="secret_env"
        )
        inline_env = _ensure_env_entries(svc.get("env", []), context="environment")

        environment = _normalise_env(
            inline_env,
            svc_secret_env,
            rotation_timestamp=rotation_timestamp,
            service_name=svc.get("name", service_name),
            connections_per_second=connections_per_second,
            primary_service_name=primary_service_name,
        )

        svc_file_secrets = svc.get("file_secrets", file_secrets_default)

        svc_init = svc.get("init", default_init)
        if svc_init is not None:
            svc_init = bool(svc_init)

        svc.update(
            {
                "render_user": svc_user,
                "render_read_only": svc_read_only,
                "render_cap_drop": svc_cap_drop,
                "render_security_opt": security_opts,
                "render_tmpfs": svc_tmpfs,
                "render_env_files": svc_env_file,
                "render_environment": environment,
                "render_file_secrets": svc_file_secrets,
                "render_init": svc_init,
            }
        )

        prepared.append(svc)

    return prepared


class FilterModule(object):
    def filters(self) -> Dict[str, Any]:
        return {"docker_compose_prepare_services": docker_compose_prepare_services}
