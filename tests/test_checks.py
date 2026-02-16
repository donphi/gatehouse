"""Unit tests for gatehouse.lib.checks check-type dispatch."""

from __future__ import annotations

from pathlib import Path

from gatehouse.lib.analyzer import SourceAnalyzer
from gatehouse.lib.checks import (
    check_ast_check,
    check_ast_node_exists,
    check_file_metric,
    check_pattern_exists,
    check_token_scan,
    check_uppercase_assignments,
    run_check,
)


def _analyzer(source: str, filepath: str = "test.py") -> SourceAnalyzer:
    """Create a SourceAnalyzer from source code."""
    return analyzer if (analyzer := SourceAnalyzer(source, filepath)) else None


class TestCheckPatternExists:
    """Tests for the pattern_exists check type."""

    def test_main_guard_present(self):
        """File with main guard passes."""
        source = 'if __name__ == "__main__":\n    pass\n'
        analyzer = _analyzer(source)
        result = check_pattern_exists(analyzer, {"pattern": "if_name_main"}, {})
        assert result == []

    def test_main_guard_missing(self):
        """File without main guard fails."""
        source = "x = 1\n"
        analyzer = _analyzer(source)
        result = check_pattern_exists(analyzer, {"pattern": "if_name_main"}, {})
        assert len(result) == 1


class TestCheckAstNodeExists:
    """Tests for the ast_node_exists check type."""

    def test_module_docstring_present(self):
        """File with module docstring passes."""
        source = '"""Module docstring."""\nimport os\n'
        analyzer = _analyzer(source)
        result = check_ast_node_exists(analyzer, {"node": "module_docstring"}, {})
        assert result == []

    def test_module_docstring_missing(self):
        """File without module docstring fails."""
        source = "import os\nx = 1\n"
        analyzer = _analyzer(source)
        result = check_ast_node_exists(analyzer, {"node": "module_docstring"}, {})
        assert len(result) == 1


class TestCheckAstCheck:
    """Tests for the ast_check check type."""

    def test_all_functions_have_docstrings_pass(self):
        """Functions with docstrings pass."""
        source = 'def foo():\n    """Docstring."""\n    pass\n'
        analyzer = _analyzer(source)
        result = check_ast_check(
            analyzer, {"check": "all_functions_have_docstrings"}, {}
        )
        assert result == []

    def test_function_missing_docstring(self):
        """Function without docstring fails."""
        source = "def foo():\n    pass\n"
        analyzer = _analyzer(source)
        result = check_ast_check(
            analyzer, {"check": "all_functions_have_docstrings"}, {}
        )
        assert len(result) == 1
        assert result[0]["function_name"] == "foo"


class TestCheckTokenScan:
    """Tests for the token_scan check type."""

    def test_hardcoded_literal_detected(self):
        """Hardcoded number inside function body is flagged."""
        source = 'def train():\n    lr = 0.001\n'
        analyzer = _analyzer(source)
        result = check_token_scan(
            analyzer,
            {"scan": "hardcoded_literals", "safe_values": [0, 1, -1], "safe_contexts": []},
            {},
        )
        assert len(result) >= 1

    def test_safe_values_ignored(self):
        """Values in safe_values are not flagged."""
        source = 'def train():\n    x = 0\n    y = 1\n'
        analyzer = _analyzer(source)
        result = check_token_scan(
            analyzer,
            {"scan": "hardcoded_literals", "safe_values": [0, 1, -1], "safe_contexts": []},
            {},
        )
        assert result == []


class TestCheckUppercaseAssignments:
    """Tests for the uppercase_assignments_exist check type."""

    def test_constants_present(self):
        """File with uppercase constants passes."""
        source = 'CONFIG_PATH = "config.yaml"\nMAX_RETRIES = 3\n'
        analyzer = _analyzer(source)
        result = check_uppercase_assignments(analyzer, {"min_count": 1}, {})
        assert result == []

    def test_no_constants(self):
        """File without uppercase constants fails."""
        source = 'x = 1\ny = 2\n'
        analyzer = _analyzer(source)
        result = check_uppercase_assignments(analyzer, {"min_count": 1}, {})
        assert len(result) == 1


class TestCheckFileMetric:
    """Tests for the file_metric check type."""

    def test_file_under_limit(self):
        """File under the line limit passes."""
        source = "x = 1\n" * 10
        analyzer = _analyzer(source)
        result = check_file_metric(
            analyzer, {"metric": "line_count", "max_lines": 100}, {}
        )
        assert result == []

    def test_file_over_limit(self):
        """File over the line limit fails."""
        source = "x = 1\n" * 200
        analyzer = _analyzer(source)
        result = check_file_metric(
            analyzer, {"metric": "line_count", "max_lines": 100}, {}
        )
        assert len(result) == 1
