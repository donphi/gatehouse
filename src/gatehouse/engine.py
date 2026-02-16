"""Gatehouse engine — thin orchestrator for schema enforcement.

Composes the library modules to scan a Python source string against
a schema and return structured results. This is the main entry point
for programmatic usage.

Design notes:
    The engine never parses source directly — it delegates to
    SourceAnalyzer (lib/analyzer) for CST construction and to
    lib/checks for rule evaluation. This keeps the engine as a
    pure orchestration layer with no parsing or analysis logic.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from gatehouse import __version__ as VERSION
from gatehouse.exceptions import GatehouseParseError
from gatehouse.lib import config
from gatehouse.lib.checks import run_check
from gatehouse.lib.formatter import (
    format_summary_stderr,
    format_violation_stderr,
    format_violations_json,
    inject_variables,
)
from gatehouse.lib.logger import log_scan
from gatehouse.lib.rules import (
    apply_project_overrides,
    find_gate_home,
    load_project_config,
    load_schema,
    resolve_rules,
)
from gatehouse.lib.scope import is_file_in_scope, resolve_effective_schema


@dataclass
class Violation:
    """A single rule violation found during scanning."""

    rule_id: str
    severity: str
    line: int
    source: str
    message: str
    fix: str


@dataclass
class ScanResult:
    """Result of scanning a file against a schema."""

    status: str
    violations: list[Violation] = field(default_factory=list)
    blocking_count: int = 0
    warning_count: int = 0
    scan_ms: int = 0
    schema_name: str = ""
    schema_version: str = ""


def scan_file(
    source: str,
    filepath: str,
    schema_path: str,
    *,
    output_format: str = "",
    skip_scope: bool = False,
) -> ScanResult:
    """Scan a Python source string against the schema.

    This is the primary entry point for Gatehouse enforcement.

    Args:
        source: Python source code as a string.
        filepath: Path to the file (used for scope checking and templates).
        schema_path: Path to the .gate_schema.yaml project config.
        output_format: 'stderr' for human output, 'json' for structured.
            Defaults to the value from config.
        skip_scope: If True, skip gated_paths scope checking.

    Returns:
        ScanResult with status, violations, and timing.
    """
    if not output_format:
        output_format = config.get_str("formats.default")

    status_passed = config.get_str("statuses.passed")
    sev_off = config.get_str("severities.off")
    sev_block = config.get_str("severities.block")
    sev_warn = config.get_str("severities.warn")
    status_rejected = config.get_str("statuses.rejected")
    fallback_line = config.get_int("defaults.fallback_line")
    error_line = config.get_int("defaults.error_line")
    default_version = config.get_str("defaults.schema_version")
    fmt_json = config.get_str("formats.json")
    violation_sep = config.get_str("formatting.violation_separator")
    json_indent = config.get_int("defaults.json_indent")

    start = time.time()

    # 1. Resolve gate home and project config
    gate_home = find_gate_home()
    if not gate_home:
        return ScanResult(status=status_passed)

    project_config = load_project_config(schema_path)
    if not project_config:
        return ScanResult(status=status_passed)

    # 2. Determine effective schema for this file path
    schema_name = resolve_effective_schema(filepath, project_config)
    if schema_name is None:
        return ScanResult(status=status_passed)

    schema_data = load_schema(schema_name, gate_home)
    if not schema_data:
        msg = config.get_str("messages.schema_not_found")
        sys.stderr.write(msg.format(name=schema_name, path="") + "\n")
        return ScanResult(status=status_passed)

    # 3. Check file scope (early exit if out of scope)
    if not skip_scope and not is_file_in_scope(filepath, schema_data, project_config):
        return ScanResult(status=status_passed)

    # 4. Load and filter active rules
    rules = resolve_rules(schema_data, gate_home)
    rules = apply_project_overrides(rules, project_config)
    active_rules = [r for r in rules if r["enabled"] and r["severity"] != sev_off]

    # 5. Parse source and run checks against each rule
    # Wrap parse errors so callers get a GatehouseParseError instead of
    # an opaque LibCST exception they cannot handle.
    try:
        from gatehouse.lib.analyzer import SourceAnalyzer

        analyzer = SourceAnalyzer(source, filepath)
    except Exception as exc:
        raise GatehouseParseError(filepath, exc) from exc

    all_rule_violations: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    passed_rules: list[str] = []
    violations_log: list[dict[str, Any]] = []
    variables = analyzer.build_variables()

    for rule_obj in active_rules:
        try:
            violations = run_check(rule_obj, analyzer, gate_home)
        except Exception as exc:
            msg = config.get_str("messages.rule_exception")
            sys.stderr.write(
                "  " + msg.format(
                    rule_id=rule_obj["id"],
                    error=type(exc).__name__,
                    detail=str(exc),
                ) + "\n"
            )
            err_msg = config.get_str("messages.internal_rule_error")
            violations = [
                {
                    "line": error_line,
                    "source": err_msg.format(rule_id=rule_obj["id"]),
                }
            ]

        if violations:
            all_rule_violations.append((rule_obj, violations))
            for v in violations:
                # Merge analyzer variables with per-violation overrides so
                # that template strings in error messages can reference both.
                merged = dict(variables)
                merged.update(v)
                violations_log.append({
                    "rule": rule_obj["id"],
                    "severity": rule_obj["severity"],
                    "line": v.get("line", fallback_line),
                })
        else:
            passed_rules.append(rule_obj["id"])

    # 6. Compute timing and violation counts
    scan_ms = int((time.time() - start) * 1000)

    blocking_count = sum(
        len(vs) for ro, vs in all_rule_violations if ro["severity"] == sev_block
    )
    warning_count = sum(
        len(vs) for ro, vs in all_rule_violations if ro["severity"] == sev_warn
    )

    status = status_rejected if blocking_count > 0 else status_passed
    schema_version = schema_data.get("schema", {}).get("version", default_version)

    # 7. Log scan results (if enabled)
    log_dir = project_config.get("logging", {}).get("directory", "")
    if project_config.get("logging", {}).get("enabled", False) and log_dir:
        log_scan(
            log_dir,
            filepath,
            schema_name,
            schema_version,
            status,
            violations_log,
            passed_rules,
            len(active_rules),
            source,
            scan_ms,
        )

    # 8. Format output and return result
    structured_violations: list[Violation] = []
    for rule_obj, violations in all_rule_violations:
        rule_data = rule_obj["rule_data"]
        error_config = rule_data.get("error", {})
        for v in violations:
            # Build a merged dict so template variables from the analyzer
            # (e.g. filename, line_count) coexist with violation-specific
            # fields (e.g. line, source) for message interpolation.
            merged = dict(variables)
            merged.update(v)
            structured_violations.append(Violation(
                rule_id=rule_obj["id"],
                severity=rule_obj["severity"],
                line=v.get("line", fallback_line),
                source=v.get("source", ""),
                message=inject_variables(error_config.get("message", ""), merged),
                fix=inject_variables(error_config.get("fix", ""), merged),
            ))

    result = ScanResult(
        status=status,
        violations=structured_violations,
        blocking_count=blocking_count,
        warning_count=warning_count,
        scan_ms=scan_ms,
        schema_name=schema_name,
        schema_version=schema_version,
    )

    if output_format == fmt_json:
        json_data = format_violations_json(
            all_rule_violations, variables, schema_name, schema_version
        )
        sys.stderr.write(json.dumps(json_data, indent=json_indent))
    elif all_rule_violations:
        output_parts: list[str] = []
        for rule_obj, violations in all_rule_violations:
            for v in violations:
                merged = dict(variables)
                merged.update(v)
                output_parts.append(format_violation_stderr(rule_obj, v, merged))
        output_parts.append(
            format_summary_stderr(
                schema_name, schema_version, blocking_count, warning_count
            )
        )
        sys.stderr.write(violation_sep.join(output_parts) + "\n")

    return result


def main() -> None:
    """CLI entry point for python -m gatehouse.engine."""
    import argparse

    fmt_stderr = config.get_str("formats.stderr")
    fmt_json = config.get_str("formats.json")
    stdin_filename = config.get_str("defaults.stdin_filename")
    exit_blocked = config.get_int("exit_codes.blocked")
    exit_ok = config.get_int("exit_codes.ok")
    exit_error = config.get_int("exit_codes.error")

    parser = argparse.ArgumentParser(
        description="Gate Engine — Schema enforcement for Python files",
    )
    parser.add_argument("--file", help="Path to the Python file to check")
    parser.add_argument(
        "--stdin", action="store_true", help="Read code from stdin"
    )
    parser.add_argument(
        "--filename", help="Filename to use when reading from stdin"
    )
    parser.add_argument(
        "--schema", required=True, help="Path to .gate_schema.yaml"
    )
    parser.add_argument(
        "--format",
        choices=[fmt_stderr, fmt_json],
        default=fmt_stderr,
        help="Output format",
    )
    parser.add_argument(
        "--no-scope",
        action="store_true",
        help="Skip scope checking (used by python_gate)",
    )
    parser.add_argument(
        "--version", action="version", version=f"gatehouse {VERSION}"
    )

    args = parser.parse_args()

    if args.stdin:
        source = sys.stdin.read()
        filepath = args.filename or stdin_filename
    elif args.file:
        filepath = args.file
        with open(filepath, "r", encoding="utf-8") as fh:
            source = fh.read()
    else:
        parser.error("Either --file or --stdin is required")
        return

    try:
        result = scan_file(
            source,
            filepath,
            args.schema,
            output_format=args.format,
            skip_scope=args.no_scope,
        )
    except GatehouseParseError as exc:
        sys.stderr.write(f"  {exc}\n")
        sys.exit(exit_error)

    sys.exit(exit_blocked if result.blocking_count > 0 else exit_ok)


if __name__ == "__main__":
    main()
