"""Unit test conftest - custom markers and CLI options for pytest."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Custom markers
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers used across the unit test suite."""
    config.addinivalue_line("markers", "safety: safety-critical functionality tests")
    config.addinivalue_line("markers", "calibration: calibration path verification tests")
    config.addinivalue_line("markers", "datapath: radar data-path logic tests")
    config.addinivalue_line("markers", "config: configuration parsing tests")
    config.addinivalue_line("markers", "slow: tests that take > 1 second")


# ---------------------------------------------------------------------------
# CLI options
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom CLI options for unit tests."""
    parser.addoption(
        "--board-config",
        action="store",
        default=None,
        help="Path to board configuration YAML file",
    )
    parser.addoption(
        "--device",
        action="store",
        default="AWR2944",
        help="Target device part number (default: AWR2944)",
    )
