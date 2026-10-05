"""Exact public-baseline regression oracles for the snapshot optimization.

Golden data was captured from edf7299, not from the candidate implementation.
Every turn's complete snapshot/events/narrative and ordered RNG primitives are
checked; no approximate float comparisons or relaxed precision are used.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from chronicler.intelligence import _get_perceived_stat_with_accuracy, get_perceived_stat
from scripts.benchmark_headless import FixedDateTime, rng_trace, run


FIXTURES = Path(__file__).parent / "fixtures" / "performance"
BASELINE = json.loads((FIXTURES / "public_edf7299.json").read_text())
PERCEPTIONS = json.loads((FIXTURES / "perception_edf7299.json").read_text())


@pytest.mark.parametrize("name", BASELINE["workloads"])
def test_public_baseline_all_turns_and_rng(name, tmp_path, monkeypatch):
    # Fix the lane even in environments where the optional Rust extension exists.
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    expected = BASELINE["workloads"][name]
    turns = []

    def capture(snapshot, text, events, named):
        data = [snapshot.model_dump(mode="json"), text,
                [event.model_dump(mode="json") for event in events],
                [event.model_dump(mode="json") for event in named]]
        turns.append(hashlib.sha256(json.dumps(data, ensure_ascii=False,
                                              separators=(",", ":")).encode()).hexdigest())

    with rng_trace(tmp_path / "rng.jsonl") as trace:
        run(expected["spec"], tmp_path / "artifacts", on_turn=capture)
    assert turns == expected["turn_sha256"]
    assert trace == expected["rng"]


@pytest.mark.parametrize("case", PERCEPTIONS["cases"])
def test_perception_public_baseline_boundaries(case, monkeypatch):
    observer = SimpleNamespace(name="Observer")
    target = SimpleNamespace(name="Target", military=case["actual"])
    world = SimpleNamespace(seed=42, turn=7)
    monkeypatch.setattr("chronicler.intelligence.compute_accuracy",
                        lambda *args: case["accuracy"])
    # Cover no contact, exact knowledge, integer noise truncation, clipping,
    # negative/high actual values, and caller-specific max_value from old code.
    assert get_perceived_stat(observer, target, "military", world, case["max_value"]) == case["expected"]
    assert _get_perceived_stat_with_accuracy(
        observer, target, "military", world, case["max_value"],
        accuracy=case["accuracy"],
    ) == case["expected"]


def test_ordinary_perception_reads_recompute_after_world_change(monkeypatch):
    observer = SimpleNamespace(name="Observer")
    target = SimpleNamespace(name="Target", military=65)
    world = SimpleNamespace(seed=42, turn=7, accuracy=0.0)
    monkeypatch.setattr("chronicler.intelligence.compute_accuracy", lambda *args: world.accuracy)
    assert get_perceived_stat(observer, target, "military", world) is None
    world.accuracy = 1.0
    assert get_perceived_stat(observer, target, "military", world) == 65


def test_duplicate_names_preserve_discarded_rng_draws(tmp_path, monkeypatch):
    import argparse
    from chronicler.main import execute_run
    from chronicler.models import FactionState, FactionType
    from chronicler.world_gen import generate_world

    expected = json.loads((FIXTURES / "duplicates_edf7299.json").read_text())
    world = generate_world(seed=42, num_civs=3, num_regions=6)
    first, second, target = world.civilizations
    first.name = second.name = "Twin"
    first.factions = FactionState(influence={FactionType.MILITARY: 1.0,
                                           FactionType.MERCHANT: 0.0, FactionType.CULTURAL: 0.0})
    second.factions = FactionState(influence={FactionType.MILITARY: 0.0,
                                            FactionType.MERCHANT: 0.0, FactionType.CULTURAL: 1.0})
    # First observer has exact knowledge; second has noisy knowledge. Reusing the
    # last name-keyed entry for the first would create otherwise absent RNG draws,
    # even though its duplicate output row is later overwritten.
    first.leader.grudges = [{"rival_civ": target.name, "intensity": 0.8} for _ in range(10)]
    world.invalidate_civ_map()

    def tick(world, *args, **kwargs):
        world.turn += 1
        return ""

    monkeypatch.setattr("chronicler.main.run_turn", tick)
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.bundle.datetime", FixedDateTime)
    turns = []

    def capture(snapshot, text, events, named):
        data = [snapshot.model_dump(mode="json"), text,
                [event.model_dump(mode="json") for event in events],
                [event.model_dump(mode="json") for event in named]]
        turns.append(hashlib.sha256(json.dumps(data, ensure_ascii=False,
                                              separators=(",", ":")).encode()).hexdigest())

    args = argparse.Namespace(seed=42, turns=2, civs=3, regions=6,
                              output=str(tmp_path / "chronicle.md"), state=str(tmp_path / "state.json"),
                              resume=None, reflection_interval=10, llm_actions=False, scenario=None,
                              simulate_only=True, agents="off")
    with rng_trace(tmp_path / "rng.jsonl") as trace:
        execute_run(args, world=world, on_turn=capture)
    assert turns == expected["turn_sha256"]
    assert trace == expected["rng"]


def test_benchmark_comparison_rejects_rng_artifact_and_environment_changes():
    from copy import deepcopy
    from scripts.benchmark_headless import compare

    original = {"environment": {"python": "fixed"}, "workloads": {
        "small": {"workload": {"seed": 42}, "equivalence": {
            "artifacts": {"bundle": "hash"}, "rng": "hash", "turns": ["hash"]},
            "median_seconds": 1.0, "peak_tracemalloc_bytes": 100}}}
    assert compare(original, original)["passed"]
    for change in ("environment", "artifacts", "rng", "turns", "workload"):
        changed = deepcopy(original)
        if change == "environment":
            changed["environment"]["python"] = "different"
        elif change == "workload":
            changed["workloads"]["small"]["workload"]["seed"] = 43
        else:
            changed["workloads"]["small"]["equivalence"][change] = "different"
        assert not compare(original, changed)["passed"]
