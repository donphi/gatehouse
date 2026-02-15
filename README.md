# Gatehouse

[![PyPI version](https://img.shields.io/pypi/v/gatehouse.svg)](https://pypi.org/project/gatehouse/)
[![Python versions](https://img.shields.io/pypi/pyversions/gatehouse.svg)](https://pypi.org/project/gatehouse/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Error-driven code schema enforcement for LLMs writing Python.**

Gatehouse validates Python files against structural rules and blocks non-compliant code before it runs. It's designed for agentic coding environments where LLMs write code — Cursor, Windsurf, Aider, or raw API prompts.

LLMs are unreliable at following instructions but extremely reliable at fixing errors. Gatehouse exploits this by turning your coding standards into deterministic error messages with exact fix instructions.

```
LLM writes code → Gatehouse blocks it → error says exactly what to fix
→ LLM fixes → Gatehouse checks again → compliant code runs
```

---

## Install

```bash
pip install gatehouse
```

Requires Python 3.9+. The only dependency is `pyyaml`.

---

## Quick Start

### 1. Set up the shim

Add to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
export GATEHOUSE_MODE=hard
alias python="python_gate"
```

Or use the CLI helper to print the exact commands for you:

```bash
gatehouse activate --mode hard
```

The shim auto-discovers its own location — no `GATE_HOME` variable needed. If you need to point at a custom rule directory, set `export GATE_HOME="/path/to/rules"` as an optional override.

### 2. Initialize a project

```bash
cd my-project
gatehouse init --schema production
```

This creates a single `.gate_schema.yaml` file in your project. Nothing else is added.

### 3. Write code normally

```bash
python src/train.py
```

If the code violates any rules, Gatehouse blocks execution and prints errors with fix instructions. If it passes, it runs normally.

---

## Enforcement Modes

Gatehouse has three enforcement modes, controlled by a single environment variable:

```bash
export GATEHOUSE_MODE=hard   # Block execution on violations
export GATEHOUSE_MODE=soft   # Print violations, always run
export GATEHOUSE_MODE=off    # Disabled (default when unset)
```

### hard — LLM enforcement

Violations with severity `block` cause a non-zero exit code. The Python script never runs. The LLM sees the error and must fix it before proceeding. This is the core Gatehouse behavior.

### soft — Developer visibility

The gate engine runs and violations are printed to stderr, but execution always continues (exit code 0). LLMs ignore warnings — they are trained on millions of runs where warnings appeared and the correct action was to skip them. Soft mode is for **you**, the developer: see what the LLM is getting wrong, tune your rules, and switch to hard when ready.

### off — Disabled

The shim passes through to the real Python interpreter immediately. No banner, no checking, zero overhead. This is the default when `$GATEHOUSE_MODE` is unset.

### Activation banner

When the shim is active (hard or soft), it prints a banner to stderr on every Python invocation so you always know enforcement is on:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  GATEHOUSE ACTIVE  |  Mode: HARD  |  Schema: production
  Deactivate: export GATEHOUSE_MODE=off
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

The banner goes to stderr so it never corrupts your program's stdout.

---

## What It Does

Given this code:

```python
import torch

def train():
    learning_rate = 0.001
    for epoch in range(10):
        print(f"Epoch {epoch}")
```

Gatehouse blocks it:

```
  File "src/train.py", line 1
    import torch
  StructureError: Missing standard file header
  Fix: Add the following as the first lines of src/train.py:

        # ============================================================================
        # FILE: train.py
        # LOCATION: src/
        # PIPELINE POSITION: <describe where this fits>
        # PURPOSE: <one-line description>
        # ============================================================================

  File "src/train.py", line 4
        learning_rate = 0.001
                        ^^^^^
  HardcodedValueError: numeric literal `0.001` on line 4
  Fix: Move to a HYPERPARAMETERS block as LEARNING_RATE = 0.001

  Schema: production-ready-python (v1.0.0)
  Violations: 6 blocking, 0 warnings
  Execution: BLOCKED
```

Every error includes the file, line number, the offending code, what's wrong, and exactly how to fix it. The LLM reads these, fixes the code, and tries again.

---

## How It Works

Gatehouse intercepts `python` calls at the OS level via a bash shim. The shim checks `$GATEHOUSE_MODE` first — if it's `off` or unset, Python runs normally with zero overhead. In `hard` or `soft` mode, the shim auto-discovers the gate engine and validates the code before execution. The LLM can't bypass it because it doesn't know the shim exists — it only sees the errors.

---

## Schemas

Schemas are rule sets. Pick one when initializing a project:

| Schema | Rules | Use Case |
|--------|-------|----------|
| `production` | 10 rules, mostly blocking | Production source code |
| `exploration` | 2 rules, warnings only | Scratch scripts, experiments |
| `api` | Production + API route rules | FastAPI / Flask services |
| `minimal` | 1 rule, warning only | Just catch hardcoded values |

```bash
gatehouse init --schema exploration
```

---

## Rules

Each rule is a single YAML file. The `production` schema includes:

| Rule | Checks For | Severity |
|------|-----------|----------|
| `file-header` | Standard header block at top of file | Block |
| `module-docstring` | Module docstring with required sections | Block |
| `no-hardcoded-values` | Magic numbers buried in code | Block |
| `function-docstrings` | Docstring on every function | Block |
| `main-guard` | `if __name__ == "__main__":` guard | Block |
| `hyperparameter-block` | UPPER_SNAKE_CASE constants | Block |
| `max-file-length` | File length under 1000 lines | Block |
| `rich-progress` | Progress tracking on loops | Warn |
| `imports-present` | Import statements exist | Warn |

**Block** = code cannot run. **Warn** = warning shown, code still runs.

---

## Customization

### Override rules per project

Edit `.gate_schema.yaml` in your project root:

```yaml
schema: "production"

rule_overrides:
  "main-guard":
    severity: "off"              # Disable a rule
  "function-docstrings":
    severity: "warn"             # Downgrade from block to warn
  "max-file-length":
    params:
      max_lines: 500             # Make stricter

overrides:
  "scripts/":
    schema: "exploration"        # Different schema for a folder
  "tests/":
    schema: null                 # No checking
```

### Create custom rules

Using the CLI (interactive, no YAML knowledge needed):

```bash
gatehouse new-rule
```

Or manually — create a YAML file in the `rules/` directory:

```yaml
# rules/no-todo-comments.yaml
name: "No TODO Comments"
description: "Disallow TODO comments in production code"

check:
  type: "pattern_exists"
  pattern: "# TODO"
  location: "anywhere"

error:
  message: "StyleWarning: TODO comment found on line {line}"
  fix: "Resolve the TODO or move it to a tracking issue"

defaults:
  severity: "warn"
  enabled: true
```

Then reference it in a schema:

```yaml
rules:
  - id: "no-todo-comments"
```

### Built-in check types

| Type | What It Does |
|------|-------------|
| `pattern_exists` | Match a regex or string at a location |
| `ast_node_exists` | Check for an AST node (docstring, import, class) |
| `ast_check` | Parameterized AST checks (all functions have docstrings, etc.) |
| `token_scan` | Tokenizer-level scan (hardcoded literals, log calls) |
| `uppercase_assignments_exist` | Module-level constant detection |
| `docstring_contains` | Required sections in docstrings |
| `file_metric` | Line count, function count, import count thresholds |
| `custom` | Inline Python expression or external plugin file |

---

## Standalone Usage

Use Gatehouse with any LLM API in a validation loop:

```python
import subprocess

result = subprocess.run(
    ["python3", "-m", "gate_engine", "--stdin",
     "--schema", ".gate_schema.yaml",
     "--filename", "src/train.py"],
    input=code_from_llm,
    capture_output=True, text=True
)

if result.returncode == 0:
    # Code passed — save it
    with open("src/train.py", "w") as f:
        f.write(code_from_llm)
else:
    # Code failed — feed errors back to the LLM
    errors = result.stderr
```

See `examples/standalone_usage.py` for a complete working example.

---

## CLI Reference

```bash
gatehouse init --schema <name>          # Initialize a project
gatehouse list-rules                    # List all available rules
gatehouse list-rules --schema <name>    # List rules in a specific schema
gatehouse new-rule                      # Create a rule interactively
gatehouse test-rule <rule> <file>       # Test a rule against a file
gatehouse disable-rule <rule> --schema <name>  # Disable a rule in a schema
gatehouse status                        # Show current enforcement mode and config
gatehouse activate [--mode hard|soft]   # Print shell commands to activate
gatehouse deactivate                    # Print shell commands to deactivate
```

---

## Telemetry

Every scan is logged to `logs/gate/violations.jsonl` in your project directory. Each line is a JSON object:

```json
{
  "timestamp": "2026-02-14T14:57:00Z",
  "file": "src/train.py",
  "schema": "production",
  "status": "rejected",
  "violations": [{"rule": "file-header", "severity": "block", "line": 1}],
  "passed_rules": ["max-file-length", "imports-present"],
  "scan_ms": 7
}
```

Useful for tracking which rules get violated most, measuring LLM compliance over time, and generating fine-tuning data.

---

## Docker Usage

Gatehouse works in Docker containers with no special configuration. Add to your Dockerfile:

```dockerfile
RUN pip install gatehouse
ENV GATEHOUSE_MODE=hard
RUN ln -sf "$(which python_gate)" /usr/local/bin/python
```

After `pip install`, `python_gate` is on `$PATH` and auto-discovers its rules and schemas. No `GATE_HOME` needed. The shim works identically inside and outside containers.

---

## Architecture

```
gatehouse/
├── gate_engine.py          # Core engine — fixed runtime, never changes for rule changes
├── python_gate             # Bash shim — intercepts python calls at OS level
├── cli/                    # Interactive CLI for rule management
├── rules/                  # One YAML file per rule (12 built-in)
├── schemas/                # Schema manifests — assemble rules into sets
├── plugins/                # Custom check plugins (Python files)
└── examples/               # Example configs and usage scripts
```

The engine is fixed. All behavior comes from YAML rule files and schema manifests. Adding a rule means adding a YAML file. Removing a rule means deleting a line from a schema. The engine code never changes.

---

## License

MIT
