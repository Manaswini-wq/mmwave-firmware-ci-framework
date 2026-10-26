"""Tests for CRC-32 validation utilities.

Verifies the firmware CRC calculation against known vectors and
confirms that single-bit and burst errors are reliably detected.
"""
from __future__ import annotations

import struct

import pytest

from framework.utils.crc import crc32_compute, crc32_verify


# ---------------------------------------------------------------------------
# Known-vector tests
# ---------------------------------------------------------------------------

class TestCRC32KnownVectors:
    """CRC-32 output must match industry-standard test vectors."""

    @pytest.mark.parametrize(
        "data, expected_crc",
        [
            (b"123456789", 0xCBF43926),
            (b"", 0x00000000),
            (b"\x00" * 32, 0x190A55AD),
            (b"\xFF" * 32, 0xFF6CAB0B),
            (b"mmWave Radar Sensor", 0x7A3E117D),
        ],
        ids=["itu-standard", "empty", "all-zeros-32", "all-ones-32", "project-string"],
    )
    def test_crc32_known_vectors(self, data: bytes, expected_crc: int) -> None:
        """Computed CRC must match the reference value for known inputs."""
        assert crc32_compute(data) == expected_crc


# ---------------------------------------------------------------------------
# Error detection tests
# ---------------------------------------------------------------------------

class TestCRCErrorDetection:
    """CRC must detect single-bit and burst errors in firmware images."""

    def test_crc_detect_single_bit_error(self) -> None:
        """Flipping any single bit must cause CRC mismatch."""
        payload = b"Test payload for CRC single-bit error detection."
        original_crc = crc32_compute(payload)

        corrupted = bytearray(payload)
        # Flip bit 5 of byte 10
        corrupted[10] ^= 0x20
        assert crc32_compute(bytes(corrupted)) != original_crc

    def test_crc_detect_burst_error(self) -> None:
        """A burst error spanning multiple bytes must be detected."""
        payload = b"\xAB" * 256
        original_crc = crc32_compute(payload)

        corrupted = bytearray(payload)
        # Corrupt a 4-byte burst in the middle of the payload
        corrupted[128:132] = b"\x00\x00\x00\x00"
        assert crc32_compute(bytes(corrupted)) != original_crc

    def test_crc_empty_data(self) -> None:
        """CRC of empty data should be the standard initial value."""
        crc = crc32_compute(b"")
        assert isinstance(crc, int)
        assert crc == 0x00000000

    def test_crc_large_data(self) -> None:
        """CRC computation must handle payloads > 1 MiB without error."""
        large_payload = bytes(range(256)) * 4096  # 1 MiB
        crc = crc32_compute(large_payload)
        assert isinstance(crc, int)
        # Verify determinism
        assert crc32_compute(large_payload) == crc


# ---------------------------------------------------------------------------
# Verify round-trip
# ---------------------------------------------------------------------------

class TestCRCVerification:
    """Appended-CRC verification round-trip."""

    def test_verify_appended_crc(self) -> None:
        """Payload + appended CRC must pass verification."""
        payload = b"Firmware image section 0x08000000"
        crc = crc32_compute(payload)
        image = payload + struct.pack("<I", crc)
        assert crc32_verify(image) is True

    def test_verify_corrupted_image_fails(self) -> None:
        """Corrupted image must fail CRC verification."""
        payload = b"Firmware image section 0x08000000"
        crc = crc32_compute(payload)
        image = bytearray(payload + struct.pack("<I", crc))
        image[0] ^= 0x01  # corrupt first byte
        assert crc32_verify(bytes(image)) is False
