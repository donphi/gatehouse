"""Gatehouse import-hook layer — automatic enforcement via MetaPathFinder.

This module installs a sys.meta_path hook that intercepts Python module
imports and runs Gatehouse schema validation before any module is loaded.
It provides the *inner* enforcement layer (alongside the *outer* python_gate
shim) for comprehensive coverage across all execution paths including:

    - pytest / unittest discovery
    - Jupyter notebooks
    - Celery / RQ workers
    - subprocess.run(["python", "-m", ...])

Usage:
    # Activate via sitecustomize, conftest, or explicit import:
    import gatehouse.auto
    gatehouse.auto.activate()

    # Or via python -m:
    python -m gatehouse.auto your_script.py

Environment variables:
    GATEHOUSE_MODE           — "hard" (block), "soft" (warn), "off" (disabled)
    GATEHOUSE_SCHEMA         — path to .gate_schema.yaml (optional, auto-discovered)
    GATEHOUSE_OUTER_VERDICT  — internal anti-double-scan marker (do not set manually)
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Optional, Sequence

from gatehouse.engine import ScanResult, scan_file
from gatehouse.exceptions import GatehouseParseError, GatehouseViolationError
from gatehouse.lib import config

_PACKAGE_DIR = Path(__file__).resolve().parent


def _get_mode(explicit_mode: Optional[str] = None) -> str:
    """Read the enforcement mode from an explicit value or the environment.

    Args:
        explicit_mode: If provided, overrides the environment variable.

    Returns:
        One of 'hard', 'soft', or 'off'.
    """
    mode_hard = config.get_str("modes.hard")
    mode_soft = config.get_str("modes.soft")
    mode_off = config.get_str("modes.off")
    env_key = config.get_str("env_vars.mode")

    if explicit_mode:
        raw = explicit_mode.lower().strip()
    else:
        raw = os.environ.get(env_key, mode_off).lower().strip()

    if raw in (mode_hard, mode_soft):
        return raw
    return mode_off


def _find_schema_path() -> Optional[str]:
    """Locate the .gate_schema.yaml for the current working directory.

    Walks up from cwd looking for the config file. Falls back to
    GATEHOUSE_SCHEMA env var if set.

    Returns:
        Absolute path to .gate_schema.yaml, or None.
    """
    env_key = config.get_str("env_vars.schema")
    project_cfg = config.get_str("filenames.project_config")

    explicit = os.environ.get(env_key)
    if explicit and os.path.isfile(explicit):
        return os.path.abspath(explicit)

    directory = Path.cwd()
    while True:
        candidate = directory / project_cfg
        if candidate.is_file():
            return str(candidate)
        parent = directory.parent
        if parent == directory:
            break
        directory = parent

    return None


def _already_scanned(filepath: str) -> bool:
    """Check if this filepath was already scanned in this process.

    Uses a process-level environment variable to track scanned files,
    preventing the outer shim + inner hook from double-scanning.

    Args:
        filepath: Absolute path to the file.

    Returns:
        True if already scanned.
    """
    # Environment variable is used (rather than a Python set) so that the
    # scanned-file list survives across subprocess boundaries.
    env_key = config.get_str("env_vars.outer_verdict")
    separator = config.get_str("defaults.marker_separator")
    scanned_raw = os.environ.get(env_key, "")
    if not scanned_raw:
        return False
    scanned_set = set(scanned_raw.split(separator))
    return filepath in scanned_set


def _mark_scanned(filepath: str) -> None:
    """Record that this filepath has been scanned.

    Args:
        filepath: Absolute path to the file.
    """
    env_key = config.get_str("env_vars.outer_verdict")
    separator = config.get_str("defaults.marker_separator")
    scanned_raw = os.environ.get(env_key, "")
    if scanned_raw:
        entries = set(scanned_raw.split(separator))
        entries.add(filepath)
        os.environ[env_key] = separator.join(entries)
    else:
        os.environ[env_key] = filepath


def _should_skip(filepath: str) -> bool:
    """Determine if a file should be skipped from scanning.

    Skips gatehouse's own modules, non-existent files, non-.py files,
    and files in standard library or site-packages.

    Args:
        filepath: Path to the module file.

    Returns:
        True if the file should not be scanned.
    """
    # Skip non-Python or missing files — nothing to validate.
    if not filepath or not filepath.endswith(".py"):
        return True

    if not os.path.isfile(filepath):
        return True

    normalized = os.path.normpath(filepath)

    # Skip third-party packages — they are outside the user's control.
    site_pkg = config.get_str("skip_markers.site_packages")
    dist_pkg = config.get_str("skip_markers.dist_packages")
    if site_pkg in normalized or dist_pkg in normalized:
        return True

    # Skip gatehouse itself — scanning our own code during import would
    # cause infinite recursion.
    package_prefix = str(_PACKAGE_DIR)
    if normalized.startswith(package_prefix):
        return True

    # Skip the standard library — not user code.
    stdlib_path = os.path.dirname(os.__file__)
    if normalized.startswith(stdlib_path):
        return True

    return False


class GatehouseImportHook(importlib.abc.MetaPathFinder):
    """MetaPathFinder that validates Python source on import.

    Installed onto sys.meta_path to intercept all module imports.
    Uses the modern find_spec protocol. Delegates actual module finding
    to the default finders — this hook only adds validation before the
    module is loaded.

    Attributes:
        _schema_path: Absolute path to the .gate_schema.yaml config file.
        _mode: Enforcement mode — 'hard' (raise on violations) or 'soft'
            (warn only).
    """

    def __init__(self, schema_path: str, mode: str) -> None:
        """Initialize with the schema config path and enforcement mode.

        Args:
            schema_path: Absolute path to .gate_schema.yaml.
            mode: Enforcement mode ('hard' or 'soft').
        """
        self._schema_path = schema_path
        self._mode = mode

    def find_spec(
        self,
        fullname: str,
        path: Optional[Sequence[str]],
        target: Any = None,
    ) -> Optional[importlib.machinery.ModuleSpec]:
        """Find a module spec with Gatehouse validation.

        Implements the PEP 451 MetaPathFinder protocol. Called by the
        import machinery for every import statement. Returns None to
        defer actual module loading to the default finders — this hook
        only intercepts to run validation as a side effect.

        Args:
            fullname: Fully qualified module name.
            path: Module search path.
            target: Target module (unused).

        Returns:
            Always None — validation is a side effect, loading is
            deferred to the default finders.
        """
        mode_off = config.get_str("modes.off")
        if self._mode == mode_off:
            return None

        spec = self._find_spec_without_self(fullname, path)
        if spec is None or spec.origin is None:
            return None

        filepath = spec.origin
        abs_path = os.path.abspath(filepath)
        if _should_skip(filepath) or _already_scanned(abs_path):
            return None

        self._validate_file(abs_path)
        _mark_scanned(abs_path)

        return None

    def _validate_file(self, filepath: str) -> None:
        """Run Gatehouse validation on a source file.

        Args:
            filepath: Absolute path to the .py file.

        Raises:
            GatehouseViolationError: In hard mode when blocking violations exist.
        """
        sev_block = config.get_str("severities.block")
        mode_hard = config.get_str("modes.hard")
        fmt_stderr = config.get_str("formats.stderr")

        try:
            source = Path(filepath).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return

        try:
            result: ScanResult = scan_file(
                source,
                filepath,
                self._schema_path,
                output_format=fmt_stderr,
            )
        except GatehouseParseError as exc:
            error_line = config.get_int("defaults.error_line")
            msg = str(exc)
            if self._mode == mode_hard:
                raise GatehouseViolationError(
                    filepath,
                    [{"line": error_line, "message": msg, "fix": ""}],
                    schema_name="",
                ) from exc
            sys.stderr.write(f"  {msg}\n")
            return

        if result.blocking_count > 0 and self._mode == mode_hard:
            violations_data = [
                {"line": v.line, "message": v.message, "rule_id": v.rule_id}
                for v in result.violations
                if v.severity == sev_block
            ]
            raise GatehouseViolationError(
                filepath,
                violations_data,
                schema_name=result.schema_name,
            )

    def _find_spec_without_self(
        self,
        fullname: str,
        path: Optional[Sequence[str]],
    ) -> Optional[importlib.machinery.ModuleSpec]:
        """Find a module spec using only the default finders.

        Temporarily removes self from sys.meta_path to prevent infinite
        recursion: find_spec triggers the import machinery, which would
        re-enter this hook if we didn't remove ourselves first.

        Args:
            fullname: Fully qualified module name.
            path: Module search path.

        Returns:
            ModuleSpec if found, None otherwise.
        """
        # Snapshot and restore meta_path around the call to prevent
        # re-entrant find_spec from invoking this hook again.
        original_meta = sys.meta_path[:]
        sys.meta_path = [f for f in sys.meta_path if f is not self]
        try:
            return importlib.util.find_spec(fullname, path)
        except (ModuleNotFoundError, ValueError):
            return None
        finally:
            sys.meta_path = original_meta


def activate(mode: Optional[str] = None) -> bool:
    """Install the Gatehouse import hook.

    Only installs if the mode is 'hard' or 'soft' and a schema
    is found. Safe to call multiple times (idempotent).

    Args:
        mode: Explicit enforcement mode. If None, reads from
            GATEHOUSE_MODE environment variable.

    Returns:
        True if the hook was installed, False otherwise.
    """
    resolved_mode = _get_mode(mode)
    mode_off = config.get_str("modes.off")
    position = config.get_int("defaults.meta_path_position")

    if resolved_mode == mode_off:
        return False

    for finder in sys.meta_path:
        if isinstance(finder, GatehouseImportHook):
            return True

    schema_path = _find_schema_path()
    if not schema_path:
        return False

    hook = GatehouseImportHook(schema_path, resolved_mode)
    sys.meta_path.insert(position, hook)
    return True


def deactivate() -> bool:
    """Remove the Gatehouse import hook from sys.meta_path.

    Returns:
        True if a hook was removed, False if none was installed.
    """
    original_len = len(sys.meta_path)
    sys.meta_path[:] = [
        f for f in sys.meta_path
        if not isinstance(f, GatehouseImportHook)
    ]
    return len(sys.meta_path) < original_len


def install() -> bool:
    """Deprecated: use activate() instead."""
    warnings.warn(
        "gatehouse.auto.install() is deprecated. Use activate() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return activate()


def uninstall() -> bool:
    """Deprecated: use deactivate() instead."""
    warnings.warn(
        "gatehouse.auto.uninstall() is deprecated. Use deactivate() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return deactivate()

def main() -> None:
    """Run a target script after activating the import hook."""
    import argparse
    import runpy

    parser = argparse.ArgumentParser(
        description="Run a Python script with Gatehouse auto-activation"
    )
    parser.add_argument("target", nargs="?", help="Python script to run")
    args, remaining = parser.parse_known_args()

    if not args.target:
        parser.print_help()
        return

    activate()
    sys.argv = [args.target] + remaining
    runpy.run_path(args.target, run_name="__main__")


activate()

if __name__ == "__main__":
    main()
