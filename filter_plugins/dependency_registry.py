from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class RegistryFormatError(ValueError):
    """Raised when a registry fragment does not match the expected format."""


def _ensure_mapping(value: Any, context: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    raise RegistryFormatError(
        f"{context} must be a mapping of keys to values; received {value!r} instead."
    )


def _normalize_requirement(item: Any) -> dict[str, Any]:
    """Normalize a dependency requirement entry into a canonical mapping."""
    if isinstance(item, str):
        return {"name": item}
    if isinstance(item, dict):
        if "name" in item and isinstance(item["name"], str):
            normalized = {"name": item["name"]}
            if item.get("version") is not None:
                normalized["version"] = item["version"]
            if item.get("exports_hash") is not None:
                normalized["exports_hash"] = item["exports_hash"]
            return normalized
        if len(item) == 1:
            key, value = next(iter(item.items()))
            if isinstance(value, dict):
                normalized = {"name": key}
                if value.get("version") is not None:
                    normalized["version"] = value["version"]
                if value.get("exports_hash") is not None:
                    normalized["exports_hash"] = value["exports_hash"]
                return normalized
    raise ValueError(f"Unsupported requirement entry: {item!r}")


def normalize_requirements(requirements: Any) -> list[dict[str, Any]]:
    """Normalize requirement entries into canonical mappings."""
    if not requirements:
        return []
    if isinstance(requirements, dict):
        normalized: list[dict[str, Any]] = []
        for name, meta in requirements.items():
            entry = {"name": name}
            if isinstance(meta, dict):
                if meta.get("version") is not None:
                    entry["version"] = meta["version"]
                if meta.get("exports_hash") is not None:
                    entry["exports_hash"] = meta["exports_hash"]
            normalized.append(entry)
        return normalized
    if isinstance(requirements, Iterable) and not isinstance(
        requirements, (str, bytes)
    ):
        return [_normalize_requirement(item) for item in requirements]
    return [_normalize_requirement(requirements)]


def normalize_dependency_registry(registry: Any) -> dict[str, dict[str, Any]]:
    """Normalize registry input into a mapping of dependency name -> metadata."""
    if not registry:
        return {}

    source = registry
    if isinstance(registry, dict) and "dependencies" in registry:
        source = registry["dependencies"]

    if not isinstance(source, dict):
        raise RegistryFormatError(
            "Dependency registry must be a mapping of dependency names to metadata. "
            f"Received {type(source).__name__}: {source!r}."
        )

    normalized: dict[str, dict[str, Any]] = {}
    for raw_name, raw_metadata in source.items():
        if not isinstance(raw_name, str) or not raw_name:
            raise RegistryFormatError(
                "Dependency registry keys must be non-empty strings. "
                f"Received key {raw_name!r}."
            )

        metadata = _ensure_mapping(
            raw_metadata,
            context=f"Dependency '{raw_name}' metadata",
        )

        entry: dict[str, Any] = {}
        for key in ("version", "exports_hash", "exports"):
            if key in metadata and metadata[key] is not None:
                entry[key] = metadata[key]
        if "requires" in metadata and metadata["requires"] is not None:
            entry["requires"] = normalize_requirements(metadata["requires"])
        normalized[raw_name] = entry

    return normalized


def merge_dependency_registries(registries: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """Merge multiple registry fragments into a single normalized mapping."""
    result: dict[str, dict[str, Any]] = {}

    for registry in registries or []:
        if not registry:
            continue

        normalized = normalize_dependency_registry(registry)
        for name, metadata in normalized.items():
            existing = result.get(name)
            if existing and "version" in metadata:
                existing_version = existing.get("version")
                new_version = metadata.get("version")
                if (
                    existing_version is not None
                    and new_version is not None
                    and existing_version != new_version
                ):
                    raise RegistryFormatError(
                        "Conflicting versions detected for dependency "
                        f"'{name}': existing={existing_version!r}, "
                        f"incoming={new_version!r}."
                    )

            merged = existing.copy() if existing else {}
            for key, value in metadata.items():
                if key == "requires":
                    existing_requires = normalize_requirements(
                        merged.get("requires", [])
                    )
                    new_requires = normalize_requirements(value)
                    merged["requires"] = _merge_requirements(
                        existing_requires, new_requires
                    )
                else:
                    merged[key] = value
            result[name] = merged

    return result


def _merge_requirements(
    existing: list[dict[str, Any]], new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {item["name"]: item for item in existing}
    for item in new:
        name = item["name"]
        if name not in merged:
            merged[name] = item
            continue
        merged_item = merged[name].copy()
        for key in ("version", "exports_hash"):
            if item.get(key) is not None:
                merged_item[key] = item[key]
        merged[name] = merged_item
    return list(merged.values())


def dependency_graph_cycles(
    registry: Any, current_service: str | None = None, current_requires: Any = None
) -> list[str]:
    """Return dependency cycles detected within the registry and current service."""
    normalized_registry = (
        registry
        if isinstance(registry, dict)
        else normalize_dependency_registry(registry)
    )
    graph: dict[str, list[str]] = {}

    for name, metadata in normalized_registry.items():
        requires = normalize_requirements(metadata.get("requires", []))
        graph[name] = [item["name"] for item in requires if item.get("name")]

    if current_service:
        requires = normalize_requirements(current_requires)
        graph[current_service] = [item["name"] for item in requires if item.get("name")]
        for req in graph[current_service]:
            graph.setdefault(req, [])

    return _find_cycles(graph)


def _find_cycles(graph: dict[str, list[str]]) -> list[str]:
    cycles: set[tuple[str, ...]] = set()
    stack: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            cycle = stack[stack.index(node) :] + [node]
            cycles.add(_canonical_cycle(tuple(cycle)))
            return
        if node in visited:
            return

        visiting.add(node)
        stack.append(node)
        for neighbor in graph.get(node, []):
            visit(neighbor)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in graph.keys():
        if node not in visited:
            visit(node)

    return [" -> ".join(cycle + (cycle[0],)) for cycle in sorted(cycles)]


def _canonical_cycle(cycle: tuple[str, ...]) -> tuple[str, ...]:
    if not cycle:
        return cycle
    unique = cycle[:-1]
    min_index = min(range(len(unique)), key=lambda i: unique[i])
    rotated = unique[min_index:] + unique[:min_index]
    return tuple(rotated)


class FilterModule:
    """Ansible filter plugin entrypoint."""

    def filters(self) -> dict[str, Any]:
        return {
            "normalize_dependency_registry": normalize_dependency_registry,
            "merge_dependency_registries": merge_dependency_registries,
            "normalize_requirements": normalize_requirements,
            "dependency_graph_cycles": dependency_graph_cycles,
        }
