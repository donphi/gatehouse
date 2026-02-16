"""Unit tests for gatehouse.lib.rules schema and rule loading."""

from __future__ import annotations

from pathlib import Path

from gatehouse.lib.rules import (
    apply_project_overrides,
    find_gate_home,
    load_project_config,
    load_rule,
    load_schema,
    resolve_rules,
)


class TestFindGateHome:
    """Tests for gate home discovery."""

    def test_finds_installed_home(self):
        """Gate home should resolve to a valid directory."""
        home = find_gate_home()
        assert home is not None
        assert home.is_dir()


class TestLoadRule:
    """Tests for loading individual rules."""

    def test_load_existing_rule(self, gate_home):
        """Load a known built-in rule."""
        rule = load_rule("file-header", gate_home)
        assert rule is not None
        assert rule["name"] == "File Header"

    def test_load_nonexistent_rule(self, gate_home):
        """Loading a nonexistent rule returns None."""
        rule = load_rule("nonexistent-rule-xyz", gate_home)
        assert rule is None

    def test_gate_home_is_used(self, tmp_path):
        """Verify gate_home parameter is actually used, not ignored."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "custom.yaml").write_text(
            'name: "Custom"\ndefaults:\n  severity: "warn"\n  enabled: true\n'
        )
        result = load_rule("custom", tmp_path)
        assert result is not None
        assert result["name"] == "Custom"


class TestLoadSchema:
    """Tests for loading schemas."""

    def test_load_production_schema(self, gate_home):
        """Load the production schema."""
        schema = load_schema("production", gate_home)
        assert schema is not None
        assert "rules" in schema

    def test_load_nonexistent_schema(self, gate_home):
        """Loading a nonexistent schema returns None."""
        schema = load_schema("nonexistent-schema-xyz", gate_home)
        assert schema is None

    def test_gate_home_is_used(self, tmp_path):
        """Verify gate_home parameter is actually used for schemas."""
        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        (schemas_dir / "test.yaml").write_text(
            'schema:\n  name: "test"\nrules: []\n'
        )
        result = load_schema("test", tmp_path)
        assert result is not None


class TestResolveRules:
    """Tests for rule resolution from schemas."""

    def test_resolve_production_rules(self, gate_home):
        """Resolve rules from the production schema."""
        schema = load_schema("production", gate_home)
        rules = resolve_rules(schema, gate_home)
        assert len(rules) > 0
        rule_ids = [r["id"] for r in rules]
        assert "file-header" in rule_ids

    def test_schema_inheritance(self, gate_home):
        """API schema extends production and adds additional rules."""
        schema = load_schema("api", gate_home)
        rules = resolve_rules(schema, gate_home)
        rule_ids = [r["id"] for r in rules]
        assert "file-header" in rule_ids
        assert "route-docstrings" in rule_ids


class TestApplyProjectOverrides:
    """Tests for project-level rule overrides."""

    def test_override_severity(self):
        """Override a rule's severity from the project config."""
        rules = [{"id": "test-rule", "severity": "block", "enabled": True, "params": {}}]
        config = {"rule_overrides": {"test-rule": {"severity": "warn"}}}
        result = apply_project_overrides(rules, config)
        assert result[0]["severity"] == "warn"

    def test_override_enabled(self):
        """Disable a rule via project override."""
        rules = [{"id": "test-rule", "severity": "block", "enabled": True, "params": {}}]
        config = {"rule_overrides": {"test-rule": {"enabled": False}}}
        result = apply_project_overrides(rules, config)
        assert result[0]["enabled"] is False

    def test_no_overrides(self):
        """Rules unchanged when no overrides exist."""
        rules = [{"id": "test-rule", "severity": "block", "enabled": True, "params": {}}]
        config = {"rule_overrides": {}}
        result = apply_project_overrides(rules, config)
        assert result[0]["severity"] == "block"
