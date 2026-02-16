"""config — lazy-loaded, typed accessor for Gatehouse defaults.

Reads ``config/defaults.yaml`` on first access and caches the result for the
lifetime of the process.  Typed accessor helpers (``get_str``, ``get_int``,
``get_list``) enforce expected types at the call-site so that configuration
mismatches surface as early and loudly as possible.  No module-level side
effects — config is loaded lazily.

Design notes:
    Configuration is loaded once and cached in a module-level sentinel so that
    every caller shares the same snapshot and the YAML file is only read from
    disk a single time.  The ``reset()`` function exists solely for test
    isolation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULTS: dict[str, Any] | None = None

_CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "defaults.yaml"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_defaults() -> dict[str, Any]:
    """Load and cache the defaults.yaml configuration file.

    Returns:
        The full configuration dictionary.

    Raises:
        FileNotFoundError: If defaults.yaml is missing.
        yaml.YAMLError: If defaults.yaml contains invalid YAML.
    """
    global _DEFAULTS  # noqa: PLW0603
    if _DEFAULTS is None:
        with open(_CONFIG_FILE, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            msg = f"defaults.yaml must be a YAML mapping, got {type(data).__name__}"
            raise TypeError(msg)
        _DEFAULTS = data
    return _DEFAULTS


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------


def get(dotted_key: str) -> Any:
    """Access a nested config value using dot notation.

    Args:
        dotted_key: A dot-separated path like ``"severities.block"``.

    Returns:
        The value at the specified path.

    Raises:
        KeyError: If any segment of the path is missing.
    """
    parts = dotted_key.split(".")
    node: Any = load_defaults()
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            msg = f"Config key not found: {dotted_key!r} (missing segment: {part!r})"
            raise KeyError(msg)
        node = node[part]
    return node


def get_str(dotted_key: str) -> str:
    """Return a config value as a string.

    Args:
        dotted_key: A dot-separated path.

    Returns:
        The string value.

    Raises:
        KeyError: If the key is missing.
        TypeError: If the value is not a string.
    """
    value = get(dotted_key)
    if not isinstance(value, str):
        msg = f"Expected str for {dotted_key!r}, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def get_int(dotted_key: str) -> int:
    """Return a config value as an integer.

    Args:
        dotted_key: A dot-separated path.

    Returns:
        The integer value.

    Raises:
        KeyError: If the key is missing.
        TypeError: If the value is not an integer.
    """
    value = get(dotted_key)
    if not isinstance(value, int):
        msg = f"Expected int for {dotted_key!r}, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def get_list(dotted_key: str) -> list[Any]:
    """Return a config value as a list.

    Args:
        dotted_key: A dot-separated path.

    Returns:
        The list value.

    Raises:
        KeyError: If the key is missing.
        TypeError: If the value is not a list.
    """
    value = get(dotted_key)
    if not isinstance(value, list):
        msg = f"Expected list for {dotted_key!r}, got {type(value).__name__}"
        raise TypeError(msg)
    return value


# ---------------------------------------------------------------------------
# Test utilities
# ---------------------------------------------------------------------------


def reset() -> None:
    """Clear the cached config (used by tests)."""
    global _DEFAULTS  # noqa: PLW0603
    _DEFAULTS = None
