"""Scaffold checks: everything imports, the CLI parses, and no secrets can slip in."""

from __future__ import annotations

import importlib
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

MODULES = [
    "agent", "cli", "config", "guardrails", "llm", "models",
    "runlog", "runner", "server", "storage", "tools",
]  # fmt: skip


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    importlib.import_module(f"leadgen.{name}")


def test_agents_sdk_imports() -> None:
    # The exact names the core agent will use, checked against the installed SDK.
    from agents import Agent, Runner, function_tool  # noqa: F401
    from agents.models.interface import Model, ModelProvider  # noqa: F401


def test_cli_flags(capsys: pytest.CaptureFixture[str]) -> None:
    from leadgen.cli import build_parser, main

    args = build_parser().parse_args(["--source", "file", "--limit", "3", "--dry-run"])
    assert (args.source, args.limit, args.dry_run) == ("file", 3, True)
    assert main(["--dry-run"]) == 0
    assert "dry run" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--limit", "0"])


def _env_assignments() -> dict[str, str]:
    """Active and commented-out KEY=value lines in example.env."""
    pairs = re.findall(r"^#? ?([A-Z][A-Z0-9_]+)=(\S*)", (ROOT / "example.env").read_text(), re.M)
    return dict(pairs)


def test_example_env_lists_required_variables() -> None:
    env = _env_assignments()
    for name in [
        "OPENAI_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "MAX_LEADS_PER_RUN",
        "MAX_TOOL_CALLS_PER_LEAD", "MAX_TOKENS_PER_RUN", "VITE_API_URL",
    ]:  # fmt: skip
        assert name in env, f"{name} missing from example.env"
    assert env["LLM_PROVIDER"] == "openai"


def test_example_env_has_only_placeholders() -> None:
    for name, value in _env_assignments().items():
        if name.endswith("_API_KEY"):
            assert "REPLACE-ME" in value, f"{name} must be an obvious placeholder"


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "service-account.json",
        "my-service_account-file.json",
        "google-credentials.json",
        "client_secret_123.json",
        "data/runtime/leads.json",
        "data/runs.jsonl",
    ],
)
def test_gitignore_covers_secrets_and_runtime_data(path: str) -> None:
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
    assert result.returncode == 0, f"{path} is not git-ignored"


@pytest.mark.parametrize("path", ["example.env", "data/sample_leads.csv", "config/client.yaml"])
def test_gitignore_keeps_committed_files(path: str) -> None:
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
    assert result.returncode == 1, f"{path} must not be git-ignored"
