"""Opt-in paired compiled API experiment; controller never imports the runtime."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
try:
    import resource
except ImportError:  # Disabled mode and pure contracts remain portable.
    resource = None
import signal
import statistics
import subprocess
import sys
import time


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b = load_module("paired_context_core", Path(__file__).with_name("benchmark_named_context.py"))
METHOD = "paired-context-v1-fresh-per-trial-20000records"
SOURCES = {
    "parent": ("82902b85a94ebb008168cb06195b031c6ee1eb92", "a840fd12462deedf92b256878d474404eeac892d"),
    "child": ("ef716e7f0d5ba0fa1e4c53774389201bcc23720d", "8e3ec0e90e184bcb9f11d6bd21eb5d275e7bf9db"),
}
RUN_REF = "refs/heads/lead/paired-context-benchmark-run-20261030"
CONTROLLER_AS = 128 * 1024**2
WORKER_AS = 1920 * 1024**2
TOTAL_AS = 2 * 1024**3
CPU_SECONDS = 24
WORKER_CREDIT_US = 512_000_000
WALL_NS = 600_000_000_000
MAX_FRAGMENT = 8192
MAX_ERROR = 32768
MAX_JOURNAL = 1280 * 1024
MAX_RESULT = 256 * 1024
MAX_OWNER = 8192
TOTAL_BODY = 2 * 1024**2
GITHUB_FIELDS = ("GITHUB_SHA", "GITHUB_REF", "GITHUB_JOB", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")


def schedule():
    rows = []
    for case in range(21):
        for trial in range(3):
            roles = ("parent", "child") if (case+trial) % 2 == 0 else ("child", "parent")
            for role in roles:
                rows.append(dict(ordinal=len(rows), case=case, trial=trial, role=role,
                    source_order=list(roles)))
    return rows


def plan():
    workers = schedule()
    return dict(kind="PAIRED_CONTEXT_PLAN", method=METHOD, sources=SOURCES,
        conditions=b.conditions(), schedule=workers, planned_workers=len(workers),
        planned_timings=2*len(workers), records_per_helper_trial=20000, warmup_records=200,
        trials=3, pool_lifetime="fresh per source/case/trial; two helpers share it",
        helper_order="scalar,batch if (case+trial)%2==0 else batch,scalar",
        comparison_limits=dict(wall_seconds=600, CPU_seconds=540, CPUs=1,
            application_AS_bytes=TOTAL_AS, controller_soft_AS=CONTROLLER_AS,
            worker_hard_AS=WORKER_AS, controller_hard_CPU=24, worker_hard_CPU=24,
            waited_worker_credit_us=WORKER_CREDIT_US, accounting_slack_seconds=4),
        build_outside_comparison=True, retries=0,
        scope="Initialized compiled context getters; no World/tick/whole-turn/scientific qualification.")


def driver_pins():
    folder = Path(__file__).resolve().parent
    return {name: b.file_pin(folder/name, b.MAX_BUILD) for name in
        ("paired_context_benchmark.py", "benchmark_named_context.py", "native_wheel_receipt.py")}


def github_admission():
    b.require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "first_attempt_required")
    b.require(os.environ.get("GITHUB_REF") == RUN_REF, "paired_run_ref_required")
    source = os.environ.get("GITHUB_SHA", "")
    b.require(len(source) == 40 and all(c in "0123456789abcdef" for c in source), "controller_source")
    b.require(bool(os.environ.get("GITHUB_JOB"))
        and os.environ.get("GITHUB_RUN_ID", "").isdigit(), "actual_run_job_required")
    return source


def git(root, *args):
    value = subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    b.require(value.returncode == 0, "source_git_failure")
    return value.stdout.decode().strip()


def checked_checkout(root, expected):
    b.require(Path(git(root, "rev-parse", "--show-toplevel")).resolve() == root.resolve(), "checkout_top")
    b.require(git(root, "rev-parse", "HEAD") == expected, "checkout_commit")
    b.require(not git(root, "status", "--porcelain", "--untracked-files=no"), "dirty_tracked_source")


def receipt_function():
    helper = load_module("paired_context_receipt", Path(__file__).with_name("native_wheel_receipt.py"))
    return helper.wheel_receipt


def seal_sources(root, staged_rows):
    sealed = hashlib.sha256()
    source_bytes = source_files = 0
    for row in staged_rows.split(b"\0"):
        if not row:
            continue
        metadata, name = row.split(b"\t", 1)
        mode, oid, stage = metadata.decode().split()
        path = root/os.fsdecode(name)
        b.require(mode in ("100644", "100755") and stage == "0"
            and path.is_file() and not path.is_symlink(), "tracked_payload")
        size = path.stat().st_size
        pin = b.file_pin(path, 64*1024**2) if size else dict(filename=path.name,
            bytes=0, sha256=hashlib.sha256(b"").hexdigest())
        sealed.update(json.dumps([os.fsdecode(name), mode, oid, pin], sort_keys=True).encode()+b"\n")
        source_files += 1
        source_bytes += size
        path.chmod(0o555 if mode == "100755" else 0o444)
    return dict(files=source_files, bytes=source_bytes, aggregate_sha256=sealed.hexdigest())


def record_build(controller_root, measured_root, role, wheel_dir, output):
    import importlib.metadata
    controller_sha = github_admission()
    checked_checkout(controller_root, controller_sha)
    b.require(Path(__file__).resolve().is_relative_to(controller_root.resolve()), "driver_outside_controller")
    source, native_tree = SOURCES[role]
    checked_checkout(measured_root, source)
    b.require(git(measured_root, "rev-parse", "HEAD:chronicler-agents") == native_tree, "measured_native_tree")
    native, native_path = b.compiled_module()
    wheels = list(wheel_dir.glob("*.whl"))
    b.require(len(wheels) == 1, "one_own_wheel")
    b.file_pin(wheels[0], b.MAX_WHEEL)
    b.file_pin(native_path, b.MAX_NATIVE)
    link = receipt_function()(wheel_dir, native_path, source)
    distributions = sorted((d.metadata["Name"].lower().replace("_", "-"), d.version)
        for d in importlib.metadata.distributions())
    raw = subprocess.check_output(["git", "--no-replace-objects", "-C", str(measured_root),
        "ls-files", "--stage", "-z"])
    sealed = seal_sources(measured_root, raw)
    checked_checkout(measured_root, source)
    wheels[0].chmod(0o444)
    native_path.chmod(native_path.stat().st_mode & 0o555)
    value = dict(kind="PAIRED_OWN_MEASURED_BUILD", method=METHOD, role=role,
        source_commit=source, source_tree=git(measured_root, "rev-parse", "HEAD^{tree}"),
        native_tree=native_tree, controller_commit=controller_sha,
        controller_tree=git(controller_root, "rev-parse", "HEAD^{tree}"), driver=driver_pins(),
        workflow=b.file_pin(controller_root/".github/workflows/paired-context-benchmark.yml", b.MAX_BUILD),
        measured_root=str(measured_root.resolve()), controller_root=str(controller_root.resolve()),
        wheel_dir=str(wheel_dir.resolve()), worker_python=sys.executable,
        venv_prefix=sys.prefix, native_file=str(native_path.resolve()), wheel_receipt=link,
        python=dict(version=sys.version, binary=b.file_pin(Path(sys.executable).resolve(), b.MAX_NATIVE)),
        host=dict(uname=list(os.uname()), runner={key: os.environ.get(key) for key in
            ("RUNNER_NAME", "RUNNER_OS", "RUNNER_ARCH")}),
        distributions=distributions,
        uv_lock=b.file_pin(measured_root/"uv.lock", 4*1024**2),
        cargo_lock=b.file_pin(measured_root/"chronicler-agents/Cargo.lock", b.MAX_BUILD),
        toolchain={name: b.file_pin(output.parent/name, 4096) for name in
            ("rustc.txt", "cargo.txt", "maturin.txt", "uv.txt")},
        sealed_source=sealed,
        build_flags={key: os.environ.get(key, "") for key in
            ("CARGO_TARGET_DIR", "CARGO_BUILD_JOBS", "CARGO_INCREMENTAL", "RUSTFLAGS")},
        github={key: os.environ.get(key) for key in GITHUB_FIELDS},
        scope="Own fresh locked build/installed bytes, not reproducibility or scientific qualification.")
    b.write_json(output, value, b.MAX_BUILD)
    output.chmod(0o444)
    return value


def validate_build(value, role, controller_sha, drivers, github):
    b.require(type(value) is dict and role in SOURCES, "build_record")
    b.require(value["kind"] == "PAIRED_OWN_MEASURED_BUILD" and value["method"] == METHOD
        and value["role"] == role, "build_role")
    b.require((value["source_commit"], value["native_tree"]) == SOURCES[role], "source_whitelist")
    b.require(value["controller_commit"] == controller_sha and value["driver"] == drivers,
        "controller_identity")
    b.require(github["GITHUB_SHA"] == controller_sha and github["GITHUB_REF"] == RUN_REF
        and github["GITHUB_RUN_ATTEMPT"] == "1"
        and all(value["github"][key] == github[key] for key in GITHUB_FIELDS), "actual_workflow_identity")
    for key in ("measured_root", "controller_root", "wheel_dir", "worker_python", "venv_prefix", "native_file"):
        b.require(type(value[key]) is str and Path(value[key]).is_absolute(), "build_path")
    return value


def read_build(path, role):
    b.require(path.stat().st_size <= b.MAX_BUILD, "build_record_limit")
    return validate_build(json.loads(path.read_text()), role, github_admission(), driver_pins(),
        {key: os.environ.get(key) for key in GITHUB_FIELDS})


def match_builds(builds, verify_files=True):
    parent, child = builds["parent"], builds["child"]
    for key in ("controller_commit", "controller_tree", "driver", "github", "python", "host", "distributions",
                "uv_lock", "cargo_lock", "toolchain"):
        b.require(parent[key] == child[key], "unequal_build_environment_"+key)
    for key in ("CARGO_BUILD_JOBS", "CARGO_INCREMENTAL", "RUSTFLAGS"):
        b.require(parent["build_flags"][key] == child["build_flags"][key], "unequal_build_flag")
    b.require(parent["build_flags"]["CARGO_BUILD_JOBS"] == "1"
        and parent["build_flags"]["CARGO_INCREMENTAL"] == "0"
        and parent["build_flags"]["CARGO_TARGET_DIR"] != child["build_flags"]["CARGO_TARGET_DIR"],
        "isolated_fresh_build_policy")
    b.require(parent["venv_prefix"] != child["venv_prefix"]
        and parent["wheel_dir"] != child["wheel_dir"], "isolated_environments")
    total = 0
    for role, build in builds.items():
        wheel = build["wheel_receipt"]["wheel"]
        total += wheel["bytes"]
        if verify_files:
            current = b.file_pin(Path(build["wheel_dir"])/wheel["filename"], b.MAX_WHEEL)
            b.require(all(current[k] == wheel[k] for k in ("filename", "bytes", "sha256")), "wheel_changed")
    b.require(total <= b.MAX_WHEEL, "joint_wheel_limit")


def controller_limits():
    b.require(resource is not None and sys.platform == "linux", "Linux_comparison_required")
    b.require(len(os.sched_getaffinity(0)) == 1, "one_CPU_required")
    b.require(resource.getrlimit(resource.RLIMIT_AS) == (TOTAL_AS, TOTAL_AS)
        and resource.getrlimit(resource.RLIMIT_CPU) == (540, 540), "outer_joint_limits")
    resource.setrlimit(resource.RLIMIT_AS, (CONTROLLER_AS, TOTAL_AS))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    b.require(not any(n == "chronicler_agents" or n.startswith("chronicler_agents.")
        for n in sys.modules), "controller_native_loaded")


def worker_bootstrap(controller_pid):
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), "parent_death_signal")
    if os.getppid() != controller_pid:
        os.kill(os.getpid(), signal.SIGKILL)
    resource.setrlimit(resource.RLIMIT_AS, (WORKER_AS, WORKER_AS))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FRAGMENT, MAX_FRAGMENT))


class SystemBackend:
    def __init__(self, build_paths):
        self.build_paths, self.active = build_paths, None

    def run(self, job, build, fragment, errors):
        b.require(self.active is None, "overlapping_workers")
        allowed = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", *GITHUB_FIELDS)
            if key in os.environ}
        allowed.update(PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0", PYTHONUNBUFFERED="1",
            RAYON_NUM_THREADS="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        argv = [build["worker_python"], "-B", str(Path(__file__).resolve()), "--worker",
            "--role", job["role"], "--case", str(job["case"]), "--trial", str(job["trial"]),
            "--build", str(self.build_paths[job["role"]])]
        with fragment.open("xb") as stdout, errors.open("xb") as stderr:
            pid = os.getpid()
            self.active = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=allowed,
                preexec_fn=lambda: worker_bootstrap(pid))
            try:
                _, status, usage = os.wait4(self.active.pid, 0)
                code = os.waitstatus_to_exitcode(status)
                self.active.returncode = code
                return dict(returncode=code, worker_pid=self.active.pid,
                    cpu_us=math.ceil((usage.ru_utime+usage.ru_stime)*1_000_000),
                    waited_user_seconds=usage.ru_utime, waited_system_seconds=usage.ru_stime,
                    maximum_worker_RSS_kib=usage.ru_maxrss)
            finally:
                self.close()

    def close(self):
        if self.active is not None:
            if self.active.returncode is None:
                self.active.kill()
                _, status, _ = os.wait4(self.active.pid, 0)
                self.active.returncode = os.waitstatus_to_exitcode(status)
            self.active = None

    def total_cpu_us(self):
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return math.ceil((usage.ru_utime+usage.ru_stime)*1_000_000)


def emit(value):
    body = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    b.require(sys.stdout.buffer.tell()+len(body) <= MAX_FRAGMENT, "worker_fragment_limit")
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def worker(role, case, trial, build_path):
    b.require(type(case) is int and 0 <= case < 21 and type(trial) is int and 0 <= trial < 3,
        "registered_worker")
    emit(dict(kind="worker_start", role=role, case=case, trial=trial,
        source_commit=SOURCES[role][0], native_tree=SOURCES[role][1], worker_pid=os.getpid(),
        clock_info={key: vars(time.get_clock_info(name)) for key, name in
            (("wall", "perf_counter"), ("CPU", "process_time"))}))
    try:
        build = read_build(build_path, role)
        b.require(len(os.sched_getaffinity(0)) == 1
            and resource.getrlimit(resource.RLIMIT_AS) == (WORKER_AS, WORKER_AS)
            and resource.getrlimit(resource.RLIMIT_CPU) == (CPU_SECONDS, CPU_SECONDS), "worker_limits")
        b.require(sys.prefix == build["venv_prefix"] and sys.executable == build["worker_python"], "own_venv")
        native, path = b.compiled_module()
        b.require(receipt_function()(Path(build["wheel_dir"]), path, build["source_commit"])
            == build["wheel_receipt"], "installed_wheel_changed")
        import pyarrow as pa
        sim, ids = b.fixture_factory(native, pa)(b.conditions()[case])
        result = b.condition_trial(b.conditions()[case], sim, ids, sys.stdout.buffer,
            time.perf_counter_ns, time.process_time_ns, trial)
        result.pop("samples")  # Exact raw sample rows were flushed before acceptance.
        emit(dict(kind="worker_end", result=result))
        return 0  # A completed numerical refusal is data; controller continues the schedule.
    except Exception as exc:
        emit(dict(kind="worker_error", error=dict(type=type(exc).__name__, message=str(exc)[:512])))
        return 2


def parse_fragment(data, job, expected_pid):
    b.require(0 < len(data) <= MAX_FRAGMENT and data.endswith(b"\n"), "worker_fragment_shape")
    rows = [json.loads(line) for line in data.splitlines()]
    b.require(len(rows) == 4 and rows[0]["kind"] == "worker_start"
        and rows[-1]["kind"] == "worker_end", "worker_protocol")
    head, result = rows[0], rows[-1]["result"]
    role, case, trial = job["role"], job["case"], job["trial"]
    b.require((head["role"], head["case"], head["trial"], head["source_commit"], head["native_tree"])
        == (role, case, trial, *SOURCES[role]), "worker_identity")
    b.require(type(expected_pid) is int and expected_pid > 0
        and type(head["worker_pid"]) is int and head["worker_pid"] == expected_pid, "worker_PID")
    spec = b.conditions()[case]
    b.require(all(result[k] == v for k, v in spec.items()) and result["trial"] == trial,
        "worker_case")
    b.require(result["records_per_helper_trial"] == 20000
        and result["warmup_records_per_helper"] == 200
        and result["repetitions"] == 20000//spec["requests"], "worker_dose")
    ids, positions = result["request_ids"], result["slot_positions"]
    b.require(type(ids) is list and len(ids) == spec["requests"]
        and all(type(i) is int and 0 <= i < 2**32 for i in ids), "observed_query_ids")
    n, p = spec["slots"], spec["requests"]
    expected_positions = ([None]*p if spec["layout"] == "missing" else
        list(range(p)) if spec["layout"] == "prefix" else
        [n//2] if p == 1 else [i*(n-1)//(p-1) for i in range(p)])
    b.require(positions == expected_positions, "observed_slot_layout")
    missing = spec["layout"] == "missing"
    fixture_checksum = sum(b.consume(i, [], None if missing else (0.,)*6,
        None if missing else [None]*spec["bond_slots"]) for i in ids)*result["repetitions"]
    b.require(type(result["expected_checksum"]) is int and result["expected_checksum"] == fixture_checksum,
        "initialized_fixture_checksum")
    for key in ("ordered_payload_sha256", "control_payload_sha256"):
        digest = result[key]
        b.require(type(digest) is str and len(digest) == 64
            and all(c in "0123456789abcdef" for c in digest), "payload_digest")
    order = ["scalar", "batch"] if (case+trial) % 2 == 0 else ["batch", "scalar"]
    samples = rows[1:-1]
    accepted = []
    for sample, side in zip(samples, order):
        b.require((sample["case"], sample["trial"], sample["helper"], sample["order"])
            == (case, trial, side, order), "sample_identity")
        for key in ("wall_start_ns", "wall_end_ns", "process_CPU_start_ns", "process_CPU_end_ns",
                    "wall_ns", "process_CPU_ns"):
            b.require(type(sample[key]) is int, "sample_clock_type")
        b.require(sample["wall_ns"] == sample["wall_end_ns"]-sample["wall_start_ns"]
            and sample["process_CPU_ns"] == sample["process_CPU_end_ns"]-sample["process_CPU_start_ns"],
            "sample_clock_join")
        ok = sample["wall_ns"] > 0 and sample["process_CPU_ns"] > 0 \
            and sample["checksum"] == result["expected_checksum"]
        b.require(type(sample["accepted"]) is bool and sample["accepted"] == ok
            and "error" not in sample, "sample_acceptance")
        accepted.append(ok)
    b.require(result["status"] == ("complete" if all(accepted) else "refused"), "numerical_status")
    return dict(result, role=role, source_commit=SOURCES[role][0], worker_pid=head["worker_pid"],
        clock_info=head["clock_info"], samples=samples)


def join_pair(parent, child):
    for key in ("case", "trial", "slots", "requests", "layout", "bond_slots", "request_ids",
                "slot_positions", "expected_checksum", "ordered_payload_sha256", "control_payload_sha256", "clock_info"):
        b.require(parent[key] == child[key], "cross_source_payload_"+key)


def credit_admits(charged_us):
    return type(charged_us) is int and 0 <= charged_us and charged_us+24_000_000 <= WORKER_CREDIT_US


def summaries(completed):
    result = []
    for case in range(21):
        rows = [r for r in completed if r["case"] == case]
        if len(rows) != 6:
            continue
        item = dict(case=case, status="refused")
        if all(r["status"] == "complete" for r in rows):
            medians = {role: {clock: {helper: statistics.median(s[clock] for r in rows
                if r["role"] == role for s in r["samples"] if s["helper"] == helper)
                for helper in ("scalar", "batch")} for clock in ("wall_ns", "process_CPU_ns")}
                for role in SOURCES}
            item.update(status="complete", medians=medians,
                scalar_over_batch={role: {clock: medians[role][clock]["scalar"]/medians[role][clock]["batch"]
                    for clock in ("wall_ns", "process_CPU_ns")} for role in SOURCES},
                child_change_percent={helper: {clock:
                    (medians["child"][clock][helper]/medians["parent"][clock][helper]-1)*100
                    for clock in ("wall_ns", "process_CPU_ns")} for helper in ("scalar", "batch")})
        result.append(item)
    return result


def run_schedule(builds, output, backend, wall=time.monotonic_ns, own_cpu=time.process_time_ns):
    b.require(output.is_absolute(), "absolute_output")
    output.mkdir(exist_ok=False)
    b.write_json(output/"plan.json", plan(), b.MAX_PLAN)
    jobs = schedule()
    state = dict(kind="PAIRED_CONTEXT_RESULT", method=METHOD, status="failed", planned_workers=len(jobs),
        planned_timings=2*len(jobs), retained_sample_rows=0, completed_workers=0,
        sample_count_scope="Rows counted after successful checked journal write, flush and fsync. Failed/interrupted canonical journal or active fragments can contain additional uncounted rows.",
        workers=[dict(j, status="not_run") for j in jobs], waited_worker_CPU_us=0,
        worker_CPU_accounting_complete=True,
        no_World_wholeturn_RNG_checkpoint_science_qualification=True, fresh_pool_per_trial=True)
    complete, joined = [], {}
    start, cpu_start = wall(), own_cpu()
    usage_pending = False
    try:
        with (output/"journal.jsonl").open("xb") as journal:
            for job in jobs:
                if wall()-start >= WALL_NS or not credit_admits(state["waited_worker_CPU_us"]):
                    state.update(status="resource_refused", error="joint_resource_credit")
                    break
                ordinal = job["ordinal"]
                state["workers"][ordinal] = dict(job, status="started")
                fragment, errors = output/"active.jsonl", output/"active.stderr"
                usage_pending = True
                usage = backend.run(job, builds[job["role"]], fragment, errors)
                b.require(type(usage["cpu_us"]) is int and usage["cpu_us"] >= 0, "waited_CPU")
                state["waited_worker_CPU_us"] += usage["cpu_us"]
                usage_pending = False
                b.require(fragment.stat().st_size <= MAX_FRAGMENT and errors.stat().st_size <= MAX_FRAGMENT,
                    "worker_file_limit")
                data = fragment.read_bytes()
                b.require(journal.tell()+len(data) <= MAX_JOURNAL, "joint_journal_limit")
                b.require(journal.write(data) == len(data), "short_journal_write")
                journal.flush()
                os.fsync(journal.fileno())
                for line in data.splitlines():
                    try:
                        row = json.loads(line)
                    except (ValueError, UnicodeError):
                        continue
                    if type(row) is dict and row.get("helper") in ("scalar", "batch"):
                        state["retained_sample_rows"] += 1
                stderr = errors.read_bytes()
                if stderr:
                    b.write_json(output/"worker-error.json", dict(job=job, stderr_hex=stderr.hex(),
                        stderr_sha256=hashlib.sha256(stderr).hexdigest(), usage=usage), MAX_ERROR)
                    b.require(False, "unexpected_worker_stderr")
                b.require(usage["returncode"] == 0, "worker_process_failed")
                result = parse_fragment(data, job, usage["worker_pid"])
                result["usage"] = usage
                partner = joined.get((job["case"], job["trial"]))
                if partner is not None:
                    join_pair(partner, result)
                else:
                    joined[(job["case"], job["trial"])] = result
                complete.append(result)
                state["workers"][ordinal] = dict(job, **{k: v for k, v in result.items()
                    if k not in ("samples", "case", "trial", "role")})
                state["completed_workers"] += 1
                fragment.unlink()
                errors.unlink()
                b.require(state["waited_worker_CPU_us"] <= WORKER_CREDIT_US, "worker_credit_exceeded")
            else:
                b.require(state["completed_workers"] == len(jobs)
                    and state["retained_sample_rows"] == 2*len(jobs), "registered_completion_count")
                state["status"] = "complete" if all(r["status"] == "complete" for r in complete) else "refused"
    except Exception as exc:
        state["error"] = dict(type=type(exc).__name__, message=str(exc)[:512])
        if usage_pending:
            state["worker_CPU_accounting_complete"] = False
        for row in state["workers"]:
            if row["status"] == "started":
                row["status"] = "failed"
    finally:
        backend.close()
        if hasattr(backend, "total_cpu_us"):
            # Includes failed-start/cleanup reaps whose per-worker reply was unavailable.
            try:
                observed = backend.total_cpu_us()
                state["observed_waited_CPU_us"] = observed
                state["waited_worker_CPU_us"] = max(state["waited_worker_CPU_us"], observed)
                state["worker_CPU_accounting_complete"] = True
            except Exception as exc:
                state.update(status="failed", worker_CPU_accounting_complete=False,
                    CPU_observation_error=type(exc).__name__+":"+str(exc)[:512])
        state["case_summaries"] = summaries(complete)
        cpu_end = own_cpu()
        state.update(scheduler_wall_ns=wall()-start, scheduler_CPU_ns=cpu_end-cpu_start,
            controller_CPU_ns=cpu_end,
            CPU_observation_scope="Whole controller process through finalization, before final JSON serialization; hard24s covers the entire process.",
            external_whole_comparison_wall_CPU_RSS=None)
        state["controller_native_modules"] = [n for n in sys.modules
            if n == "chronicler_agents" or n.startswith("chronicler_agents.")]
        if state["controller_native_modules"]:
            state.update(status="failed", error="controller_native_loaded", case_summaries=[])
        if state["controller_CPU_ns"]+state["waited_worker_CPU_us"]*1000 > 540_000_000_000:
            state.update(status="resource_refused", error="observed_joint_CPU_overage", case_summaries=[])
        b.write_json(output/"result.json", state, MAX_RESULT)
    return state


def encode_owner(value, file_bytes, body_cap, file_cap):
    def encode(row):
        return (json.dumps(row, sort_keys=True, indent=2)+"\n").encode()
    body = encode(value)
    if len(body) > file_cap or file_bytes+len(body) > body_cap:
        value = dict(value, evidence_retention="refused", refusal=value.get("refusal")
            or "structured evidence including owner exceeds the fixed body cap")
        body = encode(value)
        if len(body) > file_cap:
            value = dict(value, files=[],
                refusal="owner inventory exceeds per-file cap; member list omitted")
            body = encode(value)
    if len(body) > min(body_cap, file_cap):
        raise ValueError("bounded owner metadata exceeds the fixed body cap")
    return value, body


def record_owner(root, wheel_root):
    root.mkdir(exist_ok=True)
    value = dict(kind="PAIRED_CONTEXT_OWNER_ASOF", github={k: os.environ.get(k) for k in GITHUB_FIELDS},
        comparison_exit=os.environ.get("PAIRED_COMPARISON_EXIT") or None,
        identity_outcomes={role: os.environ.get("PAIRED_"+role.upper()+"_IDENTITY_OUTCOME") for role in SOURCES},
        files=[], evidence_retention="within_body_cap", refusal=None, wheels_allowed=False,
        wheel_refusal=None,
        build_outside_comparison=True, planned_timings=252, actual_samples=None,
        counted_durable_sample_rows=None,
        sample_count_scope="Rows counted after successful checked write, flush and fsync; failed/interrupted canonical journal or active fragments may add uncounted rows. Actual_samples is known only for a fully completed schedule.",
        complete_Python_sync_World_science_measured=False)
    total = 0
    try:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == root/"owner.json":
                continue
            relative = path.relative_to(root).as_posix()
            cap = MAX_JOURNAL if relative == "comparison/journal.jsonl" else (
                MAX_FRAGMENT if path.name in ("active.jsonl", "active.stderr") else (
                MAX_ERROR if path.name == "worker-error.json" else 512*1024))
            pin = b.file_pin(path, cap) if path.stat().st_size else dict(filename=path.name,
                bytes=0, sha256=hashlib.sha256(b"").hexdigest())
            total += pin["bytes"]
            b.require(total <= TOTAL_BODY, "joint_evidence_body_limit")
            value["files"].append(dict(path=relative, **pin))
    except Exception as exc:
        value.update(evidence_retention="refused", refusal=type(exc).__name__+":"+str(exc)[:512])
    result = root/"comparison/result.json"
    if result.exists() and value["refusal"] is None:
        try:
            content = json.loads(result.read_text())
            b.require(type(content["retained_sample_rows"]) is int
                and 0 <= content["retained_sample_rows"] <= 252
                and type(content["completed_workers"]) is int
                and 0 <= content["completed_workers"] <= 126
                and content["status"] in ("complete", "refused", "failed", "resource_refused"),
                "comparison_result_schema")
            value["counted_durable_sample_rows"] = content["retained_sample_rows"]
            if content["status"] in ("complete", "refused") \
                    and content["completed_workers"] == 126 and content["retained_sample_rows"] == 252:
                value["actual_samples"] = 252
            value["comparison_status"] = content["status"]
        except Exception as exc:
            value["comparison_status"] = "incomplete"
            value["result_parse_error"] = type(exc).__name__+":"+str(exc)[:512]
    try:
        wheels = list(wheel_root.glob("*/*.whl"))
        b.require(sum(p.stat().st_size for p in wheels) <= b.MAX_WHEEL, "joint_wheel_limit")
        builds = {role: read_build(root/"build"/(role+".json"), role) for role in SOURCES}
        match_builds(builds)
        b.require(len(wheels) == 2 and all(value["identity_outcomes"][r] == "success" for r in SOURCES),
            "two_build_identities_required")
        value["wheels_allowed"] = True
    except Exception as exc:
        value["wheel_refusal"] = type(exc).__name__+":"+str(exc)[:512]
    value, body = encode_owner(value, total, TOTAL_BODY, MAX_OWNER)
    if value["refusal"]:
        value["wheels_allowed"] = False
        value, body = encode_owner(value, 0, TOTAL_BODY, MAX_OWNER)
    (root/"owner.json").write_bytes(body)
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
            stream.write("wheels_allowed="+str(value["wheels_allowed"]).lower()+"\n")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    for name in ("plan-only", "record-measured-build", "controller", "worker", "record-owner"):
        mode.add_argument("--"+name, action="store_true")
    for name in ("output", "controller-root", "measured-root", "wheel-dir", "build",
                 "parent-build", "child-build", "evidence-root", "wheel-root"):
        parser.add_argument("--"+name, type=Path)
    parser.add_argument("--role", choices=tuple(SOURCES))
    parser.add_argument("--case", type=int)
    parser.add_argument("--trial", type=int)
    args = parser.parse_args(argv)
    if args.plan_only:
        b.require(args.output is not None, "plan_output")
        b.write_json(args.output, plan(), b.MAX_PLAN)
        return 0
    if args.record_measured_build:
        b.require(resource is not None and sys.platform == "linux", "Linux_build_record_required")
        b.require(all((args.controller_root, args.measured_root, args.role, args.wheel_dir, args.build)), "build_arguments")
        record_build(args.controller_root, args.measured_root, args.role, args.wheel_dir, args.build)
        return 0
    if args.worker:
        b.require(resource is not None and sys.platform == "linux", "Linux_worker_required")
        b.require(args.role is not None and args.build is not None, "worker_arguments")
        return worker(args.role, args.case, args.trial, args.build)
    if args.record_owner:
        b.require(args.evidence_root and args.wheel_root, "owner_arguments")
        value = record_owner(args.evidence_root, args.wheel_root)
        return 0 if value["refusal"] is None else 2
    if args.controller:
        b.require(all((args.parent_build, args.child_build, args.output)), "controller_arguments")
        controller_limits()
        builds = {"parent": read_build(args.parent_build, "parent"), "child": read_build(args.child_build, "child")}
        match_builds(builds)
        backend = SystemBackend({"parent": args.parent_build, "child": args.child_build})
        result = run_schedule(builds, args.output, backend)
        return 0 if result["status"] == "complete" else 2
    print('{"kind":"PAIRED_CONTEXT_BENCHMARK","status":"disabled"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
