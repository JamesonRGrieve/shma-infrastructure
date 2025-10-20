from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import json

try:  # pragma: no cover - import for package execution
    from .messages import FEATURES_REQUIRE_RUNTIME_MESSAGE
except ImportError:  # pragma: no cover - CLI fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ci.messages import FEATURES_REQUIRE_RUNTIME_MESSAGE

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


ALLOWED_LXC_FEATURES = {"nesting", "keyctl", "fuse", "mount"}
VALID_FIREWALL_ACTIONS = {"ACCEPT", "DROP", "REJECT"}
VALID_FIREWALL_DIRECTIONS = {"in", "out"}

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


def load_vmid_registry(path: Path) -> dict[int, str | None]:
    registry = load_yaml(path)

    entries: dict[int, str | None] = {}

    def register(vmid_value: object, owner: object | None = None) -> None:
        if vmid_value is None:
            return
        try:
            vmid = int(str(vmid_value).strip())
        except (TypeError, ValueError) as exc:  # pragma: no cover - invalid data
            raise ValueError(
                f"Invalid VMID entry {vmid_value!r} in registry {path}"
            ) from exc
        owner_str = str(owner).strip() if owner not in (None, "") else None
        entries[vmid] = owner_str

    if registry is None:
        return entries

    if isinstance(registry, Mapping):
        candidates = registry.get("vmids")
        if isinstance(candidates, Sequence) and not isinstance(
            candidates, (str, bytes)
        ):
            for item in candidates:
                if isinstance(item, Mapping):
                    register(
                        item.get("vmid", item.get("id")),
                        item.get("service") or item.get("owner"),
                    )
                else:
                    register(item)
        else:
            for key, value in registry.items():
                if isinstance(value, Mapping):
                    register(
                        value.get("vmid", key),
                        value.get("service") or value.get("owner") or value.get("name"),
                    )
                else:
                    register(key, value)
        return entries

    if isinstance(registry, Sequence) and not isinstance(registry, (str, bytes)):
        for item in registry:
            if isinstance(item, Mapping):
                register(
                    item.get("vmid", item.get("id")),
                    item.get("service") or item.get("owner"),
                )
            else:
                register(item)
        return entries

    register(registry)
    return entries


def validate_manifest(
    manifest_path: Path,
    service_definition: Path | None = None,
    reserved_vmid: Path | None = None,
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

    registry: dict[int, str | None] = {}
    if reserved_vmid:
        if not reserved_vmid.exists():
            print(f"VMID registry not found: {reserved_vmid}", file=sys.stderr)
            return 1
        try:
            registry = load_vmid_registry(reserved_vmid)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

    service: Mapping[str, object] | dict[str, object]
    if service_definition:
        try:
            service = load_yaml(service_definition)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
    else:
        service = {}

    container_spec = manifest.get("container", {})

    vmid_raw = container_spec.get("vmid")
    try:
        vmid_int = int(str(vmid_raw).strip())
    except (TypeError, ValueError):
        vmid_int = None

    if vmid_int is not None and registry:
        vmid_owner = registry.get(vmid_int)
        service_id = str(service.get("service_id", "")).strip() if service else ""
        if vmid_owner and service_id and vmid_owner != service_id:
            print(
                f"Proxmox VMID {vmid_int} conflicts with existing container owned by {vmid_owner}",
                file=sys.stderr,
            )
            return 1
        if vmid_owner and not service_id:
            print(
                f"Proxmox VMID {vmid_int} conflicts with existing container owned by {vmid_owner}",
                file=sys.stderr,
            )
            return 1

    needs_runtime = service.get("needs_container_runtime", True)
    has_features = bool(container_spec.get("features"))
    if has_features and not needs_runtime:
        print(f"{FEATURES_REQUIRE_RUNTIME_MESSAGE}", file=sys.stderr)
        return 1

    security = service.get("service_security") or {}
    allow_privileged = False
    if isinstance(security, Mapping):
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

        normalized_features: list[tuple[str, str]] = []
        for feature in raw_features:
            if not feature:
                continue
            name, _, value = feature.partition("=")
            normalized_features.append((name.strip(), value.strip() or "1"))

        invalid_features = sorted(
            {
                name
                for name, _ in normalized_features
                if name not in ALLOWED_LXC_FEATURES
            }
        )
        if invalid_features:
            print(
                "Unsupported Proxmox LXC feature(s): " + ", ".join(invalid_features),
                file=sys.stderr,
            )
            return 1

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

    firewall_spec = container_spec.get("firewall")
    if firewall_spec not in (None, {}):
        if not isinstance(firewall_spec, Mapping):
            print("container.firewall must be a mapping", file=sys.stderr)
            return 1

        rules_field = firewall_spec.get("rules")
        if rules_field is not None and not isinstance(rules_field, Sequence):
            print("container.firewall.rules must be a list", file=sys.stderr)
            return 1

        rules = (
            [rule for rule in rules_field if rule is not None]
            if isinstance(rules_field, Sequence)
            else []
        )

        for index, rule in enumerate(rules):
            if not isinstance(rule, Mapping):
                print(
                    f"container.firewall.rules[{index}] must be a mapping",
                    file=sys.stderr,
                )
                return 1

            action = rule.get("action")
            if not action or str(action).upper() not in VALID_FIREWALL_ACTIONS:
                allowed_actions = ", ".join(sorted(VALID_FIREWALL_ACTIONS))
                print(
                    f"container.firewall.rules[{index}] action must be one of {allowed_actions}",
                    file=sys.stderr,
                )
                return 1

            direction = rule.get("direction")
            if (
                direction is not None
                and str(direction) not in VALID_FIREWALL_DIRECTIONS
            ):
                print(
                    f"container.firewall.rules[{index}] direction must be 'in' or 'out'",
                    file=sys.stderr,
                )
                return 1

            for boolean_key in ("enable", "log"):
                if boolean_key in rule and not isinstance(
                    rule[boolean_key], (bool, int)
                ):
                    print(
                        f"container.firewall.rules[{index}].{boolean_key} must be a boolean",
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
    parser.add_argument(
        "--vmid-registry",
        type=Path,
        help="Optional path to a VMID registry used to detect conflicts",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return validate_manifest(args.manifest, args.service_definition, args.vmid_registry)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
