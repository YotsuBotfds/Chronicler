#!/usr/bin/env python3
"""Pending remote-only forensics of the original incomplete full cohort.

Two exact raw ZIPs; whole compressed identity and selected metadata CRC/hash.
No full member audit, scientific qualification, state decode, CP body or World.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import resource
import signal
import stat
import sys
import time
import zipfile
import zlib

import wealth_floor_full_archive_audit as W
import wealth_floor_baseline_admission as A
import wealth_floor_build_resources as R
import wealth_floor_hosted_deployment as D

REVIEWED_DIAGNOSTIC_ACTIVATION = None
BRANCH = "lead/cloud-wealth-floor-failed-cohort-diagnostic-20261029"
WORKFLOW = ".github/workflows/wealth-floor-failed-cohort-diagnostic.yml"
TEMPLATE_FILE = "docs/workflows/wealth-floor-failed-cohort-diagnostic.yml"
TEMPLATE_SHA256 = "0f840149f565463db93dcd3317767f2a7c61a3752c49080054cb20fd89cfb960"
PUBLICATION_FILE = "docs/integration/wealth-floor-failed-cohort-publications.json"
PUBLICATION_SHA256 = "f212d0a0ac120aaa672fdfa87f7075c618f56a50cd916de9ad5968c07f88b383"
REPOSITORY_ID = 1187468861
ORIGINAL_CUTOFF = "2026-11-28T01:15:25Z"
MAX_OUTPUT = 8 * A.BLOCK_BYTES
MAX_SELECTED = 128 * A.BLOCK_BYTES
MAX_TAIL = 64 * 1024
MAX_JOURNAL_LINE = 64 * 1024
JOB_NAME = "Read original failed cohort metadata"
EXPECTED_STAGED = 1418182084
CAP_KEYS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS", "RAYON_NUM_THREADS", "CARGO_BUILD_JOBS")
SOURCE_PINS = {
    "scripts/wealth_floor_full_archive_audit.py": "336285269f835cd341f710236d1e3ae42ec9f053806d6771acb880f38dbab0e0",
    "scripts/wealth_floor_baseline_admission.py": W.KERNEL_SHA256,
    "scripts/wealth_floor_build_resources.py": "44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2",
    "scripts/wealth_floor_hosted_deployment.py": "d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8",
}
PROGRESS = frozenset({"progress.jsonl", "progress-segments/index.json"} |
    {f"progress-segments/segment-{i:03d}.jsonl" for i in range(15)})
ALLOWLIST = PROGRESS | frozenset({
    "logs/original-runner.log", "result.json", "light/result.json", "light/completion.json",
    "candidate-checkpoint-capture.jsonl", "candidate-checkpoint-index.json",
    "checkpoint-retirement.json", "checkpoint-retirement.jsonl", "failed-checkpoint-body-selection.json",
    "runtime-before.json", "probes/before.json", "execution-admission.json", "execution-deadline.json",
    "source-snapshot-before.json", "control-sources-before.json", "build-manifest.json",
    "raw/full_gate/batch_42/batch_manifest.json", "raw/full_gate/batch_42/run_manifest.json",
    "raw/full_gate/batch_42/validate_report_full.json", "raw/full_gate/batch_42/gate_decision_full.json",
    "raw/full_gate/ablation_42/ablation_manifest.json",
})
REQUIRED = frozenset({"result.json", "logs/original-runner.log", "candidate-checkpoint-capture.jsonl"})
CREDENTIAL = re.compile(r"(?i)(?:authorization\s*[:=]|bearer\s+|--(?:token|password|secret|credential)(?:=|\Z)|"
    r"(?:[?&]|\b)(?:access_token|api_key|password|secret|signature|sig)=|[a-z]+://[^/\s]*@)")


class JobRefused(A.AdmissionError):
    def __init__(self, message, *, reason="contract_refused"):
        self.reason = reason
        super().__init__(message)


def registration():
    A.require(A.hash_shape(REVIEWED_DIAGNOSTIC_ACTIVATION), "diagnostic activation pending source review")
    return REVIEWED_DIAGNOSTIC_ACTIVATION


def workflow_contract(dormant, active):
    A.require(type(dormant) is bytes and type(active) is bytes and len(dormant) <= 64 * 1024
        and hashlib.sha256(dormant).hexdigest() == TEMPLATE_SHA256 and active == dormant,
        "reviewed active diagnostic workflow differs")
    return True


def validate_origin(run, jobs, artifacts, pins, *, now):
    A.require(type(run) is dict and type(run.get("id")) is int and run["id"] == W.PRODUCER_RUN
        and type(run.get("run_attempt")) is int and run["run_attempt"] == 1
        and run.get("head_sha") == W.PRODUCER_SOURCE and run.get("event") == "push"
        and run.get("head_branch") == "lead/cloud-wealth-floor-outcome-cohort-20261029"
        and run.get("path") == ".github/workflows/wealth-floor-outcome-cohort.yml"
        and run.get("status") == "completed" and run.get("conclusion") == "failure"
        and run.get("repository", {}).get("id") == REPOSITORY_ID, "original failed run differs")
    A.require(type(jobs) is dict and type(jobs.get("total_count")) is int and jobs["total_count"] == 2
        and type(jobs.get("jobs")) is list and len(jobs["jobs"]) == 2, "both original jobs required")
    wanted = {v: k for k, v in W.PRODUCER_JOBS.items()}
    A.require({row.get("id") for row in jobs["jobs"]} == set(wanted), "original job set differs")
    for row in jobs["jobs"]:
        A.require(type(row.get("id")) is int and row.get("run_id") == W.PRODUCER_RUN
            and type(row.get("run_attempt")) is int and row["run_attempt"] == 1
            and row.get("head_sha") == W.PRODUCER_SOURCE and row.get("status") == "completed"
            and row.get("conclusion") == "failure" and row.get("name") == f"cohort ({wanted[row['id']]})",
            "original failed job differs")
    A.require(type(pins) is list and len(pins) == 10 and len({p["id"] for p in pins}) == 10,
        "closed ten-output source publication required")
    A.require(type(artifacts) is dict and type(artifacts.get("total_count")) is int and artifacts["total_count"] == 10
        and type(artifacts.get("artifacts")) is list and len(artifacts["artifacts"]) == 10,
        "complete original publication listing required")
    actual = {row.get("id"): row for row in artifacts["artifacts"]}
    A.require(len(actual) == 10 and set(actual) == {p["id"] for p in pins}, "output IDs changed or missing")
    fields = ("id", "name", "size_in_bytes", "digest", "expires_at", "expired", "workflow_run")
    cutoffs = [W.strict_utc(ORIGINAL_CUTOFF)]
    for pin in pins:
        row = actual[pin["id"]]
        A.require(A.json_bytes({key: row.get(key) for key in fields}) == A.json_bytes(pin)
            and row.get("expired") is False, "original output publication differs")
        origin = row.get("workflow_run", {})
        A.require(type(origin.get("id")) is int and origin["id"] == W.PRODUCER_RUN
            and origin.get("head_sha") == W.PRODUCER_SOURCE
            and origin.get("head_branch") == "lead/cloud-wealth-floor-outcome-cohort-20261029"
            and origin.get("repository_id") == origin.get("head_repository_id") == REPOSITORY_ID,
            "original output origin differs")
        cutoffs.append(W.strict_utc(pin["expires_at"]))
    A.require(isinstance(now, datetime) and now.tzinfo is not None and now < min(cutoffs), "effective original retention expired")
    return dict(producer_source=W.PRODUCER_SOURCE, run_id=W.PRODUCER_RUN, attempt=1,
        jobs=dict(W.PRODUCER_JOBS), artifact_ids=sorted(actual),
        effective_earliest_expires_at=min(cutoffs).strftime("%Y-%m-%dT%H:%M:%SZ"), original_retention_extended=False)


class DiagnosticClient(W.ClosedClient):
    """Same held response/metadata primitives; only two ZIP endpoints exist."""
    def __init__(self, token, raws, budget, *, opener_factory=None, current_run_id=None):
        A.require(type(raws) is tuple and len(raws) == 2 and all(type(p) is W.InputPin and p.family == "raw" for p in raws)
            and {p.worldgen for p in raws} == W.WORLDGENS
            and sum(p.size for p in raws) == EXPECTED_STAGED <= W.MAX_STAGED,
            "exact two-archive staging required")
        A.require(type(token) is str and token and not any(c.isspace() for c in token), "job credential unavailable")
        self.token, self.budget = token, budget
        self.opener_factory = opener_factory or W.urllib.request.build_opener
        self.zip_endpoints = frozenset(W.endpoint(p) + "/zip" for p in raws)
        allowed = {W.API + f"/actions/runs/{W.PRODUCER_RUN}/attempts/1",
            W.API + f"/actions/runs/{W.PRODUCER_RUN}/attempts/1/jobs?per_page=100",
            W.API + f"/actions/runs/{W.PRODUCER_RUN}/artifacts?per_page=100"}
        if current_run_id is not None:
            A.require(type(current_run_id) is int and current_run_id > 0, "current diagnostic run ID")
            allowed.update((W.API + f"/actions/runs/{current_run_id}/attempts/1",
                W.API + f"/actions/runs/{current_run_id}/attempts/1/jobs?per_page=100"))
        self.metadata_endpoints = frozenset(allowed)


def selected_limit(name):
    return 8 * A.BLOCK_BYTES if name.endswith(".jsonl") or name == "logs/original-runner.log" else A.MAX_METADATA_BYTES


def index_policy(infos, names):
    A.require(len(infos) == len(names) <= A.MAX_ENTRIES, "ZIP index count differs")
    total, selected = 0, {}
    seen = set(); directories = set()
    for info, expected_name in zip(infos, names, strict=True):
        A.require(info.orig_filename == info.filename == expected_name, "ZIP name normalized")
        name = A.canonical_name(info.filename, directory=info.is_dir()); mode = stat.S_IFMT(info.external_attr >> 16)
        A.require(not info.flag_bits & 1 and info.compress_type in (0, 8), "unsupported ZIP member")
        if info.is_dir():
            A.require(mode in (0, stat.S_IFDIR) and info.file_size == info.compress_size == info.CRC == 0
                and info.compress_type == zipfile.ZIP_STORED, "unsafe directory member")
            directories.add(name)
            continue
        A.require(mode in (0, stat.S_IFREG) and name not in seen and type(info.file_size) is int and info.file_size >= 0,
            "unsafe or aliased regular member")
        A.require(type(info.compress_size) is int and 0 <= info.compress_size <= A.MAX_COMPRESSED_BYTES,
            "member compressed span bound")
        A.require(not name.endswith('.ckpt'), "unexpected CP body in original raw publication")
        seen.add(name); total += info.file_size
        A.require(total <= A.MAX_PAYLOAD_BYTES, "whole archive expanded cap")
        if name.startswith("progress-segments/") and name.endswith(".jsonl"):
            A.require(name in PROGRESS, "unregistered progress segment")
        if name in ALLOWLIST:
            A.require(info.file_size <= selected_limit(name), "selected member cap")
            selected[name] = info
    A.require(REQUIRED <= selected.keys(), "required original diagnostic member missing")
    A.require(sum(info.file_size for info in selected.values()) <= MAX_SELECTED, "selected metadata aggregate cap")
    prefixes = {str(p) for name in seen for p in PurePosixPath(name).parents if str(p) != "."}
    A.require(not seen & prefixes, "ZIP file/directory prefix collision")
    A.require(not directories & seen and directories <= prefixes, "unexpected/aliased ZIP directory")
    return selected, total, len(seen)


def summarize(name, raw, budget):
    """Only source-declared metadata formats; every other payload stays opaque."""
    if name == "logs/original-runner.log":
        text = raw.decode("utf-8", "replace")
        A.require(not CREDENTIAL.search(text), "potential credential-bearing original log refused")
        errors = [line for line in text.splitlines() if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Refused|Exception):", line)]
        A.require(all(len(line.encode()) <= 4096 for line in errors), "exception line cap")
        return dict(exception_lines=errors[:8], tail_bytes=min(len(raw), MAX_TAIL), original_log_bytes=len(raw)), raw[-MAX_TAIL:]
    if name.endswith(".jsonl"):
        rows = []; events = {}; first = last = None; parsed_lines = 0
        for line in raw.splitlines(keepends=True):
            budget.check(); A.require(len(line) <= MAX_JOURNAL_LINE and line.endswith(b'\n'), "metadata journal framing")
            row = A.parse_json(line, budget); parsed_lines += 1; first = first or row; last = row
            event = row.get("event")
            if type(event) is str: events[event] = events.get(event, 0) + 1
            if name == "candidate-checkpoint-capture.jsonl":
                captured = {key: row.get(key) for key in ("path", "seed", "turn", "bytes", "sha256", "strict_current_identity_matches")}
                header = row.get("header", {})
                captured.update(header_world=header.get("world"), header_sections=[s.get("name") for s in header.get("sections", [])],
                    header_source=header.get("identity", {}).get("source"),
                    header_native_sha256=header.get("identity", {}).get("native", {}).get("sha256"))
                rows.append(captured)
        return dict(row_count=parsed_lines, event_counts=events,
            first_event=first if name != "candidate-checkpoint-capture.jsonl" else None,
            last_event=last if name != "candidate-checkpoint-capture.jsonl" else None, captured=rows), None
    value = A.parse_json(raw, budget)
    if name.endswith("batch_manifest.json"):
        runs = value.get("runs"); seeds = value.get("seeds")
        return dict(status=value.get("status"), seeds=seeds, turns=value.get("turns"), parallel_requested=value.get("parallel_requested"),
            source=value.get("source"), native=value.get("native"), environment=value.get("environment"),
            run_count=len(runs) if type(runs) is list else None,
            declared_runs=[{k: row.get(k) for k in ("seed", "dir", "total_turns")} for row in runs] if type(runs) is list else None,
            scope="Original manifest declarations; no scientific payload decode or complete-cohort qualification."), None
    if name == "failed-checkpoint-body-selection.json":
        return {key: value.get(key) for key in ("failed_producer", "selected_bytes", "limits", "publication_status",
            "selection_complete_for_remaining_verified_files")} | dict(selected_count=len(value.get("selected", [])),
            omitted_count=len(value.get("omitted", [])), missing_count=len(value.get("missing_or_already_retired", []))), None
    return value, None


def inspect_archive(path, pin, budget, *, emit_tail):
    A.require(type(pin) is W.InputPin and pin.family == "raw", "typed original raw pin required")
    rows = {}; observations = {}
    with A._regular(path, budget) as (stream, before):
        A.require(before.st_size == pin.size and A._archive_hash(stream, pin.size, budget) == pin.sha256,
            "original ZIP whole identity differs")
        names = A.preflight_zip_index(stream, pin.size, budget)
        with zipfile.ZipFile(stream) as archive:
            selected, expanded, files = index_policy(archive.infolist(), names)
            for name, info in sorted(selected.items()):
                budget.check(); digest = hashlib.sha256(); crc = count = 0; pieces = []
                with archive.open(info) as member:
                    while True:
                        budget.check(); block = member.read(min(A.BLOCK_BYTES, info.file_size + 1 - count)); budget.check()
                        if not block: break
                        count += len(block); A.require(count <= info.file_size, "selected member expansion")
                        digest.update(block); crc = zlib.crc32(block, crc); pieces.append(block)
                A.require(count == info.file_size and crc & 0xffffffff == info.CRC, "selected member EOF/CRC differs")
                raw = b''.join(pieces); observation, tail = summarize(name, raw, budget)
                rows[name] = dict(bytes=count, sha256=digest.hexdigest(), crc32=info.CRC)
                observations[name] = observation
                if tail is not None: emit_tail(tail)
        A.require(A._archive_hash(stream, pin.size, budget) == pin.sha256, "original ZIP changed during selected read")
    return dict(archive_id=pin.artifact_id, archive_sha256=pin.sha256, archive_bytes=pin.size,
        whole_index_files=files, whole_index_expanded_bytes=expanded, selected=rows,
        absent_selected=sorted(ALLOWLIST - rows.keys()), observations=observations,
        complete_member_CRC_or_payload_audit=False, scientific_qualification=False, checkpoint_body_decode=False)


class OverallClock:
    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
    def check(self):
        elapsed = self.clock() - self.started
        A.require(type(elapsed) in (int, float) and 0 <= elapsed <= 3300, "overall controller wall budget exceeded")
        return elapsed


class TransportBudget:
    """Transport+small staging only; this clock is frozen before raw auditing."""
    def __init__(self, overall, *, wall=time.monotonic, cpu=time.process_time):
        self.overall, self.wall, self.cpu = overall, wall, cpu
        self.start_wall, self.start_cpu = wall(), cpu()
        self.floor_probe, self.next_floor, self.resources = None, 0.0, None
    def check(self):
        self.overall.check()
        w, c = self.wall() - self.start_wall, self.cpu() - self.start_cpu
        A.require(0 <= w <= 1200 and 0 <= c <= 300, "transport CPU/wall budget exceeded")
        if self.floor_probe is not None and w >= self.next_floor:
            self.next_floor = w + 0.5
            self.resources = self.floor_probe()
            self.overall.check()
            w, c = self.wall() - self.start_wall, self.cpu() - self.start_cpu
            A.require(0 <= w <= 1200 and 0 <= c <= 300, "transport CPU/wall budget exceeded")
        return dict(wall_seconds=w, cpu_seconds=c)


class AuditBudget(A.Budget):
    def __init__(self, overall):
        self.overall = overall
        super().__init__()
    def check(self):
        self.overall.check()
        result = super().check()
        self.overall.check()
        return result


@contextmanager
def hard_wall(seconds):
    """Interrupt blocking POSIX IO; nested timers retain the outer deadline."""
    A.require(hasattr(signal, "setitimer") and signal.getitimer(signal.ITIMER_REAL)[1] == 0,
              "one-shot POSIX deadline required")
    started, previous = time.monotonic(), signal.getitimer(signal.ITIMER_REAL)[0]
    handler = signal.getsignal(signal.SIGALRM)
    def expired(_signum, _frame):
        raise JobRefused("blocking operation wall deadline exceeded", reason="deadline_exceeded")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(seconds, previous) if previous > 0 else seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, handler)
        if previous > 0:
            remaining = previous - (time.monotonic() - started)
            A.require(remaining > 0, "outer wall deadline exceeded")
            signal.setitimer(signal.ITIMER_REAL, remaining)


@contextmanager
def fresh_file(path, budget):
    path = Path(path); budget.check()
    with A._directory(path.parent, budget) as parent:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path.name, flags, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            before = os.fstat(stream.fileno())
            A.require(stat.S_ISREG(before.st_mode), "fresh output not regular")
            yield stream
            stream.flush(); os.fsync(stream.fileno()); budget.check()
            after = os.fstat(stream.fileno())
            current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            A.require(stat.S_ISREG(current.st_mode) and (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
                      and A.identity(current) == A.identity(after), "fresh output replaced")
        os.fsync(parent); budget.check()


def fresh_directory(path, budget):
    path = Path(path)
    with A._directory(path.parent, budget) as parent:
        os.mkdir(path.name, 0o700, dir_fd=parent)
        child = os.open(path.name, A._flags(True), dir_fd=parent)
        try:
            before = os.fstat(child)
            A.require(stat.S_ISDIR(before.st_mode) and A.identity(before) ==
                      A.identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), "fresh directory replaced")
            os.fsync(child); os.fsync(parent); budget.check()
        finally:
            os.close(child)


def save_bytes(path, raw, budget):
    A.require(type(raw) is bytes and len(raw) <= A.MAX_METADATA_BYTES, "output metadata bound exceeded")
    with fresh_file(path, budget) as stream:
        budget.check(); stream.write(raw); budget.check()
    budget.check(); digest = hashlib.sha256(raw).hexdigest(); budget.check()
    return dict(bytes=len(raw), sha256=digest)


def source_snapshot(control, budget):
    A.require(Path(A.__file__).resolve() == control / "scripts/wealth_floor_baseline_admission.py"
        and Path(W.__file__).resolve() == control / "scripts/wealth_floor_full_archive_audit.py"
        and Path(R.__file__).resolve() == control / "scripts/wealth_floor_build_resources.py"
        and Path(D.__file__).resolve() == control / "scripts/wealth_floor_hosted_deployment.py", "loaded source origin differs")
    rows = {}
    for name in (*SOURCE_PINS, "scripts/wealth_floor_failed_cohort_diagnostic.py", PUBLICATION_FILE, TEMPLATE_FILE, WORKFLOW):
        raw = A.bounded_read(control / name, A.MAX_METADATA_BYTES, budget)
        digest = hashlib.sha256(raw).hexdigest()
        if name in SOURCE_PINS: A.require(digest == SOURCE_PINS[name], "protected dependency differs")
        if name == PUBLICATION_FILE: A.require(digest == PUBLICATION_SHA256, "observed publication source differs")
        rows[name] = dict(bytes=len(raw), sha256=digest)
    workflow_contract(A.bounded_read(control / TEMPLATE_FILE, 64 * 1024, budget),
        A.bounded_read(control / WORKFLOW, 64 * 1024, budget))
    A.require(all(v is None for v in A.REVIEWED_CANDIDATE_PROOFS.values())
        and all(getattr(W, key) is None for key in ("REVIEWED_OUTPUTS", "REVIEWED_CLOSURES", "REVIEWED_OUTCOMES",
            "REVIEWED_RESOURCE_POLICY", "REVIEWED_COMPLETION")), "full completion authority must remain NULL")
    return rows


def current_producer(client, run_id, source):
    run = client.metadata(W.API + f"/actions/runs/{run_id}/attempts/1")
    jobs = client.metadata(W.API + f"/actions/runs/{run_id}/attempts/1/jobs?per_page=100")
    A.require(run.get("id") == run_id and type(run.get("run_attempt")) is int and run["run_attempt"] == 1
        and run.get("head_sha") == source and run.get("event") == "push" and run.get("head_branch") == BRANCH
        and run.get("path") == WORKFLOW and run.get("status") == "in_progress"
        and run.get("conclusion") is None
        and run.get("repository", {}).get("id") == REPOSITORY_ID, "current diagnostic producer differs")
    A.require(type(jobs.get("total_count")) is int and jobs["total_count"] == 1
        and type(jobs.get("jobs")) is list and len(jobs["jobs"]) == 1, "one diagnostic job required")
    job = jobs["jobs"][0]
    A.require(type(job.get("id")) is int and job["id"] > 0 and job.get("run_id") == run_id
        and type(job.get("run_attempt")) is int and job["run_attempt"] == 1
        and job.get("head_sha") == source and job.get("status") == "in_progress" and job.get("conclusion") is None
        and job.get("name") == JOB_NAME,
        "current diagnostic job differs")
    return dict(run_id=run_id, attempt=1, source=source, job_id=job["id"], branch=BRANCH, workflow=WORKFLOW)


def original_publication(client, pins):
    run = client.metadata(W.API + f"/actions/runs/{W.PRODUCER_RUN}/attempts/1")
    jobs = client.metadata(W.API + f"/actions/runs/{W.PRODUCER_RUN}/attempts/1/jobs?per_page=100")
    artifacts = client.metadata(W.API + f"/actions/runs/{W.PRODUCER_RUN}/artifacts?per_page=100")
    return validate_origin(run, jobs, artifacts, pins, now=datetime.now(timezone.utc))


class Outputs:
    def __init__(self, root):
        self.root, self.rows, self.total = root, {}, 0
    def save(self, name, value, budget, *, raw=False):
        A.canonical_name(name)
        A.require('/' not in name and name not in self.rows and len(self.rows) < 24, "finite fresh output name required")
        body = value if raw else A.json_bytes(value)
        A.require(type(body) is bytes and self.total + len(body) <= MAX_OUTPUT, "total diagnostic publication cap")
        row = save_bytes(self.root / name, body, budget)
        self.rows[name] = row; self.total += len(body)
        return row


def safe_failure(exc):
    value = dict(error_type=type(exc).__name__)
    code = getattr(exc, "code", None)
    if type(code) is str and code in D.REFUSAL_CODES: value["deployment_refusal_code"] = code
    elif type(code) is str and code in W.REFUSAL_CODES: value["reader_refusal_code"] = code
    reason = getattr(exc, "reason", None)
    if type(reason) is str and reason in {"contract_refused", "deadline_exceeded"}: value["controller_refusal_code"] = reason
    return value


def retain_failure(root, exc):
    """Two-second failure-only cleanup; never buys more reads or positive work."""
    budget = A.Budget(cpu_limit=1, wall_limit=2)
    value = dict(diagnostic_complete=False, **safe_failure(exc),
        scientific_qualification=False, worlds_admitted=False, original_archives_remain_remote=True)
    raw = A.json_bytes(value)
    with A._directory(Path(root) / "diagnostic", budget) as directory:
        try:
            info = os.stat("completion.json", dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            info = None
        if info is not None:
            A.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "unsafe failed completion")
            os.unlink("completion.json", dir_fd=directory)
        budget.check()
        fd = os.open("failure.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory)
        with os.fdopen(fd, 'wb') as stream:
            A.require(stream.write(raw) == len(raw), "partial failure receipt")
            stream.flush(); os.fsync(stream.fileno())
        os.fsync(directory); budget.check()
    return hashlib.sha256(raw).hexdigest()


def execute():
    registration()  # Before getenv, paths, host probes, credentials or clients.
    resource.setrlimit(resource.RLIMIT_CPU, (1200, 1200))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    overall = OverallClock(); root = None; outputs = None
    try:
        with hard_wall(3300):
            A.require(sys.platform == "linux" and sys.version_info[:3] == (3, 13, 17), "exact registered Linux/Python required")
            A.require(os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
                and os.environ.get("GITHUB_EVENT_NAME") == "push" and os.environ.get("GITHUB_JOB") == "diagnostic",
                "closed diagnostic first attempt required")
            source = os.environ.get("GITHUB_SHA"); run_text = os.environ.get("GITHUB_RUN_ID", "")
            A.require(type(source) is str and re.fullmatch(r"[0-9a-f]{40}", source)
                and re.fullmatch(r"[1-9][0-9]*", run_text), "diagnostic source/run required")
            run_id = int(run_text); control = Path(__file__).resolve().parents[1]
            temporary = Path(os.environ["RUNNER_TEMP"]).resolve()
            deployment = D.hosted_vm_precondition()
            A.require(os.environ.get("PYTHON_CPU_COUNT") == "1" and os.environ.get("PYTHONHASHSEED") == "0"
                and all(os.environ.get(key) == "1" for key in CAP_KEYS), "registered reader caps required")
            available = sorted(os.sched_getaffinity(0)); A.require(available, "reader CPU visibility required")
            os.sched_setaffinity(0, {available[0]})
            reader_runtime = dict(affinity=sorted(os.sched_getaffinity(0)), logical_cpu_count=1,
                caps={key: os.environ[key] for key in CAP_KEYS}, process_cpu_limit_seconds=1200,
                address_space_limit_bytes=2 * 1024**3)
            resources = A._resources(temporary, admission=True)
            W.staging_admission(available_disk=resources["disk_free_bytes"], available_ram=resources["ram_available_bytes"],
                staged_bytes=EXPECTED_STAGED, output_bytes=MAX_OUTPUT)
            sources_before = source_snapshot(control, overall)
            policy = A.parse_json(A.bounded_read(control / PUBLICATION_FILE, A.MAX_METADATA_BYTES, overall), overall)
            pins = policy.get("artifacts")
            A.require(policy.get("producer_source") == W.PRODUCER_SOURCE and policy.get("run_id") == W.PRODUCER_RUN,
                "closed failed producer source policy")
            raws = []
            for world in ("template", "procedural"):
                matching = [p for p in pins if p["name"] == f"wealth-outcome-full-{world}-raw-{W.PRODUCER_RUN}-1"]
                A.require(len(matching) == 1 and matching[0]["digest"].startswith("sha256:"), "one exact raw artifact per world")
                p = matching[0]
                raws.append(W.InputPin(world, "raw", p["id"], p["name"], p["size_in_bytes"], p["digest"][7:], p["expires_at"]))
            A.require(sum(p.size for p in raws) == EXPECTED_STAGED <= W.MAX_STAGED, "total original ZIP staging differs")
            root = temporary / "wealth-failed-cohort-diagnostic"
            A.require(len(str(root)) <= 128, "bounded diagnostic output path")
            fresh_directory(root, overall); fresh_directory(root / "archives", overall); fresh_directory(root / "diagnostic", overall)
            outputs = Outputs(root / "diagnostic")
            outputs.save("pending.json", dict(diagnostic_complete=False, scientific_qualification=False,
                complete_member_audit=False, worlds_admitted=False, original_full_run=W.PRODUCER_RUN), overall)
            outputs.save("sources-before.json", sources_before, overall)
            transport = TransportBudget(overall); transport.floor_probe = lambda: A._resources(root)
            token = os.environ.get("GH_TOKEN")
            client = DiagnosticClient(token, tuple(raws), transport, current_run_id=run_id)
            with hard_wall(1200):
                producer = current_producer(client, run_id, source)
                before_origin = original_publication(client, pins)
                outputs.save("origin-before.json", before_origin, transport)
                downloads = {}
                for pin in raws:
                    path = root / "archives" / (pin.worldgen + ".zip")
                    with client.response(W.endpoint(pin) + "/zip", zip_input=True) as response:
                        with fresh_file(path, transport) as stream:
                            downloads[pin.worldgen] = W.stream_download(response, pin, stream.write, transport.check)
                after_origin = original_publication(client, pins)
                after_producer = current_producer(client, run_id, source)
                A.require(A.json_bytes(before_origin) == A.json_bytes(after_origin)
                    and A.json_bytes(producer) == A.json_bytes(after_producer), "official publication/producer changed during transfer")
                outputs.save("origin-after-transfer.json", after_origin, transport)
                transport_measure = transport.check()
            audit = AuditBudget(overall); audit.floor_probe = lambda: A._resources(root)
            inspected = {}
            with hard_wall(1800):
                for pin in raws:
                    def tail(raw, world=pin.worldgen):
                        outputs.save(world + "-original-runner-tail.log", raw, audit, raw=True)
                    inspected[pin.worldgen] = inspect_archive(root / "archives" / (pin.worldgen + ".zip"), pin, audit, emit_tail=tail)
                    outputs.save(pin.worldgen + "-diagnostic.json", inspected[pin.worldgen], audit)
                audit_measure = audit.check()
                sources_after = source_snapshot(control, audit)
                A.require(A.json_bytes(sources_before) == A.json_bytes(sources_after), "diagnostic source bytes changed")
                outputs.save("sources-after.json", sources_after, audit)
                report = dict(schema_version=1, kind="incomplete-cohort-original-metadata-diagnostic", diagnostic_complete=True,
                    status="pending_completed_diagnostic_job_and_publication_verification", producer=producer,
                    original_publication=after_origin, deployment=deployment, admission=resources, downloads=downloads,
                reader_runtime=reader_runtime,
                    archives={world: {k: v for k, v in row.items() if k != "observations"} for world, row in inspected.items()},
                    selected_observations="Per-world diagnostic files; original log tails retain at most64KiB each.",
                    transport_measured=transport_measure, selected_read_measured=audit_measure,
                    selected_read_and_finalization_measured=audit.check(), controller_wall_before_final_serialization=overall.check(),
                    measured_scope="Single controller process clocks; final serialization/upload excluded; hard overall wall still covers final writes.",
                    scientific_qualification=False, complete_payload_audit=False, full_proof_registries_remain_null=True,
                    original_failed_checkpoint_bodies_acquired=False, checkpoint_state_decoded=False, worlds_admitted=False)
                report_row = outputs.save("diagnostic.json", report, audit)
                completion = dict(diagnostic_report=report_row, files=dict(outputs.rows), retained_bytes=outputs.total,
                    completed_producer_required=True, qualification=False, diagnostic_complete=True)
                outputs.save("completion.json", completion, audit)
                A.require(A.json_bytes(source_snapshot(control, audit)) == A.json_bytes(sources_after), "late source drift")
                overall.check(); audit.check()
                print(A.json_bytes(dict(status="DIAGNOSTIC_PENDING_COMPLETED_JOB", report_sha256=report_row["sha256"],
                    completion_sha256=outputs.rows["completion.json"]["sha256"], candidate_worlds=False)).decode(), end="")
                return 0
    except BaseException as exc:
        # Preserve original metadata/tails and never publish raw ZIPs. A failed
        # outer job/failure receipt invalidates any earlier diagnostic-complete
        # file; no standalone positive file is a consumer grant.
        if root is not None:
            try:
                retain_failure(root, exc)
            except BaseException:
                pass
        print(A.json_bytes(dict(status="REFUSED", **safe_failure(exc), diagnostic_complete=False,
            scientific_qualification=False, worlds_admitted=False)).decode(), end="")
        return 1


def main(argv=None):
    registration()
    A.require((sys.argv[1:] if argv is None else argv) == ["--execute"], "only closed diagnostic execution is registered")
    return execute()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except A.AdmissionError:
        print(A.json_bytes(dict(status="PENDING_SOURCE_REVIEW", diagnostic_complete=False,
            candidate_worlds=False, archive_acquired=False)).decode(), end="")
        raise SystemExit(2)
