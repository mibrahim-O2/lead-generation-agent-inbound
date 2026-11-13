# Evals

`evals/cases/` holds 20 cases, one YAML file each: a clear hot lead, a vague
lead, price-only questions, factory and farm leads, a complaint, a legal
threat, spam, prompt injection, a duplicate, Roman-Urdu messages, missing
contact details and more.

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

Optional keys under `expected`: `flags`, `missing_info`, `language`. A case can
also list `seed_leads`, which are processed first (used for the duplicate case).

Every case is also checked for the rules that must always hold: handover and
spam leads have no draft, and no draft contains a forbidden claim.

## Running

```bash
make evals
```

This uses the mock model, so it needs no API key. With the mock, the evals
check the pipeline, the tools and the code-level guardrails. The mock is
keyword matching, so a pass does not tell you how a real model will judge
these messages. To test a real model, set your key in `.env` and run:

```bash
python -m leadgen.evals
```

That makes real API calls and costs tokens.
