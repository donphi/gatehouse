"""Integration tests for gatehouse.cli command dispatch."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


CLI_MODULE = "gatehouse.cli.main"
PYTHON = sys.executable


class TestCLIEntryPoint:
    """Tests for 'python -m gatehouse.cli.main' dispatch."""

    def test_help_flag(self) -> None:
        """--help prints usage and exits 0."""
        result = subprocess.run(
            [PYTHON, "-m", CLI_MODULE, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "gatehouse" in result.stdout.lower()

    def test_version_flag(self) -> None:
        """--version prints the version string."""
        result = subprocess.run(
            [PYTHON, "-m", CLI_MODULE, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "0.3.0" in result.stdout

    def test_unknown_command(self) -> None:
        """Unknown subcommand prints help (not crash)."""
        result = subprocess.run(
            [PYTHON, "-m", CLI_MODULE, "nonexistent-cmd"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0 or "usage" in result.stdout.lower() or "error" in result.stderr.lower()

    def test_status_subcommand(self) -> None:
        """'status' subcommand runs without crash."""
        result = subprocess.run(
            [PYTHON, "-m", CLI_MODULE, "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_list_rules_subcommand(self) -> None:
        """'list-rules' subcommand runs without crash."""
        result = subprocess.run(
            [PYTHON, "-m", CLI_MODULE, "list-rules"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
