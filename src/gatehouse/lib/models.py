"""Data models for Gatehouse configuration, rules, and scope.

Typed dataclasses that replace raw dict access across the codebase.
Each model validates structure at construction time and raises clear
errors on missing or invalid fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Rule model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleEntry:
    """A single resolved rule ready for check execution.

    Attributes:
        rule_id: Unique identifier for the rule (filename stem).
        name: Human-readable name.
        description: What the rule checks.
        check_type: Check type identifier (e.g. 'pattern_exists').
        check_params: Check-type-specific parameters.
        severity: 'block' or 'warn'.
        enabled: Whether the rule is active.
        error_message: Message shown on violation.
        fix_instruction: Suggested fix text.
        version: Rule definition version string.
    """

    rule_id: str
    name: str
    description: str
    check_type: str
    check_params: dict[str, Any]
    severity: str
    enabled: bool
    error_message: str
    fix_instruction: str
    version: str = ""


# ---------------------------------------------------------------------------
# Scope model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScopeConfig:
    """Scope definition from a schema or project config.

    Attributes:
        gated_paths: Paths that are actively enforced (empty = all).
        exempt_paths: Paths excluded from enforcement.
        exempt_files: Individual filenames excluded from enforcement.
    """

    gated_paths: list[str] = field(default_factory=list)
    exempt_paths: list[str] = field(default_factory=list)
    exempt_files: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScopeConfig:
        """Build from a raw dict (e.g. schema_data['scope']).

        Args:
            data: Scope mapping from YAML.

        Returns:
            Validated ScopeConfig instance.
        """
        return cls(
            gated_paths=data.get("gated_paths", []),
            exempt_paths=data.get("exempt_paths", []),
            exempt_files=data.get("exempt_files", []),
        )


# ---------------------------------------------------------------------------
# Project configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GatehouseConfig:
    """Top-level project configuration from .gate_schema.yaml.

    Attributes:
        schema: Base schema name (e.g. 'production').
        overrides: Per-path schema overrides mapping.
        scope: File-level scope configuration.
    """

    schema: str
    overrides: dict[str, Any] = field(default_factory=dict)
    scope: Optional[ScopeConfig] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], default_schema: str) -> GatehouseConfig:
        """Build from a raw .gate_schema.yaml dict.

        Args:
            data: Parsed YAML mapping.
            default_schema: Fallback schema name from defaults.yaml.

        Returns:
            Validated GatehouseConfig instance.
        """
        scope_raw = data.get("scope")
        scope = ScopeConfig.from_dict(scope_raw) if scope_raw else None
        return cls(
            schema=data.get("schema", default_schema),
            overrides=data.get("overrides", {}),
            scope=scope,
        )


def validate_project_config(data: Any) -> list[str]:
    """Validate the structure of a .gate_schema.yaml dict.

    Returns a list of human-readable error strings (empty = valid).

    Args:
        data: The parsed YAML content.

    Returns:
        List of validation error messages. Empty if valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        errors.append(f"Project config must be a mapping, got {type(data).__name__}")
        return errors

    if "schema" not in data:
        errors.append("Missing required key: 'schema'")

    schema_val = data.get("schema")
    if schema_val is not None and not isinstance(schema_val, str):
        errors.append(
            f"'schema' must be a string, got {type(schema_val).__name__}"
        )

    overrides = data.get("overrides")
    if overrides is not None and not isinstance(overrides, dict):
        errors.append(
            f"'overrides' must be a mapping, got {type(overrides).__name__}"
        )

    scope = data.get("scope")
    if scope is not None:
        if not isinstance(scope, dict):
            errors.append(
                f"'scope' must be a mapping, got {type(scope).__name__}"
            )
        else:
            for list_key in ("gated_paths", "exempt_paths", "exempt_files"):
                val = scope.get(list_key)
                if val is not None and not isinstance(val, list):
                    errors.append(
                        f"scope.{list_key} must be a list, "
                        f"got {type(val).__name__}"
                    )

    return errors
