# Changelog

All notable changes to Gatehouse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.1] - 2026-02-20

### Added

- **Automated publish workflow** (`.github/workflows/publish.yml`) — tag-triggered pipeline that builds sdist + wheel, publishes to TestPyPI, then to production PyPI after manual approval, and creates a GitHub Release with changelog body and downloadable assets
- **OIDC trusted publishing** — keyless authentication to both PyPI and TestPyPI via GitHub's OpenID Connect identity tokens; no API tokens or secrets required
- **GitHub Release automation** — extracts the relevant section from `CHANGELOG.md` and attaches built distributions as release assets

## [0.3.0] - 2026-02-16

### Added

- **Modular library architecture** — decomposed the monolithic `gate_engine.py` (845 lines) into 10 focused modules under `lib/`:
  - `lib/analyzer.py` — `SourceAnalyzer` class: single CST parse + metadata resolution for all rules
  - `lib/checks.py` — check-type dispatch and implementations (`run_check()` + 8 check functions)
  - `lib/config.py` — lazy-loaded, typed accessors for `config/defaults.yaml`
  - `lib/formatter.py` — violation formatting for stderr, JSON, and traceback output
  - `lib/logger.py` — JSONL scan telemetry logging
  - `lib/rules.py` — rule/schema loading with inheritance resolution
  - `lib/scope.py` — file scope checking and per-path schema overrides
  - `lib/theme.py` — ANSI colour theme loading from `cli/theme.yaml`
  - `lib/yaml_loader.py` — unified YAML loading utility
  - `lib/models.py` — frozen dataclasses (`RuleEntry`, `ScopeConfig`, `GatehouseConfig`) replacing raw dict access
- **`engine.py`** — thin orchestrator that composes the `lib/` modules; the new primary entry point for programmatic usage
- **`auto.py`** — import-hook enforcement layer via `sys.meta_path` MetaPathFinder; intercepts Python imports and validates against the schema before any module loads, covering pytest, Jupyter, Celery, subprocess, and `python -m` execution paths
- **`exceptions.py`** — dedicated exception module with `GatehouseViolationError(ImportError)`, `GatehouseParseError(Exception)`, and `PluginError(Exception)`
- **`config/defaults.yaml`** — all string literals, messages, labels, severities, modes, env var names, directory names, and filenames externalised to YAML; zero hardcoded values remain in Python code
- **`cli/main.py`** — CLI entry point with argument parsing and command dispatch
- **`cli/commands.py`** — CLI command handlers for all subcommands
- **`cli/prompts.py`** — interactive terminal input helpers for the rule builder
- **`cli/wizard.py`** — interactive rule creation wizard (extracted from `new-rule` command)
- **Stable public API** — `__init__.py` exports `scan_file`, `ScanResult`, `Violation`, `GatehouseViolationError`, `PluginError` with semver-protected guarantees and a deprecation policy
- **`validate_project_config()`** — structural validation for `.gate_schema.yaml` files with human-readable error messages
- **Comprehensive test suite** — 16 test modules covering every library module, the engine, import hook, CLI, exceptions, formatter, theme, models, edge cases, fuzz inputs, and performance:
  - `conftest.py` with shared fixtures (gate_home, tmp_project, passing/failing source)
  - `tests/fixtures/` with passing, failing, and edge-case Python files
- **GitHub Actions CI** — matrix testing across Python 3.9–3.13, import verification lint step
- **Anti-double-scan coordination** — `python_gate` sets `GATEHOUSE_OUTER_VERDICT` env var so `auto.py`'s import hook skips files already scanned by the outer shim

### Changed

- **CLI entry point** moved from `gatehouse.cli.gatehouse_cli:main` to `gatehouse.cli.main:main`
- **`_paths.py`** reads all directory and filename constants from `config/defaults.yaml` via lazy accessor instead of hardcoding them
- **`python_gate`** now references `gatehouse.engine` instead of `gatehouse.gate_engine`; uses `GATEHOUSE_OUTER_VERDICT` for hook coordination
- **`run_check` signature** changed from `(rule_obj, analyzer)` to `(rule_obj, analyzer, gate_home)` to support plugin resolution without global state
- **`pyproject.toml`** adds `dev` optional dependencies (`pytest>=7.0`, `pytest-cov>=4.0`), `[tool.pytest.ini_options]` configuration, and `config/*.yaml` to package data

### Deprecated

- **`gatehouse.gate_engine`** — now a 20-line shim that emits `DeprecationWarning` and delegates to `gatehouse.engine`. Will be removed in v0.4.0.

### Removed

- **`gatehouse_cli.py`** (795 lines) — replaced by `cli/main.py`, `cli/commands.py`, `cli/prompts.py`, `cli/wizard.py`
- **All logic from `gate_engine.py`** (845 → 20 lines) — replaced by `engine.py` and `lib/` modules
- **Inline YAML loader fallback** — the `try: import yaml / except: simple_parser` pattern in `gate_engine.py` is gone; `pyyaml>=6.0` is now a hard dependency

## [0.2.2] - 2026-02-15

### Fixed

- **`python_gate` shim failed to enforce rules after src-layout restructuring** — the shim invoked `gate_engine.py` as a direct file (`python /path/to/gate_engine.py`), but after the v0.2.1 restructuring `gate_engine.py` uses package imports (`from gatehouse._paths import ...`) that require proper package context. Running as a file sets `__package__ = None`, causing imports to fail or resolve incorrectly depending on `sys.path` configuration. Fixed by invoking via `python -m gatehouse.gate_engine`, which sets `__package__ = "gatehouse"` and guarantees all package imports resolve correctly.

## [0.2.1] - 2026-02-15

### Added

- `src/gatehouse/_paths.py` — single module for all path resolution; the only file in the codebase that uses `__file__`
- `src/gatehouse/__init__.py` — defines `__version__` as the single source of truth for the package version
- `tests/` directory with `__init__.py`

### Changed

- **Restructured to standard Python `src/` layout** — all source code now lives under `src/gatehouse/`
- All path resolution centralised in `_paths.py` — `gate_engine.py`, `gatehouse_cli.py`, `python_gate`, and `examples/` no longer compute their own paths
- `gate_engine.py` reads version from `gatehouse.__version__` instead of parsing `pyproject.toml` at runtime
- `python_gate` discovers the installed package via `import gatehouse.gate_engine` (was `import gate_engine`)
- `python_gate` adds `src/` to `PYTHONPATH` automatically in dev/source checkouts
- `pyproject.toml` updated for `src-layout` packaging (`packages.find.where = ["src"]`)
- `MANIFEST.in` paths updated for new layout
- CLI `test-rule` invokes engine via `python -m gatehouse.gate_engine` instead of direct file path
- Standalone usage example uses `-m gatehouse.gate_engine` instead of direct file path
- README file map updated to reflect new structure

### Removed

- `_read_version()` function from `gate_engine.py` — version now comes from `gatehouse.__version__`
- All `__file__`-based path computation from `gate_engine.py`, `gatehouse_cli.py`, and `standalone_usage.py`

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
