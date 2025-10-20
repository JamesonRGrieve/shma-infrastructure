"""A very small JSON Schema validator for the test environment.

The real project depends on the :mod:`jsonschema` package which is not
available in this execution environment.  The test-suite only exercises a tiny
subset of the Draft 2020-12 specification, so this module implements enough of
that functionality for the tests to run successfully.

Supported features include:

* ``type`` checks for ``object``, ``array``, ``string``, ``integer``, ``number``,
  ``boolean``, and ``null``.
* ``required`` properties and ``properties`` definitions for nested objects.
* ``items`` validation for arrays (both schema objects and fixed tuples).
* ``enum``, ``const``, ``pattern``, ``minimum``/``maximum`` and
  ``minLength``/``maxLength`` checks.
* ``minItems``/``maxItems`` for arrays.
* ``oneOf``, ``anyOf``, and ``allOf`` composition keywords.
* ``$ref`` resolution for local files (used by the service schema).

The behaviour intentionally mirrors the public API of :mod:`jsonschema` where it
matters for the tests: a :class:`ValidationError` is raised when validation
fails, and :class:`Draft202012Validator` exposes a ``validate`` method.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

__all__ = ["Draft202012Validator", "ValidationError", "RefResolver"]


class ValidationError(Exception):
    """Exception raised when a JSON document does not match a schema."""

    def __init__(self, message: str, path: Iterable[str | int] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.path = list(path or [])


@dataclass
class RefResolver:
    """Minimal resolver that supports local file references."""

    base_uri: str
    referrer: dict

    def resolve(self, ref: str) -> dict:
        if ref.startswith("#"):
            # Fragment identifiers are not required for the tests; return the
            # referrer unchanged.
            return self.referrer
        base_path = Path(self.base_uri)
        if base_path.is_file():
            base_dir = base_path.parent
        else:
            base_dir = base_path
        target_path = (base_dir / ref).resolve()
        if not target_path.exists():
            raise ValidationError(f"Reference target not found: {ref}")
        return yaml.safe_load(target_path.read_text()) or {}


class Draft202012Validator:
    """Minimal validator covering the subset of JSON Schema used in tests."""

    def __init__(self, schema: dict, resolver: RefResolver | None = None) -> None:
        self.schema = schema or {}
        if resolver is None:
            self.resolver = RefResolver(Path.cwd().resolve().as_uri(), self.schema)
        else:
            self.resolver = resolver

    def validate(self, instance: Any) -> None:
        self._validate_schema(self.schema, instance, path=[])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _validate_schema(
        self, schema: dict, instance: Any, path: list[str | int]
    ) -> None:
        if "$ref" in schema:
            ref_schema = self.resolver.resolve(schema["$ref"])
            self._validate_schema(ref_schema, instance, path)
            return

        schema_type = schema.get("type")
        if schema_type is not None:
            self._check_type(schema_type, instance, path)

        if "enum" in schema:
            if instance not in schema["enum"]:
                raise ValidationError(
                    f"{self._format_path(path)} is not one of {schema['enum']}",
                    path,
                )

        if "const" in schema:
            if instance != schema["const"]:
                raise ValidationError(
                    f"{self._format_path(path)} must equal {schema['const']}", path
                )

        if "pattern" in schema and isinstance(instance, str):
            if re.search(schema["pattern"], instance) is None:
                raise ValidationError(
                    f"{self._format_path(path)} does not match pattern {schema['pattern']}",
                    path,
                )

        if isinstance(instance, str):
            min_length = schema.get("minLength")
            max_length = schema.get("maxLength")
            if min_length is not None and len(instance) < int(min_length):
                raise ValidationError(
                    f"{self._format_path(path)} is shorter than {min_length}", path
                )
            if max_length is not None and len(instance) > int(max_length):
                raise ValidationError(
                    f"{self._format_path(path)} is longer than {max_length}", path
                )

        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            exclusive_min = schema.get("exclusiveMinimum")
            exclusive_max = schema.get("exclusiveMaximum")
            if minimum is not None and instance < minimum:
                raise ValidationError(
                    f"{self._format_path(path)} is less than {minimum}", path
                )
            if maximum is not None and instance > maximum:
                raise ValidationError(
                    f"{self._format_path(path)} is greater than {maximum}", path
                )
            if exclusive_min is not None and instance <= exclusive_min:
                raise ValidationError(
                    f"{self._format_path(path)} must be greater than {exclusive_min}",
                    path,
                )
            if exclusive_max is not None and instance >= exclusive_max:
                raise ValidationError(
                    f"{self._format_path(path)} must be less than {exclusive_max}",
                    path,
                )

        if isinstance(instance, dict):
            self._validate_object(schema, instance, path)

        if isinstance(instance, list):
            self._validate_array(schema, instance, path)

        for keyword in ("allOf", "anyOf", "oneOf"):
            if keyword in schema:
                self._validate_composition(keyword, schema[keyword], instance, path)

    def _validate_object(
        self, schema: dict, instance: dict, path: list[str | int]
    ) -> None:
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                raise ValidationError(
                    f"{self._format_path(path + [key])} is a required property",
                    path + [key],
                )

        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in instance:
                self._validate_schema(subschema or {}, instance[key], path + [key])

        additional = schema.get("additionalProperties")
        if additional is False and properties:
            for key in instance:
                if key not in properties:
                    raise ValidationError(
                        f"Unexpected property {key} at {self._format_path(path)}",
                        path + [key],
                    )
        elif isinstance(additional, dict):
            for key, value in instance.items():
                if key not in properties:
                    self._validate_schema(additional, value, path + [key])

    def _validate_array(
        self, schema: dict, instance: list, path: list[str | int]
    ) -> None:
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(instance) < int(min_items):
            raise ValidationError(
                f"{self._format_path(path)} has fewer than {min_items} items", path
            )
        if max_items is not None and len(instance) > int(max_items):
            raise ValidationError(
                f"{self._format_path(path)} has more than {max_items} items", path
            )

        items = schema.get("items")
        if isinstance(items, list):
            for idx, (element, subschema) in enumerate(zip(instance, items)):
                self._validate_schema(subschema or {}, element, path + [idx])
        elif isinstance(items, dict):
            for idx, element in enumerate(instance):
                self._validate_schema(items, element, path + [idx])

    def _validate_composition(
        self,
        keyword: str,
        subschemas: list[dict],
        instance: Any,
        path: list[str | int],
    ) -> None:
        results = []
        for subschema in subschemas:
            try:
                self._validate_schema(subschema or {}, instance, path)
                results.append(True)
            except ValidationError:
                results.append(False)
        if keyword == "allOf" and not all(results):
            raise ValidationError(f"{self._format_path(path)} failed allOf", path)
        if keyword == "anyOf" and not any(results):
            raise ValidationError(f"{self._format_path(path)} failed anyOf", path)
        if keyword == "oneOf" and results.count(True) != 1:
            raise ValidationError(f"{self._format_path(path)} failed oneOf", path)

    def _check_type(self, expected: Any, instance: Any, path: list[str | int]) -> None:
        type_map = {
            "object": dict,
            "array": list,
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "null": type(None),
        }
        if isinstance(expected, list):
            for option in expected:
                try:
                    self._check_type(option, instance, path)
                    return
                except ValidationError:
                    continue
            raise ValidationError(
                f"{self._format_path(path)} is not any of {expected}", path
            )
        if expected not in type_map:
            return
        expected_type = type_map[expected]
        if expected == "integer":
            if isinstance(instance, bool) or not isinstance(instance, int):
                raise ValidationError(
                    f"{self._format_path(path)} is not of type {expected}", path
                )
            return
        if not isinstance(instance, expected_type):
            raise ValidationError(
                f"{self._format_path(path)} is not of type {expected}", path
            )

    @staticmethod
    def _format_path(path: list[str | int]) -> str:
        if not path:
            return "instance"
        formatted = []
        for element in path:
            if isinstance(element, int):
                formatted.append(f"[{element}]")
            else:
                formatted.append(f".{element}")
        return "instance" + "".join(formatted)
