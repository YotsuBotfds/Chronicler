"""Closed, stdlib-only original-byte audit primitives. No work on import.

This is a new archive contract, not an override of a generic reader's caps.
Historical publication observations are never treated as new audit clocks.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.abc
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

GIB = 1024**3
SECONDS, RESERVE, METADATA = 600, 20, 2 * 1024**2
MAX_ENTRIES, MAX_EXPANSION, MAX_MEMBER = 5000, 512 * 1024**2, 64 * 1024**2
PUBLICATION_BYTES, PUBLICATION_FILES = 8 * 1024**2, 64
REPO, REPO_ID = "YotsuBotfds/Chronicler", 1187468861
ORIGINAL = "2d3faa8c41b4704386b246507b8606d4e3980be7"
PRODUCER = "cbf6e368ebd218c1f54179bee4accffc1ab2a4c0"
BRANCH = "lead/cloud-fresh-practice-original-audit-deps-20261029"
WORKFLOW = ".github/workflows/research-practice-original-audit.yml"
WORKSPACE = Path("/home/runner/work/Chronicler/Chronicler")
TEMP = Path("/home/runner/work/_temp")
TOPS = {"practice-study-evidence": "dir", "practice-study-readout": "dir",
        "practice-study-contracts": "dir", "practice-study-wheel": "dir",
        "practice-study-freeze.json": "file", "proof-metadata-observation.json": "file"}
BASE_BUDGETS = {"controller_charged_upper_bound_cpu_seconds", "controller_measured_to_seal_cpu_seconds",
                "controller_finalization_cpu_reserve_seconds", "aggregate_wall_seconds", "within_registered_limits"}
ANNOTATIONS = {"reader_cpu_seconds", "controller_charge_plus_reader_measured_cpu_upper_bound_seconds",
               "total_cpu_accounting_scope", "controller_to_readout_wall_seconds"}
PUBLISH_KEYS = ("reader_cpu_seconds", "controller_charge_plus_reader_measured_cpu_upper_bound_seconds",
                "total_cpu_accounting_scope", "controller_to_readout_wall_seconds")
SCOPE = "conservative controller charge plus measured reader CPU; not measured total CPU"
USER_AGENT = "Chronicler-closed-original-practice-audit"
INPUTS = {
    "raw": dict(id=12898552635, run=40877451052, job=123459812638, source=ORIGINAL,
        branch="lead/cloud-fresh-practice-study-cbf-20261029", event="push",
        workflow=".github/workflows/research-practice-fresh-study-cbf.yml",
        name="fresh-practice-study-raw-40877451052-1", bytes=106435368,
        sha256="248960348f7361e7a903f6a5323d3bca503b47cced45e57157631b8d0aba5ac0",
        expiry="2026-11-28T13:00:35Z"),
    "wheel": dict(id=12882944002, run=40841527996, job=123338805674, source=PRODUCER,
        branch="lead/research-practice-observer-runner-seam-20261029", event="workflow_dispatch",
        workflow=".github/workflows/tests.yml", name="native-wheel-" + PRODUCER, bytes=3850581,
        sha256="9cc55c9dbf7939056f0b0613e3e54e74798a782463719185d41b1fe129ebe2cf",
        expiry="2026-11-12T08:33:42Z")}


class Refused(ValueError):
    pass


class AdmissionRefused(Refused):
    def __init__(self, code, observation):
        self.observation = observation
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise Refused(code)


def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def canonical(value):
    # The map registration deliberately uses NO newline, unlike C.encoded.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode()


def loads(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "duplicate_json_key")
            value[key] = item
        return value
    def number(value):
        value = float(value)
        require(math.isfinite(value), "nonfinite_json")
        return value
    def constant(value):
        raise Refused("nonfinite_json")
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def regular(path):
    row = Path(path).lstat()
    require(stat.S_ISREG(row.st_mode) and row.st_nlink == 1, "regular_nlink1_required")
    return row


def bounded(path, maximum=MAX_MEMBER):
    row = regular(path)
    require(row.st_size <= maximum, "file_bound")
    with Path(path).open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) == row.st_size and len(raw) <= maximum, "file_changed_or_bound")
    return raw


def file_pin(path, check=lambda: None):
    row, size, digest = regular(path), 0, hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024**2):
            check()
            size += len(block)
            digest.update(block)
    final = regular(path)
    require(size == row.st_size and all(getattr(row, key) == getattr(final, key) for key in
            ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")), "file_changed")
    return dict(bytes=size, sha256=digest.hexdigest())


def relative(name):
    require(type(name) is str and name and "\\" not in name and "\0" not in name
            and not name.startswith("/") and not name.endswith("/")
            and PurePosixPath(name).as_posix() == name
            and all(p not in ("", ".", "..") for p in name.split("/")), "unsafe_member_path")
    return name


def central(archive, *, count=None, expanded=None):
    entries = archive.infolist()
    require(len(entries) <= MAX_ENTRIES and (count is None or len(entries) == count), "central_count")
    rows, total = {}, 0
    for info in entries:
        name = relative(info.filename)
        mode = info.external_attr >> 16
        require(getattr(info, "orig_filename", name) == name and name not in rows and not info.is_dir() and not info.flag_bits & 1
                and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "central_member_kind")
        require(type(info.file_size) is int and 0 <= info.file_size <= MAX_MEMBER, "member_bound")
        total += info.file_size
        require(total <= MAX_EXPANSION, "expansion_bound")
        rows[name] = info
    require(expanded is None or total == expanded, "central_expansion")
    # File/directory collisions must fail before the first copy.
    require(not any(parent.as_posix() in rows for name in rows
                    for parent in PurePosixPath(name).parents if str(parent) != "."), "member_prefix_alias")
    return rows


def member(archive, info, expected, check=lambda: None, destination=None):
    require(type(expected) is dict and set(expected) == {"bytes", "sha256"}
            and type(expected["bytes"]) is int and expected["bytes"] == info.file_size, "member_pin_shape")
    digest, size, chunks = hashlib.sha256(), 0, []
    with archive.open(info) as stream:
        while block := stream.read(64 * 1024):
            check()
            size += len(block)
            require(size <= expected["bytes"], "member_stream_bound")
            digest.update(block)
            if destination is None:
                chunks.append(block)
            else:
                destination.write(block)
    require(dict(bytes=size, sha256=digest.hexdigest()) == expected, "member_hash_or_crc")
    return b"".join(chunks) if destination is None else None


def expected_map(archive, rows, registration, check=lambda: None):
    small = registration["small_authority"]["member_pins"]
    payloads = {name: member(archive, rows[name], value, check) for name, value in small.items()}
    execution = loads(payloads["practice-study-evidence/execution.json"])
    files = execution["files"]
    require(type(files) is dict and len(files) == 2442
            and sum(v["bytes"] for v in files.values()) == 500545147, "execution_inventory_size")
    result = {"practice-study-evidence/" + relative(name): row for name, row in files.items()}
    for name, row in small.items():
        require(name not in result or result[name] == row, "small_inventory_collision")
        result[name] = row
    verification = loads(payloads["practice-study-wheel/verification.json"])
    for name in ("build-manifest.json", "producer-metadata.json"):
        result["practice-study-wheel/" + name] = verification["files"][name]
    closure = registration["expected_archive_closure"]
    require(closure["expected_file_members"] == 2455 and closure["expected_expanded_bytes"] == 502390864
            and closure["expected_member_map_sha256"] == "8f2a0923119ea08ef6136e0e9175aeb6dc7d1fe382146de0a1d768263b85c47c",
            "fixed_map_registration")
    return close_map(rows, result, closure)


def close_map(rows, result, closure):
    """Pure closure gate; expected_map supplies the fixed study registration."""
    require(len(result) == closure["expected_file_members"]
            and sum(v["bytes"] for v in result.values()) == closure["expected_expanded_bytes"]
            and hashlib.sha256(canonical(result)).hexdigest() == closure["expected_member_map_sha256"], "closed_map_digest")
    require(set(result) == set(rows) and all(rows[n].file_size == p["bytes"] for n, p in result.items()), "closed_map_set")
    return result


def no_links(path):
    path = Path(path)
    require(path.is_absolute(), "absolute_owned_path_required")
    for parent in reversed((path, *path.parents)):
        if parent.exists() or parent.is_symlink():
            require(not parent.is_symlink(), "path_symlink")


def lease_targets(base):
    """Caller owns fixed absent top-level targets; lease lies OUTSIDE them."""
    no_links(base)
    require(base.is_dir(), "target_parent_missing")
    require(all(not (base / name).exists() and not (base / name).is_symlink() for name in TOPS), "target_preexists")
    result = {}
    try:
        for name, kind in TOPS.items():
            path = base / name
            if kind == "dir":
                path.mkdir(mode=0o700)
            else:
                with path.open("xb"):
                    pass
            row = path.lstat()
            result[name] = dict(device=row.st_dev, inode=row.st_ino, kind=kind)
    except BaseException:
        cleanup_targets(base, result)
        raise
    return result


def owned_root(base, top, lease):
    require(top in lease and top in TOPS, "unleased_target")
    path = base / top
    no_links(path)
    row = path.lstat()
    require((row.st_dev, row.st_ino) == (lease[top]["device"], lease[top]["inode"])
            and (stat.S_ISDIR(row.st_mode) if lease[top]["kind"] == "dir" else
                 stat.S_ISREG(row.st_mode) and row.st_nlink == 1), "target_lease_changed")
    return path


def copy_member(archive, info, expected, base, lease, check):
    parts = relative(info.filename).split("/")
    root = owned_root(base, parts[0], lease)
    if len(parts) == 1:
        require(lease[parts[0]]["kind"] == "file" and root.stat().st_size == 0, "placeholder_changed")
        descriptor = os.open(root, os.O_WRONLY | os.O_NOFOLLOW)
        try:
            row = os.fstat(descriptor)
            require((row.st_dev, row.st_ino) == (lease[parts[0]]["device"], lease[parts[0]]["inode"]), "placeholder_identity")
        except BaseException:
            os.close(descriptor)
            raise
    else:
        require(lease[parts[0]]["kind"] == "dir", "target_kind")
        parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            row = os.fstat(parent)
            require((row.st_dev, row.st_ino) == (lease[parts[0]]["device"], lease[parts[0]]["inode"]), "copy_root_identity")
            for component in parts[1:-1]:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=parent)
                except FileExistsError:
                    pass
                following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = following
            descriptor = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 mode=0o600, dir_fd=parent)
        finally:
            os.close(parent)
    with os.fdopen(descriptor, "wb") as stream:
        require(os.fstat(stream.fileno()).st_nlink == 1, "copy_alias")
        member(archive, info, expected, check, stream)
        stream.flush()
        os.fchmod(stream.fileno(), 0o444)
    require(file_pin(base / info.filename, check) == expected, "copy_posthash")


def cleanup_targets(base, lease):
    for name in reversed(lease):
        root = owned_root(base, name, lease)
        if lease[name]["kind"] == "dir":
            # Refuse links/aliases before deleting anything in this root.
            paths = list(root.rglob("*"))
            require(len(paths) <= MAX_ENTRIES * 2, "cleanup_inventory_bound")
            for path in paths:
                require(not path.is_symlink(), "cleanup_link")
                if path.is_file():
                    regular(path)
                else:
                    require(stat.S_ISDIR(path.lstat().st_mode), "cleanup_special")
            root.chmod(0o700)
            for path in paths:
                if path.is_dir():
                    path.chmod(0o700)
            for path in sorted(paths, key=lambda p: len(p.parts), reverse=True):
                path.rmdir() if path.is_dir() else path.unlink()
            root.rmdir()
        else:
            root.unlink()
    require(all(not (base / name).exists() for name in lease), "cleanup_incomplete")


def resources(path, resolver, *, initial=False, next_bytes=0, disk_usage=shutil.disk_usage):
    require(type(next_bytes) is int and next_bytes >= 0, "copy_reserve_type")
    memory = resolver()
    free = disk_usage(path).free
    row = dict(free_disk_bytes=free, next_copy_bytes=next_bytes, memory=memory)
    if free < (12 if initial else 3) * GIB + next_bytes + PUBLICATION_BYTES:
        raise AdmissionRefused("disk_floor", row)
    if type(memory["available_bytes"]) is not int or memory["available_bytes"] < (2 if initial else 1) * GIB:
        raise AdmissionRefused("ram_floor", row)
    return row


def forbidden(name):
    return name.split(".", 1)[0] in {"chronicler", "chronicler_agents", "numpy", "pyarrow", "arro3",
        "scipy", "pydantic", "pickle", "_pickle", "cloudpickle", "dill"}


class ImportGuard(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.attempts = []
    def find_spec(self, fullname, path=None, target=None):
        if forbidden(fullname):
            require(len(self.attempts) < 32, "import_attempt_bound")
            self.attempts.append(fullname)
            raise Refused("forbidden_import")


@contextmanager
def import_guard():
    require(not any(forbidden(n) for n in sys.modules), "forbidden_module_preloaded")
    guard, before = ImportGuard(), sorted(sys.modules)
    sys.meta_path.insert(0, guard)
    try:
        yield guard, before
        require(not guard.attempts and not any(forbidden(n) for n in sys.modules), "forbidden_module_or_attempt")
    finally:
        sys.meta_path.remove(guard)


def historical_annotations(C, original, execution_receipt, receipt, completion):
    C.closed(original["budgets"], BASE_BUDGETS | ANNOTATIONS, "original budgets")
    require(type(original.get("publication_status")) is str and original["publication_status"] ==
            "provisional_until_matching_completion_seal", "publication_status")
    previous_cpu = previous_wall = None
    closed = execution_receipt
    for row in (original["budgets"], receipt["budget_observation"], completion["budget_observation"]):
        C.closed(row, (BASE_BUDGETS - {"aggregate_wall_seconds", "within_registered_limits"}) | ANNOTATIONS
                 if row is not original["budgets"] else BASE_BUDGETS | ANNOTATIONS, "historical annotation budget")
        for key in (BASE_BUDGETS | ANNOTATIONS) - {"total_cpu_accounting_scope", "within_registered_limits"}:
            if key in row:
                require(type(row[key]) in (int, float) and math.isfinite(row[key]) and row[key] >= 0,
                        "historical_budget_number")
        require(row["total_cpu_accounting_scope"] == SCOPE and type(row["total_cpu_accounting_scope"]) is str,
                "historical_budget_scope")
        require(all(type(row[k]) is float for k in ANNOTATIONS - {"total_cpu_accounting_scope"}),
                "historical_annotation_float_type")
        for name, source in (("controller_charged_upper_bound_cpu_seconds", "charged_aggregate_cpu_seconds"),
                ("controller_measured_to_seal_cpu_seconds", "measured_to_seal_cpu_seconds"),
                ("controller_finalization_cpu_reserve_seconds", "finalization_cpu_reserve_seconds")):
            require(C.same(row[name], closed[source]), "historical_controller_link")
        cpu, wall = row["reader_cpu_seconds"], row["controller_to_readout_wall_seconds"]
        require(C.same(row["controller_charge_plus_reader_measured_cpu_upper_bound_seconds"],
                closed["charged_aggregate_cpu_seconds"] + cpu)
                and closed["charged_aggregate_cpu_seconds"] + cpu <= 900
                and closed["aggregate_wall_seconds"] <= wall <= 1800, "historical_budget_equation")
        require(previous_cpu is None or cpu >= previous_cpu and wall >= previous_wall, "historical_budget_regressed")
        previous_cpu, previous_wall = cpu, wall
    return {key: deepcopy(original["budgets"][key]) for key in PUBLISH_KEYS}


def semantic_replay(C, D, rebuilt, original, annotations, markdown_raw):
    require("publication_status" not in rebuilt and set(rebuilt["budgets"]) == BASE_BUDGETS,
            "unexpected_rebuilt_publisher_fields")
    semantic = deepcopy(original)
    del semantic["publication_status"]
    for key in ANNOTATIONS:
        del semantic["budgets"][key]
    # Replay EXACT C.write wire encoding. It PRESERVES mapping insertion order;
    # only checkpoint_projection sorts, and it is NOT used for this boundary.
    rebuilt_wire = C.loads(C.encoded(rebuilt))
    require(C.same(rebuilt_wire, semantic), "semantic_replay_differs")
    reconstructed = deepcopy(rebuilt)
    reconstructed["publication_status"] = original["publication_status"]
    reconstructed["budgets"].update(annotations)
    require(C.same(C.loads(C.encoded(reconstructed)), original), "whole_readout_reconstruction_differs")
    require(D.markdown(rebuilt).encode("utf-8") == markdown_raw, "markdown_replay_differs")
    return dict(semantic_equal=True, whole_original_reconstructed=True, original_markdown_equal=True,
                scope="semantic replay plus original publication seals; no new historical CPU measurement")


def unexpired_inputs(now=None):
    """Both fixed originals remain unexpired through terminal publication."""
    observed = datetime.now(timezone.utc) if now is None else now
    for role, value in INPUTS.items():
        expiry = datetime.fromisoformat(value["expiry"].replace("Z", "+00:00"))
        require(observed < expiry, "original_" + role + "_expired")
    return dict(checked_utc=observed.isoformat(), registered_expiries={role: value["expiry"] for role, value in INPUTS.items()})


def metadata_contract(role, value, now=None):
    p = INPUTS[role]
    require(type(value) is dict and set(value) == {"run", "job", "artifact"}, "metadata_roles")
    run, job, artifact = (value[k] for k in ("run", "job", "artifact"))
    expected = dict(id=p["run"], run_attempt=1, head_sha=p["source"], head_branch=p["branch"],
                    event=p["event"], path=p["workflow"], status="completed", conclusion="success")
    require(all(type(run.get(k)) is type(v) and run[k] == v for k, v in expected.items())
            and run.get("repository", {}).get("id") == REPO_ID
            and run["repository"].get("full_name") == REPO, "producer_metadata")
    expected = dict(id=p["job"], run_id=p["run"], run_attempt=1, head_sha=p["source"], status="completed", conclusion="success")
    require(all(type(job.get(k)) is type(v) and job[k] == v for k, v in expected.items()), "producer_job")
    expected = dict(id=p["id"], name=p["name"], size_in_bytes=p["bytes"], digest="sha256:" + p["sha256"],
                    expired=False, expires_at=p["expiry"])
    require(all(type(artifact.get(k)) is type(v) and artifact[k] == v for k, v in expected.items()), "artifact_metadata")
    origin = artifact.get("workflow_run", {})
    expected = dict(id=p["run"], head_sha=p["source"], repository_id=REPO_ID, head_repository_id=REPO_ID)
    require(all(type(origin.get(k)) is type(v) and origin[k] == v for k, v in expected.items()), "artifact_origin")
    expiry = datetime.fromisoformat(p["expiry"].replace("Z", "+00:00"))
    require(expiry > (now or datetime.now(timezone.utc)), "artifact_expired")
    return deepcopy(p)


class TransportFailure(Refused):
    def __init__(self, stage, status, provider):
        self.facts = dict(stage=stage, http_status=status, provider_kind=provider)
        super().__init__("fixed_input_transport_refused")


def provider(url):
    try:
        p = urllib.parse.urlsplit(url)
        if p.scheme == "https" and p.hostname == "api.github.com":
            return "github_api"
        if p.scheme == "https" and p.hostname and p.hostname.endswith(".blob.core.windows.net"):
            return "azure_blob"
    except (TypeError, ValueError):
        pass
    return "unregistered"


class FixedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, zip_endpoint, notes):
        self.zip_endpoint, self.notes = zip_endpoint, notes
    def redirect_request(self, request, response, code, message, headers, newurl):
        try:
            p = urllib.parse.urlsplit(newurl)
            allowed = (request.full_url == self.zip_endpoint and code == 302 and len(newurl) <= 16384
                and all(33 <= ord(c) <= 126 for c in newurl) and p.scheme == "https"
                and p.hostname and p.hostname.endswith(".blob.core.windows.net")
                and p.port in (None, 443) and p.username is p.password is None and not p.fragment)
        except (ValueError, TypeError):
            allowed = False
        if not allowed:
            raise TransportFailure("redirect_validation", code, provider(request.full_url))
        self.notes.append(dict(stage="zip_get", http_status=302, provider_kind="github_api"))
        return urllib.request.Request(newurl, headers={"User-Agent": USER_AGENT}, method="GET")
    def http_error_302(self, request, response, code, message, headers):
        try:
            target = headers.get("location") or headers.get("Location")
            require(type(target) is str, "redirect_refused")
            new = self.redirect_request(request, response, code, message, headers, target)
        finally:
            response.close()  # Never read redirect/error bodies.
        return self.parent.open(new, timeout=request.timeout)
    def http_error_301(self, request, response, code, message, headers):
        response.close()
        raise TransportFailure("redirect_validation", code, "unregistered")
    http_error_303 = http_error_307 = http_error_308 = http_error_301


class Transport:
    """One fixed role per transfer; never an endpoint or digest CLI override."""
    def __init__(self, role, token, guard, deadline, *, opener=None):
        require(role in INPUTS and type(token) is str and bool(token), "transport_registration")
        self.p, self.role, self.token, self.guard = INPUTS[role], role, token, guard
        self.deadline, self.notes = deadline, []
        self.base = "https://api.github.com/repos/" + REPO
        self.zip_endpoint = self.base + "/actions/artifacts/" + str(self.p["id"]) + "/zip"
        self.opener = opener or urllib.request.build_opener(FixedRedirect(self.zip_endpoint, self.notes))
    def check(self):
        self.guard()
        require(time.monotonic() < self.deadline, "transfer_deadline")
    def request(self, url, stage, maximum, destination=None):
        allowed = {self.zip_endpoint, self.zip_endpoint[:-4], self.base + "/actions/runs/" + str(self.p["run"]),
                   self.base + "/actions/jobs/" + str(self.p["job"])}
        require(url in allowed, "unregistered_endpoint")
        self.check()
        request = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT})
        chunks, size, digest = [], 0, hashlib.sha256()
        try:
            with self.opener.open(request, timeout=min(15, max(.1, self.deadline - time.monotonic()))) as response:
                kind = provider(response.geturl())
                require(response.getcode() == 200 and kind in ("github_api", "azure_blob")
                        and (kind == "github_api" or url == self.zip_endpoint), "response_origin")
                self.notes.append(dict(stage="azure_redirect" if kind == "azure_blob" else stage,
                                       http_status=200, provider_kind=kind))
                require(len(self.notes) <= 16, "transport_observation_bound")
                length = response.headers.get("Content-Length")
                require(length is None or length.isdecimal() and int(length) <= maximum, "response_length")
                while True:
                    self.check()
                    block = response.read(min(64 * 1024, maximum + 1 - size))
                    if not block:
                        break
                    size += len(block)
                    require(size <= maximum, "response_bound")
                    digest.update(block)
                    if destination is None:
                        chunks.append(block)
                    else:
                        destination.write(block)
        except urllib.error.HTTPError as exc:
            kind = provider(exc.url)
            status = exc.code if type(exc.code) is int and 100 <= exc.code <= 599 else None
            exc.close()
            raise TransportFailure("azure_redirect" if kind == "azure_blob" else stage, status, kind) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise TransportFailure(stage, None, "unregistered") from None
        self.check()
        return (b"".join(chunks) if destination is None else dict(bytes=size, sha256=digest.hexdigest()))
    def metadata(self):
        rows = {}
        for role, path in (("run", "/actions/runs/" + str(self.p["run"])),
                           ("job", "/actions/jobs/" + str(self.p["job"])),
                           ("artifact", "/actions/artifacts/" + str(self.p["id"]))):
            rows[role] = loads(self.request(self.base + path, role + "_get", METADATA))
        metadata_contract(self.role, rows)
        return rows
    def download(self, path):
        with Path(path).open("xb") as stream:
            observed = self.request(self.zip_endpoint, "zip_get", self.p["bytes"], stream)
        require(observed == {k: self.p[k] for k in ("bytes", "sha256")}, "whole_archive_bytes")
        require(file_pin(path, self.check) == observed, "archive_posthash")
        return observed
