"""Board hardware fixtures for firmware test sessions."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Board controller fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def board_controller(request):
    """Initialize board controller for the test session."""
    from framework.targets.board_controller import BoardController

    config = request.config.getoption("--board-config", default=None)
    if config is None:
        pytest.skip("No board config provided (--board-config)")
    controller = BoardController(config)
    controller.power_on()
    yield controller
    controller.power_off()


# ---------------------------------------------------------------------------
# JTAG interface fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def jtag_interface(board_controller):
    """JTAG interface connected to the DUT."""
    from framework.targets.jtag_interface import JTAGInterface

    jtag = JTAGInterface(backend="openocd", config=board_controller.config)
    jtag.connect()
    yield jtag
    jtag.disconnect()


# ---------------------------------------------------------------------------
# UART monitor fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def uart_monitor(board_controller):
    """UART serial monitor for capturing DUT log output."""
    from framework.targets.uart_monitor import UARTMonitor

    port = board_controller.config.get("uart_port", "COM3")
    baud = board_controller.config.get("uart_baud", 115200)
    monitor = UARTMonitor(port=port, baudrate=baud)
    monitor.open()
    yield monitor
    monitor.close()


# ---------------------------------------------------------------------------
# Flash programmer fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def flash_programmer(jtag_interface, board_controller):
    """Flash programmer wired through the active JTAG interface."""
    from framework.targets.flash_programmer import FlashProgrammer

    programmer = FlashProgrammer(
        jtag=jtag_interface,
        device=board_controller.config.get("device", "AWR2944"),
    )
    yield programmer


# ---------------------------------------------------------------------------
# Trace collector fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def trace_collector(jtag_interface):
    """SWO / ETM trace collector for code-coverage and profiling."""
    from framework.targets.trace_collector import TraceCollector

    collector = TraceCollector(jtag=jtag_interface, protocol="swo")
    collector.start()
    yield collector
    collector.stop()
    collector.flush()


# ---------------------------------------------------------------------------
# Radar configurator fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def radar_configurator(uart_monitor):
    """Radar chirp / frame configurator that speaks the DUT CLI protocol."""
    from framework.radar.configurator import RadarConfigurator

    configurator = RadarConfigurator(transport=uart_monitor)
    configurator.reset_to_defaults()
    yield configurator
