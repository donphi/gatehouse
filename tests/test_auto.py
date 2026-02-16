"""Unit tests for gatehouse.auto import-hook layer."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from gatehouse.auto import (
    GatehouseImportHook,
    _already_scanned,
    _find_schema_path,
    _get_mode,
    _mark_scanned,
    _should_skip,
    activate,
    deactivate,
)


class TestGetMode:
    """Tests for environment mode reading."""

    def test_default_is_off(self):
        """Mode is 'off' when env var is unset."""
        with patch.dict(os.environ, {}, clear=True):
            assert _get_mode() == "off"

    def test_hard_mode(self):
        """Hard mode is recognized."""
        with patch.dict(os.environ, {"GATEHOUSE_MODE": "hard"}):
            assert _get_mode() == "hard"

    def test_soft_mode(self):
        """Soft mode is recognized."""
        with patch.dict(os.environ, {"GATEHOUSE_MODE": "soft"}):
            assert _get_mode() == "soft"

    def test_invalid_mode_defaults_off(self):
        """Unknown mode defaults to 'off'."""
        with patch.dict(os.environ, {"GATEHOUSE_MODE": "potato"}):
            assert _get_mode() == "off"

    def test_case_insensitive(self):
        """Mode comparison is case-insensitive."""
        with patch.dict(os.environ, {"GATEHOUSE_MODE": "HARD"}):
            assert _get_mode() == "hard"


class TestShouldSkip:
    """Tests for file skip logic."""

    def test_skip_non_python(self):
        """Non-.py files are skipped."""
        assert _should_skip("/some/file.txt") is True

    def test_skip_empty_path(self):
        """Empty path is skipped."""
        assert _should_skip("") is True

    def test_skip_site_packages(self, tmp_path):
        """Files in site-packages are skipped."""
        sp_dir = tmp_path / "site-packages"
        sp_dir.mkdir()
        f = sp_dir / "mod.py"
        f.write_text("x = 1")
        assert _should_skip(str(f)) is True

    def test_skip_gatehouse_own_modules(self):
        """Gatehouse's own modules are skipped."""
        from gatehouse.auto import _PACKAGE_DIR

        engine_path = str(_PACKAGE_DIR / "engine.py")
        assert _should_skip(engine_path) is True

    def test_allow_user_code(self, tmp_path):
        """User project code is NOT skipped."""
        f = tmp_path / "train.py"
        f.write_text("print('hello')")
        assert _should_skip(str(f)) is False

    def test_skip_nonexistent_file(self):
        """Nonexistent files are skipped."""
        assert _should_skip("/nonexistent/path.py") is True


class TestAntiDoubleScan:
    """Tests for the anti-double-scan mechanism."""

    def test_not_scanned_initially(self):
        """No files are marked as scanned initially."""
        with patch.dict(os.environ, {}, clear=True):
            assert _already_scanned("/tmp/test.py") is False

    def test_mark_and_check(self):
        """After marking, the file is detected as scanned."""
        with patch.dict(os.environ, {}, clear=True):
            _mark_scanned("/tmp/test.py")
            assert _already_scanned("/tmp/test.py") is True

    def test_multiple_marks(self):
        """Multiple files can be marked."""
        with patch.dict(os.environ, {}, clear=True):
            _mark_scanned("/tmp/a.py")
            _mark_scanned("/tmp/b.py")
            assert _already_scanned("/tmp/a.py") is True
            assert _already_scanned("/tmp/b.py") is True
            assert _already_scanned("/tmp/c.py") is False


class TestFindSchemaPath:
    """Tests for schema discovery."""

    def test_finds_schema_in_cwd(self, tmp_project):
        """Finds .gate_schema.yaml in current directory."""
        with patch("gatehouse.auto.Path") as mock_path:
            mock_path.cwd.return_value = tmp_project
            result = _find_schema_path()
            assert result is not None

    def test_env_var_override(self, tmp_project):
        """GATEHOUSE_SCHEMA env var takes precedence."""
        schema_path = str(tmp_project / ".gate_schema.yaml")
        with patch.dict(os.environ, {"GATEHOUSE_SCHEMA": schema_path}):
            result = _find_schema_path()
            assert result == schema_path


class TestActivateDeactivate:
    """Tests for hook activate/deactivate lifecycle."""

    def test_install_off_mode(self):
        """Activate returns False when mode is 'off'."""
        with patch.dict(os.environ, {"GATEHOUSE_MODE": "off"}):
            result = activate()
            assert result is False

    def test_uninstall_when_nothing_installed(self):
        """Deactivate returns False when no hook is present."""
        sys.meta_path[:] = [
            f for f in sys.meta_path
            if not isinstance(f, GatehouseImportHook)
        ]
        assert deactivate() is False

    def test_install_uninstall_roundtrip(self, tmp_project):
        """Activate then deactivate leaves sys.meta_path clean."""
        sys.meta_path[:] = [
            f for f in sys.meta_path
            if not isinstance(f, GatehouseImportHook)
        ]
        schema_path = str(tmp_project / ".gate_schema.yaml")
        with patch.dict(os.environ, {
            "GATEHOUSE_MODE": "hard",
            "GATEHOUSE_SCHEMA": schema_path,
        }):
            activated = activate()
            assert activated is True
            hook_count = sum(1 for f in sys.meta_path if isinstance(f, GatehouseImportHook))
            assert hook_count == 1

            removed = deactivate()
            assert removed is True
            hook_count = sum(1 for f in sys.meta_path if isinstance(f, GatehouseImportHook))
            assert hook_count == 0
