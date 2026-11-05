"""Exact reviewed comparison-gallery source inverse, independent of behavior."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS = ROOT / "tests/fixtures/gallery_candidate_source_inverse.json"


def before_gallery_candidate(source: str, path: str, *, allow_parent: bool = False) -> str:
    from scripts.testing.livelihoods_sprint_witness import before_livelihoods_sprint
    source = before_livelihoods_sprint(source, path)
    row = json.loads(WITNESS.read_text(encoding="utf-8"))["files"].get(path)
    if row is None:
        return source
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if allow_parent:
        # Composed witnesses may already hold exact pre-gallery or older source.
        # This is an allowlist of full hashes, never a permissive textual match.
        parents = {row["sha256"]}
        older = json.loads((ROOT / "tests/fixtures/scenarios_candidate_source_inverse.json").read_text(encoding="utf-8"))["files"].get(path)
        if older is not None:
            parents.add(older["sha256"])
        if digest in parents:
            return source
    assert digest == row["current_sha256"], f"gallery candidate witness changed: {path}"
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"gallery candidate insertion changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == row["sha256"], path
    return source
