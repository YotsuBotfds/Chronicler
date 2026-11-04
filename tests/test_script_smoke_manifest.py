"""Static checks of scripts/testing/script_smoke_manifest.json.

Reads files only: no child process, network or native import, so it runs in
the bounded offline lane. scripts/testing/script_smoke.py executes the safe
entries in a detached temporary worktree.
"""
import json
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scripts" / "testing" / "script_smoke_manifest.json"
ARCHIVE = ROOT / "scripts" / "archive"
FIELDS = {"invocation", "expected_exit", "safe_to_run", "mutates", "native", "network", "inputs",
          "fixture_outputs", "note"}
NATIVE = {"none", "optional", "required", "import"}


def _unique(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"), object_pairs_hook=_unique)


def _is_canonical(path: str) -> bool:
    pure = PurePosixPath(path)
    return (not pure.is_absolute() and "\\" not in path and "\0" not in path
            and pure.as_posix() == path and ".." not in pure.parts and "." not in pure.parts)


def test_duplicate_keys_are_rejected():
    with pytest.raises(ValueError):
        json.loads('{"scripts": {"a": {}, "a": {}}}', object_pairs_hook=_unique)


def test_top_level_shape(manifest):
    assert set(manifest) == {"schema_version", "scope", "scripts"}
    assert type(manifest["schema_version"]) is int and manifest["schema_version"] == 1
    assert isinstance(manifest["scope"], str) and manifest["scope"].strip()
    assert isinstance(manifest["scripts"], dict) and manifest["scripts"]
    assert list(manifest["scripts"]) == sorted(manifest["scripts"])


def test_every_archived_script_has_exactly_one_entry(manifest):
    archived = {f"scripts/archive/{p.name}" for p in ARCHIVE.iterdir() if p.name != "README.md"}
    listed = {path for path in manifest["scripts"] if path.startswith("scripts/archive/")}
    assert listed == archived
    names = [PurePosixPath(path).name for path in manifest["scripts"]]
    assert len(names) == len(set(names))


def test_no_stale_entries(manifest):
    for path in manifest["scripts"]:
        assert _is_canonical(path), path
        assert PurePosixPath(path).suffix in (".py", ".sh"), path
        assert (ROOT / path).is_file(), f"stale entry {path}"
        if not path.startswith("scripts/archive/"):
            # Outside the archive only fixture generators that left it are listed.
            assert PurePosixPath(path).parent == PurePosixPath("scripts"), path
            assert manifest["scripts"][path]["fixture_outputs"], path


def test_entries_are_well_formed(manifest):
    for path, entry in manifest["scripts"].items():
        assert isinstance(entry, dict) and set(entry) == FIELDS, path
        assert isinstance(entry["invocation"], list), path
        assert all(isinstance(a, str) and a and "\0" not in a for a in entry["invocation"]), path
        assert type(entry["expected_exit"]) is int and 0 <= entry["expected_exit"] <= 255, path
        for flag in ("safe_to_run", "mutates", "network"):
            assert type(entry[flag]) is bool, (path, flag)
        assert entry["native"] in NATIVE, path
        assert isinstance(entry["inputs"], list), path
        assert all(isinstance(item, str) and item.strip() for item in entry["inputs"]), path
        assert isinstance(entry["note"], str) and entry["note"].strip(), path


def test_fixture_outputs_are_checked_in_files(manifest):
    for path, entry in manifest["scripts"].items():
        outputs = entry["fixture_outputs"]
        assert isinstance(outputs, list) and len(outputs) == len(set(outputs)), path
        for output in outputs:
            assert isinstance(output, str) and _is_canonical(output), (path, output)
            assert (ROOT / output).is_file(), (path, output)


def test_unsafe_invocations_are_never_marked_safe(manifest):
    for path, entry in manifest["scripts"].items():
        if entry["mutates"] or entry["network"] or entry["native"] == "import":
            assert entry["safe_to_run"] is False, path
