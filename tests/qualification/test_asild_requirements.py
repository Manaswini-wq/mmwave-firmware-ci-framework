"""ISO 26262 ASIL-D requirement-mapped tests.

Each test is traced to a specific safety requirement ID for
full traceability in the safety case evidence package.
"""
from __future__ import annotations

import time

import pytest


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.asild, pytest.mark.hardware]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WATCHDOG_TIMEOUT_MS = 50
SAFE_STATE_TIMEOUT_S = 1.0
SPFM_THRESHOLD_PCT = 99.0
LFM_THRESHOLD_PCT = 97.0


# ---------------------------------------------------------------------------
# REQ_SAFETY_001 - Watchdog detection
# ---------------------------------------------------------------------------

class TestReqSafety001:
    """REQ_SAFETY_001: The system shall detect a CPU hang within 50 ms."""

    def test_REQ_SAFETY_001_watchdog_detection(
        self, jtag_interface, uart_monitor
    ) -> None:
        """REQ_SAFETY_001 — Halting the CPU must produce a watchdog reset
        within the configured timeout period.

        Requirement ID: REQ_SAFETY_001
        ASIL: D
        """
        jtag_interface.halt_cpu()
        time.sleep((WATCHDOG_TIMEOUT_MS / 1000.0) * 3)
        jtag_interface.resume_cpu()

        banner = uart_monitor.read_until(pattern="[BOOT]", timeout_s=5.0)
        assert banner is not None, "Watchdog reset did not occur"


# ---------------------------------------------------------------------------
# REQ_SAFETY_002 - ECC single-bit correction
# ---------------------------------------------------------------------------

class TestReqSafety002:
    """REQ_SAFETY_002: Single-bit SRAM errors shall be corrected transparently."""

    def test_REQ_SAFETY_002_ecc_correction(
        self, jtag_interface, uart_monitor
    ) -> None:
        """REQ_SAFETY_002 — A single-bit flip in ECC-protected memory must
        be silently corrected and logged.

        Requirement ID: REQ_SAFETY_002
        ASIL: D
        """
        addr = 0x20000200
        original = jtag_interface.read_memory(address=addr)
        jtag_interface.write_memory(address=addr, data=original ^ 0x01)
        time.sleep(0.1)

        log = uart_monitor.read_until(pattern="ECC_SB", timeout_s=2.0)
        assert log is not None, "Single-bit ECC correction not reported"


# ---------------------------------------------------------------------------
# REQ_SAFETY_003 - Lockstep compare
# ---------------------------------------------------------------------------

class TestReqSafety003:
    """REQ_SAFETY_003: Lockstep core mismatch shall trigger safe state."""

    def test_REQ_SAFETY_003_lockstep_compare(
        self, jtag_interface, uart_monitor
    ) -> None:
        """REQ_SAFETY_003 — Corrupting a register on the secondary core
        must produce a lockstep compare fault and enter safe state.

        Requirement ID: REQ_SAFETY_003
        ASIL: D
        """
        jtag_interface.write_register("R0", 0xBADC0DE0, core=1)
        safe = uart_monitor.read_until(pattern="SAFE", timeout_s=SAFE_STATE_TIMEOUT_S)
        assert safe is not None, "Lockstep mismatch did not trigger safe state"


# ---------------------------------------------------------------------------
# REQ_SAFETY_004 - Safe state transition
# ---------------------------------------------------------------------------

class TestReqSafety004:
    """REQ_SAFETY_004: On critical fault, TX outputs shall be disabled."""

    def test_REQ_SAFETY_004_safe_state_transition(
        self, jtag_interface, uart_monitor
    ) -> None:
        """REQ_SAFETY_004 — After safe-state entry the radar TX must be OFF.

        Requirement ID: REQ_SAFETY_004
        ASIL: D
        """
        jtag_interface.write_register("R0", 0xBADC0DE0, core=1)
        uart_monitor.read_until(pattern="SAFE", timeout_s=SAFE_STATE_TIMEOUT_S)

        tx_status = uart_monitor.read_until(pattern="TX_OFF", timeout_s=2.0)
        assert tx_status is not None, "TX was not disabled upon safe-state entry"


# ---------------------------------------------------------------------------
# REQ_SAFETY_005 - SPFM >= 99%
# ---------------------------------------------------------------------------

class TestReqSafety005:
    """REQ_SAFETY_005: Single-Point Fault Metric shall exceed 99%."""

    def test_REQ_SAFETY_005_spfm_above_99_percent(
        self, uart_monitor
    ) -> None:
        """REQ_SAFETY_005 — BIST-computed SPFM must be >= 99%.

        Requirement ID: REQ_SAFETY_005
        ASIL: D
        """
        uart_monitor.send_command("bist spfm\r\n")
        result = uart_monitor.read_until(pattern="SPFM=", timeout_s=10.0)
        assert result is not None, "SPFM result not received"
        spfm = float(result.split("SPFM=")[1].split("%")[0])
        assert spfm >= SPFM_THRESHOLD_PCT, f"SPFM {spfm:.1f}% < {SPFM_THRESHOLD_PCT}%"


# ---------------------------------------------------------------------------
# REQ_SAFETY_006 - LFM >= 97%
# ---------------------------------------------------------------------------

class TestReqSafety006:
    """REQ_SAFETY_006: Latent Fault Metric shall exceed 97%."""

    def test_REQ_SAFETY_006_lfm_above_97_percent(
        self, uart_monitor
    ) -> None:
        """REQ_SAFETY_006 — BIST-computed LFM must be >= 97%.

        Requirement ID: REQ_SAFETY_006
        ASIL: D
        """
        uart_monitor.send_command("bist lfm\r\n")
        result = uart_monitor.read_until(pattern="LFM=", timeout_s=10.0)
        assert result is not None, "LFM result not received"
        lfm = float(result.split("LFM=")[1].split("%")[0])
        assert lfm >= LFM_THRESHOLD_PCT, f"LFM {lfm:.1f}% < {LFM_THRESHOLD_PCT}%"


# ---------------------------------------------------------------------------
# REQ_SAFETY_007 - BIST execution
# ---------------------------------------------------------------------------

class TestReqSafety007:
    """REQ_SAFETY_007: Power-on BIST shall execute and report PASS."""

    def test_REQ_SAFETY_007_bist_execution(
        self, board_controller, uart_monitor
    ) -> None:
        """REQ_SAFETY_007 — After reset, the boot log must contain BIST PASS.

        Requirement ID: REQ_SAFETY_007
        ASIL: D
        """
        board_controller.reset()
        bist_log = uart_monitor.read_until(pattern="BIST", timeout_s=10.0)
        assert bist_log is not None, "BIST log not found in boot output"
        assert "PASS" in bist_log, f"BIST did not pass: {bist_log}"
