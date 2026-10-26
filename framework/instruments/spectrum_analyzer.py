"""Spectrum analyzer control for RF firmware validation.

Wraps common measurement routines (peak search, channel power, ACLR, trace
capture) used during mmWave transmitter characterisation and production test.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from framework.instruments.scpi_base import SCPIInstrument

logger = logging.getLogger(__name__)


class SpectrumAnalyzer(SCPIInstrument):
    """High-level driver for SCPI-based spectrum analyzers (R&S / Keysight / etc.).

    Inherits VISA lifecycle management from :class:`SCPIInstrument` and adds
    domain-specific methods for frequency-domain measurements.

    Args:
        resource_string: VISA resource address.
        timeout_ms: Default I/O timeout in milliseconds.
    """

    def __init__(self, resource_string: str, timeout_ms: int = 10000) -> None:
        super().__init__(resource_string, timeout_ms=timeout_ms)

    # -- sweep configuration --------------------------------------------------

    def configure_sweep(
        self,
        center_freq_hz: float,
        span_hz: float,
        rbw_hz: float,
        vbw_hz: float,
    ) -> None:
        """Configure the frequency sweep parameters.

        Args:
            center_freq_hz: Centre frequency in Hz.
            span_hz: Frequency span in Hz.
            rbw_hz: Resolution bandwidth in Hz.
            vbw_hz: Video bandwidth in Hz.
        """
        logger.info(
            "Configuring sweep: center=%.3f MHz, span=%.3f MHz, RBW=%.1f kHz, VBW=%.1f kHz",
            center_freq_hz / 1e6,
            span_hz / 1e6,
            rbw_hz / 1e3,
            vbw_hz / 1e3,
        )
        self.write(f"FREQ:CENT {center_freq_hz}")
        self.write(f"FREQ:SPAN {span_hz}")
        self.write(f"BAND {rbw_hz}")
        self.write(f"BAND:VID {vbw_hz}")
        self.wait_opc()

    def set_reference_level(self, level_dbm: float) -> None:
        """Set the analyser reference level.

        Args:
            level_dbm: Reference level in dBm.
        """
        logger.info("Setting reference level to %.1f dBm", level_dbm)
        self.write(f"DISP:WIND:TRAC:Y:RLEV {level_dbm}")
        self.wait_opc()

    # -- measurements ---------------------------------------------------------

    def measure_peak_power(self) -> Tuple[float, float]:
        """Perform a single sweep and return the peak marker value.

        Returns:
            Tuple of (frequency_hz, power_dbm) at the spectral peak.
        """
        self.write("INIT:IMM;*WAI")
        self.wait_for_sweep()
        self.marker_to_peak(1)
        freq, power = self.get_marker_value(1)
        logger.info("Peak power: %.2f dBm @ %.6f MHz", power, freq / 1e6)
        return freq, power

    def measure_channel_power(self, center_freq: float, bandwidth: float) -> float:
        """Measure integrated channel power.

        Args:
            center_freq: Channel centre frequency in Hz.
            bandwidth: Integration bandwidth in Hz.

        Returns:
            Channel power in dBm.
        """
        self.write("CALC:MARK:FUNC:POW:SEL CPOW")
        self.write(f"FREQ:CENT {center_freq}")
        self.write(f"POW:ACH:BWID {bandwidth}")
        self.write("INIT:IMM;*WAI")
        self.wait_for_sweep()
        result_str = self.query("CALC:MARK:FUNC:POW:RES? CPOW")
        power_dbm = float(result_str)
        logger.info("Channel power: %.2f dBm (BW=%.3f MHz)", power_dbm, bandwidth / 1e6)
        return power_dbm

    def measure_aclr(
        self,
        center_freq: float,
        channel_bw: float,
        adj_bw: float,
    ) -> Dict[str, float]:
        """Measure adjacent-channel leakage ratio (ACLR).

        Args:
            center_freq: Channel centre frequency in Hz.
            channel_bw: Main channel bandwidth in Hz.
            adj_bw: Adjacent channel bandwidth in Hz.

        Returns:
            Dictionary with keys ``'lower_aclr_dB'``, ``'upper_aclr_dB'``, and
            ``'channel_power_dBm'``.
        """
        self.write("CALC:MARK:FUNC:POW:SEL ACP")
        self.write(f"FREQ:CENT {center_freq}")
        self.write(f"POW:ACH:BWID {channel_bw}")
        self.write(f"POW:ACH:BWID:ACH {adj_bw}")
        self.write("INIT:IMM;*WAI")
        self.wait_for_sweep()
        result_str = self.query("CALC:MARK:FUNC:POW:RES? ACP")
        values = [float(v) for v in result_str.split(",")]
        result: Dict[str, float] = {
            "channel_power_dBm": values[0],
            "lower_aclr_dB": values[1] if len(values) > 1 else float("nan"),
            "upper_aclr_dB": values[2] if len(values) > 2 else float("nan"),
        }
        logger.info("ACLR: %s", result)
        return result

    # -- trace & marker -------------------------------------------------------

    def get_trace_data(self, trace_num: int = 1) -> np.ndarray:
        """Download trace data as a numpy array.

        Args:
            trace_num: Trace number (1-based).

        Returns:
            1-D numpy array of amplitude values in the current unit.
        """
        data = self.query_binary(f"TRAC? TRACE{trace_num}")
        logger.debug("Retrieved %d trace points from TRACE%d", len(data), trace_num)
        return data

    def set_marker(self, marker_num: int, freq_hz: float) -> None:
        """Place a marker at a specific frequency.

        Args:
            marker_num: Marker index (1-based).
            freq_hz: Marker frequency in Hz.
        """
        self.write(f"CALC:MARK{marker_num}:STAT ON")
        self.write(f"CALC:MARK{marker_num}:X {freq_hz}")
        self.wait_opc()

    def marker_to_peak(self, marker_num: int = 1) -> None:
        """Move a marker to the trace peak.

        Args:
            marker_num: Marker index (1-based).
        """
        self.write(f"CALC:MARK{marker_num}:STAT ON")
        self.write(f"CALC:MARK{marker_num}:MAX")
        self.wait_opc()

    def get_marker_value(self, marker_num: int = 1) -> Tuple[float, float]:
        """Read frequency and amplitude from a marker.

        Args:
            marker_num: Marker index (1-based).

        Returns:
            Tuple of (frequency_hz, power_dbm).
        """
        freq = float(self.query(f"CALC:MARK{marker_num}:X?"))
        power = float(self.query(f"CALC:MARK{marker_num}:Y?"))
        return freq, power

    # -- utilities ------------------------------------------------------------

    def capture_screenshot(self, filepath: str) -> None:
        """Save the current display as a PNG screenshot.

        Args:
            filepath: Local file path for the saved image.
        """
        self.write("HCOP:DEV:LANG PNG")
        self.write("HCOP:IMM")
        self.wait_opc()
        raw = self._inst.query_binary_values(  # type: ignore[union-attr]
            "HCOP:DATA?", datatype="B", is_big_endian=False,
        )
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(raw))
        logger.info("Screenshot saved to %s", filepath)

    def wait_for_sweep(self, poll_interval_s: float = 0.25, timeout_s: float = 30.0) -> None:
        """Poll until the current sweep completes or *timeout_s* elapses.

        Args:
            poll_interval_s: Polling interval in seconds.
            timeout_s: Maximum wait time in seconds.

        Raises:
            TimeoutError: If the sweep does not complete within *timeout_s*.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            status = self.query("STAT:OPER:COND?")
            if int(status) & 0x8 == 0:  # sweeping bit clear
                return
            time.sleep(poll_interval_s)
        raise TimeoutError(f"Sweep did not complete within {timeout_s}s")
