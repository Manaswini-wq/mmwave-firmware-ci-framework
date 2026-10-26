"""Code coverage analysis for ISO 26262 / IEC 61508 compliance.

Parses gcov, trace-based, and MC/DC coverage data, checks against ASIL-D
structural coverage requirements, and generates certification-grade reports.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CoverageMetrics:
    """Aggregated coverage metrics.

    Attributes:
        total: Total coverable items (lines, branches, conditions).
        covered: Number of items exercised.
        percentage: Coverage percentage (0-100).
        by_file: Per-source-file breakdown {filepath: (covered, total)}.
    """

    total: int = 0
    covered: int = 0
    percentage: float = 0.0
    by_file: Dict[str, Tuple[int, int]] = field(default_factory=dict)

    def update_percentage(self) -> None:
        """Recompute the percentage from total/covered."""
        self.percentage = (self.covered / self.total * 100.0) if self.total > 0 else 0.0


class CoverageAnalyzer:
    """Analyses and aggregates code coverage for safety certification.

    Supports gcov (line/branch), execution-trace (instruction), and
    MC/DC coverage data.  Provides ASIL-D compliance checks as required
    by ISO 26262 Part 6 Table 12.

    Args:
        elf_path: Path to the firmware ELF binary (used for symbol lookup).
        source_root: Root directory of the firmware source tree.
    """

    # ISO 26262 Part 6 Table 12 structural-coverage requirements by ASIL
    ASIL_COVERAGE_REQUIREMENTS: Dict[str, Dict[str, float]] = {
        "ASIL_A": {"line": 80.0},
        "ASIL_B": {"line": 80.0, "branch": 80.0},
        "ASIL_C": {"branch": 90.0},
        "ASIL_D": {"branch": 100.0, "mcdc": 100.0},
    }

    def __init__(self, elf_path: str, source_root: str) -> None:
        self.elf_path: str = elf_path
        self.source_root: str = source_root
        self._line_coverage: CoverageMetrics = CoverageMetrics()
        self._branch_coverage: CoverageMetrics = CoverageMetrics()
        self._mcdc_coverage: CoverageMetrics = CoverageMetrics()
        self._safety_critical_files: Set[str] = set()
        self._covered_functions: Set[str] = set()
        self._all_functions: Set[str] = set()
        logger.debug("CoverageAnalyzer initialised: elf=%s, source=%s", elf_path, source_root)

    # -- data loading ---------------------------------------------------------

    def load_trace_coverage(self, trace_data: Dict[str, Any]) -> None:
        """Load instruction-level coverage from an execution trace.

        Args:
            trace_data: Dictionary with ``'executed_addresses'`` (set of ints)
                        and ``'address_to_source'`` mapping.
        """
        executed: Set[int] = set(trace_data.get("executed_addresses", []))
        mapping: Dict[int, str] = trace_data.get("address_to_source", {})
        total = len(mapping)
        covered = len(executed & set(mapping.keys()))
        self._line_coverage.total += total
        self._line_coverage.covered += covered
        self._line_coverage.update_percentage()
        logger.info("Trace coverage loaded: %d/%d lines (%.1f%%)", covered, total, self._line_coverage.percentage)

    def load_gcov_coverage(self, gcov_dir: str) -> None:
        """Parse all ``.gcov`` files in a directory.

        Populates line and branch coverage metrics.

        Args:
            gcov_dir: Directory containing ``.gcov`` output files.
        """
        gcov_path = Path(gcov_dir)
        if not gcov_path.is_dir():
            logger.error("gcov directory not found: %s", gcov_dir)
            return

        line_total = 0
        line_covered = 0
        branch_total = 0
        branch_covered = 0

        for gcov_file in gcov_path.glob("*.gcov"):
            file_line_total = 0
            file_line_covered = 0
            source_name = gcov_file.stem  # approximate

            with open(gcov_file, "r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    raw_line = raw_line.rstrip()
                    # gcov format: "count:line_no:source_line"
                    match = re.match(r"^\s*(-|#+|[0-9]+):\s*(\d+):", raw_line)
                    if not match:
                        continue
                    count_str = match.group(1)
                    if count_str == "-":
                        continue  # non-executable line
                    file_line_total += 1
                    if count_str != "#####" and count_str != "0":
                        file_line_covered += 1

                    # Branch lines (gcov branch annotations)
                    if raw_line.startswith("branch"):
                        branch_total += 1
                        if "taken" in raw_line and "taken 0" not in raw_line:
                            branch_covered += 1

            line_total += file_line_total
            line_covered += file_line_covered
            self._line_coverage.by_file[source_name] = (file_line_covered, file_line_total)

        self._line_coverage.total += line_total
        self._line_coverage.covered += line_covered
        self._line_coverage.update_percentage()
        self._branch_coverage.total += branch_total
        self._branch_coverage.covered += branch_covered
        self._branch_coverage.update_percentage()
        logger.info("gcov loaded: line=%d/%d (%.1f%%), branch=%d/%d (%.1f%%)",
                     line_covered, line_total, self._line_coverage.percentage,
                     branch_covered, branch_total, self._branch_coverage.percentage)

    # -- accessors ------------------------------------------------------------

    def get_line_coverage(self) -> CoverageMetrics:
        """Return aggregated line coverage metrics."""
        return self._line_coverage

    def get_branch_coverage(self) -> CoverageMetrics:
        """Return aggregated branch coverage metrics."""
        return self._branch_coverage

    def get_mcdc_coverage(self) -> CoverageMetrics:
        """Return MC/DC coverage metrics."""
        return self._mcdc_coverage

    # -- ASIL compliance ------------------------------------------------------

    def check_asild_compliance(self, asil: str = "ASIL_D") -> Tuple[bool, List[str]]:
        """Check coverage against ASIL structural-coverage requirements.

        Args:
            asil: ASIL level string (``'ASIL_A'`` through ``'ASIL_D'``).

        Returns:
            Tuple of (compliant, list_of_gap_descriptions).
        """
        requirements = self.ASIL_COVERAGE_REQUIREMENTS.get(asil, {})
        gaps: List[str] = []

        if "line" in requirements:
            if self._line_coverage.percentage < requirements["line"]:
                gaps.append(
                    f"Line coverage {self._line_coverage.percentage:.1f}% "
                    f"< required {requirements['line']:.1f}%"
                )
        if "branch" in requirements:
            if self._branch_coverage.percentage < requirements["branch"]:
                gaps.append(
                    f"Branch coverage {self._branch_coverage.percentage:.1f}% "
                    f"< required {requirements['branch']:.1f}%"
                )
        if "mcdc" in requirements:
            if self._mcdc_coverage.percentage < requirements["mcdc"]:
                gaps.append(
                    f"MC/DC coverage {self._mcdc_coverage.percentage:.1f}% "
                    f"< required {requirements['mcdc']:.1f}%"
                )

        compliant = len(gaps) == 0
        logger.info("%s compliance: %s (%d gaps)", asil, "PASS" if compliant else "FAIL", len(gaps))
        return compliant, gaps

    # -- uncovered item queries -----------------------------------------------

    def get_uncovered_functions(self) -> List[str]:
        """Return the list of functions with zero coverage."""
        uncovered = sorted(self._all_functions - self._covered_functions)
        logger.debug("%d uncovered function(s)", len(uncovered))
        return uncovered

    def get_uncovered_safety_critical(self) -> List[str]:
        """Return uncovered functions that are marked safety-critical."""
        uncovered = self._safety_critical_files - {
            f for f, (c, t) in self._line_coverage.by_file.items() if c > 0
        }
        return sorted(uncovered)

    # -- reporting ------------------------------------------------------------

    def generate_coverage_report(self, output_path: str, format: str = "json") -> None:
        """Write a coverage report file.

        Args:
            output_path: Destination path.
            format: ``'json'`` or ``'text'``.
        """
        report: Dict[str, Any] = {
            "line_coverage": {
                "total": self._line_coverage.total,
                "covered": self._line_coverage.covered,
                "percentage": round(self._line_coverage.percentage, 2),
            },
            "branch_coverage": {
                "total": self._branch_coverage.total,
                "covered": self._branch_coverage.covered,
                "percentage": round(self._branch_coverage.percentage, 2),
            },
            "mcdc_coverage": {
                "total": self._mcdc_coverage.total,
                "covered": self._mcdc_coverage.covered,
                "percentage": round(self._mcdc_coverage.percentage, 2),
            },
            "uncovered_functions": self.get_uncovered_functions(),
        }

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2)
        else:
            with open(out, "w", encoding="utf-8") as fh:
                for section, data in report.items():
                    fh.write(f"=== {section} ===\n")
                    if isinstance(data, dict):
                        for k, v in data.items():
                            fh.write(f"  {k}: {v}\n")
                    elif isinstance(data, list):
                        for item in data:
                            fh.write(f"  - {item}\n")
                    fh.write("\n")
        logger.info("Coverage report written to %s", output_path)

    # -- merging --------------------------------------------------------------

    def merge_coverage(self, other: "CoverageAnalyzer") -> None:
        """Merge coverage data from another analyser instance.

        Args:
            other: Another :class:`CoverageAnalyzer` whose data will be
                   incorporated into *self*.
        """
        self._line_coverage.total += other._line_coverage.total
        self._line_coverage.covered += other._line_coverage.covered
        self._line_coverage.by_file.update(other._line_coverage.by_file)
        self._line_coverage.update_percentage()

        self._branch_coverage.total += other._branch_coverage.total
        self._branch_coverage.covered += other._branch_coverage.covered
        self._branch_coverage.by_file.update(other._branch_coverage.by_file)
        self._branch_coverage.update_percentage()

        self._mcdc_coverage.total += other._mcdc_coverage.total
        self._mcdc_coverage.covered += other._mcdc_coverage.covered
        self._mcdc_coverage.by_file.update(other._mcdc_coverage.by_file)
        self._mcdc_coverage.update_percentage()

        self._all_functions |= other._all_functions
        self._covered_functions |= other._covered_functions
        logger.info("Merged coverage data from %s", other.elf_path)
