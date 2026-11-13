"""The agent loop against the mock model and against deliberately misbehaving models."""

from __future__ import annotations

import asyncio

import pytest

from leadgen.agent import build_agent, build_instructions
from leadgen.config import Settings
from leadgen.llm import LLMConfigError, mock_analyse, resolve_llm
from leadgen.models import Lead, LeadDecision
from leadgen.runner import process_lead
from leadgen.storage import MemoryStorage
from tests.conftest import decision, scripted


def run(lead: Lead, rulebook, llm, settings=None, storage=None):
    settings = settings or Settings(mock_llm=True)
    record, tokens_in, tokens_out = asyncio.run(
        process_lead(
            lead, rulebook=rulebook, storage=storage or MemoryStorage(), llm=llm, settings=settings
        )
    )
    return record


def test_agent_definition(rulebook) -> None:
    agent = build_agent(rulebook, None)
    assert agent.output_type is LeadDecision
    assert len(agent.tools) == 8
    text = build_instructions(rulebook)
    for phrase in ("never send", "untrusted DATA", "Example Solar Co", "score 7", "guarantee"):
        assert phrase.lower() in text.lower(), phrase


def test_hot_lead_end_to_end_with_mock(rulebook, settings) -> None:
    lead = Lead(
        id="H1", name="Hot Lead", email="hot@example.com",
        message="1 kanal house in DHA Lahore, bill around 60,000, need a quote this month. "
                "How does net metering work?",
    )  # fmt: skip
    storage = MemoryStorage()
    record = run(lead, rulebook, resolve_llm(settings), settings, storage)
    assert (record.route, record.status, record.is_hot) == ("draft_reply", "pending_approval", True)
    assert record.score == 9
    assert "https://example.com/book-a-call" in record.draft_reply
    assert "distribution company" in record.draft_reply  # FAQ answer was used
    assert record.tool_calls[0] == "check_duplicate" and record.tool_calls[-1] == "save_lead"
    assert storage.list_records()[0].lead.id == "H1"


def test_mock_chooses_different_tools_for_different_leads(rulebook, settings) -> None:
    llm = resolve_llm(settings)
    vague = run(Lead(id="V", email="v@example.com", message="solar info please"), rulebook, llm)
    complaint = run(Lead(id="C", email="c@example.com", message="I want a refund"), rulebook, llm)
    assert "get_calendar_link" not in vague.tool_calls and "draft_reply" in vague.tool_calls
    assert complaint.tool_calls == ["check_duplicate", "flag_handover", "save_lead"]


def test_forbidden_draft_is_rejected_by_the_tool(rulebook, lead) -> None:
    llm = scripted(
        [
            ("tool", "draft_reply", {"body": "It costs Rs 900,000.", "language": "english"}),
            ("tool", "save_lead", {"intent": "price_enquiry", "route": "draft_reply",
                                   "summary": "s", "missing_info": []}),
            ("final", decision(draft_reply="It costs Rs 900,000, guaranteed.")),
        ]
    )  # fmt: skip
    record = run(lead, rulebook, llm)
    assert record.draft_reply == "" and record.route == "handover"
    assert "draft_blocked" in record.flags


def test_model_can_fix_a_rejected_draft(rulebook, lead) -> None:
    llm = scripted(
        [
            ("tool", "draft_reply", {"body": "You will save 80% for sure.", "language": "english"}),
            ("tool", "draft_reply", {"body": "Which city are you in?", "language": "english"}),
            ("final", decision()),
        ]
    )  # fmt: skip
    record = run(lead, rulebook, llm)
    assert record.route == "draft_reply" and record.draft_reply == "Which city are you in?"
    assert "draft_blocked" in record.flags  # the reviewer still sees that one was blocked


def test_tool_call_limit_stops_a_runaway_model(rulebook, lead) -> None:
    llm = scripted([("tool", "search_faq", {"query": "warranty"})])  # never stops by itself
    settings = Settings(mock_llm=True, max_tool_calls_per_lead=3)
    record = run(lead, rulebook, llm, settings)
    assert record.route == "handover" and "tool_limit_hit" in record.flags
    assert len(record.tool_calls) <= settings.max_tool_calls_per_lead + 2
    assert "MaxTurnsExceeded" in record.error


def test_model_error_becomes_a_handover_not_a_crash(rulebook, lead) -> None:
    record = run(lead, rulebook, scripted([("raise", "provider down")]))
    assert record.route == "handover" and "provider down" in record.error


def test_model_cannot_skip_scoring_or_fake_a_score(rulebook) -> None:
    lead = Lead(id="S", email="s@example.com", message="Factory in Lahore, bill 15 lakh")
    fields = {"property_type": "home", "monthly_bill_pkr": None, "location": "Lahore",
              "timeline": "unknown", "product_interest": [], "quote_requested": False,
              "urgency": "low"}  # fmt: skip
    llm = scripted(
        [
            ("tool", "draft_reply", {"body": "Thanks for reaching out.", "language": "english"}),
            ("final", decision(score=10, extracted=fields)),
        ]
    )
    record = run(lead, rulebook, llm)
    assert record.score == 4  # rubric on the extracted fields, not the claimed 10
    assert any("score_lead" in note for note in record.guardrail_notes)


def test_resolve_llm(settings) -> None:
    assert resolve_llm(settings).mock
    with pytest.raises(LLMConfigError, match="OPENAI_API_KEY"):
        resolve_llm(Settings())
    with pytest.raises(LLMConfigError, match="OPENAI_API_KEY"):
        resolve_llm(Settings(openai_api_key="sk-REPLACE-ME"))
    with pytest.raises(LLMConfigError, match="not supported"):
        resolve_llm(Settings(llm_provider="other", openai_api_key="x"))
    real = resolve_llm(Settings(openai_api_key="sk-test-not-real", llm_model="some-model"))
    assert (real.provider, real.model, real.mock) == ("openai", "some-model", False)
    assert resolve_llm(Settings(openai_api_key="sk-test-not-real")).model is None


@pytest.mark.parametrize(
    ("message", "amount"),
    [("bill around 60,000", 60_000), ("bill 70 hazar aata hai", 70_000),
     ("monthly bill is around 15 lakh", 1_500_000), ("45k monthly bill", 45_000),
     ("no number here", None)],
)  # fmt: skip
def test_mock_reads_bill_amounts(message: str, amount) -> None:
    assert mock_analyse(message)["monthly_bill_pkr"] == amount
