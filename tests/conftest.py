"""Shared fixtures. Every test runs on the mock or a scripted model: no key, no network."""

from __future__ import annotations

from typing import Any

import pytest
from agents import Model, set_tracing_disabled

from leadgen.config import RuleBook, Settings, load_rulebook
from leadgen.llm import LLMSetup, build_response
from leadgen.models import Lead

set_tracing_disabled(True)


@pytest.fixture(autouse=True)
def safe_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Force mock mode and a throwaway data folder, whatever is in the developer's .env."""
    monkeypatch.setenv("LEADGEN_MOCK_LLM", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LEADGEN_DATA_DIR", str(tmp_path / "data"))
    for name in ("LLM_PROVIDER", "LLM_MODEL", "MAX_LEADS_PER_RUN", "MAX_TOOL_CALLS_PER_LEAD",
                 "MAX_TOKENS_PER_RUN", "LEADGEN_PRESET", "LEADGEN_CLIENT_CONFIG", "CORS_ORIGINS",
                 "API_HOST", "API_PORT"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def rulebook() -> RuleBook:
    return load_rulebook("solar", "config/client.yaml")


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(mock_llm=True, data_dir=str(tmp_path / "data"))


@pytest.fixture
def lead() -> Lead:
    return Lead(
        id="T1",
        name="Test Lead",
        email="test.lead@example.com",
        phone="0300-0000099",
        message="We need solar for our house in Lahore.",
    )


class ScriptedModel(Model):
    """Plays back a fixed list of steps, to act as a misbehaving model in tests.

    Each step is ("tool", name, arguments) or ("final", decision_dict). The last
    step repeats if the run keeps going.
    """

    def __init__(self, steps: list[tuple]) -> None:
        self.steps = steps
        self.calls = 0

    async def get_response(self, *args: Any, **kwargs: Any):
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        if step[0] == "raise":
            raise RuntimeError(step[1])
        if step[0] == "tool":
            return build_response("tool", {"name": step[1], "arguments": step[2]}, self.calls, 400)
        return build_response("final", step[1], self.calls, 400)

    def stream_response(self, *args: Any, **kwargs: Any):
        raise NotImplementedError


def scripted(steps: list[tuple]) -> LLMSetup:
    return LLMSetup(provider="test", model_name="scripted", model=ScriptedModel(steps))


def decision(**overrides: Any) -> dict[str, Any]:
    base = {
        "intent": "general_enquiry",
        "extracted": {
            "property_type": "unknown", "monthly_bill_pkr": None, "location": None,
            "timeline": "unknown", "product_interest": [], "quote_requested": False,
            "urgency": "medium",
        },
        "score": 1,
        "route": "draft_reply",
        "missing_info": [],
        "draft_reply": "",
        "summary": "test",
    }  # fmt: skip
    return {**base, **overrides}
