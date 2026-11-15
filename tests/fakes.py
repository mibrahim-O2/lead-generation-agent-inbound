"""Test doubles. Nothing here touches the network."""

from __future__ import annotations

from leadgen.sheets import SheetsError


class FakeSheetsClient:
    """An in-memory spreadsheet that records every call made to it."""

    def __init__(self, tabs: dict[str, list[list[str]]] | None = None) -> None:
        self.tabs: dict[str, list[list[str]]] = tabs or {"Leads": [], "Inbox": []}
        self.calls: list[tuple] = []
        self.frozen: list[str] = []
        self.dropdowns: list[tuple[str, str, list[str]]] = []
        self.fail_writes = 0  # how many upcoming writes should fail
        self.fail_reads = 0

    @property
    def writes(self) -> list[tuple]:
        return [call for call in self.calls if call[0] != "read"]

    def _write_guard(self) -> None:
        if self.fail_writes:
            self.fail_writes -= 1
            raise SheetsError("Google Sheets failed while adding a row. Share the sheet.")

    def read(self, tab: str) -> list[list[str]]:
        self.calls.append(("read", tab))
        if self.fail_reads:
            self.fail_reads -= 1
            raise SheetsError("Google Sheets failed while reading. Check GOOGLE_SHEET_ID.")
        return [list(row) for row in self.tabs[tab]]

    def append(self, tab: str, row: list[str]) -> None:
        self.calls.append(("append", tab, list(row)))
        self._write_guard()
        self.tabs[tab].append(list(row))

    def set_cell(self, tab: str, row: int, column: int, value: str) -> None:
        self.calls.append(("set_cell", tab, row, column, value))
        self._write_guard()
        cells = self.tabs[tab][row - 1]
        cells.extend([""] * (column - len(cells)))
        cells[column - 1] = value

    def freeze_header(self, tab: str) -> None:
        self.calls.append(("freeze_header", tab))
        self.frozen.append(tab)

    def add_dropdown(self, tab: str, cell_range: str, options: list[str]) -> None:
        self.calls.append(("add_dropdown", tab, cell_range))
        self.dropdowns.append((tab, cell_range, list(options)))
