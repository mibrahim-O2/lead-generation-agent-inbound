"""Eval runner: runs each case in evals/cases/ through the agent and checks the result.

    python -m leadgen.evals                      # uses the model from the environment
    LEADGEN_MOCK_LLM=1 python -m leadgen.evals   # offline, no key (what `make evals` does)

With the mock model the evals check the pipeline, tools and guardrails. Run them
against a real model to check that model's judgement.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from leadgen.config import RuleBook, Settings, load_rulebook, project_root
from leadgen.guardrails import check_draft
from leadgen.llm import LLMSetup, resolve_llm
from leadgen.models import Lead, LeadRecord
from leadgen.runner import process_lead
from leadgen.storage import MemoryStorage


@dataclass
class EvalCase:
    id: str
    description: str
    lead: Lead
    expected: dict[str, Any]
    seed_leads: list[Lead] = field(default_factory=list)


@dataclass
class EvalResult:
    case: EvalCase
    record: LeadRecord
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def cases_dir() -> Path:
    return project_root() / "evals" / "cases"


def load_cases(directory: Path | None = None) -> list[EvalCase]:
    cases = []
    for path in sorted((directory or cases_dir()).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases.append(
            EvalCase(
                id=data["id"],
                description=data.get("description", ""),
                lead=Lead.model_validate({"id": data["id"], **data["lead"]}),
                expected=data["expected"],
                seed_leads=[
                    Lead.model_validate({"id": f"{data['id']}-seed{i}", **seed})
                    for i, seed in enumerate(data.get("seed_leads", []), start=1)
                ],
            )
        )
    return cases


def check_record(case: EvalCase, record: LeadRecord, rulebook: RuleBook) -> list[str]:
    """Compare a record with the case's expectations. Returns human-readable failures."""
    expected, failures = case.expected, []
    if record.route != expected["route"]:
        failures.append(f"route {record.route}, expected {expected['route']}")
    low, high = expected["score_min"], expected["score_max"]
    if not low <= record.score <= high:
        failures.append(f"score {record.score}, expected {low}-{high}")
    for flag in expected.get("flags", []):
        if flag not in record.flags:
            failures.append(f"missing flag {flag}")
    for item in expected.get("missing_info", []):
        if item not in record.missing_info:
            failures.append(f"missing_info lacks {item}")
    if "language" in expected and record.draft_language != expected["language"]:
        failures.append(f"language {record.draft_language}, expected {expected['language']}")
    # Rules that hold for every case, whatever the model did.
    if record.route in ("handover", "spam") and record.draft_reply:
        failures.append(f"a {record.route} lead must not have a draft")
    if record.route == "draft_reply" and not record.draft_reply:
        failures.append("draft_reply route without a draft")
    if broken := check_draft(record.draft_reply, rulebook):
        failures.append(f"draft contains forbidden claims: {broken}")
    if record.error:
        failures.append(f"run error: {record.error}")
    return failures


async def run_case(
    case: EvalCase, settings: Settings, rulebook: RuleBook, llm: LLMSetup
) -> EvalResult:
    storage = MemoryStorage()  # every case starts clean and never touches disk
    for seed in case.seed_leads:
        await process_lead(
            seed.with_defaults(), rulebook=rulebook, storage=storage, llm=llm, settings=settings
        )
    record, _, _ = await process_lead(
        case.lead.with_defaults(), rulebook=rulebook, storage=storage, llm=llm, settings=settings
    )
    return EvalResult(case=case, record=record, failures=check_record(case, record, rulebook))


async def run_all(settings: Settings) -> list[EvalResult]:
    rulebook = load_rulebook(settings.preset, settings.client_config)
    llm = resolve_llm(settings)
    return [await run_case(case, settings, rulebook, llm) for case in load_cases()]


def main() -> int:
    load_dotenv()
    results = asyncio.run(run_all(Settings.from_env()))
    for result in results:
        record = result.record
        mark = "PASS" if result.passed else "FAIL"
        print(f"{mark}  {result.case.id:<28} route={record.route:<12} score={record.score:<3}")
        for failure in result.failures:
            print(f"      - {failure}")
    passed = sum(result.passed for result in results)
    print(f"\n{passed}/{len(results)} cases passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
