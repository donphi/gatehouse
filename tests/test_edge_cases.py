"""Edge-case tests for Gatehouse boundary conditions."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gatehouse.engine import scan_file
from gatehouse.exceptions import GatehouseParseError
from gatehouse.lib.formatter import format_violations_json, format_summary_stderr
from gatehouse.lib.yaml_loader import load_yaml


FIXTURES_DIR = Path(__file__).parent / "fixtures"
EDGE_DIR = FIXTURES_DIR / "edge_cases"


class TestEmptyFile:
    """Engine behavior on empty files."""

    def test_empty_source_string(self, tmp_project: Path) -> None:
        """An empty string still gets evaluated (no crash)."""
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file("", "empty.py", schema_path, skip_scope=True)
        assert result is not None
        assert result.schema_name == "production"

    def test_empty_file_fixture(self, tmp_project: Path) -> None:
        """The empty_file.py fixture does not crash scan_file."""
        source = (EDGE_DIR / "empty_file.py").read_text(encoding="utf-8")
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file(source, "empty_file.py", schema_path, skip_scope=True)
        assert result is not None


class TestUnicodeSource:
    """Engine handling of non-ASCII source code."""

    def test_unicode_file_scans(self, tmp_project: Path) -> None:
        """A file with Unicode content scans without error."""
        source = (EDGE_DIR / "unicode_source.py").read_text(encoding="utf-8")
        schema_path = str(tmp_project / ".gate_schema.yaml")
        result = scan_file(
            source, "unicode_source.py", schema_path, skip_scope=True
        )
        assert result is not None
        assert result.schema_name == "production"


class TestMalformedYaml:
    """YAML loader handling of malformed files."""

    def test_malformed_yaml_raises(self) -> None:
        """load_yaml raises YAMLError for unparseable YAML."""
        with pytest.raises(yaml.YAMLError):
            load_yaml(str(EDGE_DIR / "malformed_yaml.yaml"))

    def test_nonexistent_yaml_raises(self) -> None:
        """load_yaml raises FileNotFoundError for a missing file."""
        with pytest.raises(FileNotFoundError):
            load_yaml("/nonexistent/path.yaml")


class TestFormatSummaryStderr:
    """Tests for format_summary_stderr output."""

    def test_zero_violations(self) -> None:
        """Summary with zero violations still returns a string."""
        result = format_summary_stderr(
            schema_name="production",
            schema_version="1.0",
            blocking_count=0,
            warning_count=0,
        )
        assert isinstance(result, str)
        assert "production" in result

    def test_with_blocking_violations(self) -> None:
        """Summary includes blocking count."""
        result = format_summary_stderr(
            schema_name="production",
            schema_version="1.0",
            blocking_count=3,
            warning_count=1,
        )
        assert isinstance(result, str)
        assert "3" in result


class TestFormatViolationsJsonEdge:
    """Edge cases for JSON formatting."""

    def test_empty_violations(self) -> None:
        """Empty violations produce valid JSON structure."""
        result = format_violations_json(
            rule_violations=[],
            variables={"filepath": "ok.py"},
            schema_name="production",
            schema_version="1.0",
        )
        assert isinstance(result, dict)
        assert result["status"] == "passed"
