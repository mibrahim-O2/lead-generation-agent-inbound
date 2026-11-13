# Inbound Lead Generation Agent

An AI agent that reads new customer enquiries, works out what is missing,
scores the lead, decides where it should go, and writes a **draft** reply for a
human to approve. Built with the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) (Python).

> **Demo project.** Everything here is dummy data for a fictional company,
> "Example Solar Co" (solar panels, inverters, batteries, installation and net
> metering in Lahore). No real company, customer or contact details are used.

## What it will do

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
| 1. Scaffold | `feat/scaffold` | this PR |
| 2. Core agent, tools, evals, API server | `feat/core-agent` | planned |
| 3. Provider switch (`llm.py`, `MODEL_SWITCH.md`) | `feat/model-switch` | planned |
| 4. Dashboard (React + Vite, GitHub Pages) | `feat/dashboard` | planned |
| 5. User guide and deploy docs | `docs/user-guide` | planned |

Right now the repo is a skeleton: the structure, tooling, tests and CI are in
place, and the agent itself arrives in task 2.

## Quick start

Needs Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
make install
make test
```

Tests run without any API key. To prepare for real runs later:

```bash
cp example.env .env
```

Then open `.env` and fill in your own key. `example.env` explains every variable. Never commit `.env`.

```bash
make demo
```

`make demo` currently prints a placeholder; it becomes the full one-command demo in task 2.

## Layout

```
src/leadgen/        Python package
  agent.py          agent instructions and tool wiring
  tools.py          the tools the agent can call
  guardrails.py     hard rules enforced in code
  llm.py            the only module that touches model providers
  config.py         layered config: defaults -> preset -> client
  storage.py        storage interface (local JSON/CSV by default)
  runner.py         run loop, limits, dry run
  runlog.py         run history and cost estimates
  server.py         local FastAPI server for the dashboard
  cli.py            command line: --dry-run, --limit, --source
presets/solar.yaml  niche rule book
config/client.yaml  client values (fictional)
data/               sample leads and FAQ (dummy); runtime files are git-ignored
evals/              evaluation cases
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
