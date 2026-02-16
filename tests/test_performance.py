"""Performance tests for Gatehouse scan latency and throughput."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from gatehouse.engine import scan_file


FIXTURES_DIR = Path(__file__).parent / "fixtures"
PASSING_DIR = FIXTURES_DIR / "passing"

MAX_SCAN_MS = 2000


class TestScanPerformance:
    """Timing guard tests for scan_file."""

    def test_single_file_under_threshold(self, tmp_project: Path) -> None:
        """A single clean file scans in under MAX_SCAN_MS."""
        source = (PASSING_DIR / "clean_production.py").read_text(encoding="utf-8")
        schema_path = str(tmp_project / ".gate_schema.yaml")

        start = time.perf_counter()
        result = scan_file(source, "perf_test.py", schema_path, skip_scope=True)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < MAX_SCAN_MS, (
            f"scan_file took {elapsed_ms:.1f}ms (limit: {MAX_SCAN_MS}ms)"
        )
        assert result.scan_ms >= 0

    def test_repeated_scans_stable(self, tmp_project: Path) -> None:
        """Running scan_file 10 times does not degrade performance."""
        source = (PASSING_DIR / "clean_production.py").read_text(encoding="utf-8")
        schema_path = str(tmp_project / ".gate_schema.yaml")
        iterations = 10

        start = time.perf_counter()
        for _ in range(iterations):
            scan_file(source, "perf_test.py", schema_path, skip_scope=True)
        total_ms = (time.perf_counter() - start) * 1000

        per_scan = total_ms / iterations
        assert per_scan < MAX_SCAN_MS, (
            f"Average scan took {per_scan:.1f}ms over {iterations} runs"
        )
