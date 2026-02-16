"""rules — rule loading, schema resolution, and project-level overrides.

Handles YAML rule files, schema manifests with inheritance via the
``extends`` key, and project-level configuration from ``.gate_schema.yaml``.
Schema inheritance allows a child schema to include all rules from a parent
and selectively override severity, enabled status, or parameters.  Project
config layering then applies repository-specific ``rule_overrides`` on top
of the fully resolved rule set.

Design notes:
    Inheritance resolution is recursive: the parent chain is resolved first,
    then child rules are merged on top.  Later rules override earlier ones
    when rule IDs collide, giving the most-specific schema the final say.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, Union

from gatehouse._paths import get_gate_home, rules_dir, schemas_dir
from gatehouse.lib import config
from gatehouse.lib.yaml_loader import load_yaml


def find_gate_home() -> Optional[Path]:
    """Resolve gate home directory (auto-discovered or $GATE_HOME override).

    Returns:
        The gate home Path if the directory exists, else None.
    """
    home = get_gate_home()
    if home.is_dir():
        return home
    return None


def load_rule(rule_id: str, gate_home: Path) -> Optional[dict[str, Any]]:
    """Load a single rule YAML file by ID.

    Args:
        rule_id: The rule identifier (matches filename without extension).
        gate_home: The gate home directory for rule discovery.

    Returns:
        Parsed rule dict, or None if the rule file does not exist.
    """
    ext = config.get_str("filenames.rule_extension")
    rule_path = rules_dir(gate_home) / f"{rule_id}{ext}"
    if not rule_path.is_file():
        return None
    return load_yaml(str(rule_path))


def load_schema(schema_name: str, gate_home: Path) -> Optional[dict[str, Any]]:
    """Load a schema manifest by name.

    Args:
        schema_name: The schema identifier (matches filename without extension).
        gate_home: The gate home directory for schema discovery.

    Returns:
        Parsed schema dict, or None if the schema file does not exist.
    """
    ext = config.get_str("filenames.schema_extension")
    schema_path = schemas_dir(gate_home) / f"{schema_name}{ext}"
    if not schema_path.is_file():
        return None
    return load_yaml(str(schema_path))


def resolve_rules(
    schema_data: dict[str, Any],
    gate_home: Path,
) -> list[dict[str, Any]]:
    """Resolve all rule references from a schema into full rule objects.

    Handles schema inheritance via 'extends' and applies severity/enabled/params
    overrides from the schema definition.

    Args:
        schema_data: Parsed schema YAML dict.
        gate_home: The gate home directory for rule discovery.

    Returns:
        List of resolved rule objects with full rule data and overrides applied.
    """
    default_severity = config.get_str("defaults.severity")
    default_enabled = config.get("defaults.enabled")
    msg_tpl = config.get_str("messages.rule_not_found")

    rules: list[dict[str, Any]] = []

    if schema_data.get("extends"):
        parent = load_schema(schema_data["extends"], gate_home)
        if parent:
            rules = resolve_rules(parent, gate_home)

    schema_rules = schema_data.get("rules", [])
    if isinstance(schema_rules, list):
        for entry in schema_rules:
            if isinstance(entry, str):
                entry = {"id": entry}
            rule_id = entry.get("id")
            if not rule_id:
                continue

            rule_data = load_rule(rule_id, gate_home)
            if not rule_data:
                sys.stderr.write(
                    msg_tpl.format(
                        rule_id=rule_id, path=rules_dir(gate_home)
                    ) + "\n"
                )
                continue

            defaults = rule_data.get("defaults", {})
            rule_obj: dict[str, Any] = {
                "id": rule_id,
                "rule_data": rule_data,
                "severity": entry.get(
                    "severity", defaults.get("severity", default_severity)
                ),
                "enabled": entry.get(
                    "enabled", defaults.get("enabled", default_enabled)
                ),
                "params": entry.get("params", {}),
            }

            existing_ids = [r["id"] for r in rules]
            if rule_id in existing_ids:
                idx = existing_ids.index(rule_id)
                rules[idx] = rule_obj
            else:
                rules.append(rule_obj)

    for entry in schema_data.get("additional_rules", []):
        if isinstance(entry, str):
            entry = {"id": entry}
        rule_id = entry.get("id")
        if not rule_id:
            continue
        rule_data = load_rule(rule_id, gate_home)
        if not rule_data:
            sys.stderr.write(
                msg_tpl.format(
                    rule_id=rule_id, path=rules_dir(gate_home)
                ) + "\n"
            )
            continue
        defaults = rule_data.get("defaults", {})
        rule_obj = {
            "id": rule_id,
            "rule_data": rule_data,
            "severity": entry.get(
                "severity", defaults.get("severity", default_severity)
            ),
            "enabled": entry.get(
                "enabled", defaults.get("enabled", default_enabled)
            ),
            "params": {},
        }
        rules.append(rule_obj)

    return rules


def load_project_config(
    schema_path: Union[str, Path],
) -> Optional[dict[str, Any]]:
    """Load the project's .gate_schema.yaml configuration.

    Args:
        schema_path: Path to the .gate_schema.yaml file.

    Returns:
        Parsed config dict, or None if loading fails.
    """
    try:
        return load_yaml(str(schema_path))
    except FileNotFoundError:
        return None


def apply_project_overrides(
    rules: list[dict[str, Any]],
    project_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply rule_overrides from the project config to resolved rules.

    Modifies rules in-place for severity, enabled, and params overrides.

    Args:
        rules: List of resolved rule objects.
        project_config: Parsed .gate_schema.yaml config.

    Returns:
        The same rules list with overrides applied in-place.
    """
    overrides = project_config.get("rule_overrides", {})
    if not overrides:
        return rules

    for rule in rules:
        rule_id = rule["id"]
        if rule_id in overrides:
            ovr = overrides[rule_id]
            if "severity" in ovr:
                rule["severity"] = ovr["severity"]
            if "enabled" in ovr:
                rule["enabled"] = ovr["enabled"]
            if "params" in ovr:
                rule["params"].update(ovr["params"])

    return rules
