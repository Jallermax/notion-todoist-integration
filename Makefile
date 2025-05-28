# Makefile for task hierarchy testing

.PHONY: help install test test-fast test-performance test-coverage lint format type-check clean

# Default target
help:
	@echo "Available targets:"
	@echo "  install         - Install testing dependencies"
	@echo "  test           - Run all tests"
	@echo "  test-fast      - Run tests excluding performance tests"
	@echo "  test-performance - Run only performance tests"
	@echo "  test-coverage  - Run tests with coverage report"
	@echo "  test-parallel  - Run tests in parallel"
	@echo "  lint           - Run code linting"
	@echo "  format         - Format code with black and isort"
	@echo "  type-check     - Run type checking with mypy"
	@echo "  clean          - Clean up generated files"

# Install dependencies
install:
	pip install -r requirements-test.txt

# Run all tests
test:
	pytest

# Run tests excluding performance tests (faster for development)
test-fast:
	pytest -m "not performance"

# Run only performance tests
test-performance:
	pytest -m "performance"

# Run tests with coverage
test-coverage:
	pytest --cov=. --cov-report=html --cov-report=term-missing

# Run tests in parallel (requires pytest-xdist)
test-parallel:
	pytest -n auto

# Run tests with verbose output and stop on first failure
test-debug:
	pytest -vvv -x

# Continuous testing (watch for changes)
test-watch:
	ptw -- --testmon

# Code quality checks
lint:
	flake8 .

format:
	black .
	isort .

type-check:
	mypy .

# Run all quality checks
quality: lint type-check

# Clean up generated files
clean:
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete