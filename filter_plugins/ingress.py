"""Ingress contract helper filters."""

from __future__ import annotations

from ansible.errors import AnsibleFilterError


REQUIRED_EXPORT_KEYS = ("APP_FQDN", "APP_PORT", "APP_BACKEND_IP")


def _parse_env(content: str) -> dict[str, str]:
    exports: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise AnsibleFilterError(
                f"invalid exports line '{raw_line}'; expected KEY=VALUE"
            )
        key, value = line.split("=", 1)
        exports[key.strip()] = value.strip()
    return exports


def parse_ingress_exports(
    content: str, required_keys: tuple[str, ...] | None = None
) -> dict[str, str]:
    """Parse an exports.env snippet into a dictionary.

    Parameters
    ----------
    content:
        The raw file contents to parse.
    required_keys:
        Optional tuple of keys that must exist in the parsed result. When
        omitted the default ingress export keys are enforced.
    """

    exports = _parse_env(content)
    keys_to_check = required_keys or REQUIRED_EXPORT_KEYS
    missing = [key for key in keys_to_check if not exports.get(key)]
    if missing:
        raise AnsibleFilterError(
            "ingress exports missing required keys: " + ", ".join(missing)
        )
    return exports


def coerce_ingress_port(exports: dict[str, str]) -> int:
    """Convert APP_PORT to an integer for downstream templates."""

    try:
        return int(exports["APP_PORT"])
    except (KeyError, TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise AnsibleFilterError(
            "APP_PORT must be an integer-compatible value"
        ) from exc


class FilterModule:
    """Register ingress contract helper filters."""

    def filters(self) -> dict[str, object]:
        return {
            "parse_ingress_exports": parse_ingress_exports,
            "coerce_ingress_port": coerce_ingress_port,
        }
