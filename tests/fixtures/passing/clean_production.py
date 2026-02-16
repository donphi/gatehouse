# ============================================================================
# FILE: clean_production.py
# LOCATION: tests/fixtures/passing/
# PIPELINE POSITION: test fixture
# PURPOSE: A file that passes all production schema rules
# ============================================================================
"""Fixture: fully compliant production file — passing.

This file passes all production schema rules including file headers,
docstrings, type hints, main guard, and no hardcoded values.
This file is loaded by test fixtures and scanned against schemas.
"""

import os

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/default.yaml")


def greet(name: str) -> str:
    """Return a greeting string.

    Args:
        name: The name to greet.

    Returns:
        Greeting string.
    """
    return f"Hello, {name}"


def main() -> None:
    """Entry point for the clean production fixture."""
    result = greet("world")
    print(result)


if __name__ == "__main__":
    main()
