"""Command-line entry point: `leadgen` / `python -m leadgen`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import textwrap
from collections.abc import Sequence

from dotenv import load_dotenv

from leadgen.config import ConfigError, Settings, load_rulebook
from leadgen.llm import LLMConfigError
from leadgen.models import LeadRecord
from leadgen.runlog import format_summary
from leadgen.runner import RunOutcome, SourceError, load_leads, run_leads
from leadgen.storage import LocalStorage

SOURCES = ("sample", "file", "webhook")


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
        help="sample = data/sample_leads.csv, file = --file, webhook = leads queued via the API.",
    )
    parser.add_argument("--file", help="Path to a CSV or JSON file (required with --source file).")
    parser.add_argument("--limit", type=positive_int, default=None, help="Process at most N leads.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full agent but write nothing; print what it would do.",
    )
    parser.add_argument("--verbose", action="store_true", help="Show per-lead log lines.")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.source == "file" and not args.file:
        parser.error("--file is required when --source file is used")
    if args.file and args.source != "file":
        parser.error("--file can only be used with --source file")
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


def print_outcome(outcome: RunOutcome, data_dir: str) -> None:
    for record in outcome.records:
        print(format_record(record))
        print()
    print(format_summary(outcome.run))
    if outcome.run.dry_run:
        print("DRY RUN: nothing was written and nothing was sent.")
    else:
        print(f"Saved to {data_dir}. Nothing was sent: drafts wait for human approval.")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv()  # reads .env if present; real environment variables win
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        settings = Settings.from_env()
        rulebook = load_rulebook(settings.preset, settings.client_config)
        storage = LocalStorage(settings.resolved_data_dir())
        leads = load_leads(args.source, storage, args.file)
        if not leads:
            print(f"No new leads from source '{args.source}'.")
            return 0
        outcome = asyncio.run(
            run_leads(
                leads,
                settings=settings,
                rulebook=rulebook,
                storage=storage,
                source=args.source,
                dry_run=args.dry_run,
                limit=args.limit,
            )
        )
    except (ConfigError, LLMConfigError, SourceError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print_outcome(outcome, str(settings.resolved_data_dir()))
    return 1 if outcome.run.errors else 0
