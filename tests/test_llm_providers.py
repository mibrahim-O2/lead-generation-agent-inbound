"""Provider switching. No key, no network: provider classes are replaced by recorders."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from agents import Model, OpenAIChatCompletionsModel

from leadgen import llm
from leadgen.config import Settings
from leadgen.llm import PROVIDERS, LLMConfigError, MockModel, resolve_llm

ROOT = Path(__file__).resolve().parents[1]
LITELLM = {
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic"),
    "gemini": ("GEMINI_API_KEY", "gemini"),
    "mistral": ("MISTRAL_API_KEY", "mistral"),
    "deepseek": ("DEEPSEEK_API_KEY", "deepseek"),
    "groq": ("GROQ_API_KEY", "groq"),
    "openrouter": ("OPENROUTER_API_KEY", "openrouter"),
}


class Recorder(Model):
    """Stands in for LitellmModel: remembers how it was built, never calls anything."""

    def __init__(self, model: str, api_key: str | None, base_url: str | None) -> None:
        self.model, self.api_key, self.base_url = model, api_key, base_url

    async def get_response(self, *args, **kwargs):
        raise AssertionError("no model call is expected in these tests")

    def stream_response(self, *args, **kwargs):
        raise AssertionError("no model call is expected in these tests")


@pytest.fixture
def litellm(monkeypatch) -> None:
    monkeypatch.setattr(llm, "_litellm_model", Recorder)


def settings(provider: str, model: str = "some-model", **extra) -> Settings:
    return Settings(llm_provider=provider, llm_model=model, **extra)


def test_provider_table_covers_the_documented_providers() -> None:
    assert set(PROVIDERS) == {
        "openai", "anthropic", "gemini", "mistral", "deepseek", "groq", "openrouter", "ollama",
        "openai_compatible",
    }  # fmt: skip
    for name, (key_env, prefix) in LITELLM.items():
        spec = PROVIDERS[name]
        assert (spec.kind, spec.key_env, spec.litellm_prefix) == ("litellm", key_env, prefix)


def test_openai_is_the_default_and_uses_the_sdk_default_path() -> None:
    assert Settings.from_env({}).llm_provider == "openai"
    setup = resolve_llm(Settings(openai_api_key="sk-test-not-real", llm_model="some-model"), {})
    assert (setup.provider, setup.model, setup.model_name) == ("openai", "some-model", "some-model")
    default = resolve_llm(Settings(openai_api_key="sk-test-not-real"), {})
    assert default.model is None and default.model_name == "sdk-default"


@pytest.mark.parametrize("provider", sorted(LITELLM))
def test_litellm_providers(litellm, provider: str) -> None:
    key_env, prefix = LITELLM[provider]
    setup = resolve_llm(settings(provider), {key_env: "test-key-not-real"})
    assert setup.provider == provider and setup.model_name == "some-model" and not setup.mock
    assert isinstance(setup.model, Recorder)
    assert setup.model.model == f"{prefix}/some-model"
    assert setup.model.api_key == "test-key-not-real" and setup.model.base_url is None


@pytest.mark.parametrize("provider", sorted(LITELLM))
@pytest.mark.parametrize("value", [None, "", "REPLACE-ME"])
def test_missing_key_names_the_variable(litellm, provider: str, value) -> None:
    key_env = LITELLM[provider][0]
    env = {} if value is None else {key_env: value}
    with pytest.raises(LLMConfigError, match=f"needs {key_env} in .env"):
        resolve_llm(settings(provider), env)


def test_openai_key_from_another_provider_is_not_used(litellm) -> None:
    with pytest.raises(LLMConfigError, match="ANTHROPIC_API_KEY"):
        resolve_llm(settings("anthropic", openai_api_key="sk-test-not-real"), {})


def test_ollama_needs_no_key_and_has_a_default_address(litellm) -> None:
    setup = resolve_llm(settings("ollama", "local-model"), {})
    assert setup.model.model == "ollama_chat/local-model"
    assert setup.model.api_key is None and setup.model.base_url == "http://localhost:11434"
    custom = resolve_llm(settings("ollama", "m"), {"OLLAMA_BASE_URL": "http://192.168.1.5:11434"})
    assert custom.model.base_url == "http://192.168.1.5:11434"


def test_openai_compatible_uses_the_sdk_chat_completions_model() -> None:
    env = {"LLM_BASE_URL": "https://llm.example.com/v1", "LLM_API_KEY": "test-key-not-real"}
    setup = resolve_llm(settings("openai_compatible", "my-model"), env)
    assert isinstance(setup.model, OpenAIChatCompletionsModel)
    assert setup.model.model == "my-model"
    assert str(setup.model._client.base_url).rstrip("/") == "https://llm.example.com/v1"
    with pytest.raises(LLMConfigError, match="LLM_BASE_URL is required"):
        resolve_llm(settings("openai_compatible"), {"LLM_API_KEY": "test-key-not-real"})
    with pytest.raises(LLMConfigError, match="needs LLM_API_KEY"):
        resolve_llm(settings("openai_compatible"), {"LLM_BASE_URL": "https://llm.example.com/v1"})


@pytest.mark.parametrize("provider", [*sorted(LITELLM), "ollama", "openai_compatible"])
def test_model_name_is_required_for_other_providers(litellm, provider: str) -> None:
    with pytest.raises(LLMConfigError, match=f"LLM_MODEL is required when LLM_PROVIDER={provider}"):
        resolve_llm(settings(provider, model=""), {"ANY": "x"})


def test_unknown_provider_lists_the_choices() -> None:
    with pytest.raises(LLMConfigError) as info:
        resolve_llm(settings("chatgpt"), {})
    message = str(info.value)
    assert "Unknown LLM_PROVIDER 'chatgpt'" in message and "MODEL_SWITCH.md" in message
    assert all(name in message for name in PROVIDERS)


def test_provider_name_is_case_insensitive(litellm) -> None:
    from_env = Settings.from_env({"LLM_PROVIDER": "Anthropic", "LLM_MODEL": "some-model"})
    assert resolve_llm(from_env, {"ANTHROPIC_API_KEY": "test-key-not-real"}).provider == "anthropic"


def test_missing_optional_dependency_is_a_clear_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "agents.extensions.models.litellm_model", None)
    with pytest.raises(LLMConfigError, match=r'Run: pip install -e "\.\[providers\]"'):
        resolve_llm(settings("anthropic"), {"ANTHROPIC_API_KEY": "test-key-not-real"})


def test_tracing_is_switched_off_for_other_providers(litellm, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(llm, "set_tracing_disabled", calls.append)
    resolve_llm(Settings(openai_api_key="sk-test-not-real"), {})
    assert calls == []  # OpenAI: left as the SDK and OPENAI_AGENTS_DISABLE_TRACING decide
    resolve_llm(settings("groq"), {"GROQ_API_KEY": "test-key-not-real"})
    assert calls == [True]


def test_mock_wins_over_any_provider_and_needs_nothing() -> None:
    setup = resolve_llm(settings("anthropic", mock_llm=True), {})
    assert setup.mock and isinstance(setup.model, MockModel)


def test_real_litellm_class_is_used_when_the_extra_is_installed() -> None:
    """Only runs where the optional extra is installed."""
    pytest.importorskip("litellm")
    from agents.extensions.models.litellm_model import LitellmModel

    setup = resolve_llm(settings("anthropic"), {"ANTHROPIC_API_KEY": "test-key-not-real"})
    assert isinstance(setup.model, LitellmModel)
    assert setup.model.model == "anthropic/some-model"


def test_agent_runs_with_a_non_openai_model_object(litellm, rulebook) -> None:
    """The agent accepts any provider's Model object; nothing else in the code changes."""
    from leadgen.agent import build_agent

    setup = resolve_llm(settings("mistral"), {"MISTRAL_API_KEY": "test-key-not-real"})
    agent = build_agent(rulebook, setup.model)
    assert agent.model is setup.model and len(agent.tools) == 8


def test_only_llm_py_imports_provider_classes() -> None:
    forbidden = ("litellm", "OpenAIChatCompletionsModel", "AsyncOpenAI", "anthropic", "ollama")
    for path in (ROOT / "src" / "leadgen").glob("*.py"):
        if path.name == "llm.py":
            continue
        imports = [
            line for line in path.read_text().splitlines()
            if line.lstrip().startswith(("import ", "from "))
        ]  # fmt: skip
        for line in imports:
            assert not any(word in line for word in forbidden), f"{path.name}: {line}"


def test_every_provider_is_documented() -> None:
    guide = (ROOT / "MODEL_SWITCH.md").read_text()
    env_file = (ROOT / "example.env").read_text()
    for name, spec in PROVIDERS.items():
        assert f"LLM_PROVIDER={name}" in guide, f"{name} missing from MODEL_SWITCH.md"
        for variable in (spec.key_env, spec.base_url_env):
            if variable:
                assert variable in guide, f"{variable} missing from MODEL_SWITCH.md"
                assert variable in env_file, f"{variable} missing from example.env"
