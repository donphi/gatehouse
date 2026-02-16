"""formatter — violation output formatting for stderr, JSON, and traceback.

Provides stderr (human-readable), JSON (structured), and traceback-style
(SyntaxError-like) formatters for violation output.  Template variables
from ``SourceAnalyzer.build_variables()`` are injected into error message
and fix templates via simple ``{key}`` placeholder replacement before each
formatter renders its final output.
"""

from __future__ import annotations

from typing import Any

from gatehouse.lib import config
from gatehouse.lib.theme import code as _c


# ---------------------------------------------------------------------------
# Variable injection
# ---------------------------------------------------------------------------


def inject_variables(template: str, variables: dict[str, Any]) -> str:
    """Replace {variable} placeholders in a template string.

    Args:
        template: String containing {key} placeholders.
        variables: Mapping of key names to replacement values.

    Returns:
        Template with all recognized placeholders replaced.
    """
    result = template
    for key, val in variables.items():
        result = result.replace(f"{{{key}}}", str(val))
    return result


# ---------------------------------------------------------------------------
# Stderr formatting
# ---------------------------------------------------------------------------


def format_violation_stderr(
    rule_obj: dict[str, Any],
    violation: dict[str, Any],
    variables: dict[str, Any],
) -> str:
    """Format a single violation for stderr output.

    Args:
        rule_obj: The resolved rule object.
        violation: Single violation dict with line, source, etc.
        variables: Template variables for message injection.

    Returns:
        Formatted multi-line string for stderr.
    """
    rule_data = rule_obj["rule_data"]
    error_config: dict[str, Any] = rule_data.get("error", {})
    default_msg = config.get_str("messages.default_violation").format(
        rule_id=rule_obj["id"]
    )
    message = error_config.get("message", default_msg)
    fix = error_config.get("fix", "")

    merged = dict(variables)
    merged.update(violation)

    message = inject_variables(message, merged)
    fix = inject_variables(fix, merged)

    filepath = merged.get("filepath", "")
    fallback_line = config.get_int("defaults.fallback_line")
    line = violation.get("line", fallback_line)
    source = violation.get("source", "")

    file_line_tpl = config.get_str("traceback.file_line_template")
    caret = config.get_str("formatting.caret_char")
    fix_prefix = config.get_str("messages.fix_prefix")

    parts: list[str] = []
    parts.append(
        f"  {_c('file_path')}{file_line_tpl.format(filepath=filepath, line=line)}"
        f"{_c('reset')}"
    )
    if source:
        parts.append(f"    {source}")
        if violation.get("value"):
            val_str = str(violation["value"])
            col = source.find(val_str)
            if col >= 0:
                parts.append(
                    f"    {_c('caret')}{' ' * col}"
                    f"{caret * len(val_str)}{_c('reset')}"
                )
    parts.append(f"  {_c('error')}{message}{_c('reset')}")
    if fix:
        fix_lines = fix.strip().splitlines()
        parts.append(f"  {_c('fix')}{fix_prefix}{fix_lines[0]}{_c('reset')}")
        for fl in fix_lines[1:]:
            padding = " " * len(fix_prefix)
            parts.append(f"  {_c('fix')}{padding}{fl}{_c('reset')}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# JSON formatting
# ---------------------------------------------------------------------------


def format_violations_json(
    rule_violations: list[tuple[dict[str, Any], list[dict[str, Any]]]],
    variables: dict[str, Any],
    schema_name: str,
    schema_version: str,
) -> dict[str, Any]:
    """Format all violations as structured JSON-compatible dict.

    Args:
        rule_violations: List of (rule_obj, violations) tuples.
        variables: Template variables for message injection.
        schema_name: Name of the active schema.
        schema_version: Version of the active schema.

    Returns:
        Dict suitable for json.dumps().
    """
    sev_block = config.get_str("severities.block")
    sev_warn = config.get_str("severities.warn")
    status_rejected = config.get_str("statuses.rejected")
    status_passed = config.get_str("statuses.passed")
    fallback_line = config.get_int("defaults.fallback_line")

    all_violations: list[dict[str, Any]] = []
    for rule_obj, violations in rule_violations:
        rule_data = rule_obj["rule_data"]
        error_config: dict[str, Any] = rule_data.get("error", {})
        for v in violations:
            merged = dict(variables)
            merged.update(v)
            all_violations.append({
                "rule": rule_obj["id"],
                "severity": rule_obj["severity"],
                "line": v.get("line", fallback_line),
                "source": v.get("source", ""),
                "message": inject_variables(error_config.get("message", ""), merged),
                "fix": inject_variables(error_config.get("fix", ""), merged),
            })

    blocking = sum(
        1 for ro, vs in rule_violations for _ in vs if ro["severity"] == sev_block
    )
    warnings = sum(
        1 for ro, vs in rule_violations for _ in vs if ro["severity"] == sev_warn
    )

    return {
        "status": status_rejected if blocking > 0 else status_passed,
        "file": variables.get("filepath", ""),
        "violations": all_violations,
        "summary": {
            "blocking": blocking,
            "warnings": warnings,
            "total_rules": len(rule_violations),
        },
    }


# ---------------------------------------------------------------------------
# Stderr summary
# ---------------------------------------------------------------------------


def format_summary_stderr(
    schema_name: str,
    schema_version: str,
    blocking_count: int,
    warning_count: int,
) -> str:
    """Format the summary footer bar for stderr output.

    Args:
        schema_name: Name of the active schema.
        schema_version: Version of the active schema.
        blocking_count: Number of blocking violations.
        warning_count: Number of warning violations.

    Returns:
        Formatted summary string.
    """
    bar_width = config.get_int("formatting.summary_bar_width")
    bar_char = config.get_str("formatting.summary_bar_char")
    lbl_schema = config.get_str("labels.schema")
    lbl_violations = config.get_str("labels.violations")
    lbl_blocking = config.get_str("labels.blocking")
    lbl_warnings = config.get_str("labels.warnings")
    lbl_blocked = config.get_str("labels.execution_blocked")
    lbl_allowed = config.get_str("labels.execution_allowed")

    bar = f"{_c('summary_bar')}{bar_char * bar_width}{_c('reset')}"
    parts: list[str] = [f"\n{bar}"]
    parts.append(
        f"  {_c('bold')}{lbl_schema}{_c('reset')} "
        f"{_c('info')}{schema_name}{_c('reset')} "
        f"{_c('dim')}(v{schema_version}){_c('reset')}"
    )
    parts.append(
        f"  {_c('bold')}{lbl_violations}{_c('reset')} "
        f"{_c('error')}{blocking_count} {lbl_blocking}{_c('reset')}, "
        f"{_c('warning')}{warning_count} {lbl_warnings}{_c('reset')}"
    )
    if blocking_count > 0:
        parts.append(
            f"  {_c('blocked')}{_c('bold')}{lbl_blocked}{_c('reset')}"
        )
    else:
        parts.append(
            f"  {_c('allowed')}{lbl_allowed}{_c('reset')}"
        )
    parts.append(bar)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Traceback formatting
# ---------------------------------------------------------------------------


def format_violation_traceback(
    filepath: str,
    violations: list[dict[str, Any]],
) -> str:
    """Format violations in SyntaxError-style traceback format.

    Args:
        filepath: Path to the file with violations.
        violations: List of violation dicts with line, message, fix keys.

    Returns:
        Traceback-formatted string.
    """
    tb_header = config.get_str("formatting.traceback_header")
    file_line_tpl = config.get_str("traceback.file_line_template")
    exc_prefix = config.get_str("traceback.exception_prefix")
    error_name = config.get_str("traceback.error_name")
    fix_prefix = config.get_str("messages.fix_prefix")
    fallback_line = config.get_int("defaults.fallback_line")

    parts: list[str] = [tb_header]
    for v in violations:
        line = v.get("line", fallback_line)
        source = v.get("source", "")
        message = v.get("message", error_name)
        parts.append(f"  {file_line_tpl.format(filepath=filepath, line=line)}")
        if source:
            parts.append(f"    {source}")
        parts.append(f"{exc_prefix}{message}")
        fix = v.get("fix", "")
        if fix:
            parts.append(f"  {fix_prefix}{fix.strip().splitlines()[0]}")
    return "\n".join(parts)
