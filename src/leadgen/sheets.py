"""Optional Google Sheets support: a live "Leads" tab and an "Inbox" tab.

Nothing here is needed for the default install. It is used only when
SHEETS_ENABLED=1, and never in a dry run. The Google library (gspread) is an
optional extra: pip install -e ".[sheets]".

Layout:
- `SheetsClient` is the small set of operations this project needs from a
  spreadsheet. `GspreadClient` is the real one; tests use a fake.
- `LeadsSheet` appends one row per finished lead to the Leads tab.
- `InboxSheet` reads new enquiries typed into the Inbox tab and marks them done.
- `SheetMirrorStorage` wraps the normal storage: everything is still saved
  locally first, then mirrored to the sheet. A Google failure never loses a lead.

Everything written to the sheet is written as plain text (RAW), so a lead
message starting with "=" can never run as a formula.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Protocol

from leadgen.config import ConfigError, Settings, project_root
from leadgen.models import Lead, LeadRecord, RunRecord, now_iso
from leadgen.storage import LocalStorage, Storage

logger = logging.getLogger("leadgen")

LEADS_HEADER = [
    "Received At", "Lead ID", "Name", "Channel", "Message", "Intent", "Score", "Hot",
    "Route", "Status", "Missing Info", "Handover Reason", "Draft Reply", "Run ID",
]  # fmt: skip
INBOX_HEADER = ["Received At", "Name", "Email", "Phone", "Message", "Processed"]
STATUS_COLUMN = LEADS_HEADER.index("Status") + 1  # 1-based
PROCESSED_COLUMN = INBOX_HEADER.index("Processed") + 1
# What a human may pick in the Status dropdown. "discarded" is what spam gets.
STATUS_OPTIONS = ["pending_approval", "approved", "rejected", "needs_human", "nurture", "discarded"]
DROPDOWN_ROWS = 1000
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"  # Sheets only; no Drive access
MAX_CONSECUTIVE_FAILURES = 3


class SheetsError(Exception):
    """Google Sheets could not be used. The message says what to fix."""


class SheetsClient(Protocol):
    """The spreadsheet operations this project uses."""

    def read(self, tab: str) -> list[list[str]]:
        """All rows of a tab as text, including the header row."""

    def append(self, tab: str, row: list[str]) -> None:
        """Add one row after the last row with data."""

    def set_cell(self, tab: str, row: int, column: int, value: str) -> None:
        """Write one cell (1-based row and column)."""

    def freeze_header(self, tab: str) -> None:
        """Keep the first row visible while scrolling."""

    def add_dropdown(self, tab: str, cell_range: str, options: list[str]) -> None:
        """Add a dropdown list to a range such as J2:J1000."""


# ----------------------------------------------------------------------------- real client


class GspreadClient:
    """Talks to Google Sheets through gspread with a service account.

    Connects on first use. Every failure is turned into a SheetsError that names
    the setting or step to fix. The key file's contents are never logged.
    """

    def __init__(self, sheet_id: str, key_file: str | Path) -> None:
        self.sheet_id = sheet_id
        self.key_file = Path(key_file)
        self._spreadsheet: Any = None
        self._tabs: dict[str, Any] = {}

    def _service_account_email(self) -> str:
        try:
            return json.loads(self.key_file.read_text(encoding="utf-8")).get("client_email", "")
        except (OSError, ValueError):
            return ""

    def _explain(self, exc: Exception, doing: str) -> SheetsError:
        """Turn a library error into one sentence a beginner can act on."""
        email = self._service_account_email() or "the service account email (client_email)"
        text = str(exc)
        code = getattr(exc, "code", None)
        if isinstance(exc, PermissionError) or code == 403 and "permission" in text.lower():
            fix = f"Share the sheet with {email} as Editor."
        elif type(exc).__name__ == "SpreadsheetNotFound" or code == 404:
            fix = (
                "GOOGLE_SHEET_ID is wrong: copy the id from the sheet's URL "
                "(between /d/ and /edit)."
            )
        elif code == 403:
            fix = "Enable the Google Sheets API for the project that owns the service account."
        elif code == 429:
            fix = "Google's request quota was hit. Wait a minute and try again."
        elif code in (400, 401) or "invalid_grant" in text or "JWT" in text:
            fix = (
                "The service account key was rejected. Create a new JSON key and replace the file."
            )
        else:
            fix = "Check your internet connection and the Google Sheets settings in .env."
        return SheetsError(f"Google Sheets failed while {doing} ({type(exc).__name__}). {fix}")

    def _open(self) -> Any:
        if self._spreadsheet is not None:
            return self._spreadsheet
        try:
            import gspread
        except ImportError as exc:
            raise SheetsError(
                'Google Sheets support is not installed. Run: pip install -e ".[sheets]"'
            ) from exc
        if not self.key_file.is_file():
            raise SheetsError(
                f"Service account key not found at {self.key_file}. Put the JSON key there "
                "or set GOOGLE_SERVICE_ACCOUNT_FILE to its path."
            )
        try:
            client = gspread.service_account(filename=str(self.key_file), scopes=[SHEETS_SCOPE])
            self._spreadsheet = client.open_by_key(self.sheet_id)
        except ValueError as exc:  # the file is not a valid service account key
            raise SheetsError(
                f"{self.key_file} is not a valid service account JSON key. Download a new "
                "key from Google Cloud and replace the file."
            ) from exc
        except Exception as exc:  # noqa: BLE001 - every Google/network error gets a clear message
            raise self._explain(exc, "opening the sheet") from exc
        return self._spreadsheet

    def _tab(self, tab: str) -> Any:
        if tab not in self._tabs:
            spreadsheet = self._open()
            try:
                self._tabs[tab] = spreadsheet.worksheet(tab)
            except Exception as exc:  # noqa: BLE001
                if type(exc).__name__ == "WorksheetNotFound":
                    raise SheetsError(
                        f'The sheet has no tab named "{tab}". Create it, or set SHEET_LEADS_TAB / '
                        "SHEET_INBOX_TAB to the tab's exact name."
                    ) from exc
                raise self._explain(exc, f'opening the "{tab}" tab') from exc
        return self._tabs[tab]

    def _call(self, tab: str, doing: str, method: str, *args: Any, **kwargs: Any) -> Any:
        worksheet = self._tab(tab)
        try:
            return getattr(worksheet, method)(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise self._explain(exc, doing) from exc

    def read(self, tab: str) -> list[list[str]]:
        rows = self._call(tab, f'reading the "{tab}" tab', "get_all_values")
        return [[str(cell) for cell in row] for row in rows]

    def append(self, tab: str, row: list[str]) -> None:
        # RAW: values are stored as typed, never parsed as formulas.
        self._call(tab, f'adding a row to "{tab}"', "append_row", row, value_input_option="RAW")

    def set_cell(self, tab: str, row: int, column: int, value: str) -> None:
        self._call(tab, f'updating "{tab}"', "update_cell", row, column, value)

    def freeze_header(self, tab: str) -> None:
        self._call(tab, f'freezing the header of "{tab}"', "freeze", rows=1)

    def add_dropdown(self, tab: str, cell_range: str, options: list[str]) -> None:
        from gspread.utils import ValidationConditionType

        self._call(
            tab,
            f'adding the Status dropdown to "{tab}"',
            "add_validation",
            cell_range,
            ValidationConditionType.one_of_list,
            options,
            strict=False,
            showCustomUi=True,
        )


# ----------------------------------------------------------------------------- Leads tab


def column_letter(column: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def lead_row(record: LeadRecord) -> list[str]:
    """One Leads-tab row, in LEADS_HEADER order. Everything is text."""
    lead = record.lead
    return [
        lead.received_at,
        lead.id,
        lead.name,
        lead.channel,
        lead.message,
        record.intent,
        str(record.score),
        "yes" if record.is_hot else "no",
        record.route,
        record.status,
        ", ".join(record.missing_info),
        record.handover_reason,
        record.draft_reply,
        record.run_id,
    ]


class LeadsSheet:
    """Appends one row per finished lead to the Leads tab."""

    def __init__(self, client: SheetsClient, tab: str = "Leads") -> None:
        self.client = client
        self.tab = tab
        self._ready = False

    def ensure_header(self) -> None:
        """On an empty tab: write the header, freeze it and add the Status dropdown."""
        if self._ready:
            return
        if not any(any(cell.strip() for cell in row) for row in self.client.read(self.tab)):
            self.client.append(self.tab, list(LEADS_HEADER))
            self.client.freeze_header(self.tab)
            letter = column_letter(STATUS_COLUMN)
            self.client.add_dropdown(
                self.tab, f"{letter}2:{letter}{DROPDOWN_ROWS}", list(STATUS_OPTIONS)
            )
        self._ready = True

    def append_record(self, record: LeadRecord) -> None:
        self.ensure_header()
        self.client.append(self.tab, lead_row(record))


# ----------------------------------------------------------------------------- Inbox tab


class InboxSheet:
    """Reads enquiries typed into the Inbox tab and marks each one once processed."""

    def __init__(self, client: SheetsClient, tab: str = "Inbox") -> None:
        self.client = client
        self.tab = tab
        self._rows: dict[str, int] = {}  # lead id -> sheet row number

    def pending(self) -> list[Lead]:
        """Rows that have a message and an empty "Processed" cell."""
        rows = self.client.read(self.tab)
        if not any(any(cell.strip() for cell in row) for row in rows):
            self.client.append(self.tab, list(INBOX_HEADER))
            return []
        # Row 1 is skipped only when it really is a header. If someone typed an
        # enquiry into row 1 of a tab without a header, it must not be lost.
        first = {cell.strip().lower() for cell in rows[0]}
        start = 2 if first & {"message", "received at", "processed"} else 1
        leads = []
        for number, row in enumerate(rows[start - 1 :], start=start):
            cells = [cell.strip() for cell in row] + [""] * len(INBOX_HEADER)
            received, name, email, phone, message, processed = cells[: len(INBOX_HEADER)]
            if not message or processed:
                continue
            digest = hashlib.sha1(f"{email}|{phone}|{message}".encode()).hexdigest()[:8]
            lead = Lead(
                id=f"SH-{number}-{digest}",
                received_at=received or now_iso(),
                name=name,
                email=email,
                phone=phone,
                channel="sheet",
                message=message[:5000],
            )
            self._rows[lead.id] = number
            leads.append(lead)
        return leads

    def mark_processed(self, record: LeadRecord) -> None:
        """Write the result into the row's "Processed" cell so it is never handled twice."""
        row = self._rows.get(record.lead.id)
        if row is not None:
            note = f"{record.route} ({record.lead.id}) {now_iso()}"
            self.client.set_cell(self.tab, row, PROCESSED_COLUMN, note)


# ----------------------------------------------------------------------------- storage wrapper


class SheetMirrorStorage(Storage):
    """The normal storage, plus one Leads-tab row per finished lead.

    All reads and writes go to the wrapped storage, so local files stay the
    source of truth. The sheet is written only in `on_lead_finished`, after the
    lead is already saved locally.
    """

    def __init__(self, inner: Storage, sheet: LeadsSheet) -> None:
        self.inner = inner
        self.sheet = sheet
        self._failures = 0

    def enqueue_lead(self, lead: Lead) -> None:
        self.inner.enqueue_lead(lead)

    def list_inbox(self) -> list[Lead]:
        return self.inner.list_inbox()

    def save_record(self, record: LeadRecord) -> None:
        self.inner.save_record(record)

    def list_records(self) -> list[LeadRecord]:
        return self.inner.list_records()

    def save_run(self, run: RunRecord) -> None:
        self.inner.save_run(run)

    def list_runs(self) -> list[RunRecord]:
        return self.inner.list_runs()

    def on_lead_finished(self, record: LeadRecord) -> str | None:
        if self._failures >= MAX_CONSECUTIVE_FAILURES:
            return None  # already reported; stop hammering Google for the rest of the run
        try:
            self.sheet.append_record(record)
        except SheetsError as exc:
            self._failures += 1
            message = (
                f"Google Sheets: lead {record.lead.id} is saved locally but not in the sheet. {exc}"
            )
            if self._failures >= MAX_CONSECUTIVE_FAILURES:
                message += " Sheet updates are paused for the rest of this run."
            logger.warning("sheet write failed for lead=%s", record.lead.id)
            return message
        self._failures = 0
        return None


# ----------------------------------------------------------------------------- wiring


def sheets_active(settings: Settings) -> bool:
    """Whether this process may talk to Google Sheets at all.

    Off unless SHEETS_ENABLED=1. In mock mode it stays off (so tests, CI and
    `make demo` can never reach Google) unless SHEETS_ALLOW_MOCK=1 is also set,
    which only `make demo-sheet` does.
    """
    if not settings.sheets_enabled:
        return False
    return not settings.mock_llm or settings.sheets_allow_mock


def make_client(settings: Settings) -> SheetsClient:
    if not settings.google_sheet_id:
        raise ConfigError(
            "SHEETS_ENABLED=1 but GOOGLE_SHEET_ID is empty. Set it in .env to the id in the "
            "sheet's URL (between /d/ and /edit)."
        )
    key_file = Path(settings.google_service_account_file)
    if not key_file.is_absolute():
        key_file = project_root() / key_file
    return GspreadClient(settings.google_sheet_id, key_file)


def open_storage(settings: Settings, client: SheetsClient | None = None) -> Storage:
    """Local storage, mirrored to the Leads tab when Google Sheets is active."""
    local = LocalStorage(settings.resolved_data_dir())
    if not sheets_active(settings):
        return local
    client = client or make_client(settings)
    return SheetMirrorStorage(local, LeadsSheet(client, settings.sheet_leads_tab))


def open_inbox(settings: Settings, client: SheetsClient | None = None) -> InboxSheet:
    """The Inbox tab as a lead source. Fails clearly when Sheets is not usable."""
    if not settings.sheets_enabled:
        raise ConfigError("--source sheet needs SHEETS_ENABLED=1 in .env.")
    if not sheets_active(settings):
        raise ConfigError(
            "--source sheet is off in mock mode (LEADGEN_MOCK_LLM=1), so the mock never calls "
            "Google. Set LEADGEN_MOCK_LLM=0, or SHEETS_ALLOW_MOCK=1 to use the mock on purpose."
        )
    return InboxSheet(client or make_client(settings), settings.sheet_inbox_tab)
