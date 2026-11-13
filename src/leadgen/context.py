"""Per-lead working state shared by the tools and the guardrails."""

from __future__ import annotations

from dataclasses import dataclass, field

from leadgen.config import RuleBook
from leadgen.models import ExtractedFields, Language, Lead, LeadRecord, ScoreResult
from leadgen.storage import Storage


@dataclass
class Screening:
    """Result of the code-level check of the raw message, done before the agent runs."""

    handover_reasons: list[str] = field(default_factory=list)
    injection_hits: list[str] = field(default_factory=list)


@dataclass
class LeadContext:
    """Passed to every tool call for one lead. The model never sees this object."""

    lead: Lead
    rulebook: RuleBook
    storage: Storage
    max_tool_calls: int
    run_id: str = ""
    screening: Screening = field(default_factory=Screening)

    # Working state filled in by tools.
    tool_calls: list[str] = field(default_factory=list)
    limit_hit: bool = False
    duplicate_of: str = ""
    extracted: ExtractedFields | None = None
    score: ScoreResult | None = None
    draft: str = ""
    draft_language: Language = "english"
    rejected_drafts: list[str] = field(default_factory=list)
    handover_reason: str = ""
    proposal: dict | None = None  # what the agent passed to save_lead
    record: LeadRecord | None = None
