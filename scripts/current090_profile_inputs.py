"""Selected authenticated metadata/transport utilities; no study CLI or World imports.

A fe7129a6 and H0d3a2c5d are immutable source dependencies from5ab. Only
allowlisted definitions below are reused, not their old matrix/controllers.
New input constants are specific to current090; actual execution remains held.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import time
from types import SimpleNamespace
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = "YotsuBotfds/Chronicler"
REPOSITORY_ID = 1187468861
METADATA_LIMIT = 2 * 1024**2
TRANSFER_SECONDS = 120


class Refusal(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Refusal(message)


def strict_json(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise Refusal("duplicate JSON key")
            out[key] = value
        return out

    def number(token):
        value = float(token)
        require(math.isfinite(value), "non-finite JSON number")
        return value

    def constant(token):
        raise Refusal("non-finite JSON constant")
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


H = SimpleNamespace(strict_json=strict_json)


@dataclass(frozen=True)
class ArtifactPin:
    artifact_id: int
    run_id: int
    job_id: int
    source: str
    name: str
    size: int
    sha256: str
    expiry: str
    workflow: str


def exact_int(value, expected):
    return type(value) is int and value == expected


def utc(value):
    require(type(value) is str and value.endswith("Z"), "invalid UTC timestamp")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def validate_publication(pin, run, job, artifact, now):
    require(exact_int(run.get("id"), pin.run_id) and run.get("head_sha") == pin.source
        and exact_int(run.get("run_attempt"), 1), "wrong completed input run")
    require(run.get("status") == "completed" and run.get("conclusion") == "success"
        and run.get("path") == pin.workflow and exact_int(run.get("repository", {}).get("id"), REPOSITORY_ID),
        "input run not completed successfully")
    require(exact_int(job.get("id"), pin.job_id) and exact_int(job.get("run_id"), pin.run_id)
        and exact_int(job.get("run_attempt"), 1) and job.get("head_sha") == pin.source
        and job.get("status") == "completed" and job.get("conclusion") == "success", "wrong completed input job")
    origin = artifact.get("workflow_run", {})
    require(exact_int(artifact.get("id"), pin.artifact_id) and artifact.get("name") == pin.name
        and exact_int(artifact.get("size_in_bytes"), pin.size) and artifact.get("digest") == "sha256:" + pin.sha256,
        "wrong input artifact content identity")
    require(exact_int(origin.get("id"), pin.run_id) and origin.get("head_sha") == pin.source
        and exact_int(origin.get("repository_id"), REPOSITORY_ID)
        and exact_int(origin.get("head_repository_id"), REPOSITORY_ID), "wrong artifact producer")
    require(artifact.get("expired") is False and artifact.get("expires_at") == pin.expiry
        and utc(pin.expiry) > now, "input artifact expired or original expiry changed")
    identity = {"run_id": pin.run_id, "job_id": pin.job_id, "attempt": 1, "source": pin.source,
        "workflow": pin.workflow, "artifact_id": pin.artifact_id, "name": pin.name,
        "bytes": pin.size, "sha256": pin.sha256, "expiry": pin.expiry, "completed_success": True}
    return {"identity": identity, "observed": {"run": run, "job": job, "artifact": artifact}}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class Transport:
    """Closed GitHub endpoints; never forward API authorization to blob storage."""
    def __init__(self, token, supervisor, deadline):
        require(type(token) is str and bool(token), "read-only artifact token required")
        self.token, self.supervisor = token, supervisor
        self.deadline = min(deadline, time.monotonic() + TRANSFER_SECONDS)
        self.opener = urllib.request.build_opener(_NoRedirect)

    def check(self):
        require(time.monotonic() < self.deadline, "input transfer deadline exceeded")
        self.supervisor.admission("input-transfer", 3, 1)

    def api(self, suffix):
        self.check()
        request = urllib.request.Request("https://api.github.com/repos/" + REPOSITORY + suffix,
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "closed-default-export-qualification"})
        return self.opener.open(request, timeout=min(15, max(.1, self.deadline-time.monotonic())))

    def metadata(self, pin):
        rows = []
        try:
            for suffix in (f"/actions/runs/{pin.run_id}", f"/actions/jobs/{pin.job_id}",
                           f"/actions/artifacts/{pin.artifact_id}"):
                with self.api(suffix) as stream:
                    raw = stream.read(METADATA_LIMIT + 1)
                    require(len(raw) <= METADATA_LIMIT, "input metadata too large")
                self.check()
                rows.append(H.strict_json(raw))
        except (OSError, urllib.error.URLError):
            raise Refusal("input metadata transport refused") from None
        return validate_publication(pin, *rows, datetime.now(timezone.utc))

    def download(self, pin, path):
        try:
            try:
                response = self.api(f"/actions/artifacts/{pin.artifact_id}/zip")
            except urllib.error.HTTPError as exc:
                code, location = exc.code, exc.headers.get("Location", "")
                exc.close()
                require(code in (301, 302, 303, 307, 308), "artifact redirect refused")
                url = urllib.parse.urlsplit(location)
                require(url.scheme == "https" and not url.username and not url.password
                    and url.port in (None, 443) and (url.hostname or "").endswith(
                        (".blob.core.windows.net", ".actions.githubusercontent.com", ".githubusercontent.com")),
                    "artifact storage origin refused")
                # Signed location is used only here; it is never logged or serialized.
                response = self.opener.open(urllib.request.Request(location),
                    timeout=min(15, max(.1, self.deadline-time.monotonic())))
            with response as stream, path.open("xb") as out:
                size, digest = 0, hashlib.sha256()
                while True:
                    self.check()
                    block = stream.read(min(1024 * 1024, pin.size + 1 - size))
                    if not block:
                        break
                    size += len(block)
                    require(size <= pin.size, "input download exceeds registered size")
                    out.write(block); digest.update(block)
                out.flush(); os.fsync(out.fileno())
            require(size == pin.size and digest.hexdigest() == pin.sha256, "input download digest mismatch")
            path.chmod(0o444)
        except (OSError, urllib.error.URLError):
            raise Refusal("artifact transport refused") from None


def artifact_pins(reference):
    require(reference["source"] == "0900f3d203cc74102809bb871a1a057ba91a951f"
            and reference["input_run"] == 40865043984 and reference["input_job"] == 123417559998,
            "closed090 input producer")
    require(set(reference["artifacts"]) == {"12893517727", "12894166162"}, "closed artifact set")
    return [ArtifactPin(int(key), reference["input_run"], reference["input_job"], reference["source"],
                        row["name"], row["size_in_bytes"], row["digest"].removeprefix("sha256:"),
                        row["expires_at"], ".github/workflows/tests.yml")
            for key, row in sorted(reference["artifacts"].items())]


def verify_zip(stream, registered, *, expanded_limit, member_limit, keep=()):
    """CRC/EOF and exact registered content; no archive-driven filesystem paths."""
    retained, observed = {}, {}
    with zipfile.ZipFile(stream) as archive:
        entries = archive.infolist()
        require(len(entries) == len(registered) and len(entries) <= 16, "wheel ZIP entry set")
        require(sum(row.file_size for row in entries) <= expanded_limit, "wheel ZIP expansion")
        for row in entries:
            name = row.filename
            require(name == row.orig_filename and name in registered and name not in observed
                    and not row.is_dir() and not row.flag_bits & 1
                    and row.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "wheel ZIP member")
            require(stat.S_IFMT(row.external_attr >> 16) in (0, stat.S_IFREG), "wheel ZIP file type")
            expected = registered[name]
            require(type(row.file_size) is int and row.file_size == expected["bytes"]
                    and row.file_size <= member_limit, "wheel ZIP member bytes")
            size, hashed, pieces = 0, hashlib.sha256(), []
            with archive.open(row) as member:
                while block := member.read(1024 * 1024):
                    size += len(block)
                    require(size <= row.file_size, "wheel ZIP decoded bound")
                    hashed.update(block)
                    if name in keep: pieces.append(block)
            require(size == row.file_size and hashed.hexdigest() == expected["sha256"], "wheel ZIP content")
            observed[name] = {"bytes": size, "sha256": hashed.hexdigest()}
            if name in keep: retained[name] = b"".join(pieces)
        require(set(observed) == set(registered), "wheel ZIP missing member")
    return observed, retained


def stage_wheel(zip_path, output, reference):
    wheel_name = "chronicler-agents/target/wheels/" + reference["wheel"]["filename"]
    outer, keep = verify_zip(zip_path, reference["outer_wheel_members"], expanded_limit=8 * 1024**2,
                             member_limit=4 * 1024**2, keep=(wheel_name,))
    wheel = keep[wheel_name]
    require(len(wheel) == reference["wheel"]["bytes"]
            and hashlib.sha256(wheel).hexdigest() == reference["wheel"]["sha256"], "registered inner wheel")
    inner, _ = verify_zip(io.BytesIO(wheel), reference["wheel_members"], expanded_limit=32 * 1024**2,
                          member_limit=16 * 1024**2)
    require(not output.exists() and not output.is_symlink(), "fresh inner wheel path")
    with output.open("xb") as stream:
        stream.write(wheel); stream.flush(); os.fsync(stream.fileno())
    output.chmod(0o444)
    return {"outer": outer, "inner": inner, "wheel_sha256": reference["wheel"]["sha256"]}
