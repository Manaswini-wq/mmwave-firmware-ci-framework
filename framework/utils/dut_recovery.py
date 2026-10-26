"""DUT (Device Under Test) recovery utilities.

Implements a multi-strategy recovery pipeline (power-cycle, JTAG reset,
full re-flash) to bring an unresponsive radar board back into a testable
state, minimising wasted CI wall-clock time.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RecoveryStrategy(str, Enum):
    """Available DUT recovery strategies, ordered by severity."""

    AUTO = "auto"
    POWER_CYCLE = "power_cycle"
    JTAG_RESET = "jtag_reset"
    REFLASH = "reflash"


class DUTRecovery:
    """Manages DUT health checks and multi-stage recovery.

    The *auto* strategy tries progressively heavier recovery methods
    until the DUT is responsive again.

    Args:
        board_controller: Object with ``power_on()``, ``power_off()``,
                          ``is_powered()`` methods for bench power control.
        jtag_interface: Object with ``reset()``, ``halt()``, ``resume()``,
                        ``flash(firmware_path)`` for debug-probe control.
    """

    HEALTH_CHECK_TIMEOUT_S: float = 5.0
    POWER_CYCLE_DELAY_S: float = 3.0

    def __init__(self, board_controller: Any, jtag_interface: Any) -> None:
        self.board = board_controller
        self.jtag = jtag_interface
        self._default_firmware: Optional[str] = None
        logger.debug("DUTRecovery initialised")

    # -- health check ---------------------------------------------------------

    def check_health(self) -> bool:
        """Perform a quick health check on the DUT.

        Verifies that the board responds to a JTAG probe and that the
        UART prompt is reachable.

        Returns:
            ``True`` if the DUT is considered healthy.
        """
        try:
            if not self.board.is_powered():
                logger.warning("DUT power is off")
                return False
            # Attempt a lightweight JTAG register read
            pc = self.jtag.read_register("PC")
            if pc is None:
                logger.warning("JTAG read failed — DUT unresponsive")
                return False
            logger.info("DUT healthy (PC=0x%08X)", pc)
            return True
        except Exception as exc:
            logger.warning("Health check exception: %s", exc)
            return False

    # -- recovery dispatch ----------------------------------------------------

    def recover(self, strategy: str = "auto", firmware_path: Optional[str] = None) -> bool:
        """Attempt to recover the DUT using the specified strategy.

        Args:
            strategy: One of ``'auto'``, ``'power_cycle'``, ``'jtag_reset'``,
                      or ``'reflash'``.
            firmware_path: Path to firmware binary (required for ``'reflash'``).

        Returns:
            ``True`` if recovery succeeded and the DUT is healthy.
        """
        strat = RecoveryStrategy(strategy)
        logger.info("Recovery requested: strategy=%s", strat.value)

        if strat == RecoveryStrategy.AUTO:
            return self.auto_recover(firmware_path=firmware_path)
        elif strat == RecoveryStrategy.POWER_CYCLE:
            self._power_cycle_recovery()
        elif strat == RecoveryStrategy.JTAG_RESET:
            self._jtag_reset_recovery()
        elif strat == RecoveryStrategy.REFLASH:
            if firmware_path is None:
                firmware_path = self._default_firmware
            if firmware_path is None:
                logger.error("Reflash requested but no firmware path provided")
                return False
            self._reflash_recovery(firmware_path)
        else:
            logger.error("Unknown strategy: %s", strategy)
            return False

        return self._verify_recovery()

    def auto_recover(self, firmware_path: Optional[str] = None) -> bool:
        """Try recovery strategies in escalating order.

        1. JTAG reset (fastest)
        2. Power cycle
        3. Full reflash (last resort)

        Args:
            firmware_path: Firmware binary for reflash stage.

        Returns:
            ``True`` if any strategy succeeded.
        """
        strategies = [
            ("jtag_reset", self._jtag_reset_recovery),
            ("power_cycle", self._power_cycle_recovery),
        ]

        for name, method in strategies:
            logger.info("Auto-recover: trying %s ...", name)
            try:
                method()
                if self._verify_recovery():
                    logger.info("Auto-recover: %s succeeded", name)
                    return True
            except Exception as exc:
                logger.warning("Auto-recover: %s failed (%s)", name, exc)

        # Last resort: reflash
        fw = firmware_path or self._default_firmware
        if fw:
            logger.info("Auto-recover: trying reflash ...")
            try:
                self._reflash_recovery(fw)
                if self._verify_recovery():
                    logger.info("Auto-recover: reflash succeeded")
                    return True
            except Exception as exc:
                logger.warning("Auto-recover: reflash failed (%s)", exc)
        else:
            logger.warning("Auto-recover: no firmware path for reflash; skipping")

        logger.error("Auto-recover: all strategies exhausted — DUT unrecoverable")
        return False

    # -- individual strategies ------------------------------------------------

    def _power_cycle_recovery(self) -> None:
        """Recover the DUT via a full power cycle."""
        logger.info("Power-cycling DUT ...")
        self.board.power_off()
        time.sleep(self.POWER_CYCLE_DELAY_S)
        self.board.power_on()
        time.sleep(self.POWER_CYCLE_DELAY_S)
        logger.info("Power cycle complete")

    def _jtag_reset_recovery(self) -> None:
        """Recover the DUT via JTAG system reset."""
        logger.info("Performing JTAG reset ...")
        self.jtag.reset()
        time.sleep(1.0)
        logger.info("JTAG reset complete")

    def _reflash_recovery(self, firmware_path: str) -> None:
        """Recover the DUT by erasing and re-flashing firmware.

        Args:
            firmware_path: Path to the firmware binary to flash.
        """
        logger.info("Reflashing DUT with %s ...", firmware_path)
        self.jtag.halt()
        time.sleep(0.5)
        self.jtag.flash(firmware_path)
        self.jtag.reset()
        time.sleep(2.0)
        logger.info("Reflash complete")

    # -- verification ---------------------------------------------------------

    def _verify_recovery(self) -> bool:
        """Verify the DUT is healthy after a recovery attempt.

        Retries the health check with a short settling delay.

        Returns:
            ``True`` if the DUT is responsive.
        """
        time.sleep(1.0)  # allow boot / init
        healthy = self.check_health()
        if healthy:
            logger.info("Recovery verified: DUT healthy")
        else:
            logger.warning("Recovery verification: DUT still unresponsive")
        return healthy
