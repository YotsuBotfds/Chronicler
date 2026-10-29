"""Explicit NONDEFAULT pure contracts. UNRUN; no real filesystem/network/ZIP use.

Select this whole file only under a separately reviewed pure guard. Its filename
is outside test_*.py and *_test.py; existing CI registrations remain unchanged.
"""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import PurePosixPath
import stat
from types import SimpleNamespace as NS

import pytest
from scripts import ci_artifact_intake as C


def sha(body):
    return hashlib.sha256(body).hexdigest()


BINDING = C.Binding("owner/repository", "a" * 40, 101, 1)


class FakeFile:
    def __init__(self, inode, body=b"", *, kind="file", links=1):
        self.identity = C.Identity(7, inode)
        self.body = bytearray(body)
        self.kind, self.links, self.uid, self.mode = kind, links, 1000, 0o600


class FakeRoot:
    def __init__(self, path, inode, *, kind="dir"):
        self.path, self.identity, self.uid = path, C.Identity(7, inode), 1000
        self.kind, self.mode, self.closed = kind, 0o700, False
        self.files = {}


class FakeWriter:
    def __init__(self, fs, root, name, descriptor):
        self.fs, self.root, self.name, self.descriptor = fs, root, name, descriptor
        self.identity = root.files[name].identity

    def write(self, body):
        self.fs.events.append(("write", self.name, bytes(body)))
        self.fs.trip("write", self.name)
        accepted = len(body) - 1 if ("short", self.name) in self.fs.actions else len(body)
        self.root.files[self.name].body.extend(body[:accepted])
        self.fs.trip("write-after", self.name)
        return accepted

    def flush(self):
        self.fs.events.append(("flush", self.name))
        self.fs.trip("flush", self.name)

    def sync(self):
        self.fs.events.append(("sync", self.name))
        self.fs.trip("sync", self.name)

    def close(self):
        descriptor, self.descriptor = self.descriptor, -1
        assert descriptor >= 0
        self.fs.close_calls.append(descriptor)
        self.fs.events.append(("close-file", self.name, descriptor))
        self.fs.trip("close-before", self.name)
        del self.fs.handles[descriptor]
        self.fs.trip("close-after", self.name)


class FakeFS:
    def __init__(self):
        self.roots, self.events, self.handles, self.close_calls = {}, [], {}, []
        self.failures, self.actions = {}, set()
        self.next_inode, self.next_fd = 10, 40

    def trip(self, stage, name):
        error = self.failures.get((stage, name))
        if error is not None:
            raise error

    def allocate(self, name):
        descriptor = self.next_fd
        self.next_fd += 1
        self.handles[descriptor] = name
        return descriptor

    def create_root(self, path):
        self.events.append(("create-root", path))
        if path in self.roots:
            raise FileExistsError(path)
        root = FakeRoot(path, self.next_inode)
        self.next_inode += 1
        root.descriptor = self.allocate(path)
        self.roots[path] = root
        return root

    def check_root(self, handle, path, identity, *, readonly=False):
        self.events.append(("check-root", path))
        if (self.roots.get(path) is not handle or handle.closed or handle.kind != "dir"
                or handle.identity != identity or handle.uid != 1000
                or handle.mode != (0o555 if readonly else 0o700)):
            raise C.IntakeError("namespace")

    def list_infos(self, handle):
        return {n: C.FileInfo(f.identity, f.kind, f.links, f.uid, f.mode, len(f.body))
                for n, f in handle.files.items()}

    def create_file(self, handle, name):
        self.events.append(("create-file", name))
        self.trip("create", name)
        if name in handle.files:
            raise FileExistsError(name)
        handle.files[name] = FakeFile(self.next_inode)
        self.next_inode += 1
        return FakeWriter(self, handle, name, self.allocate(name))

    def inspect_file(self, handle, name, limit):
        self.trip("inspect", name)
        f = handle.files[name]
        if f.kind != "file" or f.links != 1 or f.uid != 1000 or len(f.body) > limit:
            raise C.IntakeError("namespace")
        return C.FilePin(name, f.identity, len(f.body), sha(bytes(f.body)), f.mode)

    def freeze_root(self, handle, expected):
        self.trip("freeze", "*")
        assert set(handle.files) == set(expected)
        assert all(handle.files[n].identity == identity for n, identity in expected.items())
        for f in handle.files.values():
            f.mode = 0o444
        handle.mode = 0o555
        self.trip("freeze-after", "*")

    def close_root(self, handle):
        if handle.closed:
            raise C.IntakeError("closed")
        handle.closed = True
        descriptor, handle.descriptor = handle.descriptor, -1
        self.close_calls.append(descriptor)
        self.trip("root-close-before", "*")
        del self.handles[descriptor]
        self.trip("root-close-after", "*")


def artifact(identity=1, body=b"opaque ZIP bytes", name=None):
    return C.Artifact(identity, name or "original-" + str(identity), len(body), sha(body))


def owned(body=b"opaque ZIP bytes"):
    fs = FakeFS()
    a = artifact(body=body)
    intake = C.create_intake("/owned", BINDING, [a], expected_count=1, fs=fs)
    return intake, fs, a, fs.roots["/owned"]


def write_events(fs):
    return [event for event in fs.events if event[0] in ("create-file", "write")]


def ingest(intake, a, body):
    return intake.ingest(intake.namespace, BINDING, a, io.BytesIO(body))


def test_fixed_caps_and_nondefault_test_scope():
    assert C.DEFAULT_ARTIFACTS == 9 and C.MAX_ARTIFACTS == 16
    assert C.ARCHIVE_CAP == 8 * 1024**2 and C.TOTAL_CAP == 24 * 1024**2
    assert C.CONTROL_RESERVE == C.MANIFEST_CAP == 1024**2
    assert C.NAME_CAP == 512 and C.CHUNK == 65536 and C.MAX_FILES == 35
    assert C.MAX_READ_CALLS == 4096


@pytest.mark.parametrize("kind", ["dir", "file", "symlink"])
def test_factory_refuses_every_existing_target_without_writing_it(kind):
    fs = FakeFS()
    old = FakeRoot("/old", 99, kind=kind)
    old.files["sealed.json"] = FakeFile(100, b"old original")
    fs.roots["/old"] = old
    before = bytes(old.files["sealed.json"].body)
    with pytest.raises(FileExistsError):
        C.create_intake("/old", BINDING, [artifact()], expected_count=1, fs=fs)
    assert write_events(fs) == []
    assert bytes(old.files["sealed.json"].body) == before
    assert old.files.keys() == {"sealed.json"}


@pytest.mark.parametrize("path", ["relative", "/", "/a/../b", "/a//b", "/a/./b", "/a\\b", "/a\0b"])
def test_namespace_path_refusal_happens_before_factory_io(path):
    fs = FakeFS()
    with pytest.raises(C.IntakeError):
        C.create_intake(path, BINDING, [artifact()], expected_count=1, fs=fs)
    assert fs.events == []


@pytest.mark.parametrize("field,value", [
    ("repository", "bad"), ("source", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"), ("run_id", True), ("attempt", 0),
])
def test_binding_types_and_identity_domains_are_closed(field, value):
    values = dict(repository="owner/repository", source="a" * 40, run_id=101, attempt=1)
    values[field] = value
    with pytest.raises(C.IntakeError):
        C.Binding(**values)


@pytest.mark.parametrize("field,value", [
    ("artifact_id", True), ("name", "../escape"), ("name", "a\\b"),
    ("name", "bad\0name"), ("size", 8_388_609),
    ("sha256", "SHA256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
])
def test_artifact_closed_domains_refuse_unbounded_or_alias_inputs(field, value):
    values = dict(artifact_id=1, name="original", size=0, sha256=sha(b""))
    values[field] = value
    with pytest.raises(C.IntakeError):
        C.Artifact(**values)


def test_name_bound_measures_utf8_bytes_and_keeps_exact_boundary():
    assert len(("é" * 256).encode("utf-8")) == 512
    assert C.Artifact(1, "é" * 256, 0, sha(b"")).name == "é" * 256
    with pytest.raises(C.IntakeError):
        C.Artifact(1, "é" * 257, 0, sha(b""))


@pytest.mark.parametrize("kind", ["duplicate-id", "duplicate-name", "wrong-count", "too-many", "aggregate"])
def test_closed_allowlist_and_cap_refusal_precede_namespace_creation(kind):
    fs = FakeFS()
    items, count = [artifact()], 1
    if kind == "duplicate-id":
        items, count = [artifact(), artifact(name="other")], 2
    elif kind == "duplicate-name":
        items, count = [artifact(), artifact(2, name="original-1")], 2
    elif kind == "wrong-count":
        count = 9
    elif kind == "too-many":
        items, count = [artifact(n) for n in range(1, 18)], 17
    else:
        items, count = [C.Artifact(n, "body-" + str(n), 3 * 1024**2, sha(b"")) for n in range(1, 10)], 9
    with pytest.raises(C.IntakeError):
        C.create_intake("/new", BINDING, items, expected_count=count, fs=fs)
    assert fs.events == [] and not fs.roots


def test_default_requires_exact_nine_and_names_are_not_output_paths():
    fs = FakeFS()
    items = [artifact(n, b"", "é" * 250 + str(n)) for n in range(1, 10)]
    cap = C.create_intake("/new", BINDING, items, fs=fs)
    assert list(fs.roots["/new"].files) == [C.CAPABILITY]
    marker = json.loads(fs.roots["/new"].files[C.CAPABILITY].body)
    assert [row["artifact_id"] for row in marker["artifacts"]] == list(range(1, 10))
    assert all(row["name"].startswith("é") for row in marker["artifacts"])
    cap.close()


def test_input_records_are_copied_and_namespace_is_factory_bound():
    fs = FakeFS()
    binding, a = replace(BINDING), artifact()
    cap = C.create_intake("/new", binding, [a], expected_count=1, fs=fs)
    original = cap.namespace
    object.__setattr__(binding, "run_id", 999)
    object.__setattr__(a, "name", "changed")
    assert cap.namespace == original
    marker = json.loads(fs.roots["/new"].files[C.CAPABILITY].body)
    assert marker["binding"]["run_id"] == 101 and marker["artifacts"][0]["name"] == "original-1"
    cap.close()


@pytest.mark.parametrize("changed", ["repository", "source", "run", "attempt", "path", "inode", "capability"])
def test_stale_binding_or_borrowed_destination_refuses_before_any_writer(changed):
    cap, fs, a, root = owned()
    destination, binding = cap.namespace, BINDING
    if changed == "repository":
        binding = replace(binding, repository="other/repository")
    elif changed == "source":
        binding = replace(binding, source="b" * 40)
    elif changed == "run":
        binding = replace(binding, run_id=102)
    elif changed == "attempt":
        binding = replace(binding, attempt=2)
    elif changed == "path":
        destination = replace(destination, path="/old")
    elif changed == "inode":
        destination = replace(destination, identity=C.Identity(7, 999))
    else:
        destination = replace(destination, capability_sha256="f" * 64)
    before = list(write_events(fs))
    with pytest.raises(C.IntakeError):
        cap.ingest(destination, binding, a, io.BytesIO(b"opaque ZIP bytes"))
    assert write_events(fs) == before
    assert list(root.files) == [C.CAPABILITY]
    cap.close()


@pytest.mark.parametrize("changed", ["root-replaced", "root-symlink", "marker-replaced", "marker-bytes", "hardlink", "foreign", "extra"])
def test_actual_namespace_or_marker_mismatch_refuses_before_archive_or_metadata_write(changed):
    cap, fs, a, root = owned()
    if changed == "root-replaced":
        fs.roots["/owned"] = FakeRoot("/owned", 999)
    elif changed == "root-symlink":
        root.kind = "symlink"
    elif changed == "marker-replaced":
        root.files[C.CAPABILITY] = FakeFile(999, root.files[C.CAPABILITY].body)
    elif changed == "marker-bytes":
        root.files[C.CAPABILITY].body[-1:] = b"x"
    elif changed == "hardlink":
        root.files[C.CAPABILITY].links = 2
    elif changed == "foreign":
        root.files[C.CAPABILITY].uid = 1001
    else:
        root.files["unknown.json"] = FakeFile(999, b"unknown")
    before = list(write_events(fs))
    with pytest.raises(C.IntakeError):
        ingest(cap, a, b"opaque ZIP bytes")
    assert write_events(fs) == before
    cap.close()


@pytest.mark.parametrize("kind", ["unknown-id", "name", "size", "digest", "mutated-bool"])
def test_unknown_or_mismatched_artifact_refuses_before_writer(kind):
    cap, fs, a, root = owned()
    if kind == "unknown-id":
        request = artifact(99)
    elif kind == "name":
        request = replace(a, name="other")
    elif kind == "size":
        request = replace(a, size=a.size + 1)
    elif kind == "digest":
        request = replace(a, sha256="b" * 64)
    else:
        request = replace(a)
        object.__setattr__(request, "artifact_id", True)
    before = list(write_events(fs))
    with pytest.raises(C.IntakeError):
        ingest(cap, request, b"opaque ZIP bytes")
    assert write_events(fs) == before and list(root.files) == [C.CAPABILITY]
    cap.close()


def test_opaque_binary_copy_is_exact_and_metadata_exclusive():
    body = b"not decoded as ZIP\x00\xff" * 4
    cap, fs, a, root = owned(body)
    p = ingest(cap, a, body)
    assert bytes(root.files["artifact-1.zip"].body) == body
    assert p.sha256 == sha(body) and p.size == len(body)
    row = json.loads(root.files["artifact-1.metadata.json"].body)
    assert row["binding"] == BINDING.record()
    assert row["artifact"] == a.record() and row["copy_status"] == "MATCHED_BYTES"
    assert not fs.handles.keys() - {root.descriptor}
    result = cap.finalize(cap.namespace, BINDING)
    assert result["status"] == "COMPLETE" and root.mode == 0o555
    assert len(result["files"]) == 5 and all(p.mode == 0o444 for p in result["files"])
    assert set(root.files) == {C.CAPABILITY, "artifact-1.zip", "artifact-1.metadata.json", C.MANIFEST, C.RESULT}
    assert not fs.handles


def test_zero_length_original_is_a_real_exclusive_body():
    cap, fs, a, root = owned(b"")
    ingest(cap, a, b"")
    assert root.files["artifact-1.zip"].body == b""
    assert cap.finalize(cap.namespace, BINDING)["status"] == "COMPLETE"


def test_duplicate_id_is_not_retried_or_rewritten():
    cap, fs, a, root = owned()
    ingest(cap, a, b"opaque ZIP bytes")
    before = list(write_events(fs))
    old_zip = bytes(root.files["artifact-1.zip"].body)
    old_meta = bytes(root.files["artifact-1.metadata.json"].body)
    with pytest.raises(C.IntakeError):
        ingest(cap, a, b"opaque ZIP bytes")
    assert write_events(fs) == before
    assert bytes(root.files["artifact-1.zip"].body) == old_zip
    assert bytes(root.files["artifact-1.metadata.json"].body) == old_meta
    assert cap.finalize(cap.namespace, BINDING)["status"] == "NEGATIVE"


@pytest.mark.parametrize("body,reason", [(b"short", "size"), (b"opaque ZIP bytes!", "size"), (b"wrong ZIP bytes!", "digest")])
def test_bad_size_or_digest_retains_original_negative_body_without_retry(body, reason):
    cap, fs, a, root = owned()
    with pytest.raises(C.IntakeError) as caught:
        ingest(cap, a, body)
    assert caught.value.code == reason
    partial = bytes(root.files["artifact-1.zip"].body)
    row = json.loads(root.files["artifact-1.metadata.json"].body)
    assert row["copy_status"] == "NEGATIVE" and row["first_fault"] == reason
    before = list(write_events(fs))
    with pytest.raises(C.IntakeError):
        ingest(cap, a, b"opaque ZIP bytes")
    assert write_events(fs) == before and bytes(root.files["artifact-1.zip"].body) == partial
    assert cap.finalize(cap.namespace, BINDING)["status"] == "NEGATIVE"


class ChunkReader:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.calls = self.close_calls = 0

    def read(self, amount):
        self.calls += 1
        value = self.chunks.pop(0) if self.chunks else b""
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.close_calls += 1


def test_midcopy_reader_error_preserves_identity_prefix_and_caller_reader_ownership():
    cap, fs, a, root = owned(b"abcdef")
    marker = OSError("reader sentinel")
    reader = ChunkReader([b"abc", marker])
    with pytest.raises(OSError) as caught:
        cap.ingest(cap.namespace, BINDING, a, reader)
    assert caught.value is marker and bytes(root.files["artifact-1.zip"].body) == b"abc"
    assert reader.close_calls == 0
    assert cap.first_fault == "read"
    assert cap.finalize(cap.namespace, BINDING)["status"] == "NEGATIVE"


@pytest.mark.parametrize("kind", ["nonbytes", "oversized", "read-count"])
def test_reader_protocol_refuses_before_denied_chunk_write(kind):
    cap, fs, a, root = owned(b"abcdef")
    reader = ChunkReader(["bad"] if kind == "nonbytes" else [b"x" * (C.CHUNK + 1)])
    if kind == "read-count":
        cap.close()
        class TinyReader:
            def read(self, amount):
                return b"a"
        a = artifact(body=b"a" * (C.MAX_READ_CALLS + 1))
        fs = FakeFS()
        cap = C.create_intake("/tiny", BINDING, [a], expected_count=1, fs=fs)
        root, reader = fs.roots["/tiny"], TinyReader()
    with pytest.raises(C.IntakeError):
        cap.ingest(cap.namespace, BINDING, a, reader)
    assert len(root.files["artifact-1.zip"].body) <= C.MAX_READ_CALLS
    assert cap.finalize(cap.namespace, BINDING)["status"] == "NEGATIVE"


@pytest.mark.parametrize("stage", ["write", "write-after", "flush", "sync", "close-before", "close-after", "short"])
def test_archive_io_failure_keeps_actual_body_and_first_error(stage):
    cap, fs, a, root = owned(b"abcdef")
    marker = OSError("archive sentinel")
    if stage == "short":
        fs.actions.add(("short", "artifact-1.zip"))
    else:
        fs.failures[(stage, "artifact-1.zip")] = marker
    with pytest.raises((OSError, C.IntakeError)) as caught:
        ingest(cap, a, b"abcdef")
    if stage != "short":
        assert caught.value is marker
    assert "artifact-1.zip" in root.files
    assert sum(event[:2] == ("create-file", "artifact-1.zip") for event in fs.events) == 1
    fs.failures.clear()
    result = cap.finalize(cap.namespace, BINDING)
    assert result["status"] == "NEGATIVE"


@pytest.mark.parametrize("stage", ["write", "write-after", "flush", "sync", "close-before", "close-after", "short"])
def test_metadata_failure_is_partial_exclusive_and_never_retried_or_complete(stage):
    cap, fs, a, root = owned()
    name = "artifact-1.metadata.json"
    marker = OSError("metadata sentinel")
    if stage == "short":
        fs.actions.add(("short", name))
    else:
        fs.failures[(stage, name)] = marker
    with pytest.raises((OSError, C.IntakeError)) as caught:
        ingest(cap, a, b"opaque ZIP bytes")
    if stage != "short":
        assert caught.value is marker
    partial = bytes(root.files[name].body)
    assert sum(e[:2] == ("create-file", name) for e in fs.events) == 1
    fs.failures.clear()
    result = cap.finalize(cap.namespace, BINDING)
    assert result["status"] == "NEGATIVE" and bytes(root.files[name].body) == partial


def test_reader_first_error_is_not_masked_by_writer_close_or_negative_metadata_error():
    cap, fs, a, root = owned(b"abcdef")
    marker = OSError("primary read")
    fs.failures[("close-before", "artifact-1.zip")] = OSError("secondary close")
    fs.failures[("write", "artifact-1.metadata.json")] = OSError("secondary metadata")
    with pytest.raises(OSError) as caught:
        cap.ingest(cap.namespace, BINDING, a, ChunkReader([b"abc", marker]))
    assert caught.value is marker
    assert len(fs.close_calls) == len(set(fs.close_calls))
    assert cap.first_fault == "read" and bytes(root.files["artifact-1.zip"].body) == b"abc"
    fs.failures.clear()
    assert cap.finalize(cap.namespace, BINDING)["status"] == "NEGATIVE"


def test_interruption_closes_output_once_and_never_replays_or_calls_reader_close():
    cap, fs, a, root = owned(b"abcdef")
    marker = KeyboardInterrupt()
    reader = ChunkReader([b"abc", marker])
    with pytest.raises(KeyboardInterrupt) as caught:
        cap.ingest(cap.namespace, BINDING, a, reader)
    assert caught.value is marker and reader.close_calls == 0
    assert len(fs.close_calls) == len(set(fs.close_calls))
    assert "artifact-1.metadata.json" not in root.files
    assert cap.finalize(cap.namespace, BINDING)["status"] == "NEGATIVE"


def test_missing_artifact_finalize_is_finite_negative_and_closes_ingress():
    cap, fs, a, root = owned()
    result = cap.finalize(cap.namespace, BINDING)
    assert result["status"] == "NEGATIVE"
    manifest = json.loads(root.files[C.MANIFEST].body)
    assert manifest["missing"] == [a.artifact_id] and len(result["files"]) == 3
    before = list(write_events(fs))
    with pytest.raises(C.IntakeError):
        ingest(cap, a, b"opaque ZIP bytes")
    assert write_events(fs) == before


@pytest.mark.parametrize("name", ["intake-manifest.json", "intake-result.json"])
@pytest.mark.parametrize("stage", ["write", "sync", "close-after"])
def test_finalization_metadata_error_never_returns_complete_and_preserves_partial(name, stage):
    cap, fs, a, root = owned()
    ingest(cap, a, b"opaque ZIP bytes")
    marker = OSError("terminal metadata")
    fs.failures[(stage, name)] = marker
    with pytest.raises(OSError) as caught:
        cap.finalize(cap.namespace, BINDING)
    assert caught.value is marker and name in root.files
    before = list(write_events(fs))
    with pytest.raises(C.IntakeError):
        ingest(cap, a, b"opaque ZIP bytes")
    assert write_events(fs) == before
    assert len(fs.close_calls) == len(set(fs.close_calls))


@pytest.mark.parametrize("stage", ["freeze", "freeze-after", "root-close-before", "root-close-after"])
def test_readonly_or_root_close_failure_is_not_a_positive_return_or_retry(stage):
    cap, fs, a, root = owned()
    ingest(cap, a, b"opaque ZIP bytes")
    marker = OSError("freeze/close")
    fs.failures[(stage, "*")] = marker
    with pytest.raises(OSError) as caught:
        cap.finalize(cap.namespace, BINDING)
    assert caught.value is marker
    assert C.RESULT in root.files  # readable marker alone is not completion authority
    before = list(fs.close_calls)
    cap.close()
    assert fs.close_calls == before


def test_changed_completed_body_or_unknown_entry_blocks_finalization_before_manifest_write():
    cap, fs, a, root = owned()
    ingest(cap, a, b"opaque ZIP bytes")
    root.files["artifact-1.zip"].body[0] ^= 1
    before = list(write_events(fs))
    with pytest.raises(C.IntakeError):
        cap.finalize(cap.namespace, BINDING)
    assert write_events(fs) == before and C.MANIFEST not in root.files


def test_all_sixteen_artifacts_have_exact_inventory_and_unchanged_total_caps():
    fs = FakeFS()
    specs = [artifact(n, bytes([n])) for n in range(1, 17)]
    cap = C.create_intake("/sixteen", BINDING, list(reversed(specs)), expected_count=16, fs=fs)
    for a in specs:
        ingest(cap, a, bytes([a.artifact_id]))
    result = cap.finalize(cap.namespace, BINDING)
    assert result["status"] == "COMPLETE" and len(result["files"]) == C.MAX_FILES
    assert sum(p.size for p in result["files"]) <= C.TOTAL_CAP
    assert result["metadata_debited"] <= C.CONTROL_RESERVE
    manifest = json.loads(fs.roots["/sixteen"].files[C.MANIFEST].body)
    assert len(manifest["inventory"]) == 33
    assert manifest["required_file_mode"] == 0o444 and manifest["required_root_mode"] == 0o555


class FakeOS:
    """Root-acquisition descriptor model only; no real syscalls."""
    name = "posix"
    O_RDONLY, O_WRONLY, O_CREAT, O_EXCL = 0, 1, 64, 128
    O_DIRECTORY, O_NOFOLLOW, O_CLOEXEC = 65536, 131072, 524288

    def __init__(self):
        self.paths = {"/": 1, "/a": 2, "/a/b": 3}
        self.handles, self.closes = {40: "/unrelated"}, []
        self.next_fd = 41
        self.fail_open = self.fail_close = self.fail_fstat = None
        self.marker = OSError("first acquisition")
        self.close_after = False

    def geteuid(self):
        return 1000

    def path(self, name, dir_fd):
        return name if name.startswith("/") else str(PurePosixPath(self.handles[dir_fd]) / name)

    def open(self, name, flags, mode=0o600, *, dir_fd=None):
        path = self.path(name, dir_fd)
        if path == self.fail_open:
            raise self.marker
        if path not in self.paths:
            raise FileNotFoundError(path)
        descriptor = self.next_fd
        self.next_fd += 1
        self.handles[descriptor] = path
        return descriptor

    def mkdir(self, name, mode=0o700, *, dir_fd):
        path = self.path(name, dir_fd)
        if path in self.paths:
            raise FileExistsError(path)
        self.paths[path] = 4

    def fstat(self, descriptor):
        path = self.handles[descriptor]
        if path == self.fail_fstat:
            raise self.marker
        return NS(st_dev=7, st_ino=self.paths[path], st_mode=stat.S_IFDIR | 0o700,
                  st_uid=1000, st_nlink=2, st_size=0)

    def close(self, descriptor):
        path = self.handles[descriptor]
        self.closes.append(descriptor)
        if path == self.fail_close:
            if self.close_after:
                del self.handles[descriptor]
            raise self.marker
        del self.handles[descriptor]


@pytest.mark.parametrize("path", ["/", "/a", "/a/b", "/a/b/new"])
def test_posix_backend_root_acquisition_failure_preserves_first_exception_and_known_fd_ownership(path):
    o = FakeOS()
    o.fail_open = path
    with pytest.raises(OSError) as caught:
        C.PosixFS(os_module=o).create_root("/a/b/new")
    assert caught.value is o.marker and o.handles == {40: "/unrelated"}
    assert len(o.closes) == len(set(o.closes))


@pytest.mark.parametrize("path", ["/", "/a", "/a/b"])
@pytest.mark.parametrize("after", [False, True])
def test_posix_backend_handoff_and_final_close_never_retry_unknown_descriptor(path, after):
    o = FakeOS()
    o.fail_close, o.close_after = path, after
    with pytest.raises(OSError) as caught:
        C.PosixFS(os_module=o).create_root("/a/b/new")
    assert caught.value is o.marker and len(o.closes) == len(set(o.closes))
    unknown = set(o.handles) - {40}
    assert len(unknown) == (0 if after else 1)
    assert all(o.handles[fd] == path for fd in unknown)


def test_posix_backend_root_fstat_error_closes_root_and_parent_without_touching_baseline():
    o = FakeOS()
    o.fail_fstat = "/a/b/new"
    with pytest.raises(OSError) as caught:
        C.PosixFS(os_module=o).create_root("/a/b/new")
    assert caught.value is o.marker and o.handles == {40: "/unrelated"}
    assert len(o.closes) == len(set(o.closes))


def test_posix_backend_requires_its_factory_handle_before_any_file_open():
    o = FakeOS()
    backend = C.PosixFS(os_module=o)
    with pytest.raises(C.IntakeError):
        backend.create_file(NS(descriptor=40), "artifact-1.zip")
    assert o.handles == {40: "/unrelated"} and o.closes == []


def test_root_switch_during_copy_stops_before_next_payload_or_metadata_write():
    cap, fs, a, original = owned(b"abcdef")
    borrowed = FakeRoot("/owned", 999)
    borrowed.files["old-metadata.json"] = FakeFile(1000, b"sealed original")
    class SwitchingReader:
        def __init__(self):
            self.calls = 0
        def read(self, amount):
            self.calls += 1
            if self.calls == 1:
                return b"abc"
            fs.roots["/owned"] = borrowed
            return b"def"
    with pytest.raises(C.IntakeError):
        cap.ingest(cap.namespace, BINDING, a, SwitchingReader())
    assert bytes(original.files["artifact-1.zip"].body) == b"abc"
    assert bytes(borrowed.files["old-metadata.json"].body) == b"sealed original"
    assert set(borrowed.files) == {"old-metadata.json"}
    assert "artifact-1.metadata.json" not in original.files
    cap.close()


def test_root_switch_after_archive_readback_stops_before_metadata_writer():
    cap, fs, a, original = owned()
    borrowed = FakeRoot("/owned", 999)
    borrowed.files["sealed.json"] = FakeFile(1000, b"old")
    inspect = fs.inspect_file
    def switched(handle, name, limit):
        result = inspect(handle, name, limit)
        if name == "artifact-1.zip":
            fs.roots["/owned"] = borrowed
        return result
    fs.inspect_file = switched
    with pytest.raises(C.IntakeError):
        ingest(cap, a, b"opaque ZIP bytes")
    assert "artifact-1.metadata.json" not in original.files
    assert set(borrowed.files) == {"sealed.json"}
    assert bytes(borrowed.files["sealed.json"].body) == b"old"
    cap.close()


@pytest.mark.parametrize("mapping", ["ids", "pins"])
@pytest.mark.parametrize("when", ["before", "after"])
def test_writer_registration_failure_closes_untransferred_writer_once(mapping, when):
    cap, fs, a, root = owned()
    marker = MemoryError("registration sentinel")
    class FailingMap(dict):
        def __setitem__(self, key, value):
            if key == "artifact-1.zip":
                if when == "after":
                    super().__setitem__(key, value)
                raise marker
            super().__setitem__(key, value)
    if mapping == "ids":
        cap._ids = FailingMap(cap._ids)
    else:
        cap._pins = FailingMap(cap._pins)
    baseline = dict(fs.handles)
    with pytest.raises(MemoryError) as caught:
        ingest(cap, a, b"opaque ZIP bytes")
    assert caught.value is marker
    assert fs.handles == baseline
    assert bytes(root.files["artifact-1.zip"].body) == b""
    assert len(fs.close_calls) == len(set(fs.close_calls))
    cap.close()


