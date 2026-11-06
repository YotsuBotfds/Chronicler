"""L6b household food retail on the real compiled extension.

Gated, not skipped: the PL4 native methods (``household_retail.NATIVE_METHODS``)
land in a separate lane. Until the installed extension has all of them, this
module collects only the contract check below, which fails on a partial
build (some methods without the others) and, with
``CHRONICLER_REQUIRE_RETAIL_NATIVE=1``, on their absence. Once they exist the
integration tests are collected and run; no skip is registered for them in
``scripts/testing/native_shards_manifest.json``.

Template seed 7 (the default template world), the development seed. Native
decisions, deaths, trips, prices and the provisioning step are not mocked;
constructed steps are named where they occur (direct native credits before a
forked tick, raised granary targets).
"""
from __future__ import annotations

import os
import random

import pyarrow as pa
import pytest

pytest.importorskip("chronicler_agents")

from chronicler import household_retail as HR
from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint

pytestmark = pytest.mark.native

BASE = ["--seed", "7", "--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only"]
RETAIL = ["--food-allocation", "--household-retail"]


def _native_class():
    from chronicler_agents import AgentSimulator
    return AgentSimulator


_PRESENT = {name: callable(getattr(_native_class(), name, None)) for name in HR.NATIVE_METHODS}
READY = all(_PRESENT.values())


def test_retail_native_methods_are_all_present_or_all_absent():
    """The gate itself: a partial extension is refused, never silently gated."""
    present = sorted(name for name, ok in _PRESENT.items() if ok)
    assert not present or READY, f"partial household retail extension: only {present}"
    purposes = list(_native_class().wealth_transfer_purposes())
    if READY:
        assert purposes[HR.PURPOSE_FOOD_PURCHASE] == "food_purchase"
        assert purposes[HR.PURPOSE_FOOD_PROCUREMENT] == "food_procurement"
    else:
        assert "food_purchase" not in purposes and "food_procurement" not in purposes
    if os.environ.get("CHRONICLER_REQUIRE_RETAIL_NATIVE") == "1":
        assert READY, "CHRONICLER_REQUIRE_RETAIL_NATIVE=1: the retail native methods are missing"


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
    return [s["livelihoods"]["household_retail"] for s in bundle["history"]
            if (s.get("livelihoods") or {}).get("household_retail")]


def _world(*flags, grain_reserves=False):
    from chronicler.agent_bridge import AgentBridge
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.main import _build_parser
    from chronicler.world_gen import generate_world
    world = generate_world(seed=7)
    world.agent_mode = "hybrid"
    if grain_reserves:
        from chronicler.grain_reserves import set_grain_reserves_enabled
        set_grain_reserves_enabled(world, True)
    bridge = AgentBridge(world, mode="hybrid")
    configure_livelihoods(world, _build_parser().parse_args([*RETAIL, *flags]), agent_mode="hybrid")
    return world, bridge


def _turn(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    engine = ActionEngine(world)
    run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed), lambda w, e: "",
                    seed=world.seed + world.turn, agent_bridge=bridge)
    return world.livelihoods.household_retail


def _agents(sim):
    return {r["id"]: r for r in pa.record_batch(sim.get_snapshot()).to_pylist()}


def _state(world, bridge, turns=40):
    return RunState(world=world, agent_bridge=bridge, memories={}, history=[], chronicle_entries=[],
                    era_reflections={}, pending_injections=[], start_turn=0, seed=world.seed, num_turns=turns)


def _capture(monkeypatch):
    """Record every settled frame with the pre-tick pool it was installed on."""
    seen = []
    before = HR.before_agent_tick
    settle = HR._settle_frame

    def spy_before(world, agent_bridge, economy_result):
        seen.append({"turn": world.turn, "pre": _agents(agent_bridge._sim)})
        before(world, agent_bridge, economy_result)

    def spy_settle(world, state, t, installed, frame, receipt):
        seen[-1].update(installed=installed, frame=frame, receipt=receipt)
        settle(world, state, t, installed, frame, receipt)

    monkeypatch.setattr(HR, "before_agent_tick", spy_before)
    monkeypatch.setattr(HR, "_settle_frame", spy_settle)
    return seen


if READY:

    def test_install_validation_refuses_before_mutation_and_cancels_once():
        world, bridge = _world()
        sim = bridge._sim
        _turn(world, bridge)
        before = bytes(sim.checkpoint_state())
        for regions, claims in (([(99, 300, 1.0)], []), ([(2, -1, 1.0)], []), ([(2, 300, -1.0)], []),
                                ([(2, 300, 1.0), (2, 300, 1.0)], []), ([(2, 300, 1.0)], [(1, 2, -5)])):
            with pytest.raises(ValueError):
                sim.set_household_retail(world.turn, 0, regions, claims)
        assert bytes(sim.checkpoint_state()) == before
        sim.set_household_retail(world.turn, 0, [(2, 300, 1.0)], [])
        with pytest.raises(ValueError):
            sim.set_household_retail(world.turn, 0, [(2, 300, 1.0)], [])     # a pending install
        assert sim.cancel_household_retail() is True and sim.cancel_household_retail() is False
        sim.install_retail_income(world.turn, [2])
        assert sim.cancel_retail_income() is True and sim.cancel_retail_income() is False
        assert sim.take_household_retail_frame() is None and sim.take_retail_income_receipt() is None
        bridge.close()

    def test_title_sale_payment_ration_and_income_move_once_and_close(monkeypatch):
        """A pilot run: every frame is taken once, closes in Python, and its
        income receipt names only the pilot's pre-tick farmers."""
        monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
        seen = _capture(monkeypatch)
        world, bridge = _world()
        sim = bridge._sim
        sold = paid = replaced = 0
        for _ in range(12):
            state = _turn(world, bridge)
            assert sim.take_household_retail_frame() is None and sim.take_retail_income_receipt() is None
            for reg in state.regions:
                assert sum(reg.claims.values()) == sum(reg.goods)
            rec = seen[-1]
            if "frame" not in rec:
                continue
            pilots = set(rec["installed"].regions)
            farmers = {aid for aid, p in rec["pre"].items() if p["occupation"] == 0 and p["region"] in pilots}
            turn, rows = rec["receipt"]
            assert turn == rec["turn"] and {aid for aid, _ in rows} <= farmers
            assert all(v >= 0 for _, v in rows)
            replaced += len(rows)
            for aid, region, _hh, ration, fair, status in rec["frame"][5]:
                assert region in pilots and 0.0 <= ration <= 1.0 + 1e-6 and status in (0, 1, 2)
            sold += sum(r.provisioning["sold_milli"] for r in state.frame if r.provisioning)
            paid += state.money.get("paid_milli", 0)
        assert sold > 0 and paid > 0 and replaced > 0
        assert world.livelihoods.household_retail.counters["turns_settled"] >= 10
        bridge.close()

    def _priced_out_fork(tmp_path, monkeypatch, credit):
        """Fork one exact checkpoint into a control and an arm whose cash-limited
        buyer is credited ``credit(sim, turn, buyer)`` before the tick."""
        seen = _capture(monkeypatch)
        world, bridge = _world()
        for _ in range(4):
            _turn(world, bridge)
        path = tmp_path / "fork.ckpt"
        write_checkpoint(path, _state(world, bridge))
        bridge.close()
        for _ in range(12):
            control, arm = read_checkpoint(path).state, read_checkpoint(path).state
            rng = random.getstate()
            _turn(control.world, control.agent_bridge)
            rec = seen[-1]
            buyers = sorted(aid for aid, _r, _h, _ration, _f, status in rec.get("frame", (None,) * 6)[5] or ()
                            if status == 1)
            if buyers:
                random.setstate(rng)
                credit(arm.agent_bridge._sim, arm.world.turn, buyers[0])
                _turn(arm.world, arm.agent_bridge)
                money = {row[0]: row for row in seen[-1]["frame"][4]}
                control_money = {row[0]: row for row in rec["frame"][4]}
                got = money.get(buyers[0], (0, 0, 0, 0))[1]
                had = control_money.get(buyers[0], (0, 0, 0, 0))[1]
                control.agent_bridge.close()
                arm.agent_bridge.close()
                return had, got
            write_checkpoint(path, control)
            control.agent_bridge.close()
            arm.agent_bridge.close()
        pytest.fail("a cash-limited buyer was expected within twelve turns")

    def test_a_workshop_wage_raises_a_cash_limited_buyers_purchase(tmp_path, monkeypatch):
        """Constructed: the L6a wage seam (purpose ``workshop_wage``) credits a
        priced-out buyer before the forked tick; that buyer then pays more."""
        def wage(sim, turn, buyer):
            rows = sim.transfer_wealth(turn, 0, 900, [(buyer, 5000)])
            assert rows[0][2] > 0
        had, got = _priced_out_fork(tmp_path, monkeypatch, wage)
        assert got > had

    def test_a_remittance_raises_the_recipients_purchase(tmp_path, monkeypatch):
        """Constructed: an RS4 remittance (``remit_wealth``) from the wealthiest
        living person reaches a priced-out buyer before the forked tick."""
        def remit(sim, turn, buyer):
            people = _agents(sim)
            sender = max((aid for aid in people if aid != buyer), key=lambda a: (people[a]["wealth"], -a))
            rows = sim.remit_wealth(turn, 900, [(sender, buyer, 4000, 0)])
            assert rows[0][4] > 0
        had, got = _priced_out_fork(tmp_path, monkeypatch, remit)
        assert got > had

    def test_granary_procurement_pays_owners_by_id(monkeypatch):
        """Constructed: every granary wants four turns of demand, so pilot owners'
        surplus is procured; their wealth rises by exactly the credits applied."""
        import chronicler.grain_reserves as G
        monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
        monkeypatch.setattr(G, "target_grain", lambda granary, demand: 4.0 * demand)
        credits = []
        original = HR._credit_procurement

        def spy(world, state, t, agent_bridge):
            before = _agents(agent_bridge._sim)
            summary = original(world, state, t, agent_bridge)
            after = _agents(agent_bridge._sim)
            credits.append((summary, before, after))
            return summary

        monkeypatch.setattr(HR, "_credit_procurement", spy)
        world, bridge = _world(grain_reserves=True)
        for _ in range(16):
            _turn(world, bridge)
        paid = [c for c in credits if c[0]["credited_milli"] > 0]
        assert paid, "owners' grain was expected to be procured within sixteen turns"
        for summary, before, after in paid:
            gained = sum(after[a]["wealth"] - before[a]["wealth"] for a in after if a in before)
            assert gained == pytest.approx(summary["credited_milli"] / 1000, rel=2e-5, abs=2e-3)
        assert world.livelihoods.household_retail.last_procured_turn is not None
        bridge.close()

    def test_exact_resume_mid_pilot_is_byte_identical(tmp_path, monkeypatch):
        import sys
        from chronicler.bundle_codec import load_bundle
        from chronicler.main import main
        straight = tmp_path / "straight"
        _cli(straight, *RETAIL, "--grain-reserves", "--checkpoint-every", "1",
             "--checkpoint", str(tmp_path / "ck" / "turn_{turn:04d}.ckpt"), turns=14)
        ck = read_checkpoint(tmp_path / "ck" / "turn_0007.ckpt").state
        assert any(r.claims for r in ck.world.livelihoods.household_retail.regions)   # live claims
        ck.agent_bridge.close()
        resumed = tmp_path / "resumed"
        monkeypatch.setattr(sys, "argv", ["chronicler", "--resume", str(tmp_path / "ck" / "turn_0007.ckpt"),
                                          "--output", str(resumed / "chronicle.md"),
                                          "--state", str(resumed / "state.json")])
        main()
        a = load_bundle(straight / "chronicle_bundle.json")
        b = load_bundle(resumed / "chronicle_bundle.json")
        assert a["history"] == b["history"] and a["world_state"] == b["world_state"]

    def test_feature_off_identity(tmp_path):
        off = _cli(tmp_path / "off", "--food-allocation", turns=12)
        disabled = _cli(tmp_path / "disabled", "--food-allocation", "--no-household-retail", turns=12)
        assert off == disabled
        assert all("household_retail" not in (s.get("livelihoods") or {}) for s in off["history"])

    def test_record_only_trajectory_equals_l2_alone(tmp_path):
        alone = _cli(tmp_path / "alone", "--food-allocation", turns=12)
        shadow = _cli(tmp_path / "shadow", *RETAIL, "--household-retail-mode", "record_only", turns=12)
        records = _records(shadow)
        assert records and any(f["would_be"] for r in records for f in r["regions"] or ())
        for a, b in zip(alone["history"], shadow["history"], strict=True):
            b = dict(b, livelihoods=dict(b["livelihoods"]))
            b["livelihoods"].pop("household_retail")
            assert a == b
        world = dict(shadow["world_state"], livelihoods=dict(shadow["world_state"]["livelihoods"]))
        world["livelihoods"].pop("household_retail")
        assert world == alone["world_state"]

    @pytest.mark.parametrize("mode", ["retail", "no_relief", "free_exchange"])
    @pytest.mark.parametrize("boundary", ["market", "paid_work", "all"])
    def test_every_mode_and_boundary_balances_under_the_resource_checks(tmp_path, monkeypatch, mode, boundary):
        monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
        bundle = _cli(tmp_path, *RETAIL, "--grain-reserves", "--public-grain-shipments", "--remittances",
                      "--household-retail-mode", mode, "--household-retail-boundary", boundary, turns=10)
        records = _records(bundle)
        assert records and all(r["mode"] == mode and r["boundary"] == boundary for r in records)
        for r in records:
            for f in r["regions"] or ():
                signed = sum(HR.FLOW_SIGNS[k] * v for k, v in f["flows"].items())
                assert f["open_milli"] + signed == f["close_milli"] == sum(f["goods_close"])
            if mode == "free_exchange" and r["money"]:
                assert r["money"].get("paid_milli", 0) == 0

    def test_inheritance_agrees_with_the_native_estate_rule_for_spouses(monkeypatch):
        """Lead decision 6: the spouse case must agree with ``household.rs``
        (spouse first when alive after the tick). A child case may differ
        (Python: living children in the claim's region, equally; native:
        dependants first, then all children, anywhere): counted, not refused,
        and documented in docs/integration/household-retail.md."""
        rows = []
        original = HR._settle_deaths

        def spy(world, state, t, sim):
            spouses = dict(t.spouses or {})
            original(world, state, t, sim)
            rows.append((world.turn, spouses, _agents(sim)))

        monkeypatch.setattr(HR, "_settle_deaths", spy)
        world, bridge = _world()
        spouse_cases = child_cases = child_differs = 0
        for _ in range(24):
            state = _turn(world, bridge)
            turn, spouses, alive = rows[-1]
            dead = sorted({r.owner for r in state.log if r.turn == turn and r.kind in ("inherited", "escheat")})
            for owner in dead:
                heirs = sorted({r.other for r in state.log
                                if r.turn == turn and r.owner == owner and r.kind == "inherited"})
                spouse = spouses.get(owner)
                if spouse is not None and spouse in alive:
                    assert heirs == [spouse]
                    spouse_cases += 1
                    continue
                children = sorted(a for a, p in alive.items() if owner in (p["parent_id_0"], p["parent_id_1"]))
                dependants = [a for a in children if alive[a]["age"] < HR.ADULT_AGE]
                child_cases += 1
                child_differs += heirs != (dependants or children)
        assert child_differs <= child_cases
        assert world.livelihoods.household_retail.counters.get("deaths", 0) >= spouse_cases
        bridge.close()
