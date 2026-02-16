"""Unit tests for gatehouse.cli.prompts interactive input helpers."""

from __future__ import annotations

from gatehouse.cli.prompts import evaluate_show_if


class TestEvaluateShowIf:
    """Tests for the safe show_if evaluator."""

    def test_equality_match(self):
        """Field == value matches."""
        assert evaluate_show_if("type == 'foo'", {"type": "foo"}) is True

    def test_equality_mismatch(self):
        """Field == value does not match."""
        assert evaluate_show_if("type == 'foo'", {"type": "bar"}) is False

    def test_in_match(self):
        """Field in [...] matches."""
        assert evaluate_show_if("mode in ['a', 'b', 'c']", {"mode": "b"}) is True

    def test_in_mismatch(self):
        """Field in [...] does not match."""
        assert evaluate_show_if("mode in ['a', 'b']", {"mode": "c"}) is False

    def test_empty_expression(self):
        """Empty expression returns True."""
        assert evaluate_show_if("", {}) is True

    def test_unparseable_expression(self):
        """Unknown expression format returns True (permissive fallback)."""
        assert evaluate_show_if("some_random_stuff", {}) is True

    def test_missing_field(self):
        """Missing field in collected values returns False for equality."""
        assert evaluate_show_if("field == 'val'", {}) is False

    def test_double_quotes(self):
        """Double-quoted values work."""
        assert evaluate_show_if('type == "pattern"', {"type": "pattern"}) is True
