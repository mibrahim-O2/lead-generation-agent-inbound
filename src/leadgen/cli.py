"""Command-line entry point: `leadgen` / `python -m leadgen`.

The flags are final; the agent run behind them is implemented in the core-agent task.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

SOURCES = ("sample", "file", "webhook")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leadgen",
        description="Inbound lead agent. Drafts replies for human approval - never sends.",
    )
    parser.add_argument(
        "--source", choices=SOURCES, default="sample", help="Where new enquiries come from."
    )
    parser.add_argument("--file", help="Path to a CSV/JSON file (with --source file).")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N leads.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full agent but write nothing; print what it would do.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mode = "dry run" if args.dry_run else "real run"
    print(f"leadgen scaffold: source={args.source} limit={args.limit} ({mode})")
    print("The agent is not implemented yet - it arrives in the core-agent task.")
    return 0
