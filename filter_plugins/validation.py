"""Validation filters shared by runtime templates."""

from __future__ import annotations

from typing import Any, Iterable


def _extract_name(item: Any) -> str | None:
    """Return the stringified ``name`` attribute from a template item."""

    if item is None:
        return None

    if isinstance(item, dict):
        name = item.get("name")
    else:
        name = getattr(item, "name", None)

    if name is None:
        return None

    value = str(name)
    return value if value else None


def ensure_defined(
    items: Any,
    defined_names: Iterable[str] | None,
    context: str = "item",
) -> Any:
    """Ensure every referenced item exists in the provided name catalogue.

    Parameters
    ----------
    items:
        Iterable of objects or mappings containing a ``name`` attribute.
    defined_names:
        Collection of known/declared names.
    context:
        Human-readable description used when reporting missing names.

    Returns
    -------
    Any
        The original ``items`` iterable so the template can continue
        processing without additional transformations.

    Raises
    ------
    ValueError
        If any ``items`` entry references a name that is not present in
        ``defined_names``.
    """

    if not items:
        return [] if items in (None, []) else items

    known = {str(name) for name in (defined_names or []) if name}
    missing: set[str] = set()

    try:
        iterator = list(items)  # type: ignore[arg-type]
    except TypeError:  # pragma: no cover - defensive guard
        iterator = [items]

    for item in iterator:
        name = _extract_name(item)
        if name and name not in known:
            missing.add(name)

    if missing:
        available = ", ".join(sorted(known)) if known else "none"
        missing_display = ", ".join(sorted(missing))
        raise ValueError(
            f"Unknown {context}(s): {missing_display}. Available: {available}."
        )

    return items


class FilterModule:
    """Expose validation helpers to Ansible templates."""

    def filters(self) -> dict[str, Any]:
        return {
            "ensure_defined": ensure_defined,
        }
