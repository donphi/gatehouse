"""Gatehouse CLI entry point — argument parsing and command dispatch.

Provides the ``main()`` entry point that builds the argparse parser tree and
dispatches each subcommand to its handler in :mod:`gatehouse.cli.commands`.
All configurable strings (program name, description, default values) are
loaded from the central config module so nothing is hardcoded.

Usage::

    gatehouse new-rule
    gatehouse init --schema production
    gatehouse list-rules [--schema <name>]
    gatehouse test-rule <rule-id> <file>
    gatehouse disable-rule <rule-id>
    gatehouse enable-rule <rule-id>
    gatehouse status
    gatehouse activate [--mode hard|soft]
    gatehouse deactivate
    gatehouse lint-rules
"""

from __future__ import annotations

import argparse
import sys

from gatehouse import __version__
from gatehouse.cli.commands import (
    cmd_activate,
    cmd_deactivate,
    cmd_disable_rule,
    cmd_enable_rule,
    cmd_init,
    cmd_lint_rules,
    cmd_list_rules,
    cmd_new_rule,
    cmd_status,
    cmd_test_rule,
)
from gatehouse.lib import config


def main() -> None:
    """Parse arguments and dispatch to the appropriate command handler.

    Build the full argparse tree (one sub-parser per subcommand), resolve
    the selected command, and delegate to the matching handler function.
    Print help text when no subcommand is given.
    """
    prog = config.get_str("cli.prog_name")
    desc = config.get_str("cli.description")
    default_schema = config.get_str("defaults.schema_name")
    activate_mode = config.get_str("cli.activate_mode")
    valid_modes = [
        config.get_str("modes.hard"),
        config.get_str("modes.soft"),
    ]

    parser = argparse.ArgumentParser(prog=prog, description=desc)
    parser.add_argument(
        "--version", action="version", version=f"{prog} {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("new-rule", help="Create a new rule interactively")

    sub_init = subparsers.add_parser(
        "init", help="Initialize a project with .gate_schema.yaml"
    )
    sub_init.add_argument(
        "--schema",
        default=default_schema,
        help=f"Schema to use (default: {default_schema})",
    )

    sub_list = subparsers.add_parser("list-rules", help="List available rules")
    sub_list.add_argument("--schema", help="Show rules in a specific schema")

    sub_test = subparsers.add_parser(
        "test-rule", help="Test a rule against a file"
    )
    sub_test.add_argument("rule_id", help="Rule ID to test")
    sub_test.add_argument("file", help="Python file to test against")

    sub_disable = subparsers.add_parser(
        "disable-rule", help="Disable a rule in .gate_schema.yaml"
    )
    sub_disable.add_argument("rule_id", help="Rule ID to disable")

    sub_enable = subparsers.add_parser(
        "enable-rule", help="Re-enable a previously disabled rule"
    )
    sub_enable.add_argument("rule_id", help="Rule ID to enable")

    sub_status = subparsers.add_parser(
        "status", help="Show current enforcement status"
    )
    sub_status.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show resolved rules, effective config, and scope",
    )

    sub_activate = subparsers.add_parser(
        "activate", help="Print shell commands to activate Gatehouse"
    )
    sub_activate.add_argument(
        "--mode",
        choices=valid_modes,
        default=activate_mode,
        help=f"Enforcement mode (default: {activate_mode})",
    )

    subparsers.add_parser(
        "deactivate", help="Print shell commands to deactivate Gatehouse"
    )

    subparsers.add_parser(
        "lint-rules", help="Validate all rule YAML files for correctness"
    )

    args = parser.parse_args()

    dispatch = {
        "new-rule": cmd_new_rule,
        "init": cmd_init,
        "list-rules": cmd_list_rules,
        "test-rule": cmd_test_rule,
        "disable-rule": cmd_disable_rule,
        "enable-rule": cmd_enable_rule,
        "status": cmd_status,
        "activate": cmd_activate,
        "deactivate": cmd_deactivate,
        "lint-rules": cmd_lint_rules,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
