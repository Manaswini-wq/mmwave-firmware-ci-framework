"""IEC 61508 SIL-3 requirement-mapped tests.

Each test is traced to a specific SIL-3 requirement for evidence
generation in the IEC 61508 safety lifecycle documentation.
"""
from __future__ import annotations

import time

import pytest


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.sil3, pytest.mark.hardware]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SFF_THRESHOLD_PCT = 99.0
DIAGNOSTIC_TEST_INTERVAL_MS = 100
PROOF_TEST_COVERAGE_PCT = 95.0


# ---------------------------------------------------------------------------
# REQ_SIL3_001 - Safe Failure Fraction >= 99%
# ---------------------------------------------------------------------------

class TestReqSIL3001:
    """REQ_SIL3_001: Safe Failure Fraction shall be >= 99%."""

    def test_REQ_SIL3_001_sff_above_99_percent(
        self, uart_monitor
    ) -> None:
        """REQ_SIL3_001 — Runtime SFF computed by the diagnostic manager
        must exceed the 99% threshold for SIL-3 compliance.

        Requirement ID: REQ_SIL3_001
        SIL: 3
        """
        uart_monitor.send_command("diag sff\r\n")
        result = uart_monitor.read_until(pattern="SFF=", timeout_s=10.0)
        assert result is not None, "SFF result not received from DUT"

        sff = float(result.split("SFF=")[1].split("%")[0])
        assert sff >= SFF_THRESHOLD_PCT, (
            f"SFF {sff:.1f}% is below SIL-3 threshold {SFF_THRESHOLD_PCT}%"
        )


# ---------------------------------------------------------------------------
# REQ_SIL3_002 - Diagnostic test interval
# ---------------------------------------------------------------------------

class TestReqSIL3002:
    """REQ_SIL3_002: Diagnostic tests shall execute at <= 100 ms intervals."""

    def test_REQ_SIL3_002_diagnostic_test_interval(
        self, uart_monitor
    ) -> None:
        """REQ_SIL3_002 — The interval between consecutive diagnostic test
        completions must not exceed the configured limit.

        Requirement ID: REQ_SIL3_002
        SIL: 3
        """
        timestamps: list[float] = []
        for _ in range(5):
            line = uart_monitor.read_until(pattern="DIAG_COMPLETE", timeout_s=1.0)
            assert line is not None, "Diagnostic completion message not received"
            timestamps.append(time.monotonic())

        for i in range(1, len(timestamps)):
            interval_ms = (timestamps[i] - timestamps[i - 1]) * 1000.0
            assert interval_ms <= DIAGNOSTIC_TEST_INTERVAL_MS * 1.1, (
                f"Diagnostic interval {interval_ms:.1f} ms exceeds "
                f"{DIAGNOSTIC_TEST_INTERVAL_MS} ms limit"
            )


# ---------------------------------------------------------------------------
# REQ_SIL3_003 - Proof test coverage
# ---------------------------------------------------------------------------

class TestReqSIL3003:
    """REQ_SIL3_003: Proof test coverage shall be >= 95%."""

    def test_REQ_SIL3_003_proof_test_coverage(
        self, uart_monitor
    ) -> None:
        """REQ_SIL3_003 — Running the full proof-test suite must achieve
        at least 95% fault coverage.

        Requirement ID: REQ_SIL3_003
        SIL: 3
        """
        uart_monitor.send_command("proof_test run_all\r\n")
        result = uart_monitor.read_until(pattern="COVERAGE=", timeout_s=30.0)
        assert result is not None, "Proof test coverage result not received"

        coverage = float(result.split("COVERAGE=")[1].split("%")[0])
        assert coverage >= PROOF_TEST_COVERAGE_PCT, (
            f"Proof test coverage {coverage:.1f}% below {PROOF_TEST_COVERAGE_PCT}% threshold"
        )


# ---------------------------------------------------------------------------
# REQ_SIL3_004 - Common cause failure mitigation
# ---------------------------------------------------------------------------

class TestReqSIL3004:
    """REQ_SIL3_004: Common-cause failures shall be mitigated by diversity."""

    def test_REQ_SIL3_004_common_cause_mitigation(
        self, jtag_interface, uart_monitor
    ) -> None:
        """REQ_SIL3_004 — Injecting a fault into both lockstep cores
        simultaneously must still be detected by the independent
        safety monitor (diverse redundancy).

        Requirement ID: REQ_SIL3_004
        SIL: 3
        """
        # Corrupt the same register on both cores
        jtag_interface.write_register("R0", 0xDEAD0001, core=0)
        jtag_interface.write_register("R0", 0xDEAD0002, core=1)
        time.sleep(0.2)

        # The independent safety island must still detect the anomaly
        alert = uart_monitor.read_until(pattern="SAFETY_ISLAND_ALERT", timeout_s=2.0)
        assert alert is not None, (
            "Safety island did not detect common-cause fault — "
            "diverse redundancy may be insufficient"
        )
