"""Fixture: Unicode content in source file — edge case.

This file tests that the Gatehouse engine handles non-ASCII source files
correctly, including emoji, CJK characters, and Cyrillic text.
This file is loaded by test fixtures and scanned against schemas.
"""


# Various Unicode: emojis, CJK, Cyrillic
GREETING = "Hello, 世界! Привет! 🌍"
MATH_SYMBOL = "∑∏∫"


def greet(name: str) -> str:
    """Return a greeting with Unicode.

    Args:
        name: Person to greet.

    Returns:
        Greeting string.
    """
    return f"{GREETING} — {name}"


if __name__ == "__main__":
    greet("test")
