"""yaml_loader — unified YAML loading for all Gatehouse configuration files.

Wraps PyYAML's ``safe_load`` behind a single entry point shared by the engine,
CLI, and all library modules.  A dedicated loader exists so that encoding,
error handling, and safe-parsing choices are defined in one place rather than
scattered across callers.  PyYAML is a required dependency — no fallback parser
is provided.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import yaml


def load_yaml(path: Union[str, Path]) -> Optional[dict[str, Any]]:
    """Load a YAML file and return its contents as a dict.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed YAML contents, or None if the file is empty.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file contains invalid YAML.
    """
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_yaml_string(text: str) -> Optional[dict[str, Any]]:
    """Parse a YAML string and return its contents as a dict.

    Args:
        text: YAML content as a string.

    Returns:
        Parsed YAML contents, or None if the string is empty.

    Raises:
        yaml.YAMLError: If the string contains invalid YAML.
    """
    return yaml.safe_load(text)
