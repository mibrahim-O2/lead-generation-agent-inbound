"""The guides must match the code: variables, make targets, flags and linked files."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from leadgen.cli import build_parser
from leadgen.llm import PROVIDERS

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ["README.md", "USER.md", "MODEL_SWITCH.md", "docs/GOOGLE_SHEETS.md",
          "dashboard/README.md", "evals/README.md"]  # fmt: skip
MAKE_TARGETS = set(re.findall(r"^([a-z][a-z-]*):", (ROOT / "Makefile").read_text(), re.M))


def test_every_environment_variable_the_code_reads_is_in_example_env() -> None:
    example = (ROOT / "example.env").read_text()
    names = set()
    for module in ("config.py", "llm.py"):
        source = (ROOT / "src" / "leadgen" / module).read_text()
        names |= set(
            re.findall(r'(?:env\.get|_int|_flag)\(\s*(?:env,\s*)?"([A-Z][A-Z0-9_]+)"', source)
        )
    for spec in PROVIDERS.values():
        names |= {name for name in (spec.key_env, spec.base_url_env) if name}
    names |= {"VITE_API_URL", "VITE_BASE", "OPENAI_AGENTS_DISABLE_TRACING"}
    assert len(names) > 25
    for name in sorted(names):
        assert re.search(rf"^#? ?{name}=", example, re.M), f"{name} is not in example.env"


def test_example_env_explains_every_variable() -> None:
    """Each documented variable says whether it is required/optional and what happens if missing."""
    example = (ROOT / "example.env").read_text()
    assert example.count("If missing") >= 20
    assert "REQUIRED" in example and "optional" in example
    for line in re.findall(r"^[A-Z][A-Z0-9_]*_API_KEY=(.*)$", example, re.M):
        assert "REPLACE-ME" in line


@pytest.mark.parametrize("guide", GUIDES)
def test_make_commands_in_the_guides_exist(guide: str) -> None:
    text = (ROOT / guide).read_text()
    # Commands appear in backticks or at the start of a line in a code block.
    used = set(re.findall(r"(?:`|^)make ([a-z][a-z-]*)", text, re.M))
    assert used and used <= MAKE_TARGETS, used - MAKE_TARGETS


@pytest.mark.parametrize("guide", GUIDES)
def test_cli_flags_in_the_guides_exist(guide: str) -> None:
    text = (ROOT / guide).read_text()
    known = {option for action in build_parser()._actions for option in action.option_strings}
    known |= {"--live", "--case", "--filter", "--max-leads", "--max-tokens"}  # leadgen.evals
    known |= {"--bind"}
    for line in re.findall(r"^.*python -m leadgen.*$", text, re.M):
        for flag in re.findall(r"(--[a-z][a-z-]*)", line):
            assert flag in known, f"{guide}: unknown flag {flag} in: {line.strip()}"


@pytest.mark.parametrize("guide", GUIDES)
def test_links_between_guides_resolve(guide: str) -> None:
    path = ROOT / guide
    for target in re.findall(r"\]\(([^)#]+?)(?:#[^)]*)?\)", path.read_text()):
        if target.startswith(("http://", "https://")):
            continue
        assert (path.parent / target).exists(), f"{guide} links to missing {target}"


def test_user_guide_covers_the_required_topics() -> None:
    text = (ROOT / "USER.md").read_text().lower()
    for topic in ["install", ".env", "make demo", "dry run", "dashboard", "google sheets",
                  "model provider", "pull request", "troubleshooting", "safety"]:  # fmt: skip
        assert topic in text, topic
    anchors = re.findall(r"\]\(#([a-z0-9-]+)\)", (ROOT / "USER.md").read_text())
    headings = {
        re.sub(r"[^a-z0-9 -]", "", heading.lower()).strip().replace(" ", "-")
        for heading in re.findall(r"^## (.+)$", (ROOT / "USER.md").read_text(), re.M)
    }
    assert anchors and set(anchors) <= headings, set(anchors) - headings


def test_readme_status_table_has_nothing_left_planned() -> None:
    readme = (ROOT / "README.md").read_text()
    assert "| planned |" not in readme and "USER.md" in readme
