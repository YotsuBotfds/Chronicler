"""Declared finite seed-42 controls against the real native economy.

The scenario is a constructed demonstration, not a population or accuracy
qualification. No reports, forecast truth, or shipments are injected.
"""
from __future__ import annotations

import random
import pytest

pytest.importorskip("chronicler_agents")

from chronicler.action_engine import ActionEngine
from chronicler.agent_bridge import AgentBridge
from chronicler.contact_ledger import set_contact_ledger_enabled
from chronicler.grain_reserves import set_grain_reserves_enabled, _ensure
from chronicler.grain_storage import enable_storage
from chronicler.grain_storage_state import StorageAsset
from chronicler.harvest_forecasts import set_harvest_forecasts_enabled, set_report_delay
from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
from chronicler.simulation import run_turn_result
from chronicler.world_gen import generate_world

pytestmark = pytest.mark.native


def _declared_world():
    """Seed42: two rulers, four linked regions, finite food/treasury/storage.

    Region0 has no yielding food slot; region1 has grain yield 1.8; region2
    has grain yield .6; region3 has grain yield 1.8. These are constructed
    initial economic conditions, not measured causal evidence or forecasts.
    """
    world = generate_world(seed=42, num_regions=4, num_civs=2)
    world.agent_mode = "hybrid"
    for ci, civ in enumerate(world.civilizations):
        civ.regions = [world.regions[2*ci].name, world.regions[2*ci+1].name]
        civ.capital_region = world.regions[2*ci].name
        civ.population = 120
        civ.treasury = 100
    for rid, region in enumerate(world.regions):
        region.controller = world.civilizations[rid // 2].name
        region.population = 60
        region.carrying_capacity = 100
        region.adjacencies = [r.name for j, r in enumerate(world.regions) if j != rid]
        region.stockpile.goods = {"grain": 0.0 if rid == 0 else 120.0}
        region.resource_types = [255, 255, 255] if rid == 0 else [0, 255, 255]
        region.resource_base_yields = [[0.0, 0.0, 0.0], [1.8, 0.0, 0.0],
                                       [0.6, 0.0, 0.0], [1.8, 0.0, 0.0]][rid]
    set_grain_reserves_enabled(world, True)
    reserves = _ensure(world)
    for rid, granary in enumerate(reserves.granaries):
        granary.owner = rid // 2
        granary.grain = 0.0
    storage = enable_storage(world)
    storage.assets = [StorageAsset(capacity=100.0, condition=1.0, owner=rid // 2) for rid in range(4)]
    set_contact_ledger_enabled(world, True)
    set_harvest_forecasts_enabled(world, True)
    return world


def _step(world, bridge):
    engine = ActionEngine(world)
    return run_turn_result(world, lambda civ, w: engine.select_action(civ, seed=w.seed),
        lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)


def _save(path, world, bridge, history=()):
    write_checkpoint(path, RunState(world=world, agent_bridge=bridge, memories={},
        history=list(history), chronicle_entries=[], era_reflections={}, pending_injections=[],
        start_turn=0, seed=world.seed, num_turns=14))


def _designed_diverse_surplus_world():
    """Additional development control, designed after the null fixture.

    Its source markets start with finite grain and salt and fertile, watered
    grain land. This explicitly probes the existing four-turn market-surplus
    gate; it is not a pre-registered efficacy or held-out comparison.
    """
    world = _declared_world()
    for rid in (1, 3):
        region = world.regions[rid]
        region.ecology.soil = 1.0
        region.ecology.water = 1.0
        region.stockpile.goods = {"grain": 150.0, "salt": 150.0}
    return world


def _timeline(world, bridge, n):
    from copy import deepcopy
    from chronicler.harvest_forecasts import snapshot_summary
    timeline = []
    for _ in range(n):
        turn = world.turn
        _step(world, bridge)
        forecast = deepcopy(snapshot_summary(world))
        flows = [x.model_dump() for x in world.grain_reserves.flows]
        storage = [x.model_dump() for x in world.grain_reserves.storage.receipts]
        timeline.append((turn, forecast, flows, storage,
                         dict(world._economy_result.food_sufficiency)))
    return timeline


def _arms(tmp_path, factory):
    world = factory()
    bridge = AgentBridge(world, mode="hybrid")
    path = tmp_path / "same-initial.ckpt"
    _save(path, world, bridge)
    state_rng = random.getstate()
    results = {}
    try:
        for policy, delay in (("normal", 0), ("normal", 3), ("normal", 12),
                              ("withhold", 0), ("shuffle", 0)):
            loaded = read_checkpoint(path)
            assert loaded.exact
            w, b = loaded.state.world, loaded.state.agent_bridge
            try:
                w.harvest_forecasts.policy = policy
                set_report_delay(w, delay)
                random.setstate(state_rng)
                results[(policy, delay)] = _timeline(w, b, 14)
            finally:
                b.close()
    finally:
        bridge.close()
    return results


def _warning_paid(timeline):
    return sum(x[1]["counters"]["paid_during_warning"] for x in timeline[-1:])


def test_declared_finite_world_keeps_null_purchase_controls(tmp_path):
    arms = _arms(tmp_path, _declared_world)
    assert all(_warning_paid(timeline) == 0 for timeline in arms.values())
    assert arms[("normal", 0)][-1][1]["counters"]["delivered"] > 0
    assert arms[("normal", 12)][-1][1]["counters"]["delivered"] == 0
    assert arms[("withhold", 0)][-1][1]["counters"]["withheld"] > 0


def test_designed_development_surplus_real_forecast_and_procurement(tmp_path):
    """Designed after the null run; demonstrates a path, not an efficacy estimate."""
    arms = _arms(tmp_path, _designed_diverse_surplus_world)
    timely, delay3 = arms[("normal", 0)], arms[("normal", 3)]
    late, withheld, shuffle = (arms[("normal", 12)], arms[("withhold", 0)],
                               arms[("shuffle", 0)])
    initial = timely[5][1]["reports"]
    local = next(r for r in initial if r["source_region"] == r["recipient_region"] == 0)
    assert local["issued_turn"] == 5 and local["delivered_turn"] is None
    assert local["expires_turn"] == 11
    for r in initial:
        assert all(t <= r["issued_turn"] for t, _ in r["estimator_metadata"]["observations"])
    assert next(r for r in timely[6][1]["reports"] if r["id"] == local["id"])["delivered_turn"] == 6
    assert next(r for r in delay3[9][1]["reports"] if r["id"] == local["id"])["delivered_turn"] == 9
    assert late[-1][1]["counters"]["delivered"] == 0
    assert any(r["id"] == local["id"] and r["status"] == "pending" for r in late[11][1]["reports"])
    assert any(r["id"] == local["id"] and r["delivered_turn"] is None for r in late[12][1]["outcomes"])
    assert withheld[-1][1]["counters"]["withheld"] > 0
    assert _warning_paid(timely) > 0
    assert _warning_paid(delay3) == _warning_paid(late) == _warning_paid(withheld) == 0
    # The shuffle changes reported values here; it need not change purchases.
    shuffled = next(r for r in shuffle[5][1]["reports"] if r["id"] == local["id"])
    assert shuffled["predicted_ratio"] != local["predicted_ratio"]
    assert _warning_paid(shuffle) == _warning_paid(timely)
    paid_rows = []
    cap_reduced = False
    for turn, snapshot, flows, storage, _ in timely:
        batch = snapshot["procurement_decisions"]
        assert (batch["source_turn"], batch["available_turn"]) == (turn, turn + 1)
        assert batch["schema_version"] == 1 and batch["mode"] == "hybrid"
        assert batch["goods_units"] == "model_food_goods"
        assert batch["currency_units"] == "model_treasury_coins"
        for row in batch["rows"]:
            decision = row["decision"]
            assert all(report["delivered_turn"] <= turn <= report["expires_turn"]
                       for report in decision["reports"])
            assert row["paid"] <= decision["opening_budget"]
            cap = storage[decision["region"]]
            assert decision["requested_target"] == pytest.approx(cap["target_requested"])
            assert decision["feasible_target"] == pytest.approx(cap["target_feasible"])
            cap_reduced |= cap["target_feasible"] < cap["target_requested"]
            if row["paid"] and decision["reports"]:
                assert row["purchased_grain"] > 0
                related = [f for f in flows if f["region"] == decision["region"] and f["kind"] == 0]
                assert sum(f["amount"] for f in related) == pytest.approx(row["purchased_grain"])
                assert sum(f["cost"] for f in related) == row["paid"]
                paid_rows.append(row)
    assert paid_rows and cap_reduced


def test_pending_report_checkpoint_exact_continuation(tmp_path):
    world = _designed_diverse_surplus_world()
    bridge = AgentBridge(world, mode="hybrid")
    try:
        history = _timeline(world, bridge, 6)
        pending = [r for r in world.harvest_forecasts.reports if r.delivered_turn is None]
        assert pending and all(r.issued_turn == 5 for r in pending)
        path = tmp_path / "reports-in-transit.ckpt"
        _save(path, world, bridge, history)
        loaded = read_checkpoint(path)
        assert loaded.exact and loaded.state.history == history
        restored, resumed = loaded.state.world, loaded.state.agent_bridge
        try:
            assert restored.harvest_forecasts == world.harvest_forecasts
            rng = random.getstate()
            expected = _timeline(world, bridge, 8)
            after = random.getstate()
            random.setstate(rng)
            actual = _timeline(restored, resumed, 8)
            assert actual == expected
            assert random.getstate() == after
            assert restored.model_dump_json() == world.model_dump_json()
            assert resumed._sim.checkpoint_state() == bridge._sim.checkpoint_state()
        finally:
            resumed.close()
    finally:
        bridge.close()


def test_development_source_eligibility_at_actual_procurement_boundary(monkeypatch):
    """Observe the kernel's existing KEEP gate, without changing its decision."""
    import math
    import chronicler.harvest_forecasts as forecast_module
    from chronicler.economy import FOOD_GOODS
    from chronicler.grain_reserves import GRAIN, KEEP_TURNS, _demand
    from chronicler.mutual_aid import read_stockpile_commitments

    world = _designed_diverse_surplus_world()
    assert world.regions[1].population == 60
    assert world.regions[1].stockpile.goods == {"grain": 150.0, "salt": 150.0}
    assert world.grain_reserves.storage.assets[1].capacity == 100.0
    bridge = AgentBridge(world, mode="hybrid")
    original = forecast_module.begin_forecast_decisions
    observed = []

    def capture(w, economy, *args, **kwargs):
        if w.turn == 7:
            native_before = bridge._sim.checkpoint_state()
            rng_before = random.getstate()
            region = w.regions[1]
            held = read_stockpile_commitments(w, bridge._sim).get(region.name, {})
            free = {g: max(0.0, region.stockpile.goods.get(g, 0.0) - held.get(g, 0.0))
                    for g in sorted(FOOD_GOODS)}
            demand = _demand(economy, region.name)
            eligible = max(0.0, min(free[GRAIN], math.fsum(free.values()) - KEEP_TURNS * demand))
            observed.append((eligible, free[GRAIN], demand, region.population))
            assert bridge._sim.checkpoint_state() == native_before
            assert random.getstate() == rng_before
        return original(w, economy, *args, **kwargs)

    monkeypatch.setattr(forecast_module, "begin_forecast_decisions", capture)
    try:
        timeline = _timeline(world, bridge, 8)
        eligible, grain, demand, population = observed[0]
        actual = [f for f in timeline[7][2] if f["kind"] == 0 and f["source"] == 1]
        assert population > 0 and demand > 0 and eligible > 0 and grain > 0
        assert actual and sum(f["sent"] for f in actual) <= eligible + 1e-6
    finally:
        bridge.close()
