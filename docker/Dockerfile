# mmWave Firmware CI Framework
# Multi-stage build for test execution environment

FROM python:3.11-slim AS base

LABEL maintainer="firmware-ci@company.com"
LABEL description="mmWave Firmware CI Framework test environment"

# Install system dependencies and build tools for on-target stub compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc-arm-none-eabi \
    openocd \
    make \
    git \
    curl \
    libnewlib-arm-none-eabi \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy framework source
COPY . .

# Install framework in editable mode
RUN pip install --no-cache-dir -e ".[dev]"

# Build on-target test stubs
RUN if [ -d "on_target/harness" ]; then \
        make -C on_target/harness/ || true; \
    fi

# Create directories for reports and logs
RUN mkdir -p reports/junit reports/safety_evidence logs

# Default: run unit tests
CMD ["pytest", "tests/unit/", "-v", "--cov=framework", "--cov-report=html", "--junit-xml=reports/junit/unit_results.xml"]

# Healthcheck - verify framework is importable
HEALTHCHECK --interval=30s --timeout=5s --retries=1 \
    CMD python -c "import framework; print('OK')" || exit 1
