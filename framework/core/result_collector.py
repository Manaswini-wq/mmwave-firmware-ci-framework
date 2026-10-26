"""
Result Collector - Aggregate, export, and compare test results.

Supports JUnit XML, JSON, and CSV export formats for CI pipeline
integration and historical regression analysis.
"""
from __future__ import annotations

import csv
import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SuiteSummary:
    """High-level summary of a test suite execution."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    total_duration: float = 0.0
    coverage_pct: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# ResultCollector
# ---------------------------------------------------------------------------

class ResultCollector:
    """Collects individual test results and provides aggregation / export."""

    def __init__(self) -> None:
        self._results: list[Any] = []  # List of TestResult objects

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def add_result(self, test_result: Any) -> None:
        """Append a *TestResult* to the collection."""
        self._results.append(test_result)

    @property
    def results(self) -> list[Any]:
        return list(self._results)

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        """Return a summary dict with pass/fail/skip/error counts."""
        summary = SuiteSummary()
        for r in self._results:
            summary.total += 1
            summary.total_duration += getattr(r, "duration", 0.0)
            status = getattr(r, "status", "error")
            if status == "pass":
                summary.passed += 1
            elif status == "fail":
                summary.failed += 1
            elif status == "skip":
                summary.skipped += 1
            else:
                summary.errors += 1
        return asdict(summary)

    def get_failures(self) -> list[Any]:
        """Return only the failed test results."""
        return [r for r in self._results if getattr(r, "status", "") == "fail"]

    def get_errors(self) -> list[Any]:
        """Return only the errored test results."""
        return [r for r in self._results if getattr(r, "status", "") == "error"]

    # ------------------------------------------------------------------
    # JUnit XML export
    # ------------------------------------------------------------------

    def to_junit_xml(self, output_path: str | Path) -> Path:
        """Export results as a JUnit-compatible XML file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        summary = self.get_summary()

        testsuite = ET.Element(
            "testsuite",
            name="mmwave-firmware-tests",
            tests=str(summary["total"]),
            failures=str(summary["failed"]),
            errors=str(summary["errors"]),
            skipped=str(summary["skipped"]),
            time=f"{summary['total_duration']:.3f}",
            timestamp=summary["timestamp"],
        )

        for r in self._results:
            tc = ET.SubElement(
                testsuite,
                "testcase",
                name=getattr(r, "name", "unknown"),
                time=f"{getattr(r, 'duration', 0.0):.3f}",
            )
            status = getattr(r, "status", "error")
            message = getattr(r, "message", "")
            logs = getattr(r, "logs", "")

            if status == "fail":
                fail_el = ET.SubElement(tc, "failure", message=message)
                fail_el.text = logs
            elif status == "error":
                err_el = ET.SubElement(tc, "error", message=message)
                err_el.text = logs
            elif status == "skip":
                ET.SubElement(tc, "skipped", message=message)

            if logs:
                sysout = ET.SubElement(tc, "system-out")
                sysout.text = logs

        tree = ET.ElementTree(testsuite)
        ET.indent(tree, space="  ")
        tree.write(output_path, encoding="unicode", xml_declaration=True)
        logger.info("JUnit XML written to %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # JSON export
    # ------------------------------------------------------------------

    def to_json(self, output_path: str | Path) -> Path:
        """Export results as a JSON file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {
            "summary": self.get_summary(),
            "results": [],
        }
        for r in self._results:
            payload["results"].append(asdict(r) if hasattr(r, "__dataclass_fields__") else vars(r))

        output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        logger.info("JSON results written to %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------

    def to_csv(self, output_path: str | Path) -> Path:
        """Export results as a CSV file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = ["name", "status", "duration", "message", "retry_count"]
        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in self._results:
                row = asdict(r) if hasattr(r, "__dataclass_fields__") else vars(r)
                writer.writerow({k: row.get(k, "") for k in fieldnames})

        logger.info("CSV results written to %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Regression comparison
    # ------------------------------------------------------------------

    def compare_with(self, other: ResultCollector) -> dict[str, Any]:
        """Compare this run against *other* to detect regressions.

        Returns a dict with newly failing, newly passing, and stable tests.
        """
        current_map = {getattr(r, "name", ""): getattr(r, "status", "") for r in self._results}
        other_map = {getattr(r, "name", ""): getattr(r, "status", "") for r in other.results}

        all_names = set(current_map) | set(other_map)
        regressions: list[str] = []
        fixes: list[str] = []
        stable_pass: list[str] = []
        stable_fail: list[str] = []

        for name in sorted(all_names):
            prev = other_map.get(name, "new")
            curr = current_map.get(name, "removed")
            if prev == "pass" and curr in ("fail", "error"):
                regressions.append(name)
            elif prev in ("fail", "error") and curr == "pass":
                fixes.append(name)
            elif curr == "pass":
                stable_pass.append(name)
            else:
                stable_fail.append(name)

        return {
            "regressions": regressions,
            "fixes": fixes,
            "stable_pass": stable_pass,
            "stable_fail": stable_fail,
        }
