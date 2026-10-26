"""Calibration result validation for mmWave radar sensors.

Validates TX power, RX gain, phase mismatch, LO leakage, and noise figure
against specification limits and generates structured calibration reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CalibrationResult:
    """Result of a single calibration check.

    Attributes:
        parameter: Name of the calibration parameter.
        passed: Whether the check passed.
        measured: Measured value.
        expected: Expected (nominal) value.
        tolerance: Allowed tolerance.
        delta: Absolute deviation from expected.
        unit: Engineering unit string.
    """

    parameter: str
    passed: bool
    measured: float
    expected: float
    tolerance: float
    delta: float
    unit: str = ""


class CalibrationValidator:
    """Validates radar calibration results against specification limits.

    Args:
        spec_limits: Dictionary of parameter names to ``(min, max)`` tuples
                     defining acceptable value ranges.
    """

    def __init__(self, spec_limits: Dict[str, Tuple[float, float]]) -> None:
        self.spec_limits: Dict[str, Tuple[float, float]] = spec_limits
        self._results: List[CalibrationResult] = []
        logger.debug("CalibrationValidator initialised with %d spec limits", len(spec_limits))

    # -- individual validations -----------------------------------------------

    def validate_tx_power(
        self,
        measured_power: float,
        expected: float,
        tolerance: float,
    ) -> Tuple[bool, float]:
        """Validate transmitter output power.

        Args:
            measured_power: Measured TX power in dBm.
            expected: Expected TX power in dBm.
            tolerance: Allowed deviation in dB.

        Returns:
            Tuple of (pass_flag, delta_dB).
        """
        delta = abs(measured_power - expected)
        passed = delta <= tolerance
        self._results.append(CalibrationResult(
            parameter="tx_power", passed=passed,
            measured=measured_power, expected=expected,
            tolerance=tolerance, delta=delta, unit="dBm",
        ))
        logger.info(
            "TX power: measured=%.2f dBm, expected=%.2f dBm, delta=%.2f dB -> %s",
            measured_power, expected, delta, "PASS" if passed else "FAIL",
        )
        return passed, delta

    def validate_rx_gain(
        self,
        gains_db: List[float],
        expected: float,
    ) -> Tuple[bool, List[Tuple[int, float]]]:
        """Validate per-channel RX gain.

        Args:
            gains_db: Measured gain for each RX channel in dB.
            expected: Expected gain in dB.

        Returns:
            Tuple of (all_pass, list_of_(channel_index, delta) for mismatches).
        """
        spec = self.spec_limits.get("rx_gain", (expected - 3.0, expected + 3.0))
        mismatches: List[Tuple[int, float]] = []
        for idx, gain in enumerate(gains_db):
            if not (spec[0] <= gain <= spec[1]):
                mismatches.append((idx, gain - expected))
        all_pass = len(mismatches) == 0
        for idx, gain in enumerate(gains_db):
            self._results.append(CalibrationResult(
                parameter=f"rx_gain_ch{idx}", passed=(spec[0] <= gain <= spec[1]),
                measured=gain, expected=expected,
                tolerance=(spec[1] - spec[0]) / 2, delta=abs(gain - expected), unit="dB",
            ))
        logger.info("RX gain: %d channels, %d mismatches -> %s",
                     len(gains_db), len(mismatches), "PASS" if all_pass else "FAIL")
        return all_pass, mismatches

    def validate_phase_mismatch(
        self,
        phases_deg: List[float],
        tolerance: float,
    ) -> Tuple[bool, float]:
        """Validate inter-channel phase mismatch.

        Args:
            phases_deg: Phase measurements per channel in degrees.
            tolerance: Maximum allowable phase deviation in degrees.

        Returns:
            Tuple of (pass_flag, max_phase_error_deg).
        """
        if not phases_deg:
            return True, 0.0
        mean_phase = sum(phases_deg) / len(phases_deg)
        deviations = [abs(p - mean_phase) for p in phases_deg]
        max_error = max(deviations)
        passed = max_error <= tolerance
        self._results.append(CalibrationResult(
            parameter="phase_mismatch", passed=passed,
            measured=max_error, expected=0.0,
            tolerance=tolerance, delta=max_error, unit="deg",
        ))
        logger.info("Phase mismatch: max_error=%.2f deg, tolerance=%.2f deg -> %s",
                     max_error, tolerance, "PASS" if passed else "FAIL")
        return passed, max_error

    def validate_lo_leakage(
        self,
        leakage_dbm: float,
        limit: float,
    ) -> Tuple[bool, float]:
        """Validate LO leakage level.

        Args:
            leakage_dbm: Measured LO leakage in dBm.
            limit: Maximum acceptable leakage in dBm.

        Returns:
            Tuple of (pass_flag, margin_dB).  Margin is positive when passing.
        """
        margin = limit - leakage_dbm
        passed = leakage_dbm <= limit
        self._results.append(CalibrationResult(
            parameter="lo_leakage", passed=passed,
            measured=leakage_dbm, expected=limit,
            tolerance=0.0, delta=abs(margin), unit="dBm",
        ))
        logger.info("LO leakage: %.2f dBm (limit %.2f dBm), margin=%.2f dB -> %s",
                     leakage_dbm, limit, margin, "PASS" if passed else "FAIL")
        return passed, margin

    def validate_noise_figure(
        self,
        nf_db: float,
        limit: float,
    ) -> Tuple[bool, float]:
        """Validate receiver noise figure.

        Args:
            nf_db: Measured noise figure in dB.
            limit: Maximum acceptable noise figure in dB.

        Returns:
            Tuple of (pass_flag, margin_dB).
        """
        margin = limit - nf_db
        passed = nf_db <= limit
        self._results.append(CalibrationResult(
            parameter="noise_figure", passed=passed,
            measured=nf_db, expected=limit,
            tolerance=0.0, delta=abs(margin), unit="dB",
        ))
        logger.info("Noise figure: %.2f dB (limit %.2f dB), margin=%.2f dB -> %s",
                     nf_db, limit, margin, "PASS" if passed else "FAIL")
        return passed, margin

    # -- reporting ------------------------------------------------------------

    def generate_cal_report(self, results: Optional[List[CalibrationResult]] = None) -> Dict[str, Any]:
        """Generate a structured calibration report.

        Args:
            results: Optional explicit result list; defaults to internally
                     accumulated results.

        Returns:
            Dictionary with ``'summary'``, ``'total'``, ``'passed'``,
            ``'failed'``, and per-parameter ``'details'``.
        """
        entries = results if results is not None else self._results
        passed_count = sum(1 for r in entries if r.passed)
        failed_count = len(entries) - passed_count
        report: Dict[str, Any] = {
            "summary": "PASS" if failed_count == 0 else "FAIL",
            "total": len(entries),
            "passed": passed_count,
            "failed": failed_count,
            "details": [
                {
                    "parameter": r.parameter,
                    "passed": r.passed,
                    "measured": r.measured,
                    "expected": r.expected,
                    "tolerance": r.tolerance,
                    "delta": r.delta,
                    "unit": r.unit,
                }
                for r in entries
            ],
        }
        logger.info("Calibration report: %d/%d passed", passed_count, len(entries))
        return report
