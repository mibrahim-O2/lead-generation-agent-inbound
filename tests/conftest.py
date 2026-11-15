"""Shared fixtures. Every test runs on the mock or a scripted model: no key, no network."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import dotenv
import dotenv.main
import pytest
from agents import Model, set_tracing_disabled

from leadgen.config import RuleBook, Settings, load_rulebook
from leadgen.llm import LLMSetup, build_response
from leadgen.models import Lead

set_tracing_disabled(True)


ROOT = Path(__file__).resolve().parents[1]

# Every variable the application documents, active or commented out in example.env.
ENV_NAMES = frozenset(
    re.findall(r"^#? ?([A-Z][A-Z0-9_]+)=", (ROOT / "example.env").read_text(), re.M)
)
# Prefixes the application reads, so a new variable is covered before it is documented.
ENV_PREFIXES = (
    "LEADGEN_", "LLM_", "OPENAI_", "SHEETS_", "SHEET_", "GOOGLE_", "OLLAMA_", "API_",
    "CORS_", "VITE_", "MAX_",
)  # fmt: skip
# The only values tests start with. Everything else falls back to the code defaults.
TEST_ENV = {"LEADGEN_MOCK_LLM": "1", "OPENAI_API_KEY": ""}


def _find_no_dotenv(*_args: Any, **_kwargs: Any) -> str:
    """Stands in for dotenv's file search: during tests no .env file is ever found."""
    return ""


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make every test independent of the developer's shell and of any real .env file.

    1. The CLI, the eval runner and the server call `load_dotenv()`, which searches
       upward from src/leadgen and finds the repository's real .env. Its values are
       then written into os.environ for the rest of the test run. Replacing the
       search with one that finds nothing stops that at the source, without
       changing any application code. Loading an explicit path still works.
    2. Every documented variable, and any variable with a prefix the app reads, is
       removed for the duration of the test, so values exported in the shell do
       not leak in either. Tests set what they need with monkeypatch.
    """
    monkeypatch.setattr(dotenv.main, "find_dotenv", _find_no_dotenv)  # used by load_dotenv()
    monkeypatch.setattr(dotenv, "find_dotenv", _find_no_dotenv)  # the package-level name
    for name in list(os.environ):
        if name in ENV_NAMES or name.startswith(ENV_PREFIXES):
            monkeypatch.delenv(name)
    for name, value in TEST_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LEADGEN_DATA_DIR", str(tmp_path / "data"))


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
