# mmWave Firmware CI Framework - Architecture

## Overview

The mmWave Firmware CI Framework is a layered, extensible test automation platform designed for validating radar firmware on TI mmWave devices. It supports unit testing, hardware-in-the-loop integration testing, RF validation, and safety qualification evidence generation.

---

## Framework Layers

```
+------------------------------------------------------------------+
|                        CI / Orchestration                         |
|  (GitHub Actions, Jenkins, Makefile, docker-compose)              |
+------------------------------------------------------------------+
|                        Test Suites (YAML)                         |
|  smoke_test | nightly_regression | safety_qualification | rf     |
+------------------------------------------------------------------+
|                      Test Runner & Discovery                      |
|  pytest plugins, suite loader, tag filtering, retry logic         |
+------------------------------------------------------------------+
|                        Framework Core                             |
|  test_runner.py | test_discovery.py | result_collector.py         |
+------------------------------------------------------------------+
|                    Domain Modules                                 |
|  radar/  |  safety/  |  instruments/  |  targets/  |  utils/     |
+------------------------------------------------------------------+
|                   Hardware Abstraction                            |
|  JTAG (OpenOCD) | UART (pyserial) | VISA (pyvisa) | USB relay   |
+------------------------------------------------------------------+
|                    Physical Hardware                              |
|  AWR2944 EVM | IWR6843 EVM | Spectrum Analyzer | Signal Gen     |
+------------------------------------------------------------------+
```

### Layer Responsibilities

1. **CI / Orchestration**: Triggers test runs, manages environments, collects artifacts, sends notifications.

2. **Test Suites (YAML)**: Declarative test suite definitions listing tests, timeouts, platform compatibility, and requirement mappings.

3. **Test Runner & Discovery**: pytest-based execution engine with custom plugins for board management, suite loading, and result collection.

4. **Framework Core**: Central modules for test lifecycle management:
   - `test_discovery.py` - Finds and filters tests based on suite config, tags, and platform
   - `test_runner.py` - Executes tests with timeout, retry, and power-cycle support
   - `result_collector.py` - Aggregates results into JUnit XML and HTML reports

5. **Domain Modules**:
   - `radar/` - Radar-specific data path validation, chirp configuration, ADC readout
   - `safety/` - Safety mechanism tests (MPU, ECC, watchdog, CRC)
   - `instruments/` - SCPI instrument drivers (spectrum analyzer, signal generator, power meter)
   - `targets/` - Board abstraction (flash, reset, UART communication)
   - `utils/` - Shared utilities (logging, config parsing, file I/O)

6. **Hardware Abstraction**: Low-level drivers for JTAG debuggers, serial ports, VISA instruments, and power relays.

---

## Data Flow

```
Suite YAML --> Test Discovery --> Test Execution --> Result Collection --> Reporting
                    |                   |                   |
              Tag Filtering      Board Setup /        JUnit XML
              Platform Match     Instrument Init      HTML Report
                                 Power Cycle          Coverage
                                 UART Commands        Traceability
```

1. **Discovery**: The suite YAML is parsed. Tests are filtered by platform, tags, and availability.
2. **Setup**: Board fixtures initialize JTAG, flash firmware, open UART, connect instruments.
3. **Execution**: Each test function runs with configurable timeout and retry. Results are captured.
4. **Teardown**: Board is reset, instruments disconnected, resources released.
5. **Reporting**: Results are aggregated into JUnit XML, HTML reports, coverage summaries, and traceability matrices.

---

## Extension Points

### Adding a New Board

1. Create a YAML config in `config/boards/`
2. If the board requires a custom flash or reset sequence, extend the `targets/` module

### Adding a New Instrument

1. Create a YAML config in `config/instruments/`
2. Add a driver class in `framework/instruments/` inheriting from `SCPIBase`
3. Implement `connect()`, `configure()`, `measure()`, and `close()` methods

### Adding a New Test Module

1. Create a test file in `tests/unit/`, `tests/integration/`, `tests/safety/`, or `tests/rf/`
2. Use pytest fixtures for board and instrument access
3. Add tests to a suite YAML for scheduled execution

### Custom Reporters

The `result_collector.py` module supports pluggable reporters. Implement the `Reporter` interface and register it in `framework_config.yaml`.

---

## Plugin Model

The framework uses pytest plugins for extensibility:

- **`conftest.py` fixtures**: Board connection, instrument handles, firmware flash
- **`pytest_addoption`**: CLI options like `--board-config`, `--suite`, `--no-retry`
- **`pytest_collection_modifyitems`**: Filter tests by suite YAML and platform
- **`pytest_runtest_makereport`**: Capture detailed failure info and screenshots

### Key Fixtures

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `board` | session | Connected board with JTAG and UART |
| `firmware` | session | Flashed and booted firmware |
| `spectrum_analyzer` | session | Connected spectrum analyzer |
| `signal_generator` | session | Connected signal generator |
| `uart` | function | Fresh UART session per test |
| `power_control` | session | USB relay for power cycling |

---

## Directory Structure

```
mmwave-firmware-ci-framework/
  framework/           # Core Python framework
    core/              # Runner, discovery, results
    instruments/       # SCPI instrument drivers
    radar/             # Radar domain logic
    safety/            # Safety test support
    targets/           # Board/target abstraction
    utils/             # Shared utilities
  tests/               # All test cases
    unit/              # Host-only unit tests
    integration/       # Hardware-in-the-loop tests
    safety/            # Safety qualification tests
    rf/                # RF performance tests
  config/              # YAML configuration
    boards/            # Board definitions
    test_suites/       # Test suite definitions
    instruments/       # Instrument configs
  scripts/             # Perl/Lua utility scripts
  templates/           # Jinja2 report templates
  docs/                # Documentation
  docker/              # Container definitions
  on_target/           # On-target test harness (C code)
  .github/workflows/   # CI pipeline definitions
```
