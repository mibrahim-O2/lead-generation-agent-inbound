from __future__ import annotations

import pytest

from leadgen.config import DEFAULTS, ConfigError, Settings, deep_merge, load_rulebook


def test_deep_merge_dicts_merge_and_plain_lists_replace() -> None:
    base = {"a": {"x": 1, "y": 2}, "items": [1, 2], "keep": True}
    merged = deep_merge(base, {"a": {"y": 3}, "items": [9]})
    assert merged == {"a": {"x": 1, "y": 3}, "items": [9], "keep": True}
    assert base["a"]["y"] == 2  # the input is not modified


def test_deep_merge_id_lists_merge_by_id() -> None:
    base = [{"id": "a", "patterns": ["1"]}, {"id": "b", "patterns": ["2"]}]
    merged = deep_merge(base, [{"id": "b", "patterns": ["new"]}, {"id": "c", "patterns": ["3"]}])
    assert [rule["id"] for rule in merged] == ["a", "b", "c"]
    assert merged[1]["patterns"] == ["new"]


def test_layers_resolve_defaults_then_preset_then_client(rulebook) -> None:
    # defaults: built-in safety rules survive
    claim_ids = {rule.id for rule in rulebook.forbidden_claims}
    assert {rule["id"] for rule in DEFAULTS["forbidden_claims"]} <= claim_ids
    # preset: adds niche rules and the rubric
    assert "net_metering_approval" in claim_ids
    assert rulebook.niche == "solar"
    assert rulebook.scoring.hot_threshold == 7
    # client: overrides company details and the sign-off only
    assert rulebook.company.name == "Example Solar Co"
    assert rulebook.tone.sign_off == "Example Solar Co Customer Care"
    assert "Roman Urdu" in rulebook.tone.style  # still from the preset


def test_preset_only_when_client_file_is_missing() -> None:
    book = load_rulebook("solar", "config/does-not-exist.yaml")
    assert book.company.name == "Example Co"  # the built-in default
    assert book.tone.sign_off == "Customer Care Team"  # the preset value


def test_client_file_changes_behaviour_without_code(tmp_path) -> None:
    client = tmp_path / "client.yaml"
    client.write_text("company: {name: Other Co}\nscoring: {hot_threshold: 9}\n")
    book = load_rulebook("solar", client)
    assert (book.company.name, book.scoring.hot_threshold) == ("Other Co", 9)
    assert book.scoring.rubric.property_type["factory"] == 3  # rest of the rubric kept


def test_unknown_preset_and_bad_yaml_raise(tmp_path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_rulebook("nope")
    bad = tmp_path / "bad.yaml"
    bad.write_text("scoring: {hot_threshold: not-a-number}\n")
    with pytest.raises(ConfigError, match="Invalid rule book"):
        load_rulebook("solar", bad)


def test_settings_defaults_and_overrides() -> None:
    defaults = Settings.from_env({})
    assert (defaults.llm_provider, defaults.mock_llm) == ("openai", False)
    assert (defaults.max_leads_per_run, defaults.max_tool_calls_per_lead) == (25, 12)
    assert defaults.max_tokens_per_run == 200_000
    assert defaults.cors_origins == ("http://localhost:5173",)
    custom = Settings.from_env(
        {"LEADGEN_MOCK_LLM": "true", "MAX_LEADS_PER_RUN": "3", "CORS_ORIGINS": "http://a, http://b"}
    )
    assert (custom.mock_llm, custom.max_leads_per_run) == (True, 3)
    assert custom.cors_origins == ("http://a", "http://b")


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_settings_reject_bad_limits(value: str) -> None:
    with pytest.raises(ConfigError, match="MAX_TOKENS_PER_RUN"):
        Settings.from_env({"MAX_TOKENS_PER_RUN": value})
