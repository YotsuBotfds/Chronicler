"""The refactor preflight separates known pins from references and history.

Everything here reads files only: no Git, no subprocess, no network.
"""
import hashlib
import json

import pytest

from scripts import refactor_preflight as pf


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def repo(tmp_path):
    pinned = _write(tmp_path, "src/chronicler/pinned.py", "VALUE = 1\n")
    _write(tmp_path, "src/chronicler/free.py", "def helper():\n    return 2\n")
    hashed = _write(tmp_path, "scripts/hashed.py", "print('hashed')\n")
    _write(tmp_path, "src/chronicler/older.py", "OLD = 3\n")
    _write(tmp_path, "src/chronicler/user.py", "from chronicler import free\nfrom chronicler.pinned import VALUE\n")
    _write(tmp_path, "tests/fixtures/demo_source_inverse.json", json.dumps({
        "base": "0" * 40, "head": "1" * 40,
        "files": {"src/chronicler/pinned.py": {"sha256": "2" * 64, "current_sha256": pinned, "patches": []}},
        "new_files": {}}))
    _write(tmp_path, "tests/fixtures/performance/run.json", json.dumps(
        {"provenance": {"source_sha256": {"src/chronicler/older.py": "3" * 64}}}))
    _write(tmp_path, "tests/test_hash.py", f'DIGEST = "{hashed}"\n')
    _write(tmp_path, "tests/test_patch.py",
           'def test_x(monkeypatch):\n    monkeypatch.setattr("chronicler.free.helper", lambda: 0)\n')
    _write(tmp_path, "tests/test_unassigned.py", "def test_y():\n    pass\n")
    _write(tmp_path, pf.SHARD_MANIFEST, json.dumps({
        "shards": {"0": ["tests/test_hash.py"], "1": ["tests/test_patch.py"]},
        "expected_skips": ["tests/test_patch.py::test_x"]}))
    _write(tmp_path, pf.ORACLE_RUNNER, 'CHUNKS = {"a": ["tests/test_hash.py"]}\n')
    _write(tmp_path, ".github/workflows/w.yml", "run: python scripts/hashed.py\n")
    _write(tmp_path, "docs/workflows/w.yml.in", "run: python scripts/hashed.py\n")
    _write(tmp_path, "docs/guide.md", "See `src/chronicler/free.py`.\n")
    return pf.Repo(tmp_path)


def _kinds(report, level=None):
    return {(f.level, f.kind) for f in report.findings if level is None or f.level == level}


def test_witness_listed_file_is_enforced(repo):
    report = pf.analyse(repo, "src/chronicler/pinned.py")
    assert ("enforced", "source witness") in _kinds(report)
    assert "matches the current file" in report.findings[0].detail
    assert report.verdict.startswith("enforced pins found")


def test_literal_current_digest_is_a_digest_pin(repo):
    report = pf.analyse(repo, "scripts/hashed.py")
    assert ("digest", "literal digest") in _kinds(report)
    assert ("reference", "workflow text") in _kinds(report)
    assert not _kinds(report, "enforced")
    assert report.verdict.startswith("current digest recorded")


def test_older_recorded_hash_is_historical_not_a_pin(repo):
    report = pf.analyse(repo, "src/chronicler/older.py")
    assert _kinds(report) == {("historical", "provenance hash")}
    assert report.verdict.startswith("no known pins")


def test_unpinned_file_reports_references_without_pins(repo):
    report = pf.analyse(repo, "src/chronicler/free.py")
    kinds = _kinds(report)
    assert ("reference", "importer") in kinds
    assert ("reference", "string target") in kinds
    assert ("reference", "docs") in kinds
    assert not _kinds(report, "enforced") and not _kinds(report, "digest")
    assert report.verdict.startswith("references found")


def test_test_modules_report_manifest_ownership_and_skips(repo):
    owned = pf.analyse(repo, "tests/test_patch.py")
    assert {("enforced", "native shard owner"), ("enforced", "expected skips")} <= _kinds(owned)
    unassigned = pf.analyse(repo, "tests/test_unassigned.py")
    assert any("not assigned" in f.detail for f in unassigned.findings)
    chunked = pf.analyse(repo, "tests/test_hash.py")
    assert ("enforced", "oracle chunk") in _kinds(chunked)


def test_workflow_and_its_pinned_copy_find_each_other(repo):
    assert ("enforced", "workflow copy") in _kinds(pf.analyse(repo, ".github/workflows/w.yml"))
    assert ("enforced", "workflow copy") in _kinds(pf.analyse(repo, "docs/workflows/w.yml.in"))


def test_absent_path_is_reported_not_guessed(repo):
    report = pf.analyse(repo, "src/chronicler/missing.py")
    assert not report.exists and report.sha256 is None
    assert report.verdict.startswith("no known pins")


def test_cli_json_exit_codes_and_move(repo, capsys):
    root = str(repo.root)
    assert pf.main(["--root", root, "--json", "src/chronicler/free.py"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["reports"][0]["path"] == "src/chronicler/free.py"
    assert data["not_covered"] == list(pf.NOT_COVERED)
    assert pf.main(["--root", root, "--fail-on-enforced", "src/chronicler/free.py"]) == 0
    assert pf.main(["--root", root, "--fail-on-enforced", "src/chronicler/pinned.py"]) == 1
    capsys.readouterr()
    assert pf.main(["--root", root, "--move", "src/chronicler/free.py:src/chronicler/tools/free.py"]) == 0
    text = capsys.readouterr().out
    assert "move to src/chronicler/tools/free.py" in text and "Not covered by this tool" in text
    with pytest.raises(SystemExit):
        pf.main(["--root", root, "--move", "no-colon"])


def test_preflight_never_writes(repo):
    before = {p: p.read_bytes() for p in repo.root.rglob("*") if p.is_file()}
    pf.main(["--root", str(repo.root), "--json", "src/chronicler/pinned.py", "tests/test_patch.py"])
    after = {p: p.read_bytes() for p in repo.root.rglob("*") if p.is_file()}
    assert before == after


def test_real_checkout_pinned_and_unpinned_files():
    repo = pf.Repo(pf.ROOT)
    witness = json.loads((pf.ROOT / "tests/fixtures/household_candidate_source_inverse.json").read_text())
    pinned = next(path for path, row in witness["files"].items()
                  if hashlib.sha256((pf.ROOT / path).read_bytes()).hexdigest() == row["current_sha256"])
    assert ("enforced", "source witness") in _kinds(pf.analyse(repo, pinned))
    skipped = pf.analyse(repo, "tests/test_m38b_regression.py")
    assert ("enforced", "expected skips") in _kinds(skipped)
    unpinned = pf.analyse(repo, "docs/README.md")
    assert not _kinds(unpinned, "enforced") and not _kinds(unpinned, "digest")


def test_frozen_pin_sources_match_manifest_and_pinned_set():
    # Integrity of the frozen witness snapshot: every copy hashes to its
    # MANIFEST digest and MANIFEST names exactly the witnessed path set.
    # Provenance against the freeze commit is checked by --verify (needs Git).
    from scripts.testing import freeze_pin_sources as freeze
    from scripts.testing import frozen_sources as frozen

    files = frozen.MANIFEST["files"]
    assert len(frozen.MANIFEST["freeze_commit"]) == 40
    assert sorted(files) == freeze.pinned_paths(pf.ROOT)
    copies = sorted(p.relative_to(frozen.FROZEN_ROOT).as_posix()
                    for p in frozen.FROZEN_ROOT.rglob("*") if p.is_file())
    assert copies == sorted(["MANIFEST.json", *(f"{rel}.txt" for rel in files)])
    for rel, digest in files.items():
        assert hashlib.sha256(frozen.frozen_bytes(rel)).hexdigest() == digest, rel
    with pytest.raises(FileNotFoundError, match="no frozen copy"):
        frozen.frozen_bytes("src/chronicler/not_frozen.py")
