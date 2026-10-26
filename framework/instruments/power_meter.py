"""Power meter control for RF firmware validation.

Wraps sensor configuration, single/continuous measurement, zeroing, and
averaging for USB/GPIB/LAN-connected RF power meters.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from framework.instruments.scpi_base import SCPIInstrument

logger = logging.getLogger(__name__)


class PowerMeter(SCPIInstrument):
    """Driver for SCPI-based RF power meters (R&S NRP, Keysight U2000, etc.).

    Inherits VISA lifecycle management from :class:`SCPIInstrument`.

    Args:
        resource_string: VISA resource address.
        timeout_ms: Default I/O timeout in milliseconds.
    """

    def __init__(self, resource_string: str, timeout_ms: int = 5000) -> None:
        super().__init__(resource_string, timeout_ms=timeout_ms)
        self._continuous_thread: Optional[threading.Thread] = None
        self._continuous_running: bool = False

    # -- configuration --------------------------------------------------------

    def configure(self, freq_hz: float, range_dbm: Optional[float] = None) -> None:
        """Configure the power sensor for a measurement.

        Args:
            freq_hz: Expected signal frequency in Hz (for frequency-dependent
                     calibration factor correction).
            range_dbm: Manual measurement range in dBm.  ``None`` selects
                       auto-range.
        """
        logger.info("Configuring power meter: freq=%.6f MHz", freq_hz / 1e6)
        self.write(f"SENS:FREQ {freq_hz}")
        if range_dbm is not None:
            self.write(f"SENS:POW:AC:RANG {range_dbm}")
            logger.info("Manual range: %.1f dBm", range_dbm)
        else:
            self.write("SENS:POW:AC:RANG:AUTO ON")
            logger.info("Auto-range enabled")
        self.wait_opc()

    # -- single-shot measurement ----------------------------------------------

    def measure_power(self) -> float:
        """Trigger a single measurement and return the result.

        Returns:
            Measured power in dBm.
        """
        result_str = self.query("MEAS?")
        power_dbm = float(result_str)
        logger.info("Measured power: %.3f dBm", power_dbm)
        return power_dbm

    # -- sensor zeroing -------------------------------------------------------

    def zero_sensor(self) -> None:
        """Zero (null) the power sensor.

        The RF signal **must** be removed from the sensor input before
        calling this method.
        """
        logger.info("Zeroing power sensor (ensure no RF input) ...")
        self.write("CAL:ZERO:AUTO ONCE")
        self.wait_opc()
        logger.info("Sensor zeroing complete")

    # -- averaging ------------------------------------------------------------

    def set_averaging(self, count: int) -> None:
        """Set the number of measurement averages.

        Args:
            count: Number of averages (1 disables averaging).
        """
        if count < 1:
            raise ValueError("Averaging count must be >= 1")
        logger.info("Setting averaging count to %d", count)
        if count == 1:
            self.write("SENS:AVER:STAT OFF")
        else:
            self.write("SENS:AVER:STAT ON")
            self.write(f"SENS:AVER:COUN {count}")
        self.wait_opc()

    # -- continuous measurement -----------------------------------------------

    def continuous_measure(
        self,
        callback: Callable[[float], None],
        interval_s: float = 0.5,
    ) -> None:
        """Start continuous power measurements in a background thread.

        Each reading is passed to *callback* as a ``float`` in dBm.
        Call :meth:`stop_continuous` to terminate the loop.

        Args:
            callback: Callable invoked with each power reading (dBm).
            interval_s: Delay between successive measurements in seconds.
        """
        if self._continuous_running:
            logger.warning("Continuous measurement already running")
            return

        self._continuous_running = True

        def _loop() -> None:
            logger.info("Continuous measurement started (interval=%.2fs)", interval_s)
            while self._continuous_running:
                try:
                    power = self.measure_power()
                    callback(power)
                except Exception:
                    logger.exception("Error during continuous measurement")
                time.sleep(interval_s)
            logger.info("Continuous measurement stopped")

        self._continuous_thread = threading.Thread(target=_loop, daemon=True)
        self._continuous_thread.start()

    def stop_continuous(self) -> None:
        """Stop the background continuous measurement loop."""
        self._continuous_running = False
        if self._continuous_thread is not None:
            self._continuous_thread.join(timeout=5.0)
            self._continuous_thread = None
