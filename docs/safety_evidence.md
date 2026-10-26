# Safety Evidence Generation Guide

This guide describes how to use the mmWave Firmware CI Framework to generate safety evidence for functional safety certification under ISO 26262 and IEC 61508.

## Table of Contents

1. [Overview](#overview)
2. [ISO 26262 ASIL-D Evidence Requirements](#iso-26262-asil-d-evidence-requirements)
3. [IEC 61508 SIL-3 Evidence Requirements](#iec-61508-sil-3-evidence-requirements)
4. [Running Qualification Suites](#running-qualification-suites)
5. [Generating TUV Audit Packages](#generating-tuv-audit-packages)
6. [Coverage Requirements](#coverage-requirements)

---

## Overview

Functional safety certification requires demonstrating that firmware has been tested with sufficient rigor. This framework generates the following evidence artifacts:

- **Test execution reports** with pass/fail status and traceability
- **Code coverage reports** (statement, branch, MC/DC)
- **Requirements traceability matrix** linking requirements to test cases
- **Safety mechanism test evidence** (MPU, ECC, watchdog, CRC)
- **Regression analysis** showing no degradation between releases

All evidence is generated in auditable, version-controlled formats suitable for submission to certification bodies (TUV, SGS, UL).

---

## ISO 26262 ASIL-D Evidence Requirements

ISO 26262:2018 Part 6 specifies the following verification methods for ASIL-D software:

### Required Test Methods (Table 9)

| Method | ISO Reference | Framework Support |
|--------|--------------|-------------------|
| Requirements-based testing | Part 6, 9.4.2 | Requirement markers + traceability report |
| Interface testing | Part 6, 9.4.2 | Integration test suite |
| Fault injection testing | Part 6, 9.4.2 | Safety qualification suite |
| Resource usage testing | Part 6, 9.4.2 | Memory/stack tests |
| Back-to-back testing | Part 6, 9.4.5 | Model vs. target comparison |

### Required Coverage Metrics (Table 12)

| Metric | ASIL-D Requirement | Framework Target |
|--------|-------------------|-----------------|
| Statement coverage | Highly recommended | 100% (safety-critical) |
| Branch coverage | Highly recommended | 100% (safety-critical) |
| MC/DC coverage | Highly recommended | 80% minimum |

### Evidence Artifacts

1. **Software Verification Report** - Generated HTML/PDF test report
2. **Software Test Specification** - Test suite YAML with requirement IDs
3. **Traceability Matrix** - Auto-generated from test markers
4. **Coverage Analysis** - gcov/lcov output with threshold enforcement

---

## IEC 61508 SIL-3 Evidence Requirements

IEC 61508:2010 Part 3, Annex A defines techniques for SIL-3:

### Required Techniques

| Technique | IEC Reference | Framework Support |
|-----------|--------------|-------------------|
| Boundary value analysis | Table A.3 | Parameterized tests |
| Equivalence classes | Table A.3 | Test case design |
| Error guessing | Table A.5 | Fault injection tests |
| Structural test coverage | Table B.2 | Branch + MC/DC coverage |
| Performance testing | Table A.6 | Timing validation tests |

### Diagnostic Coverage

For SIL-3, the framework validates:

- **Memory protection**: MPU region isolation, stack overflow detection
- **Data integrity**: ECC single-bit correction, double-bit detection
- **Execution monitoring**: Watchdog timeout, window violation
- **Communication integrity**: CRC32 validation, checksum verification
- **CPU self-test**: Register march test, ALU verification

---

## Running Qualification Suites

### Prerequisites

1. Controlled lab environment with calibrated equipment
2. Board in known-good state with qualified firmware image
3. No concurrent tests or debug sessions
4. Test operator with appropriate training

### Execution

```bash
# Run ASIL-D safety qualification suite
pytest tests/safety/ -v \
    --board-config=config/boards/awr2944_evm.yaml \
    --suite=config/test_suites/safety_qualification.yaml \
    --no-retry \
    --junit-xml=reports/safety_evidence/junit_results.xml \
    --html=reports/safety_evidence/test_report.html

# Generate coverage report
make test-unit  # with gcov instrumentation
perl scripts/perl/coverage_report.pl \
    --input reports/coverage.info \
    --output reports/safety_evidence/coverage_summary.md \
    --line-threshold 100 \
    --branch-threshold 100
```

### Important Notes

- **No retries**: Qualification tests must not use retry logic. A failure is a real failure.
- **Clean environment**: Power-cycle the board before each qualification run.
- **Reproducibility**: Record firmware version, board serial number, and environment conditions.
- **Witnessing**: For TUV audit, tests may need to be run in the presence of an assessor.

---

## Generating TUV Audit Packages

The audit package generator creates a structured archive suitable for certification body review:

```bash
python -m framework.safety.generate_audit_package \
    --test-report reports/safety_evidence/test_report.html \
    --coverage-report reports/safety_evidence/coverage_summary.md \
    --traceability reports/safety_evidence/traceability.html \
    --output reports/audit_package/
```

### Audit Package Contents

```
audit_package/
  01_test_specification/
    safety_qualification.yaml
    smoke_test.yaml
  02_test_results/
    test_report.html
    junit_results.xml
  03_coverage_analysis/
    coverage_summary.md
    coverage_report.html
    lcov_raw_data.info
  04_traceability/
    traceability_report.html
    requirements_matrix.csv
  05_environment/
    board_config.yaml
    instrument_configs/
    framework_version.txt
  06_signatures/
    test_operator.txt
    review_checklist.md
```

---

## Coverage Requirements

### Thresholds by Safety Level

| Module Type | Line Coverage | Branch Coverage | MC/DC Coverage |
|-------------|--------------|-----------------|----------------|
| Safety-critical (ASIL-D) | 100% | 100% | 80% |
| Safety-related (ASIL-B/C) | 95% | 95% | N/A |
| Non-safety | 90% | 90% | N/A |

### Measuring Coverage

The framework uses gcov/lcov for C code coverage and pytest-cov for Python:

```bash
# C code coverage (on-target stubs)
make on-target COVERAGE=1
lcov --capture --directory on_target/ --output-file reports/coverage.info
lcov --remove reports/coverage.info '*/test_*' --output-file reports/coverage.info

# Python framework coverage
pytest tests/unit/ --cov=framework --cov-report=html --cov-branch
```

### Excluding Non-Safety Code

Configure exclusion patterns in `config/framework_config.yaml`:

```yaml
coverage:
  exclude_patterns:
    - "*/test_*"
    - "*/conftest.py"
    - "*/mock_*"
```

Only safety-critical modules are held to 100% coverage. The coverage report flags any files below their applicable threshold.
