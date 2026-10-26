#!/usr/bin/env python3
"""Identity check for narration changes: everything but the narration is equal.

``compare BASE_DIR NEW_DIR``
    Every file of two run directories (one run, or a batch of ``seed_*``
    runs) byte for byte, except the narration itself: ``chronicle.md``, the
    captured ``prompts.jsonl`` and its ``report.json``, logs and
    ``run_manifest.json`` are skipped,
    and ``chronicle_bundle.json`` is compared decoded, without
    ``metadata.generated_at``, ``chronicle_entries`` and ``gap_summaries``.
    State, sidecars, snapshots (the bundle's history), the event timeline,
    agent events and validation sidecars must be identical.

``compare-observers BASE_DIR NEW_DIR``
    As ``compare``, for changes to what observes the run: the in-world
    chronicles (``state.historiography.json`` and the bundle's
    ``historiography``) are left out, and a movement founding's causes that
    cite a like movement's won demand (``movement_reform`` or
    ``movement_concession``, the news link) are removed from the timeline in
    ``state.json`` and the bundle before comparing. Prints what it removed:
    the news links and the accounts on each side.

Run BASE with the base commit's source on ``PYTHONPATH`` and NEW with this
branch; same interpreter, native extension, arguments and
``PYTHONHASHSEED=0``. See docs/integration/narration-coverage.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from chronicler.bundle_codec import load_bundle

SKIPPED_NAMES = frozenset({"run_manifest.json", "chronicle.md", "prompts.jsonl", "narrated.json", "report.json"})
NARRATION_FIELDS = ("chronicle_entries", "gap_summaries")


def _skipped(rel: Path) -> bool:
    return rel.name in SKIPPED_NAMES or rel.suffix == ".log"


NEWS_SUCCESS = ("movement_reform", "movement_concession")
OBSERVER_FILES = frozenset({"state.historiography.json"})


def _strip_news(timeline: list, counts: dict) -> None:
    """Remove a founding's causes that cite a won demand (the news link)."""
    kinds = {e.get("event_id"): e.get("event_type") for e in timeline}
    for ev in timeline:
        if ev.get("event_type") != "movement_founded":
            continue
        kept = [c for c in ev.get("causes", []) if kinds.get(c) not in NEWS_SUCCESS]
        if len(kept) != len(ev.get("causes", [])):
            counts["news_links"] = counts.get("news_links", 0) + len(ev["causes"]) - len(kept)
            if kept:
                ev["causes"] = kept
            else:
                del ev["causes"]   # an event without causes is written without the field


def _content(path: Path, observers: bool = False, counts: dict | None = None) -> bytes:
    counts = {} if counts is None else counts
    if path.name == "chronicle_bundle.json":
        data = load_bundle(path)
        data.get("metadata", {}).pop("generated_at", None)
        for key in NARRATION_FIELDS:
            data.pop(key, None)
        if observers:
            counts["accounts"] = len((data.pop("historiography", None) or {}).get("accounts", []))
            _strip_news(data.get("events_timeline", []), counts)
            _strip_news((data.get("world_state") or {}).get("events_timeline", []), counts)
        return json.dumps(data, sort_keys=True).encode("utf-8")
    if observers and path.name == "state.json":
        data = json.loads(path.read_text(encoding="utf-8"))
        _strip_news(data.get("events_timeline", []), counts)
        return json.dumps(data, sort_keys=True).encode("utf-8")
    return path.read_bytes()


def _accounts(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    return len(data.get("state", {}).get("accounts", []))


def compare(base: Path, new: Path, observers: bool = False) -> tuple[int, list[str]]:
    base_files = {p.relative_to(base) for p in base.rglob("*") if p.is_file()}
    new_files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()}
    problems: list[str] = []
    for rel in sorted(base_files ^ new_files):
        if not _skipped(rel):
            problems.append(f"only in {'base' if rel in base_files else 'new'}: {rel}")
    checked = 0
    for rel in sorted(base_files & new_files):
        if _skipped(rel):
            continue
        if observers and rel.name in OBSERVER_FILES:
            print(f"left out: {rel} (accounts {_accounts(base / rel)} -> {_accounts(new / rel)})")
            continue
        cb: dict = {}
        cn: dict = {}
        a, b = _content(base / rel, observers, cb), _content(new / rel, observers, cn)
        if cb or cn:
            print(f"stripped: {rel}: base {cb}, new {cn}")
        checked += 1
        if a != b:
            problems.append(f"differs: {rel} ({hashlib.sha256(a).hexdigest()[:12]} != "
                            f"{hashlib.sha256(b).hexdigest()[:12]})")
    return checked, problems


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in ("compare", "compare-observers"):
        print(__doc__)
        return 2
    checked, problems = compare(Path(argv[1]), Path(argv[2]), observers=argv[0] == "compare-observers")
    for line in problems:
        print(line)
    print(f"{checked} files compared, {len(problems)} differences")
    return 0 if not problems and checked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
