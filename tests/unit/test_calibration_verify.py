"""Tests for calibration verification logic.

Ensures TX power, RX gain, phase error, and LO leakage measurements
are validated against datasheet tolerance limits.
"""
from __future__ import annotations

import pytest

from framework.radar.calibration import CalibrationVerifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def verifier() -> CalibrationVerifier:
    """Pre-configured calibration verifier with default limits."""
    return CalibrationVerifier(
        tx_power_nominal_dbm=12.0,
        tx_power_tolerance_db=1.5,
        rx_gain_mismatch_limit_db=1.0,
        phase_error_limit_deg=5.0,
        lo_leakage_limit_dbc=-35.0,
    )


# ---------------------------------------------------------------------------
# TX power tests
# ---------------------------------------------------------------------------

class TestTXPowerVerification:
    """TX output power must be within the allowed tolerance band."""

    @pytest.mark.calibration
    def test_tx_power_within_tolerance(self, verifier: CalibrationVerifier) -> None:
        """TX power of 11.8 dBm is within +/-1.5 dB of 12.0 dBm nominal."""
        result = verifier.check_tx_power(measured_dbm=11.8)
        assert result.passed is True
        assert result.deviation_db == pytest.approx(-0.2, abs=0.01)

    @pytest.mark.calibration
    def test_tx_power_out_of_tolerance(self, verifier: CalibrationVerifier) -> None:
        """TX power of 9.0 dBm exceeds the 1.5 dB tolerance and must fail."""
        result = verifier.check_tx_power(measured_dbm=9.0)
        assert result.passed is False


# ---------------------------------------------------------------------------
# RX gain mismatch tests
# ---------------------------------------------------------------------------

class TestRXGainMismatch:
    """RX channel gain mismatch must stay below the configured limit."""

    @pytest.mark.calibration
    def test_rx_gain_mismatch_detection(self, verifier: CalibrationVerifier) -> None:
        """Gain values differing by more than 1 dB must be flagged."""
        rx_gains = [30.0, 30.5, 29.8, 31.5]  # RX3 deviates > 1 dB from mean
        result = verifier.check_rx_gain_mismatch(rx_gains)
        assert result.passed is False
        assert result.max_mismatch_db > 1.0

    @pytest.mark.calibration
    def test_rx_gain_within_limit(self, verifier: CalibrationVerifier) -> None:
        """Tightly matched gains must pass."""
        rx_gains = [30.0, 30.1, 29.9, 30.2]
        result = verifier.check_rx_gain_mismatch(rx_gains)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Phase error tests
# ---------------------------------------------------------------------------

class TestPhaseError:
    """Inter-channel phase error must remain below the threshold."""

    @pytest.mark.calibration
    def test_phase_error_threshold(self, verifier: CalibrationVerifier) -> None:
        """Phase errors exceeding 5 deg must be flagged."""
        phase_offsets_deg = [0.0, 1.2, -2.1, 6.5]  # RX3 exceeds limit
        result = verifier.check_phase_error(phase_offsets_deg)
        assert result.passed is False
        assert result.max_error_deg == pytest.approx(6.5, abs=0.1)

    @pytest.mark.calibration
    def test_phase_error_within_limit(self, verifier: CalibrationVerifier) -> None:
        """Phase offsets within limit must pass."""
        phase_offsets_deg = [0.0, 1.0, -1.5, 2.0]
        result = verifier.check_phase_error(phase_offsets_deg)
        assert result.passed is True


# ---------------------------------------------------------------------------
# LO leakage tests
# ---------------------------------------------------------------------------

class TestLOLeakage:
    """LO leakage must be below the specified dBc limit."""

    @pytest.mark.calibration
    def test_lo_leakage_limit_check(self, verifier: CalibrationVerifier) -> None:
        """LO leakage of -30 dBc exceeds the -35 dBc limit."""
        result = verifier.check_lo_leakage(measured_dbc=-30.0)
        assert result.passed is False

    @pytest.mark.calibration
    def test_lo_leakage_within_limit(self, verifier: CalibrationVerifier) -> None:
        """LO leakage of -42 dBc is well below the -35 dBc limit."""
        result = verifier.check_lo_leakage(measured_dbc=-42.0)
        assert result.passed is True
