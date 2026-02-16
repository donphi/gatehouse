"""Custom exceptions for Gatehouse enforcement.

Defines the exception hierarchy used across the Gatehouse engine,
import hook, and plugin system. All exceptions are importable from
the top-level ``gatehouse`` package.

Exceptions:
    GatehouseViolationError — Raised by the import hook (auto.py) when
        blocking violations are found. Subclasses ImportError.
    PluginError — Raised when a custom check plugin fails during
        execution. Captures plugin path and underlying error.
    GatehouseParseError — Raised when LibCST cannot parse a source
        file. Wraps the original parse exception.
"""

from __future__ import annotations

from typing import Any

from gatehouse.lib import config


class GatehouseViolationError(ImportError):
    """Raised when a module fails Gatehouse schema enforcement.

    Inherits from ImportError so the import system treats it as a
    failed import. Carries structured violation data and formats
    output like a SyntaxError for IDE/tool compatibility.
    """

    def __init__(
        self,
        filepath: str,
        violations: list[dict[str, Any]],
        schema_name: str = "",
    ) -> None:
        """Initialize with violation details.

        Args:
            filepath: Path to the file that failed validation.
            violations: List of violation dicts with line, message, fix keys.
            schema_name: Name of the schema that was enforced.
        """
        self.filepath = filepath
        self.violations = violations
        self.schema_name = schema_name
        self.blocking_count = len(violations)
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Build a SyntaxError-style message from violations."""
        summary_tpl = config.get_str("messages.violation_summary")
        line_tpl = config.get_str("messages.violation_line_format")
        fix_prefix = config.get_str("messages.fix_prefix")
        fallback_line = config.get_int("defaults.fallback_line")

        parts: list[str] = [
            summary_tpl.format(
                count=self.blocking_count, filepath=self.filepath
            )
        ]
        for v in self.violations:
            line = v.get("line", fallback_line)
            message = v.get("message", "violation")
            parts.append(f"  {line_tpl.format(line=line, message=message)}")
            fix = v.get("fix", "")
            if fix:
                parts.append(
                    f"    {fix_prefix}{fix.strip().splitlines()[0]}"
                )
        return "\n".join(parts)


class PluginError(Exception):
    """Raised when a custom check plugin fails during execution.

    Captures the plugin path and the underlying error for diagnostics.
    Subprocess isolation for plugins is planned for v0.4.0.
    """

    def __init__(
        self, plugin_path: str, rule_id: str, original_error: Exception
    ) -> None:
        """Initialize with plugin error details.

        Args:
            plugin_path: Path to the plugin file that failed.
            rule_id: The rule ID that triggered the plugin.
            original_error: The underlying exception from the plugin.
        """
        self.plugin_path = plugin_path
        self.rule_id = rule_id
        self.original_error = original_error
        msg = config.get_str("messages.plugin_error")
        super().__init__(msg.format(rule_id=rule_id, error=original_error))


class GatehouseParseError(Exception):
    """Raised when LibCST cannot parse a source file.

    A file that cannot be parsed is treated as a blocking error
    to prevent non-parseable code from silently passing.
    """

    def __init__(self, filepath: str, original_error: Exception) -> None:
        """Initialize with parse error details.

        Args:
            filepath: Path to the file that failed parsing.
            original_error: The underlying parse exception.
        """
        self.filepath = filepath
        self.original_error = original_error
        msg = config.get_str("messages.parse_error")
        super().__init__(msg.format(filepath=filepath, error=original_error))
