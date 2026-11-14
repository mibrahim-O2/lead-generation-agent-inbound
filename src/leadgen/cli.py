"""Command-line entry point: `leadgen` / `python -m leadgen`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import textwrap
import time
from collections.abc import Callable, Sequence
from dataclasses import replace

from dotenv import load_dotenv

from leadgen.config import ConfigError, RuleBook, Settings, load_rulebook
from leadgen.llm import LLMConfigError
from leadgen.models import Lead, LeadRecord
from leadgen.runlog import format_summary
from leadgen.runner import RunOutcome, SourceError, load_leads, run_leads
from leadgen.sheets import InboxSheet, SheetsError, open_inbox, open_storage, sheets_active
from leadgen.storage import Storage

SOURCES = ("sample", "file", "webhook", "sheet")
# Rough average for one lead on a real model, measured on a live eval run.
ESTIMATED_TOKENS_PER_LEAD = 12_500


def non_negative_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leadgen",
        description="Inbound lead agent. Drafts replies for human approval - never sends.",
    )
    parser.add_argument(
        "--source",
        choices=SOURCES,
        default="sample",
        help="sample = data/sample_leads.csv, file = --file, webhook = leads queued via the "
        "API, sheet = new rows in the Google Sheet's Inbox tab.",
    )
    parser.add_argument("--file", help="Path to a CSV or JSON file (required with --source file).")
    parser.add_argument("--limit", type=positive_int, default=None, help="Process at most N leads.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full agent but write nothing; print what it would do.",
    )
    parser.add_argument("--verbose", action="store_true", help="Show per-lead log lines.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="With --source sheet: keep checking the Inbox tab for new rows until Ctrl+C.",
    )
    parser.add_argument(
        "--interval",
        type=positive_int,
        default=10,
        help="With --watch: seconds between checks (default 10).",
    )
    parser.add_argument(
        "--delay",
        type=non_negative_float,
        default=0.0,
        help="Pause this many seconds between leads (for live demos).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Demo helper: print the estimated cost first, and use the mock model when "
        "no API key is set.",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.source == "file" and not args.file:
        parser.error("--file is required when --source file is used")
    if args.file and args.source != "file":
        parser.error("--file can only be used with --source file")
    if args.watch and args.source != "sheet":
        parser.error("--watch can only be used with --source sheet")
    return args


def format_record(record: LeadRecord) -> str:
    lead = record.lead
    lines = [
        f"[{lead.id}] {lead.name or '(no name)'} via {lead.channel}",
        f"  intent: {record.intent}   score: {record.score}/10"
        f"{' (HOT)' if record.is_hot else ''}   route: {record.route}   status: {record.status}",
    ]
    if record.flags:
        lines.append(f"  flags: {', '.join(record.flags)}")
    if record.handover_reason:
        lines.append(f"  handover reason: {record.handover_reason}")
    if record.missing_info:
        lines.append(f"  missing: {', '.join(record.missing_info)}")
    for rejected in record.rejected_drafts:
        lines.append(f"  rejected draft #{rejected.attempt}:")
        for problem in rejected.problems:
            found = f" (found: {problem.found})" if problem.found else ""
            lines.append(f"    - {problem.check}{found} -> {problem.fix}")
    for note in record.guardrail_notes:
        if not note.startswith(f"{len(record.rejected_drafts)} draft(s) rejected"):
            lines.append(f"  guardrail: {note}")
    lines.append(f"  tools used: {' > '.join(record.tool_calls) or 'none'}")
    if record.draft_reply:
        lines.append("  DRAFT (not sent - waiting for human approval):")
        lines.append(textwrap.indent(record.draft_reply, "    | "))
    return "\n".join(lines)


def print_summary(outcome: RunOutcome, data_dir: str) -> None:
    print(format_summary(outcome.run))
    for error in outcome.run.errors:
        print(f"  ! {error}")
    if outcome.run.dry_run:
        print("DRY RUN: nothing was written and nothing was sent.")
    else:
        print(f"Saved to {data_dir}. Nothing was sent: drafts wait for human approval.")


def print_record(record: LeadRecord) -> None:
    print(format_record(record))
    print(flush=True)


def demo_settings(settings: Settings) -> Settings:
    """--demo: fall back to the mock model when there is no usable API key."""
    has_key = bool(settings.openai_api_key) and settings.openai_api_key != "sk-REPLACE-ME"
    if settings.mock_llm or (settings.llm_provider == "openai" and not has_key):
        return replace(settings, mock_llm=True)
    return settings


def cost_estimate(lead_count: int, settings: Settings, rulebook: RuleBook) -> str:
    """One line shown before a demo run starts."""
    if settings.mock_llm:
        return f"Model: mock (no API key needed). Estimated cost for {lead_count} lead(s): $0."
    tokens = lead_count * ESTIMATED_TOKENS_PER_LEAD
    model = f"{settings.llm_provider}/{settings.llm_model or 'sdk-default'}"
    price = rulebook.pricing.input_per_1m_usd  # nearly all tokens are input tokens
    if price:
        cost = f"about ${tokens * price / 1_000_000:.3f} at the prices in config/client.yaml"
    else:
        cost = "cost unknown: set pricing in config/client.yaml"
    return (
        f"Model: {model} (REAL API calls). Estimated use for {lead_count} lead(s): "
        f"about {tokens:,} tokens, {cost}."
    )


def watch_inbox(
    inbox: InboxSheet,
    *,
    args: argparse.Namespace,
    settings: Settings,
    rulebook: RuleBook,
    storage: Storage,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Poll the Inbox tab and process new rows until Ctrl+C or a cap is reached.

    The whole watch session shares one budget: MAX_LEADS_PER_RUN leads and
    MAX_TOKENS_PER_RUN tokens in total.
    """
    data_dir = str(settings.resolved_data_dir())
    leads_done = tokens_used = failures = 0
    seen: set[str] = set()  # a dry run cannot mark rows, so remember them here
    had_errors = False
    print(f"Watching the Inbox tab every {args.interval}s. Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            if leads_done >= settings.max_leads_per_run:
                print(f"Lead limit reached ({settings.max_leads_per_run}). Stopping.")
                break
            if tokens_used >= settings.max_tokens_per_run:
                print(f"Token limit reached ({settings.max_tokens_per_run}). Stopping.")
                break
            try:
                leads = [lead for lead in inbox.pending() if lead.id not in seen]
                failures = 0
            except SheetsError as exc:
                failures += 1
                print(f"Error: {exc}", file=sys.stderr)
                if failures >= 3:
                    print("Giving up after 3 failed attempts to read the sheet.", file=sys.stderr)
                    return 2
                leads = []
            if leads:
                outcome = run_batch(
                    leads,
                    inbox,
                    args=args,
                    settings=replace(
                        settings, max_tokens_per_run=settings.max_tokens_per_run - tokens_used
                    ),
                    rulebook=rulebook,
                    storage=storage,
                    limit=settings.max_leads_per_run - leads_done,
                )
                seen.update(record.lead.id for record in outcome.records)
                leads_done += outcome.run.leads_processed
                tokens_used += outcome.run.total_tokens
                had_errors = had_errors or bool(outcome.run.errors)
                print_summary(outcome, data_dir)
            sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by Ctrl+C.")
    print(f"Watch finished: {leads_done} lead(s) processed, {tokens_used} tokens used.")
    return 1 if had_errors else 0


def run_batch(
    leads: list[Lead],
    inbox: InboxSheet | None,
    *,
    args: argparse.Namespace,
    settings: Settings,
    rulebook: RuleBook,
    storage: Storage,
    limit: int | None,
) -> RunOutcome:
    """Run one batch, printing each lead as it finishes and marking its inbox row."""
    mark_failures: list[str] = []

    def lead_done(record: LeadRecord) -> None:
        print_record(record)
        if inbox is not None and not args.dry_run:  # a dry run never writes to the sheet
            try:
                inbox.mark_processed(record)
            except SheetsError as exc:
                mark_failures.append(f"Google Sheets: could not mark {record.lead.id}. {exc}")

    outcome = asyncio.run(
        run_leads(
            leads,
            settings=settings,
            rulebook=rulebook,
            storage=storage,
            source=args.source,
            dry_run=args.dry_run,
            limit=limit,
            on_lead_done=lead_done,
            delay=args.delay,
        )
    )
    outcome.run.errors.extend(mark_failures)
    return outcome


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv()  # reads .env if present; real environment variables win
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        settings = Settings.from_env()
        if args.demo:
            settings = demo_settings(settings)
        rulebook = load_rulebook(settings.preset, settings.client_config)
        storage = open_storage(settings)
        inbox = open_inbox(settings) if args.source == "sheet" else None
        if sheets_active(settings) and not args.dry_run:
            print(f'Google Sheets: results also go to the "{settings.sheet_leads_tab}" tab.')
        if args.watch and inbox is not None:
            return watch_inbox(
                inbox, args=args, settings=settings, rulebook=rulebook, storage=storage
            )
        leads = (
            inbox.pending() if inbox is not None else load_leads(args.source, storage, args.file)
        )
        if not leads:
            print(f"No new leads from source '{args.source}'.")
            return 0
        if args.demo:
            count = min(len(leads), args.limit or len(leads), settings.max_leads_per_run)
            print(cost_estimate(count, settings, rulebook), flush=True)
        outcome = run_batch(
            leads,
            inbox,
            args=args,
            settings=settings,
            rulebook=rulebook,
            storage=storage,
            limit=args.limit,
        )
    except (ConfigError, LLMConfigError, SourceError, SheetsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print_summary(outcome, str(settings.resolved_data_dir()))
    return 1 if outcome.run.errors else 0
