"""Selected C60 ownership and bounded intake; fixed trace=False adapter only.

C60 original3b941645a42c8c159a2f8ce9e383d484066b6355 controller SHA256
60bb77212757f632d8d80ed226f94e6ef9864134c4453b5affeb51dc059b9dd1.
Only direct_children, Cancellation, SubreaperLease and make_supervisor are copied
verbatim. Their active globals are explicit below; R44 remains the exact source
owned resolver. Original27f base ownership lives in exact_near_screen_session.
B primitives/constants come from original3b941645 bridge SHA256 cb87ff673817fc655beb39cce88c39295cfa87dcd787e108e2cbf85026965373.
The optional original strace branch is excluded from this fixed screen: the
owner never passes trace=True, and its otherwise omitted dependency refuses.
"""
from __future__ import annotations
import ctypes
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
import types
from wealth_floor_build_resources import memory_admission
import exact_near_screen_session as legacy

_BRIDGE_PRIMITIVES = r"""
class BridgeRefused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise BridgeRefused(message)


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()

_CREDENTIAL = re.compile(r"(?i)(?:authorization\s*[:=]|bearer\s+|--(?:token|password|secret|credential)(?:=|\Z)|"
                         r"(?:[?&]|\b)(?:access_token|api_key|password|secret|signature|sig)=|[a-z]+://[^/\s]*@)")
"""
B = types.ModuleType("exact_near_screen_B_primitives")
B.__dict__.update(json=json, re=re)
exec(compile(_BRIDGE_PRIMITIVES, "<selected-qualified-B-primitives>", "exec"), B.__dict__)
B.MIB = 1024**2
B.MAX_TRACE_LINE = 256 * 1024
B.MAX_PENDING_EXECS = 2048

def _unsupported_trace():
    raise B.BridgeRefused("trace branch is outside this fixed experiment")

B.TraceAccumulator = _unsupported_trace
MAX_LOG_BYTES = 8 * B.MIB
MAX_PROGRESS_BYTES = 8 * B.MIB

def direct_children(*, proc_root=Path("/proc"), process_id=None, waitid_fn=None):
    """Bounded direct-child observation, including kernels without PROC_CHILDREN.

    An empty non-atomic proc observation needs the kernel's ECHILD confirmation.
    WNOWAIT preserves exited leaders and all later wait/accounting ownership.
    Fixture roots and waitid functions are used only by pure tests.
    """
    owner = os.getpid() if process_id is None else process_id
    waitid_fn = os.waitid if waitid_fn is None else waitid_fn
    B.require(type(owner) is int and owner > 0, "invalid controller PID")
    root = Path(proc_root)
    try:
        with (root / "self/task" / str(owner) / "children").open("rb") as stream:
            raw = stream.read(65537)
        B.require(len(raw) <= 65536, "owned-child list byte bound")
        values = raw.split()
        B.require(len(values) <= B.MAX_PENDING_EXECS and all(value.isdigit() for value in values), "owned-child list invalid")
        children = [int(value) for value in values]
        B.require(len(set(children)) == len(children) and all(pid > 0 for pid in children), "owned-child list aliases")
    except FileNotFoundError:
        children, observed = [], 0
        with os.scandir(root) as entries:
            for entry in entries:
                if not entry.name.isascii() or not entry.name.isdecimal():
                    continue
                observed += 1
                B.require(observed <= 32768, "proc process scan bound exceeded")
                try:
                    with (root / entry.name / "stat").open("rb") as stream:
                        raw = stream.read(65537)
                    B.require(len(raw) <= 65536, "proc stat byte bound exceeded")
                    fields = raw.rsplit(b")", 1)[1].split()
                    pid, parent, birth = int(raw.split(b" ", 1)[0]), int(fields[1]), int(fields[19])
                    B.require(pid == int(entry.name) and parent >= 0 and birth >= 0, "proc process identity invalid")
                except (FileNotFoundError, ProcessLookupError):
                    continue
                except (ValueError, IndexError, OSError) as exc:
                    raise B.BridgeRefused("proc process visibility invalid") from exc
                if parent == owner:
                    children.append(pid)
                    B.require(len(children) <= B.MAX_PENDING_EXECS, "owned-child count bound exceeded")
    if not children:
        try:
            waitid_fn(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return []
        raise B.BridgeRefused("empty proc scan lacks kernel ECHILD confirmation")
    return sorted(children)


class Cancellation:
    """Signals request cancellation; they never interrupt owned-child cleanup."""

    def __init__(self):
        self.cancelled = False

    def __enter__(self):
        self.previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        for sig in self.previous:
            signal.signal(sig, self.request)
        return self

    def request(self, _signal, _frame):
        self.cancelled = True

    def check(self):
        B.require(not self.cancelled, "controller cancellation requested")

    def __exit__(self, typ, value, traceback):
        try:
            if typ is None:
                self.check()
        finally:
            for sig, handler in self.previous.items():
                signal.signal(sig, handler)


class SubreaperLease:
    """Exclusive adoption catches descendants which leave a private session."""

    def __enter__(self):
        B.require(sys.platform == "linux" and not direct_children(), "exclusive Linux controller required")
        self.libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        B.require(self.libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0 and previous.value == 0,
                  "existing subreaper ownership refused")
        B.require(self.libc.prctl(36, 1, 0, 0, 0) == 0, "cannot establish subreaper ownership")
        return self

    def reap_orphans(self, exclude=()):
        excluded = set(exclude)
        deadline = time.monotonic() + 5
        found = False
        while True:
            children = [pid for pid in direct_children() if pid not in excluded]
            if not children:
                return found
            found = True
            B.require(time.monotonic() < deadline, "adopted child cleanup incomplete")
            for pid in children:
                try:
                    fd = os.pidfd_open(pid)
                except ProcessLookupError:
                    continue
                try:
                    if pid in direct_children():
                        try:
                            signal.pidfd_send_signal(fd, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                finally:
                    os.close(fd)
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            time.sleep(.01)

    def __exit__(self, typ, value, traceback):
        try:
            orphaned = self.reap_orphans()
            B.require(not orphaned, "unexpected adopted descendants invalidate completed build")
        finally:
            B.require(self.libc.prctl(36, 0, 0, 0, 0) == 0, "subreaper restoration failed")


def make_supervisor(legacy, root, deadline, lease, cancellation=None):
    class Supervisor(legacy.Supervisor):
        """Same 27f leader/session/pidfd pattern, bounded pipe intake."""

        def __init__(self):
            super().__init__(root, deadline - 25, budget_label="reserved 30-minute build")
            self.overall_deadline = deadline
            self.last_stdout = b""
            self.last_trace = None

        def check(self, *, final=False):
            if cancellation is not None:
                cancellation.check()
            B.require(time.monotonic() <= (self.overall_deadline if final else self.deadline), "controller wall deadline exceeded")
            if final:
                observed = memory_admission()
                B.require(shutil.disk_usage(self.root).free >= 3 * 1024**3 and observed["available_bytes"] >= 1024**3,
                          "final effective resource floor refused")

        def event(self, kind, **fields):
            path = self.root / "progress.jsonl"
            raw = B.canonical_bytes(dict(event=kind, monotonic=time.monotonic(), **fields))
            B.require((path.stat().st_size if path.exists() else 0) + len(raw) <= MAX_PROGRESS_BYTES, "progress record cap")
            with path.open("ab") as stream:
                stream.write(raw)

        def admission(self, phase, disk, ram):
            observed = memory_admission()
            free = shutil.disk_usage(self.root).free
            self.event("resources", phase=phase, disk_free_bytes=free, memory=observed)
            B.require(free >= disk * 1024**3 and observed["available_bytes"] >= ram * 1024**3, "effective resource admission refused")

        def command(self, label, command, env, cwd, *, allowed_exit_codes=(0,), trace=False):
            B.require(label.replace("-", "").replace("_", "").isalnum(), "invalid command label")
            self.check(); self.admission(label + ":before", 3, 1)
            B.require(not any(B._CREDENTIAL.search(str(arg)) for arg in command), "credential-bearing command refused")
            self.event("child_start", label=label, command=command, cwd=str(cwd))
            boot = legacy.boot_id()
            trace_read = trace_write = None
            trace_state = B.TraceAccumulator() if trace else None
            actual = list(command)
            if trace:
                trace_read, trace_write = os.pipe()
                actual = [shutil.which("strace"), "-f", "-ttt", "-xx", "-s", "131072", "-e", "trace=execve,execveat",
                    "-o", f"/proc/self/fd/{trace_write}", "--", *command]
                B.require(actual[0], "passive strace unavailable")
            child = owner = failed = cleanup_error = None
            captured, line_buffers = bytearray(), {}
            selector = selectors.DefaultSelector()
            output = (self.root / "logs" / (label + ".log")).open("xb")
            self.cleanup_complete = False
            try:
                child = subprocess.Popen(actual, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    start_new_session=True, pass_fds=() if trace_write is None else (trace_write,))
                self.children.append(child)
                if trace_write is not None:
                    os.close(trace_write); trace_write = None
                owner = legacy.process_stat(child.pid)
                B.require(owner and owner["session"] == child.pid and owner["pgrp"] == child.pid,
                          "private session ownership unavailable")
                fds = [(child.stdout.fileno(), "log")]
                if trace_read is not None:
                    fds.append((trace_read, "trace"))
                for fd, kind in fds:
                    os.set_blocking(fd, False); selector.register(fd, selectors.EVENT_READ, kind); line_buffers[kind] = bytearray()
                last_resource = 0.0
                while True:
                    exited = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    self.check()
                    B.require(not [pid for pid in direct_children() if pid != child.pid], "unexpected adopted child")
                    if time.monotonic() - last_resource >= 1:
                        self.admission(label + ":running", 3, 1); last_resource = time.monotonic()
                    for key, _ in selector.select(.1):
                        block = os.read(key.fd, 65536)
                        kind = key.data
                        if not block:
                            selector.unregister(key.fd)
                        line_buffers[kind].extend(block)
                        B.require(len(line_buffers[kind]) <= B.MAX_TRACE_LINE + 65536, "child line byte cap")
                        while b"\n" in line_buffers[kind] or (not block and line_buffers[kind]):
                            end = line_buffers[kind].find(b"\n") + 1 if b"\n" in line_buffers[kind] else len(line_buffers[kind])
                            line = bytes(line_buffers[kind][:end]); del line_buffers[kind][:end]
                            if kind == "trace":
                                trace_state.feed(line)
                            else:
                                B.require(not B._CREDENTIAL.search(line.decode("utf-8", "replace")), "potential credential-bearing log refused")
                                B.require(len(captured) + len(line) <= MAX_LOG_BYTES, "child log byte cap")
                                captured.extend(line); output.write(line)
                    if exited:
                        B.require(not legacy.session_live(child.pid), "child exited with live session descendants")
                        if not selector.get_map():
                            break
            except BaseException as exc:
                failed = exc
            finally:
                if trace_write is not None:
                    os.close(trace_write)
                try:
                    if child is not None:
                        # Preserve the unreaped leader until ownership-sensitive
                        # same-session signalling is complete, as in 27f.
                        for sig, seconds in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
                            end = time.monotonic() + seconds
                            while legacy.session_live(child.pid) and time.monotonic() < end:
                                self.signal_session(child, owner, boot, sig); time.sleep(.05)
                            if not legacy.session_live(child.pid):
                                break
                        B.require(not legacy.session_live(child.pid), "owned session cleanup incomplete")
                        orphaned = lease.reap_orphans(exclude=(child.pid,))
                        child.wait(timeout=2); self.children.remove(child)
                        B.require(not orphaned, "escaped adopted descendants invalidate build")
                    self.cleanup_complete = True
                except BaseException as exc:
                    cleanup_error = type(exc).__name__
                selector.close(); output.close()
                if child is not None and child.stdout is not None:
                    child.stdout.close()
                if trace_read is not None:
                    os.close(trace_read)
                self.event("child_cleanup", label=label, complete=self.cleanup_complete, cleanup_error=cleanup_error)
            B.require(self.cleanup_complete, "owned-child cleanup unverified")
            if failed is not None:
                raise failed
            self.check()
            self.event("child_exit", label=label, returncode=child.returncode)
            B.require(child.returncode in allowed_exit_codes, "child exited unsuccessfully: " + label)
            self.last_stdout = bytes(captured)
            self.last_trace = None if trace_state is None else trace_state.finish()
            return self.last_stdout

    return Supervisor()
