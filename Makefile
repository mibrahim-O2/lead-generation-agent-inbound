.PHONY: install test lint demo

PYTHON ?= python

install:  ## Install the package and dev tools into the current environment
	$(PYTHON) -m pip install -e ".[dev]"

test:  ## Run the test suite (no API key needed)
	$(PYTHON) -m pytest

lint:  ## Check code style
	$(PYTHON) -m ruff check .

demo:  ## One-command demo (the agent itself arrives in the core-agent task)
	$(PYTHON) -m leadgen --source sample --dry-run
