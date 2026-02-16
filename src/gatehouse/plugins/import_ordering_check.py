"""Example custom check plugin for the gate engine.

Checks that imports are ordered: stdlib, third-party, local.

This file is referenced by a rule YAML like:

  check:
    type: "custom"
    plugin: "plugins/import_ordering_check.py"
    function: "check"

Plugin contract (v0.3.0+):
    def check(analyzer: SourceAnalyzer) -> list[dict]
    Each dict should contain at minimum a 'line' key.
"""

from __future__ import annotations

import ast
import sys
from typing import Any

# Use Python's own stdlib introspection (3.10+) so the set stays accurate
# across Python versions automatically.  Fall back to a static snapshot
# only for Python 3.9, which reached EOL October 2025.
if hasattr(sys, "stdlib_module_names"):
    STDLIB_MODULES: frozenset[str] = sys.stdlib_module_names
else:
    STDLIB_MODULES = frozenset({
        "abc", "argparse", "ast", "asyncio", "base64", "collections",
        "contextlib", "copy", "csv", "dataclasses", "datetime", "decimal",
        "enum", "functools", "glob", "hashlib", "http", "importlib",
        "inspect", "io", "itertools", "json", "logging", "math",
        "multiprocessing", "operator", "os", "pathlib", "pickle",
        "platform", "pprint", "queue", "random", "re", "shutil", "signal",
        "socket", "sqlite3", "string", "struct", "subprocess", "sys",
        "tempfile", "textwrap", "threading", "time", "tokenize",
        "traceback", "typing", "unittest", "urllib", "uuid", "warnings",
        "xml", "zipfile",
    })


def _get_import_name(node: ast.AST) -> str:
    """Extract the top-level module name from an import node.

    The extracted name feeds into ``_classify`` to determine ordering category.
    """
    if isinstance(node, ast.Import):
        return node.names[0].name.split(".")[0]
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            return node.module.split(".")[0]
    return ""


def _classify(name: str) -> int:
    """Classify an import as stdlib (0), third-party (1), or local (2).

    The numeric categories enforce the expected import sort order.
    """
    if name in STDLIB_MODULES:
        return 0
    if name.startswith("."):
        return 2
    return 1


def check(analyzer: Any) -> list[dict[str, Any]]:
    """Check that imports are ordered: stdlib, then third-party, then local.

    Args:
        analyzer: A SourceAnalyzer instance. Uses analyzer.source for parsing.

    Returns:
        A list of violation dicts, each with 'line' and optionally 'message'.
        Empty list if the code passes.
    """
    violations: list[dict[str, Any]] = []
    imports: list[tuple[int, str, int]] = []

    ast_tree = ast.parse(analyzer.source)
    for node in ast.iter_child_nodes(ast_tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            name = _get_import_name(node)
            category = _classify(name)
            imports.append((node.lineno, name, category))

    prev_category = -1
    for lineno, name, category in imports:
        if category < prev_category:
            violations.append({
                "line": lineno,
                "message": (
                    f"Import '{name}' is out of order "
                    f"(stdlib -> third-party -> local)"
                ),
            })
        prev_category = max(prev_category, category)

    return violations
