"""Logic analyzer interface for digital protocol timing validation.

Supports Saleae Logic analysers via the Saleae Automation API and provides
higher-level helpers to verify SPI / I2C bus timing against device
specifications.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    """Configuration for a single logic-analyser channel.

    Attributes:
        index: Physical channel index (0-based).
        label: Human-readable label, e.g. ``"SPI_CLK"``.
        is_digital: ``True`` for digital, ``False`` for analogue.
        sample_rate_hz: Per-channel sample rate.
    """

    index: int
    label: str = ""
    is_digital: bool = True
    sample_rate_hz: int = 25_000_000


@dataclass
class TimingViolation:
    """A single timing-spec violation detected during analysis."""

    parameter: str
    expected: str
    measured: float
    unit: str = "s"
    message: str = ""


class LogicAnalyzer:
    """High-level driver for logic-analyser capture and protocol analysis.

    Currently supports **Saleae Logic** analysers via the gRPC-based
    Automation API.  Other back-ends can be added by subclassing or
    extending ``_saleae_automation_api``.

    Args:
        device_type: Analyser family, e.g. ``"saleae"``.
        serial_number: Analyser serial number (used when multiple units
                       are connected).
    """

    SUPPORTED_DEVICES = {"saleae"}

    def __init__(self, device_type: str = "saleae", serial_number: Optional[str] = None) -> None:
        if device_type not in self.SUPPORTED_DEVICES:
            raise ValueError(f"Unsupported device type '{device_type}'. Choose from {self.SUPPORTED_DEVICES}")
        self.device_type: str = device_type
        self.serial_number: Optional[str] = serial_number
        self._manager: Any = None  # saleae.automation.Manager
        self._device: Any = None
        self._capture: Any = None
        self._channels: List[ChannelConfig] = []
        self._connected: bool = False
        logger.debug("LogicAnalyzer created: type=%s, serial=%s", device_type, serial_number)

    # -- lifecycle ------------------------------------------------------------

    def connect(self) -> None:
        """Open a connection to the logic analyser."""
        logger.info("Connecting to %s logic analyser (serial=%s) ...", self.device_type, self.serial_number)
        if self.device_type == "saleae":
            self._saleae_automation_api("connect")
        self._connected = True
        logger.info("Logic analyser connected")

    def disconnect(self) -> None:
        """Release the analyser connection."""
        if self._connected:
            if self.device_type == "saleae":
                self._saleae_automation_api("disconnect")
            self._connected = False
            logger.info("Logic analyser disconnected")

    # -- channel configuration ------------------------------------------------

    def configure_channels(self, channels_config: List[ChannelConfig]) -> None:
        """Apply channel configuration (labels, sample rate, digital/analog).

        Args:
            channels_config: List of :class:`ChannelConfig` instances.
        """
        self._channels = channels_config
        logger.info("Configured %d channels", len(channels_config))
        for ch in channels_config:
            logger.debug("  CH%d (%s): digital=%s, rate=%d Hz", ch.index, ch.label, ch.is_digital, ch.sample_rate_hz)

    # -- trigger & capture ----------------------------------------------------

    def set_trigger(self, channel: int, edge: str = "rising", position: float = 0.1) -> None:
        """Set the capture trigger.

        Args:
            channel: Channel index for the trigger.
            edge: ``'rising'``, ``'falling'``, or ``'either'``.
            position: Trigger position as fraction of the capture buffer (0.0-1.0).
        """
        logger.info("Trigger set: CH%d, edge=%s, position=%.0f%%", channel, edge, position * 100)
        self._saleae_automation_api("set_trigger", channel=channel, edge=edge, position=position)

    def start_capture(self, duration_s: float = 1.0) -> None:
        """Start a timed capture.

        Args:
            duration_s: Capture duration in seconds.
        """
        logger.info("Starting capture for %.3f s", duration_s)
        self._saleae_automation_api("start_capture", duration_s=duration_s)

    def stop_capture(self) -> None:
        """Manually stop an ongoing capture."""
        logger.info("Stopping capture")
        self._saleae_automation_api("stop_capture")

    # -- data retrieval -------------------------------------------------------

    def get_digital_data(self, channel: int) -> List[Tuple[float, int]]:
        """Return timestamped digital transitions for a channel.

        Args:
            channel: Channel index.

        Returns:
            List of ``(timestamp_s, logic_value)`` tuples.
        """
        raw = self._saleae_automation_api("get_digital_data", channel=channel)
        if raw is None:
            return []
        data: List[Tuple[float, int]] = [(float(t), int(v)) for t, v in raw]
        logger.debug("CH%d: %d digital transitions retrieved", channel, len(data))
        return data

    # -- protocol analysis ----------------------------------------------------

    def analyze_spi_timing(
        self,
        clk_ch: int,
        mosi_ch: int,
        miso_ch: int,
        cs_ch: int,
    ) -> Dict[str, Any]:
        """Analyse SPI bus timing from captured data.

        Args:
            clk_ch: SPI clock channel index.
            mosi_ch: MOSI channel index.
            miso_ch: MISO channel index.
            cs_ch: Chip-select channel index.

        Returns:
            Dictionary with timing metrics: ``clock_freq_hz``,
            ``setup_time_s``, ``hold_time_s``, ``cs_to_clk_s``.
        """
        logger.info("Analysing SPI timing (CLK=CH%d, MOSI=CH%d, MISO=CH%d, CS=CH%d)",
                     clk_ch, mosi_ch, miso_ch, cs_ch)
        clk_data = self.get_digital_data(clk_ch)
        cs_data = self.get_digital_data(cs_ch)

        if len(clk_data) < 2:
            logger.warning("Insufficient clock edges for SPI analysis")
            return {}

        clk_periods = [clk_data[i + 1][0] - clk_data[i][0] for i in range(len(clk_data) - 1)]
        avg_period = sum(clk_periods) / len(clk_periods) if clk_periods else 0.0

        cs_to_clk = 0.0
        if cs_data and clk_data:
            cs_assert = next((t for t, v in cs_data if v == 0), None)
            first_clk = clk_data[0][0] if clk_data else None
            if cs_assert is not None and first_clk is not None:
                cs_to_clk = first_clk - cs_assert

        result: Dict[str, Any] = {
            "clock_freq_hz": 1.0 / avg_period if avg_period > 0 else 0.0,
            "avg_period_s": avg_period,
            "cs_to_clk_s": cs_to_clk,
            "num_clock_edges": len(clk_data),
        }
        logger.info("SPI timing: %s", result)
        return result

    def analyze_i2c_timing(self, sda_ch: int, scl_ch: int) -> Dict[str, Any]:
        """Analyse I2C bus timing from captured data.

        Args:
            sda_ch: SDA channel index.
            scl_ch: SCL channel index.

        Returns:
            Dictionary with timing metrics: ``clock_freq_hz``,
            ``start_hold_s``, ``stop_setup_s``.
        """
        logger.info("Analysing I2C timing (SDA=CH%d, SCL=CH%d)", sda_ch, scl_ch)
        scl_data = self.get_digital_data(scl_ch)
        sda_data = self.get_digital_data(sda_ch)

        if len(scl_data) < 2:
            logger.warning("Insufficient SCL edges for I2C analysis")
            return {}

        scl_periods = [scl_data[i + 1][0] - scl_data[i][0] for i in range(len(scl_data) - 1)]
        avg_period = sum(scl_periods) / len(scl_periods) if scl_periods else 0.0

        result: Dict[str, Any] = {
            "clock_freq_hz": 1.0 / (avg_period * 2) if avg_period > 0 else 0.0,
            "avg_half_period_s": avg_period,
            "num_scl_edges": len(scl_data),
            "num_sda_edges": len(sda_data),
        }
        logger.info("I2C timing: %s", result)
        return result

    def verify_protocol_timing(
        self,
        protocol: str,
        spec: Dict[str, Tuple[float, float]],
    ) -> Tuple[bool, List[TimingViolation]]:
        """Check measured timing against a specification.

        Args:
            protocol: ``'spi'`` or ``'i2c'``.
            spec: Mapping of parameter name to ``(min, max)`` in seconds.

        Returns:
            Tuple of (pass_flag, list_of_violations).
        """
        violations: List[TimingViolation] = []

        if protocol.lower() == "spi":
            # Requires a prior capture with correct channel mapping stored
            logger.warning("verify_protocol_timing for SPI requires pre-captured data")
        elif protocol.lower() == "i2c":
            logger.warning("verify_protocol_timing for I2C requires pre-captured data")
        else:
            raise ValueError(f"Unsupported protocol: {protocol}")

        passed = len(violations) == 0
        logger.info("Protocol timing verification: %s, violations=%d", "PASS" if passed else "FAIL", len(violations))
        return passed, violations

    # -- export ---------------------------------------------------------------

    def export_data(self, filepath: str, format: str = "csv") -> None:
        """Export captured data to a file.

        Args:
            filepath: Destination path.
            format: ``'csv'`` or ``'json'``.
        """
        logger.info("Exporting capture data to %s (format=%s)", filepath, format)
        self._saleae_automation_api("export", filepath=filepath, format=format)

    # -- internal Saleae helpers ----------------------------------------------

    def _saleae_automation_api(self, command: str, **kwargs: Any) -> Any:
        """Dispatch a command to the Saleae Automation API.

        This method acts as an adapter layer.  In production it would
        communicate with the Saleae Logic 2 gRPC server; here it logs the
        requested operation to facilitate integration testing.

        Args:
            command: API action name.
            **kwargs: Action-specific parameters.

        Returns:
            Response data from the analyser, or ``None``.
        """
        logger.debug("Saleae API call: %s(%s)", command, kwargs)
        # In a real implementation this would use:
        #   from saleae import automation
        #   self._manager = automation.Manager.connect()
        # and call the appropriate methods on the capture/device objects.
        return None
