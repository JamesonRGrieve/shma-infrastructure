from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, ValidationError

SCHEMA_PATH = Path("schemas/proxmox.schema.yml")


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - runtime validation
        raise ValueError(f"Failed to parse YAML file {path}: {exc}") from exc


def validate_manifest(
    manifest_path: Path, service_definition: Path | None = None
) -> int:
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        manifest = load_yaml(manifest_path)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    schema = load_yaml(SCHEMA_PATH)
    validator = Draft202012Validator(schema)

    try:
        validator.validate(manifest)
    except ValidationError as exc:
        print(f"Proxmox manifest validation failed: {exc.message}", file=sys.stderr)
        return 1

    if service_definition:
        try:
            service = load_yaml(service_definition)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

        needs_runtime = service.get("needs_container_runtime", True)
        has_features = bool(manifest.get("container", {}).get("features"))
        if has_features and not needs_runtime:
            print(
                "Proxmox manifest contains features but needs_container_runtime is false",
                file=sys.stderr,
            )
            return 1

    print(f"Validated Proxmox manifest at {manifest_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate rendered Proxmox manifest")
    parser.add_argument("manifest", type=Path, help="Path to rendered Proxmox YAML")
    parser.add_argument(
        "--service-definition",
        type=Path,
        help="Service definition used to render the manifest",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return validate_manifest(args.manifest, args.service_definition)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
