"""Bounded, same-input full Phase 2 comparison against checkpoint 003.

Run with ``python tests/benchmark_war_projection.py``. Each timed call receives
a fresh world and accumulator prepared before the clock starts. The baseline
function is loaded verbatim from the accepted Git checkpoint.
"""

import ast
from copy import deepcopy
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "347ab1f4a94b3cbf7291512bd835a4a668da5bd9"
sys.path.insert(0, str(REPO_ROOT / "src"))

from chronicler import simulation
from chronicler.accumulator import StatAccumulator
from chronicler.models import Civilization, Leader, Region, WorldState


def load_baseline():
    source = subprocess.run(
        [
            "git", "-c", f"safe.directory={REPO_ROOT.as_posix()}",
            "show", f"{BASE_COMMIT}:src/chronicler/simulation.py",
        ],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8")
    function = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "apply_automatic_effects"
    )
    function_source = ast.get_source_segment(source, function)
    namespace = dict(vars(simulation))
    exec("from __future__ import annotations\n" + function_source, namespace)
    return namespace["apply_automatic_effects"]


def make_world(civ_count: int, at_war: bool) -> WorldState:
    regions = []
    civs = []
    for index in range(civ_count):
        name = f"Civ{index}"
        region_name = f"Region{index}"
        regions.append(Region(
            name=region_name,
            terrain="plains",
            carrying_capacity=60,
            resources="fertile",
            controller=name,
        ))
        civs.append(Civilization(
            name=name,
            population=50,
            military=5,
            economy=10,
            culture=10,
            stability=50,
            treasury=4 if index < 4 else 40,
            leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
            regions=[region_name],
        ))
    return WorldState(
        name="War projection benchmark",
        seed=42,
        regions=regions,
        civilizations=civs,
        active_wars=[("Civ0", "Civ1"), ("Civ2", "Civ3")] if at_war else [],
    )


def make_accumulator(world: WorldState) -> StatAccumulator:
    acc = StatAccumulator()
    for civ_index, civ in enumerate(world.civilizations):
        for _ in range(3):
            acc.add(civ_index, civ, "treasury", -1, "keep")
            acc.add(civ_index, civ, "stability", -1, "signal")
            acc.add(civ_index, civ, "treasury", 1, "keep")
    return acc


def make_case(template: WorldState, with_acc: bool):
    world = deepcopy(template)
    acc = make_accumulator(world) if with_acc else None
    return world, acc


def assert_same_input(old_case, new_case) -> None:
    old_world, old_acc = old_case
    new_world, new_acc = new_case
    assert old_world.model_dump(mode="python") == new_world.model_dump(mode="python")
    if old_acc is None:
        assert new_acc is None
    else:
        assert old_acc._changes == new_acc._changes


def assert_exact_parity(baseline, template: WorldState, with_acc: bool) -> None:
    old_case = make_case(template, with_acc)
    new_case = make_case(template, with_acc)
    assert_same_input(old_case, new_case)
    old_world, old_acc = old_case
    new_world, new_acc = new_case

    initial_rng = random.getstate()
    try:
        random.seed(1745)
        old_events = baseline(old_world, acc=old_acc, cross_routes=[])
        old_rng = random.getstate()
        random.seed(1745)
        new_events = simulation.apply_automatic_effects(
            new_world, acc=new_acc, cross_routes=[]
        )
        new_rng = random.getstate()
    finally:
        random.setstate(initial_rng)

    assert [event.model_dump(mode="python") for event in old_events] == [
        event.model_dump(mode="python") for event in new_events
    ]
    assert old_world.model_dump(mode="python") == new_world.model_dump(mode="python")
    assert old_world._artifact_intents == new_world._artifact_intents
    assert old_world._artifact_lifecycle_intents == new_world._artifact_lifecycle_intents
    assert old_rng == new_rng
    if with_acc:
        assert old_acc._changes == new_acc._changes


def time_batch(function, cases) -> float:
    start = perf_counter()
    for world, acc in cases:
        function(world, acc=acc, cross_routes=[])
    return (perf_counter() - start) / len(cases)


def run_case(baseline, civ_count: int, at_war: bool, with_acc: bool) -> None:
    template = make_world(civ_count, at_war)
    assert_exact_parity(baseline, template, with_acc)
    samples = 6 if civ_count == 8 else 3
    old_times = []
    new_times = []
    for _ in range(3):
        old_cases = [make_case(template, with_acc) for _ in range(samples)]
        new_cases = [make_case(template, with_acc) for _ in range(samples)]
        for old_case, new_case in zip(old_cases, new_cases):
            assert_same_input(old_case, new_case)
        random.seed(1745)
        old_times.append(time_batch(baseline, old_cases))
        random.seed(1745)
        new_times.append(time_batch(simulation.apply_automatic_effects, new_cases))

    old_time = min(old_times)
    new_time = min(new_times)
    label = f"{civ_count} civs, {'war' if at_war else 'peace'}, {'acc' if with_acc else 'direct'}"
    print(
        f"{label}: baseline {old_time * 1000:.3f} ms, "
        f"candidate {new_time * 1000:.3f} ms, "
        f"speedup {old_time / new_time:.2f}x"
    )


def main() -> None:
    baseline = load_baseline()
    for civ_count in (8, 32):
        for at_war in (False, True):
            for with_acc in (False, True):
                run_case(baseline, civ_count, at_war, with_acc)


if __name__ == "__main__":
    main()
