"""Provider abstraction - the ONLY module that knows about model providers.

`resolve_llm(settings)` is the single entry point. Selection is env-only:
LLM_PROVIDER and LLM_MODEL, or LEADGEN_MOCK_LLM=1 for the offline mock.

The mock is a small rule-based stand-in for a real model. It speaks the Agents
SDK `Model` interface, so the real agent loop, tools and guardrails all run
without an API key. It is for tests and demos: it is keyword matching, not
language understanding.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agents import Model, ModelResponse, Usage, set_tracing_disabled
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from leadgen.config import Settings


class LLMConfigError(Exception):
    """The provider settings are missing or not supported."""


@dataclass
class LLMSetup:
    provider: str
    model_name: str  # label for logs
    model: str | Model | None  # what is passed to Agent(model=...); None = SDK default
    mock: bool = False


def resolve_llm(settings: Settings) -> LLMSetup:
    """Pick the model from the environment settings."""
    if settings.mock_llm:
        set_tracing_disabled(True)  # tracing uploads need an OpenAI key
        return LLMSetup(provider="mock", model_name="mock-rules", model=MockModel(), mock=True)
    if settings.llm_provider == "openai":
        if not settings.openai_api_key or settings.openai_api_key == "sk-REPLACE-ME":
            raise LLMConfigError(
                "Missing API key: set OPENAI_API_KEY in .env, "
                "or set LEADGEN_MOCK_LLM=1 to run without a key."
            )
        return LLMSetup(
            provider="openai",
            model_name=settings.llm_model or "sdk-default",
            model=settings.llm_model or None,
        )
    raise LLMConfigError(
        f"LLM_PROVIDER='{settings.llm_provider}' is not supported yet. "
        "Use 'openai' or set LEADGEN_MOCK_LLM=1."
    )


# =============================================================================
# Mock model
# =============================================================================

_PROPERTY_WORDS = {
    "factory": r"factory|textile|mill\b|industrial|manufactur|warehouse|cold storage|plant\b",
    "farm": r"farm|tube ?well|agricultur|zameen|khet|dairy|poultry|orchard",
    "business": r"office|shop|school|hospital|restaurant|plaza|commercial|clinic|hotel"
    r"|showroom|dukaan|business|store\b|salon",
    "home": r"house|home|ghar|makan|kanal|marla|residen|apartment|flat\b|bungalow|villa",
}
_CITIES = (
    "kasur|sheikhupura|gujranwala|muridke|pattoki|nankana|karachi|islamabad|rawalpindi|multan"
    "|peshawar|quetta|faisalabad|sialkot|hyderabad|bahawalpur|sargodha|lahore"
)
_AREAS = "dha|gulberg|johar town|model town|bahria|raiwind|cantt"
_IMMEDIATE = (
    r"this month|this week|next week|asap|as soon as|urgent|immediately|right away"
    r"|jaldi|foran|abhi\b|is mahine|is hafte"
)
_SOON = r"next month|agle mahine|within (2|3|two|three) months|few weeks|couple of months|soon\b"
_LATER = (
    r"next year|agle saal|just exploring|only exploring|someday|no rush|not in a hurry"
    r"|baad mein|in future|later\b|6 months|six months|not sure when"
)
_QUOTE = r"quot(e|ation)|proposal|estimate|\brates?\b|price|pricing|cost|kitn[ae]|qeemat|keemat"
_SITE_VISIT = r"site (visit|survey)|\bsurvey\b|\bvisit\b"
_PRODUCTS = {
    "panels": r"panel",
    "inverter": r"inverter",
    "battery": r"batter",
    "net metering": r"net[- ]?metering",
    "installation": r"install|lagwa",
    "hybrid system": r"hybrid",
    "solar system": r"\d\s*kw\b.{0,20}system|solar system|complete system",
    "on-grid system": r"on[- ]?grid",
}
_FAQ_TOPICS = {
    "net metering process": r"net[- ]?metering",
    "warranty": r"warrant",
    "financing": r"financ|installment|instalment|loan|qist|bank",
    "system sizing": r"what size|how many (panels|kw)|sizing|kitne (kw|panel)|which system",
    "installation time": r"how long|kitne din|kitna time|installation time",
    "batteries and backup": r"backup|load ?shedding",
}
_SPAM = (
    r"\bseo\b|backlink|crypto|bitcoin|casino|lottery|viagra|click here|guest post"
    r"|web ?design|increase your (traffic|sales|followers)|forex|earn \$|work from home"
    r"|whatsapp group|buy followers|https?://(?!example\.com)"
)
_COMPLAINT = (
    r"complain|refund|legal action|lawyer|court|\bsue\b|worst|pathetic|fraud|scam"
    r"|never came|still faulty|not working|fed up|shikayat"
)


def _find(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def _bill_amount(text: str) -> int | None:
    """A monthly bill figure in rupees, if one is stated near the word 'bill'."""
    number = r"(\d[\d,]*(?:\.\d+)?)\s*(k\b|lakh|lac|lacs|hazar|hazaar|thousand|million)?"
    for pattern in (rf"bill\D{{0,30}}{number}", rf"{number}\D{{0,25}}bill"):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1).replace(",", ""))
            unit = (match.group(2) or "").lower()
            if unit in ("k", "hazar", "hazaar", "thousand"):
                value *= 1_000
            elif unit in ("lakh", "lac", "lacs"):
                value *= 100_000
            elif unit == "million":
                value *= 1_000_000
            return int(value)
    return None


def _load_kw(text: str) -> int | None:
    """A sanctioned or connected load in kW, if one is stated."""
    number = r"(\d[\d,]*)\s*kw"
    for pattern in (rf"\bload\D{{0,20}}{number}", rf"{number}\s*(sanctioned|connected)?\s*load"):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def mock_analyse(message: str) -> dict[str, Any]:
    """Keyword 'understanding' of a message. Stands in for what a real model would infer."""
    text = message.lower()
    property_type = next((k for k, p in _PROPERTY_WORDS.items() if _find(p, text)), "unknown")
    city = re.search(rf"\b({_CITIES})\b", text) or re.search(rf"\b({_AREAS})\b", text)
    if _find(_IMMEDIATE, text):
        timeline = "immediate"
    elif _find(_LATER, text):
        timeline = "later"
    elif _find(_SOON, text):
        timeline = "within_3_months"
    else:
        timeline = "unknown"
    quote, site_visit = _find(_QUOTE, text), _find(_SITE_VISIT, text)
    faq_topic = next((k for k, p in _FAQ_TOPICS.items() if _find(p, text)), None)
    bill, load = _bill_amount(text), _load_kw(text)

    if _find(_SPAM, text):
        intent = "spam"
    elif _find(_COMPLAINT, text):
        intent = "complaint"
    elif site_visit or _find(r"quot(e|ation)|proposal|estimate", text):
        intent = "quote_request"
    elif quote and property_type == "unknown" and bill is None:
        intent = "price_enquiry"
    elif faq_topic:
        intent = "product_question"
    else:
        intent = "general_enquiry"

    return {
        "intent": intent,
        "property_type": property_type,
        "monthly_bill_pkr": bill,
        "sanctioned_load_kw": load,
        "location": city.group(1) if city else None,
        "timeline": timeline,
        "quote_requested": quote,
        "site_visit_requested": site_visit,
        "product_interest": [k for k, p in _PRODUCTS.items() if _find(p, text)],
        "urgency": {"immediate": "high", "later": "low"}.get(timeline, "medium"),
        "faq_topic": faq_topic,
    }


def _write_draft(
    analysis: dict[str, Any],
    lead: dict[str, Any],
    questions: list[str],
    route: str,
    language: str,
    profile: dict[str, Any],
    faq: list[dict[str, str]],
    calendar: dict[str, Any] | None,
) -> str:
    """Compose a reply from the tool results. Avoids every forbidden claim.

    `questions` come from score_lead: already in the reply language and limited
    to what is really missing.
    """
    urdu = language != "english"
    company = profile.get("company", {}).get("name", "our team")
    sign_off = profile.get("tone", {}).get("sign_off", company)
    first_name = (lead.get("name") or "").split(" ")[0]
    greeting = "Assalam o Alaikum" if urdu else "Hi"
    parts = [f"{greeting}{' ' + first_name if first_name else ''},"]

    if route == "nurture":  # short note, at most one question, no list
        question = f" {questions[0]}" if questions else ""
        if urdu:
            parts.append(
                f"{company} se rabta karne ka shukriya. Koi jaldi nahi hai, jab bhi aap tayyar "
                f"hon isi message ka jawab de dein aur hum baat aage barha lein ge.{question}"
            )
            parts.append(f"Shukriya,\n{sign_off}")
        else:
            parts.append(
                f"Thank you for contacting {company}. There is no rush at all: whenever you "
                f"are ready, just reply to this message and we will pick it up from there."
                f"{question}"
            )
            parts.append(f"Kind regards,\n{sign_off}")
        return "\n\n".join(parts)

    if urdu:
        parts.append(f"{company} se rabta karne ka shukriya.")
        if analysis["intent"] == "price_enquiry":
            parts.append(
                "Qeemat system ke size aur equipment par depend karti hai, is liye hum "
                "figures sirf written proposal mein share karte hain."
            )
        if questions:
            parts.append(
                "Behtar proposal ke liye yeh maloomat share kar dein:\n"
                + "\n".join(f"- {q}" for q in questions)
            )
        if calendar:
            parts.append(
                f"Call ya site survey ke liye aap yahan waqt book kar sakte hain: "
                f"{calendar['calendar_link']}"
            )
        parts.append(f"Shukriya,\n{sign_off}")
    else:
        parts.append(f"Thank you for contacting {company}.")
        if analysis["intent"] == "price_enquiry":
            parts.append(
                "Pricing depends on the system size and the equipment chosen, so we share "
                "figures only in a written proposal once we understand your needs."
            )
        if faq:
            parts.append(f"About {faq[0]['topic'].lower()}: {faq[0]['answer']}")
        if questions:
            parts.append(
                "To prepare the right proposal for you, could you please share:\n"
                + "\n".join(f"- {q}" for q in questions)
            )
        if calendar:
            hours = calendar.get("working_hours", {})
            parts.append(
                "You are welcome to book a call or a site survey at a time that suits you: "
                f"{calendar['calendar_link']} "
                f"(our team is available {hours.get('days', '')}, {hours.get('hours', '')})."
            )
        parts.append(f"Kind regards,\n{sign_off}")
    return "\n\n".join(parts)


def _get(item: Any, key: str) -> Any:
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def _read_conversation(
    items: str | list[Any],
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    """Return (lead, system facts, tool results so far) from the SDK's input items."""
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    user_text, names, outputs = "", {}, {}
    for item in items:
        kind = _get(item, "type")
        if kind == "function_call":
            names[_get(item, "call_id")] = _get(item, "name")
        elif kind == "function_call_output":
            outputs[_get(item, "call_id")] = _get(item, "output")
        elif _get(item, "role") == "user" and not user_text:
            content = _get(item, "content")
            if isinstance(content, list):
                content = " ".join(str(_get(part, "text") or "") for part in content)
            user_text = str(content)
    match = re.search(r"<lead_data>\s*(\{.*\})\s*</lead_data>(.*)", user_text, re.DOTALL)
    lead = json.loads(match.group(1)) if match else {"message": user_text}
    # Facts are read only from the text AFTER the data tag, never from the message.
    facts = dict(re.findall(r"^- (\w+): (\S+)", match.group(2) if match else "", re.MULTILINE))
    done: dict[str, Any] = {}
    for call_id, name in names.items():
        raw = outputs.get(call_id)
        try:
            done[name] = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            done[name] = {"raw": raw}
    return lead, facts, done


def mock_next_step(
    lead: dict[str, Any], facts: dict[str, str], done: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Decide the next move from what is known so far.

    Returns ("tool", {"name": ..., "arguments": {...}}) or ("final", decision).
    """
    analysis = mock_analyse(lead.get("message", ""))
    language = facts.get("reply_language", "english")
    if language == "urdu":
        language = "roman_urdu"  # the mock cannot write Urdu script
    duplicate_of = facts.get("duplicate_of", "none")
    fields = {
        key: analysis[key]
        for key in (
            "property_type", "monthly_bill_pkr", "sanctioned_load_kw", "location", "timeline",
            "quote_requested", "site_visit_requested", "product_interest", "urgency",
        )
    }  # fmt: skip
    scored = done.get("score_lead") or {}
    missing = scored.get("missing_fields", [])

    def tool(name: str, **arguments: Any) -> tuple[str, dict[str, Any]]:
        return "tool", {"name": name, "arguments": arguments}

    def finish(route: str, summary: str, score: int = 1) -> tuple[str, dict[str, Any]]:
        if "save_lead" not in done:
            return tool("save_lead", intent=analysis["intent"], route=route, summary=summary)
        return "final", {
            "intent": analysis["intent"],
            "extracted": fields,
            "score": done["save_lead"].get("score", score),
            "route": done["save_lead"].get("route", route),
            "missing_info": missing if route in ("draft_reply", "nurture") else [],
            "draft_reply": done.get("_draft", ""),
            "summary": summary,
        }

    if any("error" in (result or {}) for result in done.values() if isinstance(result, dict)):
        return finish("handover", "Stopped early: a tool reported an error.")
    if analysis["intent"] == "spam":
        return finish("spam", "Looks like spam or an unrelated sales pitch.")
    if analysis["intent"] == "complaint":
        if "flag_handover" not in done:
            return tool(
                "flag_handover",
                reason="Customer is unhappy or raising a complaint; needs a personal reply.",
                category="complaint",
            )
        return finish("handover", "Complaint or upset customer. Handed to a human.")
    if duplicate_of != "none":
        if "flag_handover" not in done:
            return tool(
                "flag_handover",
                reason=f"Same contact as existing lead {duplicate_of}; avoid a second reply.",
                category="duplicate",
            )
        return finish("handover", "Repeat enquiry from an existing lead.")

    if "score_lead" not in done:
        return tool("score_lead", **fields)
    score = scored.get("score", 1)
    is_hot = bool(scored.get("is_hot"))
    route = "nurture" if scored.get("draft_kind") == "nurture" else "draft_reply"
    questions = scored.get("questions_to_ask", [])

    if "get_company_profile" not in done:
        return tool("get_company_profile")
    if analysis["faq_topic"] and route != "nurture" and "search_faq" not in done:
        return tool("search_faq", query=analysis["faq_topic"])
    if is_hot and "get_calendar_link" not in done:
        return tool("get_calendar_link")
    draft = _write_draft(
        analysis,
        lead,
        questions,
        route,
        language,
        done["get_company_profile"],
        (done.get("search_faq") or {}).get("results", []),
        done.get("get_calendar_link"),
    )
    if "draft_reply" not in done:
        return tool("draft_reply", body=draft, language=language)
    done["_draft"] = draft if done["draft_reply"].get("accepted") else ""
    label = "Hot lead" if is_hot else "Lead"
    return finish(
        route,
        f"{label} ({analysis['property_type']}, score {score}). "
        f"Still missing: {', '.join(missing) or 'nothing'}.",
        score,
    )


def build_response(
    kind: str, payload: dict[str, Any], call_number: int, prompt_chars: int = 0
) -> ModelResponse:
    """Build an SDK ModelResponse holding one tool call ("tool") or the final answer."""
    if kind == "tool":
        text = json.dumps(payload["arguments"], ensure_ascii=False)
        item: Any = ResponseFunctionToolCall(
            id=f"fc_mock_{call_number}",
            call_id=f"call_mock_{call_number}",
            name=payload["name"],
            arguments=text,
            type="function_call",
            status="completed",
        )
    else:
        text = json.dumps(payload, ensure_ascii=False)
        item = ResponseOutputMessage(
            id=f"msg_mock_{call_number}",
            content=[ResponseOutputText(text=text, type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        )
    # Rough token estimate (about 4 characters per token) so limits and logs work.
    input_tokens, output_tokens = prompt_chars // 4, max(1, len(text) // 4)
    return ModelResponse(
        output=[item],
        usage=Usage(
            requests=1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
        response_id=None,
    )


class MockModel(Model):
    """Offline stand-in for a real model. One tool call (or the final answer) per turn."""

    def __init__(self) -> None:
        self._calls = 0

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[Any],
        model_settings: Any,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        **kwargs: Any,
    ) -> ModelResponse:
        self._calls += 1
        lead, facts, done = _read_conversation(input)
        kind, payload = mock_next_step(lead, facts, done)
        prompt_chars = len(system_instructions or "") + len(json.dumps(input, default=str))
        return build_response(kind, payload, self._calls, prompt_chars)

    def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        raise NotImplementedError("The mock model does not support streaming.")
