"""Exact test-only inverse of the additive food-accounting source layer.

This projects reviewed source bytes, not runtime behavior or parity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS = ROOT / "tests/fixtures/food_accounting_source_inverse.json"


def before_food_accounting(source: str, path: str, *, allow_parent: bool = False) -> str:
    from scripts.testing.livelihoods_sprint_witness import before_livelihoods_sprint
    source = before_livelihoods_sprint(source, path)
    from scripts.testing.crisis_candidate_witness import before_crisis_candidate
    source = before_crisis_candidate(source, path, allow_parent=True)
    row = json.loads(WITNESS.read_text(encoding="utf-8"))["files"].get(path)
    if row is None:
        return source
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if allow_parent and digest == row["sha256"]:
        return source
    assert digest == row["current_sha256"], f"food accounting witness changed: {path}"
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"food accounting insertion changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == row["sha256"], path
    return source
