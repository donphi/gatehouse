#!/usr/bin/env python3
"""
gate_engine.py — Fixed runtime for error-driven code schema enforcement.

This engine NEVER changes when rules change. All behavior comes from:
  - Rule YAML files in rules/   (auto-discovered next to this file)
  - Schema manifests in schemas/ (auto-discovered next to this file)
  - Project config in .gate_schema.yaml

Resource discovery: the engine locates rules/ and schemas/ relative to its
own file path. Set $GATE_HOME to override (e.g. for a custom rule directory).

Usage:
  python3 gate_engine.py --file src/train.py --schema .gate_schema.yaml
  echo "code" | python3 gate_engine.py --stdin --schema .gate_schema.yaml --filename src/train.py
"""

import ast
import io
import json
import os
import re
import sys
import hashlib
import tokenize
import datetime
from pathlib import Path

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
# Constants
# ---------------------------------------------------------------------------

_PACKAGE_DIR = str(Path(__file__).resolve().parent)
GATE_HOME = os.environ.get("GATE_HOME", _PACKAGE_DIR)


def _read_version():
    """Read version from pyproject.toml so it is defined in exactly one place."""
    toml_path = Path(__file__).resolve().parent / "pyproject.toml"
    if toml_path.is_file():
        with open(toml_path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


VERSION = _read_version()


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------

def find_gate_home():
    """Resolve gate home directory (auto-discovered or $GATE_HOME override)."""
    if os.path.isdir(GATE_HOME):
        return GATE_HOME
    return None


def load_rule(rule_id, gate_home):
    """Load a single rule YAML file by ID."""
    rule_path = os.path.join(gate_home, "rules", f"{rule_id}.yaml")
    if not os.path.isfile(rule_path):
        return None
    return load_yaml(rule_path)


def load_schema(schema_name, gate_home):
    """Load a schema manifest by name."""
    schema_path = os.path.join(gate_home, "schemas", f"{schema_name}.yaml")
    if not os.path.isfile(schema_path):
        return None
    return load_yaml(schema_path)


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
                sys.stderr.write(f"Warning: Rule '{rule_id}' not found in {gate_home}/rules/\n")
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
            sys.stderr.write(f"Warning: Rule '{rule_id}' not found in {gate_home}/rules/\n")
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
# Check type implementations
# ---------------------------------------------------------------------------

def check_pattern_exists(source, source_lines, filepath, check_config, params):
    """Check for a text pattern at a location."""
    pattern = check_config.get("pattern", check_config.get("value", ""))
    value = check_config.get("value", pattern)
    location = check_config.get("location", "anywhere")
    required_substrings = check_config.get("required_substrings", [])

    violations = []

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
        found = False
        for i, line in enumerate(source_lines):
            if value and value in line:
                found = True
                break
        # Also try regex
        if not found and value:
            try:
                if re.search(value, source):
                    found = True
            except re.error:
                pass
        if not found:
            violations.append({"line": 1, "source": source_lines[0].rstrip() if source_lines else ""})
    elif location == "end_of_file":
        if source_lines and value not in source_lines[-1]:
            violations.append({"line": len(source_lines), "source": source_lines[-1].rstrip()})

    # Special pattern checks
    if check_config.get("pattern") == "if_name_main":
        # Only match actual code lines, not comments that mention the pattern
        code_lines = (line for line in source_lines if not line.strip().startswith("#"))
        found = any("if __name__" in line and "__main__" in line for line in code_lines)
        if not found:
            violations = [{"line": len(source_lines), "source": ""}]
        else:
            violations = []

    if check_config.get("pattern") == "print_call_with_checkmark":
        found = any("print(" in line for line in source_lines)
        if not found:
            violations = [{"line": len(source_lines), "source": ""}]
        else:
            violations = []

    # Check required_substrings in the header block
    if not violations and required_substrings:
        # Check first comment block
        header_text = ""
        for line in source_lines:
            if line.strip().startswith("#") or not line.strip():
                header_text += line
            else:
                break
        for sub in required_substrings:
            # Replace template variables for checking
            clean_sub = sub.split("{")[0] if "{" in sub else sub
            if clean_sub and clean_sub not in header_text:
                violations.append({"line": 1, "source": source_lines[0].rstrip() if source_lines else ""})
                break

    return violations


def check_ast_node_exists(source, ast_tree, check_config):
    """Check for existence of an AST node type."""
    node_type = check_config.get("node", "")
    required_substrings = check_config.get("required_substrings", [])
    violations = []

    if node_type == "module_docstring":
        docstring = ast.get_docstring(ast_tree)
        if not docstring:
            violations.append({"line": 1, "source": ""})
        elif required_substrings:
            for sub in required_substrings:
                if sub not in docstring:
                    violations.append({"line": 1, "source": f'Missing "{sub}" in module docstring'})
                    break

    elif node_type == "import_statement":
        has_import = any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            for node in ast.walk(ast_tree)
        )
        if not has_import:
            violations.append({"line": 1, "source": ""})

    elif node_type == "class_definition":
        has_class = any(isinstance(node, ast.ClassDef) for node in ast.walk(ast_tree))
        if not has_class:
            violations.append({"line": 1, "source": ""})

    elif node_type == "function_definition":
        has_func = any(isinstance(node, ast.FunctionDef) for node in ast.walk(ast_tree))
        if not has_func:
            violations.append({"line": 1, "source": ""})

    return violations


def check_ast_check(source, ast_tree, source_lines, check_config):
    """Run parameterized AST checks."""
    check_name = check_config.get("check", "")
    violations = []

    if check_name == "all_functions_have_docstrings":
        for node in ast.walk(ast_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not ast.get_docstring(node):
                    args_str = ", ".join(a.arg for a in node.args.args)
                    violations.append({
                        "line": node.lineno,
                        "source": source_lines[node.lineno - 1].rstrip() if node.lineno <= len(source_lines) else "",
                        "function_name": node.name,
                        "params": args_str,
                    })

    elif check_name == "for_loops_without_progress":
        for node in ast.walk(ast_tree):
            if isinstance(node, ast.For):
                # Check if the iterable is wrapped in track() or tqdm()
                iter_src = ast.dump(node.iter)
                if "track" not in iter_src and "tqdm" not in iter_src:
                    violations.append({
                        "line": node.lineno,
                        "source": source_lines[node.lineno - 1].rstrip() if node.lineno <= len(source_lines) else "",
                    })

    elif check_name == "decorated_functions_have_docstrings":
        patterns = check_config.get("decorator_pattern", [])
        for node in ast.walk(ast_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    dec_name = _get_decorator_name(dec)
                    if any(p in dec_name for p in patterns):
                        if not ast.get_docstring(node):
                            violations.append({
                                "line": node.lineno,
                                "function_name": node.name,
                            })

    elif check_name == "decorated_functions_have_try_except":
        patterns = check_config.get("decorator_pattern", [])
        for node in ast.walk(ast_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    dec_name = _get_decorator_name(dec)
                    if any(p in dec_name for p in patterns):
                        has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
                        if not has_try:
                            violations.append({
                                "line": node.lineno,
                                "function_name": node.name,
                            })

    elif check_name == "functions_with_param_pattern_have_log_call":
        param_patterns = check_config.get("param_pattern", [])
        for node in ast.walk(ast_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                param_names = [a.arg for a in node.args.args]
                has_matching_param = any(
                    any(p in pname for p in param_patterns)
                    for pname in param_names
                )
                if has_matching_param:
                    # Check for logging call in function body
                    func_source = ast.dump(node)
                    has_log = "log" in func_source.lower() or "audit" in func_source.lower()
                    if not has_log:
                        violations.append({
                            "line": node.lineno,
                            "function_name": node.name,
                        })

    return violations


def _get_decorator_name(dec):
    """Extract decorator name as string."""
    if isinstance(dec, ast.Name):
        return dec.id
    elif isinstance(dec, ast.Attribute):
        parts = []
        node = dec
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))
    elif isinstance(dec, ast.Call):
        return _get_decorator_name(dec.func)
    return ""


def check_token_scan(source, source_lines, check_config):
    """Scan tokens for patterns."""
    scan_type = check_config.get("scan", "")
    violations = []

    if scan_type == "hardcoded_literals":
        safe_values = check_config.get("safe_values", [0, 1, -1, "", "None", "True", "False", "__main__"])
        safe_values_str = [str(v) for v in safe_values]
        safe_contexts = check_config.get("safe_contexts", [])

        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        except tokenize.TokenError:
            return violations

        for i, tok in enumerate(tokens):
            if tok.type == tokenize.NUMBER:
                if tok.string in safe_values_str:
                    continue
                # Check if it's an UPPER_SNAKE_CASE assignment
                if "UPPER_SNAKE_CASE_assignment" in safe_contexts:
                    if i >= 2 and tokens[i - 1].string == "=" and tokens[i - 2].type == tokenize.NAME:
                        name = tokens[i - 2].string
                        if name == name.upper() and "_" in name:
                            continue
                violations.append({
                    "line": tok.start[0],
                    "source": source_lines[tok.start[0] - 1].rstrip() if tok.start[0] <= len(source_lines) else "",
                    "value": tok.string,
                    "value_type": "numeric",
                })

            elif tok.type == tokenize.STRING:
                val = tok.string.strip("'\"")
                if val in safe_values_str or tok.string in safe_values_str:
                    continue
                # Skip f-strings — these are display/log text, not config values
                if "fstring" in safe_contexts:
                    raw = tok.string.lstrip("bBrRuU")
                    if raw and raw[0] in ("f", "F"):
                        continue
                # Skip docstrings (strings that are the first expression in a function/class/module)
                if i > 0 and tokens[i - 1].type in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT):
                    continue
                # Skip dict keys — string immediately followed by ':'
                if "dict_key" in safe_contexts:
                    if i + 1 < len(tokens) and tokens[i + 1].string == ":":
                        continue
                # Skip UPPER_SNAKE_CASE assignments
                if "UPPER_SNAKE_CASE_assignment" in safe_contexts:
                    if i >= 2 and tokens[i - 1].string == "=" and tokens[i - 2].type == tokenize.NAME:
                        name = tokens[i - 2].string
                        if name == name.upper() and "_" in name:
                            continue
                # Skip keyword arguments
                if "keyword_argument_name" in safe_contexts:
                    if i >= 2 and tokens[i - 1].string == "=":
                        continue

                violations.append({
                    "line": tok.start[0],
                    "source": source_lines[tok.start[0] - 1].rstrip() if tok.start[0] <= len(source_lines) else "",
                    "value": val,
                    "value_type": "string",
                })

    elif scan_type == "log_calls_containing":
        forbidden = check_config.get("forbidden_strings", [])
        for i, line in enumerate(source_lines):
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


def check_uppercase_assignments(source, ast_tree, check_config):
    """Check for UPPER_SNAKE_CASE module-level assignments."""
    min_count = check_config.get("min_count", 1)
    violations = []

    count = 0
    for node in ast.iter_child_nodes(ast_tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    if name == name.upper() and "_" in name and not name.startswith("_"):
                        count += 1

    if count < min_count:
        violations.append({
            "line": 1,
            "source": "",
        })

    return violations


def check_docstring_contains(source, ast_tree, check_config):
    """Check that the module docstring contains specific text."""
    value = check_config.get("value", "")
    violations = []

    docstring = ast.get_docstring(ast_tree)
    if not docstring or value not in docstring:
        violations.append({
            "line": 1,
            "source": "",
        })

    return violations


def check_file_metric(source, source_lines, check_config, params):
    """Check file metrics (line count, etc.)."""
    metric = check_config.get("metric", "line_count")
    violations = []

    max_val = params.get("max_lines", check_config.get("max_lines", 1000))

    if metric == "line_count":
        if len(source_lines) > max_val:
            violations.append({
                "line": len(source_lines),
                "source": "",
                "line_count": len(source_lines),
            })

    return violations


def check_custom(source, ast_tree, source_lines, filepath, check_config):
    """Run a custom check (inline expression or plugin)."""
    violations = []

    if "expression" in check_config:
        expr = check_config["expression"]
        try:
            result = eval(expr, {
                "ast": ast,
                "ast_tree": ast_tree,
                "source_lines": source_lines,
                "source": source,
                "filepath": filepath,
                "tokenize": tokenize,
                "re": re,
                "io": io,
            })
            if result:
                violations.append({"line": 1, "source": ""})
        except Exception as e:
            sys.stderr.write(f"Custom check expression error: {e}\n")

    elif "plugin" in check_config:
        plugin_path = check_config["plugin"]
        if not os.path.isabs(plugin_path):
            plugin_path = os.path.join(GATE_HOME, plugin_path)
        func_name = check_config.get("function", "check")
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("plugin", plugin_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            func = getattr(mod, func_name)
            result = func(source, ast_tree, filepath)
            if isinstance(result, list):
                violations.extend(result)
        except Exception as e:
            sys.stderr.write(f"Custom check plugin error: {e}\n")

    return violations


# ---------------------------------------------------------------------------
# Main check dispatcher
# ---------------------------------------------------------------------------

def run_check(rule_obj, source, ast_tree, source_lines, filepath):
    """
    Run a single rule's check against the source code.
    Returns a list of violation dicts.
    """
    rule_data = rule_obj["rule_data"]
    check_config = rule_data.get("check", {})
    params = rule_obj.get("params", {})
    check_type = check_config.get("type", "")

    if check_type == "pattern_exists":
        return check_pattern_exists(source, source_lines, filepath, check_config, params)
    elif check_type == "ast_node_exists":
        return check_ast_node_exists(source, ast_tree, check_config)
    elif check_type == "ast_check":
        return check_ast_check(source, ast_tree, source_lines, check_config)
    elif check_type == "token_scan":
        return check_token_scan(source, source_lines, check_config)
    elif check_type == "uppercase_assignments_exist":
        return check_uppercase_assignments(source, ast_tree, check_config)
    elif check_type == "docstring_contains":
        return check_docstring_contains(source, ast_tree, check_config)
    elif check_type == "file_metric":
        return check_file_metric(source, source_lines, check_config, params)
    elif check_type == "custom":
        return check_custom(source, ast_tree, source_lines, filepath, check_config)
    else:
        sys.stderr.write(f"Warning: Unknown check type '{check_type}' in rule '{rule_obj['id']}'\n")
        return []


# ---------------------------------------------------------------------------
# Variable injection
# ---------------------------------------------------------------------------

def build_variables(filepath, source_lines, ast_tree, extra=None):
    """Build the variable dict for error template injection."""
    filename = os.path.basename(filepath)
    directory = os.path.dirname(filepath)
    module_name = os.path.splitext(filename)[0]

    variables = {
        "filename": filename,
        "filepath": filepath,
        "directory": directory,
        "module_name": module_name,
        "line_count": len(source_lines),
    }

    # Extract function/class names
    func_names = []
    class_names = []
    for node in ast.walk(ast_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            class_names.append(node.name)

    variables["function_names"] = ", ".join(func_names)
    variables["class_names"] = ", ".join(class_names)

    if extra:
        variables.update(extra)

    return variables


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
    parts.append(f'  File "{filepath}", line {line}')
    if source:
        parts.append(f"    {source}")
        # Caret pointer
        if violation.get("value"):
            val_str = str(violation["value"])
            col = source.find(val_str)
            if col >= 0:
                parts.append(f"    {' ' * col}{'^' * len(val_str)}")
    parts.append(f"  {message}")
    if fix:
        for fix_line in fix.strip().splitlines():
            parts.append(f"  Fix: {fix_line}" if fix_line == fix.strip().splitlines()[0] else f"       {fix_line}")

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

def scan_file(source, filepath, schema_path, output_format="stderr"):
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
        sys.stderr.write(f"Warning: Schema '{schema_name}' not found in {gate_home}/schemas/\n")
        return 0, ""

    # Check scope
    if not is_file_in_scope(filepath, schema_data, project_config):
        return 0, ""

    # Resolve rules
    rules = resolve_rules(schema_data, gate_home)
    rules = apply_project_overrides(rules, project_config)

    # Filter to enabled rules
    active_rules = [r for r in rules if r["enabled"] and r["severity"] != "off"]

    # Parse AST
    try:
        ast_tree = ast.parse(source)
    except SyntaxError as e:
        # If the code has syntax errors, let Python handle it
        return 0, ""

    source_lines = source.splitlines()

    # Run all checks
    all_violations = []
    passed_rules = []
    violations_data = []

    variables = build_variables(filepath, source_lines, ast_tree)

    for rule_obj in active_rules:
        violations = run_check(rule_obj, source, ast_tree, source_lines, filepath)
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
        output_parts.append(f"\n  Schema: {schema_name} (v{schema_version})")
        output_parts.append(f"  Violations: {blocking_count} blocking, {warning_count} warnings")
        if blocking_count > 0:
            output_parts.append("  Execution: BLOCKED")
        else:
            output_parts.append("  Execution: ALLOWED (warnings only)")

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

    exit_code, output = scan_file(source, filepath, args.schema, args.format)

    if output:
        sys.stderr.write(output)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
