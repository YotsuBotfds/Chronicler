"""Lead-only helper that drafts one livelihoods sprint inverse layer.

Usage (from the repository root, after the landing's edits are in the work
tree and before committing the layer)::

    python scripts/testing/livelihoods_layer_tool.py NAME PARENT_REV PATH [PATH ...]

For each PATH it diffs the bytes at ``PARENT_REV`` (the source the layer
inverts to) against the work tree, emits literal ``(old, new)`` hunks with at
least three lines of context on both sides, widened until each ``new`` block
occurs exactly once, verifies that the exact inverse reproduces the parent
digest, and writes ``tests/fixtures/livelihoods_<NAME>_source_inverse.json``.
The output is a draft for review, not an automatic approval: read every hunk.
It never edits historical fixtures. It does not append NAME to ``LAYERS``.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = 3


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hunks(old: str, new: str) -> list[dict]:
    a, b = old.splitlines(keepends=True), new.splitlines(keepends=True)
    ops = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    spans = []
    for _, i1, i2, j1, j2 in ops:
        spans.append([i1, i2, j1, j2])
    patches = []
    k = 0
    while k < len(spans):
        i1, i2, j1, j2 = spans[k]
        ctx = CONTEXT
        while True:
            lo_a, lo_b = max(0, i1 - ctx), max(0, j1 - ctx)
            hi_a, hi_b = min(len(a), i2 + ctx), min(len(b), j2 + ctx)
            # Merge following spans whose context would overlap.
            while k + 1 < len(spans) and spans[k + 1][2] - ctx <= hi_b:
                k += 1
                i2, j2 = spans[k][1], spans[k][3]
                hi_a, hi_b = min(len(a), i2 + ctx), min(len(b), j2 + ctx)
            new_block = "".join(b[lo_b:hi_b])
            if new.count(new_block) == 1 or (lo_b == 0 and hi_b == len(b)):
                break
            ctx += 2
        patches.append({"old": "".join(a[lo_a:hi_a]), "new": new_block})
        k += 1
    return patches


def _invert(source: str, patches: list[dict]) -> str:
    for patch in reversed(patches):
        assert source.count(patch["new"]) == 1, "draft hunk is not unique"
        source = source.replace(patch["new"], patch["old"], 1)
    return source


def build(name: str, parent: str, paths: list[str]) -> dict:
    files = {}
    for path in paths:
        old = subprocess.run(["git", "show", f"{parent}:{path}"], cwd=ROOT, check=True,
                             capture_output=True).stdout.decode("utf-8")
        new = (ROOT / path).read_bytes().decode("utf-8")
        if old == new:
            continue
        patches = _hunks(old, new)
        assert _invert(new, patches) == old, f"inverse does not reproduce {path}"
        files[path] = {"sha256": _digest(old), "current_sha256": _digest(new), "patches": patches}
    return {"schema_version": 1, "layer": name, "parent": parent, "files": files}


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    name, parent, paths = argv[0], argv[1], argv[2:]
    parent = subprocess.run(["git", "rev-parse", parent], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    layer = build(name, parent, paths)
    out = ROOT / "tests/fixtures" / f"livelihoods_{name}_source_inverse.json"
    out.write_text(json.dumps(layer, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for path, row in layer["files"].items():
        print(f"{path}: {len(row['patches'])} hunks")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
