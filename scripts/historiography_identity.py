#!/usr/bin/env python3
"""Prove that in-world historiography changes no simulation output.

``compare BASE_DIR NEW_DIR``
    Historiography off (or a base without it): walk two run directories (one
    run, a batch of ``seed_*`` runs, or a gate batch) and compare every file.
    ``chronicle_bundle.json`` is compared after dropping
    ``metadata.generated_at`` (the wall-clock stamp); every other file must
    match byte for byte. Files present on only one side are reported.

``compare --historiography BASE_DIR NEW_DIR``
    NEW ran with historiography on. Every file must still match byte for byte
    (``state.json``, memories, ``agent_events.arrow``, validation sidecars and
    reports) except the narration surfaces:

    * ``chronicle_bundle.json`` must be identical after dropping
      ``metadata.generated_at`` and the narration fields
      (``historiography``, ``chronicle_entries``, ``gap_summaries``); the
      world state, every history snapshot, the event timeline, named events,
      era reflections and the rest of the metadata are compared;
    * ``chronicle.md`` (the narration) may differ;
    * ``<state>.historiography.json`` sidecars exist only in NEW.

    It also checks NEW's narration side: every bundle carries the field,
    every account's ``event_id`` and every cited cause resolves to an event of
    that bundle's timeline, and every chronicle entry's ``accounts`` id
    resolves to an account.

``--normalize OLD=NEW`` (repeatable) replaces a path prefix in text files
before comparing (gate reports name their batch directory).

Run BASE with the base commit's source on ``PYTHONPATH`` and NEW with this
branch, same interpreter, native extension, arguments and
``PYTHONHASHSEED=0``. See docs/integration/historiography.md. Exit status 0
when identical.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

IGNORED_NAMES = frozenset({"run_manifest.json"})  # gate tooling, records its own flags
SIDECAR_SUFFIX = ".historiography.json"
NARRATION_FIELDS = ("historiography", "chronicle_entries", "gap_summaries")
NARRATION_FILES = frozenset({"chronicle.md"})


def _bundle(path: Path, *, drop_narration: bool) -> bytes:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.get("metadata", {}).pop("generated_at", None)
    if drop_narration:
        for key in NARRATION_FIELDS:
            data.pop(key, None)
    return json.dumps(data, sort_keys=True).encode("utf-8")


def _content(path: Path, *, drop_narration: bool, normalize: list[tuple[str, str]]) -> bytes:
    if path.name == "chronicle_bundle.json":
        return _bundle(path, drop_narration=drop_narration)
    data = path.read_bytes()
    if normalize and path.suffix in (".json", ".md", ".txt"):
        text = data.decode("utf-8", errors="surrogateescape")
        for old, new in normalize:
            text = text.replace(old, new)
        data = text.encode("utf-8", errors="surrogateescape")
    return data


def check_narration(bundle_path: Path) -> list[str]:
    """NEW-side checks: the field exists and every id in it resolves."""
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    field = data.get("historiography")
    if not isinstance(field, dict):
        return [f"no historiography field: {bundle_path}"]
    problems: list[str] = []
    events = {e.get("event_id") for e in data.get("events_timeline", []) if e.get("event_id")}
    columns = field.get("account_columns", [])
    try:
        eid_col, chron_col, cited_col = (columns.index(c) for c in ("event_id", "chronicler", "cited"))
    except ValueError:
        return [f"unknown account columns {columns}: {bundle_path}"]
    ids = set()
    for row in field.get("accounts", []):
        eid = row[eid_col]
        ids.add(f"{row[chron_col]}/{eid}")
        if eid not in events:
            problems.append(f"account of unknown event {eid}: {bundle_path}")
        for cause in row[cited_col] or []:
            if cause not in events:
                problems.append(f"account {row[chron_col]}/{eid} cites unknown event {cause}")
    for chron, eids in field.get("plain", {}).items():
        for eid in eids:
            ids.add(f"{chron}/{eid}")
            if eid not in events:
                problems.append(f"plain account of unknown event {eid}: {bundle_path}")
    for entry in data.get("chronicle_entries", []):
        if isinstance(entry, dict):
            for aid in entry.get("accounts", []):
                if aid not in ids:
                    problems.append(f"chronicle entry cites unknown account {aid}")
    return problems[:20]


def compare(base: Path, new: Path, *, historiography: bool = False,
            normalize: list[tuple[str, str]] | None = None) -> tuple[int, list[str], list[str]]:
    normalize = normalize or []
    base_files = {p.relative_to(base) for p in base.rglob("*") if p.is_file()}
    new_files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()}
    problems: list[str] = []
    notes: list[str] = []
    sidecars = 0
    for rel in sorted(base_files ^ new_files):
        if rel.name in IGNORED_NAMES:
            continue
        if historiography and rel in new_files and rel.name.endswith(SIDECAR_SUFFIX):
            sidecars += 1
            continue
        problems.append(f"only in {'base' if rel in base_files else 'new'}: {rel}")
    checked = narration_diffs = bundles = 0
    for rel in sorted(base_files & new_files):
        if rel.name in IGNORED_NAMES or rel.suffix in (".log",):
            continue
        a = _content(base / rel, drop_narration=historiography, normalize=normalize)
        b = _content(new / rel, drop_narration=historiography, normalize=normalize)
        checked += 1
        if rel.name == "chronicle_bundle.json":
            bundles += 1
            if historiography:
                problems.extend(check_narration(new / rel))
        if a != b:
            if historiography and rel.name in NARRATION_FILES:
                narration_diffs += 1
                continue
            problems.append(f"differs: {rel} ({hashlib.sha256(a).hexdigest()[:12]} != "
                            f"{hashlib.sha256(b).hexdigest()[:12]})")
    if historiography:
        notes.append(f"{sidecars} historiography sidecars only in new (expected)")
        notes.append(f"{narration_diffs} narration files (chronicle.md) differ (allowed)")
        notes.append(f"{bundles} bundles identical apart from {', '.join(NARRATION_FIELDS)}")
        if bundles and not sidecars:
            problems.append("historiography mode but NEW wrote no sidecar")
    return checked, problems, notes


def main(argv: list[str]) -> int:
    args = list(argv)
    if not args or args[0] != "compare":
        print(__doc__)
        return 2
    args.pop(0)
    historiography = False
    normalize: list[tuple[str, str]] = []
    paths: list[str] = []
    while args:
        arg = args.pop(0)
        if arg == "--historiography":
            historiography = True
        elif arg == "--normalize" and args:
            old, _, new = args.pop(0).partition("=")
            normalize.append((old, new))
        else:
            paths.append(arg)
    if len(paths) != 2:
        print(__doc__)
        return 2
    checked, problems, notes = compare(Path(paths[0]), Path(paths[1]),
                                       historiography=historiography, normalize=normalize)
    for line in problems:
        print(line)
    for line in notes:
        print(line)
    print(f"{checked} files compared, {len(problems)} differences")
    return 0 if not problems and checked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
