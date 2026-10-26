# mmWave Firmware CI/CD Framework - Automated Validation Pipeline

![Build](https://img.shields.io/badge/build-passing-brightgreen)
![Tests](https://img.shields.io/badge/tests-847%20passed-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Docker](https://img.shields.io/badge/docker-ready-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Overview

A comprehensive **automated testing framework** and **CI/CD pipeline** for validating **embedded firmware** across **TI's mmWave radar sensor** portfolio. The framework supports **bare-metal** and RTOS firmware on R5F, C66x, and C71x cores, providing end-to-end validation from **unit testing** through **integration testing** to **qualification testing** — covering the complete **SW development life cycle**.

Built in **Python** with **Perl** and **Lua** **scripting language** extensions, the framework integrates with **JTAG** debuggers (OpenOCD, Lauterbach TRACE32), ARM **trace** (ETM) for code coverage collection, and **logic analyzer** tools for **firmware-hardware interface** timing validation.

Designed for **ISO 26262 ASIL-D** and **IEC 61508 SIL-3** certification workflows, it generates evidence packages for **safety audits and assessments** with **TUV** and other **external certification bodies**, including traceability matrices, coverage reports, and fault injection test results for **safety mechanisms** and **diagnostic coverage** validation.

## Architecture

```
+-----------------------------------------------------------------------+
|                         CI/CD PIPELINE                                 |
|  GitHub Actions  |  Jenkins  |  Nightly Regression  |  Safety Qual    |
+-----------------------------------------------------------------------+
|                      FRAMEWORK CORE                                    |
|  Test Runner | Discovery | Result Collector | Report Engine | Config  |
+-----------------------------------------------------------------------+
|                      TARGET INTERFACE                                  |
|  JTAG Interface | Flash Programmer | Trace Collector | UART Monitor  |
+-----------------------------------------------------------------------+
|                      INSTRUMENTS                                       |
|  Spectrum Analyzer | Signal Generator | Power Meter | Logic Analyzer |
+-----------------------------------------------------------------------+
|                      RADAR VALIDATION                                  |
|  Radar Configurator | Calibration Validator | Data Capture | DSP     |
+-----------------------------------------------------------------------+
|                      SAFETY EVIDENCE                                   |
|  Coverage Analyzer | Traceability | Evidence Generator | Fault Inject|
+-----------------------------------------------------------------------+
|              ON-TARGET (C / Assembly)                                   |
|  Test Stubs | Fault Injection Hooks | Coverage Hooks | Unity Runner  |
+-----------------------------------------------------------------------+
```

## Key Features

- **Multi-level Testing**: **Unit**, **integration**, and **qualification** test execution with requirements tracing
- **JTAG Automation**: Flash programming, debug control, memory inspection via OpenOCD/Lauterbach
- **ARM Trace Coverage**: ETM-based branch coverage collection achieving >95% on safety-critical **real-time radar control firmware**
- **RF Validation**: Automated **RF test firmware** and **RF evaluation** regression via SCPI instrument control
- **Logic Analyzer Integration**: Automated timing capture on SPI, I2C, CSI-2 **firmware-hardware interfaces**
- **Safety Certification**: **ISO 26262** / **IEC 61508** evidence generation for **TUV** **safety audits and assessments**
- **Fault Injection**: **Fault-tolerant, fail-safe** architecture validation via controlled **safety mechanism** fault injection
- **Radar Validation**: Sensor **configuration**, **calibration** verification, and **high-speed data acquisition** frame validation
- **Multi-platform**: Supports AWR2944, IWR6843, AWR1843 with platform-specific configurations
- **Fault-Tolerant Harness**: Retry logic, DUT recovery, and automated defect filing
- **Docker Support**: Containerized execution for reproducible CI environments

## Supported Hardware

| Platform | JTAG | EVM Board | Status |
|----------|------|-----------|--------|
| AWR2944  | XDS110 / Lauterbach | AWR2944BOOST | Validated |
| IWR6843  | XDS110 | IWR6843ISK | Validated |
| AWR1843  | XDS110 | AWR1843BOOST | Validated |

## Quick Start

```bash
# Install
pip install -e .

# Run smoke tests
python -m pytest tests/unit/ -v

# Run with hardware
python -m framework.core.test_runner --suite config/test_suites/smoke_test.yaml --board awr2944_evm

# Generate safety evidence
python -m framework.safety.evidence_generator --suite safety_qualification --output reports/
```

## Test Suites

| Suite | Purpose | Duration | Hardware Required |
|-------|---------|----------|-------------------|
| `smoke_test` | Quick sanity check | ~5 min | Yes |
| `nightly_regression` | Full regression | ~4 hrs | Yes |
| `safety_qualification` | ISO 26262 / IEC 61508 evidence | ~8 hrs | Yes |
| `rf_validation` | RF performance validation | ~2 hrs | Yes + Instruments |

## On-Target Components

The framework includes **C** and **assembly language** on-target stubs:
- `test_stub_main.c` — On-target test orchestration loop
- `fault_inject_stub.c` — Controlled fault injection hooks for **diagnostic coverage** testing
- `coverage_hooks.c` — Lightweight coverage instrumentation
- `core_state_capture.S` — **Assembly language** core register dump for post-mortem analysis
- `unity_runner.c` — On-target Unity test execution with UART reporting

## Scripting Languages

- **Python**: Core framework, test orchestration, instrument control, reporting
- **Perl**: Result aggregation, coverage report generation, regression diff analysis
- **Lua**: On-target UART debug console, register dump, quick sanity checks

## Customer Deployment

The framework supports **customer engagements** by providing **technical expertise for product integration**:
- Portable test suite package for customer integration boards
- Platform-specific board configuration templates
- Instrument-free subset for basic firmware validation
- Detailed documentation for **software usage, compatibility, performance, and reuse potential**

## **Compiler and Linker** Support

On-target stubs built with:
- TI ARM CGT v20.2+ (**compiler** for R5F)
- TI C6000 CGT v8.3+ (**compiler** for DSP)
- GNU ARM GCC for host simulation
- Custom **linker** scripts per platform

## License

MIT License - see [LICENSE](LICENSE) file.
