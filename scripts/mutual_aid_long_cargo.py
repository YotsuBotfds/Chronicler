"""Private deterministic qualification; independent grain/salt accounting.

Policy lane uses synthetic snapshots/commitments and no native runtime. Native
lane uses real planner cargo through direct ABI calls; initial stocks, zero crop
production, explicit route graph and route-margin inputs are fixture inputs.
No macro loop, ecology, checkpoint restore, or policy tuning is exercised.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from importlib import util
from importlib.machinery import EXTENSION_SUFFIXES
import json
import math
from pathlib import Path

import pyarrow as pa

from chronicler.economy import EconomyResult, FIXED_GOODS
from chronicler.models import Civilization, Leader, Region, WorldState
from chronicler.mutual_aid import dispatch_mutual_aid, observe_mutual_aid, read_stockpile_commitments

GOODS = ("grain", "salt")
# Independent specification values: deliberately do not import policy/economy constants.
SURVIVAL = {"grain": .95, "salt": 1.0}
TOL = 2e-4  # ABI stock and diagnostic quantities are float32.


def close(actual, expected, tolerance=1e-8):
    assert math.isfinite(actual) and abs(actual - expected) <= tolerance, (actual, expected)


def stocks(world):
    return {r.name: {g: r.stockpile.goods.get(g, 0.) for g in GOODS} for r in world.regions}


def world_for(names, edges, initial, populations, enabled=True, seed=42, treasury=100):
    regions = [Region(name=n, terrain="plains", carrying_capacity=120, population=populations[n],
                      resources="fertile", controller="Cooperative", adjacencies=edges[n],
                      resource_types=[255, 255, 255], resource_effective_yields=[0., 0., 0.]) for n in names]
    for r in regions:
        r.stockpile.goods = dict(initial.get(r.name, {}))
    civ = Civilization(name="Cooperative", population=sum(populations.values()), military=10,
                       economy=40, culture=30, stability=80, treasury=treasury,
                       leader=Leader(name="Steward", trait="cautious", reign_start=0), regions=names)
    world = WorldState(name="Long cargo qualification", seed=seed, regions=regions, civilizations=[civ],
                       relationships={}, agent_mode="hybrid", mutual_aid_enabled=enabled)
    # Slot-less regions with no production are the specification here: no
    # 2026-10 goods-economy foraging. Older sources ignore the key.
    world.tuning_overrides["ecology.subsistence_baseline"] = 0.0
    return world


def audit_aid(world, snap, commitments):
    """Per-region/per-good delta oracle plus aggregate bounds, no dispatch reimplementation."""
    before = stocks(world)
    counts = Counter(snap.column("region").to_pylist())
    demand = {r.name: counts[i] * .5 for i, r in enumerate(world.regions)}
    treasury = world.civilizations[0].treasury
    events = dispatch_mutual_aid(world, snap, commitments=commitments)
    transfers = [t.model_dump() for t in world.mutual_aid_last_transfers]
    expected = {n: dict(gs) for n, gs in before.items()}
    outgoing, incoming, losses = defaultdict(float), defaultdict(float), defaultdict(float)
    for t in transfers:
        assert t["donor"] != t["recipient"]
        assert t["recipient"] in world.region_map[t["donor"]].adjacencies
        assert t["donor"] in world.region_map[t["recipient"]].adjacencies
        sent = sum(t["sent"].values())
        close(t["treasury_cost"], math.ceil(sent * .1))
        loss = 0.
        for g, qty in t["sent"].items():
            assert g in GOODS and qty > 0
            received = qty * SURVIVAL[g]
            close(t["received"][g], received)
            expected[t["donor"]][g] -= qty
            expected[t["recipient"]][g] += received
            losses[g] += qty - received
            loss += qty - received
        close(t["transit_loss"], loss)
        outgoing[t["donor"]] += sent
        incoming[t["recipient"]] += sum(t["received"].values())
    after = stocks(world)
    for n in before:
        for g in GOODS:
            close(after[n][g], expected[n][g])
            assert after[n][g] >= -1e-8
    for n, sent in outgoing.items():
        assert sent <= demand[n] * .25 + 1e-8
        free = sum(max(0., after[n][g] - commitments[n][g]) for g in GOODS)
        assert free >= 2 * demand[n] - 1e-8
        for g in GOODS:
            assert after[n][g] >= min(before[n][g], commitments[n][g]) - 1e-8
    for n, received in incoming.items():
        assert received <= demand[n] * .5 + 1e-8
    for g in GOODS:
        close(sum(v[g] for v in before.values()), sum(v[g] for v in after.values()) + losses[g])
    close(treasury - world.civilizations[0].treasury, sum(t["treasury_cost"] for t in transfers))
    state = world.model_dump_json()
    assert dispatch_mutual_aid(world, snap, commitments=commitments) == []
    assert world.model_dump_json() == state  # repeated planning cannot dispatch twice.
    return {"before": before, "after": after, "demand": demand, "transfers": transfers,
            "losses": dict(losses), "events": len(events), "treasury": world.civilizations[0].treasury}


def run_policy(enabled=True, reverse=False, treasury=100):
    names = ["A", "B", "C", "First", "Second"]
    if reverse:
        names.reverse()
    edges = {n: (["First", "Second"] if n in "ABC" else ["A", "B", "C"]) for n in names}
    populations = {n: 10 if n == "First" else 20 for n in names}
    world = world_for(names, edges, {"A": {"grain": 25}, "B": {"salt": 27.5}, "C": {"grain": 27}},
                      populations, enabled=enabled, treasury=treasury)
    snap = pa.record_batch({"region": pa.array([i for i, n in enumerate(names) for _ in range(populations[n])], type=pa.uint16())})
    commitments = {n: {g: 0. for g in FIXED_GOODS} for n in names}
    commitments["A"]["grain"] = 4.
    commitments["B"]["salt"] = 3.
    suff = {n: 1.5 if n in "ABC" else (0. if n == "First" else .2) for n in names}
    for turn in range(3):
        world.turn = turn
        observe_mutual_aid(world, EconomyResult(food_sufficiency=suff), snap)
    history = []
    for turn in range(3, 9):
        world.turn = turn
        history.append(audit_aid(world, snap, commitments))
        observe_mutual_aid(world, EconomyResult(food_sufficiency=suff), snap)
    return {"lane": "python-policy-synthetic-commitments", "enabled": enabled,
            "treasury": treasury, "history": history}


def diagnostic(sim):
    rows = pa.record_batch(sim.get_delivery_diagnostics()).to_pylist()
    return {(r["region_id"], FIXED_GOODS[r["good_slot"]]): r for r in rows}


def route_batch(edges):
    return pa.record_batch({"from_region": pa.array([a for a, b in edges], type=pa.uint16()),
                            "to_region": pa.array([b for a, b in edges], type=pa.uint16()),
                            "is_river": pa.array([False] * len(edges), type=pa.bool_()),
                            "transport_cost": pa.array([.1] * len(edges), type=pa.float32())})


def native_identity():
    import chronicler_agents as ca
    spec = util.find_spec("chronicler_agents.chronicler_agents")
    assert spec and spec.origin.endswith(tuple(EXTENSION_SUFFIXES)), spec
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        assert isinstance(getattr(ca, name), type)
    p = Path(spec.origin)
    return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def stock_oracle(before, counts, delta, population):
    """Independent zero-production economy specification for grain/salt.

    Derive ingress from lifetime counter deltas, consumption from the live
    snapshot, then storage preservation and cap. No reconstructed conservation
    totals or native stock outputs feed this expected-value calculation.
    """
    expected, ledger = {}, {k: defaultdict(float) for k in ("departures", "arrivals", "returns", "transit_loss", "consumption", "storage_loss", "cap_overflow")}
    for rid, (n, goods) in enumerate(before.items()):
        values = {}
        for g in GOODS:
            d, a, r = (delta[rid, g][k] for k in ("total_departures", "total_arrivals", "total_returns"))
            assert min(d, a, r) >= -TOL
            values[g] = goods[g] - d + a * SURVIVAL[g] + r
            assert values[g] >= -TOL, (n, g, values[g])
            values[g] = max(0., values[g])
            for field, qty in (("departures", d), ("arrivals", a), ("returns", r), ("transit_loss", a * (1 - SURVIVAL[g]))):
                ledger[field][g] += qty
        total = sum(values.values())
        fraction = min(1., counts[rid] * .5 / total) if total else 0.
        for g in GOODS:
            consumed = values[g] * fraction
            values[g] -= consumed
            ledger["consumption"][g] += consumed
        preservation = min(.5, values["salt"] / max(.1, values["grain"]) * 2.5)
        decay = values["grain"] * .03 * (1 - preservation)
        values["grain"] -= decay
        ledger["storage_loss"]["grain"] += decay
        for g in GOODS:
            cap = population[n] * 2.5
            overflow = max(0., values[g] - cap)
            values[g] -= overflow
            ledger["cap_overflow"][g] += overflow
        expected[n] = values
    return expected, {k: {g: v[g] for g in GOODS} for k, v in ledger.items()}


def run_native(hops=4, seed=42, enabled=True, disruption=None, turns=28):
    identity = native_identity()
    from chronicler.agent_bridge import AgentBridge, build_region_batch, build_signals
    from chronicler.economy import build_economy_region_input_batch, build_economy_trade_route_batch, reconstruct_economy_result
    names = ["A", "B"] + [f"Way{i}" for i in range(hops - 1)] + ["First", "Second"]
    # Aid adjacency differs from the explicit directed merchant network. Both are scenario inputs.
    adjacency = {n: (["First", "Second"] if n in ("A", "B") else (["A", "B"] if n in ("First", "Second") else [])) for n in names}
    population = {n: (10 if n == "First" else 20) if n in ("A", "B", "First", "Second") else 0 for n in names}
    initial = {"A": {"grain": 50., "salt": 50.}, "B": {"grain": 50., "salt": 50.}}
    world = world_for(names, adjacency, initial, population, enabled, seed)
    chain = list(range(2, len(names) - 2))
    edges = [(0, chain[0]), (1, chain[0])] + list(zip(chain, chain[1:])) + [(chain[-1], len(names) - 2), (chain[-1], len(names) - 1)]
    bridge = AgentBridge(world, mode="hybrid")
    sim = bridge._sim
    sim.set_merchant_route_graph(route_batch(edges))
    last_settled = diagnostic(sim)
    history = []
    cargo = {g: 0. for g in GOODS}
    try:
        for turn in range(turns):
            world.turn = turn
            snap = pa.record_batch(sim.get_snapshot())
            counts = Counter(snap.column("region").to_pylist())
            commitments_raw = pa.record_batch(sim.get_stockpile_commitments()).to_pylist()
            commitments = read_stockpile_commitments(world, sim)
            assert pa.record_batch(sim.get_stockpile_commitments()).to_pylist() == commitments_raw
            aid = audit_aid(world, snap, commitments)
            assert pa.record_batch(sim.get_stockpile_commitments()).to_pylist() == commitments_raw
            diag = diagnostic(sim)
            assert diagnostic(sim) == diag  # lifetime counter reads do not drain.
            delta = {key: {k: row[k] - last_settled[key][k] for k in row if k.startswith("total_")} for key, row in diag.items()}
            try:
                expected, ledger = stock_oracle(aid["after"], counts, delta, population)
            except AssertionError as error:
                failure = {"error": str(error), "native": identity, "hops": hops, "seed": seed,
                           "enabled": enabled, "disruption": disruption, "turn": turn,
                           "aid": aid, "commitments": commitments_raw,
                           "delivery_delta": [{"region_id": key[0], "good": key[1], **v} for key, v in delta.items()],
                           "history": history}
                target = Path(__file__).resolve().parents[1] / "qualification-receipts"
                target.mkdir(exist_ok=True)
                (target / f"failure-{hops}-{seed}-{enabled}-{disruption}.json").write_text(json.dumps(failure, indent=2))
                raise
            previous_cargo = dict(cargo)
            for g in GOODS:
                cargo[g] += ledger["departures"][g] - ledger["arrivals"][g] - ledger["returns"][g]
                assert cargo[g] >= -TOL
            result = reconstruct_economy_result(*sim.tick_economy(build_economy_region_input_batch(world),
                        build_economy_trade_route_batch(world, [("Cooperative", "Cooperative")]), 0, False, 1.), world, require_oracle_shadow=True)
            actual = stocks(world)
            errors = {n: {g: actual[n][g] - expected[n][g] for g in GOODS} for n in names}
            for n in names:
                for g in GOODS:
                    close(actual[n][g], expected[n][g], TOL)
            # Full independent per-good stock + outstanding cargo balance.
            for g in GOODS:
                lhs = sum(v[g] for v in aid["before"].values()) + previous_cargo[g]
                rhs = sum(v[g] for v in actual.values()) + cargo[g] + aid["losses"].get(g, 0.) + sum(ledger[k][g] for k in ("transit_loss", "consumption", "storage_loss", "cap_overflow"))
                close(lhs, rhs, TOL * len(names))
            c = result.conservation
            close(c["production"], 0., TOL)
            close(c["clamp_floor_loss"], 0., TOL)
            close(c["in_transit_delta"], sum(cargo.values()) - sum(previous_cargo.values()), TOL)
            settled = diagnostic(sim)
            for key in diag:
                for k in ("total_departures", "total_arrivals", "total_returns"):
                    close(settled[key][k], diag[key][k])
                close(settled[key]["total_transit_decay"] - diag[key]["total_transit_decay"], delta[key]["total_arrivals"] * (1 - SURVIVAL.get(key[1], 1.)), TOL)
            after_commitments = pa.record_batch(sim.get_stockpile_commitments()).to_pylist()
            for before_row, after_row in zip(commitments_raw, after_commitments, strict=True):
                close(after_row["pending_departure"], 0.)
                close(after_row["reserved"], before_row["reserved"])
            observe_mutual_aid(world, result, snap)
            # One economy-only replay verifies that already-settled arrivals and
            # departures cannot be applied twice; legitimate consumption continues.
            if turn == hops + 3:
                zero = {key: {k: 0. for k in row if k.startswith("total_")} for key, row in settled.items()}
                replay_expected, replay_ledger = stock_oracle(actual, counts, zero, population)
                replay = reconstruct_economy_result(*sim.tick_economy(build_economy_region_input_batch(world), build_economy_trade_route_batch(world, []), 0, False, 1.), world, require_oracle_shadow=True)
                for n in names:
                    for g in GOODS:
                        close(stocks(world)[n][g], replay_expected[n][g], TOL)
                close(replay.conservation["in_transit_delta"], 0.)
                close(replay.conservation["transit_loss"], 0.)
                assert diagnostic(sim) == settled
            else:
                replay_ledger = None
            bridge.set_economy_result(result)
            batch = build_region_batch(world, result)
            batch = batch.set_column(batch.schema.get_field_index("merchant_route_margin"), "merchant_route_margin", pa.array([.0] * (len(names) - 2) + [.9, .8], type=pa.float32()))
            if disruption == "death" and turn == 2:
                batch = batch.set_column(batch.schema.get_field_index("catastrophe_deaths_this_turn"), "catastrophe_deaths_this_turn", pa.array([100] * len(names), type=pa.uint16()))
            sim.set_region_state(batch)
            active_edges = edges
            if disruption == "cancel" and turn == 1:
                active_edges = [e for e in edges if e[0] not in (0, 1)]
            if disruption == "return" and turn == 2:
                active_edges = [e for e in edges if e[0] != chain[0]]
            if turn >= turns - hops - 2:
                active_edges = []  # settle/cancel/return all cargo before ending.
            sim.set_merchant_route_graph(route_batch(active_edges))
            sim.tick(turn, build_signals(world, economy_result=result))
            stats = sim.get_merchant_trip_stats()
            knowledge = sim.get_knowledge_stats()
            try:
                close(stats["total_in_transit_qty"], sum(r["total_departures"] - r["total_arrivals"] - r["total_returns"] for r in diagnostic(sim).values()), TOL)
            except AssertionError as error:
                target = Path(__file__).resolve().parents[1] / "qualification-receipts"
                failure = {"error": str(error), "turn": turn, "native": identity,
                           "hops": hops, "seed": seed, "enabled": enabled, "disruption": disruption,
                           "history": history, "stats": stats, "before_snapshot": snap.to_pylist(),
                           "after_snapshot": pa.record_batch(sim.get_snapshot()).to_pylist(),
                           "diagnostics": list(diagnostic(sim).values())}
                (target / f"failure-flight-{hops}-{seed}-{enabled}-{disruption}.json").write_text(json.dumps(failure, indent=2))
                raise
            history.append({"turn": turn, "aid": aid, "commitments": commitments_raw,
                            "after_economy_commitments": after_commitments,
                            "delivery_delta": [{"region_id": key[0], "good": key[1], **v} for key, v in delta.items() if key[1] in GOODS],
                            "cargo": dict(cargo), "oracle_ledger": ledger, "oracle_errors": errors,
                            "native_conservation": c, "economy_replay_ledger": replay_ledger,
                            "stocks_after_economy": actual, "trip_stats": stats,
                            "knowledge_stats": knowledge, "edges": active_edges})
            last_settled = settled
    finally:
        bridge.close()
    return {"lane": "native-direct-ABI", "native": identity, "hops": hops, "seed": seed, "enabled": enabled,
            "disruption": disruption, "turns": turns, "initial_stocks": initial,
            "route_margin_input": {"First": .9, "Second": .8}, "history": history,
            "full_hybrid_continuation_tested": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lane", choices=["policy", "native"], required=True)
    p.add_argument("--hops", type=int, choices=[3, 4, 5], default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--disruption", choices=["cancel", "return", "death"])
    p.add_argument("--disabled", action="store_true")
    args = p.parse_args()
    receipt = run_policy(not args.disabled) if args.lane == "policy" else run_native(args.hops, args.seed, not args.disabled, args.disruption)
    print(json.dumps(receipt, indent=2, sort_keys=True))
