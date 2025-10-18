from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, ValidationError


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - runtime validation
        raise ValueError(f"Failed to parse YAML file {path}: {exc}") from exc


def validate_schema(schema_path: Path) -> dict | int:
    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        return 1

    try:
        schema = load_yaml(schema_path)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # pragma: no cover - validation error details vary
        print(f"Schema validation failed: {exc}", file=sys.stderr)
        return 1

    return schema


def validate_examples(schema: dict, examples_dir: Path) -> int:
    validator = Draft202012Validator(schema)
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

        if (
            document.get("needs_container_runtime") is not True
            and document.get("service_container", {}).get("features")
        ):
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    schema_path = Path("schemas/service.schema.yml")
    schema = validate_schema(schema_path)
    if isinstance(schema, int):  # pragma: no cover - failure already logged
        return schema

    print("Schema validation succeeded.")

    if args.examples:
        examples_dir = args.examples
        if not examples_dir.exists():
            print(f"Examples directory not found: {examples_dir}", file=sys.stderr)
            return 1
        result = validate_examples(schema, examples_dir)
        if result != 0:
            return result
        print(f"Validated examples in {examples_dir}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
