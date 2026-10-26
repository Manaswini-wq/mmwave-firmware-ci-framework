"""Requirements-to-test traceability matrix for safety certification.

Loads requirements from a structured file, links them to test cases and
results, computes traceability coverage, and exports reports suitable for
ISO 26262 / IEC 61508 audits.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Requirement:
    """A single traceable requirement.

    Attributes:
        req_id: Unique requirement identifier, e.g. ``"SRS-RF-042"``.
        description: Human-readable description.
        priority: Priority / ASIL level.
        linked_tests: Mapping of test name to pass/fail/None.
    """

    req_id: str
    description: str = ""
    priority: str = ""
    linked_tests: Dict[str, Optional[bool]] = field(default_factory=dict)


class TraceabilityMatrix:
    """Bidirectional requirements-to-test traceability.

    Args:
        requirements_path: Path to a JSON file listing requirements.
    """

    def __init__(self, requirements_path: Optional[str] = None) -> None:
        self._requirements: Dict[str, Requirement] = {}
        self._orphan_tests: Set[str] = set()
        if requirements_path:
            self.load_requirements(requirements_path)

    # -- loading --------------------------------------------------------------

    def load_requirements(self, path: str) -> None:
        """Load requirements from a JSON file.

        Expected schema::

            [
                {"id": "SRS-RF-001", "description": "...", "priority": "ASIL-D"},
                ...
            ]

        Args:
            path: Path to the requirements JSON file.
        """
        req_path = Path(path)
        if not req_path.is_file():
            logger.error("Requirements file not found: %s", path)
            return

        with open(req_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        for entry in data:
            req = Requirement(
                req_id=entry["id"],
                description=entry.get("description", ""),
                priority=entry.get("priority", ""),
            )
            self._requirements[req.req_id] = req

        logger.info("Loaded %d requirements from %s", len(self._requirements), path)

    # -- linking --------------------------------------------------------------

    def link_test(self, requirement_id: str, test_name: str, test_result: Optional[bool] = None) -> None:
        """Link a test case (and optionally its result) to a requirement.

        Args:
            requirement_id: Requirement ID to link.
            test_name: Unique test name / identifier.
            test_result: ``True`` = pass, ``False`` = fail, ``None`` = not yet run.
        """
        if requirement_id not in self._requirements:
            logger.warning("Requirement %s not found; test %s recorded as orphan", requirement_id, test_name)
            self._orphan_tests.add(test_name)
            return
        self._requirements[requirement_id].linked_tests[test_name] = test_result
        logger.debug("Linked test '%s' (result=%s) to %s", test_name, test_result, requirement_id)

    # -- coverage queries -----------------------------------------------------

    def get_coverage(self) -> Tuple[int, int, float]:
        """Compute requirement coverage.

        A requirement is *covered* if it has at least one linked test.

        Returns:
            Tuple of (covered_count, total_count, percentage).
        """
        total = len(self._requirements)
        covered = sum(1 for r in self._requirements.values() if r.linked_tests)
        pct = (covered / total * 100.0) if total > 0 else 0.0
        logger.info("Traceability coverage: %d/%d (%.1f%%)", covered, total, pct)
        return covered, total, pct

    def get_uncovered_requirements(self) -> List[str]:
        """Return IDs of requirements with no linked tests."""
        return sorted(r.req_id for r in self._requirements.values() if not r.linked_tests)

    def get_failed_requirements(self) -> List[str]:
        """Return IDs of requirements where any linked test failed."""
        failed: List[str] = []
        for req in self._requirements.values():
            if any(result is False for result in req.linked_tests.values()):
                failed.append(req.req_id)
        return sorted(failed)

    # -- validation -----------------------------------------------------------

    def validate_bidirectional(self) -> List[str]:
        """Check for bidirectional-traceability issues.

        Returns:
            List of issue descriptions:
            - Requirements with no tests
            - Tests linked to no requirement (orphans)
        """
        issues: List[str] = []
        for req in self._requirements.values():
            if not req.linked_tests:
                issues.append(f"Requirement {req.req_id} has no linked tests")
        for test_name in sorted(self._orphan_tests):
            issues.append(f"Test '{test_name}' is not linked to any requirement")
        logger.info("Bidirectional validation: %d issue(s)", len(issues))
        return issues

    # -- reporting ------------------------------------------------------------

    def generate_matrix_report(self, output_path: str) -> None:
        """Generate a JSON traceability report.

        Args:
            output_path: Destination file path.
        """
        covered, total, pct = self.get_coverage()
        report: Dict[str, Any] = {
            "summary": {
                "total_requirements": total,
                "covered_requirements": covered,
                "coverage_percentage": round(pct, 2),
                "failed_requirements": self.get_failed_requirements(),
                "orphan_tests": sorted(self._orphan_tests),
            },
            "requirements": [
                {
                    "id": req.req_id,
                    "description": req.description,
                    "priority": req.priority,
                    "linked_tests": {
                        name: result for name, result in req.linked_tests.items()
                    },
                    "status": self._req_status(req),
                }
                for req in self._requirements.values()
            ],
        }

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        logger.info("Traceability matrix report written to %s", output_path)

    def export_csv(self, output_path: str) -> None:
        """Export the traceability matrix as CSV.

        Columns: ``Requirement ID``, ``Description``, ``Priority``,
        ``Test Name``, ``Result``.

        Args:
            output_path: Destination CSV path.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Requirement ID", "Description", "Priority", "Test Name", "Result"])
            for req in self._requirements.values():
                if req.linked_tests:
                    for test_name, result in req.linked_tests.items():
                        result_str = "PASS" if result is True else ("FAIL" if result is False else "NOT RUN")
                        writer.writerow([req.req_id, req.description, req.priority, test_name, result_str])
                else:
                    writer.writerow([req.req_id, req.description, req.priority, "", "NO TEST"])
        logger.info("Traceability CSV exported to %s", output_path)

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _req_status(req: Requirement) -> str:
        """Derive an overall status string for a requirement."""
        if not req.linked_tests:
            return "UNCOVERED"
        if any(r is False for r in req.linked_tests.values()):
            return "FAIL"
        if any(r is None for r in req.linked_tests.values()):
            return "PENDING"
        return "PASS"
