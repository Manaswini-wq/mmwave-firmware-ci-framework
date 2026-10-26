"""Base SCPI instrument class for spectrum analyzers, signal generators, power meters.

Provides a reusable abstraction over pyvisa for VISA resource management,
connection lifecycle, SCPI command/query execution, and standard IEEE 488.2
common commands (*IDN?, *RST, *OPC?, SYST:ERR?).
"""

from __future__ import annotations

import logging
from typing import Optional

import pyvisa
import numpy as np

logger = logging.getLogger(__name__)


class SCPIInstrument:
    """Base class for SCPI-controlled lab instruments.

    Manages the VISA resource lifecycle, provides convenience wrappers for
    SCPI write/query operations, and implements context-manager support so
    instruments are released deterministically.

    Args:
        resource_string: VISA resource address, e.g. ``"TCPIP0::192.168.1.10::inst0::INSTR"``.
        timeout_ms: Default I/O timeout in milliseconds.
    """

    def __init__(self, resource_string: str, timeout_ms: int = 5000) -> None:
        self.resource_string: str = resource_string
        self.timeout_ms: int = timeout_ms
        self._rm: Optional[pyvisa.ResourceManager] = None
        self._inst: Optional[pyvisa.resources.MessageBasedResource] = None
        self._connected: bool = False
        logger.debug("SCPIInstrument created for %s (timeout=%d ms)", resource_string, timeout_ms)

    # -- connection lifecycle -------------------------------------------------

    def connect(self) -> None:
        """Open the VISA session to the instrument."""
        logger.info("Connecting to %s ...", self.resource_string)
        self._rm = pyvisa.ResourceManager()
        self._inst = self._rm.open_resource(self.resource_string)
        self._inst.timeout = self.timeout_ms
        self._connected = True
        idn = self.identify()
        logger.info("Connected: %s", idn)

    def disconnect(self) -> None:
        """Close the VISA session and release resources."""
        if self._inst is not None:
            try:
                self._inst.close()
                logger.info("Disconnected from %s", self.resource_string)
            except pyvisa.VisaIOError as exc:
                logger.warning("Error during disconnect: %s", exc)
            finally:
                self._inst = None
        if self._rm is not None:
            self._rm.close()
            self._rm = None
        self._connected = False

    # -- context manager ------------------------------------------------------

    def __enter__(self) -> "SCPIInstrument":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.disconnect()

    # -- low-level I/O --------------------------------------------------------

    def write(self, command: str) -> None:
        """Send an SCPI command string to the instrument.

        Args:
            command: SCPI command, e.g. ``"FREQ:CENT 1 GHz"``.
        """
        self._validate_connection()
        logger.debug("WRITE >>> %s", command)
        self._inst.write(command)  # type: ignore[union-attr]

    def query(self, command: str) -> str:
        """Send a query and return the stripped response string.

        Args:
            command: SCPI query ending with ``?``.

        Returns:
            Instrument response with leading/trailing whitespace removed.
        """
        self._validate_connection()
        logger.debug("QUERY >>> %s", command)
        response: str = self._inst.query(command).strip()  # type: ignore[union-attr]
        logger.debug("QUERY <<< %s", response)
        return response

    def query_binary(self, command: str, datatype: str = "f") -> np.ndarray:
        """Send a query and read the response as IEEE 488.2 binary block data.

        Args:
            command: SCPI query that returns binary data.
            datatype: Data format character (``'f'`` = 32-bit float, ``'d'`` = 64-bit).

        Returns:
            Numpy array of decoded values.
        """
        self._validate_connection()
        logger.debug("QUERY_BINARY >>> %s", command)
        raw = self._inst.query_binary_values(command, datatype=datatype)  # type: ignore[union-attr]
        return np.array(raw)

    # -- IEEE 488.2 common commands -------------------------------------------

    def identify(self) -> str:
        """Return the instrument identification string (*IDN?)."""
        return self.query("*IDN?")

    def reset(self) -> None:
        """Reset the instrument to factory defaults (*RST)."""
        logger.info("Resetting %s", self.resource_string)
        self.write("*RST")
        self.wait_opc()

    def wait_opc(self) -> None:
        """Block until all pending operations complete (*OPC?)."""
        self.query("*OPC?")

    def check_errors(self) -> list[str]:
        """Read and return all queued instrument errors via ``SYST:ERR?``.

        Returns:
            List of error strings. An empty list means no errors.
        """
        errors: list[str] = []
        while True:
            resp = self.query("SYST:ERR?")
            if resp.startswith("0,") or resp.startswith("+0,"):
                break
            errors.append(resp)
            logger.warning("Instrument error: %s", resp)
        return errors

    # -- internal helpers -----------------------------------------------------

    def _validate_connection(self) -> None:
        """Raise if the instrument session is not open."""
        if not self._connected or self._inst is None:
            raise RuntimeError(
                f"Not connected to {self.resource_string}. Call connect() first."
            )
