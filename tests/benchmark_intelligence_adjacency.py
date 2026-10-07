"""Same-input time and peak-memory benchmark for intelligence adjacency.

Run with ``python tests/benchmark_intelligence_adjacency.py``. The baseline
function is loaded exactly from the pre-change Git commit as UTF-8 bytes.
"""

import ast
import gc
from pathlib import Path
import subprocess
import sys
import timeit
import tracemalloc

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "0b54edb8bd966ee111d3ba2c103c138916610e17"
sys.path.insert(0, str(REPO_ROOT / "src"))

from chronicler.intelligence import shares_adjacent_region
from chronicler.models import Civilization, Leader, Region, WorldState


def load_baseline():
    source = subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:src/chronicler/intelligence.py"],
        cwd=REPO_ROOT, check=True, stdout=subprocess.PIPE,
    ).stdout.decode("utf-8")
    function = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "shares_adjacent_region"
    )
    function_source = ast.get_source_segment(source, function)
    namespace = {}
    exec("from __future__ import annotations\n" + function_source, namespace)
    return namespace["shares_adjacent_region"]


def make_world(region_count: int, civ_count: int, *, early_match: bool) -> WorldState:
    civ_names = [f"Civ{i}" for i in range(civ_count)]
    regions_by_civ = {name: [] for name in civ_names}
    regions = []
    for i in range(region_count):
        offsets = (1, 2, 3) if early_match else (2, 3, 1)
        adjacencies = [f"R{(i + offset) % region_count}" for offset in offsets]
        controller = civ_names[i % civ_count]
        region_name = f"R{i}"
        regions.append(Region(
            name=region_name, terrain="plains", carrying_capacity=50,
            resources="fertile", controller=controller, adjacencies=adjacencies,
        ))
        regions_by_civ[controller].append(region_name)

    civs = [Civilization(
        name=name, population=50, military=5, economy=5, culture=5,
        stability=50, treasury=10,
        leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
        regions=regions_by_civ[name],
    ) for name in civ_names]
    civs.append(Civilization(
        name="Distant", population=0, military=0, economy=0, culture=0,
        stability=50, treasury=0,
        leader=Leader(name="Distant Leader", trait="cautious", reign_start=0),
        regions=[],
    ))
    return WorldState(
        name="Intelligence adjacency benchmark", seed=42, turn=0,
        regions=regions, civilizations=civs,
    )


def peak_allocated_bytes(batch) -> int:
    gc.collect()
    tracemalloc.start()
    batch()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def run_case(label: str, world: WorldState, queries, baseline, number: int) -> None:
    def old_batch() -> int:
        return sum(baseline(observer, target, world) for observer, target in queries)

    def new_batch() -> int:
        return sum(shares_adjacent_region(observer, target, world) for observer, target in queries)

    assert [baseline(observer, target, world) for observer, target in queries] == [
        shares_adjacent_region(observer, target, world) for observer, target in queries
    ]
    old_time = min(timeit.repeat(old_batch, repeat=3, number=number)) / number
    new_time = min(timeit.repeat(new_batch, repeat=3, number=number)) / number
    old_peak = peak_allocated_bytes(old_batch)
    new_peak = peak_allocated_bytes(new_batch)
    print(
        f"{label} ({len(queries)} pair queries): "
        f"old {old_time * 1000:.3f} ms, new {new_time * 1000:.3f} ms, "
        f"speedup {old_time / new_time:.2f}x; "
        f"peak traced old {old_peak / 1024:.1f} KiB, "
        f"new {new_peak / 1024:.1f} KiB"
    )


def main() -> None:
    baseline = load_baseline()
    for region_count, civ_count, single_runs, pair_runs in (
        (8, 3, 1000, 100),
        (256, 16, 150, 3),
    ):
        early = make_world(region_count, civ_count, early_match=True)
        later = make_world(region_count, civ_count, early_match=False)
        prefix = f"{region_count} regions / {civ_count} owning civs"
        run_case(
            prefix + ", early match", early,
            [(early.civilizations[0], early.civilizations[1])], baseline, single_runs,
        )
        run_case(
            prefix + ", later match", later,
            [(later.civilizations[0], later.civilizations[1])], baseline, single_runs,
        )
        run_case(
            prefix + ", no match", later,
            [(later.civilizations[0], later.civilizations[-1])], baseline, single_runs,
        )
        owners = later.civilizations[:-1]
        ordered_pairs = [
            (observer, target) for observer in owners for target in owners
            if observer is not target
        ]
        run_case(prefix + ", ordered civ pairs", later, ordered_pairs, baseline, pair_runs)


if __name__ == "__main__":
    main()
