# Evals

`evals/cases/` holds 28 cases, one YAML file each: a clear hot lead, a vague
lead, price-only questions, factory and farm leads, a complaint, a legal
threat, spam, prompt injection, a duplicate, Roman-Urdu messages, missing
contact details and more. Cases 21 to 25 are the five sample leads from
`data/sample_leads.csv`.

Each case gives the lead, the expected route and an acceptable score range:

```yaml
id: 05_farm
description: Farm lead in a nearby town
lead:
  name: Eval Lead 05
  email: eval05@example.com
  message: I have a dairy farm near Kasur ...
expected:
  route: draft_reply
  score_min: 6
  score_max: 8
```

Optional keys under `expected`:

| Key | Meaning |
| --- | --- |
| `flags` | Flags the record must carry, e.g. `duplicate`, `injection_suspected`. |
| `missing_info` | Fields that must be reported as missing. |
| `not_missing` | Fields that must NOT be reported as missing (the lead states them). |
| `language` | Language of the draft: `english` or `roman_urdu`. |
| `max_questions` | Most question marks allowed in the draft. |

A case can also list `seed_leads`, which are processed first (used for the
duplicate case).

Every case is also checked for the rules that must always hold: handover and
spam leads have no draft, no draft contains a forbidden claim, no draft asks
more questions than the rule book allows (3, or 1 for nurture), and no draft
asks for contact details that are already on file.

## Running on the mock model

```bash
make evals
```

This always uses the mock model, even if `.env` holds a real key, so it needs no
API key and costs nothing. With the mock, the evals check the pipeline, the
tools and the code-level guardrails. The mock is keyword matching, so a pass
does not tell you how a real model will judge these messages.

## Running on the real model (optional)

```bash
make evals-live
```

This runs the same cases against the model configured in `.env`
(`OPENAI_API_KEY`, `LLM_MODEL`) and prints a summary table with route, score,
language, question count and tokens per case.

- It makes real API calls and costs tokens.
- Hard caps: by default it stops after 30 leads or 400,000 tokens, whichever
  comes first, and lists the cases it did not run. You can lower the caps or
  raise them up to the hard limits of 40 leads and 600,000 tokens.
- It refuses to run when the `CI` environment variable is set, and it is not
  part of `make test` or the CI workflow.

### Retrying one case

```bash
make evals-live-case CASE=01_hot_home
```

Runs a single case on the real model, which is the cheap way to retry a
failure (roughly 10,000 to 20,000 tokens for one case). The case id is the
file name without `.yaml`. To run a group instead, use a filter:

```bash
python -m leadgen.evals --live --filter sample_s00 --max-leads 5
```

### Reading the output

Under each row the table shows why a lead ended where it did:

```
FAIL  01_hot_home                  handover     9 (8-10)   -          0   15234
        - route handover, expected draft_reply
        > handover reason: No approved draft: 2 rejected (attempt 1: price (Rs 900,000) | attempt 2: contact (...))
        > rejected draft #1:
        >   - price (found: Rs 900,000) -> Remove every price and rupee amount. ...
```

- `handover reason` is shown for every lead that ends in handover.
- `rejected draft #N` lists each draft the checks refused, with the check that
  failed (`price`, `savings`, `delivery_date`, `guarantee`, `advice`, `sent`,
  `net_metering_approval`, `language`, `questions`, `length`, `contact`), the
  text that triggered it, and the fix the model was told to make.

### The JSON report

Every live run also writes `data/runtime/live-eval-report.json` (git-ignored;
it follows `LEADGEN_DATA_DIR`). Each run overwrites the previous report. Per
case it holds: case id, pass or fail with the failures, route, score, handover
reason, rejected drafts with their problems and full text, the final draft,
tools used, flags, guardrail notes and tokens. The mock run (`make evals`)
does not write a report.
