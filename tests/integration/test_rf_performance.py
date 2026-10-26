"""RF performance integration tests.

Measures TX power, noise figure, phase noise, and frequency accuracy
using calibrated lab instruments connected to the DUT.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.hardware, pytest.mark.rf]


# ---------------------------------------------------------------------------
# Specification limits
# ---------------------------------------------------------------------------

TX_POWER_MIN_DBM = 10.0
TX_POWER_MAX_DBM = 14.0
NOISE_FIGURE_MAX_DB = 16.0
PHASE_NOISE_LIMIT_DBCHZ = -80.0  # at 1 MHz offset
FREQUENCY_ACCURACY_PPM = 25.0
CARRIER_FREQUENCY_GHZ = 77.0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTXPower:
    """Validate transmitted RF power is within datasheet limits."""

    def test_tx_power_output(
        self, radar_configurator, power_meter
    ) -> None:
        """Measured TX power must be within the datasheet min/max range."""
        radar_configurator.apply_default_config()
        radar_configurator.enable_tx(tx_index=0)
        radar_configurator.start_sensor()

        power_dbm = power_meter.measure_power(frequency_ghz=CARRIER_FREQUENCY_GHZ)
        radar_configurator.stop_sensor()

        assert TX_POWER_MIN_DBM <= power_dbm <= TX_POWER_MAX_DBM, (
            f"TX power {power_dbm:.2f} dBm outside [{TX_POWER_MIN_DBM}, {TX_POWER_MAX_DBM}]"
        )


class TestNoiseFigure:
    """Validate receiver noise figure."""

    def test_rx_noise_figure(
        self, radar_configurator, spectrum_analyzer, signal_generator
    ) -> None:
        """RX noise figure measured via Y-factor method must be below spec."""
        # Cold measurement (input terminated)
        signal_generator.output_off()
        radar_configurator.apply_default_config()
        radar_configurator.start_sensor()

        cold_power = spectrum_analyzer.measure_channel_power(
            center_freq_ghz=CARRIER_FREQUENCY_GHZ,
            span_mhz=100,
        )

        # Hot measurement (noise source on)
        signal_generator.configure_noise(enr_db=15.0)
        signal_generator.output_on()
        hot_power = spectrum_analyzer.measure_channel_power(
            center_freq_ghz=CARRIER_FREQUENCY_GHZ,
            span_mhz=100,
        )
        signal_generator.output_off()
        radar_configurator.stop_sensor()

        y_factor = 10 ** ((hot_power - cold_power) / 10.0)
        noise_figure_db = 10 * __import__("math").log10(15.0 / (y_factor - 1))

        assert noise_figure_db <= NOISE_FIGURE_MAX_DB, (
            f"Noise figure {noise_figure_db:.2f} dB exceeds limit {NOISE_FIGURE_MAX_DB} dB"
        )


class TestPhaseNoise:
    """Validate phase noise at 1 MHz offset from carrier."""

    def test_phase_noise_at_1mhz_offset(
        self, radar_configurator, spectrum_analyzer
    ) -> None:
        """Phase noise at 1 MHz offset must be below the specification limit."""
        radar_configurator.apply_default_config()
        radar_configurator.enable_tx(tx_index=0)
        radar_configurator.start_sensor()

        pn_dbchz = spectrum_analyzer.measure_phase_noise(
            carrier_freq_ghz=CARRIER_FREQUENCY_GHZ,
            offset_mhz=1.0,
        )
        radar_configurator.stop_sensor()

        assert pn_dbchz <= PHASE_NOISE_LIMIT_DBCHZ, (
            f"Phase noise {pn_dbchz:.1f} dBc/Hz exceeds limit {PHASE_NOISE_LIMIT_DBCHZ} dBc/Hz"
        )


class TestFrequencyAccuracy:
    """Validate carrier frequency accuracy."""

    def test_frequency_accuracy(
        self, radar_configurator, spectrum_analyzer
    ) -> None:
        """Carrier frequency error must be within the allowed PPM tolerance."""
        radar_configurator.apply_default_config()
        radar_configurator.enable_tx(tx_index=0)
        radar_configurator.start_sensor()

        measured_ghz = spectrum_analyzer.measure_peak_frequency(
            center_freq_ghz=CARRIER_FREQUENCY_GHZ,
            span_mhz=10,
        )
        radar_configurator.stop_sensor()

        error_hz = abs(measured_ghz - CARRIER_FREQUENCY_GHZ) * 1e9
        error_ppm = error_hz / (CARRIER_FREQUENCY_GHZ * 1e3)  # ppm

        assert error_ppm <= FREQUENCY_ACCURACY_PPM, (
            f"Frequency error {error_ppm:.1f} ppm exceeds limit {FREQUENCY_ACCURACY_PPM} ppm"
        )
