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


def gather_secret_values(service: dict) -> set[str]:
    secrets = set()
    secret_block = service.get("secrets", {})

    for item in secret_block.get("env", []) or []:
        value = item.get("value")
        if value:
            secrets.add(str(value))

    for item in secret_block.get("files", []) or []:
        value = item.get("value")
        if value:
            secrets.add(str(value))

    return secrets


def check_manifest(manifest_path: Path, secrets: set[str]) -> list[str]:
    content = manifest_path.read_text()
    found = []
    for secret in secrets:
        if secret and secret in content:
            found.append(secret)
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ensure rendered manifests do not contain inline secrets")
    parser.add_argument("service_definition", type=Path, help="Service definition file used during rendering")
    parser.add_argument("manifest", nargs="+", type=Path, help="Manifest files to inspect")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        service = load_yaml(args.service_definition)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    secrets = gather_secret_values(service)
    if not secrets:
        return 0

    failures: list[str] = []
    for manifest in args.manifest:
        if not manifest.exists():
            print(f"Manifest not found: {manifest}", file=sys.stderr)
            return 1
        inlined = check_manifest(manifest, secrets)
        if inlined:
            failures.append(
                f"{manifest}: found inline secrets {', '.join(sorted(inlined))}"
            )

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
