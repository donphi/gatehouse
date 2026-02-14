# Changelog

All notable changes to Gatehouse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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
