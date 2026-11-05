"""Reviewed exact-inverse layers for the livelihoods/commons sprint.

Each landing that edits a pinned file records one layer fixture,
``tests/fixtures/livelihoods_<landing>_source_inverse.json``, listed in
``LAYERS`` oldest first. A layer row holds the file's full current digest, the
literal ``(old, new)`` hook patches (with lexical context on both sides, each
``new`` occurring exactly once) and the digest of the bytes before the landing.
Projection applies the newest layer first, so the result is the sprint
baseline (main 64863f1) that every historical chain already verifies.

Unknown digests pass through unchanged when ``strict`` is false: the older,
historical layers then reject them, because they admit only exact hashes. The
sprint's own test calls with ``strict=True``. This is source lineage only; it
does not qualify runtime parity, RNG, checkpoints or scientific efficacy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "64863f1274e400c3898972fe0cd5df510d3bb06f"
#: Landing layers, oldest first. Append only; never edit a landed layer.
LAYERS: tuple[str, ...] = ("l0", "l1a", "l2", "l3", "l4", "s1r", "l8", "l5", "l6", "l9", "l7", "r3", "s2r", "rs0", "rs6", "rs5")


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def layer_fixture(name: str) -> Path:
    return ROOT / "tests/fixtures" / f"livelihoods_{name}_source_inverse.json"


def _rows(path: str):
    for name in reversed(LAYERS):
        row = json.loads(layer_fixture(name).read_text(encoding="utf-8"))["files"].get(path)
        if row is not None:
            yield name, row


def before_livelihoods_sprint(source: str, path: str, *, strict: bool = False) -> str:
    """Project current sprint source back to the baseline bytes of ``path``."""
    rows = list(_rows(path))
    if not rows:
        return source
    if strict:
        assert _digest(source) == rows[0][1]["current_sha256"], f"livelihoods witness changed: {path}"
    for name, row in rows:
        if _digest(source) != row["current_sha256"]:
            continue
        for patch in reversed(row["patches"]):
            assert source.count(patch["new"]) == 1, f"livelihoods {name} insertion changed: {path}"
            source = source.replace(patch["new"], patch["old"], 1)
        assert _digest(source) == row["sha256"], f"livelihoods {name} inverse incomplete: {path}"
    return source
