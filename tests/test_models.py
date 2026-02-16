"""Unit tests for gatehouse.lib.models typed dataclasses."""

from __future__ import annotations

import pytest

from gatehouse.lib.models import (
    GatehouseConfig,
    RuleEntry,
    ScopeConfig,
    validate_project_config,
)


class TestScopeConfig:
    """Tests for ScopeConfig dataclass."""

    def test_from_dict_full(self) -> None:
        """All fields populated from dict."""
        data = {
            "gated_paths": ["src/"],
            "exempt_paths": ["tests/"],
            "exempt_files": ["conftest.py"],
        }
        sc = ScopeConfig.from_dict(data)
        assert sc.gated_paths == ["src/"]
        assert sc.exempt_paths == ["tests/"]
        assert sc.exempt_files == ["conftest.py"]

    def test_from_dict_empty(self) -> None:
        """Empty dict produces empty lists."""
        sc = ScopeConfig.from_dict({})
        assert sc.gated_paths == []
        assert sc.exempt_paths == []
        assert sc.exempt_files == []


class TestGatehouseConfig:
    """Tests for GatehouseConfig dataclass."""

    def test_from_dict_minimal(self) -> None:
        """Minimal config with just schema key."""
        gc = GatehouseConfig.from_dict({"schema": "production"}, "default")
        assert gc.schema == "production"
        assert gc.overrides == {}
        assert gc.scope is None

    def test_from_dict_with_scope(self) -> None:
        """Config with scope section."""
        data = {
            "schema": "strict",
            "scope": {"gated_paths": ["src/"], "exempt_paths": []},
        }
        gc = GatehouseConfig.from_dict(data, "default")
        assert gc.schema == "strict"
        assert gc.scope is not None
        assert gc.scope.gated_paths == ["src/"]

    def test_from_dict_uses_default_schema(self) -> None:
        """Missing schema key falls back to default."""
        gc = GatehouseConfig.from_dict({}, "production")
        assert gc.schema == "production"


class TestRuleEntry:
    """Tests for RuleEntry dataclass."""

    def test_frozen(self) -> None:
        """RuleEntry is immutable."""
        entry = RuleEntry(
            rule_id="test",
            name="Test",
            description="A test rule",
            check_type="pattern_exists",
            check_params={},
            severity="block",
            enabled=True,
            error_message="fail",
            fix_instruction="fix it",
        )
        with pytest.raises(AttributeError):
            entry.rule_id = "changed"  # type: ignore[misc]


class TestValidateProjectConfig:
    """Tests for validate_project_config."""

    def test_valid_config(self) -> None:
        """Valid config returns empty error list."""
        data = {"schema": "production"}
        assert validate_project_config(data) == []

    def test_not_a_dict(self) -> None:
        """Non-dict input reports error."""
        errors = validate_project_config("not a dict")
        assert len(errors) == 1
        assert "mapping" in errors[0]

    def test_missing_schema(self) -> None:
        """Missing 'schema' key reports error."""
        errors = validate_project_config({})
        assert any("schema" in e for e in errors)

    def test_bad_schema_type(self) -> None:
        """Non-string 'schema' reports error."""
        errors = validate_project_config({"schema": 123})
        assert any("string" in e for e in errors)

    def test_bad_overrides_type(self) -> None:
        """Non-dict 'overrides' reports error."""
        errors = validate_project_config({"schema": "x", "overrides": "bad"})
        assert any("overrides" in e for e in errors)

    def test_bad_scope_type(self) -> None:
        """Non-dict 'scope' reports error."""
        errors = validate_project_config({"schema": "x", "scope": "bad"})
        assert any("scope" in e for e in errors)

    def test_bad_scope_list_type(self) -> None:
        """Non-list scope.gated_paths reports error."""
        errors = validate_project_config({
            "schema": "x",
            "scope": {"gated_paths": "not a list"},
        })
        assert any("gated_paths" in e for e in errors)
