"""theme — ANSI colour theme loading and text colourisation.

Reads colour definitions lazily from ``cli/theme.yaml`` on first access and
caches the resolved role-to-ANSI-code mapping for the process lifetime.
Colourisation is suppressed automatically when the output stream is not a TTY,
so piped and redirected output stays clean.  All public helpers delegate to a
module-level ``Theme`` singleton.
"""

from __future__ import annotations

import sys
from typing import Any, Optional, Union

from gatehouse._paths import theme_path
from gatehouse.lib.yaml_loader import load_yaml


class Theme:
    """Lazy-loaded ANSI colour theme from cli/theme.yaml.

    The theme file is read once on first access.  All subsequent calls
    use the cached result.

    Attributes:
        resolved: Mapping of semantic role names to ANSI escape codes.
    """

    def __init__(self) -> None:
        """Initialize with deferred loading."""
        self._resolved: Optional[dict[str, str]] = None

    def _load(self) -> dict[str, str]:
        """Load and resolve the role-to-ANSI mapping so colour data is only read from disk once."""
        tp = theme_path()
        if not tp.is_file():
            return {}
        raw = load_yaml(str(tp))
        if not raw:
            return {}
        ansi: dict[str, str] = raw.get("ansi", {})
        roles: dict[str, str] = raw.get("roles", {})
        resolved: dict[str, str] = {}
        for role, color_name in roles.items():
            resolved[role] = ansi.get(color_name, "")
        resolved["bold"] = ansi.get("bold", "")
        resolved["dim"] = ansi.get("dim", "")
        resolved["reset"] = ansi.get("reset", "")
        return resolved

    @property
    def resolved(self) -> dict[str, str]:
        """Return the resolved role-to-ANSI-code mapping, loading on first access."""
        if self._resolved is None:
            self._resolved = self._load()
        return self._resolved

    def colorize(self, text: str, role: str, *, stream: Any = None) -> str:
        """Wrap text in ANSI color codes for a semantic role.

        Args:
            text: The text to colorize.
            role: Semantic role name (e.g., 'error', 'fix', 'warning').
            stream: The output stream to check for TTY. Defaults to sys.stderr.

        Returns:
            Colorized text if the stream is a TTY, plain text otherwise.
        """
        target = stream or sys.stderr
        if not hasattr(target, "isatty") or not target.isatty():
            return text
        code = self.resolved.get(role, "")
        if not code:
            return text
        reset = self.resolved.get("reset", "")
        return f"{code}{text}{reset}"

    def code(self, role: str, *, stream: Any = None) -> str:
        """Return the raw ANSI escape code for a role.

        Args:
            role: Semantic role name.
            stream: The output stream to check for TTY. Defaults to sys.stderr.

        Returns:
            ANSI escape code string, or empty string if not a TTY.
        """
        target = stream or sys.stderr
        if not hasattr(target, "isatty") or not target.isatty():
            return ""
        return self.resolved.get(role, "")


_theme = Theme()


def colorize(text: str, role: str, *, stream: Any = None) -> str:
    """Wrap text in ANSI codes using the global theme singleton.

    Args:
        text: The text to colorize.
        role: Semantic role name.
        stream: Output stream for TTY check. Defaults to sys.stderr.

    Returns:
        Colorized text if stream is a TTY, plain text otherwise.
    """
    return _theme.colorize(text, role, stream=stream)


def code(role: str, *, stream: Any = None) -> str:
    """Return raw ANSI escape code from the global theme singleton.

    Args:
        role: Semantic role name.
        stream: Output stream for TTY check. Defaults to sys.stderr.

    Returns:
        ANSI escape code string, or empty string.
    """
    return _theme.code(role, stream=stream)
