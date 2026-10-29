#!/usr/bin/env python3
"""Inactive, fixed natural-research study adapter; activation is a separate decision.

The controller and selected producer are separate clean roots. No production
module is imported until its exact registered root has been selected.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from copy import deepcopy
import importlib
import importlib.machinery
import os
from pathlib import Path
import random
import resource
import shutil
import signal
import subprocess
import sys
import time

import research_natural_contract as C

SCRIPT = Path(__file__).resolve()
CONTROL = SCRIPT.parents[1]
_EXCLUSIVE_OWNER = None


def runtime(source):
    source = Path(source).resolve()
    if "chronicler" not in sys.modules:
        sys.path.insert(0, str(source / "src"))
    else:
        require_path = Path(sys.modules["chronicler"].__file__).resolve().parent
        C.require(require_path == source / "src/chronicler", "a different producer was already imported")
    from chronicler.batch_manifest import environment_identity, native_identity, source_identity
    import chronicler_agents as public
    compiled = importlib.import_module("chronicler_agents.chronicler_agents")
    origin = Path(compiled.__file__).resolve()
    C.require(str(origin).endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)), "native origin is not compiled")
    classes = {}
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(public, name)
        C.require(type(cls) is type and cls is getattr(compiled, name), "native class export is not compiled")
        version, fingerprint, schema = cls.checkpoint_schema()
        classes[name] = dict(version=version, fingerprint=fingerprint,
                             schema_sha256=C.hashlib.sha256(schema.encode()).hexdigest())
    actual = dict(source=source_identity(), native=native_identity(), environment=environment_identity(),
                  compiled_origin=str(origin), available_compiled_classes=classes)
    C.require(actual["source"]["git_sha"] == C.SOURCE and
              Path(actual["source"]["package_dir"]).resolve() == source / "src/chronicler", "actual producer differs")
    C.require(actual["native"]["sha256"] == C.NATIVE and actual["native"]["module_file"] == str(origin), "native binary differs")
    env = actual["environment"]
    C.require(env["affinity_cpu_count"] == 1 and all(env["thread_env"].get(k) == "1" for k in C.THREADS)
              and env["thread_env"].get("PYTHON_CPU_COUNT") == "1"
              and env["thread_env"].get("PYTHONHASHSEED") == "0", "one CPU/thread/hash-seed environment required")
    return actual


def identity(source):
    source = Path(source).resolve()
    C.require(source != CONTROL, "producer and control roots must be separate")
    return dict(schema_version=1, kind="natural-research-continuation-freeze", producer=C.source_snapshot(source, C.SOURCE),
        control=C.source_snapshot(CONTROL), runtime=runtime(source),
        controls={name: C.sha(CONTROL / name) for name in C.CONTROL_FILES})


def verify_freeze(source, path):
    frozen = C.read(path)
    C.require(C.same(frozen, identity(source)), "producer/control/native/environment changed from prospective freeze")
    return frozen


def simulation_args(folder, seed, role):
    args = ["--seed", str(seed), "--turns", str(C.END), "--worldgen", "template", "--regions", "8", "--civs", "4",
        "--agents", "hybrid", "--simulate-only", "--scholarship", "--techniques", "--scientific-claims",
        "--scientific-research-agendas", "--no-health-care", "--no-harvest-forecasts", "--no-ritual-gatherings",
        "--no-transaction-receipts", "--validation-sidecar", "--output", str(folder / "chronicle.md"),
        "--state", str(folder / "state.json"), "--checkpoint-turns", "60,180" if role == "parent" else "180"]
    return args


def request(seed, role, registration, parent=None):
    controls = dict(C.CONTROLS)
    if role != "parent":
        controls["research_enabled"] = role == "active"
    value = dict(schema_version=1, experiment=C.EXPERIMENT, cohort="development", feature="scientific_claims",
        arm=role, controls=controls, fork=role != "parent", registration=registration)
    if parent is not None:
        value["parent_checkpoint"] = dict(path=str(parent.resolve()), sha256=C.sha(parent))
    return value


def rng_state():
    import numpy as np
    p, n = random.getstate(), np.random.get_state()
    return dict(python=[p[0], list(p[1]), p[2]], numpy=[n[0], n[1].tolist(), *n[2:]])


def restore_rng(value):
    import numpy as np
    C.validate_rng_json(value)
    p, n = value["python"], value["numpy"]
    python_value = (p[0], tuple(p[1]), p[2])
    numpy_value = (n[0], np.array(n[1], dtype=np.uint32), *n[2:])
    # Validate both before either module global is mutated.
    random.Random(0).setstate(python_value)
    np.random.RandomState(0).set_state(numpy_value)
    random.setstate(python_value)
    np.random.set_state(numpy_value)
    C.require(C.same(rng_state(), value), "external RNG restoration is not lossless")


class BoundaryCapture:
    """Read-only existing turn-boundary hook, after reflection/checkpoint writing."""
    def __init__(self, folder, frozen):
        self.folder, self.frozen, self.captured = folder, frozen, False

    def bind(self, save, config):
        self.config = config
        C.require(config["simulation_args"]["scientific_research_agendas"] is True, "research not active before first tick")
        C.require(config["expansion_experiment"]["controls_after"] == C.CONTROLS, "v2 controls not applied before bind/first tick")

    def live_record(self):
        return None

    def turn_end(self, world):
        if world.turn == C.FORK:
            C.require(not self.captured, "boundary RNG captured twice")
            parent = self.folder / f"checkpoint_turn_{C.FORK}.ckpt"
            header, sections = C.checkpoint_sections(parent)
            C.require(header["turn"] == C.FORK and header["seed"] == world.seed and header["exact"] is True,
                      "RNG callback did not follow the actual exact checkpoint")
            before = rng_state()
            C.write(self.folder / "boundary-rng.json", dict(schema_version=1, seed=world.seed, turn=C.FORK,
                checkpoint_sha256=C.sha(parent), checkpoint_sections=sections,
                producer_runtime=self.frozen["runtime"], controls_sha256=C.digest(self.frozen["controls"]),
                state=before, state_sha256=C.digest(before),
                clock="turn_boundary.turn_end after scheduled checkpoint/reflection; before source60"))
            C.require(C.same(before, rng_state()), "observing boundary RNG changed its state")
            self.captured = True
        return False


def native_records(loaded, path, folder=None):
    import chronicler_agents as native
    header, sections = C.checkpoint_sections(path)
    C.require(header == loaded.header, "loaded checkpoint header differs")
    actual = {}
    for field, attr, cls, kind in (("agent_bridge", "_sim", "AgentSimulator", "agent"),
            ("ecology_runtime", None, "EcologySimulator", "ecology"),
            ("politics_runtime", None, "PoliticsSimulator", "politics")):
        obj = getattr(loaded.state, field)
        if obj is None:
            continue
        obj = getattr(obj, attr) if attr else obj
        name = "native." + kind + ".0"
        C.require(type(obj) is getattr(native, cls) and name in sections, "active native class/section differs")
        raw = bytes(obj.checkpoint_state())
        C.require(C.hashlib.sha256(raw).hexdigest() == sections[name]["sha256"], "restored native bytes differ")
        version, fingerprint, schema = obj.checkpoint_schema()
        actual[name] = dict(**sections[name], class_name=cls, version=version, fingerprint=fingerprint,
                            schema_sha256=C.hashlib.sha256(schema.encode()).hexdigest())
        if folder is not None:
            with (folder / (name + "-final.bin")).open("xb") as stream:
                stream.write(raw)
    C.require(set(actual) == {k for k in sections if k.startswith("native.")} == {"native.agent.0"},
              "hybrid native section set differs")
    return actual


def worker(options):
    resource.setrlimit(resource.RLIMIT_CPU, (C.WORKER_CPU, C.WORKER_CPU))
    resource.setrlimit(resource.RLIMIT_FSIZE, (C.MAX_METADATA, C.MAX_METADATA))
    source, root = Path(options.source_root).resolve(), Path(options.output_root).resolve()
    frozen = verify_freeze(source, options.freeze)
    import numpy as np
    from chronicler import main
    from chronicler.bundle_codec import load_bundle, same
    from chronicler.run_checkpoint import read_checkpoint
    from chronicler.scientific_research import validate_state
    folder = root / f"seed-{options.seed}" / options.role
    parent_path = root / f"seed-{options.seed}/parent/checkpoint_turn_{C.FORK}.ckpt"
    registration = dict(path=str((CONTROL / C.REGISTRATION).resolve()), sha256=frozen["controls"][C.REGISTRATION])
    cli = simulation_args(folder, options.seed, options.role)
    parser = main._build_parser()
    args = parser.parse_args(cli)
    loaded, parent_record, boundary = None, None, None
    before, started = rng_state(), time.monotonic()
    try:
        if options.role == "parent":
            random.seed(options.seed)
            np.random.seed(options.seed)
            C.write(folder / "initial-rng.json", dict(seed=options.seed, state=rng_state()))
            boundary = BoundaryCapture(folder, frozen)
        else:
            loaded = read_checkpoint(parent_path)
            C.require(loaded.exact and loaded.state.world.turn == C.FORK and loaded.state.world.seed == options.seed,
                      "parent is not compatible exact boundary")
            validate_state(loaded.state.world)
            parent_record = dict(checkpoint_sha256=C.sha(parent_path), header=loaded.header,
                native_sections=native_records(loaded, parent_path),
                world=loaded.state.world.model_dump(mode="json"),
                history=[h.model_dump(mode="json") for h in loaded.state.history],
                run_config=deepcopy(loaded.state.run_config))
            C.write(folder / "restore.json", parent_record)
            C.require(not main._adopt_checkpoint_args(parser, args, loaded), "saved/CLI configuration conflicts")
            rng = C.read(parent_path.parent / "boundary-rng.json")
            C.require(rng["checkpoint_sha256"] == parent_record["checkpoint_sha256"]
                      and rng["turn"] == C.FORK and rng["seed"] == options.seed
                      and C.same(rng["producer_runtime"], frozen["runtime"])
                      and rng["controls_sha256"] == C.digest(frozen["controls"])
                      and rng["state_sha256"] == C.digest(rng["state"]), "external boundary RNG provenance differs")
            restore_rng(rng["state"])
            C.write(folder / "restored-rng.json", dict(sidecar_sha256=C.sha(parent_path.parent / "boundary-rng.json"),
                state_sha256=C.digest(rng_state()), scope="explicit external sidecar restoration, not RunState checkpoint"))
        experiment = request(options.seed, options.role, registration, parent_path if loaded else None)
        C.write(folder / "request.json", experiment)
        main.execute_run(args, checkpoint_resume=loaded, expansion_experiment=experiment, turn_boundary=boundary)
        final_rng = rng_state()
        final_path = folder / f"checkpoint_turn_{C.END}.ckpt"
        final = read_checkpoint(final_path)
        validate_state(final.state.world)
        C.require(final.state.world.turn == C.END, "worker ended before registered horizon")
        C.require(final.header["exact"] is (options.role == "parent"), "declared fork exact label differs")
        native = native_records(final, final_path, folder)
        history = [h.model_dump(mode="json") for h in final.state.history]
        C.write(folder / "raw-history.json", history)
        world = final.state.world.model_dump(mode="json")
        science = world["scientific_claims"]
        bundle = load_bundle(folder / "chronicle_bundle.json")
        C.require(len(history) == C.END and [h["turn"] for h in history] == list(range(1, C.END + 1)), "ordinary history coverage differs")
        C.require(same(world["scientific_claims"], bundle["world_state"]["scientific_claims"]), "bundle science differs from checkpoint")
        receipt = bundle["metadata"]["expansion_experiment"]
        C.require(receipt == final.state.run_config["expansion_experiment"], "experiment receipt differs")
        pause = None
        if parent_record:
            C.require(C.same(history[:C.FORK], parent_record["history"]), "raw history prefix changed")
            prefix_events = parent_record["world"]["events_timeline"]
            C.require(C.same(world["events_timeline"][:len(prefix_events)], prefix_events), "event prefix changed")
            if options.role == "pause_new_trials":
                pause = C.pause_archive(parent_record["world"]["scientific_claims"], science)
        if boundary:
            C.require(boundary.captured, "parent did not capture actual RNG checkpoint boundary")
        C.write(folder / "worker-summary.json", dict(schema_version=1, seed=options.seed, role=options.role,
            execution_complete=True, actual_physics_ticks=C.END if options.role == "parent" else C.END - C.FORK,
            final_turn=C.END, native_sections=native, final_rng=final_rng, final_rng_sha256=C.digest(final_rng),
            parent_checkpoint_sha256=C.sha(parent_path) if loaded else None,
            run_config=final.state.run_config, header=final.header, experiment_receipt=receipt,
            raw_history_sha256=C.digest(history), raw_world_sha256=C.digest(world),
            pause=pause, exposure=C.exposure(science, history),
            seconds=time.monotonic() - started))
    finally:
        after = verify_freeze(source, options.freeze)
        C.write(folder / "worker-identity.json", dict(before=frozen, after=after,
            identities_stable=C.same(frozen, after), initial_global_rng_sha256=C.digest(before)))


def memory_available():
    """Observed host and visible cgroup-v2 headroom; unknown constraints refuse."""
    rows = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(rows["MemAvailable"].strip().split()[0]) * 1024
    entries = [line.split(":", 2) for line in Path("/proc/self/cgroup").read_text().splitlines()]
    unified = [line[2] for line in entries if line[:2] == ["0", ""]]
    C.require(len(unified) == 1, "visible unified cgroup required for resource accounting")
    cg = Path("/sys/fs/cgroup")
    raw = unified[0]
    C.require(raw.startswith("/") and ".." not in Path(raw).parts and cg.is_dir(), "unsupported cgroup mount mapping")
    leaf = cg / raw.lstrip("/")
    C.require(leaf.is_dir(), "actual cgroup leaf is not visible")
    observations = []
    while True:
        maximum, current = leaf / "memory.max", leaf / "memory.current"
        if maximum.exists() and current.exists():
            limit, used = maximum.read_text().strip(), int(current.read_text().strip())
            C.require(used >= 0, "invalid cgroup memory usage")
            if limit != "max":
                available = min(available, max(0, int(limit) - used))
            observations.append(dict(path=str(leaf), maximum=limit, current=used))
        else:
            C.require(leaf == cg and not maximum.exists() and not current.exists(), "partial/missing nonroot cgroup memory data")
            observations.append(dict(path=str(leaf), maximum="true-hierarchy-root-unbounded", current=None))
        if leaf == cg:
            break
        leaf = leaf.parent
    return dict(available=available, cgroups=observations)


def resources(root, admission=False):
    disk = shutil.disk_usage(root).free
    memory = memory_available()
    files, size = 0, 0
    for path in root.rglob("*"):
        C.require(not path.is_symlink(), "output link appeared during execution")
        if path.is_file():
            files += 1
            size += path.stat().st_size
    C.require(files <= C.MAX_FILES and size <= C.MAX_BYTES, "evidence budget crossed")
    C.require(disk >= (6 if admission else 3) * 1024**3, "registered disk floor not met")
    C.require(memory["available"] >= (2 if admission else 1) * 1024**3, "registered RAM floor not met")
    return dict(free_disk=disk, memory=memory, evidence_bytes=size, evidence_files=files)


def process_record(pid):
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return None
    values = raw[raw.rfind(")") + 2:].split()
    return dict(pid=pid, state=values[0], ppid=int(values[1]), pgrp=int(values[2]), session=int(values[3]),
                cpu_ticks=sum(int(values[i]) for i in (11, 12, 13, 14)), start_ticks=int(values[19]))


def owned_group(pid):
    return [row for path in Path("/proc").iterdir() if path.name.isdecimal()
            and (row := process_record(int(path.name))) and row["pgrp"] == row["session"] == pid and row["state"] != "Z"]


def owned_tree(pid, known):
    """Retain birth identities, including descendants which create another session.

    Linux /proc is sampled, so CPU limits have bounded polling granularity; no
    per-process RLIMIT is presented as an aggregate descendant limit.
    """
    C.require(_EXCLUSIVE_OWNER == os.getpid(), "exclusive child ownership lease is not active")
    rows = {int(path.name): row for path in Path("/proc").iterdir() if path.name.isdecimal()
            and (row := process_record(int(path.name)))}
    selected = {number: row for number, row in rows.items()
                if known.get(number) == row["start_ticks"]}
    for number in known.keys() & rows.keys():
        C.require(known[number] == rows[number]["start_ticks"],
                  "process group identity cannot be established; refusing numeric-PID reuse")
    # The still-live leased leader anchors descendants before their first sample.
    # A leader can exit before its first /proc observation. The exclusive
    # subreaper ownership lease still anchors every remaining direct orphan.
    if pid in rows and pid not in known and rows[pid]["ppid"] == os.getpid():
        leader = rows[pid]
        C.require(leader["pgrp"] == leader["session"] == pid,
                  "unobserved worker leader is outside its fresh session")
        known[pid] = leader["start_ticks"]
        selected[pid] = leader
    # The controller is an exclusive child subreaper. Descendants which orphan
    # before any sample, even after setsid(), become our direct children.
    selected.update({number: row for number, row in rows.items() if row["ppid"] == os.getpid()})
    while True:
        added = {number: row for number, row in rows.items()
                 if number not in selected and row["ppid"] in selected}
        if not added:
            break
        selected.update(added)
    known.update({number: row["start_ticks"] for number, row in selected.items()})
    return list(selected.values())


def direct_children():
    return [row for path in Path("/proc").iterdir() if path.name.isdecimal()
            and (row := process_record(int(path.name))) and row["ppid"] == os.getpid()]


@contextmanager
def exclusive_subreaper():
    """Own transient orphan descendants before the first worker can fork."""
    global _EXCLUSIVE_OWNER
    C.require(_EXCLUSIVE_OWNER is None and sys.platform == "linux" and not direct_children(),
              "exclusive Linux child ownership required before worker launch")
    libc = ctypes.CDLL(None, use_errno=True)
    prior = ctypes.c_int()
    C.require(libc.prctl(37, ctypes.byref(prior), 0, 0, 0) == 0 and
              libc.prctl(36, 1, 0, 0, 0) == 0, "Linux child subreaper setup failed")
    _EXCLUSIVE_OWNER = os.getpid()
    try:
        yield
    finally:
        # Refuse to silently release an ownership lease with unreaped children.
        C.require(not direct_children(), "subreaper still owns descendants after cleanup")
        C.require(libc.prctl(36, prior.value, 0, 0, 0) == 0, "child subreaper restoration failed")
        _EXCLUSIVE_OWNER = None


def cleanup(child, known):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        members = owned_group(child.pid)
        for row in members:
            if row["pid"] in known:
                C.require(known[row["pid"]] == row["start_ticks"],
                      "process group identity cannot be established; refusing numeric-PID reuse")
        deadline = time.monotonic() + 5
        while True:
            members = [row for row in owned_tree(child.pid, known) if row["state"] != "Z"]
            if not members:
                break
            for row in reversed(members):
                try:
                    pinned = os.pidfd_open(row["pid"], 0)
                except ProcessLookupError:
                    continue
                try:
                    current = process_record(row["pid"])
                    C.require(current is None or current["start_ticks"] == known[row["pid"]],
                              "owned process birth changed during cleanup")
                    try:
                        signal.pidfd_send_signal(pinned, sig)
                    except ProcessLookupError:
                        pass
                finally:
                    os.close(pinned)
            if time.monotonic() >= deadline:
                break
            time.sleep(.025)
        while True:
            try:
                waited, status, usage = os.wait4(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not waited:
                break
            if waited == child.pid:
                child.returncode = os.waitstatus_to_exitcode(status)
    C.require(not owned_tree(child.pid, known), "owned process tree cleanup incomplete")
    child.wait(timeout=5)


@contextmanager
def interruption_guard():
    """Turn termination into stack unwinding so the controller owns cleanup."""
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    def interrupted(signum, frame):
        # One interruption stops the fixed sequence. Repeated terminal signals
        # must not cut through owned-child cleanup or its negative receipt.
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        raise InterruptedError("controller interrupted by signal " + str(signum))
    for sig in previous:
        signal.signal(sig, interrupted)
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def supervise(child, known, aggregate_cpu, resource_guard, controller_started, worker_started,
              *, worker_cpu=C.WORKER_CPU, aggregate_limit=C.AGGREGATE_CPU,
              worker_wall=C.WORKER_WALL, aggregate_wall=C.AGGREGATE_WALL):
    """Observe the whole leased tree, and reap with exact leader/waited usage."""
    peak_cpu, reaped_cpu = 0.0, 0.0
    leader_done = child.returncode is not None
    while True:
        resource_guard()
        members = owned_tree(child.pid, known)
        live_cpu = sum(row["cpu_ticks"] for row in members) / os.sysconf("SC_CLK_TCK")
        peak_cpu = max(peak_cpu, reaped_cpu + live_cpu)
        C.require(peak_cpu <= worker_cpu, "worker process-tree CPU budget crossed")
        C.require(aggregate_cpu() + live_cpu <= aggregate_limit, "aggregate CPU budget crossed")
        now = time.monotonic()
        C.require(now - controller_started <= aggregate_wall and now - worker_started <= worker_wall,
                  "wall budget crossed")
        while True:
            try:
                waited, status, usage = os.wait4(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not waited:
                break
            reaped_cpu += usage.ru_utime + usage.ru_stime
            if waited == child.pid:
                child.returncode = os.waitstatus_to_exitcode(status)
                leader_done = True
        remaining = owned_tree(child.pid, known)
        remaining_cpu = sum(row["cpu_ticks"] for row in remaining) / os.sysconf("SC_CLK_TCK")
        peak_cpu = max(peak_cpu, reaped_cpu + remaining_cpu)
        C.require(peak_cpu <= worker_cpu, "worker process-tree CPU budget crossed at exit")
        C.require(aggregate_cpu() + remaining_cpu <= aggregate_limit, "aggregate CPU budget crossed at exit")
        C.require(not leader_done or not remaining, "worker exited leaving owned descendants")
        if leader_done:
            return dict(returncode=child.returncode, tree_cpu_seconds=peak_cpu,
                        accounting="exclusive Linux subreaper; proc own+waited CPU; all wait4 exits; 50ms polling")
        time.sleep(.05)


def verify_active_before_further_launches(root, source, seed, frozen):
    """Run the same detached strict check before pause or the next seed."""
    import read_research_natural_continuation as reader
    decode, strict, prune = reader.codec(source, frozen)
    parent = reader.inspect_role(root, seed, "parent", frozen, decode, prune)
    active = reader.inspect_role(root, seed, "active", frozen, decode, prune)
    compared = reader.active_identity(parent, active, strict)
    C.write(root / f"seed-{seed}/active-noop.json", compared)
    C.require(compared["file_set_equal"] and all(compared["files"].values()) and
              all(compared[key] for key in ("raw_world_equal", "raw_history_equal", "actual_native_sections_equal",
                                            "final_external_global_rng_equal")),
              "active no-op continuation identity failed; further launches refused")


def publish_execution(root, value, cpu, started, guard):
    """Serialize/hash the large provisional payload before final accounting."""
    root = Path(root)
    try:
        C.write(root / "execution.json", value)
        guard()
        payload_hash = C.sha(root / "execution.json")
        guard()
        measured = cpu()
        charged = measured + 1.0
        C.require(charged <= C.AGGREGATE_CPU, "final accounting reserve exceeds unchanged aggregate CPU budget")
        receipt = dict(schema_version=1, kind="natural-research-execution-receipt",
            publication_complete=True, execution_sha256=payload_hash,
            measured_to_seal_cpu_seconds=measured, finalization_cpu_reserve_seconds=1.0,
            charged_aggregate_cpu_seconds=charged, aggregate_wall_seconds=time.monotonic() - started,
            controller_started_monotonic=started, boot_id=value["boot_id"])
        def final_guard():
            guard()
            C.require(cpu() <= charged, "final accounting publication exceeded charged CPU reserve")
        C.write(root / "pending-execution-receipt.json", receipt)
        final_guard()
        os.replace(root / "pending-execution-receipt.json", root / "execution-receipt.json")
        final_guard()
        return True
    except BaseException:
        for name in ("execution-receipt.json", "pending-execution-receipt.json", "execution.json"):
            path = root / name
            if path.exists():
                os.replace(path, root / ("incomplete-" + name))
        raise


def run(options):
    own0, children0 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    initial_cpu = own0.ru_utime + own0.ru_stime + children0.ru_utime + children0.ru_stime
    root = Path(options.output_root).resolve()
    try:
        with exclusive_subreaper(), interruption_guard():
            code = _run(options)
        if code == 0:
            receipt = C.read(root / "execution-receipt.json")
            own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
            final_cpu = own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime - initial_cpu
            C.require(final_cpu <= receipt["charged_aggregate_cpu_seconds"] <= C.AGGREGATE_CPU and
                      time.monotonic() - receipt["controller_started_monotonic"] <= C.AGGREGATE_WALL,
                      "controller finalization exceeded charged aggregate budget")
        return code
    except BaseException:
        # Handler/subreaper restoration is part of the successful transaction.
        # An exception there must not leave a valid positive accounting seal.
        path = root / "execution-receipt.json"
        if path.exists():
            target = root / "incomplete-finalization-execution-receipt.json"
            C.require(not target.exists(), "refusing to overwrite retained incomplete execution receipt")
            os.replace(path, target)
        raise


def _run(options):
    started = time.monotonic()
    cpu0 = resource.getrusage(resource.RUSAGE_SELF)
    child0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    initial_cpu = cpu0.ru_utime + cpu0.ru_stime + child0.ru_utime + child0.ru_stime
    def cpu():
        own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime - initial_cpu
    source, root = Path(options.source_root).resolve(), Path(options.output_root).resolve()
    C.require(not root.exists() and all(not root.is_relative_to(path) for path in (source, CONTROL)), "fresh external evidence root required")
    root.mkdir(parents=True)
    rows, error, child = [], None, None
    frozen = None
    try:
        frozen = verify_freeze(source, options.freeze)
        C.write(root / "freeze.json", frozen)
        C.write(root / "admission.json", resources(root, admission=True))
        halted = False
        for seed in C.SEEDS:
            for role in C.ROLES:
                record = dict(seed=seed, role=role, status="not_attempted_after_failure")
                if halted:
                    rows.append(record)
                    continue
                if cpu() + C.WORKER_CPU > C.AGGREGATE_CPU or time.monotonic() - started >= C.AGGREGATE_WALL:
                    record["status"] = "budget_censored"
                    rows.append(record)
                    halted = True
                    continue
                folder = root / f"seed-{seed}" / role
                folder.mkdir(parents=True)
                C.write(folder / "launch-resources.json", resources(root))
                command = [sys.executable, "-B", str(SCRIPT), "worker", "--source-root", str(source),
                    "--freeze", str(Path(options.freeze).resolve()), "--output-root", str(root), "--seed", str(seed), "--role", role]
                worker_started = time.monotonic()
                known = {}
                try:
                    with (folder / "worker.log").open("xb") as log:
                        child = subprocess.Popen(command, cwd=CONTROL, stdin=subprocess.DEVNULL, stdout=log,
                            stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
                        lease = process_record(child.pid)
                        if lease is not None:
                            C.require(lease["pgrp"] == lease["session"] == child.pid, "worker session lease unavailable")
                            known[child.pid] = lease["start_ticks"]
                        C.write(folder / "process-lease.json", dict(leader=lease,
                            ownership="exclusive Linux child subreaper established before launch",
                            leader_pid=child.pid, initial_birth_observed=lease is not None))
                        accounting = supervise(child, known, cpu, lambda: resources(root), started, worker_started)
                    code = accounting["returncode"]
                    cleanup(child, known)
                    C.write(folder / "cleanup.json", dict(complete=True, identities=known, accounting=accounting))
                    C.require(code == 0, "worker exited unsuccessfully")
                    summary = C.read(folder / "worker-summary.json")
                    C.require(summary["execution_complete"] is True and summary["final_turn"] == C.END, "worker completion not verified")
                    if role == "active":
                        verify_active_before_further_launches(root, source, seed, frozen)
                        resources(root)
                        C.require(cpu() <= C.AGGREGATE_CPU and time.monotonic() - started <= C.AGGREGATE_WALL,
                                  "active no-op readout exceeded aggregate budget")
                    record.update(status="complete", returncode=code, tree_cpu_seconds=accounting["tree_cpu_seconds"])
                except BaseException as exc:
                    record.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
                    if child is not None:
                        try:
                            cleanup(child, known)
                        except BaseException as cleanup_error:
                            record["cleanup_error"] = str(cleanup_error)
                    halted = True
                finally:
                    child = None
                record["elapsed_seconds"] = time.monotonic() - worker_started
                rows.append(record)
                C.write(root / f"progress-{len(rows):02d}.json", rows)
        verify_freeze(source, options.freeze)
        resources(root)
        C.require(cpu() <= C.AGGREGATE_CPU and time.monotonic() - started <= C.AGGREGATE_WALL, "final aggregate budget crossed")
    except BaseException as exc:
        error = dict(type=type(exc).__name__, message=str(exc))
    complete = error is None and len(rows) == 24 and all(row["status"] == "complete" for row in rows)
    try:
        files = C.inventory(root)
    except Exception as exc:
        files = None
        complete = False
        error = dict(type=type(exc).__name__, message="Final bounded inventory refused: " + str(exc))
    if cpu() > C.AGGREGATE_CPU or time.monotonic() - started > C.AGGREGATE_WALL:
        complete = False
        error = dict(type="ResourceCensoring", message="Final inventory/identity exceeded aggregate budget")
    execution = dict(schema_version=1, kind="natural-research-continuation-execution",
        execution_complete=complete, qualified=False, scientific_standing="readout_required" if complete else "incomplete_or_censored",
        controller_started_monotonic=started, boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        freeze_sha256=C.sha(options.freeze), source_sha=C.SOURCE, control_sha=frozen["control"]["git_sha"] if frozen else None,
        expected_executions=24, expected_physics_ticks=3360, actual_physics_ticks=3360 if complete else None,
        aggregate_cpu_seconds=cpu(), aggregate_wall_seconds=time.monotonic() - started, runs=rows, error=error,
        files=files)
    def final_guard():
        C.require(cpu() <= C.AGGREGATE_CPU and time.monotonic() - started <= C.AGGREGATE_WALL,
                  "final execution serialization/publication exceeded aggregate budget")
    try:
        publish_execution(root, execution, cpu, started, final_guard)
    except BaseException as exc:
        complete = False
        execution.update(execution_complete=False, scientific_standing="incomplete_or_censored",
            actual_physics_ticks=None, error=dict(type=type(exc).__name__, message=str(exc)))
        C.write(root / "execution.json", execution)
        negative_hash = C.sha(root / "execution.json")
        negative_cpu = cpu()
        C.write(root / "execution-receipt.json", dict(schema_version=1,
            kind="natural-research-execution-receipt", publication_complete=False,
            execution_sha256=negative_hash, measured_to_seal_cpu_seconds=negative_cpu,
            finalization_cpu_reserve_seconds=0.0, charged_aggregate_cpu_seconds=negative_cpu,
            aggregate_wall_seconds=time.monotonic() - started, controller_started_monotonic=started,
            boot_id=execution["boot_id"]))
    return 0 if complete else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "run", "worker"))
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--seed", type=int, choices=C.SEEDS)
    parser.add_argument("--role", choices=C.ROLES)
    options = parser.parse_args(argv)
    if options.mode == "freeze":
        C.write(options.freeze, identity(options.source_root))
        return 0
    C.require(options.output_root is not None, "output root required")
    if options.mode == "worker":
        C.require(options.seed is not None and options.role is not None, "fixed worker seed/role required")
        worker(options)
        return 0
    C.require(options.seed is options.role is None, "controller cannot select a seed/role subset")
    return run(options)


if __name__ == "__main__":
    raise SystemExit(main())
