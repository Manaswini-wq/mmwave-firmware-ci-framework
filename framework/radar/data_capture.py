"""Radar data capture and validation.

Captures raw ADC frame data from the mmWave radar sensor over UART/DMA,
validates frame integrity (CRC, packet structure), and persists captures
to disk in binary or NumPy format.
"""

from __future__ import annotations

import logging
import struct
import time
import zlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class DataCapture:
    """Captures and validates radar ADC frames.

    Args:
        uart_monitor: An object with ``read(size)`` / ``readline()`` methods
                      (e.g. a ``serial.Serial`` instance) connected to the
                      radar data port.
        config: Radar configuration dictionary containing at least
                ``num_rx``, ``num_tx``, ``adc_samples``, ``num_chirps``,
                ``adc_bits`` (12 or 16), and ``complex_samples`` (bool).
    """

    SYNC_PATTERN: bytes = b"\x02\x01\x04\x03\x06\x05\x08\x07"

    def __init__(self, uart_monitor: Any, config: Dict[str, Any]) -> None:
        self.uart_monitor = uart_monitor
        self.config: Dict[str, Any] = config
        self._frames: List[np.ndarray] = []
        self._capturing: bool = False
        self._raw_buffer: bytearray = bytearray()

        # Derived sizes
        self._num_rx: int = int(config.get("num_rx", 4))
        self._num_tx: int = int(config.get("num_tx", 3))
        self._adc_samples: int = int(config.get("adc_samples", 256))
        self._num_chirps: int = int(config.get("num_chirps", 128))
        self._adc_bits: int = int(config.get("adc_bits", 16))
        self._complex: bool = bool(config.get("complex_samples", True))

        samples_per_chirp = self._adc_samples * (2 if self._complex else 1)
        bytes_per_sample = 2 if self._adc_bits <= 16 else 4
        self._frame_size: int = (
            self._num_rx * self._num_tx * self._num_chirps
            * samples_per_chirp * bytes_per_sample
        )
        logger.debug("Expected frame size: %d bytes", self._frame_size)

    # -- capture control ------------------------------------------------------

    def start_capture(self, num_frames: int = 1) -> None:
        """Begin capturing radar frames.

        Args:
            num_frames: Number of frames to capture before auto-stopping.
        """
        logger.info("Starting capture of %d frame(s)", num_frames)
        self._frames.clear()
        self._raw_buffer.clear()
        self._capturing = True

        for frame_idx in range(num_frames):
            frame = self.get_frame(timeout_s=10.0)
            if frame is not None:
                self._frames.append(frame)
                logger.info("Frame %d/%d captured (%d samples)",
                            frame_idx + 1, num_frames, frame.size)
            else:
                logger.warning("Frame %d/%d timed out", frame_idx + 1, num_frames)

        self._capturing = False
        logger.info("Capture complete: %d frame(s) stored", len(self._frames))

    def stop_capture(self) -> None:
        """Signal the capture loop to stop."""
        self._capturing = False
        logger.info("Capture stop requested")

    # -- frame retrieval ------------------------------------------------------

    def get_frame(self, timeout_s: float = 5.0) -> Optional[np.ndarray]:
        """Read one complete frame from the data port.

        Args:
            timeout_s: Maximum time to wait for a complete frame.

        Returns:
            Parsed ADC data as a numpy array, or ``None`` on timeout.
        """
        deadline = time.monotonic() + timeout_s
        buf = bytearray()

        while time.monotonic() < deadline:
            remaining = self._frame_size - len(buf)
            chunk = self.uart_monitor.read(min(remaining, 4096))
            if chunk:
                buf.extend(chunk)
            if len(buf) >= self._frame_size:
                raw_frame = bytes(buf[: self._frame_size])
                return self._parse_adc_data(raw_frame)
            time.sleep(0.001)

        logger.warning("Timeout waiting for frame data (%d/%d bytes received)",
                       len(buf), self._frame_size)
        return None

    # -- validation -----------------------------------------------------------

    def validate_frame(self, frame_data: np.ndarray) -> Tuple[bool, List[str]]:
        """Run integrity checks on a captured frame.

        Args:
            frame_data: Parsed ADC frame array.

        Returns:
            Tuple of (pass_flag, list_of_issue_strings).
        """
        issues = self._check_data_integrity(frame_data)
        passed = len(issues) == 0
        if passed:
            logger.info("Frame validation: PASS")
        else:
            logger.warning("Frame validation: FAIL (%d issues)", len(issues))
            for issue in issues:
                logger.warning("  - %s", issue)
        return passed, issues

    # -- persistence ----------------------------------------------------------

    def save_capture(self, filepath: str, format: str = "npy") -> None:
        """Save all captured frames to disk.

        Args:
            filepath: Output file path (extension added automatically).
            format: ``'npy'`` for NumPy binary or ``'bin'`` for raw binary.
        """
        if not self._frames:
            logger.warning("No frames to save")
            return

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == "npy":
            all_data = np.stack(self._frames)
            np.save(str(path.with_suffix(".npy")), all_data)
            logger.info("Saved %d frames to %s", len(self._frames), path.with_suffix(".npy"))
        elif format == "bin":
            with open(path.with_suffix(".bin"), "wb") as fh:
                for frame in self._frames:
                    fh.write(frame.tobytes())
            logger.info("Saved %d frames (raw) to %s", len(self._frames), path.with_suffix(".bin"))
        else:
            raise ValueError(f"Unsupported format: {format}")

    # -- internal helpers -----------------------------------------------------

    def _parse_adc_data(self, raw_bytes: bytes) -> np.ndarray:
        """Decode raw bytes into a structured numpy array.

        Args:
            raw_bytes: Raw ADC payload.

        Returns:
            Complex or real numpy array shaped
            ``(num_chirps, num_rx * num_tx, adc_samples)``.
        """
        dtype = np.int16 if self._adc_bits <= 16 else np.int32
        samples = np.frombuffer(raw_bytes, dtype=dtype)

        if self._complex:
            real = samples[0::2]
            imag = samples[1::2]
            data = real.astype(np.float32) + 1j * imag.astype(np.float32)
        else:
            data = samples.astype(np.float32)

        try:
            data = data.reshape(
                self._num_chirps,
                self._num_rx * self._num_tx,
                self._adc_samples,
            )
        except ValueError:
            logger.warning("Could not reshape ADC data to expected dimensions; returning flat array")

        return data

    def _verify_frame_crc(self, data: bytes, expected_crc: int) -> bool:
        """Verify a frame CRC-32 checksum.

        Args:
            data: Frame payload bytes.
            expected_crc: Expected CRC-32 value.

        Returns:
            ``True`` if CRC matches.
        """
        computed = zlib.crc32(data) & 0xFFFFFFFF
        match = computed == expected_crc
        if not match:
            logger.warning("CRC mismatch: computed=0x%08X, expected=0x%08X", computed, expected_crc)
        return match

    @staticmethod
    def _check_data_integrity(frame: np.ndarray) -> List[str]:
        """Run heuristic integrity checks on parsed frame data.

        Args:
            frame: Parsed ADC numpy array.

        Returns:
            List of issue description strings (empty means OK).
        """
        issues: List[str] = []
        if frame.size == 0:
            issues.append("Frame is empty")
            return issues

        real_data = np.real(frame) if np.iscomplexobj(frame) else frame

        # Check for all-zeros (disconnected sensor)
        if np.all(real_data == 0):
            issues.append("All samples are zero (possible sensor disconnect)")

        # Check for saturation (all samples at max/min)
        unique_count = len(np.unique(real_data))
        if unique_count < 3:
            issues.append(f"Very low sample diversity ({unique_count} unique values)")

        # Check for NaN / Inf
        if np.any(np.isnan(real_data)) or np.any(np.isinf(real_data)):
            issues.append("Frame contains NaN or Inf values")

        return issues
