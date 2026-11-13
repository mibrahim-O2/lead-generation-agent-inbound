"""Run logging: what happened in one run, with a token and cost estimate."""

from __future__ import annotations

import logging
import uuid

from leadgen.config import Pricing
from leadgen.models import LeadRecord, RunRecord, now_iso

logger = logging.getLogger("leadgen")


class RunLog:
    """Collects the numbers for one run and turns them into a RunRecord."""

    def __init__(self, source: str, dry_run: bool, provider: str, model: str) -> None:
        self.run = RunRecord(
            id="run-" + uuid.uuid4().hex[:10],
            started_at=now_iso(),
            source=source,
            dry_run=dry_run,
            provider=provider,
            model=model,
        )

    def add_lead(self, record: LeadRecord) -> None:
        run = self.run
        run.leads_processed += 1
        run.drafts_created += 1 if record.draft_reply else 0
        run.handovers += 1 if record.route == "handover" else 0
        run.nurture += 1 if record.route == "nurture" else 0
        run.spam += 1 if record.route == "spam" else 0
        run.hot_leads += 1 if record.is_hot else 0
        if record.error:
            self.add_error(f"{record.lead.id}: {record.error}")
        logger.info(
            "lead=%s route=%s score=%s flags=%s",
            record.lead.id, record.route, record.score, ",".join(record.flags) or "-",
        )  # fmt: skip

    def add_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.run.input_tokens += input_tokens
        self.run.output_tokens += output_tokens
        self.run.total_tokens += input_tokens + output_tokens

    def add_error(self, message: str) -> None:
        self.run.errors.append(message)
        logger.error(message)

    def finish(self, pricing: Pricing, stopped_reason: str = "") -> RunRecord:
        run = self.run
        run.finished_at = now_iso()
        run.stopped_reason = stopped_reason
        if pricing.input_per_1m_usd or pricing.output_per_1m_usd:
            cost = (
                run.input_tokens * pricing.input_per_1m_usd
                + run.output_tokens * pricing.output_per_1m_usd
            ) / 1_000_000
            run.cost_estimate_usd = round(cost, 6)
        logger.info("run=%s finished: %s", run.id, format_summary(run).replace("\n", " | "))
        return run


def format_summary(run: RunRecord) -> str:
    cost = "not set" if run.cost_estimate_usd is None else f"${run.cost_estimate_usd:.4f}"
    lines = [
        f"Run {run.id} ({'DRY RUN' if run.dry_run else 'real run'}, source={run.source}, "
        f"model={run.provider}/{run.model})",
        f"Leads processed: {run.leads_processed} of {run.leads_received} (hot: {run.hot_leads})",
        f"Drafts created: {run.drafts_created}   Handovers: {run.handovers}   "
        f"Nurture: {run.nurture}   Spam: {run.spam}",
        f"Tokens: {run.total_tokens} (in {run.input_tokens}, out {run.output_tokens})   "
        f"Cost estimate: {cost}",
        f"Errors: {len(run.errors)}",
    ]
    if run.stopped_reason:
        lines.append(f"Stopped early: {run.stopped_reason}")
    return "\n".join(lines)
