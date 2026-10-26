"""
Test Runner - Main orchestration engine for firmware validation.

Supports unit, integration, and qualification testing across the
full SW development life cycle for TI's mmWave radar sensor firmware.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    _HAS_COLORAMA = True
except ImportError:
    _HAS_COLORAMA = False

from framework.core.config_loader import ConfigLoader
from framework.core.test_discovery import TestDiscovery, TestSpec
from framework.core.result_collector import ResultCollector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    """Outcome of a single test execution."""

    name: str
    status: str  # "pass", "fail", "skip", "error"
    duration: float = 0.0
    logs: str = ""
    artifacts: list[str] = field(default_factory=list)
    message: str = ""
    retry_count: int = 0


# ---------------------------------------------------------------------------
# Coloured helpers
# ---------------------------------------------------------------------------

def _colour(text: str, colour: str) -> str:
    if not _HAS_COLORAMA:
        return text
    mapping = {"green": Fore.GREEN, "red": Fore.RED, "yellow": Fore.YELLOW, "cyan": Fore.CYAN}
    return f"{mapping.get(colour, '')}{text}{Style.RESET_ALL}"


def _status_colour(status: str) -> str:
    colours = {"pass": "green", "fail": "red", "skip": "yellow", "error": "red"}
    return _colour(status.upper(), colours.get(status, "cyan"))


# ---------------------------------------------------------------------------
# TestRunner
# ---------------------------------------------------------------------------

class TestRunner:
    """Orchestrates firmware validation test execution."""

    def __init__(
        self,
        config_path: str | Path,
        board: str = "default",
        suite: str | None = None,
        verbosity: int = 1,
        parallel: int = 1,
        retry_count: int = 0,
        output_dir: str | Path = "results",
    ) -> None:
        self._config_path = Path(config_path)
        self._board = board
        self._suite_filter = suite
        self._verbosity = verbosity
        self._parallel = max(1, parallel)
        self._retry_count = max(0, retry_count)
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._config_loader = ConfigLoader()
        self._config: dict[str, Any] = {}
        self._discovery = TestDiscovery()
        self._collector = ResultCollector()
        self._tests: list[TestSpec] = []
        self._interrupted = False

        # Graceful Ctrl-C handling
        signal.signal(signal.SIGINT, self._handle_interrupt)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover_tests(self) -> list[TestSpec]:
        """Scan test suites from YAML configuration and return discovered tests."""
        self._config = self._config_loader.load(self._config_path)
        suite_paths = self._config.get("test_suites", [])
        all_tests: list[TestSpec] = []
        for sp in suite_paths:
            discovered = self._discovery.discover(Path(sp))
            all_tests.extend(discovered)

        # Apply platform filter
        board_cfg = self._config_loader.get_board_config(self._board)
        platform = board_cfg.get("platform", self._board)
        all_tests = self._discovery.filter_by_platform(all_tests, platform)

        # Apply suite filter
        if self._suite_filter:
            all_tests = [t for t in all_tests if self._suite_filter in t.tags]

        self._tests = self._discovery._build_execution_order(all_tests)
        logger.info("Discovered %d test(s) for board '%s'", len(self._tests), self._board)
        return self._tests

    def run_all(self) -> ResultCollector:
        """Execute all discovered tests and return the result collector."""
        if not self._tests:
            self.discover_tests()

        self._setup_board()
        try:
            if self._parallel > 1 and len(self._tests) > 1:
                self._run_parallel(self._tests)
            else:
                self._run_sequential(self._tests)
        finally:
            self._teardown_board()
            self._collect_results()
        return self._collector

    def run_suite(self, suite_name: str) -> ResultCollector:
        """Run a specific named test suite."""
        if not self._tests:
            self.discover_tests()
        subset = [t for t in self._tests if suite_name in t.tags]
        if not subset:
            logger.warning("No tests found for suite '%s'", suite_name)
            return self._collector

        self._setup_board()
        try:
            self._run_sequential(subset)
        finally:
            self._teardown_board()
            self._collect_results()
        return self._collector

    # ------------------------------------------------------------------
    # Board lifecycle
    # ------------------------------------------------------------------

    def _setup_board(self) -> None:
        """Initialize JTAG connection and flash firmware to the target board."""
        board_cfg = self._config_loader.get_board_config(self._board)
        logger.info("Setting up board '%s' (platform=%s)", self._board, board_cfg.get("platform"))
        # In a real implementation this would:
        #  1. Power-cycle the board via BoardController
        #  2. Connect via JTAG
        #  3. Flash the firmware binary
        #  4. Wait for boot-up UART banner
        logger.info("Board setup complete.")

    def _teardown_board(self) -> None:
        """Clean up board state, disconnect JTAG, and collect logs."""
        logger.info("Tearing down board '%s'", self._board)
        # Collect UART logs, disconnect JTAG, optionally power-off
        logger.info("Board teardown complete.")

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    def _run_sequential(self, tests: list[TestSpec]) -> None:
        for idx, test in enumerate(tests, 1):
            if self._interrupted:
                logger.warning("Execution interrupted — skipping remaining tests.")
                break
            prefix = f"[{idx}/{len(tests)}]"
            logger.info("%s Running: %s", prefix, test.name)
            result = self._execute_test(test)
            self._collector.add_result(result)
            logger.info(
                "%s %s  %s (%.2fs)",
                prefix,
                _status_colour(result.status),
                result.name,
                result.duration,
            )

    def _run_parallel(self, tests: list[TestSpec]) -> None:
        logger.info("Running %d tests with parallelism=%d", len(tests), self._parallel)
        with ThreadPoolExecutor(max_workers=self._parallel) as pool:
            futures = {pool.submit(self._execute_test, t): t for t in tests}
            for future in as_completed(futures):
                if self._interrupted:
                    break
                result = future.result()
                self._collector.add_result(result)
                logger.info(
                    "%s  %s (%.2fs)", _status_colour(result.status), result.name, result.duration
                )

    def _execute_test(self, test: TestSpec) -> TestResult:
        """Execute a single test with timeout and retry-on-failure logic."""
        last_result: TestResult | None = None
        for attempt in range(1 + self._retry_count):
            start = time.monotonic()
            try:
                fn = self._discovery._resolve_test_module(test)
                if fn is None:
                    return TestResult(
                        name=test.name, status="error", message="Could not resolve test function"
                    )
                # Execute with timeout awareness (simplistic; real impl uses threading.Timer)
                fn()
                elapsed = time.monotonic() - start
                return TestResult(name=test.name, status="pass", duration=elapsed)
            except AssertionError as exc:
                elapsed = time.monotonic() - start
                last_result = TestResult(
                    name=test.name,
                    status="fail",
                    duration=elapsed,
                    message=str(exc),
                    logs=traceback.format_exc(),
                    retry_count=attempt,
                )
            except Exception as exc:  # noqa: BLE001
                elapsed = time.monotonic() - start
                last_result = TestResult(
                    name=test.name,
                    status="error",
                    duration=elapsed,
                    message=str(exc),
                    logs=traceback.format_exc(),
                    retry_count=attempt,
                )
            if attempt < self._retry_count:
                logger.info("Retrying '%s' (attempt %d/%d)", test.name, attempt + 2, self._retry_count + 1)
        return last_result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def _collect_results(self) -> None:
        """Aggregate results and persist to disk."""
        summary = self._collector.get_summary()
        logger.info(
            "Results — Total: %d | Pass: %d | Fail: %d | Skip: %d | Error: %d | Duration: %.2fs",
            summary["total"],
            summary["passed"],
            summary["failed"],
            summary["skipped"],
            summary["errors"],
            summary["total_duration"],
        )
        self._collector.to_junit_xml(self._output_dir / "results.xml")
        self._collector.to_json(self._output_dir / "results.json")

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        logger.warning("Caught interrupt signal — finishing current test then stopping.")
        self._interrupted = True


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    """Command-line entry point for the test runner."""
    parser = argparse.ArgumentParser(
        description="mmWave Firmware CI Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", required=True, help="Path to YAML test configuration")
    parser.add_argument("--board", default="default", help="Target board identifier")
    parser.add_argument("--suite", default=None, help="Run only the named test suite")
    parser.add_argument("--output", default="results", help="Output directory for results")
    parser.add_argument("--verbosity", type=int, default=1, choices=[0, 1, 2], help="Verbosity level")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel test workers")
    parser.add_argument("--retry-count", type=int, default=0, help="Retry failed tests N times")

    args = parser.parse_args()

    log_level = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}.get(args.verbosity, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    runner = TestRunner(
        config_path=args.config,
        board=args.board,
        suite=args.suite,
        verbosity=args.verbosity,
        parallel=args.parallel,
        retry_count=args.retry_count,
        output_dir=args.output,
    )
    runner.discover_tests()
    collector = runner.run_all()

    summary = collector.get_summary()
    sys.exit(0 if summary["failed"] == 0 and summary["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
