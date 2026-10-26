"""
Board Controller - Power, reset, and boot-mode control for target boards.

Abstracts GPIO and USB-relay based control of mmWave evaluation boards,
providing power cycling, boot-mode selection, and board health checks.
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Optional

from framework.targets.jtag_interface import JTAGInterface

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ResetMode(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    JTAG = "jtag"


class BootMode(str, Enum):
    SPI_FLASH = "spi_flash"
    UART_BOOT = "uart_boot"
    JTAG = "jtag"
    FUNCTIONAL = "functional"


# ---------------------------------------------------------------------------
# BoardController
# ---------------------------------------------------------------------------

class BoardController:
    """High-level board power, reset, and boot-mode management."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._board_name: str = config.get("name", "unknown")
        self._platform: str = config.get("platform", "unknown")

        # GPIO / relay pin mapping
        self._power_pin: int | None = config.get("pins", {}).get("power")
        self._reset_pin: int | None = config.get("pins", {}).get("reset")
        self._boot_mode_pins: dict[str, int] = config.get("pins", {}).get("boot_mode", {})

        # USB relay config (vid:pid or relay ID)
        self._relay_device: str | None = config.get("usb_relay", {}).get("device")
        self._relay_channel: int = config.get("usb_relay", {}).get("channel", 1)

        # JTAG interface (optional — injected later or created here)
        self._jtag: JTAGInterface | None = None
        jtag_cfg = config.get("jtag")
        if jtag_cfg:
            self._jtag = JTAGInterface(
                backend=jtag_cfg.get("backend", "openocd"),
                config=jtag_cfg,
            )

        self._powered = False

    # ------------------------------------------------------------------
    # Power control
    # ------------------------------------------------------------------

    def power_on(self) -> None:
        """Apply power to the target board."""
        logger.info("Powering ON board '%s'", self._board_name)
        if self._relay_device:
            self._usb_relay_control(self._relay_channel, state=True)
        elif self._power_pin is not None:
            self._gpio_control(self._power_pin, state=True)
        else:
            logger.warning("No power-control method configured — assuming board is powered")
        self._powered = True
        # Allow voltage rails to settle
        settle_time = float(self._config.get("power_settle_s", 0.5))
        time.sleep(settle_time)
        logger.info("Board '%s' powered ON", self._board_name)

    def power_off(self) -> None:
        """Remove power from the target board."""
        logger.info("Powering OFF board '%s'", self._board_name)
        if self._relay_device:
            self._usb_relay_control(self._relay_channel, state=False)
        elif self._power_pin is not None:
            self._gpio_control(self._power_pin, state=False)
        self._powered = False
        logger.info("Board '%s' powered OFF", self._board_name)

    def power_cycle(self, delay_s: float = 2.0) -> None:
        """Power-cycle the board with a configurable off-duration."""
        logger.info("Power-cycling board '%s' (delay=%.1fs)", self._board_name, delay_s)
        self.power_off()
        time.sleep(delay_s)
        self.power_on()

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self, mode: str | ResetMode = ResetMode.HARD) -> None:
        """Reset the board using the specified mode."""
        mode = ResetMode(mode)
        logger.info("Resetting board '%s' (mode=%s)", self._board_name, mode.value)

        if mode == ResetMode.HARD:
            if self._reset_pin is not None:
                self._gpio_control(self._reset_pin, state=False)
                time.sleep(0.1)
                self._gpio_control(self._reset_pin, state=True)
            else:
                # Fall back to power-cycle
                self.power_cycle(delay_s=1.0)

        elif mode == ResetMode.SOFT:
            if self._jtag and self._jtag.is_connected:
                # Write to the Cortex-R AIRCR register to request a system reset
                import struct
                aircr_addr = 0xE000ED0C
                reset_val = 0x05FA0004  # SYSRESETREQ
                self._jtag.write_memory(aircr_addr, struct.pack("<I", reset_val))
            else:
                logger.warning("Soft reset requires JTAG — falling back to hard reset")
                self.reset(ResetMode.HARD)

        elif mode == ResetMode.JTAG:
            if self._jtag and self._jtag.is_connected:
                self._jtag.reset(halt=True)
            else:
                logger.error("JTAG reset requested but JTAG is not connected")

    # ------------------------------------------------------------------
    # Boot mode
    # ------------------------------------------------------------------

    def select_boot_mode(self, mode: str | BootMode) -> None:
        """Configure boot-mode pins/straps before reset."""
        mode = BootMode(mode)
        pin = self._boot_mode_pins.get(mode.value)
        if pin is not None:
            logger.info("Selecting boot mode '%s' (pin %d)", mode.value, pin)
            self._gpio_control(pin, state=True)
            # Deassert other boot mode pins
            for bm, p in self._boot_mode_pins.items():
                if bm != mode.value:
                    self._gpio_control(p, state=False)
        else:
            logger.warning("Boot mode '%s' has no pin mapping — manual configuration may be required", mode.value)

    # ------------------------------------------------------------------
    # Board info / health
    # ------------------------------------------------------------------

    def get_board_info(self) -> dict[str, Any]:
        """Read board identity and silicon revision via JTAG."""
        info: dict[str, Any] = {
            "board": self._board_name,
            "platform": self._platform,
            "powered": self._powered,
        }

        if self._jtag and self._jtag.is_connected:
            try:
                import struct
                # TI device ID register (typical for AWR/IWR devices)
                dev_id_raw = self._jtag.read_memory(0xFFFFE1F0, 4)
                dev_id = struct.unpack("<I", dev_id_raw)[0] if len(dev_id_raw) >= 4 else 0
                info["device_id"] = f"0x{dev_id:08X}"
                info["silicon_rev"] = (dev_id >> 28) & 0xF
            except Exception:
                logger.debug("Could not read device ID via JTAG")

        return info

    def is_responsive(self) -> bool:
        """Check whether the board responds to JTAG commands."""
        if not self._powered:
            return False
        if self._jtag is None:
            logger.warning("No JTAG interface configured — cannot check responsiveness")
            return self._powered  # optimistic

        try:
            if not self._jtag.is_connected:
                self._jtag.connect()
            # Try reading the PC register
            pc = self._jtag.read_register("pc")
            return pc != 0
        except Exception:
            logger.debug("Board not responsive")
            return False

    # ------------------------------------------------------------------
    # Low-level GPIO / relay
    # ------------------------------------------------------------------

    @staticmethod
    def _gpio_control(pin: int, state: bool) -> None:
        """Set a GPIO pin HIGH (True) or LOW (False).

        In production, this interfaces with ``libgpiod``, ``sysfs``, or a
        USB-to-GPIO adapter. Here we log the intended action.
        """
        logger.debug("GPIO pin %d -> %s", pin, "HIGH" if state else "LOW")
        # Platform-specific implementation would go here:
        # e.g. gpiod.Line.set_value() on Linux, FTDI bitbang on Windows

    @staticmethod
    def _usb_relay_control(relay_id: int, state: bool) -> None:
        """Control a USB relay module channel.

        Typical modules use HID commands (e.g. LCUS-1 / SainSmart).
        """
        action = "ON" if state else "OFF"
        logger.debug("USB relay channel %d -> %s", relay_id, action)
        # In production: open HID device and send control report
