"""Regression tests: no real .env file and no exported variable may reach the tests.

Background: a developer's .env with SHEETS_ENABLED=1 made CLI tests fail locally
while CI passed. These tests fill a .env with a value for EVERY variable in
example.env and prove the suite ignores it. They never read or write the
repository's own .env.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import dotenv
import pytest
from dotenv import dotenv_values

from leadgen import cli, evals
from leadgen.config import Settings
from tests.conftest import ENV_NAMES, ROOT, TEST_ENV

# Obviously fake values that would each change behaviour if they leaked in.
FAKE_VALUES = {
    "SHEETS_ENABLED": "1",
    "SHEETS_ALLOW_MOCK": "1",
    "LEADGEN_MOCK_LLM": "0",
    "OPENAI_API_KEY": "sk-test-fake-not-real",
    "LLM_PROVIDER": "anthropic",
    "LLM_MODEL": "fake-model-not-real",
    "GOOGLE_SHEET_ID": "fake-sheet-id-not-real",
    "GOOGLE_SERVICE_ACCOUNT_FILE": "secrets/fake-key-not-real.json",
    "SHEET_LEADS_TAB": "FakeLeads",
    "SHEET_INBOX_TAB": "FakeInbox",
    "MAX_LEADS_PER_RUN": "2",
    "MAX_TOOL_CALLS_PER_LEAD": "3",
    "MAX_TOKENS_PER_RUN": "1000",
    "LEADGEN_PRESET": "fake-preset-not-real",
    "LEADGEN_CLIENT_CONFIG": "config/fake-client-not-real.yaml",
    "LEADGEN_DATA_DIR": "data/runtime/fake-env-leak",
    "API_HOST": "0.0.0.0",
    "API_PORT": "9999",
    "CORS_ORIGINS": "http://fake.example.com",
    "OPENAI_AGENTS_DISABLE_TRACING": "0",
    "OLLAMA_BASE_URL": "http://fake.example.com:11434",
    "LLM_BASE_URL": "https://fake.example.com/v1",
    "VITE_API_URL": "http://fake.example.com",
    "VITE_BASE": "/fake/",
}


def write_fake_env(folder: Path) -> Path:
    """A .env with a fake value for every variable documented in example.env."""
    lines = [f"{name}={FAKE_VALUES.get(name, 'fake-' + name.lower() + '-not-real')}"
             for name in sorted(ENV_NAMES)]  # fmt: skip
    path = folder / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_fake_env_covers_every_documented_variable_and_would_change_settings(tmp_path) -> None:
    values = dotenv_values(write_fake_env(tmp_path))
    assert set(values) == ENV_NAMES and len(ENV_NAMES) >= 30
    # Sanity: if this file were loaded, the settings would be very different.
    leaked = Settings.from_env({k: v or "" for k, v in values.items()})
    assert leaked.sheets_enabled and not leaked.mock_llm and leaked.max_leads_per_run == 2


def test_documented_and_prefixed_variables_are_cleared_for_every_test() -> None:
    for name in ENV_NAMES - set(TEST_ENV) - {"LEADGEN_DATA_DIR"}:
        assert name not in os.environ, f"{name} leaked into the test environment"
    assert os.environ["LEADGEN_MOCK_LLM"] == "1" and os.environ["OPENAI_API_KEY"] == ""


def test_dotenv_search_finds_nothing_but_explicit_paths_still_load(tmp_path, monkeypatch) -> None:
    assert dotenv.find_dotenv() == ""
    assert dotenv.load_dotenv() is False
    # An explicit path is not affected: tests that need a file can still load one.
    path = tmp_path / "explicit.env"
    path.write_text("LEADGEN_ISOLATION_PROBE=yes\n")
    monkeypatch.delenv("LEADGEN_ISOLATION_PROBE", raising=False)
    assert dotenv.load_dotenv(path) is True
    assert os.environ["LEADGEN_ISOLATION_PROBE"] == "yes"


def test_cli_and_evals_ignore_a_full_fake_env(tmp_path, monkeypatch, capsys) -> None:
    """The exact failure from the bug report, plus every other variable."""
    write_fake_env(tmp_path)
    monkeypatch.chdir(tmp_path)  # also covers dotenv's "search from the cwd" mode
    before = {name: os.environ.get(name) for name in ENV_NAMES}

    assert cli.main(["--source", "sheet"]) == 2
    assert "SHEETS_ENABLED=1" in capsys.readouterr().err  # the original failing check
    assert cli.main(["--dry-run", "--limit", "1"]) == 0
    out = capsys.readouterr().out
    assert "model=mock/mock-rules" in out and "results also go" not in out
    assert evals.main(["--case", "21_sample_s001_hot_home"]) == 0
    assert "1/1 cases passed" in capsys.readouterr().out

    assert {name: os.environ.get(name) for name in ENV_NAMES} == before
    settings = Settings.from_env()
    assert settings.mock_llm and not settings.sheets_enabled
    assert (settings.llm_provider, settings.llm_model, settings.max_leads_per_run) == (
        "openai",
        "",
        25,
    )
    assert settings.google_service_account_file == "secrets/service-account.json"
    assert not (tmp_path / "data" / "runtime" / "fake-env-leak").exists()


# Files the CLI, sheets, evals and config tests need, copied into a scratch project.
PROJECT_FILES = [
    "src", "tests", "config", "presets", "evals", "data/sample_leads.csv", "data/faq.md",
    "example.env", "pyproject.toml", "Makefile", ".gitignore",
]  # fmt: skip


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git for the gitignore tests")
def test_suite_passes_with_a_full_fake_env_in_the_project_root(tmp_path) -> None:
    """End to end: a scratch copy of the project with a fake .env in its root.

    The copy's own source is imported, so dotenv's upward search from its
    src/leadgen really finds that .env, exactly as on a developer's machine.
    """
    project = tmp_path / "project"
    for name in PROJECT_FILES:
        source, target = ROOT / name, project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "runtime"))
        else:
            shutil.copy2(source, target)
    write_fake_env(project)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)

    env = {**os.environ, "PYTHONPATH": str(project / "src")}
    env.pop("PYTEST_CURRENT_TEST", None)
    where = subprocess.run(
        [sys.executable, "-c", "import leadgen; print(leadgen.__file__)"],
        cwd=project, env=env, capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert where.stdout.strip().startswith(str(project)), "the copy's source must be imported"

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider",
         "tests/test_cli.py", "tests/test_sheets.py", "tests/test_evals.py",
         "tests/test_diagnostics.py", "tests/test_config.py", "tests/test_env_isolation.py",
         "-k", "not full_fake_env_in_the_project_root"],
        cwd=project, env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip
    summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr
    assert result.returncode == 0, (
        f"suite failed with a fake .env present: {summary}\n{result.stdout[-3000:]}"
    )
    assert " passed" in summary and "failed" not in summary
