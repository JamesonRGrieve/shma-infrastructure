from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, ValidationError
from jsonschema import RefResolver


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - runtime validation
        raise ValueError(f"Failed to parse YAML file {path}: {exc}") from exc


def build_validator(schema_path: Path, schema: dict) -> Draft202012Validator | int:
    base_uri = schema_path.resolve().as_uri()
    try:
        resolver = RefResolver(base_uri=base_uri, referrer=schema)
        return Draft202012Validator(schema, resolver=resolver)
    except Exception as exc:  # pragma: no cover - validation error details vary
        print(f"Schema validation failed: {exc}", file=sys.stderr)
        return 1


def validate_schema(schema_path: Path) -> tuple[dict, Draft202012Validator] | int:
    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        return 1

    try:
        schema = load_yaml(schema_path)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    validator = build_validator(schema_path, schema)
    if isinstance(validator, int):  # pragma: no cover - failure already logged
        return validator

    return schema, validator


def validate_examples(validator: Draft202012Validator, examples_dir: Path) -> int:
    schema = validator.schema
    failures: list[str] = []

    for example in sorted(examples_dir.glob("*.yml")):
        try:
            document = load_yaml(example)
        except ValueError as exc:
            failures.append(str(exc))
            continue

        try:
            validator.validate(document)
        except ValidationError as exc:
            failures.append(f"{example}: {exc.message}")
            continue

        secrets = document.get("secrets", {})
        placeholder_failures: list[str] = []
        for secret in secrets.get("env", []) or []:
            value = secret.get("value", "")
            if isinstance(value, str) and value.lower().startswith("change-me"):
                placeholder_failures.append(secret.get("name", "<unnamed>"))
        for secret in secrets.get("files", []) or []:
            raw_value = secret.get("value") or secret.get("content") or ""
            if isinstance(raw_value, str) and raw_value.lower().startswith("change-me"):
                placeholder_failures.append(secret.get("name", "<unnamed>"))
        if placeholder_failures:
            failures.append(
                f"{example}: secrets {', '.join(sorted(placeholder_failures))} retain change-me placeholders"
            )

        if document.get("needs_container_runtime") is not True and document.get(
            "service_container", {}
        ).get("features"):
            failures.append(
                "{}: service_container.features requires needs_container_runtime=true".format(
                    example
                )
            )

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Validate service schema and examples")
    parser.add_argument(
        "--examples",
        type=Path,
        help="Directory containing sample service definitions to validate",
    )
    parser.add_argument(
        "--dependency-registry",
        type=Path,
        action="append",
        help="Path to dependency registry file(s) to validate against the registry schema",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    schema_path = Path("schemas/service.schema.yml")
    schema_validation = validate_schema(schema_path)
    if isinstance(schema_validation, int):  # pragma: no cover - failure already logged
        return schema_validation

    schema, validator = schema_validation

    print("Schema validation succeeded.")

    if args.dependency_registry:
        registry_schema_validation = validate_schema(
            Path("schemas/dependency-registry.schema.yml")
        )
        if isinstance(
            registry_schema_validation, int
        ):  # pragma: no cover - failure already logged
            return registry_schema_validation

        _, registry_validator = registry_schema_validation
        registry_failures: list[str] = []
        for registry_path in args.dependency_registry:
            if not registry_path.exists():
                registry_failures.append(
                    f"Dependency registry file not found: {registry_path}"
                )
                continue
            try:
                registry_document = load_yaml(registry_path)
            except ValueError as exc:
                registry_failures.append(str(exc))
                continue
            try:
                registry_validator.validate(registry_document)
            except ValidationError as exc:
                registry_failures.append(f"{registry_path}: {exc.message}")

        if registry_failures:
            for failure in registry_failures:
                print(failure, file=sys.stderr)
            return 1

        print(
            "Validated dependency registry files: "
            + ", ".join(str(path) for path in args.dependency_registry)
        )

    if args.examples:
        examples_dir = args.examples
        if not examples_dir.exists():
            print(f"Examples directory not found: {examples_dir}", file=sys.stderr)
            return 1
        result = validate_examples(validator, examples_dir)
        if result != 0:
            return result
        print(f"Validated examples in {examples_dir}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
