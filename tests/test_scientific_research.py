"""Finite paid research mechanics, not natural-world benefit qualification."""
from __future__ import annotations

from copy import deepcopy
import pickle

import pytest

from chronicler import scientific_claims as C
from chronicler.accumulator import StatAccumulator
from chronicler.scholarship_state import ACADEMY, Seat
from chronicler.scientific_research import capacities, set_research_agendas_enabled, validate_state
from chronicler.scientific_claims_state import FUNDED_CONTEXT_PUBLICATION
from test_scientific_claims import _world


def research_world():
    world = _world(seats=(0, 1), treasury=10000)
    world.climate_config.period = 10000
    world.scientific_claims.publication_rule = FUNDED_CONTEXT_PUBLICATION
    set_research_agendas_enabled(world, True)
    return world


def advance(world, start, stop):
    events = []
    for turn in range(start, stop):
        world.turn = turn
        C.prepare_adoption_effort(world)
        events += C.tick_scientific_claims(world)
    world.turn = stop
    return events


def test_research_goes_beyond_four_trials_with_stable_topics_and_retained_knowledge():
    world = research_world()
    advance(world, 0, 24)
    state = world.scientific_claims
    first = [claim.model_dump() for claim in state.claims]
    old_trials = [trial.model_dump() for trial in state.trials]
    old_receipts = [receipt.model_dump() for receipt in state.receipts]
    advance(world, 24, 77)
    assert len(state.trials) == 14 and state.trial_spent == 28
    assert len(state.claims) == 4 and [claim.model_dump() for claim in state.claims[:2]] == first
    assert [trial.model_dump() for trial in state.trials[:4]] == old_trials
    assert [receipt.model_dump() for receipt in state.receipts[:len(old_receipts)]] == old_receipts
    assert [cycle.opened_turn for cycle in state.research_agendas.cycles] == [0, 25, 50, 75]
    assert [cycle.origin_seat for cycle in state.research_agendas.cycles] == [0, 1, 0, 1]
    assert state.research_agendas.cycles[1].claims == [0, 1]
    assert state.cohort == 0 and state.started_turn == 0
    assert sum(civ.treasury for civ in world.civilizations) == 20000 - state.trial_spent - state.effort_spent
    assert len(C.snapshot_summary(world)["beliefs"]) <= 4


@pytest.mark.parametrize("entry", [C.tick_scientific_claims, C.prepare_adoption_effort,
    lambda w: C.confidence(w, 0, 0), lambda w: set_research_agendas_enabled(w, True)])
@pytest.mark.parametrize("same_birth", [True, False])
def test_reset_host_never_inherits_archive_at_reused_seat_zero(entry, same_birth):
    from chronicler.scholarship import set_scholarship_enabled
    world = research_world()
    advance(world, 0, 13)  # cached paid grants and real retained local receipts
    old_seats = deepcopy(world.scholarship.seats)
    old_receipts = [r.model_dump() for r in world.scientific_claims.receipts]
    set_scholarship_enabled(world, False)
    set_scholarship_enabled(world, True)
    world.scholarship.seats.extend(old_seats)
    if not same_birth:
        world.scholarship.seats[0].founded_turn = world.turn
        world.scholarship.seats[0].name = "Replacement academy"
    assert world.scholarship.scientific_research_identity is None
    before = pickle.dumps(world, protocol=5)
    with pytest.raises(ValueError, match="registry does not match"):
        entry(world)
    assert pickle.dumps(world, protocol=5) == before
    assert [r.model_dump() for r in world.scientific_claims.receipts] == old_receipts


@pytest.mark.parametrize("field,value", [("founded_turn", 2), ("region", 2),
    ("name", "A different birth"), ("founder", 0), ("kind", 1)])
def test_changed_enrolled_birth_is_rejected_before_guards_or_cached_grants(field, value):
    world = research_world()
    advance(world, 0, 13)
    setattr(world.scholarship.seats[0], field, value)
    before = pickle.dumps(world, protocol=5)
    with pytest.raises(ValueError, match="birth|Input should be"):
        C.prepare_adoption_effort(world)
    assert pickle.dumps(world, protocol=5) == before


def test_bound_host_restores_exactly_but_absent_host_only_allows_dormancy_and_pause():
    from chronicler.models import WorldState
    from chronicler.scholarship import set_scholarship_enabled
    world = research_world()
    advance(world, 0, 2)
    for restored in (WorldState.model_validate_json(world.model_dump_json()),
                     pickle.loads(pickle.dumps(world, protocol=5)), world.model_copy(deep=True)):
        validate_state(restored)
        assert restored.scholarship.scientific_research_identity.seal == restored.scientific_claims.research_agendas.host_seal
        advance(restored, 2, 14)
    set_scholarship_enabled(world, False)
    before = pickle.dumps(world, protocol=5)
    assert C.tick_scientific_claims(world) == [] and C.prepare_adoption_effort(world) == {}
    assert C.confidence(world, 0, 0) == .5 and C.snapshot_summary(world) is None
    assert pickle.dumps(world, protocol=5) == before
    set_research_agendas_enabled(world, False)
    assert world.scientific_claims.research_agendas.enabled is False
    assert world.scientific_claims.receipts
    before = pickle.dumps(world, protocol=5)
    with pytest.raises(ValueError):
        set_research_agendas_enabled(world, True)
    assert pickle.dumps(world, protocol=5) == before


def test_mutable_academy_status_does_not_rewrite_birth_and_new_admission_is_distinct():
    world = research_world()
    advance(world, 0, 2)
    plan = world.scientific_claims.research_agendas
    original = [b.model_dump() for b in plan.academy_births]
    seat = world.scholarship.seats[0]
    seat.lord, seat.level, seat.scholars, seat.fallen_turn = 1, 0, 0., 2
    world.scholarship.seats.append(Seat(region=0, name="New seat", founded_turn=2, founder=1))
    advance(world, 2, 3)
    assert [b.model_dump() for b in plan.academy_births[:2]] == original
    assert plan.academy_births[-1].seat == 2 and plan.academy_births[-1].founded_turn == 2
    assert all(r.seat != 2 for r in world.scientific_claims.receipts)


def test_same_canonical_question_renews_at_another_origin_after_first_origin_falls():
    world = research_world()
    advance(world, 0, 24)
    state = world.scientific_claims
    first = [claim.model_dump() for claim in state.claims]
    world.scholarship.seats[0].fallen_turn = 24
    advance(world, 24, 27)
    assert len(state.claims) == 2 and [claim.model_dump() for claim in state.claims] == first
    cycle = state.research_agendas.cycles[1]
    assert cycle.origin_seat == 1 and cycle.participants == [1]
    assert all(state.trials[tid].seat == 1 for tid in cycle.trials)
    assert all(state.trials[tid].parent == -1 for tid in cycle.trials)
    assert all(p.agenda_id == 1 for p in state.proposals if p.received_turn == 25)


def test_pause_retains_archive_and_restarts_one_actual_cycle_without_backfill():
    world = research_world()
    advance(world, 0, 5)
    state = world.scientific_claims
    retained = [receipt.model_dump() for receipt in state.receipts]
    set_research_agendas_enabled(world, False)
    advance(world, 5, 40)
    assert len(state.trials) == 2 and len(state.research_agendas.cycles) == 1
    assert [receipt.model_dump() for receipt in state.receipts] == retained
    assert state.effort_spent > 0 and state.research_agendas.enabled is False
    set_research_agendas_enabled(world, True)
    advance(world, 40, 41)
    assert [cycle.opened_turn for cycle in state.research_agendas.cycles] == [0, 40]
    assert state.research_agendas.next_open_turn == 65
    before = pickle.dumps(world, protocol=5)
    world.turn = 40
    assert C.tick_scientific_claims(world) == []
    world.turn = 41
    assert pickle.dumps(world, protocol=5) == before


def test_paid_running_receipt_reservations_survive_funding_close_and_use_actual_publication_date():
    world = research_world()
    advance(world, 0, 1)
    world.turn = 100  # no science ticks while the hosts are dormant
    set_research_agendas_enabled(world, False)
    C.tick_scientific_claims(world)
    state = world.scientific_claims
    assert all(trial.resolved_turn == 100 for trial in state.trials)
    assert state.research_agendas.cycles[0].closed_turn == 100
    cap = capacities(world, state.research_agendas)
    assert cap["trials"] == dict(used=2, reserved=0, limit=40)
    assert cap["receipts"] == dict(used=2, reserved=2, limit=800)
    assert cap["messages"]["used"] == 2 and cap["messages"]["reserved"] == 0
    assert all(message.expires_turn == 106 for message in state.messages)
    advance(world, 101, 102)
    assert len(state.receipts) == 4 and capacities(world, state.research_agendas)["receipts"]["reserved"] == 0


@pytest.mark.parametrize("entry", [C.tick_scientific_claims, C.prepare_adoption_effort])
def test_invalid_archive_rejection_precedes_tick_and_effort_mutation(entry):
    world = research_world()
    advance(world, 0, 2)
    world.scientific_claims.trials[0].cost = 3
    before = pickle.dumps(world, protocol=5)
    with pytest.raises(ValueError):
        entry(world)
    assert pickle.dumps(world, protocol=5) == before


def test_finite_capacity_stops_before_new_debit_and_keeps_all_past_records():
    world = research_world()
    events = advance(world, 0, 261)
    state = world.scientific_claims
    assert len(state.trials) == 40 and state.trial_spent == 80
    assert len(state.research_agendas.cycles) == 10
    assert state.research_agendas.blocked_reason == "cycle_capacity"
    assert state.research_agendas.blocked_turn == 250
    assert sum(e.event_type == "scientific_research_capacity_blocked" for e in events) == 1
    assert sum(civ.treasury for civ in world.civilizations) == 20000 - state.trial_spent - state.effort_spent
    assert len({trial.id for trial in state.trials}) == 40 and state.cohort == 0
    assert all(row["used"] + row["reserved"] <= row["limit"]
               for row in capacities(world, state.research_agendas).values())


def test_partial_next_turn_effort_is_never_relabelled_as_prior_snapshot():
    world = research_world()
    advance(world, 0, 12)
    assert C.snapshot_summary(world) is not None
    C.prepare_adoption_effort(world)  # Phase4 source12 while last tick is source11
    assert C.snapshot_summary(world) is None


@pytest.mark.parametrize("enabled", [False, True])
def test_prospective_pause_or_resume_never_leaks_into_prior_completed_source(enabled):
    world = research_world()
    if enabled:
        set_research_agendas_enabled(world, False)
    advance(world, 0, 2)
    assert C.snapshot_summary(world)["research_agendas"]["enabled"] is not enabled
    set_research_agendas_enabled(world, enabled)
    plan = world.scientific_claims.research_agendas
    assert plan.policy_changed_turn == 2 and C.snapshot_summary(world) is None
    advance(world, 2, 3)
    assert C.snapshot_summary(world)["source_turn"] == 2
    assert C.snapshot_summary(world)["research_agendas"]["enabled"] is enabled
    set_research_agendas_enabled(world, enabled)  # same setting is not a new change
    assert plan.policy_changed_turn == 2 and C.snapshot_summary(world) is not None


def test_lazy_allocation_claim_is_the_actual_phase_four_canonical_topic():
    world = research_world()
    advance(world, 0, 13)
    state = world.scientific_claims
    assert state.last_effort and all(row.claim_id is not None for row in state.last_effort)
    for row in state.last_effort:
        assert state.claims[row.claim_id].recipe == row.recipe
    assert all("claim_id" in row for row in C.snapshot_summary(world)["allocations"])


def test_exact_python_checkpoint_with_renewed_question_and_running_trial(tmp_path):
    from chronicler.run_checkpoint import save_world, load_world
    world = research_world()
    advance(world, 0, 26)
    path = tmp_path / "agenda.ckpt"
    save_world(path, world)
    resumed = load_world(path)
    advance(world, 26, 80)
    advance(resumed, 26, 80)
    assert resumed.model_dump_json() == world.model_dump_json()


@pytest.mark.parametrize("change", ["activation", "policy", "next_open", "tick", "effort", "duplicate_message"])
def test_inconsistent_clock_or_duplicate_message_is_rejected_without_mutation(change):
    world = research_world()
    advance(world, 0, 1)
    state = world.scientific_claims
    if change == "activation":
        state.research_agendas.enabled_turn = 2
    elif change == "policy":
        state.research_agendas.policy_changed_turn = 2
    elif change == "next_open":
        state.research_agendas.next_open_turn = 1
    elif change == "tick":
        state.last_tick_turn = 2
    elif change == "effort":
        state.last_effort_turn = 2
    else:
        state.messages.append(deepcopy(state.messages[0]))
    before = pickle.dumps(world, protocol=5)
    with pytest.raises(ValueError):
        C.tick_scientific_claims(world)
    assert pickle.dumps(world, protocol=5) == before


def test_legacy_adoption_keeps_late_funding_and_dynamic_recipient_exception():
    world = _world(seats=(0,), treasury=20)
    world.climate_config.period = 10000
    world.turn = 4
    C.tick_scientific_claims(world)
    world.scholarship.seats.append(Seat(region=1, kind=ACADEMY, name="Later academy",
                                       founded_turn=50, lord=0, scholars=10.))
    world.turn = 50
    C.tick_scientific_claims(world)
    for civ in world.civilizations:
        civ.treasury = 1000
    world.turn = 100
    C.tick_scientific_claims(world)
    world.turn = 101
    before = [trial.model_dump() for trial in world.scientific_claims.trials]
    set_research_agendas_enabled(world, True)
    plan = world.scientific_claims.research_agendas
    assert plan.cycles[0].legacy_adopted and not plan.cycles[0].opening_roster_complete
    assert plan.cycles[0].closed_turn == 101 and plan.next_open_turn == 126
    assert [trial.model_dump() for trial in world.scientific_claims.trials] == before
    advance(world, 101, 103)
    state = world.scientific_claims
    assert all(trial.funded_turn == 100 and trial.resolved_turn == 101 for trial in state.trials)
    assert any(receipt.seat == 1 for receipt in state.receipts)
    summary = C.snapshot_summary(world)["research_agendas"]["cycles"][0]
    assert summary["original_deadline"] is summary["funding_deadline"] is None
    assert summary["opening_roster_scope"] == "observed_at_legacy_activation"


def test_cross_cycle_aliases_and_same_block_readings_do_not_gain_independence(monkeypatch):
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    world = _world(seats=(0,), treasury=10000)
    world.climate_config.period = 10000
    world.scientific_claims.publication_rule = FUNDED_CONTEXT_PUBLICATION
    set_research_agendas_enabled(world, True)
    advance(world, 0, 27)
    world.turn = 36  # original context returns; no new measurement is added
    state = world.scientific_claims
    first, second = [trial for trial in state.trials if trial.claim == 0]
    assert C.confidence(world, 0, 0) == pytest.approx(3 / 4)
    second_source = second.source_data
    second.source_data = first.source_data  # adversarial alias of one physical source
    assert C.confidence(world, 0, 0) == pytest.approx(2 / 3)
    second.source_data = second_source
    second.dependence_group = first.dependence_group
    second.supports = False  # distinct contradictory declared reading in one block
    groups, _ = C._received_groups(world, 0, state.claims[0])
    assert len(groups) == 1 and C.confidence(world, 0, 0) == .5


def test_context_a_to_b_to_a_restores_retained_evidence_without_new_measurement(monkeypatch):
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    world = research_world()
    advance(world, 0, 73)
    old = C.confidence(world, 0, 0)
    assert old > .5
    advance(world, 73, 78)
    assert C.confidence(world, 0, 0) == .5
    receipts = [row.model_dump() for row in world.scientific_claims.receipts]
    world.turn = 84
    assert C.confidence(world, 0, 0) == old
    assert [row.model_dump() for row in world.scientific_claims.receipts] == receipts


def test_phase_ten_publication_does_not_rewrite_earlier_phase_four_allocation(monkeypatch):
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    world = research_world()
    advance(world, 0, 1)
    world.turn = 12  # late publication after host dormancy, on an eligible paid turn
    C.prepare_adoption_effort(world)
    before = [row.model_dump() for row in world.scientific_claims.last_effort]
    assert before and all(row["confidence"] == .5 for row in before)
    C.tick_scientific_claims(world)
    world.turn = 13
    snapshot = C.snapshot_summary(world)
    assert snapshot["allocations"] == before
    assert {row["confidence"] for row in snapshot["beliefs"]} == {1 / 3, 2 / 3}
    assert all(row["claim_id"] in (0, 1) for row in before)


@pytest.mark.parametrize("income_already_applied", [False, True])
def test_reserved_row_capacity_does_not_earmark_or_invent_projected_cash(income_already_applied):
    world = _world(seats=(0,), treasury=20)
    set_research_agendas_enabled(world, True)
    acc = StatAccumulator()
    acc.add(0, world.civilizations[0], "treasury", -100, "keep")
    acc.apply_keep(world)
    acc.add(0, world.civilizations[0], "treasury", 23.9, "keep")
    if income_already_applied:
        acc.apply_keep(world)
    C.tick_scientific_claims(world, acc)
    state = world.scientific_claims
    assert len(state.trials) == 1 and state.trial_spent == 2
    assert capacities(world, state.research_agendas)["trials"]["reserved"] == 3
    assert state.research_agendas.cycles[0].slot_reasons["original:1"] == "projected_treasury_floor"
    before = pickle.dumps((world, acc), protocol=5)
    assert C.tick_scientific_claims(world, acc) == []
    assert pickle.dumps((world, acc), protocol=5) == before
    acc.apply_keep(world)
    assert world.civilizations[0].treasury == 21
    acc.apply_keep(world)
    assert world.civilizations[0].treasury == 21


@pytest.mark.parametrize("arm,expected_trials,expected_receipts", [
    ("normal", 10, None), ("withheld", 10, 0), ("no_transmission", 6, 6), ("uninformative", 10, None)])
def test_controls_remain_ordinary_in_fixed_eligibility_cycles(arm, expected_trials, expected_receipts):
    world = research_world()
    state = world.scientific_claims
    state.withhold_information = arm == "withheld"
    state.transmission_enabled = arm != "no_transmission"
    state.uninformative_tests = arm == "uninformative"
    advance(world, 0, 55)
    assert len(state.trials) == expected_trials and state.trial_spent == 2 * expected_trials
    if expected_receipts is not None:
        assert len(state.receipts) == expected_receipts
    if arm == "no_transmission":
        assert all(trial.parent < 0 for trial in state.trials)
        # An old same-topic proposal must not authorize a new-cycle replication.
        assert state.research_agendas.cycles[1].claims == [0, 1]


@pytest.mark.parametrize("bad", ["nan", "negative_confidence", "paid", "duplicate", "wrong_region", "bool_seat", "counter"])
def test_invalid_cached_grants_are_rejected_without_mutating_world_or_accumulator(bad):
    world = research_world()
    advance(world, 0, 13)
    world.turn = 12  # request the same already-paid source; cached grants must be validated
    state = world.scientific_claims
    if bad == "nan":
        state.last_effort[0].share = float("nan")
    elif bad == "negative_confidence":
        state.last_effort[0].confidence = -.1
    elif bad == "paid":
        state.last_effort[0].paid = 2
    elif bad == "duplicate":
        state.last_effort.append(deepcopy(state.last_effort[0]))
    elif bad == "wrong_region":
        state.last_effort[0].region = 4
    elif bad == "bool_seat":
        next(row for row in state.last_effort if row.seat == 1).seat = True
    else:
        state.effort_spent = -1
    acc = StatAccumulator()
    before = pickle.dumps((world, acc), protocol=5)
    with pytest.raises(ValueError):
        C.prepare_adoption_effort(world, acc)
    assert pickle.dumps((world, acc), protocol=5) == before


def test_phase_four_topic_identity_survives_context_switch_to_other_known_topic_before_phase_ten():
    world = research_world()
    advance(world, 0, 25)
    for region in world.regions:
        region.ecology.soil = .1
    advance(world, 25, 28)
    assert len(world.scientific_claims.claims) == 4
    world.turn = 36
    for region in world.regions:
        region.ecology.soil = .8
    C.prepare_adoption_effort(world)
    paid = [row.model_dump() for row in world.scientific_claims.last_effort]
    assert {row["claim_id"] for row in paid} == {0, 1}
    for region in world.regions:
        region.ecology.soil = .1
    C.tick_scientific_claims(world)
    world.turn = 37
    snapshot = C.snapshot_summary(world)
    assert {row["claim"] for row in snapshot["beliefs"]} == {2, 3}
    assert snapshot["allocations"] == paid


def test_impossible_overlapping_historical_funding_windows_fail_before_mutation():
    world = research_world()
    advance(world, 0, 51)
    plan = world.scientific_claims.research_agendas
    plan.cycles[0].closed_turn = 50
    before = pickle.dumps(world, protocol=5)
    with pytest.raises(ValueError, match="overlap"):
        C.tick_scientific_claims(world)
    assert pickle.dumps(world, protocol=5) == before


def test_new_academy_does_not_inherit_or_receive_closed_cohort_results_even_before_expiry():
    world = _world(seats=(0,), treasury=10000)
    world.climate_config.period = 10000
    world.scientific_claims.publication_rule = FUNDED_CONTEXT_PUBLICATION
    set_research_agendas_enabled(world, True)
    advance(world, 0, 2)
    world.scholarship.seats.append(Seat(region=1, kind=ACADEMY, name="New academy",
                                       founded_turn=2, lord=0, scholars=10.))
    advance(world, 2, 26)
    state = world.scientific_claims
    assert state.research_agendas.cycles[0].participants == [0]
    assert state.research_agendas.cycles[1].origin_seat == 1
    assert state.research_agendas.cycles[1].claims == [0, 1]
    assert all(receipt.seat == 0 for receipt in state.receipts)
    assert C.confidence(world, 1, 0) == .5
    assert all(state.trials[tid].seat == 1 for tid in state.research_agendas.cycles[1].trials)


def test_running_receipts_reserve_despite_withholding_but_completed_withheld_results_never_reseed():
    world = research_world()
    state = world.scientific_claims
    state.withhold_information = True
    advance(world, 0, 1)
    assert capacities(world, state.research_agendas)["receipts"]["reserved"] == 8
    set_research_agendas_enabled(world, False)
    advance(world, 1, 2)
    assert all(trial.status == "completed" for trial in state.trials) and state.receipts == []
    assert capacities(world, state.research_agendas)["receipts"]["reserved"] == 0
    state.withhold_information = False
    advance(world, 2, 5)
    assert state.receipts == []  # current control cannot recreate an old withheld publication


def test_activation_validates_before_attaching_any_lazy_backing():
    world = _world(seats=(0, 1))
    C.tick_scientific_claims(world)
    world.scientific_claims.trials[0].cost = 3
    before = pickle.dumps(world, protocol=5)
    with pytest.raises(ValueError):
        set_research_agendas_enabled(world, True)
    assert pickle.dumps(world, protocol=5) == before
    assert "_research_agendas" not in world.scientific_claims.__dict__


def test_explicit_pause_of_absent_research_is_a_raw_state_noop():
    world = _world()
    before = pickle.dumps(world, protocol=5)
    set_research_agendas_enabled(world, False)
    assert pickle.dumps(world, protocol=5) == before


def test_first_new_academy_paid_allocation_cites_its_actual_renewed_question():
    world = _world(seats=(0,), treasury=10000)
    world.climate_config.period = 10000
    world.scientific_claims.withhold_information = True
    world.scientific_claims.publication_rule = FUNDED_CONTEXT_PUBLICATION
    set_research_agendas_enabled(world, True)
    advance(world, 0, 2)
    world.scholarship.seats.append(Seat(region=1, kind=ACADEMY, name="Later academy",
                                       founded_turn=2, lord=0, scholars=10.))
    advance(world, 2, 36)
    events = []
    C.prepare_adoption_effort(world, events=events)
    announcement = world.scientific_claims.research_agendas.cycles[1].announcement_event_id
    assert events and all(announcement in event.causes for event in events)
    assert world.scientific_claims.receipts == []
