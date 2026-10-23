"""Bounded same-input time and peak-memory comparison for population sync.

Run with ``python tests/benchmark_sync_all_populations.py``. The baseline
function is the former sync_all_populations body.
"""

from copy import deepcopy
import gc
from pathlib import Path
import sys
import timeit
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler.models import Civilization, Leader, Region, TechEra, WorldState
from chronicler.utils import sync_all_populations, sync_civ_population


def baseline_sync_all_populations(world: WorldState) -> None:
    for civ in world.civilizations:
        sync_civ_population(civ, world)


def make_world(region_count: int, civ_count: int) -> WorldState:
    civ_names = [f"Civ{i}" for i in range(civ_count)]
    regions_by_civ = {name: [] for name in civ_names}
    regions = []
    for i in range(region_count):
        controller = None if i % 11 == 0 else civ_names[i % civ_count]
        name = f"Region{i}"
        regions.append(Region(
            name=name, terrain="plains", carrying_capacity=100,
            resources="fertile", controller=controller, population=i % 47 + 1,
        ))
        if controller is not None:
            regions_by_civ[controller].append(name)

    civs = [Civilization(
        name=name, population=0, military=5, economy=5, culture=5,
        stability=50, tech_era=TechEra.IRON, treasury=10,
        leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
        regions=regions_by_civ[name], values=["Honor"], asabiya=0.5,
    ) for name in civ_names]
    return WorldState(
        name="Population sync benchmark", seed=42, turn=0,
        regions=regions, civilizations=civs, relationships={},
    )


def peak_allocated_bytes(func, world: WorldState) -> int:
    gc.collect()
    tracemalloc.start()
    func(world)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def run_case(region_count: int, civ_count: int, number: int) -> None:
    baseline_world = make_world(region_count, civ_count)
    current_world = deepcopy(baseline_world)
    baseline_sync_all_populations(baseline_world)
    sync_all_populations(current_world)
    assert [c.population for c in baseline_world.civilizations] == [
        c.population for c in current_world.civilizations
    ]

    baseline_time = min(timeit.repeat(
        lambda: baseline_sync_all_populations(baseline_world), repeat=3, number=number,
    )) / number
    current_time = min(timeit.repeat(
        lambda: sync_all_populations(current_world), repeat=3, number=number,
    )) / number
    baseline_peak = peak_allocated_bytes(baseline_sync_all_populations, baseline_world)
    current_peak = peak_allocated_bytes(sync_all_populations, current_world)

    print(
        f"{region_count} regions / {civ_count} civs: "
        f"old {baseline_time * 1000:.3f} ms, "
        f"new {current_time * 1000:.3f} ms, "
        f"speedup {baseline_time / current_time:.2f}x; "
        f"peak traced old {baseline_peak / 1024:.1f} KiB, "
        f"new {current_peak / 1024:.1f} KiB"
    )


if __name__ == "__main__":
    run_case(8, 3, 1000)
    run_case(256, 24, 100)
