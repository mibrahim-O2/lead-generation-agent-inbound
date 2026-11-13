from __future__ import annotations

import json

import pytest

from leadgen.cli import main, parse_args


def test_flags_parse() -> None:
    args = parse_args(["--source", "file", "--file", "x.csv", "--limit", "3", "--dry-run"])
    assert (args.source, args.file, args.limit, args.dry_run) == ("file", "x.csv", 3, True)
    assert parse_args([]).source == "sample"


@pytest.mark.parametrize(
    "argv",
    [["--source", "file"], ["--file", "x.csv"], ["--limit", "0"], ["--source", "email"]],
)
def test_bad_flags_are_rejected(argv, capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        parse_args(argv)
    assert exit_info.value.code == 2
    assert "error" in capsys.readouterr().err


def test_dry_run_prints_everything_and_writes_nothing(capsys, tmp_path) -> None:
    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "[S001]" in out and "(HOT)" in out and "route: handover" in out
    assert "DRAFT (not sent - waiting for human approval)" in out
    assert "DRY RUN: nothing was written and nothing was sent." in out
    assert not (tmp_path / "data").exists()


def test_real_run_saves_drafts_but_sends_nothing(capsys, tmp_path) -> None:
    assert main(["--limit", "2"]) == 0
    out = capsys.readouterr().out
    assert "Nothing was sent" in out and "Leads processed: 2 of 5" in out
    saved = json.loads((tmp_path / "data" / "leads.json").read_text())
    assert [row["lead"]["id"] for row in saved] == ["S001", "S002"]
    assert all(row["status"] == "pending_approval" for row in saved)
    assert len(json.loads((tmp_path / "data" / "runs.json").read_text())) == 1


def test_file_source(capsys, tmp_path) -> None:
    leads = tmp_path / "in.json"
    leads.write_text(json.dumps([{"name": "F", "email": "f@example.com", "message": "SEO offer"}]))
    assert main(["--source", "file", "--file", str(leads), "--dry-run"]) == 0
    assert "route: spam" in capsys.readouterr().out


def test_webhook_source_with_empty_queue(capsys) -> None:
    assert main(["--source", "webhook"]) == 0
    assert "No new leads" in capsys.readouterr().out


def test_missing_key_is_a_clear_error(monkeypatch, capsys) -> None:
    monkeypatch.setenv("LEADGEN_MOCK_LLM", "0")
    assert main(["--dry-run"]) == 2
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_missing_file_is_a_clear_error(capsys) -> None:
    assert main(["--source", "file", "--file", "nope.csv"]) == 2
    assert "not found" in capsys.readouterr().err
