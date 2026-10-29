"""Owned orchestration for an inactive, separate current6a2 timing diagnostic.

No installer, network transport, job-clock authenticator or active workflow is
provided here. Those admissions need a separately reviewed source activation.
Every runtime entry refuses while either approval is NULL, before product import.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import resource
import re
import sys
import time

import current6a2_timing_diagnostic as core
import current6a2_timing_records as records

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "docs/experiments/current6a2-timing-diagnostic.json"
PRODUCER_PINS = ROOT / "docs/experiments/current6a2-timing-producer-pins.json"
OWNER_WALL = 2400
OWNER_CPU = 1800
FINAL_WALL_RESERVE = 150
FINAL_CPU_RESERVE = 100
JOB_PUBLICATION_RESERVE = 105  # proposed20 serialization +60 upload +25 safety; review is NULL
require = records.require


def cpu_seconds():
    own = resource.getrusage(resource.RUSAGE_SELF)
    waited = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + waited.ru_utime + waited.ru_stime


def load_registration():
    value = records.read_json(REGISTRATION, 1024**2)
    require(value.get("protocol") == records.PROTOCOL and value.get("producer_source") == core.SOURCE,
            "registered diagnostic producer")
    require(value.get("execution_approval") == core.EXECUTION_APPROVAL
            and value.get("job_clock_admission_approval") == core.JOB_CLOCK_ADMISSION_APPROVAL,
            "source approval registration")
    require(value.get("schedule") == core.schedule() and value.get("windows") == [list(w) for w in core.WINDOWS],
            "fixed matrix registration")
    return value


def control_snapshot(registration):
    expected = registration.get("control_file_pins")
    require(type(expected) is dict and set(expected) >= {
        "scripts/current6a2_timing_owner.py", "scripts/current6a2_timing_diagnostic.py",
        "scripts/current6a2_timing_records.py", "docs/experiments/current6a2-timing-producer-pins.json"},
        "closed control source pins")
    result = {"registration": records.hash_regular(REGISTRATION, 1024**2), "files": {}}
    for name, pin in expected.items():
        require(type(name) is str and not name.startswith("/") and ".." not in Path(name).parts,
                "relative control pin")
        result["files"][name] = records.hash_regular(ROOT / name, 1024**2)
        require(result["files"][name] == pin, "current control source bytes")
    for name, pin in registration["selected_control_files"].items():
        require(records.hash_regular(ROOT / "scripts/current6a2_timing_controls" / name, 64 * 1024) == pin,
                "current selected helper bytes")
    return result


def git_metadata(root, expected):
    """Read bounded HEAD/ref bytes after an owned git command established the SHA."""
    root = records.absolute(root)
    head_path = root / ".git/HEAD"
    head_pin = records.hash_regular(head_path, 4096)
    raw = head_path.read_bytes()
    require(len(raw) == head_pin["bytes"] and hashlib.sha256(raw).hexdigest() == head_pin["sha256"],
            "Git HEAD changed during read")
    text = raw.decode("ascii").strip()
    result = {"HEAD": head_pin}
    if text == expected:
        return result
    require(text.startswith("ref: refs/heads/"), "explicit Git branch or detached HEAD")
    name = text[5:]
    require(re.fullmatch(r"refs/heads/[A-Za-z0-9._/-]+", name) and ".." not in name.split("/")
            and all(part not in ("", ".") for part in name.split("/")), "canonical Git ref")
    loose = root / ".git" / name
    result["loose_exists"] = loose.exists() or loose.is_symlink()
    if result["loose_exists"]:
        pin = records.hash_regular(loose, 128)
        require(loose.read_text(encoding="ascii").strip() == expected, "current loose Git ref")
        result["loose"] = pin
    else:
        packed = root / ".git/packed-refs"
        pin = records.hash_regular(packed, 1024**2)
        rows = packed.read_text(encoding="ascii").splitlines()
        matches = [row for row in rows if row.endswith(" " + name)]
        require(matches == [expected + " " + name], "current packed Git ref")
        result["packed"] = pin
    return result


def load_controls(registration):
    directory = ROOT / "scripts/current6a2_timing_controls"
    expected = registration["selected_control_files"]
    names = ("wealth_floor_build_resources", "exact_near_screen_session",
             "exact_near_screen_process", "wealth_floor_hosted_deployment")
    require(set(expected) == {name + ".py" for name in names}, "closed selected control names")
    modules = {}
    for name in names:
        path = directory / (name + ".py")
        require(records.hash_regular(path, 64 * 1024) == expected[path.name], "selected control bytes")
        require(name not in sys.modules, "selected control module alias occupied")
        spec = importlib.util.spec_from_file_location(name, path)
        require(spec is not None and spec.loader is not None, "selected control module spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules[name] = module
    return modules


def input_admission(path, registration, source_root, prefix):
    """Consume an exact separately approved receipt; never authenticate transport here."""
    expected = registration.get("runtime_input_admission_sha256")
    require(type(expected) is str and len(expected) == 64, "runtime input admission remains NULL")
    require(records.hash_regular(path, 1024**2)["sha256"] == expected, "approved runtime receipt digest")
    value = records.read_json(path, 1024**2)
    require(value.get("kind") == "ROOT_ADMITTED_CURRENT6A2_TIMING_INPUT"
            and value.get("producer_source") == core.SOURCE
            and value.get("qualified_CI_run") == 40939929535, "current6a2 own input source")
    require(value.get("source_root") == str(source_root) and value.get("native_prefix") == str(prefix),
            "admitted physical source/prefix")
    require(value.get("wheel") == {"bytes": core.WHEEL_BYTES, "sha256": core.WHEEL_SHA}
            and value.get("native") == {"bytes": core.NATIVE_BYTES, "sha256": core.NATIVE_SHA}
            and value.get("builder_source_digest") == core.SOURCE_DIGEST,
            "fresh own wheel/native803 source binding")
    require(value.get("official_origin_expiry_reauthenticated") is True,
            "separate official input admission missing")
    native_file = records.absolute(value["installed_native_file"])
    require(native_file.is_relative_to(prefix)
            and records.hash_regular(native_file, core.NATIVE_BYTES) == value["native"],
            "admitted physical native bytes")
    require(records.hash_regular(records.absolute(value["wheel_file"]), core.WHEEL_BYTES) == value["wheel"],
            "admitted physical original wheel bytes")
    expiry = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
    require(expiry.tzinfo is not None and datetime.now(timezone.utc) < expiry,
            "admitted input expiry")
    return value


def job_deadline(path, registration, control_source, *, now=time.monotonic):
    """Only consume a pinned authenticated same-VM receipt. No first-shell fallback.

    Its producer/HTTP-Date/official job join and upload reserve require a future
    source review; both approval and receipt hash are NULL in this child.
    """
    require(core.JOB_CLOCK_ADMISSION_APPROVAL is not None, "actual job-clock source review is NULL")
    expected = registration.get("job_clock_admission_sha256")
    require(type(expected) is str and len(expected) == 64, "job-clock receipt pin remains NULL")
    require(records.hash_regular(path, 64 * 1024)["sha256"] == expected, "approved job-clock digest")
    value = records.read_json(path, 64 * 1024)
    require(value.get("kind") == "ROOT_ADMITTED_ACTUAL_JOB_DEADLINE"
            and value.get("approval") == core.JOB_CLOCK_ADMISSION_APPROVAL
            and value.get("control_source") == control_source
            and value.get("producer_source") == core.SOURCE, "same job/source clock receipt")
    run, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(run.isascii() and run.isdecimal() and int(run) > 0 and attempt == "1"
            and value.get("run_id") == int(run) and value.get("attempt") == 1,
            "actual run/attempt clock join")
    deadline = value.get("job_deadline_monotonic")
    observed = value.get("monotonic_observed")
    require(type(deadline) in (int, float) and math.isfinite(deadline)
            and type(observed) in (int, float) and math.isfinite(observed)
            and 0 <= observed <= now() < deadline and deadline - observed <= 2700,
            "actual job-clock bounded monotonic domain")
    require(value.get("publication_reserve_seconds") == JOB_PUBLICATION_RESERVE,
            "reviewed job publication reserve")
    return deadline


def child_environment(source, prefix):
    # Credentials and inherited PYTHONPATH/loader/preload variables are not forwarded.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT")
           if key in os.environ}
    env.update(core.CAPS)
    env["PYTHONPATH"] = os.pathsep.join((str(source / "src"), str(ROOT / "scripts")))
    env["VIRTUAL_ENV"] = str(prefix)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CHRONICLER_QUIET"] = "1"
    return env


def child_limits(cpu=240):
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (records.ROLE_BYTES, records.ROLE_BYTES))


def producer_pins():
    value = records.read_json(PRODUCER_PINS, 1024**2)
    require(value.get("producer_source") == core.SOURCE and value.get("builder_source_digest") == core.SOURCE_DIGEST,
            "protected producer registration")
    return value["source_files"]


def child(args):
    core.require_approval()
    registration = load_registration()
    source, prefix = records.absolute(args.source), records.absolute(args.prefix)
    input_admission(args.admission, registration, source, prefix)
    child_limits(40 if args.child in ("hash", "compare") else 240)
    hashes = producer_pins()
    if args.child == "bootstrap":
        _cm, np, _sync, identity = core.import_runtime(source, prefix, hashes)
        rng = core.capture_rng(np)
        core.validate_rng(rng)
        records.write_new(args.result, {"kind": "TIMING_ONLY_INITIAL_RNG_INPUT", "protocol": records.PROTOCOL,
                          "identity": identity, "rng": rng, "unknown": dict(records.UNKNOWN)})
    elif args.child == "role":
        records.integer(args.index, 0, 5)
        shared = records.read_json(args.shared_rng, records.SUMMARY_BYTES)
        require(shared.get("kind") == "TIMING_ONLY_INITIAL_RNG_INPUT" and shared.get("unknown") == records.UNKNOWN,
                "initial RNG input record")
        core.run_role(core.schedule()[args.index], source_root=source, prefix=prefix,
                      expected_hashes=hashes, ordinary=args.ordinary, role_root=args.role_root,
                      shared_rng=shared["rng"])
    elif args.child == "hash":
        records.integer(args.remaining_hash_bytes, 0, records.ROLE_BYTES)
        value = records.inventory(args.ordinary, maximum_bytes=args.remaining_hash_bytes)
        records.write_new(args.result, value, records.DETAIL_BYTES)
    elif args.child == "compare":
        left = records.read_json(args.left, records.DETAIL_BYTES)
        right = records.read_json(args.right, records.DETAIL_BYTES)
        records.write_new(args.result, records.compare_inventories(left, right))
    else:
        raise records.Refused("unknown child operation")
    require(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 <= 2 * 1024**3,
            "whole child lifetime RSS cap")


def materiality(root):
    """A predeclared prioritization screen, never an improvement/adoption decision."""
    fractions = []
    missing = []
    for index in (2, 5):
        path = root / "roles" / str(index) / "detail.json"
        try:
            detail = records.read_json(path, records.DETAIL_BYTES)
            require(detail.get("kind") == "TIMING_ONLY_COMPLETE_PROFILE_DETAIL"
                    and detail.get("table_complete") is True, "complete diagnostic detail")
            values = detail["sync_opportunity"]
            require(type(values) is list and len(values) == 2, "two materiality windows")
            for window in values:
                value = window["observed_profiled_window_CPU_fraction"]
                require(window["complete_selected_caller_coverage"] is True
                        and type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
                        "unknown or incomplete attribution")
                fractions.append(value)
        except (OSError, ValueError, KeyError, TypeError):
            missing.append(index)
    decision = "INCONCLUSIVE"
    if any(value >= .05 for value in fractions):
        decision = "INVESTIGATE_SEPARATE_BATCH_CANDIDATE"
    elif len(fractions) == 4 and not missing and all(value < .01 for value in fractions):
        decision = "DEPRIORITIZE_BATCH_RANK_BROADER_HOTSPOTS"
    return {"decision": decision, "observed_profiled_window_CPU_fractions": fractions,
            "unavailable_role_details": missing, "scope": "inclusive sync opportunity; no predicted gain or activation",
            "controlled_speedup": None}


def run_owner(args):
    core.require_approval()
    registration = load_registration()
    source, prefix, root = map(records.absolute, (args.source, args.prefix, args.output))
    require(source != ROOT and not source.is_relative_to(ROOT) and not ROOT.is_relative_to(source),
            "separate immutable producer/control roots")
    require(not root.exists() and not root.is_symlink(), "fresh diagnostic root")
    started, cpu_started = time.monotonic(), cpu_seconds()
    deadline = min(started + OWNER_WALL, job_deadline(args.job_clock, registration, args.control_source) - JOB_PUBLICATION_RESERVE)
    require(deadline - started > FINAL_WALL_RESERVE, "job room before any World")
    admitted = input_admission(args.admission, registration, source, prefix)
    controls = load_controls(registration)
    own, legacy = controls["exact_near_screen_process"], controls["exact_near_screen_session"]
    deployment = controls["wealth_floor_hosted_deployment"].hosted_vm_precondition()
    root.mkdir()
    for directory in ("logs", "roles", "work", "comparisons"):
        (root / directory).mkdir()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    env = child_environment(source, prefix)
    require(all(os.environ.get(key) == value for key, value in core.CAPS.items()), "owner startup caps")
    report = {"kind": "TIMING_ONLY_OWNER_SUMMARY", "protocol": records.PROTOCOL,
              "producer_source": core.SOURCE, "control_source": args.control_source,
              "completed_roles": [], "errors": [], "matrix_complete": False,
              "actual_native_ticks": None, "actual_native_population": None,
              "unknown": dict(records.UNKNOWN), "deployment": deployment,
              "input_admission_digest": records.hash_regular(args.admission, 1024**2),
              "job_clock_digest": records.hash_regular(args.job_clock, records.SUMMARY_BYTES),
              "publication_room_is_reserved_not_guaranteed_delivery": True,
              "optional_observations_unavailable": []}
    supervisor = None
    failure = None
    whole_cleanup = False
    controls_before = control_snapshot(registration)
    git_before = None
    def final_source_guard():
        require(control_snapshot(registration) == controls_before, "late control source/registration mutation")
        core.verify_producer(source, producer_pins())
        require(git_before is not None and git_metadata(ROOT, args.control_source) == git_before["control"]
                and git_metadata(source, core.SOURCE) == git_before["producer"], "late Git HEAD/ref mutation")
        input_admission(args.admission, registration, source, prefix)
        require(records.hash_regular(args.job_clock, records.SUMMARY_BYTES) == report["job_clock_digest"],
                "late actual-job-clock receipt mutation")
        require(time.monotonic() <= deadline and cpu_seconds() - cpu_started <= OWNER_CPU,
                "final source/admission live limits")
    try:
        with own.Cancellation() as cancellation, own.SubreaperLease() as lease:
            supervisor = own.make_supervisor(legacy, root, deadline, lease, cancellation)
            supervisor.admission("initial", 12, 4)
            def guard(final=False):
                supervisor.check(final=final)
                require(cpu_seconds() - cpu_started <= OWNER_CPU, "owner measured self+waited CPU cap")
                require(datetime.now(timezone.utc) < datetime.fromisoformat(admitted["expires_at"].replace("Z", "+00:00")),
                        "input expired during owned operation")
            def command(label, argv, wall=300):
                guard()
                cpu_room = OWNER_CPU - (cpu_seconds() - cpu_started) - FINAL_CPU_RESERVE
                wall_room = deadline - time.monotonic() - FINAL_WALL_RESERVE
                allowed = min(wall, cpu_room, wall_room)
                require(allowed >= 1, "reserved finalization room")
                supervisor.command(label, ["/usr/bin/timeout", "--signal=TERM", "--kill-after=5s",
                                          str(int(allowed)), *argv], env, root)
                guard()
            for label, path, expected in (("control", ROOT, args.control_source), ("producer", source, core.SOURCE)):
                command(label + "-head", ["git", "-C", str(path), "rev-parse", "HEAD"], 30)
                require(supervisor.last_stdout.strip().decode() == expected, "checkout Git identity")
                command(label + "-clean", ["git", "-C", str(path), "status", "--porcelain=v1"], 30)
                require(not supervisor.last_stdout, "dirty or untracked checkout")
            git_before = {"control": git_metadata(ROOT, args.control_source),
                          "producer": git_metadata(source, core.SOURCE)}
            py = prefix / "bin/python"
            require(py.exists(), "separately admitted runtime Python")
            base = [str(py), "-P", "-s", "-B", "-X", "cpu_count=1", str(Path(__file__).resolve()),
                    "--source", str(source), "--prefix", str(prefix), "--admission", str(args.admission)]
            shared = root / "initial-rng.json"
            command("bootstrap", [*base, "--child", "bootstrap", "--result", str(shared)])
            ordinary_bytes = 0
            for request in core.schedule():
                index = request["index"]
                role = root / "roles" / str(index)
                role.mkdir()
                ordinary = root / "work" / request["case"]
                report["stage"] = "role:" + str(index)
                command("role-" + str(index), [*base, "--child", "role", "--index", str(index),
                        "--ordinary", str(ordinary), "--role-root", str(role), "--shared-rng", str(shared)])
                summary = records.validate_summary(records.read_json(role / "summary.json", records.SUMMARY_BYTES))
                require(summary["request"] == request and summary["role_complete"] is True,
                        "successful witnessed role return")
                require(supervisor.cleanup_complete, "owned role quiescence")
                remaining = min(records.ROLE_BYTES, records.TOTAL_BYTES - ordinary_bytes)
                inventory_path = role / "ordinary-inventory.json"
                command("hash-" + str(index), [*base, "--child", "hash", "--ordinary", str(ordinary),
                        "--remaining-hash-bytes", str(remaining), "--result", str(inventory_path)], 60)
                facts = records.validate_inventory(records.read_json(inventory_path, records.DETAIL_BYTES))
                ordinary_bytes += facts["bytes"]
                role_metadata = records.inventory(role, maximum_bytes=records.ROLE_BYTES, guard=guard)
                require(facts["bytes"] + role_metadata["bytes"] <= records.ROLE_BYTES, "joint whole role output cap")
                require(supervisor.cleanup_complete, "owned hash child quiescence")
                os.rename(ordinary, role / "ordinary")
                # No second body hash: rename identity is checked at root and the
                # first complete closed map is retained for exact paired comparison.
                archived = records.stat_inventory(role / "ordinary", maximum_bytes=records.ROLE_BYTES, guard=guard)
                require(not ordinary.exists() and archived["root_identity"] == facts["root_identity"]
                        and archived["identities"] == facts["identities"], "ordinary archival identity")
                report["completed_roles"].append({"index": index, "request": request,
                    "completed_world_turn_boundaries": summary["completed_world_turn_boundaries"],
                    "actual_native_ticks": None, "actual_native_population": None,
                    "ordinary_bytes_hashed": facts["bytes"]})
                if index % 2:
                    comparison_path = root / "comparisons" / (request["case"] + ".json")
                    try:
                        command("compare-" + request["case"], [*base, "--child", "compare", "--left",
                                str(root / "roles" / str(index - 1) / "ordinary-inventory.json"), "--right",
                                str(inventory_path), "--result", str(comparison_path)], 60)
                        status = {"available": True, "reason": None}
                    except Exception:
                        guard()
                        require(supervisor.cleanup_complete and not own.direct_children(),
                                "comparison refusal requires owned quiescence")
                        report["optional_observations_unavailable"].append(request["case"] + ":comparison")
                        status = {"available": False, "reason": "BOUNDED_COMPARISON_REFUSED"}
                    records.write_new(root / "comparisons" / (request["case"] + "-status.json"), status,
                                      records.SUMMARY_BYTES, guard=guard)
                # Joint accounting includes metadata, logs and all generated bodies;
                # the full64MiB/128metadata reserve stays inside3GiB/5000files.
                current = records.stat_inventory(root,
                    maximum_bytes=records.TOTAL_BYTES - records.METADATA_BYTES - 3 * records.SUMMARY_BYTES,
                    maximum_files=records.TOTAL_FILES - records.METADATA_FILES - 3, guard=guard)
                require(current["bytes"] + records.METADATA_BYTES <= records.TOTAL_BYTES,
                        "joint aggregate publication reserve")
            report["matrix_complete"] = len(report["completed_roles"]) == 6
            report["materiality"] = materiality(root)
            guard()
            require(supervisor.cleanup_complete and not own.direct_children(), "final owned quiescence")
            for label, path, expected in (("control", ROOT, args.control_source), ("producer", source, core.SOURCE)):
                command("final-" + label + "-head", ["git", "-C", str(path), "rev-parse", "HEAD"], 30)
                require(supervisor.last_stdout.strip().decode() == expected, "final checkout Git identity")
                command("final-" + label + "-clean", ["git", "-C", str(path), "status", "--porcelain=v1"], 30)
                require(not supervisor.last_stdout, "final dirty/untracked checkout")
            final_source_guard()
            guard(final=True)
        require(not own.direct_children(), "whole owner post-lease quiescence")
        whole_cleanup = True
    except BaseException as exc:
        failure = exc
        report["errors"].append({"stage": report.get("stage", "admission"), "code": "OWNED_OPERATION_REFUSED"})
        report["matrix_complete"] = False
    report["owner_wall_seconds"] = time.monotonic() - started
    report["owner_self_plus_waited_CPU_seconds"] = cpu_seconds() - cpu_started
    report["whole_owner_cleanup_certified"] = whole_cleanup
    # Terminal evidence is immutable and negative when any late guard refuses.
    try:
        require(time.monotonic() <= deadline and cpu_seconds() - cpu_started <= OWNER_CPU,
                "terminal owner limits")
        final_source_guard()
        records.stat_inventory(root, maximum_bytes=records.TOTAL_BYTES - records.METADATA_BYTES - 3 * records.SUMMARY_BYTES,
                               maximum_files=records.TOTAL_FILES - records.METADATA_FILES - 3)
        records.write_new(root / "owner-summary.json", report)
        records.write_new(root / "terminal.json", {"kind": "TIMING_ONLY_TERMINAL", "protocol": records.PROTOCOL,
                          "matrix_complete": report["matrix_complete"], "owner_summary": records.hash_regular(root / "owner-summary.json", records.SUMMARY_BYTES),
                          "whole_owner_cleanup_certified": report["whole_owner_cleanup_certified"],
                          "unknown": dict(records.UNKNOWN)})
        if supervisor is not None:
            supervisor.check(final=True)
        final_source_guard()
        records.stat_inventory(root, maximum_bytes=records.TOTAL_BYTES - records.METADATA_BYTES - records.SUMMARY_BYTES,
                               maximum_files=records.TOTAL_FILES - records.METADATA_FILES - 1)
        require(time.monotonic() <= deadline and cpu_seconds() - cpu_started <= OWNER_CPU,
                "post-terminal live owner limits")
    except BaseException:
        failure = failure or records.Refused("terminal or post-terminal guard refused")
        # Distinct immutable sentinel invalidates a preexisting positive terminal.
        try:
            records.write_new(root / "terminal-failure.json", {"kind": "TIMING_ONLY_TERMINAL_FAILURE",
                              "protocol": records.PROTOCOL, "unknown": dict(records.UNKNOWN)})
        except BaseException:
            pass
    if failure is not None:
        raise failure
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--control-source")
    parser.add_argument("--job-clock", type=Path)
    parser.add_argument("--child", choices=("bootstrap", "role", "hash", "compare"))
    parser.add_argument("--index", type=int)
    parser.add_argument("--ordinary", type=Path)
    parser.add_argument("--role-root", type=Path)
    parser.add_argument("--shared-rng", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--left", type=Path)
    parser.add_argument("--right", type=Path)
    parser.add_argument("--remaining-hash-bytes", type=int, default=records.ROLE_BYTES)
    args = parser.parse_args()
    core.require_approval()
    if args.child:
        child(args)
    else:
        require(args.output is not None and args.control_source is not None and args.job_clock is not None,
                "owner explicit source/output/job-clock arguments")
        run_owner(args)


if __name__ == "__main__":
    main()
