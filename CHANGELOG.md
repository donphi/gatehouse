# Changelog

All notable changes to Gatehouse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.2] - 2026-02-14

### Fixed

- `rules/` and `schemas/` now install into `site-packages/` correctly — previously installed to the wrong location via `data-files`, causing all CLI commands to fail after `pip install`
- `python_gate` shim is now installed to `$PATH` via `script-files` — previously missing from the wheel entirely
- `python_gate` no longer hardcodes `/usr/bin/python3` — dynamically discovers `python3` via `command -v`, fixing macOS, pyenv, nix, and container environments
- `gatehouse init --schema` now exits non-zero when the schema is not found — previously exited 0
- `gatehouse test-rule` now exits non-zero when the rule or file is not found — previously exited 0
- `gatehouse list-rules --schema` no longer crashes with `FileNotFoundError` — validates path before loading
- `gatehouse disable-rule` now exits non-zero on error — previously exited 0
- Docker usage instructions in README now work as documented

### Changed

- `$GATE_HOME` is no longer required — the engine, shim, and CLI all auto-discover their own location via file path resolution; `$GATE_HOME` is now an optional override for custom rule directories
- `python_gate` shim self-discovers its location via `readlink -f` with fallbacks — works whether symlinked, aliased, or installed to PATH
- `gate_engine.py` defaults to `Path(__file__).resolve().parent` instead of `~/.python_gate`
- `gatehouse activate` prints only `GATEHOUSE_MODE` + alias (no longer prints `export GATE_HOME=...`)
- `gatehouse status` now shows auto-discovery source, rules/schemas directory status, and detects shim on `$PATH`
- Simplified Quick Start in README — activation reduced from 3 env vars to 1 + alias
- Simplified Docker instructions — 3 lines instead of 5, no `GATE_HOME` needed
- Removed MCP references from publishing guide and release description

## [0.1.1] - 2026-02-14

### Added

- Three enforcement modes via `$GATEHOUSE_MODE` environment variable: `hard` (block execution), `soft` (print warnings), `off` (disabled, default)
- Activation banner printed to stderr on every Python invocation when mode is `hard` or `soft`
- `gatehouse status` command — shows current mode, GATE_HOME, shim location, and project schema
- `gatehouse activate [--mode hard|soft]` command — prints shell commands to enable enforcement
- `gatehouse deactivate` command — prints shell command to disable enforcement
- Docker usage documentation in README

### Changed

- `python_gate` shim now reads `$GATEHOUSE_MODE` instead of always enforcing — safe default is `off`
- Shim passes through immediately with zero overhead when mode is `off` or unset

## [0.1.0] - 2026-02-14

### Added

- Core gate engine (`gate_engine.py`) with 8 built-in check types
- Bash shim (`python_gate`) for OS-level Python interception
- Interactive CLI (`gatehouse`) for rule creation, project init, and rule management
- 12 built-in rules covering structure, documentation, and hardcoded values
- 4 schema presets: production, exploration, api, minimal
- Custom check support via inline Python expressions and plugin files
- YAML-based rule definitions (one file per rule)
- Schema manifests with inheritance and per-rule overrides
- Project-level configuration via `.gate_schema.yaml`
- JSONL telemetry logging for violation tracking
- Docker-based packaging environment for PyPI publishing
