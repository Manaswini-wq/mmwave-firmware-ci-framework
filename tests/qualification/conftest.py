"""Qualification test conftest - safety-certification markers and guards."""
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register markers for qualification / certification tests."""
    config.addinivalue_line("markers", "asild: ISO 26262 ASIL-D requirement tests")
    config.addinivalue_line("markers", "sil3: IEC 61508 SIL-3 requirement tests")
    config.addinivalue_line("markers", "rf_spec: RF specification compliance tests")
    config.addinivalue_line("markers", "hardware: requires physical board connection")


@pytest.fixture(autouse=True)
def _require_hardware(request: pytest.FixtureRequest) -> None:
    """All qualification tests require a live hardware target."""
    board_cfg = request.config.getoption("--board-config", default=None)
    if board_cfg is None:
        pytest.skip("Qualification tests require --board-config")
