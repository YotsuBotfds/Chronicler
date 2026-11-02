"""Exact reviewed M7-to-M6 source projection, not runtime parity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS = ROOT / "tests/fixtures/scenarios_candidate_source_inverse.json"


def before_scenarios_candidate(source: str, path: str, *, allow_parent: bool = False) -> str:
    from scripts.testing.restoration_candidate_witness import before_restoration_candidate
    source = before_restoration_candidate(source, path, allow_parent=True)
    row = json.loads(WITNESS.read_text(encoding="utf-8"))["files"].get(path)
    if row is None:
        return source
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if allow_parent and digest == row["sha256"]:
        return source
    assert digest == row["current_sha256"], f"scenarios candidate witness changed: {path}"
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"scenarios candidate insertion changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == row["sha256"], path
    return source
