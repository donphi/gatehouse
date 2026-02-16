"""Backward-compatibility shim for gatehouse.gate_engine.

DEPRECATED: This module exists so that 'python -m gatehouse.gate_engine'
continues to work after the v0.3.0 restructuring. All logic has moved to
gatehouse.engine. This shim will be removed in v0.4.0.

See also:
    gatehouse.engine — the canonical engine module that contains all logic.
"""

import warnings

warnings.warn(
    "gatehouse.gate_engine is deprecated. Use gatehouse.engine instead. "
    "This module will be removed in v0.4.0.",
    DeprecationWarning,
    stacklevel=2,
)

from gatehouse.engine import main  # noqa: E402

if __name__ == "__main__":
    main()
