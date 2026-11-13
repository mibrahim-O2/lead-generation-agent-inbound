"""Storage interface with a local JSON/CSV backend.

Everything else talks to the `Storage` interface, so a Google Sheets or Gmail
backend can be added later without touching the agent. `MemoryStorage` is used
for dry runs: it can read what is already stored but never writes to disk.
"""

from __future__ import annotations

import csv
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from leadgen.models import Lead, LeadRecord, RunRecord


def normalise_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("92") and len(digits) > 10:
        digits = "0" + digits[2:]
    return digits


def same_contact(a: Lead, b: Lead) -> bool:
    """Two leads are the same person when the email or the phone number matches."""
    email_a, email_b = a.email.strip().lower(), b.email.strip().lower()
    if email_a and email_a == email_b:
        return True
    phone_a, phone_b = normalise_phone(a.phone), normalise_phone(b.phone)
    return bool(phone_a) and len(phone_a) >= 7 and phone_a == phone_b


class Storage(ABC):
    """What the agent, runner and API need from a storage backend."""

    @abstractmethod
    def enqueue_lead(self, lead: Lead) -> None:
        """Add a new enquiry to the inbox (not processed yet)."""

    @abstractmethod
    def list_inbox(self) -> list[Lead]:
        """Every enquiry ever queued."""

    @abstractmethod
    def save_record(self, record: LeadRecord) -> None:
        """Insert or replace the processed record for record.lead.id."""

    @abstractmethod
    def list_records(self) -> list[LeadRecord]:
        """All processed leads, oldest first."""

    @abstractmethod
    def save_run(self, run: RunRecord) -> None:
        """Append one run to the run history."""

    @abstractmethod
    def list_runs(self) -> list[RunRecord]:
        """Run history, oldest first."""

    # Shared behaviour built on the methods above.

    def pending_leads(self) -> list[Lead]:
        """Queued enquiries that have not been processed yet."""
        done = {record.lead.id for record in self.list_records()}
        return [lead for lead in self.list_inbox() if lead.id not in done]

    def find_duplicate(self, lead: Lead) -> LeadRecord | None:
        """An earlier record from the same person (different lead id), if any."""
        for record in self.list_records():
            if record.lead.id != lead.id and same_contact(record.lead, lead):
                return record
        return None


class MemoryStorage(Storage):
    """Keeps everything in memory. Optionally starts from another storage's contents."""

    def __init__(self, seed: Storage | None = None) -> None:
        self._inbox: list[Lead] = list(seed.list_inbox()) if seed else []
        self._records: dict[str, LeadRecord] = (
            {r.lead.id: r for r in seed.list_records()} if seed else {}
        )
        self._runs: list[RunRecord] = list(seed.list_runs()) if seed else []

    def enqueue_lead(self, lead: Lead) -> None:
        self._inbox.append(lead)

    def list_inbox(self) -> list[Lead]:
        return list(self._inbox)

    def save_record(self, record: LeadRecord) -> None:
        self._records[record.lead.id] = record

    def list_records(self) -> list[LeadRecord]:
        return list(self._records.values())

    def save_run(self, run: RunRecord) -> None:
        self._runs.append(run)

    def list_runs(self) -> list[RunRecord]:
        return list(self._runs)


CSV_COLUMNS = [
    "id", "received_at", "name", "email", "phone", "channel", "intent", "score", "is_hot",
    "route", "status", "handover_reason", "duplicate_of", "flags", "draft_reply", "processed_at",
]  # fmt: skip


class LocalStorage(Storage):
    """JSON files under a data directory, plus a leads.csv export for spreadsheets."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)

    def _read(self, name: str) -> list[dict[str, Any]]:
        path = self.data_dir / name
        if not path.is_file():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, name: str, rows: list[dict[str, Any]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # atomic: a crash never leaves a half-written file

    def enqueue_lead(self, lead: Lead) -> None:
        self._write("inbox.json", [*self._read("inbox.json"), lead.model_dump()])

    def list_inbox(self) -> list[Lead]:
        return [Lead.model_validate(row) for row in self._read("inbox.json")]

    def save_record(self, record: LeadRecord) -> None:
        rows = [r for r in self._read("leads.json") if r["lead"]["id"] != record.lead.id]
        rows.append(record.model_dump())
        self._write("leads.json", rows)
        self._export_csv(rows)

    def list_records(self) -> list[LeadRecord]:
        return [LeadRecord.model_validate(row) for row in self._read("leads.json")]

    def save_run(self, run: RunRecord) -> None:
        self._write("runs.json", [*self._read("runs.json"), run.model_dump()])

    def list_runs(self) -> list[RunRecord]:
        return [RunRecord.model_validate(row) for row in self._read("runs.json")]

    def _export_csv(self, rows: list[dict[str, Any]]) -> None:
        with (self.data_dir / "leads.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                flat = {**row, **row["lead"], "flags": "; ".join(row.get("flags", []))}
                writer.writerow(flat)
