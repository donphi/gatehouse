#!/usr/bin/env python3
"""
gatehouse_cli.py — Config-driven interactive Rule Builder CLI.

This CLI is a generic prompt runner. It does NOT have a hardcoded list of
check types. Instead, it reads its menu, prompts, and options from:
  - cli/check_types.yaml   (drives the new-rule wizard)
  - cli/branding.yaml      (ASCII art, colors, version)
  - cli/templates/rule_template.yaml  (output template)

Adding a new check type to the engine means adding one YAML entry to
check_types.yaml. Zero code changes to this file.

Usage:
  gatehouse new-rule
  gatehouse init --schema production
  gatehouse list-rules
  gatehouse list-rules --schema production
  gatehouse test-rule <rule-id> <file>
  gatehouse disable-rule <rule-id> --schema <schema>
  gatehouse status
  gatehouse activate [--mode hard|soft]
  gatehouse deactivate
"""

import argparse
import os
import sys
import textwrap

# ---------------------------------------------------------------------------
# YAML loading (same fallback as gate_engine.py)
# ---------------------------------------------------------------------------

try:
    import yaml

    def load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
except ImportError:
    def load_yaml(path):
        """Minimal YAML loader for the CLI config files."""
        # For full functionality, install PyYAML: pip install pyyaml
        print("Warning: PyYAML not installed. Install with: pip install pyyaml")
        print("The CLI requires PyYAML to read its configuration files.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# ANSI color helpers — loaded from cli/theme.yaml
# ---------------------------------------------------------------------------

def _load_cli_colors():
    """Load ANSI codes from theme.yaml. Returns name→code dict."""
    cli_dir = os.path.dirname(os.path.abspath(__file__))
    theme_path = os.path.join(cli_dir, "theme.yaml")
    if not os.path.isfile(theme_path):
        return {"reset": ""}
    raw = load_yaml(theme_path)
    if not raw:
        return {"reset": ""}
    ansi = raw.get("ansi", {})
    roles = raw.get("roles", {})
    merged = dict(ansi)
    for role, color_name in roles.items():
        merged[role] = ansi.get(color_name, "")
    return merged


COLORS = _load_cli_colors()


def color(text, color_name):
    """Wrap text in ANSI color codes."""
    if not sys.stdout.isatty():
        return text
    code = COLORS.get(color_name, "")
    return f"{code}{text}{COLORS.get('reset', '')}" if code else text


# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

def get_gate_home():
    """Get $GATE_HOME, defaulting to the parent of this script's directory."""
    env_home = os.environ.get("GATE_HOME")
    if env_home and os.path.isdir(env_home):
        return env_home
    # Fall back to parent of cli/ directory
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_cli_dir():
    """Get the cli/ directory path."""
    return os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------

def print_banner(branding, color_config):
    """Print the ANSI art banner."""
    title = branding.get("title", "GATEHOUSE")
    subtitle = branding.get("subtitle", "")
    version = branding.get("version", "")
    tagline = branding.get("tagline", "")

    title_color = color_config.get("title", "cyan")
    border_color = color_config.get("border", "white")

    # Calculate box width from the longest title line
    title_lines = [l for l in title.strip().splitlines() if l.strip()]
    max_width = max(len(l) for l in title_lines) if title_lines else 60
    box_width = max(max_width + 4, 60)

    print()
    print(color(f"  ╔{'═' * box_width}╗", border_color))
    print(color(f"  ║{' ' * box_width}║", border_color))

    for line in title_lines:
        padded = line.ljust(box_width)
        print(color(f"  ║", border_color) + color(padded, title_color) + color("║", border_color))

    print(color(f"  ║{' ' * box_width}║", border_color))

    if subtitle or version:
        info = f"  {subtitle} v{version}" if version else f"  {subtitle}"
        padded = info.ljust(box_width)
        print(color(f"  ║", border_color) + color(padded, "white") + color("║", border_color))

    if tagline:
        padded = f"  {tagline}".ljust(box_width)
        print(color(f"  ║", border_color) + color(padded, "dim") + color("║", border_color))

    print(color(f"  ║{' ' * box_width}║", border_color))
    print(color(f"  ╚{'═' * box_width}╝", border_color))
    print()


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def prompt_text(question, hint=None, default=None):
    """Prompt for free text input."""
    prompt_str = f"  {question}"
    if hint:
        prompt_str += color(f" ({hint})", "dim")
    if default:
        prompt_str += color(f" [{default}]", "dim")
    prompt_str += ": "

    answer = input(prompt_str).strip()
    return answer if answer else default


def prompt_choice(question, options):
    """Prompt for a single choice from a list."""
    print(f"\n  {question}")
    for i, opt in enumerate(options, 1):
        label = opt.get("label", opt.get("value", ""))
        print(f"    {color(str(i), 'green')}. {label}")
    print()

    while True:
        answer = input(f"  Select [1-{len(options)}]: ").strip()
        try:
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                return options[idx]["value"]
        except (ValueError, IndexError):
            pass
        print(color(f"  Please enter a number between 1 and {len(options)}", "red"))


def prompt_text_list(question, hint=None):
    """Prompt for a comma-separated list."""
    raw = prompt_text(question, hint=hint)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def prompt_number(question, default=None):
    """Prompt for a number."""
    while True:
        raw = prompt_text(question, default=str(default) if default else None)
        if not raw and default is not None:
            return default
        try:
            return int(raw)
        except (ValueError, TypeError):
            print(color("  Please enter a number", "red"))


def prompt_severity():
    """Prompt for block/warn severity."""
    print("\n  Should this BLOCK execution or just WARN?")
    print(f"    {color('block', 'green')} — Code cannot run until this is fixed")
    print(f"    {color('warn', 'green')}  — Show a warning but allow execution")
    print()
    while True:
        answer = input("  Select [block/warn]: ").strip().lower()
        if answer in ("block", "warn"):
            return answer
        print(color("  Please enter 'block' or 'warn'", "red"))


# ---------------------------------------------------------------------------
# show_if evaluation
# ---------------------------------------------------------------------------

def evaluate_show_if(show_if_expr, collected_values):
    """Evaluate a show_if condition against collected prompt values."""
    if not show_if_expr:
        return True
    try:
        return eval(show_if_expr, {"__builtins__": {}}, collected_values)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# new-rule command
# ---------------------------------------------------------------------------

def cmd_new_rule(args):
    """Interactive rule creation wizard."""
    gate_home = get_gate_home()
    cli_dir = get_cli_dir()

    # Load config files
    branding = load_yaml(os.path.join(cli_dir, "branding.yaml"))
    check_types_config = load_yaml(os.path.join(cli_dir, "check_types.yaml"))
    template_config = load_yaml(os.path.join(cli_dir, "templates", "rule_template.yaml"))

    color_config = branding.get("colors", {})
    check_types = check_types_config.get("check_types", [])

    # Print banner
    print_banner(branding, color_config)

    # Basic info
    rule_id = prompt_text("Rule ID (used as filename, e.g. 'no-todo-comments')")
    if not rule_id:
        print(color("  Rule ID is required.", "red"))
        return

    rule_name = prompt_text("Rule Name (human-readable)")
    description = prompt_text("Description")

    # Check type selection
    print()
    print(color("  ┌─────────────────────────────────────────────────────────────┐", "white"))
    print(color("  │  What kind of check do you want?                            │", "white"))
    print(color("  │                                                             │", "white"))

    for i, ct in enumerate(check_types, 1):
        label = ct.get("label", ct["id"])
        line = f"  │    {i}. {ct['id']:<25s}— {label}"
        line = line.ljust(62) + "│"
        print(color(line, "white"))

    print(color("  │                                                             │", "white"))
    print(color("  └─────────────────────────────────────────────────────────────┘", "white"))
    print()

    while True:
        answer = input(f"  Select [1-{len(check_types)}]: ").strip()
        try:
            idx = int(answer) - 1
            if 0 <= idx < len(check_types):
                selected_type = check_types[idx]
                break
        except (ValueError, IndexError):
            pass
        print(color(f"  Please enter a number between 1 and {len(check_types)}", "red"))

    check_type_id = selected_type["id"]

    # Run prompts for the selected check type
    collected = {}
    check_params_yaml = ""

    if selected_type.get("prompts"):
        print()
        print(color(f"  ┌─────────────────────────────────────────────────────────────┐", "white"))
        print(color(f"  │  {check_type_id} — Configure".ljust(62) + "│", "white"))
        print(color(f"  │                                                             │", "white"))
        print(color(f"  └─────────────────────────────────────────────────────────────┘", "white"))

        for prompt_def in selected_type["prompts"]:
            # Check show_if condition
            show_if = prompt_def.get("show_if", "")
            if show_if and not evaluate_show_if(show_if, collected):
                continue

            field = prompt_def["field"]
            ask = prompt_def["ask"]
            ptype = prompt_def["type"]
            hint = prompt_def.get("hint")
            default = prompt_def.get("default")
            optional = prompt_def.get("optional", False)

            if ptype == "text":
                val = prompt_text(ask, hint=hint, default=str(default) if default else None)
                if val or not optional:
                    collected[field] = val
            elif ptype == "choice":
                options = prompt_def.get("options", [])
                val = prompt_choice(ask, options)
                collected[field] = val
            elif ptype == "text_list":
                val = prompt_text_list(ask, hint=hint)
                if val:
                    collected[field] = val
            elif ptype == "number":
                val = prompt_number(ask, default=default)
                collected[field] = val

    # Build check params YAML
    params_lines = []
    for key, val in collected.items():
        if key == "mode":
            continue  # Internal to the CLI, not a check param
        if isinstance(val, list):
            params_lines.append(f"  {key}:")
            for item in val:
                params_lines.append(f'    - "{item}"')
        elif isinstance(val, int):
            params_lines.append(f"  {key}: {val}")
        else:
            params_lines.append(f'  {key}: "{val}"')

    check_params_yaml = "\n".join(params_lines)

    # Severity
    severity = prompt_severity()

    # Error message and fix
    print()
    error_message = prompt_text("Error message (what the LLM sees when it fails)")
    fix_instruction = prompt_text("Fix instruction (what the LLM should do to fix it)")

    # Generate the rule file
    rules_dir = os.path.join(gate_home, "rules")
    os.makedirs(rules_dir, exist_ok=True)
    rule_path = os.path.join(rules_dir, f"{rule_id}.yaml")

    rule_content = f"""# rules/{rule_id}.yaml
# Auto-generated by: gatehouse new-rule

name: "{rule_name}"
description: "{description}"
version: "1.0.0"

check:
  type: "{check_type_id}"
{check_params_yaml}

error:
  message: "{error_message}"
  fix: "{fix_instruction}"

defaults:
  severity: "{severity}"
  enabled: true
"""

    with open(rule_path, "w", encoding="utf-8") as f:
        f.write(rule_content)

    # Success message
    print()
    print(color("  ┌─────────────────────────────────────────────────────────────┐", "green"))
    print(color(f"  │  ✓ Created: rules/{rule_id}.yaml".ljust(62) + "│", "green"))
    print(color("  │                                                             │", "green"))
    print(color("  │  To activate, add to your schema:                           │", "green"))
    print(color(f'  │    - id: "{rule_id}"'.ljust(62) + "│", "green"))
    print(color("  │                                                             │", "green"))
    test_cmd = f"gatehouse test-rule {rule_id} <file.py>"
    print(color(f"  │  To test: {test_cmd}".ljust(62) + "│", "green"))
    print(color("  └─────────────────────────────────────────────────────────────┘", "green"))
    print()


# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------

def cmd_init(args):
    """Initialize a project with a .gate_schema.yaml."""
    schema_name = args.schema or "production"
    gate_home = get_gate_home()

    # Verify schema exists
    schema_path = os.path.join(gate_home, "schemas", f"{schema_name}.yaml")
    if not os.path.isfile(schema_path):
        print(color(f"Error: Schema '{schema_name}' not found at {schema_path}", "red"))
        print(f"Available schemas:")
        schemas_dir = os.path.join(gate_home, "schemas")
        if os.path.isdir(schemas_dir):
            for f in sorted(os.listdir(schemas_dir)):
                if f.endswith(".yaml"):
                    print(f"  - {f[:-5]}")
        sys.exit(1)

    config_path = os.path.join(os.getcwd(), ".gate_schema.yaml")
    if os.path.exists(config_path):
        answer = input(f".gate_schema.yaml already exists. Overwrite? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    content = f"""# .gate_schema.yaml — auto-generated by 'gatehouse init --schema {schema_name}'

schema: "{schema_name}"

rule_overrides: {{}}

logging:
  enabled: true
  directory: "./logs/gate"
"""

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(color(f"✓ Created .gate_schema.yaml (schema: {schema_name})", "green"))
    print(f"  The gate is now active for this project.")
    print(f"  Rules are loaded from: {gate_home}")


# ---------------------------------------------------------------------------
# list-rules command
# ---------------------------------------------------------------------------

def cmd_list_rules(args):
    """List available rules."""
    gate_home = get_gate_home()
    rules_dir = os.path.join(gate_home, "rules")

    if args.schema:
        # Show rules in a specific schema
        schema_file = os.path.join(gate_home, "schemas", f"{args.schema}.yaml")
        if not os.path.isfile(schema_file):
            print(color(f"Schema '{args.schema}' not found at {schema_file}", "red"))
            sys.exit(1)
        schema_data = load_yaml(schema_file)
        if not schema_data:
            print(color(f"Schema '{args.schema}' is empty.", "red"))
            sys.exit(1)

        print(f"\nRules in schema '{args.schema}':")
        print(f"{'─' * 60}")

        rules_list = schema_data.get("rules", [])
        for entry in rules_list:
            if isinstance(entry, str):
                entry = {"id": entry}
            rule_id = entry.get("id", "")
            severity = entry.get("severity", "")
            enabled = entry.get("enabled", True)

            # Load rule for description
            rule_path = os.path.join(rules_dir, f"{rule_id}.yaml")
            desc = ""
            if os.path.isfile(rule_path):
                rule_data = load_yaml(rule_path)
                desc = rule_data.get("description", "")
                if not severity:
                    severity = rule_data.get("defaults", {}).get("severity", "warn")

            status = color("OFF", "dim") if not enabled else (
                color("BLOCK", "red") if severity == "block" else color("WARN", "cyan")
            )
            print(f"  {status:>20s}  {rule_id:<30s}  {desc}")

    else:
        # Show all available rules
        if not os.path.isdir(rules_dir):
            print("No rules directory found.")
            return

        print(f"\nAvailable rules ({rules_dir}):")
        print(f"{'─' * 60}")

        for filename in sorted(os.listdir(rules_dir)):
            if not filename.endswith(".yaml"):
                continue
            rule_id = filename[:-5]
            rule_data = load_yaml(os.path.join(rules_dir, filename))
            name = rule_data.get("name", rule_id)
            desc = rule_data.get("description", "")
            severity = rule_data.get("defaults", {}).get("severity", "warn")
            status = color("BLOCK", "red") if severity == "block" else color("WARN", "cyan")
            print(f"  {status:>20s}  {rule_id:<30s}  {desc}")

    print()


# ---------------------------------------------------------------------------
# test-rule command
# ---------------------------------------------------------------------------

def cmd_test_rule(args):
    """Test a single rule against a file."""
    gate_home = get_gate_home()
    rule_id = args.rule_id
    filepath = args.file

    if not os.path.isfile(filepath):
        print(color(f"File not found: {filepath}", "red"))
        sys.exit(1)

    rule_path = os.path.join(gate_home, "rules", f"{rule_id}.yaml")
    if not os.path.isfile(rule_path):
        print(color(f"Rule not found: {rule_id}", "red"))
        sys.exit(1)

    # Use gate_engine to test
    import subprocess
    engine_path = os.path.join(gate_home, "gate_engine.py")

    # Create a temporary minimal schema that includes just this rule
    import tempfile
    temp_schema = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_config = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)

    try:
        temp_schema.write(f"""schema:
  name: "test-single-rule"
  version: "0.0.0"
scope:
  gated_paths: [""]
rules:
  - id: "{rule_id}"
""")
        temp_schema.close()

        temp_config.write(f"""schema: "test-single-rule"
logging:
  enabled: false
""")
        temp_config.close()

        # We need to temporarily copy the schema to the schemas dir
        test_schema_path = os.path.join(gate_home, "schemas", "test-single-rule.yaml")
        import shutil
        shutil.copy(temp_schema.name, test_schema_path)

        result = subprocess.run(
            [sys.executable, engine_path, "--file", filepath, "--schema", temp_config.name],
            capture_output=True, text=True,
            env={**os.environ, "GATE_HOME": gate_home}
        )

        if result.returncode == 0:
            print(color(f"✓ {filepath} passes rule '{rule_id}'", "green"))
        else:
            print(color(f"✗ {filepath} violates rule '{rule_id}':", "red"))
            print(result.stderr)
            sys.exit(result.returncode)

    finally:
        os.unlink(temp_schema.name)
        os.unlink(temp_config.name)
        if os.path.exists(test_schema_path):
            os.unlink(test_schema_path)


# ---------------------------------------------------------------------------
# disable-rule command
# ---------------------------------------------------------------------------

def cmd_disable_rule(args):
    """Disable a rule in a schema."""
    gate_home = get_gate_home()
    schema_name = args.schema
    rule_id = args.rule_id

    schema_path = os.path.join(gate_home, "schemas", f"{schema_name}.yaml")
    if not os.path.isfile(schema_path):
        print(color(f"Schema '{schema_name}' not found.", "red"))
        sys.exit(1)

    schema_data = load_yaml(schema_path)
    rules = schema_data.get("rules", [])

    found = False
    for entry in rules:
        if isinstance(entry, dict) and entry.get("id") == rule_id:
            entry["enabled"] = False
            found = True
            break
        elif isinstance(entry, str) and entry == rule_id:
            idx = rules.index(entry)
            rules[idx] = {"id": rule_id, "enabled": False}
            found = True
            break

    if not found:
        print(color(f"Rule '{rule_id}' not found in schema '{schema_name}'.", "red"))
        sys.exit(1)

    # Write back
    try:
        import yaml
        with open(schema_path, "w", encoding="utf-8") as f:
            yaml.dump(schema_data, f, default_flow_style=False, sort_keys=False)
        print(color(f"✓ Disabled rule '{rule_id}' in schema '{schema_name}'", "green"))
    except ImportError:
        print(color("PyYAML required to write schema files. Install: pip install pyyaml", "red"))


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------

def cmd_status(args):
    """Show current Gatehouse enforcement status."""
    gate_home = get_gate_home()
    mode = os.environ.get("GATEHOUSE_MODE", "off").lower()

    if mode not in ("hard", "soft", "off"):
        mode = "off"

    mode_colors = {"hard": "red", "soft": "yellow", "off": "dim"}
    mode_labels = {
        "hard": "HARD — violations block execution (LLM enforcement)",
        "soft": "SOFT — violations printed, execution continues (developer visibility)",
        "off": "OFF — pass-through, no checking",
    }

    print()
    print(f"  {color('GATEHOUSE STATUS', 'bold')}")
    print(f"  {'─' * 56}")
    print(f"  Mode:      {color(mode_labels[mode], mode_colors[mode])}")
    print(f"  Home:      {color(gate_home, 'cyan')} {'(auto-discovered)' if not os.environ.get('GATE_HOME') else '($GATE_HOME)'}")

    # Check if python_gate is reachable (local or on PATH)
    import shutil
    gate_path = os.path.join(gate_home, "python_gate")
    gate_on_path = shutil.which("python_gate")
    if os.path.isfile(gate_path):
        print(f"  Gate:      {color('found', 'green')} ({gate_path})")
    elif gate_on_path:
        print(f"  Gate:      {color('found', 'green')} ({gate_on_path})")
    else:
        print(f"  Gate:      {color('NOT FOUND', 'red')}")

    # Check rules and schemas directories
    rules_dir = os.path.join(gate_home, "rules")
    schemas_dir = os.path.join(gate_home, "schemas")
    rules_ok = os.path.isdir(rules_dir) and any(f.endswith(".yaml") for f in os.listdir(rules_dir))
    schemas_ok = os.path.isdir(schemas_dir) and any(f.endswith(".yaml") for f in os.listdir(schemas_dir))
    print(f"  Rules:     {color('found', 'green') if rules_ok else color('NOT FOUND', 'red')} ({rules_dir})")
    print(f"  Schemas:   {color('found', 'green') if schemas_ok else color('NOT FOUND', 'red')} ({schemas_dir})")

    # Check for .gate_schema.yaml in current directory
    schema_path = os.path.join(os.getcwd(), ".gate_schema.yaml")
    if os.path.isfile(schema_path):
        project_config = load_yaml(schema_path)
        schema_name = project_config.get("schema", "unknown")
        print(f"  Project:   {color(schema_name, 'cyan')} (.gate_schema.yaml found)")
    else:
        print(f"  Project:   {color('no .gate_schema.yaml in current directory', 'dim')}")

    print(f"  {'─' * 56}")

    if mode == "off":
        print(f"  {color('To activate:', 'dim')} export GATEHOUSE_MODE=hard")
    else:
        print(f"  {color('To deactivate:', 'dim')} export GATEHOUSE_MODE=off")

    print()


def cmd_activate(args):
    """Print the shell commands to activate Gatehouse."""
    mode = args.mode or "hard"
    if mode not in ("hard", "soft"):
        print(color("  Mode must be 'hard' or 'soft'.", "red"))
        sys.exit(1)

    gate_home = get_gate_home()
    gate_path = os.path.join(gate_home, "python_gate")

    # Check if python_gate is on PATH (installed via pip script-files)
    import shutil
    gate_on_path = shutil.which("python_gate")

    print()
    print(f"  {color('Run these commands in your shell:', 'bold')}")
    print()
    print(f"    export GATEHOUSE_MODE={mode}")
    if gate_on_path:
        print(f"    alias python=\"python_gate\"")
    else:
        print(f"    alias python=\"{gate_path}\"")
    print()

    mode_desc = {
        "hard": "violations will BLOCK execution (LLM enforcement)",
        "soft": "violations will be PRINTED but execution continues (developer visibility)",
    }
    print(f"  {color(mode_desc[mode], 'yellow' if mode == 'soft' else 'red')}")
    print()
    print(f"  {color('Add to ~/.bashrc or ~/.zshrc to persist across sessions.', 'dim')}")
    print()


def cmd_deactivate(args):
    """Print the shell command to deactivate Gatehouse."""
    print()
    print(f"  {color('Run this command in your shell:', 'bold')}")
    print()
    print(f"    export GATEHOUSE_MODE=off")
    print()
    print(f"  {color('Gatehouse will pass through to real Python with zero overhead.', 'dim')}")
    print()


# ---------------------------------------------------------------------------
# Main CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="gatehouse",
        description="Gatehouse — Error-driven code schema enforcement",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # new-rule
    sub_new = subparsers.add_parser("new-rule", help="Create a new rule interactively")

    # init
    sub_init = subparsers.add_parser("init", help="Initialize a project with .gate_schema.yaml")
    sub_init.add_argument("--schema", default="production", help="Schema to use (default: production)")

    # list-rules
    sub_list = subparsers.add_parser("list-rules", help="List available rules")
    sub_list.add_argument("--schema", help="Show rules in a specific schema")

    # test-rule
    sub_test = subparsers.add_parser("test-rule", help="Test a rule against a file")
    sub_test.add_argument("rule_id", help="Rule ID to test")
    sub_test.add_argument("file", help="Python file to test against")

    # disable-rule
    sub_disable = subparsers.add_parser("disable-rule", help="Disable a rule in a schema")
    sub_disable.add_argument("rule_id", help="Rule ID to disable")
    sub_disable.add_argument("--schema", required=True, help="Schema to modify")

    # status
    subparsers.add_parser("status", help="Show current enforcement status")

    # activate
    sub_activate = subparsers.add_parser("activate", help="Print shell commands to activate Gatehouse")
    sub_activate.add_argument("--mode", choices=["hard", "soft"], default="hard",
                              help="Enforcement mode (default: hard)")

    # deactivate
    subparsers.add_parser("deactivate", help="Print shell commands to deactivate Gatehouse")

    args = parser.parse_args()

    if args.command == "new-rule":
        cmd_new_rule(args)
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "list-rules":
        cmd_list_rules(args)
    elif args.command == "test-rule":
        cmd_test_rule(args)
    elif args.command == "disable-rule":
        cmd_disable_rule(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "activate":
        cmd_activate(args)
    elif args.command == "deactivate":
        cmd_deactivate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
