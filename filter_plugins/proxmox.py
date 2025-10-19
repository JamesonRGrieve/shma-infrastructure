"""Custom Proxmox filters used by templates and tasks."""

from __future__ import annotations
from collections.abc import Mapping, Sequence
from typing import Any


def _stringify(value: Any) -> str:
    """Return a string representation for payload emission."""

    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def proxmox_firewall_options(config: Any) -> dict[str, str]:
    """Normalize firewall option mappings for the Proxmox API."""

    if not isinstance(config, Mapping):
        return {}

    result: dict[str, str] = {}

    if "enabled" in config:
        result["enable"] = _stringify(bool(config["enabled"]))

    field_map = {
        "default_inbound_policy": "policy_in",
        "default_outbound_policy": "policy_out",
        "default_forward_policy": "policy_forward",
        "log_level": "log_level",
    }

    for source, dest in field_map.items():
        value = config.get(source)
        if value not in (None, ""):
            result[dest] = str(value)

    return result


def proxmox_firewall_rules(config: Any) -> list[dict[str, str]]:
    """Normalize firewall rule declarations into API payloads."""

    rules: Sequence[Any]
    if isinstance(config, Mapping):
        raw_rules = config.get("rules", [])
        if isinstance(raw_rules, Sequence) and not isinstance(raw_rules, (str, bytes)):
            rules = raw_rules
        else:
            rules = []
    else:
        rules = []

    normalized: list[dict[str, str]] = []
    field_map = {
        "action": "action",
        "direction": "type",
        "interface": "iface",
        "macro": "macro",
        "source": "source",
        "destination": "dest",
        "protocol": "proto",
        "source_port": "sport",
        "destination_port": "dport",
        "icmp_type": "icmp-type",
        "comment": "comment",
    }

    for entry in rules:
        if not isinstance(entry, Mapping):
            continue

        payload: dict[str, str] = {}
        for source, dest in field_map.items():
            if source in entry:
                value = entry[source]
                if value not in (None, ""):
                    payload[dest] = str(value)

        for boolean_key in ("enable", "log"):
            if boolean_key in entry:
                payload[boolean_key] = _stringify(bool(entry[boolean_key]))

        if payload:
            normalized.append(payload)

    return normalized


class FilterModule:
    """Expose filters to Ansible."""

    def filters(self) -> dict[str, Any]:
        return {
            "proxmox_firewall_options": proxmox_firewall_options,
            "proxmox_firewall_rules": proxmox_firewall_rules,
        }
