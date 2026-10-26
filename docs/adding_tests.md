# Adding New Tests

This guide covers how to add new test cases to the mmWave Firmware CI Framework.

## Table of Contents

1. [Test File Naming Conventions](#test-file-naming-conventions)
2. [Test Structure](#test-structure)
3. [Using Fixtures](#using-fixtures)
4. [Requirement Tracing](#requirement-tracing)
5. [Tagging and Filtering](#tagging-and-filtering)
6. [Adding to a Test Suite](#adding-to-a-test-suite)

---

## Test File Naming Conventions

All test files must follow these naming conventions for automatic discovery:

| Category | Directory | File Pattern | Example |
|----------|-----------|-------------|---------|
| Unit tests | `tests/unit/` | `test_*.py` | `test_config_parser.py` |
| Integration tests | `tests/integration/` | `test_*.py` | `test_radar_data_path.py` |
| Safety tests | `tests/safety/` | `test_*.py` | `test_memory_protection.py` |
| RF tests | `tests/rf/` | `test_*.py` | `test_tx_performance.py` |

Test functions within files must be prefixed with `test_`:

```python
def test_firmware_boots_successfully(board):
    """Verify firmware boots and responds on UART."""
    ...
```

Test classes should be prefixed with `Test`:

```python
class TestChirpConfiguration:
    def test_valid_chirp_params(self, board):
        ...
    def test_invalid_slope_rejected(self, board):
        ...
```

---

## Test Structure

A typical integration test follows this pattern:

```python
"""Tests for radar data path validation."""

import pytest
from framework.radar import ChirpConfig

class TestRadarDataPath:
    """Validate radar ADC data path end-to-end."""

    def test_adc_data_not_all_zeros(self, board, firmware):
        """ADC output should contain non-zero samples after chirp."""
        config = ChirpConfig(
            start_freq_ghz=77.0,
            slope_mhz_per_us=70.0,
            num_samples=256,
            num_chirps=128,
        )
        board.configure_chirp(config)
        board.trigger_frame()
        data = board.read_adc_data()

        assert len(data) > 0, "No ADC data received"
        assert any(sample != 0 for sample in data), "All ADC samples are zero"

    def test_frame_capture_correct_size(self, board, firmware):
        """Captured frame should match expected dimensions."""
        expected_samples = 256 * 128 * 4  # samples * chirps * rx_channels
        board.trigger_frame()
        data = board.read_adc_data()

        assert len(data) == expected_samples, (
            f"Frame size mismatch: got {len(data)}, expected {expected_samples}"
        )
```

---

## Using Fixtures

### Available Fixtures

The framework provides these pytest fixtures via `conftest.py`:

```python
def test_example(board, firmware, uart, spectrum_analyzer):
    # board        - Connected board with JTAG/UART (session scope)
    # firmware     - Flashed and booted firmware (session scope)
    # uart         - Fresh UART handle (function scope)
    # spectrum_analyzer - Connected SA instrument (session scope)
    pass
```

### Custom Fixtures

Define test-specific fixtures in a local `conftest.py`:

```python
# tests/integration/conftest.py

import pytest
from framework.radar import ChirpConfig

@pytest.fixture
def default_chirp_config():
    """Standard chirp configuration for integration tests."""
    return ChirpConfig(
        start_freq_ghz=77.0,
        slope_mhz_per_us=70.0,
        num_samples=256,
        num_chirps=128,
    )
```

---

## Requirement Tracing

For safety-critical tests, link each test to requirement IDs using the `requirement` marker:

```python
import pytest

@pytest.mark.requirement("SW-SAF-001", "SW-SAF-002")
def test_stack_overflow_detection(board):
    """MPU must detect and trap stack overflow conditions."""
    board.inject_stack_overflow()
    status = board.read_safety_status()
    assert status.stack_overflow_detected, "Stack overflow was not detected"
```

The traceability report template automatically collects these markers and generates the requirements-to-tests mapping.

---

## Tagging and Filtering

### Applying Tags

Use `pytest.mark` to tag tests:

```python
@pytest.mark.smoke
@pytest.mark.boot
def test_firmware_boot(board):
    ...

@pytest.mark.safety
@pytest.mark.slow
def test_full_memory_march(board):
    ...
```

Register custom markers in `pytest.ini` or `pyproject.toml`:

```ini
[pytest]
markers =
    smoke: Quick sanity tests
    boot: Boot-related tests
    safety: Safety qualification tests
    rf: RF performance tests
    slow: Tests that take > 60 seconds
```

### Filtering at Runtime

```bash
# Run only smoke tests
pytest -m smoke

# Run safety tests excluding slow ones
pytest -m "safety and not slow"

# Run tests matching a keyword
pytest -k "chirp"
```

---

## Adding to a Test Suite

After creating your test, add it to the appropriate suite YAML in `config/test_suites/`:

```yaml
tests:
  - name: test_my_new_feature
    module: tests.integration.test_my_module
    function: test_my_new_feature
    timeout_s: 60
    tags: [integration, feature_x]
    description: "Verify new feature X works correctly"
```

Fields:
- `name`: Unique test identifier within the suite
- `module`: Python module path (dot-separated)
- `function`: Test function name
- `timeout_s`: Maximum execution time
- `tags`: List of tags for filtering
- `requirement_ids`: (optional) Linked safety requirements
- `description`: Human-readable description
