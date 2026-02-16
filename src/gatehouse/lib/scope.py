"""scope — file-level scope checking and per-path schema resolution.

Evaluates whether a given file falls within a schema's enforcement perimeter.
Schemas declare ``gated_paths`` (directories to enforce) and ``exempt_paths`` /
``exempt_files`` (exclusions).  When a project config contains per-path
overrides, ``resolve_effective_schema`` maps a filepath to the correct schema
name — or to ``None`` if the path is explicitly exempted.
"""

from __future__ import annotations

import fnmatch
import os
from typing import Any, Optional

from gatehouse.lib import config


def is_file_in_scope(
    filepath: str,
    schema_data: dict[str, Any],
    project_config: dict[str, Any],
) -> bool:
    """Check if a file is within the gated scope of a schema.

    Args:
        filepath: Path to the file being checked.
        schema_data: Parsed schema YAML dict with scope settings.
        project_config: Parsed .gate_schema.yaml config.

    Returns:
        True if the file should be checked, False if exempt.
    """
    scope: dict[str, Any] = schema_data.get("scope", {})
    gated_paths: list[str] = scope.get("gated_paths", [])
    exempt_paths: list[str] = scope.get("exempt_paths", [])
    exempt_files: list[str] = scope.get("exempt_files", [])

    filename = os.path.basename(filepath)

    if filename in exempt_files:
        return False

    for ep in exempt_paths:
        if filepath.startswith(ep) or f"/{ep}" in filepath:
            return False

    if not gated_paths:
        return True

    for gp in gated_paths:
        if filepath.startswith(gp) or f"/{gp}" in filepath:
            return True

    return False


def resolve_effective_schema(
    filepath: str,
    project_config: dict[str, Any],
) -> Optional[str]:
    """Resolve the effective schema name for a file after applying overrides.

    Checks per-path overrides in the project config. Returns None if the
    file is exempt (schema override set to null).

    Args:
        filepath: Path to the file being checked.
        project_config: Parsed .gate_schema.yaml config.

    Returns:
        Schema name string, or None if the file is exempt.
    """
    base_schema: str = project_config.get(
        "schema", config.get_str("defaults.schema_name")
    )
    overrides: dict[str, Any] = project_config.get("overrides", {})

    for pattern, ovr in overrides.items():
        if ovr and ovr.get("schema") is None:
            if (
                fnmatch.fnmatch(filepath, pattern)
                or fnmatch.fnmatch(os.path.basename(filepath), pattern)
            ):
                return None
        elif ovr and ovr.get("schema"):
            if (
                fnmatch.fnmatch(filepath, pattern)
                or filepath.startswith(pattern.rstrip("*"))
            ):
                return ovr["schema"]

    return base_schema
