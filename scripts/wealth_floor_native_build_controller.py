#!/usr/bin/env python3
"""Dormant paired-native builder. No workflow activates this controller yet.

Reuse the exact 27f private-session supervisor/ownership helpers, adding bounded
pipe/trace intake. CPU values describe self and waited children; they are not an
aggregate live-tree CPU budget. An exact old native rebuild is mandatory for
historical baseline reuse. No function here creates an ordinary physics world.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.machinery
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import types

SCRIPT = Path(__file__).resolve()
# Isolated native probes may import only these reviewed control helpers and the
# wheel's own package, never either producer's chronicler Python package.
sys.path.insert(0, str(SCRIPT.parent))
import wealth_floor_native_build_bridge as B
from wealth_floor_build_resources import memory_admission
from wealth_floor_hosted_deployment import hosted_vm_precondition

LEGACY_SOURCE = "27f0f3d11a1a171e1539353eb2c3a0fb896f0939"
LEGACY_FILE = "scripts/default_output_identity_qualification.py"
LEGACY_SHA = "e4ca3f0c3732e4b5536a88a6284ab44b173e2165fafb59586be02fbd1d015932"
MAX_LOG_BYTES = 8 * B.MIB
MAX_PROGRESS_BYTES = 8 * B.MIB
MAX_RAW_BYTES = 256 * B.MIB
MAX_RAW_FILES = 512
MAX_SMALL_BYTES = 2 * B.MIB
MAX_LIGHT_BYTES = 8 * B.MIB
MAX_LIGHT_FILES = 32
CAPS = {key: "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS", "RAYON_NUM_THREADS", "CARGO_BUILD_JOBS")}
CAPS.update(PYTHONHASHSEED="0", PYTHON_CPU_COUNT="2", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
    OPENBLAS_THREAD_TIMEOUT="16", CARGO_INCREMENTAL="0")
LIGHT_NAMES = ("build-manifest.json", "source-control-before.json", "source-control-after.json",
    "baseline/source-before.json", "baseline/source-after.json", "baseline/context.json", "baseline/probe.json",
    "baseline/trace-summary.json", "candidate/source-before.json", "candidate/source-after.json",
    "candidate/context.json", "candidate/probe.json", "candidate/trace-summary.json", "cache-retirement.json")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(B.MIB), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    raw = B.canonical_bytes(value)
    B.require(len(raw) <= MAX_SMALL_BYTES, "controller JSON byte cap")
    temporary = path.with_name("pending-" + path.name)
    with temporary.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def bounded_json(path):
    B.require(Path(path).is_file() and not Path(path).is_symlink() and Path(path).stat().st_size <= MAX_SMALL_BYTES,
              "controller JSON missing/oversize")
    raw = Path(path).read_bytes()
    B.require(len(raw) <= MAX_SMALL_BYTES, "controller JSON grew")
    return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(B.BridgeRefused("nonfinite JSON")))


def legacy_helpers(root):
    path = Path(root) / LEGACY_FILE
    B.require(path.is_file() and not path.is_symlink() and path.stat().st_size == 33607, "legacy supervisor file differs")
    raw = path.read_bytes()
    B.require(hashlib.sha256(raw).hexdigest() == LEGACY_SHA, "legacy supervisor source hash differs")
    module = types.ModuleType("wealth_bridge_27f_supervisor")
    module.__file__ = str(path)
    # Execute the bytes just hashed, rather than reopening a replaceable path.
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def source_snapshot(legacy, root, expected, deadline):
    # These are local metadata operations, with no remote authentication. Do not
    # let an inherited Git directory/index/config override select another tree.
    overrides = {key: value for key, value in os.environ.items() if key.startswith("GIT_")}
    try:
        for key in overrides:
            os.environ.pop(key)
        B.require(time.monotonic() < deadline, "source snapshot wall deadline")
        result = legacy.source_snapshot(root, expected, deadline)
        B.require(time.monotonic() < deadline, "source snapshot wall deadline")
        return result
    finally:
        os.environ.update(overrides)


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


def build_environment(task_root, python):
    # Preserve runtime authentication/proxy/CA/guard inputs without forwarding
    # arbitrary compiler customizations. No selected value is printed here.
    exact = {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "LC_CTYPE",
        "TERM", "CI", "ImageOS", "ImageVersion", "RUSTUP_HOME", "RUSTUP_TOOLCHAIN", "CARGO_HOME", "CARGO_TERM_COLOR",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS"}
    prefixes = ("GITHUB_", "RUNNER_", "CODEX_", "OIC_", "UV_")
    env = {key: value for key, value in os.environ.items() if key in exact or key.startswith(prefixes)}
    env.update(CAPS, CARGO_TARGET_DIR=str(task_root / "full-gates-cargo"), PYO3_PYTHON=python)
    for key in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS"):
        env[key] = ""
    env.pop("PYTHONPATH", None)
    return env


def cargo_config_visibility(source, cwd, env):
    directories = {source, *source.parents, cwd, *cwd.parents}
    home = Path(env.get("CARGO_HOME", str(Path(env["HOME"]) / ".cargo")))
    B.absolute_path(str(home))
    candidates = {home / name for name in ("config", "config.toml")}
    candidates.update(directory / ".cargo" / name for directory in directories for name in ("config", "config.toml"))
    B.require(len(candidates) <= 128, "Cargo configuration path bound")
    # Configuration files can contain registry credentials. Absence is enough
    # for this closed build; never read/print a discovered configuration file.
    B.require(not any(path.exists() or path.is_symlink() for path in candidates), "Cargo configuration present; effective context unknown")
    return dict(checked_absent_paths=sorted(str(path.absolute()) for path in candidates),
        scope="Cargo home and command/manifest ancestors; config files absent")


def executable_facts(supervisor, records, env, cwd, phase):
    paths = sorted({record["executable"] for record in records})
    B.require(0 < len(paths) <= 64, "observed tool set cap")
    rows = []
    for index, name in enumerate(paths):
        path = Path(name)
        B.require(path.is_file(), "observed executable vanished")
        before = sha(path)
        raw = supervisor.command(f"{phase}-tool-{index}", [name, "--version"], env, cwd, allowed_exit_codes=(0, 1))
        B.require(sha(path) == before and raw.strip(), "observed tool identity/version changed")
        rows.append(dict(path=name, sha256=before, version=raw.decode("utf-8", "strict").strip()))
    return rows


def common_context(supervisor, source, env, wheel_stage, trace, phase):
    tools = executable_facts(supervisor, trace["records"], env, source, phase)
    native_linkers = [row for row in trace["records"] if Path(row["executable"]).name in B.LINKER_NAMES
        and any("libchronicler_agents.so" in arg for arg in row["argv"])]
    B.require(native_linkers, "actual compiled-module linker not observed")
    linker = next(row for row in tools if row["path"] == native_linkers[-1]["executable"])
    def version(label, command):
        return supervisor.command(phase + "-" + label, command, env, source).decode().strip()
    manifest = str(source / "chronicler-agents/Cargo.toml")
    result = dict(unknown=trace["unknown"], rustc=version("rustc", ["rustc", "--version", "--verbose"]),
        cargo=version("cargo", ["cargo", "--version"]), maturin=version("maturin", [env["PYO3_PYTHON"], "-m", "maturin", "--version"]),
        uv=version("uv", ["uv", "--version"]), python=platform.python_version(), target=B.TARGET,
        flags={key: env.get(key) for key in sorted(B.REQUIRED_FLAGS | B.OPTIONAL_FLAGS)},
        linker=dict(path=linker["path"], version=linker["version"], executable_sha256=linker["sha256"]), executables=tools,
        host=dict(system=platform.system(), machine=platform.machine(), platform=platform.platform(),
            image_os=env.get("ImageOS"), image_version=env.get("ImageVersion")),
        release_profile={"codegen-units": 1, "lto": True, "opt-level": 3}, features=["pyo3/extension-module"],
        lock_sha256=sha(source / "uv.lock"), pyproject_sha256=sha(source / "pyproject.toml"),
        manifest_path=manifest, target_path=env["CARGO_TARGET_DIR"], staging_wheel_path=str(wheel_stage),
        build_argv=["-m", "maturin", "build", "--release", "--locked", "--manifest-path", manifest, "--out", str(wheel_stage)],
        cargo_config=cargo_config_visibility(source, supervisor.root, env))
    B.validate_context(result)
    return result


def probe(args):
    B.require(platform.python_version() == B.PYTHON_VERSION and Path(sys.prefix).resolve() == Path(args.environment_root).resolve(),
              "native API probe runtime differs")
    import chronicler_agents as package
    import chronicler_agents.chronicler_agents as native
    origin = Path(native.__file__).resolve()
    B.require(isinstance(native.__loader__, importlib.machinery.ExtensionFileLoader)
        and str(origin).endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)) and origin.is_relative_to(Path(sys.prefix).resolve()),
        "native API probe did not load isolated compiled module")
    schemas = {}
    for name in B.CLASS_NAMES:
        cls = getattr(package, name)
        B.require(isinstance(cls, type) and cls is getattr(native, name), "real native class exports differ")
        version, fingerprint, schema = cls.checkpoint_schema()
        B.require(type(schema) is str and len(schema.encode()) <= 4 * B.MIB, "native schema byte bound")
        schemas[name] = dict(version=version, fingerprint=fingerprint, schema_sha256=hashlib.sha256(schema.encode()).hexdigest())
    B.schemas_equal_registered(schemas)
    source_imports = sorted(name for name in sys.modules if name == "chronicler" or name.startswith("chronicler."))
    B.require(not source_imports, "native API probe imported producer source")
    write_json(args.out, dict(compiled_extension=True, real_exported_classes=True, native_sha256=sha(origin), native_path=str(origin),
        environment_root=str(Path(sys.prefix).resolve()), python=platform.python_version(), schemas=schemas,
        source_imports=source_imports, native_pools_created=0, scope="class/schema API calls only; no simulator instances or physics worlds"))


def inventory(root, *, exclude=()):
    files, total = {}, 0
    excluded = set(exclude)
    for directory, dirs, names in os.walk(root, followlinks=False):
        B.require(all(not (Path(directory) / name).is_symlink() for name in dirs), "evidence directory link")
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if relative in excluded or any(name.endswith("/") and relative.startswith(name) for name in excluded):
                continue
            B.require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), "evidence file type differs")
            total += path.stat().st_size
            B.require(len(files) < MAX_RAW_FILES and total <= MAX_RAW_BYTES, "evidence file/byte cap")
            files[relative] = dict(bytes=path.stat().st_size, sha256=sha(path))
    return dict(files=files, file_count=len(files), total_bytes=total)


def stage_light(root):
    rows = {}
    for name in LIGHT_NAMES:
        path = root / name
        if path.exists():
            B.require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL_BYTES, "light input unsafe/oversize")
            rows[name] = dict(bytes=path.stat().st_size, sha256=sha(path))
    B.require(sum(row["bytes"] for row in rows.values()) <= MAX_LIGHT_BYTES - 2 * B.MIB and len(rows) + 2 <= MAX_LIGHT_FILES,
              "light pre-copy bound exceeded")
    light = root / "light"; light.mkdir(exist_ok=False)
    for name, row in rows.items():
        out = light / name; out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, out)
        B.require(sha(root / name) == row["sha256"] == sha(out), "light bytes changed")
    index = dict(schema_version=1, kind="wealth-floor-native-build-light", limits=dict(bytes=MAX_LIGHT_BYTES, files=MAX_LIGHT_FILES),
        payload_file_count=len(rows), indexed_payload_bytes=sum(row["bytes"] for row in rows.values()),
        index_included_in_limits=True, completion_included_in_limits=True, completion_uploaded_beside_directory=True,
        files=rows, qualification="Copy/provenance only; no candidate-world grant.")
    raw = B.canonical_bytes(index)
    B.require(len(raw) <= B.MIB and index["indexed_payload_bytes"] + len(raw) <= MAX_LIGHT_BYTES, "light index bound exceeded")
    write_json(light / "index.json", index)


def invalidate_publication(root, report):
    """Preserve superseded bytes under incomplete names; clear positive paths."""
    for directory in (root, root / "light"):
        if not directory.is_dir():
            continue
        for name in ("completion.json", "build-manifest.json"):
            path = directory / name
            if path.exists():
                number = 0
                target = directory / ("incomplete-" + name)
                while target.exists():
                    number += 1
                    B.require(number <= 8, "publication invalidation slots exhausted")
                    target = directory / (f"incomplete-{number}-" + name)
                os.replace(path, target)
    report["status"] = "incomplete"; report["historical_reuse_eligible"] = False
    report["publication_status"] = "incomplete"
    for directory in (root, root / "light"):
        if directory.is_dir():
            try:
                write_json(directory / "build-manifest.json", report)
            except BaseException:
                pass
    try:
        write_json(root / "completion.json", dict(publication_complete=False, error="incomplete_build_publication"))
    except BaseException:
        pass


def publish_complete(root, report, check, clocks):
    """Hash heavy payloads before the completion observation/commit.

    Completion is uploaded beside the bounded light directory, so no circular
    index/completion hash is needed. Consumers require it, the matching manifest
    and original inventory, plus completed successful job/publication metadata.
    """
    try:
        write_json(root / "raw-inventory.json", inventory(root,
            exclude=("raw-inventory.json", "build-manifest.json", "completion.json", "light/")))
        check()
        report["publication_status"] = "provisional_until_matching_completion_seal"
        report["measured_before_publication"] = clocks()
        write_json(root / "build-manifest.json", report)
        stage_light(root)
        check()
        sealed = {name: dict(bytes=(root / name).stat().st_size, sha256=sha(root / name)) for name in
            ("build-manifest.json", "raw-inventory.json", "light/index.json")}
        check()
        completion = dict(schema_version=1, kind="wealth-floor-native-build-completion", publication_complete=True,
            files=sealed, budget_observation=clocks(),
            clock_stage="After heavy inventory, manifest and light hashing; before this completion commit. Post-commit deadline check required.",
            qualification="Requires completed successful producer job and exact published artifact; no candidate-world grant.")
        B.require(len(B.canonical_bytes(completion)) <= B.MIB, "bounded light completion byte cap")
        write_json(root / "completion.json", completion)
        check()
        B.require(not direct_children(), "late adopted descendants invalidate completion")
        return completion
    except BaseException:
        invalidate_publication(root, report)
        raise


def build(args):
    start = time.monotonic(); deadline = start + B.Policy().wall_seconds
    B.require(sys.platform == "linux" and platform.python_version() == B.PYTHON_VERSION, "registered Linux/Python runtime required")
    B.require(Path(args.python).is_absolute() and Path(args.python).resolve() == Path(sys.executable).resolve(),
              "build interpreter must be the registered controller interpreter")
    task_root = Path(os.environ["RUNNER_TEMP"]).resolve()
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    source, root, control = Path(args.producer_root).resolve(), Path(args.evidence).resolve(), SCRIPT.parents[1]
    B.require(source == workspace / "candidate" and root == task_root / "wealth-native-bridge" and control == workspace / "control",
              "registered source/control/evidence paths differ")
    B.require(not root.exists() and not (task_root / "full-gates-env").exists()
        and not (task_root / "full-gates-cargo").exists() and not (task_root / "full-gates-build").exists(), "fresh external paths required")
    root.mkdir(); (root / "logs").mkdir(); (root / "wheels").mkdir()
    legacy = legacy_helpers(args.legacy_root)
    usage_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    report = dict(schema_version=1, kind="wealth-floor-native-build-bridge", status="incomplete", historical_reuse_eligible=False,
        candidate_worlds_admitted=False, phases={}, legacy_supervisor_source=LEGACY_SOURCE, legacy_supervisor_sha256=LEGACY_SHA,
        producer=dict(control_sha=os.environ["GITHUB_SHA"], run_id=os.environ["GITHUB_RUN_ID"],
            run_attempt=os.environ["GITHUB_RUN_ATTEMPT"], job_key=os.environ["GITHUB_JOB"]))
    cancellation = Cancellation()
    cancellation.__enter__()
    supervisor = None
    failed = None
    try:
        report["deployment"] = hosted_vm_precondition()
        with SubreaperLease() as lease:
            supervisor = make_supervisor(legacy, root, deadline, lease, cancellation)
            supervisor.admission("before_build", 12, 2)
            B.require(shutil.which("strace"), "passive strace is required before any build")
            available = sorted(os.sched_getaffinity(0)); B.require(len(available) >= 2, "two actual CPUs required")
            os.sched_setaffinity(0, set(available[:2]))
            control_before = source_snapshot(legacy, control, os.environ["GITHUB_SHA"], supervisor.deadline)
            write_json(root / "source-control-before.json", control_before)
            system_env = build_environment(task_root, args.python)
            supervisor.command("initial-source", ["git", "-C", str(source), "rev-parse", "HEAD"], system_env, control)
            B.require(supervisor.last_stdout.decode().strip() == B.CANDIDATE_SOURCE, "initial exact candidate checkout required")
            supervisor.command("initial-source-standing", ["git", "-C", str(source), "status", "--porcelain=v1", "--untracked-files=all"], system_env, control)
            B.require(not supervisor.last_stdout, "initial source checkout is not clean")
            for role, (source_sha, _crate) in B.SOURCES.items():
                supervisor.command(role + "-object-available", ["git", "-C", str(source), "cat-file", "-e", source_sha + "^{commit}"], system_env, control)
            supervisor.command("baseline-checkout", ["git", "-C", str(source), "checkout", "--detach", B.BASELINE_SOURCE], system_env, control)
            build_py = str(task_root / "full-gates-env/bin/python")
            system_env["UV_PROJECT_ENVIRONMENT"] = str(task_root / "full-gates-env")
            supervisor.command("locked-environment", ["uv", "sync", "--project", str(source), "--frozen", "--no-install-project", "--python", args.python], system_env, control)
            supervisor.command("pinned-maturin", ["uv", "pip", "install", "--python", build_py, "maturin==1.15.0"], system_env, control)
            env = build_environment(task_root, build_py)
            cargo_config_visibility(source, root, env)
            versions = {}
            for label, command in (("rustc", ["rustc", "--version", "--verbose"]), ("cargo", ["cargo", "--version"]),
                ("uv", ["uv", "--version"]), ("maturin", [build_py, "-m", "maturin", "--version"])):
                versions[label] = supervisor.command("prebuild-" + label, command, env, root).decode().strip()
            B.require(B.RUSTC_COMMIT in versions["rustc"] and "LLVM version: 23.1.1" in versions["rustc"]
                and versions["rustc"].startswith("rustc 1.99.1 ")
                and versions["cargo"] == "cargo 1.99.1 (5f94df478 2026-08-27)"
                and versions["uv"] == "uv 0.13.6 (x86_64-unknown-linux-gnu)" and versions["maturin"] == "maturin 1.15.0",
                "pinned toolchain preflight refused before compilation")
            wheel_stage = task_root / "full-gates-build/wheels"; wheel_stage.mkdir(parents=True)
            for role, (source_sha, crate) in B.SOURCES.items():
                phase_root = root / role; phase_root.mkdir()
                supervisor.check(); supervisor.admission(role + ":build", 12, 2)
                if role == "candidate":
                    supervisor.command("candidate-checkout", ["git", "-C", str(source), "checkout", "--detach", source_sha], env, control)
                before = source_snapshot(legacy, source, source_sha, supervisor.deadline)
                B.require(before["crate_tree"] == crate and sha(source / "uv.lock") == B.LOCK_SHA256
                    and sha(source / "pyproject.toml") == B.PYPROJECT_SHA256, "source/crate/lock inputs differ")
                write_json(phase_root / "source-before.json", before)
                command = [build_py, "-m", "maturin", "build", "--release", "--locked", "--manifest-path",
                    str(source / "chronicler-agents/Cargo.toml"), "--out", str(wheel_stage)]
                supervisor.command(role + "-release-build", command, env, root, trace=True)
                trace = supervisor.last_trace
                write_json(phase_root / "trace-summary.json", {key: value for key, value in trace.items() if key != "records"})
                with (phase_root / "compiler-linker.jsonl").open("xb") as stream:
                    for row in trace["records"]:
                        stream.write(B.canonical_bytes(row))
                wheels = list(wheel_stage.iterdir()); B.require(len(wheels) == 1 and wheels[0].name == B.WHEEL_NAME, "one registered wheel required")
                wheel = wheels[0]
                B.require(wheel.stat().st_size <= B.MAX_WHEEL_BYTES, "wheel byte bound")
                wheel_facts = B.inspect_wheel(wheel.read_bytes(), wheel.name)
                retained = root / "wheels" / role; retained.mkdir(); retained_wheel = retained / wheel.name
                os.replace(wheel, retained_wheel)
                context = common_context(supervisor, source, env, wheel_stage, trace, role)
                write_json(phase_root / "context.json", context)
                probe_env = dict(env, UV_PROJECT_ENVIRONMENT=str(task_root / ("wealth-native-" + role + "-env")))
                probe_py = str(Path(probe_env["UV_PROJECT_ENVIRONMENT"]) / "bin/python")
                B.require(not Path(probe_env["UV_PROJECT_ENVIRONMENT"]).exists(), "fresh isolated probe environment required")
                supervisor.command(role + "-probe-environment", ["uv", "sync", "--project", str(source), "--frozen", "--no-dev", "--no-install-project", "--python", args.python], probe_env, control)
                supervisor.command(role + "-install-wheel", ["uv", "pip", "install", "--no-deps", "--python", probe_py, str(retained_wheel)], probe_env, control)
                supervisor.command(role + "-native-api-probe", [probe_py, "-I", "-B", str(SCRIPT), "probe", "--environment-root",
                    probe_env["UV_PROJECT_ENVIRONMENT"], "--out", str(phase_root / "probe.json")], probe_env, control)
                regressions = None
                if role == "candidate":
                    supervisor.command("candidate-regressions", ["cargo", "test", "--locked", "--lib", "--manifest-path",
                        str(source / "chronicler-agents/Cargo.toml"), "household_migration_"], env, source)
                    text = supervisor.last_stdout.decode()
                    B.require("test result: ok. 4 passed; 0 failed;" in text
                        and all("test " + name + " ... ok" in text for name in B.REGRESSIONS), "four targeted native regressions did not pass")
                    regressions = {name: "PASS" for name in B.REGRESSIONS}
                after = source_snapshot(legacy, source, source_sha, supervisor.deadline)
                write_json(phase_root / "source-after.json", after)
                B.require(before == after and sha(retained_wheel) == wheel_facts["sha256"], "phase source/wheel changed")
                phase = dict(source_sha=source_sha, crate_tree=crate, source_clean=True, build_complete=True,
                    cleanup_complete=supervisor.cleanup_complete, source_before_sha256=sha(phase_root / "source-before.json"),
                    source_after_sha256=sha(phase_root / "source-after.json"), wheel=wheel_facts,
                    probe=bounded_json(phase_root / "probe.json"), context=context, regressions=regressions)
                B.validate_phase(phase, role); report["phases"][role] = phase
                if role == "baseline":
                    # The target contains only reproducible compiler outputs. The
                    # wheel, logs and source receipts already live outside it.
                    supervisor.command("retire-baseline-cargo-cache", ["cargo", "clean", "--manifest-path",
                        str(source / "chronicler-agents/Cargo.toml"), "--target-dir", env["CARGO_TARGET_DIR"]], env, source)
                    B.require(not Path(env["CARGO_TARGET_DIR"]).exists(), "baseline Cargo cache retirement incomplete")
                    write_json(root / "cache-retirement.json", dict(kind="derived-cargo-cache-retirement", path=env["CARGO_TARGET_DIR"],
                        source_sha=source_sha, retained_wheel_sha256=sha(retained_wheel), raw_evidence_removed=False))
            control_after = source_snapshot(legacy, control, os.environ["GITHUB_SHA"], supervisor.deadline)
            B.require(control_before == control_after, "control source changed")
            write_json(root / "source-control-after.json", control_after)
            supervisor.check(final=True)
        # The subreaper lease has closed before a positive-looking manifest.
        B.require(not direct_children() and supervisor.cleanup_complete, "final owned-child cleanup incomplete")
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        def clocks():
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            return dict(final_observation=True, cleanup_complete=True, live_processes=0,
                controller_measured_cpu_seconds=time.process_time(),
                waited_children_cpu_seconds=(usage.ru_utime + usage.ru_stime) - (usage_start.ru_utime + usage_start.ru_stime),
                cpu_scope="Measured controller self and waited-child usage; no exact aggregate live-tree CPU or CPU admission claim",
                wall_seconds=time.monotonic() - start, wall_limit_seconds=B.Policy().wall_seconds)
        supervisor.check(final=True)
        result = B.classify_pair(report["phases"]["baseline"], report["phases"]["candidate"], clocks())
        result["phases"] = report["phases"]; result["producer"] = report["producer"]
        result["deployment"] = report["deployment"]
        result["legacy_supervisor_source"] = LEGACY_SOURCE; result["legacy_supervisor_sha256"] = LEGACY_SHA
        report = result
        publish_complete(root, report, lambda: supervisor.check(final=True), clocks)
    except BaseException as exc:
        failed = exc
        report["status"] = "incomplete"; report["historical_reuse_eligible"] = False
        report["error"] = type(exc).__name__
        try: invalidate_publication(root, report)
        except BaseException: pass
    finally:
        if time.monotonic() > deadline or direct_children() or cancellation.cancelled:
            failed = failed or B.BridgeRefused("late teardown/deadline failure")
            report["status"] = "incomplete"; report["historical_reuse_eligible"] = False
            try: invalidate_publication(root, report)
            except BaseException: pass
        try:
            cancellation.__exit__(type(failed) if failed else None, failed, None)
        except BaseException as exc:
            failed = failed or exc
            try: invalidate_publication(root, report)
            except BaseException: pass
    if failed is not None:
        print("Native build bridge incomplete: " + type(failed).__name__, file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    run = modes.add_parser("build")
    run.add_argument("--producer-root", required=True); run.add_argument("--legacy-root", required=True)
    run.add_argument("--python", required=True); run.add_argument("--evidence", required=True)
    api = modes.add_parser("probe")
    api.add_argument("--environment-root", required=True); api.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    return build(args) if args.mode == "build" else probe(args)


if __name__ == "__main__":
    raise SystemExit(main())
