"""Gatehouse — Error-driven code schema enforcement for Python.

Stable public API (semver-protected):
    scan_file: Scan a Python source string against a schema.
    ScanResult: Dataclass returned by scan_file.
    Violation: Dataclass for individual violations.
    GatehouseViolationError: Exception raised by import hook.
    PluginError: Exception raised when a custom check plugin fails.

Deprecation policy:
    - Deprecated symbols emit DeprecationWarning for one minor version.
    - Removed in the next minor version (e.g. deprecated in 0.3, removed in 0.4).
    - gatehouse.gate_engine is deprecated; use gatehouse.engine instead.
"""

__version__ = "0.3.0"

from gatehouse.engine import ScanResult, Violation, scan_file
from gatehouse.exceptions import GatehouseViolationError, PluginError

__all__ = [
    "__version__",
    "scan_file",
    "ScanResult",
    "Violation",
    "GatehouseViolationError",
    "PluginError",
]
