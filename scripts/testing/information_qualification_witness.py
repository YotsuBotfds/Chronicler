"""Exact reviewed forecast qualification-to-030 source projection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS = ROOT / "tests/fixtures/information_qualification_source_inverse.json"
WALKTHROUGH_WITNESS = ROOT / "tests/fixtures/forecast_walkthrough_source_inverse.json"


def before_forecast_walkthrough(source: str, path: str, *, allow_parent: bool = False) -> str:
    """Remove only the separately reviewed walkthrough/CLI correction.

    The historical information fixture retains its original new-file digest.
    Whole-file admission and the final parent digest prevent this projection
    from accepting partial edits or unrelated simulation changes.
    """
    row = json.loads(WALKTHROUGH_WITNESS.read_text(encoding="utf-8"))["files"].get(path)
    if row is None:
        return source
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if allow_parent and digest == row["sha256"]:
        return source
    assert digest == row["current_sha256"], f"forecast walkthrough witness changed: {path}"
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"forecast walkthrough insertion changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == row["sha256"], path
    return source


def before_information_qualification(source: str, path: str, *, allow_parent: bool = False) -> str:
    row = json.loads(WITNESS.read_text(encoding="utf-8"))["files"].get(path)
    if row is None:
        return source
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if allow_parent:
        parents = {row["sha256"]}
        for fixture in ("restoration_candidate_source_inverse.json", "scenarios_candidate_source_inverse.json", "information_candidate_source_inverse.json", "academy_candidate_source_inverse.json", "household_candidate_source_inverse.json", "crisis_candidate_source_inverse.json", "food_accounting_source_inverse.json"):
            older = json.loads((ROOT / "tests/fixtures" / fixture).read_text(encoding="utf-8"))["files"].get(path)
            if older is not None:
                parents.add(older["sha256"])
        if digest in parents:
            return source
    assert digest == row["current_sha256"], f"information qualification witness changed: {path}"
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"information qualification insertion changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == row["sha256"], path
    return source
