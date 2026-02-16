"""Centralized path resolution for the gatehouse package.

This is the ONLY module that touches __file__ or computes directory paths.
Every other module imports from here. To override the auto-discovered
location, set the $GATE_HOME environment variable.

Environment variables:
    GATE_HOME — Override the default gate home directory. When set to
        an existing directory path, all rule/schema/plugin lookups use
        that directory instead of the package-internal default.
"""

import os
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def _cfg(key: str) -> str:
    """Lazy config accessor to avoid circular imports at module level.

    Args:
        key: Dotted config key.

    Returns:
        The string config value.
    """
    from gatehouse.lib.config import get_str

    return get_str(key)


def get_gate_home() -> Path:
    """Return the gate home directory (env override or auto-discovered)."""
    env = os.environ.get(_cfg("env_vars.gate_home"))
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    return _PACKAGE_DIR


def rules_dir(gate_home: "Path | None" = None) -> Path:
    """Return the rules/ directory path."""
    return (gate_home or get_gate_home()) / _cfg("directories.rules")


def schemas_dir(gate_home: "Path | None" = None) -> Path:
    """Return the schemas/ directory path."""
    return (gate_home or get_gate_home()) / _cfg("directories.schemas")


def cli_dir() -> Path:
    """Return the cli/ directory path."""
    return _PACKAGE_DIR / _cfg("directories.cli")


def plugins_dir(gate_home: "Path | None" = None) -> Path:
    """Return the plugins/ directory path."""
    return (gate_home or get_gate_home()) / _cfg("directories.plugins")


def config_dir() -> Path:
    """Return the config/ directory path."""
    return _PACKAGE_DIR / "config"


def theme_path() -> Path:
    """Return the path to cli/theme.yaml."""
    return cli_dir() / _cfg("filenames.theme")
