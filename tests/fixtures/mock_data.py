"""Mock data generators for offline / unit testing without hardware."""
from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# ADC frame generator
# ---------------------------------------------------------------------------

def generate_mock_adc_frame(
    num_chirps: int = 128,
    num_samples: int = 256,
    num_rx: int = 4,
    noise_floor_dbfs: float = -40.0,
) -> np.ndarray:
    """Return a synthetic ADC data cube (chirps x samples x rx) as int16.

    A single simulated target is injected at range bin 50 with a sinusoidal
    beat tone so that basic FFT processing can detect it.
    """
    rng = np.random.default_rng(seed=42)
    noise_amplitude = 10 ** (noise_floor_dbfs / 20) * 32767
    frame = (rng.standard_normal((num_chirps, num_samples, num_rx)) * noise_amplitude)

    # Inject a target at range bin 50
    target_bin = 50
    target_amplitude = 0.8 * 32767
    t = np.arange(num_samples)
    tone = target_amplitude * np.sin(2 * np.pi * target_bin * t / num_samples)
    for chirp in range(num_chirps):
        for rx in range(num_rx):
            frame[chirp, :, rx] += tone

    return frame.astype(np.int16)


# ---------------------------------------------------------------------------
# Range profile generator
# ---------------------------------------------------------------------------

def generate_mock_range_profile(
    num_bins: int = 256,
    targets: list[dict] | None = None,
) -> np.ndarray:
    """Return a 1-D range magnitude profile with optional injected targets.

    Each target dict should contain ``bin`` (int) and ``amplitude`` (float).
    """
    if targets is None:
        targets = [{"bin": 50, "amplitude": 1000.0}, {"bin": 120, "amplitude": 500.0}]

    rng = np.random.default_rng(seed=99)
    profile = rng.standard_normal(num_bins).astype(np.float64) * 5.0
    profile = np.abs(profile)

    for tgt in targets:
        b = int(tgt["bin"])
        a = float(tgt["amplitude"])
        # Gaussian spread around the target bin
        spread = np.exp(-0.5 * ((np.arange(num_bins) - b) / 1.5) ** 2)
        profile += a * spread

    return profile


# ---------------------------------------------------------------------------
# Chirp / frame config generators
# ---------------------------------------------------------------------------

def generate_test_chirp_config() -> dict:
    """Return a realistic chirp configuration dictionary."""
    return {
        "start_freq_ghz": 77.0,
        "freq_slope_mhz_per_us": 60.0,
        "idle_time_us": 5.0,
        "adc_start_time_us": 6.0,
        "ramp_end_time_us": 40.0,
        "adc_samples": 256,
        "sample_rate_ksps": 10000,
        "rx_gain_db": 30,
        "tx_enable_mask": 0x07,
    }


def generate_test_frame_config() -> dict:
    """Return a realistic frame configuration dictionary."""
    return {
        "num_chirps_per_frame": 128,
        "num_frames": 0,  # 0 = infinite
        "frame_periodicity_ms": 33.33,
        "trigger_select": "software",
        "chirp_start_idx": 0,
        "chirp_end_idx": 2,
        "num_loops": 64,
    }


# ---------------------------------------------------------------------------
# Sample UART log output
# ---------------------------------------------------------------------------

SAMPLE_UART_LOG: str = """\
[BOOT] mmWave Radar Sensor FW v2.4.1 (build 20240315)
[BOOT] Platform: AWR2944, ROM v1.2
[BOOT] BSS version: 3.8.2
[INIT] Configuring RF front-end ...
[INIT] TX channels enabled: TX0 TX1 TX2
[INIT] RX channels enabled: RX0 RX1 RX2 RX3
[CAL]  Running factory calibration ...
[CAL]  TX0 power: 11.8 dBm  [PASS]
[CAL]  TX1 power: 11.6 dBm  [PASS]
[CAL]  TX2 power: 11.9 dBm  [PASS]
[CAL]  RX gain mismatch: 0.3 dB  [PASS]
[CAL]  LO leakage: -42 dBc  [PASS]
[SAFE] Watchdog enabled, timeout=50ms
[SAFE] ECC SRAM check: PASS
[SAFE] Lockstep core compare: PASS
[READY] Sensor ready — awaiting start command
"""
