"""Bounded metadata copying contracts; no worlds, native runtime or network."""
import hashlib
import importlib.util
import json
from pathlib import Path
import os

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def stager():
    spec = importlib.util.spec_from_file_location("natural_light_test", ROOT / "scripts/stage_research_natural_light.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def put(root, name, raw):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def result(output):
    return json.loads((output / "index.json").read_bytes())


def assert_bounded(stager, output):
    files = [p for p in output.rglob("*") if p.is_file()]
    assert len(files) <= stager.MAX_FILES
    assert sum(p.stat().st_size for p in files) <= stager.MAX_BYTES


def test_allowlist_is_closed_finite_metadata_only(stager):
    assert len(stager.ALLOWLIST) == len(set(stager.ALLOWLIST)) <= 31
    assert stager.MAX_BYTES == 8 * 1024**2 and stager.MAX_FILES == 32
    assert all(Path(n).suffix in (".json", ".xml") for n in stager.ALLOWLIST)
    assert not any(n.startswith("/") or ".." in Path(n).parts or "*" in n for n in stager.ALLOWLIST)


def test_exact_bytes_missing_rows_and_total_including_index_without_scientific_parsing(stager, tmp_path):
    source = tmp_path / "runner"
    source.mkdir()
    # Deliberately invalid JSON is opaque copied evidence, never a parsed verdict.
    payload = b'{"qualified": false, "odd": -0.0, "overflow":1e9999,\n'
    put(source, "natural-research-readout/readout.json", payload)
    put(source, "natural-research-contracts/junit.xml", b"<testsuite failures='1'/>\r\n")
    put(source, "natural-research-evidence/state.json", b"raw simulation excluded")
    put(source, "natural-research-evidence/native.agent.0-final.bin", b"native excluded")
    put(source, "natural-research-wheel/official-artifact.zip", b"ZIP excluded")
    put(source, "natural-research-wheel/package.whl", b"wheel excluded")
    put(source, "natural-research-evidence/events.arrow", b"Arrow excluded")
    output = source / stager.OUTPUT_NAME
    assert stager.stage(source, output) == 0
    index = result(output)
    assert index["staging_complete"] is True and index["scientific_qualification"] is False
    assert (output / "natural-research-readout/readout.json").read_bytes() == payload
    rows = {r["path"]: r for r in index["files"]}
    assert set(rows) == set(stager.ALLOWLIST)
    assert rows["natural-research-readout/readout.json"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert rows["natural-research-wheel/failure.json"] == {"path": "natural-research-wheel/failure.json", "status": "missing"}
    actual = [p for p in output.rglob("*") if p.is_file()]
    assert index["file_count"] == len(actual) == 3
    assert index["total_bytes"] == sum(p.stat().st_size for p in actual)
    assert index["index_bytes"] == (output / "index.json").stat().st_size
    assert {p.suffix for p in actual} <= {".json", ".xml"}
    assert_bounded(stager, output)


def test_real_eight_mib_and_32_file_admission_boundaries_include_index(stager):
    # Integer admission checks exercise the actual fixed caps without allocating
    # or copying an eight-megabyte fixture on the shared runner filesystem.
    stager.admit(8 * 1024**2 - 1000, 1000, 32)
    with pytest.raises(stager.StagingRefused):
        stager.admit(8 * 1024**2 - 1000, 1001, 32)
    with pytest.raises(stager.StagingRefused):
        stager.admit(0, 1000, 33)


def test_aggregate_oversize_is_rejected_before_hashing_or_any_copy(stager, tmp_path, monkeypatch):
    source = tmp_path / "runner"
    source.mkdir()
    names = stager.ALLOWLIST[:2]
    for name in names:
        put(source, name, b"x" * 200)
    monkeypatch.setattr(stager, "MAX_BYTES", 350)
    original = stager.source_record
    def observe(root_fd, name, *, hashing=True):
        assert not hashing, "all lengths must be admitted before reading payloads"
        return original(root_fd, name, hashing=False)
    monkeypatch.setattr(stager, "source_record", observe)
    monkeypatch.setattr(stager, "copy_file", lambda *a: pytest.fail("oversize cannot copy any source"))
    output = source / stager.OUTPUT_NAME
    assert stager.stage(source, output) == 1
    assert result(output)["staging_complete"] is False
    assert [p.name for p in output.iterdir()] == ["index.json"]
    assert_bounded(stager, output)


def test_index_bytes_are_admitted_before_copy_even_when_payload_fits(stager, tmp_path, monkeypatch):
    source = tmp_path / "runner"
    source.mkdir()
    name = stager.ALLOWLIST[0]
    payload = b"x" * 100
    put(source, name, payload)
    monkeypatch.setattr(stager, "ALLOWLIST", (name,))
    record = dict(path=name, status="copied", bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    # Use a small synthetic cap, retaining the real index serialization rules.
    for _ in range(4):
        monkeypatch.setattr(stager, "MAX_BYTES", len(payload) + len(stager.index_bytes([record])) - 1)
    monkeypatch.setattr(stager, "copy_file", lambda *a: pytest.fail("index was not admitted"))
    output = source / stager.OUTPUT_NAME
    assert stager.stage(source, output) == 1
    assert result(output)["staging_complete"] is False
    assert not (output / name).exists()
    assert_bounded(stager, output)


@pytest.mark.parametrize("kind", ["leaf_link", "parent_link", "fifo"])
def test_selected_paths_never_follow_links_or_read_special_files(stager, tmp_path, kind):
    source, outside = tmp_path / "runner", tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    sentinel = put(outside, "readout.json", b"must not be copied")
    parent = source / "natural-research-readout"
    if kind == "parent_link":
        parent.symlink_to(outside, target_is_directory=True)
    else:
        parent.mkdir()
        if kind == "leaf_link":
            (parent / "readout.json").symlink_to(sentinel)
        else:
            os.mkfifo(parent / "readout.json")
    output = source / stager.OUTPUT_NAME
    assert stager.stage(source, output) == 1
    assert result(output)["staging_complete"] is False
    assert sentinel.read_bytes() == b"must not be copied"
    assert not (output / "natural-research-readout/readout.json").exists()
    assert_bounded(stager, output)


@pytest.mark.parametrize("change", ["source_bytes", "newly_present", "destination_bytes", "replace_source"])
def test_changes_during_copy_refuse_positive_publication_and_keep_partial_copies(stager, tmp_path, monkeypatch, change):
    source = tmp_path / "runner"
    source.mkdir()
    name = "natural-research-readout/readout.json"
    original_path = put(source, name, b"original raw verdict bytes")
    output = source / stager.OUTPUT_NAME
    original_copy = stager.copy_file
    def copy(*args):
        original_copy(*args)
        if change == "source_bytes":
            original_path.write_bytes(b"changed source verdict bytes")
        elif change == "newly_present":
            put(source, "natural-research-wheel/failure.json", b"newly appeared")
        elif change == "destination_bytes":
            (output / name).write_bytes(b"changed copied bytes")
        else:
            replacement = put(source, "replacement", original_path.read_bytes())
            os.replace(replacement, original_path)
    monkeypatch.setattr(stager, "copy_file", copy)
    assert stager.stage(source, output) == 1
    assert result(output)["staging_complete"] is False
    assert (output / name).exists()
    assert not (output / "pending-index.json").exists()
    assert_bounded(stager, output)


def test_source_change_during_final_index_publication_invalidates_positive(stager, tmp_path, monkeypatch):
    source = tmp_path / "runner"
    source.mkdir()
    path = put(source, "natural-research-readout/readout.json", b"original")
    output = source / stager.OUTPUT_NAME
    original_write = stager.write_index
    def publish(*args):
        original_write(*args)
        path.write_bytes(b"changed during index publication")
    monkeypatch.setattr(stager, "write_index", publish)
    assert stager.stage(source, output) == 1
    assert result(output)["staging_complete"] is False
    assert (output / "natural-research-readout/readout.json").read_bytes() == b"original"
    assert_bounded(stager, output)


def test_fresh_output_and_exact_runner_temp_cli_are_required(stager, tmp_path, monkeypatch):
    source = tmp_path / "runner"
    source.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(source))
    with pytest.raises(stager.StagingRefused):
        stager.main(["--source-root", str(tmp_path), "--output-root", str(tmp_path / stager.OUTPUT_NAME)])
    with pytest.raises(stager.StagingRefused):
        stager.stage(source, source / "elsewhere")
    outside = tmp_path / "outside"
    outside.mkdir()
    output = source / stager.OUTPUT_NAME
    output.symlink_to(outside, target_is_directory=True)
    with pytest.raises(stager.StagingRefused):
        stager.stage(source, output)
    assert not list(outside.iterdir())


def test_corrupted_published_index_bytes_cannot_report_success(stager, tmp_path, monkeypatch):
    source = tmp_path / "runner"
    source.mkdir()
    output = source / stager.OUTPUT_NAME
    original = stager.write_index
    def corrupt(*args):
        original(*args)
        (output / "index.json").write_bytes(b"changed index bytes")
    monkeypatch.setattr(stager, "write_index", corrupt)
    assert stager.stage(source, output) == 1
    assert result(output)["staging_complete"] is False
    assert_bounded(stager, output)


def test_negative_index_writer_does_not_block_or_write_to_an_injected_fifo(stager, tmp_path, monkeypatch):
    source = tmp_path / "runner"
    source.mkdir()
    put(source, stager.ALLOWLIST[0], b"x" * 200)
    monkeypatch.setattr(stager, "MAX_BYTES", 100)  # Refuse before any source copy.
    output = source / stager.OUTPUT_NAME
    original_open = stager.os.open
    readers = []
    def injected(path, flags, *args, **kwargs):
        if path == "index.json" and flags & os.O_WRONLY:
            assert flags & os.O_NONBLOCK, "the refusal path must never block on special files"
            assert not flags & os.O_TRUNC, "special-file type must be checked before truncation"
            os.mkfifo("index.json", dir_fd=kwargs["dir_fd"])
            readers.append(original_open("index.json", os.O_RDONLY | os.O_NONBLOCK, dir_fd=kwargs["dir_fd"]))
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(stager.os, "open", injected)
    # Permit the fixed small negative record while still forcing preflight failure.
    original_encoded = stager.encoded
    monkeypatch.setattr(stager, "encoded", lambda value: b"refused\n" if value.get("staging_complete") is False else original_encoded(value))
    try:
        assert stager.stage(source, output) == 1
        assert (output / "index.json").is_fifo()
        assert os.read(readers[0], 64) == b""  # No metadata was written to it.
    finally:
        for fd in readers:
            os.close(fd)


@pytest.mark.parametrize("mutation", ["payload_same_length", "extra_file", "extra_empty_directory", "extra_link", "extra_fifo", "known_directory_link"])
def test_final_publication_rechecks_payload_hashes_and_closed_output_inventory(stager, tmp_path, monkeypatch, mutation):
    source = tmp_path / "runner"
    source.mkdir()
    name = "natural-research-readout/readout.json"
    original_payload = b"original verdict bytes"
    put(source, name, original_payload)
    outside = tmp_path / "outside"
    outside.mkdir()
    put(outside, "readout.json", b"outside content never selected")
    output = source / stager.OUTPUT_NAME
    original_publish = stager.write_index
    original_open = stager.os.open
    def guarded_open(path, flags, *args, **kwargs):
        assert path != "unexpected-directory", "unexpected trees must be rejected before descent"
        return original_open(path, flags, *args, **kwargs)
    def publish(*args):
        original_publish(*args)
        if mutation == "payload_same_length":
            (output / name).write_bytes(b"X" * len(original_payload))
        elif mutation == "extra_file":
            put(output, "unexpected.json", b"extra")
        elif mutation == "extra_empty_directory":
            (output / "unexpected-directory").mkdir()
        elif mutation == "extra_link":
            (output / "unexpected-link").symlink_to(outside, target_is_directory=True)
        elif mutation == "extra_fifo":
            os.mkfifo(output / "unexpected-fifo")
        else:
            os.rename(output / "natural-research-readout", output / "retained-copies")
            (output / "natural-research-readout").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(stager, "write_index", publish)
    monkeypatch.setattr(stager.os, "open", guarded_open)
    assert stager.stage(source, output) == 1
    assert result(output)["staging_complete"] is False
    assert (source / name).read_bytes() == original_payload
    assert (outside / "readout.json").read_bytes() == b"outside content never selected"


@pytest.mark.parametrize("replacement", ["source_root", "output_root"])
def test_final_publication_requires_original_root_directory_bindings(stager, tmp_path, monkeypatch, replacement):
    source = tmp_path / "runner"
    source.mkdir()
    name = "natural-research-readout/readout.json"
    put(source, name, b"raw bytes")
    output = source / stager.OUTPUT_NAME
    original_publish = stager.write_index
    retained = tmp_path / "retained-runner" if replacement == "source_root" else source / "retained-light"
    def publish(*args):
        original_publish(*args)
        if replacement == "source_root":
            os.rename(source, retained)
            source.mkdir()
        else:
            os.rename(output, retained)
            output.mkdir()
    monkeypatch.setattr(stager, "write_index", publish)
    assert stager.stage(source, output) == 1
    actual_output = retained / stager.OUTPUT_NAME if replacement == "source_root" else retained
    assert result(actual_output)["staging_complete"] is False
    assert (actual_output / name).read_bytes() == b"raw bytes"
    assert not (output / "index.json").exists()
