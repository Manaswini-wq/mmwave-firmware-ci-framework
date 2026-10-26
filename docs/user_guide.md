# mmWave Firmware CI Framework - User Guide

## Table of Contents

1. [Installation and Setup](#installation-and-setup)
2. [Quick Start](#quick-start)
3. [Running Tests](#running-tests)
4. [Board Configuration](#board-configuration)
5. [Instrument Setup](#instrument-setup)
6. [Interpreting Results](#interpreting-results)
7. [Troubleshooting](#troubleshooting)

---

## Installation and Setup

### Prerequisites

- Python 3.9 or later
- `pip` package manager
- For on-target testing: OpenOCD, XDS110 drivers, USB relay hardware
- For RF testing: VISA-compatible instrument drivers (NI-VISA or Keysight IO Libraries)

### Install from Source

```bash
git clone https://github.com/your-org/mmwave-firmware-ci-framework.git
cd mmwave-firmware-ci-framework
pip install -e ".[dev]"
```

### Install Dependencies Only

```bash
pip install -r requirements.txt
```

### Docker Setup

For a fully isolated environment:

```bash
docker-compose -f docker/docker-compose.yml up --build
```

### Verify Installation

```bash
python -c "import framework; print(framework.__version__)"
make test-unit
```

---

## Quick Start

1. **Configure your board** by copying and editing a board config file:
   ```bash
   cp config/boards/awr2944_evm.yaml config/boards/my_board.yaml
   # Edit UART port, JTAG settings, etc.
   ```

2. **Run the smoke test suite** to verify basic connectivity:
   ```bash
   pytest tests/integration/ -v \
       --board-config=config/boards/my_board.yaml \
       --suite=config/test_suites/smoke_test.yaml
   ```

3. **View the report** generated in `reports/`:
   ```bash
   open reports/test_report.html
   ```

---

## Running Tests

### Unit Tests

Unit tests run without hardware and validate framework logic:

```bash
make test-unit
# Or directly:
pytest tests/unit/ -v --cov=framework --cov-report=html
```

### Integration Tests

Integration tests require a connected board:

```bash
make test-integration
# Or with a specific board:
pytest tests/integration/ -v --board-config=config/boards/iwr6843_evm.yaml
```

### Running a Specific Test Suite

```bash
pytest tests/integration/ -v \
    --board-config=config/boards/awr2944_evm.yaml \
    --suite=config/test_suites/nightly_regression.yaml
```

### Safety Qualification Tests

These require a controlled lab environment and must not use retries:

```bash
pytest tests/safety/ -v \
    --board-config=config/boards/awr2944_evm.yaml \
    --suite=config/test_suites/safety_qualification.yaml \
    --no-retry
```

### Filtering Tests by Tag

```bash
pytest tests/ -v -m "smoke"
pytest tests/ -v -m "safety and not slow"
pytest tests/ -v -m "rf and tx"
```

---

## Board Configuration

Board configuration files live in `config/boards/` and define:

- **Platform identity**: chip family, silicon revision
- **JTAG settings**: backend (OpenOCD), interface (XDS110), speed
- **UART settings**: COM port, baud rate, parity
- **Firmware defaults**: binary path, flash address
- **Power control**: relay method, boot delays

To add a new board, create a YAML file following the structure of existing configs. The `platform` field must match one of the supported platforms: `awr2944`, `iwr6843`, `awr1843`.

---

## Instrument Setup

Lab instruments are configured in `config/instruments/`. Each instrument config specifies:

- **Connection**: VISA resource string or USB/network address
- **Default settings**: frequency, power level, sweep parameters

Before running RF tests, ensure:

1. Instruments are powered on and connected to the network
2. VISA drivers are installed (NI-VISA recommended)
3. Instrument configs have correct IP addresses / resource strings

See [Instrument Setup Guide](instrument_setup.md) for detailed instructions.

---

## Interpreting Results

### Test Report (HTML)

The HTML report in `reports/test_report.html` shows:
- **Summary bar**: total, passed, failed, skipped counts
- **Pass rate bar**: visual pass/fail/skip proportion
- **Detailed table**: per-test name, status, duration, failure message

### Coverage Report

Coverage reports show line and branch coverage percentages. Files below the configured threshold are flagged. View `reports/coverage_summary.md` or the HTML report.

### JUnit XML

Machine-readable JUnit XML files are written to `reports/junit/` for CI system integration (Jenkins, GitHub Actions, etc.).

---

## Troubleshooting

### UART Connection Fails

- Verify the correct COM port in your board config (`Device Manager` on Windows, `ls /dev/tty*` on Linux)
- Check baud rate matches firmware expectations
- Ensure no other application is using the port

### JTAG Flashing Fails

- Verify XDS110 drivers are installed
- Check USB connection to the EVM
- Try reducing JTAG speed (`speed_khz` in board config)
- Run `openocd` manually to check for errors

### Tests Timeout

- Increase `timeout_s` in the test suite YAML or framework config
- Check that firmware is booting correctly (UART console output)
- Verify power supply is stable

### Instrument Not Found

- Check VISA resource string with NI MAX or Keysight Connection Expert
- Verify network connectivity (`ping <instrument_ip>`)
- Ensure instrument is not in local/remote lockout mode

### Import Errors

- Verify installation: `pip install -e ".[dev]"`
- Check Python version: `python --version` (must be 3.9+)
- Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`
