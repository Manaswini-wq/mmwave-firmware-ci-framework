"""Tests for safety monitoring subsystem.

Validates watchdog, ECC, and safe-state transition logic required
for ISO 26262 ASIL-D and IEC 61508 SIL-3 compliance.
"""
from __future__ import annotations

import pytest

from framework.safety.monitor import SafetyMonitor, SafeState
from framework.safety.ecc import ECCEngine
from framework.safety.diagnostics import DiagnosticCoverage


# ---------------------------------------------------------------------------
# Watchdog tests
# ---------------------------------------------------------------------------

class TestWatchdogTimeout:
    """Watchdog must detect CPU hangs within the configured timeout."""

    def test_watchdog_timeout_detection(self) -> None:
        """Monitor shall flag a timeout when the watchdog is not serviced."""
        monitor = SafetyMonitor(watchdog_timeout_ms=50)
        monitor.start()
        # Simulate elapsed time without servicing
        monitor.advance_time_ms(60)
        assert monitor.watchdog_expired is True

    def test_watchdog_serviced_no_timeout(self) -> None:
        """Servicing the watchdog within the window prevents timeout."""
        monitor = SafetyMonitor(watchdog_timeout_ms=50)
        monitor.start()
        monitor.advance_time_ms(40)
        monitor.service_watchdog()
        monitor.advance_time_ms(40)
        assert monitor.watchdog_expired is False


# ---------------------------------------------------------------------------
# ECC tests
# ---------------------------------------------------------------------------

class TestECCHandling:
    """ECC engine must correct single-bit and detect double-bit errors."""

    def test_ecc_single_bit_correction(self) -> None:
        """A single-bit error in SRAM must be silently corrected."""
        engine = ECCEngine(word_size=32)
        original = 0xDEADBEEF
        encoded = engine.encode(original)
        # Inject single-bit error
        corrupted = encoded ^ (1 << 5)
        corrected, error_type = engine.decode(corrupted)
        assert corrected == original
        assert error_type == "single_bit"

    def test_ecc_double_bit_detection(self) -> None:
        """A double-bit error must be detected (uncorrectable)."""
        engine = ECCEngine(word_size=32)
        original = 0xCAFEBABE
        encoded = engine.encode(original)
        # Inject two-bit error
        corrupted = encoded ^ (1 << 5) ^ (1 << 12)
        _, error_type = engine.decode(corrupted)
        assert error_type == "double_bit"

    def test_ecc_no_error(self) -> None:
        """Clean data must decode without error flags."""
        engine = ECCEngine(word_size=32)
        original = 0x12345678
        encoded = engine.encode(original)
        decoded, error_type = engine.decode(encoded)
        assert decoded == original
        assert error_type == "none"


# ---------------------------------------------------------------------------
# Safe state transition tests
# ---------------------------------------------------------------------------

class TestSafeStateTransition:
    """System must enter a defined safe state on critical faults."""

    def test_safe_state_transition(self) -> None:
        """Injecting a critical fault shall move the system to SAFE."""
        monitor = SafetyMonitor(watchdog_timeout_ms=50)
        monitor.start()
        monitor.inject_fault("lockstep_mismatch")
        assert monitor.current_state == SafeState.SAFE

    def test_safe_state_outputs_disabled(self) -> None:
        """In SAFE state all radar TX outputs must be disabled."""
        monitor = SafetyMonitor(watchdog_timeout_ms=50)
        monitor.start()
        monitor.inject_fault("ecc_double_bit")
        assert monitor.tx_enabled is False


# ---------------------------------------------------------------------------
# Diagnostic coverage calculation tests
# ---------------------------------------------------------------------------

class TestDiagnosticCoverage:
    """Diagnostic coverage metrics for safety analysis."""

    def test_diagnostic_coverage_calculation(self) -> None:
        """DC must be computed as detected_faults / total_faults."""
        dc = DiagnosticCoverage(total_faults=1000, detected_faults=990)
        assert dc.percentage == pytest.approx(99.0)

    def test_spfm_threshold(self) -> None:
        """Single-point fault metric must exceed ASIL-D threshold (99%)."""
        dc = DiagnosticCoverage(total_faults=10000, detected_faults=9910)
        assert dc.percentage >= 99.0

    def test_lfm_threshold(self) -> None:
        """Latent fault metric must exceed ASIL-D threshold (90%)."""
        dc = DiagnosticCoverage(total_faults=5000, detected_faults=4600)
        assert dc.percentage >= 90.0
