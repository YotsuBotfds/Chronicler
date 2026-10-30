"""Opt-in same-binary full GP-sync benchmark; production routing is untouched.

Default/plan/controller modes import no simulator or product module. Builds and
all runtime actions require explicit modes; Native work belongs only to workers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import statistics
import struct
import subprocess
import sys
import time
from types import SimpleNamespace
import zipfile
try:
    import resource
except ImportError:
    resource = None

import paired_context_benchmark as paired

METHOD = "named-gp-fullsync-v1-69x3x2-256"
RUN_REF = "refs/heads/lead/gp-fullsync-benchmark-run-20261030"
PARENT = "0e2cf3b7427dc83993f5c3ed4c1712bd7bfb2f60"
NATIVE_TREE = "0dca68c36baa2663c66dcf45bb4afd0c5696b18f"
FIXED = {
    "src/chronicler/_gp_context_sync.py": "33b72facb44c58b8223e69d3d0a285685015ccbe9782bacaa932cd107519e11f",
    "src/chronicler/agent_bridge.py": "153197b0ed2602bccefdca686785a2c53ad8e5c56c663c9dd06aa929b3a67f9e",
    "src/chronicler/models.py": "e8f8de307a2f06cb2875657976e7450fde91821d25c7710767691b313bafe1c6",
}
CALLS, WARMUPS = 256, 2
BODY, ZIP_CAP = 2*1024**2, 2*1024**2
PLAN_CAP, BUILD_CAP, JOURNAL_CAP = 65536, 65536, 1536*1024
RESULT_CAP, OWNER_CAP, FRAGMENT_CAP, ERROR_CAP = 128*1024, 8192, 4096, 16384
PACKAGE_MAP_CAP = 16384  # Included in the existing64KiB build record.
CUSTODY_CAP = 512  # Parent control inside the unchanged whole-body allowance.
GITHUB = paired.GITHUB_FIELDS
sha = lambda b: hashlib.sha256(b).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def encode(value):
    def byte_value(item):
        if type(item) is bytes:
            return {"bytes_hex": item.hex()}
        raise TypeError("unsupported evidence value: "+type(item).__name__)
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
        allow_nan=False, default=byte_value)+"\n").encode()


def digest(value):
    return sha(encode(value))


def payload_digest(rows):
    return digest([(aid, memories, None if needs is None else
        [struct.pack("!d", n).hex() for n in needs], bonds)
        for aid, memories, needs, bonds in rows])


def schema_reference(raw):
    """Real Native tuple is (version,16hex FNV fingerprint,full schema text)."""
    require(type(raw) in (list,tuple) and len(raw)==3 and type(raw[0]) is int
        and 0<=raw[0]<2**32 and type(raw[1]) is str and re.fullmatch(r"[0-9a-f]{16}",raw[1])
        and type(raw[2]) is str and bool(raw[2]),"raw_schema_shape")
    body=raw[2].encode("utf-8");require(len(body)<=BUILD_CAP,"raw_schema_bound")
    fingerprint=14695981039346656037
    for value in body:
        fingerprint=((fingerprint^value)*1099511628211)&((1<<64)-1)
    require(f"{fingerprint:016x}"==raw[1],"raw_schema_fingerprint")
    return dict(version=raw[0],fingerprint=raw[1],schema_bytes=len(body),schema_sha256=sha(body))


def package_versions(distributions=None):
    """Observed distribution versions, not hashes of every installed file."""
    if distributions is None:
        from importlib import metadata
        distributions=metadata.distributions()
    versions={}
    for distribution in distributions:
        name=distribution.metadata.get("Name");version=distribution.version
        require(type(name) is str and type(version) is str and 0<len(version)<=128,"package_metadata")
        canonical=re.sub(r"[-_.]+","-",name).lower()
        require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*",canonical) is not None
            and len(canonical)<=128 and canonical not in versions,"ambiguous_package_name")
        versions[canonical]=version
        require(len(versions)<=512 and len(encode(versions))<=PACKAGE_MAP_CAP,"package_map_bound")
    require(bool(versions),"empty_package_map")
    return dict(sorted(versions.items()))


def check_packages(actual, expected, expected_digest):
    require(type(actual) is dict and type(expected) is dict and actual==expected
        and digest(actual)==expected_digest,"installed_package_version_mismatch")
    return expected_digest


def conditions():
    rows = []
    for n in (512, 8192, 65536):
        rows.append(dict(initial_agents=n, requests=0, layout="empty"))
        rows.extend(dict(initial_agents=n, requests=p, layout=layout)
            for p in (1, 2, 5, 10, 25, 50)
            for layout in ("prefix", "spread", "half-missing"))
    rows.extend(dict(initial_agents=n, requests=p, layout="all-missing")
        for n in (512, 8192, 65536) for p in (1, 50))
    rows.extend(dict(initial_agents=n, requests=p, layout="post1-spread")
        for n in (8192, 65536) for p in (1, 10, 50))
    return [dict(case=i, **row) for i, row in enumerate(rows)]


def schedule():
    jobs = []
    for spec in conditions():
        for trial in range(3):
            order = ("scalar", "candidate") if (spec["case"]+trial)%2 == 0 else ("candidate", "scalar")
            for arm in order:
                jobs.append(dict(ordinal=len(jobs), case=spec["case"], trial=trial, arm=arm))
    return jobs


def plan():
    return dict(kind="GP_FULLSYNC_PLAN", method=METHOD, conditions=conditions(),
        schedule=schedule(), workers=414, measured_calls_each=CALLS, warmups=WARMUPS,
        seed=42, global_seed=0, initial_agents_scope="N before setup tick; not post-tick allocated scan slots",
        controller_source="Actual immutable GITHUB_SHA; root must register/review that exact source before ONE run-ref activation",
        parent=PARENT, native_tree=NATIVE_TREE, fixed_product_sha256=FIXED,
        limits=dict(wall_seconds=600, joint_CPU_seconds=540, controller_CPU_seconds=24,
            worker_CPU_seconds=24, waited_worker_credit_us=512000000,
            controller_AS=128*1024**2, worker_AS=1920*1024**2, CPUs=1,
            body_bytes=BODY, ZIP_bytes=ZIP_CAP, active_bytes=FRAGMENT_CAP),
        scope="Controlled edited GP rosters/full helper; not natural promotions, default adoption, whole-turn or science",
        allocation_failure_partial_progress_equivalence=False, retries=0)


def query_rows(ids, civs, spec):
    n, p, layout = len(ids), spec["requests"], spec["layout"]
    require(n >= p and len(civs) == n and len(set(ids)) == n
        and all(type(i) is int and 0 < i < 2**32 for i in ids), "snapshot_identity")
    require(all(type(c) is int and 0 <= c < 8 for c in civs), "snapshot_civ")
    positions = ([] if not p else list(range(p)) if layout == "prefix" else
        [n//2] if p == 1 else [i*(n-1)//(p-1) for i in range(p)])
    rows = []
    for i, pos in enumerate(positions):
        absent = layout == "all-missing" or layout == "half-missing" and i%2 == 1
        aid = 2**32-1-i if absent else ids[pos]
        require(not absent or aid not in ids, "missing_id_collision")
        rows.append(dict(id=aid, position=None if absent else pos,
            precursor=pos, civ=i%8 if layout == "all-missing" else civs[pos]))
    return rows


def fixture(spec, api):
    """Public constructors/Native methods only; injectable explicit pure fakes."""
    n = spec["initial_agents"]
    civs = [api["Civilization"](name=f"C{i}", population=n//8, military=20,
        economy=20, culture=20, stability=50,
        leader=api["Leader"](name=f"L{i}", trait="bold", reign_start=0),
        regions=[f"R{i}"], capital_region=f"R{i}") for i in range(8)]
    regions = [api["Region"](name=f"R{i}", terrain="plains", resources="fertile",
        population=n//8, carrying_capacity=n//8, controller=f"C{i}") for i in range(8)]
    world = api["WorldState"](name="gp-fullsync", seed=42, turn=0,
        civilizations=civs, regions=regions)
    bridge = api["AgentBridge"](world, mode="hybrid", agent_scale_mode="exact",
        validation_sidecar=False, relationship_stats=False)
    sim, pa = bridge._sim, api["pa"]
    initial = pa.record_batch(sim.get_snapshot())
    require(initial.num_rows == n, "initial_population")
    query_rows(initial.column("id").to_pylist(),initial.column("civ_affinity").to_pylist(),
        dict(requests=0,layout="empty"))
    setup_ticks = int(spec["layout"] == "post1-spread")
    if setup_ticks:
        signals = pa.record_batch({
            "civ_id": pa.array(range(8), type=pa.uint8()),
            "stability": pa.array([50]*8, type=pa.uint8()),
            "is_at_war": pa.array([False]*8, type=pa.bool_()),
            "dominant_faction": pa.array([0]*8, type=pa.uint8()),
            "faction_military": pa.array([.33]*8, type=pa.float32()),
            "faction_merchant": pa.array([.33]*8, type=pa.float32()),
            "faction_cultural": pa.array([.34]*8, type=pa.float32()),
        })
        sim.tick(1, signals)
    snapshot = pa.record_batch(sim.get_snapshot())
    ids = snapshot.column("id").to_pylist()
    affinities = snapshot.column("civ_affinity").to_pylist()
    rows = query_rows(ids, affinities, spec)
    if setup_ticks:
        edges = [(r["id"], ids[(r["precursor"]+k)%len(ids)]) for r in rows for k in range(1, 9)]
        sim.apply_relationship_ops(pa.record_batch({
            "op_type": pa.array([0]*len(edges), type=pa.uint8()),
            "agent_a": pa.array([a for a, _ in edges], type=pa.uint32()),
            "agent_b": pa.array([b for _, b in edges], type=pa.uint32()),
            "bond_type": pa.array([6]*len(edges), type=pa.uint8()),
            "sentiment": pa.array([50]*len(edges), type=pa.int8()),
            "formed_turn": pa.array([1]*len(edges), type=pa.uint16()),
        }))
    stale = ([dict(event_type=9, intensity=-0.0, keep="old")],
        {name: -0.0 for name in ("safety", "material", "social", "spiritual", "autonomy", "purpose")},
        [dict(target_id=999, sentiment=-3, bond_type=6, formed_turn=0)])
    shared = dict(value=1.25, signed_zero=-0.0)
    def person(name, aid, civ, active=True):
        gp = api["GreatPerson"](name=name, role="merchant", trait="bold", source="agent",
            active=active, agent_id=aid, born_turn=0, civilization=f"C{civ}", origin_civilization=f"C{civ}")
        gp.memories, gp.needs, gp.agent_bonds = stale
        gp.utility_overrides["benchmark_shared"] = shared
        return gp
    controls = []
    for j in range(20):
        c = j%8
        gp = person(f"Control-{j}", ids[0] if j%2 == 0 else None, c, active=j%2 == 1)
        civs[c].great_persons.append(gp)
        controls.append(gp)
    attached = []
    for i, row in enumerate(rows):
        gp = person(f"GP-{i}", row["id"], row["civ"])
        civs[row["civ"]].great_persons.append(gp)
        attached.append((gp, row))
    ordered = [(gp, row) for c in civs for gp in c.great_persons for wanted, row in attached if gp is wanted]
    counts = pa.record_batch(sim.get_region_populations()).column("alive_count").to_pylist()
    require(len(counts) == 8 and sum(counts) == len(ids), "alive_census")
    return bridge, world, dict(rows=ordered, controls=controls, stale=stale,
        alive=len(ids), per_region=counts, setup_ticks=setup_ticks)


def full_gp_state(world, base_model):
    """Closed Native2 traversal: all GP fields/private/extras/fieldset and aliases."""
    seen = {}
    def freeze(value):
        if type(value) is float:
            return ("float64", struct.pack("!d", value).hex())
        if value is None or type(value) in (bool, int, str, bytes):
            return (type(value).__name__, value)
        token = id(value)
        if token in seen:
            return ("alias", seen[token])
        seen[token] = len(seen)
        if isinstance(value, base_model):
            return (type(value).__qualname__, freeze(value.__dict__),
                freeze(value.__pydantic_extra__), freeze(value.__pydantic_private__),
                freeze(value.__pydantic_fields_set__))
        if type(value) is dict:
            return ("dict", tuple((freeze(k), freeze(v)) for k, v in value.items()))
        if type(value) in (list, tuple):
            return (type(value).__name__, tuple(freeze(v) for v in value))
        if type(value) is set:
            return ("set", tuple(sorted(freeze(v) for v in value)))
        raise ValueError("unhandled GP state type: "+str(type(value)))
    return tuple(freeze(c.great_persons) for c in world.civilizations)


def rng_state(random, np):
    bits = lambda x: None if x is None else struct.pack("!d", x).hex()
    py, nu = random.getstate(), np.random.get_state()
    return ((py[0], py[1], bits(py[2])), (nu[0], nu[1].dtype.str, nu[1].shape,
        nu[1].strides, nu[1].tobytes(order="C"), nu[2], nu[3], bits(nu[4])))


def observe_calls(sim, action):
    require(sys.getprofile() is None, "preexisting_profiler")
    counts, trace = [0, 0, 0, 0], []
    names = ("get_agent_memories", "get_agent_needs", "get_agent_relationships", "get_agent_context_batch")
    def profile(frame, event, arg):
        if event == "c_call" and getattr(arg, "__self__", None) is sim:
            name = getattr(arg, "__name__", None)
            if name in names:
                index = names.index(name); counts[index] += 1; trace.append(index)
    try:
        sys.setprofile(profile)
        result = action()
    finally:
        sys.setprofile(None)
    return result, counts, trace


def timed_sync(action, wall=time.perf_counter_ns, cpu=time.process_time_ns):
    done = 0
    result = None
    start, cstart = wall(), cpu()
    error = None
    try:
        for _ in range(CALLS):
            result = action()
            done += 1
    except Exception as exc:
        error = dict(type=type(exc).__name__, message=str(exc)[:160])
    cend, end = cpu(), wall()
    if error is None and result is not None:
        error = dict(type="ValueError", message="helper_return")
    return dict(kind="timing", wall_start_ns=start, CPU_start_ns=cstart,
        CPU_end_ns=cend, wall_end_ns=end, wall_ns=end-start, CPU_ns=cend-cstart,
        completed_calls=done, error=error)


def check_contexts(info, raw):
    stale = info["stale"]
    live = []
    for (gp, _), row in zip(info["rows"], raw):
        if row[2] is None:
            require(gp.memories == [] and gp.needs is stale[1] and gp.agent_bonds is stale[2], "missing_stale_context")
        else:
            live.append(gp)
    for name in ("memories", "needs", "agent_bonds"):
        require(len({id(getattr(g, name)) for g in live}) == len(live), "independent_context_containers")
    require(all(g.memories is stale[0] and g.needs is stale[1] and g.agent_bonds is stale[2]
        for g in info["controls"]), "excluded_controls_changed")


def child_audit(event, args):
    if event in ("subprocess.Popen", "os.system", "os.fork", "os.forkpty", "os.posix_spawn", "os.exec") \
            or event.startswith("socket."):
        raise RuntimeError("GP worker forbids child/network: "+event)


def emit(value, cap):
    body = encode(value); require(len(body) <= cap, "worker_record_limit")
    sys.stdout.buffer.write(body); sys.stdout.buffer.flush()


def worker(job, build_path):
    sys.addaudithook(child_audit)
    try:
        packages=package_versions();package_digest=digest(packages)
        emit(dict(kind="worker_start", ordinal=job["ordinal"], case=job["case"], trial=job["trial"],
            arm=job["arm"],pid=os.getpid(),packages_sha256=package_digest),256)
        build = read_build(build_path)
        check_packages(packages,build["packages"],build["packages_sha256"])
        require(sys.executable == build["worker_python"] and sys.prefix == build["venv_prefix"], "own_venv")
        require(resource.getrlimit(resource.RLIMIT_AS) == (1920*1024**2,)*2
            and resource.getrlimit(resource.RLIMIT_CPU) == (24,)*2
            and len(os.sched_getaffinity(0)) == 1, "worker_limits")
        native, native_path = paired.b.compiled_module()
        require(paired.receipt_function()(Path(build["wheel_dir"]), native_path,
            build["source_commit"]) == build["wheel_receipt"], "installed_own_wheel")
        import pyarrow as pa
        import random
        import numpy as np
        from pydantic import BaseModel
        from chronicler import models, agent_bridge, _gp_context_sync as gp
        root = Path(build["source_root"])
        for module, name in ((models,"models.py"),(agent_bridge,"agent_bridge.py"),(gp,"_gp_context_sync.py")):
            require(Path(module.__file__).resolve() == root/"src/chronicler"/name, "Python_source_origin")
        random.seed(0); np.random.seed(0)
        api = {name:getattr(models,name) for name in ("WorldState","Civilization","Leader","Region","GreatPerson")}
        api.update(AgentBridge=agent_bridge.AgentBridge, pa=pa)
        spec = conditions()[job["case"]]
        bridge, world, info = fixture(spec, api)
        sim = bridge._sim
        initial = digest(full_gp_state(world, BaseModel))
        controls_world=SimpleNamespace(civilizations=[SimpleNamespace(great_persons=info["controls"])])
        controls_before=digest(full_gp_state(controls_world,BaseModel))
        checkpoint = bytes(sim.checkpoint_state()); schema = native.AgentSimulator.checkpoint_schema()
        require(list(schema)==build["agent_schema"] and schema_reference(schema)==build["agent_schema_reference"],
            "own_build_raw_schema_join")
        rng = digest(rng_state(random, np))
        prepared = gp._prepare_native_sync(bridge, world)
        require(prepared is not None and prepared[0] is sim
            and prepared[2].__self__ is sim and prepared[2].__name__ == "get_agent_context_batch"
            and len(prepared[1]) == spec["requests"]
            and all(a is b and aid == row["id"] for (a,aid),(b,row) in zip(prepared[1],info["rows"])), "real_Native_admission")
        ids = [row["id"] for _,row in info["rows"]]
        raw = [(aid, sim.get_agent_memories(aid), sim.get_agent_needs(aid), sim.get_agent_relationships(aid)) for aid in ids]
        if ids:
            require(payload_digest(raw) == payload_digest(sim.get_agent_context_batch(ids)), "compiled_payload_parity")
        if not info["setup_ticks"]:
            require(all(not r[1] and (r[3] is None or not r[3]) for r in raw), "base_empty_stores")
        require(digest(full_gp_state(world, BaseModel)) == initial
            and bytes(sim.checkpoint_state()) == checkpoint and digest(rng_state(random,np)) == rng,
            "admission_or_getter_mutation")
        action = lambda: (gp._sync_scalar_reference if job["arm"] == "scalar" else gp._sync_batch_prototype)(bridge,world)
        result, counts, trace = observe_calls(sim, action)
        expected = [0,1,2]*len(ids) if job["arm"] == "scalar" else ([3] if ids else [])
        require(result is None and trace == expected, "original_C_call_trace")
        for _ in range(WARMUPS):
            require(action() is None, "warmup_return")
        warm = digest(full_gp_state(world, BaseModel))
        timing = timed_sync(action)
        emit(timing, 512)
        require(timing["error"] is None and timing["completed_calls"] == CALLS, "timed_helper_exception")
        check_contexts(info, raw)
        require(digest(full_gp_state(controls_world,BaseModel))==controls_before,"complete_control_state_changed")
        final = digest(full_gp_state(world, BaseModel))
        after = bytes(sim.checkpoint_state()); after_rng = digest(rng_state(random, np))
        require(after == checkpoint and after_rng == rng and native.AgentSimulator.checkpoint_schema() == schema,
            "Native_persistent_or_RNG_mutation")
        emit(dict(kind="worker_end", ids=ids, positions=[r["position"] for _,r in info["rows"]],
            precursors=[r["precursor"] for _,r in info["rows"]], alive=info["alive"], per_region=info["per_region"],
            setup_ticks=info["setup_ticks"], payload=payload_digest(raw), memories=[len(r[1]) for r in raw],
            legacy=[sum(bool(m[5]) for m in r[1]) for r in raw],
            bonds=[None if r[3] is None else len(r[3]) for r in raw], needs=sum(r[2] is not None for r in raw),
            initial_gp=initial, warm_gp=warm, final_gp=final, control_gp=controls_before,native_before=sha(checkpoint),
            native_after=sha(after), rng_before=rng, rng_after=after_rng,schema=schema_reference(schema),
            diagnostic_counts=counts), 2816)
        return 0
    except Exception as exc:
        emit(dict(kind="worker_error", type=type(exc).__name__, message=str(exc)[:384]), 768)
        return 2


def file_pin(path, cap):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= cap, "pinned_file")
    return dict(bytes=path.stat().st_size, sha256=sha(path.read_bytes()))


def driver_pins():
    root = Path(__file__).resolve().parents[1]
    names = ("scripts/benchmark_gp_context_sync.py", "scripts/paired_context_benchmark.py",
        "scripts/benchmark_named_context.py", "scripts/native_wheel_receipt.py",
        ".github/workflows/gp-context-benchmark.yml")
    return {n:file_pin(root/n, 128*1024) for n in names}


def current_source():
    source = os.environ.get("GITHUB_SHA", "")
    require(len(source) == 40 and all(c in "0123456789abcdef" for c in source), "actual_controller_SHA")
    require(os.environ.get("GITHUB_REF") == RUN_REF and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
        and bool(os.environ.get("GITHUB_JOB")) and os.environ.get("GITHUB_RUN_ID", "").isdigit(), "actual_run_context")
    return source


def body_usage(root, unsafe=()):
    total, count = 0, 0
    for path in Path(root).rglob("*"):
        if path.relative_to(root).as_posix() in unsafe:
            total += FRAGMENT_CAP; count += 1
            continue  # Reserved bound: no child stat/read/hash while custody is unknown.
        require(not path.is_symlink(), "evidence_symlink")
        if path.is_file():
            count += 1; total += path.stat().st_size
    require(count <= 500 and total <= BODY, "whole_body_or_file_limit")
    return total


def write_new(path, value, cap, root=None, unsafe=()):
    """Existing exclusive/fsync record discipline; owner is charged jointly."""
    body = encode(value); require(len(body) <= cap, "record_limit")
    if root is not None:
        require(body_usage(root,unsafe)+len(body) <= BODY, "joint_body_including_record")
    with Path(path).open("xb") as out:
        require(out.write(body) == len(body), "short_record")
        out.flush(); os.fsync(out.fileno())
    Path(path).chmod(0o444)
    return file_pin(path, cap)


def record_build(root, wheel_dir, output):
    """Only build preparation may invoke Git/compiled identity discovery."""
    source = current_source()
    root, wheel_dir, output = root.resolve(), wheel_dir.resolve(), output.resolve()
    paired.checked_checkout(root, source)
    require(Path(__file__).resolve() == root/"scripts/benchmark_gp_context_sync.py", "own_driver_source")
    require(paired.git(root,"rev-parse","HEAD:chronicler-agents") == NATIVE_TREE, "native_source")
    for name, expected in FIXED.items():
        require(file_pin(root/name, 256*1024)["sha256"] == expected, "fixed_product_source")
    native, native_path = paired.b.compiled_module()
    raw_schema=native.AgentSimulator.checkpoint_schema();schema=schema_reference(raw_schema)
    packages=package_versions()
    wheels = list(wheel_dir.glob("*.whl")); require(len(wheels) == 1, "one_fresh_wheel")
    file_pin(wheels[0], 16*1024**2); file_pin(native_path, 64*1024**2)
    receipt = paired.receipt_function()(wheel_dir, native_path, source)
    staged = subprocess.check_output(["git","--no-replace-objects","-C",str(root),"ls-files","--stage","-z"])
    sealed = paired.seal_sources(root, staged)
    paired.checked_checkout(root, source)
    wheels[0].chmod(0o444); native_path.chmod(native_path.stat().st_mode&0o555)
    value = dict(kind="OWN_GP_FULLSYNC_BUILD", method=METHOD, source_commit=source,
        source_tree=paired.git(root,"rev-parse","HEAD^{tree}"), native_tree=NATIVE_TREE,
        source_root=str(root), wheel_dir=str(wheel_dir), worker_python=sys.executable,
        venv_prefix=sys.prefix, native_file=str(native_path.resolve()), wheel_receipt=receipt,
        python=dict(version=sys.version,binary=file_pin(Path(sys.executable).resolve(),64*1024**2)),
        host=list(os.uname()), driver=driver_pins(), fixed_product_sha256=FIXED,
        agent_schema=list(raw_schema),agent_schema_reference=schema,
        packages=packages,packages_sha256=digest(packages),
        package_identity_scope="Observed canonical distribution versions; not all installed file bytes",
        uv_lock=file_pin(root/"uv.lock",4*1024**2), cargo_lock=file_pin(root/"chronicler-agents/Cargo.lock",128*1024),
        sealed_source=sealed, toolchain={n:file_pin(output.parent/n,4096)
            for n in ("rustc.txt","cargo.txt","maturin.txt","uv.txt")},
        build_flags={k:os.environ.get(k,"") for k in ("CARGO_BUILD_JOBS","CARGO_INCREMENTAL","CARGO_TARGET_DIR","RUSTFLAGS")},
        github={k:os.environ.get(k) for k in GITHUB}, build_outside_comparison=True)
    write_new(output,value,BUILD_CAP,output.parent.parent)
    return value


def read_build(path):
    require(Path(path).stat().st_size <= BUILD_CAP, "build_record_limit")
    value = json.loads(Path(path).read_bytes())
    require(value["kind"] == "OWN_GP_FULLSYNC_BUILD" and value["method"] == METHOD
        and value["source_commit"] == current_source() and value["native_tree"] == NATIVE_TREE
        and value["driver"] == driver_pins() and value["fixed_product_sha256"] == FIXED
        and value["github"] == {k:os.environ.get(k) for k in GITHUB}, "build_identity")
    require(schema_reference(value["agent_schema"])==value["agent_schema_reference"],"build_raw_schema_reference")
    expected=package_versions([SimpleNamespace(metadata={"Name":n},version=v) for n,v in value["packages"].items()])
    check_packages(expected,value["packages"],value["packages_sha256"])
    root = Path(value["source_root"])
    require(root.is_absolute() and Path(__file__).resolve() == root/"scripts/benchmark_gp_context_sync.py", "sealed_source_path")
    for name, expected in FIXED.items():
        require(file_pin(root/name,256*1024)["sha256"] == expected, "fixed_source_changed")
    return value


def host_admission(path, available=None, free=None):
    if available is None:
        text = Path("/proc/meminfo").read_text()
        rows = [line.split() for line in text.splitlines() if line.startswith("MemAvailable:")]
        require(len(rows) == 1 and rows[0][2] == "kB", "host_memory_observation")
        available = int(rows[0][1])*1024
    if free is None:
        fs = os.statvfs(path); free = fs.f_bavail*fs.f_frsize
    require(type(available) is int and available >= 1920*1024**2
        and type(free) is int and free >= 3*1024**3, "host_memory_or_disk_floor")
    return dict(MemAvailable=available, filesystem_free=free,
        scope="Host observations; not aggregate/cgroup capacity attestation")


def group_members(group):
    """Wholeturn closure primitive plus stable start time for parent exclusions."""
    members = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry/"stat").read_text(); fields = raw[raw.rfind(")")+2:].split()
            if int(fields[2]) == group:
                members[int(entry.name)] = int(fields[19])
        except (FileNotFoundError,ProcessLookupError):
            continue
    return members


def settle_worker(group, leader, baseline, *, members=group_members,
                  now=time.monotonic, pause=time.sleep, kill=None):
    """Bounded post-terminal proof; preexisting outer-group tasks are excluded."""
    def stable_kill(pid, stamp):
        require(hasattr(os,"pidfd_open") and hasattr(signal,"pidfd_send_signal"), "stable_kill_unavailable")
        fd = os.pidfd_open(pid)
        try:
            require(group_members(group).get(pid) == stamp, "member_identity_changed")
            signal.pidfd_send_signal(fd,signal.SIGKILL)
        finally:
            os.close(fd)
    kill = stable_kill if kill is None else kill
    deadline, observations, requested = now()+.5, 0, []
    try:
        while True:
            current = members(group)
            extra = {pid:stamp for pid,stamp in current.items()
                if pid != leader and baseline.get(pid) != stamp}
            observations += 1
            if not extra:
                return dict(proven=True,observations=observations,killed=requested)
            for pid,stamp in extra.items():
                try:kill(pid,stamp); requested.append(pid)
                except ProcessLookupError:pass
            if now() >= deadline:
                return dict(proven=False,observations=observations,remaining=list(extra),killed=requested)
            pause(min(.02,max(0,deadline-now())))
    except Exception as exc:
        return dict(proven=False,observations=observations,error=type(exc).__name__,killed=requested)


class SystemBackend:
    def __init__(self, build_path):
        self.build_path, self.active, self.quiescent = build_path, None, True
        self.group, self.baseline = None, None

    def run(self, job, build, fragment):
        require(self.active is None, "overlapping_worker")
        allowed = {k:os.environ[k] for k in ("PATH","LANG","LC_ALL","TMPDIR",*GITHUB) if k in os.environ}
        allowed.update(PYTHONPATH=build["source_root"]+"/src",PYTHONDONTWRITEBYTECODE="1",
            PYTHONHASHSEED="0",PYTHONUNBUFFERED="1")
        for k in ("RAYON_NUM_THREADS","OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS",
                  "ARROW_NUM_THREADS","NUMEXPR_NUM_THREADS","VECLIB_MAXIMUM_THREADS","BLIS_NUM_THREADS"):
            allowed[k] = "1"
        argv = [build["worker_python"],"-B",str(Path(__file__).resolve()),"--worker",
            "--ordinal",str(job["ordinal"]),"--build",str(self.build_path)]
        group = os.getpgrp(); baseline = group_members(group); parent = os.getpid()
        self.group, self.baseline = group, baseline
        self.quiescent = False
        with fragment.open("xb") as out:
            def bootstrap():
                paired.worker_bootstrap(parent)
                resource.setrlimit(resource.RLIMIT_FSIZE,(FRAGMENT_CAP,FRAGMENT_CAP))
            self.active = subprocess.Popen(argv,stdout=out,stderr=subprocess.STDOUT,env=allowed,preexec_fn=bootstrap)
            try:
                os.waitid(os.P_PID,self.active.pid,os.WEXITED|os.WNOWAIT)
                custody = settle_worker(group,self.active.pid,baseline)
                _,status,usage = os.wait4(self.active.pid,0)
                code = os.waitstatus_to_exitcode(status); self.active.returncode = code
                self.quiescent = custody["proven"]
                return dict(returncode=code,pid=self.active.pid,quiescent=self.quiescent,custody=custody,
                    cpu_us=math.ceil((usage.ru_utime+usage.ru_stime)*1000000),
                    user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,maximum_RSS_kib=usage.ru_maxrss)
            finally:
                self.close()

    def close(self):
        if self.active is not None and self.active.returncode is None:
            try:self.active.kill()
            except ProcessLookupError:pass
            os.waitid(os.P_PID,self.active.pid,os.WEXITED|os.WNOWAIT)
            custody=settle_worker(self.group,self.active.pid,self.baseline)
            _,status,_ = os.wait4(self.active.pid,0)
            self.active.returncode = os.waitstatus_to_exitcode(status)
            self.quiescent = custody["proven"]
            # Without the run() reply the parent still records custody UNKNOWN.
        self.active = None

    def total_cpu_us(self):
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return math.ceil((usage.ru_utime+usage.ru_stime)*1000000)


def parse_fragment(data, job, pid, expected_schema, expected_packages):
    require(0 < len(data) <= FRAGMENT_CAP and data.endswith(b"\n"), "fragment_shape")
    rows = [json.loads(line) for line in data.splitlines()]
    require(len(rows) == 3, "worker_protocol")
    head,timing,end = rows
    require(head == dict(kind="worker_start",**job,pid=pid,packages_sha256=expected_packages)
        and type(pid) is int and pid>0,
        "worker_identity")
    require(timing["kind"] == "timing" and end["kind"] == "worker_end", "record_kinds")
    for key in ("wall_start_ns","wall_end_ns","CPU_start_ns","CPU_end_ns","wall_ns","CPU_ns","completed_calls"):
        require(type(timing[key]) is int,"clock_integer")
    require(timing["wall_ns"] == timing["wall_end_ns"]-timing["wall_start_ns"]
        and timing["CPU_ns"] == timing["CPU_end_ns"]-timing["CPU_start_ns"]
        and timing["completed_calls"] == CALLS and timing["error"] is None,"clock_or_dose_join")
    spec = conditions()[job["case"]]; p = spec["requests"]
    for key in ("ids","positions","precursors","memories","legacy","bonds"):
        require(type(end[key]) is list and len(end[key]) == p,"observed_vector_size")
    require(all(type(a) is int and 0 <= a < 2**32 for a in end["ids"])
        and type(end["alive"]) is int and end["alive"] >= p
        and len(end["per_region"]) == 8 and sum(end["per_region"]) == end["alive"],"observed_census")
    require(type(end["setup_ticks"]) is int and end["setup_ticks"] == int(spec["layout"]=="post1-spread"),"setup_tick_dose")
    if not end["setup_ticks"]:
        require(end["alive"] == spec["initial_agents"],"base_alive_population")
    expected_positions=([] if p==0 else list(range(p)) if spec["layout"]=="prefix" else
        [end["alive"]//2] if p==1 else [i*(end["alive"]-1)//(p-1) for i in range(p)])
    require(sorted(end["precursors"])==expected_positions,"precursor_layout")
    present=0
    for aid,pos,prior,mc,lc,bc in zip(end["ids"],end["positions"],end["precursors"],end["memories"],end["legacy"],end["bonds"]):
        index=expected_positions.index(prior)
        missing=spec["layout"]=="all-missing" or spec["layout"]=="half-missing" and index%2==1
        require(type(mc) is int and type(lc) is int and 0<=lc<=mc<=8
            and (bc is None or type(bc) is int and 0<=bc<=8),"payload_counts")
        require((pos is None and aid==2**32-1-index and mc==0 and bc is None) if missing
            else type(pos) is int and pos==prior and aid>0 and bc is not None,"missing_live_layout")
        present+=not missing
        if not end["setup_ticks"]:require(mc==0 and bc in (None,0),"base_empty_counts")
    require(type(end["needs"]) is int and end["needs"]==present
        and all(type(n) is int and n>=0 for n in end["per_region"]),"needs_alive_counts")
    require(end["native_before"] == end["native_after"] and end["rng_before"] == end["rng_after"],"persistent_invariance")
    require(type(end["diagnostic_counts"]) is list and all(type(v) is int for v in end["diagnostic_counts"])
        and end["diagnostic_counts"] == ([p,p,p,0] if job["arm"]=="scalar" else [0,0,0,int(p>0)]),"actual_C_counts")
    require(type(end["schema"]) is dict and end["schema"]==expected_schema
        and type(end["schema"].get("version")) is int
        and type(end["schema"].get("schema_bytes")) is int
        and re.fullmatch(r"[0-9a-f]{16}",end["schema"].get("fingerprint","")) is not None
        and re.fullmatch(r"[0-9a-f]{64}",end["schema"].get("schema_sha256","")) is not None,
        "checkpoint_schema_build_join")
    for k in ("payload","initial_gp","warm_gp","final_gp","control_gp","native_before","native_after","rng_before","rng_after"):
        require(type(end[k]) is str and len(end[k])==64 and all(c in "0123456789abcdef" for c in end[k]),"proof_digest")
    return dict(job,timing=timing,proof=end)


def join_pair(left, right):
    require(left["case"] == right["case"] and left["trial"] == right["trial"]
        and {left["arm"],right["arm"]} == {"scalar","candidate"},"pair_identity")
    a,b = left["proof"],right["proof"]
    require({k:v for k,v in a.items() if k != "diagnostic_counts"}
        == {k:v for k,v in b.items() if k != "diagnostic_counts"},"full_GP_payload_CP_RNG_pair")


def summaries(records):
    result=[]
    for spec in conditions():
        rows=[r for r in records if r["case"]==spec["case"]]
        row=dict(spec,complete_pairs=len(rows)//2,status="incomplete")
        if len(rows)==6:
            by={arm:sorted((r for r in rows if r["arm"]==arm),key=lambda r:r["trial"])
                for arm in ("scalar","candidate")}
            wall={a:[r["timing"]["wall_ns"] for r in rs] for a,rs in by.items()}
            cpu={a:[r["timing"]["CPU_ns"] for r in rs] for a,rs in by.items()}
            row.update(wall_ns=wall,CPU_ns=cpu,status="complete" if all(x>0 for v in wall.values() for x in v) else "numerical_refused")
            if row["status"]=="complete":
                med={a:statistics.median(v) for a,v in wall.items()}
                row.update(median_wall_ns=med,scalar_over_candidate=med["scalar"]/med["candidate"],
                    paired_wall_ratios=[a/b for a,b in zip(wall["scalar"],wall["candidate"])],
                    median_per_call_ns={a:v/CALLS for a,v in med.items()})
            row["CPU_ratios"] = ([a/b for a,b in zip(cpu["scalar"],cpu["candidate"])]
                if all(x>0 for v in cpu.values() for x in v) else None)
        result.append(row)
    return result


def append_record(stream, value, cap):
    body=encode(value); require(len(body)<=cap and stream.tell()+len(body)<=JOURNAL_CAP,"journal_bound")
    require(stream.write(body)==len(body),"short_journal_write"); stream.flush(); os.fsync(stream.fileno())


def run_schedule(build, output, backend, wall=time.monotonic_ns, cpu=time.process_time_ns,
                 admission=host_admission):
    require(output.is_absolute(),"absolute_comparison_output"); output.mkdir(exist_ok=False)
    root=output.parent; jobs=schedule(); records=[]; pending={}; started=wall()
    state=dict(kind="GP_FULLSYNC_RESULT",method=METHOD,status="failed",planned_workers=414,
        completed_workers=0,retained_timing_rows=0,waited_worker_CPU_us=0,accounting_complete=True,
        child_namespaces_quiescent=True,workers=[dict(j,status="NOT_ATTEMPTED") for j in jobs])
    try:
        with (output/"journal.jsonl").open("xb") as journal:
            for job in jobs:
                require(wall()-started+24000000000 <= 600000000000
                    and paired.credit_admits(state["waited_worker_CPU_us"]),"joint_resource_credit")
                admission(output)
                require(body_usage(root)+FRAGMENT_CAP+RESULT_CAP+OWNER_CAP <= BODY,"remaining_output_credit")
                append_record(journal,dict(kind="launch_intent",**job),128)
                slot=state["workers"][job["ordinal"]]; slot["status"]="ATTEMPTED"
                state["child_namespaces_quiescent"]=False; state["accounting_complete"]=False
                usage=backend.run(job,build,output/"active.jsonl")
                require(type(usage["cpu_us"]) is int and usage["cpu_us"]>=0,"waited_CPU")
                require(type(usage["returncode"]) is int and type(usage["pid"]) is int and usage["pid"]>0,"actual_process_reply")
                slot.update(status="FAILED",exit=usage["returncode"],pid=usage["pid"],cpu_us=usage["cpu_us"],
                    maximum_RSS_kib=usage["maximum_RSS_kib"])
                state["waited_worker_CPU_us"]+=usage["cpu_us"];state["accounting_complete"]=True
                state["child_namespaces_quiescent"]=usage.get("quiescent") is True
                require(state["child_namespaces_quiescent"],"child_custody_UNKNOWN_no_read")
                fragment=output/"active.jsonl"
                require(fragment.stat().st_size<=FRAGMENT_CAP,"fragment_limit")
                data=fragment.read_bytes()
                require(journal.tell()+len(data)<=JOURNAL_CAP,"journal_bound")
                require(journal.write(data)==len(data),"short_fragment_journal");journal.flush();os.fsync(journal.fileno())
                for line in data.splitlines():
                    try:row=json.loads(line)
                    except (ValueError,UnicodeError):continue
                    if type(row) is dict and row.get("kind")=="timing":state["retained_timing_rows"]+=1
                require(usage["returncode"]==0,"worker_exit")
                result=parse_fragment(data,job,usage["pid"],build["agent_schema_reference"],build["packages_sha256"])
                key=(job["case"],job["trial"])
                if key in pending:join_pair(pending.pop(key),result)
                else:pending[key]=result
                records.append(result);state["completed_workers"]+=1
                slot["status"]="COMPLETE";fragment.unlink()
                require(state["waited_worker_CPU_us"]<=512000000,"worker_credit_overage")
            else:
                require(len(records)==414 and state["retained_timing_rows"]==414 and not pending,"registered_completion")
                state["status"]="complete" if all(r["timing"]["wall_ns"]>0 for r in records) else "numerical_refused"
    except Exception as exc:
        state["error"]=dict(type=type(exc).__name__,message=str(exc)[:256])
        for slot in state["workers"]:
            if slot["status"]=="ATTEMPTED":slot["status"]="FAILED_UNKNOWN_EXIT"
    finally:
        try:backend.close()
        except Exception as exc:
            state.update(child_namespaces_quiescent=False,accounting_complete=False,
                cleanup_error=type(exc).__name__+":"+str(exc)[:128])
        if hasattr(backend,"total_cpu_us"):
            try:
                observed=backend.total_cpu_us();require(type(observed) is int and observed>=0,"observed_waited_CPU")
                state["observed_waited_CPU_us"]=observed
                state["waited_worker_CPU_us"]=max(observed,state["waited_worker_CPU_us"])
            except Exception:state["accounting_complete"]=False
        state.update(case_summaries=summaries(records),scheduler_wall_ns=wall()-started,
            controller_CPU_ns=cpu(),external_owner_CPU_wall_RSS=None,
            actual_source=current_source(),no_default_or_wholeturn_science_qualification=True,
            timing_row_count_scope="Counted JSON timing rows after durable raw append; not accepted pairs. Abrupt death can leave additional uncounted rows.")
        if cpu()+state["waited_worker_CPU_us"]*1000>540000000000:
            state.update(status="resource_refused",case_summaries=[])
        require(not any(n=="chronicler_agents" or n.startswith("chronicler_agents.") for n in sys.modules),"controller_Native_loaded")
        # Written ONCE only after the schedule stops and cleanup finishes, before
        # result.json. It cannot be a stale proof from an earlier worker.
        attempted=[r["ordinal"] for r in state["workers"] if r["status"]!="NOT_ATTEMPTED"]
        custody=dict(kind="GP_FULLSYNC_PARENT_CUSTODY",github={k:os.environ.get(k) for k in GITHUB},
            parent_pid=os.getpid(),last_attempted_ordinal=attempted[-1] if attempted else None,
            proven=state["child_namespaces_quiescent"] is True)
        write_new(output/"custody.json",custody,CUSTODY_CAP,root,
            unsafe=() if custody["proven"] else (output.name+"/active.jsonl",))
        write_new(output/"result.json",state,RESULT_CAP,root,
            unsafe=() if state["child_namespaces_quiescent"] else (output.name+"/active.jsonl",))
    return state


def read_parent_record(path, cap):
    """Bounded recovery of closed parent records, with original failure pins."""
    observed={}
    def closed_object(pairs):
        value={}
        for key,item in pairs:
            require(key not in value,"duplicate_parent_key");value[key]=item
        return value
    def nonfinite(value):
        raise ValueError("nonfinite_parent_value")
    try:
        require(not path.is_symlink() and path.is_file() and path.stat().st_size<=cap,"parent_record_file_bound")
        raw=path.read_bytes();require(len(raw)<=cap,"parent_record_read_bound")
        observed=dict(bytes=len(raw),sha256=sha(raw))
        value=json.loads(raw,object_pairs_hook=closed_object,parse_constant=nonfinite)
        require(type(value) is dict,"parent_record_not_object")
        return value,observed,None
    except Exception as exc:
        return None,observed,type(exc).__name__+":"+str(exc)[:160]


def validate_parent_result(value):
    require(type(value) is dict and value.get("kind")=="GP_FULLSYNC_RESULT"
        and type(value.get("planned_workers")) is int and value["planned_workers"]==414
        and value.get("method")==METHOD
        and value.get("actual_source")==current_source(),"parent_result_identity")
    require(value.get("status") in ("complete","numerical_refused","failed","resource_refused")
        and type(value.get("child_namespaces_quiescent")) is bool,"parent_result_state")
    for key in ("completed_workers","retained_timing_rows"):
        require(type(value.get(key)) is int and 0<=value[key]<=414,"parent_result_counts")
    if value["status"] in ("complete","numerical_refused"):
        require(value["completed_workers"]==value["retained_timing_rows"]==414
            and value["child_namespaces_quiescent"],"parent_result_completion")
    return value


def owner(evidence, wheel_dir, comparison_exit):
    """Keep bounded parent failures; child bytes require final custody proof."""
    evidence=evidence.resolve();require(evidence.is_dir(),"evidence_root")
    custody,custody_observed,recovery=read_parent_record(evidence/"comparison/custody.json",CUSTODY_CAP)
    proven=False;result=None;result_observed={}
    if recovery is None:
        try:
            require(set(custody)=={"kind","github","parent_pid","last_attempted_ordinal","proven"}
                and custody.get("kind")=="GP_FULLSYNC_PARENT_CUSTODY"
                and custody.get("github")=={k:os.environ.get(k) for k in GITHUB}
                and type(custody.get("parent_pid")) is int and custody["parent_pid"]>0
                and type(custody.get("proven")) is bool and custody["proven"],"parent_custody_not_proven")
            ordinal=custody.get("last_attempted_ordinal")
            require(ordinal is None or type(ordinal) is int and 0<=ordinal<414,"parent_custody_ordinal")
            proven=True
        except Exception as exc:recovery=type(exc).__name__+":"+str(exc)[:160]
    # No result stat/read/parse before proven final custody. A malformed result
    # never fabricates successful counts and never permits active-child data.
    if proven:
        result,result_observed,error=read_parent_record(evidence/"comparison/result.json",RESULT_CAP)
        if error is None:
            try:result=validate_parent_result(result)
            except Exception as exc:result=None;error=type(exc).__name__+":"+str(exc)[:160]
        if error is not None:recovery=error
    child_allowed=proven and result is not None and result["child_namespaces_quiescent"]
    names=["plan.json","build/build.json","build/rustc.txt","build/cargo.txt","build/maturin.txt","build/uv.txt",
        "comparison/journal.jsonl","comparison/custody.json","comparison.stderr","comparison.time"]
    if proven and result_observed:names.append("comparison/result.json")
    if child_allowed:names.append("comparison/active.jsonl")
    pins=[];total=0;packing=None
    try:
        for name in names:
            p=evidence/name
            if not p.exists():continue
            cap=(JOURNAL_CAP if name.endswith("journal.jsonl") else RESULT_CAP if name.endswith("result.json")
                else CUSTODY_CAP if name.endswith("custody.json") else PLAN_CAP if name=="plan.json"
                else BUILD_CAP if name.endswith("build.json") else FRAGMENT_CAP if name.endswith("active.jsonl")
                else 4096 if name.startswith("build/") else ERROR_CAP)
            require(not p.is_symlink() and p.is_file() and p.stat().st_size<=cap,"safe_owner_file")
            body=p.read_bytes();total+=len(body);pins.append(dict(path=name,bytes=len(body),sha256=sha(body)))
        reserved=(0 if child_allowed else FRAGMENT_CAP)+(0 if proven and result_observed else RESULT_CAP)
        require(total+reserved+OWNER_CAP<=BODY,"owner_inclusive_body")
    except Exception as exc:packing=type(exc).__name__+":"+str(exc)[:160]
    value=dict(kind="GP_FULLSYNC_OWNER",method=METHOD,github={k:os.environ.get(k) for k in GITHUB},
        actual_comparison_exit=comparison_exit,files=pins,child_custody="PROVEN" if proven else "UNKNOWN",
        child_data_allowed=child_allowed,unsafe_active_namespace_read_or_upload=False,
        unknown_active_reserved_bytes=0 if child_allowed else FRAGMENT_CAP,
        unknown_result_reserved_bytes=0 if proven and result_observed else RESULT_CAP,
        body_bytes_known=total,retention="within_cap" if packing is None else "refused",
        refusal=recovery or packing,recovery_problem=recovery,parent_custody_record=custody_observed,
        parent_result_record=result_observed,last_attempted_ordinal=None if not proven else custody["last_attempted_ordinal"],
        completed_workers=None if result is None else result["completed_workers"],
        durable_timing_rows=None if result is None else result["retained_timing_rows"],
        comparison_status="UNKNOWN" if result is None else result["status"],wheels_allowed=False,
        proof_scope="Observed GP/persistent Native/RNG and version identity; no production/whole-turn/science qualification")
    try:
        build=read_build(evidence/"build/build.json")
        wheels=list(wheel_dir.glob("*.whl"));require(len(wheels)==1,"one_wheel")
        file_pin(wheels[0],16*1024**2)
        value["wheels_allowed"]=recovery is None and packing is None and build["source_commit"]==current_source()
    except Exception as exc:
        value["wheel_refusal"]=type(exc).__name__+":"+str(exc)[:160]
    write_new(evidence/"owner.json",value,OWNER_CAP,None)
    selected=[row["path"] for row in pins]+["owner.json"]
    archive=evidence.parent/"gp-fullsync-compact.zip"
    require(not archive.exists(),"fresh_compact_archive")
    require(sum((evidence/n).stat().st_size for n in selected)<=BODY,"selected_body_cap")
    with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in selected:
            z.write(evidence/name,name)
    require(archive.stat().st_size<=ZIP_CAP,"compact_ZIP_cap")
    archive.chmod(0o444)
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as out:
            out.write("compact_allowed="+str(packing is None).lower()+"\n")
            out.write("wheels_allowed="+str(value["wheels_allowed"]).lower()+"\n")
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group()
    for flag in ("plan-only","record-build","execute","worker","owner"):
        modes.add_argument("--"+flag,action="store_true")
    parser.add_argument("--root",type=Path)
    parser.add_argument("--wheel-dir",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--build",type=Path)
    parser.add_argument("--evidence",type=Path)
    parser.add_argument("--ordinal",type=int)
    parser.add_argument("--comparison-exit",type=int)
    args=parser.parse_args(argv)
    if args.plan_only:
        require(args.output is not None,"plan_output")
        write_new(args.output,plan(),PLAN_CAP,args.output.parent);return 0
    if args.record_build:
        require(all(x is not None for x in (args.root,args.wheel_dir,args.output)),"build_arguments")
        record_build(args.root,args.wheel_dir,args.output);return 0
    if args.worker:
        require(args.build is not None and type(args.ordinal) is int and 0<=args.ordinal<414,"worker_selection")
        return worker(schedule()[args.ordinal],args.build)
    if args.execute:
        require(args.build is not None and args.output is not None,"execute_arguments")
        require(args.output.resolve()==args.build.resolve().parents[1]/"comparison","comparison_namespace")
        paired.controller_limits()
        build=read_build(args.build)
        host=host_admission(args.output.parent)
        require(host["MemAvailable"]>=(2*1024**3+128*1024**2),"entry_host_memory")
        result=run_schedule(build,args.output,SystemBackend(args.build))
        return 0 if result["status"]=="complete" else 2
    if args.owner:
        require(args.evidence is not None and args.wheel_dir is not None,"owner_arguments")
        value=owner(args.evidence,args.wheel_dir,args.comparison_exit)
        return 0 if value["retention"]=="within_cap" and value["recovery_problem"] is None else 2
    print('{"kind":"GP_FULLSYNC_BENCHMARK","status":"disabled"}')
    return 0


if __name__=="__main__":
    raise SystemExit(main())
