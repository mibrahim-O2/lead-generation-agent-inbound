"""Runs the 20 eval cases against the mock model."""

from __future__ import annotations

import asyncio

import pytest

from leadgen.evals import EvalCase, load_cases, run_case
from leadgen.llm import resolve_llm

CASES = load_cases()


def test_there_are_twenty_well_formed_cases() -> None:
    assert len(CASES) == 20
    assert len({case.id for case in CASES}) == 20
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
