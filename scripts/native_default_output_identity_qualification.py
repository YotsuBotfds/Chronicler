#!/usr/bin/env python3
"""Dormant C76/95 default-export qualification using registered retained wheels.

The original 8bbc helper is immutable. This module changes only its shared-
binary orchestration; no simulation, comparator or matrix is copied/modified.
No command runs worlds unless ``run --execute`` is explicitly selected.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import sys
import sysconfig
import time
from types import MappingProxyType, ModuleType
import urllib.error
import urllib.parse
import urllib.request
import zipfile

SCRIPT = Path(__file__).resolve()
HELPER_SHA = "0d3a2c5db023a47a82307d3a9b789eebd979915e52be66e7208f0c93a94540f5"
HELPER_BYTES = 34186


def load_helper(path=SCRIPT.with_name("arc_output_identity_qualification.py")):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != HELPER_BYTES:
        raise RuntimeError("original helper identity refused")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != HELPER_SHA:
        raise RuntimeError("original helper bytes changed")
    # Execute the bytes just authenticated, never a reopened source or .pyc.
    module = ModuleType("_original_export_qualification")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


H = load_helper()
Refusal, require = H.Refusal, H.require
REPOSITORY = "YotsuBotfds/Chronicler"
REPOSITORY_ID = 1187468861
PYTHON = "3.13.17"
UV_VERSION = "0.13.6"
ACTIVE_BRANCH = "lead/cloud-native-default-output-identity-20261029"
WORKFLOW_PATH = ".github/workflows/native-default-output-identity.yml"
TEMPLATE_PATH = "docs/experiments/native-default-output-identity-workflow.yml"
JOB_KEY = "native-default-output-identity"
WORKFLOW_SHA = "273bbafe275b585c03a121c9f88ff81b9f7767aae21d85f4c3e1fbc89b9f434f"
WHEEL_NAME = "chronicler_agents-0.1.0-cp313-cp313-manylinux_2_34_x86_64.whl"
NATIVE_MEMBER = "chronicler_agents/chronicler_agents.cpython-313-x86_64-linux-gnu.so"
GIB = 1024 ** 3
MAX_MEMBER = 32 * 1024 ** 2
MAX_EXPANSION = 192 * 1024 ** 2
MAX_ENTRIES = 2048
METADATA_LIMIT = 2 * 1024 ** 2
TRANSFER_SECONDS = 120
PACKAGE_NAMES = ("arro3-core", "chronicler-agents", "numpy", "pyarrow", "pydantic", "scipy")
SOURCES = MappingProxyType({
    "baseline": "c76efe8552b4c6c288ebb1f813e2c0a58e5957b1",
    "candidate": "95f73a74f809d7e10f09a1241c98014864350ffb",
})
CRATES = MappingProxyType({
    "baseline": "a4703ef4e9a21b5dbb194d318536a46e6ca8b71c",
    "candidate": "912a1a2489f8f8c548df19302bb2c0a4365fc32e",
})


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


@dataclass(frozen=True)
class WheelPin:
    artifact: str
    member: str
    size: int
    sha256: str
    native_size: int
    native_sha256: str


ARTIFACTS = MappingProxyType({
    "old": ArtifactPin(12874494535, 40820753788, 123272420780,
        "3bf976cde1f0b4809945162395714e5aacccebdd", "wealth-native-raw-40820753788-1",
        9041361, "fe23a7da31d04d7dd751937ba5050e953fa6a6597b865148bc11b559270b2ff9",
        "2026-11-28T05:11:23Z", ".github/workflows/wealth-floor-native-build-bridge.yml"),
    "new": ArtifactPin(12875201593, 40821282241, 123274093114,
        SOURCES["candidate"], "native-wheel-" + SOURCES["candidate"], 3850596,
        "f411d352e1e537607e8eacfa6b3061f05cb45f3dc9149a347a2a60b4c6719c90",
        "2026-11-12T05:15:07Z", ".github/workflows/tests.yml"),
    "new-preflight": ArtifactPin(12874798572, 40821282241, 123274093114,
        SOURCES["candidate"], "python-native-" + SOURCES["candidate"], 140449,
        "eabba760178cb6157d7bfe35bf0f27c663be5ad24bec1f1e46071e6e74e35e8d",
        "2026-11-12T05:15:05Z", ".github/workflows/tests.yml"),
})
WHEELS = MappingProxyType({
    "baseline": WheelPin("old", "wheels/baseline/" + WHEEL_NAME, 3831429,
        "2e491456d01c2dd7bb2f7688e6acbc06b614610bbbe5be5ea6f0832ae220759a",
        13443872, "06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6"),
    "candidate": WheelPin("new", "chronicler-agents/target/wheels/" + WHEEL_NAME, 3915402,
        "b0896cd9a03ae89f26a93748fd85717c1f6110d2d45e2d623fb3406c3f24d64b",
        13695168, "3ee06a53b3c16dcba01bc53c8fe1dd97e530754a61d65fe2c1396b158b48e6d0"),
})
OLD_SEALS = MappingProxyType({
    "build-manifest.json": "dffb6aa2f07d89a23aad89a9988dd37f39f876cbff29c573838010cdbbb09169",
    "completion.json": "442f58798e655f241290baa0020456e26107193f7d2ec5696549f6599460ce59",
    "raw-inventory.json": "f9cdd8fddc3dcd8ae87815ff54d721e5dc7fa04fc3b7e15cba7b4e09842faf61",
    "light/index.json": "221b28e582a3ad366f36c3f9b430a8eb52ea2c46f9503f3f0346d1793c1e4e81",
})
SCHEMAS = {
    "AgentSimulator": {"version": 1, "fingerprint": "dcf0c34097c88451", "schema_sha256": "0b792f3ec33ac68605caf7b6d66fa7462c919b52e6f489f0e3dd7fa42f9fba3b"},
    "EcologySimulator": {"version": 1, "fingerprint": "4ab7f8c199b5e5f8", "schema_sha256": "bf7daf59c53773518770b90f5a5dee5b71e63d2a62d2af6c756922a07a503aff"},
    "PoliticsSimulator": {"version": 1, "fingerprint": "b1a710f3450f5015", "schema_sha256": "48e27b42f817e0057ad5f15bf2c2e8d8cca072314a9ca666753f2c9341c47395"},
}


def pin_bytes(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


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


def member_name(info, allow_directories):
    name = info.filename
    require(name == info.orig_filename and "\\" not in name and "\0" not in name
        and ":" not in name and not name.startswith("/"), "unsafe ZIP member")
    logical = name[:-1] if info.is_dir() else name
    path = PurePosixPath(logical)
    require(bool(logical) and path.as_posix() == logical
        and all(part not in ("", ".", "..") for part in logical.split("/")), "noncanonical ZIP member")
    kind = stat.S_IFMT(info.external_attr >> 16)
    require(not info.flag_bits & 1, "encrypted ZIP member")
    if info.is_dir():
        require(allow_directories and kind in (0, stat.S_IFDIR) and info.file_size == 0
            and info.CRC == 0 and info.compress_size <= 16, "invalid empty wheel directory")
    else:
        require(kind in (0, stat.S_IFREG), "nonregular ZIP member")
    return logical


def inspect_zip(stream, selected=(), *, allow_directories=False):
    pins, payloads, aliases = {}, {}, set()
    with zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        require(0 < len(infos) <= MAX_ENTRIES, "ZIP entry count refused")
        require(sum(row.file_size for row in infos) <= MAX_EXPANSION, "ZIP expansion refused")
        for info in infos:
            alias = member_name(info, allow_directories)
            require(alias not in aliases, "ZIP member alias")
            aliases.add(alias)
            require(0 <= info.file_size <= MAX_MEMBER and 0 <= info.compress_size <= MAX_MEMBER,
                    "ZIP member size refused")
            digest, size, chunks = hashlib.sha256(), 0, []
            with archive.open(info) as source:
                while True:
                    block = source.read(64 * 1024)
                    if not block:
                        break
                    size += len(block)
                    require(size <= MAX_MEMBER, "ZIP stream exceeds member cap")
                    digest.update(block)
                    if info.filename in selected:
                        chunks.append(block)
            require(size == info.file_size, "ZIP size/EOF mismatch")
            if not info.is_dir():
                pins[info.filename] = {"bytes": size, "sha256": digest.hexdigest()}
                if info.filename in selected:
                    payloads[info.filename] = b"".join(chunks)
    require(set(selected) <= payloads.keys(), "registered ZIP payload missing")
    return pins, payloads


def inspect_artifact(path, pin, selected):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size == pin.size
        and H.sha(path) == pin.sha256, "artifact refused before ZIP parsing")
    before = (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
    with path.open("rb") as stream:
        result = inspect_zip(stream, selected)
    require(before == (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
        and H.sha(path) == pin.sha256, "artifact changed during inspection")
    return result


def require_inventory(pins, inventory):
    require(type(inventory) is dict and all(type(n) is str and type(row) is dict
        and set(row) == {"bytes", "sha256"} and type(row["bytes"]) is int and row["bytes"] >= 0
        and type(row["sha256"]) is str and re.fullmatch("[0-9a-f]{64}", row["sha256"])
        for n, row in inventory.items()), "invalid sealed inventory")
    require(all(pins.get(name) == row for name, row in inventory.items()), "sealed inventory mismatch")


def validate_old(pins, payloads):
    require(len(pins) == 85 and all(pins.get(name, {}).get("sha256") == value
        for name, value in OLD_SEALS.items()), "old build publication seals changed")
    manifest = H.strict_json(payloads["build-manifest.json"])
    completion = H.strict_json(payloads["completion.json"])
    raw = H.strict_json(payloads["raw-inventory.json"])
    light = H.strict_json(payloads["light/index.json"])
    require_inventory(pins, raw["files"])
    require(exact_int(raw["file_count"], 66) and len(raw["files"]) == 66
        and raw["total_bytes"] == sum(row["bytes"] for row in raw["files"].values()), "old raw inventory incomplete")
    require_inventory(pins, {"light/" + name: row for name, row in light["files"].items()})
    expected = set(raw["files"]) | {"light/" + name for name in light["files"]} | set(OLD_SEALS)
    require(set(pins) == expected, "old raw/light publication member set changed")
    require(completion["publication_complete"] is True and completion["files"] ==
        {name: pins[name] for name in ("build-manifest.json", "raw-inventory.json", "light/index.json")},
        "old completion does not seal publication")
    require(manifest["baseline_source"] == "d0281e5f57c508f27cea1676f36e0e6ed1225c9d"
        and manifest["baseline_crate"] == CRATES["baseline"]
        and manifest["rebuilt_baseline_native_sha256"] == WHEELS["baseline"].native_sha256
        and manifest["historical_reuse_eligible"] is True and manifest["candidate_worlds_admitted"] is False,
        "old build source/native role changed")
    require(manifest["producer"] == {"control_sha": ARTIFACTS["old"].source,
        "job_key": "paired-native-build", "run_attempt": "1", "run_id": str(ARTIFACTS["old"].run_id)},
        "old manifest producer changed")
    for role in ("baseline", "candidate"):
        require(pins[role + "/source-before.json"] == pins[role + "/source-after.json"], "old source snapshots differ")
        phase = manifest["phases"][role]
        require(phase["build_complete"] is True and phase["cleanup_complete"] is True
            and phase["source_clean"] is True and phase["source_before_sha256"] == phase["source_after_sha256"]
            == pins[role + "/source-before.json"]["sha256"], "old build phase incomplete")
        phase_wheel = phase["wheel"]
        require(pins["wheels/" + role + "/" + phase_wheel["filename"]] ==
            {"bytes": phase_wheel["bytes"], "sha256": phase_wheel["sha256"]}, "old phase wheel not sealed by raw inventory")
    require(pins["source-control-before.json"] == pins["source-control-after.json"], "old controller snapshots differ")
    require(manifest["phases"]["baseline"]["probe"]["schemas"] == SCHEMAS, "old schema registration changed")
    wheel = WHEELS["baseline"]
    require(manifest["phases"]["baseline"]["wheel"] == {"filename": WHEEL_NAME, "bytes": wheel.size,
        "sha256": wheel.sha256, "native_member": NATIVE_MEMBER, "native_bytes": wheel.native_size,
        "native_sha256": wheel.native_sha256}, "old wheel manifest mismatch")
    old_probe = manifest["phases"]["baseline"]["probe"]
    require(old_probe["compiled_extension"] is True and old_probe["real_exported_classes"] is True
        and exact_int(old_probe["native_pools_created"], 0) and old_probe["source_imports"] == []
        and old_probe["native_sha256"] == wheel.native_sha256 and old_probe["python"] == PYTHON,
        "old compiled preflight incomplete")
    return {"build_source": manifest["baseline_source"], "world_source": SOURCES["baseline"],
            "qualification": "Retained baseline binary only; no wealth503 world or checkpoint grant."}


def validate_new(pins, payloads, preflight_pins, preflight_payloads):
    wheel = WHEELS["candidate"]
    require(set(pins) == {"ci-native-wheel/manifest.json", wheel.member}
        and set(preflight_pins) == {"native-identity.json", "native.xml"}, "new publication member set changed")
    manifest = H.strict_json(payloads["ci-native-wheel/manifest.json"])
    identity = H.strict_json(preflight_payloads["native-identity.json"])
    require(exact_int(manifest.get("schema_version"), 1)
        and manifest["source_commit"] == identity["source_commit"] == SOURCES["candidate"], "new wheel source mismatch")
    require(manifest["wheel"] == {"filename": WHEEL_NAME, "bytes": wheel.size,
        "sha256": wheel.sha256, "native_member": NATIVE_MEMBER}, "new wheel manifest mismatch")
    native = manifest["installed_native"]
    require(native["filename"] == Path(NATIVE_MEMBER).name and native["bytes"] == wheel.native_size
        and native["sha256"] == native["wheel_member_sha256"]
        == identity["sha256"] == wheel.native_sha256, "new installed preflight differs from wheel")
    require(identity["classes"] == manifest["classes"] == ["AgentSimulator", "EcologySimulator", "PoliticsSimulator"]
        and identity["python"] == manifest["python"] and identity["python"].startswith(PYTHON + " ")
        and identity["compiled_extension"].endswith(".so"), "new native preflight incomplete")
    return manifest


def validate_wheel(raw, wheel):
    require(pin_bytes(raw) == {"bytes": wheel.size, "sha256": wheel.sha256}, "wrong arm wheel")
    pins, _ = inspect_zip(io.BytesIO(raw), allow_directories=True)
    natives = {name for name in pins if name.endswith((".so", ".pyd", ".dylib"))}
    require(natives == {NATIVE_MEMBER} and pins[NATIVE_MEMBER] ==
        {"bytes": wheel.native_size, "sha256": wheel.native_sha256}, "wrong arm compiled member")
    return pins


def admit_inputs(root, supervisor, deadline):
    transport = Transport(os.environ.get("GITHUB_TOKEN"), supervisor, deadline)
    selected = {"old": set(OLD_SEALS) | {WHEELS["baseline"].member},
                "new": {"ci-native-wheel/manifest.json", WHEELS["candidate"].member},
                "new-preflight": {"native-identity.json"}}
    publications, contents, paths = {}, {}, {}
    for role, pin in ARTIFACTS.items():
        before = transport.metadata(pin)
        path = root / "inputs" / (str(pin.artifact_id) + ".zip")
        transport.download(pin, path)
        contents[role] = inspect_artifact(path, pin, selected[role])
        after = transport.metadata(pin)
        require(before["identity"] == after["identity"], "input producer/publication changed during transfer")
        publications[role] = {"before": before, "after": after}; paths[role] = path
    old = validate_old(*contents["old"])
    new = validate_new(*contents["new"], *contents["new-preflight"])
    result = {"publications": publications, "old_role": old, "new_manifest": new,
              "members": {role: value[0] for role, value in contents.items()}}
    for arm, wheel in WHEELS.items():
        raw = contents[wheel.artifact][1][wheel.member]
        result.setdefault("wheel_members", {})[arm] = validate_wheel(raw, wheel)
        path = root / "wheels" / arm / WHEEL_NAME
        with path.open("xb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        path.chmod(0o444)
    H.write(root / "input-admission.json", result)
    return paths


def case_rows():
    return [{"arm": arm, "case": name, "status": "not_attempted"}
            for arm in SOURCES for name in H.CASES]


def require_complete(rows):
    require([(row.get("arm"), row.get("case")) for row in rows] ==
        [(row["arm"], row["case"]) for row in case_rows()], "case rows or order changed")
    require(all(row.get("status") == "complete" and type(row.get("audit_sha256")) is str
        and re.fullmatch("[0-9a-f]{64}", row["audit_sha256"]) for row in rows), "not all registered cases complete")


def install_command(py, wheel, uv="uv"):
    return [uv, "pip", "install", "--no-deps", "--reinstall", "--python", py, str(wheel)]


def producer_context(env):
    require(env.get("GITHUB_REPOSITORY") == REPOSITORY and env.get("GITHUB_ACTIONS") == "true"
        and env.get("GITHUB_EVENT_NAME") == "push" and env.get("GITHUB_REF") == "refs/heads/" + ACTIVE_BRANCH
        and env.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/" + WORKFLOW_PATH + "@refs/heads/" + ACTIVE_BRANCH
        and env.get("GITHUB_JOB") == JOB_KEY and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and re.fullmatch("[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")) is not None
        and re.fullmatch("[0-9a-f]{40}", env.get("GITHUB_SHA", "")) is not None,
        "closed first-attempt push producer required")
    return {"control_sha": env["GITHUB_SHA"], "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": "1", "job_key": JOB_KEY, "workflow_ref": env["GITHUB_WORKFLOW_REF"],
        "event": "push", "branch": ACTIVE_BRANCH}


def workflow_contract(control):
    template, active = control / TEMPLATE_PATH, control / WORKFLOW_PATH
    require(not template.is_symlink() and not active.is_symlink()
        and H.sha(template) == WORKFLOW_SHA and active.read_bytes() == template.read_bytes(),
        "active workflow differs from reviewed dormant template")


ENVIRONMENT_PROBE = """import importlib.metadata as m, importlib.util as u, json, platform, sys
if platform.python_version() != '3.13.17' or platform.python_implementation() != 'CPython':
    raise RuntimeError('wrong dependency environment interpreter')
if u.find_spec('chronicler') is not None or u.find_spec('chronicler_agents') is not None:
    raise RuntimeError('project/native import available in fresh dependency environment')
for name in ('chronicler', 'chronicler-agents'):
    try: m.distribution(name)
    except m.PackageNotFoundError: pass
    else: raise RuntimeError('project/native distribution in fresh dependency environment')
print(json.dumps({'python': platform.python_version(), 'prefix': sys.prefix, 'project_or_native_installed': False}))
"""


def prepare_environment(root, sources, py, prefix, env, supervisor):
    require(not prefix.exists() and all(not prefix.is_relative_to(source) for source in
        sources.values()) and not root.is_relative_to(prefix)
        and not prefix.is_relative_to(root), "fresh external common prefix required")
    require(platform.python_version() == PYTHON and platform.python_implementation() == "CPython",
            "registered bootstrap interpreter required")
    supervisor.command("install-exact-uv", [sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "--no-cache-dir", "--only-binary=:all:", "uv==" + UV_VERSION], env, root)
    uv = Path(sysconfig.get_path("scripts")) / "uv"
    require(not uv.is_symlink() and uv.is_file(), "installed uv executable missing")
    uv_identity = {"path": str(uv.resolve()), "bytes": uv.stat().st_size, "sha256": H.sha(uv)}
    supervisor.command("uv-version", [uv_identity["path"], "--version"], env, root)
    with (root / "logs/uv-version.log").open("rb") as stream:
        version = stream.read(4097)
    require(len(version) <= 4096 and re.fullmatch(rb"uv 0\.13\.6(?: \([^\r\n]*\))?\r?\n?", version),
            "actual uv installer version differs")
    prepared_env = dict(env, UV_PROJECT_ENVIRONMENT=str(prefix))
    supervisor.command("locked-input-check", [uv_identity["path"], "lock", "--project", str(sources["candidate"]), "--check"], prepared_env, root)
    supervisor.command("fresh-locked-environment", [uv_identity["path"], "sync", "--project", str(sources["candidate"]),
        "--frozen", "--no-dev", "--no-install-project", "--no-build", "--python", sys.executable], prepared_env, root)
    require(Path(py) == prefix / "bin/python" and Path(py).is_file(), "wrong prepared interpreter path")
    supervisor.command("fresh-environment-probe", [py, "-I", "-B", "-c", ENVIRONMENT_PROBE], prepared_env, root)
    with (root / "logs/fresh-environment-probe.log").open("rb") as stream:
        probe_raw = stream.read(4097)
    require(len(probe_raw) <= 4096, "fresh environment probe exceeded bound")
    observation = H.strict_json(probe_raw)
    require(observation == {"python": PYTHON, "prefix": str(prefix), "project_or_native_installed": False},
            "fresh dependency environment identity differs")
    supervisor.admission("environment-prepared", 6, 2)
    require(H.sha(uv) == uv_identity["sha256"], "installer changed during preparation")
    result = {"uv": uv_identity, "version": version.decode().strip(), "environment": observation,
              "bootstrap_python": sys.executable, "bootstrap_version": sys.version}
    H.write(root / "environment-preparation.json", result)
    return result


def runtime_seal():
    keys = tuple(H.CAPS) + ("PYTHONHASHSEED", "OPENBLAS_THREAD_TIMEOUT")
    return {"python": platform.python_version(), "version": sys.version,
        "implementation": platform.python_implementation(), "platform": platform.platform(), "machine": platform.machine(),
        "executable": str(Path(sys.executable).resolve()), "prefix": str(Path(sys.prefix).resolve()),
        "affinity": sorted(os.sched_getaffinity(0)), "cpu_count": os.cpu_count(),
        "process_cpu_count": os.process_cpu_count(), "optimize": sys.flags.optimize,
        "no_user_site": sys.flags.no_user_site, "dont_write_bytecode": sys.dont_write_bytecode,
        "thread_env": {key: os.environ.get(key) for key in keys},
        "packages": {name: importlib.metadata.version(name) for name in PACKAGE_NAMES}}


def probe(args):
    require(args.expected_sha == SOURCES[args.arm], "unregistered probe source")
    H.probe(args)
    value = H.strict_json(Path(args.out).read_bytes())
    value["runtime"] = runtime_seal()
    H.write(args.out, value)


def validate_probe(value, arm, source, prefix, runtime=None):
    wheel = WHEELS[arm]
    require(value["source"]["git_sha"] == SOURCES[arm]
        and Path(value["source"]["package_dir"]).resolve() == source / "src/chronicler"
        and Path(value["source_file"]).resolve() == source / "src/chronicler/__init__.py", "wrong own-source import")
    require(Path(value["prefix"]).resolve() == prefix
        and Path(value["native_file"]).resolve().is_relative_to(prefix), "wrong compiled environment")
    require(value["native"]["sha256"] == wheel.native_sha256 and value["native"]["bytes"] == wheel.native_size
        and value["schemas"] == SCHEMAS, "loaded arm native/schema mismatch")
    actual = value["runtime"]
    require(actual["python"] == PYTHON and actual["implementation"] == "CPython"
        and type(actual["version"]) is str and actual["version"].startswith(PYTHON + " ")
        and actual["machine"] == "x86_64" and len(actual["affinity"]) == 1
        and type(actual["affinity"][0]) is int and actual["affinity"][0] >= 0
        and actual["affinity"] == value["affinity"] and exact_int(actual["cpu_count"], 1)
        and exact_int(actual["process_cpu_count"], 1),
        "actual runtime CPU/interpreter mismatch")
    require(actual["prefix"] == str(prefix) and exact_int(actual["optimize"], 0)
        and exact_int(actual["no_user_site"], 1) and actual["dont_write_bytecode"] is True
        and actual["thread_env"] == {**H.CAPS, "PYTHONHASHSEED": "0", "OPENBLAS_THREAD_TIMEOUT": "16"},
        "actual runtime policy changed")
    require(type(actual["packages"]) is dict and set(actual["packages"]) == set(PACKAGE_NAMES)
        and all(type(value) is str and value for value in actual["packages"].values()), "runtime package record incomplete")
    require(runtime is None or runtime == actual, "actual old/new runtime differs")
    return actual


def run_cases(root, roots, py, prefix, env, supervisor, report):
    runtime, package_digests, current_arm = None, {}, None
    native_copies = {}
    for row in report["cases"]:
        arm, name = row["arm"], row["case"]
        source, wheel = roots[arm], WHEELS[arm]
        if arm != current_arm:
            wheel_path = root / "wheels" / arm / WHEEL_NAME
            require(H.sha(wheel_path) == wheel.sha256, "arm wheel changed before installation")
            installer = report["installer"]["uv"]
            require(H.sha(installer["path"]) == installer["sha256"], "selected installer changed")
            supervisor.command("install-" + arm, install_command(py, wheel_path, installer["path"]), env, root)
            supervisor.admission("prepared-" + arm, 6, 2)
            current_arm = arm
        arm_root = root / "raw" / arm
        arm_root.mkdir(exist_ok=True)
        child_env = dict(env, PYTHONPATH=str(source / "src"))
        for stage in ("before", "after"):
            output = root / "probes" / (arm + "-" + name + "-" + stage + ".json")
            supervisor.command("probe-" + arm + "-" + name + "-" + stage,
                [py, str(SCRIPT), "probe", "--arm", arm, "--source-root", str(source),
                 "--expected-sha", SOURCES[arm], "--venv", str(prefix), "--out", str(output)], child_env, arm_root)
            identity = H.strict_json(output.read_bytes())
            runtime = validate_probe(identity, arm, source, prefix, runtime)
            report.update(installed_native_path=identity["native_file"], installed_native_arm=arm)
            digest = identity["source"]["package_digest"]
            require(package_digests.setdefault(arm, digest) == digest, "running source digest changed")
            if arm not in native_copies:
                copy = root / "native" / arm / Path(identity["native_file"]).name
                shutil.copyfile(identity["native_file"], copy)
                require(H.sha(copy) == wheel.native_sha256, "retained native copy mismatch")
                copy.chmod(0o444); native_copies[arm] = copy
            if stage == "before":
                row["status"] = "started"
                supervisor.command("world-" + arm + "-" + name,
                    [py, str(source / "scripts/turn_speed_identity.py"), "run", str(arm_root),
                     "--source-root", str(source), "--case", name], child_env, arm_root)
                which = (arm_root / "which.txt").read_text()
                require(which == "chronicler " + identity["source_file"] + "\nnative "
                    + identity["native_file"] + " " + wheel.native_sha256 + "\n", "driver source/native differs")
                (root / "probes" / (arm + "-" + name + "-which.txt")).write_text(which)
        audit = root / "audits" / (arm + "-" + name + ".json")
        supervisor.command("audit-" + arm + "-" + name,
            [py, str(H.SCRIPT), "inspect", "--case-root", str(arm_root / name),
             "--case", name, "--out", str(audit)], child_env, arm_root)
        row.update(status="complete", audit_sha256=H.sha(audit))
        supervisor.event("case_complete", arm=arm, case=name, audit_sha256=row["audit_sha256"])
    require_complete(report["cases"])
    H.require_case_sets(*[{path.name for path in (root / "raw" / arm).iterdir() if path.is_dir()} for arm in SOURCES])
    supervisor.command("compare", [py, str(roots["candidate"] / "scripts/turn_speed_identity.py"),
        "compare", str(root / "raw/baseline"), str(root / "raw/candidate")],
        dict(env, PYTHONPATH=str(roots["candidate"] / "src")), root)
    report.update(runtime=runtime, package_digests=package_digests)
    return native_copies


def finish_report(root, report, quiescent, deadline):
    H.finish_evidence(root, report, quiescent, deadline)
    if not report["qualified"] and report["status"] != "refused":
        report["status"] = "refused"
        H.write(root / "result.json", report)  # Negative only; never promotes a late result.


def execute(args):
    require(getattr(args, "execute", False) is True, "inactive: explicit --execute required")
    producer = producer_context(os.environ)
    control = producer["control_sha"]
    require(not [key for key in os.environ if key.startswith("GIT_") and key != "GIT_PAGER"], "ambient Git override refused")
    require(not [key for key in os.environ if key.startswith("CHRONICLER_") and key != "CHRONICLER_QUIET"],
            "unexpected simulation environment switch")
    root = Path(args.evidence).resolve()
    roots = {"baseline": Path(args.baseline_root).resolve(), "candidate": Path(args.candidate_root).resolve(), "control": SCRIPT.parents[1]}
    require(len(set(roots.values())) == 3 and all(not root.is_relative_to(source) for source in roots.values()), "external distinct roots required")
    root.mkdir(parents=True, exist_ok=False)
    for folder in ("logs", "probes", "audits", "raw", "inputs", "wheels", "native"):
        (root / folder).mkdir()
    for arm in SOURCES:
        (root / "wheels" / arm).mkdir(); (root / "native" / arm).mkdir()
    deadline = time.monotonic() + H.WALL_SECONDS
    supervisor = H.Supervisor(root, deadline)
    env = dict(os.environ, **H.CAPS, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1", PYTHONOPTIMIZE="0", OPENBLAS_THREAD_TIMEOUT="16", CHRONICLER_QUIET="1")
    for key in ("GITHUB_TOKEN", "GH_TOKEN", "PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    for key in tuple(env):
        if key.startswith(("PIP_", "UV_")) or key == "VIRTUAL_ENV": env.pop(key)
    env["PIP_CONFIG_FILE"] = os.devnull
    expected = {**SOURCES, "control": control}
    report = {"qualified": False, "status": "pending", "baseline": SOURCES["baseline"], "candidate": SOURCES["candidate"],
        "control": control, "producer": producer, "cases": case_rows(), "normalization": "metadata.generated_at only; original .log/run_manifest exclusions",
        "native_sha256_by_arm": {arm: pin.native_sha256 for arm, pin in WHEELS.items()},
        "wheel_sha256_by_arm": {arm: pin.sha256 for arm, pin in WHEELS.items()},
        "limitations": ["exports only; no checkpoint/RNG or broad science qualification", "no CPU/wall/RSS performance claim",
                        "controller success requires separate completed-producer/publication attestation"]}
    before, input_paths, native_copies = {}, {}, {}
    py = str(Path(args.python).absolute()); prefix = Path(py).parent.parent.resolve()
    try:
        allowed = os.sched_getaffinity(0); os.sched_setaffinity(0, {min(allowed)})
        supervisor.admission("initial", 12, 2)
        before = {name: H.source_snapshot(source, expected[name], deadline) for name, source in roots.items()}
        workflow_contract(roots["control"])
        require(all(before[arm]["crate_tree"] == CRATES[arm] for arm in SOURCES), "wrong registered crate tree")
        for relative in ("uv.lock", "pyproject.toml", "scripts/turn_speed_identity.py", "scripts/cities_identity.py", "src/chronicler/bundle_codec.py"):
            require(H.sha(roots["baseline"] / relative) == H.sha(roots["candidate"] / relative), "shared input differs: " + relative)
        for arm in SOURCES:
            H.require_matrix(roots[arm] / "scripts/turn_speed_identity.py")
        H.write(root / "freeze.json", {"sources": before, "matrix": H.CASES, "helper_sha256": H.sha(H.SCRIPT),
            "adapter_sha256": H.sha(SCRIPT), "thread_caps": H.CAPS, "affinity": sorted(os.sched_getaffinity(0))})
        report["installer"] = prepare_environment(root, roots, py, prefix, env, supervisor)
        input_paths = admit_inputs(root, supervisor, deadline)
        supervisor.admission("inputs-prepared", 6, 2)
        native_copies = run_cases(root, roots, py, prefix, env, supervisor, report)
        require_complete(report["cases"])
        report.update(qualified=True, status="exports_complete_pending_completed_job")
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)[:2048]
    finally:
        try:
            require(supervisor.cleanup_complete, "cleanup unverified; final inventories withheld")
            after = {name: H.source_snapshot(source, expected[name], deadline) for name, source in roots.items()}
            H.write(root / "sources-after.json", after)
            require(before == after, "source standing or tracked bytes/modes changed")
            for role, path in input_paths.items():
                require(H.sha(path) == ARTIFACTS[role].sha256, "input artifact changed")
            for arm, wheel in WHEELS.items():
                require(H.sha(root / "wheels" / arm / WHEEL_NAME) == wheel.sha256, "retained arm wheel changed")
            for arm, copy in native_copies.items():
                require(H.sha(copy) == WHEELS[arm].native_sha256, "retained arm native changed")
            if "installer" in report:
                require(H.sha(report["installer"]["uv"]["path"]) == report["installer"]["uv"]["sha256"],
                        "selected installer changed after execution")
            if "installed_native_path" in report:
                require(H.sha(report["installed_native_path"]) == WHEELS[report["installed_native_arm"]].native_sha256,
                        "last installed native changed after final probe")
            for row in report["cases"]:
                if row["status"] == "complete":
                    audit = root / "audits" / (row["arm"] + "-" + row["case"] + ".json")
                    require(H.sha(audit) == row["audit_sha256"], "case audit changed")
                    require(H.payload_inventory(root / "raw" / row["arm"] / row["case"]) ==
                            H.strict_json(audit.read_bytes())["files"], "raw exports changed after audit")
            require(time.monotonic() <= deadline, "aggregate wall budget exceeded")
        except Exception as exc:
            report.update(qualified=False, final_identity_error=type(exc).__name__ + ": " + str(exc)[:2048])
        for row in report["cases"]:
            if row["status"] == "started": row["status"] = "failed"
        if not report["qualified"]: report["status"] = "refused"
        finish_report(root, report, supervisor.cleanup_complete, deadline)
    print(json.dumps({key: report.get(key) for key in ("qualified", "status", "baseline", "candidate", "control",
        "error", "final_identity_error", "inventory_error", "inventory_sha256", "elapsed_wall_seconds")}, allow_nan=False))
    return 0 if report["qualified"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("describe")
    run = commands.add_parser("run")
    run.add_argument("--execute", action="store_true")
    for name in ("baseline-root", "candidate-root", "python", "evidence"):
        run.add_argument("--" + name, required=True)
    p = commands.add_parser("probe")
    p.add_argument("--arm", choices=tuple(SOURCES), required=True)
    for name in ("source-root", "expected-sha", "venv", "out"):
        p.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    if args.command == "probe": probe(args); return 0
    if args.command == "run": return execute(args)
    print(json.dumps({"status": "inactive", "execution_enabled_by_default": False, "sources": dict(SOURCES),
        "worlds": len(case_rows()), "physics_ticks": 2 * sum(int(cli[cli.index("--turns") + 1]) for cli, _ in H.CASES.values()),
        "helper_sha256": HELPER_SHA, "qualification": "No worlds, build, download or native probe performed."}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
