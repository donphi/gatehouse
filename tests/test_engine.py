"""Integration tests for gatehouse.engine.scan_file."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gatehouse.engine import ScanResult, scan_file
from gatehouse.exceptions import GatehouseParseError


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestScanFilePassing:
    """Tests for files that should pass production schema."""

    def test_clean_production_file(self, tmp_project, passing_source):
        """A fully compliant file produces zero blocking violations."""
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file(
            passing_source,
            "src/clean_production.py",
            schema_path,
            skip_scope=True,
        )
        assert result.status == "passed"
        assert result.blocking_count == 0


class TestScanFileFailing:
    """Tests for files that should fail production schema."""

    def test_missing_header(self, tmp_project, failing_header_source):
        """File missing header block is rejected."""
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file(
            failing_header_source,
            "src/missing_header.py",
            schema_path,
            skip_scope=True,
        )
        assert result.status == "rejected"
        assert result.blocking_count > 0
        rule_ids = [v.rule_id for v in result.violations]
        assert "file-header" in rule_ids

    def test_missing_docstrings(self, tmp_project, failing_docstring_source):
        """File with undocumented functions is rejected."""
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file(
            failing_docstring_source,
            "src/missing_docstrings.py",
            schema_path,
            skip_scope=True,
        )
        assert result.status == "rejected"
        rule_ids = [v.rule_id for v in result.violations]
        assert "function-docstrings" in rule_ids

    def test_missing_main_guard(self, tmp_project, failing_main_guard_source):
        """File missing the main guard is rejected."""
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file(
            failing_main_guard_source,
            "src/missing_main_guard.py",
            schema_path,
            skip_scope=True,
        )
        assert result.status == "rejected"
        rule_ids = [v.rule_id for v in result.violations]
        assert "main-guard" in rule_ids

    def test_hardcoded_values(self, tmp_project, failing_hardcoded_source):
        """File with hardcoded values in functions is rejected."""
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file(
            failing_hardcoded_source,
            "src/hardcoded_values.py",
            schema_path,
            skip_scope=True,
        )
        assert result.status == "rejected"
        rule_ids = [v.rule_id for v in result.violations]
        assert "no-hardcoded-values" in rule_ids


class TestScanFileEdgeCases:
    """Tests for edge cases."""

    def test_syntax_error_raises(self, tmp_project):
        """Unparseable source raises GatehouseParseError."""
        bad_source = "def broken(\n    this is not valid python\n"
        schema_path = str(tmp_project / ".gate_schema.yaml")
        with pytest.raises(GatehouseParseError):
            scan_file(bad_source, "src/bad.py", schema_path, skip_scope=True)

    def test_no_schema_file(self):
        """Missing schema file returns passed (no enforcement)."""
        result = scan_file("x = 1\n", "test.py", "/nonexistent/schema.yaml")
        assert result.status == "passed"

    def test_scan_result_has_timing(self, tmp_project, passing_source):
        """ScanResult includes scan_ms timing."""
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file(
            passing_source,
            "src/clean.py",
            schema_path,
            skip_scope=True,
        )
        assert result.scan_ms >= 0

    def test_scan_result_has_schema_name(self, tmp_project, passing_source):
        """ScanResult includes the schema name."""
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file(
            passing_source,
            "src/clean.py",
            schema_path,
            skip_scope=True,
        )
        assert result.schema_name == "production"
