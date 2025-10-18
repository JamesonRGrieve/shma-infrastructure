from __future__ import annotations

import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def main() -> int:
    schema_path = Path("schemas/service.schema.yml")
    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        return 1

    try:
        schema = yaml.safe_load(schema_path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - runtime validation
        print(f"Failed to parse schema: {exc}", file=sys.stderr)
        return 1

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # pragma: no cover - validation error details vary
        print(f"Schema validation failed: {exc}", file=sys.stderr)
        return 1

    print("Schema validation succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
