"""Integration test conftest - hardware markers and shared fixtures."""
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register markers for integration tests that require hardware."""
    config.addinivalue_line("markers", "hardware: requires physical board connection")
    config.addinivalue_line("markers", "rf: requires RF instrumentation")
    config.addinivalue_line("markers", "safety: safety-chain integration tests")
    config.addinivalue_line("markers", "firmware_update: firmware flash / update tests")


@pytest.fixture(autouse=True)
def _skip_without_board(request: pytest.FixtureRequest) -> None:
    """Auto-skip hardware tests when no board config is available."""
    if request.node.get_closest_marker("hardware"):
        board_cfg = request.config.getoption("--board-config", default=None)
        if board_cfg is None:
            pytest.skip("Hardware test skipped — no --board-config provided")
