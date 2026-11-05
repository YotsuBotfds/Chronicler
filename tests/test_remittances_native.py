"""RS4 diaspora ledger and remittances on the real compiled extension.

Template seed 7 (the default template world), the development seed: native
decisions, migrations, deaths, bond sweeps, trips and the pairwise
``remit_wealth`` operation are not mocked. Constructed steps are named where
they occur (direct native calls, a rebuilt pool, a two-arm fork from one
exact checkpoint).
"""
from __future__ import annotations

import random

import pyarrow as pa
import pytest

pytest.importorskip("chronicler_agents")

from chronicler import remittances as RM
from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint

pytestmark = pytest.mark.native

BASE = ["--seed", "7", "--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only"]


def _cli(tmp_path, *extra, turns=12):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    args = _build_parser().parse_args([*BASE, "--turns", str(turns), *extra,
                                       "--output", str(tmp_path / "chronicle.md"),
                                       "--state", str(tmp_path / "state.json")])
    execute_run(args)
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    bundle["metadata"].pop("generated_at")
    return bundle


def _records(bundle):
    return [s["livelihoods"]["remittances"] for s in bundle["history"]
            if (s.get("livelihoods") or {}).get("remittances")]


def _world(mode="send"):
    from chronicler.agent_bridge import AgentBridge
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.main import _build_parser
    from chronicler.world_gen import generate_world
    world = generate_world(seed=7)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    configure_livelihoods(world, _build_parser().parse_args(["--remittances", "--remittance-mode", mode]),
                          agent_mode="hybrid")
    return world, bridge


def _turn(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    engine = ActionEngine(world)
    run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed), lambda w, e: "",
                    seed=world.seed + world.turn, agent_bridge=bridge)
    return world.livelihoods.remittances


def _agents(sim):
    return {r["id"]: r for r in pa.record_batch(sim.get_snapshot()).to_pylist()}


def _state(world, bridge, turns=40):
    return RunState(world=world, agent_bridge=bridge, memories={}, history=[], chronicle_entries=[],
                    era_reflections={}, pending_injections=[], start_turn=0, seed=world.seed, num_turns=turns)


def test_remittances_follow_live_bonds_and_match_live_wealth(monkeypatch):
    """Each receipt's sender is a settled migrant at its ledger destination and
    its recipient a Marriage/Kin partner in the origin; every wealth change in
    the pool equals the receipts, and the turn balances."""
    seen = {"rows": 0, "returns": 0, "deaths": 0, "unmet": 0, "turns": 0}
    original = RM.after_agent_tick

    def checked(world, agent_bridge):
        sim = agent_bridge._sim
        before = _agents(sim)
        bonds = {}
        out = original(world, agent_bridge)
        after = _agents(sim)
        state = world.livelihoods.remittances
        seen["turns"] += 1
        net: dict[int, int] = {}
        entries = {e.id: e for e in state.entries}
        for r in state.receipts:
            assert r.status in ("applied", "limited")
            e = entries[r.sender]
            s, t = before[r.sender], before[r.recipient]
            assert s["age"] >= RM.ADULT_AGE and s["displacement_turn"] == 0
            assert world.turn - e.arrival_turn >= RM.SETTLED_TURNS
            assert s["region"] == e.destination == r.destination != e.origin == r.origin == t["region"]
            if r.sender not in bonds:
                bonds[r.sender] = sim.get_agent_relationships(r.sender)
            kind = {"marriage": 2, "kin": 5}[r.bond]
            assert any(b[0] == r.recipient and b[2] == kind and b[1] == r.sentiment >= RM.MIN_SENTIMENT
                       for b in bonds[r.sender])
            assert (r.amount, r.fee_requested) == RM.remittance_amount(r.wealth_milli)
            assert r.sent == r.fee + r.credited + r.refunded
            net[r.sender] = net.get(r.sender, 0) - (r.fee + r.credited)
            net[r.recipient] = net.get(r.recipient, 0) + r.credited
            seen["rows"] += 1
        for aid, change in net.items():
            assert after[aid]["wealth"] - before[aid]["wealth"] == pytest.approx(change / 1000, abs=2e-3)
        untouched = set(before) - set(net)
        assert all(after[a]["wealth"] == before[a]["wealth"] for a in untouched)
        t = state.totals
        assert t["debited_milli"] == t["credited_milli"] + t["fee_milli"]
        assert sum(x.inflow_milli for x in state.regions) == t["credited_milli"]
        assert sum(x.outflow_milli for x in state.regions) == t["debited_milli"]
        for c in state.closures:
            if c.reason == "death":
                assert c.id not in after
                seen["deaths"] += 1
            elif c.reason == "return":
                assert after[c.id]["region"] == c.origin if c.id in after else True
                seen["returns"] += 1
        for u in state.unmet:
            assert u.id in after and after[u.id]["region"] == u.destination != u.origin
            seen["unmet"] += 1
        # Every open entry names a living person away from its origin's region index.
        assert all(e.id in after and e.origin != e.destination for e in state.entries)
        return out

    monkeypatch.setattr(RM, "after_agent_tick", checked)
    world, bridge = _world()
    for _ in range(24):
        _turn(world, bridge)
    assert seen["turns"] == 24 and seen["rows"] > 0 and seen["returns"] > 0 and seen["deaths"] > 0
    assert seen["unmet"] > 0
    assert world.livelihoods.remittances.last_settled_turn == 23
    bridge.close()


def test_native_remit_refusals_absent_parties_and_one_key():
    """Direct native calls (constructed rows on a real pool)."""
    world, bridge = _world()
    sim = bridge._sim
    people = sorted(_agents(sim).values(), key=lambda r: r["id"])
    a, b = people[0]["id"], people[1]["id"]
    before = bytes(sim.checkpoint_state())
    for bad in ([(a, b, 100, 10), (a, b, 50, 0)], [(a, a, 100, 10)], [(a, b, 0, 10)], [(a, b, 100, -1)]):
        with pytest.raises(ValueError):
            sim.remit_wealth(world.turn, 0, bad)
    assert sim.trip_agent_ids() == sorted(sim.trip_agent_ids())
    assert bytes(sim.checkpoint_state()) == before
    wa, wb = people[0]["wealth"], people[1]["wealth"]
    rows = sim.remit_wealth(world.turn, 0, [(a, b, 400, 100), (b, 10**9, 100, 0)])
    sent = min(500, int(wa * 1000))
    assert rows[0][:3] == (a, b, sent) and rows[0][2] == rows[0][3] + rows[0][4] + rows[0][5]
    assert rows[1] == (b, 10**9, 0, 0, 0, 0, 2)                    # unknown recipient: nothing moves
    after = _agents(sim)
    assert after[a]["wealth"] == pytest.approx(wa - (rows[0][3] + rows[0][4]) / 1000, abs=2e-3)
    assert after[b]["wealth"] == pytest.approx(wb + rows[0][4] / 1000, abs=2e-3)
    with pytest.raises(ValueError, match="already applied"):
        sim.remit_wealth(world.turn, 0, [(b, a, 100, 0)])
    with pytest.raises(ValueError, match="already applied"):
        sim.transfer_wealth(world.turn, RM.PURPOSE_REMITTANCE, 0, [(a, 100)])
    assert sim.wealth_transfer_purposes()[RM.PURPOSE_REMITTANCE] == "remittance"
    bridge.close()


def test_a_rebuilt_pool_closes_the_ledger_dated():
    """A legacy-style rebuild: a second simulator for the same world."""
    from chronicler.agent_bridge import AgentBridge
    from chronicler.livelihoods import bind_native_pool
    world, bridge = _world()
    for _ in range(4):
        state = _turn(world, bridge)
    open_entries = len(state.entries)
    assert open_entries > 0
    other = AgentBridge(world, mode="hybrid")
    bind_native_pool(world, other)
    assert state.entries == [] and state.last_pool_reset.entries_closed == open_entries
    assert state.last_pool_reset.turn == world.turn and state.counters["pool_resets"] == 1
    bind_native_pool(world, other)                                 # bound now: no second reset
    assert state.counters["pool_resets"] == 1
    other.close()
    bridge.close()


def test_record_only_and_send_fork_from_one_exact_checkpoint(tmp_path):
    """The same ledger, eligibility and requested amounts; only send moves wealth."""
    world, bridge = _world("record_only")
    for _ in range(8):
        _turn(world, bridge)
    path = tmp_path / "fork.ckpt"
    write_checkpoint(path, _state(world, bridge))
    found = None
    for _ in range(8):
        control, sent = read_checkpoint(path).state, read_checkpoint(path).state
        sent.world.livelihoods.remittances.mode = "send"
        rng = random.getstate()
        c = _turn(control.world, control.agent_bridge)
        random.setstate(rng)
        s = _turn(sent.world, sent.agent_bridge)
        if c.receipts:
            found = (c, s, control, sent)
            break
        write_checkpoint(path, control)
        sent.agent_bridge.close()
    assert found is not None, "a remittance row was expected within eight turns"
    c, s, control, sent = found
    keys = {"sender", "recipient", "bond", "sentiment", "amount", "fee_requested", "wealth_milli"}
    assert [r.model_dump(include=keys) for r in c.receipts] == [r.model_dump(include=keys) for r in s.receipts]
    assert all(r.status == "not_sent" and r.sent == 0 for r in c.receipts)
    assert all(r.status in ("applied", "limited") for r in s.receipts)
    assert [e.model_dump(exclude={"sent_turns", "credited_milli"}) for e in c.entries] == \
        [e.model_dump(exclude={"sent_turns", "credited_milli"}) for e in s.entries]
    cw, sw = _agents(control.agent_bridge._sim), _agents(sent.agent_bridge._sim)
    r = s.receipts[0]
    assert sw[r.recipient]["wealth"] > cw[r.recipient]["wealth"]
    assert sw[r.sender]["wealth"] < cw[r.sender]["wealth"]
    control.agent_bridge.close()
    sent.agent_bridge.close()
    bridge.close()


def test_exact_resume_inside_a_live_ledger_settles_once(tmp_path, monkeypatch):
    import sys
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import main
    straight = tmp_path / "straight"
    _cli(straight, "--remittances", "--checkpoint-every", "1",
         "--checkpoint", str(tmp_path / "ck" / "turn_{turn:04d}.ckpt"), turns=16)
    ck = read_checkpoint(tmp_path / "ck" / "turn_0009.ckpt").state
    assert ck.world.livelihoods.remittances.entries                # a live ledger at the resume point
    ck.agent_bridge.close()
    resumed = tmp_path / "resumed"
    monkeypatch.setattr(sys, "argv", ["chronicler", "--resume", str(tmp_path / "ck" / "turn_0009.ckpt"),
                                      "--output", str(resumed / "chronicle.md"),
                                      "--state", str(resumed / "state.json")])
    main()
    a = load_bundle(straight / "chronicle_bundle.json")
    b = load_bundle(resumed / "chronicle_bundle.json")
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    late = [r for r in _records(a) if r["source_turn"] >= 9 and r["receipts"]]
    assert late, "remittances were expected after the resume turn"


def test_feature_off_identity_and_a_control_that_moves_nothing(tmp_path):
    off = _cli(tmp_path / "off", turns=16)
    disabled = _cli(tmp_path / "disabled", "--no-remittances", turns=16)
    assert off == disabled and all("livelihoods" not in s for s in off["history"])
    control = _cli(tmp_path / "control", "--remittances", "--remittance-mode", "record_only", turns=16)
    assert any(r["receipts"] for r in _records(control))
    for a, b in zip(off["history"], control["history"], strict=True):
        b = dict(b)
        record = b.pop("livelihoods")["remittances"]
        assert record["totals"] is None or record["totals"]["debited_milli"] == 0
        assert a == b


def test_remittances_settle_after_relocation_fares_and_balance_every_turn(tmp_path, monkeypatch):
    """With L7 fares on, the fare debits come first (the remittance reads the
    post-fare pool) and both books balance each turn."""
    from chronicler import relocation_costs as R
    order = []
    fares, remit = R.after_agent_tick, RM.after_agent_tick
    monkeypatch.setattr(R, "after_agent_tick", lambda w, b: (order.append(("fare", w.turn)), fares(w, b))[1])
    monkeypatch.setattr(RM, "after_agent_tick", lambda w, b: (order.append(("remit", w.turn)), remit(w, b))[1])
    bundle = _cli(tmp_path, "--relocation-costs", "--remittances", turns=16)
    assert order == [(kind, t) for t in range(16) for kind in ("fare", "remit")]
    records = _records(bundle)
    assert len(records) == 16 and any(r["receipts"] for r in records)
    for r in records:
        t = r["totals"]
        assert t["debited_milli"] == t["credited_milli"] + t["fee_milli"]
        assert t["sent_milli"] == t["debited_milli"] + t["refunded_milli"]
        assert sum(x["inflow_milli"] for x in r["regions"]) == t["credited_milli"]
    fare = bundle["history"][-1]["livelihoods"]["relocation_costs"]["counters"]
    assert fare.get("fare_debited_milli", 0) > 0
