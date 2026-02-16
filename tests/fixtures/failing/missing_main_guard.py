# ============================================================================
# FILE: missing_main_guard.py
# LOCATION: tests/fixtures/failing/
# PIPELINE POSITION: test fixture
# PURPOSE: A file missing the if __name__ == '__main__' guard
# ============================================================================
"""Fixture: missing ``if __name__ == '__main__'`` guard — failing.

This file triggers the main-guard-required rule by calling main() directly
at module level instead of wrapping it in the standard guard.
This file is loaded by test fixtures and scanned against schemas.
"""

import os

CONFIG_PATH = os.environ.get("CONFIG_PATH", "default")


def main() -> None:
    """Entry point."""
    print("hello")


main()
