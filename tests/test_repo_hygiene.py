"""No secrets can slip in, and example.env matches what the code reads."""

from __future__ import annotations

import re
import subprocess
from dataclasses import fields
from pathlib import Path

import pytest

from leadgen.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def env_assignments(include_commented: bool = True) -> dict[str, str]:
    prefix = r"#? ?" if include_commented else ""
    text = (ROOT / "example.env").read_text()
    return dict(re.findall(rf"^{prefix}([A-Z][A-Z0-9_]+)=(\S*)", text, re.M))


def test_example_env_has_only_placeholders() -> None:
    for name, value in env_assignments().items():
        if name.endswith("_API_KEY"):
            assert "REPLACE-ME" in value, f"{name} must be an obvious placeholder"


def test_example_env_defaults_match_the_code() -> None:
    """Loading example.env as-is must give exactly the built-in defaults."""
    env = env_assignments(include_commented=False)
    from_example = Settings.from_env(env)
    defaults = Settings.from_env({})
    for item in fields(Settings):
        if item.name == "openai_api_key":
            continue  # the placeholder key is not a default
        assert getattr(from_example, item.name) == getattr(defaults, item.name), item.name


def test_every_setting_is_documented_in_example_env() -> None:
    documented = env_assignments()
    for name in [
        "OPENAI_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "LEADGEN_MOCK_LLM",
        "OPENAI_AGENTS_DISABLE_TRACING", "MAX_LEADS_PER_RUN", "MAX_TOOL_CALLS_PER_LEAD",
        "MAX_TOKENS_PER_RUN", "LEADGEN_PRESET", "LEADGEN_CLIENT_CONFIG", "LEADGEN_DATA_DIR",
        "API_HOST", "API_PORT", "CORS_ORIGINS", "VITE_API_URL",
    ]:  # fmt: skip
        assert name in documented, f"{name} missing from example.env"


@pytest.mark.parametrize(
    "path",
    [
        ".env", ".env.local", "service-account.json", "my-service_account-file.json",
        "google-credentials.json", "client_secret_123.json", "data/runtime/leads.json",
        "data/runtime/demo/leads.csv", "data/runs.jsonl",
    ],
)  # fmt: skip
def test_gitignore_covers_secrets_and_runtime_data(path: str) -> None:
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
    assert result.returncode == 0, f"{path} is not git-ignored"


@pytest.mark.parametrize(
    "path", ["example.env", "data/sample_leads.csv", "config/client.yaml", "evals/cases/x.yaml"]
)
def test_gitignore_keeps_committed_files(path: str) -> None:
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
    assert result.returncode == 1, f"{path} must not be git-ignored"
