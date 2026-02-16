"""prompts — interactive terminal input helpers for the rule builder.

Provides reusable prompt primitives for the interactive rule-creation wizard
and other CLI flows that require user input.  Available prompt types include
free-text input, numbered single-choice selection, comma-separated lists,
integer input, and severity (block/warn) selection.  A lightweight expression
evaluator supports conditional prompt visibility.
"""

from __future__ import annotations

import re
import sys
from typing import Any, Optional

from gatehouse.lib import config
from gatehouse.lib.theme import colorize


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _color(text: str, role: str) -> str:
    """Colorize text for stdout output so prompts respect the active theme."""
    return colorize(text, role, stream=sys.stdout)


# -------------------------------------------------------------------------
# Prompt primitives
# -------------------------------------------------------------------------


def prompt_text(
    question: str,
    hint: Optional[str] = None,
    default: Optional[str] = None,
) -> Optional[str]:
    """Prompt for free text input.

    Args:
        question: The question to display.
        hint: Optional hint text shown in parentheses.
        default: Default value shown in brackets, returned if input is empty.

    Returns:
        User input string, or default if empty.
    """
    prompt_str = f"  {question}"
    if hint:
        prompt_str += _color(f" ({hint})", "dim")
    if default:
        prompt_str += _color(f" [{default}]", "dim")
    prompt_str += ": "

    answer = input(prompt_str).strip()
    return answer if answer else default


def prompt_choice(question: str, options: list[dict[str, str]]) -> str:
    """Prompt for a single choice from a numbered list.

    Args:
        question: The question to display.
        options: List of dicts with 'value' and 'label' keys.

    Returns:
        The 'value' of the selected option.
    """
    print(f"\n  {question}")
    for i, opt in enumerate(options, 1):
        label = opt.get("label", opt.get("value", ""))
        print(f"    {_color(str(i), 'green')}. {label}")
    print()

    while True:
        answer = input(f"  Select [1-{len(options)}]: ").strip()
        try:
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                return options[idx]["value"]
        except (ValueError, IndexError):
            pass
        print(_color(f"  Please enter a number between 1 and {len(options)}", "red"))


def prompt_text_list(
    question: str,
    hint: Optional[str] = None,
) -> list[str]:
    """Prompt for a comma-separated list.

    Args:
        question: The question to display.
        hint: Optional hint text.

    Returns:
        List of trimmed strings, or empty list.
    """
    raw = prompt_text(question, hint=hint)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def prompt_number(
    question: str,
    default: Optional[int] = None,
) -> int:
    """Prompt for an integer.

    Args:
        question: The question to display.
        default: Default value if input is empty.

    Returns:
        The entered integer.
    """
    err_msg = config.get_str("messages.invalid_number")
    while True:
        raw = prompt_text(question, default=str(default) if default else None)
        if not raw and default is not None:
            return default
        try:
            return int(raw)
        except (ValueError, TypeError):
            print(_color(f"  {err_msg}", config.get_str("colors.error")))


def prompt_severity() -> str:
    """Prompt for block/warn severity selection.

    Returns:
        Either 'block' or 'warn'.
    """
    sev_choices = tuple(config.get_list("severities.valid_choices"))
    question = config.get_str("prompts.severity_question")
    block_desc = config.get_str("prompts.block_description")
    warn_desc = config.get_str("prompts.warn_description")
    input_label = config.get_str("prompts.severity_input_label")
    err_msg = config.get_str("messages.invalid_severity")

    print(f"\n  {question}")
    print(f"    {_color(sev_choices[0], 'green')} \u2014 {block_desc}")
    print(f"    {_color(sev_choices[1], 'green')}  \u2014 {warn_desc}")
    print()
    while True:
        answer = input(f"  {input_label}").strip().lower()
        if answer in sev_choices:
            return answer
            print(_color(f"  {err_msg}", config.get_str("colors.error")))


# -------------------------------------------------------------------------
# Condition evaluation
# -------------------------------------------------------------------------


def evaluate_show_if(
    show_if_expr: str,
    collected_values: dict[str, Any],
) -> bool:
    """Safely evaluate a show_if condition from check_types.yaml.

    Supports two patterns only (no eval):
      - "field == 'value'"
      - "field in ['value1', 'value2']"

    Args:
        show_if_expr: The condition expression string.
        collected_values: Dict of previously collected prompt values.

    Returns:
        True if the condition is met or cannot be parsed.
    """
    if not show_if_expr:
        return True

    eq_match = re.match(r"(\w+)\s*==\s*['\"](.+?)['\"]", show_if_expr)
    if eq_match:
        field_name = eq_match.group(1)
        expected = eq_match.group(2)
        return collected_values.get(field_name) == expected

    in_match = re.match(r"(\w+)\s+in\s+\[(.+?)\]", show_if_expr)
    if in_match:
        field_name = in_match.group(1)
        raw_items = in_match.group(2)
        allowed = [
            item.strip().strip("'\"")
            for item in raw_items.split(",")
        ]
        return collected_values.get(field_name) in allowed

    return True
