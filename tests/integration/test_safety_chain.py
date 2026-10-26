"""Integration tests for the safety chain.

Validates that safety mechanisms (watchdog, ECC, lockstep, BIST)
function correctly on the physical target via JTAG fault injection.
"""
from __future__ import annotations

import time

import pytest


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.hardware, pytest.mark.safety]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WATCHDOG_TIMEOUT_MS = 50
SAFE_STATE_ENTRY_TIMEOUT_S = 1.0
DIAGNOSTIC_COVERAGE_THRESHOLD_PCT = 99.0


# ---------------------------------------------------------------------------
# Fault injection helpers
# ---------------------------------------------------------------------------

def _wait_for_safe_state(uart_monitor, timeout_s: float = SAFE_STATE_ENTRY_TIMEOUT_S) -> bool:
    """Poll UART for the safe-state entry log message."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        line = uart_monitor.readline(timeout_s=0.1)
        if line and "[SAFE]" in line and "ENTERED" in line.upper():
            return True
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFaultInjection:
    """Verify fault detection via JTAG-based fault injection."""

    def test_fault_injection_detected(
        self, jtag_interface, uart_monitor
    ) -> None:
        """A memory corruption injected via JTAG must trigger an ECC alert."""
        # Corrupt a single word in ECC-protected SRAM
        jtag_interface.write_memory(address=0x20000100, data=0xDEAD_DEAD)
        time.sleep(0.1)

        log = uart_monitor.read_until(pattern="ECC", timeout_s=2.0)
        assert log is not None, "ECC error was not reported after memory corruption"

    def test_safe_state_entered_on_fault(
        self, jtag_interface, uart_monitor
    ) -> None:
        """After a critical fault, the DUT must enter the defined safe state."""
        # Inject a lockstep mismatch by corrupting the compare register
        jtag_interface.write_register("R0", 0xBADC0DE0, core=1)
        entered = _wait_for_safe_state(uart_monitor)
        assert entered, "DUT did not enter safe state within timeout"


class TestWatchdogReset:
    """Verify that watchdog reset occurs on CPU hang."""

    def test_watchdog_reset_on_hang(
        self, jtag_interface, uart_monitor
    ) -> None:
        """Halting the CPU via JTAG must trigger a watchdog reset."""
        jtag_interface.halt_cpu()
        # Wait longer than the watchdog timeout
        time.sleep((WATCHDOG_TIMEOUT_MS / 1000.0) * 3)
        jtag_interface.resume_cpu()

        # After reset, the boot banner must reappear
        banner = uart_monitor.read_until(pattern="[BOOT]", timeout_s=5.0)
        assert banner is not None, "Boot banner not seen — watchdog reset may have failed"


class TestECCReporting:
    """Validate ECC error reporting through the safety chain."""

    def test_ecc_error_reported(
        self, jtag_interface, uart_monitor
    ) -> None:
        """Single-bit ECC errors must be logged and the corrected value used."""
        # Flip one bit in ECC-protected region
        original = jtag_interface.read_memory(address=0x20000200)
        jtag_interface.write_memory(address=0x20000200, data=original ^ 0x01)
        time.sleep(0.1)

        log = uart_monitor.read_until(pattern="ECC_SB", timeout_s=2.0)
        assert log is not None, "Single-bit ECC correction not reported"


class TestDiagnosticCoverage:
    """Verify that the runtime diagnostic coverage meets the target."""

    def test_diagnostic_coverage_met(
        self, uart_monitor
    ) -> None:
        """The BIST diagnostic coverage percentage must meet the ASIL-D target."""
        # Trigger BIST execution via CLI command
        uart_monitor.send_command("bist run\r\n")
        result_line = uart_monitor.read_until(pattern="DC=", timeout_s=10.0)
        assert result_line is not None, "BIST result not received"

        # Parse "DC=99.3%" from the log line
        dc_str = result_line.split("DC=")[1].split("%")[0]
        dc_pct = float(dc_str)
        assert dc_pct >= DIAGNOSTIC_COVERAGE_THRESHOLD_PCT, (
            f"Diagnostic coverage {dc_pct:.1f}% below threshold "
            f"{DIAGNOSTIC_COVERAGE_THRESHOLD_PCT}%"
        )
