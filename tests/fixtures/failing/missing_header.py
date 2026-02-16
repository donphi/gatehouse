"""Fixture: file missing the standard file header block — failing.

This file is designed to trigger the file-header-required rule by omitting
the standard comment header block expected at the top of every source file.
This file is loaded by test fixtures and scanned against schemas.
"""

import os

CONFIG_PATH = os.environ.get("CONFIG_PATH", "default")


def main() -> None:
    """Entry point."""
    print("hello")


if __name__ == "__main__":
    main()
