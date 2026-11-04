"""Unregistered source-only fake contracts; no World/model/native/Arrow use.

These tests have not been run. Their future guarded selection needs a separate
registration/review/grant. FakeOS replaces only this module's os reference, not
Python's interpreter-wide filesystem functions; no real output root is created.
"""
from dataclasses import replace
import os
from pathlib import Path, PurePosixPath
import stat
from types import SimpleNamespace

import pytest

from chronicler import artifact_budget as budget_module
from chronicler import artifact_io
from chronicler.artifact_budget import (
    ArtifactBudget, ArtifactBudgetError, MonotonicArtifactLedger,
    ORDINARY_BYTE_CAP, CARE_BYTE_CAP, TOTAL_BYTE_CAP,
    ORDINARY_TERMINAL_RESERVE, CARE_METADATA_RESERVE,
)


class FakeStream:
    def __init__(self, filesystem, descriptor):
        self.fs = filesystem
        self.descriptor = descriptor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def close(self):
        self.fs.close(self.descriptor)
        if self.fs.fail_at == "close":
            raise OSError("injected close")

    def write(self, data):
        path = self.fs.handles[self.descriptor]
        self.fs.events.append(("write", path, bytes(data)))
        if self.fs.fail_at == "write":
            raise OSError("injected write")
        count = len(data) - 1 if self.fs.fail_at == "short" else len(data)
        self.fs.files[path]["body"].extend(data[:count])
        return count

    def flush(self):
        self.fs.events.append(("flush", self.descriptor))
        if self.fs.fail_at == "flush":
            raise OSError("injected flush")

    def fileno(self):
        return self.descriptor


class FakeOS:
    name = "posix"
    linesep = "\n"
    fspath = staticmethod(os.fspath)

    def __init__(self):
        self.directories = {"/": self.info(directory=True, inode=1, mode=0o755)}
        self.files = {}
        self.handles = {}
        self.next_fd = 40
        self.next_inode = 2
        self.events = []
        self.fail_at = None

    def __getattr__(self, name):
        if name.startswith("O_"):
            return getattr(os, name)
        raise AttributeError(name)

    @staticmethod
    def info(*, directory=False, inode=1, mode=0o600, links=1):
        return SimpleNamespace(st_dev=7, st_ino=inode, st_uid=1000,
                               st_mode=(stat.S_IFDIR if directory else stat.S_IFREG) | mode,
                               st_nlink=links)

    def geteuid(self):
        return 1000

    def path(self, name, dir_fd):
        if str(name).startswith("/"):
            return str(PurePosixPath(name))
        return str(PurePosixPath(self.handles[dir_fd]) / name)

    def allocate(self, path):
        descriptor = self.next_fd
        self.next_fd += 1
        self.handles[descriptor] = path
        return descriptor

    def open(self, name, flags, mode=0o666, *, dir_fd=None):
        path = self.path(name, dir_fd)
        self.events.append(("open", path, flags))
        if flags & os.O_DIRECTORY:
            if path not in self.directories:
                raise FileNotFoundError(path)
        else:
            if path in self.files and flags & os.O_EXCL:
                raise FileExistsError(path)
            if path not in self.files:
                if not flags & os.O_CREAT:
                    raise FileNotFoundError(path)
                self.files[path] = {"body": bytearray(), "info": self.info(inode=self.next_inode, mode=mode)}
                self.next_inode += 1
        return self.allocate(path)

    def mkdir(self, name, mode=0o777, *, dir_fd=None):
        path = self.path(name, dir_fd)
        self.events.append(("mkdir", path))
        if path in self.directories or path in self.files:
            raise FileExistsError(path)
        self.directories[path] = self.info(directory=True, inode=self.next_inode, mode=mode)
        self.next_inode += 1

    def fstat(self, descriptor):
        path = self.handles[descriptor]
        return self.directories[path] if path in self.directories else self.files[path]["info"]

    def stat(self, name, *, dir_fd, follow_symlinks):
        assert follow_symlinks is False
        path = self.path(name, dir_fd)
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]["info"]

    def dup(self, descriptor):
        return self.allocate(self.handles[descriptor])

    def close(self, descriptor):
        self.events.append(("close", descriptor))
        del self.handles[descriptor]

    def fdopen(self, descriptor, mode, *, buffering):
        assert mode == "wb" and buffering == 0
        return FakeStream(self, descriptor)

    def ftruncate(self, descriptor, length):
        assert length == 0
        path = self.handles[descriptor]
        self.events.append(("truncate", path))
        self.files[path]["body"].clear()

    def fchmod(self, descriptor, mode):
        self.fstat(descriptor).st_mode = stat.S_IFREG | mode

    def fsync(self, descriptor):
        path = self.handles[descriptor]
        kind = "dir_fsync" if path in self.directories else "file_fsync"
        self.events.append((kind, path))
        if self.fail_at == kind:
            raise OSError("injected fsync")

    def replace(self, source, target, *, src_dir_fd, dst_dir_fd):
        source_path = self.path(source, src_dir_fd)
        target_path = self.path(target, dst_dir_fd)
        self.events.append(("replace", source_path, target_path))
        if self.fail_at == "rename":
            raise OSError("injected rename")
        self.files[target_path] = self.files.pop(source_path)

    def unlink(self, name, *, dir_fd):
        path = self.path(name, dir_fd)
        self.events.append(("unlink", path))
        del self.files[path]


@pytest.fixture
def owned(monkeypatch):
    filesystem = FakeOS()
    monkeypatch.setattr(budget_module, "os", filesystem)
    ledger = MonotonicArtifactLedger(capacity=64, terminal_reserve=8)
    facade = ArtifactBudget(Path("/owned"), ledger=ledger)
    return facade, filesystem, ledger


def test_fixed_partitions_cannot_be_increased_or_borrowed():
    assert ORDINARY_BYTE_CAP == CARE_BYTE_CAP == 16_777_216
    assert TOTAL_BYTE_CAP == ORDINARY_BYTE_CAP + CARE_BYTE_CAP == 33_554_432
    assert ORDINARY_TERMINAL_RESERVE == 131_072
    assert CARE_METADATA_RESERVE == 65_536
    with pytest.raises(ArtifactBudgetError):
        MonotonicArtifactLedger(capacity=TOTAL_BYTE_CAP)


def test_same_path_attempts_charge_again_even_without_writes():
    ledger = MonotonicArtifactLedger(capacity=8, terminal_reserve=2)
    ledger.reserve("state.json", 3)
    ledger.reserve("state.json", 3, operation="atomic")
    assert ledger.charged_bytes == 8
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve("state.json", 1)
    assert ledger.charged_bytes == 8
    assert ledger.first_fault.code == "capacity"


def test_terminal_reserve_survives_capacity_fault_and_is_single_use():
    ledger = MonotonicArtifactLedger(capacity=8, terminal_reserve=2)
    ledger.reserve("body", 6)
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve("denied", 1)
    first = ledger.first_fault
    terminal = ledger.reserve("terminal.json", 2, terminal_role="terminal")
    ledger.consume(terminal)
    assert ledger.charged_bytes == 8
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve("terminal-again.json", 1, terminal_role="terminal")
    assert ledger.first_fault is first


def test_copied_token_is_not_an_admission():
    ledger = MonotonicArtifactLedger(capacity=8, terminal_reserve=0)
    token = ledger.reserve("body", 3)
    with pytest.raises(ArtifactBudgetError):
        ledger.consume(replace(token))
    assert ledger.charged_bytes == 3
    assert ledger.first_fault.code == "replay"


def test_token_is_single_use_and_cannot_cross_ledgers():
    ledger = MonotonicArtifactLedger(capacity=8, terminal_reserve=0)
    other = MonotonicArtifactLedger(capacity=8, terminal_reserve=0)
    token = ledger.reserve("body", 3)
    with pytest.raises(ArtifactBudgetError):
        other.consume(token)
    ledger.consume(token)
    with pytest.raises(ArtifactBudgetError):
        ledger.consume(token)
    assert ledger.charged_bytes == 3
    assert other.charged_bytes == 0


@pytest.mark.parametrize("path", ["../escape", "a/../b", "/absolute", "a//b", "a/./b", "a\\b", "a\x00b"])
def test_path_aliases_refuse_before_any_debit(path):
    ledger = MonotonicArtifactLedger(capacity=8, terminal_reserve=0)
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve(path, 1)
    assert ledger.charged_bytes == 0
    assert ledger.first_fault.code == "path"


def test_pending_nonterminal_token_cannot_write_after_first_fault():
    ledger = MonotonicArtifactLedger(capacity=8, terminal_reserve=0)
    token = ledger.reserve("body", 3)
    ledger.fail("io")
    with pytest.raises(ArtifactBudgetError):
        ledger.consume(token)
    assert ledger.first_fault.code == "io"
    assert ledger.charged_bytes == 3


def test_invalid_integer_or_operation_latches_bounded_fault():
    ledger = MonotonicArtifactLedger(capacity=8, terminal_reserve=0)
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve("body", True)
    first = ledger.first_fault
    ledger.fail("arbitrary exception body")
    assert ledger.first_fault is first
    assert first.code == "bounds"


def test_multibyte_text_is_charged_by_actual_utf8_bytes(owned):
    facade, filesystem, ledger = owned
    facade.write_text(Path("/owned/body"), "é\n", encoding="utf-8")
    assert bytes(filesystem.files["/owned/body"]["body"]) == b"\xc3\xa9\n"
    assert ledger.charged_bytes == 11


def test_unsupported_encoding_refuses_before_file_open(owned):
    facade, filesystem, ledger = owned
    before = list(filesystem.events)
    with pytest.raises(ArtifactBudgetError):
        facade.write_text(Path("/owned/body"), "body", encoding="latin-1")
    assert filesystem.events == before
    assert ledger.charged_bytes == 8
    assert ledger.first_fault.code == "encoding"


def test_capacity_refusal_does_not_create_or_truncate_target(owned):
    facade, filesystem, ledger = owned
    facade.write_bytes(Path("/owned/body"), b"old")
    before = list(filesystem.events)
    with pytest.raises(ArtifactBudgetError):
        facade.write_bytes(Path("/owned/body"), b"x" * 54)
    assert filesystem.events == before
    assert bytes(filesystem.files["/owned/body"]["body"]) == b"old"
    assert ledger.charged_bytes == 11


def test_normal_direct_replacement_and_unlink_never_refund(owned):
    facade, filesystem, ledger = owned
    facade.write_bytes(Path("/owned/body"), b"first")
    facade.write_bytes(Path("/owned/body"), b"next")
    assert bytes(filesystem.files["/owned/body"]["body"]) == b"next"
    assert ledger.charged_bytes == 17
    facade.unlink(Path("/owned/body"))
    assert "/owned/body" not in filesystem.files
    assert ledger.charged_bytes == 17
    facade.unlink(Path("/owned/absent"))
    assert ledger.first_fault is None


def test_atomic_success_charges_old_and_new_without_refund(owned):
    facade, filesystem, ledger = owned
    facade.write_bytes(Path("/owned/body"), b"old")
    facade.write_bytes(Path("/owned/body"), b"newer", atomic=True)
    assert bytes(filesystem.files["/owned/body"]["body"]) == b"newer"
    assert set(filesystem.files) == {"/owned/body"}
    assert ledger.charged_bytes == 16
    assert any(row[0] == "replace" for row in filesystem.events)


@pytest.mark.parametrize("stage", ["write", "short", "flush", "file_fsync", "close", "rename"])
def test_atomic_failure_keeps_partial_temp_and_full_debit(owned, stage):
    facade, filesystem, ledger = owned
    facade.write_bytes(Path("/owned/body"), b"old")
    filesystem.fail_at = stage
    with pytest.raises(OSError):
        facade.write_bytes(Path("/owned/body"), b"newer", atomic=True)
    assert bytes(filesystem.files["/owned/body"]["body"]) == b"old"
    partials = [path for path in filesystem.files if path != "/owned/body"]
    assert len(partials) == 1
    assert partials[0].endswith(".tmp")
    assert ledger.charged_bytes == 16
    assert ledger.first_fault.code == "io"
    assert not any(row[0] == "unlink" for row in filesystem.events)
    if stage == "short":
        assert bytes(filesystem.files[partials[0]]["body"]) == b"newe"


def test_directory_fsync_failure_preserves_replaced_body_and_fault(owned):
    facade, filesystem, ledger = owned
    facade.write_bytes(Path("/owned/body"), b"old")
    filesystem.fail_at = "dir_fsync"
    with pytest.raises(OSError):
        facade.write_bytes(Path("/owned/body"), b"newer", atomic=True)
    assert bytes(filesystem.files["/owned/body"]["body"]) == b"newer"
    assert ledger.charged_bytes == 16
    with pytest.raises(ArtifactBudgetError):
        facade.require_healthy()


@pytest.mark.parametrize("kind", ["hardlink", "symlink", "foreign"])
def test_owned_target_alias_or_foreign_replacement_refuses_before_mutation(owned, kind):
    facade, filesystem, ledger = owned
    facade.write_bytes(Path("/owned/body"), b"old")
    info = filesystem.files["/owned/body"]["info"]
    if kind == "hardlink":
        info.st_nlink = 2
    elif kind == "symlink":
        info.st_mode = stat.S_IFLNK | 0o600
    else:
        info.st_ino += 1
    before_writes = sum(row[0] == "write" for row in filesystem.events)
    with pytest.raises(ArtifactBudgetError):
        facade.write_bytes(Path("/owned/body"), b"newer")
    assert bytes(filesystem.files["/owned/body"]["body"]) == b"old"
    assert sum(row[0] == "write" for row in filesystem.events) == before_writes
    assert ledger.charged_bytes == 16


def test_outside_or_relative_path_never_reaches_filesystem(owned):
    facade, filesystem, ledger = owned
    before = list(filesystem.events)
    with pytest.raises(ArtifactBudgetError):
        facade.write_bytes(Path("/outside/body"), b"body")
    assert filesystem.events == before
    assert ledger.charged_bytes == 8


def test_no_public_fd_seek_stream_or_checkpoint_escape(owned):
    facade, filesystem, ledger = owned
    for name in ("fileno", "open", "seek", "truncate", "stream", "write_stream"):
        assert not hasattr(facade, name)
    with pytest.raises(ArtifactBudgetError):
        facade.__getstate__()
    assert ledger.first_fault.code == "checkpoint"


def test_closed_budget_refuses_before_creating_file(owned):
    facade, filesystem, ledger = owned
    facade.close()
    before = list(filesystem.events)
    with pytest.raises(ArtifactBudgetError):
        facade.write_bytes(Path("/owned/body"), b"body")
    assert filesystem.events == before
    assert ledger.first_fault.code == "closed"


def test_terminal_metadata_can_be_retained_after_nonterminal_fault(owned):
    facade, filesystem, ledger = owned
    ledger.fail("capacity")
    facade.write_terminal(Path("/owned/terminal.json"), b"{}", role="terminal")
    assert bytes(filesystem.files["/owned/terminal.json"]["body"]) == b"{}"
    assert ledger.charged_bytes == 8
    assert ledger.first_fault.code == "capacity"


def test_atomic_io_none_uses_original_private_writer_call(monkeypatch):
    calls = []
    monkeypatch.setattr(artifact_io, "_atomic_write", lambda *args: calls.append(args))
    path = Path("unchanged")
    artifact_io.atomic_write_text(path, "text")
    artifact_io.atomic_write_bytes(path, b"body", artifact_budget=None)
    assert calls == [(path, "text", "w", "utf-8"), (path, b"body", "wb", None)]


def test_atomic_io_explicit_budget_never_calls_default_writer(monkeypatch):
    calls = []
    def forbidden(*args):
        raise AssertionError("unbudgeted writer called")
    monkeypatch.setattr(artifact_io, "_atomic_write", forbidden)
    explicit = SimpleNamespace(write_text=lambda *a, **k: calls.append((a, k)),
                               write_bytes=lambda *a, **k: calls.append((a, k)))
    path = Path("explicit")
    artifact_io.atomic_write_text(path, "text", artifact_budget=explicit)
    artifact_io.atomic_write_bytes(path, b"body", artifact_budget=explicit)
    assert calls == [((path, "text"), {"encoding": "utf-8", "atomic": True}),
                     ((path, b"body"), {"atomic": True})]


def test_first_write_error_survives_a_later_descriptor_close_error(owned, monkeypatch):
    facade, filesystem, ledger = owned
    primary = OSError("primary flush")
    original_close = filesystem.close
    def flush_failure(self):
        raise primary
    def close_failure(descriptor):
        path = filesystem.handles[descriptor]
        original_close(descriptor)
        if path == "/owned":
            raise OSError("secondary directory close")
    monkeypatch.setattr(FakeStream, "flush", flush_failure)
    monkeypatch.setattr(filesystem, "close", close_failure)
    with pytest.raises(OSError) as caught:
        facade.write_bytes(Path("/owned/body"), b"body")
    assert caught.value is primary
    assert ledger.charged_bytes == 12
    assert ledger.first_fault.code == "io"


def test_upstream_output_fault_is_sticky_without_physics_or_file_retry(owned):
    facade, filesystem, ledger = owned
    facade.fail("io")
    first = ledger.first_fault
    facade.fail("capacity")
    before = list(filesystem.events)
    with pytest.raises(ArtifactBudgetError):
        facade.write_bytes(Path("/owned/body"), b"body")
    assert filesystem.events == before
    assert ledger.first_fault is first
    assert first.code == "io"


def test_existing_root_is_never_adopted_or_repaired(owned):
    facade, filesystem, ledger = owned
    original_root = filesystem.directories["/owned"]
    with pytest.raises(FileExistsError):
        ArtifactBudget(Path("/owned"))
    assert filesystem.directories["/owned"] is original_root
    assert not filesystem.files
    assert ledger.first_fault is None


def test_disappeared_owned_directory_is_not_silently_recreated(owned):
    facade, filesystem, ledger = owned
    facade.ensure_directory(Path("/owned/sub"))
    del filesystem.directories["/owned/sub"]
    before = list(filesystem.events)
    with pytest.raises(ArtifactBudgetError):
        facade.ensure_directory(Path("/owned/sub"))
    assert not any(row[0] == "mkdir" for row in filesystem.events[len(before):])
    assert ledger.first_fault.code == "io"


@pytest.mark.parametrize("bound", ["paths", "attempts"])
def test_zero_byte_requests_cannot_escape_finite_ledger_bounds(bound):
    ledger = MonotonicArtifactLedger(capacity=8, terminal_reserve=0)
    limit = budget_module.MAX_OWNED_PATHS if bound == "paths" else budget_module.MAX_ATTEMPTS
    for ordinal in range(limit):
        path = "body-" + str(ordinal) if bound == "paths" else "body"
        ledger.reserve(path, 0)
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve("one-more", 0)
    assert ledger.charged_bytes == 0
    assert ledger.first_fault.code == "bounds"


def test_mismatched_body_cannot_consume_a_smaller_admission(owned):
    facade, filesystem, ledger = owned
    token = ledger.reserve("body", 3)
    before = list(filesystem.events)
    with pytest.raises(ArtifactBudgetError):
        facade._write(token, b"four")
    assert filesystem.events == before
    assert ledger.charged_bytes == 11
    assert ledger.first_fault.code == "protocol"


# Append-only successor contracts: the complete dbb test source above is exact.
# These are source-written only; neither the old 42 nor these cases have run.
_RESERVED_TERMINAL_BODY = b"T" * 8_192
_RESERVED_FREEZE_BODY = b"F" * 122_880


def _production_fake_budget(monkeypatch):
    filesystem = FakeOS()
    monkeypatch.setattr(budget_module, "os", filesystem)
    ledger = MonotonicArtifactLedger()
    facade = ArtifactBudget(Path("/owned"), ledger=ledger)
    return facade, filesystem, ledger


def _retain_both_reserved_bodies(facade, filesystem):
    if "/owned/terminal.json" not in filesystem.files:
        facade.write_terminal(Path("/owned/terminal.json"), _RESERVED_TERMINAL_BODY,
                              role="terminal")
    facade.write_terminal(Path("/owned/freeze.json"), _RESERVED_FREEZE_BODY, role="freeze")
    assert bytes(filesystem.files["/owned/terminal.json"]["body"]) == _RESERVED_TERMINAL_BODY
    assert bytes(filesystem.files["/owned/freeze.json"]["body"]) == _RESERVED_FREEZE_BODY


@pytest.mark.parametrize("bound", ["paths", "attempts"])
def test_production_count_exhaustion_preserves_both_terminal_grants(monkeypatch, bound):
    facade, filesystem, ledger = _production_fake_budget(monkeypatch)
    limit = (budget_module.MAX_OWNED_PATHS if bound == "paths"
             else budget_module.MAX_ATTEMPTS) - 2
    for ordinal in range(limit):
        path = "body-" + str(ordinal) if bound == "paths" else "body"
        ledger.reserve(path, 0)
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve("ordinary-overflow", 0)
    first = ledger.first_fault
    _retain_both_reserved_bodies(facade, filesystem)
    assert ledger.first_fault is first
    assert first.code == "bounds"
    assert ledger.charged_bytes == ORDINARY_TERMINAL_RESERVE
    assert ledger._attempt <= budget_module.MAX_ATTEMPTS
    assert len(ledger._paths) <= budget_module.MAX_OWNED_PATHS


def test_reserved_root_roles_reject_ordinary_files_and_descendants(monkeypatch):
    facade, filesystem, ledger = _production_fake_budget(monkeypatch)
    with pytest.raises(ArtifactBudgetError):
        facade.write_bytes(Path("/owned/terminal.json/ordinary"), b"body")
    assert not filesystem.files
    _retain_both_reserved_bodies(facade, filesystem)
    assert ledger.first_fault.code == "terminal"


@pytest.mark.parametrize("operation", ["file", "directory", "unlink"])
def test_ordinary_operations_cannot_claim_or_remove_reserved_roots(monkeypatch, operation):
    facade, filesystem, ledger = _production_fake_budget(monkeypatch)
    if operation == "unlink":
        facade.write_terminal(Path("/owned/terminal.json"), _RESERVED_TERMINAL_BODY,
                              role="terminal")
    with pytest.raises(ArtifactBudgetError):
        if operation == "file":
            facade.write_bytes(Path("/owned/terminal.json"), b"ordinary")
        elif operation == "directory":
            facade.ensure_directory(Path("/owned/terminal.json"))
        else:
            facade.unlink(Path("/owned/terminal.json"))
    _retain_both_reserved_bodies(facade, filesystem)
    assert "/owned/terminal.json" not in filesystem.directories
    assert ledger.first_fault is not None


@pytest.mark.parametrize("wrong_path", ["other.json", "nested/terminal.json"])
def test_terminal_roles_require_the_closed_root_paths(wrong_path):
    ledger = MonotonicArtifactLedger()
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve(wrong_path, 1, terminal_role="terminal")
    first = ledger.first_fault
    ledger.consume(ledger.reserve("terminal.json", 1, terminal_role="terminal"))
    ledger.consume(ledger.reserve("freeze.json", 1, terminal_role="freeze"))
    assert ledger.first_fault is first


def test_atomic_terminal_operation_cannot_borrow_a_third_live_slot():
    ledger = MonotonicArtifactLedger()
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve("terminal.json", 1, terminal_role="terminal", operation="atomic")
    ledger.consume(ledger.reserve("terminal.json", 1, terminal_role="terminal"))
    ledger.consume(ledger.reserve("freeze.json", 1, terminal_role="freeze"))
    assert ledger.first_fault.code == "terminal"


def test_zero_reserve_remains_an_ordinary_only_fake_contract():
    ledger = MonotonicArtifactLedger(capacity=8, terminal_reserve=0)
    ledger.consume(ledger.reserve("terminal.json", 0))
    with pytest.raises(ArtifactBudgetError):
        ledger.reserve("freeze.json", 0, terminal_role="freeze")
    assert ledger.charged_bytes == 0
    assert ledger.first_fault.code == "terminal"


def test_facade_file_boundary_keeps_both_reserved_live_slots(monkeypatch):
    facade, filesystem, ledger = _production_fake_budget(monkeypatch)
    for ordinal in range(budget_module.MAX_OWNED_PATHS - 2):
        facade.write_bytes(Path("/owned/body-" + str(ordinal)), b"")
    before = set(filesystem.files)
    with pytest.raises(ArtifactBudgetError):
        facade.write_bytes(Path("/owned/body-0"), b"", atomic=True)
    assert set(filesystem.files) == before
    assert not any(path.endswith(".tmp") for path in filesystem.files)
    _retain_both_reserved_bodies(facade, filesystem)
    assert len(filesystem.files) == budget_module.MAX_OWNED_PATHS
    assert ledger.first_fault.code == "io"


def test_retained_failed_atomic_temp_uses_only_an_ordinary_live_slot(monkeypatch):
    facade, filesystem, ledger = _production_fake_budget(monkeypatch)
    for ordinal in range(budget_module.MAX_OWNED_PATHS - 3):
        facade.write_bytes(Path("/owned/body-" + str(ordinal)), b"")
    filesystem.fail_at = "short"
    with pytest.raises(OSError):
        facade.write_bytes(Path("/owned/body-0"), b"partial", atomic=True)
    first = ledger.first_fault
    partials = [path for path in filesystem.files if path.endswith(".tmp")]
    assert len(partials) == 1
    assert bytes(filesystem.files[partials[0]]["body"]) == b"partia"
    assert len(filesystem.files) == budget_module.MAX_OWNED_PATHS - 2
    filesystem.fail_at = None
    _retain_both_reserved_bodies(facade, filesystem)
    assert ledger.first_fault is first
    assert len(filesystem.files) == budget_module.MAX_OWNED_PATHS
    assert ledger.charged_bytes == ORDINARY_TERMINAL_RESERVE + len(b"partial")
    assert bytes(filesystem.files[partials[0]]["body"]) == b"partia"


def test_terminal_root_records_need_no_new_directory_slot(monkeypatch):
    facade, filesystem, ledger = _production_fake_budget(monkeypatch)
    for ordinal in range(budget_module.MAX_OWNED_PATHS - 1):
        facade.ensure_directory(Path("/owned/directory-" + str(ordinal)))
    assert len(facade._owned_directories) == budget_module.MAX_OWNED_PATHS
    with pytest.raises(ArtifactBudgetError):
        facade.ensure_directory(Path("/owned/ordinary-overflow"))
    first = ledger.first_fault
    _retain_both_reserved_bodies(facade, filesystem)
    assert ledger.first_fault is first
    assert len(facade._owned_directories) == budget_module.MAX_OWNED_PATHS


class _RejectDirectoryIdentity(dict):
    def __init__(self, original, rejected_key, marker):
        super().__init__(original)
        self.rejected_key = rejected_key
        self.marker = marker

    def __setitem__(self, key, value):
        if key == self.rejected_key:
            raise self.marker
        super().__setitem__(key, value)


@pytest.mark.parametrize("shape,stage", [
    ("owned", "fstat"), ("new", "fstat"), ("new", "fstat-second"),
    ("new", "insert"), ("owned-prefix-new", "fstat"),
    ("owned-prefix-new", "fstat-second"), ("owned-prefix-new", "insert"),
])
def test_directory_error_closes_both_locals_and_preserves_first_identity(owned, monkeypatch,
                                                                        shape, stage):
    facade, filesystem, ledger = owned
    if shape == "owned":
        facade.ensure_directory(Path("/owned/child"))
    elif shape == "owned-prefix-new":
        facade.ensure_directory(Path("/owned/prefix"))
    key = "prefix/child" if shape == "owned-prefix-new" else "child"
    target = "/owned/" + key
    marker = MemoryError("first directory identity error")
    baseline = dict(filesystem.handles)
    if stage in ("fstat", "fstat-second"):
        original_fstat = filesystem.fstat
        target_calls = 0
        def failing_fstat(descriptor):
            nonlocal target_calls
            if filesystem.handles[descriptor] == target:
                target_calls += 1
                if stage == "fstat" or target_calls == 2:
                    raise marker
            return original_fstat(descriptor)
        monkeypatch.setattr(filesystem, "fstat", failing_fstat)
    else:
        facade._owned_directories = _RejectDirectoryIdentity(
            facade._owned_directories, key, marker)
    with pytest.raises(MemoryError) as caught:
        facade.ensure_directory(Path(target))
    assert caught.value is marker
    assert filesystem.handles == baseline
    assert ledger.first_fault.code == "io"
    facade.close()
    assert not filesystem.handles


@pytest.mark.parametrize("failed_local", ["child", "parent"])
@pytest.mark.parametrize("close_timing", ["before-removal", "after-removal"])
def test_directory_cleanup_close_error_does_not_mask_or_retry(owned, monkeypatch,
                                                              failed_local, close_timing):
    facade, filesystem, ledger = owned
    facade.ensure_directory(Path("/owned/child"))
    baseline = dict(filesystem.handles)
    marker = MemoryError("first fstat error")
    cleanup = OSError("later close error")
    original_fstat, original_close = filesystem.fstat, filesystem.close
    close_attempts = []
    failed_descriptors = []
    def failing_fstat(descriptor):
        if filesystem.handles[descriptor] == "/owned/child":
            raise marker
        return original_fstat(descriptor)
    def failing_close(descriptor):
        path = filesystem.handles[descriptor]
        close_attempts.append(descriptor)
        selected = path == ("/owned/child" if failed_local == "child" else "/owned")
        if selected:
            failed_descriptors.append(descriptor)
            if close_timing == "after-removal":
                original_close(descriptor)
            raise cleanup
        original_close(descriptor)
    monkeypatch.setattr(filesystem, "fstat", failing_fstat)
    monkeypatch.setattr(filesystem, "close", failing_close)
    with pytest.raises(MemoryError) as caught:
        facade.ensure_directory(Path("/owned/child"))
    assert caught.value is marker
    assert len(failed_descriptors) == 1
    assert close_attempts.count(failed_descriptors[0]) == 1
    unknown = set(filesystem.handles) - set(baseline)
    assert unknown == ({failed_descriptors[0]} if close_timing == "before-removal" else set())
    assert all(filesystem.handles[descriptor] == path for descriptor, path in baseline.items())
    assert ledger.first_fault.code == "io"
    monkeypatch.setattr(filesystem, "close", original_close)
    facade.close()
    assert set(filesystem.handles) == unknown


@pytest.mark.parametrize("close_timing", ["before-removal", "after-removal"])
def test_parent_transfer_close_failure_still_closes_untransferred_child(owned, monkeypatch,
                                                                        close_timing):
    facade, filesystem, ledger = owned
    facade.ensure_directory(Path("/owned/child"))
    baseline = dict(filesystem.handles)
    marker = OSError("first parent transfer close error")
    original_close = filesystem.close
    failed_descriptors = []
    close_attempts = []
    def failing_close(descriptor):
        path = filesystem.handles[descriptor]
        close_attempts.append(descriptor)
        if path == "/owned":
            failed_descriptors.append(descriptor)
            if close_timing == "after-removal":
                original_close(descriptor)
            raise marker
        original_close(descriptor)
    monkeypatch.setattr(filesystem, "close", failing_close)
    with pytest.raises(OSError) as caught:
        facade.ensure_directory(Path("/owned/child"))
    assert caught.value is marker
    assert len(failed_descriptors) == 1
    assert close_attempts.count(failed_descriptors[0]) == 1
    unknown = set(filesystem.handles) - set(baseline)
    assert unknown == ({failed_descriptors[0]} if close_timing == "before-removal" else set())
    assert ledger.first_fault.code == "io"
    monkeypatch.setattr(filesystem, "close", original_close)
    facade.close()
    assert set(filesystem.handles) == unknown


# Coherent constructor successor: all 68 earlier case bodies above remain exact.
# These primitive FakeOS cases are also unregistered and unrun.
class _ConstructorOrigin:
    def __init__(self, marker):
        self.marker = marker
        self.traceback_tail = None

    def raise_primary(self):
        try:
            raise self.marker
        except BaseException:
            self.traceback_tail = self.marker.__traceback__
            raise


def _constructor_environment(monkeypatch):
    filesystem = FakeOS()
    for inode, path in enumerate(("/first", "/first/second", "/unrelated"), start=91):
        filesystem.directories[path] = filesystem.info(directory=True, inode=inode, mode=0o755)
    filesystem.allocate("/unrelated")
    baseline = dict(filesystem.handles)
    monkeypatch.setattr(budget_module, "os", filesystem)
    return filesystem, MonotonicArtifactLedger(), baseline, Path("/first/second/owned")


def _assert_constructor_primary(caught, origin):
    assert caught.value is origin.marker
    frames = []
    traceback = caught.value.__traceback__
    while traceback is not None:
        frames.append(traceback)
        traceback = traceback.tb_next
    assert any(frame is origin.traceback_tail for frame in frames)
    assert sum(frame.tb_frame.f_code is ArtifactBudget.__init__.__code__ for frame in frames) == 1


def _assert_constructor_handles(filesystem, baseline, failed_descriptors, close_timing,
                                extra_unknown=()):
    for descriptor, path in baseline.items():
        assert filesystem.handles[descriptor] == path
    unknown = set(filesystem.handles) - set(baseline)
    expected = set(failed_descriptors) if close_timing == "before-removal" else set()
    expected.update(extra_unknown)
    assert unknown == expected


class _ConstructorRootIdentity(dict):
    def __init__(self, original, origin, when):
        super().__init__(original)
        self.origin = origin
        self.when = when

    def __setitem__(self, key, value):
        if key == "":
            if self.when == "map-after":
                super().__setitem__(key, value)
            self.origin.raise_primary()
        super().__setitem__(key, value)


def test_constructor_success_retains_only_root_above_unrelated_baseline(monkeypatch):
    filesystem, ledger, baseline, root = _constructor_environment(monkeypatch)
    facade = ArtifactBudget(root, ledger=ledger)
    assert filesystem.handles == {**baseline, facade._root_fd: str(root)}
    assert ledger.first_fault is None
    facade.close()
    assert filesystem.handles == baseline


@pytest.mark.parametrize("stage", [
    "initial-open", "first-ancestor-open", "later-ancestor-open", "mkdir", "root-open",
])
def test_constructor_acquisition_failure_latches_io_and_closes_known_handles(monkeypatch, stage):
    filesystem, ledger, baseline, root = _constructor_environment(monkeypatch)
    origin = _ConstructorOrigin(OSError("first constructor acquisition error"))
    original_open, original_mkdir = filesystem.open, filesystem.mkdir
    targets = {"initial-open": "/", "first-ancestor-open": "/first",
               "later-ancestor-open": "/first/second", "root-open": str(root)}
    def failing_open(name, flags, mode=0o666, *, dir_fd=None):
        if stage != "mkdir" and filesystem.path(name, dir_fd) == targets[stage]:
            origin.raise_primary()
        return original_open(name, flags, mode, dir_fd=dir_fd)
    def failing_mkdir(name, mode=0o777, *, dir_fd=None):
        if stage == "mkdir" and filesystem.path(name, dir_fd) == str(root):
            origin.raise_primary()
        return original_mkdir(name, mode, dir_fd=dir_fd)
    monkeypatch.setattr(filesystem, "open", failing_open)
    monkeypatch.setattr(filesystem, "mkdir", failing_mkdir)
    with pytest.raises(OSError) as caught:
        ArtifactBudget(root, ledger=ledger)
    _assert_constructor_primary(caught, origin)
    assert filesystem.handles == baseline
    assert ledger.first_fault.code == "io"
    assert ledger.charged_bytes == ORDINARY_TERMINAL_RESERVE


@pytest.mark.parametrize("ancestor_parent", ["/", "/first"])
@pytest.mark.parametrize("close_timing", ["before-removal", "after-removal"])
@pytest.mark.parametrize("child_cleanup", ["normal", "before-removal", "after-removal"])
def test_constructor_ancestor_handoff_close_error_cleans_untransferred_child(monkeypatch,
                                                                            ancestor_parent,
                                                                            close_timing,
                                                                            child_cleanup):
    filesystem, ledger, baseline, root = _constructor_environment(monkeypatch)
    origin = _ConstructorOrigin(OSError("first ancestor handoff close error"))
    original_close = filesystem.close
    close_attempts, failed_descriptors, child_failures = [], [], []
    child_path = "/first" if ancestor_parent == "/" else "/first/second"
    def failing_close(descriptor):
        path = filesystem.handles[descriptor]
        close_attempts.append(descriptor)
        if path == ancestor_parent:
            failed_descriptors.append(descriptor)
            if close_timing == "after-removal":
                original_close(descriptor)
            origin.raise_primary()
        if path == child_path and child_cleanup != "normal":
            child_failures.append(descriptor)
            if child_cleanup == "after-removal":
                original_close(descriptor)
            raise OSError("secondary untransferred child close error")
        original_close(descriptor)
    monkeypatch.setattr(filesystem, "close", failing_close)
    with pytest.raises(OSError) as caught:
        ArtifactBudget(root, ledger=ledger)
    _assert_constructor_primary(caught, origin)
    assert len(failed_descriptors) == 1
    assert len(child_failures) == (0 if child_cleanup == "normal" else 1)
    assert all(close_attempts.count(descriptor) == 1
               for descriptor in failed_descriptors + child_failures)
    extra_unknown = child_failures if child_cleanup == "before-removal" else ()
    _assert_constructor_handles(filesystem, baseline, failed_descriptors, close_timing,
                                extra_unknown)
    assert ledger.first_fault.code == "io"
    if child_cleanup != "before-removal":
        assert child_path not in filesystem.handles.values()


@pytest.mark.parametrize("stage", ["fstat", "map-before", "map-after"])
@pytest.mark.parametrize("secondary,close_timing", [
    ("none", "unused"), ("root", "before-removal"), ("root", "after-removal"),
    ("parent", "before-removal"), ("parent", "after-removal"),
    ("both", "before-removal"), ("both", "after-removal"),
])
def test_constructor_root_primary_survives_independent_secondary_closes(monkeypatch, stage,
                                                                      secondary, close_timing):
    filesystem, ledger, baseline, root = _constructor_environment(monkeypatch)
    origin = _ConstructorOrigin(MemoryError("first root identity error"))
    original_fstat, original_close = filesystem.fstat, filesystem.close
    close_attempts, failed_descriptors = [], []
    selected_paths = set()
    if secondary in ("root", "both"):
        selected_paths.add(str(root))
    if secondary in ("parent", "both"):
        selected_paths.add(str(root.parent))
    def failing_fstat(descriptor):
        if stage == "fstat" and filesystem.handles[descriptor] == str(root):
            origin.raise_primary()
        return original_fstat(descriptor)
    def failing_close(descriptor):
        path = filesystem.handles[descriptor]
        close_attempts.append(descriptor)
        if path in selected_paths:
            failed_descriptors.append(descriptor)
            if close_timing == "after-removal":
                original_close(descriptor)
            raise OSError("secondary constructor cleanup close error")
        original_close(descriptor)
    class RootMapFailureBudget(ArtifactBudget):
        def __setattr__(self, name, value):
            if name == "_owned_directories":
                value = _ConstructorRootIdentity(value, origin, stage)
            super().__setattr__(name, value)
    budget_type = ArtifactBudget if stage == "fstat" else RootMapFailureBudget
    monkeypatch.setattr(filesystem, "fstat", failing_fstat)
    monkeypatch.setattr(filesystem, "close", failing_close)
    with pytest.raises(MemoryError) as caught:
        budget_type(root, ledger=ledger)
    _assert_constructor_primary(caught, origin)
    assert len(failed_descriptors) == len(selected_paths)
    assert all(close_attempts.count(descriptor) == 1 for descriptor in failed_descriptors)
    _assert_constructor_handles(filesystem, baseline, failed_descriptors, close_timing)
    assert ledger.first_fault.code == "io"


@pytest.mark.parametrize("close_timing", ["before-removal", "after-removal"])
@pytest.mark.parametrize("root_cleanup", ["normal", "before-removal", "after-removal"])
def test_constructor_success_body_final_parent_close_failure_cleans_unreturned_root(monkeypatch,
                                                                                   close_timing,
                                                                                   root_cleanup):
    filesystem, ledger, baseline, root = _constructor_environment(monkeypatch)
    origin = _ConstructorOrigin(OSError("first final parent close error"))
    original_close = filesystem.close
    close_attempts, failed_descriptors, root_failures = [], [], []
    def failing_close(descriptor):
        path = filesystem.handles[descriptor]
        close_attempts.append(descriptor)
        if path == str(root.parent):
            failed_descriptors.append(descriptor)
            if close_timing == "after-removal":
                original_close(descriptor)
            origin.raise_primary()
        if path == str(root) and root_cleanup != "normal":
            root_failures.append(descriptor)
            if root_cleanup == "after-removal":
                original_close(descriptor)
            raise OSError("secondary unreturned root close error")
        original_close(descriptor)
    monkeypatch.setattr(filesystem, "close", failing_close)
    with pytest.raises(OSError) as caught:
        ArtifactBudget(root, ledger=ledger)
    _assert_constructor_primary(caught, origin)
    assert len(failed_descriptors) == 1
    assert len(root_failures) == (0 if root_cleanup == "normal" else 1)
    assert all(close_attempts.count(descriptor) == 1
               for descriptor in failed_descriptors + root_failures)
    extra_unknown = root_failures if root_cleanup == "before-removal" else ()
    _assert_constructor_handles(filesystem, baseline, failed_descriptors, close_timing,
                                extra_unknown)
    if root_cleanup != "before-removal":
        assert str(root) not in filesystem.handles.values()
    assert ledger.first_fault.code == "io"


@pytest.mark.parametrize("bad_identity", ["uid", "mode"])
def test_constructor_invalid_root_identity_closes_root_and_parent(monkeypatch, bad_identity):
    filesystem, ledger, baseline, root = _constructor_environment(monkeypatch)
    original_fstat = filesystem.fstat
    def invalid_identity(descriptor):
        info = original_fstat(descriptor)
        if filesystem.handles[descriptor] == str(root):
            if bad_identity == "uid":
                info.st_uid += 1
            else:
                info.st_mode = stat.S_IFDIR | 0o755
        return info
    monkeypatch.setattr(filesystem, "fstat", invalid_identity)
    with pytest.raises(ArtifactBudgetError) as caught:
        ArtifactBudget(root, ledger=ledger)
    frames = []
    traceback = caught.value.__traceback__
    while traceback is not None:
        frames.append(traceback)
        traceback = traceback.tb_next
    assert sum(frame.tb_frame.f_code is ArtifactBudget.__init__.__code__ for frame in frames) == 1
    assert filesystem.handles == baseline
    assert ledger.first_fault.code == "io"
