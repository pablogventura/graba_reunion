.PHONY: setup install test lint format check

setup:
	bash scripts/setup.sh

install:
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest -q --cov=graba_reunion

lint:
	.venv/bin/ruff check src tests

format:
	.venv/bin/ruff format src tests

check: lint test
