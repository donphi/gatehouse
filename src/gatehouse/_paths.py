"""Centralized path resolution for the gatehouse package.

This is the ONLY module that touches __file__ or computes directory paths.
Every other module imports from here. To override the auto-discovered
location, set the $GATE_HOME environment variable.
"""

import os
from pathlib import Path

# Auto-discover: all resource dirs are siblings of this file
_PACKAGE_DIR = Path(__file__).resolve().parent


def get_gate_home() -> Path:
    """Return the gate home directory (env override or auto-discovered)."""
    env = os.environ.get("GATE_HOME")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    return _PACKAGE_DIR


def rules_dir(gate_home: "Path | None" = None) -> Path:
    """Return the rules/ directory path."""
    return (gate_home or get_gate_home()) / "rules"


def schemas_dir(gate_home: "Path | None" = None) -> Path:
    """Return the schemas/ directory path."""
    return (gate_home or get_gate_home()) / "schemas"


def cli_dir() -> Path:
    """Return the cli/ directory path."""
    return _PACKAGE_DIR / "cli"


def plugins_dir(gate_home: "Path | None" = None) -> Path:
    """Return the plugins/ directory path."""
    return (gate_home or get_gate_home()) / "plugins"


def theme_path() -> Path:
    """Return the path to cli/theme.yaml."""
    return cli_dir() / "theme.yaml"
