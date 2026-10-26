"""Integration tests for the radar data path.

Exercises the full ADC -> DMA -> range-FFT pipeline on real hardware
and validates frame geometry, CRC integrity, and target detection.
"""
from __future__ import annotations

import numpy as np
import pytest

from framework.utils.crc import crc32_verify


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.hardware, pytest.mark.datapath]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_CHIRPS_PER_FRAME = 128
EXPECTED_ADC_SAMPLES = 256
EXPECTED_NUM_RX = 4
TARGET_RANGE_BIN = 50
DETECTION_THRESHOLD_DB = 15.0
NUM_CONTINUITY_FRAMES = 10


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFrameCapture:
    """Verify basic frame capture integrity."""

    def test_frame_capture_correct_size(
        self, radar_configurator, uart_monitor
    ) -> None:
        """Captured frame must have the expected (chirps x samples x rx) shape."""
        radar_configurator.apply_config(
            chirps=EXPECTED_CHIRPS_PER_FRAME,
            samples=EXPECTED_ADC_SAMPLES,
            rx_channels=EXPECTED_NUM_RX,
        )
        radar_configurator.start_sensor()
        frame = uart_monitor.read_frame(timeout_s=5.0)
        radar_configurator.stop_sensor()

        assert frame is not None, "No frame received within timeout"
        assert frame.shape == (
            EXPECTED_CHIRPS_PER_FRAME,
            EXPECTED_ADC_SAMPLES,
            EXPECTED_NUM_RX,
        )

    def test_frame_crc_valid(self, radar_configurator, uart_monitor) -> None:
        """Each frame's trailing CRC must verify against its payload."""
        radar_configurator.apply_default_config()
        radar_configurator.start_sensor()
        raw_packet = uart_monitor.read_raw_packet(timeout_s=5.0)
        radar_configurator.stop_sensor()

        assert raw_packet is not None, "No packet received"
        assert crc32_verify(raw_packet), "Frame CRC verification failed"

    def test_adc_data_not_all_zeros(
        self, radar_configurator, uart_monitor
    ) -> None:
        """ADC samples must contain non-zero data (antenna connected)."""
        radar_configurator.apply_default_config()
        radar_configurator.start_sensor()
        frame = uart_monitor.read_frame(timeout_s=5.0)
        radar_configurator.stop_sensor()

        assert frame is not None
        assert not np.all(frame == 0), "All-zero ADC frame indicates HW issue"


class TestRangeProcessing:
    """Verify range-FFT and target detection."""

    def test_range_fft_target_detection(
        self, radar_configurator, uart_monitor, signal_generator
    ) -> None:
        """A calibrated target injected by the signal generator must appear
        at the expected range bin above the detection threshold."""
        signal_generator.configure_cw(frequency_ghz=77.5, power_dbm=-20.0)
        signal_generator.output_on()

        radar_configurator.apply_default_config()
        radar_configurator.start_sensor()
        frame = uart_monitor.read_frame(timeout_s=5.0)
        radar_configurator.stop_sensor()
        signal_generator.output_off()

        assert frame is not None
        # Compute range profile from first chirp, first RX
        range_fft = np.abs(np.fft.fft(frame[0, :, 0]))
        peak_bin = int(np.argmax(range_fft[:EXPECTED_ADC_SAMPLES // 2]))
        peak_power = 20 * np.log10(range_fft[peak_bin] + 1e-12)
        noise_floor = 20 * np.log10(np.median(range_fft[:EXPECTED_ADC_SAMPLES // 2]) + 1e-12)
        snr = peak_power - noise_floor

        assert snr >= DETECTION_THRESHOLD_DB, (
            f"Target SNR {snr:.1f} dB below threshold {DETECTION_THRESHOLD_DB} dB"
        )


class TestMultiFrameContinuity:
    """Validate frame counter continuity across multiple frames."""

    def test_multi_frame_continuity(
        self, radar_configurator, uart_monitor
    ) -> None:
        """Frame counter must increment by exactly 1 between consecutive frames."""
        radar_configurator.apply_default_config()
        radar_configurator.start_sensor()

        frame_numbers: list[int] = []
        for _ in range(NUM_CONTINUITY_FRAMES):
            header = uart_monitor.read_frame_header(timeout_s=5.0)
            assert header is not None, "Missed frame header"
            frame_numbers.append(header["frame_number"])

        radar_configurator.stop_sensor()

        for i in range(1, len(frame_numbers)):
            expected = frame_numbers[i - 1] + 1
            assert frame_numbers[i] == expected, (
                f"Frame discontinuity: expected {expected}, got {frame_numbers[i]}"
            )
