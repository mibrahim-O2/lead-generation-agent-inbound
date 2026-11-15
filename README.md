# Inbound Lead Generation Agent

An AI agent that reads new customer enquiries, works out what is missing,
scores the lead, decides where it should go, and writes a **draft** reply for a
human to approve. Built with the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) (Python).

> **Demo project.** Everything here is dummy data for a fictional company,
> "Example Solar Co" (solar panels, inverters, batteries, installation and net
> metering in Lahore). No real company, customer or contact details are used.

**New here? Start with [USER.md](USER.md)**, the step-by-step guide: install, run
the demo, set up `.env`, the dashboard, Google Sheets, switching models, and
troubleshooting.

| Guide | For |
| --- | --- |
| [USER.md](USER.md) | Using the project from a fresh clone |
| [MODEL_SWITCH.md](MODEL_SWITCH.md) | Using a provider other than OpenAI |
| [docs/GOOGLE_SHEETS.md](docs/GOOGLE_SHEETS.md) | The optional Google Sheets live demo |
| [dashboard/README.md](dashboard/README.md) | The dashboard and its two modes |
| [evals/README.md](evals/README.md) | Eval cases, including the live runs |

## What it does

A new enquiry arrives (web form, webhook, or a row from `data/sample_leads.csv`). The agent:

1. Understands the message: intent, property type, monthly bill, location, timeline, product interest, urgency.
2. Decides what is missing and drafts a reply asking the right questions.
3. Scores the lead 1 to 10 using the rule book in `presets/solar.yaml`.
4. Routes it: draft reply, human handover, nurture, or spam.
5. Saves everything and leaves a draft reply waiting for human approval.

## Safety rules

- **Drafts only.** The agent never sends anything. A human reviews and sends.
- No promises about prices, savings, delivery dates or net-metering approval.
- No electrical, legal or tax advice.
- Angry, complaint or legal-threat messages go straight to a human.
- The lead's message is treated as data, never as instructions.
- Hard limits on leads per run, tool calls per lead and tokens per run.

## Status

| Task | Branch | State |
| --- | --- | --- |
| 1. Scaffold | `feat/scaffold` | done |
| 2. Core agent, tools, evals, API server | `feat/core-agent` | done |
| Agent tuning and live-eval diagnostics | `fix/agent-tuning`, `fix/live-eval-diagnostics` | done |
| Google Sheets live demo (optional) | `feat/google-sheets-demo` | done |
| 3. Provider switch (`llm.py`, `MODEL_SWITCH.md`) | `feat/model-switch` | done |
| 4. Dashboard (React + Vite, GitHub Pages) | `feat/dashboard` | done |
| 5. User guide (`USER.md`) | `docs/user-guide` | done |

The agent, its tools, the guardrails, the local API and the evals work today,
using OpenAI or the built-in mock model. Other providers and the dashboard are next.

## Quick start

Needs Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
make install
make demo
```

`make demo` runs the five sample leads end to end on the built-in mock model: no
API key, no network, no cost. It prints each lead's score, route and draft reply,
and saves the results under `data/runtime/demo/` (git-ignored).

```bash
make test
make evals
```

Both run without a key.

Two optional commands run the eval cases on your real model. They cost tokens,
have caps on leads and tokens, and never run in CI or in `make test`:

| Command | What it does |
| --- | --- |
| `make evals-live` | All eval cases on the real model. Prints a table and writes `data/runtime/live-eval-report.json`. |
| `make evals-live-case CASE=01_hot_home` | One case only: the cheap way to retry a failure. |

The table shows the handover reason for every handover and every rejected draft
with the check that failed. See [evals/README.md](evals/README.md).

### How a lead is scored

Five signals from `presets/solar.yaml`, added up and clamped to 1-10. A lead is hot
at 7 or more.

| Signal | Points |
| --- | --- |
| Property type | factory 3; business, farm or home 2 |
| Energy size | monthly bill OR sanctioned load in kW, whichever gives more (up to 3) |
| Location fit | core area 2, nearby 1 |
| Timeline | this month 2, within 3 months 1 |
| Intent | site visit or survey 2, quote or price request 1 |

## Running with a real model

```bash
cp example.env .env
```

Open `.env` and set `OPENAI_API_KEY`. `example.env` explains every variable. Never
commit `.env`. Then:

```bash
python -m leadgen --source sample --dry-run
```

| Flag | Meaning |
| --- | --- |
| `--dry-run` | Runs the full agent, prints what it would do, writes nothing. |
| `--limit N` | Process at most N leads. |
| `--source sample` | Read `data/sample_leads.csv` (default). |
| `--source file --file leads.csv` | Read your own CSV or JSON file. |
| `--source webhook` | Process leads queued through the local API. |
| `--source sheet` | Process new rows in the Google Sheet's Inbox tab (optional feature). |
| `--watch --interval 10` | With `--source sheet`: keep checking for new rows until Ctrl+C. |
| `--delay 3` | Pause between leads, for live demos. |

Without `--dry-run`, leads, drafts and the run log are saved under `data/runtime/`.
Nothing is ever sent in either mode.

## Using another model provider

OpenAI is the default. Anthropic, Google Gemini, Mistral, DeepSeek, Groq,
OpenRouter, a local Ollama model or any OpenAI-compatible server can be selected
in `.env` with `LLM_PROVIDER` and `LLM_MODEL`, with no code change. See
[MODEL_SWITCH.md](MODEL_SWITCH.md). Only OpenAI has been run with a real key.

## Google Sheets live demo (optional)

A Google Sheet can fill up row by row while the agent works, which is handy for a
screen recording. It is off by default and needs an optional install:

```bash
pip install -e ".[sheets]"
```

```bash
make demo-sheet
```

Setup takes about 15 minutes and is explained step by step in
[docs/GOOGLE_SHEETS.md](docs/GOOGLE_SHEETS.md). New enquiries can also be typed
into the sheet's Inbox tab and processed with `--source sheet` (add `--watch` to
keep polling). A dry run never writes to the sheet, and mock mode never contacts
Google unless you opt in.

## Local API

```bash
make serve
```

| Endpoint | Purpose |
| --- | --- |
| `POST /leads` | Queue a new enquiry (name, email, phone, channel, message). |
| `GET /leads` | Processed leads and the pending queue. |
| `GET /runs` | Run history. |
| `POST /run` | Process leads now: `{"source": "webhook" or "sample", "dry_run": false, "limit": 5}`. |
| `POST /leads/{id}/review` | Record a human decision: `{"action": "approve"}`, `"reject"` or `"handover"`. Changes the status only; sends nothing. |

The API has no login. Keep it on `127.0.0.1`.

## Dashboard

A static React page shows the leads table (score, route, status), each lead's
drafted reply, run history, today's counts and the average score.

```bash
make dashboard-install
```

```bash
make dashboard-demo
```

That opens demo mode at http://localhost:5173 with bundled dummy data. For local
mode, which reads your own runs and has working Approve, Reject and Hand over
buttons, run `make serve` in one terminal and `make dashboard-dev` in another.
The buttons record a decision; they never send anything.

The demo version is published to GitHub Pages by a workflow. Details are in
[dashboard/README.md](dashboard/README.md).

## How the rules are enforced

The agent chooses its own tools and steps, but the hard rules do not depend on it
behaving:

- There is no tool that sends anything. Drafts are stored as `pending_approval`.
- `draft_reply` rejects any draft containing a forbidden claim.
- Complaints, anger, legal threats and safety incidents are detected in code on the
  raw message and force a human handover, whatever the agent decided.
- The score always comes from the rubric in `presets/solar.yaml`, never from the model.
- Whether a genuine lead is `draft_reply` or `nurture` is decided in code from the
  facts (the `nurture` block in `presets/solar.yaml`): a "later" timeline, no quote
  or site visit requested, and a score of 5 or less. A hot lead is never nurture.
- Every rejected draft is recorded with its attempt number, the check that failed
  and the fix the agent was told to make. Every handover carries its reason. Both
  appear in the run output and in the saved record.
- The duplicate check runs in code before the agent starts. It does not depend on
  the agent calling a tool.
- What is "missing" is worked out in code from the extracted fields and the contact
  details on file, so a stated fact is never asked for again. The questions the
  agent may ask come from that list.
- `draft_reply` also rejects a draft in the wrong language (English for English,
  Roman Urdu for Roman Urdu, Urdu script only if the lead used it), a draft with
  more than 3 questions (1 for a nurture note), and a draft asking for contact
  details that are already on file. Restating the customer's own bill, saying the
  team will call the number on file, or saying that pricing comes in a written
  proposal is allowed; any other rupee amount, date or timeframe is not.
- The message is wrapped as untrusted data and screened for injection attempts;
  suspicious leads go to a human.
- Limits on leads per run, tool calls per lead and tokens per run stop a runaway run.

The mock model is keyword matching for demos and tests. It shows the pipeline
working; it does not show how well a real model understands messages.

## Layout

```
src/leadgen/        Python package
  agent.py          agent instructions and tool wiring
  tools.py          the tools the agent can call
  guardrails.py     hard rules enforced in code
  llm.py            the only module that touches model providers
  config.py         layered config: defaults -> preset -> client
  context.py        per-lead working state shared by the tools
  scoring.py        the scoring rubric, applied in code
  evals.py          eval runner
  storage.py        storage interface (local JSON/CSV by default)
  sheets.py         optional Google Sheets mirror and Inbox source
  runner.py         run loop, limits, dry run
  runlog.py         run history and cost estimates
  server.py         local FastAPI server for the dashboard
  cli.py            command line: --dry-run, --limit, --source
presets/solar.yaml  niche rule book
config/client.yaml  client values (fictional)
data/               sample leads and FAQ (dummy); runtime files are git-ignored
evals/cases/        20 evaluation cases
dashboard/          React + TypeScript dashboard (demo and local modes)
tests/              test suite
```

## Configuration layers

Settings resolve in three layers, so another client or niche needs no code change:

1. built-in defaults
2. niche preset (`presets/solar.yaml`)
3. client values (`config/client.yaml`)

## Contributing

`main` is never committed to directly. Each task gets its own branch and a pull request, which is reviewed before merging.

## License

[MIT](LICENSE)
