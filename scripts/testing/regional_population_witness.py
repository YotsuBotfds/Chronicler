"""Exact test-only inverse of the additive regional observation export.

The c04 parent and older care/default/shipment pins remain immutable. Each
literal insertion is reviewed in its original lexical context; this inverse
rejects changes inside the insertion and unrelated parent source changes.
It proves source projection, not runtime parity or scientific qualification.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS = ROOT / "tests/fixtures/regional_population_source_inverse.json"


def before_regional_population(source: str, path: str) -> str:
    from scripts.testing.food_accounting_witness import before_food_accounting
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    row = witness["files"].get(path)
    if row is None:
        # The shipment composition applies the grain inverse first. Its exact
        # frozen result is already older than the food parent.
        from scripts.testing.grain_release_witness import _LAYERS
        grain = _LAYERS.get(path)
        if grain and hashlib.sha256(source.encode()).hexdigest() == grain["sha256"]:
            return source
        return before_food_accounting(source, path, allow_parent=True)
    source = before_food_accounting(source, path, allow_parent=True)
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"regional observation witness changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode()).hexdigest() == row["sha256"], path
    return source
