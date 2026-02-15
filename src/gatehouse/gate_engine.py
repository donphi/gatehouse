#!/usr/bin/env python3
"""
gate_engine.py — Fixed runtime for error-driven code schema enforcement.

This engine NEVER changes when rules change. All behavior comes from:
  - Rule YAML files in rules/   (discovered via gatehouse._paths)
  - Schema manifests in schemas/ (discovered via gatehouse._paths)
  - Project config in .gate_schema.yaml

Resource discovery: all paths are resolved through gatehouse._paths, which
auto-discovers the package directory. Set $GATE_HOME to override.

Usage:
  python3 -m gatehouse.gate_engine --file src/train.py --schema .gate_schema.yaml
  echo "code" | python3 -m gatehouse.gate_engine --stdin --schema .gate_schema.yaml --filename src/train.py
"""

import datetime
import hashlib
import json
import os
import re
import sys

from gatehouse import __version__ as VERSION
from gatehouse._paths import get_gate_home, plugins_dir, rules_dir, schemas_dir, theme_path

# ---------------------------------------------------------------------------
# YAML loader (minimal, no external dependency)
# Falls back to a simple parser if PyYAML is not installed.
# ---------------------------------------------------------------------------

try:
    import yaml

    def load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_yaml_string(text):
        return yaml.safe_load(text)

except ImportError:
    # Minimal YAML subset parser — handles the rule/schema files we generate.
    # For production use, install PyYAML.
    def _mini_yaml_parse(text):
        """Very small YAML-subset parser. Handles flat keys, lists, nested dicts."""
        import json as _json
        # Try JSON first (some of our files are JSON-compatible YAML)
        try:
            return _json.loads(text)
        except Exception:
            pass
        result = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                val = val.strip()
                if val:
                    # Try to parse as JSON value
                    for parser in [_json.loads, int, float]:
                        try:
                            result[key.strip()] = parser(val)
                            break
                        except Exception:
                            continue
                    else:
                        result[key.strip()] = val.strip('"').strip("'")
        return result

    def load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return _mini_yaml_parse(f.read())

    def load_yaml_string(text):
        return _mini_yaml_parse(text)


# ---------------------------------------------------------------------------
# Theme / colour helpers
# ---------------------------------------------------------------------------


def _load_theme() -> dict:
    """Load ANSI theme from cli/theme.yaml. Returns resolved role→code mapping."""
    tp = theme_path()
    if not tp.is_file():
        return {}
    raw = load_yaml(str(tp))
    if not raw:
        return {}
    ansi = raw.get("ansi", {})
    roles = raw.get("roles", {})
    resolved = {}
    for role, color_name in roles.items():
        resolved[role] = ansi.get(color_name, "")
    resolved["bold"] = ansi.get("bold", "")
    resolved["dim"] = ansi.get("dim", "")
    resolved["reset"] = ansi.get("reset", "")
    return resolved


_THEME = _load_theme()


def _c(role: str) -> str:
    """Return the ANSI code for a semantic role. Empty string if not found or not a TTY."""
    if not sys.stderr.isatty():
        return ""
    return _THEME.get(role, "")


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------

def find_gate_home() -> str | None:
    """Resolve gate home directory (auto-discovered or $GATE_HOME override)."""
    home = get_gate_home()
    if home.is_dir():
        return str(home)
    return None


def load_rule(rule_id: str, gate_home: str) -> dict | None:
    """Load a single rule YAML file by ID."""
    rule_path = rules_dir(None) / f"{rule_id}.yaml"
    if not rule_path.is_file():
        return None
    return load_yaml(str(rule_path))


def load_schema(schema_name: str, gate_home: str) -> dict | None:
    """Load a schema manifest by name."""
    schema_path = schemas_dir(None) / f"{schema_name}.yaml"
    if not schema_path.is_file():
        return None
    return load_yaml(str(schema_path))


def resolve_rules(schema_data, gate_home):
    """
    Given a loaded schema dict, resolve all rule references into full rule objects.
    Applies severity/enabled/params overrides from the schema.
    Handles 'extends' for schema inheritance.
    """
    rules = []

    # Handle schema inheritance
    if schema_data.get("extends"):
        parent = load_schema(schema_data["extends"], gate_home)
        if parent:
            rules = resolve_rules(parent, gate_home)

    # Load rules listed in this schema
    schema_rules = schema_data.get("rules", [])
    if isinstance(schema_rules, list):
        for entry in schema_rules:
            if isinstance(entry, str):
                entry = {"id": entry}
            rule_id = entry.get("id")
            if not rule_id:
                continue

            rule_data = load_rule(rule_id, gate_home)
            if not rule_data:
                sys.stderr.write(f"Warning: Rule '{rule_id}' not found in {rules_dir()}\n")
                continue

            # Apply overrides from schema
            defaults = rule_data.get("defaults", {})
            severity = entry.get("severity", defaults.get("severity", "warn"))
            enabled = entry.get("enabled", defaults.get("enabled", True))
            params = entry.get("params", {})

            rule_obj = {
                "id": rule_id,
                "rule_data": rule_data,
                "severity": severity,
                "enabled": enabled,
                "params": params,
            }
            # Replace if already exists (from parent), otherwise append
            existing_ids = [r["id"] for r in rules]
            if rule_id in existing_ids:
                idx = existing_ids.index(rule_id)
                rules[idx] = rule_obj
            else:
                rules.append(rule_obj)

    # Handle additional_rules (for extends schemas)
    for entry in schema_data.get("additional_rules", []):
        if isinstance(entry, str):
            entry = {"id": entry}
        rule_id = entry.get("id")
        if not rule_id:
            continue
        rule_data = load_rule(rule_id, gate_home)
        if not rule_data:
            sys.stderr.write(f"Warning: Rule '{rule_id}' not found in {rules_dir()}\n")
            continue
        defaults = rule_data.get("defaults", {})
        rule_obj = {
            "id": rule_id,
            "rule_data": rule_data,
            "severity": entry.get("severity", defaults.get("severity", "warn")),
            "enabled": entry.get("enabled", defaults.get("enabled", True)),
            "params": {},
        }
        rules.append(rule_obj)

    return rules


def load_project_config(schema_path):
    """Load the project's .gate_schema.yaml."""
    return load_yaml(schema_path)


def apply_project_overrides(rules, project_config):
    """Apply rule_overrides from the project config."""
    overrides = project_config.get("rule_overrides", {})
    if not overrides:
        return rules

    for rule in rules:
        rule_id = rule["id"]
        if rule_id in overrides:
            ovr = overrides[rule_id]
            if "severity" in ovr:
                rule["severity"] = ovr["severity"]
            if "enabled" in ovr:
                rule["enabled"] = ovr["enabled"]
            if "params" in ovr:
                rule["params"].update(ovr["params"])

    return rules


# ---------------------------------------------------------------------------
# Check type implementations — all use SourceAnalyzer (LibCST)
# ---------------------------------------------------------------------------

def check_pattern_exists(analyzer, check_config, params):
    """Check for structural patterns via CST — replaces text scanning."""
    pattern = check_config.get("pattern", "")
    violations = []

    if pattern == "if_name_main":
        if not analyzer.has_main_guard():
            violations.append({"line": analyzer.line_count(), "source": ""})

    elif pattern == "print_call_with_checkmark":
        if not analyzer.has_print_call():
            violations.append({"line": analyzer.line_count(), "source": ""})

    elif pattern == "comment_block_starting_with":
        value = check_config.get("value", "")
        required_substrings = check_config.get("required_substrings", [])
        header = analyzer.header_comments()
        header_text = "\n".join(header)

        if value and not any(value in c for c in header):
            violations.append({"line": 1, "source": ""})

        if not violations and required_substrings:
            for sub in required_substrings:
                clean_sub = sub.split("{")[0] if "{" in sub else sub
                if clean_sub and clean_sub not in header_text:
                    violations.append({"line": 1, "source": ""})
                    break

    else:
        value = check_config.get("value", pattern)
        location = check_config.get("location", "anywhere")
        source_lines = analyzer.source_lines

        if location == "first_non_empty_line":
            first_line = ""
            first_line_num = 0
            for i, line in enumerate(source_lines):
                if line.strip():
                    first_line = line
                    first_line_num = i + 1
                    break
            if value and value not in first_line:
                violations.append({
                    "line": first_line_num or 1,
                    "source": first_line.rstrip() if first_line else "",
                })
        elif location == "anywhere":
            found = any(value in line for line in source_lines) if value else False
            if not found and value:
                try:
                    if re.search(value, analyzer.source):
                        found = True
                except re.error:
                    pass
            if not found:
                violations.append({"line": 1, "source": source_lines[0].rstrip() if source_lines else ""})
        elif location == "end_of_file":
            if source_lines and value not in source_lines[-1]:
                violations.append({"line": len(source_lines), "source": source_lines[-1].rstrip()})

    return violations


def check_ast_node_exists(analyzer, check_config):
    """Check for existence of a structural element via CST."""
    node_type = check_config.get("node", "")
    required_substrings = check_config.get("required_substrings", [])
    violations = []

    if node_type == "module_docstring":
        docstring = analyzer.get_module_docstring()
        if not docstring:
            violations.append({"line": 1, "source": ""})
        elif required_substrings:
            for sub in required_substrings:
                if sub not in docstring:
                    violations.append({"line": 1, "source": f'Missing "{sub}" in module docstring'})
                    break

    elif node_type == "import_statement":
        if not analyzer.has_import():
            violations.append({"line": 1, "source": ""})

    return violations


def check_ast_check(analyzer, check_config):
    """Run parameterized CST checks."""
    check_name = check_config.get("check", "")
    violations = []

    if check_name == "all_functions_have_docstrings":
        violations = analyzer.functions_missing_docstrings()

    elif check_name == "for_loops_without_progress":
        violations = analyzer.for_loops_without_progress()

    elif check_name == "decorated_functions_have_docstrings":
        patterns = check_config.get("decorator_pattern", [])
        violations = analyzer.decorated_functions_check(patterns, "docstring")

    elif check_name == "decorated_functions_have_try_except":
        patterns = check_config.get("decorator_pattern", [])
        violations = analyzer.decorated_functions_check(patterns, "try_except")

    return violations


def check_token_scan(analyzer, check_config):
    """Scan for hardcoded literals via CST; log scans use source lines."""
    scan_type = check_config.get("scan", "")
    violations = []

    if scan_type == "hardcoded_literals":
        safe_values = set()
        for v in check_config.get("safe_values", []):
            safe_values.add(v)
        safe_contexts = check_config.get("safe_contexts", [])
        violations = analyzer.literals_in_function_bodies(safe_values, safe_contexts)

    elif scan_type == "log_calls_containing":
        forbidden = check_config.get("forbidden_strings", [])
        for i, line in enumerate(analyzer.source_lines):
            lower_line = line.lower()
            if any(kw in lower_line for kw in ["log.", "logging.", "print(", "logger."]):
                for forbidden_str in forbidden:
                    if forbidden_str.lower() in lower_line:
                        violations.append({
                            "line": i + 1,
                            "source": line.rstrip(),
                            "value": forbidden_str,
                        })

    return violations


def check_uppercase_assignments(analyzer, check_config):
    """Check for uppercase module-level constant assignments via CST."""
    min_count = check_config.get("min_count", 1)
    violations = []

    count = len(analyzer.module_level_constants())
    if count < min_count:
        violations.append({"line": 1, "source": ""})

    return violations


def check_docstring_contains(analyzer, check_config):
    """Check that the module docstring contains specific text."""
    value = check_config.get("value", "")
    violations = []

    docstring = analyzer.get_module_docstring()
    if not docstring or value not in docstring:
        violations.append({"line": 1, "source": ""})

    return violations


def check_file_metric(analyzer, check_config, params):
    """Check file metrics (line count, etc.)."""
    metric = check_config.get("metric", "line_count")
    violations = []

    max_val = params.get("max_lines", check_config.get("max_lines", 1000))

    if metric == "line_count":
        lc = analyzer.line_count()
        if lc > max_val:
            violations.append({
                "line": lc,
                "source": "",
                "line_count": lc,
            })

    return violations


def check_custom(analyzer, check_config):
    """Run a custom check (inline expression or plugin)."""
    violations = []

    if "expression" in check_config:
        expr = check_config["expression"]
        try:
            result = eval(expr, {
                "source_lines": analyzer.source_lines,
                "source": analyzer.source,
                "filepath": analyzer.filepath,
                "re": re,
            })
            if result:
                violations.append({"line": 1, "source": ""})
        except Exception as e:
            sys.stderr.write(f"Custom check expression error: {e}\n")

    elif "plugin" in check_config:
        plugin_path = check_config["plugin"]
        if not os.path.isabs(plugin_path):
            plugin_path = str(plugins_dir() / os.path.basename(plugin_path))
        func_name = check_config.get("function", "check")
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("plugin", plugin_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            func = getattr(mod, func_name)
            result = func(analyzer.source, None, analyzer.filepath)
            if isinstance(result, list):
                violations.extend(result)
        except Exception as e:
            sys.stderr.write(f"Custom check plugin error: {e}\n")

    return violations


# ---------------------------------------------------------------------------
# Main check dispatcher
# ---------------------------------------------------------------------------

def run_check(rule_obj, analyzer):
    """
    Run a single rule's check against the SourceAnalyzer.
    Returns a list of violation dicts.
    """
    rule_data = rule_obj["rule_data"]
    check_config = rule_data.get("check", {})
    params = rule_obj.get("params", {})
    check_type = check_config.get("type", "")

    if check_type == "pattern_exists":
        return check_pattern_exists(analyzer, check_config, params)
    elif check_type == "ast_node_exists":
        return check_ast_node_exists(analyzer, check_config)
    elif check_type == "ast_check":
        return check_ast_check(analyzer, check_config)
    elif check_type == "token_scan":
        return check_token_scan(analyzer, check_config)
    elif check_type == "uppercase_assignments_exist":
        return check_uppercase_assignments(analyzer, check_config)
    elif check_type == "docstring_contains":
        return check_docstring_contains(analyzer, check_config)
    elif check_type == "file_metric":
        return check_file_metric(analyzer, check_config, params)
    elif check_type == "custom":
        return check_custom(analyzer, check_config)
    else:
        sys.stderr.write(f"Warning: Unknown check type '{check_type}' in rule '{rule_obj['id']}'\n")
        return []


# ---------------------------------------------------------------------------
# Variable injection
# ---------------------------------------------------------------------------

def build_variables(analyzer, extra=None):
    """Build the variable dict for error template injection via SourceAnalyzer."""
    return analyzer.build_variables(extra)


def inject_variables(template, variables):
    """Replace {variable} placeholders in a template string."""
    result = template
    for key, val in variables.items():
        result = result.replace(f"{{{key}}}", str(val))
    return result


# ---------------------------------------------------------------------------
# Error formatting (stderr)
# ---------------------------------------------------------------------------

def format_violation_stderr(rule_obj, violation, variables):
    """Format a single violation for stderr output."""
    rule_data = rule_obj["rule_data"]
    error_config = rule_data.get("error", {})
    message = error_config.get("message", f"Violation of rule '{rule_obj['id']}'")
    fix = error_config.get("fix", "")

    # Merge violation-specific variables
    v = dict(variables)
    v.update(violation)

    message = inject_variables(message, v)
    fix = inject_variables(fix, v)

    filepath = v.get("filepath", "")
    line = violation.get("line", 0)
    source = violation.get("source", "")

    parts = []
    parts.append(f"  {_c('file_path')}File \"{filepath}\", line {line}{_c('reset')}")
    if source:
        parts.append(f"    {source}")
        if violation.get("value"):
            val_str = str(violation["value"])
            col = source.find(val_str)
            if col >= 0:
                parts.append(f"    {_c('caret')}{' ' * col}{'^' * len(val_str)}{_c('reset')}")
    parts.append(f"  {_c('error')}{message}{_c('reset')}")
    if fix:
        fix_lines = fix.strip().splitlines()
        parts.append(f"  {_c('fix')}Fix: {fix_lines[0]}{_c('reset')}")
        for fl in fix_lines[1:]:
            parts.append(f"  {_c('fix')}     {fl}{_c('reset')}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Error formatting (JSON)
# ---------------------------------------------------------------------------

def format_violations_json(rule_violations, variables, schema_name, schema_version):
    """Format all violations as structured JSON."""
    all_violations = []
    for rule_obj, violations in rule_violations:
        rule_data = rule_obj["rule_data"]
        error_config = rule_data.get("error", {})
        for v in violations:
            merged = dict(variables)
            merged.update(v)
            all_violations.append({
                "rule": rule_obj["id"],
                "severity": rule_obj["severity"],
                "line": v.get("line", 0),
                "source": v.get("source", ""),
                "message": inject_variables(error_config.get("message", ""), merged),
                "fix": inject_variables(error_config.get("fix", ""), merged),
            })

    blocking = sum(1 for rv in rule_violations for _ in rv[1] if rv[0]["severity"] == "block")
    warnings = sum(1 for rv in rule_violations for _ in rv[1] if rv[0]["severity"] == "warn")
    total = len([rv for rv in rule_violations])

    return {
        "status": "rejected" if blocking > 0 else "passed",
        "file": variables.get("filepath", ""),
        "violations": all_violations,
        "summary": {
            "blocking": blocking,
            "warnings": warnings,
            "total_rules": total,
        },
    }


# ---------------------------------------------------------------------------
# JSONL logging
# ---------------------------------------------------------------------------

def log_scan(log_dir, filepath, schema_name, schema_version, status, violations_data,
             passed_rules, total_rules, source, scan_ms, iteration=1):
    """Write a JSONL log entry."""
    if not log_dir:
        return
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "violations.jsonl")

    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": "scan",
        "file": filepath,
        "schema": schema_name,
        "schema_version": schema_version,
        "iteration": iteration,
        "status": status,
        "violations": violations_data,
        "passed_rules": passed_rules,
        "total_rules": total_rules,
        "code_length_lines": len(source.splitlines()),
        "code_hash": "sha256:" + hashlib.sha256(source.encode()).hexdigest()[:12],
        "scan_ms": scan_ms,
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Scope checking
# ---------------------------------------------------------------------------

def is_file_in_scope(filepath, schema_data, project_config):
    """Check if a file is within the gated scope."""
    scope = schema_data.get("scope", {})
    gated_paths = scope.get("gated_paths", [])
    exempt_paths = scope.get("exempt_paths", [])
    exempt_files = scope.get("exempt_files", [])

    filename = os.path.basename(filepath)

    # Check exempt files
    if filename in exempt_files:
        return False

    # Check exempt paths
    for ep in exempt_paths:
        if filepath.startswith(ep) or f"/{ep}" in filepath:
            return False

    # If gated_paths is empty, everything is gated
    if not gated_paths:
        return True

    # Check gated paths
    for gp in gated_paths:
        if filepath.startswith(gp) or f"/{gp}" in filepath:
            return True

    return False


# ---------------------------------------------------------------------------
# Main scan function
# ---------------------------------------------------------------------------

def scan_file(source, filepath, schema_path, output_format="stderr", skip_scope=False):
    """
    Main entry point: scan a Python source string against the schema.
    Returns (exit_code, output_string).
    """
    import time
    start = time.time()

    gate_home = find_gate_home()
    if not gate_home:
        return 0, ""  # No gate installation, pass through

    # Load project config
    project_config = load_project_config(schema_path)
    if not project_config:
        return 0, ""

    schema_name = project_config.get("schema", "production")

    # Check for per-path overrides
    overrides = project_config.get("overrides", {})
    for pattern, ovr in overrides.items():
        if ovr and ovr.get("schema") is None:
            # Exempt
            import fnmatch
            if fnmatch.fnmatch(filepath, pattern) or fnmatch.fnmatch(os.path.basename(filepath), pattern):
                return 0, ""
        elif ovr and ovr.get("schema"):
            import fnmatch
            if fnmatch.fnmatch(filepath, pattern) or filepath.startswith(pattern.rstrip("*")):
                schema_name = ovr["schema"]

    # Load schema
    schema_data = load_schema(schema_name, gate_home)
    if not schema_data:
        sys.stderr.write(f"Warning: Schema '{schema_name}' not found in {schemas_dir()}\n")
        return 0, ""

    # Check scope (skipped when invoked by python_gate for a specific file)
    if not skip_scope and not is_file_in_scope(filepath, schema_data, project_config):
        return 0, ""

    # Resolve rules
    rules = resolve_rules(schema_data, gate_home)
    rules = apply_project_overrides(rules, project_config)

    # Filter to enabled rules
    active_rules = [r for r in rules if r["enabled"] and r["severity"] != "off"]

    # Parse via LibCST (single parse, single metadata resolve)
    # NOTE: libcst.ParserSyntaxError does NOT inherit from SyntaxError.
    # We catch Exception here so that a parse failure never silently approves
    # a file.  A file that cannot be parsed is treated as a blocking error.
    try:
        from gatehouse.lib.analyzer import SourceAnalyzer
        analyzer = SourceAnalyzer(source, filepath)
    except Exception as exc:
        err_msg = f"  Parse error in {filepath}: {exc}\n"
        sys.stderr.write(err_msg)
        return 1, err_msg

    # Run all checks
    all_violations = []
    passed_rules = []
    violations_data = []

    variables = build_variables(analyzer)

    for rule_obj in active_rules:
        try:
            violations = run_check(rule_obj, analyzer)
        except Exception as exc:
            # A broken rule must not silently approve the file.
            # Treat the rule as having a violation so the file is blocked.
            sys.stderr.write(f"  Rule '{rule_obj['id']}' raised {type(exc).__name__}: {exc}\n")
            violations = [{"line": 1, "source": f"internal error in rule {rule_obj['id']}"}]
        if violations:
            all_violations.append((rule_obj, violations))
            for v in violations:
                merged = dict(variables)
                merged.update(v)
                violations_data.append({
                    "rule": rule_obj["id"],
                    "severity": rule_obj["severity"],
                    "line": v.get("line", 0),
                })
        else:
            passed_rules.append(rule_obj["id"])

    scan_ms = int((time.time() - start) * 1000)

    # Determine status
    blocking_count = sum(
        len(vs) for rule_obj, vs in all_violations if rule_obj["severity"] == "block"
    )
    warning_count = sum(
        len(vs) for rule_obj, vs in all_violations if rule_obj["severity"] == "warn"
    )

    status = "rejected" if blocking_count > 0 else "saved"

    # Log
    log_dir = project_config.get("logging", {}).get("directory", "")
    if project_config.get("logging", {}).get("enabled", False) and log_dir:
        schema_version = schema_data.get("schema", {}).get("version", "0.0.0")
        log_scan(
            log_dir, filepath, schema_name, schema_version, status,
            violations_data, passed_rules, len(active_rules), source, scan_ms,
        )

    # Format output
    if output_format == "json":
        schema_version = schema_data.get("schema", {}).get("version", "0.0.0")
        result = format_violations_json(all_violations, variables, schema_name, schema_version)
        return (1 if blocking_count > 0 else 0), json.dumps(result, indent=2)

    else:  # stderr
        if not all_violations:
            return 0, ""

        output_parts = []
        for rule_obj, violations in all_violations:
            for v in violations:
                merged = dict(variables)
                merged.update(v)
                output_parts.append(format_violation_stderr(rule_obj, v, merged))

        schema_version = schema_data.get("schema", {}).get("version", "0.0.0")
        bar = f"{_c('summary_bar')}{'━' * 62}{_c('reset')}"
        output_parts.append(f"\n{bar}")
        output_parts.append(f"  {_c('bold')}Schema:{_c('reset')} {_c('info')}{schema_name}{_c('reset')} {_c('dim')}(v{schema_version}){_c('reset')}")
        output_parts.append(f"  {_c('bold')}Violations:{_c('reset')} {_c('error')}{blocking_count} blocking{_c('reset')}, {_c('warning')}{warning_count} warnings{_c('reset')}")
        if blocking_count > 0:
            output_parts.append(f"  {_c('blocked')}{_c('bold')}Execution: BLOCKED{_c('reset')}")
        else:
            output_parts.append(f"  {_c('allowed')}Execution: ALLOWED (warnings only){_c('reset')}")
        output_parts.append(bar)

        return (1 if blocking_count > 0 else 0), "\n\n".join(output_parts) + "\n"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Gate Engine — Schema enforcement for Python files")
    parser.add_argument("--file", help="Path to the Python file to check")
    parser.add_argument("--stdin", action="store_true", help="Read code from stdin")
    parser.add_argument("--filename", help="Filename to use when reading from stdin")
    parser.add_argument("--schema", required=True, help="Path to .gate_schema.yaml")
    parser.add_argument("--format", choices=["stderr", "json"], default="stderr", help="Output format")
    parser.add_argument("--no-scope", action="store_true", help="Skip scope checking (used by python_gate)")
    parser.add_argument("--version", action="version", version=f"gate_engine {VERSION}")

    args = parser.parse_args()

    if args.stdin:
        source = sys.stdin.read()
        filepath = args.filename or "stdin.py"
    elif args.file:
        filepath = args.file
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    else:
        parser.error("Either --file or --stdin is required")
        return

    exit_code, output = scan_file(source, filepath, args.schema, args.format, args.no_scope)

    if output:
        sys.stderr.write(output)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
