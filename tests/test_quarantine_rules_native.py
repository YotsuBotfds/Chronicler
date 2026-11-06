"""Quarantine rules with the real native extension (connected-world C1).

Agent merchants on a closed border (replan, unwind, no new crossing), the
dated hybrid chain (tick t blocked, observed at t+1, ledger at the end of
t+1, imports at t+2) and an exact hybrid checkpoint resume inside an active
closure with merchants in transit. Run against a freshly built extension.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pytest

import chronicler.contact_ledger as cl
import chronicler.epidemiology as ep
import chronicler.quarantine_rules as qr

pytestmark = pytest.mark.native

_REAL_OBSERVE = cl.observe_phase2


def _native():
    native = pytest.importorskip("chronicler_agents")
    sim = getattr(native, "AgentSimulator", None)
    if not isinstance(sim, type) or not hasattr(sim, "configure_transaction_receipts") \
            or not hasattr(sim, "checkpoint_state"):
        pytest.skip("requires a fresh chronicler_agents build (receipts and exact checkpoints)")
    return native


# --- a controlled border: two polities, merchants crossing ---------------------------------

def _border_fixture():
    from chronicler.agent_bridge import AgentBridge
    from chronicler.economy import EconomyResult
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.world_gen import generate_world

    world = generate_world(seed=42, num_regions=12, num_civs=4)
    world.agent_mode = "hybrid"
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    world.epidemics.quarantine_rules = qr.QuarantineRulesState(mode="closure")
    a, b = world.civilizations[0], world.civilizations[1]
    half = len(world.regions) // 2
    a.regions = [r.name for r in world.regions[:half]]
    b.regions = [r.name for r in world.regions[half:]]
    for civ in world.civilizations[2:]:
        civ.regions = []
    for i, region in enumerate(world.regions):
        region.controller = a.name if i < half else b.name
        region.stockpile.goods = {"grain": 50.0}
    for x, y in ((a.name, b.name), (b.name, a.name)):
        world.relationships[x][y].disposition = world.relationships[x][y].disposition.__class__("friendly")
    set_transaction_receipts_enabled(world, True)
    bridge = AgentBridge(world, mode="hybrid")
    # Controlled market (an FFI observation fixture, not a run): a dear,
    # populated destination in B; stocked origins everywhere.
    dear = next(i for i in reversed(range(half, len(world.regions))) if world.regions[i].population > 0)
    bridge._economy_result = EconomyResult(
        food_sufficiency={r.name: 0.25 if i == dear else 2.0 for i, r in enumerate(world.regions)},
        market_demand={r.name: (100.0, 0.0, 0.0, 0.0) for r in world.regions},
        market_supply={r.name: (25.0 if i == dear else 200.0, 0.0, 0.0, 0.0)
                       for i, r in enumerate(world.regions)})
    return world, bridge, half


def _border_tick(world, bridge, close: bool):
    """One agent tick through the real bridge composition, closed or open."""
    from chronicler.agent_bridge import _quarantine_route_graph, build_signals
    from chronicler.columnar import pylist
    from chronicler.economy import build_merchant_route_graph
    from chronicler.transaction_receipts import capture_transaction_receipts, prepare_transaction_receipts

    rules = world.epidemics.quarantine_rules
    rules.receipt = qr.QuarantineReceipt(turn=world.turn)
    rules.closures = ([qr.QuarantineClosure(id=1, civ=1, target=0, opened_turn=world.turn,
                                            last_renewed_turn=world.turn)] if close else [])
    bridge.sync_regions(world)
    graph = build_merchant_route_graph(world)
    bridge._sim.set_merchant_route_graph(_quarantine_route_graph(world, graph))
    prepare_transaction_receipts(world, bridge)
    bridge._sim.tick(world.turn, build_signals(world))
    capture_transaction_receipts(world, bridge)
    arrivals = bridge._sim.get_pending_arrivals()  # cumulative here: no economy tick consumes them
    rows = list(zip(*[pylist(arrivals.column(c)) for c in ("source_region", "dest_region")])) \
        if arrivals.num_rows else []
    frame = list(world.transaction_receipts.frame)
    world.turn += 1
    cross_edges = sum(1 for x, y in zip(pylist(graph.column("from_region")), pylist(graph.column("to_region")))
                      if (x < len(world.regions) // 2) != (y < len(world.regions) // 2))
    return rows, frame, rules.receipt.merchant_edges_removed, cross_edges


def test_agent_merchants_stop_crossing_a_closed_border_and_in_transit_trips_unwind():
    _native()
    closed_world, closed_bridge, half = _border_fixture()
    open_world, open_bridge, _ = _border_fixture()
    close_at, ticks = 6, 12

    def crossing(row) -> bool:
        return (row[0] < half) != (row[1] < half)

    closed_cross, open_cross, operations = [], [], Counter()
    for t in range(ticks):
        rows, frame, removed, cross_edges = _border_tick(closed_world, closed_bridge, t >= close_at)
        open_rows, *_ = _border_tick(open_world, open_bridge, False)
        closed_cross.append(sum(map(crossing, rows)))
        open_cross.append(sum(map(crossing, open_rows)))
        if t >= close_at:
            # Every cross-border edge of the agent graph is cut, both directions.
            assert removed == cross_edges > 0
            for row in frame:
                operations[row.operation] += 1
                if row.operation in ("reserved", "departed"):
                    # No new journey across the closed border.
                    assert (row.origin_region < half) == (row.dest_region < half), row
        else:
            assert removed == 0
    assert closed_cross[:close_at] == open_cross[:close_at]          # identical until the closure
    assert closed_cross[close_at - 1] > 0, "the fixture must exercise border trade"
    # Cumulative cross-border deliveries stop from the closure tick (one tick
    # allowed for a merchant already across); the open border keeps adding.
    assert closed_cross[-1] <= closed_cross[close_at]
    assert open_cross[-1] > closed_cross[-1]
    # In-transit merchants whose next hop vanished replan or return their cargo.
    assert operations["returned"] + operations["replanned"] + operations["reservation_cancelled"] > 0


# --- the dated chain in a full hybrid run -------------------------------------------------

def _hybrid_run(mode: str, turns: int, monkeypatch):
    from chronicler.action_engine import ActionEngine
    from chronicler.agent_bridge import AgentBridge
    from chronicler.simulation import run_turn
    from chronicler.world_gen import generate_world

    world = generate_world(seed=7, num_regions=8, num_civs=4)
    world.campaigns_enabled = True
    world.agent_mode = "hybrid"
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    world.epidemics.quarantine_rules = qr.QuarantineRulesState(mode=mode)
    bridge = AgentBridge(world, mode="hybrid")
    observed: dict[int, list] = {}
    receipts: dict[int, qr.QuarantineReceipt] = {}
    def spy(w, routes, agent_bridge=None):
        before = len(cl._pending(w))
        _REAL_OBSERVE(w, routes, agent_bridge)
        # Deliveries of the previous agent tick, with controllers at observation.
        observed[w.turn] = [(s, d, q, w.regions[s].controller, w.regions[d].controller)
                            for s, d, ch, q in cl._pending(w)[before:] if ch == cl.TRADE]

    monkeypatch.setattr(cl, "observe_phase2", spy)
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed), lambda w, ev: "",
                 seed=world.seed + world.turn, agent_bridge=bridge)
        receipt = world.epidemics.quarantine_rules.receipt
        receipts[receipt.turn] = receipt.model_copy(deep=True)
    return world, observed, receipts


def _pairs(world, decided) -> set[tuple[str, str]]:
    names = [c.name for c in world.civilizations]
    return {tuple(sorted((names[a], names[b]))) for a, b in decided}


def _across(rows, pairs) -> list:
    return [r for r in rows if r[3] and r[4] and r[3] != r[4] and tuple(sorted((r[3], r[4]))) in pairs]


def test_hybrid_closure_blocks_deliveries_from_tick_t_and_the_ledger_from_t_plus_one(monkeypatch):
    _native()
    turns = 30
    closed, closed_obs, closed_receipts = _hybrid_run("closure", turns, monkeypatch)
    cost, cost_obs, cost_receipts = _hybrid_run("cost_only", turns, monkeypatch)
    first = min(t for t, r in closed_receipts.items() if r.decided)
    # Identical worlds until the first decision; the same decisions that turn.
    assert closed_receipts[first].decided == cost_receipts[first].decided
    assert closed_obs[first] == cost_obs[first]       # deliveries of tick first-1, made before the closure
    leaked = blocked = 0
    for t in range(first + 1, turns):
        receipt = closed_receipts[t]
        # The receipt's leak count is the observed deliveries (made in tick t-1) across every
        # pair closed during tick t-1, whether or not it is still closed at t.
        during = _pairs(closed, closed_receipts[t - 1].decided)
        assert receipt.leaked_deliveries == len(_across(closed_obs[t], during))
        leaked += receipt.leaked_deliveries
        blocked += len(_across(cost_obs[t], _pairs(cost, cost_receipts[t - 1].decided)))
    # Under cost_only the same kind of pairs keep exchanging deliveries; closed borders carry
    # only the few journeys that crossed before the closure or went round through a third polity.
    assert blocked > 0
    assert leaked < blocked / 2
    totals = closed.epidemics.quarantine_rules.totals
    assert totals.merchant_edges_removed > 0 and totals.route_turns_removed > 0


# --- exact hybrid resume inside an active closure -----------------------------------------

def _args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=7, turns=turns, civs=4, regions=8, output=str(folder / "chronicle.md"),
        state=str(folder / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, simulate_only=True, agents="hybrid", tuning_overrides={},
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _outputs(folder: Path, after: int = -1) -> dict[str, bytes]:
    from chronicler.bundle_codec import load_bundle
    out = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix == ".ckpt":
            continue
        stem = path.stem
        if "_turn_" in stem and int(stem.rsplit("_", 1)[1]) <= after:
            continue
        if path.name == "chronicle_bundle.json":
            data = load_bundle(path)
            data["metadata"].pop("generated_at", None)
            out[path.name] = json.dumps(data, sort_keys=True).encode()
        else:
            out[path.relative_to(folder).as_posix()] = path.read_bytes()
    return out


def test_exact_hybrid_resume_inside_a_closure_with_merchants_in_transit(tmp_path):
    _native()
    import chronicler.run_checkpoint as rc
    from chronicler.main import execute_run

    straight = tmp_path / "straight"
    execute_run(_args(straight, 16, quarantine_mode="closure", transaction_receipts=True,
                      checkpoint_every=2, checkpoint=str(straight / "c{turn}.ckpt")))
    chosen = []
    for k in range(2, 16, 2):
        loaded = rc.read_checkpoint(straight / f"c{k}.ckpt")
        rules = loaded.state.world.epidemics.quarantine_rules
        voyages = loaded.state.world.transaction_receipts.active
        if rules.closures and rules.receipt.merchant_edges_removed and voyages:
            chosen.append(k)
    assert chosen, "no checkpoint inside an active closure with merchants in transit"
    for k in chosen[:2]:
        resumed = tmp_path / f"resumed_{k}"
        execute_run(_args(resumed, 16), checkpoint_resume=rc.read_checkpoint(straight / f"c{k}.ckpt"))
        expected, got = _outputs(straight, after=k), _outputs(resumed)
        assert got.keys() == expected.keys()
        assert [name for name in got if got[name] != expected[name]] == []
    state = json.loads((straight / "state.json").read_text())["epidemics"]["quarantine_rules"]
    assert state["mode"] == "closure" and state["next_closure_id"] > 1
