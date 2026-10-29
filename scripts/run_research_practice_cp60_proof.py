#!/usr/bin/env python3
"""Dormant proof-only seed1999: observed parent62 + two exact CP60 resumes.

Source preparation is not permission to execute. This is not the eight-seed
study and never relaxes its END180 recorder or labels a partial journal complete.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib
import importlib.machinery
import os
from pathlib import Path
import random
import resource
import signal
import subprocess
import sys
import time
from datetime import datetime

import research_practice_contract as C
import research_practice_recorder as T
import run_research_practice_continuation as R
import read_research_practice_continuation as D
import research_practice_trace_reader as Q

SEED, FORK, END = 1999, 60, 62
ROLES = ("parent", "none", "observed")
REGISTRATION = "docs/experiments/practice-observer-cp60-proof-registration-2026-10-29.md"
EXPERIMENT = "practice-observer-cp60-proof-20261029"
SCRIPT, CONTROL = Path(__file__).resolve(), R.CONTROL
STATE_VIEW_PATH = "scripts/profile_ablation_writer_cadence.py"
STATE_VIEW_BLOB = "bc83caaeb31c9136b9bb97d35836b45a31144436"
STATE_VIEW_SHA256 = "80b129632dd4bbc05964e770c8a393ca2ff8a1e17917e50136f0d412ebfaa17b"
LIVE_METHOD_SOURCES = {
    "chronicler-agents/src/ffi/mod.rs": ("d0d68244668505c55042f341fca9bd7cfa54e840", "526c550ee1506c32f1a855c15dd0aca0a24b9e5d41976a6d47998ef01f648b0d"),
    "chronicler-agents/src/pool.rs": ("096a23e111648b9053d2a2a774589861ae73ac83", "cce2b09b3f841d32f87fd133216b4648ac0ff7572a8c40008596b2bedf854ced"),
    "chronicler-agents/src/ffi/schema.rs": ("ac0f3db531dac8eaff61a2ecbb1024165ff1a7d3", "f98a4977ec9b63127f8e342be4aabeeddec59b28bb260b536250501884f5d726"),
}


def write_small(path, value):
    raw = T.encoded(value) + b"\n"
    C.require(len(raw) <= 256*1024, "narrow proof metadata ceiling")
    with Path(path).open("xb") as stream:
        C.require(stream.write(raw) == len(raw), "short narrow proof write")
        stream.flush()
        os.fsync(stream.fileno())


class ProofOwner:
    """Caller-owned clocks/counters plus exactly two post-CP observation frames."""
    def __init__(self, folder, role, observer, *, checkpoint_effort=None):
        C.require(role in ROLES and (observer is None) is (role == "none"), "proof observer role differs")
        C.require(role == "parent" or checkpoint_effort is not None, "actual proof CP counter required")
        self.folder, self.role, self.observer = Path(folder), role, observer
        self.start = 0 if role == "parent" else FORK
        self.expected = None if checkpoint_effort is None else T.uint(checkpoint_effort)
        self.baseline, self.previous, self.world_id, self.pending = None, None, None, None
        self.calls, self.completed, self.frames, self.counters = 0, 0, [], []
        self.checkpoint_effort, self.failed, self.closed = None, False, False

    def begin(self, world, clock):
        try:
            C.require(not self.failed and not self.closed and type(world.seed) is int and world.seed == SEED
                      and type(world.turn) is int and world.turn == self.start + self.completed < END,
                      "proof World/source differs")
            if self.world_id is not None:
                C.require(id(world) == self.world_id, "proof World owner changed")
            if self.baseline is None:
                actual = T.uint(world.scientific_claims.effort_spent)
                C.require(self.expected is None or actual == self.expected, "proof actual CP counter differs")
                self.world_id, self.previous = id(world), actual
                self.baseline = dict(seed=SEED, role=self.role, source_turn=world.turn,
                    initial_effort_spent=actual, expected_checkpoint_effort=self.expected, clock=clock)
                write_small(self.folder / "proof-baseline.json", self.baseline)
        except BaseException:
            self.failed = True
            raise

    def run_turn_result(self, world, *args, **kwargs):
        try:
            C.require(self.observer is not None and self.pending is None, "proof cannot repeat physics")
            self.begin(world, "actual World immediately before public observer/physics call")
            source = world.turn
            self.calls += 1
            result = self.observer.run_turn_result(world, *args, **kwargs)
            C.require(type(world.turn) is int and world.turn == source+1 and
                      type(result.observation.source_turn) is int and result.observation.source_turn == source and
                      type(result.observation.completed_turn) is int and result.observation.completed_turn == source+1,
                      "proof returned turn stamps differ")
            self.pending = source
            return result
        except BaseException:
            self.failed = True
            raise

    def record_turn_end(self, world):
        try:
            source = self.start + self.completed
            C.require(not self.failed and not self.closed and self.baseline is not None and
                      id(world) == self.world_id and type(world.turn) is int and world.turn == source+1 and
                      (self.observer is None or self.pending == source), "proof completed boundary differs")
            actual = T.uint(world.scientific_claims.effort_spent)
            C.require(actual >= self.previous, "proof counter decreased")
            if world.turn == FORK:
                self.checkpoint_effort = actual
            if source >= FORK:
                C.require(source < END and len(self.counters) < 2, "narrow proof retention window")
                self.counters.append(dict(source_turn=source, before=self.previous, after=actual, delta=actual-self.previous))
                if self.observer is not None:
                    frame = T.copy_frame(self.observer.read_latest(expected_source_turn=source), source, self.calls)
                    C.require(frame["status"] == "captured", "actual post-CP proof frame unavailable")
                    accounting = T.accounting(frame, self.previous, actual)
                    C.require(accounting["status"] == "matched", "actual proof group debit differs")
                    self.frames.append(dict(source_turn=source, frame=frame, accounting=accounting))
            self.previous, self.pending, self.completed = actual, None, self.completed+1
        except BaseException:
            self.failed = True
            raise

    def finish(self):
        try:
            C.require(not self.failed and not self.closed and self.pending is None and self.completed == END-self.start
                      and self.calls == (END-self.start if self.observer is not None else 0)
                      and len(self.counters) == 2 and len(self.frames) == (2 if self.observer is not None else 0),
                      "narrow proof window incomplete")
            report = dict(kind="practice-cp60-two-source-observation", seed=SEED, role=self.role,
                source_start=self.start, source_end=END-1, actual_physics_ticks=self.completed,
                capture_enabled=self.observer is not None, retained_sources=[60, 61], selected_pairs=T.SELECTED,
                selected_rows_per_frame=16, expected_retained_frames=2 if self.observer is not None else 0,
                initial_effort_spent=self.baseline["initial_effort_spent"], checkpoint_effort_spent=self.checkpoint_effort,
                final_effort_spent=self.previous, counters=self.counters, frames=self.frames,
                scope="two post-CP sources only; no complete180-turn study journal or causal growth claim")
            write_small(self.folder / "proof-observation.json", report)
            return report
        except BaseException:
            self.failed = True
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            if self.observer is not None:
                self.observer.close()

    def __getstate__(self):
        raise TypeError("narrow proof owner is transient caller state")


class ProofBoundary(R.BoundaryCapture):
    def __init__(self, folder, frozen, owner, loaded):
        super().__init__(folder, frozen, owner, parent=owner.role == "parent")
        self.loaded = loaded

    def bind(self, save, config):
        super().bind(save, config)
        if self.owner.observer is None:
            C.require(self.loaded is not None and self.loaded.exact and not self.loaded.mismatches,
                      "None proof requires actual exact loaded checkpoint")
            self.owner.begin(self.loaded.state.world, "actual restored World alias after normal configure at Boundary.bind")

    def turn_end(self, world):
        if self.loaded is not None:
            C.require(world is self.loaded.state.world, "main did not use the actual restored World alias")
        return super().turn_end(world)


def metadata_freeze(options):
    """Retain actual three-class metadata before the fail-closed identity gate."""
    source, path = Path(options.source_root).resolve(), Path(options.freeze).resolve()
    C.require(not path.exists() and not any(path.is_relative_to(root) for root in (source, CONTROL)),
              "fresh external proof metadata required")
    C.source_snapshot(source, C.SOURCE)
    C.source_snapshot(CONTROL)
    selected = C.P.policy()
    R.policy_evidence(source, selected, options.wheel_receipt)
    if "chronicler" not in sys.modules:
        sys.path.insert(0, str(source / "src"))
    else:
        C.require(Path(sys.modules["chronicler"].__file__).resolve().parent == source / "src/chronicler",
                  "foreign source before proof metadata")
    from chronicler.batch_manifest import environment_identity, native_identity, source_identity
    import chronicler_agents as public
    compiled = importlib.import_module("chronicler_agents.chronicler_agents")
    origin = Path(compiled.__file__).resolve()
    C.require(str(origin).endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)), "proof native origin is not compiled")
    classes = {}
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(public, name)
        C.require(type(cls) is type and cls is getattr(compiled, name), "proof compiled class alias differs")
        version, fingerprint, schema = cls.checkpoint_schema()
        classes[name] = dict(version=version, fingerprint=fingerprint,
                             schema_sha256=hashlib.sha256(schema.encode()).hexdigest())
    actual = dict(source=source_identity(), native=native_identity(), environment=environment_identity(),
                  compiled_origin=str(origin), available_compiled_classes=classes)
    C.write(path.with_name("proof-metadata-observation.json"), dict(kind="actual-class-schema-metadata",
        runtime=actual, source_bound_schema_class_calls=3,
        scope="three static checkpoint_schema calls; source path contains no World/pool construction or physics entry"))
    # This repeats the static metadata calls and validates every source, wheel,
    # Python/package/thread/affinity/native/schema condition before any World.
    frozen = R.identity(source, C.P.DEFAULT_POLICY, options.wheel_receipt)
    C.require(C.same(actual, frozen["runtime"]), "actual metadata changed during proof freeze")
    C.write(path, frozen)


def proof_args(folder, role):
    values = R.simulation_args(folder, SEED, "parent" if role == "parent" else "active")
    values[values.index("--turns")+1] = str(END)
    values[values.index("--checkpoint-turns")+1] = "60,62" if role == "parent" else "62"
    return values


def decoded_projection(loaded):
    # Existing source-owned semantic carried/native projection. The diagnostic
    # also computes pickle hashes; those are deliberately discarded here.
    C.require(C.sha(CONTROL / STATE_VIEW_PATH) == STATE_VIEW_SHA256 and
              C.git(CONTROL, "rev-parse", "HEAD:"+STATE_VIEW_PATH).decode().strip() == STATE_VIEW_BLOB,
              "source-owned state projection changed")
    from profile_ablation_writer_cadence import state_view
    view = state_view(loaded.state)
    C.closed(view, {"turn", "carried", "native", "memory_pickle_sha256", "memory_cache", "python_pickle_sha256"}, "source state view")
    C.closed(view["carried"], {"world", "world_extras", "private_signals", "archives", "bridge_python", "memories",
        "history", "chronicle_entries", "era_reflections", "pending_injections", "economy_tracker"}, "source carried state")
    C.require(all(type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
                  for value in view["carried"].values()), "source state signature type differs")
    C.require(type(view["native"]) is dict and set(view["native"]) == {"agent.0"}
              and type(view["memory_cache"]) is dict, "source state native/cache fields differ")
    C.closed(view["native"]["agent.0"], {"bytes", "sha256"}, "source native state")
    C.require(type(view["native"]["agent.0"]["bytes"]) is int and view["native"]["agent.0"]["bytes"] > 0,
              "source native state is empty")
    digest = view["native"]["agent.0"]["sha256"]
    C.require(type(digest) is str and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
              "source native state digest differs")
    state, world = loaded.state, loaded.state.world
    C.require(state.live is None and not any("observer" in key or key == "_practice_trace"
              for obj in (state, world) for key in vars(obj)), "observer persisted into decoded state")
    C.require("practice_observer" not in state.run_config, "observer config persisted")
    return dict(turn=view["turn"], carried=view["carried"], native=view["native"], memory_cache=view["memory_cache"],
                transient_state_absent=True,
                scope="source-owned semantic carried/native projection; no raw checkpoint or Python pickle byte identity")


def checked_checkpoint(path, frozen, *, turn, resumed):
    """Bounded envelope/header/source/schema checks before trusted decoding."""
    header, sections = C.checkpoint_sections(path)
    C.checkpoint_build_identity(header, frozen)
    for key, value in dict(turn=turn, seed=SEED, start_turn=0, num_turns=END, exact=True).items():
        C.require(C.same(header[key], value), "proof checkpoint header differs: "+key)
    config = header["run_config"]
    lineage = [dict(resumed_at=FORK, kind="checkpoint", exact=True)] if resumed else []
    C.require(C.same(header["lineage"], C.checkpoint_projection(lineage)) and
              C.same(config["lineage"], C.checkpoint_projection(lineage)) and config["resume_info"] is None,
              "proof exact resume lineage differs")
    for key, value in dict(agents="hybrid", worldgen="template", regions=8, civs=4, scholarship=True,
                          techniques=True, scientific_claims=True, scientific_research_agendas=True).items():
        C.require(C.same(config["simulation_args"][key], value), "proof simulation config differs: "+key)
    for key in ("scholarship", "techniques", "scientific_claims", "scientific_research_agendas"):
        C.require(header["flags"][key] is True, "proof enabled feature differs")
    for key in ("health_care", "harvest_forecasts", "ritual_gatherings", "transaction_receipts"):
        C.require(header["flags"][key] is False and config["simulation_args"][key] is False, "proof disabled feature differs")
    receipt = config["expansion_experiment"]
    for key, value in dict(schema_version=1, experiment=EXPERIMENT, cohort="development", feature="scientific_claims",
                          arm="parent", intervention_fork=False, applied_before_turn=0, seed=SEED).items():
        C.require(C.same(receipt[key], value), "proof control receipt differs: "+key)
    C.require(receipt["parent_checkpoint"] is None and receipt["previous_experiment"] is None and
              C.same(receipt["controls_after"], C.checkpoint_projection(C.CONTROLS)) and
              C.same(receipt["source"], C.checkpoint_projection(frozen["runtime"]["source"])) and
              C.same(receipt["native"], C.checkpoint_projection(frozen["runtime"]["native"])) and
              C.same(receipt["registration"], C.checkpoint_projection(dict(path=str(CONTROL / REGISTRATION),
                  sha256=frozen["control"]["files"][REGISTRATION]["sha256"]))), "proof source/native/registration receipt differs")
    policy = receipt["research_policy"]
    C.require(C.same(policy["before"], policy["after"]) and policy["requested_enabled"] is None and
              policy["after"]["enabled"] is True and type(policy["after"]["enabled_turn"]) is int and policy["after"]["enabled_turn"] == 0,
              "proof changed research admission")
    C.require({name for name in sections if name.startswith("native.")} == {"native.agent.0"}, "proof active native section differs")
    return header, sections


def live_rows(batch):
    """Exactly eight scalar count rows; no agent-body/snapshot cache access."""
    C.require(type(batch.num_rows) is int and batch.num_rows == 8 and
              type(batch.num_columns) is int and batch.num_columns == 2 and
              batch.schema.names == ["region_id", "alive_count"], "native live-count table differs")
    ids, counts = [], []
    for name, target, maximum in (("region_id", ids, 7), ("alive_count", counts, 2**32-1)):
        column = batch.column(name)
        C.require(column.null_count == 0, "native live-count column contains null")
        values = column.to_pylist()
        C.require(type(values) is list and len(values) == 8, "native live-count scalar bound")
        target.extend(T.uint(value, maximum) for value in values)
    C.require(ids == list(range(8)) and sum(counts) > 0, "native live pool is empty or region rows differ")
    return dict(region_ids=ids, alive_counts=counts, in_bounds_live_count=T.uint(sum(counts)))


def live_population(loaded, checkpoint_path, frozen):
    for name, (blob, digest) in LIVE_METHOD_SOURCES.items():
        C.require(frozen["producer"]["files"][name]["sha256"] == digest and
                  C.git(CONTROL, "rev-parse", "HEAD:"+name).decode().strip() == blob,
                  "read-only live-count method source differs")
    # This shared check binds the actual object to the compiled AgentSimulator
    # and to this exact checkpoint's active native section/schema.
    native = R.native_records(loaded, checkpoint_path)["native.agent.0"]
    sim = loaded.state.agent_bridge._sim
    before = bytes(sim.checkpoint_state())
    C.require(len(before) <= C.MAX_METADATA and hashlib.sha256(before).hexdigest() == native["sha256"],
              "live-count actual native payload differs before read")
    rng = R.rng_state()
    cache_before = sim.snapshot_is_cached()
    observed = live_rows(sim.get_region_populations())
    cache_after = sim.snapshot_is_cached()
    C.require(type(cache_before) is bool and type(cache_after) is bool and cache_before is cache_after and
              bytes(sim.checkpoint_state()) == before and C.same(rng, R.rng_state()),
              "native live-count read changed payload/RNG/cache")
    return dict(**observed, world_turn=loaded.state.world.turn, checkpoint_sha256=C.sha(checkpoint_path),
        native_payload_sha256=native["sha256"], native_payload_bytes=len(before),
        native_payload_and_caller_rng_unchanged=True,
        snapshot_cache_before=cache_before, snapshot_cache_after=cache_after,
        method="compiled get_region_populations(&self); exactly8rows, no snapshot_cache write",
        method_sources={name: dict(blob=blob, sha256=digest) for name, (blob, digest) in LIVE_METHOD_SOURCES.items()})


def worker(options):
    resource.setrlimit(resource.RLIMIT_CPU, (C.WORKER_CPU, C.WORKER_CPU))
    resource.setrlimit(resource.RLIMIT_FSIZE, (C.MAX_METADATA, C.MAX_METADATA))
    source, root = Path(options.source_root).resolve(), Path(options.output_root).resolve()
    frozen = R.verify_freeze(source, options.freeze, C.P.DEFAULT_POLICY, options.wheel_receipt)
    # All exact source/runtime/native/three-schema checks above precede imports
    # or calls that can generate/restore a World or construct a native pool.
    import numpy as np
    from chronicler import main
    from chronicler.run_checkpoint import read_checkpoint
    folder, role = root / options.role, options.role
    parent_path = root / "parent/checkpoint_turn_60.ckpt"
    parser = main._build_parser()
    args = parser.parse_args(proof_args(folder, role))
    loaded, parent, owner, restored_live = None, None, None, None
    decodes = []
    def decode(path, *, turn, resumed, purpose, stepped_after):
        checked_checkpoint(path, frozen, turn=turn, resumed=resumed)
        value = read_checkpoint(path)
        C.require(value.exact and not value.mismatches, "proof trusted checkpoint decode is not exact")
        decodes.append(dict(turn=turn, checkpoint_sha256=C.sha(path), purpose=purpose,
                            stepped_after=stepped_after, source_native_schema_checked_before_decode=True))
        return value
    try:
        if role == "parent":
            random.seed(SEED)
            np.random.seed(SEED)
            C.write(folder / "initial-rng.json", R.rng_state())
        else:
            loaded = decode(parent_path, turn=FORK, resumed=False, purpose="execution-start-cp60", stepped_after=True)
            C.require(loaded.exact and not loaded.mismatches and loaded.state.world.turn == FORK
                      and loaded.state.world.seed == SEED, "proof parent is not actual exact CP60")
            C.checkpoint_build_identity(loaded.header, frozen)
            parent = dict(checkpoint_sha256=C.sha(parent_path), header=loaded.header,
                world=loaded.state.world.model_dump(mode="json"),
                history=[row.model_dump(mode="json") for row in loaded.state.history],
                native=R.native_records(loaded, parent_path), run_config=deepcopy(loaded.state.run_config))
            C.write(folder / "restore.json", parent)
            restored_live = live_population(loaded, parent_path, frozen)
            C.require(not main._adopt_checkpoint_args(parser, args, loaded), "proof saved/CLI arguments conflict")
            sidecar = C.read(parent_path.parent / "boundary-rng.json")
            header, sections = C.checkpoint_sections(parent_path)
            C.require(sidecar["seed"] == SEED and sidecar["turn"] == FORK and
                      sidecar["checkpoint_sha256"] == parent["checkpoint_sha256"] and
                      C.same(sidecar["checkpoint_sections"], sections) and
                      C.same(sidecar["producer_runtime"], frozen["runtime"]) and
                      sidecar["controls_sha256"] == C.digest(frozen["controls"]) and
                      sidecar["state_sha256"] == C.digest(sidecar["state"]), "proof actual CP/RNG linkage differs")
            R.restore_rng(sidecar["state"])
            C.write(folder / "restored-rng.json", dict(sidecar_sha256=C.sha(parent_path.parent / "boundary-rng.json"),
                                                     state_sha256=C.digest(R.rng_state())))
        observer = None
        if role != "none":
            from chronicler.practice_growth import PracticeGrowthObserver
            observer = PracticeGrowthObserver(T.SELECTED, max_rows=16, max_encoded_bytes=T.ROW_BYTES)
        expected = parent["world"]["scientific_claims"]["effort_spent"] if parent else None
        owner = ProofOwner(folder, role, observer, checkpoint_effort=expected)
        boundary = ProofBoundary(folder, frozen, owner, loaded)
        experiment = None
        if role == "parent":
            experiment = dict(schema_version=1, experiment=EXPERIMENT, cohort="development", feature="scientific_claims",
                arm="parent", controls=dict(C.CONTROLS), fork=False,
                registration=dict(path=str(CONTROL / REGISTRATION), sha256=C.sha(CONTROL / REGISTRATION)))
        # None is passed literally in the control arm; no default-path wrapper.
        result = main.execute_run(args, checkpoint_resume=loaded, expansion_experiment=experiment,
                                  turn_boundary=boundary, practice_observer=owner if observer is not None else None)
        final_rng = R.rng_state()  # Before trusted final checkpoint decoding.
        observation = owner.finish()
        C.require(role != "parent" or boundary.captured, "actual parent CP60/RNG not captured")
        final_path = folder / "checkpoint_turn_62.ckpt"
        final = decode(final_path, turn=END, resumed=role != "parent", purpose="unstepped-final-cp62-validation", stepped_after=False)
        C.require(final.exact and not final.mismatches and final.state.world.turn == END and
                  final.state.world.seed == SEED, "proof final checkpoint is not exact same-source state")
        C.checkpoint_build_identity(final.header, frozen)
        world = final.state.world.model_dump(mode="json")
        history = [row.model_dump(mode="json") for row in final.state.history]
        C.require([row["turn"] for row in history] == list(range(1, END+1)), "proof complete history differs")
        C.require(C.same(world, C.read(folder / "state.json")), "ordinary export differs from decoded World")
        C.write(folder / "raw-history.json", history)
        native = R.native_records(final, final_path, folder)
        C.write(folder / "decoded-checkpoint.json", decoded_projection(final))
        final_live = live_population(final, final_path, frozen)
        if role == "parent":
            parent_loaded = decode(parent_path, turn=FORK, resumed=False,
                                   purpose="unstepped-parent-cp60-inspection-after-normal-run", stepped_after=False)
            C.require(parent_loaded.exact and not parent_loaded.mismatches, "proof parent CP60 restore differs")
            restored_live = live_population(parent_loaded, parent_path, frozen)
        C.write(folder / "native-live-population.json", dict(restored_cp60=restored_live, final_cp62=final_live,
            scope="actual restored/final compiled instances; positive live counts, separate from nonempty payload bytes"))
        stats = asdict(result)
        # RunResult covers the saved run origin0; newly stepped ticks are the
        # independent owner.completed ledger (62 for parent,2 for each resume).
        C.require(result.output_dir == folder and type(result.total_turns) is int and result.total_turns == END and
                  type(owner.completed) is int and owner.completed == END-(0 if role == "parent" else FORK),
                  "proof normal RunResult handoff differs")
        stats["output_dir"] = str(stats["output_dir"])
        C.write(folder / "worker-summary.json", dict(seed=SEED, role=role, execution_complete=True,
            actual_physics_ticks=owner.completed, final_turn=END, final_rng=final_rng,
            final_rng_sha256=C.digest(final_rng), world_sha256=C.digest(world), history_sha256=C.digest(history),
            header=final.header, run_config=final.state.run_config, native=native, result=stats,
            observation_sha256=C.sha(folder / "proof-observation.json"),
            baseline_sha256=C.sha(folder / "proof-baseline.json"),
            native_live_sha256=C.sha(folder / "native-live-population.json"),
            parent_checkpoint_sha256=parent["checkpoint_sha256"] if parent else None,
            trusted_checkpoint_decodes=decodes, fresh_world_generation_calls=int(role == "parent"),
            registered_control_sha256=C.sha(CONTROL / REGISTRATION)))
    finally:
        if owner is not None:
            owner.close()
        after = R.verify_freeze(source, options.freeze, C.P.DEFAULT_POLICY, options.wheel_receipt)
        C.write(folder / "worker-identity.json", dict(before=frozen, after=after, identities_stable=C.same(frozen, after)))


PROOF_FILES = {"proof-baseline.json", "proof-observation.json", "decoded-checkpoint.json", "native-live-population.json",
               "checkpoint_turn_60.ckpt", "checkpoint_turn_62.ckpt"}


def inspect_role(root, source, role, frozen):
    """Detached JSON/envelope checks; never decode checkpoint Python here."""
    folder = Path(root) / role
    summary, baseline, observed = (C.read(folder / name) for name in (
        "worker-summary.json", "proof-baseline.json", "proof-observation.json"))
    C.closed(summary, {"seed", "role", "execution_complete", "actual_physics_ticks", "final_turn", "final_rng",
        "final_rng_sha256", "world_sha256", "history_sha256", "header", "run_config", "native", "result",
        "observation_sha256", "baseline_sha256", "native_live_sha256", "parent_checkpoint_sha256",
        "trusted_checkpoint_decodes", "fresh_world_generation_calls", "registered_control_sha256"}, "proof worker summary")
    C.closed(baseline, {"seed", "role", "source_turn", "initial_effort_spent", "expected_checkpoint_effort", "clock"}, "proof baseline")
    C.closed(observed, {"kind", "seed", "role", "source_start", "source_end", "actual_physics_ticks", "capture_enabled",
        "retained_sources", "selected_pairs", "selected_rows_per_frame", "expected_retained_frames", "initial_effort_spent",
        "checkpoint_effort_spent", "final_effort_spent", "counters", "frames", "scope"}, "narrow proof observation")
    for value in (baseline["initial_effort_spent"], observed["initial_effort_spent"], observed["final_effort_spent"]):
        T.uint(value)
    for value in (baseline["expected_checkpoint_effort"], observed["checkpoint_effort_spent"]):
        if value is not None:
            T.uint(value)
    C.require(summary["seed"] == SEED and summary["role"] == role and summary["execution_complete"] is True and
              summary["actual_physics_ticks"] == (END if role == "parent" else END-FORK) and
              summary["final_turn"] == END, "proof worker completion differs")
    expected_decodes = ([(END, "unstepped-final-cp62-validation", False),
                         (FORK, "unstepped-parent-cp60-inspection-after-normal-run", False)] if role == "parent" else
                        [(FORK, "execution-start-cp60", True), (END, "unstepped-final-cp62-validation", False)])
    C.require(type(summary["trusted_checkpoint_decodes"]) is list and len(summary["trusted_checkpoint_decodes"]) == 2 and
              C.same(summary["fresh_world_generation_calls"], int(role == "parent")), "proof generation/decode ledger differs")
    for event, (turn, purpose, stepped) in zip(summary["trusted_checkpoint_decodes"], expected_decodes):
        path = Path(root) / "parent/checkpoint_turn_60.ckpt" if turn == FORK else folder / "checkpoint_turn_62.ckpt"
        C.require(C.same(event, dict(turn=turn, checkpoint_sha256=C.sha(path), purpose=purpose,
                       stepped_after=stepped, source_native_schema_checked_before_decode=True)), "proof actual decode purpose differs")
    identity, cleanup = C.read(folder / "worker-identity.json"), C.read(folder / "cleanup.json")
    C.require(identity["identities_stable"] is True and C.same(identity["before"], frozen) and C.same(identity["after"], frozen),
              "proof worker source/runtime changed")
    C.require(cleanup["complete"] is True and cleanup["accounting"]["returncode"] == 0 and
              0 <= cleanup["accounting"]["tree_cpu_seconds"] <= C.WORKER_CPU, "proof process cleanup/accounting differs")
    header, sections = checked_checkpoint(folder / "checkpoint_turn_62.ckpt", frozen, turn=END, resumed=role != "parent")
    C.require(C.same(header, summary["header"]) and C.same(header["run_config"], C.checkpoint_projection(summary["run_config"])),
              "proof decoded header/config attestation differs")
    state, history = C.read(folder / "state.json"), C.read(folder / "raw-history.json")
    C.require(type(state["seed"]) is int and state["seed"] == SEED and state["turn"] == END and
              len(state["regions"]) == 8 and len(state["civilizations"]) >= 4 and state["agent_mode"] == "hybrid" and
              C.digest(state) == summary["world_sha256"] and C.digest(history) == summary["history_sha256"] and
              [row["turn"] for row in history] == list(range(1, END+1)), "proof ordinary World/history differs")
    decode, strict, prune = D.codec(source, frozen)
    bundle = decode(C.read(folder / "chronicle_bundle.json"))
    pruned, tails = prune(history)
    C.require(C.same(pruned, bundle["history"]) and C.same(tails, bundle["pruned_civ_stats"]) and
              C.same(state["scientific_claims"], bundle["world_state"]["scientific_claims"]), "proof raw/export/pruned history linkage differs")
    C.validate_rng_json(summary["final_rng"])
    C.require(C.digest(summary["final_rng"]) == summary["final_rng_sha256"], "proof actual final RNG hash differs")
    native = summary["native"]
    C.require(set(native) == {"native.agent.0"}, "proof actual native set differs")
    for name, row in native.items():
        C.require(all(C.same(row[key], value) for key, value in sections[name].items()) and
                  C.sha(folder / (name+"-final.bin")) == row["sha256"] and row["class_name"] == "AgentSimulator" and
                  all(C.same(row[key], value) for key, value in frozen["runtime"]["available_compiled_classes"]["AgentSimulator"].items()),
                  "proof actual native section/class/schema differs")
    projection = C.read(folder / "decoded-checkpoint.json")
    C.require(projection["transient_state_absent"] is True and projection["turn"] == END and
              projection["native"] == {"agent.0": {key: native["native.agent.0"][key] for key in ("bytes", "sha256")}},
              "proof semantic/native decoded projection differs")
    live = C.read(folder / "native-live-population.json")
    C.closed(live, {"restored_cp60", "final_cp62", "scope"}, "actual native live observations")
    C.require(C.sha(folder / "native-live-population.json") == summary["native_live_sha256"], "actual live-population bytes differ")
    for key, turn, path in (("restored_cp60", FORK, Path(root) / "parent/checkpoint_turn_60.ckpt"),
                            ("final_cp62", END, folder / "checkpoint_turn_62.ckpt")):
        row = live[key]
        C.closed(row, {"region_ids", "alive_counts", "in_bounds_live_count", "world_turn", "checkpoint_sha256",
            "native_payload_sha256", "native_payload_bytes", "native_payload_and_caller_rng_unchanged",
            "snapshot_cache_before", "snapshot_cache_after", "method", "method_sources"}, "actual native live witness")
        C.require(type(row["region_ids"]) is list and row["region_ids"] == list(range(8)) and
                  all(type(value) is int and 0 <= value < 8 for value in row["region_ids"]) and
                  type(row["alive_counts"]) is list and len(row["alive_counts"]) == 8 and
                  all(type(value) is int and 0 <= value <= 2**32-1 for value in row["alive_counts"]) and
                  type(row["in_bounds_live_count"]) is int and row["in_bounds_live_count"] == sum(row["alive_counts"]) > 0 and
                  row["world_turn"] == turn and row["checkpoint_sha256"] == C.sha(path) and
                  row["native_payload_and_caller_rng_unchanged"] is True and
                  type(row["snapshot_cache_before"]) is bool and row["snapshot_cache_before"] is row["snapshot_cache_after"] and
                  row["method_sources"] == {name: dict(blob=blob, sha256=digest) for name, (blob, digest) in LIVE_METHOD_SOURCES.items()},
                  "actual restored/final live population not witnessed")
        _, live_sections = C.checkpoint_sections(path)
        C.require(row["native_payload_sha256"] == live_sections["native.agent.0"]["sha256"] and
                  row["native_payload_bytes"] == live_sections["native.agent.0"]["bytes"] > 0,
                  "actual live instance is not bound to checkpoint native section")
    C.require(summary["observation_sha256"] == C.sha(folder / "proof-observation.json") and
              summary["baseline_sha256"] == C.sha(folder / "proof-baseline.json"), "proof observation bytes differ")
    start, enabled = (0 if role == "parent" else FORK), role != "none"
    for key, value in dict(kind="practice-cp60-two-source-observation", seed=SEED, role=role,
            source_start=start, source_end=END-1, actual_physics_ticks=END-start, capture_enabled=enabled,
            retained_sources=[60, 61], selected_pairs=[list(pair) for pair in T.SELECTED], selected_rows_per_frame=16,
            expected_retained_frames=2 if enabled else 0).items():
        C.require(C.same(observed[key], value), "proof retained window differs: "+key)
    C.require(type(observed["frames"]) is list and len(observed["frames"]) == (2 if enabled else 0) and
              type(observed["counters"]) is list and len(observed["counters"]) == 2 and
              observed["final_effort_spent"] == state["scientific_claims"]["effort_spent"] and
              C.same(observed["initial_effort_spent"], baseline["initial_effort_spent"]), "proof actual counter coverage differs")
    for counter in observed["counters"]:
        C.closed(counter, {"source_turn", "before", "after", "delta"}, "proof actual counter")
        for key in counter:
            T.uint(counter[key])
        C.require(counter["after"]-counter["before"] == counter["delta"], "proof actual counter delta differs")
    C.require([row["source_turn"] for row in observed["counters"]] == [60, 61] and
              observed["counters"][1]["before"] == observed["counters"][0]["after"] and
              observed["counters"][-1]["after"] == observed["final_effort_spent"], "proof post-CP counter clocks differ")
    for entry, counter in zip(observed["frames"], observed["counters"]):
        C.closed(entry, {"source_turn", "frame", "accounting"}, "proof frame")
        source_turn = counter["source_turn"]
        frame = Q.copied_frame(entry["frame"], source_turn, source_turn-start+1)
        C.require(entry["source_turn"] == source_turn and frame["status"] == "captured" and
                  C.same(entry["accounting"], T.accounting(frame, counter["before"], counter["after"])),
                  "proof actual frame/group debit differs")
    C.require(baseline["seed"] == SEED and baseline["role"] == role and baseline["source_turn"] == start and
              summary["registered_control_sha256"] == frozen["control"]["files"][REGISTRATION]["sha256"], "proof baseline/control provenance differs")
    expected_clock = ("actual restored World alias after normal configure at Boundary.bind" if role == "none"
                      else "actual World immediately before public observer/physics call")
    C.require(baseline["clock"] == expected_clock, "proof baseline clock differs")
    return dict(summary=summary, state=state, history=history, bundle=bundle, projection=projection,
                observation=observed, baseline=baseline, live=live, files=C.inventory(folder))


def compare(root, source, role, frozen):
    C.require(role in ("none", "observed"), "proof comparison role differs")
    parent, resumed = (inspect_role(root, source, name, frozen) for name in ("parent", role))
    actual_parent = C.read(Path(root) / role / "restore.json")
    parent_path = Path(root) / "parent/checkpoint_turn_60.ckpt"
    header, sections = checked_checkpoint(parent_path, frozen, turn=FORK, resumed=False)
    C.require(actual_parent["checkpoint_sha256"] == C.sha(parent_path) == resumed["summary"]["parent_checkpoint_sha256"] and
              C.same(actual_parent["header"], header) and C.same(actual_parent["history"], resumed["history"][:FORK]) and
              C.same(parent["history"][:FORK], actual_parent["history"]), "proof exact common CP/prefix differs")
    expected = actual_parent["world"]["scientific_claims"]["effort_spent"]
    C.require(C.same(expected, parent["observation"]["checkpoint_effort_spent"]) and
              C.same(expected, parent["observation"]["counters"][0]["before"]) and
              C.same(expected, resumed["baseline"]["expected_checkpoint_effort"]) and
              C.same(expected, resumed["baseline"]["initial_effort_spent"]), "proof actual CP counter baseline differs")
    sidecar = C.read(parent_path.parent / "boundary-rng.json")
    restored = C.read(Path(root) / role / "restored-rng.json")
    C.require(sidecar["checkpoint_sha256"] == C.sha(parent_path) and C.same(sidecar["checkpoint_sections"], sections) and
              sidecar["seed"] == SEED and sidecar["turn"] == FORK and
              C.same(sidecar["producer_runtime"], frozen["runtime"]) and sidecar["controls_sha256"] == C.digest(frozen["controls"]) and
              restored["sidecar_sha256"] == C.sha(parent_path.parent / "boundary-rng.json") and
              sidecar["state_sha256"] == C.digest(sidecar["state"]) == restored["state_sha256"], "proof actual boundary RNG differs")
    C.validate_rng_json(sidecar["state"])
    outputs = []
    for item in (parent, resumed):
        ordinary = D.ordinary({name: value for name, value in item["files"].items() if name not in PROOF_FILES})
        bundle = deepcopy(item["bundle"])
        generated = bundle["metadata"].pop("generated_at")
        C.require(type(generated) is str and datetime.fromisoformat(generated).utcoffset() is not None, "proof writer timestamp differs")
        # Exact continuation retains the original experiment and resume label;
        # unlike the study intervention forks, neither is removed here.
        ordinary["chronicle_bundle.json"] = bundle
        outputs.append(ordinary)
    C.require(C.same(outputs[0], outputs[1]) and C.same(parent["state"], resumed["state"]) and
              C.same(parent["history"], resumed["history"]) and C.same(parent["projection"], resumed["projection"]) and
              C.same(parent["summary"]["native"], resumed["summary"]["native"]) and
              C.same(parent["summary"]["final_rng"], resumed["summary"]["final_rng"]) and
              C.same(parent["observation"]["counters"], resumed["observation"]["counters"]), "proof ordinary/native/RNG/counter identity failed")
    # Each live witness's own checkpoint hash is validated above. Parent/fork
    # final envelopes carry different exact-resume lineage; do not compare raw
    # checkpoint hashes or waive any unvalidated field here.
    live_fields = ("region_ids", "alive_counts", "in_bounds_live_count", "world_turn", "native_payload_sha256",
                   "native_payload_bytes", "native_payload_and_caller_rng_unchanged", "snapshot_cache_before",
                   "snapshot_cache_after", "method", "method_sources")
    C.require(C.same({stage: {key: parent["live"][stage][key] for key in live_fields} for stage in ("restored_cp60", "final_cp62")},
                     {stage: {key: resumed["live"][stage][key] for key in live_fields} for stage in ("restored_cp60", "final_cp62")}),
              "proof actual restored/final live populations differ")
    frames_equal = None
    if role == "observed":
        def normalized(item):
            return [{**entry, "frame": {**entry["frame"], "attempt": "validated_owner_attempt"}}
                    for entry in item["observation"]["frames"]]
        frames_equal = C.same(normalized(parent), normalized(resumed))
        C.require(frames_equal, "proof actual post-CP trace differs")
        plain = inspect_role(root, source, "none", frozen)
        stats = [deepcopy(item["summary"]["result"]) for item in (plain, resumed)]
        for item in stats:
            item.pop("output_dir")
        C.require(C.same(stats[0], stats[1]), "proof observed/None result handoff differs")
    return dict(seed=SEED, role=role, ordinary_state_history_outputs_equal=True, decoded_semantic_native_equal=True,
        actual_python_numpy_rng_equal=True, actual_counter_baseline_and_deltas_equal=True,
        actual_post_cp_trace_equal=frames_equal, timestamp_normalization_only=True,
        scope="same-source exact CP60 continuation; observed parent first60 is not an unobserved-fresh-world comparison")


def _proof_run(options):
    started = time.monotonic()
    own0, child0 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    base = own0.ru_utime+own0.ru_stime+child0.ru_utime+child0.ru_stime
    def cpu():
        own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        return own.ru_utime+own.ru_stime+children.ru_utime+children.ru_stime-base
    source, root = Path(options.source_root).resolve(), Path(options.output_root).resolve()
    C.require(not root.exists() and all(not root.is_relative_to(path) for path in (source, CONTROL)), "fresh external proof root required")
    root.mkdir(parents=True)
    rows = [dict(role=role, status="not_attempted_after_failure") for role in ROLES]
    error, frozen, child = None, None, None
    def guard():
        R.resources(root)
        C.require(cpu() <= C.AGGREGATE_CPU and time.monotonic()-started <= C.AGGREGATE_WALL, "proof aggregate budget crossed")
    try:
        frozen = R.verify_freeze(source, options.freeze, C.P.DEFAULT_POLICY, options.wheel_receipt)
        observed = C.read(Path(options.freeze).with_name("proof-metadata-observation.json"))
        C.require(C.same(observed["runtime"], frozen["runtime"]) and observed["source_bound_schema_class_calls"] == 3,
                  "actual three-schema observation missing before proof World")
        C.write(root / "freeze.json", frozen)
        C.write(root / "proof-metadata-observation.json", observed)
        C.write(root / "admission.json", R.resources(root, admission=True))
        for index, role in enumerate(ROLES):
            guard()
            C.require(cpu()+C.WORKER_CPU <= C.AGGREGATE_CPU, "proof cannot reserve unchanged worker CPU allowance")
            folder = root / role
            folder.mkdir()
            C.write(folder / "launch-resources.json", R.resources(root))
            command = [sys.executable, "-B", str(SCRIPT), "worker", "--source-root", str(source),
                "--freeze", str(Path(options.freeze).resolve()), "--wheel-receipt", str(Path(options.wheel_receipt).resolve()),
                "--output-root", str(root), "--role", role]
            known, worker_started = {}, time.monotonic()
            try:
                with (folder / "worker.log").open("xb") as log:
                    child = subprocess.Popen(command, cwd=CONTROL, stdin=subprocess.DEVNULL, stdout=log,
                        stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
                    lease = R.process_record(child.pid)
                    if lease is not None:
                        C.require(lease["pgrp"] == lease["session"] == child.pid, "proof worker session lease unavailable")
                        known[child.pid] = lease["start_ticks"]
                    C.write(folder / "process-lease.json", dict(leader=lease, leader_pid=child.pid,
                        ownership="qualified exclusive Linux child subreaper established before launch"))
                    accounting = R.supervise(child, known, cpu, lambda: R.resources(root), started, worker_started)
                R.cleanup(child, known)
                C.write(folder / "cleanup.json", dict(complete=True, identities=known, accounting=accounting))
                C.require(accounting["returncode"] == 0, "proof worker failed")
                summary = C.read(folder / "worker-summary.json")
                C.require(summary["execution_complete"] is True and summary["actual_physics_ticks"] ==
                          (END if role == "parent" else END-FORK), "proof worker window incomplete")
                inspect_role(root, source, role, frozen)
                if role != "parent":
                    C.write(root / (role+"-identity.json"), compare(root, source, role, frozen))
                guard()  # Identity failure prevents the next launch, including observed after None.
                rows[index] = dict(role=role, status="complete", returncode=accounting["returncode"],
                    actual_physics_ticks=summary["actual_physics_ticks"], tree_cpu_seconds=accounting["tree_cpu_seconds"])
            except BaseException as exc:
                rows[index] = dict(role=role, status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
                if child is not None:
                    try:
                        R.cleanup(child, known)
                    except BaseException as cleanup_error:
                        rows[index]["cleanup_error"] = str(cleanup_error)
                raise
            finally:
                child = None
                C.write(root / f"progress-{index+1}.json", rows)
        R.verify_freeze(source, options.freeze, C.P.DEFAULT_POLICY, options.wheel_receipt)
        guard()
    except BaseException as exc:
        error = dict(type=type(exc).__name__, message=str(exc))
    complete = error is None and all(row["status"] == "complete" for row in rows)
    payload = dict(schema_version=1, kind="fresh-practice-cp60-proof-execution", execution_complete=complete,
        qualified=False, proof_seed=SEED, expected_executions=3, expected_physics_ticks=66,
        actual_physics_ticks=66 if complete else None, runs=rows, error=error,
        source_sha=C.SOURCE, control_sha=frozen["control"]["git_sha"] if frozen else None,
        freeze_sha256=C.sha(options.freeze), controller_started_monotonic=started,
        boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        aggregate_cpu_seconds=cpu(), aggregate_wall_seconds=time.monotonic()-started, files=C.inventory(root))
    try:
        R.publish_execution(root, payload, cpu, started, guard)
    except BaseException:
        # The shared publisher retains all provisional work under incomplete
        # names and removes positive seals. No physics or publication replay.
        raise
    return 0 if complete else 1


# Exact qualified outer transaction, with only its inner operation name changed.
exclusive_subreaper, interruption_guard = R.exclusive_subreaper, R.interruption_guard


def run(options):
    own0, children0 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    initial_cpu = own0.ru_utime + own0.ru_stime + children0.ru_utime + children0.ru_stime
    root = Path(options.output_root).resolve()
    try:
        with exclusive_subreaper(), interruption_guard():
            code = _proof_run(options)
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


def read(options):
    root, source, output = (Path(value).resolve() for value in
                            (options.evidence_root, options.source_root, options.output_root))
    C.require(not output.exists() and all(not output.is_relative_to(path) for path in (root, source, CONTROL)),
              "fresh external proof readout required")
    output.mkdir(parents=True)
    started, modules = time.monotonic(), set(sys.modules)
    own0, child0 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    base = own0.ru_utime+own0.ru_stime+child0.ru_utime+child0.ru_stime
    previous = signal.getsignal(signal.SIGALRM)
    C.require(signal.getitimer(signal.ITIMER_REAL) == (0., 0.), "proof reader requires unleased wall timer")
    def finalize():
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    try:
        execution = C.read(root / "execution.json")
        C.require(execution["kind"] == "fresh-practice-cp60-proof-execution" and execution["proof_seed"] == SEED and
                  execution["expected_executions"] == 3 and execution["expected_physics_ticks"] == 66,
                  "proof execution registration differs")
        accounting = D.execution_accounting(root, execution)
        C.require(execution["boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                  "proof original monotonic clock not visible")
        def budgets():
            own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
            measured = own.ru_utime+own.ru_stime+children.ru_utime+children.ru_stime-base
            return dict(reader_cpu_seconds=measured, controller_charged_upper_bound_cpu_seconds=accounting["charged_aggregate_cpu_seconds"],
                total_cpu_upper_bound_seconds=accounting["charged_aggregate_cpu_seconds"]+measured,
                controller_to_readout_wall_seconds=time.monotonic()-execution["controller_started_monotonic"],
                scope="conservative controller charge plus measured reader CPU; not a measured total")
        def guard():
            D.combined_evidence_budget(R.resources(root), C.inventory(output))
            observed = budgets()
            if observed["total_cpu_upper_bound_seconds"] > C.AGGREGATE_CPU or not 0 <= observed["controller_to_readout_wall_seconds"] <= C.AGGREGATE_WALL:
                raise D.ReadoutBudgetExceeded("proof original aggregate execution/readout budget crossed")
        def expired(signum, frame):
            raise D.ReadoutBudgetExceeded("proof original aggregate wall deadline crossed")
        remaining = C.AGGREGATE_WALL-budgets()["controller_to_readout_wall_seconds"]
        C.require(0 < remaining <= C.AGGREGATE_WALL, "proof original wall budget exhausted")
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        def operation():
            guard()
            C.require(execution["execution_complete"] is True and execution["actual_physics_ticks"] == 66 and
                      [row["role"] for row in execution["runs"]] == list(ROLES) and
                      all(row["status"] == "complete" for row in execution["runs"]), "proof execution incomplete")
            inventory = C.inventory(root, omit=("execution.json", "execution-receipt.json"))
            C.require(execution["files"] == inventory, "proof execution payload hashes differ")
            frozen = C.read(root / "freeze.json")
            C.selected_policy(frozen)
            C.require(C.sha(root / "freeze.json") == execution["freeze_sha256"] and
                      C.same(frozen["producer"], C.source_snapshot(source, C.SOURCE)) and
                      C.same(frozen["control"], C.source_snapshot(CONTROL, execution["control_sha"])), "proof frozen source/control differs")
            C.require(C.same(frozen["runtime_policy_evidence"], R.policy_evidence(source, C.P.policy(), options.wheel_receipt)),
                      "proof official wheel evidence differs")
            checks = {}
            for role in ROLES[1:]:
                checks[role] = compare(root, source, role, frozen)
                guard()
            C.require(C.inventory(root, omit=("execution.json", "execution-receipt.json")) == inventory,
                      "proof evidence changed during readout")
            C.require(not any(name.startswith("chronicler_agents") for name in set(sys.modules)-modules),
                      "proof reader unexpectedly imported native")
            result = dict(schema_version=1, kind="fresh-practice-cp60-proof-readout", mechanics_verified=True,
                efficacy_qualified=False, default_promotion=False, proof_seed=SEED, physics_executions=3, physics_ticks=66,
                explicit_trusted_checkpoint_decode_calls=6, unstepped_checkpoint_validations=4,
                fresh_world_generation_calls=1, total_world_or_native_object_count_claimed=False,
                source_sha=C.SOURCE, control_sha=execution["control_sha"], native_sha256=C.P.policy()["native_sha256"],
                execution_sha256=C.sha(root / "execution.json"), execution_receipt_sha256=C.sha(root / "execution-receipt.json"),
                freeze_sha256=C.sha(root / "freeze.json"), checks=checks, budgets=budgets(),
                limitations=["Observed parent sources0..59 are not an unobserved fresh-world contrast.",
                    "Exactly two post-CP sources per observed role; no END180 journal or eight-seed study execution.",
                    "Ordinary state/history/payments/RNG and semantic decoded/native projection checked; no raw checkpoint byte identity.",
                    "Any absent payment remains absent; this proof establishes no efficacy or positive paid-growth exposure."])
            D.publish_readout(output, result, guard, started=started, budget_observation=budgets)
            return result
        result = D.complete_transaction(output, operation, finalize, guard, budgets)
    except BaseException as exc:
        D.invalidate_publication(output)
        try:
            finalize()
        except BaseException as final_error:
            exc = final_error
        result = dict(schema_version=1, kind="fresh-practice-cp60-proof-readout", mechanics_verified=False,
            efficacy_qualified=False, proof_seed=SEED, roles=[dict(role=role, status="unavailable_or_unvalidated") for role in ROLES],
            error=dict(type=type(exc).__name__, message=str(exc)))
        C.write(output / "readout.json", result)
        C.write(output / "receipt.json", dict(publication_complete=False, mechanics_verified=False,
            efficacy_qualified=False, files=C.inventory(output)))
    return 0 if result["mechanics_verified"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "run", "worker", "read"))
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--freeze")
    parser.add_argument("--output-root")
    parser.add_argument("--evidence-root")
    parser.add_argument("--wheel-receipt", required=True)
    parser.add_argument("--role", choices=ROLES)
    options = parser.parse_args(argv)
    if options.mode == "read":
        C.require(options.evidence_root is not None and options.output_root is not None and options.role is None,
                  "fixed proof readout paths required")
        return read(options)
    C.require(options.freeze is not None, "prospective metadata freeze path required")
    if options.mode == "freeze":
        C.require(options.role is None, "freeze cannot select a proof subset")
        metadata_freeze(options)
        return 0
    C.require(options.output_root is not None, "external proof output required")
    if options.mode == "worker":
        C.require(options.role is not None, "fixed internal worker role required")
        worker(options)
        return 0
    C.require(options.role is None, "proof controller cannot select a subset")
    return run(options)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
