"""Prospective mechanical acceptance; these fixtures do not qualify world effects."""
from __future__ import annotations

import random

import numpy as np
import pytest

from chronicler import scientific_claims as C
from chronicler import techniques as T
from chronicler.accumulator import StatAccumulator
from chronicler.models import WorldState
from chronicler.scholarship_state import ACADEMY, LIBRARY, ScholarshipState, Seat
from chronicler.scientific_claims_state import (
    EvidenceReceipt, ProposalReceipt,
)
from chronicler.techniques_state import TECHNIQUE_INDEX as K, TechniqueState
from war_fixtures import war_world


def _world(*, seats=(0, 1, 2, 3, 4), treasury=200) -> WorldState:
    world = war_world(treasury_a=treasury, treasury_b=treasury)
    world.scholarship = ScholarshipState()
    world.techniques = TechniqueState(initialized_turn=0)
    for ri, r in enumerate(world.regions):
        r.population = 200
        r.resource_types = [0, 5, 255]
        r.resource_base_yields = [1., 1., 0.]
        r.resource_effective_yields = [1., 1., 0.]
        r.resource_reserves = [1., .5, 0.]
        r.ecology.soil, r.ecology.water = .8, .7
        for recipe in C.RECIPES:
            world.techniques.rows.append((ri, K[recipe], .5, -1, 6, 0 if ri < 2 else 1))
    for ri in seats:
        lord = 0 if ri < 2 else 1
        world.scholarship.seats.append(Seat(region=ri, kind=ACADEMY, name=f"Academy {ri}",
                                           founded_turn=-1, lord=lord, scholars=10.))
    C.set_scientific_claims_enabled(world, True)
    return world


def _tick(world, turn, acc=None):
    world.turn = turn
    return C.tick_scientific_claims(world, acc)


def _complete(world, monkeypatch):
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    _tick(world, 0)
    _tick(world, 1)


def _run(world, start, stop):
    for turn in range(start, stop):
        world.turn = turn
        C.prepare_adoption_effort(world)
        C.tick_scientific_claims(world)
    world.turn = stop
    return world


def test_default_off_and_missing_hosts_are_dormant():
    assert C.DEFAULT_ENABLED_FOR_NEW_WORLDS is False
    world = _world()
    C.set_scientific_claims_enabled(world, False)
    before = world.model_dump_json()
    assert C.tick_scientific_claims(world) == []
    assert C.prepare_adoption_effort(world) == {}
    assert world.model_dump_json() == before
    assert C.snapshot_summary(world) is None
    C.set_scientific_claims_enabled(world, True)
    state = world.scientific_claims
    C.set_scientific_claims_enabled(world, True)
    assert world.scientific_claims is state
    for host in ("techniques", "scholarship"):
        clone = world.model_copy(deep=True)
        setattr(clone, host, None)
        before = clone.model_dump_json()
        C.tick_scientific_claims(clone)
        assert C.prepare_adoption_effort(clone) == {}
        assert clone.model_dump_json() == before


def test_existing_hooks_never_call_runtime_with_flag_off(monkeypatch):
    world = _world()
    C.set_scientific_claims_enabled(world, False)
    def forbidden(*a, **kw):
        raise AssertionError("default-off science runtime invoked")
    monkeypatch.setattr(C, "prepare_adoption_effort", forbidden)
    monkeypatch.setattr(C, "tick_scientific_claims", forbidden)
    T.tick_techniques(world)
    from chronicler.scholarship import tick_scholarship
    tick_scholarship(world)


@pytest.mark.parametrize("warm_cache", [False, True])
def test_physical_evaluator_preserves_complete_state_rng_and_original_caches(warm_cache):
    world = _world()
    C.tick_scientific_claims(world)
    if warm_cache:
        world.techniques.practice_map()
        _ = world.civ_index_map
    technique_cache = world.techniques._cache
    cache_contents = (technique_cache.practice, technique_cache.region_index)
    private_ids = {key: id(value) for key, value in world.__pydantic_private__.items()}
    before = world.model_dump_json()
    py_rng, np_rng = random.getstate(), np.random.get_state()
    result = C.evaluate_trial(world, 0, world.scientific_claims.claims[0])
    assert result[0] > 0
    assert result[1] / result[0] == pytest.approx(1.05)
    assert world.model_dump_json() == before
    assert random.getstate() == py_rng
    after_np = np.random.get_state()
    assert after_np[0] == np_rng[0] and np.array_equal(after_np[1], np_rng[1])
    assert after_np[2:] == np_rng[2:]
    assert world.techniques._cache is technique_cache
    assert (technique_cache.practice, technique_cache.region_index) == cache_contents
    assert {key: id(value) for key, value in world.__pydantic_private__.items()} == private_ids


def test_evaluator_uses_existing_grain_physics_and_no_recipe_validity_label():
    world = _world()
    C.tick_scientific_claims(world)
    irrigation, masonry = world.scientific_claims.claims
    low, high, _ = C.evaluate_trial(world, 0, irrigation)
    assert high == pytest.approx(low * 1.05)
    masonry_control, masonry_treatment, _ = C.evaluate_trial(world, 0, masonry)
    assert masonry_control == masonry_treatment
    assert masonry_control == pytest.approx(high * 1.025 / 1.05)
    # Compare to the actual functions, with other farming practice held fixed.
    from chronicler.climate import get_climate_phase
    from chronicler.ecology import compute_resource_yields, goods_per_worker
    from chronicler.economy import compute_allocated_production
    region = world.regions[0]
    harvest = compute_resource_yields(region, 0, get_climate_phase(0, world.climate_config),
                                      0, world, deplete_reserves=False)
    ordinary = compute_allocated_production([0, 255, 255], [goods_per_worker(0, harvest[0]), 0., 0.], 4)
    assert C.evaluate_trial(world, 0, masonry)[0] == ordinary["grain"]
    world.scientific_claims.withhold_information = True
    world.scientific_claims.uninformative_tests = True
    assert C.evaluate_trial(world, 0, irrigation)[:2] == (low, high)


def test_trials_are_paid_dated_and_do_not_create_goods(monkeypatch):
    world = _world()
    physical = [r.model_dump_json() for r in world.regions]
    before = sum(c.treasury for c in world.civilizations)
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    _tick(world, 0)
    state = world.scientific_claims
    assert len(state.claims) == 2 and len(state.trials) == 2
    assert all(t.status == "running" and t.observed_control is None for t in state.trials)
    assert state.receipts == [] and C.confidence(world, 0, 0) == .5
    assert sum(c.treasury for c in world.civilizations) == before - 4
    _tick(world, 0)
    assert state.trial_spent == 4
    _tick(world, 1)
    assert [t.supports for t in state.trials] == [True, False]
    assert C.confidence(world, 0, 0) == pytest.approx(2/3)
    assert C.confidence(world, 0, 1) == pytest.approx(1/3)
    assert [r.model_dump_json() for r in world.regions] == physical


def test_paid_failure_cancellation_and_null_records_survive(monkeypatch):
    failed = _world()
    def fail(*a):
        raise ValueError("physical inputs invalid")
    monkeypatch.setattr(C, "evaluate_trial", fail)
    _tick(failed, 0)
    assert failed.scientific_claims.failed == 2
    assert all(t.status == "failed" and t.cost == 2 for t in failed.scientific_claims.trials)
    assert failed.civilizations[0].treasury == 196
    monkeypatch.undo()
    cancelled = _world()
    _tick(cancelled, 0)
    cancelled.scholarship.seats[0].fallen_turn = 1
    _tick(cancelled, 1)
    assert cancelled.scientific_claims.cancelled == 2
    assert cancelled.scientific_claims.receipts == []
    assert cancelled.civilizations[0].treasury == 196
    null = _world()
    null.regions[0].resource_suspensions[0] = 4
    _complete(null, monkeypatch)
    assert all(t.status == "completed" and not t.informative for t in null.scientific_claims.trials)
    assert C.confidence(null, 0, 0) == .5


def test_exact_projected_funding_floor_and_keep_watermark():
    world = _world(treasury=20)
    acc = StatAccumulator()
    # Clamp/truncation must match the real accumulator, including an applied
    # prefix; summing the deltas would incorrectly fund these requests.
    acc.add(0, world.civilizations[0], "treasury", -100, "keep")
    acc.apply_keep(world)
    acc.add(0, world.civilizations[0], "treasury", 23.9, "keep")
    _tick(world, 0, acc)
    assert len(world.scientific_claims.trials) == 1
    assert world.scientific_claims.unfunded_trials == 1
    assert world.scientific_claims.trial_spent == 2
    acc.apply_keep(world)
    assert world.civilizations[0].treasury == 21
    acc.apply_keep(world)
    assert world.civilizations[0].treasury == 21
    _tick(world, 1)
    assert len(world.scientific_claims.trials) == 1


def test_one_hop_dated_bounded_local_delivery(monkeypatch):
    world = _world()
    # Replace topology with a five-seat line: seat4 is beyond max three hops.
    for i, r in enumerate(world.regions):
        r.adjacencies = [world.regions[j].name for j in (i-1, i+1) if 0 <= j < 5]
    _tick(world, 0)
    assert {(p.seat, p.claim) for p in world.scientific_claims.proposals} == {(0, 0), (0, 1)}
    assert C.confidence(world, 1, 0) == .5
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    for turn in range(1, 9):
        _tick(world, turn)
        assert all(m.delivery_turn > turn for m in world.scientific_claims.messages)
        assert len(world.scientific_claims.messages) <= 1200
        if turn == 1:
            assert {p.seat for p in world.scientific_claims.proposals} == {0, 1}
            assert not any(r.seat == 1 for r in world.scientific_claims.receipts)
        if turn == 2:
            assert any(r.seat == 1 and r.received_turn == 2 for r in world.scientific_claims.receipts)
    assert {p.seat for p in world.scientific_claims.proposals} == {0, 1, 2, 3}
    assert {r.seat for r in world.scientific_claims.receipts} == {0, 1, 2, 3}
    assert C.confidence(world, 4, 0) == .5
    assert len({(r.seat, r.trial) for r in world.scientific_claims.receipts}) == len(world.scientific_claims.receipts)


@pytest.mark.parametrize("mismatch", ["soil", "water", "season", "climate", "no_grain", "nomadic"])
def test_context_mismatch_cannot_apply_received_evidence(mismatch, monkeypatch):
    world = _world()
    _complete(world, monkeypatch)
    state = world.scientific_claims
    # Give an institution receipts without pretending the contexts transfer.
    state.proposals += [ProposalReceipt(seat=1, claim=c.id, received_turn=1) for c in state.claims]
    state.receipts += [EvidenceReceipt(seat=1, trial=t.id, received_turn=1, sender=0) for t in state.trials]
    assert C.confidence(world, 1, 0) == pytest.approx(2/3)
    if mismatch in ("soil", "water"):
        setattr(world.regions[1].ecology, mismatch, .1)
    elif mismatch == "season":
        world.turn = 6
    elif mismatch == "climate":
        world.climate_config.phase_offset = 50
    elif mismatch == "no_grain":
        world.regions[1].resource_types[0] = 1
    else:
        from chronicler.nomads import set_nomads_enabled
        set_nomads_enabled(world, True)
        # Existing nomads state uses a per-civ list of subsistence modes.
        world.nomads.modes[0] = 2
    assert C.confidence(world, 1, 0) == .5
    assert not C._applicable(world, 1, state.claims[0])


def test_duplicate_source_and_environment_dependence_cap(monkeypatch):
    world = _world()
    _complete(world, monkeypatch)
    state = world.scientific_claims
    original = state.trials[0]
    alias = original.model_copy(deep=True)
    alias.id = 2
    alias.dependence_group = "pretend-independent-id"
    state.trials.append(alias)
    state.receipts += [EvidenceReceipt(seat=0, trial=0, received_turn=1, sender=0),
                       EvidenceReceipt(seat=0, trial=2, received_turn=1, sender=0)]
    assert C.confidence(world, 0, 0) == pytest.approx(2/3)
    dependent = original.model_copy(deep=True)
    dependent.id, dependent.source_data, dependent.supports = 3, "different-source", False
    state.trials.append(dependent)
    state.receipts.append(EvidenceReceipt(seat=0, trial=3, received_turn=1, sender=0))
    assert C.confidence(world, 0, 0) == .5  # average within one block, still n=1
    dependent.dependence_group = "another-year"
    assert C.confidence(world, 0, 0) == .5  # n=2 with one support/one rejection
    dependent.supports = True
    assert C.confidence(world, 0, 0) == .75
    dependent.control_output = 1e30
    dependent.treatment_output = 0.
    assert C.confidence(world, 0, 0) == .75  # diagnostics are not a policy input


def test_replication_is_planned_without_reading_first_result(monkeypatch):
    a, b = _world(), _world()
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    _run(a, 0, 2)
    _run(b, 0, 2)
    for trial in b.scientific_claims.trials:
        trial.supports = not trial.supports
    _run(a, 2, 14)
    _run(b, 2, 14)
    assert len(a.scientific_claims.trials) == len(b.scientific_claims.trials) == 4
    originals, replicas = a.scientific_claims.trials[:2], a.scientific_claims.trials[2:]
    assert [t.funded_turn for t in replicas] == [12, 12]
    assert all(t.seat != originals[t.claim].seat and t.parent == originals[t.claim].id for t in replicas)
    assert all(t.dependence_group != originals[t.claim].dependence_group for t in replicas)
    assert [(t.seat, t.claim, t.funded_turn, t.cost) for t in a.scientific_claims.trials] == [
        (t.seat, t.claim, t.funded_turn, t.cost) for t in b.scientific_claims.trials]


def test_controls_separate_information_from_spending(monkeypatch):
    informed, withheld, uninformative = _world(), _world(), _world()
    withheld.scientific_claims.withhold_information = True
    uninformative.scientific_claims.uninformative_tests = True
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    for world in (informed, withheld, uninformative):
        _run(world, 0, 25)
    reference = informed.scientific_claims
    for control in (withheld, uninformative):
        assert [c.treasury for c in control.civilizations] == [c.treasury for c in informed.civilizations]
        assert control.scientific_claims.trial_spent == reference.trial_spent == 8
        assert control.scientific_claims.effort_spent == reference.effort_spent
        assert [(t.claim, t.seat, t.funded_turn) for t in control.scientific_claims.trials] == [
            (t.claim, t.seat, t.funded_turn) for t in reference.trials]
        assert all(e.share == .5 for e in control.scientific_claims.last_effort)
        assert [(t.control_output, t.treatment_output) for t in control.scientific_claims.trials] == [
            (t.control_output, t.treatment_output) for t in reference.trials]
    assert withheld.scientific_claims.receipts == []
    assert C.confidence(withheld, 0, 0) == .5
    assert withheld.scientific_claims.withheld_results == 4
    assert all(t.informative and not t.supports for t in uninformative.scientific_claims.trials)
    assert C.confidence(uninformative, 0, 0) == .25  # ordinary posterior, two null observations
    assert any(e.share > .5 for e in reference.last_effort if e.recipe == "irrigation")


def test_registered_sham_measurements_do_not_discriminate_treatment_benefit():
    # Prospective amendment f5a1fae9 freezes this measurement-only domain and
    # criteria. Physical inputs are held fixed; no world outcomes are fitted.
    base = _world(seats=(0,))
    _tick(base, 0)
    support = {False: [0, 0], True: [0, 0]}
    different_sham_beliefs = 0
    for seed in range(1000, 2000):
        for sham in (False, True):
            world = base.model_copy(deep=True)
            world.seed, world.turn = seed, 1
            world.scientific_claims.uninformative_tests = sham
            C._finish_trials(world)
            for i, trial in enumerate(world.scientific_claims.trials):
                assert trial.informative
                support[sham][i] += int(trial.supports)
            if sham:
                different_sham_beliefs += C.confidence(world, 0, 0) != C.confidence(world, 0, 1)
    sham_difference = abs(support[True][0] - support[True][1]) / 1000
    informed_difference = (support[False][0] - support[False][1]) / 1000
    assert sham_difference <= .08
    assert informed_difference >= .25
    assert different_sham_beliefs > 0  # no forced equal confidence/no-evidence shortcut
    print(f"frozen seeds1000..1999: informed={support[False]}, sham={support[True]}, "
          f"distinct sham beliefs={different_sham_beliefs}")


def test_policy_cannot_read_hidden_physics_until_new_observations_arrive(monkeypatch):
    world = _world()
    _complete(world, monkeypatch)
    world.turn = 12
    changed = world.model_copy(deep=True)
    observed = [(t.observed_control, t.observed_treatment) for t in changed.scientific_claims.trials]
    before_confidence = C.confidence(world, 0, 0)
    before_effort = C.prepare_adoption_effort(world)
    before_output = C.evaluate_trial(changed, 0, changed.scientific_claims.claims[0])[:2]
    # This controlled intervention changes canonical physical truth, with
    # context, budget and received measurements held fixed. Policy cannot see it.
    monkeypatch.setitem(T.GRAIN_YIELD, "irrigation", -.05)
    after_output = C.evaluate_trial(changed, 0, changed.scientific_claims.claims[0])[:2]
    assert after_output != before_output
    assert [(t.observed_control, t.observed_treatment) for t in changed.scientific_claims.trials] == observed
    assert C.confidence(changed, 0, 0) == before_confidence
    assert C.prepare_adoption_effort(changed) == before_effort
    _tick(changed, 12)  # independently planned paid replication measures new physics
    _tick(changed, 13)
    assert C.confidence(changed, 0, 0) == before_confidence  # remote result not yet received
    _tick(changed, 14)
    assert C.confidence(changed, 0, 0) < before_confidence


def test_local_only_keeps_local_observations_and_stops_remote_protocols(monkeypatch):
    world = _world()
    world.scientific_claims.transmission_enabled = False
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    _run(world, 0, 25)
    state = world.scientific_claims
    assert len(state.trials) == 2
    assert {r.seat for r in state.receipts} == {0}
    assert C.confidence(world, 0, 0) == pytest.approx(2/3)
    assert C.confidence(world, 1, 0) == .5
    assert state.messages == []


def test_fixed_paid_allowance_is_bounded_and_exactly_once(monkeypatch):
    world = _world(seats=(0, 0, 1))
    _complete(world, monkeypatch)
    world.turn = 12
    before = world.civilizations[0].treasury
    acc = StatAccumulator()
    grants = C.prepare_adoption_effort(world, acc)
    assert sum(grants.values()) <= .01 * 2
    assert sum(v for (r, k), v in grants.items() if r == 0) == pytest.approx(.01)
    assert grants[0, K["irrigation"]] > grants[0, K["masonry"]]
    assert C.prepare_adoption_effort(world, acc) == grants
    assert sum(e.paid for e in world.scientific_claims.last_effort) == world.scientific_claims.effort_spent
    acc.apply_keep(world)
    assert world.civilizations[0].treasury == before - world.scientific_claims.effort_spent
    world.turn = 13
    assert C.prepare_adoption_effort(world) == {}


def test_effort_uses_existing_prerequisites_suitability_and_growth_kernel():
    world = _world()
    ctrl = T._controllers(world, T._civ_indices(world))
    links = {i: {} for i in range(len(world.regions))}
    suit = T._suitability(world, ctrl, links)
    base, _ = T._update_practice(world, world.techniques, ctrl, links, suit)
    grant = {(0, K["irrigation"]): .01, (0, K["masonry"]): .01}
    paid, _ = T._update_practice(world, world.techniques, ctrl, links, suit, claims_effort=grant)
    assert paid[0, K["irrigation"]] > base[0, K["irrigation"]]
    assert paid[1, K["irrigation"]] == base[1, K["irrigation"]]
    # No prerequisite irrigation at region0: an effort grant cannot grow ox plough.
    world.techniques.rows = [row for row in world.techniques.rows if row[:2] != (0, K["irrigation"])]
    world.techniques.rows.append((0, K["ox_plough"], .5, -1, 6, 0))
    without, _ = T._update_practice(world, world.techniques, ctrl, links, suit)
    with_grant, _ = T._update_practice(world, world.techniques, ctrl, links, suit,
                                      claims_effort={(0, K["ox_plough"]): .01})
    assert with_grant[0, K["ox_plough"]] == without[0, K["ox_plough"]]
    # Above the ordinary suitability cap, effort cannot override or reverse decay.
    suit[0][K["masonry"]] = False
    without, _ = T._update_practice(world, world.techniques, ctrl, links, suit)
    with_grant, _ = T._update_practice(world, world.techniques, ctrl, links, suit,
                                      claims_effort={(0, K["masonry"]): .01})
    assert with_grant[0, K["masonry"]] == without[0, K["masonry"]]


def test_resume_replays_identically_and_keeps_bounds(monkeypatch):
    uninterrupted, split = _world(), _world()
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    _run(uninterrupted, 0, 30)
    _run(split, 0, 1)  # queued proposal and running funded experiments
    split = WorldState.model_validate_json(split.model_dump_json())
    _run(split, 1, 13)  # replication paid but not yet delivered
    split = WorldState.model_validate_json(split.model_dump_json())
    _run(split, 13, 30)
    assert split.model_dump_json() == uninterrupted.model_dump_json()
    assert len(split.scientific_claims.trials) == 4
    assert len(split.scientific_claims.seat_ids) <= 20
    assert len(split.scientific_claims.claims) <= 20
    assert len(split.scientific_claims.receipts) <= 800
    assert C.snapshot_summary(split)["trial_spent"] == 8


def test_exact_checkpoint_keeps_running_trials_messages_and_measurement_rng(tmp_path):
    from chronicler.run_checkpoint import save_world, load_world
    uninterrupted, split = _world(), _world()
    _run(uninterrupted, 0, 15)
    _run(split, 0, 1)
    checkpoint = tmp_path / "running.ckpt"
    save_world(checkpoint, split)
    split = load_world(checkpoint)
    assert isinstance(split, WorldState)
    assert len(split.scientific_claims.messages) > 0
    assert all(t.status == "running" for t in split.scientific_claims.trials)
    before_rng = random.getstate()
    _run(split, 1, 15)
    assert random.getstate() == before_rng
    assert split.model_dump_json() == uninterrupted.model_dump_json()


def test_no_early_or_unreceived_diagnostics_in_policy(monkeypatch):
    world = _world()
    _complete(world, monkeypatch)
    state = world.scientific_claims
    state.receipts = []
    state.proposals.append(ProposalReceipt(seat=1, claim=0, received_turn=1))
    assert C.confidence(world, 0, 0) == .5
    state.receipts.append(EvidenceReceipt(seat=1, trial=0, received_turn=2, sender=0))
    assert C.confidence(world, 1, 0) == .5
    world.turn = 2
    assert C.confidence(world, 1, 0) == pytest.approx(2/3)
    state.withhold_information = True
    assert C.confidence(world, 1, 0) == .5


def test_delivery_expiry_and_fallen_or_local_only_destinations(monkeypatch):
    expired, fallen, stopped = _world(), _world(), _world()
    for world in (expired, fallen, stopped):
        _tick(world, 0)
        assert world.scientific_claims.messages
    _tick(expired, 7)
    assert expired.scientific_claims.expired_messages > 0
    assert {p.seat for p in expired.scientific_claims.proposals} == {0}
    fallen.scholarship.seats[1].fallen_turn = 1
    _tick(fallen, 1)
    assert not any(p.seat == 1 for p in fallen.scientific_claims.proposals)
    stopped.scientific_claims.transmission_enabled = False
    _tick(stopped, 1)
    assert {p.seat for p in stopped.scientific_claims.proposals} == {0}
    assert stopped.scientific_claims.messages == []


def test_snapshot_is_historical_detached_and_read_only(monkeypatch):
    world = _world()
    assert C.snapshot_summary(world) is None  # no completed turn yet
    _complete(world, monkeypatch)
    world.turn = 2  # completed-turn boundary, as production capture sees it
    before = world.model_dump_json()
    summary = C.snapshot_summary(world)
    assert summary["propositions"][0]["recipe"] == "irrigation"
    summary["propositions"][0]["context"]["soil_band"] = 0
    assert world.model_dump_json() == before
    from chronicler.expansion_features import expansion_snapshot_fields
    fields = expansion_snapshot_fields(world)
    assert fields["scientific_claims"]["trial_spent"] == 4
    from chronicler.models import TurnSnapshot
    # Production summary is an optional snapshot dictionary, not a live view.
    snapshot = TurnSnapshot(turn=world.turn, civ_stats={}, region_control={}, relationships={},
                            scientific_claims=fields["scientific_claims"])
    _tick(world, 2)
    assert snapshot.scientific_claims["completed"] == 2
    assert snapshot.scientific_claims["source_turn"] == 1
    assert len(snapshot.scientific_claims["trials_resolved"]) == 2
    assert C.snapshot_summary(world) is None  # future in-progress tick
    world.turn = 4
    assert C.snapshot_summary(world) is None  # stale tick


def test_library_and_unsupported_recipe_do_not_seed_claims():
    world = _world()
    for seat in world.scholarship.seats:
        seat.kind = LIBRARY
    _tick(world, 0)
    assert world.scientific_claims.claims == []
    world = _world()
    world.techniques.rows = [row for row in world.techniques.rows if row[1] != K["masonry"]]
    _tick(world, 0)
    assert world.scientific_claims.claims == []


def test_pilot_registers_at_most_twenty_seats_without_recycling_fallen_ids():
    world = _world(seats=(0,) * 30)
    _tick(world, 0)
    assert world.scientific_claims.seat_ids == list(range(20))
    assert len(world.scientific_claims.claims) == 2
    for seat in world.scholarship.seats[:20]:
        seat.fallen_turn = 1
    _tick(world, 1)
    assert world.scientific_claims.seat_ids == list(range(20))
    assert all(t.status == "cancelled" for t in world.scientific_claims.trials)


def test_full_turn_hooks_and_exact_continuation_use_paid_runtime(tmp_path):
    from chronicler.models import ActionType
    from chronicler.run_checkpoint import save_world, load_world
    from chronicler.simulation import run_turn
    uninterrupted, split = _world(), _world()
    # A bounded stable-context fixture isolates real phase/accumulator wiring;
    # seasonal transfer is still strict and does not promise world exposure.
    for world in (uninterrupted, split):
        world.tuning_overrides["climate.trend_share"] = 1.
        for r in world.regions:
            r.terrain, r.population, r.carrying_capacity = "plains", 60, 1000
    def advance(world, count):
        for _ in range(count):
            run_turn(world, lambda *args: ActionType.DEVELOP, lambda *args: "",
                     seed=world.seed + world.turn)
            summary = C.snapshot_summary(world)
            assert summary["source_turn"] == world.turn - 1
    advance(uninterrupted, 14)
    advance(split, 1)
    path = tmp_path / "full-turn.ckpt"
    save_world(path, split)
    split = load_world(path)
    advance(split, 13)
    assert split.model_dump_json() == uninterrupted.model_dump_json()
    assert split.scientific_claims.trial_spent == 8
    assert split.scientific_claims.effort_spent > 0
