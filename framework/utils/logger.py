"""Structured logging configuration for the CI framework.

Provides JSON-formatted file logging with colour-coded console output
(via ``colorama``) for human readability during interactive sessions.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import colorama
    colorama.init(autoreset=True)
    _HAS_COLORAMA = True
except ImportError:
    _HAS_COLORAMA = False


# -- colour map ---------------------------------------------------------------

_LEVEL_COLORS = {
    "DEBUG": "\033[36m",     # Cyan
    "INFO": "\033[32m",      # Green
    "WARNING": "\033[33m",   # Yellow
    "ERROR": "\033[31m",     # Red
    "CRITICAL": "\033[1;31m",  # Bold Red
}
_RESET = "\033[0m"


# -- formatters ---------------------------------------------------------------

class LogFormatter(logging.Formatter):
    """Structured JSON log formatter.

    Each log record is emitted as a single JSON line containing
    ``timestamp``, ``level``, ``logger``, ``message``, and optional
    ``exc_info``.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


class _ColorConsoleFormatter(logging.Formatter):
    """Colour-coded console formatter for human-readable output."""

    FMT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self.FMT, datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        if _HAS_COLORAMA:
            colour = _LEVEL_COLORS.get(record.levelname, "")
            return f"{colour}{formatted}{_RESET}"
        return formatted


# -- public API ---------------------------------------------------------------

def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    console: bool = True,
) -> None:
    """Configure the root logger for the framework.

    Args:
        level: Logging level name (``'DEBUG'``, ``'INFO'``, etc.).
        log_file: Optional path to a JSON log file.  Parent directories
                  are created automatically.
        console: Whether to attach a colour-coded console handler.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(_ColorConsoleFormatter())
        root.addHandler(console_handler)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(path), encoding="utf-8")
        file_handler.setFormatter(LogFormatter())
        root.addHandler(file_handler)

    logging.getLogger(__name__).debug("Logging initialised: level=%s, file=%s, console=%s",
                                       level, log_file, console)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger within the framework hierarchy.

    Args:
        name: Logger name (conventionally ``__name__``).

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
