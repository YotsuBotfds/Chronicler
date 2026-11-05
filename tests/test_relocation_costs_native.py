"""L7 relocation costs on the real compiled extension.

Template seed 1 (8 regions, 4 civilizations), the development seed: native
decisions, household consolidation, the fare gate, applied moves, the wealth
transfer and the treasury are not mocked. Constructed steps are named where
they occur (a declared controller transition, a two-arm fork from one exact
checkpoint).
"""
from __future__ import annotations

import random

import pyarrow as pa
import pytest

pytest.importorskip("chronicler_agents")

from chronicler import relocation_costs as R
from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint

pytestmark = pytest.mark.native

BASE = ["--seed", "1", "--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only"]


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
    return [s["livelihoods"]["relocation_costs"] for s in bundle["history"]
            if (s.get("livelihoods") or {}).get("relocation_costs")]


def _world(mode):
    from chronicler.agent_bridge import AgentBridge
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.main import _build_parser
    from chronicler.world_gen import generate_world
    world = generate_world(seed=1, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    configure_livelihoods(world, _build_parser().parse_args(["--relocation-costs", "--relocation-mode", mode]),
                          agent_mode="hybrid")
    return world, bridge


def _turn(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    engine = ActionEngine(world)
    run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed), lambda w, e: "",
                    seed=world.seed + world.turn, agent_bridge=bridge)
    return world.livelihoods.relocation_costs


def _agents(sim):
    return {r["id"]: r for r in pa.record_batch(sim.get_snapshot()).to_pylist()}


def _state(world, bridge, turns=40):
    return RunState(world=world, agent_bridge=bridge, memories={}, history=[], chronicle_entries=[],
                    era_reflections={}, pending_injections=[], start_turn=0, seed=world.seed, num_turns=turns)


def test_fares_are_paid_only_for_applied_moves_and_match_live_wealth(monkeypatch):
    """Every debit equals the drop in the live adult's wealth; blocked households
    stay home and pay nothing; children count in the fare and are never debited."""
    seen = {"debits": 0, "blocked": 0, "children": 0, "turns": 0}
    original = R.after_agent_tick

    def checked(world, agent_bridge):
        sim = agent_bridge._sim
        before = _agents(sim)
        out = original(world, agent_bridge)
        after = _agents(sim)
        state = world.livelihoods.relocation_costs
        seen["turns"] += 1
        for h in state.households:
            if h.reason == "short":
                assert not h.applied and h.debits == [] and h.paid == 0
                assert all(after[m]["region"] == h.from_region for m in h.members if m in after)
                seen["blocked"] += 1
                continue
            if not h.applied:
                continue
            assert all(after[m]["region"] == h.to_region for m in h.members if m in after)
            if h.reason in ("passed", "assisted"):
                assert h.fare == R.FARE_MILLI * len(h.members)
                assert h.paid + h.residual == h.movers_share
                debited = {d[0] for d in h.debits}
                assert debited <= set(h.adults)
                for aid, requested, applied, residual, status in h.debits:
                    assert requested == applied + residual
                    if status == "absent":
                        assert aid not in after and applied == 0
                    else:
                        drop = before[aid]["wealth"] - after[aid]["wealth"]
                        assert drop == pytest.approx(applied / 1000, abs=2e-3)
                        seen["debits"] += 1
                if h.children:
                    seen["children"] += 1
                    assert not debited & (set(h.members) - set(h.adults))
        for row in state.regions:
            assert row.alive_after - row.alive_before == row.arrivals - row.departures
        return out

    monkeypatch.setattr(R, "after_agent_tick", checked)
    world, bridge = _world("paid")
    for _ in range(14):
        _turn(world, bridge)
    assert seen["turns"] == 14 and seen["debits"] > 0 and seen["blocked"] > 0 and seen["children"] > 0
    assert world.livelihoods.relocation_costs.last_settled_turn == 13
    bridge.close()


def test_identical_short_households_move_only_with_funded_assistance(tmp_path):
    """Fork one exact checkpoint into liquidity_only and assisted: the same
    proposed households meet the same gate; only assistance moves short ones."""
    from chronicler.relocation_costs import set_relocation_costs_enabled
    world, bridge = _world("liquidity_only")
    for _ in range(8):
        _turn(world, bridge)
    path = tmp_path / "fork.ckpt"
    write_checkpoint(path, _state(world, bridge))
    found = None
    for _ in range(6):
        alone, helped = read_checkpoint(path).state, read_checkpoint(path).state
        helped.world.livelihoods.relocation_costs.mode = "assisted"
        assert alone.agent_bridge._sim.checkpoint_state() == helped.agent_bridge._sim.checkpoint_state()
        rng = random.getstate()
        a = _turn(alone.world, alone.agent_bridge)
        random.setstate(rng)
        h = _turn(helped.world, helped.agent_bridge)
        by_alone = {x.lead: x for x in a.households}
        assisted = [x for x in h.households if x.reason == "assisted" and x.applied]
        if assisted:
            found = (assisted[0], by_alone[assisted[0].lead], alone, helped)
            break
        # Advance the base checkpoint one ordinary liquidity_only turn and retry.
        write_checkpoint(path, alone)
        helped.agent_bridge.close()
    assert found is not None, "an assisted household was expected within six turns"
    moved, stayed, alone, helped = found
    assert (stayed.reason, stayed.applied) == ("short", False)
    assert stayed.members == moved.members and stayed.liquid == moved.liquid < moved.fare
    assert moved.assistance > 0 and moved.liquid + moved.assistance >= moved.fare
    assert moved.paid + moved.residual == moved.fare - moved.assistance
    la, ha = _agents(alone.agent_bridge._sim), _agents(helped.agent_bridge._sim)
    assert all(la[m]["region"] == stayed.from_region for m in stayed.members if m in la)
    assert all(ha[m]["region"] == moved.to_region for m in moved.members if m in ha)
    charge = next(c for c in helped.world.livelihoods.relocation_costs.assistance if c.civ == moved.payer)
    assert charge.status == "charged" and charge.charged_coins * 1000 >= charge.granted >= moved.assistance
    alone.agent_bridge.close()
    helped.agent_bridge.close()
    bridge.close()


def test_conquest_between_plan_and_settlement_refuses_the_assistance(monkeypatch):
    """A declared controller transition in Phase 10, before settlement."""
    original = R.phase10_before_reserves
    seen = {}

    def conquer(world, acc, economy_result, agent_bridge):
        pending = world.livelihoods.relocation_costs._assist
        if pending and pending[1] and "region" not in seen:
            g = pending[1][0]
            region = world.regions[g.to_region]
            old = world.civilizations[g.payer]
            new = next(c for i, c in enumerate(world.civilizations) if i != g.payer)
            old.regions = [r for r in old.regions if r != region.name]
            new.regions.append(region.name)
            region.controller = new.name
            seen.update(region=g.to_region, payer=g.payer, treasury=old.treasury, lead=g.lead)
        return original(world, acc, economy_result, agent_bridge)

    monkeypatch.setattr(R, "phase10_before_reserves", conquer)
    world, bridge = _world("assisted")
    for _ in range(20):
        state = _turn(world, bridge)
        if seen:
            break
    assert seen, "an assisted move was expected within 20 turns"
    h = next(x for x in state.households if x.lead == seen["lead"])
    assert h.applied and h.assistance_status == "controller_changed"
    refused = [c for c in state.assistance if c.status == "controller_changed"]
    assert refused and refused[0].civ == seen["payer"] and refused[0].charged_coins == 0
    bridge.close()


def test_death_after_the_move_is_a_recorded_residual(tmp_path):
    records = _records(_cli(tmp_path, "--relocation-costs", turns=12))
    absent = [(r["source_turn"], h["lead"], d) for r in records for h in r["households"] or []
              for d in h["debits"] if d[4] == "absent"]
    assert absent, "seed 1 has a mover who died later in the turn of the move"
    for _, _, (aid, requested, applied, residual, status) in absent:
        assert applied == 0 and residual == requested > 0
    last = records[-1]["counters"]
    assert last["fare_residual_milli"] > 0 and last["fare_debited_milli"] + last["fare_residual_milli"] == last["fare_due_milli"]


def test_receiving_pressure_shows_congestion_and_relief(tmp_path):
    records = _records(_cli(tmp_path, "--relocation-costs", turns=20))
    worse = relief = False
    for r in records:
        for row in r["regions"] or []:
            assert row["alive_after"] - row["alive_before"] == row["arrivals"] - row["departures"]
            if row["arrivals"] and row["pressure_after"] > row["pressure_before"] and row["pressure_after"] > 1:
                worse = True
            if row["departures"] and row["pressure_before"] > 1 and row["pressure_after"] < row["pressure_before"]:
                relief = True
    assert worse and relief


def test_exact_resume_continues_settlement_once(tmp_path, monkeypatch):
    import sys
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import main
    straight = tmp_path / "straight"
    _cli(straight, "--relocation-costs", "--relocation-mode", "assisted", "--checkpoint-every", "1",
         "--checkpoint", str(tmp_path / "ck" / "turn_{turn:04d}.ckpt"), turns=10)
    resumed = tmp_path / "resumed"
    monkeypatch.setattr(sys, "argv", ["chronicler", "--resume", str(tmp_path / "ck" / "turn_0005.ckpt"),
                                      "--output", str(resumed / "chronicle.md"),
                                      "--state", str(resumed / "state.json")])
    main()
    a = load_bundle(straight / "chronicle_bundle.json")
    b = load_bundle(resumed / "chronicle_bundle.json")
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert _records(a)[-1]["counters"]["groups_applied"] > 0


def test_feature_off_and_zero_fare_identity(tmp_path, monkeypatch):
    off = _cli(tmp_path / "off", turns=20)
    disabled = _cli(tmp_path / "disabled", "--no-relocation-costs", turns=20)
    assert off == disabled and all("livelihoods" not in s for s in off["history"])
    monkeypatch.setattr(R, "FARE_MILLI", 0)
    free = _cli(tmp_path / "free", "--relocation-costs", "--relocation-mode", "liquidity_only", turns=20)
    for a, b in zip(off["history"], free["history"], strict=True):
        b = dict(b)
        record = b.pop("livelihoods")["relocation_costs"]
        assert record["counters"].get("groups_short", 0) == 0
        assert a == b


def test_native_policy_refusals():
    from chronicler.agent_bridge import AgentBridge, build_signals
    from chronicler.world_gen import generate_world
    world = generate_world(seed=1, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    sim = bridge._sim
    n = len(world.regions)
    before = bytes(sim.checkpoint_state())
    for bad in ((-1, 0, [-1] * n, [], []), (1000, 0, [-1] * (n - 1), [], []), (1000, 0, [0] * n, [], []),
                (1000, 0, [-1] * n, [-5], []), (1000, 0, [-1] * n, [], [3, 3])):
        with pytest.raises(ValueError):
            sim.set_relocation_policy(world.turn, *bad)
    sim.set_relocation_policy(world.turn, 1000, 0, [-1] * n, [0] * 4, [])
    assert bytes(sim.checkpoint_state()) == before            # the policy is transient
    with pytest.raises(ValueError):
        sim.set_relocation_policy(world.turn, 1000, 0, [-1] * n, [0] * 4, [])
    with pytest.raises(ValueError, match="installed for this tick"):
        sim.tick(world.turn + 1, build_signals(world))
    with pytest.raises(ValueError, match="cannot both run"):
        sim.tick(world.turn, build_signals(world), liquid_requirement=0.5)
    assert sim.cancel_relocation_policy() and not sim.cancel_relocation_policy()
    assert sim.take_relocation_receipt(world.turn) is None
    assert sim.wealth_transfer_purposes()[:2] == ["workshop_wage", "relocation_fare"]
    bridge.close()
