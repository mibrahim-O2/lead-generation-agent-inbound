"""The tools the agent can call. Each one is small, typed and returns JSON text.

There is deliberately no tool that sends anything: the agent can only draft.
Every tool counts against the per-lead tool budget.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from agents import RunContextWrapper, function_tool

from leadgen.config import project_root
from leadgen.context import LeadContext
from leadgen.guardrails import check_draft, finalize
from leadgen.models import (
    ExtractedFields,
    HandoverCategory,
    Intent,
    Language,
    PropertyType,
    Route,
    Timeline,
    Urgency,
)
from leadgen.scoring import score_fields

Ctx = RunContextWrapper[LeadContext]


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _over_budget(ctx: LeadContext, tool_name: str) -> str | None:
    """Count the call. Returns an error for the model once the budget is spent."""
    ctx.tool_calls.append(tool_name)
    if len(ctx.tool_calls) > ctx.max_tool_calls:
        ctx.limit_hit = True
        return _json({"error": "Tool call limit reached. Stop and give your final answer."})
    return None


# ----------------------------------------------------------------------------- FAQ search


@lru_cache(maxsize=4)
def load_faq(path: str) -> tuple[tuple[str, str], ...]:
    """Split the FAQ markdown into (heading, body) sections."""
    text = Path(path).read_text(encoding="utf-8")
    sections = re.split(r"^## +", text, flags=re.MULTILINE)[1:]
    return tuple(
        (
            part.split("\n", 1)[0].strip(),
            " ".join(part.split("\n", 1)[1].split()) if "\n" in part else "",
        )
        for part in sections
    )


def faq_lookup(query: str, path: str | None = None, limit: int = 2) -> list[dict[str, str]]:
    """Keyword search over the FAQ: sections sharing the most words with the query."""
    path = path or str(project_root() / "data" / "faq.md")
    words = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2}
    scored = []
    for heading, body in load_faq(path):
        heading_words = set(re.findall(r"[a-z]+", heading.lower()))
        body_words = set(re.findall(r"[a-z]+", body.lower()))
        hits = 3 * len(words & heading_words) + len(words & body_words)
        if hits:
            scored.append((hits, heading, body))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [{"topic": heading, "answer": body} for _, heading, body in scored[:limit]]


# ----------------------------------------------------------------------------- the tools


@function_tool
def get_company_profile(wrapper: Ctx) -> str:
    """Get the company's name, services, customers, tone and working hours."""
    ctx = wrapper.context
    if error := _over_budget(ctx, "get_company_profile"):
        return error
    book = ctx.rulebook
    return _json(
        {
            "company": book.company.model_dump(),
            "tone": book.tone.model_dump(),
            "working_hours": book.working_hours.model_dump(),
            "qualification_questions": [q.model_dump() for q in book.qualification_questions],
        }
    )


@function_tool
def search_faq(wrapper: Ctx, query: str) -> str:
    """Search the company FAQ. Use it before answering a product or process question.

    Args:
        query: A few keywords, for example "net metering process" or "warranty".
    """
    ctx = wrapper.context
    if error := _over_budget(ctx, "search_faq"):
        return error
    return _json({"results": faq_lookup(query)})


@function_tool
def check_duplicate(wrapper: Ctx) -> str:
    """Check whether this person (same email or phone) already has a stored lead."""
    ctx = wrapper.context
    if error := _over_budget(ctx, "check_duplicate"):
        return error
    existing = ctx.storage.find_duplicate(ctx.lead)
    ctx.duplicate_of = existing.lead.id if existing else ""
    if not existing:
        return _json({"is_duplicate": False})
    return _json(
        {
            "is_duplicate": True,
            "existing_lead_id": existing.lead.id,
            "existing_route": existing.route,
            "existing_status": existing.status,
        }
    )


@function_tool
def score_lead(
    wrapper: Ctx,
    property_type: PropertyType,
    monthly_bill_pkr: int | None,
    location: str | None,
    timeline: Timeline,
    quote_requested: bool,
    product_interest: list[str],
    urgency: Urgency,
) -> str:
    """Score the lead from 1 to 10 with the company rubric. Pass only what the message says.

    Args:
        property_type: home, business, factory, farm, or unknown.
        monthly_bill_pkr: Monthly electricity bill in rupees, or null if not stated.
        location: City or area as written by the lead, or null if not stated.
        timeline: immediate (this month), within_3_months, later, or unknown.
        quote_requested: True if they asked for a quote, a price or a site visit.
        product_interest: Products mentioned, e.g. ["panels", "battery"].
        urgency: low, medium or high.
    """
    ctx = wrapper.context
    if error := _over_budget(ctx, "score_lead"):
        return error
    ctx.extracted = ExtractedFields(
        property_type=property_type,
        monthly_bill_pkr=monthly_bill_pkr,
        location=location,
        timeline=timeline,
        product_interest=product_interest,
        quote_requested=quote_requested,
        urgency=urgency,
    )
    ctx.score = score_fields(ctx.extracted, ctx.rulebook)
    return _json({**ctx.score.model_dump(), "hot_threshold": ctx.rulebook.scoring.hot_threshold})


@function_tool
def draft_reply(wrapper: Ctx, body: str, language: Language) -> str:
    """Store a DRAFT reply for human approval. Nothing is sent to the customer.

    The draft is rejected if it contains a forbidden claim; fix it and call again.

    Args:
        body: The full reply text.
        language: english or roman_urdu, matching the customer's message.
    """
    ctx = wrapper.context
    if error := _over_budget(ctx, "draft_reply"):
        return error
    body = body.strip()
    if not body:
        return _json({"accepted": False, "problems": ["empty draft"]})
    problems = check_draft(body, ctx.rulebook)
    if problems:
        ctx.rejected_drafts.append(body)
        descriptions = {rule.id: rule.description for rule in ctx.rulebook.forbidden_claims}
        return _json(
            {
                "accepted": False,
                "problems": [f"{p}: {descriptions.get(p, '')}" for p in problems],
                "hint": "Remove these claims and call draft_reply again.",
            }
        )
    ctx.draft, ctx.draft_language = body, language
    return _json({"accepted": True, "status": "draft stored for human approval; not sent"})


@function_tool
def flag_handover(wrapper: Ctx, reason: str, category: HandoverCategory) -> str:
    """Hand this lead to a human. Use for complaints, anger, legal threats or anything risky.

    Args:
        reason: One sentence a human can act on.
        category: complaint, legal_threat, angry, duplicate or other.
    """
    ctx = wrapper.context
    if error := _over_budget(ctx, "flag_handover"):
        return error
    ctx.handover_reason = f"{category}: {reason.strip()}"
    return _json({"handover": True, "note": "A human will take over. Do not draft a reply."})


@function_tool
def get_calendar_link(wrapper: Ctx) -> str:
    """Get the booking link to offer a call or site survey. Offer it to hot leads only."""
    ctx = wrapper.context
    if error := _over_budget(ctx, "get_calendar_link"):
        return error
    return _json(
        {
            "calendar_link": ctx.rulebook.calendar_link,
            "working_hours": ctx.rulebook.working_hours.model_dump(),
        }
    )


@function_tool
def save_lead(
    wrapper: Ctx, intent: Intent, route: Route, summary: str, missing_info: list[str]
) -> str:
    """Save the lead with your decision. Call this once, after scoring and drafting.

    Args:
        intent: What the person wants.
        route: draft_reply, handover, nurture or spam.
        summary: One or two sentences for the human reviewer.
        missing_info: Fields still unknown, e.g. ["monthly_bill_pkr", "timeline"].
    """
    ctx = wrapper.context
    if error := _over_budget(ctx, "save_lead"):
        return error
    ctx.proposal = {
        "intent": intent,
        "route": route,
        "summary": summary.strip(),
        "missing_info": missing_info,
    }
    ctx.record = finalize(ctx, None)
    ctx.storage.save_record(ctx.record)
    return _json(
        {
            "saved": True,
            "lead_id": ctx.lead.id,
            "route": ctx.record.route,
            "score": ctx.record.score,
            "notes": ctx.record.guardrail_notes,
        }
    )


ALL_TOOLS = [
    get_company_profile,
    search_faq,
    check_duplicate,
    score_lead,
    draft_reply,
    flag_handover,
    get_calendar_link,
    save_lead,
]
