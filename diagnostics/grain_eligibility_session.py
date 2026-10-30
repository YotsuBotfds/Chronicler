"""Parent-owned trusted Linux child custody, bounded pipes and durable records.

Adapted as source from reviewed CB17d held-WNOWAIT decisions. No CB or product
module is imported. This is not containment against malicious escaped children.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import stat
import subprocess
import time

class SessionRefused(ValueError):
    pass

def require(value, label):
    if not value:
        raise SessionRefused(label)

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()

def durable_bytes(path, data, cap, *, sync=os.fsync, open_dir=os.open):
    """Exclusive first write; file flush/fsync then directory fsync before return."""
    path = Path(path)
    require(type(data) is bytes and len(data) <= cap, "bounded durable body")
    with path.open("xb") as stream:
        require(stream.write(data) == len(data), "complete durable body write")
        stream.flush()
        sync(stream.fileno())
    descriptor = open_dir(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        sync(descriptor)
    finally:
        os.close(descriptor)

def durable_directory(path, *, sync=os.fsync):
    path = Path(path)
    path.mkdir(mode=0o700)
    for name in (path, path.parent):
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            sync(fd)
        finally:
            os.close(fd)

def terminal_reserved(pid):
    return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None

def group_members(group, leader):
    """Trusted /proc metadata only, while an unreaped owned leader reserves its ID."""
    members, other_groups = [], []
    entries = list(Path("/proc").iterdir())
    require(len(entries) <= 8192, "bounded proc catalogue")
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) == leader:
            continue
        try:
            with (entry / "stat").open("rb") as stream:
                raw = stream.read(4097)
            require(len(raw) <= 4096, "bounded proc stat")
            fields = raw[raw.rfind(b")") + 2:].split()
            require(len(fields) >= 4, "complete proc identity")
            pgrp, session = int(fields[2]), int(fields[3])
            if pgrp == group:
                members.append(int(entry.name))
            elif session == leader:
                other_groups.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return {"group": sorted(members), "other_session_groups": sorted(other_groups)}

def settle_reserved_group(pid, *, terminal=terminal_reserved, members=group_members,
                          kill=os.killpg, now=time.monotonic, pause=time.sleep):
    deadline = now() + 5
    result = {"proven": False, "leader_terminal": False, "kill_requested": False,
              "remaining_members": None, "other_session_groups": None,
              "scope": "Trusted owned Linux session/group, not a sandbox"}
    while True:
        reservation_known = False
        try:
            result["leader_terminal"] = terminal(pid)
            reservation_known = True
            observed = members(pid, pid)
            result["remaining_members"] = observed["group"]
            result["other_session_groups"] = observed["other_session_groups"]
            if result["leader_terminal"] and observed == {"group": [], "other_session_groups": []}:
                result["proven"] = True
                return result
            if not result["kill_requested"]:
                try:
                    kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                result["kill_requested"] = True
            if now() >= deadline:
                return result
            pause(min(0.02, max(0, deadline - now())))
        except BaseException as error:
            result["error_type"] = type(error).__name__
            if reservation_known and not isinstance(error, ChildProcessError) and not result["kill_requested"]:
                try:
                    kill(pid, signal.SIGKILL)
                    result["kill_requested"] = True
                except (ProcessLookupError, OSError):
                    pass
            return result

def remember_failure(endpoint, label, stage, error=None):
    failure = {"label": label, "stage": stage}
    if error is not None:
        failure["type"] = type(error).__name__
    if endpoint.get("refusal") is None:
        endpoint["refusal"] = label
        endpoint["first_failure"] = failure
    elif len(endpoint.setdefault("secondary_failures", [])) < 16:
        endpoint["secondary_failures"].append(failure)

def finish_child(process, endpoint, *, settle=settle_reserved_group):
    """All probes/signals happen with the leader held; the sole wait is last."""
    try:
        custody = settle(process.pid)
    except BaseException as error:
        custody = {"proven": False, "leader_terminal": False, "kill_requested": False,
                   "error_type": type(error).__name__}
        remember_failure(endpoint, "CUSTODY_OBSERVER_ERROR", "cleanup", error)
    endpoint["custody"] = custody
    endpoint["group_quiescent"] = custody["proven"] is True
    endpoint["cleanup_kill_sent"] = custody["kill_requested"] is True
    if custody["leader_terminal"] is True:
        try:
            endpoint["exit_code"] = process.wait()
            endpoint["waited"] = True
        except BaseException as error:
            endpoint["group_quiescent"] = False
            remember_failure(endpoint, "LEADER_REAP_UNKNOWN", "reap", error)
    if not endpoint["group_quiescent"] or not endpoint["waited"]:
        remember_failure(endpoint, "GROUP_CUSTODY_UNKNOWN", "cleanup")
    elif endpoint["cleanup_kill_sent"]:
        remember_failure(endpoint, "OWNED_SESSION_REQUIRED_CLEANUP", "cleanup")

def capture_allowed(endpoint):
    return (endpoint.get("group_quiescent") is True and endpoint.get("waited") is True
            and type(endpoint.get("exit_code")) is int
            and endpoint.get("custody", {}).get("proven") is True)

def clean_command(endpoint):
    return (capture_allowed(endpoint) and endpoint["exit_code"] == 0
            and endpoint.get("refusal") is None and endpoint.get("streams_complete") is True
            and endpoint.get("endpoint_durable") is True)

def monitored_census(pid, watch, *, terminal=terminal_reserved):
    """Narrow live metadata exception: reservation proof precedes every census."""
    terminal(pid)  # Success proves the owned child is still unreaped, terminal or live.
    return watch()

def collect_snapshot(endpoint, requests, *, reader):
    """Even lookup of a child member is forbidden without positive waited closure."""
    if not capture_allowed(endpoint):
        return {}, [{"stage": "capture", "label": "GROUP_CUSTODY_UNKNOWN"}]
    bodies, errors = {}, []
    for name, path, cap in requests:
        try:
            body = reader(path, cap)
            require(type(body) is bytes and len(body) <= cap, "snapshot body cap")
            bodies[name] = body
        except BaseException as error:
            errors.append({"member": name, "type": type(error).__name__})
    return bodies, errors

def publish_snapshot(destination, endpoint, bodies, expected, *, writer=durable_bytes,
                     mkdir=durable_directory):
    if not capture_allowed(endpoint) or set(bodies) != set(expected):
        return False
    require(sum(map(len, bodies.values())) <= 256 * 1024, "compact expanded snapshot cap")
    require(sum(len(b) for n, b in bodies.items() if n.endswith(".json")) <= 64 * 1024,
            "identity/status metadata combined cap")
    destination = Path(destination)
    mkdir(destination)
    for name, body in bodies.items():
        require("/" not in name and "\\" not in name and name not in ("", ".", ".."), "flat snapshot names")
        writer(destination / name, body, len(body))
    return True

def run_owned(command, env, caps, wall, *, cwd, control, stage, identity=None,
              watch=None, cpu_limit=None, as_limit=None, launch=subprocess.Popen,
              terminal=terminal_reserved, settle=settle_reserved_group,
              now=time.monotonic, writer=durable_bytes):
    """One first attempt, held leader, bounded parent pipes, finally group closure."""
    control = Path(control)
    durable_directory(control)
    start = now()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    endpoint = {"stage": stage, "exit_code": None, "waited": False,
                "group_quiescent": False, "cleanup_kill_sent": False, "refusal": None,
                "child_pid": None, "endpoint_durable": False, "streams_complete": False,
                "current_identity": identity, "scope": "Trusted Linux session; no sandbox claim"}
    intent = {"state": "ATTEMPTED", "stage": stage, "argv": command, "cwd": str(cwd),
              "caps": list(caps), "wall_seconds": wall, "CPU_seconds": cpu_limit,
              "AS_bytes": as_limit, "current_identity": identity, "automatic_retry": False}
    # A durable intent and directory entry must exist before Popen is even called.
    writer(control / "launch-intent.json", canonical(intent), 8192)
    process, selected = None, selectors.DefaultSelector()
    buffers = [bytearray(), bytearray()]
    seen, eof = [0, 0], [False, False]
    hashes = [hashlib.sha256(), hashlib.sha256()]
    def limits():
        if cpu_limit is not None:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
        if as_limit is not None:
            resource.setrlimit(resource.RLIMIT_AS, (as_limit, as_limit))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024**2, 32 * 1024**2))
    def consume(index, chunk):
        seen[index] += len(chunk)
        hashes[index].update(chunk)
        available = max(0, caps[index] + 1 - len(buffers[index]))
        buffers[index].extend(chunk[:available])
        if seen[index] > caps[index]:
            remember_failure(endpoint, "STDOUT_CAP" if index == 0 else "STDERR_CAP", "pipe")
    def drain_ready(key):
        try:
            chunk = os.read(key.fileobj.fileno(), 65536)
        except BlockingIOError:
            return
        if chunk:
            consume(key.data, chunk)
        else:
            eof[key.data] = True
            selected.unregister(key.fileobj)
            key.fileobj.close()
    try:
        process = launch(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         start_new_session=True, preexec_fn=limits)
        endpoint["child_pid"] = process.pid
        writer(control / "launch-started.json", canonical({"child_pid": process.pid, "stage": stage}), 4096)
        for index, stream in enumerate((process.stdout, process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selected.register(stream, selectors.EVENT_READ, index)
        while True:
            if terminal(process.pid):
                break
            if now() - start > wall:
                remember_failure(endpoint, "WALL_CAP", "monitor")
                break
            if watch is not None and not monitored_census(process.pid, watch, terminal=terminal):
                remember_failure(endpoint, "PRIVATE_DISK_CAP", "monitor")
                break
            for key, _ in selected.select(0.05):
                drain_ready(key)
            if endpoint["refusal"] is not None:
                break
    except BaseException as error:
        remember_failure(endpoint, "COMMAND_OBSERVER_ERROR", "command", error)
    finally:
        if process is not None:
            finish_child(process, endpoint, settle=settle)
        # Parent-owned pipe reads are distinct from any child filesystem capture.
        if capture_allowed(endpoint):
            try:
                for _ in range(256):
                    if not selected.get_map():
                        break
                    events = selected.select(0)
                    if not events:
                        break
                    for key, _ in events:
                        drain_ready(key)
            except BaseException as error:
                remember_failure(endpoint, "PIPE_DRAIN_ERROR", "pipe", error)
        for key in list(selected.get_map().values()):
            try:
                key.fileobj.close()
            except BaseException as error:
                remember_failure(endpoint, "PIPE_CLOSE_ERROR", "pipe", error)
        selected.close()
        if process is not None:
            for stream in (process.stdout, process.stderr):
                try:
                    stream.close()
                except BaseException as error:
                    remember_failure(endpoint, "PIPE_CLOSE_ERROR", "pipe", error)
    endpoint["streams_complete"] = all(eof) and all(seen[i] <= caps[i] for i in (0, 1))
    if not endpoint["streams_complete"]:
        remember_failure(endpoint, "PARENT_PIPE_INCOMPLETE", "pipe")
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    endpoint.update(wall_seconds=now() - start,
                    child_user_cpu_seconds=after.ru_utime - before.ru_utime,
                    child_system_cpu_seconds=after.ru_stime - before.ru_stime,
                    children_cumulative_maxrss_KiB=after.ru_maxrss,
                    streams=[{"bytes": seen[i], "sha256": hashes[i].hexdigest(),
                              "retained_bytes": len(buffers[i]), "EOF": eof[i]} for i in (0, 1)])
    try:
        # endpoint_durable means this exact body completed the durable writer.
        body = canonical({**endpoint, "endpoint_durable": True})
        writer(control / "endpoint.json", body, 8192)
        endpoint["endpoint_durable"] = True
    except BaseException as error:
        remember_failure(endpoint, "ENDPOINT_DURABILITY_UNKNOWN", "endpoint", error)
    return endpoint, [bytes(x) for x in buffers]
