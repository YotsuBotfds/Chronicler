"""Dormant, closed historical byte-audit job. Default invocation performs no IO.

Explicit execution downloads five registered official artifacts, stages only
bounded authority files and calls the separately reviewed baseline reader.
It never builds/imports native code, decodes worlds or grants candidate worlds.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import signal
import stat
import sys
import time
from types import MappingProxyType
import urllib.error
import urllib.parse
import urllib.request
import zipfile

try:
    import wealth_floor_baseline_admission as A
    import wealth_floor_hosted_deployment as D
except ImportError:
    from scripts import wealth_floor_baseline_admission as A
    from scripts import wealth_floor_hosted_deployment as D

API = "https://api.github.com/repos/YotsuBotfds/Chronicler"
REPOSITORY_ID = 1187468861
JOB_NAME = "Retained baseline byte audit"
WORKFLOW_PATH = ".github/workflows/wealth-floor-baseline-audit.yml"
PRODUCER_BRANCH = "lead/wealth-floor-baseline-audit-activation-2-20261029"
USER_AGENT = "Chronicler-closed-baseline-byte-audit"
MAX_API = 1024 * 1024
MAX_AUTHORITY = 128 * A.BLOCK_BYTES
MAX_PUBLICATION = 192 * A.BLOCK_BYTES
RESOURCE_SOURCE = "44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2"
DEPLOYMENT_SOURCE = "d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8"


class JobRefused(A.AdmissionError):
    """Only fixed, non-sensitive refusal messages cross the CLI boundary."""
    def __init__(self, message, *, reason="contract_refused"):
        self.reason = reason
        super().__init__(message)


@dataclass(frozen=True)
class InputPin:
    artifact_id: int
    name: str
    size: int
    sha256: str
    expires_at: str


INPUTS = MappingProxyType({
    "comparison": InputPin(12868832709, "full-gates-comparison-40791402289-1", 24835,
        "08a96322a503f33a4b068ead2e0832af6eb4f972e7de32bced87c01462fb5646", "2026-11-28T02:40:55Z"),
    "template-light": InputPin(12864154643, "full-gates-light-candidate-template-40791402289-1", 4860197,
        "745443ffe29595cc96a7f1d6b58b13d5f974a2abb43954299e8227b80d95c786", "2026-11-28T01:15:20Z"),
    "procedural-light": InputPin(12868305362, "full-gates-light-candidate-procedural-40791402289-1", 1768422,
        "9c6117236e0ab51671c2ded18c1536ca27d129f8976c30dd96f21a34f5f500aa", "2026-11-28T02:13:31Z"),
    **{world + "-raw": InputPin(pin.artifact_id,
        f"full-gates-raw-candidate-{world}-{A.OLD_RUN}-1", pin.size, pin.sha256, pin.expires_at)
       for world, pin in A.ARCHIVES.items()},
})
MAX_DOWNLOAD = sum(p.size for p in INPUTS.values())
AUTHORITY_NAMES = frozenset({"comparison.json"} |
    {world + "/" + name for world in A.ARCHIVES for name in A.LIGHT_NAMES})
GENERATED_NAMES = frozenset(("official-inputs.json", "producer.json", "sources.json",
    "baseline-audit.json", "controller.json", "final-charge.json"))


class Progress:
    """Bounded negative evidence; never stores response text, URLs or headers."""
    STAGES = frozenset(("admission", "old-run", "producer", "input-metadata", "download", "authority", "prepare", "audit", "finalization"))
    REASONS = frozenset(("contract_refused", "http_refused", "transport_failed", "deadline_exceeded",
                         "budget_exceeded", "resource_refused", "deployment_refused", "digest_refused", "filesystem_refused", "unexpected_exception"))
    def __init__(self):
        self.select("admission")
    def select(self, stage, key=None):
        A.require(stage in self.STAGES and (key is None or key in INPUTS), "invalid progress registration")
        self.stage, self.key, self.http_status, self.response_bytes = stage, key, None, None
    def http(self, status):
        self.http_status = status if type(status) is int and 100 <= status <= 599 else None
        self.response_bytes = 0
    def received(self, count):
        A.require(type(count) is int and 0 <= count <= MAX_DOWNLOAD + MAX_API, "invalid progress byte count")
        self.response_bytes = count
    def refusal(self, exc):
        reason = "unexpected_exception"
        deployment_code = None
        if isinstance(exc, JobRefused): reason = exc.reason if exc.reason in self.REASONS else "contract_refused"
        elif isinstance(exc, D.DeploymentRefused):
            reason = "deployment_refused"
            code = getattr(exc, "code", None)
            if type(code) is str and code in getattr(D, "REFUSAL_CODES", frozenset()): deployment_code = code
        elif isinstance(exc, A.AdmissionError):
            reason = {"transport CPU/wall budget exceeded": "budget_exceeded",
                "overall controller wall budget exceeded": "budget_exceeded", "audit CPU/wall budget exceeded": "budget_exceeded",
                "disk admission/floor unmet": "resource_refused", "RAM admission/floor unmet": "resource_refused",
                "effective memory observation refused": "resource_refused", "download EOF/digest differs": "digest_refused"
                }.get(str(exc), "contract_refused")
        elif isinstance(exc, OSError): reason = "filesystem_refused"
        return dict(kind="wealth-floor-baseline-audit-refusal", schema_version=1, status="refused", stage=self.stage,
            artifact_id=INPUTS[self.key].artifact_id if self.key is not None else None, reason=reason,
            deployment_predicate_code=deployment_code, http_status=self.http_status,
            response_bytes_received=self.response_bytes, candidate_worlds_enabled=False)


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


def artifact_endpoint(pin):
    return API + "/actions/artifacts/" + str(pin.artifact_id)


def validate_input_publication(metadata, pin, now):
    wanted = dict(id=pin.artifact_id, name=pin.name, size_in_bytes=pin.size,
                  digest="sha256:" + pin.sha256, expired=False, expires_at=pin.expires_at)
    A.require(isinstance(metadata, dict) and all(type(metadata.get(k)) is type(v) and metadata[k] == v
              for k, v in wanted.items()), "registered artifact publication differs")
    origin = metadata.get("workflow_run")
    A.require(isinstance(origin, dict) and type(origin.get("id")) is int and origin["id"] == A.OLD_RUN
              and origin.get("head_sha") == A.OLD_CONTROL and type(origin.get("repository_id")) is int
              and origin["repository_id"] == REPOSITORY_ID and type(origin.get("head_repository_id")) is int
              and origin["head_repository_id"] == REPOSITORY_ID, "registered artifact origin differs")
    A.require(isinstance(now, datetime) and now.tzinfo is not None and A.utc(pin.expires_at) > now,
              "registered artifact expired")
    # Do not retain API URL/header fields or arbitrary response content.
    return {**wanted, "workflow_run": {k: origin[k] for k in ("id", "head_sha", "repository_id", "head_repository_id")}}


def validate_old_run(row):
    A.require(isinstance(row, dict) and type(row.get("id")) is int and row["id"] == A.OLD_RUN
              and type(row.get("run_attempt")) is int and row["run_attempt"] == 1
              and row.get("head_sha") == A.OLD_CONTROL and row.get("status") == "completed"
              and row.get("conclusion") == "success" and isinstance(row.get("repository"), dict)
              and type(row["repository"].get("id")) is int and row["repository"]["id"] == REPOSITORY_ID,
              "historical run not completed successfully")
    return dict(id=A.OLD_RUN, run_attempt=1, head_sha=A.OLD_CONTROL, status="completed", conclusion="success",
                repository_id=REPOSITORY_ID)


def validate_current_producer(run, jobs, *, control_sha, run_id, attempt):
    A.validate_producer_identity(control_sha, run_id, 1)
    A.require(type(attempt) is int and attempt == 1, "only one preregistered producer attempt permitted")
    A.require(isinstance(run, dict) and type(run.get("id")) is int and run["id"] == run_id
              and run.get("head_sha") == control_sha and type(run.get("run_attempt")) is int
              and run["run_attempt"] == attempt and run.get("status") == "in_progress"
              and run.get("event") == "push" and run.get("head_branch") == PRODUCER_BRANCH and run.get("path") == WORKFLOW_PATH
              and isinstance(run.get("repository"), dict) and type(run["repository"].get("id")) is int
              and run["repository"]["id"] == REPOSITORY_ID,
              "current producer run differs")
    A.require(isinstance(jobs, dict) and type(jobs.get("total_count")) is int and jobs["total_count"] == 1
              and isinstance(jobs.get("jobs"), list) and len(jobs["jobs"]) == 1, "one complete producer job required")
    job = jobs["jobs"][0]
    A.require(isinstance(job, dict), "producer job object required")
    A.validate_producer_identity(job.get("head_sha"), job.get("run_id"), job.get("id"))
    A.require(job["head_sha"] == control_sha and job["run_id"] == run_id and job.get("name") == JOB_NAME
              and type(job.get("run_attempt")) is int and job["run_attempt"] == attempt
              and job.get("status") == "in_progress", "current producer job differs")
    return dict(control_sha=control_sha, run_id=run_id, job_id=job["id"], attempt=attempt,
                workflow_path=WORKFLOW_PATH, branch=PRODUCER_BRANCH, job_name=JOB_NAME, status="in_progress")


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    """One 302 from the selected official ZIP endpoint; no body or header copy."""
    def __init__(self, endpoint, progress=None):
        self.endpoint, self.followed, self.progress = endpoint, False, progress
    def http_error_302(self, request, response, code, message, headers):
        try:
            if self.progress is not None: self.progress.http(code)
            location = headers.get("location") or headers.get("Location")
            A.require(type(location) is str and 0 < len(location) <= 16 * 1024
                      and all(33 <= ord(c) <= 126 for c in location), "artifact redirect location refused")
            redirected = self.redirect_request(request, response, code, message, headers, location)
        finally:
            response.close()  # Never drain a redirect/error body.
        return self.parent.open(redirected, timeout=request.timeout)
    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302
    def redirect_request(self, request, response, code, message, headers, newurl):
        try:
            target = urllib.parse.urlsplit(newurl)
            allowed = (not self.followed and code == 302 and request.full_url == self.endpoint
                and self.endpoint in {artifact_endpoint(p) + "/zip" for p in INPUTS.values()}
                and target.scheme == "https" and target.hostname is not None
                and target.hostname.endswith(".blob.core.windows.net")
                and target.port in (None, 443) and target.username is target.password is None and not target.fragment)
        except ValueError:
            allowed = False
        A.require(allowed, "artifact redirect refused")
        self.followed = True
        # urllib must derive the destination Host. Never copy header_items().
        return urllib.request.Request(newurl, headers={"User-Agent": USER_AGENT}, method="GET")


class OfficialClient:
    def __init__(self, token, *, run_id, attempt, budget, opener_factory=urllib.request.build_opener, progress=None):
        A.require(type(token) is str and token and not any(c.isspace() for c in token), "job token unavailable")
        A.require(type(run_id) is int and run_id > 0 and type(attempt) is int and attempt == 1, "producer origin invalid")
        self.token, self.budget, self.opener_factory = token, budget, opener_factory
        self.progress = progress or Progress()
        self.old_run = API + f"/actions/runs/{A.OLD_RUN}/attempts/1"
        self.current_run = API + f"/actions/runs/{run_id}/attempts/{attempt}"
        self.current_jobs = self.current_run + "/jobs?per_page=100"
        self.allowed = frozenset((self.old_run, self.current_run, self.current_jobs,
                                 *(artifact_endpoint(p) for p in INPUTS.values())))
    @contextmanager
    def response(self, endpoint, *, zip_input=False):
        A.require(endpoint in self.allowed or zip_input and endpoint in
                  {artifact_endpoint(p) + "/zip" for p in INPUTS.values()}, "unregistered HTTP endpoint")
        handler = OfficialRedirect(endpoint if zip_input else "", self.progress)
        opener = self.opener_factory(handler)
        request = urllib.request.Request(endpoint, headers={"Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT})
        self.budget.check()
        try:
            with opener.open(request, timeout=15) as response:
                self.budget.check()
                self.progress.http(response.getcode())
                A.require(response.getcode() == 200, "HTTP status refused")
                if zip_input:
                    target = urllib.parse.urlsplit(response.geturl())
                    A.require(handler.followed and target.scheme == "https" and target.hostname is not None
                              and target.hostname.endswith(".blob.core.windows.net"), "ZIP response origin refused")
                else:
                    A.require(response.geturl() == endpoint and not handler.followed, "metadata response origin differs")
                    A.require(response.headers.get("Link") is None, "paginated metadata refused")
                yield response
                self.budget.check()
        except urllib.error.HTTPError as exc:
            self.progress.http(exc.code)
            exc.close()
            raise JobRefused("official HTTP request refused", reason="http_refused") from None
        except (urllib.error.URLError, TimeoutError):
            raise JobRefused("official HTTP transport failed", reason="transport_failed") from None
    def metadata(self, endpoint):
        with self.response(endpoint) as response:
            check_length(response.headers, MAX_API)
            chunks, count = [], 0
            while True:
                raw = network_read(response, min(A.BLOCK_BYTES, MAX_API + 1 - count), self.budget, self.progress)
                if not raw: break
                count += len(raw)
                A.require(count <= MAX_API, "API metadata byte bound exceeded"); chunks.append(raw)
        return A.parse_json(b"".join(chunks), self.budget)


def check_length(headers, maximum, *, exact=False):
    value = headers.get("Content-Length")
    A.require(value is None or type(value) is str and value.isascii() and value.isdecimal()
              and len(value) <= 20 and (int(value) == maximum if exact else int(value) <= maximum), "HTTP length refused")
    A.require(headers.get("Content-Encoding") in (None, "identity"), "HTTP content encoding refused")


def network_read(response, count, budget, progress=None):
    # HTTPResponse.read1 performs one buffered raw read, letting clocks/floors
    # run between received chunks rather than waiting to fill a MiB.
    A.require(callable(getattr(response, "read1", None)), "bounded HTTP reader required")
    budget.check(); raw = response.read1(count)
    A.require(type(raw) is bytes and len(raw) <= count, "HTTP reader exceeded request bound")
    if progress is not None: progress.received((progress.response_bytes or 0) + len(raw))
    budget.check()
    return raw


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


def download(client, key, path, *, progress=None):
    A.require(key in INPUTS, "unregistered artifact selection")
    pin, budget = INPUTS[key], client.budget
    progress = progress or getattr(client, "progress", None)
    digest, count = hashlib.sha256(), 0
    with client.response(artifact_endpoint(pin) + "/zip", zip_input=True) as response:
        check_length(response.headers, pin.size, exact=True)
        with fresh_file(path, budget) as stream:
            while True:
                raw = network_read(response, min(A.BLOCK_BYTES, pin.size + 1 - count), budget, progress)
                if not raw: break
                count += len(raw)
                A.require(count <= pin.size, "download byte bound exceeded")
                digest.update(raw); stream.write(raw); budget.check()
            A.require(count == pin.size and digest.hexdigest() == pin.sha256, "download EOF/digest differs")
    budget.check()
    return dict(artifact_id=pin.artifact_id, bytes=count, sha256=digest.hexdigest())


def stage_selected(path, pin, expected, destinations, budget, *, closed):
    """Read selected small files only after stable whole-archive verification."""
    A.require(expected and set(expected) == set(destinations) and sum(p.size for p in expected.values()) <= MAX_AUTHORITY
              and all(p.size <= A.MAX_METADATA_BYTES for p in expected.values()), "authority staging bound exceeded")
    records = {}
    with A._regular(path, budget) as (stream, before):
        A.require(before.st_size == pin.size and A._archive_hash(stream, pin.size, budget) == pin.sha256,
                  "authority archive digest differs")
        names = A.preflight_zip_index(stream, pin.size, budget)
        try:
            with zipfile.ZipFile(stream) as archive:
                rows = archive.infolist()
                A.require(len(rows) == len(names), "authority archive index differs")
                file_names = {name for name in names if not name.endswith("/")}
                prefixes = {str(p) for name in file_names for p in Path(name).parents if str(p) != "."}
                A.require(not file_names & prefixes, "authority file/directory conflict")
                files = set()
                for info, original in zip(rows, names, strict=True):
                    budget.check()
                    A.require(info.orig_filename == info.filename == original, "authority normalized name differs")
                    name = A.canonical_name(original, directory=info.is_dir())
                    mode = stat.S_IFMT(info.external_attr >> 16)
                    A.require(mode in (0, stat.S_IFDIR if info.is_dir() else stat.S_IFREG), "authority entry type refused")
                    if info.is_dir():
                        A.require(not closed and name in prefixes and info.file_size == info.compress_size == info.CRC == 0
                                  and info.compress_type == zipfile.ZIP_STORED, "unexpected authority directory")
                        with archive.open(info) as directory:
                            budget.check(); A.require(directory.read(1) == b"", "authority directory has data"); budget.check()
                        continue
                    A.require(name not in files, "duplicate authority file"); files.add(name)
                    if name not in expected:
                        A.require(not closed, "unexpected authority file")
                        continue
                    p = expected[name]
                    A.require(info.file_size == p.size and info.compress_size <= pin.size, "authority member size differs")
                    count, digest = 0, hashlib.sha256()
                    with archive.open(info) as member, fresh_file(destinations[name], budget) as target:
                        while True:
                            budget.check(); raw = member.read(min(A.BLOCK_BYTES, p.size + 1 - count)); budget.check()
                            if not raw: break
                            count += len(raw); A.require(count <= p.size, "authority member expanded beyond bound")
                            digest.update(raw); target.write(raw); budget.check()
                        A.require(count == p.size and digest.hexdigest() == p.sha256, "authority member EOF/hash differs")
                    records[name] = dict(bytes=count, sha256=digest.hexdigest())
                A.require(records.keys() == expected.keys() and (not closed or files == expected.keys()), "authority file set incomplete")
        except (zipfile.BadZipFile, EOFError, RuntimeError) as exc:
            raise JobRefused("authority ZIP refused") from exc
        A.require(A._archive_hash(stream, pin.size, budget) == pin.sha256, "authority archive changed")
    budget.check(); return records


def source_pins(budget):
    root = Path(__file__).absolute().parent
    result = {}
    for name in ("wealth_floor_baseline_audit_job.py", "wealth_floor_baseline_admission.py", "wealth_floor_build_resources.py",
                 "wealth_floor_hosted_deployment.py"):
        raw = A.bounded_read(root / name, A.BLOCK_BYTES, budget)
        result["scripts/" + name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    A.require(result["scripts/wealth_floor_build_resources.py"]["sha256"] == RESOURCE_SOURCE, "shared resource helper differs")
    A.require(result["scripts/wealth_floor_hosted_deployment.py"]["sha256"] == DEPLOYMENT_SOURCE, "shared deployment helper differs")
    return result


def publication_inventory(root, names, budget):
    """Finite expected directory trie; unexpected trees are refused before descent."""
    trie = {}
    for name in names:
        A.canonical_name(name); node = trie
        for part in name.split("/")[:-1]: node = node.setdefault(part, {})
        node[name.split("/")[-1]] = None
    with A._directory(root, budget) as fd:
        def visit(directory, node):
            seen = set()
            with os.scandir(directory) as entries:
                for entry in entries:
                    budget.check(); A.require(entry.name in node and entry.name not in seen, "unexpected publication entry")
                    seen.add(entry.name); before = entry.stat(follow_symlinks=False)
                    if node[entry.name] is None:
                        A.require(stat.S_ISREG(before.st_mode), "publication file not regular")
                    else:
                        A.require(stat.S_ISDIR(before.st_mode), "publication directory unsafe")
                        child = os.open(entry.name, A._flags(True), dir_fd=directory)
                        try:
                            A.require(A.identity(os.fstat(child)) == A.identity(before), "publication directory replaced")
                            visit(child, node[entry.name])
                        finally: os.close(child)
            A.require(seen == node.keys(), "publication incomplete")
        visit(fd, trie)
    rows = {}
    total = 0
    for name in sorted(names):
        raw = A.bounded_read(Path(root) / name, A.MAX_METADATA_BYTES, budget)
        total += len(raw); A.require(total <= MAX_PUBLICATION, "publication byte bound exceeded")
        rows[name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return rows


def run_job(root, *, token, control_sha, run_id, attempt, progress=None):
    with hard_wall(3300):
        return _run_job(root, token=token, control_sha=control_sha, run_id=run_id, attempt=attempt, progress=progress or Progress())


def _run_job(root, *, token, control_sha, run_id, attempt, progress):
    A.validate_producer_identity(control_sha, run_id, 1)
    A.require(type(attempt) is int and attempt == 1, "only preregistered attempt one permitted")
    overall = OverallClock(); transport = TransportBudget(overall)
    with ExitStack() as transport_deadline:
        transport_deadline.enter_context(hard_wall(1200))
        return _run_stages(root, token=token, control_sha=control_sha, run_id=run_id, attempt=attempt,
                           overall=overall, transport=transport, transport_deadline=transport_deadline, progress=progress)


def _run_stages(root, *, token, control_sha, run_id, attempt, overall, transport, transport_deadline, progress):
    root = Path(root).absolute()
    deployment = D.hosted_vm_precondition()
    transport.check()
    initial_resources = A._resources(root.parent, admission=True)
    transport.floor_probe = lambda: A._resources(root.parent)
    transport.check()
    sources_before = source_pins(transport)
    fresh_directory(root, transport)
    for name in ("archives", "publication", "publication/authority", "publication/authority/template",
                 "publication/authority/template/report", "publication/authority/procedural", "publication/authority/procedural/report"):
        fresh_directory(root / name, transport)
    archives, publication, authority = root / "archives", root / "publication", root / "publication/authority"
    client = OfficialClient(token, run_id=run_id, attempt=attempt, budget=transport, progress=progress)
    progress.select("old-run")
    old_before = validate_old_run(client.metadata(client.old_run))
    progress.select("producer")
    producer = validate_current_producer(client.metadata(client.current_run), client.metadata(client.current_jobs),
                                         control_sha=control_sha, run_id=run_id, attempt=attempt)
    before = {}
    for key, pin in INPUTS.items():
        progress.select("input-metadata", key)
        before[key] = validate_input_publication(client.metadata(artifact_endpoint(pin)), pin, datetime.now(timezone.utc))
    A.require(sum(pin.size for pin in INPUTS.values()) == MAX_DOWNLOAD, "aggregate download registration differs")
    downloads, after = {}, {}
    for key, pin in INPUTS.items():
        progress.select("download", key)
        downloads[key] = download(client, key, archives / (key + ".zip"), progress=progress)
        progress.select("input-metadata", key)
        after[key] = validate_input_publication(client.metadata(artifact_endpoint(pin)), pin, datetime.now(timezone.utc))
        A.require(after[key] == before[key], "publication changed during download")
    member = "full-gates-comparison/comparison.json"
    progress.select("authority", "comparison")
    stage_selected(archives / "comparison.zip", INPUTS["comparison"], {member: A.FilePin(71201, A.OLD_COMPARISON)},
                   {member: authority / "comparison.json"}, transport, closed=False)
    comparison = A.read_original_comparison(authority / "comparison.json", transport)
    authority_bytes = 71201
    for world in A.ARCHIVES:
        progress.select("authority", world + "-light")
        sealed = comparison["inputs"][world + "-candidate"]
        A.require(set(sealed) == A.LIGHT_NAMES, "original light input set differs")
        expected = {name: A.FilePin(row["bytes"], row["sha256"]) for name, row in sealed.items()}
        authority_bytes += sum(row.size for row in expected.values())
        A.require(authority_bytes <= MAX_AUTHORITY, "aggregate authority byte bound exceeded")
        stage_selected(archives / (world + "-light.zip"), INPUTS[world + "-light"], expected,
                       {name: authority / world / name for name in expected}, transport, closed=True)
    progress.select("old-run")
    old_after = validate_old_run(client.metadata(client.old_run))
    A.require(old_before == old_after, "historical run changed during transfer")
    progress.select("producer")
    producer_again = validate_current_producer(client.metadata(client.current_run), client.metadata(client.current_jobs),
                                               control_sha=control_sha, run_id=run_id, attempt=attempt)
    A.require(producer_again == producer, "producer changed during transfer")
    for key, pin in INPUTS.items():
        progress.select("input-metadata", key)
        A.require(validate_input_publication(client.metadata(artifact_endpoint(pin)), pin, datetime.now(timezone.utc)) == before[key],
                  "publication changed before audit")
    progress.select("finalization")
    save_bytes(publication / "producer.json", A.json_bytes(producer), transport)
    save_bytes(publication / "official-inputs.json", A.json_bytes(dict(before=before, after=after, downloads=downloads,
        original_run=dict(before=old_before, after=old_after))), transport)
    transfer_charge = transport.check()
    transport_deadline.close()
    with ExitStack() as audit_deadline:
        audit_deadline.enter_context(hard_wall(1800))
        return _audit_staged(publication, authority, archives, producer, before, control_sha, run_id,
                             transfer_charge, overall, dict(admission=initial_resources, transport_last=transport.resources), progress,
                             sources_before, deployment)


def _audit_staged(publication, authority, archives, producer, before, control_sha, run_id, transfer_charge, overall, resource_observations, progress,
                  sources_before, deployment):
    budget = AuditBudget(overall)
    progress.select("prepare")
    plan = A.prepare_baseline_plan(authority / "comparison.json", {world: authority / world for world in A.ARCHIVES}, budget)
    progress.select("audit")
    audited = A.audit_baseline(plan, {world: archives / (world + "-raw.zip") for world in A.ARCHIVES},
        {world: before[world + "-raw"] for world in A.ARCHIVES}, publication / "baseline-audit.json",
        control_sha=control_sha, run_id=run_id, job_id=producer["job_id"], budget=budget)
    progress.select("finalization")
    sources_after = source_pins(budget)
    A.require(sources_after == sources_before, "script bytes changed during transfer/audit")
    save_bytes(publication / "sources.json", A.json_bytes(dict(before=sources_before, after=sources_after, identical=True,
        scope="Disk snapshots before any transfer and after both raw audits; not an in-memory code attestation.")), budget)
    names = {"authority/" + n for n in AUTHORITY_NAMES} | (GENERATED_NAMES - {"controller.json", "final-charge.json"})
    inventory = publication_inventory(publication, names, budget)
    summary = dict(schema_version=1, status="audit_complete_pending_job", producer=producer,
        receipt_sha256=audited["receipt_sha256"], transport=transfer_charge, audit=budget.check(), overall_wall_seconds=overall.check(),
        resources={**resource_observations, "audit_last": budget.resources},
        deployment=dict(observation=deployment, accepted_proc_text_max_bytes=128, proc_text_read_max_bytes=129,
          accepted_namespace_text_max_bytes=128,
          required_github_actions="true", required_runner_environment="github-hosted", required_pid1="systemd",
          readable_pid1_namespace_must_match=True,
          unverified_pid1_namespace_policy="Only initial and repeated EACCES13 under stable hosted flags, PID1 systemd and own namespace; equality remains UNVERIFIED.",
          namespace_equality_scope="Use the shared helper's explicit observed equality and verification status; no hidden-provider proof."),
        resource_limits=dict(admission_disk_free_bytes=12*1024**3, admission_ram_available_bytes=2*1024**3,
                             running_disk_floor_bytes=3*1024**3, running_ram_floor_bytes=1024**3),
        interpreter=dict(version=sys.version, implementation=sys.implementation.name, platform=sys.platform),
        files=inventory, clocks=dict(transport_wall_limit=1200, transport_process_cpu_limit=300,
          audit_wall_limit=1800, audit_process_cpu_limit=900, overall_wall_limit=3300, github_job_timeout_minutes=60),
        retention=dict(publication_max_bytes=MAX_PUBLICATION, original_artifact_expiry_preserved=True,
          downloaded_zip_policy="Retained through controller finalization; ephemeral only at runner teardown; no deletion API.",
          original_official_artifacts="Remain at registered IDs and original expiry; not extended by this audit."),
        candidate_worlds_enabled=False, authority="Pending exact receipt digest, successful completed producer and verified audit-artifact publication.")
    save_bytes(publication / "controller.json", A.json_bytes(summary), budget)
    save_bytes(publication / "final-charge.json", A.json_bytes(dict(status="pending_completed_job", receipt_sha256=audited["receipt_sha256"],
        snapshot_scope="After controller fsync; before final full publication rehash and final source recheck; not an end-to-end CPU total.",
        audit_after_controller_fsync=budget.check(), overall_wall_seconds=overall.check())), budget)
    publication_inventory(publication, {"authority/" + n for n in AUTHORITY_NAMES} | GENERATED_NAMES, budget)
    final_sources = source_pins(budget)
    A.require(final_sources == sources_before, "script bytes changed during finalization")
    source_snapshot_digest = hashlib.sha256(A.json_bytes(final_sources)).hexdigest()
    final_observation = dict(scope="After final publication rehash and source recheck; before stdout serialization and job publication/completion.",
                             audit=budget.check(), overall_wall_seconds=overall.check(), source_snapshots_match=True,
                             source_snapshot_sha256=source_snapshot_digest)
    budget.check(); overall.check()
    return dict(status="audit_complete_pending_job", receipt_sha256=audited["receipt_sha256"], candidate_worlds_enabled=False,
                final_observation=final_observation)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--control-sha")
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--attempt", type=int)
    args = parser.parse_args(argv)
    if not args.execute:
        print(A.json_bytes(dict(status="inactive", artifact_ids=[p.artifact_id for p in INPUTS.values()],
            candidate_worlds_enabled=False)).decode().strip())
        return 0
    progress = Progress()
    try:
        A.require(args.output is not None, "fresh output path required")
        result = run_job(args.output, token=os.environ.get("GH_TOKEN"), control_sha=args.control_sha,
                         run_id=args.run_id, attempt=args.attempt, progress=progress)
    except Exception as exc:
        # No exception text, URLs, headers, token or response body is logged.
        raw = A.json_bytes(progress.refusal(exc))
        A.require(len(raw) <= 1024, "refusal receipt bound exceeded")
        print(raw.decode().strip(), file=sys.stderr)
        return 1
    print(A.json_bytes(result).decode().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
