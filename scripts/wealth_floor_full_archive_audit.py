#!/usr/bin/env python3
"""Pending full-cohort byte audit: generic contracts, no publication grant.

The actual frontend refuses before credentials, input paths, clients or ZIP
allocation while any observed-output registration is NULL. Generic functions
accept explicit synthetic inputs for pure tests. They neither create a reviewed
plan nor qualify scientific outcomes. No archive/body is decoded or imported.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath
from types import MappingProxyType
import urllib.error
import urllib.parse
import urllib.request

import wealth_floor_baseline_admission as A

KERNEL_SHA256 = "9deced451f5edb3920c786a52c4d2a927cf9ae11af0ffb4e7450ff1d74fd0bed"
TRANSPORT_SOURCE = "7185f69c3d596aea96596e89a7dd5d0034f9a309"
TRANSPORT_SHA256 = "ee62d91dd3ba76e0751be50f75a69a8f300df2c3c4df240b5c1b385a13bd7326"
PRODUCER_SOURCE = "33d331a1838d86ba2b47ac222b8f4ede6ff598bc"
PRODUCER_RUN = 40860233409
PRODUCER_JOBS = MappingProxyType(dict(template=123401310479, procedural=123401310903))
API = "https://api.github.com/repos/YotsuBotfds/Chronicler"
USER_AGENT = "Chronicler-registered-full-byte-audit"
MAX_API = A.BLOCK_BYTES
MAX_METADATA = 128 * A.BLOCK_BYTES
MAX_OUTPUT = 192 * A.BLOCK_BYTES
# Exact qualified7185 five-input aggregate, a prospective per-job ceiling.
# An actual larger staging plan requires separate source/policy review.
MAX_STAGED = 2133433148
DISK_ADMISSION = 12 * 1024**3
RAM_ADMISSION = 2 * 1024**3
DISK_FLOOR = 3 * 1024**3
RAM_FLOOR = 1024**3
RESERVE = 8 * A.BLOCK_BYTES
WORLDGENS = frozenset(PRODUCER_JOBS)
FAMILIES = frozenset(("light", "raw", "contracts", "failure-metadata", "failed-checkpoints"))
REFUSAL_CODES = frozenset(("pending_publication", "contract_refused", "http_refused", "transport_failed"))

# Literal NULLs: actual outputs, complete outcomes and total-resource facts have
# not yet been observed/reviewed. Source-known producing IDs confer no authority.
REVIEWED_OUTPUTS = None
REVIEWED_CLOSURES = None
REVIEWED_OUTCOMES = None
REVIEWED_RESOURCE_POLICY = None
REVIEWED_COMPLETION = None


class Refused(ValueError):
    def __init__(self, code="contract_refused"):
        if code not in REFUSAL_CODES:
            raise ValueError("unregistered refusal code")
        self.code = code
        super().__init__(code)


def require(condition):
    if not condition:
        raise Refused()


def registration():
    """First actual entry point: no getenv, Path, client or ZIP calls precede it."""
    if any(value is None for value in (REVIEWED_OUTPUTS, REVIEWED_CLOSURES,
            REVIEWED_OUTCOMES, REVIEWED_RESOURCE_POLICY, REVIEWED_COMPLETION)):
        raise Refused("pending_publication")
    # Filling NULLs alone cannot enable execution: actual outcome/member schemas
    # and the terminal source/controller must be reviewed as a separate child.
    raise Refused("pending_publication")


@dataclass(frozen=True)
class InputPin:
    worldgen: str
    family: str
    artifact_id: int
    name: str
    size: int
    sha256: str
    expires_at: str

    def __post_init__(self):
        require(type(self.worldgen) is str and self.worldgen in WORLDGENS
            and type(self.family) is str and self.family in FAMILIES)
        require(type(self.artifact_id) is int and self.artifact_id > 0)
        require(self.name == f"wealth-outcome-full-{self.worldgen}-{self.family}-{PRODUCER_RUN}-1")
        require(type(self.size) is int and 0 < self.size <= A.MAX_COMPRESSED_BYTES)
        require(A.hash_shape(self.sha256))
        strict_utc(self.expires_at)


def strict_utc(value):
    require(type(value) is str and len(value) == 20 and value.endswith("Z"))
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise Refused() from None
    require(parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value)
    return parsed


def closed_inputs(pins):
    """All observed outputs must be supplied; no six-artifact assumption."""
    require(type(pins) is tuple and 6 <= len(pins) <= 10 and all(type(p) is InputPin for p in pins))
    require(len({p.artifact_id for p in pins}) == len(pins)
        and len({p.name for p in pins}) == len(pins)
        and len({(p.worldgen, p.family) for p in pins}) == len(pins))
    for world in WORLDGENS:
        require({"light", "raw", "contracts"} <= {p.family for p in pins if p.worldgen == world})
    return MappingProxyType({(p.worldgen, p.family): p for p in pins})


def staging_admission(*, available_disk, available_ram, staged_bytes, output_bytes):
    """Total planned staging/output, plus floor/reserve; not just the raw ZIP."""
    require(all(type(v) is int and v >= 0 for v in (available_disk, available_ram, staged_bytes, output_bytes)))
    require(0 < output_bytes <= MAX_OUTPUT and 0 < staged_bytes <= MAX_STAGED)
    require(available_disk >= DISK_ADMISSION and available_ram >= RAM_ADMISSION)
    require(available_disk >= staged_bytes + output_bytes + DISK_FLOOR + RESERVE)
    return dict(staged_bytes=staged_bytes, output_bytes=output_bytes,
        disk_floor_bytes=DISK_FLOOR, reserve_bytes=RESERVE, ram_admission_bytes=RAM_ADMISSION)


def explicit_members(rows):
    """Validate the entire expected archive before ZipFile can allocate its index."""
    require(type(rows) is dict and 0 < len(rows) <= A.MAX_ENTRIES)
    expected = {}
    for name, row in rows.items():
        A.canonical_name(name)
        require(type(row) is dict and set(row) == {"bytes", "sha256"})
        require(type(row["bytes"]) is int and row["bytes"] >= 0 and A.hash_shape(row["sha256"]))
        expected[name] = A.FilePin(row["bytes"], row["sha256"])
    require(sum(p.size for p in expected.values()) <= A.MAX_PAYLOAD_BYTES)
    prefixes = {str(parent) for name in expected for parent in PurePosixPath(name).parents if str(parent) != "."}
    require(not expected.keys() & prefixes)
    return MappingProxyType(expected)


def metadata_admission(expected, names, *, retained_bytes=0):
    """Only an exact future allowlist; no suffix selection or body decoding."""
    require(type(names) is frozenset and names and type(retained_bytes) is int and retained_bytes >= 0)
    require(names <= expected.keys())
    require(all(expected[name].size <= A.MAX_METADATA_BYTES for name in names))
    total = retained_bytes + sum(expected[name].size for name in names)
    require(total <= MAX_METADATA)
    return total


def normal_raw_members(inventory, authority_blobs, light_members):
    """Known O publication equation; failure side archives need explicit closure."""
    require(type(inventory) is dict and inventory.get("complete") is True)
    rows = inventory.get("files")
    expected = dict(explicit_members(rows))
    require(type(inventory.get("file_count")) is int and inventory["file_count"] == len(expected))
    require(type(inventory.get("total_bytes")) is int
        and inventory["total_bytes"] == sum(p.size for p in expected.values()))
    require(type(authority_blobs) is dict and set(authority_blobs) == {"result.json", "provenance.json", "raw-inventory.json"})
    require(all(type(raw) is bytes and len(raw) <= A.MAX_METADATA_BYTES for raw in authority_blobs.values()))
    decoded_inventory = A.parse_json(authority_blobs["raw-inventory.json"], A.Budget())
    require(A.json_bytes(decoded_inventory) == A.json_bytes(inventory))
    require(type(light_members) is dict and light_members)
    extras = {name: A.FilePin(len(raw), hashlib.sha256(raw).hexdigest()) for name, raw in authority_blobs.items()}
    for name, row in explicit_members(light_members).items():
        extras["light/" + name] = row
    require(not expected.keys() & extras.keys())
    expected.update(extras)
    # Check the WHOLE final archive after authorities/duplicates, not payload only.
    return explicit_members({name: dict(bytes=p.size, sha256=p.sha256) for name, p in expected.items()})


def audit_archive(path, expected, pin, budget):
    """Direct unchanged generic A kernel; no ARCHIVES/roles/validator mutation."""
    require(type(pin) is InputPin)
    checked = explicit_members({name: dict(bytes=p.size, sha256=p.sha256) for name, p in expected.items()})
    return A.audit_archive(path, checked, pin, budget)


def outcome_consistency(report, producer_conclusion):
    """Check claims only; exact source/native/CP/seal audit remains mandatory.

    These labels never mean qualification. Real completed-negative admission is
    deliberately absent until observed artifact/member/proof shapes are frozen.
    """
    require(type(report) is dict and producer_conclusion in ("success", "failure", "cancelled", "timed_out"))
    complete = report.get("execution_complete") is True and report.get("identities_stable") is True
    if not complete:
        require(report.get("qualified") is not True)
        return "incomplete_claim_no_qualification"
    passed, code = report.get("gate_pass"), report.get("gate_exit_code")
    require(type(passed) is bool and type(code) is int and code == (0 if passed else 2))
    require(type(report.get("qualified")) is bool and report["qualified"] is passed)
    require(producer_conclusion == ("success" if passed else "failure"))
    return "positive_claim_pending_evidence" if passed else "negative_science_claim_pending_evidence"


def endpoint(pin):
    return API + "/actions/artifacts/" + str(pin.artifact_id)


class ClosedRedirect(urllib.request.HTTPRedirectHandler):
    """7185 transport logic; new explicit immutable endpoints, no old INPUTS."""
    def __init__(self, selected, allowed):
        self.selected, self.allowed, self.followed = selected, allowed, False

    def http_error_302(self, request, response, code, message, headers):
        try:
            location = headers.get("location") or headers.get("Location")
            require(type(location) is str and 0 < len(location) <= 16 * 1024
                and all(33 <= ord(c) <= 126 for c in location))
            redirected = self.redirect_request(request, response, code, message, headers, location)
        finally:
            response.close()
        return self.parent.open(redirected, timeout=request.timeout)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    def redirect_request(self, request, response, code, message, headers, newurl):
        try:
            target = urllib.parse.urlsplit(newurl)
            allowed = (not self.followed and code == 302 and request.full_url == self.selected
                and self.selected in self.allowed and target.scheme == "https" and target.hostname is not None
                and target.hostname.endswith(".blob.core.windows.net") and target.port in (None, 443)
                and target.username is target.password is None and not target.fragment)
        except ValueError:
            allowed = False
        require(allowed)
        self.followed = True
        return urllib.request.Request(newurl, headers={"User-Agent": USER_AGENT}, method="GET")


def check_length(headers, maximum, *, exact=False):
    value = headers.get("Content-Length")
    require(value is None or type(value) is str and value.isascii() and value.isdecimal() and len(value) <= 20
        and (int(value) == maximum if exact else int(value) <= maximum))
    require(headers.get("Content-Encoding") in (None, "identity"))


def stream_download(response, pin, write, check):
    """Read one bounded buffered chunk; owned durable-file orchestration is pending."""
    require(type(pin) is InputPin and callable(getattr(response, "read1", None)))
    check_length(response.headers, pin.size, exact=True)
    digest, count = hashlib.sha256(), 0
    while True:
        check(); requested = min(A.BLOCK_BYTES, pin.size + 1 - count)
        raw = response.read1(requested)
        require(type(raw) is bytes and len(raw) <= requested)
        check()
        if not raw:
            break
        count += len(raw); require(count <= pin.size)
        digest.update(raw)
        require(write(raw) == len(raw))
        check()
    require(count == pin.size and digest.hexdigest() == pin.sha256)
    return dict(artifact_id=pin.artifact_id, bytes=count, sha256=digest.hexdigest())


class ClosedClient:
    def __init__(self, token, pins, budget, *, opener_factory=urllib.request.build_opener):
        self.inputs = closed_inputs(pins)
        require(type(token) is str and token and not any(c.isspace() for c in token))
        self.token, self.budget, self.opener_factory = token, budget, opener_factory
        self.zip_endpoints = frozenset(endpoint(p) + "/zip" for p in pins)
        self.metadata_endpoints = frozenset((API + f"/actions/runs/{PRODUCER_RUN}/attempts/1",
            API + f"/actions/runs/{PRODUCER_RUN}/attempts/1/jobs?per_page=100", *(endpoint(p) for p in pins)))

    @contextmanager
    def response(self, url, *, zip_input=False):
        require(url in (self.zip_endpoints if zip_input else self.metadata_endpoints))
        handler = ClosedRedirect(url if zip_input else "", self.zip_endpoints)
        opener = self.opener_factory(handler)
        request = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT})
        self.budget.check()
        try:
            with opener.open(request, timeout=15) as response:
                self.budget.check(); require(response.getcode() == 200)
                if zip_input:
                    target = urllib.parse.urlsplit(response.geturl())
                    require(handler.followed and target.scheme == "https" and target.hostname is not None
                        and target.hostname.endswith(".blob.core.windows.net"))
                else:
                    require(response.geturl() == url and not handler.followed and response.headers.get("Link") is None)
                yield response
                self.budget.check()
        except urllib.error.HTTPError as exc:
            exc.close(); raise Refused("http_refused") from None
        except (urllib.error.URLError, TimeoutError):
            raise Refused("transport_failed") from None

    def metadata(self, url):
        with self.response(url) as response:
            check_length(response.headers, MAX_API)
            require(callable(getattr(response, "read1", None)))
            chunks, count = [], 0
            while True:
                self.budget.check(); requested = min(A.BLOCK_BYTES, MAX_API + 1 - count)
                raw = response.read1(requested)
                require(type(raw) is bytes and len(raw) <= requested)
                self.budget.check()
                if not raw:
                    break
                count += len(raw); require(count <= MAX_API); chunks.append(raw)
        return A.parse_json(b"".join(chunks), self.budget)


def main():
    registration()
    # No credential/path/client/archive use exists in this pending source child.
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Refused as exc:
        print(json.dumps(dict(status="refused", reason=exc.code, archive_acquired=False,
            worlds_admitted=False, qualification=False), sort_keys=True))
        raise SystemExit(2)
