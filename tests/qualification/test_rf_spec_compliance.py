"""RF specification compliance tests.

Validates that key RF parameters meet the published datasheet
specifications for the target mmWave sensor device.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.rf_spec, pytest.mark.hardware]


# ---------------------------------------------------------------------------
# Datasheet specification limits
# ---------------------------------------------------------------------------

TX_POWER_SPEC_MIN_DBM = 10.0
TX_POWER_SPEC_MAX_DBM = 14.0
NOISE_FIGURE_SPEC_MAX_DB = 16.0
PHASE_NOISE_SPEC_DBCHZ = -80.0  # at 1 MHz offset
BANDWIDTH_SPEC_MIN_GHZ = 4.0
CARRIER_FREQ_GHZ = 77.0


# ---------------------------------------------------------------------------
# TX power compliance
# ---------------------------------------------------------------------------

class TestTXPowerSpec:
    """TX power must meet the datasheet minimum and maximum."""

    def test_tx_power_meets_datasheet(
        self, radar_configurator, power_meter
    ) -> None:
        """Measured TX power shall fall within the datasheet specification.

        Spec: AWR2944 datasheet Table 5 — TX output power.
        """
        radar_configurator.apply_default_config()
        radar_configurator.enable_tx(tx_index=0)
        radar_configurator.start_sensor()

        power_dbm = power_meter.measure_power(frequency_ghz=CARRIER_FREQ_GHZ)
        radar_configurator.stop_sensor()

        assert TX_POWER_SPEC_MIN_DBM <= power_dbm <= TX_POWER_SPEC_MAX_DBM, (
            f"TX power {power_dbm:.2f} dBm outside spec "
            f"[{TX_POWER_SPEC_MIN_DBM}, {TX_POWER_SPEC_MAX_DBM}] dBm"
        )


# ---------------------------------------------------------------------------
# Noise figure compliance
# ---------------------------------------------------------------------------

class TestNoiseFigureSpec:
    """Receiver noise figure must meet the datasheet maximum."""

    def test_noise_figure_meets_spec(
        self, radar_configurator, spectrum_analyzer, signal_generator
    ) -> None:
        """Measured noise figure (Y-factor method) shall not exceed datasheet limit.

        Spec: AWR2944 datasheet Table 6 — Receiver noise figure.
        """
        signal_generator.output_off()
        radar_configurator.apply_default_config()
        radar_configurator.start_sensor()

        cold_power = spectrum_analyzer.measure_channel_power(
            center_freq_ghz=CARRIER_FREQ_GHZ, span_mhz=100,
        )

        signal_generator.configure_noise(enr_db=15.0)
        signal_generator.output_on()
        hot_power = spectrum_analyzer.measure_channel_power(
            center_freq_ghz=CARRIER_FREQ_GHZ, span_mhz=100,
        )
        signal_generator.output_off()
        radar_configurator.stop_sensor()

        y_factor = 10 ** ((hot_power - cold_power) / 10.0)
        import math
        nf_db = 10 * math.log10(15.0 / (y_factor - 1))

        assert nf_db <= NOISE_FIGURE_SPEC_MAX_DB, (
            f"Noise figure {nf_db:.2f} dB exceeds spec {NOISE_FIGURE_SPEC_MAX_DB} dB"
        )


# ---------------------------------------------------------------------------
# Phase noise compliance
# ---------------------------------------------------------------------------

class TestPhaseNoiseSpec:
    """Phase noise at 1 MHz offset must meet the datasheet limit."""

    def test_phase_noise_meets_spec(
        self, radar_configurator, spectrum_analyzer
    ) -> None:
        """Phase noise at 1 MHz offset shall not exceed datasheet limit.

        Spec: AWR2944 datasheet Table 7 — Synthesizer phase noise.
        """
        radar_configurator.apply_default_config()
        radar_configurator.enable_tx(tx_index=0)
        radar_configurator.start_sensor()

        pn = spectrum_analyzer.measure_phase_noise(
            carrier_freq_ghz=CARRIER_FREQ_GHZ, offset_mhz=1.0,
        )
        radar_configurator.stop_sensor()

        assert pn <= PHASE_NOISE_SPEC_DBCHZ, (
            f"Phase noise {pn:.1f} dBc/Hz exceeds spec {PHASE_NOISE_SPEC_DBCHZ} dBc/Hz"
        )


# ---------------------------------------------------------------------------
# Bandwidth compliance
# ---------------------------------------------------------------------------

class TestBandwidthSpec:
    """Chirp bandwidth must meet the datasheet minimum."""

    def test_bandwidth_meets_spec(
        self, radar_configurator, spectrum_analyzer
    ) -> None:
        """Measured chirp bandwidth shall be at least the specified minimum.

        Spec: AWR2944 datasheet Table 4 — Maximum RF bandwidth.
        """
        radar_configurator.apply_config(
            start_freq_ghz=76.0,
            freq_slope_mhz_per_us=100.0,
            ramp_end_time_us=40.0,
        )
        radar_configurator.enable_tx(tx_index=0)
        radar_configurator.start_sensor()

        bw_ghz = spectrum_analyzer.measure_occupied_bandwidth(
            center_freq_ghz=CARRIER_FREQ_GHZ, span_ghz=6.0,
        )
        radar_configurator.stop_sensor()

        assert bw_ghz >= BANDWIDTH_SPEC_MIN_GHZ, (
            f"Bandwidth {bw_ghz:.2f} GHz below spec minimum {BANDWIDTH_SPEC_MIN_GHZ} GHz"
        )
