"""Health command helpers shared between Ansible and CI tooling."""

from __future__ import annotations

from typing import Any, Iterable, List


DEFAULT_COMMAND = ["true"]


def get_health_command(health: Any | None) -> List[str]:
    """Return the normalized health command list.

    Parameters
    ----------
    health:
        Mapping or object that may contain a ``cmd`` attribute/entry.

    Returns
    -------
    list[str]
        Sanitised command arguments with all entries coerced to strings.

    Raises
    ------
    ValueError
        If ``health.cmd`` exists but is not a list/iterable of arguments.
    """

    if not health:
        return DEFAULT_COMMAND.copy()

    # Support both dict-style and attribute-style access.
    command: Any | None = None
    if isinstance(health, dict):
        command = health.get("cmd")
    else:
        command = getattr(health, "cmd", None)

    if command is None:
        return DEFAULT_COMMAND.copy()

    if not isinstance(command, Iterable) or isinstance(command, (str, bytes)):
        raise ValueError("health.cmd must be an iterable of arguments")

    return [str(arg) for arg in command]


def health_command_filter(health: Any | None) -> List[str]:
    return get_health_command(health)


class FilterModule:
    """Expose health command helpers to Ansible."""

    def filters(self) -> dict[str, Any]:
        return {
            "health_command": health_command_filter,
        }
