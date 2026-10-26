"""
JTAG Interface - Unified abstraction for OpenOCD and Lauterbach debuggers.

Provides target control (halt, resume, step), memory/register access,
breakpoint management, and firmware download for TI mmWave SoCs.
"""
from __future__ import annotations

import logging
import socket
import struct
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class JTAGBackend(str, Enum):
    OPENOCD = "openocd"
    LAUTERBACH = "lauterbach"


# ---------------------------------------------------------------------------
# JTAGInterface
# ---------------------------------------------------------------------------

class JTAGInterface:
    """Unified JTAG debugger interface supporting OpenOCD and Lauterbach T32."""

    DEFAULT_OPENOCD_HOST = "127.0.0.1"
    DEFAULT_OPENOCD_PORT = 6666
    DEFAULT_T32_HOST = "127.0.0.1"
    DEFAULT_T32_PORT = 20000

    def __init__(self, backend: str = "openocd", config: dict[str, Any] | None = None) -> None:
        self._backend = JTAGBackend(backend)
        self._config = config or {}
        self._socket: socket.socket | None = None
        self._connected = False

        # Connection parameters
        if self._backend == JTAGBackend.OPENOCD:
            self._host = self._config.get("host", self.DEFAULT_OPENOCD_HOST)
            self._port = int(self._config.get("port", self.DEFAULT_OPENOCD_PORT))
        else:
            self._host = self._config.get("host", self.DEFAULT_T32_HOST)
            self._port = int(self._config.get("port", self.DEFAULT_T32_PORT))

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish connection to the debug backend."""
        logger.info("Connecting to %s at %s:%d", self._backend.value, self._host, self._port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(float(self._config.get("timeout", 10)))
        try:
            self._socket.connect((self._host, self._port))
            self._connected = True
            logger.info("JTAG connection established (%s)", self._backend.value)
        except OSError as exc:
            self._connected = False
            logger.error("Failed to connect to %s: %s", self._backend.value, exc)
            raise ConnectionError(f"JTAG connect failed: {exc}") from exc

    def disconnect(self) -> None:
        """Close the debugger connection."""
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        self._connected = False
        logger.info("JTAG disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Target control
    # ------------------------------------------------------------------

    def reset(self, halt: bool = True) -> None:
        """Reset the target, optionally halting at the reset vector."""
        if self._backend == JTAGBackend.OPENOCD:
            cmd = "reset halt" if halt else "reset run"
            self._openocd_command(cmd)
        else:
            cmd = "SYStem.RESetTarget" if not halt else "SYStem.RESetTarget\nBreak"
            self._lauterbach_command(cmd)
        logger.info("Target reset (halt=%s)", halt)

    def halt(self) -> None:
        """Halt the target CPU."""
        if self._backend == JTAGBackend.OPENOCD:
            self._openocd_command("halt")
        else:
            self._lauterbach_command("Break")
        logger.debug("Target halted")

    def resume(self) -> None:
        """Resume target execution."""
        if self._backend == JTAGBackend.OPENOCD:
            self._openocd_command("resume")
        else:
            self._lauterbach_command("Go")
        logger.debug("Target resumed")

    def step(self) -> None:
        """Single-step the target CPU."""
        if self._backend == JTAGBackend.OPENOCD:
            self._openocd_command("step")
        else:
            self._lauterbach_command("Step")
        logger.debug("Single step executed")

    # ------------------------------------------------------------------
    # Memory access
    # ------------------------------------------------------------------

    def read_memory(self, address: int, size: int) -> bytes:
        """Read *size* bytes from target memory at *address*."""
        if self._backend == JTAGBackend.OPENOCD:
            # OpenOCD returns hex; read in 32-bit words
            n_words = (size + 3) // 4
            resp = self._openocd_command(f"mdw 0x{address:08X} {n_words}")
            return self._parse_openocd_memory(resp, size)
        else:
            resp = self._lauterbach_command(f"Data.DUMP 0x{address:08X}--0x{address + size - 1:08X}")
            return self._parse_t32_memory(resp, size)

    def write_memory(self, address: int, data: bytes) -> None:
        """Write *data* to target memory at *address*."""
        if self._backend == JTAGBackend.OPENOCD:
            for offset in range(0, len(data), 4):
                word = struct.unpack_from("<I", data.ljust(offset + 4, b"\x00"), offset)[0]
                self._openocd_command(f"mww 0x{address + offset:08X} 0x{word:08X}")
        else:
            # Lauterbach: write word by word
            for offset in range(0, len(data), 4):
                word = struct.unpack_from("<I", data.ljust(offset + 4, b"\x00"), offset)[0]
                self._lauterbach_command(f"Data.Set 0x{address + offset:08X} %Long 0x{word:08X}")
        logger.debug("Wrote %d bytes to 0x%08X", len(data), address)

    # ------------------------------------------------------------------
    # Register access
    # ------------------------------------------------------------------

    def read_register(self, reg_name: str) -> int:
        """Read a CPU register by name (e.g. 'r0', 'pc', 'sp')."""
        if self._backend == JTAGBackend.OPENOCD:
            resp = self._openocd_command(f"reg {reg_name}")
            return self._parse_openocd_register(resp)
        else:
            resp = self._lauterbach_command(f"Register.view {reg_name}")
            return self._parse_t32_register(resp)

    def write_register(self, reg_name: str, value: int) -> None:
        """Write a value to a CPU register."""
        if self._backend == JTAGBackend.OPENOCD:
            self._openocd_command(f"reg {reg_name} 0x{value:08X}")
        else:
            self._lauterbach_command(f"Register.Set {reg_name} 0x{value:08X}")
        logger.debug("Set %s = 0x%08X", reg_name, value)

    # ------------------------------------------------------------------
    # Breakpoints
    # ------------------------------------------------------------------

    def set_breakpoint(self, address: int) -> None:
        """Set a hardware breakpoint at *address*."""
        if self._backend == JTAGBackend.OPENOCD:
            self._openocd_command(f"bp 0x{address:08X} 4 hw")
        else:
            self._lauterbach_command(f"Break.Set 0x{address:08X} /Onchip")
        logger.info("Breakpoint set at 0x%08X", address)

    def clear_breakpoint(self, address: int) -> None:
        """Remove the breakpoint at *address*."""
        if self._backend == JTAGBackend.OPENOCD:
            self._openocd_command(f"rbp 0x{address:08X}")
        else:
            self._lauterbach_command(f"Break.Delete 0x{address:08X}")
        logger.info("Breakpoint cleared at 0x%08X", address)

    def wait_halt(self, timeout_s: float = 30.0) -> bool:
        """Wait up to *timeout_s* seconds for the target to halt (e.g. breakpoint hit).

        Returns True if the target halted, False on timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._backend == JTAGBackend.OPENOCD:
                resp = self._openocd_command("$_TARGETNAME curstate")
                if "halted" in resp.lower():
                    return True
            else:
                resp = self._lauterbach_command("STATE.RUN()")
                if "down" in resp.lower() or "stopped" in resp.lower():
                    return True
            time.sleep(0.1)
        logger.warning("wait_halt timed out after %.1fs", timeout_s)
        return False

    # ------------------------------------------------------------------
    # Backend command transports
    # ------------------------------------------------------------------

    def _openocd_command(self, cmd: str) -> str:
        """Send a TCL command to OpenOCD via its telnet interface."""
        if not self._connected or self._socket is None:
            raise ConnectionError("Not connected to OpenOCD")
        try:
            self._socket.sendall((cmd + "\x1a").encode("ascii"))
            chunks: list[bytes] = []
            while True:
                chunk = self._socket.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\x1a" in chunk:
                    break
            response = b"".join(chunks).decode("ascii", errors="replace").strip("\x1a \n")
            logger.debug("OpenOCD << %s >> %s", cmd, response[:200])
            return response
        except OSError as exc:
            logger.error("OpenOCD command '%s' failed: %s", cmd, exc)
            raise

    def _lauterbach_command(self, cmd: str) -> str:
        """Send a PRACTICE command to Lauterbach T32 via its remote API socket."""
        if not self._connected or self._socket is None:
            raise ConnectionError("Not connected to Lauterbach T32")
        try:
            # T32 remote API uses length-prefixed messages
            encoded = cmd.encode("ascii")
            header = struct.pack(">H", len(encoded))
            self._socket.sendall(header + encoded)
            resp_header = self._socket.recv(2)
            if len(resp_header) < 2:
                return ""
            resp_len = struct.unpack(">H", resp_header)[0]
            resp_body = self._socket.recv(resp_len) if resp_len else b""
            response = resp_body.decode("ascii", errors="replace")
            logger.debug("T32 << %s >> %s", cmd, response[:200])
            return response
        except OSError as exc:
            logger.error("Lauterbach command '%s' failed: %s", cmd, exc)
            raise

    # ------------------------------------------------------------------
    # Parse helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_openocd_memory(resp: str, size: int) -> bytes:
        """Parse OpenOCD ``mdw`` response into raw bytes."""
        words: list[int] = []
        for token in resp.split():
            clean = token.strip(":").strip()
            if clean.startswith("0x") or clean.startswith("0X"):
                try:
                    words.append(int(clean, 16))
                except ValueError:
                    continue
        raw = b"".join(struct.pack("<I", w) for w in words)
        return raw[:size]

    @staticmethod
    def _parse_t32_memory(resp: str, size: int) -> bytes:
        """Parse Lauterbach memory dump into raw bytes."""
        data = bytearray()
        for token in resp.split():
            try:
                data.append(int(token, 16))
            except ValueError:
                continue
        return bytes(data[:size])

    @staticmethod
    def _parse_openocd_register(resp: str) -> int:
        for token in resp.split():
            if token.startswith("0x") or token.startswith("0X"):
                return int(token, 16)
        return 0

    @staticmethod
    def _parse_t32_register(resp: str) -> int:
        for token in resp.split():
            if token.startswith("0x") or token.startswith("0X"):
                return int(token, 16)
        return 0
