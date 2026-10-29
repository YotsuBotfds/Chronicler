"""Inactive deployment-only observation. No token, HTTP, archive or world path."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

try:
    import wealth_floor_build_resources as R
except ImportError:
    from scripts import wealth_floor_build_resources as R

WORKFLOW_PATH = ".github/workflows/wealth-floor-deployment-diagnostic.yml"
ACTIVATION_BRANCH = "lead/wealth-floor-deployment-diagnostic-activation-20261029"
MAX_METADATA = 64 * 1024
CHUNK = 129
MAX_NAMESPACE = 128
RESOURCE_SOURCE = "44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2"
DEPLOYMENT_SOURCE = "ef872aced881b89d7bde8efbc0687134ae731916a9c2a233c368c1c22b11e085"
PATHS = {"pid1": "/proc/1/comm", "self_namespace": "/proc/self/ns/cgroup", "pid1_namespace": "/proc/1/ns/cgroup"}


class DiagnosticRefused(ValueError):
    pass


def require(condition, code):
    if not condition: raise DiagnosticRefused(code)


class Limits:
    def __init__(self, clock=time.monotonic):
        self.clock, self.start, self.bytes = clock, clock(), 0
    def check(self):
        elapsed = self.clock() - self.start
        require(0 <= elapsed <= 30, "deadline")
        return elapsed
    def charge(self, size):
        require(type(size) is int and size >= 0, "metadata_shape")
        require(self.bytes + size <= MAX_METADATA, "metadata_bound")
        self.bytes += size
        self.check()


@contextmanager
def hard_deadline():
    require(hasattr(signal, "setitimer") and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "timer_context")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(_sig, _frame): raise DiagnosticRefused("deadline")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def bounded_file(path, limits, *, once=False, opener=open):
    """Every underlying read is <=129 bytes; all metadata shares one cap."""
    chunks = []
    with opener(path, "rb") as stream:
        while True:
            limits.check()
            remaining = MAX_METADATA - limits.bytes
            require(remaining > 0, "metadata_bound")
            raw = stream.read(min(CHUNK, remaining))
            require(type(raw) is bytes and len(raw) <= min(CHUNK, remaining), "metadata_shape")
            limits.charge(len(raw)); chunks.append(raw)
            if once or not raw: break
    return b"".join(chunks).decode("ascii")


def safe_errno(exc):
    return exc.errno if type(exc.errno) is int and 0 <= exc.errno <= 4095 else None


def observe_field(field, reader, limits, *, namespace=False):
    try:
        limits.check(); value = reader(PATHS[field]); limits.check()
        if namespace:
            require(type(value) is str, "metadata_shape")
            size=len(value.encode("utf-8"));limits.charge(size)
            if size>MAX_NAMESPACE:return dict(value=None,error="namespace_bound",errno=None)
        return dict(value=value, error=None, errno=None)
    except OSError as exc:
        return dict(value=None, error="os_error", errno=safe_errno(exc))
    except UnicodeError:
        return dict(value=None, error="decode_error", errno=None)
    except DiagnosticRefused as exc:
        if str(exc) == "deadline": raise
        return dict(value=None, error="metadata_bound" if str(exc)=="metadata_bound" else "metadata_shape", errno=None)


def namespace_shape(value):
    return (type(value) is str and value.isascii() and len(value) <= MAX_NAMESPACE
            and re.fullmatch(r"cgroup:\[[1-9][0-9]{0,19}\]", value) is not None)


def comm_class(value):
    if type(value) is not str or not value.isascii() or len(value) > 128: return "other"
    value = value.strip()
    if value in ("systemd", "init", "tini", "bash"): return value
    if re.fullmatch(r"python(?:[0-9]+(?:\.[0-9]+)*)?", value): return "python"
    return "other"


def flag(value, known):
    return value if type(value) is str and value in known else "missing" if value is None else "other"


def error_row(row):
    return dict(category=row["error"], errno=row["errno"])


def first_predicate(env_ok, first, second):
    """Follow frozen ef872's order over this diagnostic's observations only."""
    if not env_ok: return "runner_context"
    if any(first[f]["error"] not in (None,"namespace_bound") for f in PATHS): return "initial_read_unavailable"
    if comm_class(first["pid1"]["value"]) != "systemd": return "pid1_systemd"
    if not all(namespace_shape(first[f]["value"]) for f in ("self_namespace", "pid1_namespace")): return "namespace_format"
    if first["self_namespace"]["value"] != first["pid1_namespace"]["value"]: return "namespace_match"
    for field in PATHS:
        if second[field]["error"]=="namespace_bound":return "evidence_stability"
        if second[field]["error"]: return "reread_unavailable"
        if second[field]["value"] != first[field]["value"]: return "evidence_stability"
    return "none_observed"


def memory_observation(limits, observer, reader):
    try:
        result = observer(read_text=reader)
        rows = result["visible_ancestors"]
        require(type(rows) is list and len(rows) <= 128, "metadata_shape")
        # Keep numeric observations and registered scope only; no path/text dump.
        observed = {key: result[key] for key in ("available_bytes", "host_available_bytes")}
        require(all(type(value) is int and 0 <= value <= 2**64-1 for value in observed.values()), "metadata_shape")
        numeric = []
        for row in rows:
            one = {key: row[key] for key in ("memory_max_bytes", "memory_current_bytes", "remaining_bytes")}
            require(all(value is None or type(value) is int and 0 <= value <= 2**64-1 for value in one.values()), "metadata_shape")
            numeric.append(one)
        limits.check()
        return dict(status="observed_only", **observed, visible_ancestor_count=len(rows), visible_limits=numeric,
                    scope="Host plus visible cgroup-v2 ancestors; namespace-invisible provider limits unobservable; no admission grant.")
    except OSError as exc:
        return dict(status="unavailable", category="os_error", errno=safe_errno(exc))
    except (R.ResourceRefused, UnicodeError):
        return dict(status="unavailable", category="unsupported_visible_metadata", errno=None)
    except DiagnosticRefused as exc:
        if str(exc)=="deadline": raise
        return dict(status="unavailable", category="metadata_bound" if str(exc)=="metadata_bound" else "metadata_shape", errno=None)
    except (KeyError, TypeError):
        return dict(status="unavailable", category="metadata_shape", errno=None)


def collect(*, environ, limits, read_comm, read_link, memory_reader, memory_observer=R.memory_admission):
    flags = dict(github_actions=flag(environ.get("GITHUB_ACTIONS"), {"true", "false"}),
                 runner_environment=flag(environ.get("RUNNER_ENVIRONMENT"), {"github-hosted", "self-hosted"}))
    first = {f: observe_field(f, read_comm if f=="pid1" else read_link, limits, namespace=f!="pid1") for f in PATHS}
    second = {f: observe_field(f, read_comm if f=="pid1" else read_link, limits, namespace=f!="pid1") for f in PATHS}
    env_ok = flags == dict(github_actions="true", runner_environment="github-hosted")
    namespaces_valid = all(namespace_shape(first[f]["value"]) for f in ("self_namespace", "pid1_namespace"))
    fields = {f: dict(initial_error=error_row(first[f]), reread_error=error_row(second[f]),
                      stable=first[f]["error"] is None and second[f]["error"] is None and first[f]["value"]==second[f]["value"])
              for f in PATHS}
    result = dict(schema_version=1, status="observation_only", diagnostic_only=True, admission_granted=False,
        candidate_worlds_enabled=False, flags=flags, pid1_class=comm_class(first["pid1"]["value"]),
        pid1_shape_valid=type(first["pid1"]["value"]) is str and first["pid1"]["value"].isascii() and len(first["pid1"]["value"])<=128,
        namespaces=dict(self_format_valid=namespace_shape(first["self_namespace"]["value"]),
          pid1_format_valid=namespace_shape(first["pid1_namespace"]["value"]),
          equal=first["self_namespace"]["value"]==first["pid1_namespace"]["value"] if namespaces_valid else None),
        fields=fields, first_failed_predicate=first_predicate(env_ok,first,second),
        scope="Current diagnostic observations only; original9aae failed predicate remains unknown; no provider attestation.",
        shared_helpers=dict(resource_sha256=RESOURCE_SOURCE, unchanged_deployment_sha256=DEPLOYMENT_SOURCE))
    result["memory"] = memory_observation(limits, memory_observer, memory_reader)
    result["limits"] = dict(wall_seconds=30, job_minutes=5, per_read_bytes=CHUNK, admitted_namespace_bytes=MAX_NAMESPACE,
                            aggregate_metadata_bytes=MAX_METADATA, output_bytes=MAX_METADATA)
    result["observed_metadata_bytes"] = limits.bytes
    result["wall_seconds_before_output"] = limits.check()
    require(len(encoded(result)) <= MAX_METADATA, "output_bound")
    return result


def encoded(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))+"\n").encode()


def pin_one_cpu(*, get_affinity=None, set_affinity=None):
    get_affinity=get_affinity or getattr(os,"sched_getaffinity",None)
    set_affinity=set_affinity or getattr(os,"sched_setaffinity",None)
    require(callable(get_affinity) and callable(set_affinity), "cpu_policy")
    available = get_affinity(0)
    require(available and len(available)<=4096 and all(type(cpu) is int and cpu>=0 for cpu in available), "cpu_policy")
    selected=min(available);set_affinity(0,{selected})
    require(get_affinity(0)=={selected}, "cpu_policy")
    return dict(selected_cpu=selected, process_affinity_count=1, numerical_thread_caps=1)


def write_output(path, raw, limits):
    require(len(raw)<=MAX_METADATA, "output_bound")
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,"wb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "output_type")
        stream.write(raw);stream.flush();os.fsync(stream.fileno());limits.check()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observe",action="store_true");parser.add_argument("--output")
    args=parser.parse_args(argv)
    if not args.observe:
        print('{"status":"inactive","diagnostic_only":true}');return 0
    stage="arguments"
    try:
        require(args.output is not None,"output_required")
        with hard_deadline():
            limits=Limits();stage="cpu_policy";cpu=pin_one_cpu()
            stage="observe"
            result=collect(environ=os.environ,limits=limits,
                read_comm=lambda path:bounded_file(path,limits,once=True),read_link=os.readlink,
                memory_reader=lambda path:bounded_file(path,limits))
            result["cpu_policy"]=cpu
            raw=encoded(result);require(len(raw)<=MAX_METADATA,"output_bound")
            stage="publish"
            write_output(args.output,raw,limits);limits.check()
            print(raw.decode().strip())
        return 0
    except Exception as exc:
        known={"deadline","metadata_shape","metadata_bound","timer_context","output_bound","cpu_policy","output_type","output_required"}
        reason=str(exc) if isinstance(exc,DiagnosticRefused) and str(exc) in known else "os_error" if isinstance(exc,OSError) else "unexpected_exception"
        print(encoded(dict(status="diagnostic_refused",stage=stage,reason=reason,
            errno=safe_errno(exc) if isinstance(exc,OSError) else None,admission_granted=False)).decode().strip(),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
