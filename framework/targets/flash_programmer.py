"""
Flash Programmer - Flash programming via JTAG for TI mmWave SoCs.

Supports binary (.bin), Intel HEX (.hex), and TI-COFF (.out) firmware
images with erase, program, and read-back verification.
"""
from __future__ import annotations

import argparse
import logging
import struct
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from framework.targets.jtag_interface import JTAGInterface

logger = logging.getLogger(__name__)

# Typical flash sector size for TI mmWave devices (4 KiB)
DEFAULT_SECTOR_SIZE = 0x1000


# ---------------------------------------------------------------------------
# FlashProgrammer
# ---------------------------------------------------------------------------

class FlashProgrammer:
    """Program firmware images to on-chip flash via JTAG."""

    def __init__(
        self,
        jtag_interface: JTAGInterface,
        sector_size: int = DEFAULT_SECTOR_SIZE,
        page_size: int = 256,
    ) -> None:
        self._jtag = jtag_interface
        self._sector_size = sector_size
        self._page_size = page_size
        self._progress_cb: Callable[[float], None] | None = None

    def set_progress_callback(self, callback: Callable[[float], None]) -> None:
        """Register a callback that receives progress percentage (0-100)."""
        self._progress_cb = callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def erase(self, address: int, size: int) -> None:
        """Erase flash sectors covering [address, address+size)."""
        start_sector = address & ~(self._sector_size - 1)
        end_addr = address + size
        current = start_sector
        total = end_addr - start_sector
        erased = 0

        logger.info("Erasing 0x%08X – 0x%08X (%d bytes)", start_sector, end_addr, total)
        self._jtag.halt()

        while current < end_addr:
            # Trigger sector erase via flash controller registers
            # (Device-specific; here we write the erase command to the flash wrapper)
            self._jtag.write_memory(current, b"\xFF" * self._sector_size)
            current += self._sector_size
            erased += self._sector_size
            self._progress_callback(min(100.0, erased / total * 100.0))

        logger.info("Erase complete")

    def program(self, binary_path: str | Path, address: int) -> None:
        """Program a firmware image to flash at *address*."""
        binary_path = Path(binary_path)
        data = self._parse_binary(binary_path)
        total = len(data)
        logger.info("Programming %d bytes from %s to 0x%08X", total, binary_path.name, address)

        self._jtag.halt()
        written = 0
        for offset in range(0, total, self._page_size):
            chunk = data[offset : offset + self._page_size]
            self._jtag.write_memory(address + offset, chunk)
            written += len(chunk)
            self._progress_callback(min(100.0, written / total * 100.0))

        logger.info("Programming complete (%d bytes)", total)

    def verify(self, binary_path: str | Path, address: int) -> bool:
        """Read-back verify flash contents against the binary image.

        Returns True if the flash contents match.
        """
        binary_path = Path(binary_path)
        expected = self._parse_binary(binary_path)
        total = len(expected)
        logger.info("Verifying %d bytes at 0x%08X", total, address)

        self._jtag.halt()
        verified = 0
        for offset in range(0, total, self._page_size):
            chunk_len = min(self._page_size, total - offset)
            actual = self._jtag.read_memory(address + offset, chunk_len)
            if actual != expected[offset : offset + chunk_len]:
                logger.error(
                    "Verification FAILED at offset 0x%08X (address 0x%08X)",
                    offset,
                    address + offset,
                )
                return False
            verified += chunk_len
            self._progress_callback(min(100.0, verified / total * 100.0))

        logger.info("Verification PASSED")
        return True

    def program_and_verify(self, binary_path: str | Path, address: int) -> bool:
        """Erase, program, then verify — convenience wrapper."""
        data = self._parse_binary(Path(binary_path))
        self.erase(address, len(data))
        self.program(binary_path, address)
        return self.verify(binary_path, address)

    # ------------------------------------------------------------------
    # Binary parsing
    # ------------------------------------------------------------------

    def _parse_binary(self, path: Path) -> bytes:
        """Load a firmware image, supporting .bin, .hex, and .out formats."""
        suffix = path.suffix.lower()
        if suffix == ".bin":
            return path.read_bytes()
        if suffix == ".hex":
            return self._parse_intel_hex(path)
        if suffix == ".out":
            return self._parse_ti_coff(path)
        logger.warning("Unknown extension '%s' — treating as raw binary", suffix)
        return path.read_bytes()

    @staticmethod
    def _parse_intel_hex(path: Path) -> bytes:
        """Minimal Intel HEX parser returning a contiguous byte image."""
        segments: dict[int, bytes] = {}
        base_address = 0

        for line in path.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if not line.startswith(":"):
                continue
            byte_count = int(line[1:3], 16)
            address = int(line[3:7], 16)
            record_type = int(line[7:9], 16)
            data_hex = line[9 : 9 + byte_count * 2]
            data = bytes.fromhex(data_hex)

            if record_type == 0x00:  # Data
                segments[base_address + address] = data
            elif record_type == 0x02:  # Extended Segment Address
                base_address = int(data_hex, 16) << 4
            elif record_type == 0x04:  # Extended Linear Address
                base_address = int(data_hex, 16) << 16
            elif record_type == 0x01:  # EOF
                break

        if not segments:
            return b""
        min_addr = min(segments)
        max_addr = max(addr + len(d) for addr, d in segments.items())
        image = bytearray(b"\xFF" * (max_addr - min_addr))
        for addr, d in segments.items():
            offset = addr - min_addr
            image[offset : offset + len(d)] = d
        return bytes(image)

    @staticmethod
    def _parse_ti_coff(path: Path) -> bytes:
        """Minimal TI COFF / ELF loader — reads loadable sections."""
        raw = path.read_bytes()
        # Check for ELF magic
        if raw[:4] == b"\x7fELF":
            # Minimal ELF program-header loader
            e_phoff = struct.unpack_from("<I", raw, 28)[0]
            e_phentsize = struct.unpack_from("<H", raw, 42)[0]
            e_phnum = struct.unpack_from("<H", raw, 44)[0]
            segments: list[tuple[int, bytes]] = []
            for i in range(e_phnum):
                off = e_phoff + i * e_phentsize
                p_type = struct.unpack_from("<I", raw, off)[0]
                if p_type != 1:  # PT_LOAD
                    continue
                p_offset = struct.unpack_from("<I", raw, off + 4)[0]
                p_vaddr = struct.unpack_from("<I", raw, off + 8)[0]
                p_filesz = struct.unpack_from("<I", raw, off + 16)[0]
                segments.append((p_vaddr, raw[p_offset : p_offset + p_filesz]))
            if segments:
                min_addr = min(s[0] for s in segments)
                max_addr = max(s[0] + len(s[1]) for s in segments)
                image = bytearray(b"\xFF" * (max_addr - min_addr))
                for addr, d in segments:
                    o = addr - min_addr
                    image[o : o + len(d)] = d
                return bytes(image)
        # Fallback: treat as raw binary
        logger.warning("Could not parse %s as ELF/COFF — using raw bytes", path.name)
        return raw

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def _progress_callback(self, percent: float) -> None:
        """Invoke the registered progress callback."""
        if self._progress_cb:
            self._progress_cb(percent)
        elif int(percent) % 25 == 0:
            logger.info("Progress: %.0f%%", percent)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    """Standalone flash programming tool."""
    parser = argparse.ArgumentParser(description="mmWave Flash Programmer")
    parser.add_argument("binary", help="Firmware binary path (.bin, .hex, .out)")
    parser.add_argument("--address", type=lambda x: int(x, 0), default=0x0, help="Flash base address")
    parser.add_argument("--backend", choices=["openocd", "lauterbach"], default="openocd")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6666)
    parser.add_argument("--verify-only", action="store_true", help="Verify without programming")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    jtag = JTAGInterface(backend=args.backend, config={"host": args.host, "port": args.port})
    jtag.connect()
    try:
        prog = FlashProgrammer(jtag)
        if args.verify_only:
            ok = prog.verify(args.binary, args.address)
        else:
            ok = prog.program_and_verify(args.binary, args.address)
        sys.exit(0 if ok else 1)
    finally:
        jtag.disconnect()


if __name__ == "__main__":
    main()
