.PHONY: install test lint evals evals-live evals-live-case demo demo-dry demo-sheet serve dashboard-install dashboard-dev dashboard-demo dashboard-test dashboard-build dashboard-demo-data

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

DELAY ?= 3
demo-sheet:  ## OPTIONAL live demo: sample leads one by one into your Google Sheet (docs/GOOGLE_SHEETS.md). DELAY=seconds between leads.
	SHEETS_ENABLED=1 SHEETS_ALLOW_MOCK=1 LEADGEN_DATA_DIR=data/runtime/demo $(PYTHON) -m leadgen --source sample --demo --delay $(DELAY)

serve:  ## Start the local API for the dashboard (settings come from .env)
	$(PYTHON) -m leadgen.server

# --- Dashboard (needs Node.js 20+; see dashboard/README.md) --------------------
API_URL ?= http://127.0.0.1:8000

dashboard-install:  ## Install the dashboard's npm packages (once)
	cd dashboard && npm install

dashboard-dev:  ## Dashboard in LOCAL mode at http://localhost:5173 (run `make serve` in another terminal)
	cd dashboard && VITE_API_URL=$(API_URL) npm run dev

dashboard-demo:  ## Dashboard in DEMO mode at http://localhost:5173 (bundled dummy data, no API)
	cd dashboard && VITE_API_URL= npm run dev

dashboard-test:  ## Type check and unit tests for the dashboard
	cd dashboard && npm run typecheck && npm test

dashboard-build:  ## Production build of the DEMO site into dashboard/dist
	cd dashboard && VITE_API_URL= npm run build

dashboard-demo-data:  ## Regenerate the dashboard's bundled demo data from the mock model
	$(PYTHON) dashboard/scripts/make_demo_data.py
