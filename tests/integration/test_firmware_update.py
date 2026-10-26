"""Integration tests for firmware update (flash / boot / rollback).

Validates the firmware update flow including flashing a new image,
verifying boot-up, and rolling back on corruption.
"""
from __future__ import annotations

import time

import pytest

from framework.utils.crc import crc32_compute


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.hardware, pytest.mark.firmware_update]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOOT_TIMEOUT_S = 10.0
EXPECTED_FW_VERSION = "2.4.1"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFlashAndBoot:
    """Verify flashing a valid firmware image and subsequent boot."""

    def test_flash_and_boot(
        self, flash_programmer, uart_monitor, board_controller
    ) -> None:
        """Flashing a valid image must result in a successful boot banner."""
        fw_path = board_controller.config.get("firmware_image")
        assert fw_path is not None, "firmware_image not set in board config"

        flash_programmer.erase()
        flash_programmer.program(fw_path)
        flash_programmer.verify(fw_path)

        board_controller.reset()
        banner = uart_monitor.read_until(pattern="[BOOT]", timeout_s=BOOT_TIMEOUT_S)
        assert banner is not None, "Boot banner not seen after flash"


class TestVersionVerification:
    """Verify the firmware version string after update."""

    def test_version_after_update(
        self, uart_monitor, board_controller
    ) -> None:
        """The UART boot banner must contain the expected firmware version."""
        board_controller.reset()
        banner = uart_monitor.read_until(pattern="[BOOT]", timeout_s=BOOT_TIMEOUT_S)
        assert banner is not None, "Boot banner not received"
        assert EXPECTED_FW_VERSION in banner, (
            f"Expected version {EXPECTED_FW_VERSION} not found in banner: {banner}"
        )


class TestRollback:
    """Verify rollback behaviour when a corrupt image is flashed."""

    def test_rollback_on_corrupt_image(
        self, flash_programmer, uart_monitor, board_controller
    ) -> None:
        """Flashing a corrupted image must trigger rollback to the golden copy.

        The DUT bootloader should detect the CRC mismatch, reject the
        primary image, and fall back to the golden (factory) image.
        """
        fw_path = board_controller.config.get("firmware_image")
        assert fw_path is not None

        # Read original image bytes and corrupt the last 4 KB
        with open(fw_path, "rb") as fh:
            image_data = bytearray(fh.read())
        image_data[-4096:] = b"\xFF" * 4096

        corrupt_path = fw_path + ".corrupt"
        with open(corrupt_path, "wb") as fh:
            fh.write(image_data)

        flash_programmer.erase()
        flash_programmer.program(corrupt_path)

        board_controller.reset()
        # Expect rollback message instead of normal boot
        rollback_msg = uart_monitor.read_until(
            pattern="ROLLBACK", timeout_s=BOOT_TIMEOUT_S
        )
        assert rollback_msg is not None, (
            "Rollback message not seen — DUT may have booted corrupt image"
        )

        # After rollback, the golden image should boot
        banner = uart_monitor.read_until(pattern="[BOOT]", timeout_s=BOOT_TIMEOUT_S)
        assert banner is not None, "Golden image did not boot after rollback"
