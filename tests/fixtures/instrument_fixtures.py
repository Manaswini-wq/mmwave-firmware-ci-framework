"""Lab instrument fixtures for RF performance validation."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Spectrum analyzer fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def spectrum_analyzer(request):
    """Keysight / R&S spectrum analyzer connected via VISA."""
    from framework.instruments.spectrum_analyzer import SpectrumAnalyzer

    visa_addr = request.config.getoption("--sa-address", default=None)
    if visa_addr is None:
        pytest.skip("No spectrum analyzer address provided (--sa-address)")
    sa = SpectrumAnalyzer(visa_address=visa_addr)
    sa.connect()
    sa.reset()
    yield sa
    sa.disconnect()


# ---------------------------------------------------------------------------
# Signal generator fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def signal_generator(request):
    """Signal generator for injecting known RF stimuli."""
    from framework.instruments.signal_generator import SignalGenerator

    visa_addr = request.config.getoption("--sg-address", default=None)
    if visa_addr is None:
        pytest.skip("No signal generator address provided (--sg-address)")
    sg = SignalGenerator(visa_address=visa_addr)
    sg.connect()
    sg.reset()
    yield sg
    sg.disconnect()


# ---------------------------------------------------------------------------
# Power meter fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def power_meter(request):
    """RF power meter for TX output power measurements."""
    from framework.instruments.power_meter import PowerMeter

    visa_addr = request.config.getoption("--pm-address", default=None)
    if visa_addr is None:
        pytest.skip("No power meter address provided (--pm-address)")
    pm = PowerMeter(visa_address=visa_addr)
    pm.connect()
    pm.zero()
    yield pm
    pm.disconnect()


# ---------------------------------------------------------------------------
# Logic analyzer fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def logic_analyzer(request):
    """Logic analyzer for digital timing verification."""
    from framework.instruments.logic_analyzer import LogicAnalyzer

    visa_addr = request.config.getoption("--la-address", default=None)
    if visa_addr is None:
        pytest.skip("No logic analyzer address provided (--la-address)")
    la = LogicAnalyzer(visa_address=visa_addr)
    la.connect()
    la.configure_channels(channels=[0, 1, 2, 3], sample_rate_mhz=200)
    yield la
    la.disconnect()
