"""checks — check-type dispatch and rule evaluation against SourceAnalyzer.

Each check type is implemented as a pure function that receives a
SourceAnalyzer and returns a list of violation dicts.  The ``run_check()``
dispatcher maps the check-type string from rule YAML to the corresponding
function, following a strategy pattern where new check types only require a
new function and a dispatch branch.

Plugin trust model (v0.3.0):
    - Plugins are loaded ONLY from gate_home/plugins/ (first-party trusted).
    - Plugins execute in the same process (no subprocess isolation).
    - Subprocess isolation is planned for v0.4.0.
    - Plugin contract: def check(analyzer: SourceAnalyzer) -> list[dict]
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Any

from gatehouse._paths import plugins_dir
from gatehouse.lib import config
from gatehouse.lib.analyzer import SourceAnalyzer


# ---------------------------------------------------------------------------
# Dispatch function
# ---------------------------------------------------------------------------


def run_check(
    rule_obj: dict[str, Any],
    analyzer: SourceAnalyzer,
    gate_home: Path,
) -> list[dict[str, Any]]:
    """Dispatch a single rule's check to the appropriate implementation.

    Args:
        rule_obj: Resolved rule object with 'rule_data', 'params', etc.
        analyzer: The SourceAnalyzer for the file being checked.
        gate_home: Gate home directory for plugin resolution.

    Returns:
        List of violation dicts. Empty list means the rule passed.
    """
    rule_data = rule_obj["rule_data"]
    check_config: dict[str, Any] = rule_data.get("check", {})
    params: dict[str, Any] = rule_obj.get("params", {})
    check_type = check_config.get("type", "")

    ct = config.get("check_types")
    if check_type == ct["pattern_exists"]:
        return check_pattern_exists(analyzer, check_config, params)
    elif check_type == ct["ast_node_exists"]:
        return check_ast_node_exists(analyzer, check_config, params)
    elif check_type == ct["ast_check"]:
        return check_ast_check(analyzer, check_config, params)
    elif check_type == ct["token_scan"]:
        return check_token_scan(analyzer, check_config, params)
    elif check_type == ct["uppercase_assignments"]:
        return check_uppercase_assignments(analyzer, check_config, params)
    elif check_type == ct["docstring_contains"]:
        return check_docstring_contains(analyzer, check_config, params)
    elif check_type == ct["file_metric"]:
        return check_file_metric(analyzer, check_config, params)
    elif check_type == ct["custom"]:
        return check_custom(analyzer, check_config, params, gate_home)
    else:
        msg = config.get_str("messages.unknown_check_type")
        sys.stderr.write(
            msg.format(check_type=check_type, rule_id=rule_obj["id"]) + "\n"
        )
        return []


# ---------------------------------------------------------------------------
# Pattern checks
# ---------------------------------------------------------------------------


def check_pattern_exists(
    analyzer: SourceAnalyzer,
    check_config: dict[str, Any],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check for structural patterns via CST — replaces text scanning.

    Args:
        analyzer: Source analyzer for the file under inspection.
        check_config: Check configuration from the rule YAML.
        params: User-supplied parameter overrides.

    Returns:
        List of violation dicts.  Empty if the pattern is found.
    """
    pattern = check_config.get("pattern", "")
    violations: list[dict[str, Any]] = []
    patterns = config.get("patterns")
    locations = config.get("locations")
    error_line = config.get_int("defaults.error_line")

    if pattern == patterns["if_name_main"]:
        if not analyzer.has_main_guard():
            violations.append({"line": analyzer.line_count(), "source": ""})

    elif pattern == patterns["print_call_with_checkmark"]:
        if not analyzer.has_print_call():
            violations.append({"line": analyzer.line_count(), "source": ""})

    elif pattern == patterns["comment_block_starting_with"]:
        value = check_config.get("value", "")
        required_substrings = check_config.get("required_substrings", [])
        header = analyzer.header_comments()
        header_text = "\n".join(header)

        if value and not any(value in c for c in header):
            violations.append({"line": error_line, "source": ""})

        if not violations and required_substrings:
            for sub in required_substrings:
                clean_sub = sub.split("{")[0] if "{" in sub else sub
                if clean_sub and clean_sub not in header_text:
                    violations.append({"line": error_line, "source": ""})
                    break

    else:
        value = check_config.get("value", pattern)
        location = check_config.get("location", locations["anywhere"])
        source_lines = analyzer.source_lines

        if location == locations["first_non_empty_line"]:
            first_line = ""
            first_line_num = 0
            for i, line in enumerate(source_lines):
                if line.strip():
                    first_line = line
                    first_line_num = i + 1
                    break
            if value and value not in first_line:
                violations.append({
                    "line": first_line_num or error_line,
                    "source": first_line.rstrip() if first_line else "",
                })

        elif location == locations["anywhere"]:
            found = any(value in line for line in source_lines) if value else False
            if not found and value:
                try:
                    if re.search(value, analyzer.source):
                        found = True
                except re.error:
                    pass
            if not found:
                violations.append({
                    "line": error_line,
                    "source": source_lines[0].rstrip() if source_lines else "",
                })

        elif location == locations["end_of_file"]:
            if source_lines and value not in source_lines[-1]:
                violations.append({
                    "line": len(source_lines),
                    "source": source_lines[-1].rstrip(),
                })

    return violations


# ---------------------------------------------------------------------------
# AST checks
# ---------------------------------------------------------------------------


def check_ast_node_exists(
    analyzer: SourceAnalyzer,
    check_config: dict[str, Any],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check for existence of a structural element via CST.

    Args:
        analyzer: Source analyzer for the file under inspection.
        check_config: Check configuration from the rule YAML.
        params: User-supplied parameter overrides.

    Returns:
        List of violation dicts.  Empty if the required node exists.
    """
    node_type = check_config.get("node", "")
    required_substrings = check_config.get("required_substrings", [])
    violations: list[dict[str, Any]] = []
    nodes = config.get("node_types")
    error_line = config.get_int("defaults.error_line")

    if node_type == nodes["module_docstring"]:
        docstring = analyzer.get_module_docstring()
        if not docstring:
            violations.append({"line": error_line, "source": ""})
        elif required_substrings:
            for sub in required_substrings:
                if sub not in docstring:
                    violations.append({
                        "line": error_line,
                        "source": f'Missing "{sub}" in module docstring',
                    })
                    break

    elif node_type == nodes["import_statement"]:
        if not analyzer.has_import():
            violations.append({"line": error_line, "source": ""})

    return violations


def check_ast_check(
    analyzer: SourceAnalyzer,
    check_config: dict[str, Any],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run parameterized CST checks.

    Args:
        analyzer: Source analyzer for the file under inspection.
        check_config: Check configuration from the rule YAML.
        params: User-supplied parameter overrides.

    Returns:
        List of violation dicts from the delegated AST check.
    """
    check_name = check_config.get("check", "")
    violations: list[dict[str, Any]] = []
    ac = config.get("ast_checks")
    cm = config.get("check_modes")

    if check_name == ac["all_functions_docstrings"]:
        violations = analyzer.functions_missing_docstrings()

    elif check_name == ac["for_loops_progress"]:
        violations = analyzer.for_loops_without_progress()

    elif check_name == ac["decorated_docstrings"]:
        patterns = check_config.get("decorator_pattern", [])
        violations = analyzer.decorated_functions_check(patterns, cm["docstring"])

    elif check_name == ac["decorated_try_except"]:
        patterns = check_config.get("decorator_pattern", [])
        violations = analyzer.decorated_functions_check(patterns, cm["try_except"])

    return violations


def check_token_scan(
    analyzer: SourceAnalyzer,
    check_config: dict[str, Any],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Scan for hardcoded literals via CST; log scans use source lines.

    Args:
        analyzer: Source analyzer for the file under inspection.
        check_config: Check configuration including scan type and safe values.
        params: User-supplied parameter overrides.

    Returns:
        List of violation dicts for detected forbidden tokens.
    """
    scan_type = check_config.get("scan", "")
    violations: list[dict[str, Any]] = []
    st = config.get("scan_types")

    if scan_type == st["hardcoded_literals"]:
        safe_values: set[object] = set()
        for v in check_config.get("safe_values", []):
            safe_values.add(v)
        safe_contexts: list[str] = check_config.get("safe_contexts", [])
        violations = analyzer.literals_in_function_bodies(safe_values, safe_contexts)

    elif scan_type == st["log_calls_containing"]:
        log_keywords = tuple(config.get_list("defaults.log_keywords"))
        forbidden: list[str] = check_config.get("forbidden_strings", [])
        for i, line in enumerate(analyzer.source_lines):
            lower_line = line.lower()
            if any(kw in lower_line for kw in log_keywords):
                for forbidden_str in forbidden:
                    if forbidden_str.lower() in lower_line:
                        violations.append({
                            "line": i + 1,
                            "source": line.rstrip(),
                            "value": forbidden_str,
                        })

    return violations


def check_uppercase_assignments(
    analyzer: SourceAnalyzer,
    check_config: dict[str, Any],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check for uppercase module-level constant assignments via CST.

    Args:
        analyzer: Source analyzer for the file under inspection.
        check_config: Check configuration including minimum count threshold.
        params: User-supplied parameter overrides.

    Returns:
        List of violation dicts.  Non-empty if constant count is below minimum.
    """
    default_min = config.get_int("defaults.min_uppercase_count")
    min_count: int = check_config.get("min_count", default_min)
    violations: list[dict[str, Any]] = []
    error_line = config.get_int("defaults.error_line")

    count = len(analyzer.module_level_constants())
    if count < min_count:
        violations.append({"line": error_line, "source": ""})

    return violations


def check_docstring_contains(
    analyzer: SourceAnalyzer,
    check_config: dict[str, Any],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check that the module docstring contains specific text.

    Args:
        analyzer: Source analyzer for the file under inspection.
        check_config: Check configuration including the required value string.
        params: User-supplied parameter overrides.

    Returns:
        List of violation dicts.  Non-empty if the required text is absent.
    """
    value: str = check_config.get("value", "")
    violations: list[dict[str, Any]] = []
    error_line = config.get_int("defaults.error_line")

    docstring = analyzer.get_module_docstring()
    if not docstring or value not in docstring:
        violations.append({"line": error_line, "source": ""})

    return violations


# ---------------------------------------------------------------------------
# File metric checks
# ---------------------------------------------------------------------------


def check_file_metric(
    analyzer: SourceAnalyzer,
    check_config: dict[str, Any],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check file metrics (line count, etc.).

    Args:
        analyzer: Source analyzer for the file under inspection.
        check_config: Check configuration including metric type and threshold.
        params: User-supplied parameter overrides (e.g. ``max_lines``).

    Returns:
        List of violation dicts.  Non-empty if the metric exceeds the threshold.
    """
    metric: str = check_config.get("metric", "line_count")
    violations: list[dict[str, Any]] = []
    default_max = config.get_int("defaults.max_lines")

    max_val: int = params.get("max_lines", check_config.get("max_lines", default_max))

    if metric == "line_count":
        lc = analyzer.line_count()
        if lc > max_val:
            violations.append({
                "line": lc,
                "source": "",
                "line_count": lc,
            })

    return violations


# ---------------------------------------------------------------------------
# Custom / plugin checks
# ---------------------------------------------------------------------------


def check_custom(
    analyzer: SourceAnalyzer,
    check_config: dict[str, Any],
    params: dict[str, Any],
    gate_home: Path,
) -> list[dict[str, Any]]:
    """Run a custom check via plugin file.

    Inline ``expression`` checks have been removed (security risk).
    Use plugin files for custom checks.  The plugin contract:
    ``def check(analyzer: SourceAnalyzer) -> list[dict]``.
    Each dict should have at minimum a ``line`` key.

    Args:
        analyzer: Source analyzer for the file under inspection.
        check_config: Check configuration with plugin path and function name.
        params: User-supplied parameter overrides.
        gate_home: Gate home directory for resolving relative plugin paths.

    Returns:
        List of violation dicts returned by the plugin function.
    """
    violations: list[dict[str, Any]] = []
    error_line = config.get_int("defaults.error_line")

    if "expression" in check_config:
        sys.stderr.write(
            config.get_str("messages.expression_deprecated") + "\n"
        )
        return violations

    if "plugin" not in check_config:
        return violations

    plugin_path = check_config["plugin"]
    if not os.path.isabs(plugin_path):
        plugin_path = str(plugins_dir(gate_home) / os.path.basename(plugin_path))
    func_name: str = check_config.get(
        "function", config.get_str("defaults.plugin_function_name")
    )

    try:
        plugin_spec_name = config.get_str("defaults.plugin_spec_name")
        spec = importlib.util.spec_from_file_location(plugin_spec_name, plugin_path)
        if spec is None or spec.loader is None:
            msg = config.get_str("messages.plugin_load_error")
            raise ImportError(msg.format(path=plugin_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        func = getattr(mod, func_name)
        result = func(analyzer)
        if isinstance(result, list):
            violations.extend(result)
    except Exception as exc:
        msg = config.get_str("messages.plugin_error")
        sys.stderr.write(msg.format(rule_id="custom", error=exc) + "\n")
        violations.append({"line": error_line, "source": f"plugin error: {exc}"})

    return violations
