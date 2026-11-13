"""Runs the 20 eval cases against the mock model."""

from __future__ import annotations

import asyncio

import pytest

from leadgen import evals
from leadgen.evals import EvalCase, load_cases, run_case
from leadgen.llm import resolve_llm

CASES = load_cases()


def test_cases_are_well_formed() -> None:
    assert len(CASES) >= 28
    assert len({case.id for case in CASES}) == len(CASES)
    for case in CASES:
        expected = case.expected
        assert expected["route"] in ("draft_reply", "handover", "nurture", "spam"), case.id
        assert 1 <= expected["score_min"] <= expected["score_max"] <= 10, case.id
        assert not case.lead.email or case.lead.email.endswith("@example.com"), case.id
    assert {case.expected["route"] for case in CASES} == {
        "draft_reply", "handover", "nurture", "spam",
    }  # fmt: skip


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_eval_case(case: EvalCase, settings, rulebook) -> None:
    result = asyncio.run(run_case(case, settings, rulebook, resolve_llm(settings)))
    assert result.passed, result.failures


# --------------------------------------------------------------------------- runner and live mode


def test_sample_leads_are_eval_cases_and_s003_must_be_hot() -> None:
    by_id = {case.id: case for case in CASES}
    samples = [case for case in CASES if "_sample_s00" in case.id]
    assert len(samples) == 5
    assert by_id["23_sample_s003_factory_load"].expected["score_min"] >= 7


def test_caps_stop_the_run_and_report_what_was_skipped(settings) -> None:
    by_leads = asyncio.run(evals.run_all(settings, max_leads=3))
    assert len(by_leads.results) == 3 and "lead cap" in by_leads.stopped_reason
    assert len(by_leads.skipped) == len(CASES) - 3 and not by_leads.ok

    by_tokens = asyncio.run(evals.run_all(settings, max_tokens=1))
    assert len(by_tokens.results) == 1 and "token cap" in by_tokens.stopped_reason

    filtered = asyncio.run(evals.run_all(settings, name_filter="sample_s00"))
    assert len(filtered.results) == 5 and filtered.ok and filtered.tokens > 0


def test_seed_leads_count_towards_the_lead_cap(settings) -> None:
    report = asyncio.run(evals.run_all(settings, name_filter="10_duplicate", max_leads=1))
    assert report.results == [] and report.skipped == ["10_duplicate"]


def test_default_run_is_always_the_mock_even_with_a_key(monkeypatch, capsys) -> None:
    monkeypatch.setenv("LEADGEN_MOCK_LLM", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    assert evals.main(["--filter", "sample_s001"]) == 0
    out = capsys.readouterr().out
    assert "mock model" in out and "1/1 cases passed" in out and "total tokens" in out


def test_live_mode_refuses_to_run_in_ci(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    assert evals.main(["--live"]) == 2
    assert "never run in CI" in capsys.readouterr().err


def test_live_mode_needs_a_key_and_ignores_the_mock_flag(monkeypatch, capsys) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("LEADGEN_MOCK_LLM", "1")  # --live must not silently fall back to the mock
    assert evals.main(["--live"]) == 2
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_live_caps_cannot_exceed_the_hard_limits(monkeypatch, capsys) -> None:
    monkeypatch.delenv("CI", raising=False)
    seen = {}

    async def fake_run_all(settings, **kwargs):
        seen.update(kwargs, mock=settings.mock_llm)
        return evals.EvalReport(results=[])

    monkeypatch.setattr(evals, "run_all", fake_run_all)
    assert evals.main(["--live", "--max-leads", "9999", "--max-tokens", "99999999"]) == 0
    assert seen["max_leads"] == evals.LIVE_HARD_MAX_LEADS
    assert seen["max_tokens"] == evals.LIVE_HARD_MAX_TOKENS
    assert seen["mock"] is False
    assert "Live evals: real API calls" in capsys.readouterr().out
