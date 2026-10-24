#!/usr/bin/env python3
"""Prove that the in-world languages layer changes no simulation output.

``compare BASE_DIR NEW_DIR``
    Languages off (or a base without them): walk two run directories (one
    run, a batch of ``seed_*`` runs, or a gate batch) and compare every file.
    ``chronicle_bundle.json`` is compared after dropping
    ``metadata.generated_at`` (the wall-clock stamp); every other file must
    match byte for byte. Files present on only one side are reported.

``compare --languages BASE_DIR NEW_DIR``
    NEW ran with languages on. Every file must still match byte for byte
    (``state.json``, the historiography sidecar, memories,
    ``agent_events.arrow``, validation sidecars and reports) except the
    narration surfaces:

    * ``chronicle_bundle.json`` must be identical after dropping
      ``metadata.generated_at`` and the narration fields (``languages``,
      ``chronicle_entries``); the world state, every history snapshot, the
      event timeline, named events, era reflections, gap summaries, the
      historiography field and the rest of the metadata are compared;
    * ``chronicle.md`` (the narration) may differ;
    * ``<state>.languages.json`` sidecars exist only in NEW.

    It also checks NEW's field: every bundle carries it, every word's
    language and source resolve, every language's parent resolves, and every
    civ and region index it names is within the bundle's world.

``--normalize OLD=NEW`` (repeatable) replaces a path prefix in text files
before comparing (gate reports name their batch directory).

Run BASE with the base commit's source on ``PYTHONPATH`` (or this branch
without ``--languages``) and NEW with this branch, same interpreter, native
extension, arguments and ``PYTHONHASHSEED=0``. See
docs/integration/languages.md. Exit status 0 when identical.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

IGNORED_NAMES = frozenset({"run_manifest.json"})  # gate tooling, records its own flags
SIDECAR_SUFFIX = ".languages.json"
NARRATION_FIELDS = ("languages", "chronicle_entries")
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


def check_field(bundle_path: Path) -> list[str]:
    """NEW-side checks: the field exists and every id in it resolves."""
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    field = data.get("languages")
    if not isinstance(field, dict):
        return [f"no languages field: {bundle_path}"]
    problems: list[str] = []
    world = data.get("world_state", {})
    n_civs = len(world.get("civilizations", []))
    n_regions = len(world.get("regions", []))
    langs = {lang["id"] for lang in field.get("languages", [])}
    for lang in field.get("languages", []):
        if lang.get("parent") is not None and lang["parent"] not in langs:
            problems.append(f"language {lang['id']} has unknown parent {lang['parent']}")
    columns = field.get("word_columns", [])
    try:
        id_col, lang_col, kind_col, ref_col, src_col = (
            columns.index(c) for c in ("id", "lang", "kind", "ref", "source"))
    except ValueError:
        return [f"unknown word columns {columns}: {bundle_path}"]
    ids = {row[id_col] for row in field.get("words", [])}
    for row in field.get("words", []):
        if row[lang_col] not in langs:
            problems.append(f"word {row[id_col]} of unknown language {row[lang_col]}")
        if row[src_col] is not None and row[src_col] not in ids:
            problems.append(f"word {row[id_col]} has unknown source {row[src_col]}")
        if row[kind_col] == "civ" and not 0 <= row[ref_col] < n_civs:
            problems.append(f"word {row[id_col]} names unknown civ {row[ref_col]}")
        if row[kind_col] == "region" and not 0 <= row[ref_col] < n_regions:
            problems.append(f"word {row[id_col]} names unknown region {row[ref_col]}")
    return problems[:20]


def compare(base: Path, new: Path, *, languages: bool = False,
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
        if languages and rel in new_files and rel.name.endswith(SIDECAR_SUFFIX):
            sidecars += 1
            continue
        problems.append(f"only in {'base' if rel in base_files else 'new'}: {rel}")
    checked = narration_diffs = bundles = 0
    for rel in sorted(base_files & new_files):
        if rel.name in IGNORED_NAMES or rel.suffix in (".log",):
            continue
        a = _content(base / rel, drop_narration=languages, normalize=normalize)
        b = _content(new / rel, drop_narration=languages, normalize=normalize)
        checked += 1
        if rel.name == "chronicle_bundle.json":
            bundles += 1
            if languages:
                problems.extend(check_field(new / rel))
        if a != b:
            if languages and rel.name in NARRATION_FILES:
                narration_diffs += 1
                continue
            problems.append(f"differs: {rel} ({hashlib.sha256(a).hexdigest()[:12]} != "
                            f"{hashlib.sha256(b).hexdigest()[:12]})")
    if languages:
        notes.append(f"{sidecars} languages sidecars only in new (expected)")
        notes.append(f"{narration_diffs} narration files (chronicle.md) differ (allowed)")
        notes.append(f"{bundles} bundles identical apart from {', '.join(NARRATION_FIELDS)}")
        if bundles and not sidecars:
            problems.append("languages mode but NEW wrote no sidecar")
    return checked, problems, notes


def main(argv: list[str]) -> int:
    args = list(argv)
    if not args or args[0] != "compare":
        print(__doc__)
        return 2
    args.pop(0)
    languages = False
    normalize: list[tuple[str, str]] = []
    paths: list[str] = []
    while args:
        arg = args.pop(0)
        if arg == "--languages":
            languages = True
        elif arg == "--normalize" and args:
            old, _, new = args.pop(0).partition("=")
            normalize.append((old, new))
        else:
            paths.append(arg)
    if len(paths) != 2:
        print(__doc__)
        return 2
    checked, problems, notes = compare(Path(paths[0]), Path(paths[1]),
                                       languages=languages, normalize=normalize)
    for line in problems:
        print(line)
    for line in notes:
        print(line)
    print(f"{checked} files compared, {len(problems)} differences")
    return 0 if not problems and checked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
