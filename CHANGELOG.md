# Changelog

All notable changes to Gatehouse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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
