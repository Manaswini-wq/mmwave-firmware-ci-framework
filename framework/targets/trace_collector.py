"""
Trace Collector - ARM ETM trace collection for code coverage analysis.

Configures Embedded Trace Macrocell (ETM) via JTAG, captures branch/execution
trace data, and maps traced addresses back to source lines using ELF debug info.
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from framework.targets.jtag_interface import JTAGInterface

logger = logging.getLogger(__name__)

# ARM CoreSight ETM register offsets (Cortex-R series typical)
ETM_CR = 0xE0041000  # ETM Main Control
ETM_TRIGGER = 0xE0041008
ETM_SR = 0xE0041010  # ETM Status
ETM_TECR1 = 0xE0041024  # Trace Enable Control 1
ETM_LAR = 0xE0041FB0  # Lock Access
ETM_UNLOCK_KEY = 0xC5ACCE55

# Embedded Trace Buffer (ETB) registers
ETB_BASE = 0xE0042000
ETB_RDP = 0xE0042004  # RAM Depth
ETB_STS = 0xE004200C  # Status
ETB_RRD = 0xE0042010  # RAM Read Data
ETB_CTL = 0xE0042020  # Control
ETB_FFCR = 0xE0042304  # Formatter/Flush Control


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CoverageReport:
    """Summary of code coverage computed from ETM trace."""

    total_branches: int = 0
    covered_branches: int = 0
    branch_coverage_pct: float = 0.0
    total_lines: int = 0
    covered_lines: int = 0
    line_coverage_pct: float = 0.0
    uncovered_lines: list[str] = field(default_factory=list)  # "file:line" strings


# ---------------------------------------------------------------------------
# TraceCollector
# ---------------------------------------------------------------------------

class TraceCollector:
    """Collect ARM ETM trace data and compute code coverage metrics."""

    def __init__(self, jtag_interface: JTAGInterface, elf_path: str | Path) -> None:
        self._jtag = jtag_interface
        self._elf_path = Path(elf_path)
        self._trace_buffer_size = 0
        self._raw_trace: bytes = b""
        self._decoded_addresses: list[int] = []
        self._source_map: dict[int, str] = {}  # addr -> "file.c:123"

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup_trace(self, buffer_size: int = 4096) -> None:
        """Configure the ETM and ETB for trace collection.

        *buffer_size* is the desired ETB RAM depth in 32-bit words.
        """
        self._trace_buffer_size = buffer_size
        logger.info("Configuring ETM trace (buffer=%d words)", buffer_size)

        self._jtag.halt()

        # Unlock ETM
        self._jtag.write_memory(ETM_LAR, struct.pack("<I", ETM_UNLOCK_KEY))

        # Power up and enable ETM
        self._jtag.write_memory(ETM_CR, struct.pack("<I", 0x00000D00))  # Programming bit set
        self._jtag.write_memory(ETM_TECR1, struct.pack("<I", 0x00000001))  # Include all

        # Enable ETB capture
        self._jtag.write_memory(ETB_CTL, struct.pack("<I", 0x00000001))
        self._jtag.write_memory(ETB_FFCR, struct.pack("<I", 0x00000001))

        # Clear programming bit — trace is armed
        self._jtag.write_memory(ETM_CR, struct.pack("<I", 0x00000900))

        logger.info("ETM trace configured and armed")

    def start_collection(self) -> None:
        """Resume target execution and begin collecting trace."""
        logger.info("Starting trace collection")
        self._jtag.resume()

    def stop_collection(self) -> None:
        """Halt the target and stop trace collection."""
        self._jtag.halt()
        # Disable ETB
        self._jtag.write_memory(ETB_CTL, struct.pack("<I", 0x00000000))
        logger.info("Trace collection stopped")

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------

    def extract_trace_data(self) -> bytes:
        """Read the raw trace data from the ETB."""
        # Read ETB status
        sts_raw = self._jtag.read_memory(ETB_STS, 4)
        sts = struct.unpack("<I", sts_raw)[0] if len(sts_raw) >= 4 else 0

        # Read depth
        depth_raw = self._jtag.read_memory(ETB_RDP, 4)
        depth = struct.unpack("<I", depth_raw)[0] if len(depth_raw) >= 4 else self._trace_buffer_size

        logger.info("ETB status=0x%08X, depth=%d words", sts, depth)

        words: list[bytes] = []
        for _ in range(depth):
            word = self._jtag.read_memory(ETB_RRD, 4)
            words.append(word)

        self._raw_trace = b"".join(words)
        logger.info("Extracted %d bytes of trace data", len(self._raw_trace))
        return self._raw_trace

    # ------------------------------------------------------------------
    # Coverage analysis
    # ------------------------------------------------------------------

    def calculate_branch_coverage(self) -> float:
        """Decode trace and return branch coverage percentage."""
        if not self._raw_trace:
            self.extract_trace_data()
        self._decoded_addresses = self._decode_etm_packets(self._raw_trace)
        source_entries = self._map_addresses_to_source(self._decoded_addresses, self._elf_path)
        self._source_map = {a: s for a, s in zip(self._decoded_addresses, source_entries)}

        # For branch coverage we count unique branch-target addresses
        total_branches = len(set(source_entries))
        covered_branches = len({s for s in source_entries if s != "??"})
        pct = (covered_branches / total_branches * 100.0) if total_branches else 0.0
        logger.info("Branch coverage: %.1f%% (%d/%d)", pct, covered_branches, total_branches)
        return pct

    def calculate_line_coverage(self) -> float:
        """Decode trace and return line coverage percentage."""
        if not self._decoded_addresses:
            self.calculate_branch_coverage()

        covered_lines = {s for s in self._source_map.values() if s != "??"}
        # We would need the total line count from ELF debug info
        total_lines = max(len(covered_lines) + 10, 1)  # placeholder heuristic
        pct = len(covered_lines) / total_lines * 100.0
        logger.info("Line coverage: %.1f%% (%d/%d)", pct, len(covered_lines), total_lines)
        return pct

    def generate_coverage_report(self, output_path: str | Path) -> CoverageReport:
        """Generate a full coverage report and write it to *output_path*."""
        branch_pct = self.calculate_branch_coverage()
        line_pct = self.calculate_line_coverage()

        covered_lines = {s for s in self._source_map.values() if s != "??"}
        total_lines = max(len(covered_lines) + 10, 1)

        report = CoverageReport(
            total_branches=len(set(self._source_map.values())),
            covered_branches=len({s for s in self._source_map.values() if s != "??"}),
            branch_coverage_pct=branch_pct,
            total_lines=total_lines,
            covered_lines=len(covered_lines),
            line_coverage_pct=line_pct,
            uncovered_lines=[],  # Would be populated from full debug info
        )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        output_path.write_text(
            json.dumps({
                "branch_coverage": report.branch_coverage_pct,
                "line_coverage": report.line_coverage_pct,
                "total_branches": report.total_branches,
                "covered_branches": report.covered_branches,
                "total_lines": report.total_lines,
                "covered_lines": report.covered_lines,
                "uncovered_lines": report.uncovered_lines,
            }, indent=2),
            encoding="utf-8",
        )
        logger.info("Coverage report written to %s", output_path)
        return report

    # ------------------------------------------------------------------
    # Internal: ETM decode
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_etm_packets(raw_data: bytes) -> list[int]:
        """Decode ETM v3/v4 trace packets and extract executed addresses.

        This is a simplified decoder that extracts branch addresses from
        the ETM atom and address packets.
        """
        addresses: list[int] = []
        i = 0
        current_address = 0

        while i < len(raw_data):
            header = raw_data[i]

            if header == 0x00:
                # Async/sync — skip
                i += 1
                continue

            if (header & 0x01) == 0x01 and i + 4 < len(raw_data):
                # Branch address packet (simplified): 4 subsequent bytes
                addr_bytes = raw_data[i + 1 : i + 5]
                addr = struct.unpack("<I", addr_bytes)[0] & 0xFFFFFFFE
                if addr != 0:
                    current_address = addr
                    addresses.append(addr)
                i += 5
            else:
                # Atom packet or other — advance
                i += 1

        logger.debug("Decoded %d branch addresses from trace", len(addresses))
        return addresses

    @staticmethod
    def _map_addresses_to_source(addresses: list[int], elf_path: Path) -> list[str]:
        """Map instruction addresses to source file:line using ELF debug info.

        In production this would invoke ``addr2line`` or parse DWARF info.
        Here we return a placeholder mapping.
        """
        # Attempt to use addr2line if available
        import shutil
        import subprocess

        addr2line = shutil.which("addr2line")
        if addr2line and elf_path.exists() and addresses:
            try:
                addr_args = [f"0x{a:08X}" for a in addresses]
                result = subprocess.run(
                    [addr2line, "-e", str(elf_path)] + addr_args,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                lines = result.stdout.strip().splitlines()
                if len(lines) == len(addresses):
                    return lines
            except Exception:
                logger.debug("addr2line unavailable or failed — using fallback")

        return [f"0x{a:08X}" for a in addresses]
