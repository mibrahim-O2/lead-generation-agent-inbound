"""Regenerate dashboard/src/demo-data.json from the mock model.

    make dashboard-demo-data

Runs the sample leads and a few eval leads through the real agent loop with the
mock model (no key, no network) and writes the result as the dashboard's bundled
demo data. Timestamps and run ids are fixed so the file only changes when the
agent's behaviour does. Everything in it is fictional.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from leadgen.config import Settings, load_rulebook, project_root
from leadgen.evals import load_cases
from leadgen.models import Lead, RunRecord
from leadgen.runner import load_leads, run_leads
from leadgen.storage import MemoryStorage

EXTRA_CASES = ["04_factory", "07_spam", "08_prompt_injection", "13_missing_contact",
               "15_nurture", "18_office_survey", "19_angry"]  # fmt: skip
ZONE = timezone(timedelta(hours=5))
DAY_ONE = datetime(2026, 1, 5, 9, 30, tzinfo=ZONE)
OUTPUT = project_root() / "dashboard" / "src" / "demo-data.json"


def stamp(when: datetime) -> str:
    return when.isoformat(timespec="seconds")


async def build() -> dict:
    settings = Settings(mock_llm=True)
    rulebook = load_rulebook(settings.preset, settings.client_config)
    storage = MemoryStorage()

    sample = load_leads("sample", storage)
    cases = {case.id: case.lead for case in load_cases()}
    extra = [
        cases[case_id].model_copy(
            update={
                "id": f"D{index:03d}",
                "name": f"Demo Lead {index + 5}",
                "received_at": stamp(DAY_ONE + timedelta(days=2, minutes=37 * index)),
            }
        )  # fmt: skip
        for index, case_id in enumerate(EXTRA_CASES, start=1)
    ]
    extra = [
        lead.model_copy(
            update={
                "email": lead.email and f"demo.lead{index + 5}@example.com",
                "phone": lead.phone and f"0300-00000{index + 5:02d}",
            }
        )  # fmt: skip
        for index, lead in enumerate(extra, start=1)
    ]

    runs: list[RunRecord] = []
    for number, batch in enumerate([sample, extra], start=1):
        outcome = await run_leads(
            batch, settings=settings, rulebook=rulebook, storage=storage, source="sample"
        )
        newest = max(datetime.fromisoformat(lead.received_at) for lead in batch)
        started = newest + timedelta(minutes=20)
        run = outcome.run.model_copy(
            update={"id": f"run-demo-{number}", "started_at": stamp(started),
                    "finished_at": stamp(started + timedelta(seconds=40))}
        )  # fmt: skip
        runs.append(run)
        for offset, record in enumerate(outcome.records):
            fixed = record.model_copy(
                update={"run_id": run.id,
                        "processed_at": stamp(started + timedelta(seconds=8 * offset))}
            )  # fmt: skip
            storage.save_record(fixed)

    pending = Lead(
        id="D900", name="Demo Lead 13", email="demo.lead13@example.com", phone="0300-0000013",
        channel="webhook", received_at=stamp(DAY_ONE + timedelta(days=2, hours=6)),
        message="Need solar for our shop in Johar Town.",
    )  # fmt: skip
    return {
        "leads": [record.model_dump() for record in storage.list_records()],
        "pending": [pending.model_dump()],
        "runs": [run.model_dump() for run in runs],
    }


def main() -> None:
    data = asyncio.run(build())
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['leads'])} leads and {len(data['runs'])} runs to {Path(OUTPUT)}")


if __name__ == "__main__":
    main()
