"""Validate rendered bare-metal systemd units for hardened defaults."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List

import yaml

DEFAULT_APPLY_TARGETS = ["docker", "podman", "kubernetes", "proxmox", "baremetal"]


def parse_unit(unit_path: Path) -> Dict[str, Dict[str, List[str]]]:
    sections: Dict[str, Dict[str, List[str]]] = {}
    current_section: str | None = None

    for raw_line in unit_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            sections.setdefault(current_section, {})
            continue
        if "=" not in raw_line or current_section is None:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        value = value.strip()
        section_entries = sections.setdefault(current_section, {})
        section_entries.setdefault(key, []).append(value)

    return sections


def load_service_definition(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def enforce_protect_system(service: dict) -> bool:
    security = service.get("service_security") or {}
    unit_overrides = (service.get("service_unit") or {}).get("service") or {}
    if "ProtectSystem" in unit_overrides:
        return False
    if "protect_system" in security:
        return False
    if "read_only_root_filesystem" in security:
        return False
    return True


def enforce_protect_home(service: dict) -> bool:
    security = service.get("service_security") or {}
    unit_overrides = (service.get("service_unit") or {}).get("service") or {}
    if "ProtectHome" in unit_overrides:
        return False
    if "protect_home" in security:
        return False
    return True


def ephemeral_paths_for_baremetal(service: dict) -> List[str]:
    mounts = (service.get("mounts") or {}).get("ephemeral_mounts") or []
    paths: List[str] = []
    for mount in mounts:
        path = mount.get("path")
        if not path:
            continue
        apply_to: Iterable[str] | None = mount.get("apply_to")
        if not apply_to:
            apply_to = DEFAULT_APPLY_TARGETS
        if "baremetal" in apply_to:
            paths.append(path)
    return paths


def validate_unit(unit_path: Path, service_path: Path) -> int:
    service = load_service_definition(service_path)
    unit_sections = parse_unit(unit_path)
    service_section = unit_sections.get("Service")

    errors: List[str] = []
    if service_section is None:
        errors.append("[Service] section missing from unit file")
        service_section = {}

    if enforce_protect_system(service):
        values = service_section.get("ProtectSystem", [])
        if not values:
            errors.append("ProtectSystem directive missing from [Service] section")
        elif values[-1].strip().lower() != "strict":
            errors.append(
                f"ProtectSystem is {values[-1]!r}; expected 'strict' for hardened default"
            )

    if enforce_protect_home(service):
        values = service_section.get("ProtectHome", [])
        if not values:
            errors.append("ProtectHome directive missing from [Service] section")
        elif values[-1].strip().lower() != "yes":
            errors.append(
                f"ProtectHome is {values[-1]!r}; expected 'yes' for hardened default"
            )

    expected_tmpfs = ephemeral_paths_for_baremetal(service)
    if expected_tmpfs:
        tmpfs_entries = service_section.get("TemporaryFileSystem", [])
        missing = []
        for path in expected_tmpfs:
            if not any(entry.split(":", 1)[0] == path for entry in tmpfs_entries):
                missing.append(path)
        if missing:
            errors.append(
                "Missing TemporaryFileSystem entries for ephemeral mounts: "
                + ", ".join(sorted(missing))
            )

    if errors:
        for error in errors:
            print(f"{unit_path}: {error}")
        return 1

    print(f"Validated systemd unit security directives in {unit_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate rendered systemd unit security directives",
    )
    parser.add_argument("unit", type=Path, help="Path to rendered systemd unit")
    parser.add_argument(
        "--service-definition",
        type=Path,
        required=True,
        help="Service definition used to render the unit",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return validate_unit(args.unit, args.service_definition)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
