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
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    row = witness["files"].get(path)
    if row is None:
        return source
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"regional observation witness changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode()).hexdigest() == row["sha256"], path
    return source
