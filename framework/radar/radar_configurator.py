"""Radar configuration for testing via UART command interface.

Handles the serial command protocol used by TI mmWave radar devices to
configure chirp profiles, frame parameters, and calibration sequences.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import serial

logger = logging.getLogger(__name__)


class RadarConfigurator:
    """Control interface for mmWave radar sensor configuration over UART.

    The class manages the serial connection and implements the command/response
    protocol used by the radar's CLI firmware.

    Args:
        uart_port: Serial port identifier, e.g. ``"COM4"`` or ``"/dev/ttyUSB0"``.
        baudrate: UART baud rate (default 115200).
    """

    RESPONSE_TIMEOUT_S: float = 2.0

    def __init__(self, uart_port: str, baudrate: int = 115200) -> None:
        self.uart_port: str = uart_port
        self.baudrate: int = baudrate
        self._serial: Optional[serial.Serial] = None
        self._connected: bool = False
        logger.debug("RadarConfigurator created for %s @ %d baud", uart_port, baudrate)

    # -- lifecycle ------------------------------------------------------------

    def connect(self) -> None:
        """Open the serial port to the radar device."""
        logger.info("Opening UART %s @ %d baud", self.uart_port, self.baudrate)
        self._serial = serial.Serial(
            port=self.uart_port,
            baudrate=self.baudrate,
            timeout=self.RESPONSE_TIMEOUT_S,
            write_timeout=self.RESPONSE_TIMEOUT_S,
        )
        self._connected = True
        logger.info("UART connected to %s", self.uart_port)

    def disconnect(self) -> None:
        """Close the serial port."""
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
            logger.info("UART disconnected from %s", self.uart_port)
        self._serial = None
        self._connected = False

    # -- high-level configuration ---------------------------------------------

    def send_config(self, config_dict: Dict[str, Any]) -> None:
        """Send a complete radar configuration as a dictionary.

        Each key-value pair is translated into the appropriate CLI command
        and dispatched in the correct order (sensor stop -> profile ->
        chirp -> frame -> sensor start).

        Args:
            config_dict: Configuration dictionary with keys such as
                         ``'profile'``, ``'chirp'``, ``'frame'``.
        """
        logger.info("Sending radar configuration (%d keys)", len(config_dict))
        self._send_command("sensorStop", {})

        if "profile" in config_dict:
            self.set_chirp_profile(config_dict["profile"])
        if "chirp" in config_dict:
            for chirp in config_dict["chirp"] if isinstance(config_dict["chirp"], list) else [config_dict["chirp"]]:
                self._send_command("chirpCfg", chirp)
        if "frame" in config_dict:
            self.set_frame_config(config_dict["frame"])
        if "extra_commands" in config_dict:
            for cmd_name, params in config_dict["extra_commands"].items():
                self._send_command(cmd_name, params)

        self._send_command("sensorStart", {})
        logger.info("Radar configuration applied and sensor started")

    def set_chirp_profile(self, profile: Dict[str, Any]) -> None:
        """Configure a chirp profile.

        Args:
            profile: Profile parameters (``start_freq_ghz``, ``idle_time_us``,
                     ``ramp_end_time_us``, ``freq_slope_mhz_per_us``,
                     ``tx_power``, ``adc_samples``, ``sample_rate_ksps``, etc.).
        """
        logger.info("Setting chirp profile: %s", profile)
        self._send_command("profileCfg", profile)

    def set_frame_config(self, frame_config: Dict[str, Any]) -> None:
        """Configure the radar frame structure.

        Args:
            frame_config: Frame parameters (``num_chirps``, ``num_frames``,
                          ``frame_periodicity_ms``, ``trigger_select``, etc.).
        """
        logger.info("Setting frame config: %s", frame_config)
        self._send_command("frameCfg", frame_config)

    def trigger_calibration(self, cal_type: str) -> Dict[str, Any]:
        """Trigger an on-chip calibration sequence.

        Args:
            cal_type: Calibration type, e.g. ``'factory'``, ``'runtime'``, ``'lo_leakage'``.

        Returns:
            Parsed calibration response.
        """
        logger.info("Triggering calibration: %s", cal_type)
        resp = self._send_command("calibration", {"type": cal_type})
        return self._parse_response(resp)

    # -- status queries -------------------------------------------------------

    def get_sensor_status(self) -> Dict[str, Any]:
        """Query the current sensor status.

        Returns:
            Dictionary with status fields: ``state``, ``temperature_degC``,
            ``active_profile``, etc.
        """
        resp = self._send_command("sensorStatus", {})
        status = self._parse_response(resp)
        logger.info("Sensor status: %s", status)
        return status

    def get_temperature(self) -> float:
        """Read the on-die temperature sensor.

        Returns:
            Temperature in degrees Celsius.
        """
        resp = self._send_command("tempMonitor", {})
        parsed = self._parse_response(resp)
        temp = float(parsed.get("temperature_degC", 0.0))
        logger.info("Sensor temperature: %.1f C", temp)
        return temp

    def verify_config_applied(self) -> bool:
        """Verify that the sensor accepted the last configuration.

        Returns:
            ``True`` if the sensor reports the configuration is active.
        """
        status = self.get_sensor_status()
        applied = status.get("state", "").lower() == "active"
        if applied:
            logger.info("Configuration verified: active")
        else:
            logger.warning("Configuration NOT active. Sensor state: %s", status.get("state"))
        return applied

    # -- internal helpers -----------------------------------------------------

    def _send_command(self, cmd: str, params: Dict[str, Any]) -> str:
        """Format and send a CLI command, then read the response.

        Args:
            cmd: Command name.
            params: Parameter dictionary serialised as space-separated values.

        Returns:
            Raw response string from the device.

        Raises:
            RuntimeError: If the serial port is not open.
        """
        if not self._connected or self._serial is None:
            raise RuntimeError("Not connected. Call connect() first.")

        param_str = " ".join(str(v) for v in params.values()) if params else ""
        line = f"{cmd} {param_str}\n" if param_str else f"{cmd}\n"
        logger.debug("UART TX >>> %s", line.strip())
        self._serial.write(line.encode("ascii"))
        self._serial.flush()

        # Read response lines until prompt or timeout
        response_lines: List[str] = []
        deadline = time.monotonic() + self.RESPONSE_TIMEOUT_S
        while time.monotonic() < deadline:
            raw_line = self._serial.readline()
            if not raw_line:
                break
            decoded = raw_line.decode("ascii", errors="replace").strip()
            response_lines.append(decoded)
            logger.debug("UART RX <<< %s", decoded)
            if decoded.startswith("Done") or decoded.startswith("Error"):
                break

        return "\n".join(response_lines)

    @staticmethod
    def _parse_response(raw_data: str) -> Dict[str, Any]:
        """Parse a multi-line device response into a dictionary.

        The expected format is ``key:value`` pairs, one per line.

        Args:
            raw_data: Raw multi-line response.

        Returns:
            Parsed key-value dictionary.
        """
        result: Dict[str, Any] = {}
        for line in raw_data.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                try:
                    result[key] = int(value)
                except ValueError:
                    try:
                        result[key] = float(value)
                    except ValueError:
                        result[key] = value
        return result
