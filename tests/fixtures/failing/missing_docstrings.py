# ============================================================================
# FILE: missing_docstrings.py
# LOCATION: tests/fixtures/failing/
# PIPELINE POSITION: test fixture
# PURPOSE: A file where functions lack docstrings
# ============================================================================
"""Fixture: functions missing docstrings — failing.

This file triggers the docstring-required rule by containing functions
(add, subtract) that lack docstrings entirely.
This file is loaded by test fixtures and scanned against schemas.
"""

import os

CONFIG_PATH = os.environ.get("CONFIG_PATH", "default")


def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


def main() -> None:
    """Entry point."""
    print(add(0, 0))


if __name__ == "__main__":
    main()
