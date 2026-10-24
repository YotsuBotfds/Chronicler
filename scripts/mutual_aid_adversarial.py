"""15-turn native economy/behavior fixture with real merchant commitments.

No native state injection, narrator, ecology tick, macro fiscal income, or native
checkpoint restore. Two units of initial treasury are a finite relief budget;
economy tax outputs are reported but not credited in this isolated fixture.
The crop schedule is an explicit scenario input, not a feature modifier.
Run: .venv/bin/python scripts/mutual_aid_adversarial.py --enabled --treasury 2
Select untouched source/native controls with PYTHONPATH and --disabled.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math

import pyarrow as pa

import chronicler
import chronicler_agents
from chronicler.accumulator import StatAccumulator
from chronicler.agent_bridge import AgentBridge
from chronicler.economy import (
    FOOD_GOODS, build_economy_region_input_batch, build_economy_trade_route_batch,
    reconstruct_economy_result,
)
from chronicler.models import Civilization, Leader, Region, WorldState


def _world(enabled: bool, treasury: int) -> WorldState:
    regions = [
        Region(name="Granary", terrain="plains", carrying_capacity=60, population=20,
               resources="fertile", controller="Cooperative", adjacencies=["Mine"],
               resource_types=[0, 255, 255], resource_effective_yields=[.5, 0, 0],
               resource_current_yields=[.5, 0, 0]),
        # Integrated goods trade (inventory prices, physical cold start) lets
        # merchant cargo partly relieve a 20-person Mine before aid is needed;
        # 30 people keep the stress -> blocked -> reserve-bound aid sequence.
        Region(name="Mine", terrain="hills", carrying_capacity=60, population=30,
               resources="mineral", controller="Cooperative", adjacencies=["Granary"],
               resource_types=[5, 255, 255], resource_effective_yields=[.5, 0, 0],
               resource_current_yields=[.5, 0, 0]),
    ]
    for region in regions:
        _set_yield(region, region.resource_current_yields[0])
    regions[0].stockpile.goods = {"grain": 35.0}
    civ = Civilization(name="Cooperative", population=50, military=10, economy=40,
                       culture=30, stability=80, treasury=treasury,
                       leader=Leader(name="Steward", trait="cautious", reign_start=0),
                       regions=[r.name for r in regions])
    world = WorldState(name="Adversarial Aid Fixture", seed=42, regions=regions,
                       civilizations=[civ], relationships={}, agent_mode="hybrid",
                       mutual_aid_enabled=enabled)
    # The Mine is food-less by design (the stress the aid must answer): no
    # 2026-10 goods-economy foraging. Older sources ignore the key.
    world.tuning_overrides["ecology.subsistence_baseline"] = 0.0
    return world


def _total_goods(world) -> float:
    return math.fsum(v for r in world.regions for v in r.stockpile.goods.values())


def _harvest_index(rtype: int, goods_per_farmer: float) -> float:
    """Realized harvest index that the economy converts to ``goods_per_farmer``."""
    try:
        from chronicler.ecology import harvest_normal_index
    except ImportError:  # sources before the 2026-10 goods-unit conversion
        return goods_per_farmer
    return goods_per_farmer * harvest_normal_index(rtype)


def _set_yield(region, value: float) -> None:
    # No ecology tick runs here, so the prescribed crop (goods per farmer) is
    # also the realized harvest that the integrated Phase 2 economy reads.
    region.resource_effective_yields[0] = value
    region.resource_current_yields[0] = _harvest_index(region.resource_types[0], value)


def _schedule(world, turn: int) -> list[str]:
    changes = []
    if turn == 3:
        _set_yield(world.regions[0], 4.0)
        changes.append("Donor effective grain yield .5 -> 4; no stock injection")
    if turn == 5:
        world.regions[1].resource_types[0] = 0
        _set_yield(world.regions[1], 2.0)
        changes.append("Recipient primary ore -> grain, effective yield2; production ledger accounts output")
    if turn == 6:
        _set_yield(world.regions[1], 0.0)
        changes.append("Recipient effective grain yield2 -> 0; existing stocks/cargo preserved")
    return changes


def _commitment_rows(sim):
    if not hasattr(sim, "get_stockpile_commitments"):
        return None  # only permitted for the disabled untouched-native control
    return pa.record_batch(sim.get_stockpile_commitments()).to_pylist()


def run_adversarial(enabled: bool, treasury: int = 2) -> dict:
    if enabled:
        from chronicler.mutual_aid import (
            dispatch_mutual_aid, observe_mutual_aid, read_stockpile_commitments,
        )
    world = _world(enabled, treasury)
    bridge = AgentBridge(world, mode="hybrid")
    history = []
    try:
        for turn in range(15):
            world.turn = turn
            scenario_changes = _schedule(world, turn)
            snap = bridge.get_snapshot()
            counts = Counter(snap.column("region").to_pylist())
            demand = {r.name: counts[i] * .5 for i, r in enumerate(world.regions)}
            before = _total_goods(world)
            stocks_before = {r.name: dict(r.stockpile.goods) for r in world.regions}
            raw_commitments = _commitment_rows(bridge._sim)
            prior_memory = {n: s.model_dump() for n, s in
                            getattr(world, "mutual_aid_state", {}).items()}
            treasury_before = world.civilizations[0].treasury
            aid_events = []
            if enabled:
                commitments = read_stockpile_commitments(world, bridge._sim)
                acc = StatAccumulator()
                aid_events = dispatch_mutual_aid(world, snap, acc=acc, commitments=commitments)
                acc.apply_keep(world)
                assert _commitment_rows(bridge._sim) == raw_commitments, "Aid mutated native cargo"
            elif hasattr(world, "mutual_aid_enabled"):
                # Exercise functions with saved/missing runtime data and prove strict no-op.
                from chronicler.mutual_aid import dispatch_mutual_aid, observe_mutual_aid
                state_before = world.model_dump_json()
                assert dispatch_mutual_aid(world, snap) == []
                observe_mutual_aid(world, None, None)
                assert world.model_dump_json() == state_before
            transfers = [t.model_dump() for t in getattr(world, "mutual_aid_last_transfers", [])]
            aid_loss = math.fsum(t["transit_loss"] for t in transfers)
            assert math.isclose(before, _total_goods(world) + aid_loss, rel_tol=1e-10, abs_tol=1e-8), "Aid balance failed"
            assert treasury_before - world.civilizations[0].treasury == sum(t["treasury_cost"] for t in transfers)
            stocks_after_aid = {r.name: dict(r.stockpile.goods) for r in world.regions}
            result = reconstruct_economy_result(
                *bridge._sim.tick_economy(
                    build_economy_region_input_batch(world),
                    build_economy_trade_route_batch(world, [("Cooperative", "Cooperative")]),
                    0, False, 1.0),
                world, require_oracle_shadow=True)
            bridge.set_economy_result(result)
            if enabled:
                observe_mutual_aid(world, result, snap)
            c = result.conservation
            residual = before + c["production"] + c["clamp_floor_loss"] - (
                _total_goods(world) + aid_loss + c["consumption"] + c["transit_loss"]
                + c["storage_loss"] + c["cap_overflow"] + (c["in_transit_delta"] or 0.0))
            assert abs(residual) < 5e-5, f"Native stock/cargo balance failed: {residual}"
            assert c["clamp_floor_loss"] == 0.0, "Fixture cannot use clamp corrections as food"
            if enabled:
                for donor_name in {t["donor"] for t in transfers}:
                    stock = world.region_map[donor_name]  # audit after aid, before consumption
                    free = math.fsum(max(0.0, stocks_after_aid[donor_name].get(g, 0.0)
                                        - commitments[donor_name][g]) for g in FOOD_GOODS)
                    assert free + 1e-8 >= 2 * demand[donor_name], "Donor reserve was spent"
                    for good in FOOD_GOODS:
                        committed = commitments[stock.name][good]
                        remaining = stocks_after_aid[stock.name].get(good, 0.0)
                        assert remaining + 1e-8 >= min(committed, stocks_before[stock.name].get(good, 0)), "Cargo was spent"
            bridge.sync_regions(world)
            bridge.tick_agents(world)
            normalized = world.model_dump(mode="json")
            # The fishery experiment is dormant in this aid-only control. Keep
            # every legacy field exact and verify added defaults before removal.
            if "fishery_experiment" in normalized:
                assert normalized.pop("fishery_experiment") == {
                    "enabled": False, "reserve_turns": 8., "recovery_rate": .04,
                    "harvest_fraction": .25, "reference_workers": 200,
                }
                for region in normalized["regions"]:
                    assert region.pop("fishery_stocks") == [1., 1., 1.]
                    assert region.pop("fishery_yield_ratios") == [1., 1., 1.]
                    assert region.pop("fishery_catch_budgets") == [None, None, None]
            for key in ("mutual_aid_enabled", "mutual_aid_state", "mutual_aid_last_dispatch_turn",
                        "mutual_aid_last_transfers"):
                normalized.pop(key, None)
            history.append({
                "turn": turn, "scenario_changes": scenario_changes,
                "food_demand": demand, "stocks_before": stocks_before,
                "native_commitments": raw_commitments, "prior_memory": prior_memory,
                "stocks_after_aid": stocks_after_aid, "transfers": transfers,
                "aid_events": [e.model_dump() for e in aid_events],
                "aid_transit_loss": aid_loss, "treasury_before": treasury_before,
                "treasury_after": world.civilizations[0].treasury,
                "sufficiency": result.food_sufficiency,
                "memory_after": {n: s.model_dump() for n, s in
                                 getattr(world, "mutual_aid_state", {}).items()},
                "economy_conservation": c, "conservation_residual": residual,
                "tax_output_not_credited": {str(k): v for k, v in result.treasury_tax.items()},
                "delivery_diagnostics": pa.record_batch(bridge._sim.get_delivery_diagnostics()).to_pylist(),
                "merchant_trip_stats": bridge._sim.get_merchant_trip_stats(),
                "world_after_behavior": normalized,
                "agent_snapshot": pa.record_batch(bridge.get_snapshot()).to_pydict(),
            })
    finally:
        bridge.close()
    return {"base": "edf7299", "source": chronicler.__file__, "native": chronicler_agents.__file__,
            "native_has_stockpile_commitments": hasattr(bridge._sim, "get_stockpile_commitments"),
            "enabled": enabled, "initial_treasury": treasury, "seed": 42, "turns": 15,
            "scope": "native economy + unmodified agent behavior; fixed relief budget; no macro fiscal credits or ecology tick",
            "full_hybrid_continuation_tested": False, "history": history}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enabled", action="store_true")
    group.add_argument("--disabled", action="store_true")
    parser.add_argument("--treasury", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(run_adversarial(args.enabled, args.treasury), indent=2))
