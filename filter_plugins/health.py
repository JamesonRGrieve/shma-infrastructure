"""Health command helpers shared between Ansible and CI tooling."""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping


DEFAULT_COMMAND = ["true"]
DEFAULT_INTERVAL = "10s"
DEFAULT_TIMEOUT = "5s"
DEFAULT_RETRIES = 3


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


def _get_value(source: Any | None, key: str, default: Any) -> Any:
    if not source:
        return default

    if isinstance(source, Mapping):
        return source.get(key, default)

    return getattr(source, key, default)


def _duration_to_seconds(value: Any, default: Any) -> int:
    value = value if value is not None else default

    if isinstance(value, (int, float)):
        return int(value)

    if not value:
        return int(default)

    text = str(value).strip().lower()
    multiplier = 1

    if text.endswith("ms"):
        multiplier = 0.001
        text = text[:-2]
    elif text.endswith("s"):
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 60
        text = text[:-1]

    try:
        return int(float(text) * multiplier)
    except (TypeError, ValueError):
        return int(default)


def normalize_health(health: Any | None) -> dict[str, Any]:
    interval = _get_value(health, "interval", DEFAULT_INTERVAL)
    timeout = _get_value(health, "timeout", DEFAULT_TIMEOUT)
    retries = _get_value(health, "retries", DEFAULT_RETRIES)
    start_period = _get_value(health, "start_period", None)

    interval_value = DEFAULT_INTERVAL if interval is None else interval
    timeout_value = DEFAULT_TIMEOUT if timeout is None else timeout

    return {
        "command": get_health_command(health),
        "interval": str(interval_value),
        "timeout": str(timeout_value),
        "retries": int(retries if retries is not None else DEFAULT_RETRIES),
        "start_period": start_period,
        "interval_seconds": _duration_to_seconds(interval, DEFAULT_INTERVAL),
        "timeout_seconds": _duration_to_seconds(timeout, DEFAULT_TIMEOUT),
    }


def health_command_filter(health: Any | None) -> List[str]:
    return get_health_command(health)


def normalize_health_filter(health: Any | None) -> dict[str, Any]:
    return normalize_health(health)


class FilterModule:
    """Expose health command helpers to Ansible."""

    def filters(self) -> dict[str, Any]:
        return {
            "health_command": health_command_filter,
            "normalize_health": normalize_health_filter,
        }
