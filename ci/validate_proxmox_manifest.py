from __future__ import annotations

import argparse
import sys
from pathlib import Path

import json

if __package__ in {None, ""}:  # pragma: no cover - compatibility for CLI execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ci.messages import FEATURES_REQUIRE_RUNTIME_MESSAGE
else:  # pragma: no cover - module import within package context
    from .messages import FEATURES_REQUIRE_RUNTIME_MESSAGE

try:  # pragma: no cover - exercised via fallback in tests when PyYAML is absent
    import yaml
except ImportError:  # pragma: no cover - fallback for environments without PyYAML
    yaml = None
try:
    from jsonschema import Draft202012Validator, ValidationError
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal test envs

    class ValidationError(Exception):
        """Fallback validation error used when jsonschema is unavailable."""

    class Draft202012Validator:  # type: ignore[override]
        def __init__(self, schema: dict | None = None) -> None:
            self.schema = schema or {}

        def validate(self, instance: dict) -> None:
            return None


SCHEMA_PATH = Path("schemas/proxmox.schema.yml")


def load_yaml(path: Path) -> dict:
    text = path.read_text()

    if yaml is not None:
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:  # pragma: no cover - runtime validation
            raise ValueError(f"Failed to parse YAML file {path}: {exc}") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - runtime validation
        raise ValueError(f"Failed to parse JSON file {path}: {exc}") from exc


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

        container_spec = manifest.get("container", {})
        needs_runtime = service.get("needs_container_runtime", True)
        has_features = bool(container_spec.get("features"))
        if has_features and not needs_runtime:
            print(f"{FEATURES_REQUIRE_RUNTIME_MESSAGE}", file=sys.stderr)
            return 1

        security = service.get("service_security") or {}
        allow_privileged = False
        if isinstance(security, dict):
            allow_privileged = bool(security.get("allow_privilege_escalation")) or (
                security.get("no_new_privileges") is False
            )

        unprivileged_raw = container_spec.get("unprivileged", "yes")
        if isinstance(unprivileged_raw, str):
            unprivileged_value = unprivileged_raw.strip().lower() in {
                "yes",
                "true",
                "1",
            }
        else:
            unprivileged_value = bool(unprivileged_raw)

        if not unprivileged_value and not allow_privileged:
            print(
                "Proxmox containers must remain unprivileged unless service_security"
                ".allow_privilege_escalation is true or service_security.no_new_privileges"
                " is explicitly set to false",
                file=sys.stderr,
            )
            return 1

        features_field = container_spec.get("features")
        if features_field:
            if isinstance(features_field, str):
                raw_features = [part.strip() for part in features_field.split(",")]
            elif isinstance(features_field, (list, tuple, set)):
                raw_features = [str(item).strip() for item in features_field]
            else:
                raw_features = [str(features_field).strip()]

            normalized_features = []
            for feature in raw_features:
                if not feature:
                    continue
                name, _, value = feature.partition("=")
                normalized_features.append((name.strip(), value.strip() or "1"))

            nesting_enabled = any(
                name == "nesting" and value not in {"0", "false", "no"}
                for name, value in normalized_features
            )

            if nesting_enabled and not allow_privileged:
                print(
                    "Proxmox container nesting requires service_security.allow_privilege_escalation="
                    "true or service_security.no_new_privileges=false",
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
