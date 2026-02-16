# Fixture: intentional syntax error — edge case.
#
# This file contains deliberately broken Python syntax to verify that
# the Gatehouse engine handles unparseable source files gracefully.
# This file is loaded by test fixtures and scanned against schemas.

def broken(
    this is not valid python
