"""Explicit optional ordinary-artifact admission; no owner/log integration.

The ledger is pure and monotonic. The POSIX facade owns a fresh output root,
pre-admits complete encoded bodies, and never exposes its descriptors. Neither
class is a filesystem sandbox or a complete study aggregate enforcer: caller
coverage, controller/log admission, Arrow byte parity and memory fit need their
separate qualification. No stream/seek API or checkpoint support is supplied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import io
import locale
import os
from pathlib import Path
import stat
from typing import Any

ORDINARY_BYTE_CAP = 16_777_216
CARE_BYTE_CAP = 16_777_216
TOTAL_BYTE_CAP = 33_554_432
ORDINARY_TERMINAL_RESERVE = 131_072
CARE_METADATA_RESERVE = 65_536
MAX_PATH_BYTES = 512
MAX_PATH_DEPTH = 16
MAX_OWNED_PATHS = 256
MAX_ATTEMPTS = 65_536
_FAULT_CODES = frozenset({
    "capacity", "terminal", "path", "alias", "protocol", "replay", "bounds",
    "encoding", "io", "closed", "checkpoint",
})
_OPERATIONS = frozenset({"direct", "atomic"})
_TERMINAL_ROLE_PATHS = (("terminal", "terminal.json"), ("freeze", "freeze.json"))


class ArtifactBudgetError(ValueError):
    """Closed admission failure; the first fault remains on the ledger."""


@dataclass(frozen=True, slots=True)
class ArtifactFault:
    code: str
    attempt: int


@dataclass(frozen=True, slots=True)
class WriteAdmission:
    """One exact write-attempt grant, accepted only by its issuing ledger."""

    path: str
    byte_count: int
    operation: str
    attempt: int
    terminal_role: str | None
    _issuer: object = field(repr=False, compare=False)


def _relative_parts(path: str) -> tuple[str, ...]:
    if (not isinstance(path, str) or not path or len(path) > MAX_PATH_BYTES
            or len(path.encode("utf-8")) > MAX_PATH_BYTES
            or "\\" in path or "\x00" in path or path.startswith("/")):
        raise ArtifactBudgetError("invalid relative artifact path")
    parts = tuple(path.split("/"))
    if (len(parts) > MAX_PATH_DEPTH or any(part in ("", ".", "..") for part in parts)
            or any(ord(char) < 32 or ord(char) == 127 for char in path)):
        raise ArtifactBudgetError("invalid relative artifact path")
    return parts


class MonotonicArtifactLedger:
    """Pure ordinary-half ledger; reduced limits are useful for fake contracts.

    The production default is exactly 16 MiB, including a prepaid 128 KiB
    terminal reserve. No constructor can increase either production maximum.
    A positive reserve also protects both root terminal names and two slots
    inside the unchanged attempt/path ceilings. A zero reserve is ordinary-only
    fake semantics: all original ordinary count slots remain available and no
    terminal role is accepted. Care admission, owner IPC and cross-process
    linearization are not implemented. This object is a single-caller ledger.
    """

    def __init__(self, *, capacity: int = ORDINARY_BYTE_CAP,
                 terminal_reserve: int = ORDINARY_TERMINAL_RESERVE) -> None:
        if (type(capacity) is not int or not 0 < capacity <= ORDINARY_BYTE_CAP
                or type(terminal_reserve) is not int
                or not 0 <= terminal_reserve <= min(capacity, ORDINARY_TERMINAL_RESERVE)):
            raise ArtifactBudgetError("invalid ordinary budget limits")
        self._capacity = capacity
        self._terminal_reserve = terminal_reserve
        self._charged = terminal_reserve
        self._attempt = 0
        self._ordinary_attempts = 0
        self._terminal_paths = (frozenset(path for _, path in _TERMINAL_ROLE_PATHS)
                                if terminal_reserve else frozenset())
        self._issuer = object()
        self._pending: dict[int, WriteAdmission] = {}
        self._consumed: set[int] = set()
        self._paths: set[str] = set(self._terminal_paths)
        self._terminal_roles: set[str] = set()
        self._fault: ArtifactFault | None = None

    @property
    def charged_bytes(self) -> int:
        return self._charged

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def first_fault(self) -> ArtifactFault | None:
        return self._fault

    def fail(self, code: str) -> None:
        if self._fault is None:
            self._fault = ArtifactFault(code if type(code) is str and code in _FAULT_CODES else "protocol", self._attempt)

    def require_healthy(self) -> None:
        if self._fault is not None:
            raise ArtifactBudgetError("artifact budget fault: " + self._fault.code)

    def reserve(self, path: str, byte_count: int, *, operation: str = "direct",
                terminal_role: str | None = None) -> WriteAdmission:
        """Debit a full attempt before any file mutation; never refund it.

        Only the two prepaid ordinary terminal roles may be admitted after a
        sticky fault. Their complete bodies are each reserved once, even if
        their later write fails. Root paths and two count slots are protected
        whenever terminal_reserve is positive. This is not schema validation.
        """
        try:
            _relative_parts(path)
        except (ArtifactBudgetError, UnicodeError):
            self.fail("path")
            raise ArtifactBudgetError("invalid relative artifact path") from None
        if (type(byte_count) is not int or not 0 <= byte_count <= self._capacity
                or type(operation) is not str or operation not in _OPERATIONS
                or (terminal_role is not None and type(terminal_role) is not str)
                or self._attempt >= MAX_ATTEMPTS
                or (path not in self._paths and len(self._paths) >= MAX_OWNED_PATHS)):
            self.fail("bounds")
            raise ArtifactBudgetError("artifact admission bounds")
        if terminal_role is None:
            self.require_healthy()
            if path.split("/", 1)[0] in self._terminal_paths:
                self.fail("terminal")
                raise ArtifactBudgetError("ordinary use of reserved terminal path")
            if self._ordinary_attempts >= MAX_ATTEMPTS - len(self._terminal_paths):
                self.fail("bounds")
                raise ArtifactBudgetError("ordinary artifact attempt bounds")
            if self._charged + byte_count > self._capacity:
                self.fail("capacity")
                raise ArtifactBudgetError("ordinary artifact capacity")
            self._charged += byte_count
            self._ordinary_attempts += 1
        else:
            terminal_max = min(8_192, self._terminal_reserve)
            limits = {"terminal": terminal_max,
                      "freeze": self._terminal_reserve - terminal_max}
            if (not self._terminal_paths or terminal_role not in limits
                    or terminal_role in self._terminal_roles
                    or path != dict(_TERMINAL_ROLE_PATHS).get(terminal_role)
                    or operation != "direct" or byte_count > limits[terminal_role]):
                self.fail("terminal")
                raise ArtifactBudgetError("ordinary terminal reservation")
            self._terminal_roles.add(terminal_role)
        self._attempt += 1
        self._paths.add(path)
        token = WriteAdmission(path, byte_count, operation, self._attempt,
                               terminal_role, self._issuer)
        self._pending[token.attempt] = token
        return token

    def consume(self, token: WriteAdmission) -> None:
        """Consume this exact object once; copied/forged/replayed tokens fail."""
        if (not isinstance(token, WriteAdmission) or token._issuer is not self._issuer
                or type(token.attempt) is not int
                or self._pending.get(token.attempt) is not token
                or token.attempt in self._consumed):
            self.fail("replay")
            raise ArtifactBudgetError("invalid or replayed artifact admission")
        if token.terminal_role is None:
            self.require_healthy()
        self._consumed.add(token.attempt)
        del self._pending[token.attempt]

    def __getstate__(self) -> Any:
        self.fail("checkpoint")
        raise ArtifactBudgetError("artifact budget checkpoint support is unqualified")


def _encoded_text(text: str, encoding: str | None) -> bytes:
    # Path.write_text(newline=None) translates LF on non-POSIX platforms.
    # Budgeted output supports only the explicitly qualified POSIX LF/UTF-8
    # shape; the default None caller branches never invoke this function.
    if os.name != "posix" or os.linesep != "\n" or not isinstance(text, str):
        raise ArtifactBudgetError("unsupported budgeted text runtime")
    chosen = encoding
    if chosen is None:
        chosen = io.text_encoding(None)
        if chosen == "locale":
            chosen = locale.getencoding()
    if (not isinstance(chosen, str) or len(chosen) > 32
            or chosen.lower().replace("-", "").replace("_", "") != "utf8"):
        raise ArtifactBudgetError("unsupported budgeted text encoding")
    return text.encode("utf-8")


class ArtifactBudget:
    """Caller-owned POSIX file facade for the audited ordinary writer paths.

    ``root`` must be a fresh absolute directory name: this constructor creates
    it exclusively. All writer paths must be absolute descendants. Directory
    FDs pin traversal, existing files must be this instance's single-link regular
    files, and deterministic exclusive temp names require no RNG. Python-private
    attributes are not an adversarial sandbox; external mutation invalidates
    evidence. No descriptor/open/seek/stream interface is exposed.
    """

    def __init__(self, root: Path, *, ledger: MonotonicArtifactLedger | None = None) -> None:
        if ledger is not None and type(ledger) is not MonotonicArtifactLedger:
            raise ArtifactBudgetError("exact ordinary ledger required")
        self._ledger = ledger if ledger is not None else MonotonicArtifactLedger()
        self._ledger.require_healthy()
        self._root = Path(root)
        self._closed = False
        self._owned_files: dict[str, tuple[int, int]] = {}
        self._owned_directories: dict[str, tuple[int, int]] = {}
        self._root_fd = -1
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or not self._root.is_absolute() or ".." in self._root.parts
                or not self._root.name):
            self._ledger.fail("path")
            raise ArtifactBudgetError("fresh absolute POSIX artifact root required")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        parent_fd = -1
        child_fd = -1
        root_fd = -1
        try:
            # All acquisition, handoff and final-parent cleanup belongs to this
            # region. A newly opened descriptor stays tracked until transfer.
            parent_fd = os.open("/", flags)
            for part in self._root.parts[1:-1]:
                child_fd = os.open(part, flags, dir_fd=parent_fd)
                retiring = parent_fd
                parent_fd = -1
                os.close(retiring)
                parent_fd = child_fd
                child_fd = -1
            os.mkdir(self._root.name, mode=0o700, dir_fd=parent_fd)
            root_fd = os.open(self._root.name, flags, dir_fd=parent_fd)
            info = os.fstat(root_fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ArtifactBudgetError("owned private artifact root required")
            self._owned_directories[""] = (info.st_dev, info.st_ino)
            retiring = parent_fd
            parent_fd = -1
            os.close(retiring)
            # Publish only after final-parent close succeeds. Keep the local
            # root tracked through this last assignment until normal return.
            self._root_fd = root_fd
        except BaseException:
            self._ledger.fail("io")
            # Invalidating before each attempt prevents retry of a close with
            # unknown disposition. Cleanup errors do not replace the first
            # exception, and cannot prevent the other known closes.
            descriptor = root_fd
            root_fd = -1
            if descriptor == child_fd:
                child_fd = -1
            if descriptor == parent_fd:
                parent_fd = -1
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException:
                    self._ledger.fail("io")
            descriptor = child_fd
            child_fd = -1
            if descriptor == parent_fd:
                parent_fd = -1
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException:
                    self._ledger.fail("io")
            descriptor = parent_fd
            parent_fd = -1
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException:
                    self._ledger.fail("io")
            raise

    @property
    def ledger(self) -> MonotonicArtifactLedger:
        return self._ledger

    def fail(self, code: str) -> None:
        """Latch a closed upstream output fault without replacing its exception."""
        self._ledger.fail(code)

    def require_healthy(self) -> None:
        if self._closed:
            self._ledger.fail("closed")
        self._ledger.require_healthy()

    def _relative(self, path: Path, *, directory: bool = False) -> str:
        try:
            raw = os.fspath(path)
        except TypeError:
            self._ledger.fail("path")
            raise ArtifactBudgetError("invalid artifact path") from None
        if (not isinstance(raw, str) or "\\" in raw or "\x00" in raw
                or any(part in (".", "..") for part in raw.split("/"))):
            self._ledger.fail("path")
            raise ArtifactBudgetError("artifact path alias refused")
        candidate = Path(raw)
        if not candidate.is_absolute():
            self._ledger.fail("path")
            raise ArtifactBudgetError("absolute artifact path required")
        try:
            relative = candidate.relative_to(self._root).as_posix()
            if directory and relative == ".":
                return ""
            _relative_parts(relative)
        except (ValueError, UnicodeError):
            self._ledger.fail("path")
            raise ArtifactBudgetError("artifact path outside owned root") from None
        return relative

    def _directory_fd(self, parts: tuple[str, ...], *, create: bool) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        current = -1
        child = -1
        prefix: list[str] = []
        try:
            # Both protected records are root files, so they need no new ancestor
            # slots. Ordinary directory creation must not claim either root name.
            if parts and parts[0] in self._ledger._terminal_paths:
                raise ArtifactBudgetError("reserved terminal directory path")
            current = os.dup(self._root_fd)
            for part in parts:
                prefix.append(part)
                key = "/".join(prefix)
                try:
                    child = os.open(part, flags, dir_fd=current)
                except FileNotFoundError:
                    if key in self._owned_directories:
                        raise ArtifactBudgetError("owned artifact directory disappeared") from None
                    if not create or len(self._owned_directories) >= MAX_OWNED_PATHS:
                        raise ArtifactBudgetError("artifact directory bounds") from None
                    os.mkdir(part, mode=0o700, dir_fd=current)
                    child = os.open(part, flags, dir_fd=current)
                    info = os.fstat(child)
                    self._owned_directories[key] = (info.st_dev, info.st_ino)
                info = os.fstat(child)
                if (self._owned_directories.get(key) != (info.st_dev, info.st_ino)
                        or info.st_uid != os.geteuid()):
                    raise ArtifactBudgetError("foreign artifact directory")
                # A close that raises has unknown disposition: invalidate the
                # local before attempting it, and never retry that descriptor.
                parent = current
                current = -1
                os.close(parent)
                current = child
                child = -1
            return current
        except BaseException:
            self._ledger.fail("io")
            # child remains owned until transfer, including fstat/map-insertion
            # failures. Try both remaining closes without masking the first
            # exception or claiming a raised close succeeded.
            descriptor = child
            child = -1
            if descriptor == current:
                current = -1
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException:
                    self._ledger.fail("io")
            descriptor = current
            current = -1
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException:
                    self._ledger.fail("io")
            raise

    def ensure_directory(self, path: Path) -> None:
        self.require_healthy()
        relative = self._relative(path, directory=True)
        try:
            fd = self._directory_fd(tuple(relative.split("/")) if relative else (), create=True)
            os.close(fd)
        except BaseException:
            self._ledger.fail("io")
            raise

    def _existing(self, parent_fd: int, name: str, relative: str) -> os.stat_result | None:
        try:
            info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            if relative in self._owned_files:
                raise ArtifactBudgetError("owned artifact disappeared") from None
            return None
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or self._owned_files.get(relative) != (info.st_dev, info.st_ino)):
            raise ArtifactBudgetError("foreign or aliased artifact")
        return info

    def write_text(self, path: Path, text: str, *, encoding: str | None = None,
                   atomic: bool = False) -> None:
        self.require_healthy()
        if isinstance(text, str) and len(text) > self._ledger.capacity:
            self._ledger.fail("bounds")
            raise ArtifactBudgetError("artifact text exceeds ordinary capacity")
        try:
            data = _encoded_text(text, encoding)
        except BaseException:
            self._ledger.fail("encoding")
            raise
        self.write_bytes(path, data, atomic=atomic)

    def write_bytes(self, path: Path, content: bytes | bytearray | memoryview, *,
                    atomic: bool = False) -> None:
        self.require_healthy()
        if type(atomic) is not bool or not isinstance(content, (bytes, bytearray, memoryview)):
            self._ledger.fail("protocol")
            raise ArtifactBudgetError("invalid artifact write request")
        exact_length = content.nbytes if isinstance(content, memoryview) else len(content)
        if exact_length > self._ledger.capacity:
            self._ledger.fail("bounds")
            raise ArtifactBudgetError("artifact bytes exceed ordinary capacity")
        try:
            data = bytes(content)
        except BaseException:
            self._ledger.fail("bounds")
            raise
        relative = self._relative(path)
        token = self._ledger.reserve(relative, len(data), operation="atomic" if atomic else "direct")
        self._write(token, data)

    def write_terminal(self, path: Path, content: bytes, *, role: str) -> None:
        """One reserved metadata body; future owner/schema integration is held."""
        if (self._closed or type(content) is not bytes
                or type(role) is not str or role not in ("terminal", "freeze")):
            self._ledger.fail("protocol")
            raise ArtifactBudgetError("invalid terminal artifact request")
        relative = self._relative(path)
        token = self._ledger.reserve(relative, len(content), terminal_role=role)
        self._write(token, content)

    def _check_file_slot(self, relative: str, terminal_role: str | None) -> None:
        if relative in self._owned_files:
            return
        reserved = self._ledger._terminal_paths
        if terminal_role is None:
            ordinary_live = sum(path not in reserved for path in self._owned_files)
            if ordinary_live >= MAX_OWNED_PATHS - len(reserved):
                raise ArtifactBudgetError("ordinary live artifact count bounds")
        if len(self._owned_files) >= MAX_OWNED_PATHS:
            raise ArtifactBudgetError("owned artifact count bounds")

    def _write(self, token: WriteAdmission, data: bytes) -> None:
        if (not isinstance(token, WriteAdmission) or type(data) is not bytes
                or len(data) != token.byte_count):
            self._ledger.fail("protocol")
            raise ArtifactBudgetError("artifact body does not match its admission")
        self._ledger.consume(token)
        parts = _relative_parts(token.path)
        parent_fd = -1
        fd = -1
        temporary: str | None = None
        failure: BaseException | None = None
        try:
            parent_fd = self._directory_fd(parts[:-1], create=True)
            existing = self._existing(parent_fd, parts[-1], token.path)
            name = parts[-1]
            target_relative = token.path
            flags = os.O_WRONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            mode = 0o666 if existing is None else stat.S_IMODE(existing.st_mode) & 0o777
            if token.operation == "atomic":
                temporary = "." + name + ".artifact-budget-" + format(token.attempt, "08x") + ".tmp"
                target_relative = "/".join((*parts[:-1], temporary))
                _relative_parts(target_relative)
                self._check_file_slot(target_relative, token.terminal_role)
                fd = os.open(temporary, flags | os.O_CREAT | os.O_EXCL, mode, dir_fd=parent_fd)
                if existing is not None:
                    os.fchmod(fd, mode)
            elif existing is None:
                self._check_file_slot(target_relative, token.terminal_role)
                fd = os.open(name, flags | os.O_CREAT | os.O_EXCL, mode, dir_fd=parent_fd)
            else:
                fd = os.open(name, flags, dir_fd=parent_fd)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or (token.operation == "direct" and existing is not None
                        and (info.st_dev, info.st_ino) != (existing.st_dev, existing.st_ino))):
                raise ArtifactBudgetError("artifact changed before write")
            self._check_file_slot(target_relative, token.terminal_role)
            self._owned_files[target_relative] = (info.st_dev, info.st_ino)
            if token.operation == "direct" and existing is not None:
                # Only the already-identified owned inode is truncated, after
                # complete body admission. This operation never earns a refund.
                os.ftruncate(fd, 0)
            stream = os.fdopen(fd, "wb", buffering=0)
            fd = -1
            try:
                accepted = stream.write(data)
                if type(accepted) is not int or accepted != len(data):
                    raise OSError("short artifact write")
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                # Closing must not replace the first write/flush/fsync error.
                try:
                    stream.close()
                except BaseException:
                    self._ledger.fail("io")
                raise
            else:
                stream.close()
            if temporary is not None:
                # Check the destination again before replacing the owned target.
                self._existing(parent_fd, name, token.path)
                os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                self._owned_files[token.path] = self._owned_files.pop(target_relative)
                temporary = None
            os.fsync(parent_fd)
        except BaseException as exc:
            failure = exc
            self._ledger.fail("io")
            # Owned failed temporary and direct partial files deliberately stay.
            raise
        finally:
            cleanup_error: BaseException | None = None
            for descriptor in (fd, parent_fd):
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except BaseException as exc:
                        self._ledger.fail("io")
                        if cleanup_error is None:
                            cleanup_error = exc
            if failure is None and cleanup_error is not None:
                raise cleanup_error

    def unlink(self, path: Path) -> None:
        """Existing ordinary stale-off semantics, restricted to owned files."""
        self.require_healthy()
        relative = self._relative(path)
        parts = _relative_parts(relative)
        if parts[0] in self._ledger._terminal_paths:
            self._ledger.fail("terminal")
            raise ArtifactBudgetError("ordinary unlink of reserved terminal path")
        parent_fd = -1
        try:
            parent_fd = self._directory_fd(parts[:-1], create=False)
            existing = self._existing(parent_fd, parts[-1], relative)
            if existing is None:
                raise FileNotFoundError(path)
            os.unlink(parts[-1], dir_fd=parent_fd)
            del self._owned_files[relative]
            os.fsync(parent_fd)
        except FileNotFoundError:
            return
        except BaseException:
            self._ledger.fail("io")
            raise
        finally:
            if parent_fd >= 0:
                os.close(parent_fd)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            if self._root_fd >= 0:
                fd = self._root_fd
                self._root_fd = -1
                try:
                    os.close(fd)
                except BaseException:
                    self._ledger.fail("io")
                    raise

    def __enter__(self) -> ArtifactBudget:
        self.require_healthy()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __getstate__(self) -> Any:
        self._ledger.fail("checkpoint")
        raise ArtifactBudgetError("artifact budget checkpoint support is unqualified")
