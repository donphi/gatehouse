"""
plugins/import_ordering_check.py

Example custom check plugin for the gate engine.
Checks that imports are ordered: stdlib, third-party, local.

This file is referenced by a rule YAML like:

  check:
    type: "custom"
    plugin: "plugins/import_ordering_check.py"
    function: "check"
"""

import ast
import sys


# Known standard library modules (subset — extend as needed)
STDLIB_MODULES = {
    "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
    "copy", "csv", "dataclasses", "datetime", "decimal", "enum", "functools",
    "glob", "hashlib", "http", "importlib", "inspect", "io", "itertools",
    "json", "logging", "math", "multiprocessing", "operator", "os", "pathlib",
    "pickle", "platform", "pprint", "queue", "random", "re", "shutil",
    "signal", "socket", "sqlite3", "string", "struct", "subprocess", "sys",
    "tempfile", "textwrap", "threading", "time", "tokenize", "traceback",
    "typing", "unittest", "urllib", "uuid", "warnings", "xml", "zipfile",
}


def _get_import_name(node):
    """Extract the top-level module name from an import node."""
    if isinstance(node, ast.Import):
        return node.names[0].name.split(".")[0]
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            return node.module.split(".")[0]
    return ""


def _classify(name):
    """Classify an import as stdlib (0), third-party (1), or local (2)."""
    if name in STDLIB_MODULES:
        return 0
    # Heuristic: if it starts with "." it's relative/local
    if name.startswith("."):
        return 2
    # Otherwise assume third-party
    return 1


def check(source, ast_tree, filepath):
    """
    Check that imports are ordered: stdlib first, then third-party, then local.

    Args:
        source: The raw source code as a string
        ast_tree: The parsed AST
        filepath: Path to the file being checked

    Returns:
        A list of violation dicts, each with "line" and optionally "message".
        Return an empty list if the code passes.
    """
    violations = []
    imports = []

    for node in ast.iter_child_nodes(ast_tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            name = _get_import_name(node)
            category = _classify(name)
            imports.append((node.lineno, name, category))

    # Check ordering
    prev_category = -1
    for lineno, name, category in imports:
        if category < prev_category:
            violations.append({
                "line": lineno,
                "message": f"Import '{name}' is out of order (stdlib → third-party → local)",
            })
        prev_category = max(prev_category, category)

    return violations
