"""TUV audit evidence package generator for ISO 26262 / IEC 61508.

Assembles coverage reports, traceability matrices, test results, and
fault-injection evidence into a single auditable ZIP package with
integrity checksums, following the evidence structure required by
ISO 26262 Part 6 and IEC 61508 Part 3.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.safety.coverage_analyzer import CoverageAnalyzer
from framework.safety.traceability_matrix import TraceabilityMatrix

logger = logging.getLogger(__name__)


class EvidenceGenerator:
    """Generates a certification evidence package for safety audits.

    Usage::

        gen = EvidenceGenerator("/output/evidence")
        gen.add_coverage_report(cov_analyzer)
        gen.add_traceability_matrix(matrix)
        gen.add_test_results(result_collector)
        gen.add_fault_injection_results(fi_results)
        gen.generate_evidence_package()

    Args:
        output_dir: Directory where evidence artefacts will be written.
    """

    # ISO 26262 Part 6 evidence items
    REQUIRED_ARTIFACTS = [
        "coverage_report.json",
        "traceability_matrix.json",
        "test_results.json",
        "summary_report.json",
        "checksum_manifest.json",
    ]

    def __init__(self, output_dir: str) -> None:
        self.output_dir: Path = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts: Dict[str, Path] = {}
        self._coverage_analyzer: Optional[CoverageAnalyzer] = None
        self._traceability_matrix: Optional[TraceabilityMatrix] = None
        self._test_results: Optional[Dict[str, Any]] = None
        self._fi_results: Optional[Dict[str, Any]] = None
        logger.debug("EvidenceGenerator initialised: output_dir=%s", output_dir)

    # -- adding evidence components -------------------------------------------

    def add_coverage_report(self, coverage_analyzer: CoverageAnalyzer) -> None:
        """Add code-coverage analysis results.

        Args:
            coverage_analyzer: A populated :class:`CoverageAnalyzer`.
        """
        self._coverage_analyzer = coverage_analyzer
        report_path = self.output_dir / "coverage_report.json"
        coverage_analyzer.generate_coverage_report(str(report_path), format="json")
        self._artifacts["coverage_report.json"] = report_path
        logger.info("Coverage report added")

    def add_traceability_matrix(self, matrix: TraceabilityMatrix) -> None:
        """Add requirements traceability matrix.

        Args:
            matrix: A populated :class:`TraceabilityMatrix`.
        """
        self._traceability_matrix = matrix
        report_path = self.output_dir / "traceability_matrix.json"
        matrix.generate_matrix_report(str(report_path))
        self._artifacts["traceability_matrix.json"] = report_path
        logger.info("Traceability matrix added")

    def add_test_results(self, result_collector: Dict[str, Any]) -> None:
        """Add test execution results.

        Args:
            result_collector: Dictionary of test results (name -> outcome).
        """
        self._test_results = result_collector
        report_path = self.output_dir / "test_results.json"
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(result_collector, fh, indent=2)
        self._artifacts["test_results.json"] = report_path
        logger.info("Test results added (%d entries)", len(result_collector))

    def add_fault_injection_results(self, fi_results: Dict[str, Any]) -> None:
        """Add fault-injection campaign results.

        Args:
            fi_results: FMEDA / fault-injection results dictionary.
        """
        self._fi_results = fi_results
        report_path = self.output_dir / "fault_injection_results.json"
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(fi_results, fh, indent=2)
        self._artifacts["fault_injection_results.json"] = report_path
        logger.info("Fault injection results added")

    # -- package generation ---------------------------------------------------

    def generate_evidence_package(self) -> str:
        """Generate the complete evidence package.

        Creates the summary report, checksum manifest, validates
        completeness, and packages everything into a ZIP archive.

        Returns:
            Path to the generated ZIP file.
        """
        self._generate_summary_report()
        self._generate_checksum_manifest()

        missing = self._validate_completeness()
        if missing:
            logger.warning("Evidence package incomplete. Missing: %s", missing)

        zip_path = self.output_dir / "evidence_package.zip"
        self._package_artifacts(str(zip_path))
        logger.info("Evidence package generated: %s", zip_path)
        return str(zip_path)

    # -- internal helpers -----------------------------------------------------

    def _generate_summary_report(self) -> None:
        """Create the top-level summary report."""
        summary: Dict[str, Any] = {
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "standard": "ISO 26262 Part 6 / IEC 61508 Part 3",
            "coverage": {},
            "traceability": {},
            "test_results": {},
            "fault_injection": {},
        }

        if self._coverage_analyzer is not None:
            lc = self._coverage_analyzer.get_line_coverage()
            bc = self._coverage_analyzer.get_branch_coverage()
            summary["coverage"] = {
                "line_percentage": round(lc.percentage, 2),
                "branch_percentage": round(bc.percentage, 2),
            }

        if self._traceability_matrix is not None:
            covered, total, pct = self._traceability_matrix.get_coverage()
            summary["traceability"] = {
                "covered_requirements": covered,
                "total_requirements": total,
                "percentage": round(pct, 2),
            }

        if self._test_results is not None:
            total = len(self._test_results)
            passed = sum(1 for v in self._test_results.values() if v.get("status") == "PASS")
            summary["test_results"] = {"total": total, "passed": passed, "failed": total - passed}

        if self._fi_results is not None:
            summary["fault_injection"] = {
                "campaigns": len(self._fi_results.get("results", [])),
            }

        report_path = self.output_dir / "summary_report.json"
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        self._artifacts["summary_report.json"] = report_path
        logger.info("Summary report generated")

    def _package_artifacts(self, output_path: str) -> None:
        """Compress all artefacts into a ZIP archive.

        Args:
            output_path: Path for the output ZIP file.
        """
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, filepath in self._artifacts.items():
                if filepath.exists():
                    zf.write(filepath, arcname=name)
                    logger.debug("Packed %s", name)
        logger.info("Artifacts packaged into %s (%d files)", output_path, len(self._artifacts))

    def _validate_completeness(self) -> List[str]:
        """Check that all required artefacts are present.

        Returns:
            List of missing artefact names.
        """
        missing: List[str] = []
        for required in self.REQUIRED_ARTIFACTS:
            if required not in self._artifacts or not self._artifacts[required].exists():
                missing.append(required)
        if missing:
            logger.warning("Missing required artifacts: %s", missing)
        else:
            logger.info("All required artifacts present")
        return missing

    def _generate_checksum_manifest(self) -> None:
        """Compute SHA-256 checksums for every artefact."""
        manifest: Dict[str, str] = {}
        for name, filepath in self._artifacts.items():
            if filepath.exists():
                sha = hashlib.sha256(filepath.read_bytes()).hexdigest()
                manifest[name] = sha
        manifest_path = self.output_dir / "checksum_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        self._artifacts["checksum_manifest.json"] = manifest_path
        logger.info("Checksum manifest generated (%d entries)", len(manifest))
