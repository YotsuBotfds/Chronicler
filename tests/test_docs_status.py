"""Drift guard for the single current-status record (repo hygiene HYG-1).

The entry documents point at the status block at the top of docs/CONTINUATION.md
instead of naming pull requests themselves, and their relative Markdown links resolve.
"""

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY_DOCS = ("README.md", "AGENTS.md", "docs/README.md", "docs/RECOVERY.md")
PR_NUMBER = re.compile(r"PR #\d+")
LINK = re.compile(r"\]\(([^)\s]+)\)")


def _read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative", ["README.md", "AGENTS.md"])
def test_entry_docs_name_no_pull_request_numbers(relative):
    assert PR_NUMBER.findall(_read(relative)) == []


def test_continuation_opens_with_the_current_status_block():
    lines = _read("docs/CONTINUATION.md").splitlines()
    assert lines[0] == "## Current status"
    assert len(lines) < 100


def _relative_md_targets(relative):
    for target in LINK.findall(_read(relative)):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith("#"):
            continue
        path = unquote(target.split("#", 1)[0])
        if path.endswith(".md"):
            yield target, path


@pytest.mark.parametrize("relative", ENTRY_DOCS)
def test_entry_doc_relative_markdown_links_resolve(relative):
    base = (ROOT / relative).parent
    missing = [target for target, path in _relative_md_targets(relative)
               if not (base / path).is_file()]
    assert missing == []


def test_link_scan_sees_the_status_links():
    targets = {target for target, _ in _relative_md_targets("README.md")}
    assert "docs/CONTINUATION.md#current-status" in targets
    assert "docs/superpowers/progress/continuation-history.md" in targets
