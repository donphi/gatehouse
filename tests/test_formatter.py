"""Unit tests for gatehouse.lib.formatter output formatting."""

from __future__ import annotations

from gatehouse.lib.formatter import (
    format_summary_stderr,
    format_violation_traceback,
    format_violations_json,
    inject_variables,
)


class TestInjectVariables:
    """Tests for template variable injection."""

    def test_basic_replacement(self):
        """Replace simple placeholders."""
        result = inject_variables("File: {filename}, line {line}", {"filename": "test.py", "line": 42})
        assert result == "File: test.py, line 42"

    def test_no_placeholders(self):
        """String without placeholders is unchanged."""
        result = inject_variables("No variables here", {"key": "val"})
        assert result == "No variables here"

    def test_missing_variable(self):
        """Placeholders without matching vars are left as-is."""
        result = inject_variables("{unknown} text", {})
        assert result == "{unknown} text"


class TestFormatViolationsJson:
    """Tests for JSON output formatting."""

    def test_blocking_violation(self):
        """JSON output reports 'rejected' when blocking violations exist."""
        rule_obj = {
            "id": "test-rule",
            "severity": "block",
            "rule_data": {"error": {"message": "error", "fix": "fix it"}},
        }
        violations = [{"line": 10, "source": "x = 1"}]
        result = format_violations_json(
            [(rule_obj, violations)],
            {"filepath": "test.py"},
            "production",
            "1.0.0",
        )
        assert result["status"] == "rejected"
        assert result["summary"]["blocking"] == 1

    def test_warning_only(self):
        """JSON output reports 'passed' when only warnings exist."""
        rule_obj = {
            "id": "test-rule",
            "severity": "warn",
            "rule_data": {"error": {"message": "warning", "fix": "maybe fix"}},
        }
        violations = [{"line": 5, "source": ""}]
        result = format_violations_json(
            [(rule_obj, violations)],
            {"filepath": "test.py"},
            "production",
            "1.0.0",
        )
        assert result["status"] == "passed"
        assert result["summary"]["warnings"] == 1


class TestFormatViolationTraceback:
    """Tests for SyntaxError-style traceback formatting."""

    def test_traceback_format(self):
        """Output looks like a Python traceback."""
        violations = [{"line": 10, "message": "Missing docstring", "source": "def foo():"}]
        result = format_violation_traceback("test.py", violations)
        assert "Traceback" in result
        assert 'File "test.py", line 10' in result
        assert "Missing docstring" in result
