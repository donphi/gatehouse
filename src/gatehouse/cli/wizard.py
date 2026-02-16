"""wizard — interactive rule creation wizard for the Gatehouse CLI.

Guides the user through step-by-step rule configuration: choosing a rule ID,
name, description, check type, check-specific parameters, severity, error
message, and fix instruction.  The finished rule is written as a YAML file
into the rules directory.  An ASCII art banner is displayed at the start of
the session.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from gatehouse._paths import cli_dir as _cli_dir, rules_dir as _rules_dir
from gatehouse.cli.prompts import (
    evaluate_show_if,
    prompt_choice,
    prompt_number,
    prompt_severity,
    prompt_text,
    prompt_text_list,
)
from gatehouse.lib import config
from gatehouse.lib.theme import colorize
from gatehouse.lib.yaml_loader import load_yaml


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _color(text: str, role: str) -> str:
    """Colorize text for stdout so wizard output respects the active theme."""
    return colorize(text, role, stream=sys.stdout)


# -------------------------------------------------------------------------
# Banner
# -------------------------------------------------------------------------


def print_banner(branding: dict[str, Any], color_config: dict[str, Any]) -> None:
    """Print the ANSI art banner.

    Args:
        branding: Parsed branding.yaml dict.
        color_config: Color role mapping from branding.
    """
    bd = config.get("branding_defaults")
    title = branding.get("title", bd["title"])
    subtitle = branding.get("subtitle", bd["subtitle"])
    version = branding.get("version", bd["version"])
    tagline = branding.get("tagline", bd["tagline"])

    title_color = color_config.get("title", bd["title_color"])
    border_color = color_config.get("border", bd["border_color"])
    subtitle_color = config.get_str("colors.subtitle")
    tagline_color = config.get_str("colors.tagline")

    fallback_w = config.get_int("formatting.banner_fallback_width")
    min_w = config.get_int("formatting.banner_min_width")

    title_lines = [line for line in title.strip().splitlines() if line.strip()]
    max_width = max(len(line) for line in title_lines) if title_lines else fallback_w
    box_width = max(max_width + 4, min_w)

    print()
    print(_color(f"  \u2554{'\u2550' * box_width}\u2557", border_color))
    print(_color(f"  \u2551{' ' * box_width}\u2551", border_color))

    for line in title_lines:
        padded = line.ljust(box_width)
        print(
            _color("  \u2551", border_color)
            + _color(padded, title_color)
            + _color("\u2551", border_color)
        )

    print(_color(f"  \u2551{' ' * box_width}\u2551", border_color))

    if subtitle or version:
        info = f"  {subtitle} v{version}" if version else f"  {subtitle}"
        padded = info.ljust(box_width)
        print(
            _color("  \u2551", border_color)
            + _color(padded, subtitle_color)
            + _color("\u2551", border_color)
        )

    if tagline:
        padded = f"  {tagline}".ljust(box_width)
        print(
            _color("  \u2551", border_color)
            + _color(padded, tagline_color)
            + _color("\u2551", border_color)
        )

    print(_color(f"  \u2551{' ' * box_width}\u2551", border_color))
    print(_color(f"  \u255a{'\u2550' * box_width}\u255d", border_color))
    print()


# -------------------------------------------------------------------------
# Wizard entry point
# -------------------------------------------------------------------------


def cmd_new_rule(args: argparse.Namespace) -> None:
    """Launch the interactive rule creation wizard.

    Walk the user through creating a new rule YAML file by prompting for
    rule metadata, check type, check-specific parameters, severity, and
    error/fix messages.  The command is fully interactive.

    Args:
        args: Parsed CLI arguments (unused but required by dispatch).
    """
    # 1. Load branding and check-type configuration
    cd = _cli_dir()
    box_w = config.get_int("formatting.prompt_box_width")
    col_w = config.get_int("formatting.check_type_column_width")
    err_color = config.get_str("colors.error")
    ok_color = config.get_str("colors.success")
    new_version = config.get_str("defaults.new_rule_version")

    branding = load_yaml(str(cd / "branding.yaml"))
    check_types_config = load_yaml(str(cd / "check_types.yaml"))

    color_config: dict[str, str] = branding.get("colors", {})
    check_types: list[dict[str, Any]] = check_types_config.get("check_types", [])

    # 2. Display banner and collect rule metadata
    print_banner(branding, color_config)

    rule_id = prompt_text("Rule ID (used as filename, e.g. 'no-todo-comments')")
    if not rule_id:
        print(_color("  Rule ID is required.", err_color))
        return

    rule_name = prompt_text("Rule Name (human-readable)")
    description = prompt_text("Description")

    # 3. Prompt for check type selection
    print()
    border = "  \u250c" + "\u2500" * box_w + "\u2510"
    print(_color(border, "white"))
    print(_color(
        "  \u2502  What kind of check do you want?" + " " * 28 + "\u2502",
        "white",
    ))
    print(_color("  \u2502" + " " * box_w + "\u2502", "white"))

    for i, ct in enumerate(check_types, 1):
        label = ct.get("label", ct["id"])
        line = f"  \u2502    {i}. {ct['id']:<{col_w}s}\u2014 {label}"
        line = line.ljust(box_w + 2) + "\u2502"
        print(_color(line, "white"))

    print(_color("  \u2502" + " " * box_w + "\u2502", "white"))
    print(_color("  \u2514" + "\u2500" * box_w + "\u2518", "white"))
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
        print(_color(
            f"  Please enter a number between 1 and {len(check_types)}",
            err_color,
        ))

    # 4. Collect check-type-specific parameters
    check_type_id = selected_type["id"]
    collected: dict[str, Any] = {}

    if selected_type.get("prompts"):
        _collect_check_params(selected_type, collected, box_w)

    # 5. Collect severity, error message, and fix instruction
    params_lines: list[str] = []
    for key, val in collected.items():
        if key == "mode":
            continue
        if isinstance(val, list):
            params_lines.append(f"  {key}:")
            for item in val:
                params_lines.append(f'    - "{item}"')
        elif isinstance(val, int):
            params_lines.append(f"  {key}: {val}")
        else:
            params_lines.append(f'  {key}: "{val}"')

    check_params_yaml = "\n".join(params_lines)
    severity = prompt_severity()

    print()
    error_message = prompt_text("Error message (what the LLM sees when it fails)")
    fix_instruction = prompt_text("Fix instruction (what the LLM should do to fix it)")

    # 6. Write rule YAML to disk
    rd = _rules_dir()
    os.makedirs(rd, exist_ok=True)
    rule_path = str(rd / f"{rule_id}.yaml")

    rule_content = (
        f'# rules/{rule_id}.yaml\n'
        f'# Auto-generated by: gatehouse new-rule\n'
        f'\n'
        f'name: "{rule_name}"\n'
        f'description: "{description}"\n'
        f'version: "{new_version}"\n'
        f'\n'
        f'check:\n'
        f'  type: "{check_type_id}"\n'
        f'{check_params_yaml}\n'
        f'\n'
        f'error:\n'
        f'  message: "{error_message}"\n'
        f'  fix: "{fix_instruction}"\n'
        f'\n'
        f'defaults:\n'
        f'  severity: "{severity}"\n'
        f'  enabled: true\n'
    )

    with open(rule_path, "w", encoding="utf-8") as fh:
        fh.write(rule_content)

    # 7. Print confirmation
    print()
    print(_color("  \u250c" + "\u2500" * box_w + "\u2510", ok_color))
    print(_color(
        f"  \u2502  \u2713 Created: rules/{rule_id}.yaml".ljust(box_w + 2) + "\u2502",
        ok_color,
    ))
    print(_color("  \u2502" + " " * box_w + "\u2502", ok_color))
    print(_color(
        "  \u2502  To activate, add to your schema:" + " " * 25 + "\u2502",
        ok_color,
    ))
    print(_color(
        f'  \u2502    - id: "{rule_id}"'.ljust(box_w + 2) + "\u2502",
        ok_color,
    ))
    print(_color("  \u2502" + " " * box_w + "\u2502", ok_color))
    test_cmd = f"gatehouse test-rule {rule_id} <file.py>"
    print(_color(
        f"  \u2502  To test: {test_cmd}".ljust(box_w + 2) + "\u2502",
        ok_color,
    ))
    print(_color("  \u2514" + "\u2500" * box_w + "\u2518", ok_color))
    print()


# -------------------------------------------------------------------------
# Parameter collection
# -------------------------------------------------------------------------


def _collect_check_params(
    selected_type: dict[str, Any],
    collected: dict[str, Any],
    box_w: int,
) -> None:
    """Collect check-type-specific parameters via interactive prompts.

    Iterate the prompts defined in ``check_types.yaml`` for the chosen check
    type, respecting ``show_if`` conditions to skip irrelevant questions.

    Args:
        selected_type: The selected check type config dict.
        collected: Dict to store collected parameter values.
        box_w: Box width for formatting.
    """
    check_type_id = selected_type["id"]
    print()
    header = f"  {check_type_id} \u2014 Configure"
    print(_color("  \u250c" + "\u2500" * box_w + "\u2510", "white"))
    print(_color(f"  \u2502  {header}".ljust(box_w + 2) + "\u2502", "white"))
    print(_color("  \u2502" + " " * box_w + "\u2502", "white"))
    print(_color("  \u2514" + "\u2500" * box_w + "\u2518", "white"))

    for prompt_def in selected_type["prompts"]:
        show_if = prompt_def.get("show_if", "")
        if show_if and not evaluate_show_if(show_if, collected):
            continue

        field_name = prompt_def["field"]
        ask = prompt_def["ask"]
        ptype = prompt_def["type"]
        hint = prompt_def.get("hint")
        default = prompt_def.get("default")
        optional = prompt_def.get("optional", False)

        if ptype == "text":
            val = prompt_text(
                ask, hint=hint, default=str(default) if default else None
            )
            if val or not optional:
                collected[field_name] = val
        elif ptype == "choice":
            options = prompt_def.get("options", [])
            val = prompt_choice(ask, options)
            collected[field_name] = val
        elif ptype == "text_list":
            val = prompt_text_list(ask, hint=hint)
            if val:
                collected[field_name] = val
        elif ptype == "number":
            val = prompt_number(ask, default=default)
            collected[field_name] = val
