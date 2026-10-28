"""Causal controls for delayed, paid harvest preparedness (no native pool)."""
from __future__ import annotations

import random
import pytest

import chronicler.harvest_forecasts as H
import chronicler.grain_reserves as G
from chronicler.contact_ledger import ContactLedgerState, set_contact_ledger_enabled
from chronicler.harvest_forecasts_state import HarvestReport
from chronicler.models import WorldState
from chronicler.resources import SEASON_MOD, get_season_id
from chronicler.world_gen import generate_world

from test_grain_reserves import _economy, _granary

AMBER, FROST = 5, 0


def _world(policy="normal"):
    world = generate_world(seed=42)
    world.agent_mode = "demographics-only"
    G.set_grain_reserves_enabled(world, True)
    set_contact_ledger_enabled(world, True)
    H.set_harvest_forecasts_enabled(world, True, policy=policy)
    for civ in world.civilizations:
        civ.treasury = 200
    for region in world.regions:
        region.stockpile.goods = {}
    return world


def _measure(world, ratios=None):
    factor = SEASON_MOD[0][get_season_id(world.turn)]
    harvest = {rid: 0.5 * r.population * factor * (ratios or {}).get(rid, 0.5)
               for rid, r in enumerate(world.regions)}
    return _economy(world, harvest=harvest)


def _forecast_tick(world, ratios=None):
    events = H.tick_harvest_forecasts(world, _measure(world, ratios))
    world.events_timeline.extend(events)
    return events


def _publish(world, ratios=None):
    for turn in range(6):
        world.turn = turn
        _forecast_tick(world, ratios)
    return {r.recipient_region: r for r in world.harvest_forecasts.reports}


def _warning(world, *, probability=0.9):
    world.turn = 6
    owner = world.civ_index_map[world.regions[AMBER].controller]
    report = HarvestReport(
        id="harvest:0:5:5", source_region=AMBER, source_region_name="Amber Valley",
        recipient_region=AMBER, recipient_region_name="Amber Valley", owner=owner,
        owner_name=world.civilizations[owner].name, issued_turn=5, delivery_turn=6,
        expires_turn=11, target_start=9, target_end=11, probability=probability,
        confidence=1.0, predicted_ratio=0.2,
    )
    world.harvest_forecasts.reports = [report]
    return report


def test_flag_off_is_inert_and_never_draws(monkeypatch):
    world = generate_world(seed=42)
    before, random_before = world.model_dump_json(), random.getstate()

    def forbidden(*args):
        raise AssertionError("disabled forecast drew noise")

    monkeypatch.setattr(H, "_noise", forbidden)
    assert H.tick_harvest_forecasts(world, _economy(world)) == []
    assert H.snapshot_summary(world) == {}
    assert world.model_dump_json() == before and random.getstate() == random_before
    assert "harvest_forecasts" not in before


@pytest.mark.parametrize("missing", ["grain", "agents", "contact"])
def test_explicit_invalid_configuration_rejected_but_saved_state_is_dormant(missing):
    world = _world()
    if missing == "grain":
        G.set_grain_reserves_enabled(world, False)
    elif missing == "agents":
        world.agent_mode = "off"
    else:
        set_contact_ledger_enabled(world, False)
    before = world.harvest_forecasts.model_dump_json()
    with pytest.raises(ValueError, match="harvest forecasts require"):
        H.validate_harvest_forecasts(world)
    assert H.tick_harvest_forecasts(world, _economy(world)) == []
    assert world.harvest_forecasts.model_dump_json() == before
    assert H.snapshot_summary(world) == {}
    if missing == "agents":
        H.validate_harvest_forecasts(world, agent_mode="hybrid")


def test_dated_local_and_contact_reports_never_arrive_on_issue_turn():
    world = _world()
    world.contact_ledger = ContactLedgerState(edges=[(AMBER, FROST, 1.0, 0.0, 0.0, 0.0)], last_update_turn=4)
    reports = _publish(world)
    local, remote = reports[AMBER], reports[FROST]
    assert local.delivery_turn == 6 and remote.delivery_turn == 7
    assert local.status == remote.status == "pending"
    assert local.delivered_turn is remote.delivered_turn is None
    assert local.target_start == 9 and local.expires_turn == 11
    assert len(reports) == len({r.recipient_region for r in reports.values()})
    # Removing contact after publication cannot rewrite the delivery schedule.
    world.contact_ledger.edges = []
    world.contact_ledger.invalidate()
    world.turn = 6
    _forecast_tick(world)
    assert local.delivered_turn == 6 and remote.delivered_turn is None
    world.turn = 7
    _forecast_tick(world)
    assert remote.delivered_turn == 7


def test_contact_order_cannot_change_which_assessor_is_chosen():
    first, second = _world(), _world()
    edges = [(5, 0, 1.0, 0.0, 0.0, 0.0), (2, 0, 1.0, 0.0, 0.0, 0.0)]
    first.contact_ledger = ContactLedgerState(edges=edges)
    second.contact_ledger = ContactLedgerState(edges=list(reversed(edges)))
    a, b = _publish(first), _publish(second)
    assert a[FROST].source_region == b[FROST].source_region == 2
    assert first.harvest_forecasts == second.harvest_forecasts


def test_observers_never_read_future_climate_and_do_not_advance_existing_rng(monkeypatch):
    import chronicler.climate as climate
    world = _world()
    future = climate.region_harvest_shocks(world, turn=100)
    original = random.getstate()

    def forbidden(*args, **kwargs):
        raise AssertionError("forecast read climate truth")

    with monkeypatch.context() as patch:
        for name in ("harvest_shock", "region_harvest_shocks", "_deterministic_roll"):
            patch.setattr(climate, name, forbidden)
        _publish(world)
    assert random.getstate() == original
    assert climate.region_harvest_shocks(world, turn=100) == future


def test_withheld_and_shuffled_controls_preserve_forecast_schedule_and_noise():
    normal, withheld, shuffled = _world(), _world("withhold"), _world("shuffle")
    ratios = {2: 0.05, 3: 1.0, 5: 3.5, 7: 2.0}
    a, b, c = (_publish(world, ratios) for world in (normal, withheld, shuffled))
    assert {i: r.probability for i, r in a.items()} == {i: r.probability for i, r in b.items()}
    assert sorted(r.probability for r in a.values()) == sorted(r.probability for r in c.values())
    assert any(a[i].probability != c[i].probability for i in a)
    for world in (normal, withheld):
        world.turn = 6
        _forecast_tick(world)
    assert all(r.status == "delivered" for r in normal.harvest_forecasts.reports)
    assert all(r.status == "withheld" and r.delivered_turn is None for r in withheld.harvest_forecasts.reports)


def test_zero_noise_control_and_missing_recent_observations(monkeypatch):
    world = _world()
    monkeypatch.setattr(H, "NOISE", 0.0)
    reports = _publish(world)
    for report in reports.values():
        expected = min(0.95, max(0.05, 0.5 + 0.5 * (0.6 - report.predicted_ratio) / 0.6))
        assert report.probability == pytest.approx(expected)
    # Old observations cannot pass as a fully observed current harvest year.
    world.harvest_forecasts.reports.clear()
    world.turn = 29
    H.tick_harvest_forecasts(world, None)
    assert not world.harvest_forecasts.reports


def test_time_reversal_is_rejected_and_duplicate_tick_is_inert():
    world = _world()
    world.turn = 4
    _forecast_tick(world)
    before = world.harvest_forecasts.model_dump_json()
    assert H.tick_harvest_forecasts(world, _measure(world)) == []
    assert world.harvest_forecasts.model_dump_json() == before
    world.turn = 3
    with pytest.raises(ValueError, match="ahead of the world"):
        H.tick_harvest_forecasts(world, _measure(world))


def test_expiry_calibration_uses_production_even_when_people_are_fed():
    world = _world()
    report = _warning(world)
    for turn in range(6, 13):
        world.turn = turn
        result = _economy(world, suff={AMBER: 1.0}, harvest={AMBER: 1.0})
        world.events_timeline.extend(H.tick_harvest_forecasts(world, result))
    assert report.status == "resolved" and report.resolved_turn == 12
    assert report.outcome_shortfall is True
    assert report.brier == pytest.approx((0.9 - 1) ** 2)
    assert world.harvest_forecasts.counters["resolved"] == 1
    assert not world.harvest_forecasts.reports
    assert sum(row[0] for row in world.harvest_forecasts.calibration) == 1


def test_missing_winter_measurements_are_unscored_and_owner_changes_cancel():
    world = _world()
    report = _warning(world)
    world.turn = 12
    H.tick_harvest_forecasts(world, None)
    assert report.status == "unscored" and report.brier is None
    assert world.harvest_forecasts.counters["resolved"] == 0
    other = _world()
    cancelled = _warning(other)
    other.regions[AMBER].controller = other.civilizations[0].name
    H.tick_harvest_forecasts(other, _economy(other))
    assert cancelled.status == "cancelled" and cancelled.delivered_turn is None


def test_delivered_warning_buys_real_grain_and_pays_existing_procurement(monkeypatch):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    normal, withheld = _world(), _world("withhold")
    for world in (normal, withheld):
        _warning(world)
        world.regions[AMBER].stockpile.goods["grain"] = 100.0
        result = _economy(world)
        G.open_granaries(world, result)
        grain_before = world.regions[AMBER].stockpile.goods["grain"]
        owner = world.civ_index_map[world.regions[AMBER].controller]
        money_before = world.civilizations[owner].treasury
        events = G.tick_grain_reserves(world, economy_result=result)
        world.events_timeline.extend(events)
        granary = world.grain_reserves.granaries[AMBER]
        if world is normal:
            [row] = world.harvest_forecasts.preparedness
            assert row["base_target"] == 0 and row["extra_target"] > 0
            assert row["bought_during_warning"] == pytest.approx(granary.grain)
            assert row["paid_during_warning"] > 0
            purchase = next(event for event in events if event.event_type == "harvest_preparedness")
            assert world.harvest_forecasts.reports[0].delivered_event_id in purchase.causes
            assert world.civilizations[owner].treasury == money_before - row["paid_during_warning"]
            assert grain_before - world.regions[AMBER].stockpile.goods["grain"] == pytest.approx(granary.grain)
            # Re-reading/re-applying in the same tick cannot compound or double-count.
            target = granary.target
            counters = dict(world.harvest_forecasts.counters)
            H.apply_preparedness(world, result)
            H.record_preparedness_purchases(world)
            assert granary.target == target and world.harvest_forecasts.counters == counters
        else:
            assert granary.target == granary.grain == 0
            assert world.civilizations[owner].treasury == money_before
            assert world.harvest_forecasts.preparedness == []


def test_target_expires_without_compounding_and_does_not_bypass_empty_markets():
    world = _world()
    _warning(world)
    targets = []
    for turn in (6, 7, 8, 12):
        world.turn = turn
        result = _economy(world)
        G.open_granaries(world, result)
        G.tick_grain_reserves(world, economy_result=result)
        granary = world.grain_reserves.granaries[AMBER]
        targets.append(granary.target)
        assert granary.grain == 0
    assert targets[0] == targets[1] == targets[2] > 0 and targets[3] == 0


@pytest.mark.parametrize("reason", ["expiry", "disable", "ownership", "dormant"])
def test_phase2_never_reads_an_expired_cancelled_or_disabled_extra_target(reason):
    world = _world()
    _warning(world)
    world.turn = 11
    result = _economy(world)
    G.open_granaries(world, result)
    G.tick_grain_reserves(world, economy_result=result)
    granary = world.grain_reserves.granaries[AMBER]
    assert granary.target > 0
    if reason == "expiry":
        world.turn = 12
    elif reason == "disable":
        H.set_harvest_forecasts_enabled(world, False)
    elif reason == "ownership":
        world.regions[AMBER].controller = world.civilizations[0].name
    else:
        set_contact_ledger_enabled(world, False)
    G.open_granaries(world, _economy(world))
    assert granary.target == 0


@pytest.mark.parametrize("saved_turn", [4, 5, 7])
def test_json_resume_keeps_queue_observations_targets_and_scores(saved_turn, tmp_path):
    world = _world()
    resumed = None
    for turn in range(13):
        for current in (world,) if resumed is None else (world, resumed):
            current.turn = turn
            result = _measure(current)
            G.open_granaries(current, result)
            current.events_timeline.extend(G.tick_grain_reserves(current, economy_result=result))
        if turn == saved_turn:
            path = tmp_path / "forecast.json"
            world.save(path)
            resumed = WorldState.load(path)
        if resumed is not None:
            assert world.model_dump_json() == resumed.model_dump_json()


@pytest.mark.parametrize("saved_turn", [4, 5, 7])
def test_exact_checkpoint_preserves_transit_and_preparedness(saved_turn, tmp_path):
    from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
    world = _world()
    resumed = None
    for turn in range(13):
        for current in (world,) if resumed is None else (world, resumed):
            current.turn = turn
            result = _measure(current)
            G.open_granaries(current, result)
            current.events_timeline.extend(G.tick_grain_reserves(current, economy_result=result))
            current.turn = turn + 1
        if turn == saved_turn:
            path = tmp_path / "harvest.ckpt"
            state = RunState(world=world, memories={}, history=[], chronicle_entries=[],
                             era_reflections={}, pending_injections=[], start_turn=0,
                             seed=world.seed, num_turns=13)
            write_checkpoint(path, state)
            loaded = read_checkpoint(path)
            assert loaded.exact and not loaded.mismatches
            resumed = loaded.state.world
        if resumed is not None:
            assert world.model_dump_json() == resumed.model_dump_json()


def test_snapshot_is_completed_turn_only_and_detached_from_runtime():
    world = _world()
    _warning(world)
    result = _economy(world)
    G.open_granaries(world, result)
    G.tick_grain_reserves(world, economy_result=result)
    assert H.snapshot_summary(world) == {}  # tick 6 is not completed yet
    world.turn += 1
    snapshot = H.snapshot_summary(world)
    assert snapshot["source_turn"] == 6 and snapshot["preparedness"]
    world.harvest_forecasts.preparedness[0]["paid_during_warning"] = 999
    assert snapshot["preparedness"][0]["paid_during_warning"] != 999
    world.turn += 1
    assert H.snapshot_summary(world) == {}


@pytest.mark.native
def test_real_native_goods_run_issues_delivers_and_scores_reports():
    ca = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(ca, "AgentSimulator", None), type):
        pytest.skip("requires a real native simulator")
    from chronicler.agent_bridge import AgentBridge
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn
    world = _world()
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    for _ in range(13):
        engine = ActionEngine(world)
        run_turn(world, lambda civ, w: engine.select_action(civ, seed=w.seed),
                 lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)
    state = world.harvest_forecasts
    assert state.counters["issued"] > 0 and state.counters["delivered"] > 0
    assert state.counters["resolved"] > 0
    assert all(r.issued_turn < r.delivered_turn <= r.expires_turn for r in state.outcomes
               if r.delivered_turn is not None)


@pytest.mark.parametrize("base", [0.0, 2.5, 4.126938305182808])
def test_warning_caps_only_addition_when_current_demand_is_smaller_than_base(base):
    world = _world()
    _warning(world)
    result = _economy(world, pop={AMBER: 1})  # current demand = 0.5; six turns = 3
    granary = _granary(world, AMBER)
    granary.target = base
    H.tick_harvest_forecasts(world, result)
    H.apply_preparedness(world, result)
    [row] = world.harvest_forecasts.preparedness
    assert granary.target >= base
    assert 0 <= row["extra_target"] <= H.EXTRA_TURNS * 0.5
    assert row["extra_target"] <= max(0, H.MAX_TOTAL_TURNS * 0.5 - base)
    assert granary.target == base + row["extra_target"]
    # An already applied target stays based on the original base as demand
    # changes again, and disabling restores that base rather than a stale sum.
    result.market_demand[world.regions[AMBER].name] = (0.25, 0.0, 0.0, 0.0)
    H.apply_preparedness(world, result)
    assert row["extra_target"] == granary.target - base >= 0
    H.set_harvest_forecasts_enabled(world, False)
    assert granary.target == base


def test_empty_recipient_keeps_unobserved_base_and_accrues_no_paid_preparation():
    world = _world()
    _warning(world)
    result = _economy(world, pop={AMBER: 1})
    granary = _granary(world, AMBER)
    granary.target = 4.126938305182808
    # The economy observed 0.5 demand before this turn's native population
    # change. _observe deliberately skips the now-empty region.
    world.regions[AMBER].population = 0
    G.tick_grain_reserves(world, economy_result=result)
    assert granary.target == 4.126938305182808
    assert granary.observed == 0
    assert world.harvest_forecasts.preparedness == []
    assert world.harvest_forecasts.counters["paid_during_warning"] == 0
    assert world.harvest_forecasts.counters["bought_during_warning"] == 0


@pytest.mark.parametrize("missing", ["population", "demand", "economy"])
def test_unobserved_next_turn_restores_known_extra_before_losing_its_record(missing):
    world = _world()
    _warning(world)
    result = _economy(world)
    granary = _granary(world, AMBER)
    granary.target = 2.0
    H.tick_harvest_forecasts(world, result)
    H.apply_preparedness(world, result)
    assert granary.target > 2.0
    world.turn += 1
    if missing == "population":
        world.regions[AMBER].population = 0
    elif missing == "demand":
        result.market_demand[world.regions[AMBER].name] = (0.0, 0.0, 0.0, 0.0)
    else:
        result = None
    # Save/load at the waiting boundary retains the restoration instruction.
    resumed = WorldState.model_validate_json(world.model_dump_json())
    for current in (world, resumed):
        H.tick_harvest_forecasts(current, result)
        assert current.grain_reserves.granaries[AMBER].target == 2.0
        if result is not None:
            H.apply_preparedness(current, result)
        assert current.harvest_forecasts.preparedness == []
    assert resumed.model_dump_json() == world.model_dump_json()
