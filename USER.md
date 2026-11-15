# User guide

A step-by-step guide for someone who has just cloned this repo. No expert
knowledge is assumed. Every command is typed in a terminal, from the repo folder.

> This is a demo project with a fictional company ("Example Solar Co") and dummy
> data. Do not put real customer data or real company details into it.

## Contents

1. [What this project does](#1-what-this-project-does)
2. [Install](#2-install)
3. [Run the demo (no API key)](#3-run-the-demo-no-api-key)
4. [Set up `.env`](#4-set-up-env)
5. [Dry run and real run](#5-dry-run-and-real-run)
6. [Run with your own input](#6-run-with-your-own-input)
7. [Read the output](#7-read-the-output)
8. [The dashboard](#8-the-dashboard)
9. [Google Sheets live demo](#9-google-sheets-live-demo)
10. [Use another model provider](#10-use-another-model-provider)
11. [Change the rules without code](#11-change-the-rules-without-code)
12. [Tests and evals](#12-tests-and-evals)
13. [Working on a new task or change](#13-working-on-a-new-task-or-change)
14. [Troubleshooting](#14-troubleshooting)
15. [Safety notes](#15-safety-notes)
16. [Command reference](#16-command-reference)

## 1. What this project does

A new customer enquiry arrives. The agent:

1. reads the message and works out what the person wants,
2. scores the lead from 1 to 10 with a fixed rule book,
3. decides where it goes: a draft reply, a human handover, a nurture note, or spam,
4. writes a **draft** reply and saves everything.

It never sends anything. A person reads the draft, approves it, and sends it
themselves.

## 2. Install

You need Python 3.10 or newer. On Windows, use the Ubuntu (WSL) terminal.

Create a virtual environment (once):

```bash
python3 -m venv .venv
```

Activate it. Do this every time you open a new terminal:

```bash
source .venv/bin/activate
```

Your prompt now starts with `(.venv)`.

Install the project:

```bash
make install
```

Optional extras, only if you need them:

| Command | Needed for |
| --- | --- |
| `pip install -e ".[sheets]"` | The Google Sheets live demo (section 9) |
| `pip install -e ".[providers]"` | A model provider other than OpenAI (section 10) |
| `make dashboard-install` | The dashboard (section 8). Needs Node.js 20 or newer. |

## 3. Run the demo (no API key)

```bash
make demo
```

This runs the five sample leads through the agent using the built-in **mock
model**. It needs no key, uses no internet and costs nothing. You see each lead's
score, route and draft, then a summary. Results are saved under
`data/runtime/demo/`.

The mock model is simple keyword matching. It shows that the pipeline works. It
does not show how well a real model understands messages.

To see the same thing without saving anything:

```bash
make demo-dry
```

## 4. Set up `.env`

`.env` holds your settings and your API key. It is git-ignored and must never be
committed.

```bash
cp example.env .env
```

Open `.env` in an editor. `example.env` explains every variable. The ones that
matter first:

| Variable | What to put |
| --- | --- |
| `OPENAI_API_KEY` | Your OpenAI key, from https://platform.openai.com/api-keys |
| `LLM_MODEL` | A model name, or leave empty for the SDK default |
| `LEADGEN_MOCK_LLM` | `0` to use the real model, `1` to use the free mock |

The safety limits are also set here. Lower them while you experiment:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAX_LEADS_PER_RUN` | 25 | Most leads one run will process |
| `MAX_TOOL_CALLS_PER_LEAD` | 12 | Most tool calls the agent may make for one lead |
| `MAX_TOKENS_PER_RUN` | 200000 | The run stops once this many tokens are used |

Never type a key into a command, a chat or a commit. Edit `.env` instead.

## 5. Dry run and real run

| | Dry run (`--dry-run`) | Real run |
| --- | --- | --- |
| Runs the full agent | yes | yes |
| Calls the model (costs tokens with a real model) | yes | yes |
| Saves leads, drafts and the run log | **no** | yes, under `data/runtime/` |
| Writes to the Google Sheet | **never** | only if `SHEETS_ENABLED=1` |
| Sends anything to a customer | never | never |

Use a dry run to see what would happen. A dry run with a real model still costs
tokens, because the model is really called.

```bash
python -m leadgen --source sample --dry-run
```

```bash
python -m leadgen --source sample
```

To try one lead cheaply:

```bash
python -m leadgen --source sample --dry-run --limit 1
```

## 6. Run with your own input

### From a file

A CSV file needs a header row. Only `message` is required; `name`, `email`,
`phone`, `channel`, `id` and `received_at` are optional. See
`data/sample_leads.csv` for the format. A JSON file holds a list of objects with
the same fields.

```bash
python -m leadgen --source file --file my_leads.csv --dry-run
```

### From the local API (a "webhook")

Start the API in one terminal:

```bash
make serve
```

In a second terminal, queue an enquiry:

```bash
curl -X POST http://127.0.0.1:8000/leads -H "Content-Type: application/json" -d '{"name": "Test Lead", "email": "test@example.com", "message": "Need solar for my house in Lahore"}'
```

Then process everything that is queued:

```bash
python -m leadgen --source webhook
```

The API has no login. Keep it on `127.0.0.1` (the default) and do not expose it
to the internet.

### From a Google Sheet

See section 9.

### Flags

| Flag | Meaning |
| --- | --- |
| `--source sample` | Read `data/sample_leads.csv` (the default) |
| `--source file --file PATH` | Read your own CSV or JSON file |
| `--source webhook` | Process leads queued through the local API |
| `--source sheet` | Process new rows in the Google Sheet's Inbox tab |
| `--dry-run` | Run the agent but save nothing |
| `--limit N` | Process at most N leads |
| `--watch --interval 10` | With `--source sheet`: keep checking until Ctrl+C |
| `--delay 3` | Pause between leads, for live demos |
| `--verbose` | Show one log line per lead |

## 7. Read the output

For each lead the terminal shows something like:

```
[S003] Demo Lead Three via webhook
  intent: quote_request   score: 10/10 (HOT)   route: draft_reply   status: pending_approval
  missing: timeline
  tools used: score_lead > get_company_profile > search_faq > get_calendar_link > draft_reply > save_lead
  DRAFT (not sent - waiting for human approval):
    | Hi Demo, ...
```

| Word | Meaning |
| --- | --- |
| **score** | 1 to 10, from the rule book. 7 or more is **HOT**. |
| **route: draft_reply** | A genuine enquiry. A draft is waiting for approval. |
| **route: handover** | A person must handle it (complaint, legal threat, safety issue, duplicate, suspicious message, or the agent could not produce a safe draft). The reason is shown. |
| **route: nurture** | Genuine but not ready yet ("maybe next year"). A short note is drafted. |
| **route: spam** | Advertising or unrelated. No draft. |
| **missing** | Facts the customer has not given yet. The draft asks for at most three of them. |
| **rejected draft #1** | A draft the safety checks refused, with the check that failed. The agent then tries again. |
| **flags** | Things a reviewer should know, such as `duplicate` or `injection_suspected`. |

After the leads comes a run summary: leads processed, drafts, handovers, tokens
and a cost estimate. The estimate uses the prices in `config/client.yaml`, which
are placeholders until you set your model's real prices.

Saved files, under `data/runtime/` (or `data/runtime/demo/` for `make demo`):

| File | Contents |
| --- | --- |
| `leads.json` | Every processed lead with its draft |
| `leads.csv` | The same as a spreadsheet |
| `runs.json` | Run history |
| `inbox.json` | Leads queued through the API |

## 8. The dashboard

A web page for reviewing leads: a table with score, route and status, the draft
for each lead, run history, today's counts and the average score.

Install once (needs Node.js 20 or newer):

```bash
make dashboard-install
```

**Demo mode** shows bundled dummy data and needs nothing else:

```bash
make dashboard-demo
```

Open http://localhost:5173. The page is labelled "Demo data" and its buttons
only change the page.

**Local mode** shows your own runs. Use two terminals:

```bash
make serve
```

```bash
make dashboard-dev
```

Open http://localhost:5173. The badge reads "Local mode". Click a lead to see its
draft. The three buttons record your decision:

| Button | New status |
| --- | --- |
| Approve draft | `approved` |
| Reject draft | `rejected` |
| Hand over to a human | `needs_human` |

Approving does **not** send the reply. It only marks the draft as approved. You
copy the text and send it yourself.

Stop either command with Ctrl+C. More detail: [dashboard/README.md](dashboard/README.md).

## 9. Google Sheets live demo

Optional. A Google Sheet fills up row by row while the agent works, which is
useful for a screen recording. Setup takes about 15 minutes and is explained in
[docs/GOOGLE_SHEETS.md](docs/GOOGLE_SHEETS.md).

In short:

1. Put the service account key at `secrets/service-account.json` (git-ignored).
2. Share the sheet with the service account's email as Editor.
3. In `.env` set `SHEETS_ENABLED=1` and `GOOGLE_SHEET_ID`.
4. Install the extra: `pip install -e ".[sheets]"`.

Then:

```bash
make demo-sheet
```

To process enquiries typed into the sheet's Inbox tab, and keep watching:

```bash
python -m leadgen --source sheet --watch --interval 10
```

A dry run never writes to the sheet. The mock model never contacts Google unless
you opt in; `make demo-sheet` does that for you.

## 10. Use another model provider

OpenAI is the default. To use Anthropic, Google Gemini, Mistral, DeepSeek, Groq,
OpenRouter, a local Ollama model or any OpenAI-compatible server, you change only
`.env`:

```
LLM_PROVIDER=<provider>
LLM_MODEL=<model name>
<THAT_PROVIDER'S_KEY>=<your key>
```

Full instructions, limits and troubleshooting are in
[MODEL_SWITCH.md](MODEL_SWITCH.md). Only OpenAI has been run with a real key in
this project, so test a new provider with one lead first.

## 11. Change the rules without code

Settings resolve in three layers. A later layer wins:

1. built-in defaults (safety rules that always apply),
2. the niche preset, `presets/solar.yaml`,
3. your client file, `config/client.yaml`.

| To change | Edit |
| --- | --- |
| Company name, contact details, sign-off | `config/client.yaml` |
| Booking link | `calendar_link` in `config/client.yaml` |
| Scoring points and the hot threshold | `scoring` in `presets/solar.yaml` |
| Questions the agent may ask | `qualification_questions` in `presets/solar.yaml` |
| Service area | `service_area` in `presets/solar.yaml` |
| When a lead is "nurture" | `nurture` in `presets/solar.yaml` |
| Token prices for the cost estimate | `pricing` in `config/client.yaml` |
| FAQ answers | `data/faq.md` |

For a different business type, copy `presets/solar.yaml` to a new file, edit it,
and set `LEADGEN_PRESET` in `.env` to its name.

After changing a rule, run `make test` and `make evals`.

## 12. Tests and evals

Free, no key needed:

```bash
make lint
```

```bash
make test
```

```bash
make evals
```

`make evals` runs 28 example enquiries through the agent on the mock model and
checks the route and score of each.

Optional, on your real model. These **cost tokens**:

```bash
make evals-live-case CASE=21_sample_s001_hot_home
```

```bash
make evals-live
```

One case costs roughly 10,000 to 20,000 tokens; the full set used about 350,000
tokens in one earlier run. They stop at a cap on leads and tokens, never run in
CI, and write a report to `data/runtime/live-eval-report.json`. See
[evals/README.md](evals/README.md).

## 13. Working on a new task or change

`main` is never committed to directly. Every change goes through a branch and a
pull request (PR).

1. Start from the latest `main`:

```bash
git checkout main && git pull
```

2. Create a branch. Use `feat/...` for a feature, `fix/...` for a fix,
   `docs/...` for documentation:

```bash
git checkout -b fix/short-description
```

3. Make the change. Commit small steps with clear messages:

```bash
git add -A && git commit -m "fix: describe the change in one line"
```

4. Check everything before sharing it:

```bash
make lint && make test && make evals
```

   If you touched the dashboard, also run `make dashboard-test`.

5. Push the branch and open a PR to `main` on GitHub:

```bash
git push -u origin fix/short-description
```

6. Review the PR: read the changed files, check that the automated checks are
   green, and try the change yourself. Only then click **Merge pull request**.

7. Update your local copy:

```bash
git checkout main && git pull
```

Before every commit, make sure no secret is included:

```bash
git status
```

`.env`, anything in `secrets/` and anything in `data/runtime/` must not appear
in the list.

## 14. Troubleshooting

| Problem | What to do |
| --- | --- |
| `make: command not found` or `python: command not found` | Activate the environment: `source .venv/bin/activate`. On a system with only `python3`, run `make test PYTHON=python3`. |
| `No module named leadgen` | Activate the environment and run `make install`. |
| `Error: Missing API key: ... needs OPENAI_API_KEY` | Set the key in `.env`, or set `LEADGEN_MOCK_LLM=1` to use the mock. |
| It uses the mock although I set a key | Set `LEADGEN_MOCK_LLM=0` in `.env`. Note that `make demo`, `make demo-dry` and `make evals` always use the mock. |
| `Unknown LLM_PROVIDER` or `LLM_MODEL is required` | See [MODEL_SWITCH.md](MODEL_SWITCH.md). |
| `--file is required when --source file is used` | Add `--file path/to/leads.csv`. |
| `Lead file not found` or `Could not read leads` | Check the path, and that the file has a `message` column. |
| `No new leads from source 'webhook'` | Nothing is queued. Post a lead to the API first (section 6). |
| Every lead ends in handover | Read the `handover reason` line. "Agent run failed" followed by an error usually means a wrong model name or an invalid key. |
| A run stops early with "Token limit reached" or "Lead limit reached" | Raise `MAX_TOKENS_PER_RUN` or `MAX_LEADS_PER_RUN` in `.env`, or run again to continue. |
| The cost estimate looks wrong | It uses the placeholder prices in `config/client.yaml`. Set your model's real prices. |
| Dashboard: "Cannot reach the local API" | Start `make serve` in another terminal, and open the dashboard at exactly http://localhost:5173. |
| Dashboard shows "Demo data" but I want my own | Use `make dashboard-dev`, not `make dashboard-demo`. |
| Dashboard: `npm: command not found` | Install Node.js 20 or newer. |
| `Address already in use` | Another copy is running. Stop it with Ctrl+C, or set `API_PORT` in `.env`. |
| Google Sheets errors | See the troubleshooting table in [docs/GOOGLE_SHEETS.md](docs/GOOGLE_SHEETS.md). |
| A test fails after I edited a preset | The evals show which lead changed route or score. Adjust the rule or the expected value in `evals/cases/`. |
| I committed a key by mistake | Treat the key as leaked. Delete it at the provider and create a new one. Removing the commit is not enough. |

## 15. Safety notes

- **Drafts only.** The agent has no way to send anything. A person approves and
  sends every reply.
- **No promises.** Drafts containing a price, a saving, a date or a net-metering
  approval promise are blocked by code before they are saved. The same goes for
  electrical, legal and tax advice.
- **Complaints go to a person.** Complaints, anger, legal threats and safety
  incidents are detected in code and always handed over.
- **Customer text is data.** A message that tries to give the agent instructions
  is flagged and sent to a person.
- **Limits.** Leads per run, tool calls per lead and tokens per run are capped.
- **Read every draft.** The checks are filters, not a guarantee. A person is the
  final check.
- **Keys.** Keys live in `.env` and `secrets/` only. Never commit them, paste
  them in a chat or put them in a `VITE_*` variable.
- **The local API has no login.** Keep it on `127.0.0.1`.
- **Dummy data only.** The saved files, the dashboard and any shared Google
  Sheet show every lead in full.
- **Other providers.** Using a non-OpenAI provider sends lead text to that
  provider. Tracing to OpenAI is switched off in that case.

## 16. Command reference

| Command | What it does | Costs tokens |
| --- | --- | --- |
| `make install` | Install the project and dev tools | no |
| `make lint` | Check code style | no |
| `make test` | Run the test suite on the mock | no |
| `make evals` | Run the 28 eval cases on the mock | no |
| `make demo` | Sample leads end to end on the mock, saved to `data/runtime/demo/` | no |
| `make demo-dry` | The same, saving nothing | no |
| `make serve` | Start the local API on 127.0.0.1:8000 | no |
| `python -m leadgen ...` | Run the agent (see the flags in section 6) | yes, unless the mock is on |
| `make evals-live` | Eval cases on the real model | **yes** |
| `make evals-live-case CASE=<id>` | One eval case on the real model | **yes** |
| `make demo-sheet` | Sample leads into your Google Sheet, one by one | only with a key and the mock off |
| `make dashboard-install` | Install the dashboard's packages | no |
| `make dashboard-demo` | Dashboard with bundled demo data | no |
| `make dashboard-dev` | Dashboard connected to the local API | no |
| `make dashboard-test` | Dashboard type check and unit tests | no |
| `make dashboard-build` | Build the demo site into `dashboard/dist/` | no |
| `make dashboard-demo-data` | Regenerate the dashboard's demo data from the mock | no |
