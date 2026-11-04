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


class TestLocalForecastCredibility:
    """Model/fake boundaries: no World, native pool, checkpoint or market."""

    @staticmethod
    def local_world(policy="local_credibility"):
        from types import SimpleNamespace
        from chronicler.harvest_forecasts_state import HarvestForecastState, HarvestObserver
        state = HarvestForecastState(preparation_policy=policy,
                                     observers=[HarvestObserver(region=0)])
        return SimpleNamespace(
            seed=42, turn=12, harvest_forecasts=state,
            regions=[SimpleNamespace(name=name, controller="Realm", population=100)
                     for name in ("Home", "Source1", "Source2")],
            civilizations=[SimpleNamespace(name="Realm"), SimpleNamespace(name="Other")],
            grain_reserves=SimpleNamespace(granaries=[SimpleNamespace(target=10., owner=0)
                                                     for _ in range(3)]))

    @staticmethod
    def local_report(year=0, source=1, ratio=1., probability=.9):
        start = 12 * year
        total = 0.0
        for _ in range(3):
            total += ratio
        mean = total / 3
        return HarvestReport(
            id=f"harvest:{year}:{source}:0", source_region=source, source_region_name=f"Source{source}",
            recipient_region=0, recipient_region_name="Home", owner=0, owner_name="Realm",
            issued_turn=start + 5, delivery_turn=start + (6 if source == 0 else 7),
            delivered_turn=start + (6 if source == 0 else 7), expires_turn=start + 11,
            target_start=start + 9, target_end=start + 11, probability=probability,
            confidence=1., predicted_ratio=.2, status="resolved", resolved_turn=start + 12,
            evaluation_sum=total, evaluation_count=3, observed_ratio=mean,
            outcome_shortfall=mean < H.SHORTFALL_RATIO,
            brier=(probability - float(mean < H.SHORTFALL_RATIO)) ** 2,
            issued_event_id=f"{start + 5}:harvest_forecast_issued:0",
            delivered_event_id=f"{start + 7}:harvest_forecast_delivered:0",
            credibility_observations=[(start + t, ratio) for t in (9, 10, 11)])

    def remember(self, w, report):
        w.turn = report.resolved_turn
        H._remember_local_result(w, w.harvest_forecasts, report)

    def test_legacy_json_and_genuinely_missing_pickle_fields_stay_legacy(self):
        import pickle
        from chronicler.harvest_forecasts_state import HarvestForecastState, HarvestObserver
        state = HarvestForecastState()
        assert "preparation_policy" not in state.model_dump()
        observer = HarvestObserver(region=0)
        assert observer.model_dump() == {"region": 0, "observations": []}
        report = self.local_report()
        report.credibility_observations = []
        assert "credibility_observations" not in report.model_dump()
        del state.__dict__["preparation_policy"]
        del observer.__dict__["credibility_memory"]
        state.observers = [observer]
        restored = pickle.loads(pickle.dumps(state))
        assert H.get_preparation_policy(restored) == "fixed"
        assert H._local_memory(restored.observers[0]) == []
        w = self.local_world("fixed")
        w.harvest_forecasts = restored
        H.set_preparation_policy(w, "fixed")
        assert "preparation_policy" not in restored.__dict__

    def test_zero_history_and_fixed_policy_keep_exact_legacy_discount(self):
        w = self.local_world()
        report = self.local_report(year=1)
        assert H.local_preparation_discount(w.harvest_forecasts, report, 18) == (1., [])
        self.remember(w, self.local_report())
        w.harvest_forecasts.preparation_policy = "fixed"
        assert H.local_preparation_discount(w.harvest_forecasts, report, 18) == (1., [])

    def test_false_alarm_discount_and_accurate_result_recovery_follow_frozen_rule(self):
        w = self.local_world()
        self.remember(w, self.local_report())
        discount, ids = H.local_preparation_discount(w.harvest_forecasts, self.local_report(1), 18)
        assert discount == (2 + (1 - .9 ** 2)) / 3
        assert ids == ["harvest:0:1:0"]
        self.remember(w, self.local_report(1, ratio=.2))
        recovered, ids = H.local_preparation_discount(w.harvest_forecasts, self.local_report(2), 30)
        assert recovered == (2 + (1 - .9 ** 2) + (1 - (.9 - 1) ** 2)) / 4
        assert recovered > discount and len(ids) == 2

    def test_local_memory_is_four_results_across_sources_and_rejects_old_replay(self):
        w = self.local_world()
        for year, source in enumerate((1, 2, 1, 2, 2)):
            self.remember(w, self.local_report(year, source=source))
        memory = w.harvest_forecasts.observers[0].credibility_memory
        assert [r.issued_turn for r in memory] == [17, 29, 41, 53]
        assert len(memory) == 4
        _, ids = H.local_preparation_discount(w.harvest_forecasts, self.local_report(5), 66)
        assert ids == ["harvest:2:1:0"]
        before = w.harvest_forecasts.model_dump_json()
        old = self.local_report()
        w.turn = old.resolved_turn
        H._remember_local_result(w, w.harvest_forecasts, old)
        assert w.harvest_forecasts.model_dump_json() == before

    def test_unrelated_region_scores_and_global_history_never_supply_evidence(self):
        from chronicler.harvest_forecasts_state import HarvestObserver
        w = self.local_world()
        self.remember(w, self.local_report())
        expected = H.local_preparation_discount(w.harvest_forecasts, self.local_report(1), 18)
        w.harvest_forecasts.outcomes = [self.local_report()] * 128
        w.harvest_forecasts.calibration = [[999., 999., 999.] for _ in range(5)]
        w.harvest_forecasts.observers.append(HarvestObserver(region=99))
        assert H.local_preparation_discount(w.harvest_forecasts, self.local_report(1), 18) == expected
        w.harvest_forecasts.outcomes = []
        assert H.local_preparation_discount(w.harvest_forecasts, self.local_report(1), 18) == expected

    def test_withheld_incomplete_cancelled_late_or_other_owner_results_never_learn(self):
        from copy import deepcopy
        cases = [
            {"delivered_turn": None}, {"status": "cancelled"}, {"status": "unscored"},
            {"evaluation_count": 2}, {"credibility_observations": []},
            {"delivered_event_id": ""}, {"issued_event_id": ""},
        ]
        for changes in cases:
            w = self.local_world()
            report = self.local_report()
            for key, value in changes.items():
                setattr(report, key, value)
            self.remember(w, report)
            assert w.harvest_forecasts.observers[0].credibility_memory == []
        for change in ("owner", "extinction"):
            w = self.local_world()
            if change == "owner":
                w.regions[0].controller = "Other"
            else:
                w.regions[0].population = 0
            self.remember(w, self.local_report())
            assert w.harvest_forecasts.observers[0].credibility_memory == []
        w = self.local_world()
        report = self.local_report()
        report.delivered_turn = 9
        before = deepcopy(w.harvest_forecasts.model_dump())
        with pytest.raises(ValueError):
            self.remember(w, report)
        assert w.harvest_forecasts.model_dump() == before

    def test_exact_dates_three_real_values_and_score_arithmetic_are_required(self):
        changes = [
            ("credibility_observations", [(9, 1.), (9, 1.), (11, 1.)]),
            ("credibility_observations", [(9, 1.), (10, 1.), (11, float("nan"))]),
            ("evaluation_sum", 1.), ("observed_ratio", .2), ("brier", .01),
            ("outcome_shortfall", True), ("target_start", 8),
            ("id", "another-report"), ("resolved_turn", 11),
        ]
        for key, value in changes:
            w = self.local_world()
            report = self.local_report()
            setattr(report, key, value)
            with pytest.raises(ValueError):
                self.remember(w, report)
            assert w.harvest_forecasts.observers[0].credibility_memory == []

    def test_a_repeated_result_is_inert_and_conflicting_repetition_refuses(self):
        w = self.local_world()
        report = self.local_report()
        self.remember(w, report)
        before = w.harvest_forecasts.model_dump_json()
        self.remember(w, report)
        assert w.harvest_forecasts.model_dump_json() == before
        report.probability = .8
        report.brier = .8 ** 2
        with pytest.raises(ValueError, match="conflicting"):
            self.remember(w, report)
        assert w.harvest_forecasts.model_dump_json() == before

    def test_other_source_owner_and_not_yet_known_results_are_excluded(self):
        from copy import deepcopy
        w = self.local_world()
        self.remember(w, self.local_report())
        for changes in ({"source_region": 2}, {"owner": 1}, {"owner_name": "Other"},
                        {"issued_turn": 5}):
            report = self.local_report(1)
            for key, value in changes.items():
                setattr(report, key, value)
            assert H.local_preparation_discount(w.harvest_forecasts, report, 18) == (1., [])
        row = w.harvest_forecasts.observers[0].credibility_memory[0]
        row.resolved_turn = 30
        assert H.local_preparation_discount(w.harvest_forecasts, self.local_report(1), 18) == (1., [])

    def test_loaded_local_memory_is_bounded_ordered_and_revalidated(self):
        from copy import deepcopy
        w = self.local_world()
        self.remember(w, self.local_report())
        observer = w.harvest_forecasts.observers[0]
        valid = deepcopy(observer.credibility_memory)
        for rows in ([valid[0]] * 5, [valid[0]] * 2, [object()],
                     [valid[0].model_copy(update={"probability": float("nan")})],
                     [valid[0].model_copy(update={"observations": [(True, 1.), (10, 1.), (11, 1.)]})]):
            observer.credibility_memory = rows
            with pytest.raises(ValueError):
                H.local_preparation_discount(w.harvest_forecasts, self.local_report(1), 18)
        observer.credibility_memory = valid
        assert H.local_preparation_discount(w.harvest_forecasts, self.local_report(1), 18)[1]

    def test_preparedness_changes_only_existing_bounded_target_and_records_evidence(self, monkeypatch):
        w = self.local_world()
        self.remember(w, self.local_report())
        report = self.local_report(1)
        report.status = "delivered"
        w.turn = 19
        w.harvest_forecasts.reports = [report]
        monkeypatch.setattr(H, "harvest_forecasts_active", lambda world: True)
        monkeypatch.setattr(G, "_demand", lambda result, name: 10.)
        H.apply_preparedness(w, object())
        discount = (2 + (1 - .9 ** 2)) / 3
        expected = 10. + 2 * .9 * 10. * discount
        assert w.grain_reserves.granaries[0].target == expected
        row, = w.harvest_forecasts.preparedness
        assert row["credibility_discount"] == discount
        assert row["credibility_evidence_ids"] == ["harvest:0:1:0"]
        assert row["bought_during_warning"] == row["paid_during_warning"] == 0
        H.apply_preparedness(w, object())
        assert w.grain_reserves.granaries[0].target == expected
        H.set_preparation_policy(w, "fixed")
        assert w.grain_reserves.granaries[0].target == 10. and w.harvest_forecasts.preparedness == []
        H.apply_preparedness(w, object())
        assert w.grain_reserves.granaries[0].target == 28.
        assert "credibility_discount" not in w.harvest_forecasts.preparedness[0]

    def test_switch_restores_only_known_increment_and_retains_memory(self):
        w = self.local_world()
        self.remember(w, self.local_report())
        memory = w.harvest_forecasts.observers[0].credibility_memory
        w.harvest_forecasts.preparedness = [{"region": 0, "base_target": 10., "extra_target": 5.}]
        w.grain_reserves.granaries[0].target = 123.
        H.set_preparation_policy(w, "fixed")
        assert w.grain_reserves.granaries[0].target == 123.
        assert w.harvest_forecasts.observers[0].credibility_memory is memory
        assert w.harvest_forecasts.preparedness == []
        H.set_preparation_policy(w, "local_credibility")
        assert H.local_preparation_discount(w.harvest_forecasts, self.local_report(1), 18)[1]

    def test_invalid_switch_or_late_restoration_record_is_transactional(self):
        import pickle
        w = self.local_world("fixed")
        w.grain_reserves.granaries[0].target = 15.
        w.harvest_forecasts.preparedness = [
            {"region": 0, "base_target": 10., "extra_target": 5.},
            {"region": 1, "base_target": float("nan"), "extra_target": 1.}]
        before = pickle.dumps(w)
        with pytest.raises(ValueError):
            H.set_preparation_policy(w, "local_credibility")
        assert pickle.dumps(w) == before
        for invalid in (None, True, 1, "future_truth"):
            with pytest.raises(ValueError):
                H.set_preparation_policy(w, invalid)
            assert pickle.dumps(w) == before

    def test_same_source_model_roundtrip_retains_future_decisions_without_world_or_checkpoint(self):
        from chronicler.harvest_forecasts_state import HarvestForecastState
        w = self.local_world()
        self.remember(w, self.local_report())
        state = w.harvest_forecasts
        restored = HarvestForecastState.model_validate_json(state.model_dump_json())
        report = self.local_report(1)
        assert H.local_preparation_discount(state, report, 18) == H.local_preparation_discount(restored, report, 18)
        assert restored.model_dump() == state.model_dump()

    def test_dated_observations_resolve_once_and_pause_does_not_learn(self, monkeypatch):
        from types import SimpleNamespace
        w = self.local_world()
        report = self.local_report()
        report.status, report.resolved_turn = "delivered", None
        report.evaluation_sum, report.evaluation_count = 0., 0
        report.observed_ratio = report.outcome_shortfall = report.brier = None
        report.credibility_observations = []
        w.harvest_forecasts.reports = [report]
        monkeypatch.setattr(H, "harvest_forecasts_active", lambda world: True)
        monkeypatch.setattr(H, "_ratios", lambda world, result: {0: 1.})
        monkeypatch.setattr(H, "_emit", lambda *args, **kwargs: SimpleNamespace(event_id="fake-event"))
        monkeypatch.setattr(G, "_demand", lambda result, name: 10.)
        for turn in (9, 10, 11, 12):
            w.turn = turn
            H.tick_harvest_forecasts(w, object())
            before = w.harvest_forecasts.model_dump_json()
            assert H.tick_harvest_forecasts(w, object()) == []
            assert w.harvest_forecasts.model_dump_json() == before
        assert report.credibility_observations == [(9, 1.), (10, 1.), (11, 1.)]
        assert len(w.harvest_forecasts.observers[0].credibility_memory) == 1
        assert report.observed_ratio == 1. and report.brier == .9 ** 2
        w.turn = 13  # Policy changes occur before the next turn's forecast work.
        H.set_preparation_policy(w, "fixed")
        self.remember(w, self.local_report(1))
        assert len(w.harvest_forecasts.observers[0].credibility_memory) == 1

    def test_scored_withheld_report_cannot_become_local_knowledge(self, monkeypatch):
        from types import SimpleNamespace
        w = self.local_world()
        w.harvest_forecasts.policy = "withhold"
        report = self.local_report()
        report.status, report.delivered_turn, report.resolved_turn = "pending", None, None
        report.evaluation_sum, report.evaluation_count = 0., 0
        report.observed_ratio = report.outcome_shortfall = report.brier = None
        report.credibility_observations = []
        w.harvest_forecasts.reports = [report]
        monkeypatch.setattr(H, "harvest_forecasts_active", lambda world: True)
        monkeypatch.setattr(H, "_ratios", lambda world, result: {0: 1.})
        monkeypatch.setattr(H, "_emit", lambda *args, **kwargs: SimpleNamespace(event_id="fake-event"))
        monkeypatch.setattr(G, "_demand", lambda result, name: 10.)
        for turn in (9, 10, 11, 12):
            w.turn = turn
            H.tick_harvest_forecasts(w, object())
        assert report.status == "resolved" and report.brier == .9 ** 2
        assert w.harvest_forecasts.counters["resolved"] == 1
        assert w.harvest_forecasts.observers[0].credibility_memory == []

    def test_policy_and_discounts_do_not_draw_rng_or_change_probabilities(self):
        w = self.local_world("fixed")
        report = self.local_report()
        before = random.getstate(), report.model_dump()
        H.set_preparation_policy(w, "local_credibility")
        self.remember(w, report)
        H.local_preparation_discount(w.harvest_forecasts, self.local_report(1), 18)
        assert (random.getstate(), report.model_dump()) == before

    @staticmethod
    def experiment_metadata():
        from contextlib import contextmanager
        from types import ModuleType
        from unittest import mock
        import sys
        @contextmanager
        def context():
            batch = ModuleType("chronicler.batch_manifest")
            batch.source_identity = mock.Mock(return_value={"git_sha": "a" * 40, "package_digest": "b" * 64})
            batch.native_identity = mock.Mock(return_value={"status": "absent"})
            hashes = {"/metadata-parent.ckpt": "c" * 64, "/metadata-registration.md": "d" * 64}
            batch.file_sha256 = mock.Mock(side_effect=lambda path: hashes[str(path)])
            checkpoint = ModuleType("chronicler.run_checkpoint")
            checkpoint.read_header = mock.Mock(return_value=({"turn": 12, "seed": 42,
                "exact": True, "identity": {"source": "fake-only"}, "flags": {}}, b"unread-body"))
            with mock.patch.dict(sys.modules, {batch.__name__: batch, checkpoint.__name__: checkpoint}), \
                    mock.patch.object(sys.modules["chronicler"], "batch_manifest", batch, create=True), \
                    mock.patch.object(sys.modules["chronicler"], "run_checkpoint", checkpoint, create=True):
                yield batch, checkpoint
        return context()

    @staticmethod
    def experiment_request(controls=None, **extra):
        value = dict(schema_version=1, experiment="local-forecast-policy", cohort="development",
                     feature="harvest_forecasts", arm="control", controls={} if controls is None else controls,
                     fork=False)
        value.update(extra)
        return value

    def test_experiment_legacy_tuple_omission_and_explicit_reversion_are_truthful(self):
        from chronicler.expansion_experiment import CONTROL_FIELDS, apply_expansion_experiment, controls_for_state
        w = self.local_world("fixed")
        assert CONTROL_FIELDS["harvest_forecasts"] == ("policy",)
        with self.experiment_metadata():
            legacy = apply_expansion_experiment(w, {}, self.experiment_request(), resumed=False)
            assert legacy["controls_before"] == legacy["controls_after"] == {"policy": "normal"}
            opted = apply_expansion_experiment(w, {}, self.experiment_request(
                {"preparation_policy": "local_credibility"}), resumed=False)
            assert list(opted["controls_before"]) == ["policy", "preparation_policy"]
            assert opted["controls_before"] == {"policy": "normal", "preparation_policy": "fixed"}
            assert opted["controls_after"] == {"policy": "normal", "preparation_policy": "local_credibility"}
            inherited = apply_expansion_experiment(w, {}, self.experiment_request(), resumed=False)
            assert inherited["controls_before"] == inherited["controls_after"] == opted["controls_after"]
            reverted = apply_expansion_experiment(w, {}, self.experiment_request(
                {"preparation_policy": "fixed"}), resumed=False)
            assert reverted["controls_before"] == opted["controls_after"]
            assert reverted["controls_after"] == {"policy": "normal", "preparation_policy": "fixed"}
        assert controls_for_state("harvest_forecasts", w.harvest_forecasts) == {"policy": "normal"}

    def test_experiment_invalid_registration_and_late_metadata_are_transactional(self):
        import pickle
        from unittest import mock
        from chronicler.expansion_experiment import apply_expansion_experiment
        cases = [
            self.experiment_request({"preparation_policy": "unknown"}),
            self.experiment_request({"preparation_policy": True}),
            self.experiment_request({"preparation_policy": "local_credibility", "policy": "future_truth"}),
            self.experiment_request({"preparation_policy": "local_credibility"}, cohort="confirmatory"),
            self.experiment_request({"preparation_policy": "local_credibility"},
                registration={"path": "/metadata-registration.md", "sha256": "f" * 64}),
            self.experiment_request({"preparation_policy": "local_credibility"}, fork=True),
        ]
        for request in cases:
            w = self.local_world("fixed")
            before = pickle.dumps(w)
            with self.experiment_metadata(), pytest.raises(ValueError):
                apply_expansion_experiment(w, {}, request, resumed=False)
            assert pickle.dumps(w) == before
        w = self.local_world("fixed")
        before = pickle.dumps(w)
        with self.experiment_metadata() as (batch, checkpoint):
            batch.source_identity.return_value = {"invalid": float("nan")}
            with pytest.raises(ValueError):
                apply_expansion_experiment(w, {}, self.experiment_request(
                    {"preparation_policy": "local_credibility"}), resumed=False)
        assert pickle.dumps(w) == before

    def test_experiment_resumed_policy_change_preserves_receipts_and_model_progress(self):
        from chronicler.expansion_experiment import apply_expansion_experiment
        w = self.local_world("fixed")
        observer = w.harvest_forecasts.observers[0]
        request = self.experiment_request({"preparation_policy": "local_credibility"}, fork=True,
            parent_checkpoint={"path": "/metadata-parent.ckpt", "sha256": "c" * 64})
        with self.experiment_metadata():
            receipt = apply_expansion_experiment(w, {"expansion_experiment": {"arm": "parent"}},
                                                request, resumed=True)
        assert receipt["intervention_fork"] is True
        assert receipt["controls_after"]["preparation_policy"] == "local_credibility"
        assert receipt["previous_experiment"] == {"arm": "parent"}
        assert w.harvest_forecasts.observers[0] is observer
        assert (w.turn, w.seed) == (12, 42)

    def test_old_comparison_reader_explicitly_refuses_the_new_memory_arm(self):
        import ast
        from collections.abc import Mapping
        from pathlib import Path
        path = Path(H.__file__).with_name("expansion_compare.py")
        tree = ast.parse(path.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_controls")
        namespace = {"Mapping": Mapping}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
        blockers = []
        assert namespace["_controls"]({"policy": "normal", "preparation_policy": "local_credibility"},
                                      "harvest_forecasts", blockers) is None
        assert blockers == ["local_forecast_credibility_comparison_unsupported"]

    def test_boolean_observations_and_midturn_policy_changes_refuse_before_mutation(self):
        import pickle
        from chronicler.harvest_forecasts_state import ForecastCredibilityEvidence
        report = self.local_report()
        data = dict(report_id=report.id, source_region=report.source_region, recipient_region=0,
                    issued_event_id=report.issued_event_id, delivered_event_id=report.delivered_event_id,
                    owner=0, owner_name="Realm", issued_turn=5, delivered_turn=7, resolved_turn=12,
                    probability=.9, observations=[(9, True), (10, 1.), (11, 1.)],
                    observed_ratio=1., outcome_shortfall=False, brier=.81)
        with pytest.raises(ValueError):
            ForecastCredibilityEvidence.model_validate(data)
        w = self.local_world("fixed")
        w.harvest_forecasts.last_tick_turn = w.turn
        before = pickle.dumps(w)
        with pytest.raises(ValueError, match="pre-tick"):
            H.set_preparation_policy(w, "local_credibility")
        assert pickle.dumps(w) == before
        H.set_preparation_policy(w, "fixed")  # Same-policy call remains inert.
        assert pickle.dumps(w) == before
