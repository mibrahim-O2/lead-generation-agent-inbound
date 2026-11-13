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

To try a few cases first:

```bash
python -m leadgen.evals --live --filter sample_s00 --max-leads 5
```
