# mmWave Firmware CI Framework
# Build, test, and utility targets

.PHONY: install test test-unit test-integration test-safety test-rf lint clean on-target docs help

BOARD_CONFIG ?= config/boards/awr2944_evm.yaml
SUITE_CONFIG ?= config/test_suites/nightly_regression.yaml
PYTHON ?= python
PYTEST ?= pytest
COVERAGE_THRESHOLD ?= 80

help: ## Show this help message
	@echo "mmWave Firmware CI Framework - Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install framework in development mode
	pip install -e ".[dev]"

test: test-unit ## Run default test suite (unit tests)

test-unit: ## Run unit tests with coverage
	$(PYTEST) tests/unit/ -v \
		--cov=framework \
		--cov-report=html:reports/htmlcov \
		--cov-report=term-missing \
		--cov-branch \
		--junit-xml=reports/junit/unit_results.xml

test-integration: ## Run integration tests (requires connected board)
	$(PYTEST) tests/integration/ -v \
		--board-config=$(BOARD_CONFIG) \
		--suite=$(SUITE_CONFIG) \
		--junit-xml=reports/junit/integration_results.xml

test-safety: ## Run safety qualification tests (no retries)
	$(PYTEST) tests/safety/ -v \
		--board-config=$(BOARD_CONFIG) \
		--suite=config/test_suites/safety_qualification.yaml \
		--no-retry \
		--junit-xml=reports/junit/safety_results.xml

test-rf: ## Run RF validation tests (requires instruments)
	$(PYTEST) tests/rf/ -v \
		--board-config=$(BOARD_CONFIG) \
		--suite=config/test_suites/rf_validation.yaml \
		--junit-xml=reports/junit/rf_results.xml

test-smoke: ## Run quick smoke test suite
	$(PYTEST) tests/integration/ -v \
		--board-config=$(BOARD_CONFIG) \
		--suite=config/test_suites/smoke_test.yaml \
		--junit-xml=reports/junit/smoke_results.xml

lint: ## Run linters and type checking
	flake8 framework/ tests/ --max-line-length=120 --statistics
	mypy framework/ --ignore-missing-imports

on-target: ## Build on-target test harness
	$(MAKE) -C on_target/harness/

coverage-check: ## Check coverage meets threshold
	$(PYTEST) tests/unit/ --cov=framework --cov-report=term --cov-fail-under=$(COVERAGE_THRESHOLD)

aggregate-results: ## Aggregate test results from JUnit XML files
	perl scripts/perl/result_aggregator.pl \
		--input-dir reports/junit/ \
		--output-csv reports/aggregated_results.csv \
		--output-txt reports/aggregated_summary.txt

coverage-report: ## Generate coverage report from lcov data
	perl scripts/perl/coverage_report.pl \
		--input reports/coverage.info \
		--output reports/coverage_summary.md

clean: ## Remove build artifacts and reports
	rm -rf build/ dist/ *.egg-info/
	rm -rf reports/ htmlcov/ .coverage .pytest_cache/
	rm -rf logs/*.log
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

docs: ## Generate documentation
	@echo "Generating documentation..."
	@echo "User Guide:        docs/user_guide.md"
	@echo "Architecture:      docs/architecture.md"
	@echo "Adding Tests:      docs/adding_tests.md"
	@echo "Instrument Setup:  docs/instrument_setup.md"
	@echo "Safety Evidence:   docs/safety_evidence.md"

docker-build: ## Build Docker image
	docker-compose -f docker/docker-compose.yml build

docker-test: ## Run tests in Docker
	docker-compose -f docker/docker-compose.yml run --rm framework
