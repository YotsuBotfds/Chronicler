"""Bounded, offline source identities read directly from Git objects.

No worktree cleanliness or on-disk checkout identity is implied by this module.
``snapshot`` describes the complete tracked file set of a committed tree; its
mode values are inferred from Git's regular-file modes.  The optional Python
view is a derived read-only selection, never a checkout or an executed package.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import subprocess
import time
from typing import Iterable


MAX_FILES = 4096
MAX_BLOB_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_PATH_BYTES = 4096
COMMAND_TIMEOUT = 60
_MAX_TREE_BYTES = MAX_FILES * (MAX_PATH_BYTES + 128)
_MAX_STDERR_BYTES = 64 * 1024
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PACKAGE = "src/chronicler/"


class SnapshotError(ValueError):
    """Source identity, input, protocol, or resource bounds were not satisfied."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotError(message)


def _canonical_path(value: str) -> str:
    _require(isinstance(value, str) and bool(value), "empty or non-string source path")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise SnapshotError("source path is not UTF-8") from exc
    _require(len(encoded) <= MAX_PATH_BYTES, "source path exceeds byte limit")
    _require(not any(ord(char) < 32 or ord(char) == 127 for char in value),
             "control character in source path")
    _require("\\" not in value and ":" not in value, "noncanonical source path")
    parts = value.split("/")
    _require(all(part not in ("", ".", "..") for part in parts),
             "noncanonical source path")
    _require(not PurePosixPath(value).is_absolute()
             and PurePosixPath(value).as_posix() == value, "noncanonical source path")
    return value


def _git_args(repo: Path, arguments: list[str]) -> list[str]:
    try:
        directory = Path(repo).resolve(strict=True)
    except OSError as exc:
        raise SnapshotError("Git repository path is unavailable") from exc
    _require(directory.is_dir(), "Git repository path is not a directory")
    return ["git", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false",
            "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c",
            "protocol.allow=never", "-C", str(directory), *arguments]


def _git_environment() -> dict[str, str]:
    # Do not inherit an alternate object database, Git directory, injected config,
    # replacement policy, or other caller-specific Git behavior.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1",
                       GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    return environment


class _GitIO:
    """One deadline and bounded binary pipes, including stderr, per command."""

    def __init__(self, repo: Path, arguments: list[str], *, batch: bool = False):
        self.deadline = time.monotonic() + COMMAND_TIMEOUT
        self.buffer = bytearray()
        self.stderr = bytearray()
        self.stdout_eof = False
        self.selector = selectors.DefaultSelector()
        try:
            self.process = subprocess.Popen(
                _git_args(repo, arguments), stdin=subprocess.PIPE if batch else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_git_environment(),
                bufsize=0, close_fds=True)
        except (OSError, ValueError) as exc:
            self.selector.close()
            raise SnapshotError("could not start read-only Git command") from exc
        assert self.process.stdout is not None and self.process.stderr is not None
        for label, stream in (("stdout", self.process.stdout), ("stderr", self.process.stderr)):
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, label)

    def __enter__(self) -> _GitIO:
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.process.poll() is None:
            self.process.kill()
        try:
            self.process.wait(timeout=5)
        finally:
            self.selector.close()
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if stream is not None:
                    stream.close()

    def _remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        _require(remaining > 0, "Git command exceeded time limit")
        return remaining

    def _pump(self) -> None:
        events = self.selector.select(self._remaining())
        _require(bool(events), "Git command exceeded time limit")
        for key, _mask in events:
            try:
                raw = os.read(key.fileobj.fileno(), 64 * 1024)
            except BlockingIOError:
                continue
            if not raw:
                self.selector.unregister(key.fileobj)
                if key.data == "stdout":
                    self.stdout_eof = True
            elif key.data == "stdout":
                self.buffer.extend(raw)
            else:
                self.stderr.extend(raw)
                _require(len(self.stderr) <= _MAX_STDERR_BYTES, "Git stderr exceeded byte limit")

    def send(self, value: bytes) -> None:
        self._remaining()
        _require(self.process.stdin is not None, "Git command has no batch input")
        try:
            # A single bounded object ID is sent only after the previous response
            # was consumed, so the input pipe cannot accumulate unbounded data.
            count = self.process.stdin.write(value)
            _require(count == len(value), "incomplete Git batch request")
        except (BrokenPipeError, OSError) as exc:
            raise SnapshotError("Git batch input closed unexpectedly") from exc

    def exact(self, length: int) -> bytes:
        while len(self.buffer) < length:
            _require(not self.stdout_eof, "truncated Git output")
            self._pump()
        raw = bytes(self.buffer[:length])
        del self.buffer[:length]
        return raw

    def line(self, limit: int = 128) -> bytes:
        while True:
            position = self.buffer.find(b"\n")
            if position >= 0:
                _require(position < limit, "Git protocol header exceeds byte limit")
                return self.exact(position + 1)[:-1]
            _require(len(self.buffer) < limit, "Git protocol header exceeds byte limit")
            _require(not self.stdout_eof, "truncated Git protocol header")
            self._pump()

    def finish(self, *, require_empty: bool = True) -> None:
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        if require_empty:
            _require(not self.buffer, "unexpected trailing Git output")
        while self.selector.get_map():
            self._pump()
            if require_empty:
                _require(not self.buffer, "unexpected trailing Git output")
        try:
            result = self.process.wait(timeout=self._remaining())
        except subprocess.TimeoutExpired as exc:
            raise SnapshotError("Git command exceeded time limit") from exc
        _require(result == 0, "Git command failed: " +
                 self.stderr.decode("utf-8", errors="replace")[:2048].strip())


def _output(repo: Path, arguments: list[str], limit: int) -> bytes:
    with _GitIO(repo, arguments) as process:
        parts = []
        length = 0
        while not process.stdout_eof:
            process._pump()
            if process.buffer:
                length += len(process.buffer)
                _require(length <= limit, "Git output exceeded byte limit")
                parts.append(bytes(process.buffer))
                process.buffer.clear()
        process.finish()
        return b"".join(parts)


def _resolve_commit(repo: Path, ref: str) -> str:
    _require(isinstance(ref, str) and 0 < len(ref) <= 1024,
             "invalid Git source reference")
    _require(not ref.startswith("-") and not any(ord(char) < 33 or ord(char) == 127 for char in ref),
             "invalid Git source reference")
    raw = _output(repo, ["rev-parse", "--verify", "--end-of-options", ref + "^{commit}"], 128)
    value = raw.decode("ascii", errors="strict").strip()
    _require(_SHA1.fullmatch(value) is not None and raw == (value + "\n").encode("ascii"),
             "Git did not resolve a SHA-1 commit")
    return value


def _parse_tree(raw: bytes) -> dict[str, dict]:
    _require(len(raw) <= _MAX_TREE_BYTES, "Git tree output exceeded byte limit")
    _require(not raw or raw.endswith(b"\0"), "unterminated Git tree entry")
    # Count before splitting: malformed output with millions of tiny entries
    # must not allocate millions of list slots before the file bound is checked.
    _require(raw.count(b"\0") <= MAX_FILES, "tracked file count exceeds limit")
    rows = raw.split(b"\0", MAX_FILES + 1)[:-1]
    files = {}
    total = 0
    for row in rows:
        try:
            prefix, encoded_path = row.split(b"\t", 1)
            mode, kind, blob, encoded_size = prefix.split()
            path = _canonical_path(encoded_path.decode("utf-8", errors="strict"))
            blob = blob.decode("ascii", errors="strict")
        except (ValueError, UnicodeError) as exc:
            raise SnapshotError("malformed Git tree entry") from exc
        _require(mode in (b"100644", b"100755") and kind == b"blob",
                 "unsupported tracked source entry")
        _require(_SHA1.fullmatch(blob) is not None, "invalid Git blob identity")
        _require(encoded_size.isdigit(), "invalid Git blob size")
        _require(len(encoded_size) <= 10, "Git blob size exceeds limit")
        size = int(encoded_size)
        _require(size <= MAX_BLOB_BYTES, "Git blob exceeds byte limit")
        total += size
        _require(total <= MAX_TOTAL_BYTES, "tracked source exceeds total byte limit")
        _require(path not in files, "duplicate tracked source path")
        files[path] = {"blob": blob, "bytes": size,
                       "mode": 0o755 if mode == b"100755" else 0o644}
    # Git itself cannot contain file/descendant collisions, but validate parser
    # output independently so malformed input cannot become a filesystem view.
    for path in files:
        parts = path.split("/")
        _require(not any("/".join(parts[:i]) in files for i in range(1, len(parts))),
                 "tracked file conflicts with source directory")
    return files


def _tree(repo: Path, commit: str) -> dict[str, dict]:
    return _parse_tree(_output(repo, ["ls-tree", "-r", "-l", "-z", "--full-tree", commit],
                               _MAX_TREE_BYTES))


def _blob(process: _GitIO, blob: str, size: int, *, collect: bool = False) -> tuple[str, bytes]:
    process.send(blob.encode("ascii") + b"\n")
    expected = (blob + " blob " + str(size)).encode("ascii")
    _require(process.line() == expected, "Git blob header differs from tracked tree")
    digest = hashlib.sha256()
    git_digest = hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0")
    chunks = []
    remaining = size
    while remaining:
        raw = process.exact(min(64 * 1024, remaining))
        remaining -= len(raw)
        digest.update(raw)
        git_digest.update(raw)
        if collect:
            chunks.append(raw)
    _require(process.exact(1) == b"\n", "invalid Git batch blob terminator")
    _require(git_digest.hexdigest() == blob, "Git blob content identity differs")
    return digest.hexdigest(), b"".join(chunks)


def snapshot(repo: Path, ref: str) -> dict:
    """Return full ``{sha, crate_tree, files}`` identity from committed objects.

    Every tracked regular file is included, including files outside Python and
    the native crate.  Byte limits count repeated blobs once per tracked path.
    No filesystem checkout state, cleanliness, or native execution is claimed.
    """
    commit = _resolve_commit(repo, ref)
    files = _tree(repo, commit)
    crate_raw = _output(repo, ["rev-parse", "--verify", commit + ":chronicler-agents"], 128)
    crate = crate_raw.decode("ascii", errors="strict").strip()
    _require(_SHA1.fullmatch(crate) is not None and crate_raw == (crate + "\n").encode("ascii"),
             "invalid native crate tree identity")
    _require(_output(repo, ["cat-file", "-t", crate], 128) == b"tree\n",
             "native crate source is not a tree")
    cache: dict[str, tuple[int, str]] = {}
    with _GitIO(repo, ["cat-file", "--batch"], batch=True) as process:
        for record in files.values():
            blob, size = record["blob"], record["bytes"]
            if blob not in cache:
                content_sha, _raw = _blob(process, blob, size)
                cache[blob] = (size, content_sha)
            _require(cache[blob][0] == size, "inconsistent repeated Git blob size")
            record["sha256"] = cache[blob][1]
        process.finish()
    return {"sha": commit, "crate_tree": crate, "files": files}


def verify_snapshot(repo: Path, expected: dict) -> dict:
    """Require exact full-set equality with a frozen producer snapshot."""
    _validate_snapshot(expected)
    actual = snapshot(repo, expected["sha"])
    _require(actual == expected, "frozen source snapshot differs from committed tracked files")
    return actual


def _validate_snapshot(value: dict) -> None:
    _require(isinstance(value, dict) and set(value) == {"sha", "crate_tree", "files"},
             "invalid source snapshot fields")
    for field in ("sha", "crate_tree"):
        _require(isinstance(value[field], str) and _SHA1.fullmatch(value[field]) is not None,
                 "invalid source snapshot object identity")
    files = value["files"]
    _require(isinstance(files, dict) and len(files) <= MAX_FILES,
             "invalid source snapshot file set")
    total = 0
    for path, record in files.items():
        _canonical_path(path)
        _require(isinstance(record, dict) and set(record) == {"bytes", "sha256", "mode", "blob"},
                 "invalid source snapshot file record")
        _require(type(record["bytes"]) is int and 0 <= record["bytes"] <= MAX_BLOB_BYTES,
                 "invalid source snapshot file size")
        total += record["bytes"]
        _require(total <= MAX_TOTAL_BYTES, "source snapshot exceeds total byte limit")
        _require(type(record["mode"]) is int and record["mode"] in (0o644, 0o755),
                 "invalid source snapshot file mode")
        _require(isinstance(record["blob"], str) and _SHA1.fullmatch(record["blob"]) is not None,
                 "invalid source snapshot blob")
        _require(isinstance(record["sha256"], str) and _SHA256.fullmatch(record["sha256"]) is not None,
                 "invalid source snapshot content digest")


def read_blob(repo: Path, ref: str, path: str, limit: int = 2 * 1024 * 1024) -> bytes:
    """Read one exact tracked regular file after tree, size, and Git-blob checks."""
    path = _canonical_path(path)
    _require(type(limit) is int and 0 <= limit <= MAX_BLOB_BYTES, "invalid blob read limit")
    commit = _resolve_commit(repo, ref)
    files = _tree(repo, commit)
    _require(path in files, "requested source path is not tracked")
    record = files[path]
    _require(record["bytes"] <= limit, "requested source blob exceeds read limit")
    with _GitIO(repo, ["cat-file", "--batch"], batch=True) as process:
        _digest, raw = _blob(process, record["blob"], record["bytes"], collect=True)
        process.finish()
    return raw


def _package_files(files: dict) -> list[str]:
    return sorted(path for path in files if path.startswith(_PACKAGE) and path.endswith(".py"))


def package_digest(source: dict) -> str:
    """Match batch_manifest's digest of all tracked package Python files."""
    _validate_snapshot(source)
    paths = _package_files(source["files"])
    _require(bool(paths), "source snapshot has no chronicler Python package")
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path[len(_PACKAGE):].encode("utf-8") + b"\0" +
                      source["files"][path]["sha256"].encode("ascii") + b"\n")
    return digest.hexdigest()


def materialize_python_view(repo: Path, ref: str, destination: Path,
                            script_paths: Iterable[str]) -> dict[str, dict]:
    """Write all package .py files and exact selected scripts to a fresh view.

    Selected scripts must be tracked ``scripts/**/*.py`` paths.  The destination
    must not exist.  Files become 0444 and directories 0555, independently of
    the source modes retained in ``snapshot``; returned records contain only
    ``{bytes, sha256}``.  Nothing is imported or executed.  On failure, a partial
    derived directory may remain for inspection, and the call does not succeed.
    """
    source = snapshot(repo, ref)
    selected = _package_files(source["files"])
    _require(bool(selected), "source snapshot has no chronicler Python package")
    _require(not isinstance(script_paths, (str, bytes)), "script paths must be an iterable of paths")
    scripts = set()
    for path in script_paths:
        _require(len(scripts) < MAX_FILES, "selected script count exceeds limit")
        path = _canonical_path(path)
        _require(path.startswith("scripts/") and path.endswith(".py"),
                 "selected path is not a Python script")
        _require(path in source["files"], "selected script is not tracked")
        _require(path not in scripts, "duplicate selected script")
        scripts.add(path)
    selected = sorted(set(selected) | scripts)
    target = Path(destination)
    _require(target.name not in ("", ".", ".."), "invalid Python view destination")
    try:
        parent = target.parent.resolve(strict=True)
        target = parent / target.name
        target.mkdir(mode=0o700)  # exclusive: existing paths, including links, fail
    except OSError as exc:
        raise SnapshotError("Python view destination must be fresh with an existing parent") from exc
    directories = {target}
    result = {}
    with _GitIO(repo, ["cat-file", "--batch"], batch=True) as process:
        for relative in selected:
            expected = source["files"][relative]
            digest, raw = _blob(process, expected["blob"], expected["bytes"], collect=True)
            _require(digest == expected["sha256"], "Python view source digest changed")
            path = target.joinpath(*relative.split("/"))
            for directory in reversed(list(path.parents)):
                if directory == target or target in directory.parents:
                    if directory not in directories:
                        directory.mkdir(mode=0o700)
                        directories.add(directory)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(raw)
            _require(path.stat().st_size == expected["bytes"], "incomplete Python view write")
            # Hash the resulting bytes, independently of the data sent to write.
            written = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(64 * 1024), b""):
                    written.update(block)
            _require(written.hexdigest() == digest, "Python view bytes differ after write")
            path.chmod(0o444)
            result[relative] = {"bytes": expected["bytes"], "sha256": digest}
        process.finish()
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        directory.chmod(0o555)
    return result


__all__ = ["SnapshotError", "snapshot", "verify_snapshot", "read_blob", "package_digest",
           "materialize_python_view"]
