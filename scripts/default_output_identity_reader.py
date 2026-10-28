#!/usr/bin/env python3
"""Reinspect one pinned, completed export-parity artifact without new worlds."""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

# Protect all subsequently imported frozen source checkouts, including local CLI use.
sys.dont_write_bytecode = True

CONTROL = "db7ec48b738fa841f1b951c3ae810aa121ef1918"
BASELINE = "2f9d618b70f3304c02dcaeef12996b4a99e074c0"
CANDIDATE = "d0281e5f57c508f27cea1676f36e0e6ed1225c9d"
ARTIFACT_ID = 12859762876
RUN_ID = 40786065030
ARCHIVE_BYTES = 54788314
ARCHIVE_SHA = "025f4c215b1a2e3a556af45dc9d099c9f14343d0ba50ba9c896d8e92be37e8ff"
INVENTORY_SHA = "a25a2148d0259bfcc53acb74d5a29acb1e173c3e1a8f105c825c777cc99819cb"
WHEEL_SHA = "ef15138971a6c0597987aebb4070d47f6940ea5ab0659e552f907a30d046057a"
NATIVE_SHA = "06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6"
MEMBER_LIMIT = 256 * 1024**2
TOTAL_LIMIT = 4 * 1024**3
FILE_LIMIT = 4096
JSON_LIMIT = 32 * 1024**2
COMPARE_LIMIT = 2 * 1024**2
NORMALIZATION = "metadata.generated_at only; logs/run_manifest.json excluded by existing comparator"
SHA_PATTERN = re.compile(r"[0-9a-f]{64}")
API_URL = f"https://api.github.com/repos/YotsuBotfds/Chronicler/actions/artifacts/{ARTIFACT_ID}/zip"


class Refusal(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refusal(message)


def digest(path, limit=MEMBER_LIMIT):
    size = 0
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(min(1024**2, limit - size + 1)):
            size += len(block)
            require(size <= limit, "file exceeds byte limit")
            result.update(block)
    return {"bytes": size, "sha256": result.hexdigest()}


def strict_json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def number(token):
        value = float(token)
        require(math.isfinite(value), "nonfinite JSON number")
        return value

    def constant(token):
        raise Refusal("nonfinite JSON constant")
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def read_json(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(JSON_LIMIT + 1)
    require(len(raw) <= JSON_LIMIT, "JSON exceeds byte limit")
    return strict_json(raw)


def relative_name(name):
    require(type(name) is str and 0 < len(name) <= 512, "invalid archive or inventory path")
    require("\x00" not in name and "\\" not in name and ":" not in name,
            "unsafe archive or inventory path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(part not in ("", ".", "..") for part in name.split("/")),
            "unsafe archive or inventory path")
    require(path.as_posix() == name, "noncanonical archive or inventory path")
    return name


def archive_members(archive):
    rows = archive.infolist()
    require(len(rows) <= FILE_LIMIT * 2, "archive entry limit exceeded")
    files, directories, folded = {}, set(), set()
    total = 0
    for item in rows:
        require(item.orig_filename == item.filename, "archive name was truncated or normalized")
        directory = item.is_dir()
        name = relative_name(item.filename[:-1] if directory else item.filename)
        require(name.casefold() not in folded, "duplicate or case-aliased archive entry")
        folded.add(name.casefold())
        require(not item.flag_bits & 1, "encrypted archive member")
        require(item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                "unsupported archive compression")
        kind = stat.S_IFMT(item.external_attr >> 16)
        require(kind in ((0, stat.S_IFDIR) if directory else (0, stat.S_IFREG)),
                "nonregular archive member")
        if directory:
            require(item.file_size == 0, "nonempty archive directory")
            directories.add(name)
            continue
        require(0 <= item.file_size <= MEMBER_LIMIT, "archive member exceeds byte limit")
        files[name] = item
        total += item.file_size
        require(total <= TOTAL_LIMIT and len(files) <= FILE_LIMIT, "archive payload limit exceeded")
    require(files, "empty archive")
    prefix_spellings = {}
    file_names = {name.casefold() for name in files}
    for name in set(files) | directories:
        for prefix in (PurePosixPath(name), *PurePosixPath(name).parents):
            if prefix != PurePosixPath("."):
                spelling = prefix.as_posix()
                require(prefix_spellings.setdefault(spelling.casefold(), spelling) == spelling,
                        "case-aliased archive directory")
                require(len(prefix_spellings) <= FILE_LIMIT * 2, "archive directory limit exceeded")
        for parent in PurePosixPath(name).parents:
            if parent != PurePosixPath("."):
                require(parent.as_posix().casefold() not in file_names, "archive file/directory collision")
    return files


def extract_archive(path, destination):
    require(not Path(path).is_symlink() and Path(path).is_file(), "archive must be a regular file")
    require(digest(path, ARCHIVE_BYTES) == {"bytes": ARCHIVE_BYTES, "sha256": ARCHIVE_SHA},
            "outer artifact digest or size differs")
    with zipfile.ZipFile(path) as archive:
        files = archive_members(archive)
        destination.mkdir(parents=False, exist_ok=False)
        total = 0
        for name, item in files.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with archive.open(item) as source, target.open("xb") as output:
                while block := source.read(min(1024**2, item.file_size - written + 1)):
                    written += len(block)
                    total += len(block)
                    require(written <= item.file_size and total <= TOTAL_LIMIT,
                            "archive stream exceeds declared bounds")
                    output.write(block)
            require(written == item.file_size, "archive member is incomplete")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def _public_location(location):
    parsed = urlsplit(location or "")
    host = (parsed.hostname or "").lower()
    require(parsed.scheme == "https" and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443), "unsafe artifact redirect")
    require(host.endswith(".blob.core.windows.net") or host.endswith(".githubusercontent.com"),
            "unsupported artifact download host")
    return location


def download_archive(destination, token):
    require(type(token) is str and bool(token), "GitHub Actions read token is required")
    opener = build_opener(NoRedirect)
    request = Request(API_URL, headers={"Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        try:
            with opener.open(request, timeout=30):
                raise Refusal("artifact API did not redirect")
        except HTTPError as error:
            try:
                require(error.code == 302, "artifact API download refused")
                location = _public_location(error.headers.get("Location"))
            finally:
                error.close()
        # A distinct request, with no Authorization, is created for every public hop.
        for _ in range(3):
            try:
                response = opener.open(Request(location), timeout=60)
                break
            except HTTPError as error:
                try:
                    require(error.code in (301, 302, 303, 307, 308), "artifact storage download refused")
                    location = _public_location(error.headers.get("Location"))
                finally:
                    error.close()
        else:
            raise Refusal("too many artifact redirects")
        with response, destination.open("xb") as output:
            size, hasher = 0, hashlib.sha256()
            while block := response.read(min(1024**2, ARCHIVE_BYTES - size + 1)):
                size += len(block)
                require(size <= ARCHIVE_BYTES, "download exceeds pinned artifact size")
                hasher.update(block)
                output.write(block)
        require(size == ARCHIVE_BYTES and hasher.hexdigest() == ARCHIVE_SHA,
                "downloaded artifact digest or size differs")
    except Refusal:
        raise
    except Exception:
        # Network exceptions can contain signed URLs. Never serialize their messages.
        raise Refusal("artifact download failed") from None


def payload_inventory(root):
    rows, total = {}, 0
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "symlink in extracted payload")
        if path.is_dir():
            continue
        require(stat.S_ISREG(path.stat().st_mode), "nonregular extracted payload")
        name = relative_name(path.relative_to(root).as_posix())
        rows[name] = digest(path)
        total += rows[name]["bytes"]
        require(len(rows) <= FILE_LIMIT and total <= TOTAL_LIMIT, "extracted payload exceeds bounds")
    return rows


def validate_file_map(value):
    require(type(value) is dict and len(value) <= FILE_LIMIT, "invalid file inventory")
    folded = set()
    for name, record in value.items():
        relative_name(name)
        require(name.casefold() not in folded, "case-aliased inventory paths")
        folded.add(name.casefold())
        require(type(record) is dict and set(record) == {"bytes", "sha256"}, "invalid inventory record")
        require(type(record["bytes"]) is int and 0 <= record["bytes"] <= MEMBER_LIMIT,
                "invalid inventory byte count")
        require(type(record["sha256"]) is str and SHA_PATTERN.fullmatch(record["sha256"]),
                "invalid inventory digest")
    return value


def verify_inventory(root):
    require(digest(root / "inventory.json")["sha256"] == INVENTORY_SHA, "inventory pin differs")
    expected = validate_file_map(read_json(root / "inventory.json"))
    require(not {"inventory.json", "result.json"} & set(expected), "inventory includes excluded self-reference")
    actual = payload_inventory(root)
    require({"inventory.json", "result.json"} <= set(actual), "required receipt is missing")
    observed = {name: row for name, row in actual.items() if name not in ("inventory.json", "result.json")}
    require(observed == expected, "payload file set, size or digest differs from pinned inventory")
    return actual


def validate_result(result, cases):
    require(type(result) is dict and result.get("qualified") is True, "original result is not qualified")
    for key, expected in (("baseline", BASELINE), ("candidate", CANDIDATE),
                          ("inventory_sha256", INVENTORY_SHA), ("wheel_sha256", WHEEL_SHA),
                          ("native_sha256", NATIVE_SHA), ("normalization", NORMALIZATION)):
        require(result.get(key) == expected, "original result identity or normalization differs")
    require(not any(key in result for key in ("error", "final_identity_error", "inventory_error")),
            "original result retains an execution error")
    rows = result.get("cases")
    require(type(rows) is list and len(rows) == len(cases) * 2, "original case count differs")
    expected = {(arm, case) for arm in ("baseline", "candidate") for case in cases}
    seen = set()
    for row in rows:
        require(type(row) is dict, "invalid original case row")
        require(type(row.get("arm")) is str and type(row.get("case")) is str, "invalid original case identity")
        identity = (row.get("arm"), row.get("case"))
        require(identity in expected and identity not in seen, "missing, duplicate or extra original case")
        seen.add(identity)
        require(row.get("status") == "complete", "original case is incomplete")
        require(type(row.get("audit_sha256")) is str and SHA_PATTERN.fullmatch(row["audit_sha256"]),
                "original case audit pin is missing")
    require(seen == expected, "original case set differs")
    return rows


def verify_case_file_map(inventory, files, arm, case):
    files = validate_file_map(files)
    prefix = f"raw/{arm}/{case}/"
    actual = {name[len(prefix):]: row for name, row in inventory.items() if name.startswith(prefix)}
    require(actual == files and bool(files), "raw case file set, size or digest differs from audit")
    return files


def parse_comparison(text, expected_counts):
    lines = text.splitlines()
    names = sorted(expected_counts)
    require(len(lines) == len(names) + 1, "comparison did not emit exactly nine case summaries")
    rows = []
    for line, name in zip(lines[:-1], names):
        expected = f"{name}: {expected_counts[name]} files, 0 differences"
        require(line == expected and expected_counts[name] > 0, "comparison case summary differs")
        rows.append({"case": name, "files_compared": expected_counts[name], "differences": 0})
    total = sum(expected_counts.values())
    require(lines[-1] == f"{len(names)} cases, {total} files compared, 0 differences",
            "comparison aggregate summary differs")
    return {"cases": rows, "files_compared": total, "differences": 0}


def load_original_helper(control, expected_sha):
    path = control / "scripts/default_output_identity_qualification.py"
    require(type(expected_sha) is str and SHA_PATTERN.fullmatch(expected_sha), "invalid original helper pin")
    require(digest(path)["sha256"] == expected_sha, "original helper pin differs before import")
    spec = importlib.util.spec_from_file_location("_frozen_default_identity_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def verify_sources(root, sources, helper, helper_path, deadline):
    freeze = read_json(root / "freeze.json")
    before = freeze["sources"]
    after = read_json(root / "sources-after.json")
    require(before == after, "original before/after tracked source snapshots differ")
    require(freeze.get("script_sha256") == digest(helper_path)["sha256"], "original helper source pin differs")
    require(freeze.get("matrix") == json.loads(json.dumps(helper.CASES)), "original fixed matrix differs")
    require(freeze.get("thread_caps") == helper.CAPS, "original thread caps differ")
    affinity = freeze.get("affinity")
    require(type(affinity) is list and len(affinity) == 1 and type(affinity[0]) is int,
            "original one-CPU affinity receipt differs")
    for name, sha in (("control", CONTROL), ("baseline", BASELINE), ("candidate", CANDIDATE)):
        actual = helper.source_snapshot(sources[name], sha, deadline)
        require(before.get(name) == actual, "frozen tracked source snapshot differs")
    require(set(before) == set(sources), "original source snapshot set differs")
    return freeze


def verify_native_copies(root, inventory):
    wheels = [name for name in inventory if name.startswith("wheels/")]
    natives = [name for name in inventory if name.startswith("native/")]
    require(len(wheels) == 1 and wheels[0].endswith(".whl"), "retained wheel set differs")
    require(len(natives) == 1 and natives[0].endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)),
            "retained native-copy set differs")
    require(inventory[wheels[0]]["sha256"] == WHEEL_SHA, "retained wheel pin differs")
    require(inventory[natives[0]]["sha256"] == NATIVE_SHA, "retained native-copy pin differs")
    with zipfile.ZipFile(root / wheels[0]) as wheel:
        members = archive_members(wheel)
        compiled = [name for name in members if name.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))]
        require(len(compiled) == 1, "compiled wheel member set differs")
        with wheel.open(members[compiled[0]]) as stream:
            hasher, size = hashlib.sha256(), 0
            while block := stream.read(1024**2):
                size += len(block)
                require(size <= MEMBER_LIMIT, "compiled wheel member exceeds bound")
                hasher.update(block)
        require(hasher.hexdigest() == NATIVE_SHA, "compiled wheel member pin differs")


def verify_probes(root, inventory, result, cases):
    expected = set()
    schemas = result.get("schemas")
    require(type(schemas) is dict and set(schemas) == {
        "AgentSimulator", "EcologySimulator", "PoliticsSimulator"}, "native schema receipt set differs")
    for arm, source_sha in (("baseline", BASELINE), ("candidate", CANDIDATE)):
        for case in cases:
            identities = []
            for stage in ("before", "after"):
                name = f"probes/{arm}-{case}-{stage}.json"
                expected.add(name)
                identity = read_json(root / name)
                require(identity["source"]["git_sha"] == source_sha, "probe source revision differs")
                require(identity["native"]["sha256"] == NATIVE_SHA, "probe native pin differs")
                require(identity["schemas"] == schemas, "probe native schemas differ")
                require(identity["source"]["package_digest"] == result["package_digests"][arm],
                        "probe source package digest differs")
                affinity = identity.get("affinity")
                require(type(affinity) is list and len(affinity) == 1 and type(affinity[0]) is int,
                        "probe one-CPU affinity differs")
                identities.append(identity)
            require(identities[0] == identities[1], "before/after probe identities differ")
            name = f"probes/{arm}-{case}-which.txt"
            expected.add(name)
            identity = identities[0]
            which = ("chronicler " + identity["source_file"] + "\nnative " +
                     identity["native_file"] + " " + NATIVE_SHA + "\n")
            require((root / name).read_text(encoding="utf-8") == which, "driver provenance differs")
    require({name for name in inventory if name.startswith("probes/")} == expected,
            "probe payload file set differs")


def verify_cases(root, inventory, rows, helper, candidate):
    sys.path.insert(0, str(candidate / "src"))
    from chronicler.bundle_codec import load_bundle
    import chronicler.bundle_codec as codec
    require(Path(codec.__file__).resolve() == candidate / "src/chronicler/bundle_codec.py",
            "bundle decoder does not come from frozen candidate")
    case_files, summaries = {}, []
    expected_audits = set()
    for row in rows:
        arm, case = row["arm"], row["case"]
        name = f"audits/{arm}-{case}.json"
        expected_audits.add(name)
        require(inventory[name]["sha256"] == row["audit_sha256"], "case audit pin differs")
        audit = read_json(root / name)
        files = verify_case_file_map(inventory, audit["files"], arm, case)
        case_root = root / "raw" / arm / case
        raw_bundle = (case_root / "chronicle_bundle.json").read_bytes()
        helper.require_stamp(raw_bundle)
        summary = helper.case_contract(case, set(files), read_json(case_root / "state.json"),
                                       load_bundle(case_root / "chronicle_bundle.json"))
        require(set(audit) == set(summary), "audit summary field set differs")
        require(all(audit[key] == value for key, value in summary.items() if key != "files"),
                "audit case seed, horizon, mode or shape differs")
        for filename in helper.COMMON | helper.SIDECARS | {"agent_events.arrow"} | {
                filename for filename in files if filename.startswith("memories_")}:
            if filename in files:
                require(files[filename]["bytes"] > 0, "empty required case export")
        case_files[(arm, case)] = files
        summaries.append({"arm": arm, "case": case, "files": len(files), "turns": summary["turns"]})
    require({name for name in inventory if name.startswith("audits/")} == expected_audits,
            "case audit payload file set differs")
    for arm in ("baseline", "candidate"):
        directories = {path.name for path in (root / "raw" / arm).iterdir() if path.is_dir()}
        require(directories == set(helper.CASES), "raw case directory set differs")
    counts = {}
    for case in helper.CASES:
        common = set(case_files[("baseline", case)]) & set(case_files[("candidate", case)])
        counts[case] = sum(PurePosixPath(name).name != "run_manifest.json"
                           and PurePosixPath(name).suffix != ".log" for name in common)
    return counts, summaries


def run_compare(root, candidate, output, counts):
    log = output / "compare.log"
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "LD_LIBRARY_PATH") if key in os.environ}
    environment.update(PYTHONPATH=str(candidate / "src"), PYTHONDONTWRITEBYTECODE="1",
                       PYTHONNOUSERSITE="1", PYTHONHASHSEED="0")
    command = [sys.executable, str(candidate / "scripts/turn_speed_identity.py"), "compare",
               str(root / "raw/baseline"), str(root / "raw/candidate")]
    with log.open("xb") as stream:
        result = subprocess.run(command, cwd=output, env=environment, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=180)
    require(result.returncode == 0, "frozen read-only comparator failed")
    require(log.stat().st_size <= COMPARE_LIMIT, "comparison log exceeds bound")
    return parse_comparison(log.read_text(encoding="utf-8"), counts)


def inspect(args, output):
    sources = {name: Path(getattr(args, name + "_root")).resolve()
               for name in ("control", "baseline", "candidate")}
    require(len(set(sources.values())) == 3, "frozen sources must be separate checkouts")
    require(all(not output.is_relative_to(source) for source in [
        *sources.values(), Path(__file__).resolve().parents[1]]), "reader output must be external")
    require(sys.version_info[:2] == (3, 13), "reader requires locked Python 3.13")
    require(importlib.util.find_spec("chronicler_agents") is None, "reader environment must have no native extension")
    archive = Path(args.archive).resolve() if args.archive else output / "original-artifact.zip"
    args._phase = "download"
    token = os.environ.pop("GITHUB_TOKEN", None)
    if args.download:
        download_archive(archive, token)
    token = None  # Do not retain or pass the Actions token to source-inspection children.
    root = output / "payload"
    args._phase = "extract"
    extract_archive(archive, root)
    args._phase = "inventory"
    original = verify_inventory(root)
    helper, helper_path = load_original_helper(sources["control"], read_json(root / "freeze.json")["script_sha256"])
    deadline = time.monotonic() + 600
    args._phase = "sources"
    freeze = verify_sources(root, sources, helper, helper_path, deadline)
    helper.require_matrix(sources["candidate"] / "scripts/turn_speed_identity.py")
    helper.require_matrix(sources["baseline"] / "scripts/turn_speed_identity.py")
    args._phase = "result"
    result = read_json(root / "result.json")
    rows = validate_result(result, helper.CASES)
    args._phase = "native_copies"
    verify_native_copies(root, original)
    args._phase = "probes"
    verify_probes(root, original, result, helper.CASES)
    args._phase = "cases"
    counts, cases = verify_cases(root, original, rows, helper, sources["candidate"])
    args._phase = "compare"
    comparison = run_compare(root, sources["candidate"], output, counts)
    args._phase = "after_identity"
    require(payload_inventory(root) == original, "reader or comparator changed original payload bytes or file set")
    require(digest(archive, ARCHIVE_BYTES) == {"bytes": ARCHIVE_BYTES, "sha256": ARCHIVE_SHA},
            "reader archive bytes changed")
    verify_sources(root, sources, helper, helper_path, deadline)
    require("chronicler_agents" not in sys.modules, "reader imported a native runtime")
    return {"qualified": True, "original_run_id": RUN_ID, "original_artifact_id": ARTIFACT_ID,
            "archive_sha256": ARCHIVE_SHA, "archive_bytes": ARCHIVE_BYTES,
            "inventory_sha256": INVENTORY_SHA, "inventory_payload_files": len(original) - 2,
            "baseline": BASELINE, "candidate": CANDIDATE, "original_control": CONTROL,
            "original_helper_sha256": freeze["script_sha256"],
            "wheel_sha256": WHEEL_SHA, "native_sha256": NATIVE_SHA,
            "cases": cases, "comparison": comparison,
            "normalization": NORMALIZATION,
            "scope": "read-only reinspection of pinned completed exports; no new worlds or native pools",
            "reader_sha256": digest(Path(__file__))["sha256"],
            "reader_workflow_sha": os.environ.get("GITHUB_SHA"),
            "reader_python": sys.version, "reader_executable": sys.executable,
            "compared_script_sha256": digest(sources["candidate"] / "scripts/turn_speed_identity.py")["sha256"],
            "directory_comparator_sha256": digest(sources["candidate"] / "scripts/cities_identity.py")["sha256"],
            "bundle_decoder_sha256": digest(sources["candidate"] / "src/chronicler/bundle_codec.py")["sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control-root", "baseline-root", "candidate-root", "output"):
        parser.add_argument("--" + name, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--archive")
    mode.add_argument("--download", action="store_true")
    args = parser.parse_args(argv)
    output = Path(args.output).resolve()
    require(not output.exists(), "reader output must be fresh")
    # Refuse internal destinations before creating any output.
    require(all(not output.is_relative_to(Path(source).resolve()) for source in
                (args.control_root, args.baseline_root, args.candidate_root, Path(__file__).resolve().parents[1])),
            "reader output must be external")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {"qualified": False, "original_run_id": RUN_ID, "original_artifact_id": ARTIFACT_ID}
    try:
        report = inspect(args, output)
    except Exception as error:
        # Only our fixed refusal labels are rendered. Other exceptions might expose URLs.
        report["error"] = str(error) if type(error) is Refusal else type(error).__name__
        report["stage"] = getattr(args, "_phase", "admission")
    report["reader_elapsed_seconds"] = time.monotonic() - started
    (output / "reader-result.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    summary = {key: report.get(key) for key in (
        "qualified", "original_run_id", "original_artifact_id", "inventory_payload_files",
        "baseline", "candidate", "inventory_sha256", "error", "stage", "reader_elapsed_seconds")}
    summary["comparison"] = report.get("comparison")
    print(json.dumps(summary, allow_nan=False), flush=True)
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
