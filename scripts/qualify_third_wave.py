"""Private joint qualification through complete run_turn ordering.

The fixture supplies a directed merchant network and route-margin inputs through
an observing ABI proxy. Cargo is planned by the real native kernel; no trips,
ledgers, buffers, agents, or delivery counters are injected. Fishing suspension
at turn 16 and route shutdown at turn 23 are explicit scenario interventions.
The death case supplies catastrophe deaths of 1000 per region at turn 2.
This is accounting evidence, not a population experiment or checkpoint test.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

import pyarrow as pa

from chronicler.models import ActionType, Civilization, Leader, Region, WorldState
from chronicler.agent_bridge import AgentBridge
from chronicler.simulation import run_turn

GOODS = ("grain", "fish", "salt", "timber", "ore", "botanicals", "precious", "exotic")
FOOD = ("grain", "fish", "salt", "botanicals", "exotic")
SURVIVAL = dict(zip(GOODS, (.95, .92, 1., .99, 1., .96, 1., .94)))
DECAY = dict(zip(GOODS, (.03, .06, 0., .005, 0., .02, 0., .04)))
RT_GOOD = {0: "grain", 1: "timber", 2: "botanicals", 3: "fish", 4: "salt", 5: "ore", 6: "precious", 7: "exotic"}
TOL = 1e-3  # independent double-precision oracle versus float32 ABI


def _goods_units(index: float) -> float:
    """Fish harvest-index quantity in economy goods (2026-10 food balance)."""
    try:
        from chronicler.ecology import goods_per_worker
    except ImportError:  # sources before the goods-unit conversion
        return index
    return goods_per_worker(3, index)


def close(a, b, tol=TOL):
    assert math.isfinite(a) and math.isfinite(b) and abs(a - b) <= tol, (a, b)


def inventory(world):
    return {r.name: {g: r.stockpile.goods.get(g, 0.) for g in GOODS} for r in world.regions}


def diagnostics(sim):
    return {(r["region_id"], GOODS[r["good_slot"]]): r for r in pa.record_batch(sim.get_delivery_diagnostics()).to_pylist()}


def network(edges):
    return pa.record_batch({"from_region": pa.array([a for a, b in edges], type=pa.uint16()),
                            "to_region": pa.array([b for a, b in edges], type=pa.uint16()),
                            "is_river": pa.array([False] * len(edges), type=pa.bool_()),
                            "transport_cost": pa.array([.1] * len(edges), type=pa.float32())})


def make_world(fishery=False, aid=False, seed=42, hops=5):
    names = ["A", "B"] + [f"Way{i}" for i in range(hops - 1)] + ["First", "Second"]
    regions = []
    for name in names:
        donor = name in ("A", "B")
        recipient = name in ("First", "Second")
        population = 200 if donor or name == "Second" else (100 if recipient else 0)
        region = Region(name=name, terrain="coast" if name == "A" else "plains",
                        carrying_capacity=1200, population=population, resources="maritime" if name == "A" else "fertile",
                        controller="Cooperative", adjacencies=["First", "Second"] if donor else (["A", "B"] if recipient else []),
                        resource_types=[3 if name == "A" else 255, 255, 255],
                        resource_base_yields=[1. if name == "A" else 0., 0., 0.],
                        resource_effective_yields=[1. if name == "A" else 0., 0., 0.])
        if donor:
            region.stockpile.goods = {"grain": 500., "salt": 500.}
        if hasattr(region, "fishery_stocks"):
            region.fishery_stocks[0] = .001 if name == "A" else 1.
        regions.append(region)
    civ = Civilization(name="Cooperative", population=700, military=10, economy=40, culture=30,
                       stability=80, treasury=100, leader=Leader(name="Steward", trait="cautious", reign_start=0), regions=names)
    world = WorldState(name="Third-wave full-turn joint fixture", seed=seed, regions=regions,
                       civilizations=[civ], relationships={}, agent_mode="hybrid")
    if hasattr(world, "fishery_experiment"):
        world.fishery_experiment.enabled = fishery
    else:
        assert not fishery
    if hasattr(world, "mutual_aid_enabled"):
        world.mutual_aid_enabled = aid
    else:
        assert not aid
    return world


def legacy_values(world):
    """Shared legacy-value projection for paired sources with different schemas.

    This includes enabled cases and fixture-preset stock, so it is separate from
    the strict dormant-default artifact projection in third_wave_controls.py.
    """
    data = world.model_dump(mode="json")
    for key in ("fishery_experiment", "mutual_aid_enabled", "mutual_aid_state", "mutual_aid_last_dispatch_turn", "mutual_aid_last_transfers"):
        data.pop(key, None)
    for region in data["regions"]:
        for key in ("fishery_stocks", "fishery_yield_ratios", "fishery_catch_budgets"):
            region.pop(key, None)
    return data


class ObservedRuntime:
    def __init__(self, sim, world, hops, disruption):
        self.sim, self.world, self.hops, self.disruption = sim, world, hops, disruption
        self.set_merchant_route_graph(None)
        self.settled = diagnostics(sim)
        self.ecology = None
        self.economy = None
        self.before_aid = None
        self.commitments = None
        self.transfers = []
        self.previous_catch = 0.

    def __getattr__(self, name):
        return getattr(self.sim, name)

    def get_stockpile_commitments(self):
        result = self.sim.get_stockpile_commitments()
        assert pa.record_batch(result).to_pylist() == pa.record_batch(self.sim.get_stockpile_commitments()).to_pylist()
        self.before_aid = inventory(self.world)
        self.commitments = pa.record_batch(result).to_pylist()
        return result

    def set_region_state(self, batch):
        # Explicit economic attractiveness supplied to the native route planner.
        n = len(self.world.regions)
        batch = batch.set_column(batch.schema.get_field_index("merchant_route_margin"), "merchant_route_margin",
                                 pa.array([0.] * (n - 2) + [.9, .8], type=pa.float32()))
        if self.disruption == "death" and self.world.turn == 2:
            batch = batch.set_column(batch.schema.get_field_index("catastrophe_deaths_this_turn"), "catastrophe_deaths_this_turn",
                                     pa.array([1000] * n, type=pa.uint16()))
        return self.sim.set_region_state(batch)

    def set_merchant_route_graph(self, _batch):
        n = len(self.world.regions)
        chain = list(range(2, n - 2))
        edges = [(0, chain[0]), (1, chain[0])] + list(zip(chain, chain[1:])) + [(chain[-1], n - 2), (chain[-1], n - 1)]
        if self.disruption == "cancel" and self.world.turn == 1:
            edges = [e for e in edges if e[0] not in (0, 1)]
        if self.disruption == "return" and self.world.turn == 2:
            edges = [e for e in edges if e[0] != chain[0]]
        if self.world.turn >= 23:
            edges = []
        return self.sim.set_merchant_route_graph(network(edges))

    def tick_ecology(self, *args):
        region = self.world.regions[0]
        before = region.fishery_stocks[0] if hasattr(region, "fishery_stocks") else None
        snap = pa.record_batch(self.sim.get_snapshot()).to_pylist()
        workers = sum(r["region"] == 0 and r["occupation"] == 0 for r in snap)
        output = self.sim.tick_ecology(*args)
        self.ecology = {"before": before, "workers": workers,
                        "potential": output[0].column("current_turn_yield_0")[0].as_py()}
        return output

    def apply_fishery_yield_patch(self, batch):
        region, obs = self.world.regions[0], self.ecology
        recovery = .04 * (1. - obs["before"])
        available = obs["before"] + recovery
        effort = min(obs["workers"] / 200., 4.)
        harvest = min(obs["potential"] * effort, available * 8. * .25)
        actual = harvest / effort if effort else obs["potential"]
        close(region.fishery_stocks[0], available - harvest / 8., 1e-10)
        close(region.fishery_catch_budgets[0], harvest * 200., 1e-7)
        close(region.resource_current_yields[0], actual, 1e-7)
        assert 0 <= region.fishery_stocks[0] <= 1 and actual <= obs["potential"] + 1e-7
        if self.world.turn >= 16:
            close(harvest, 0., 1e-10)
            assert region.fishery_stocks[0] >= obs["before"]
        obs.update(recovery=recovery, harvest=harvest, stock=region.fishery_stocks[0],
                   catch_budget=region.fishery_catch_budgets[0], yield_per_worker=actual)
        self.previous_catch = harvest * 200.
        return self.sim.apply_fishery_yield_patch(batch)

    def tick_economy(self, batch, *args):
        snap = pa.record_batch(self.sim.get_snapshot()).to_pylist()
        counts = Counter(r["region"] for r in snap)
        farmers = Counter(r["region"] for r in snap if r["occupation"] == 0)
        self.transfers = [t.model_dump(mode="json") for t in getattr(self.world, "mutual_aid_last_transfers", [])]
        self._audit_aid(counts)
        diag = diagnostics(self.sim)
        assert diag == diagnostics(self.sim)
        rows = batch.to_pylist()
        enabled = getattr(getattr(self.world, "fishery_experiment", None), "enabled", False)
        if enabled:
            # The expected cap comes from the prior independently audited biomass
            # debit, not from trusting the packed production input being tested.
            close(rows[0]["fishery_catch_budget_0"], _goods_units(self.previous_catch))
        expected, ledger = {}, {k: defaultdict(float) for k in ("production", "consumption", "storage_loss", "cap_overflow", "departures", "arrivals", "returns", "transit_loss")}
        errors = []
        food_suff = {}
        for rid, row in enumerate(rows):
            values = {g: row[f"stockpile_{g}"] for g in GOODS}
            # Farmer labor is split equally across occupied valid slots; each
            # fish slot's output is capped by its prior catch budget.
            occupied = [s for s in range(3) if RT_GOOD.get(row[f"resource_type_{s}"])]
            for s in occupied:
                good = RT_GOOD[row[f"resource_type_{s}"]]
                production = row[f"resource_yield_{s}"] * farmers[rid] / len(occupied)
                budget = row.get(f"fishery_catch_budget_{s}")
                if budget is not None:
                    production = min(production, budget)
                ledger["production"][good] += production
                if enabled and rid == 0 and s == 0:
                    assert production <= _goods_units(self.previous_catch) + TOL
                values[good] += production
            for g in GOODS:
                delta = {key: diag[rid, g][key] - self.settled[rid, g][key] for key in ("total_departures", "total_arrivals", "total_returns")}
                d, a, r = (delta[k] for k in ("total_departures", "total_arrivals", "total_returns"))
                assert min(d, a, r) >= -TOL
                values[g] += -d + a * SURVIVAL[g] + r
                assert values[g] >= -TOL, (rid, g, values[g])
                for key, value in (("departures", d), ("arrivals", a), ("returns", r), ("transit_loss", a * (1. - SURVIVAL[g]))):
                    ledger[key][g] += value
            total = sum(values[g] for g in FOOD)
            food_suff[self.world.regions[rid].name] = min(2., total / max(.1, counts[rid] * .5))
            fraction = min(1., counts[rid] * .5 / total) if total else 0.
            for g in FOOD:
                consumed = values[g] * fraction
                values[g] -= consumed
                ledger["consumption"][g] += consumed
            preservation = min(.5, values["salt"] / max(.1, sum(values[g] for g in FOOD if g != "salt")) * 2.5)
            for g in GOODS:
                decay = values[g] * DECAY[g] * (1. - preservation if g in FOOD else 1.)
                values[g] -= decay
                ledger["storage_loss"][g] += decay
                overflow = max(0., values[g] - row["storage_population"] * 2.5)
                values[g] -= overflow
                ledger["cap_overflow"][g] += overflow
            expected[rid] = values
        output = self.sim.tick_economy(batch, *args)
        actual = pa.record_batch(output[0]).to_pylist()
        for rid, row in enumerate(actual):
            for g in GOODS:
                errors.append(abs(row[f"stockpile_{g}"] - expected[rid][g]))
                close(row[f"stockpile_{g}"], expected[rid][g])
            close(row["food_sufficiency"], food_suff[self.world.regions[rid].name])
        conservation = pa.record_batch(output[4]).to_pylist()[0]
        close(conservation["production"], sum(ledger["production"].values()))
        close(conservation["clamp_floor_loss"], 0.)
        close(conservation["in_transit_delta"], sum(ledger["departures"].values())
              - sum(ledger["arrivals"].values()) - sum(ledger["returns"].values()), TOL * len(rows))
        for key in ("consumption", "storage_loss", "cap_overflow", "transit_loss"):
            close(conservation[key], sum(ledger[key].values()), TOL * len(rows))
        self.economy = {"oracle_ledger": {k: dict(v) for k, v in ledger.items()}, "max_stock_error": max(errors),
                        "input": rows, "food_sufficiency": food_suff, "native_conservation": conservation,
                        "native_stocks": {self.world.regions[rid].name: {g: row[f"stockpile_{g}"] for g in GOODS} for rid, row in enumerate(actual)},
                        "prior_independent_catch": self.previous_catch if enabled else None}
        balances = {}
        for g in GOODS:
            previous_cargo = sum(r["total_departures"] - r["total_arrivals"] - r["total_returns"]
                                 for (rid, good), r in self.settled.items() if good == g)
            current_cargo = sum(r["total_departures"] - r["total_arrivals"] - r["total_returns"]
                                for (rid, good), r in diag.items() if good == g)
            lhs = sum(row[f"stockpile_{g}"] for row in rows) + previous_cargo + ledger["production"][g]
            rhs = sum(row[f"stockpile_{g}"] for row in actual) + current_cargo
            rhs += sum(ledger[k][g] for k in ("consumption", "storage_loss", "cap_overflow", "transit_loss"))
            close(lhs, rhs, TOL * len(rows))
            balances[g] = lhs - rhs
        self.economy["stock_plus_cargo_balance_residual"] = balances
        after = diagnostics(self.sim)
        for key, value in diag.items():
            for field in ("total_departures", "total_arrivals", "total_returns"):
                close(after[key][field], value[field])
        if callable(getattr(self.sim, "get_stockpile_commitments", None)):
            before_reservations = pa.record_batch(self.sim.get_stockpile_commitments()).to_pylist()
            assert all(row["pending_departure"] == 0 for row in before_reservations)
            self.economy["settled_commitments"] = before_reservations
        self.settled = after
        return output

    def _audit_aid(self, counts):
        if self.before_aid is None:
            assert not self.transfers
            return
        expected = {n: dict(v) for n, v in self.before_aid.items()}
        outgoing, incoming = defaultdict(float), defaultdict(float)
        for transfer in self.transfers:
            donor, recipient = transfer["donor"], transfer["recipient"]
            assert donor in self.world.region_map[recipient].adjacencies and recipient in self.world.region_map[donor].adjacencies
            sent = sum(transfer["sent"].values())
            assert transfer["treasury_cost"] == math.ceil(sent * .1)
            loss = 0.
            for g, qty in transfer["sent"].items():
                assert g in FOOD and qty > 0
                close(transfer["received"][g], qty * SURVIVAL[g], 1e-8)
                expected[donor][g] -= qty
                expected[recipient][g] += qty * SURVIVAL[g]
                loss += qty * (1. - SURVIVAL[g])
            close(transfer["transit_loss"], loss, 1e-8)
            outgoing[donor] += sent
            incoming[recipient] += sum(transfer["received"].values())
        after = inventory(self.world)
        encumbered = {(row["region_id"], GOODS[row["good_slot"]]): row["reserved"] + row["pending_departure"] for row in self.commitments}
        for rid, region in enumerate(self.world.regions):
            for g in GOODS:
                close(after[region.name][g], expected[region.name][g], 1e-8)
            demand = counts[rid] * .5
            assert outgoing[region.name] <= demand * .25 + 1e-8
            assert incoming[region.name] <= demand * .5 + 1e-8
            if outgoing[region.name]:
                free = sum(max(0., after[region.name][g] - encumbered[rid, g]) for g in FOOD)
                assert free >= demand * 2. - 1e-8
                for g in FOOD:
                    assert after[region.name][g] >= min(self.before_aid[region.name][g], encumbered[rid, g]) - 1e-8
        # The production path supplies a real StatAccumulator; debit must be queued
        # exactly once there. A test wrapper below captures its treasury changes.

    def tick(self, *args):
        output = self.sim.tick(*args)
        stats = self.sim.get_merchant_trip_stats()
        outstanding = sum(r["total_departures"] - r["total_arrivals"] - r["total_returns"] for r in diagnostics(self.sim).values())
        close(stats["total_in_transit_qty"], outstanding)
        return output


def run_case(fishery=False, aid=False, seed=42, hops=5, disruption=None, turns=32):
    from unittest.mock import patch
    from chronicler.accumulator import StatAccumulator
    world = make_world(fishery, aid, seed, hops)
    bridge = AgentBridge(world, mode="hybrid")
    runtime = ObservedRuntime(bridge._sim, world, hops, disruption)
    bridge._sim = runtime
    history, hashes, legacy_hashes, snapshot_hashes = [], [], [], []
    original_add = StatAccumulator.add
    original_apply_keep = StatAccumulator.apply_keep
    aid_debits = []
    flushes = []

    def observe_add(acc, civ_id, civ, stat, delta, category):
        original_add(acc, civ_id, civ, stat, delta, category)
        # Observe explicit dispatch receipts at the boundary, independent of final
        # treasury (which also includes taxes, production and consequences).
        import inspect
        if stat == "treasury" and inspect.currentframe().f_back.f_code.co_name == "dispatch_mutual_aid":
            assert category == "keep" and delta < 0
            aid_debits.append(-delta)

    def observe_apply_keep(acc, active_world):
        before = [c.treasury for c in active_world.civilizations]
        expected = list(before)
        changes = []
        for change in acc._changes[acc._keep_applied_up_to:]:
            if change.category == "keep" and change.stat == "treasury":
                idx = change.civ_id
                expected[idx] = type(expected[idx])(max(0., expected[idx] + change.delta))
                changes.append({"civ": idx, "delta": change.delta})
        original_apply_keep(acc, active_world)
        assert acc._keep_applied_up_to == len(acc._changes)
        after = [c.treasury for c in active_world.civilizations]
        assert after == expected
        flushes.append({"before": before, "unapplied_treasury_changes": changes, "after": after})

    try:
        with patch.object(StatAccumulator, "add", observe_add), patch.object(StatAccumulator, "apply_keep", observe_apply_keep):
            for turn in range(turns):
                assert world.turn == turn
                if turn >= 16:
                    world.regions[0].resource_suspensions[3] = 100
                runtime.before_aid = runtime.commitments = None
                aid_debits.clear()
                flushes.clear()
                run_turn(world, lambda *_: ActionType.DEVELOP, lambda *_: "", seed=seed + turn, agent_bridge=bridge)
                assert aid_debits == [t["treasury_cost"] for t in runtime.transfers]
                for name, goods in inventory(world).items():
                    for good, quantity in goods.items():
                        close(quantity, runtime.economy["native_stocks"][name][good], 1e-9)
                if aid:
                    from chronicler.mutual_aid import dispatch_mutual_aid
                    prior = world.model_dump_json()
                    # run_turn has advanced world.turn: use the just-completed
                    # turn solely for this same-turn idempotence assertion.
                    world.turn = turn
                    same_turn = world.model_dump_json()
                    assert dispatch_mutual_aid(world, bridge.get_snapshot()) == []
                    assert world.model_dump_json() == same_turn
                    world.turn = turn + 1
                    assert world.model_dump_json() == prior
                row = {"turn": turn, "economy": runtime.economy, "fishery": runtime.ecology,
                       "transfers": runtime.transfers, "aid_treasury_debits": list(aid_debits),
                       "treasury_flushes": list(flushes),
                       "trip_stats": runtime.sim.get_merchant_trip_stats(), "diagnostics": list(diagnostics(runtime.sim).values()),
                       "stocks": inventory(world), "treasury": [c.treasury for c in world.civilizations],
                       "yield_famine_events": [e.model_dump(mode="json") for e in world.events_timeline if e.turn == turn and e.event_type == "famine"]}
                from chronicler.climate import get_climate_phase
                from chronicler.ecology import check_food_yield
                row["fishery"]["yield_famine_predicate"] = check_food_yield(
                    world.regions[0], world.regions[0].resource_current_yields,
                    get_climate_phase(turn, world.climate_config))
                snap = pa.record_batch(runtime.sim.get_snapshot()).to_pydict()
                canonical = json.dumps([world.model_dump(mode="json"), snap, row], sort_keys=True, separators=(",", ":"))
                hashes.append(hashlib.sha256(canonical.encode()).hexdigest())
                legacy_hashes.append(hashlib.sha256(json.dumps(legacy_values(world), sort_keys=True, separators=(",", ":")).encode()).hexdigest())
                snapshot_hashes.append(hashlib.sha256(json.dumps(snap, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
                history.append(row)
    finally:
        bridge.close()
    return {"flags": f"{int(fishery)}{int(aid)}", "seed": seed, "hops": hops, "disruption": disruption,
            "turns": turns, "history": history, "turn_sha256": hashes,
            "legacy_world_sha256": legacy_hashes, "native_snapshot_sha256": snapshot_hashes,
            "full_hybrid_checkpoint_continuation": False, "population_benefit_claim": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fishery", action="store_true")
    parser.add_argument("--aid", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hops", type=int, choices=(3, 4, 5), default=5)
    parser.add_argument("--disruption", choices=("cancel", "return", "death"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_case(args.fishery, args.aid, args.seed, args.hops, args.disruption)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "history"}))
