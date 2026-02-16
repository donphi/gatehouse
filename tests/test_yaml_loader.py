"""Unit tests for gatehouse.lib.yaml_loader YAML parsing."""

from __future__ import annotations

import pytest

from gatehouse.lib.yaml_loader import load_yaml, load_yaml_string


class TestLoadYaml:
    """Tests for loading YAML from files."""

    def test_load_valid_yaml(self, tmp_path):
        """Load a valid YAML file and verify contents."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("key: value\nnested:\n  inner: 42\n")
        result = load_yaml(str(yaml_file))
        assert result == {"key": "value", "nested": {"inner": 42}}

    def test_load_empty_yaml(self, tmp_path):
        """Loading an empty file returns None."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")
        result = load_yaml(str(yaml_file))
        assert result is None

    def test_load_missing_file(self):
        """Loading a nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_yaml("/nonexistent/path.yaml")

    def test_load_list_yaml(self, tmp_path):
        """Load a YAML file containing a list."""
        yaml_file = tmp_path / "list.yaml"
        yaml_file.write_text("rules:\n  - id: foo\n  - id: bar\n")
        result = load_yaml(str(yaml_file))
        assert result["rules"] == [{"id": "foo"}, {"id": "bar"}]


class TestLoadYamlString:
    """Tests for parsing YAML from strings."""

    def test_parse_valid_string(self):
        """Parse a valid YAML string."""
        result = load_yaml_string("schema: production\nversion: 1")
        assert result == {"schema": "production", "version": 1}

    def test_parse_empty_string(self):
        """Parsing an empty string returns None."""
        result = load_yaml_string("")
        assert result is None
