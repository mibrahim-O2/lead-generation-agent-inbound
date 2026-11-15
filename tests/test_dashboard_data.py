"""The dashboard's bundled demo data must stay in step with the Python models."""

from __future__ import annotations

import json
import re
from pathlib import Path

from leadgen.models import Lead, LeadRecord, RunRecord

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
DATA = json.loads((DASHBOARD / "src" / "demo-data.json").read_text(encoding="utf-8"))


def test_demo_data_matches_the_record_models() -> None:
    records = [LeadRecord.model_validate(item) for item in DATA["leads"]]
    runs = [RunRecord.model_validate(item) for item in DATA["runs"]]
    pending = [Lead.model_validate(item) for item in DATA["pending"]]
    assert len(records) >= 10 and len(runs) >= 2 and pending
    # every field the Python model has is present, so the TypeScript types can rely on it
    for item in DATA["leads"]:
        assert set(item) == set(LeadRecord.model_fields)
    assert {record.run_id for record in records} == {run.id for run in runs}


def test_demo_data_is_fictional_and_safe() -> None:
    text = json.dumps(DATA)
    for address in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
        assert address.endswith("@example.com") or address.endswith("example.com"), address
    assert "Example Solar Co" in text
    for record in DATA["leads"]:
        assert record["status"] not in ("approved", "rejected")  # nothing pre-approved
        if record["route"] in ("handover", "spam"):
            assert record["draft_reply"] == ""
    assert {record["route"] for record in DATA["leads"]} == {
        "draft_reply", "handover", "nurture", "spam",
    }  # fmt: skip


def test_typescript_types_list_every_record_field() -> None:
    types = (DASHBOARD / "src" / "types.ts").read_text(encoding="utf-8")
    for name in [*LeadRecord.model_fields, *RunRecord.model_fields, *Lead.model_fields]:
        assert re.search(rf"\b{name}\??:", types), f"{name} missing from dashboard/src/types.ts"


def test_front_end_has_no_secrets_or_hardcoded_api() -> None:
    for path in (DASHBOARD / "src").glob("*.ts*"):
        source = path.read_text(encoding="utf-8")
        assert "API_KEY" not in source and "sk-" not in source, path.name
        assert "dangerouslySetInnerHTML" not in source, path.name  # lead text is shown as text
    data_layer = (DASHBOARD / "src" / "data.ts").read_text(encoding="utf-8")
    assert "import.meta.env.VITE_API_URL" in data_layer
    assert "localhost" not in data_layer and "127.0.0.1" not in data_layer
