#!/usr/bin/env python3
"""Fetch one registered official artifact; verify bytes without loading native code.

There are no URL, artifact, digest, wheel or policy override arguments. This is
source for an inactive workflow; verification alone neither installs nor runs it.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
from pathlib import Path
import signal
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import research_natural_contract as C
from research_natural_runtime_policy import CLOUD_POLICY, policy

MAX_API = 64 * 1024
MAX_WHEEL_MEMBERS = 32
MAX_WHEEL_EXPANDED = 32 * 1024**2
DOWNLOAD_SECONDS = 120
API = "https://api.github.com/repos/"


class FetchFailure(C.ContractError):
    """Only closed stage/status/provider facts escape a transport exception."""
    def __init__(self, stage, status, provider):
        self.record = dict(stage=stage, http_status=status, provider_kind=provider)
        super().__init__(C.encoded(self.record).decode().strip())


def provider_kind(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme == "https" and parsed.hostname == "api.github.com":
            return "github_api"
        if parsed.scheme == "https" and parsed.hostname and parsed.hostname.endswith(".blob.core.windows.net"):
            return "azure_blob"
    except (TypeError, ValueError):
        pass
    return "unregistered"


def note(trace, stage, status, provider):
    if trace is not None:
        C.require(len(trace) < 8, "registered HTTP observation count exceeded")
        C.require(status is None or type(status) is int and 100 <= status <= 599, "invalid HTTP status observation")
        trace.append(dict(stage=stage, http_status=status, provider_kind=provider))


def endpoint():
    artifact = selected()["artifact"]
    return API + artifact["repository"] + "/actions/artifacts/" + str(artifact["id"])


def selected():
    return policy(CLOUD_POLICY)


def checked_source(source, expected):
    source = Path(source).resolve()
    C.require(C.git(source, "rev-parse", "HEAD").decode().strip() == expected["producer_sha"]
              and not C.git(source, "status", "--porcelain"), "wheel producer is not the clean registered source")
    artifact = expected["artifact"]
    actual = dict(root=str(source), git_sha=expected["producer_sha"],
        crate_tree=C.git(source, "rev-parse", "HEAD:chronicler-agents").decode().strip(),
        pyproject_sha256=C.sha(source / "pyproject.toml"), lock_sha256=C.sha(source / "uv.lock"))
    C.require(all(actual[k] == artifact[k] for k in ("crate_tree", "pyproject_sha256", "lock_sha256")),
              "producer crate/dependency inputs differ from the verified wheel")
    return actual


def metadata_contract(metadata, artifact):
    C.require(type(metadata) is dict, "official artifact metadata is not an object")
    expected = dict(id=artifact["id"], name=artifact["name"], size_in_bytes=artifact["bytes"],
        digest="sha256:" + artifact["sha256"], expired=False)
    C.require(all(C.same(metadata.get(k), v) for k, v in expected.items()), "official artifact id/name/digest/size/expiry differs")
    run = metadata.get("workflow_run")
    C.require(type(run) is dict and C.same(run.get("id"), artifact["run_id"])
              and run.get("head_sha") == artifact["control_sha"], "official artifact run/control differs")


def members(archive, *, maximum, expanded):
    rows, size = {}, 0
    C.require(len(archive.infolist()) <= maximum, "ZIP member count exceeds bound")
    for info in archive.infolist():
        name = C.relative(info.filename)
        mode = info.external_attr >> 16
        C.require(name not in rows and not info.is_dir() and not info.flag_bits & 1
                  and stat.S_IFMT(mode) in (0, stat.S_IFREG), "ZIP member is duplicate, encrypted, linked or special")
        C.require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "ZIP compression method differs")
        size += info.file_size
        C.require(0 <= info.file_size <= expanded and size <= expanded, "ZIP expansion exceeds bound")
        rows[name] = info
    return rows


def read_member(archive, info):
    with archive.open(info) as stream:
        value = stream.read(info.file_size + 1)
    C.require(len(value) == info.file_size, "ZIP member length differs")
    return value


def record(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def verify_archive(raw, expected):
    artifact = expected["artifact"]
    C.require(record(raw) == dict(bytes=artifact["bytes"], sha256=artifact["sha256"]), "artifact ZIP bytes differ")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        rows = members(archive, maximum=2, expanded=8 * 1024**2)
        C.require(set(rows) == {"build-manifest.json", artifact["wheel_path"]}, "artifact ZIP file set differs")
        manifest_raw = read_member(archive, rows["build-manifest.json"])
        wheel = read_member(archive, rows[artifact["wheel_path"]])
    C.require(record(manifest_raw) == dict(bytes=artifact["manifest_bytes"], sha256=artifact["manifest_sha256"]), "build manifest bytes differ")
    C.require(record(wheel) == dict(bytes=artifact["wheel_bytes"], sha256=artifact["wheel_sha256"]), "wheel bytes differ")
    manifest = C.loads(manifest_raw)
    for key, value in dict(schema_version=1, kind="chronicler-cloud-full-gate-build", qualified=True,
            control_sha=artifact["control_sha"], github_run_id=str(artifact["run_id"]), github_run_attempt="1",
            crate_tree=artifact["crate_tree"], pyproject_sha256=artifact["pyproject_sha256"],
            lock_sha256=artifact["lock_sha256"], python_version=artifact["python_version"]).items():
        C.require(C.same(manifest.get(key), value), "build manifest provenance differs: " + key)
    C.require(C.same(manifest["native"]["schemas"], C.checkpoint_projection(expected["schemas"]))
              and manifest["native"]["sha256"] == artifact["native_sha256"], "build native schema/digest differs")
    C.require(C.same(manifest["wheel"], dict(bytes=artifact["wheel_bytes"], filename=Path(artifact["wheel_path"]).name,
        native_member=artifact["native_member"], native_sha256=artifact["native_sha256"], sha256=artifact["wheel_sha256"])),
        "manifest wheel record differs")
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        rows = members(archive, maximum=MAX_WHEEL_MEMBERS, expanded=MAX_WHEEL_EXPANDED)
        C.require({n for n in rows if n.endswith((".so", ".pyd", ".dll", ".dylib"))} == {artifact["native_member"]}, "compiled wheel member set differs")
        # Read every member through ZIP CRC validation, without executing it.
        for name, info in rows.items():
            value = read_member(archive, info)
            if name == artifact["native_member"]:
                C.require(record(value) == dict(bytes=artifact["native_bytes"], sha256=artifact["native_sha256"]), "compiled member bytes differ")
    return manifest_raw, wheel


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    """Only the official artifact endpoint may redirect to Azure blob storage."""
    def __init__(self, trace=None):
        self.trace = trace

    def http_error_302(self, request, response, code, message, headers):
        # The generic urllib handler drains redirect bodies without a bound.
        # This protocol permits one absolute signed Location and never reads
        # a redirect/error body, including on validation failure.
        try:
            target = headers.get("location") or headers.get("Location")
            if not (type(target) is str and 0 < len(target) <= 16 * 1024 and
                    all(33 <= ord(char) <= 126 for char in target)):
                raise FetchFailure("redirect_validation", code, "unregistered")
            redirected = self.redirect_request(request, response, code, message, headers, target)
        finally:
            response.close()
        return self.parent.open(redirected, timeout=request.timeout)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    def redirect_request(self, request, response, code, message, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        origin_provider = provider_kind(request.full_url)
        origin_stage = "azure_redirect" if origin_provider == "azure_blob" else (
            "zip_get" if request.full_url == endpoint() + "/zip" else "metadata_get")
        note(self.trace, origin_stage, code, origin_provider)
        allowed = (request.full_url == endpoint() + "/zip"
                  and target.scheme == "https" and target.hostname is not None
                  and target.hostname.endswith(".blob.core.windows.net")
                  and target.port in (None, 443) and target.username is target.password is None and not target.fragment)
        if not allowed:
            raise FetchFailure("redirect_validation", code, "unregistered")
        safe = {k: v for k, v in request.header_items() if k.lower() not in ("authorization", "proxy-authorization", "cookie")}
        note(self.trace, "azure_redirect", None, "azure_blob")
        return urllib.request.Request(newurl, headers=safe, method="GET")


def fetch_bytes(opener, url, token, maximum, deadline, *, trace=None, stage="metadata_get"):
    C.require(url in (endpoint(), endpoint() + "/zip"), "unregistered artifact endpoint")
    C.require(time.monotonic() <= deadline, "registered wheel download wall budget crossed")
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Chronicler-fixed-research-wheel-verifier"})
    try:
        with opener.open(request, timeout=15) as response:
            if trace is not None:
                provider = provider_kind(response.geturl())
                note(trace, "azure_redirect" if provider == "azure_blob" else stage, response.getcode(), provider)
                C.require(provider in ("github_api", "azure_blob"), "unregistered response provider")
            length = response.headers.get("Content-Length")
            C.require(length is None or length.isdecimal() and int(length) <= maximum, "response length exceeds bound")
            chunks, count = [], 0
            while True:
                C.require(time.monotonic() <= deadline, "registered wheel download wall budget crossed")
                block = response.read(min(64 * 1024, maximum + 1 - count))
                if not block:
                    break
                count += len(block)
                C.require(count <= maximum, "response exceeds bound")
                chunks.append(block)
    except urllib.error.HTTPError as exc:
        provider = provider_kind(exc.url)
        safe_stage = "azure_redirect" if provider == "azure_blob" else stage
        status = exc.code if type(exc.code) is int and 100 <= exc.code <= 599 else None
        note(trace, safe_stage, status, provider)
        try:
            exc.close()  # Never read, print or retain a denied response body/headers.
        except Exception:
            pass
        raise FetchFailure(safe_stage, status, provider) from None
    except urllib.error.URLError:
        provider = "azure_blob" if trace and trace[-1]["stage"] == "azure_redirect" else "github_api"
        raise FetchFailure("azure_redirect" if provider == "azure_blob" else stage, None, provider) from None
    C.require(time.monotonic() <= deadline, "registered wheel download wall budget crossed")
    return b"".join(chunks)


def payloads(root, artifact, *, receipt_present=False):
    expected = {"build-manifest.json": dict(bytes=artifact["manifest_bytes"], sha256=artifact["manifest_sha256"]),
        Path(artifact["wheel_path"]).name: dict(bytes=artifact["wheel_bytes"], sha256=artifact["wheel_sha256"]),
        "official-artifact.zip": dict(bytes=artifact["bytes"], sha256=artifact["sha256"])}
    paths = list(Path(root).iterdir())
    C.require(len(paths) == len(expected) + int(receipt_present)
              and {p.name for p in paths} == set(expected) | ({"verification.json"} if receipt_present else set()),
              "wheel payload file set differs")
    for name, row in expected.items():
        path = Path(root) / name
        C.require(path.is_file() and not path.is_symlink() and path.stat().st_size == row["bytes"]
                  and C.sha(path) == row["sha256"], "wheel retained payload bytes differ")
    return expected


def verify_receipt(path, source_root):
    path = Path(path).resolve()
    C.require(path.name == "verification.json", "wheel verification receipt filename differs")
    receipt, expected = C.read(path, MAX_API), selected()
    C.closed(receipt, {"schema_version", "kind", "verified", "runtime_policy", "artifact", "schemas", "producer",
        "files", "native_imported", "wheel_installed"}, "wheel verification receipt")
    C.require(C.same(receipt["schema_version"], 1) and receipt["kind"] == "natural-research-wheel-verification"
              and receipt["verified"] is True and receipt["runtime_policy"] == CLOUD_POLICY
              and receipt["native_imported"] is False and receipt["wheel_installed"] is False,
              "wheel verification receipt verdict differs")
    C.require(C.same(receipt["artifact"], expected["artifact"]) and C.same(receipt["schemas"], expected["schemas"])
              and C.same(receipt["producer"], checked_source(source_root, expected)), "wheel verification policy/source differs")
    C.require(C.same(receipt["files"], payloads(path.parent, expected["artifact"], receipt_present=True)), "verified wheel payload linkage differs")
    raw = (path.parent / "official-artifact.zip").read_bytes()
    verify_archive(raw, expected)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--diagnostic", action="store_true", help="record only bounded registered HTTP stage/status/provider facts")
    args = parser.parse_args(argv)
    expected, root = selected(), Path(args.output_root).resolve()
    C.require(not root.exists() and not root.is_relative_to(Path(args.source_root).resolve())
              and not root.is_relative_to(Path(__file__).resolve().parents[1]), "fresh external wheel evidence root required")
    root.mkdir(parents=True)
    artifact, trace, stage, metadata_verified = expected["artifact"], [], "source_check", False
    report = dict(schema_version=1, kind="registered-wheel-http-diagnostic" if args.diagnostic else "registered-wheel-fetch-failure",
        artifact_id=artifact["id"], registered_run_id=artifact["run_id"],
        metadata_contract_verified=False, archive_verified=False, observations=trace,
        failure=None, native_imported=False, wheel_installed=False)
    C.require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "registered fetch requires an unleased wall timer")
    previous_handler = signal.getsignal(signal.SIGALRM)
    def expired(signum, frame):
        # An absolute timer also bounds a response which trickles bytes without
        # ever hitting its socket timeout. No response text escapes this path.
        raise FetchFailure(stage, None, "local_verifier")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, DOWNLOAD_SECONDS)
    try:
        try:
            producer = checked_source(args.source_root, expected)
            stage = "token_ready"
            token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
            C.require(type(token) is str and bool(token), "official artifact read token unavailable")
            deadline = time.monotonic() + DOWNLOAD_SECONDS
            opener = urllib.request.build_opener(OfficialRedirect(trace))
            stage = "metadata_get"
            metadata = C.loads(fetch_bytes(opener, endpoint(), token, MAX_API, deadline, trace=trace, stage=stage))
            stage = "metadata_contract"
            metadata_contract(metadata, artifact)
            metadata_verified = report["metadata_contract_verified"] = True
            stage = "zip_get"
            raw = fetch_bytes(opener, endpoint() + "/zip", token, artifact["bytes"], deadline, trace=trace, stage=stage)
            stage = "archive_verify"
            manifest, wheel = verify_archive(raw, expected)
            # Never retain an error body or unregistered downloaded content. Only
            # the exact verified official ZIP and its verified members are saved.
            (root / "official-artifact.zip").write_bytes(raw)
            (root / "build-manifest.json").write_bytes(manifest)
            (root / Path(artifact["wheel_path"]).name).write_bytes(wheel)
            stage = "source_recheck"
            C.require(C.same(producer, checked_source(args.source_root, expected)), "wheel source changed during verification")
            report["archive_verified"] = True
            stage = "publication"
            if args.diagnostic:
                C.write(root / "diagnostics.json", report)
            else:
                C.write(root / "verification.json", dict(schema_version=1, kind="natural-research-wheel-verification", verified=True,
                    runtime_policy=CLOUD_POLICY, artifact=artifact, schemas=expected["schemas"], producer=producer,
                    files=payloads(root, artifact), native_imported=False, wheel_installed=False))
            stage = "timer_finalization"
        finally:
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
            finally:
                signal.signal(signal.SIGALRM, previous_handler)
    except BaseException as exc:
        # Teardown is inside the failure transaction. Retry only local timer
        # release; never repeat a denied HTTP request or change its route.
        try:
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
            finally:
                signal.signal(signal.SIGALRM, previous_handler)
        except BaseException:
            pass
        positive = root / ("diagnostics.json" if args.diagnostic else "verification.json")
        if positive.exists():
            incomplete = root / ("incomplete-" + positive.name)
            C.require(not incomplete.exists(), "refusing to overwrite retained incomplete publication")
            os.replace(positive, incomplete)
        report["metadata_contract_verified"] = metadata_verified
        report["archive_verified"] = False
        report["failure"] = (exc.record if isinstance(exc, FetchFailure) else
            dict(stage=stage, http_status=None, provider_kind="local_verifier"))
        C.write(root / ("diagnostics.json" if args.diagnostic else "failure.json"), report)
        print(C.encoded(report["failure"]).decode().strip(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # HTTP failures can embed signed redirect URLs; do not print exception text.
        print("Registered wheel verification refused: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
