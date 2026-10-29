"""Bounded opaque CI artifact intake into a newly created owned namespace.

No downloader, ZIP parser, Git, subprocess, product import or active integration.
This is a single-caller capability API, not an adversarial Python/OS sandbox.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
import stat

DEFAULT_ARTIFACTS = 9
MAX_ARTIFACTS = 16
ARCHIVE_CAP = 8 * 1024**2
TOTAL_CAP = 24 * 1024**2
CONTROL_RESERVE = 1024**2
NAME_CAP = 512
CHUNK = 64 * 1024
MAX_READ_CALLS = 4096
CAPABILITY_CAP = 64 * 1024
ARTIFACT_METADATA_CAP = 16 * 1024
MANIFEST_CAP = 1024**2
MAX_FILES = 2 * MAX_ARTIFACTS + 3
CAPABILITY = "intake-capability.json"
MANIFEST = "intake-manifest.json"
RESULT = "intake-result.json"
_CODES = frozenset({"binding", "namespace", "artifact", "duplicate", "capacity",
                    "protocol", "read", "write", "size", "digest", "metadata",
                    "closed", "finalize", "io", "interrupted"})
_ISSUER = object()
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class IntakeError(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in _CODES else "protocol"
        super().__init__(self.code)


def _need(condition, code):
    if not condition:
        raise IntakeError(code)


def _failure_code(error, fallback):
    code = getattr(error, "code", None) if type(error) is IntakeError else None
    return code if type(code) is str and code in _CODES else fallback


def _uint(value, maximum, *, positive=False):
    return type(value) is int and (1 if positive else 0) <= value <= maximum


def _text(value, cap=NAME_CAP):
    if type(value) is not str or not value:
        return False
    try:
        raw = value.encode("utf-8")
    except UnicodeError:
        return False
    return len(raw) <= cap and all(ord(c) >= 32 and ord(c) != 127 for c in value)


def _root_path(value):
    _need(_text(value) and value.startswith("/") and "\\" not in value, "namespace")
    parts = value.split("/")[1:]
    _need(1 <= len(parts) <= 16 and all(p not in ("", ".", "..") for p in parts), "namespace")
    return value


def _json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class Binding:
    repository: str
    source: str
    run_id: int
    attempt: int

    def __post_init__(self):
        _need(_text(self.repository, 256) and _REPO.fullmatch(self.repository), "binding")
        _need(type(self.source) is str and _SOURCE.fullmatch(self.source), "binding")
        _need(_uint(self.run_id, 2**63 - 1, positive=True)
              and _uint(self.attempt, 65535, positive=True), "binding")

    def record(self):
        return {"repository": self.repository, "source": self.source,
                "run_id": self.run_id, "attempt": self.attempt}


@dataclass(frozen=True, slots=True)
class Artifact:
    artifact_id: int
    name: str
    size: int
    sha256: str

    def __post_init__(self):
        _need(_uint(self.artifact_id, 2**63 - 1, positive=True), "artifact")
        _need(_text(self.name) and "/" not in self.name and "\\" not in self.name, "artifact")
        _need(_uint(self.size, ARCHIVE_CAP), "capacity")
        _need(type(self.sha256) is str and _HEX.fullmatch(self.sha256), "artifact")

    def record(self):
        return {"artifact_id": self.artifact_id, "name": self.name,
                "size": self.size, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class Identity:
    device: int
    inode: int

    def __post_init__(self):
        _need(_uint(self.device, 2**64 - 1)
              and _uint(self.inode, 2**64 - 1, positive=True), "namespace")

    def record(self):
        return {"device": self.device, "inode": self.inode}


@dataclass(frozen=True, slots=True)
class Namespace:
    path: str
    identity: Identity
    capability_sha256: str

    def __post_init__(self):
        _root_path(self.path)
        _need(type(self.identity) is Identity, "namespace")
        _need(type(self.capability_sha256) is str
              and _HEX.fullmatch(self.capability_sha256), "namespace")


@dataclass(frozen=True, slots=True)
class FileInfo:
    identity: Identity
    kind: str
    links: int
    uid: int
    mode: int
    size: int


@dataclass(frozen=True, slots=True)
class FilePin:
    name: str
    identity: Identity
    size: int
    sha256: str
    mode: int

    def record(self):
        return {"name": self.name, **self.identity.record(), "bytes": self.size,
                "sha256": self.sha256}


def _same_body(left, right):
    return (left.name, left.identity, left.size, left.sha256) == (
        right.name, right.identity, right.size, right.sha256)


class _Root:
    def __init__(self, issuer, owner, path, descriptor, identity, uid):
        _need(issuer is _ISSUER, "namespace")
        self.owner, self.path, self.descriptor, self.identity = owner, path, descriptor, identity
        self.uid = uid


class _Writer:
    def __init__(self, backend, descriptor, identity):
        self.backend, self.descriptor, self.identity = backend, descriptor, identity

    def write(self, body):
        _need(self.descriptor >= 0 and type(body) is bytes and len(body) <= CHUNK, "protocol")
        return self.backend._os.write(self.descriptor, body)

    def flush(self):
        _need(self.descriptor >= 0, "closed")  # unbuffered os.write has no userspace buffer

    def sync(self):
        _need(self.descriptor >= 0, "closed")
        self.backend._os.fsync(self.descriptor)

    def close(self):
        descriptor, self.descriptor = self.descriptor, -1
        _need(descriptor >= 0, "closed")
        self.backend._close(descriptor)


class PosixFS:
    """Small directory-FD backend. Test injection never replaces global os."""
    def __init__(self, *, os_module=None):
        self._os = os if os_module is None else os_module
        self.cleanup_unknown = False
        _need(self._os.name == "posix" and hasattr(self._os, "O_NOFOLLOW"), "namespace")

    def _flags(self):
        o = self._os
        return o.O_RDONLY | o.O_DIRECTORY | o.O_NOFOLLOW | getattr(o, "O_CLOEXEC", 0)

    def _owned(self, handle):
        _need(type(handle) is _Root and handle.owner is self
              and handle.descriptor >= 0, "namespace")

    def _close(self, descriptor):
        try:
            self._os.close(descriptor)
        except BaseException:
            self.cleanup_unknown = True
            raise

    def _quiet_closes(self, descriptors):
        seen = set()
        for descriptor in descriptors:
            if descriptor >= 0 and descriptor not in seen:
                seen.add(descriptor)
                try:
                    self._close(descriptor)
                except BaseException:
                    pass  # disposition unknown; never retry or claim successful cleanup

    def _identity(self, info):
        return Identity(info.st_dev, info.st_ino)

    def _file_info(self, info):
        kind = "file" if stat.S_ISREG(info.st_mode) else "dir" if stat.S_ISDIR(info.st_mode) else "other"
        return FileInfo(self._identity(info), kind, info.st_nlink, info.st_uid,
                        stat.S_IMODE(info.st_mode), info.st_size)

    def create_root(self, path):
        _root_path(path)
        o = self._os
        parent = child = root = -1
        try:
            parent = o.open("/", self._flags())
            for part in path.split("/")[1:-1]:
                child = o.open(part, self._flags(), dir_fd=parent)
                retiring, parent = parent, -1
                self._close(retiring)
                parent, child = child, -1
            name = path.rsplit("/", 1)[1]
            o.mkdir(name, mode=0o700, dir_fd=parent)  # any existing entry refuses
            root = o.open(name, self._flags(), dir_fd=parent)
            info = o.fstat(root)
            _need(stat.S_ISDIR(info.st_mode) and info.st_uid == o.geteuid()
                  and stat.S_IMODE(info.st_mode) == 0o700, "namespace")
            identity = self._identity(info)
            retiring, parent = parent, -1
            self._close(retiring)
            return _Root(_ISSUER, self, path, root, identity, info.st_uid)
        except BaseException:
            self._quiet_closes((root, child, parent))
            raise

    def check_root(self, handle, path, identity, *, readonly=False):
        self._owned(handle)
        _need(handle.path == path
              and handle.identity == identity, "namespace")
        o = self._os
        held = o.fstat(handle.descriptor)
        named = o.stat(path, follow_symlinks=False)
        mode = 0o555 if readonly else 0o700
        _need(stat.S_ISDIR(held.st_mode) and stat.S_ISDIR(named.st_mode)
              and self._identity(held) == self._identity(named) == identity
              and held.st_uid == named.st_uid == o.geteuid()
              and stat.S_IMODE(held.st_mode) == stat.S_IMODE(named.st_mode) == mode, "namespace")

    def list_infos(self, handle):
        self._owned(handle)
        result = {}
        iterator = self._os.scandir(handle.descriptor)
        try:
            for entry in iterator:
                _need(len(result) < MAX_FILES and type(entry.name) is str
                      and _text(entry.name) and "/" not in entry.name, "namespace")
                _need(entry.name not in result, "namespace")
                info = self._os.stat(entry.name, dir_fd=handle.descriptor, follow_symlinks=False)
                result[entry.name] = self._file_info(info)
        except BaseException:
            try:
                iterator.close()
            except BaseException:
                self.cleanup_unknown = True
            raise
        else:
            try:
                iterator.close()
            except BaseException:
                self.cleanup_unknown = True
                raise
            return result

    def create_file(self, handle, name):
        self._owned(handle)
        _need(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", name), "protocol")
        o = self._os
        descriptor = -1
        try:
            descriptor = o.open(name, o.O_WRONLY | o.O_CREAT | o.O_EXCL | o.O_NOFOLLOW
                                | getattr(o, "O_CLOEXEC", 0), 0o600, dir_fd=handle.descriptor)
            info = o.fstat(descriptor)
            _need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                  and info.st_uid == o.geteuid(), "namespace")
            return _Writer(self, descriptor, self._identity(info))
        except BaseException:
            self._quiet_closes((descriptor,))
            raise

    def inspect_file(self, handle, name, limit):
        self._owned(handle)
        _need(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", name), "protocol")
        o = self._os
        descriptor = -1
        try:
            descriptor = o.open(name, o.O_RDONLY | o.O_NOFOLLOW | getattr(o, "O_CLOEXEC", 0),
                                dir_fd=handle.descriptor)
            before = self._file_info(o.fstat(descriptor))
            _need(before.kind == "file" and before.links == 1 and before.uid == o.geteuid()
                  and 0 <= before.size <= limit, "namespace")
            h, size, calls = hashlib.sha256(), 0, 0
            while True:
                _need(calls < MAX_READ_CALLS, "capacity")
                calls += 1
                chunk = o.read(descriptor, min(CHUNK, limit - size + 1))
                if not chunk:
                    break
                size += len(chunk)
                _need(size <= limit, "capacity")
                h.update(chunk)
            after = self._file_info(o.fstat(descriptor))
            named = self._file_info(o.stat(name, dir_fd=handle.descriptor, follow_symlinks=False))
            _need(before == after == named and size == before.size, "namespace")
            result = FilePin(name, before.identity, size, h.hexdigest(), before.mode)
        except BaseException:
            self._quiet_closes((descriptor,))
            raise
        else:
            retiring, descriptor = descriptor, -1
            self._close(retiring)
            return result

    def freeze_root(self, handle, expected):
        self._owned(handle)
        infos = self.list_infos(handle)
        _need(set(infos) == set(expected)
              and all(infos[n].identity == identity and infos[n].kind == "file"
                      and infos[n].links == 1 and infos[n].uid == self._os.geteuid()
                      for n, identity in expected.items()), "namespace")
        for name, identity in expected.items():
            descriptor = -1
            try:
                descriptor = self._os.open(name, self._os.O_RDONLY | self._os.O_NOFOLLOW,
                                           dir_fd=handle.descriptor)
                info = self._file_info(self._os.fstat(descriptor))
                _need(info.identity == identity and info.kind == "file"
                      and info.links == 1 and info.uid == self._os.geteuid(), "namespace")
                self._os.fchmod(descriptor, 0o444)
                self._os.fsync(descriptor)
            except BaseException:
                self._quiet_closes((descriptor,))
                raise
            else:
                retiring, descriptor = descriptor, -1
                self._close(retiring)
        self._os.fchmod(handle.descriptor, 0o555)
        self._os.fsync(handle.descriptor)

    def close_root(self, handle):
        _need(type(handle) is _Root and handle.owner is self, "namespace")
        descriptor, handle.descriptor = handle.descriptor, -1
        _need(descriptor >= 0, "closed")
        self._close(descriptor)


class Intake:
    """Factory-issued, non-resumable single-caller intake capability.

    Every public ingress carries the destination and binding again. Backend
    writers remain private. Already downloaded readers stay caller-owned.
    """
    def __init__(self, issuer, fs, handle, path, identity, binding, artifacts):
        _need(issuer is _ISSUER, "namespace")
        self._fs, self._handle, self._path, self._identity = fs, handle, path, identity
        self._uid = handle.uid
        _need(_uint(self._uid, 2**32 - 1), "namespace")
        self._binding = binding
        self._artifacts = artifacts
        self._specs = {a.artifact_id: a for a in artifacts}
        self._ids, self._pins, self._attempted, self._consumed = {}, {}, set(), set()
        self._statuses = {a.artifact_id: "MISSING" for a in artifacts}
        self._metadata_used = 0
        self._fault = None
        self._unknown_close = False
        self._state = "INITIALIZING"
        self._marker = _json({"schema": 1, "path": path, "identity": identity.record(),
            "binding": binding.record(), "artifacts": [a.record() for a in artifacts],
            "caps": {"archive": ARCHIVE_CAP, "total": TOTAL_CAP,
                     "metadata": CONTROL_RESERVE, "files": MAX_FILES}})
        _need(len(self._marker) <= CAPABILITY_CAP, "capacity")
        self._claim = _digest(self._marker)

    @property
    def namespace(self):
        return Namespace(self._path, Identity(self._identity.device, self._identity.inode), self._claim)

    @property
    def first_fault(self):
        return self._fault

    def _fail(self, code):
        if getattr(self._fs, "cleanup_unknown", False):
            self._unknown_close = True
        if self._fault is None:
            self._fault = code if type(code) is str and code in _CODES else "protocol"

    def _check(self, namespace, binding, *, readonly=False):
        _need(type(namespace) is Namespace and type(binding) is Binding, "binding")
        Namespace.__post_init__(namespace)
        Identity.__post_init__(namespace.identity)
        Binding.__post_init__(binding)
        _need(namespace == self.namespace and binding == self._binding, "binding")
        self._fs.check_root(self._handle, self._path, self._identity, readonly=readonly)
        infos = self._fs.list_infos(self._handle)
        _need(type(infos) is dict and len(infos) <= MAX_FILES and set(infos) == set(self._ids), "namespace")
        _need(all(type(info) is FileInfo and info.kind == "file" and info.links == 1
                  and info.uid == self._uid and info.identity == self._ids[name]
                  and 0 <= info.size <= ARCHIVE_CAP
                  for name, info in infos.items()), "namespace")
        _need(sum(info.size for info in infos.values()) <= TOTAL_CAP, "capacity")
        if self._state != "INITIALIZING":
            marker = self._fs.inspect_file(self._handle, CAPABILITY, CAPABILITY_CAP)
            _need(marker.identity == self._ids[CAPABILITY] and marker.size == len(self._marker)
                  and marker.sha256 == self._claim, "namespace")

    def _new_writer(self, namespace, binding, name):
        self._check(namespace, binding)
        _need(name not in self._attempted and len(self._attempted) < MAX_FILES, "duplicate")
        self._attempted.add(name)
        writer = self._fs.create_file(self._handle, name)
        try:
            _need(type(writer.identity) is Identity, "namespace")
            Identity.__post_init__(writer.identity)
            self._ids[name] = writer.identity
            self._pins[name] = None
        except BaseException:
            # Ownership has not reached the caller until this method returns.
            self._close_failed_writer(writer)
            raise
        return writer

    def _close_failed_writer(self, writer):
        try:
            writer.close()
        except BaseException:
            self._unknown_close = True  # unknown descriptor disposition, no retry

    def _metadata(self, namespace, binding, name, body, limit):
        _need(type(body) is bytes and len(body) <= limit
              and self._metadata_used + len(body) <= CONTROL_RESERVE, "capacity")
        self._metadata_used += len(body)  # full debit, including failed/partial attempts
        writer = self._new_writer(namespace, binding, name)
        try:
            for at in range(0, len(body), CHUNK):
                self._check(namespace, binding)
                chunk = body[at:at + CHUNK]
                accepted = writer.write(chunk)
                _need(type(accepted) is int and accepted == len(chunk), "write")
            writer.flush()
            writer.sync()
        except BaseException:
            self._close_failed_writer(writer)
            raise
        else:
            try:
                writer.close()
            except BaseException:
                self._unknown_close = True
                raise
        pin = self._fs.inspect_file(self._handle, name, limit)
        _need(pin.identity == self._ids[name] and pin.size == len(body)
              and pin.sha256 == _digest(body), "metadata")
        self._pins[name] = pin
        return pin

    def _copy(self, namespace, binding, artifact, reader, name):
        # Allocate hashing state before taking ownership of a new output FD.
        h, size, calls, stage = hashlib.sha256(), 0, 0, "read"
        writer = self._new_writer(namespace, binding, name)
        try:
            while True:
                stage = "read"
                _need(calls < MAX_READ_CALLS, "capacity")
                calls += 1
                request = min(CHUNK, artifact.size - size + 1)
                chunk = reader.read(request)
                _need(type(chunk) is bytes and len(chunk) <= request, "protocol")
                if not chunk:
                    break
                _need(size + len(chunk) <= artifact.size, "size")
                stage = "write"
                self._check(namespace, binding)
                accepted = writer.write(chunk)
                _need(type(accepted) is int and accepted == len(chunk), "write")
                h.update(chunk)
                size += len(chunk)
            _need(size == artifact.size, "size")
            _need(h.hexdigest() == artifact.sha256, "digest")
            stage = "write"
            writer.flush()
            writer.sync()
        except BaseException as error:
            self._fail(_failure_code(error, stage if isinstance(error, Exception) else "interrupted"))
            self._close_failed_writer(writer)
            raise
        else:
            try:
                writer.close()
            except BaseException:
                self._unknown_close = True
                self._fail("io")
                raise
        pin = self._fs.inspect_file(self._handle, name, ARCHIVE_CAP)
        _need(pin.identity == self._ids[name] and pin.size == artifact.size
              and pin.sha256 == artifact.sha256, "digest")
        self._pins[name] = pin
        return pin

    def ingest(self, namespace, binding, artifact, reader):
        _need(self._state == "OPEN" and self._fault is None, "closed")
        stage = "binding"
        admitted_id = None
        try:
            self._check(namespace, binding)
            _need(type(artifact) is Artifact, "artifact")
            artifact = Artifact(artifact.artifact_id, artifact.name, artifact.size, artifact.sha256)
            _need(artifact == self._specs.get(artifact.artifact_id), "artifact")
            _need(artifact.artifact_id not in self._consumed, "duplicate")
            self._consumed.add(artifact.artifact_id)  # never retry a failed ID
            admitted_id = artifact.artifact_id
            stage = "read"
            name = "artifact-" + str(artifact.artifact_id) + ".zip"
            pin = self._copy(namespace, binding, artifact, reader, name)
            self._statuses[artifact.artifact_id] = "MATCHED_BYTES"
            stage = "metadata"
            meta = "artifact-" + str(artifact.artifact_id) + ".metadata.json"
            self._metadata(namespace, binding, meta, _json({
                "schema": 1, "binding": self._binding.record(), "capability": self._claim,
                "artifact": artifact.record(), "copy_status": "MATCHED_BYTES",
                "archive": pin.record()}), ARTIFACT_METADATA_CAP)
            self._statuses[artifact.artifact_id] = "COPIED"
            return pin
        except BaseException as error:
            self._fail(_failure_code(error, stage if isinstance(error, Exception) else "interrupted"))
            if admitted_id is not None:
                self._statuses[admitted_id] = "FAILED"
                meta = "artifact-" + str(admitted_id) + ".metadata.json"
                if isinstance(error, Exception) and meta not in self._attempted:
                    try:
                        self._metadata(namespace, binding, meta, _json({
                            "schema": 1, "binding": self._binding.record(),
                            "capability": self._claim, "artifact": artifact.record(),
                            "copy_status": "NEGATIVE", "first_fault": self._fault,
                            "cleanup_unknown": self._unknown_close}), ARTIFACT_METADATA_CAP)
                    except BaseException:
                        pass  # preserve the first exception; no metadata retry
            raise

    def _inventory(self, namespace, binding, *, readonly=False):
        self._check(namespace, binding, readonly=readonly)
        result = {}
        for name in sorted(self._ids):
            limit = ARCHIVE_CAP if name.endswith(".zip") else MANIFEST_CAP
            pin = self._fs.inspect_file(self._handle, name, limit)
            _need(pin.identity == self._ids[name], "namespace")
            prior = self._pins.get(name)
            _need(prior is None or _same_body(prior, pin), "digest")
            if readonly:
                _need(pin.mode == 0o444, "namespace")
            result[name] = pin
        return result

    def _release(self):
        handle, self._handle = self._handle, None
        if handle is not None:
            self._fs.close_root(handle)

    def finalize(self, namespace, binding):
        _need(self._state == "OPEN", "closed")
        self._state = "FINALIZING"  # even failed finalization permanently closes ingress
        try:
            before = self._inventory(namespace, binding)
            missing = [a.artifact_id for a in self._artifacts
                       if self._statuses[a.artifact_id] != "COPIED"]
            if missing:
                self._fail("artifact")
            if getattr(self._fs, "cleanup_unknown", False):
                self._unknown_close = True
                self._fail("io")
            status = "COMPLETE" if not missing and self._fault is None and not self._unknown_close else "NEGATIVE"
            # Immutable on-disk records cannot attest to a later fsync/close.
            # Only the successful return after readonly verification and root
            # close supplies COMPLETE; a readable candidate marker is weaker.
            disk_status = "CLOSED_CANDIDATE" if status == "COMPLETE" else "NEGATIVE"
            manifest = self._metadata(namespace, binding, MANIFEST, _json({
                "schema": 1, "binding": self._binding.record(), "capability": self._claim,
                "status": disk_status, "first_fault": self._fault, "missing": missing,
                "cleanup_unknown": self._unknown_close,
                "required_file_mode": 0o444, "required_root_mode": 0o555,
                "artifacts": [{"artifact": a.record(), "status": self._statuses[a.artifact_id]}
                              for a in self._artifacts],
                "inventory": [p.record() for p in before.values()],
                "accounting": {"declared_archive_reservation": sum(a.size for a in self._artifacts),
                               "control_reserve": CONTROL_RESERVE,
                               "metadata_debited_before_manifest": self._metadata_used}}), MANIFEST_CAP)
            self._metadata(namespace, binding, RESULT, _json({
                "schema": 1, "binding": self._binding.record(), "capability": self._claim,
                "status": disk_status, "first_fault": self._fault, "cleanup_unknown": self._unknown_close,
                "manifest": manifest.record(), "paths": sorted([*self._ids, RESULT]),
                "completion_requires": "Successful finalize return after readonly verification and root close.",
                "scope": "Opaque byte intake only; marker alone is not durability or CI qualification."
            }), CAPABILITY_CAP)
            prepared = self._inventory(namespace, binding)
            self._fs.freeze_root(self._handle, dict(self._ids))
            final = self._inventory(namespace, binding, readonly=True)
            _need(all(_same_body(prepared[n], final[n]) for n in prepared), "digest")
            receipt = {"status": status, "binding": self._binding.record(),
                       "namespace": self.namespace, "files": tuple(final.values()),
                       "first_fault": self._fault, "cleanup_unknown": self._unknown_close,
                       "metadata_debited": self._metadata_used}
        except BaseException as error:
            self._fail(_failure_code(error, "finalize"))
            self._state = "CLOSED"
            try:
                self._release()
            except BaseException:
                self._unknown_close = True
            raise
        else:
            self._state = "CLOSED"
            try:
                self._release()
            except BaseException:
                self._fail("io")
                self._unknown_close = True
                raise
            return receipt

    def close(self):
        """Abandon without cleanup/deletion or positive receipt; never resume."""
        self._state = "CLOSED"
        self._fail("closed")
        try:
            self._release()
        except BaseException:
            self._unknown_close = True
            raise


def create_intake(root, binding, artifacts, *, expected_count=DEFAULT_ARTIFACTS, fs=None):
    """Create a NEW namespace only. There is deliberately no adopt/load API."""
    _root_path(root)
    _need(type(binding) is Binding, "binding")
    binding = Binding(binding.repository, binding.source, binding.run_id, binding.attempt)
    _need(type(artifacts) in (list, tuple) and _uint(expected_count, MAX_ARTIFACTS, positive=True)
          and len(artifacts) == expected_count, "artifact")
    copied = []
    for artifact in artifacts:
        _need(type(artifact) is Artifact, "artifact")
        copied.append(Artifact(artifact.artifact_id, artifact.name, artifact.size, artifact.sha256))
    _need(len({a.artifact_id for a in copied}) == len(copied)
          and len({a.name for a in copied}) == len(copied), "duplicate")
    _need(sum(a.size for a in copied) + CONTROL_RESERVE <= TOTAL_CAP, "capacity")
    copied = tuple(sorted(copied, key=lambda a: a.artifact_id))
    fs = PosixFS() if fs is None else fs
    _need(not getattr(fs, "cleanup_unknown", False), "io")
    handle = fs.create_root(root)
    try:
        identity = handle.identity
        _need(type(identity) is Identity, "namespace")
        intake = Intake(_ISSUER, fs, handle, root, identity, binding, copied)
        intake._metadata(intake.namespace, binding, CAPABILITY, intake._marker, CAPABILITY_CAP)
        intake._state = "OPEN"
        intake._check(intake.namespace, binding)
    except BaseException:
        try:
            fs.close_root(handle)
        except BaseException:
            pass
        raise
    return intake

