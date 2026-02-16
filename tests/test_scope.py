"""Unit tests for gatehouse.lib.scope file-scope checking."""

from __future__ import annotations

from gatehouse.lib.scope import is_file_in_scope, resolve_effective_schema


class TestIsFileInScope:
    """Tests for scope checking."""

    def test_file_in_gated_path(self):
        """File inside a gated path is in scope."""
        schema = {"scope": {"gated_paths": ["src/"], "exempt_paths": [], "exempt_files": []}}
        assert is_file_in_scope("src/train.py", schema, {}) is True

    def test_file_outside_gated_path(self):
        """File outside all gated paths is out of scope."""
        schema = {"scope": {"gated_paths": ["src/"], "exempt_paths": [], "exempt_files": []}}
        assert is_file_in_scope("scripts/run.py", schema, {}) is False

    def test_file_in_exempt_path(self):
        """File in an exempt path is out of scope even if gated."""
        schema = {"scope": {"gated_paths": ["src/"], "exempt_paths": ["src/tests/"], "exempt_files": []}}
        assert is_file_in_scope("src/tests/test_foo.py", schema, {}) is False

    def test_exempt_filename(self):
        """Files with exempt names are out of scope."""
        schema = {"scope": {"gated_paths": ["src/"], "exempt_paths": [], "exempt_files": ["__init__.py"]}}
        assert is_file_in_scope("src/__init__.py", schema, {}) is False

    def test_no_gated_paths_means_all_gated(self):
        """If gated_paths is empty, everything is in scope."""
        schema = {"scope": {"gated_paths": [], "exempt_paths": [], "exempt_files": []}}
        assert is_file_in_scope("any/path.py", schema, {}) is True


class TestResolveEffectiveSchema:
    """Tests for per-path schema overrides."""

    def test_default_schema(self):
        """Without overrides, return the base schema."""
        config = {"schema": "production", "overrides": {}}
        assert resolve_effective_schema("src/foo.py", config) == "production"

    def test_override_to_different_schema(self):
        """Per-path override selects a different schema."""
        config = {
            "schema": "production",
            "overrides": {"src/api/": {"schema": "api"}},
        }
        assert resolve_effective_schema("src/api/routes.py", config) == "api"

    def test_override_to_exempt(self):
        """Per-path override with schema=null exempts the file."""
        config = {
            "schema": "production",
            "overrides": {"tests/*.py": {"schema": None}},
        }
        assert resolve_effective_schema("tests/test_foo.py", config) is None

    def test_no_overrides_key(self):
        """Config without overrides key defaults to base schema."""
        config = {"schema": "minimal"}
        assert resolve_effective_schema("src/foo.py", config) == "minimal"
