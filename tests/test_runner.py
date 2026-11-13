from __future__ import annotations

import asyncio
import json

import pytest

from leadgen.config import Settings
from leadgen.models import Lead
from leadgen.runner import SourceError, load_leads, run_leads
from leadgen.storage import LocalStorage, MemoryStorage


def go(leads, settings, rulebook, storage, **kwargs):
    return asyncio.run(
        run_leads(leads, settings=settings, rulebook=rulebook, storage=storage, **kwargs)
    )


def test_sample_run_end_to_end(settings, rulebook, tmp_path) -> None:
    storage = LocalStorage(tmp_path / "data")
    leads = load_leads("sample", storage)
    outcome = go(leads, settings, rulebook, storage)
    run = outcome.run
    assert (run.leads_received, run.leads_processed, run.errors) == (5, 5, [])
    assert {r.lead.id: r.route for r in outcome.records} == {
        "S001": "draft_reply", "S002": "draft_reply", "S003": "draft_reply",
        "S004": "handover", "S005": "nurture",
    }  # fmt: skip
    assert (run.drafts_created, run.handovers, run.nurture, run.hot_leads) == (4, 1, 1, 2)
    assert run.total_tokens == run.input_tokens + run.output_tokens > 0
    assert run.cost_estimate_usd is not None and run.cost_estimate_usd > 0
    assert (run.provider, run.dry_run) == ("mock", False)
    assert len(storage.list_records()) == 5 and storage.list_runs()[0].id == run.id
    assert all(r.run_id == run.id for r in storage.list_records())


def test_dry_run_writes_nothing(settings, rulebook, tmp_path) -> None:
    data_dir = tmp_path / "data"
    storage = LocalStorage(data_dir)
    outcome = go(load_leads("sample", storage), settings, rulebook, storage, dry_run=True)
    assert outcome.run.dry_run and outcome.run.leads_processed == 5
    assert outcome.run.drafts_created == 4  # the full agent still ran
    assert not data_dir.exists()


def test_rerunning_the_same_leads_updates_instead_of_duplicating(settings, rulebook) -> None:
    storage = MemoryStorage()
    leads = load_leads("sample", storage)
    go(leads, settings, rulebook, storage)
    second = go(leads, settings, rulebook, storage)
    assert len(storage.list_records()) == 5
    assert not any("duplicate" in r.flags for r in second.records)


def test_limit_and_max_leads_per_run(settings, rulebook) -> None:
    leads = load_leads("sample", MemoryStorage())
    limited = go(leads, settings, rulebook, MemoryStorage(), limit=2)
    assert limited.run.leads_processed == 2 and "Lead limit" in limited.run.stopped_reason

    capped_settings = Settings(mock_llm=True, max_leads_per_run=3)
    capped = go(leads, capped_settings, rulebook, MemoryStorage(), limit=50)
    assert capped.run.leads_processed == 3  # --limit cannot exceed the safety cap


def test_token_limit_stops_the_run(rulebook) -> None:
    settings = Settings(mock_llm=True, max_tokens_per_run=100)
    outcome = go(load_leads("sample", MemoryStorage()), settings, rulebook, MemoryStorage())
    assert outcome.run.leads_processed == 1
    assert "Token limit" in outcome.run.stopped_reason


def test_duplicate_within_one_run(settings, rulebook) -> None:
    leads = [
        Lead(id="A", email="same@example.com", message="Solar for my house in Lahore"),
        Lead(id="B", email="same@example.com", message="Any update on my solar enquiry?"),
    ]
    outcome = go(leads, settings, rulebook, MemoryStorage(), dry_run=True)
    first, second = outcome.records
    assert first.route == "draft_reply"
    assert second.route == "handover" and second.duplicate_of == "A"


def test_load_leads_from_files(tmp_path) -> None:
    csv_file = tmp_path / "leads.csv"
    csv_file.write_text('name,email,message\nA,a@example.com,"Hello, solar"\n')
    [lead] = load_leads("file", MemoryStorage(), str(csv_file))
    assert lead.message == "Hello, solar" and lead.id.startswith("L-") and lead.received_at

    json_file = tmp_path / "leads.json"
    json_file.write_text(json.dumps([{"id": "J1", "message": "hi"}, {"message": "there"}]))
    assert [lead.id for lead in load_leads("file", MemoryStorage(), str(json_file))][0] == "J1"


def test_load_leads_errors_and_webhook(tmp_path) -> None:
    with pytest.raises(SourceError, match="--file"):
        load_leads("file", MemoryStorage())
    with pytest.raises(SourceError, match="not found"):
        load_leads("file", MemoryStorage(), str(tmp_path / "missing.csv"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(SourceError, match="Could not read"):
        load_leads("file", MemoryStorage(), str(bad))

    storage = MemoryStorage()
    storage.enqueue_lead(Lead(id="W1", message="queued"))
    assert [lead.id for lead in load_leads("webhook", storage)] == ["W1"]
