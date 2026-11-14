"""Eval runner: runs each case in evals/cases/ through the agent and checks the result.

    python -m leadgen.evals          # mock model: offline, no key (`make evals`)
    python -m leadgen.evals --live   # real model from .env, capped (`make evals-live`)
    python -m leadgen.evals --live --case 01_hot_home   # one case (`make evals-live-case`)

With the mock model the evals check the pipeline, tools and guardrails. The live
mode checks a real model's judgement; it makes real API calls and costs tokens,
so it has hard caps on leads and tokens and refuses to run in CI. A live run
also writes a per-case JSON report (see REPORT_NAME) to the data directory.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from leadgen.config import ConfigError, RuleBook, Settings, load_rulebook, project_root
from leadgen.guardrails import asks_for_contact, check_draft, count_questions, max_questions
from leadgen.llm import LLMConfigError, LLMSetup, resolve_llm
from leadgen.models import Lead, LeadRecord, now_iso
from leadgen.runner import process_lead
from leadgen.storage import MemoryStorage

# Live-mode caps. The defaults cover the full set; the hard limits cannot be exceeded.
LIVE_DEFAULT_MAX_LEADS = 30
LIVE_DEFAULT_MAX_TOKENS = 400_000
LIVE_HARD_MAX_LEADS = 40
LIVE_HARD_MAX_TOKENS = 600_000
REPORT_NAME = "live-eval-report.json"  # written under LEADGEN_DATA_DIR (git-ignored)


@dataclass
class EvalCase:
    id: str
    description: str
    lead: Lead
    expected: dict[str, Any]
    seed_leads: list[Lead] = field(default_factory=list)

    @property
    def lead_count(self) -> int:
        return 1 + len(self.seed_leads)


@dataclass
class EvalResult:
    case: EvalCase
    record: LeadRecord
    failures: list[str]
    tokens: int = 0

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass
class EvalReport:
    results: list[EvalResult]
    skipped: list[str] = field(default_factory=list)  # case ids not run because of a cap
    stopped_reason: str = ""

    @property
    def passed(self) -> int:
        return sum(result.passed for result in self.results)

    @property
    def tokens(self) -> int:
        return sum(result.tokens for result in self.results)

    @property
    def ok(self) -> bool:
        return self.passed == len(self.results) and not self.skipped


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
    draft = record.draft_reply
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
    for item in expected.get("not_missing", []):
        if item in record.missing_info:
            failures.append(f"{item} reported as missing although the lead states it")
    if "language" in expected and record.draft_language != expected["language"]:
        failures.append(f"language {record.draft_language}, expected {expected['language']}")
    if "max_questions" in expected and count_questions(draft) > expected["max_questions"]:
        failures.append(
            f"{count_questions(draft)} questions, expected at most {expected['max_questions']}"
        )

    # Rules that hold for every case, whatever the model did.
    if record.route in ("handover", "spam") and draft:
        failures.append(f"a {record.route} lead must not have a draft")
    if record.route == "draft_reply" and not draft:
        failures.append("draft_reply route without a draft")
    if broken := check_draft(draft, rulebook):
        failures.append(f"draft contains forbidden claims: {broken}")
    kind = "nurture" if record.route == "nurture" else "reply"
    if count_questions(draft) > max_questions(kind, rulebook):
        failures.append(f"too many questions for a {kind} draft: {count_questions(draft)}")
    has_contact = bool(case.lead.email.strip() or case.lead.phone.strip())
    if has_contact and asks_for_contact(draft, rulebook):
        failures.append("draft asks for contact details that are already on file")
    if has_contact and "contact" in record.missing_info:
        failures.append("contact reported as missing although it is on file")
    if record.error:
        failures.append(f"run error: {record.error}")
    return failures


async def run_case(
    case: EvalCase, settings: Settings, rulebook: RuleBook, llm: LLMSetup
) -> EvalResult:
    storage = MemoryStorage()  # every case starts clean and never touches disk
    tokens = 0
    for seed in case.seed_leads:
        _, used_in, used_out = await process_lead(
            seed.with_defaults(), rulebook=rulebook, storage=storage, llm=llm, settings=settings
        )
        tokens += used_in + used_out
    record, used_in, used_out = await process_lead(
        case.lead.with_defaults(), rulebook=rulebook, storage=storage, llm=llm, settings=settings
    )
    return EvalResult(
        case=case,
        record=record,
        failures=check_record(case, record, rulebook),
        tokens=tokens + used_in + used_out,
    )


async def run_all(
    settings: Settings,
    *,
    max_leads: int | None = None,
    max_tokens: int | None = None,
    name_filter: str = "",
    case_id: str = "",
) -> EvalReport:
    """Run the cases in order, stopping before a cap would be exceeded.

    `name_filter` keeps cases whose id contains the text; `case_id` keeps the one
    case with exactly that id.
    """
    rulebook = load_rulebook(settings.preset, settings.client_config)
    llm = resolve_llm(settings)
    cases = [case for case in load_cases() if name_filter in case.id]
    if case_id:
        cases = [case for case in cases if case.id == case_id]
        if not cases:
            known = ", ".join(case.id for case in load_cases())
            raise ConfigError(f"No eval case with id '{case_id}'. Known ids: {known}")
    report = EvalReport(results=[])
    leads_used = 0
    for index, case in enumerate(cases):
        if max_leads is not None and leads_used + case.lead_count > max_leads:
            report.stopped_reason = f"lead cap reached ({max_leads})"
        elif max_tokens is not None and report.tokens >= max_tokens:
            report.stopped_reason = f"token cap reached ({max_tokens})"
        if report.stopped_reason:
            report.skipped = [c.id for c in cases[index:]]
            break
        report.results.append(await run_case(case, settings, rulebook, llm))
        leads_used += case.lead_count
    return report


def explain(record: LeadRecord) -> list[str]:
    """Why a lead ended where it did: handover reason and every rejected draft."""
    lines = []
    if record.route == "handover":
        lines.append(f"handover reason: {record.handover_reason or 'not recorded'}")
    for rejected in record.rejected_drafts:
        lines.append(f"rejected draft #{rejected.attempt}:")
        for problem in rejected.problems:
            found = f" (found: {problem.found})" if problem.found else ""
            lines.append(f"  - {problem.check}{found} -> {problem.fix}")
    if record.error:
        lines.append(f"error: {record.error}")
    return lines


def format_report(report: EvalReport, label: str) -> str:
    """A summary table, one row per case, with the reason under every handover."""
    header = f"{'':4}  {'case':<28} {'route':<12} {'score':<10} {'lang':<10} {'Qs':<3} tokens"
    lines = [f"Evals on {label}", header, "-" * len(header)]
    for result in report.results:
        record, expected = result.record, result.case.expected
        score = f"{record.score} ({expected['score_min']}-{expected['score_max']})"
        lines.append(
            f"{'PASS' if result.passed else 'FAIL':4}  {result.case.id:<28} {record.route:<12} "
            f"{score:<10} {record.draft_language if record.draft_reply else '-':<10} "
            f"{count_questions(record.draft_reply):<3} {result.tokens}"
        )
        lines.extend(f"        - {failure}" for failure in result.failures)
        lines.extend(f"        > {line}" for line in explain(record))
    lines.append("-" * len(header))
    lines.append(
        f"{report.passed}/{len(report.results)} cases passed   total tokens: {report.tokens}"
    )
    if report.skipped:
        lines.append(
            f"Stopped early: {report.stopped_reason}. "
            f"Not run ({len(report.skipped)}): {', '.join(report.skipped)}"
        )
    return "\n".join(lines)


def report_data(report: EvalReport, label: str) -> dict[str, Any]:
    """The per-case report as plain data, for the JSON file."""
    return {
        "generated_at": now_iso(),
        "model": label,
        "passed": report.passed,
        "total": len(report.results),
        "tokens": report.tokens,
        "stopped_reason": report.stopped_reason,
        "skipped": report.skipped,
        "cases": [
            {
                "case_id": result.case.id,
                "passed": result.passed,
                "failures": result.failures,
                "expected": result.case.expected,
                "route": result.record.route,
                "score": result.record.score,
                "intent": result.record.intent,
                "handover_reason": result.record.handover_reason,
                "rejected_drafts": [r.model_dump() for r in result.record.rejected_drafts],
                "final_draft": result.record.draft_reply,
                "draft_language": result.record.draft_language,
                "tools_used": result.record.tool_calls,
                "flags": result.record.flags,
                "guardrail_notes": result.record.guardrail_notes,
                "error": result.record.error,
                "tokens": result.tokens,
            }
            for result in report.results
        ],
    }


def write_report(report: EvalReport, label: str, data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / REPORT_NAME
    path.write_text(
        json.dumps(report_data(report, label), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m leadgen.evals", description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Use the real model from .env. Costs tokens."
    )
    parser.add_argument(
        "--max-leads",
        type=int,
        default=LIVE_DEFAULT_MAX_LEADS,
        help=f"Live mode: stop after this many leads (hard limit {LIVE_HARD_MAX_LEADS}).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=LIVE_DEFAULT_MAX_TOKENS,
        help=f"Live mode: stop once this many tokens are used (hard limit {LIVE_HARD_MAX_TOKENS}).",
    )
    parser.add_argument("--filter", default="", help="Only run cases whose id contains this.")
    parser.add_argument("--case", default="", help="Run only the case with exactly this id.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()
    try:
        settings = Settings.from_env()
        if args.live:
            if os.environ.get("CI"):
                print("Error: live evals never run in CI.", file=sys.stderr)
                return 2
            settings = replace(settings, mock_llm=False)
            caps = {
                "max_leads": max(1, min(args.max_leads, LIVE_HARD_MAX_LEADS)),
                "max_tokens": max(1, min(args.max_tokens, LIVE_HARD_MAX_TOKENS)),
            }
            label = f"REAL model {settings.llm_provider}/{settings.llm_model or 'sdk-default'}"
            print(
                f"Live evals: real API calls. Caps: {caps['max_leads']} leads, "
                f"{caps['max_tokens']} tokens."
            )
        else:
            # Without --live this is always the mock, even if .env holds a real key.
            settings = replace(settings, mock_llm=True)
            caps, label = {}, "mock model (pipeline and guardrails only)"
        report = asyncio.run(run_all(settings, name_filter=args.filter, case_id=args.case, **caps))
    except (ConfigError, LLMConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(format_report(report, label))
    if args.live:
        path = write_report(report, label, settings.resolved_data_dir())
        print(f"Per-case report written to {path}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
