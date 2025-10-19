from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - runtime validation
        raise ValueError(f"Failed to parse YAML file {path}: {exc}") from exc


def extract_health_command(service_definition: dict) -> list[str]:
    health = service_definition.get("health") or {}
    cmd = health.get("cmd")
    if not cmd:
        raise ValueError("Service definition does not define health.cmd")
    if not isinstance(cmd, list):
        raise ValueError("health.cmd must be a list")
    return [str(item) for item in cmd]


def compose_services(manifest: dict) -> dict:
    services = manifest.get("services")
    if not isinstance(services, dict):
        raise ValueError("Compose manifest missing services map")
    return services


def health_tests(service: dict) -> list[str] | None:
    health = service.get("healthcheck") or {}
    test = health.get("test")
    if test is None:
        return None
    if isinstance(test, list):
        return [str(item) for item in test]
    if isinstance(test, str):
        return [test]
    raise ValueError("healthcheck.test must be a list or string")


def validate_health_parity(expected: list[str], services: dict) -> list[str]:
    mismatches = []
    for name, service in services.items():
        test = health_tests(service)
        if test is None:
            continue
        if test != expected:
            mismatches.append(name)
        else:
            return []
    if mismatches:
        return [
            "healthcheck.test does not match health.cmd for services: "
            + ", ".join(sorted(mismatches))
        ]
    return ["No service exposes healthcheck.test to compare against health.cmd"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ensure Docker Compose healthcheck.test matches health.cmd"
    )
    parser.add_argument("service_definition", type=Path)
    parser.add_argument("compose_manifest", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        service_definition = load_yaml(args.service_definition)
        manifest = load_yaml(args.compose_manifest)
        expected = extract_health_command(service_definition)
        services = compose_services(manifest)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    failures = validate_health_parity(expected, services)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
