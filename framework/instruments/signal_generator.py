"""Signal generator control for RF firmware validation.

Provides high-level methods for CW tone generation, modulated signals,
frequency sweeps, and pulse modulation used during mmWave receiver
sensitivity and blocking tests.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from framework.instruments.scpi_base import SCPIInstrument

logger = logging.getLogger(__name__)


class SignalGenerator(SCPIInstrument):
    """Driver for SCPI-based RF signal generators.

    Inherits VISA lifecycle management from :class:`SCPIInstrument` and adds
    domain-specific methods for tone/modulation/sweep control.

    Args:
        resource_string: VISA resource address.
        timeout_ms: Default I/O timeout in milliseconds.
    """

    def __init__(self, resource_string: str, timeout_ms: int = 5000) -> None:
        super().__init__(resource_string, timeout_ms=timeout_ms)
        self._output_enabled: bool = False

    # -- CW control -----------------------------------------------------------

    def set_frequency(self, freq_hz: float) -> None:
        """Set the output CW frequency.

        Args:
            freq_hz: Desired frequency in Hz.
        """
        logger.info("Setting frequency to %.6f MHz", freq_hz / 1e6)
        self.write(f"FREQ {freq_hz}")
        self.wait_opc()

    def set_power(self, power_dbm: float) -> None:
        """Set the output power level.

        Args:
            power_dbm: Desired power level in dBm.
        """
        logger.info("Setting power to %.2f dBm", power_dbm)
        self.write(f"POW {power_dbm}")
        self.wait_opc()

    # -- modulation -----------------------------------------------------------

    def set_modulation(self, mod_type: str, params: Dict[str, Any]) -> None:
        """Configure modulation on the signal generator.

        Supports common modulation types (``'AM'``, ``'FM'``, ``'PM'``,
        ``'QPSK'``, ``'QAM16'``, etc.).  Additional parameters are passed
        via *params* and written as ``KEY VALUE`` SCPI commands under the
        modulation subsystem.

        Args:
            mod_type: Modulation type identifier, e.g. ``'AM'``, ``'FM'``.
            params: Dictionary of modulation parameters.  Typical keys:
                    ``'depth_pct'`` (AM), ``'deviation_hz'`` (FM),
                    ``'symbol_rate'`` (digital modulations).
        """
        logger.info("Configuring %s modulation with params: %s", mod_type, params)
        mod_upper = mod_type.upper()

        if mod_upper == "AM":
            depth = params.get("depth_pct", 50)
            self.write(f"AM:DEPT {depth}")
            self.write("AM:STAT ON")
        elif mod_upper == "FM":
            deviation = params.get("deviation_hz", 1e3)
            self.write(f"FM:DEV {deviation}")
            self.write("FM:STAT ON")
        elif mod_upper == "PM":
            deviation = params.get("deviation_rad", 1.0)
            self.write(f"PM:DEV {deviation}")
            self.write("PM:STAT ON")
        else:
            # Generic digital modulation (instrument-dependent subsystem)
            self.write(f"RAD:DMOD:TYPE {mod_upper}")
            for key, value in params.items():
                scpi_key = key.upper().replace("_", ":")
                self.write(f"RAD:DMOD:{scpi_key} {value}")
            self.write("RAD:DMOD:STAT ON")

        self.wait_opc()

    # -- output enable --------------------------------------------------------

    def output_on(self) -> None:
        """Enable the RF output."""
        logger.info("RF output ON")
        self.write("OUTP ON")
        self._output_enabled = True
        self.wait_opc()

    def output_off(self) -> None:
        """Disable the RF output."""
        logger.info("RF output OFF")
        self.write("OUTP OFF")
        self._output_enabled = False
        self.wait_opc()

    # -- frequency sweep ------------------------------------------------------

    def set_sweep(
        self,
        start_freq: float,
        stop_freq: float,
        step_freq: float,
        dwell_time: float,
    ) -> None:
        """Configure a stepped frequency sweep.

        Args:
            start_freq: Sweep start frequency in Hz.
            stop_freq: Sweep stop frequency in Hz.
            step_freq: Frequency step size in Hz.
            dwell_time: Dwell time per step in seconds.
        """
        logger.info(
            "Sweep config: %.3f-%.3f MHz, step=%.3f MHz, dwell=%.3f s",
            start_freq / 1e6,
            stop_freq / 1e6,
            step_freq / 1e6,
            dwell_time,
        )
        self.write(f"FREQ:STAR {start_freq}")
        self.write(f"FREQ:STOP {stop_freq}")
        self.write(f"SWE:FREQ:STEP:LIN {step_freq}")
        self.write(f"SWE:FREQ:DWEL {dwell_time}")
        self.write("FREQ:MODE SWE")
        self.wait_opc()

    def start_sweep(self) -> None:
        """Start the configured frequency sweep."""
        logger.info("Starting frequency sweep")
        self.write("SWE:FREQ:EXEC")
        self.wait_opc()

    def stop_sweep(self) -> None:
        """Abort the current sweep and return to CW mode."""
        logger.info("Stopping frequency sweep")
        self.write("FREQ:MODE CW")
        self.wait_opc()

    # -- pulse modulation -----------------------------------------------------

    def set_pulse_modulation(self, width_us: float, period_us: float) -> None:
        """Configure pulse modulation.

        Args:
            width_us: Pulse width in microseconds.
            period_us: Pulse period in microseconds.
        """
        if width_us >= period_us:
            raise ValueError(
                f"Pulse width ({width_us} us) must be less than period ({period_us} us)"
            )
        logger.info("Pulse modulation: width=%.2f us, period=%.2f us", width_us, period_us)
        self.write(f"PULM:WIDT {width_us}US")
        self.write(f"PULM:PER {period_us}US")
        self.write("PULM:SOUR INT")
        self.write("PULM:STAT ON")
        self.wait_opc()
