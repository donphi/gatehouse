"""Shared fixtures for the Gatehouse test suite."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml


FIXTURES_DIR = Path(__file__).parent / "fixtures"
PASSING_DIR = FIXTURES_DIR / "passing"
FAILING_DIR = FIXTURES_DIR / "failing"
EDGE_CASES_DIR = FIXTURES_DIR / "edge_cases"


@pytest.fixture()
def gate_home() -> Path:
    """Return the gate home directory (package root)."""
    from gatehouse._paths import get_gate_home

    return get_gate_home()


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with a .gate_schema.yaml."""
    config: dict[str, Any] = {
        "schema": "production",
        "rule_overrides": {},
        "logging": {"enabled": False},
    }
    schema_file = tmp_path / ".gate_schema.yaml"
    with open(schema_file, "w", encoding="utf-8") as fh:
        yaml.dump(config, fh, default_flow_style=False)
    return tmp_path


@pytest.fixture()
def passing_source() -> str:
    """Return the contents of the clean production fixture."""
    return (PASSING_DIR / "clean_production.py").read_text(encoding="utf-8")


@pytest.fixture()
def failing_header_source() -> str:
    """Return source that is missing the file header."""
    return (FAILING_DIR / "missing_header.py").read_text(encoding="utf-8")


@pytest.fixture()
def failing_docstring_source() -> str:
    """Return source with functions missing docstrings."""
    return (FAILING_DIR / "missing_docstrings.py").read_text(encoding="utf-8")


@pytest.fixture()
def failing_main_guard_source() -> str:
    """Return source missing the main guard."""
    return (FAILING_DIR / "missing_main_guard.py").read_text(encoding="utf-8")


@pytest.fixture()
def failing_hardcoded_source() -> str:
    """Return source with hardcoded values in functions."""
    return (FAILING_DIR / "hardcoded_values.py").read_text(encoding="utf-8")
