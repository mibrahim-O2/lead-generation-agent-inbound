"""Run orchestration: load leads, run the agent per lead under the safety limits.

A dry run executes the full agent but against an in-memory copy of the storage,
so nothing is written to disk. Nothing is ever sent in either mode.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from agents import Runner
from agents.exceptions import AgentsException

from leadgen.agent import build_agent
from leadgen.config import RuleBook, Settings, project_root
from leadgen.context import LeadContext
from leadgen.guardrails import finalize, screen_message, wrap_lead_data
from leadgen.llm import LLMSetup, resolve_llm
from leadgen.models import Lead, LeadDecision, LeadRecord, RunRecord
from leadgen.runlog import RunLog
from leadgen.storage import MemoryStorage, Storage


class SourceError(Exception):
    """The lead source could not be read."""


@dataclass
class RunOutcome:
    run: RunRecord
    records: list[LeadRecord]


def load_leads(source: str, storage: Storage, file: str | None = None) -> list[Lead]:
    """Read new enquiries from the sample file, a CSV/JSON file, or the webhook inbox."""
    if source == "webhook":
        return storage.pending_leads()
    if source == "sample":
        path = project_root() / "data" / "sample_leads.csv"
    elif source == "file":
        if not file:
            raise SourceError("--source file needs --file <path>")
        path = Path(file)
    else:
        raise SourceError(f"Unknown source '{source}'")
    if not path.is_file():
        raise SourceError(f"Lead file not found: {path}")
    try:
        if path.suffix.lower() == ".json":
            rows = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(rows, dict):
                rows = rows.get("leads", [rows])
        else:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        return [Lead.model_validate(row).with_defaults() for row in rows]
    except (ValueError, TypeError) as exc:
        raise SourceError(f"Could not read leads from {path}: {exc}") from exc


async def process_lead(
    lead: Lead,
    *,
    rulebook: RuleBook,
    storage: Storage,
    llm: LLMSetup,
    settings: Settings,
    run_id: str = "",
) -> tuple[LeadRecord, int, int]:
    """Run the agent on one lead. Returns (record, input tokens, output tokens)."""
    ctx = LeadContext(
        lead=lead,
        rulebook=rulebook,
        storage=storage,
        max_tool_calls=settings.max_tool_calls_per_lead,
        run_id=run_id,
        screening=screen_message(lead.message, rulebook),
    )
    decision: LeadDecision | None = None
    error = ""
    tokens_in = tokens_out = 0
    try:
        result = await Runner.run(
            build_agent(rulebook, llm.model),
            wrap_lead_data(lead),
            context=ctx,
            # One model turn per tool call, plus room for the final answer.
            max_turns=settings.max_tool_calls_per_lead + 2,
        )
        decision = result.final_output_as(LeadDecision)
        usage = result.context_wrapper.usage
        tokens_in, tokens_out = usage.input_tokens, usage.output_tokens
    except AgentsException as exc:
        error = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 - one bad lead must not stop the run
        error = f"{type(exc).__name__}: {exc}"

    # Always re-apply the guardrails on the final state and store the result,
    # whether or not the agent called save_lead.
    record = finalize(ctx, decision, error=error)
    storage.save_record(record)
    return record, tokens_in, tokens_out


async def run_leads(
    leads: list[Lead],
    *,
    settings: Settings,
    rulebook: RuleBook,
    storage: Storage,
    source: str = "sample",
    dry_run: bool = False,
    limit: int | None = None,
    llm: LLMSetup | None = None,
) -> RunOutcome:
    """Process a batch of leads under the run limits and log the run."""
    llm = llm or resolve_llm(settings)
    # Dry run: work on an in-memory copy, so the real storage is never written.
    work_storage: Storage = MemoryStorage(seed=storage) if dry_run else storage
    log = RunLog(source=source, dry_run=dry_run, provider=llm.provider, model=llm.model_name)
    log.run.leads_received = len(leads)

    cap = min(limit or settings.max_leads_per_run, settings.max_leads_per_run)
    stopped = ""
    if len(leads) > cap:
        stopped = f"Lead limit reached ({cap}); {len(leads) - cap} lead(s) left for the next run"

    records: list[LeadRecord] = []
    for lead in leads[:cap]:
        if log.run.total_tokens >= settings.max_tokens_per_run:
            stopped = f"Token limit reached ({settings.max_tokens_per_run})"
            break
        record, tokens_in, tokens_out = await process_lead(
            lead.with_defaults(),
            rulebook=rulebook,
            storage=work_storage,
            llm=llm,
            settings=settings,
            run_id=log.run.id,
        )
        log.add_usage(tokens_in, tokens_out)
        log.add_lead(record)
        records.append(record)

    run = log.finish(rulebook.pricing, stopped_reason=stopped)
    if not dry_run:
        storage.save_run(run)
    return RunOutcome(run=run, records=records)
