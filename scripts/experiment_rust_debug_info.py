#!/usr/bin/env python3
"""Prepare/run one frozen, isolated Rust debug-info footprint experiment.

Preparation never compiles. Execute only in the lead's allocated one-CPU slot.
See docs/performance/rust-debug-info-preregistration.md; no speedup inference is
valid against the earlier copied-cache qualification.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import tomllib
import urllib.request

SOURCE = Path("/workspace/chronicler-next-qualified")
HEAD = "d051d7c06b1a490841d148b8906bde22f2f5d0f0"
TREE = "a4703ef4e9a21b5dbb194d318536a46e6ca8b71c"
NATIVE = SOURCE / ".venv/lib/python3.13/site-packages/chronicler_agents/chronicler_agents.cpython-313-x86_64-linux-gnu.so"
NATIVE_SHA = "fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317"
BASELINE = Path("/workspace/chronicler-next-qualification-evidence/rust-full-d051-20261028")
GIB = 1024 ** 3
FLOOR = 3 * GIB
STOP_RESERVE = GIB // 2
TARGET_CAP = 2 * GIB
REFERENCE = "https://doc.rust-lang.org/cargo/reference/profiles.html"


def utc():
    return datetime.now(timezone.utc).isoformat()


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def environment(target):
    # Reject inherited overrides rather than silently hiding a different build.
    for key, value in os.environ.items():
        if not value:
            continue
        if (key.startswith("CARGO_PROFILE_") or key.endswith("_RUSTFLAGS")
                or key in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_INCREMENTAL", "RUSTC",
                           "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTUP_TOOLCHAIN",
                           "CARGO_BUILD_TARGET", "CARGO_BUILD_RUSTFLAGS", "PYO3_CONFIG_FILE")):
            raise ValueError(f"unexpected compiler/profile override: {key}")
    env = dict(os.environ)
    env.update(PATH="/workspace/chronicler-tooling/cargo/bin:" + env["PATH"],
               CARGO_HOME="/workspace/chronicler-tooling/cargo", RUSTUP_HOME="/workspace/chronicler-tooling/rustup",
               PYO3_PYTHON="/workspace/chronicler-health-venv/bin/python",
               LIBRARY_PATH="/workspace/chronicler-tooling/lib", CARGO_TARGET_DIR=str(target),
               CARGO_BUILD_JOBS="1", CARGO_PROFILE_DEV_DEBUG="0", RAYON_NUM_THREADS="1",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    return env


def command_text(command, env):
    return subprocess.check_output(command, cwd=SOURCE, env=env, text=True).strip()


def config_identities(env):
    paths = set()
    for parent in (SOURCE, *SOURCE.parents, SOURCE / "chronicler-agents"):
        paths.update(parent / ".cargo" / name for name in ("config", "config.toml"))
    paths.update(Path(env["CARGO_HOME"]) / name for name in ("config", "config.toml"))
    result = {}
    for path in sorted(paths):
        if not path.exists():
            result[str(path)] = None
            continue
        data = tomllib.loads(path.read_text())
        if data.get("profile") or data.get("build") or data.get("target") or data.get("env"):
            raise ValueError(f"nonempty Cargo profile/build/target/env configuration: {path}")
        # Retain digests, not potentially private registry/auth configuration.
        result[str(path)] = file_sha(path)
    return result


def immutable_identity(env):
    if (command_text(["git", "rev-parse", "HEAD"], env) != HEAD
            or command_text(["git", "rev-parse", "HEAD:chronicler-agents"], env) != TREE
            or command_text(["git", "status", "--porcelain", "--untracked-files=no"], env)):
        raise ValueError("frozen source identity changed")
    if file_sha(NATIVE) != NATIVE_SHA:
        raise ValueError("installed native release changed")
    manifest = SOURCE / "chronicler-agents/Cargo.toml"
    profiles = tomllib.loads(manifest.read_text()).get("profile", {})
    if set(profiles) != {"release"}:
        raise ValueError("unexpected dev/test/custom profiles")
    return {"git_sha": HEAD, "native_crate_tree": TREE,
            "manifest_sha256": file_sha(manifest), "lock_sha256": file_sha(manifest.with_name("Cargo.lock")),
            "installed_extension_sha256": NATIVE_SHA, "cargo_configs": config_identities(env),
            "pyo3_python_sha256": file_sha(Path(env["PYO3_PYTHON"]).resolve()),
            "pyo3_python_version": command_text([env["PYO3_PYTHON"], "--version"], env),
            "libpython_sha256": file_sha(Path(env["LIBRARY_PATH"]) / "libpython3.13.so"),
            "toolchain": {name: command_text(cmd, env) for name, cmd in (
                ("rustup", ["rustup", "show", "active-toolchain"]), ("rustc", ["rustc", "-Vv"]),
                ("cargo", ["cargo", "-Vv"]))}}


def target_inventory(target):
    logical, allocated, count, seen, files = 0, 0, 0, set(), []
    pending = [target]
    while pending:
        folder = pending.pop()
        try:
            entries = list(os.scandir(folder))
        except FileNotFoundError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    stat = entry.stat(follow_symlinks=False)
                    count += 1
                    logical += stat.st_size
                    identity = stat.st_dev, stat.st_ino
                    unique = identity not in seen
                    seen.add(identity)
                    if unique:
                        allocated += stat.st_blocks * 512
                    files.append({"path": str(Path(entry.path).relative_to(target)), "logical_bytes": stat.st_size,
                                  "allocated_bytes": stat.st_blocks * 512, "unique_inode": unique})
            except FileNotFoundError:
                continue
    return {"logical_bytes": logical, "allocated_unique_bytes": allocated, "files": count,
            "largest_files": sorted(files, key=lambda item: item["logical_bytes"], reverse=True)[:20]}


def guard_reason(sample):
    if sample["free_bytes"] < FLOOR + STOP_RESERVE:
        return "filesystem below 3GiB floor plus 512MiB stopping reserve"
    if sample["target"]["allocated_unique_bytes"] > TARGET_CAP:
        return "isolated target exceeds registered 2GiB allocated cap"
    return None


def verify_profiles(messages):
    artifacts = []
    for line in messages.splitlines():
        item = json.loads(line)
        if item.get("reason") != "compiler-artifact":
            continue
        if item.get("target", {}).get("src_path", "").startswith(str(SOURCE / "chronicler-agents")):
            profile = item["profile"]
            if (profile.get("opt_level") != "0" or profile.get("debuginfo") != 0
                    or profile.get("debug_assertions") is not True or profile.get("overflow_checks") is not True
                    or item.get("features") != ["default"]):
                raise ValueError(f"effective native crate profile differs: {item['target']['name']}: {profile}")
            artifacts.append({"target": item["target"], "profile": profile, "features": item["features"],
                              "filenames": item["filenames"], "fresh": item["fresh"]})
    if len(artifacts) < 37 or not any(a["target"]["name"] == "chronicler_agents" and a["profile"]["test"] for a in artifacts):
        raise ValueError("missing full native-crate/test compiler-artifact evidence")
    return artifacts


def test_results(log):
    suites, tests, current = [], [], None
    for line in log.splitlines():
        match = re.match(r"\s*Running (?:unittests )?(.+?\.rs) \(", line)
        if match:
            current = match[1]
        if re.match(r"\s*Doc-tests chronicler_agents", line):
            current = "doc-tests"
        match = re.fullmatch(r"test (.+?) \.\.\. (ok|ignored|FAILED)(?:, .*)?", line)
        if match:
            if current is None:
                raise ValueError("test outcome before suite identity")
            tests.append([current, match[1], match[2]])
        match = re.match(r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out", line)
        if match:
            suites.append({"suite": current, "status": match[1], **dict(zip(
                ("passed", "failed", "ignored", "measured", "filtered_out"), map(int, match.groups()[1:])))})
    if (len(suites) != 37 or sum(s["passed"] for s in suites) != 1088 or sum(s["ignored"] for s in suites) != 2
            or any(s["status"] != "ok" or s["failed"] or s["filtered_out"] or s["measured"] for s in suites)
            or len(tests) != 1090):
        raise ValueError("full expected 1088-pass/2-ignore/37-suite evidence missing")
    return {"suites": suites, "tests": tests}


def prepare(args, env):
    if args.target.exists() or args.output.exists():
        raise FileExistsError("prepare requires new target and evidence paths")
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"status": "preparing", "started_at": utc(), "target": str(args.target), "source": str(SOURCE),
               "runner_sha256": file_sha(__file__), "environment": {key: env.get(key) for key in (
                   "PATH", "CARGO_HOME", "RUSTUP_HOME", "CARGO_TARGET_DIR", "CARGO_BUILD_JOBS", "CARGO_PROFILE_DEV_DEBUG",
                   "PYO3_PYTHON", "LIBRARY_PATH", "LD_LIBRARY_PATH", "RAYON_NUM_THREADS", "OMP_NUM_THREADS",
                   "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_INCREMENTAL")},
               "guard": {"floor_bytes": FLOOR, "stopping_reserve_bytes": STOP_RESERVE,
                         "target_allocated_cap_bytes": TARGET_CAP, "sample_interval_seconds": 1},
               "baseline": {"receipt": str(BASELINE / "qualification.json"),
                            "receipt_sha256": file_sha(BASELINE / "qualification.json"),
                            "log": str(BASELINE / "cargo-test-full.log"), "log_sha256": file_sha(BASELINE / "cargo-test-full.log")}}
    try:
        receipt["immutable"] = immutable_identity(env)
        baseline = json.loads((BASELINE / "qualification.json").read_text())
        if receipt["immutable"]["toolchain"] != baseline["toolchain"]:
            raise ValueError("toolchain differs from prior qualification")
        changed_env = {key: {"baseline": value, "candidate": env.get(key)}
                       for key, value in baseline["environment"].items()
                       if key not in ("CARGO_TARGET_DIR", "CARGO_PROFILE_DEV_DEBUG") and env.get(key) != value}
        if changed_env:
            raise ValueError(f"environment differs beyond target/debug intervention: {changed_env}")
        receipt["baseline_test_results"] = test_results((BASELINE / "cargo-test-full.log").read_text())
        manifest = SOURCE / "chronicler-agents/Cargo.toml"
        command = ["cargo", "metadata", "--locked", "--offline", "--no-deps", "--format-version", "1", "--manifest-path", str(manifest)]
        with (args.output / "metadata.json").open("w") as out, (args.output / "metadata.stderr").open("w") as err:
            code = subprocess.run(command, cwd=SOURCE, env=env, stdout=out, stderr=err).returncode
        receipt["metadata_command"], receipt["metadata_exit_code"] = command, code
        if code:
            raise ValueError("Cargo metadata failed")
        metadata = json.loads((args.output / "metadata.json").read_text())
        if (metadata["workspace_root"] != str(manifest.parent) or metadata["target_directory"] != str(args.target)
                or len(metadata["workspace_members"]) != 1):
            raise ValueError("unexpected workspace/target metadata")
        html = urllib.request.urlopen(REFERENCE, timeout=20).read()
        (args.output / "cargo-profile-reference.html").write_bytes(html)
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.decode()))
        if ('[profile.test] inherits = "dev"' not in plain or 'debug-assertions = true overflow-checks = true' not in plain):
            raise ValueError("Cargo reference did not establish registered inheritance/defaults")
        receipt["profile_reference"] = {"url": REFERENCE, "sha256": file_sha(args.output / "cargo-profile-reference.html"),
                                        "test_inherits": "dev", "opt_level": 0, "debug_assertions": True, "overflow_checks": True,
                                        "actual_compiler_artifacts_required_before_tests": True}
        if immutable_identity(env) != receipt["immutable"]:
            raise ValueError("inputs changed during preparation")
        if args.target.exists() and any(args.target.iterdir()):
            raise ValueError("metadata unexpectedly created target artifacts")
        receipt["metadata_sha256"] = file_sha(args.output / "metadata.json")
        receipt["status"] = "prepared"
    except BaseException as exc:
        receipt["status"], receipt["failure"] = "failed", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_at"] = utc()
        write_json(args.output / "prepare.json", receipt)
    print(json.dumps({"status": "prepared", "target": str(args.target), "profile_intervention": "CARGO_PROFILE_DEV_DEBUG=0"}))


def execute(args, env):
    prepared = json.loads((args.output / "prepare.json").read_text())
    receipt_path = args.output / "experiment.json"
    if (prepared["status"] != "prepared" or prepared["target"] != str(args.target) or receipt_path.exists()
            or prepared["runner_sha256"] != file_sha(__file__)):
        raise ValueError("requires an unchanged prepared runner and unused execution destination")
    if args.target.exists() and any(args.target.iterdir()):
        raise ValueError("target is no longer fresh")
    args.target.mkdir(exist_ok=True)
    report = {"status": "running", "started_at": utc(), "prepare_sha256": file_sha(args.output / "prepare.json"),
              "target": str(args.target), "stages": [], "sampled_peak_logical_bytes": 0,
              "sampled_peak_allocated_bytes": 0, "sampling_limits": "1-second scans; not instantaneous peak or RSS",
              "timing_limits": "cold target vs copied warm baseline; not a controlled speedup comparison"}

    def persist():
        write_json(receipt_path, report)

    def frozen():
        if (immutable_identity(env) != prepared["immutable"] or file_sha(__file__) != prepared["runner_sha256"]
                or file_sha(BASELINE / "qualification.json") != prepared["baseline"]["receipt_sha256"]
                or file_sha(BASELINE / "cargo-test-full.log") != prepared["baseline"]["log_sha256"]):
            raise ValueError("source/environment/baseline/runner identity changed")

    def sample(label):
        record = {"at": utc(), "stage": label, "free_bytes": shutil.disk_usage(args.target).free,
                  "target": target_inventory(args.target)}
        report["sampled_peak_logical_bytes"] = max(report["sampled_peak_logical_bytes"], record["target"]["logical_bytes"])
        report["sampled_peak_allocated_bytes"] = max(report["sampled_peak_allocated_bytes"], record["target"]["allocated_unique_bytes"])
        with (args.output / "storage-samples.jsonl").open("a") as handle:
            handle.write(json.dumps(record) + "\n")
        return record

    def run(command, label, json_output=False):
        frozen()
        before = sample(label)
        if guard_reason(before):
            raise RuntimeError(guard_reason(before))
        stdout = args.output / (label + (".jsonl" if json_output else ".log"))
        stderr = args.output / (label + ".stderr") if json_output else None
        started = time.perf_counter()
        proc = None
        stop_reason = None
        with stdout.open("w") as out:
            err = stderr.open("w") if stderr else None
            try:
                proc = subprocess.Popen(command, cwd=SOURCE, env=env, stdout=out,
                                        stderr=err or subprocess.STDOUT, start_new_session=True)
                while proc.poll() is None:
                    latest = sample(label)
                    stop_reason = guard_reason(latest)
                    if stop_reason:
                        os.killpg(proc.pid, signal.SIGTERM)
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait()
                        break
                    time.sleep(1)
            except BaseException:
                if proc is not None and proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                raise
            finally:
                if err is not None:
                    err.close()
                report["stages"].append({"label": label, "command": command, "seconds": time.perf_counter() - started,
                                         "exit_code": None if proc is None else proc.poll(), "guard_stop": stop_reason,
                                         "stdout_sha256": file_sha(stdout),
                                         "stderr_sha256": None if stderr is None else file_sha(stderr)})
                persist()
        sample(label)
        if stop_reason or proc.returncode:
            raise RuntimeError(stop_reason or f"{label} exited {proc.returncode}; artifacts/logs retained")
        frozen()
        return stdout

    persist()
    try:
        common = ["cargo", "test", "--locked", "--manifest-path", str(SOURCE / "chronicler-agents/Cargo.toml"), "--jobs", "1"]
        artifacts = run(common + ["--no-run", "--message-format=json-render-diagnostics", "--verbose"], "compile", True)
        profiles = verify_profiles(artifacts.read_text())
        write_json(args.output / "effective-profiles.json", profiles)
        report["effective_profiles_verified_before_tests"] = True
        persist()
        print("compile complete; effective opt0/debug0/assertions/overflow profiles verified before tests", flush=True)
        tests = run(common + ["--", "--test-threads=1"], "cargo-test-full")
        results = test_results(tests.read_text())
        if (Counter(json.dumps(s, sort_keys=True) for s in results["suites"])
                != Counter(json.dumps(s, sort_keys=True) for s in prepared["baseline_test_results"]["suites"])
                or Counter(map(tuple, results["tests"])) != Counter(map(tuple, prepared["baseline_test_results"]["tests"]))):
            raise ValueError("full test names/outcomes or suite counts differ from baseline")
        report["suite_results"], report["test_names_outcomes_match_baseline"] = results["suites"], True
        report["status"] = "complete"
    except BaseException as exc:
        report["status"], report["failure"] = "failed", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["final_storage"] = sample("final")
        report["finished_at"] = utc()
        persist()
    print(json.dumps({"status": report["status"], "receipt": str(receipt_path),
                      "final_allocated_bytes": report["final_storage"]["target"]["allocated_unique_bytes"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "execute"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    args.output, args.target = args.output.absolute(), args.target.absolute()
    for path in (args.output, args.target):
        if path.is_symlink() or SOURCE == path or SOURCE in path.parents:
            raise ValueError("use external nonsymlink experiment directories")
    if args.output == args.target or args.output in args.target.parents or args.target in args.output.parents:
        raise ValueError("target and evidence must be separate directories")
    env = environment(args.target)
    prepare(args, env) if args.phase == "prepare" else execute(args, env)


if __name__ == "__main__":
    main()
