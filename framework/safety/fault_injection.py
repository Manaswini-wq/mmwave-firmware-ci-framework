"""Fault injection test controller for safety mechanism validation.

Injects hardware faults (memory bit-flips, register corruption, clock/voltage
glitches) via JTAG and monitors the DUT for correct detection and safe-state
transition, producing FMEDA evidence for ISO 26262 / IEC 61508 audits.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FaultType(str, Enum):
    """Enumeration of supported fault categories."""

    MEMORY = "memory"
    REGISTER = "register"
    CLOCK = "clock"
    VOLTAGE = "voltage"


@dataclass
class FaultResponse:
    """Observed DUT response to an injected fault.

    Attributes:
        detected: Whether the safety mechanism detected the fault.
        detection_time_us: Time from injection to detection in microseconds.
        response_action: Description of the DUT's corrective action.
        safe_state_reached: Whether the DUT entered a defined safe state.
    """

    detected: bool = False
    detection_time_us: float = 0.0
    response_action: str = ""
    safe_state_reached: bool = False


@dataclass
class FaultResult:
    """Result of a single fault-injection experiment.

    Attributes:
        fault_type: Category of the injected fault.
        injection_point: Description / address of the injection site.
        response: Observed DUT response.
        pass_fail: Overall verdict for this experiment.
    """

    fault_type: str = ""
    injection_point: str = ""
    response: FaultResponse = field(default_factory=FaultResponse)
    pass_fail: str = "FAIL"


class FaultInjector:
    """Controller for hardware fault-injection campaigns.

    Uses a JTAG debug interface to inject faults into the DUT and a UART
    monitor to observe the safety mechanism's response.

    Args:
        jtag_interface: Object with ``write_memory(addr, data)``,
                        ``read_memory(addr, size)``, ``write_register(name, value)``,
                        and ``read_register(name)`` methods.
        uart_monitor: Object with ``readline(timeout)`` for reading DUT
                      log / status messages.
    """

    SAFE_STATE_KEYWORDS = {"SAFE_STATE", "FAULT_DETECTED", "LOCKSTEP_ERROR", "ECC_ERROR"}

    def __init__(self, jtag_interface: Any, uart_monitor: Any) -> None:
        self.jtag = jtag_interface
        self.uart = uart_monitor
        logger.debug("FaultInjector initialised")

    # -- injection methods ----------------------------------------------------

    def inject_memory_fault(self, address: int, bit_position: int) -> None:
        """Inject a single-bit flip at a memory address.

        Args:
            address: Target memory address.
            bit_position: Bit index (0-31) to flip.
        """
        logger.info("Injecting memory fault: addr=0x%08X, bit=%d", address, bit_position)
        original = self.jtag.read_memory(address, 4)
        word = int.from_bytes(original, byteorder="little")
        corrupted = word ^ (1 << bit_position)
        self.jtag.write_memory(address, corrupted.to_bytes(4, byteorder="little"))
        logger.debug("Memory 0x%08X: 0x%08X -> 0x%08X", address, word, corrupted)

    def inject_register_fault(self, register: str, corruption: int) -> None:
        """Corrupt a CPU / peripheral register.

        Args:
            register: Register name (e.g. ``'R0'``, ``'CONTROL'``).
            corruption: XOR mask applied to the current register value.
        """
        logger.info("Injecting register fault: %s ^= 0x%08X", register, corruption)
        original = self.jtag.read_register(register)
        corrupted = original ^ corruption
        self.jtag.write_register(register, corrupted)
        logger.debug("Register %s: 0x%08X -> 0x%08X", register, original, corrupted)

    def inject_clock_fault(self, duration_us: float) -> None:
        """Simulate a clock glitch by halting the core for a short period.

        Args:
            duration_us: Glitch duration in microseconds.
        """
        logger.info("Injecting clock fault: halt for %.1f us", duration_us)
        self.jtag.write_register("DHCSR", 0xA05F0003)  # halt core
        time.sleep(duration_us / 1e6)
        self.jtag.write_register("DHCSR", 0xA05F0001)  # resume
        logger.debug("Clock glitch injected (%.1f us)", duration_us)

    def inject_voltage_fault(self, rail: str, deviation: float) -> None:
        """Log a voltage-rail perturbation request.

        Actual voltage injection requires external programmable PSU control;
        this method records the intent for the test log and delegates to the
        bench power supply via JTAG GPIO if available.

        Args:
            rail: Power rail name, e.g. ``'VDD_CORE'``.
            deviation: Voltage deviation in volts (positive = overvoltage).
        """
        logger.info("Voltage fault request: rail=%s, deviation=%+.3f V", rail, deviation)
        # In production this would command a programmable PSU.
        logger.warning("Voltage fault injection requires external PSU; logged only")

    # -- response monitoring --------------------------------------------------

    def monitor_detection(self, timeout_s: float = 1.0) -> FaultResponse:
        """Monitor the DUT for fault detection after injection.

        Args:
            timeout_s: Maximum observation window in seconds.

        Returns:
            :class:`FaultResponse` describing the observed behaviour.
        """
        start = time.monotonic()
        response = FaultResponse()

        deadline = start + timeout_s
        while time.monotonic() < deadline:
            line = self.uart.readline(timeout=0.05)
            if not line:
                continue
            text = line.decode("ascii", errors="replace").strip() if isinstance(line, bytes) else str(line).strip()
            logger.debug("DUT >>> %s", text)

            for keyword in self.SAFE_STATE_KEYWORDS:
                if keyword in text.upper():
                    response.detected = True
                    response.detection_time_us = (time.monotonic() - start) * 1e6
                    response.response_action = text
                    response.safe_state_reached = "SAFE_STATE" in text.upper()
                    logger.info("Fault detected in %.1f us: %s", response.detection_time_us, text)
                    return response

        logger.warning("No fault detection within %.1f s", timeout_s)
        return response

    def monitor_safe_state(self, timeout_s: float = 2.0) -> bool:
        """Wait for the DUT to enter a defined safe state.

        Args:
            timeout_s: Maximum wait time in seconds.

        Returns:
            ``True`` if safe state was reached.
        """
        resp = self.monitor_detection(timeout_s=timeout_s)
        return resp.safe_state_reached

    # -- campaign execution ---------------------------------------------------

    def run_fault_campaign(self, fault_list: List[Dict[str, Any]]) -> List[FaultResult]:
        """Execute a batch of fault-injection experiments.

        Each entry in *fault_list* is a dictionary with:
        - ``type``: ``'memory'``, ``'register'``, ``'clock'``, or ``'voltage'``
        - ``params``: keyword arguments for the corresponding ``inject_*`` method.

        Args:
            fault_list: List of fault specifications.

        Returns:
            List of :class:`FaultResult` instances.
        """
        results: List[FaultResult] = []
        logger.info("Starting fault campaign (%d experiments)", len(fault_list))

        for idx, fault_spec in enumerate(fault_list):
            fault_type = fault_spec.get("type", "")
            params = fault_spec.get("params", {})
            logger.info("--- Experiment %d/%d: %s ---", idx + 1, len(fault_list), fault_type)

            try:
                if fault_type == FaultType.MEMORY:
                    self.inject_memory_fault(**params)
                elif fault_type == FaultType.REGISTER:
                    self.inject_register_fault(**params)
                elif fault_type == FaultType.CLOCK:
                    self.inject_clock_fault(**params)
                elif fault_type == FaultType.VOLTAGE:
                    self.inject_voltage_fault(**params)
                else:
                    logger.error("Unknown fault type: %s", fault_type)
                    continue

                response = self.monitor_detection(timeout_s=2.0)
                passed = response.detected and response.safe_state_reached
                results.append(FaultResult(
                    fault_type=fault_type,
                    injection_point=str(params),
                    response=response,
                    pass_fail="PASS" if passed else "FAIL",
                ))
            except Exception:
                logger.exception("Experiment %d failed", idx + 1)
                results.append(FaultResult(
                    fault_type=fault_type,
                    injection_point=str(params),
                    pass_fail="ERROR",
                ))

        pass_count = sum(1 for r in results if r.pass_fail == "PASS")
        logger.info("Fault campaign complete: %d/%d passed", pass_count, len(results))
        return results

    # -- FMEDA evidence -------------------------------------------------------

    def generate_fmeda_evidence(self, results: List[FaultResult]) -> Dict[str, Any]:
        """Generate FMEDA (Failure Mode Effects and Diagnostic Analysis) evidence.

        Args:
            results: Fault-injection results from :meth:`run_fault_campaign`.

        Returns:
            Dictionary with FMEDA summary metrics and per-experiment details.
        """
        total = len(results)
        detected = sum(1 for r in results if r.response.detected)
        safe = sum(1 for r in results if r.response.safe_state_reached)
        detection_times = [r.response.detection_time_us for r in results if r.response.detected]

        evidence: Dict[str, Any] = {
            "total_experiments": total,
            "faults_detected": detected,
            "safe_state_reached": safe,
            "diagnostic_coverage_pct": round(detected / total * 100, 2) if total > 0 else 0.0,
            "safe_fault_fraction_pct": round(safe / total * 100, 2) if total > 0 else 0.0,
            "avg_detection_time_us": round(sum(detection_times) / len(detection_times), 2) if detection_times else 0.0,
            "max_detection_time_us": round(max(detection_times), 2) if detection_times else 0.0,
            "details": [
                {
                    "fault_type": r.fault_type,
                    "injection_point": r.injection_point,
                    "detected": r.response.detected,
                    "detection_time_us": r.response.detection_time_us,
                    "safe_state": r.response.safe_state_reached,
                    "verdict": r.pass_fail,
                }
                for r in results
            ],
        }
        logger.info("FMEDA evidence: DC=%.1f%%, SFF=%.1f%%",
                     evidence["diagnostic_coverage_pct"], evidence["safe_fault_fraction_pct"])
        return evidence
