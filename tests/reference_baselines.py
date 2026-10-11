"""Pinned historical test inputs that also work in shallow source checkouts."""
import hashlib
import json
from pathlib import Path


def baseline_root(commit):
    root = Path(__file__).resolve().parent / "fixtures/reference_baselines" / commit
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["commit"] == commit
    for entry in manifest["files"].values():
        raw = (root / entry["stored_path"]).read_bytes()
        assert len(raw) == entry["bytes"]
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
    return root


def baseline_source(commit, name):
    root = baseline_root(commit)
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    return (root / manifest["files"][name]["stored_path"]).read_text(encoding="utf-8")
