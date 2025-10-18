"""Filters for working with dependency registries and requirements."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _normalize_requirement(item: Any) -> dict[str, Any]:
    """Normalize a dependency requirement entry into a canonical mapping."""
    if isinstance(item, str):
        return {"name": item}
    if isinstance(item, dict):
        # Accept either already normalized mappings or minimal dicts.
        if "name" in item and isinstance(item["name"], str):
            normalized = {"name": item["name"]}
            if item.get("version") is not None:
                normalized["version"] = item["version"]
            if item.get("exports_hash") is not None:
                normalized["exports_hash"] = item["exports_hash"]
            return normalized
        # When provided as {service_name: {...}} allow the key to serve as name.
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
        # Interpret mapping of name -> metadata.
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


def _normalize_dependency_entry(entry: Any) -> dict[str, Any]:
    if entry is None:
        return {}
    if isinstance(entry, dict):
        normalized: dict[str, Any] = {}
        for key in ("version", "exports_hash", "exports"):
            if entry.get(key) is not None:
                normalized[key] = entry[key]
        if "requires" in entry:
            normalized["requires"] = normalize_requirements(entry["requires"])
        return normalized
    if isinstance(entry, str):
        return {"version": entry} if entry else {}
    raise ValueError(f"Unsupported dependency entry: {entry!r}")


def normalize_dependency_registry(registry: Any) -> dict[str, dict[str, Any]]:
    """Normalize registry input into a mapping of dependency name -> metadata."""
    if not registry:
        return {}

    if isinstance(registry, (str, bytes)):
        name = registry.decode() if isinstance(registry, bytes) else registry
        return {name: {}}

    if isinstance(registry, dict):
        if "dependencies" in registry:
            return normalize_dependency_registry(registry["dependencies"])
        normalized: dict[str, dict[str, Any]] = {}
        for name, value in registry.items():
            if isinstance(value, dict) and "name" in value and value["name"] != name:
                # Allow nested entries storing the name within their mapping.
                entry_name = value["name"]
                normalized[entry_name] = _normalize_dependency_entry(value)
            else:
                normalized[name] = _normalize_dependency_entry(value)
        return normalized

    if isinstance(registry, Iterable) and not isinstance(registry, (str, bytes)):
        normalized: dict[str, dict[str, Any]] = {}
        for item in registry:
            if isinstance(item, str):
                normalized[item] = {}
            elif isinstance(item, dict):
                if "name" not in item:
                    raise ValueError(f"Dependency entry missing name: {item!r}")
                name = item["name"]
                normalized[name] = _normalize_dependency_entry(item)
            else:
                raise ValueError(f"Unsupported dependency registry entry: {item!r}")
        return normalized

    raise ValueError(f"Unsupported dependency registry value: {registry!r}")


def merge_dependency_registries(registries: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """Merge multiple registry fragments into a single normalized mapping."""
    result: dict[str, dict[str, Any]] = {}
    for registry in registries or []:
        if not registry:
            continue
        normalized = normalize_dependency_registry(registry)
        for name, metadata in normalized.items():
            existing = result.get(name, {})
            merged = existing.copy()
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
