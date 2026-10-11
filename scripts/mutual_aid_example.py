"""Small paired fixture; no narrator, agent behavior tick, or external services.

Run: .venv/bin/python scripts/mutual_aid_example.py --backend python
Use --backend native after building chronicler-agents for the real Rust economy.
"""
from __future__ import annotations

import argparse
import json
import math

import pyarrow as pa

from chronicler.economy import (
    FOOD_GOODS, build_economy_region_input_batch, build_economy_trade_route_batch,
    compute_economy, reconstruct_economy_result,
)
from chronicler.models import Civilization, Leader, Region, WorldState
from chronicler.mutual_aid import dispatch_mutual_aid, observe_mutual_aid, read_stockpile_commitments


def fixture_world(enabled: bool, treasury: int = 10, donor_yield: float = .5) -> WorldState:
    regions = [
        Region(name="Granary", terrain="plains", carrying_capacity=60, population=20,
               resources="fertile", controller="Cooperative", adjacencies=["Mine"],
               resource_types=[0, 255, 255], resource_effective_yields=[donor_yield, 0, 0]),
        Region(name="Mine", terrain="hills", carrying_capacity=60, population=20,
               resources="mineral", controller="Cooperative", adjacencies=["Granary"],
               resource_types=[5, 255, 255], resource_effective_yields=[.5, 0, 0]),
    ]
    regions[0].stockpile.goods = {"grain": 100.0}
    civ = Civilization(name="Cooperative", population=40, military=10, economy=40,
                       culture=30, stability=80, treasury=treasury,
                       leader=Leader(name="Steward", trait="cautious", reign_start=0),
                       regions=[r.name for r in regions])
    return WorldState(name="Adjacent Aid Fixture", seed=42, regions=regions,
                      civilizations=[civ], relationships={}, agent_mode="hybrid",
                      mutual_aid_enabled=enabled)


def run_fixture(enabled: bool, backend: str = "python", turns: int = 5,
                treasury: int = 10, donor_yield: float = .5) -> dict:
    world = fixture_world(enabled, treasury, donor_yield)
    if backend == "native":
        from chronicler_agents import AgentSimulator
        from chronicler.agent_bridge import build_region_batch, configure_economy_runtime
        sim = AgentSimulator(num_regions=2, seed=42)
        configure_economy_runtime(sim, world)
        sim.set_hybrid_economy_mode(True)
        sim.set_region_state(build_region_batch(world))
        snap = sim.get_snapshot()
    else:
        world.agent_mode = "demographics-only"  # pure policy/oracle surface, no cargo ledger
        snap = pa.record_batch({
            "region": pa.array([0] * 20 + [1] * 20, type=pa.uint16()),
            "occupation": pa.array([0] * 40, type=pa.uint8()),
            "wealth": pa.array([0.0] * 40, type=pa.float32()),
            "civ_affinity": pa.array([0] * 40, type=pa.uint8()),
        })
    history = []
    for turn in range(turns):
        world.turn = turn
        before = math.fsum(v for r in world.regions for v in r.stockpile.goods.values())
        commitments = read_stockpile_commitments(world, sim) if backend == "native" and enabled else None
        dispatch_mutual_aid(world, snap, commitments=commitments)
        if backend == "native":
            result = reconstruct_economy_result(
                *sim.tick_economy(build_economy_region_input_batch(world),
                                  build_economy_trade_route_batch(world, []), 0, False, 1.0),
                world, require_oracle_shadow=True)
        else:
            result = compute_economy(world, snap, world.region_map, True, active_trade_routes=[])
        observe_mutual_aid(world, result, snap)
        transfers = world.mutual_aid_last_transfers
        c = result.conservation
        aid_loss = math.fsum(t.transit_loss for t in transfers)
        after = math.fsum(v for r in world.regions for v in r.stockpile.goods.values())
        residual = before + c["production"] + c["clamp_floor_loss"] - (after + aid_loss + c["consumption"]
            + c["transit_loss"] + c["storage_loss"] + c["cap_overflow"]
            + (c["in_transit_delta"] or 0.0))
        assert abs(residual) < 2e-5, f"Goods conservation failed: {residual}"
        history.append({
            "turn": turn, "sufficiency": result.food_sufficiency,
            "stress_streak": {n: s.stress_streak for n, s in world.mutual_aid_state.items()},
            "treasury": world.civilizations[0].treasury,
            "food_stocks": {r.name: math.fsum(r.stockpile.goods.get(g, 0) for g in FOOD_GOODS)
                            for r in world.regions},
            "transfers": [t.model_dump() for t in transfers],
            "conservation_residual": residual,
            "economy_conservation": c,
        })
    return {"backend": backend, "enabled": enabled, "seed": 42,
            "scope": "economy only; fixed population, no behavior/demography/narration",
            "history": history}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "native"], default="python")
    parser.add_argument("--treasury", type=int, default=10)
    parser.add_argument("--donor-yield", type=float, default=.5)
    args = parser.parse_args()
    print(json.dumps({"control": run_fixture(False, args.backend, treasury=args.treasury, donor_yield=args.donor_yield),
                      "treatment": run_fixture(True, args.backend, treasury=args.treasury, donor_yield=args.donor_yield)}, indent=2))
