# Inbound Lead Generation Agent

An AI agent that reads new customer enquiries, works out what is missing,
scores the lead, decides where it should go, and writes a **draft** reply for a
human to approve. Built with the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) (Python).

> **Demo project.** Everything here is dummy data for a fictional company,
> "Example Solar Co" (solar panels, inverters, batteries, installation and net
> metering in Lahore). No real company, customer or contact details are used.

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
| 3. Provider switch (`llm.py`, `MODEL_SWITCH.md`) | `feat/model-switch` | planned |
| 4. Dashboard (React + Vite, GitHub Pages) | `feat/dashboard` | planned |
| 5. User guide and deploy docs | `docs/user-guide` | planned |

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

Both run without a key. `make evals-live` is an optional extra that runs the same
eval cases on your real model, with caps on leads and tokens; see
[evals/README.md](evals/README.md). It costs tokens and never runs in CI.

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

Without `--dry-run`, leads, drafts and the run log are saved under `data/runtime/`.
Nothing is ever sent in either mode.

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

The API has no login. Keep it on `127.0.0.1`.

## How the rules are enforced

The agent chooses its own tools and steps, but the hard rules do not depend on it
behaving:

- There is no tool that sends anything. Drafts are stored as `pending_approval`.
- `draft_reply` rejects any draft containing a forbidden claim.
- Complaints, anger, legal threats and safety incidents are detected in code on the
  raw message and force a human handover, whatever the agent decided.
- The score always comes from the rubric in `presets/solar.yaml`, never from the model.
- The duplicate check runs in code before the agent starts. It does not depend on
  the agent calling a tool.
- What is "missing" is worked out in code from the extracted fields and the contact
  details on file, so a stated fact is never asked for again. The questions the
  agent may ask come from that list.
- `draft_reply` also rejects a draft in the wrong language (English for English,
  Roman Urdu for Roman Urdu, Urdu script only if the lead used it), a draft with
  more than 3 questions (1 for a nurture note), and a draft asking for contact
  details that are already on file.
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
  runner.py         run loop, limits, dry run
  runlog.py         run history and cost estimates
  server.py         local FastAPI server for the dashboard
  cli.py            command line: --dry-run, --limit, --source
presets/solar.yaml  niche rule book
config/client.yaml  client values (fictional)
data/               sample leads and FAQ (dummy); runtime files are git-ignored
evals/cases/        20 evaluation cases
dashboard/          React dashboard
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
