# Gatehouse

[![PyPI version](https://img.shields.io/pypi/v/gatehouse.svg)](https://pypi.org/project/gatehouse/)
[![Python versions](https://img.shields.io/pypi/pyversions/gatehouse.svg)](https://pypi.org/project/gatehouse/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Error-driven code schema enforcement for Python.**

Gatehouse validates Python files against structural rules and blocks non-compliant code before it runs. Designed for agentic coding environments where LLMs write code — Cursor, Windsurf, Aider, or raw API prompts.

LLMs are unreliable at following instructions but reliable at fixing errors. Gatehouse turns your coding standards into deterministic error messages with exact fix instructions.

```
LLM writes code → Gatehouse blocks it → error says exactly what to fix
→ LLM fixes → Gatehouse checks again → compliant code runs
```

---

## Install

```bash
pip install gatehouse
```

Requires Python 3.9+.

---

## Quick Start

### 1. Activate Gatehouse

Add to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
export GATEHOUSE_MODE=hard
alias python="python_gate"
```

Or use the CLI:

```bash
gatehouse activate --mode hard
```

### 2. Initialize a project

```bash
cd my-project
gatehouse init --schema production
```

This creates `.gate_schema.yaml` in your project root. Nothing else.

### 3. Run code

```bash
python src/train.py
```

If violations exist, execution is blocked and errors tell the LLM exactly what to fix. If it passes, the code runs normally.

---

## What Happens

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
  StructureError: Missing standard file header

  File "src/train.py", line 4
        learning_rate = 0.001
                        ^^^^^
  HardcodedValueError: numeric literal `0.001` on line 4
  Fix: Move this literal to a module-level constant or load it from external config

  Violations: 6 blocking, 0 warnings
  Execution: BLOCKED
```

Every error includes the file, line, offending code, what's wrong, and how to fix it.

---

## Enforcement Modes

Controlled by a single environment variable:

| Mode | Behaviour |
|------|-----------|
| `hard` | Block execution on violations. The LLM sees errors and must fix them. |
| `soft` | Print violations to stderr, always run. For tuning rules before enforcing. |
| `off` | Pass-through to real Python. Zero overhead. Default when unset. |

```bash
export GATEHOUSE_MODE=hard
```

When active, a banner prints to stderr on every invocation:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  GATEHOUSE ACTIVE  |  Mode: HARD  |  Schema: production
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Schemas and Rules

Schemas are named rule sets. Pick one when initializing:

| Schema | Rules | Use Case |
|--------|-------|----------|
| `production` | 10 rules, mostly blocking | Production source code |
| `api` | Production + API route checks | FastAPI / Flask services |
| `exploration` | 2 rules, warnings only | Scratch scripts, experiments |
| `minimal` | 1 rule, warning only | Just catch hardcoded values |

The `production` schema includes:

| Rule | What It Checks | Severity |
|------|---------------|----------|
| `file-header` | Standard header block at top of file | Block |
| `module-docstring` | Module-level docstring exists | Block |
| `no-hardcoded-values` | No magic numbers/strings/booleans inside functions | Block |
| `function-docstrings` | Every function has a docstring | Block |
| `main-guard` | `if __name__ == "__main__":` guard present | Block |
| `hyperparameter-block` | UPPER_SNAKE_CASE module-level constants | Block |
| `max-file-length` | File under 1000 lines | Block |
| `rich-progress` | Progress tracking on for-loops | Warn |
| `imports-present` | Import statements exist | Warn |

**Block** = code cannot run. **Warn** = warning shown, code runs.

---

## CLI Reference

```bash
gatehouse init --schema <name>           # Initialize project
gatehouse activate [--mode hard|soft]    # Print shell activation commands
gatehouse deactivate                     # Print deactivation commands
gatehouse status                         # Show mode and config
gatehouse list-rules                     # List all available rules
gatehouse list-rules --schema <name>     # List rules in a schema
gatehouse new-rule                       # Create a rule interactively
gatehouse test-rule <rule> <file>        # Test a rule against a file
gatehouse disable-rule <rule> --schema <name>
```

---

## Standalone Usage (API Integration)

Use Gatehouse programmatically with any LLM API:

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
    with open("src/train.py", "w") as f:
        f.write(code_from_llm)
else:
    errors = result.stderr  # Feed back to the LLM
```

See `examples/standalone_usage.py` for a complete loop.

---

# Advanced

Everything below is for understanding internals, customizing rules, and contributing.

---

## Architecture — Linear Data Flow

Every Python invocation flows through the same linear path:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ python_gate  │ ──▶ │ gate_engine  │ ──▶ │SourceAnalyzer│ ──▶ │  Rule YAML   │
│(interceptor) │     │ (dispatcher) │     │(LibCST parse)│     │(check config)│
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │                    │
       ▼                    ▼                    ▼                    ▼
  Intercepts          Loads schema &         One parse.            Each rule
  `python` calls,     resolves rules,        One tree.             queries the
  checks mode,        runs each rule         One metadata          analyzer for
  finds schema        through the            resolve.              its check.
                      dispatcher             All rules share it.
```

### Step by step

1. **`python_gate`** intercepts `python` calls at the OS level. Checks `$GATEHOUSE_MODE` — if `off`, passes through immediately. Otherwise finds `.gate_schema.yaml` by walking up from the target file.

2. **`gate_engine.py`** (dispatcher) loads the schema, resolves which rules are active, creates a single `SourceAnalyzer`, and passes it to each rule's check function.

3. **`lib/analyzer.py`** (`SourceAnalyzer`) parses the source once with [LibCST](https://github.com/Instagram/LibCST) and resolves metadata providers (`PositionProvider`, `ParentNodeProvider`). Every rule queries this object — no rule touches raw source text.

4. **`rules/*.yaml`** define what to check. Each YAML file declares a check type, parameters, error message, and fix instruction. The engine maps check types to `SourceAnalyzer` methods internally.

5. **`schemas/*.yaml`** assemble rules into named sets with severity overrides. `.gate_schema.yaml` in the project root selects which schema to use.

### File map

```
gatehouse/
├── python_gate              Interceptor — validates before Python runs
├── gate_engine.py           Dispatcher — loads rules, routes checks, formats output
├── lib/
│   └── analyzer.py          SourceAnalyzer — single LibCST parse + metadata
├── rules/                   One YAML file per rule (12 built-in)
├── schemas/                 Schema manifests (production, api, exploration, minimal)
├── cli/
│   └── gatehouse_cli.py     Interactive CLI for rule management
├── plugins/                 Custom check plugins (Python files)
└── examples/                Example configs and usage scripts
```

---

## How LibCST Powers the Engine

Gatehouse uses [LibCST](https://github.com/Instagram/LibCST) (Meta's Concrete Syntax Tree library for Python) instead of `ast` or `tokenize`. This is a deliberate architectural choice.

### Why not `ast` or `tokenize`?

`ast` discards comments and whitespace. `tokenize` gives raw tokens with no structure. Both require glue code to answer structural questions like "is this literal inside a function body?" or "is this string a docstring?".

LibCST preserves all source detail (comments, whitespace, formatting) while providing a typed tree with parent/child relationships and scope-aware metadata.

### One parse, one resolve

`SourceAnalyzer` creates exactly one parse tree and one metadata resolution per file. All 12 rules query the same object:

```python
analyzer = SourceAnalyzer(source, filepath)

# Rules call methods like:
analyzer.has_main_guard()                          # CST If node matching
analyzer.header_comments()                         # Module.header EmptyLine nodes
analyzer.literals_in_function_bodies(safe, ctx)    # Scope-aware literal detection
analyzer.functions_missing_docstrings()            # FunctionDef body inspection
```

### Metadata providers

The `MetadataWrapper` resolves two providers once, shared by all visitors:

| Provider | What it gives | Used by |
|----------|---------------|---------|
| `PositionProvider` | Line/column for any node | All rules (for error reporting) |
| `ParentNodeProvider` | Parent node of any node | `no-hardcoded-values` (dict context, call argument context, docstring detection) |

### Why this matters for `no-hardcoded-values`

The hardcoded values rule needs to answer: "Is this literal inside a function body, and if so, is it a safe context (dict, call argument, docstring)?"

With `ast`, this required hacking `_parent` attributes onto every node and walking up the chain. With LibCST, `ParentNodeProvider` gives the parent of any node in O(1), and `_func_depth` tracking in the CST visitor handles scope nesting structurally.

Negative numbers like `-1` in CST are `UnaryOperation(Minus, Integer("1"))` — a separate node type that the old `ast`-based code didn't handle. The LibCST implementation unwraps these explicitly, fixing the bug where `safe_values: [-1]` was silently ignored.

Boolean values `True`/`False` are `Name` nodes in CST (not literals), and the type-aware safe value check prevents `True == 1` from colliding with `safe_values: [1]`.

---

## Customization

### Override rules per project

Edit `.gate_schema.yaml` in your project root:

```yaml
schema: "production"

rule_overrides:
  "main-guard":
    severity: "off"
  "function-docstrings":
    severity: "warn"
  "max-file-length":
    params:
      max_lines: 500

overrides:
  "scripts/":
    schema: "exploration"
  "tests/":
    schema: null
```

### Create custom rules

Using the CLI:

```bash
gatehouse new-rule
```

Or manually — create a YAML file in `rules/`:

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

Reference it in a schema:

```yaml
rules:
  - id: "no-todo-comments"
```

### Check types

| Type | What It Does |
|------|-------------|
| `pattern_exists` | Structural CST match (main guard, print call, header block) or string/regex fallback |
| `ast_node_exists` | Check for module docstring, import statements |
| `ast_check` | Function docstrings, for-loop progress, decorated function checks |
| `token_scan` | Scope-aware hardcoded literal detection, log call scanning |
| `uppercase_assignments_exist` | Module-level UPPER_SNAKE_CASE constant count |
| `docstring_contains` | Required text in module docstring |
| `file_metric` | Line count threshold |
| `custom` | Inline Python expression or external plugin file |

Despite the legacy names (`ast_check`, `token_scan`), all check types use LibCST internally. The names are kept for backward compatibility with existing rule YAML files.

---

## Telemetry

Scans are logged to `logs/gate/violations.jsonl` (when logging is enabled in `.gate_schema.yaml`):

```json
{
  "timestamp": "2026-02-15T14:57:00Z",
  "file": "src/train.py",
  "schema": "production",
  "status": "rejected",
  "violations": [{"rule": "file-header", "severity": "block", "line": 1}],
  "passed_rules": ["max-file-length", "imports-present"],
  "scan_ms": 7
}
```

---

## Docker

```dockerfile
RUN pip install gatehouse
ENV GATEHOUSE_MODE=hard
RUN ln -sf "$(which python_gate)" /usr/local/bin/python
```

LibCST ships pre-built wheels for Linux x86_64, macOS (x86_64 + ARM), and Windows x86_64. If no wheel exists for your platform (e.g. Alpine), the Rust toolchain is required to build from source. Use `python:3.11-slim` or similar as your Docker base.

---

## License

MIT
