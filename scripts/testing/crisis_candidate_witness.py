"""Exact reviewed candidate-to-M1 source projection, not runtime parity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS = ROOT / "tests/fixtures/crisis_candidate_source_inverse.json"


def before_crisis_candidate(source: str, path: str, *, allow_parent: bool = False) -> str:
    from scripts.testing.livelihoods_sprint_witness import before_livelihoods_sprint
    source = before_livelihoods_sprint(source, path)
    from scripts.testing.household_candidate_witness import before_household_candidate
    source = before_household_candidate(source, path, allow_parent=True)
    row = json.loads(WITNESS.read_text(encoding="utf-8"))["files"].get(path)
    if row is None:
        return source
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if allow_parent:
        # The older helpers can receive the exact M1 parent, or a food-layer
        # parent already projected by a preceding helper.
        food = json.loads((ROOT / "tests/fixtures/food_accounting_source_inverse.json").read_text(encoding="utf-8"))["files"].get(path)
        if digest == row["sha256"] or food is not None and digest == food["sha256"]:
            return source
    assert digest == row["current_sha256"], f"crisis candidate witness changed: {path}"
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"crisis candidate insertion changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == row["sha256"], path
    return source
