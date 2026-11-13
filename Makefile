.PHONY: install test lint evals evals-live evals-live-case demo demo-dry serve

PYTHON ?= python

install:  ## Install the package and dev tools into the current environment
	$(PYTHON) -m pip install -e ".[dev]"

test:  ## Run the test suite (mock model, no API key needed)
	$(PYTHON) -m pytest

lint:  ## Check code style
	$(PYTHON) -m ruff check .

evals:  ## Run the eval cases on the mock model (no API key needed)
	$(PYTHON) -m leadgen.evals

evals-live:  ## OPTIONAL: run the eval cases on the REAL model from .env. Costs tokens. Never used by CI or `make test`.
	$(PYTHON) -m leadgen.evals --live

evals-live-case:  ## OPTIONAL: run ONE eval case on the REAL model: make evals-live-case CASE=01_hot_home
	@test -n "$(CASE)" || (echo "Usage: make evals-live-case CASE=<case id>, e.g. CASE=01_hot_home"; exit 2)
	$(PYTHON) -m leadgen.evals --live --case $(CASE)

demo:  ## One-command demo: sample leads end to end on the mock model, saved to data/runtime/demo
	LEADGEN_MOCK_LLM=1 LEADGEN_DATA_DIR=data/runtime/demo $(PYTHON) -m leadgen --source sample

demo-dry:  ## Same demo as a dry run: prints everything, writes nothing
	LEADGEN_MOCK_LLM=1 $(PYTHON) -m leadgen --source sample --dry-run

serve:  ## Start the local API for the dashboard (settings come from .env)
	$(PYTHON) -m leadgen.server
