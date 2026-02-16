"""logger — JSONL scan telemetry for violation tracking.

Each invocation of the engine appends a single JSON line to a log file inside
the configured log directory.  Every entry captures the scanned file path,
schema version, pass/reject status, violation details, a truncated SHA-256 hash
of the source, and timing information.  The log file name and formatting
constants are read from ``config/defaults.yaml``.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from typing import Any

from gatehouse.lib import config


def log_scan(
    log_dir: str,
    filepath: str,
    schema_name: str,
    schema_version: str,
    status: str,
    violations_data: list[dict[str, Any]],
    passed_rules: list[str],
    total_rules: int,
    source: str,
    scan_ms: int,
    iteration: int = 1,
) -> None:
    """Write a JSONL log entry for a scan result.

    Args:
        log_dir: Directory to write the log file in.
        filepath: Path to the scanned file.
        schema_name: Name of the schema used.
        schema_version: Version of the schema used.
        status: Scan status ('rejected' or 'passed').
        violations_data: List of violation summary dicts.
        passed_rules: List of rule IDs that passed.
        total_rules: Total number of active rules.
        source: The source code that was scanned.
        scan_ms: Scan duration in milliseconds.
        iteration: Iteration number for retry loops.
    """
    if not log_dir:
        return
    os.makedirs(log_dir, exist_ok=True)
    log_filename = config.get_str("filenames.scan_log")
    log_path = os.path.join(log_dir, log_filename)

    utc_src = config.get_str("formatting.utc_offset_source")
    utc_rep = config.get_str("formatting.utc_offset_replacement")
    hash_prefix = config.get_str("formatting.hash_prefix")
    hash_trunc = config.get_int("defaults.hash_truncation_length")
    separators = tuple(config.get_list("formatting.json_separators"))

    entry: dict[str, Any] = {
        "timestamp": (
            datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace(utc_src, utc_rep)
        ),
        "event": "scan",
        "file": filepath,
        "schema": schema_name,
        "schema_version": schema_version,
        "iteration": iteration,
        "status": status,
        "violations": violations_data,
        "passed_rules": passed_rules,
        "total_rules": total_rules,
        "code_length_lines": len(source.splitlines()),
        "code_hash": hash_prefix + hashlib.sha256(source.encode()).hexdigest()[:hash_trunc],
        "scan_ms": scan_ms,
    }

    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, separators=separators) + "\n")
