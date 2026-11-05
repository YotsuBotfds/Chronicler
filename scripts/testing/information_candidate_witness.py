"""Exact reviewed M6-to-M5 source projection, not runtime parity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS = ROOT / "tests/fixtures/information_candidate_source_inverse.json"


def before_information_candidate(source: str, path: str, *, allow_parent: bool = False) -> str:
    from scripts.testing.livelihoods_sprint_witness import before_livelihoods_sprint
    source = before_livelihoods_sprint(source, path)
    from scripts.testing.scenarios_candidate_witness import before_scenarios_candidate
    source = before_scenarios_candidate(source, path, allow_parent=True)
    row = json.loads(WITNESS.read_text(encoding="utf-8"))["files"].get(path)
    if row is None:
        return source
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if allow_parent:
        # Older witnesses can pass only exact known ancestor bytes.
        parents = {row["sha256"]}
        for fixture in ("academy_candidate_source_inverse.json", "household_candidate_source_inverse.json", "crisis_candidate_source_inverse.json", "food_accounting_source_inverse.json"):
            older = json.loads((ROOT / "tests/fixtures" / fixture).read_text(encoding="utf-8"))["files"].get(path)
            if older is not None:
                parents.add(older["sha256"])
        if digest in parents:
            return source
    assert digest == row["current_sha256"], f"information candidate witness changed: {path}"
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"information candidate insertion changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == row["sha256"], path
    return source
