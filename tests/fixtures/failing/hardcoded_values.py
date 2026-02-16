# ============================================================================
# FILE: hardcoded_values.py
# LOCATION: tests/fixtures/failing/
# PIPELINE POSITION: test fixture
# PURPOSE: A file with hardcoded values inside functions
# ============================================================================
"""Fixture: hardcoded numeric values inside function bodies — failing.

This file triggers the no-hardcoded-values rule by embedding numeric literals
(learning_rate, epochs, batch_size) directly inside a function body.
This file is loaded by test fixtures and scanned against schemas.
"""

import os

CONFIG_PATH = os.environ.get("CONFIG_PATH", "default")


def train() -> None:
    """Train a model with hardcoded hyperparameters."""
    learning_rate = 0.001
    epochs = 10
    batch_size = 32
    print(f"lr={learning_rate}, epochs={epochs}, bs={batch_size}")


if __name__ == "__main__":
    train()
