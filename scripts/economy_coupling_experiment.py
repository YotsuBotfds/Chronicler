"""Controlled ecology -> goods -> famine regression experiments (no LLM calls).

Run from the repository root::

    .venv/bin/python scripts/economy_coupling_experiment.py --backend python
    .venv/bin/python scripts/economy_coupling_experiment.py --backend rust --output /tmp/coupling.json

These are phase-level interventions, not full-world simulations. The Rust option
uses a real AgentSimulator pool and tick_economy with ABSTRACT trade, and compares
it to Python using that exact snapshot. It does not claim to test hybrid merchant
travel/delivery. Famine events come from the real current-turn famine post-pass.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow as pa

from chronicler.ecology import _check_famine_yield, refresh_resource_yields
from chronicler.economy import (
    CATEGORIES, FIXED_GOODS, build_economy_region_input_batch,
    build_economy_trade_route_batch, compute_allocated_production, compute_economy,
    reconstruct_economy_result,
)
from chronicler.models import (
    Civilization, ClimatePhase, Leader, Region, RegionEcology, RegionStockpile,
    WorldState,
)
from chronicler.resources import get_season_id


TARGET = "Valley"
DONOR = "Coast"


def make_world(*, reserve: float = 0.0, seed: int = 42) -> WorldState:
    """Two controlled regions; the valley's sole intervention is food reserve."""
    target = Region(
        name=TARGET, terrain="plains", carrying_capacity=100, population=20,
        resources="fertile", controller="Valley Folk", adjacencies=[DONOR],
        resource_types=[0, 255, 255], resource_base_yields=[1.8, 0.0, 0.0],
        resource_effective_yields=[1.8, 0.0, 0.0],
        ecology=RegionEcology(soil=0.8, water=0.8, forest_cover=0.2),
        stockpile=RegionStockpile(goods={"grain": reserve}),
    )
    donor = Region(
        name=DONOR, terrain="coast", carrying_capacity=300, population=120,
        resources="maritime", controller="Coast Folk", adjacencies=[TARGET],
        resource_types=[3, 255, 255], resource_base_yields=[4.0, 0.0, 0.0],
        resource_effective_yields=[4.0, 0.0, 0.0],
        ecology=RegionEcology(soil=0.8, water=0.8, forest_cover=0.2),
    )
    civs = [
        Civilization(
            name=r.controller, population=r.population, regions=[r.name],
            leader=Leader(name=f"Leader {i}", trait="cautious", reign_start=0),
        )
        for i, r in enumerate((target, donor))
    ]
    return WorldState(
        name="Controlled economy coupling", seed=seed, turn=0,
        regions=[target, donor], civilizations=civs, agent_mode="shadow",
    )


def controlled_snapshot() -> pa.RecordBatch:
    """Fixed Python-only agents: 60% farmers; donor has ample merchant capacity."""
    rows = [(0, 0, 0)] * 12 + [(0, 1, 0)] * 4 + [(0, 3, 0)] * 4
    rows += [(1, 0, 1)] * 72 + [(1, 2, 1)] * 24 + [(1, 1, 1)] * 24
    return pa.record_batch({
        "region": pa.array([r for r, _, _ in rows], type=pa.uint16()),
        "occupation": pa.array([o for _, o, _ in rows], type=pa.uint8()),
        "wealth": pa.array([0.0] * len(rows), type=pa.float32()),
        "civ_affinity": pa.array([c for _, _, c in rows], type=pa.uint8()),
    })


def new_native_simulator(world):
    """Fail clearly for an absent/stale extension; never silently use Python."""
    import chronicler_agents
    from chronicler.agent_bridge import build_region_batch, configure_economy_runtime

    cls = getattr(chronicler_agents, "AgentSimulator", None)
    if not isinstance(cls, type):
        raise RuntimeError("A real, freshly built chronicler_agents extension is required")
    sim = cls(num_regions=len(world.regions), seed=world.seed)
    configure_economy_runtime(sim, world)
    sim.set_hybrid_economy_mode(False)
    sim.set_region_state(build_region_batch(world))
    return sim


def stock_total(world):
    return sum(r.stockpile.goods.get(g, 0.0) for r in world.regions for g in FIXED_GOODS)


def conservation_error(initial_stock, world, result):
    c = result.conservation
    sinks = sum(c[k] or 0.0 for k in (
        "consumption", "transit_loss", "storage_loss", "cap_overflow", "in_transit_delta",
    ))
    # A floor clamp creates inventory relative to the unconstrained ledger.
    return initial_stock + c["production"] + c["clamp_floor_loss"] - stock_total(world) - sinks


def harvest_by_region(world, snapshot):
    rows = snapshot.to_pylist()
    return {
        r.name: compute_allocated_production(
            r.resource_types, r.resource_current_yields,
            sum(a["region"] == i and a["occupation"] == 0 for a in rows),
        ) for i, r in enumerate(world.regions)
    }


def run_phase(world, phase, route_open, *, backend="python", sim=None, snapshot=None):
    """Run a single harvest/economy/famine intervention and return measurements."""
    refresh_resource_yields(world, phase)
    if snapshot is None:
        snapshot = pa.record_batch(sim.get_snapshot()) if sim is not None else controlled_snapshot()
    routes = [("Valley Folk", "Coast Folk")] if route_open else []
    before = {r.name: dict(r.stockpile.goods) for r in world.regions}
    initial_stock = stock_total(world)
    expected_harvest = harvest_by_region(world, snapshot)
    oracle_world = world.model_copy(deep=True) if backend == "rust" else None
    if backend == "rust":
        season = get_season_id(world.turn)
        batches = sim.tick_economy(
            build_economy_region_input_batch(world),
            build_economy_trade_route_batch(world, active_trade_routes=routes),
            season, season == 3, 1.0,
        )
        result = reconstruct_economy_result(*(pa.record_batch(b) for b in batches), world)
    else:
        result = compute_economy(
            world, snapshot, {r.name: r for r in world.regions},
            agent_mode=True, active_trade_routes=routes,
        )
    error = conservation_error(initial_stock, world, result)
    expected_total = sum(sum(g.values()) for g in expected_harvest.values())
    assert math.isclose(result.conservation["production"], expected_total, abs_tol=0.002)
    assert abs(error) < 0.002, (backend, error, result.conservation)
    assert result.conservation["clamp_floor_loss"] < 0.00001
    assert all(math.isfinite(x) and x >= -0.00001 for r in world.regions for x in r.stockpile.goods.values())

    # Inspect actual post-pass decisions on a copy, keeping demographic changes
    # out of the fixed-agent stock stress experiment below.
    famine_world = world.model_copy(deep=True)
    events = _check_famine_yield(
        famine_world, {r.name: r.resource_current_yields for r in world.regions},
        phase, 0.12, 0.15, economy_result=result,
    )
    record = {
        "turn": world.turn, "climate": phase.value, "route_open": route_open,
        "regions": {
            r.name: {
                "population": sum(a["region"] == i for a in snapshot.to_pylist()),
                "farmer_count": sum(a["region"] == i and a["occupation"] == 0 for a in snapshot.to_pylist()),
                "merchant_count": sum(a["region"] == i and a["occupation"] == 2 for a in snapshot.to_pylist()),
                "harvest_yields": list(r.resource_current_yields),
                "expected_harvest_by_good": expected_harvest[r.name],
                "stocks_before": before[r.name], "stocks_after": dict(r.stockpile.goods),
                "delivered_imports": result.imports_by_region[r.name],
                "food_sufficiency": result.food_sufficiency[r.name],
                "farmer_income_modifier": result.farmer_income_modifiers[r.name],
                "food_price": result.region_goods[r.name].prices["food"] if backend == "python" else None,
                "famine_event": any(r.controller in e.actors for e in events),
            } for i, r in enumerate(world.regions)
        },
        "conservation": result.conservation, "conservation_error": error,
    }
    if oracle_world is not None:
        oracle = compute_economy(
            oracle_world, snapshot, {r.name: r for r in oracle_world.regions},
            agent_mode=True, active_trade_routes=routes,
        )
        signal_error = max(abs(result.food_sufficiency[n] - oracle.food_sufficiency[n]) for n in result.food_sufficiency)
        stock_error = max(abs(r.stockpile.goods.get(g, 0.0) - oracle_world.regions[i].stockpile.goods.get(g, 0.0))
                          for i, r in enumerate(world.regions) for g in FIXED_GOODS)
        import_error = max(abs(result.imports_by_region[n][c] - oracle.imports_by_region[n][c])
                           for n in result.imports_by_region for c in CATEGORIES)
        record["python_parity"] = {
            "max_food_sufficiency_error": signal_error, "max_stockpile_error": stock_error,
            "max_import_error": import_error,
        }
        assert max(signal_error, stock_error, import_error) < 0.002, record["python_parity"]
    return record


def run_experiment(backend="python", seed=42):
    cases = {}
    for label, phase, reserve, route_open in (
        ("temperate_no_reserve", ClimatePhase.TEMPERATE, 0.0, False),
        ("drought_no_reserve", ClimatePhase.DROUGHT, 0.0, False),
        ("drought_with_reserve", ClimatePhase.DROUGHT, 20.0, False),
        ("drought_route_open", ClimatePhase.DROUGHT, 0.0, True),
    ):
        world = make_world(reserve=reserve, seed=seed)
        sim = new_native_simulator(world) if backend == "rust" else None
        cases[label] = run_phase(world, phase, route_open, backend=backend, sim=sim)
    wet, dry, reserve, trade = (cases[n]["regions"][TARGET] for n in cases)
    assert dry["expected_harvest_by_good"]["grain"] < wet["expected_harvest_by_good"]["grain"]
    assert wet["food_sufficiency"] >= 1.0 > dry["food_sufficiency"]
    assert dry["famine_event"] and not wet["famine_event"]
    assert reserve["food_sufficiency"] >= 1.0 and not reserve["famine_event"]
    assert trade["delivered_imports"]["food"] > 0.0
    assert trade["food_sufficiency"] >= 1.0 and not trade["famine_event"]
    assert dry["delivered_imports"]["food"] == 0.0

    # Near crop failure also exercises the old yield-only famine threshold:
    # stocked/imported meals must protect people even when harvest < 0.12.
    crop_failure = {}
    for label, initial_reserve, route_open in (
        ("no_reserve", 0.0, False), ("with_reserve", 20.0, False), ("route_open", 0.0, True),
    ):
        world = make_world(reserve=initial_reserve, seed=seed)
        world.regions[0].ecology.soil = 0.1
        world.regions[0].ecology.water = 0.1
        sim = new_native_simulator(world) if backend == "rust" else None
        crop_failure[label] = run_phase(world, ClimatePhase.DROUGHT, route_open, backend=backend, sim=sim)
    assert crop_failure["no_reserve"]["regions"][TARGET]["famine_event"]
    for label in ("with_reserve", "route_open"):
        region = crop_failure[label]["regions"][TARGET]
        assert region["harvest_yields"][0] < 0.12
        assert region["food_sufficiency"] >= 1.0 and not region["famine_event"]

    # Six same-season drought harvests isolate inventory exhaustion. Holding
    # turn, ecology and agent distribution constant is intentional, not a world tick.
    depletion = {}
    for label, initial_reserve in (("no_reserve", 0.0), ("with_reserve", 20.0)):
        world = make_world(reserve=initial_reserve, seed=seed)
        sim = new_native_simulator(world) if backend == "rust" else None
        depletion[label] = [
            run_phase(world, ClimatePhase.DROUGHT, False, backend=backend, sim=sim)
            for _ in range(6)
        ]
    assert not depletion["with_reserve"][0]["regions"][TARGET]["famine_event"]
    assert depletion["with_reserve"][-1]["regions"][TARGET]["famine_event"]
    return {
        "backend": "native-rust-abstract-trade" if backend == "rust" else "python-oracle-controlled-snapshot",
        "seed": seed,
        "scope": "Phase-level controlled interventions; famine evaluated on a copy. No full-world or hybrid merchant-delivery claim.",
        "harvest_metric": "Per-good expected output computed from live/fixed farmer counts and published yields; asserted against kernel total production.",
        "price_metric": "Native FFI does not expose category prices; native food_price is null, never inferred as observed.",
        "paired_cases": cases,
        "severe_crop_failure": crop_failure,
        "fixed_agent_six_harvest_drought": depletion,
        "checks_passed": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "rust"), default="python")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_experiment(args.backend, args.seed)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
