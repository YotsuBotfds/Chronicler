"""Exact output equivalence with native checkpoints and real arm subprocesses."""
from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

from chronicler import main
from chronicler import run_checkpoint as rc

pytestmark = pytest.mark.native


def _native():
    ca = pytest.importorskip("chronicler_agents")
    if not isinstance(ca.AgentSimulator, type) or not hasattr(ca.AgentSimulator, "checkpoint_state"):
        pytest.skip("requires the real checkpoint-enabled native extension")


def _args(folder, turns, **extra):
    args = argparse.Namespace(
        seed=42, turns=turns, civs=2, regions=4, output=str(folder / "chronicle.md"),
        state=str(folder / "state.json"), resume=None, reflection_interval=4,
        simulate_only=True, narrator="local", agents="hybrid", tuning_overrides={}, scenario=None,
        validation_sidecar=True,
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _state_view(world, bridge, memories, history, entries, reflections, pending):
    # Include every persisted physical world field, the entire native state
    # (RNG/registries/queues included), and the loop's carried Python records.
    return {
        "world": world.model_dump(mode="json"),
        "native": bytes(bridge._sim.checkpoint_state()),
        "memories": {name: {"civilization_name": stream.civilization_name,
                            "entries": copy.deepcopy(stream.entries),
                            "reflections": copy.deepcopy(stream.reflections)}
                     for name, stream in memories.items()},
        "history": [snapshot.model_dump(mode="json") for snapshot in history],
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "reflections": dict(reflections), "pending": copy.deepcopy(pending),
    }


def test_lean_and_full_are_identical_at_every_boundary_and_after_finalization(tmp_path, monkeypatch):
    _native()
    for key in ("RAYON_NUM_THREADS", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(key, "1")
    main.execute_run(_args(tmp_path / "parent", 18, checkpoint_turns=(9,),
                           languages=True, historiography=True))
    checkpoint = tmp_path / "parent" / "checkpoint_turn_9.ckpt"
    original_save, original_turn = main._write_exact_checkpoint, main._run_turn_deferring_sigint
    boundaries, turns, final, results = {}, {}, {}, {}
    current = None
    def save(template, world, memories, history, entries, reflections, pending,
             run_start, seed, num_turns, bridge, *rest, **kwargs):
        boundaries[current].append(_state_view(world, bridge, memories, history, entries, reflections, pending))
        return original_save(template, world, memories, history, entries, reflections, pending,
                             run_start, seed, num_turns, bridge, *rest, **kwargs)
    def turn(world, **kwargs):
        turns[current].append((world.turn, kwargs["seed"], kwargs["force_settlement_detection"]))
        return original_turn(world, **kwargs)
    monkeypatch.setattr(main, "_write_exact_checkpoint", save)
    monkeypatch.setattr(main, "_run_turn_deferring_sigint", turn)
    for profile in ("full", "lean"):
        current = profile
        boundaries[profile], turns[profile] = [], []
        loaded = rc.read_checkpoint(checkpoint)
        folder = tmp_path / profile
        args = _args(folder, 18, decision_ablation="needs", ablation_start_turn=9,
                     ablation_output=profile == "lean", checkpoint_every=1,
                     checkpoint=str(folder / "boundary_{turn}.ckpt"))
        results[profile] = main.execute_run(args, checkpoint_resume=loaded)
        state = loaded.state
        final[profile] = _state_view(state.world, state.agent_bridge, state.memories,
                                     state.history, state.chronicle_entries, state.era_reflections,
                                     state.pending_injections)
    assert len(boundaries["full"]) == 9
    assert boundaries["full"] == boundaries["lean"]
    assert final["full"] == final["lean"]
    assert turns["full"] == turns["lean"] == [(t, 42 + t, t == 17) for t in range(9, 18)]
    assert final["full"]["reflections"], "exercise local reflections on both profiles"
    assert len(final["full"]["history"]) == 18, "the inherited history is retained"
    for profile in results:
        results[profile] = dataclasses.asdict(results[profile])
        results[profile].pop("output_dir")
    assert results["full"] == results["lean"]
    full, lean = tmp_path / "full", tmp_path / "lean"
    # This check is before the parent's compression and cleanup.
    assert (full / "agent_events.arrow").read_bytes() == (lean / "agent_events.arrow").read_bytes()
    from chronicler.bundle_codec import load_bundle
    from chronicler.ablation_arms import _compress_events, fork_info
    from chronicler.artifact_io import atomic_write_json
    metadata = load_bundle(full / "chronicle_bundle.json")["metadata"]
    atomic_write_json(full / "fork.json", fork_info(metadata))
    assert (full / "fork.json").read_bytes() == (lean / "fork.json").read_bytes()
    for folder in (full, lean):
        _compress_events(folder / "agent_events.arrow")
    assert (full / "agent_events.arrow").read_bytes() == (lean / "agent_events.arrow").read_bytes()
    assert not (lean / "chronicle_bundle.json").exists()
    assert not (lean / "chronicle.md").exists()
    # Periodic output writes remain: this is deliberately only post-run pruning.
    assert list(lean.glob("memories_*.json"))
    assert (lean / "state.json").exists()


def test_real_ablation_workers_and_downstream_oracles_match(tmp_path, monkeypatch):
    _native()
    for key in ("RAYON_NUM_THREADS", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(key, "1")
    from chronicler.ablation_arms import run_ablation_arms
    from chronicler.validation_ablation import (
        load_ablation_arms, needs_ablation_component, cohort_ablation_result,
    )
    from chronicler.validation_io import load_seed_runs

    batch = tmp_path / "batch"
    main.execute_run(_args(batch / "seed_42", 122, checkpoint_turns=(101,)))
    (batch / "batch_manifest.json").write_text(json.dumps({
        "status": "complete", "turns": 122, "runs": [{"seed": 42, "dir": "seed_42"}],
    }))
    source = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(source / "src"), RAYON_NUM_THREADS="1",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    loaded, manifests = {}, {}
    for profile in ("full", "lean"):
        output = tmp_path / profile
        manifests[profile] = run_ablation_arms(
            batch, output, arms=("needs", "kin_roots"), total_turns=122, parallel=1,
            python=sys.executable, env=env, cwd=source, delete_checkpoints=False,
            lean_output=profile == "lean", log=lambda *_: None,
        )
        loaded[profile] = load_ablation_arms(output, batch)
    assert loaded["full"]["arms"] == loaded["lean"]["arms"]
    assert loaded["lean"]["summary"]["forks"] == 2
    runs = load_seed_runs(batch)
    assert runs[0]["needs_columns"], "exercise actual exported fork cohorts"
    reports = {}
    for profile, data in loaded.items():
        reports[profile] = {
            "needs": needs_ablation_component(runs, data["arms"]["needs"]),
            "cohort": cohort_ablation_result(runs, data["arms"]["kin_roots"]),
        }
    assert reports["full"] == reports["lean"]
    # One seed is an equivalence fixture, never a causal qualification cohort.
    assert reports["lean"]["needs"]["seeds"] == 1
    for full, lean in zip(manifests["full"]["forks"], manifests["lean"]["forks"]):
        assert full["files"] == lean["files"]
        assert full["total_turns"] == lean["total_turns"] == 122
        for filename in full["files"]:
            assert (tmp_path / "full" / full["dir"] / filename).read_bytes() == (tmp_path / "lean" / lean["dir"] / filename).read_bytes()
