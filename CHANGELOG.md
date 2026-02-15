# Changelog

All notable changes to Gatehouse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-02-15

### Added

- **LibCST engine** — all rules now run against a single LibCST (Meta's Concrete Syntax Tree) parse instead of `ast`, `tokenize`, and raw text scanning
- `lib/analyzer.py` — new `SourceAnalyzer` class: one parse, one metadata resolve, every rule queries the same object
- `ParentNodeProvider` and `PositionProvider` metadata — structural parent/child and line/column lookups replace manual tree-walking hacks
- `libcst>=1.0` added as a dependency
- `cli/theme.yaml` — centralised ANSI colour theme for all engine and CLI output; change colours once, applies everywhere
- Coloured violation output — file paths, error messages, carets, fix instructions, and summary footer now use semantic colour roles from `theme.yaml`

### Fixed

- **`no-hardcoded-values`:** negative numbers in `safe_values` (e.g. `-1`) now work — previously `-1` was silently ignored because `ast.Constant` never sees negative literals as a single node; LibCST unwraps `UnaryOperation(Minus, Integer)` explicitly
- **`no-hardcoded-values`:** `True` and `False` are now flagged as hardcoded values — previously `True == 1` collided with `safe_values: [1]`; type-aware comparison prevents this
- **`main-guard`:** comments containing `if __name__` can no longer produce a false positive — CST structural matching requires an actual `If` node with a `Comparison`, which comments cannot create
- **`file-header`:** header detection reads `Module.header` comment nodes structurally instead of grepping first lines

### Changed

- `gate_engine.py` reduced from 1059 to 816 lines — all `_annotate_parents`, `_is_docstring_node`, `_is_in_dict`, `_is_call_argument`, `_is_inside_function` helpers removed
- `run_check` signature changed from `(rule_obj, source, ast_tree, source_lines, filepath)` to `(rule_obj, analyzer)`
- `scan_file` creates a single `SourceAnalyzer` instead of calling `ast.parse` + splitting source lines
- `import ast`, `import tokenize`, `import io` removed from `gate_engine.py`
- Rule YAML `type` values unchanged — backward compatible with all existing rule files

### Removed

- `check_pattern_exists` text scanning function (replaced by `SourceAnalyzer` CST methods)
- `_get_decorator_name` stdlib `ast` helper (replaced by CST equivalent in `lib/analyzer.py`)
- All `_annotate_parents` / `_is_*` helper functions from `gate_engine.py`

## [0.1.3] - 2026-02-15

### Fixed

- **Critical:** `python_gate` now discovers `gate_engine.py` correctly after `pip install` — previously it looked in its own directory (`/usr/local/bin/`) instead of site-packages, silently disabling all enforcement
- `main-guard` rule no longer matches `if __name__` patterns inside comments — files with header comments mentioning the guard were incorrectly passing
- `no-hardcoded-values` rule no longer flags f-strings, dict keys, or `return 0.0` — these are normal Python patterns, not hardcoded configuration
- `module-docstring` rule no longer requires undocumented literal sections (`MODULE OVERVIEW:`, `HYPERPARAMETERS:`, `DEPENDENCIES:`) — now checks for docstring existence only

### Changed

- `python_gate` uses a three-step discovery chain: `$GATE_HOME` override → script directory (dev install) → Python module import (pip install)
- `no-hardcoded-values` rule adds `dict_key` and `fstring` safe contexts, and `0.0` to safe values
- `module-docstring` rule error message simplified to match actual check behavior

## [0.1.2] - 2026-02-14

### Fixed

- `rules/` and `schemas/` now install into `site-packages/` correctly — previously installed to the wrong location via `data-files`, causing all CLI commands to fail after `pip install`
- `python_gate` is now installed to `$PATH` via `script-files` — previously missing from the wheel entirely
- `python_gate` no longer hardcodes `/usr/bin/python3` — dynamically discovers `python3` via `command -v`, fixing macOS, pyenv, nix, and container environments
- `gatehouse init --schema` now exits non-zero when the schema is not found — previously exited 0
- `gatehouse test-rule` now exits non-zero when the rule or file is not found — previously exited 0
- `gatehouse list-rules --schema` no longer crashes with `FileNotFoundError` — validates path before loading
- `gatehouse disable-rule` now exits non-zero on error — previously exited 0
- Docker usage instructions in README now work as documented

### Changed

- `$GATE_HOME` is no longer required — the engine, `python_gate`, and CLI all auto-discover their own location via file path resolution; `$GATE_HOME` is now an optional override for custom rule directories
- `python_gate` self-discovers its location via `readlink -f` with fallbacks — works whether symlinked, aliased, or installed to PATH
- `gate_engine.py` defaults to `Path(__file__).resolve().parent` instead of `~/.python_gate`
- `gatehouse activate` prints only `GATEHOUSE_MODE` + alias (no longer prints `export GATE_HOME=...`)
- `gatehouse status` now shows auto-discovery source, rules/schemas directory status, and detects `python_gate` on `$PATH`
- Simplified Quick Start in README — activation reduced from 3 env vars to 1 + alias
- Simplified Docker instructions — 3 lines instead of 5, no `GATE_HOME` needed
- Removed MCP references from publishing guide and release description

## [0.1.1] - 2026-02-14

### Added

- Three enforcement modes via `$GATEHOUSE_MODE` environment variable: `hard` (block execution), `soft` (print warnings), `off` (disabled, default)
- Activation banner printed to stderr on every Python invocation when mode is `hard` or `soft`
- `gatehouse status` command — shows current mode, GATE_HOME, `python_gate` location, and project schema
- `gatehouse activate [--mode hard|soft]` command — prints shell commands to enable enforcement
- `gatehouse deactivate` command — prints shell command to disable enforcement
- Docker usage documentation in README

### Changed

- `python_gate` now reads `$GATEHOUSE_MODE` instead of always enforcing — safe default is `off`
- `python_gate` passes through immediately with zero overhead when mode is `off` or unset

## [0.1.0] - 2026-02-14

### Added

- Core gate engine (`gate_engine.py`) with 8 built-in check types
- `python_gate` interceptor for OS-level Python enforcement
- Interactive CLI (`gatehouse`) for rule creation, project init, and rule management
- 12 built-in rules covering structure, documentation, and hardcoded values
- 4 schema presets: production, exploration, api, minimal
- Custom check support via inline Python expressions and plugin files
- YAML-based rule definitions (one file per rule)
- Schema manifests with inheritance and per-rule overrides
- Project-level configuration via `.gate_schema.yaml`
- JSONL telemetry logging for violation tracking
- Docker-based packaging environment for PyPI publishing
