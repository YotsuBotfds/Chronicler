"""Read the frozen snapshot of the source-witnessed files.

``tests/fixtures/frozen_pin_sources/<path>.txt`` holds the exact bytes of each
witnessed file as of ``MANIFEST["freeze_commit"]`` (built once by
``scripts/testing/freeze_pin_sources.py``). Readers never fall back to the
working tree: a path without a frozen copy raises ``FileNotFoundError``.
"""
from __future__ import annotations

import json
from pathlib import Path

FROZEN_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "frozen_pin_sources"
MANIFEST = json.loads((FROZEN_ROOT / "MANIFEST.json").read_text(encoding="utf-8"))


def frozen_bytes(rel: str) -> bytes:
    """The frozen bytes of repository path ``rel`` (for example ``src/chronicler/main.py``)."""
    if rel not in MANIFEST["files"]:
        raise FileNotFoundError(f"no frozen copy for {rel!r} in {FROZEN_ROOT / 'MANIFEST.json'}")
    path = FROZEN_ROOT / f"{rel}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"frozen copy of {rel!r} is missing: {path}")
    return path.read_bytes()


def frozen_text(rel: str) -> str:
    return frozen_bytes(rel).decode("utf-8")
