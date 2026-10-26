"""
UART Monitor - Serial log monitoring with pattern matching.

Captures UART output from the target board in a background thread,
supports regex-based pattern waiting and timestamped log retrieval.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

try:
    import serial  # pyserial

    _HAS_SERIAL = True
except ImportError:
    _HAS_SERIAL = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    """A single timestamped log line."""
    timestamp: float
    text: str


# ---------------------------------------------------------------------------
# UARTMonitor
# ---------------------------------------------------------------------------

class UARTMonitor:
    """Background UART log capture with pattern matching."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.1,
        max_buffer_lines: int = 50_000,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._max_buffer = max_buffer_lines

        self._serial: Optional[Any] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._log: deque[LogEntry] = deque(maxlen=max_buffer_lines)
        self._pattern_event: threading.Event = threading.Event()
        self._pattern_match: Optional[re.Match[str]] = None
        self._active_pattern: Optional[re.Pattern[str]] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the serial port and begin monitoring in a background thread."""
        if not _HAS_SERIAL:
            raise RuntimeError("pyserial is not installed — run: pip install pyserial")
        if self._running:
            logger.warning("UART monitor already running on %s", self._port)
            return

        self._serial = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            timeout=self._timeout,
        )
        self._running = True
        self._thread = threading.Thread(target=self._reader_thread, daemon=True, name="uart-monitor")
        self._thread.start()
        logger.info("UART monitor started on %s @ %d baud", self._port, self._baudrate)

    def stop(self) -> None:
        """Stop the background reader and close the serial port."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        if self._serial and self._serial.is_open:
            self._serial.close()
        logger.info("UART monitor stopped")

    # ------------------------------------------------------------------
    # Pattern matching
    # ------------------------------------------------------------------

    def wait_for_pattern(self, pattern: str, timeout: float = 30.0) -> re.Match[str] | None:
        """Block until *pattern* (regex) appears in UART output or *timeout* expires.

        Returns the ``re.Match`` object on success, ``None`` on timeout.
        """
        compiled = re.compile(pattern)

        # First scan existing buffer
        with self._lock:
            for entry in self._log:
                m = compiled.search(entry.text)
                if m:
                    logger.debug("Pattern '%s' found in buffered log", pattern)
                    return m

        # Set up live matching
        self._pattern_event.clear()
        self._pattern_match = None
        self._active_pattern = compiled

        found = self._pattern_event.wait(timeout=timeout)
        self._active_pattern = None

        if found and self._pattern_match:
            logger.debug("Pattern '%s' matched", pattern)
            return self._pattern_match

        logger.warning("Pattern '%s' not found within %.1fs", pattern, timeout)
        return None

    # ------------------------------------------------------------------
    # Log retrieval
    # ------------------------------------------------------------------

    def get_log(self) -> str:
        """Return the full captured log as a single string."""
        with self._lock:
            return "\n".join(entry.text for entry in self._log)

    def get_log_since(self, timestamp: float) -> str:
        """Return log lines captured after *timestamp* (monotonic seconds)."""
        with self._lock:
            return "\n".join(entry.text for entry in self._log if entry.timestamp >= timestamp)

    def flush(self) -> None:
        """Clear the log buffer."""
        with self._lock:
            self._log.clear()
        logger.debug("UART log buffer flushed")

    # ------------------------------------------------------------------
    # Background reader
    # ------------------------------------------------------------------

    def _reader_thread(self) -> None:
        """Continuously read lines from the serial port."""
        logger.debug("UART reader thread started")
        line_buffer = ""
        while self._running:
            try:
                if self._serial is None or not self._serial.is_open:
                    break
                raw = self._serial.read(self._serial.in_waiting or 1)
                if not raw:
                    continue
                text = raw.decode("ascii", errors="replace")
                line_buffer += text
                while "\n" in line_buffer:
                    line, line_buffer = line_buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    entry = LogEntry(timestamp=time.monotonic(), text=line)
                    with self._lock:
                        self._log.append(entry)

                    # Live pattern match check
                    if self._active_pattern:
                        m = self._active_pattern.search(line)
                        if m:
                            self._pattern_match = m
                            self._pattern_event.set()

            except Exception:
                if self._running:
                    logger.exception("Error in UART reader thread")
                    time.sleep(0.5)

        logger.debug("UART reader thread exiting")
