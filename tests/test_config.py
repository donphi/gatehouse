"""Unit tests for gatehouse.lib.config defaults accessor."""

from __future__ import annotations

import pytest

from gatehouse.lib import config


class TestLoadDefaults:
    """Tests for config loading and caching."""

    def test_loads_successfully(self) -> None:
        """defaults.yaml loads without error."""
        data = config.load_defaults()
        assert isinstance(data, dict)

    def test_cached_on_second_call(self) -> None:
        """Second call returns the same dict object (cached)."""
        first = config.load_defaults()
        second = config.load_defaults()
        assert first is second

    def test_reset_clears_cache(self) -> None:
        """reset() forces a fresh load on next call."""
        first = config.load_defaults()
        config.reset()
        second = config.load_defaults()
        assert first is not second
        assert first == second


class TestGet:
    """Tests for the dot-notation accessor."""

    def test_top_level_key(self) -> None:
        """Access a top-level mapping."""
        result = config.get("statuses")
        assert isinstance(result, dict)

    def test_nested_key(self) -> None:
        """Access a nested value."""
        result = config.get("statuses.passed")
        assert result == "passed"

    def test_missing_key_raises(self) -> None:
        """Missing key raises KeyError."""
        with pytest.raises(KeyError, match="nonexistent"):
            config.get("nonexistent.key")

    def test_empty_key_raises(self) -> None:
        """Empty string key raises KeyError."""
        with pytest.raises(KeyError):
            config.get("")


class TestTypedAccessors:
    """Tests for get_str, get_int, get_list."""

    def test_get_str(self) -> None:
        """get_str returns a string."""
        result = config.get_str("statuses.passed")
        assert isinstance(result, str)
        assert result == "passed"

    def test_get_str_wrong_type(self) -> None:
        """get_str raises TypeError when value is not a string."""
        with pytest.raises(TypeError, match="Expected str"):
            config.get_str("statuses")

    def test_get_int(self) -> None:
        """get_int returns an integer."""
        result = config.get_int("exit_codes.blocked")
        assert isinstance(result, int)

    def test_get_int_wrong_type(self) -> None:
        """get_int raises TypeError when value is not an int."""
        with pytest.raises(TypeError, match="Expected int"):
            config.get_int("statuses.passed")

    def test_get_list(self) -> None:
        """get_list returns a list."""
        result = config.get_list("severities.valid_choices")
        assert isinstance(result, list)

    def test_get_list_wrong_type(self) -> None:
        """get_list raises TypeError when value is not a list."""
        with pytest.raises(TypeError, match="Expected list"):
            config.get_list("statuses.passed")
