"""Unit tests for gatehouse.lib.theme ANSI colourisation."""

from __future__ import annotations

import io

from gatehouse.lib.theme import Theme, code, colorize


class TestTheme:
    """Tests for the Theme class."""

    def test_colorize_returns_string(self):
        """colorize always returns a string."""
        result = colorize("hello", "green")
        assert isinstance(result, str)

    def test_colorize_with_non_tty_stream(self):
        """Non-TTY stream strips ANSI codes."""
        stream = io.StringIO()
        result = colorize("hello", "green", stream=stream)
        assert result == "hello"

    def test_code_returns_string(self):
        """code helper always returns a string."""
        result = code("green")
        assert isinstance(result, str)

    def test_lazy_loading(self):
        """Theme data is loaded on first use, not at import."""
        theme = Theme()
        assert theme._resolved is None
        _ = theme.resolved
        assert theme._resolved is not None
