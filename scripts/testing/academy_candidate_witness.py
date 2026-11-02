"""Exact reviewed M5-to-M4 source projection, not runtime parity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS = ROOT / "tests/fixtures/academy_candidate_source_inverse.json"


def before_academy_candidate(source: str, path: str, *, allow_parent: bool = False) -> str:
    row = json.loads(WITNESS.read_text(encoding="utf-8"))["files"].get(path)
    if row is None:
        return source
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if allow_parent:
        # Older composed witnesses can receive only these exact parent bytes.
        parents = {row["sha256"]}
        for fixture in ("household_candidate_source_inverse.json", "crisis_candidate_source_inverse.json", "food_accounting_source_inverse.json"):
            older = json.loads((ROOT / "tests/fixtures" / fixture).read_text(encoding="utf-8"))["files"].get(path)
            if older is not None:
                parents.add(older["sha256"])
        if digest in parents:
            return source
    assert digest == row["current_sha256"], f"academy candidate witness changed: {path}"
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"academy candidate insertion changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == row["sha256"], path
    return source
