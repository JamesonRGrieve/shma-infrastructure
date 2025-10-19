"""Filters for platform specific lookups."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ansible.errors import AnsibleFilterError


def platform_map(
    value: Mapping[str, Any] | None,
    distribution: str | None = None,
    family: str | None = None,
    fallback: str | Sequence[str] | None = None,
    default: Any = None,
) -> Any:
    """Resolve a distribution specific value with graceful fallbacks."""

    if value is None:
        return default
    if not isinstance(value, Mapping):
        raise AnsibleFilterError("platform_map expects a mapping as the first argument")

    search_order: list[str] = []

    if distribution:
        search_order.append(str(distribution))

    if fallback:
        if isinstance(fallback, str):
            search_order.append(fallback)
        else:
            search_order.extend(str(item) for item in fallback)

    if family:
        search_order.append(str(family))

    for key in search_order:
        if key in value:
            return value[key]

    return default


class FilterModule:
    """Expose platform helper filters."""

    def filters(self):
        return {
            "platform_map": platform_map,
        }
