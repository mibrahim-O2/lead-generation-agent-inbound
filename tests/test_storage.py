from __future__ import annotations

import csv

from leadgen.models import Lead, LeadRecord, RunRecord
from leadgen.storage import LocalStorage, MemoryStorage, normalise_phone, same_contact


def record(lead_id: str, email: str = "", phone: str = "", **extra) -> LeadRecord:
    return LeadRecord(lead=Lead(id=lead_id, email=email, phone=phone, message="hi"), **extra)


def test_local_storage_round_trip(tmp_path) -> None:
    store = LocalStorage(tmp_path / "data")
    assert store.list_records() == [] and store.list_runs() == [] and store.list_inbox() == []

    store.save_record(record("A", email="a@example.com", score=8, draft_reply="Hi, A"))
    store.save_record(record("B", email="b@example.com"))
    store.save_record(record("A", email="a@example.com", score=9))  # same id replaces
    store.save_run(RunRecord(id="run-1", started_at="2026-01-01T00:00:00+00:00"))

    reopened = LocalStorage(tmp_path / "data")
    records = {r.lead.id: r for r in reopened.list_records()}
    assert set(records) == {"A", "B"} and records["A"].score == 9
    assert [run.id for run in reopened.list_runs()] == ["run-1"]
    assert not list((tmp_path / "data").glob("*.tmp"))


def test_csv_export_matches_the_records(tmp_path) -> None:
    store = LocalStorage(tmp_path)
    store.save_record(record("A", email="a@example.com", route="draft_reply", flags=["x", "y"]))
    with (tmp_path / "leads.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert (rows[0]["id"], rows[0]["email"], rows[0]["route"]) == (
        "A",
        "a@example.com",
        "draft_reply",
    )
    assert rows[0]["flags"] == "x; y"


def test_inbox_and_pending(tmp_path) -> None:
    store = LocalStorage(tmp_path)
    store.enqueue_lead(Lead(id="Q1", message="one"))
    store.enqueue_lead(Lead(id="Q2", message="two"))
    assert [lead.id for lead in store.pending_leads()] == ["Q1", "Q2"]
    store.save_record(record("Q1"))
    assert [lead.id for lead in store.pending_leads()] == ["Q2"]


def test_duplicate_detection() -> None:
    store = MemoryStorage()
    store.save_record(record("OLD", email="Same@Example.com", phone="+92 300 1234567"))
    assert store.find_duplicate(Lead(id="N1", email="same@example.com")).lead.id == "OLD"
    assert store.find_duplicate(Lead(id="N2", phone="0300-1234567")).lead.id == "OLD"
    assert store.find_duplicate(Lead(id="N3", email="other@example.com", phone="0300")) is None
    assert store.find_duplicate(Lead(id="N4")) is None  # no contact details: never a match
    assert store.find_duplicate(Lead(id="OLD", email="same@example.com")) is None  # itself


def test_contact_helpers() -> None:
    assert normalise_phone("+92 (300) 123-4567") == "03001234567"
    assert not same_contact(Lead(), Lead())


def test_memory_storage_seeded_from_disk_never_writes_back(tmp_path) -> None:
    disk = LocalStorage(tmp_path)
    disk.save_record(record("A", email="a@example.com"))
    before = (tmp_path / "leads.json").read_text()

    memory = MemoryStorage(seed=disk)
    memory.save_record(record("B", email="b@example.com"))
    memory.save_run(RunRecord(id="r", started_at="x"))
    memory.enqueue_lead(Lead(id="Q", message="m"))

    assert {r.lead.id for r in memory.list_records()} == {"A", "B"}
    assert (tmp_path / "leads.json").read_text() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["leads.csv", "leads.json"]
