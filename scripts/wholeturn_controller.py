"""Serial hosted owner for the distinct matched whole-turn study.

The owner never imports a simulation/native runtime. Entry functions reject the
deferred candidate before collection, HTTP or process launch. This is an
ordinary trusted opt-in workflow, not the held79d authentication implementation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time
import urllib.request

import wholeturn_build as build
import wholeturn_protocol as p
import wholeturn_state_proof as proof

REPOSITORY = "YotsuBotfds/Chronicler"
REPOSITORY_ID = 1187468861
WORKFLOW = ".github/workflows/matched-wholeturn.yml"


def cpu_seconds():
    own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime+own.ru_stime+children.ru_utime+children.ru_stime


def validate_job_clock(run, jobs, date_header, context, observed_monotonic_ns):
    p.require(type(run["id"]) is int and str(run["id"]) == context["GITHUB_RUN_ID"]
              and run["run_attempt"] == 1 and type(run["run_attempt"]) is int
              and run["head_sha"] == context["GITHUB_SHA"]
              and run["head_branch"] == p.RUN_REF.removeprefix("refs/heads/")
              and run["path"] == WORKFLOW and run["event"] in ("push", "workflow_dispatch")
              and run["status"] == "in_progress" and run["conclusion"] is None
              and run["repository"]["id"] == REPOSITORY_ID, "official current controller run")
    p.require(jobs["total_count"] == len(jobs["jobs"]) == 1, "one current owned job")
    job = jobs["jobs"][0]
    p.require(job["name"] == "wholeturn" and job["run_id"] == run["id"]
              and job["run_attempt"] == 1 and job["head_sha"] == context["GITHUB_SHA"]
              and job["status"] == "in_progress", "official current job")
    server = parsedate_to_datetime(date_header)
    started = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
    p.require(server.tzinfo is not None and started.tzinfo is not None and server >= started,
              "official server/job clock")
    remaining = 7200-(server-started).total_seconds()-2  # explicit HTTP-date rounding safety
    p.require(remaining > 0 and type(observed_monotonic_ns) is int, "job deadline expired")
    return {"job_id": job["id"], "started_at": job["started_at"], "HTTP_Date": date_header,
            "observed_monotonic_ns": observed_monotonic_ns,
            "deadline_monotonic_ns": observed_monotonic_ns+int(remaining*1_000_000_000),
            "actual_controller_context": context,
            "scope": "Official metadata consumed by this ordinary trusted workflow; not old79d launcher admission."}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def official_metadata(context):
    token = os.environ.get("GITHUB_TOKEN")
    p.require(type(token) is str and token, "read-only workflow token required")
    root = "https://api.github.com/repos/"+REPOSITORY+"/actions/runs/"+context["GITHUB_RUN_ID"]
    opener = urllib.request.build_opener(NoRedirect())
    bodies, date = {}, None
    observed = time.monotonic_ns()  # before either request: conservative deadline mapping
    for key, url in (("run", root), ("jobs", root+"/attempts/1/jobs")):
        request = urllib.request.Request(url, headers={"Authorization": "Bearer "+token,
            "Accept": "application/vnd.github+json", "User-Agent": "Chronicler-wholeturn-v1",
            "Cache-Control": "no-cache"})
        with opener.open(request, timeout=30) as response:
            p.require(response.status == 200 and response.geturl() == url, "official metadata origin/status")
            body = response.read(512*1024+1)
            p.require(len(body) <= 512*1024, "official metadata cell bound")
            date = response.headers.get("Date")
        bodies[key] = body
    clock = validate_job_clock(p.strict_json(bodies["run"]), p.strict_json(bodies["jobs"]), date,
                               context, observed)
    return bodies, clock


def memory_observation():
    # Existing strict unified-controller reader; importing it is observation-free.
    from wealth_floor_build_resources import memory_admission
    return memory_admission()


def admission(controller_root, root):
    reg = p.load_registration(controller_root)  # must precede Git/HTTP/collector work
    context = build.github_context(controller_root)
    p.require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "exact repository")
    root = Path(root)
    p.require(root.is_absolute() and not root.exists() and not root.is_symlink(), "new owned runtime root")
    bodies, clock = official_metadata(context)
    p.require(clock["deadline_monotonic_ns"]-time.monotonic_ns() >= (1800+4200+660)*10**9,
              "insufficient remaining build/runtime/publication room")
    root.mkdir(mode=0o700)
    for name in ("raw", "raw/roles", "raw/comparisons", "raw/shared-rng", "metadata", "ordinary"):
        (root/name).mkdir(mode=0o700, exist_ok=True)
    for name, body in bodies.items():
        p.write_new(root/"metadata"/(name+".json"), body, 512*1024)
    value = {"kind": "MATCHED_WHOLETURN_ADMISSION", "protocol": p.PROTOCOL, "github": context,
             "controller_root": str(Path(controller_root).resolve()), "root": str(root.resolve()),
             "registration": p.pin(Path(controller_root)/p.REGISTRATION),
             "drivers": build.driver_pins(controller_root), "job_clock": clock,
             "candidate": reg["candidate"], "root_decision": reg["root_decision"]}
    p.write_new(root/"admission.json", value, 512*1024)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a") as stream:
            stream.write("baseline="+reg["baseline"]["source_commit"]+"\n")
            stream.write("candidate="+reg["candidate"]["source_commit"]+"\n")
    return value


def inventory(root, *, maximum_bytes, maximum_files=5000, hash_bodies=True):
    root = Path(root)
    p.require(root.is_dir() and not root.is_symlink(), "owned directory required")
    rows, visited, total = {}, 0, 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        base = Path(directory)
        p.require(len(base.relative_to(root).parts) <= 64, "inventory depth cap")
        for name in dirs+names:
            path = base/name
            visited += 1
            p.require(visited <= 10000 and not path.is_symlink(), "inventory namespace/entry cap")
            info = path.lstat()
            p.require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), "regular owned tree")
            if stat.S_ISREG(info.st_mode):
                p.require(info.st_nlink == 1, "owned file links")
                total += info.st_size
                p.require(total <= maximum_bytes and len(rows) < maximum_files, "owned output envelope")
                row = {"bytes": info.st_size, "mode": stat.S_IMODE(info.st_mode),
                       "dev": info.st_dev, "ino": info.st_ino}
                if hash_bodies:
                    row.update(p.pin(path, maximum_bytes))
                rows[str(path.relative_to(root))] = row
    return {"files": rows, "file_count": len(rows), "bytes": total}


def group_members(group, exclude):
    """Linux trusted-worker group closure, not namespace/adversarial attestation."""
    members = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == exclude:
            continue
        try:
            raw = (entry/"stat").read_text()
            fields = raw[raw.rfind(")")+2:].split()
            if int(fields[2]) == group:
                members.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return members


def settle_owned_group(group, leader, deadline, *, terminal, members=group_members,
                       kill=os.killpg, now=time.monotonic, pause=time.sleep):
    """Bounded trusted-session observation while leader PID remains reserved.

    A kill request is not quiescence. Unknown/remaining members or an unended
    leader refuse archive/hash/upload; no unsafe namespace is normalized away.
    """
    observations, sent, ended, remaining, error = 0, False, False, None, None
    while True:
        try:
            ended = terminal()
            remaining = members(group, leader)
            observations += 1
            if ended and remaining == []:
                return {"proven": True, "leader_terminal": True, "remaining_members": [],
                        "observations": observations, "kill_requested": sent}
            if not sent:
                try:
                    kill(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                sent = True
        except BaseException as exc:
            error = type(exc).__name__
            if not sent:
                try:
                    kill(group, signal.SIGKILL)
                    sent = True
                except (ProcessLookupError, OSError):
                    pass
            break
        if now() >= deadline:
            break
        pause(min(.02, max(0, deadline-now())))
    return {"proven": False, "leader_terminal": ended, "remaining_members": remaining,
            "observations": observations, "kill_requested": sent, "error": error,
            "scope": "Quiescence UNKNOWN; do not read/move/hash/upload child namespaces."}


class SystemBackend:
    def __init__(self, registration, owner_deadline_ns, output_root):
        self.reg, self.deadline, self.root = registration, owner_deadline_ns, output_root

    def run(self, argv, log, *, wall, cpu):
        maximum = self.reg["limits"]["joint_role_log_bytes"]
        start = time.monotonic()
        end = min(start+wall, self.deadline/1_000_000_000)
        reason, count, process, usage, actual_exit = None, 0, None, None, None
        custody = {"proven": True, "leader_terminal": True, "remaining_members": [],
                   "scope": "No successful Popen return; no owned process established."}
        next_floor_check = 0
        def limits():
            resource.setrlimit(resource.RLIMIT_AS, (4*p.GIB, 4*p.GIB))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_FSIZE, (512*p.MIB, 512*p.MIB))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        env = {k: v for k, v in os.environ.items() if k not in {
            "GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_RUNTIME_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}}
        env.update(PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        env.update({name: "1" for name in ("RAYON_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                   "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS", "GOTO_NUM_THREADS")})
        with Path(log).open("xb") as stream:
            try:
                process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits)
                custody = {"proven": False, "scope": "Popen returned; terminal/group observation pending."}
                os.set_blocking(process.stdout.fileno(), False)
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        # Cleanup is inside the same wall allowance, with up to
                        # two seconds reserved for observed post-kill closure.
                        if time.monotonic() >= end-2:
                            reason = "owned_deadline_cleanup_reserve"
                            break
                        if time.monotonic() >= next_floor_check:
                            memory = memory_observation()
                            spaces = [os.statvfs(self.root), os.statvfs("/tmp")]
                            if memory["available_bytes"] < p.GIB or any(
                                    s.f_bavail*s.f_frsize < 3*p.GIB for s in spaces):
                                reason = "running_memory_or_disk_floor"
                                break
                            next_floor_check = time.monotonic()+1
                        for key, _ in selector.select(.05):
                            block = os.read(key.fd, 16384)
                            if not block:
                                selector.unregister(key.fileobj)
                                continue
                            allowed = max(0, maximum-count)
                            stream.write(block[:allowed])
                            count += min(allowed, len(block))
                            if len(block) > allowed:
                                reason = "joint_log_limit"
                                break
                        if reason:
                            break
                        ended = os.waitid(os.P_PID, process.pid, os.WEXITED|os.WNOHANG|os.WNOWAIT)
                        if ended is not None and not selector.get_map():
                            break
            except BaseException as exc:
                reason = reason or "backend_exception:"+type(exc).__name__
            finally:
                if process is not None:
                    custody = settle_owned_group(process.pid, process.pid, min(end,time.monotonic()+2),
                        terminal=lambda:os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is not None)
                    if custody.get("kill_requested"):
                        reason = reason or "owned_session_required_cleanup"
                    # Never block wait4 on a leader whose exit is unproved.
                    # PID remains reserved until the group observation ends.
                    if custody["leader_terminal"]:
                        try:
                            _, status, usage = os.wait4(process.pid, 0)
                            actual_exit = os.waitstatus_to_exitcode(status)
                            process.returncode = actual_exit
                        except (ChildProcessError, OSError) as exc:
                            custody["proven"] = False
                            reason = reason or "leader_reap_unknown:"+type(exc).__name__
                    if process.stdout is not None:
                        process.stdout.close()
                stream.flush()
                os.fsync(stream.fileno())
        if not custody["proven"]:
            reason = reason or "owned_group_quiescence_unknown"
        return {"actual_exit": actual_exit, "refusal": reason,
                "quiescent": custody["proven"], "custody": custody,
                "wall_seconds": time.monotonic()-start,
                "command_tree_CPU_seconds": usage.ru_utime+usage.ru_stime if usage is not None else None,
                "command_tree_max_RSS_KiB": usage.ru_maxrss if usage is not None else None,
                "log_bytes": count, "log": p.pin(log,maximum) if custody["proven"] else None,
                "process_group_scope": "owned trusted session; no sandbox claim"}


def resources_before(reg, root, *, roles_left, first=False):
    memory = memory_observation()
    space = os.statvfs(root)
    disk = space.f_bavail*space.f_frsize
    required = max(12*p.GIB if first else 0,
                   3*p.GIB+roles_left*512*p.MIB+64*p.MIB)
    p.require(memory["available_bytes"] >= 4*p.GIB and disk >= required and space.f_favail >= 5000,
              "actual visible memory/disk/remaining-output admission")
    # The reused helper observes /proc; /tmp must independently meet original entry floor.
    tmp = os.statvfs("/tmp")
    p.require(tmp.f_bavail*tmp.f_frsize >= (12*p.GIB if first else 3*p.GIB), "tmp floor")
    return {"memory": memory, "output_free_bytes": disk, "remaining_reserved_bytes": required}


def execute(controller_root, root, baseline_file, candidate_file):
    reg = p.load_registration(controller_root)
    context = build.github_context(controller_root)
    root = Path(root).resolve(strict=True)
    admission_record = p.read_json(root/"admission.json", 512*1024)
    p.require(admission_record["github"] == context and admission_record["root"] == str(root)
              and admission_record["registration"] == p.pin(Path(controller_root)/p.REGISTRATION),
              "same admitted source/root")
    # Only this authenticated parent namespace may receive a preflight record.
    stage, arm = "controller_drivers", None
    try:
        p.require(admission_record["drivers"] == build.driver_pins(controller_root), "same admitted source/root")
        stage = "owner_reservation"
        now = time.monotonic_ns()
        p.require(admission_record["job_clock"]["deadline_monotonic_ns"]-now >= (4200+660)*10**9,
                  "complete owner/publication reservation")
        deadline = now+4200*10**9
        stage = "build_records"
        builds = {"baseline": p.read_json(baseline_file, 512*1024), "candidate": p.read_json(candidate_file, 512*1024)}
        stage = "paired_builds"
        build.validate_builds(reg, builds, context, admission_record["drivers"])
        stage = "recheck_build"
        for arm, value in builds.items():
            build.recheck_build(value)
        stage, arm = "owner_setup", None
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        resource.setrlimit(resource.RLIMIT_AS, (4*p.GIB, 4*p.GIB))
        resource.setrlimit(resource.RLIMIT_CPU, (3300, 3300))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        def terminate_owned(signum, _frame):
            signal.signal(signum, signal.SIG_IGN)
            raise TimeoutError("owner termination signal; stop and reap owned session")
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, terminate_owned)
        stage = "backend_prepare"
        backend = SystemBackend(reg, deadline, root)
    except Exception as exc:
        failure = {"kind": "MATCHED_WHOLETURN_EXECUTE_PREFLIGHT_FAILURE", "protocol": p.PROTOCOL,
            "status": "PRE_RUN_SCHEDULE_FAILURE", "github": context,
            "registration": admission_record["registration"], "stage": stage, "arm": arm,
            "build_recheck_stage": getattr(exc, "build_recheck_stage", None),
            "error": {"type": type(exc).__name__, "reason": str(exc)[:512]},
            "pin_failure": getattr(exc, "pin_failure", None), "child_launch_attempted": False,
            "scope": "Admitted parent preflight only; no owner/child custody or role outcome claim."}
        p.write_new(root/"metadata/execute-preflight-failure.json", failure, 65536)
        raise
    return run_schedule(reg, builds, backend, root, controller_root)


def require_profile_plain(prior, summary):
    for field in ("run_config", "effective_flags", "proof"):
        p.require(summary[field] == prior[field], "profile/plain same-source semantic mismatch: "+field)
    for field in ("initial_rng", "final_rng"):
        p.require(proof.same_rng(summary[field], prior[field]), "profile/plain exact RNG mismatch: "+field)


def launch_intent(path, request, kind):
    return p.write_new(path, {"kind":kind,"protocol":p.PROTOCOL,"request":request,
        "status":"CONTROLLER_LAUNCH_INTENT","process_started_proven":False,
        "scope":"Intent precedes backend invocation; proves no process start, ticks or completion."}, 65536)


def run_schedule(reg, builds, backend, root, controller_root, *, observe=resources_before):
    """Injectable orchestration seam; fake contracts never create a process."""
    root, controller_root = Path(root), Path(controller_root)
    requests = p.schedule(reg)
    result = {"kind": "MATCHED_WHOLETURN_OWNER", "protocol": p.PROTOCOL,
              "status": "STARTED", "roles": [{"request": q, "status": "NOT_ATTEMPTED"} for q in requests],
              "comparisons": [], "source_pair": {k: reg[k] for k in ("baseline", "candidate")},
              "raw_custody_proven": True,
              "performance_qualification": None, "scientific_qualification": None}
    start, pairs, hashes, current_ordinary, current_out = time.monotonic(), {}, 0, None, None
    plain42 = {}
    worker = controller_root/"scripts/wholeturn_worker.py"
    try:
        result["entry_resources"] = observe(reg, root, roles_left=12, first=True)
        for request in requests:
            index = request["index"]
            pairs_left = 6-len(result["comparisons"])
            p.budget_room(reg, elapsed_wall=time.monotonic()-start, consumed_CPU=cpu_seconds(),
                          roles_left=12-index, comparisons_left=pairs_left)
            observe(reg, root, roles_left=12-index)
            ordinary = root/"ordinary/current"
            p.require(not ordinary.exists() and not ordinary.is_symlink(), "fresh common ordinary path")
            ordinary.mkdir(mode=0o700)
            out = root/"raw/roles"/str(index)
            out.mkdir(mode=0o700)
            current_ordinary, current_out = ordinary, out
            arm = request["arm"]
            build_file = root/(arm+"-build.json")
            p.write_new(build_file, builds[arm], 512*1024) if not build_file.exists() else None
            command = [builds[arm]["worker_python"], "-B", "-X", "cpu_count=1", str(worker), "role",
                "--controller-root", str(controller_root), "--build", str(build_file), "--index", str(index),
                "--ordinary", str(ordinary), "--output", str(out),
                "--shared-rng", str(root/"raw/shared-rng"/(request["pair"]+".json"))]
            intent = launch_intent(out/"launch-intent.json", request, "ROLE_LAUNCH_INTENT")
            result["roles"][index] = {"request":request,"status":"ATTEMPTED","launch_intent":intent}
            result["raw_custody_proven"] = False
            try:
                actual = backend.run(command, out/"combined.log", wall=300, cpu=240)
            except BaseException as exc:
                result["roles"][index].update(status="FAILED_UNKNOWN_EXIT",actual_exit=None,
                    backend_error={"type":type(exc).__name__,"message":str(exc)[:256]})
                raise
            result["raw_custody_proven"] = actual.get("quiescent") is True
            result["roles"][index] = {"request": request, "actual": actual,
                "launch_intent":intent,
                "status": "FAILED_UNKNOWN_EXIT" if actual["actual_exit"] is None else
                    ("RETURNED" if actual["actual_exit"] == 0 and actual["refusal"] is None else "FAILED")}
            p.require(result["raw_custody_proven"], "worker custody UNKNOWN; no child-namespace archive/hash/upload")
            p.require(actual["actual_exit"] == 0 and actual["refusal"] is None, "first worker failure")
            summary = p.read_json(out/"result.json", 512*1024)
            p.require(summary["request"] == request and summary["proof_complete"], "complete exact role join")
            if request["seed"] == 42:
                key = (request["family"], arm)
                if request["profiled"]:
                    prior = plain42[key]
                    require_profile_plain(prior, summary)
                else:
                    plain42[key] = summary
            owned = inventory(out, maximum_bytes=512*p.MIB, hash_bodies=False)
            ordinary_inventory = inventory(ordinary, maximum_bytes=512*p.MIB-owned["bytes"])
            hashes += ordinary_inventory["bytes"]
            p.require(hashes <= 6*p.GIB, "joint ordinary hashing bound")
            p.write_new(out/"ordinary-inventory.json", ordinary_inventory, 8*p.MIB)
            archived = out/"ordinary"
            p.require(ordinary.stat().st_dev == out.stat().st_dev, "same-filesystem output archive")
            ordinary.rename(archived)
            closed = inventory(archived, maximum_bytes=512*p.MIB, hash_bodies=False)
            expected = {name: {k: row[k] for k in ("bytes", "mode", "dev", "ino")}
                        for name, row in ordinary_inventory["files"].items()}
            p.require(closed["files"] == expected,
                      "post-rename output closure")
            inventory(out, maximum_bytes=512*p.MIB, hash_bodies=False)
            current_ordinary = None
            result["roles"][index].update(status="COMPLETE", result=p.pin(out/"result.json", 512*1024))
            key = request["pair"]
            pairs.setdefault(key, []).append(index)
            if len(pairs[key]) == 2:
                left, right = pairs[key]
                compare_dir = root/"raw/comparisons"/key
                compare_dir.mkdir(mode=0o700)
                output = compare_dir/"result.json"
                command = [builds["baseline"]["worker_python"], "-B", str(worker), "compare",
                    "--controller-root", str(controller_root), "--build", str(root/"baseline-build.json"),
                    "--left", str(root/"raw/roles"/str(left)/"result.json"),
                    "--right", str(root/"raw/roles"/str(right)/"result.json"),
                    "--left-ordinary", str(root/"raw/roles"/str(left)/"ordinary"),
                    "--right-ordinary", str(root/"raw/roles"/str(right)/"ordinary"), "--output", str(output)]
                intent = launch_intent(compare_dir/"launch-intent.json", {"pair":key,"left":left,"right":right}, "PAIR_LAUNCH_INTENT")
                comparison={"pair":key,"status":"ATTEMPTED","launch_intent":intent}
                result["comparisons"].append(comparison)
                result["raw_custody_proven"] = False
                try:
                    actual = backend.run(command, compare_dir/"combined.log", wall=60, cpu=40)
                except BaseException as exc:
                    comparison.update(status="FAILED_UNKNOWN_EXIT",actual_exit=None,
                        backend_error={"type":type(exc).__name__,"message":str(exc)[:256]})
                    raise
                result["raw_custody_proven"] = actual.get("quiescent") is True
                comparison.update(actual=actual,status="RETURNED" if actual["actual_exit"] is not None else "FAILED_UNKNOWN_EXIT")
                p.require(result["raw_custody_proven"], "comparison custody UNKNOWN; no child-namespace archive/hash/upload")
                comparison["result"] = p.pin(output, p.MIB) if output.exists() else None
                p.require(actual["actual_exit"] == 0 and actual["refusal"] is None, "first comparison failure")
            inventory(root/"raw", maximum_bytes=reg["limits"]["aggregate_output_bytes"], hash_bodies=False)
        p.require(len(result["comparisons"]) == 6, "complete fixed comparisons")
        result["status"] = "COMPLETE_DATA_WITH_ALL_REGRESSIONS"
    except BaseException as exc:
        result["status"] = "FIRST_FAILURE_NO_REPLAY"
        result["error"] = {"type": type(exc).__name__, "message": str(exc)[:512]}
    finally:
        # Retain the first incomplete ordinary tree too; it must not vanish
        # merely because the producer exited before its normal inventory.
        if not result["raw_custody_proven"]:
            result["custody_scope"] = "UNKNOWN: child namespaces remain in place, unread/unhashed; raw upload refused. Parent owner/intents only."
            result["unsafe_namespaces"] = ["raw/roles", "raw/comparisons", "raw/shared-rng", "ordinary"]
        elif current_ordinary is not None and current_ordinary.exists():
            try:
                current_ordinary.rename(current_out/"ordinary-partial")
                result["partial_ordinary_retained"] = str(current_out.relative_to(root/"raw"))+"/ordinary-partial"
            except BaseException as exc:
                result["partial_archive_error"] = type(exc).__name__
                result["unarchived_partial_root"] = str(current_ordinary)
                result["status"] = "FIRST_FAILURE_NO_REPLAY"
        result["ordinary_bytes_hashed"] = hashes
        result["owner_wall_seconds"] = time.monotonic()-start
        result["owner_self_plus_waited_CPU_seconds"] = cpu_seconds()
        result["controller_native_modules"] = [n for n in sys.modules if n == "chronicler_agents" or n.startswith("chronicler_agents.")]
        if result["controller_native_modules"] or result["owner_self_plus_waited_CPU_seconds"] > 3300 or result["owner_wall_seconds"] > 4200:
            result["status"] = "FIRST_FAILURE_NO_REPLAY"
        if result["raw_custody_proven"]:
            try:
                p.require(not (root/"ordinary/current").exists(), "unarchived ordinary namespace; upload refused")
                for role in result["roles"]:
                    path=root/"raw/roles"/str(role["request"]["index"])
                    if path.exists():
                        inventory(path,maximum_bytes=512*p.MIB,hash_bodies=False)
                result["final_raw_inventory"] = inventory(root/"raw", maximum_bytes=reg["limits"]["aggregate_output_bytes"]-2*p.MIB, hash_bodies=False)
                result["final_retained_inventory"] = inventory(root, maximum_bytes=reg["limits"]["aggregate_output_bytes"]-2*p.MIB, hash_bodies=False)
            except BaseException as exc:
                result["final_inventory_error"] = {"type": type(exc).__name__, "message": str(exc)[:256]}
                result["status"] = "FIRST_FAILURE_NO_REPLAY"
        result["raw_upload_allowed"] = result["raw_custody_proven"] and "final_retained_inventory" in result and "final_inventory_error" not in result
        p.write_new(root/"raw/owner.json", result, 2*p.MIB)
    return 0 if result["status"] == "COMPLETE_DATA_WITH_ALL_REGRESSIONS" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "admit", "execute"))
    parser.add_argument("--controller-root", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--baseline-build", type=Path)
    parser.add_argument("--candidate-build", type=Path)
    args = parser.parse_args(argv)
    if args.command == "plan":
        reg = p.load_registration(args.controller_root, ready=False)
        print(p.canonical({"candidate_deferred": reg["candidate"], "schedule": p.schedule(reg)}).decode(), end="")
        return 0
    p.load_registration(args.controller_root)
    if args.command == "admit":
        admission(args.controller_root, args.root)
        return 0
    return execute(args.controller_root, args.root, args.baseline_build, args.candidate_build)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except p.Refused as exc:
        print("WHOLETURN_REFUSED: "+str(exc), file=sys.stderr)
        if getattr(exc, "pin_failure", None) is not None:
            print("WHOLETURN_PIN_FAILURE: "+p.canonical(exc.pin_failure).decode().rstrip("\n"), file=sys.stderr)
        raise SystemExit(2)
