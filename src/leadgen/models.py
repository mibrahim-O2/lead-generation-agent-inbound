"""Typed data models shared by the agent, tools, storage and API."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

PropertyType = Literal["home", "business", "factory", "farm", "unknown"]
Timeline = Literal["immediate", "within_3_months", "later", "unknown"]
Urgency = Literal["low", "medium", "high"]
Route = Literal["draft_reply", "handover", "nurture", "spam"]
Intent = Literal[
    "quote_request",
    "price_enquiry",
    "product_question",
    "general_enquiry",
    "complaint",
    "spam",
    "other",
]
Language = Literal["english", "roman_urdu"]
HandoverCategory = Literal["complaint", "legal_threat", "angry", "duplicate", "other"]
# A draft is never sent by this system: "pending_approval" waits for a human.
Status = Literal["pending_approval", "needs_human", "nurture", "discarded"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Lead(BaseModel):
    """One inbound enquiry, exactly as it arrived."""

    id: str = ""
    received_at: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    channel: str = "web_form"
    message: str = Field(default="", max_length=5000)

    def with_defaults(self) -> Lead:
        """Fill in a stable id and a timestamp when the source did not provide them."""
        received = self.received_at or now_iso()
        lead_id = self.id
        if not lead_id:
            raw = f"{self.email}|{self.phone}|{self.message}|{received}"
            lead_id = "L-" + hashlib.sha1(raw.encode()).hexdigest()[:10]
        return self.model_copy(update={"id": lead_id, "received_at": received})


class ExtractedFields(BaseModel):
    """What the agent understood from the message."""

    property_type: PropertyType = "unknown"
    monthly_bill_pkr: int | None = None
    location: str | None = None
    timeline: Timeline = "unknown"
    product_interest: list[str] = Field(default_factory=list)
    quote_requested: bool = False
    urgency: Urgency = "medium"


class ScoreResult(BaseModel):
    score: int
    is_hot: bool
    breakdown: dict[str, int]
    location_fit: Literal["core", "nearby", "outside", "unknown"]


class LeadDecision(BaseModel):
    """The agent's final answer for one lead (its structured output)."""

    intent: Intent
    extracted: ExtractedFields
    score: int
    route: Route
    missing_info: list[str]
    draft_reply: str
    summary: str


class LeadRecord(BaseModel):
    """What gets stored for a processed lead, after the code-level guardrails ran."""

    lead: Lead
    intent: Intent = "other"
    extracted: ExtractedFields = Field(default_factory=ExtractedFields)
    score: int = 1
    is_hot: bool = False
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    route: Route = "handover"
    status: Status = "needs_human"
    missing_info: list[str] = Field(default_factory=list)
    draft_reply: str = ""
    draft_language: Language = "english"
    summary: str = ""
    handover_reason: str = ""
    duplicate_of: str = ""
    flags: list[str] = Field(default_factory=list)
    guardrail_notes: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    run_id: str = ""
    processed_at: str = Field(default_factory=now_iso)
    error: str = ""


class RunRecord(BaseModel):
    """One line of run history."""

    id: str
    started_at: str
    finished_at: str = ""
    source: str = "sample"
    dry_run: bool = False
    provider: str = ""
    model: str = ""
    leads_received: int = 0
    leads_processed: int = 0
    drafts_created: int = 0
    handovers: int = 0
    nurture: int = 0
    spam: int = 0
    hot_leads: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_estimate_usd: float | None = None
    errors: list[str] = Field(default_factory=list)
    stopped_reason: str = ""
