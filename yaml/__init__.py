"""A minimal YAML parser for environments without PyYAML.

This module implements a deliberately small subset of YAML that is sufficient
for the configuration files used in the shma-infrastructure test-suite.

Supported features:

* Indentation based mappings and sequences using spaces.
* Scalars expressed as quoted or unquoted strings, integers, floats, booleans,
  and ``null``/``~`` values.
* Inline lists (``[1, 2]``) and dictionaries (``{foo: 1}``) whose contents are
  themselves simple scalars.
* Block scalars using ``|`` and ``>`` (including their ``-``/``+`` variants) with
  basic folding semantics.
* Multiple documents separated by ``---`` and ``...`` markers.

Unsupported features include anchors, YAML tags, and custom constructors.  The
project's test data does not rely on those capabilities and omitting them keeps
this implementation compact.

When parsing fails a :class:`YAMLError` is raised to mirror the public API of
PyYAML's ``safe_load`` helpers.
"""

from __future__ import annotations

import ast
import itertools
import json
import re
from dataclasses import dataclass
from typing import IO, Iterator, List, Tuple, Union

__all__ = ["safe_load", "safe_load_all", "YAMLError"]


class YAMLError(Exception):
    """Raised when the YAML input cannot be parsed."""


@dataclass
class _Line:
    text: str
    number: int

    @property
    def indent(self) -> int:
        return len(self.text) - len(self.text.lstrip(" "))

    @property
    def stripped(self) -> str:
        return self.text.strip()


_BLOCK_INDICATORS = {"|", "|-", "|+", ">", ">-", ">+"}
_BOOL_MAP = {
    "true": True,
    "false": False,
    "yes": True,
    "no": False,
    "on": True,
    "off": False,
}
_NULL_VALUES = {"null", "~", ""}


def _split_documents(text: str) -> List[List[_Line]]:
    lines = [
        _Line(raw.rstrip("\n"), idx + 1) for idx, raw in enumerate(text.splitlines())
    ]

    documents: List[List[_Line]] = []
    current: List[_Line] = []

    def flush() -> None:
        if current:
            documents.append(current.copy())
            current.clear()

    for line in lines:
        stripped = line.stripped
        if stripped == "" or stripped.startswith("#"):
            current.append(line)
            continue
        if stripped == "---":
            flush()
            continue
        if stripped == "...":
            flush()
            continue
        current.append(line)

    flush()
    if not documents:
        documents.append([])
    return documents


def _strip_comment(value: str) -> str:
    in_single = False
    in_double = False
    for idx, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_single
        elif char == "#" and not in_single and not in_double:
            return value[:idx].rstrip()
    return value.rstrip()


def _literal_eval(value: str) -> object:
    adjusted = re.sub(r"\btrue\b", "True", value)
    adjusted = re.sub(r"\bfalse\b", "False", adjusted)
    adjusted = re.sub(r"\bnull\b", "None", adjusted)
    adjusted = re.sub(r"\b~\b", "None", adjusted)
    try:
        return ast.literal_eval(adjusted)
    except Exception as exc:  # pragma: no cover - mirrors PyYAML behaviour
        raise YAMLError(f"Invalid inline YAML scalar: {value}") from exc


def _parse_inline_list(value: str) -> list:
    inner = value[1:-1].strip()
    if not inner:
        return []
    elements: list[str] = []
    current: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    for char in inner:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        if char == "," and depth == 0 and not in_single and not in_double:
            elements.append("".join(current).strip())
            current.clear()
            continue
        current.append(char)
    if current:
        elements.append("".join(current).strip())
    return [_parse_scalar(element) for element in elements]


def _parse_scalar(raw: str, *, for_key: bool = False) -> object:
    value = raw.strip()
    if not value:
        return "" if for_key else None

    if value[0] in {'"', "'"}:
        try:
            return ast.literal_eval(value)
        except Exception as exc:  # pragma: no cover - mirrors PyYAML behaviour
            raise YAMLError(f"Invalid quoted scalar: {value}") from exc

    lowered = value.lower()
    if not for_key and lowered in _BOOL_MAP:
        return _BOOL_MAP[lowered]
    if not for_key and lowered in _NULL_VALUES:
        return None

    if not for_key:
        if re.fullmatch(r"[-+]?[0-9]+", value):
            try:
                as_int = int(value, 10)
                if isinstance(as_int, bool):
                    return value
                return as_int
            except ValueError:
                pass
        if re.fullmatch(r"[-+]?[0-9]*\.[0-9]+", value):
            try:
                return float(value)
            except ValueError:
                pass

    if value.startswith("[") and value.endswith("]"):
        try:
            return _literal_eval(value)
        except YAMLError:
            return _parse_inline_list(value)
    if value.startswith("{") and value.endswith("}"):
        return _literal_eval(value)

    return value


def _parse_block_scalar(
    lines: List[_Line], index: int, indicator: str, base_indent: int
) -> Tuple[str, int]:
    block_lines: List[Tuple[int, str]] = []
    cursor = index + 1
    while cursor < len(lines):
        line = lines[cursor]
        if line.stripped == "" and line.indent <= base_indent:
            break
        if (
            line.indent <= base_indent
            and line.stripped
            and not line.stripped.startswith("#")
        ):
            break
        block_lines.append((line.indent, line.text))
        cursor += 1

    if not block_lines:
        return ("" if indicator.endswith("-") else "\n"), cursor

    relevant = [indent for indent, text in block_lines if text.strip()]
    min_indent = min(relevant) if relevant else base_indent + 1

    processed: List[str] = []
    for indent, text in block_lines:
        if text.strip() == "":
            processed.append("")
        else:
            processed.append(text[min_indent:])

    if indicator.startswith("|"):
        value = "\n".join(processed)
    else:
        groups = [
            list(group)
            for key, group in itertools.groupby(processed, lambda x: x == "")
        ]
        folded_parts: List[str] = []
        for group in groups:
            if group and group[0] == "":
                folded_parts.append("")
            else:
                folded_parts.append(" ".join(group))
        value = "\n".join(folded_parts)

    if indicator.endswith("-"):
        return value, cursor
    if indicator.endswith("+"):
        return value + "\n", cursor
    return value + "\n", cursor


def _parse_inline_mapping(
    lines: List[_Line], index: int, base_indent: int, first_entry: str
) -> Tuple[dict, int]:
    key_raw, remainder = first_entry.split(":", 1)
    key = _parse_scalar(key_raw, for_key=True)
    remainder = remainder.strip()
    cursor = index

    item: dict = {}
    if remainder:
        item[key] = _parse_scalar(remainder)
        cursor += 1
    else:
        value, cursor = _parse_structure(lines, index + 1, base_indent + 2)
        item[key] = value

    while cursor < len(lines):
        line = lines[cursor]
        stripped = line.stripped
        if stripped == "" or stripped.startswith("#"):
            cursor += 1
            continue
        if line.indent < base_indent + 2:
            break
        if line.indent > base_indent + 2:
            value, cursor = _parse_structure(lines, cursor, base_indent + 2)
            if isinstance(value, dict):
                item.update(value)
                continue
            raise YAMLError(f"Unexpected nested structure at line {line.number}")
        if stripped.startswith("- "):
            break
        if ":" not in stripped:
            raise YAMLError(f"Expected mapping entry at line {line.number}")
        subkey_raw, subvalue_raw = stripped.split(":", 1)
        subvalue_text = _strip_comment(subvalue_raw).lstrip()
        if subvalue_text in _BLOCK_INDICATORS:
            subvalue, cursor = _parse_block_scalar(
                lines, cursor, subvalue_text, line.indent
            )
        elif subvalue_text == "":
            subvalue, cursor = _parse_structure(lines, cursor + 1, line.indent + 2)
        else:
            subvalue = _parse_scalar(subvalue_text)
            cursor += 1
        item[_parse_scalar(subkey_raw, for_key=True)] = subvalue
    return item, cursor


def _parse_structure(lines: List[_Line], start: int, indent: int) -> Tuple[object, int]:
    collection: object | None = None
    index = start

    while index < len(lines):
        line = lines[index]
        stripped = line.stripped

        if stripped == "" or stripped.startswith("#"):
            index += 1
            continue

        if line.indent < indent:
            break

        if stripped.startswith("- "):
            if collection is None:
                collection = []
            elif not isinstance(collection, list):
                raise YAMLError(f"Mixed list/dict structure near line {line.number}")
            value_part = _strip_comment(stripped[2:])
            if value_part in _BLOCK_INDICATORS:
                value, index = _parse_block_scalar(
                    lines, index, value_part, line.indent
                )
            elif value_part == "":
                value, index = _parse_structure(lines, index + 1, line.indent + 2)
            elif ":" in value_part and not value_part.strip().startswith(
                ("{", "[", "'", '"')
            ):
                value, index = _parse_inline_mapping(
                    lines, index, line.indent, value_part
                )
            else:
                value = _parse_scalar(value_part)
                index += 1
            collection.append(value)
            continue

        if ":" not in stripped:
            raise YAMLError(f"Expected mapping entry at line {line.number}")

        if collection is None:
            collection = {}
        elif not isinstance(collection, dict):
            raise YAMLError(f"Mixed list/dict structure near line {line.number}")

        key_part, value_part_raw = stripped.split(":", 1)
        key = _parse_scalar(key_part, for_key=True)
        value_part = _strip_comment(value_part_raw)
        value_part = value_part.lstrip()

        if value_part in _BLOCK_INDICATORS:
            value, index = _parse_block_scalar(lines, index, value_part, line.indent)
        elif value_part == "":
            value, index = _parse_structure(lines, index + 1, line.indent + 2)
        else:
            value = _parse_scalar(value_part)
            index += 1
        collection[key] = value

    if collection is None:
        return None, index
    return collection, index


def _parse_document(lines: List[_Line]) -> object:
    if not lines:
        return None
    value, index = _parse_structure(lines, 0, 0)
    while index < len(lines):
        if lines[index].stripped not in {"", "#"}:
            raise YAMLError(f"Unexpected content at line {lines[index].number}")
        index += 1
    return value


def _ensure_text(source: Union[str, bytes, IO[str], IO[bytes]]) -> str:
    if isinstance(source, str):
        return source
    if isinstance(source, bytes):
        return source.decode("utf-8")
    read = getattr(source, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, bytes):
            return data.decode("utf-8")
        if isinstance(data, str):
            return data
        return str(data)
    raise YAMLError("safe_load expects a string, bytes, or file-like object")


def safe_load(text: Union[str, bytes, IO[str], IO[bytes]]) -> object:
    text = _ensure_text(text)
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    try:
        documents = list(safe_load_all(text))
    except YAMLError as exc:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise exc
    if not documents:
        return None
    return documents[0]


def safe_load_all(text: Union[str, bytes, IO[str], IO[bytes]]) -> Iterator[object]:
    text = _ensure_text(text)
    for document_lines in _split_documents(text):
        yield _parse_document(document_lines)
