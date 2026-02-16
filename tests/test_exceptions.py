"""Unit tests for gatehouse.exceptions custom exception classes."""

from __future__ import annotations

from gatehouse.exceptions import GatehouseParseError, GatehouseViolationError


class TestGatehouseViolationError:
    """Tests for the import-hook violation error."""

    def test_inherits_from_import_error(self):
        """GatehouseViolationError is a subclass of ImportError."""
        assert issubclass(GatehouseViolationError, ImportError)

    def test_message_contains_filepath(self):
        """Error message includes the file path."""
        err = GatehouseViolationError("src/bad.py", [{"line": 1, "message": "fail"}])
        assert "src/bad.py" in str(err)

    def test_violations_accessible(self):
        """Violations list is stored on the exception."""
        violations = [{"line": 5, "message": "Missing docstring"}]
        err = GatehouseViolationError("test.py", violations)
        assert err.violations == violations

    def test_schema_name_stored(self):
        """Schema name is stored on the exception."""
        err = GatehouseViolationError("test.py", [], schema_name="production")
        assert err.schema_name == "production"


class TestGatehouseParseError:
    """Tests for the parse error exception."""

    def test_inherits_from_exception(self):
        """GatehouseParseError is a subclass of Exception."""
        assert issubclass(GatehouseParseError, Exception)

    def test_stores_filepath(self):
        """File path is stored on the exception."""
        original = SyntaxError("bad syntax")
        err = GatehouseParseError("test.py", original)
        assert err.filepath == "test.py"

    def test_stores_original_error(self):
        """Original error is stored on the exception."""
        original = SyntaxError("bad syntax")
        err = GatehouseParseError("test.py", original)
        assert err.original_error is original
