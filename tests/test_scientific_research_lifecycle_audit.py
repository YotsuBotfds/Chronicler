"""Legacy-source counterexamples for the proposed finite research contract.

These checks precede recurrence implementation and qualify no world effects.
"""
from __future__ import annotations

from chronicler import scientific_claims as C
from chronicler.scholarship_state import ACADEMY, Seat
from test_scientific_claims import _world, _tick


def test_legacy_research_stops_at_four_trials_despite_new_academy_and_context_returns():
    world = _world(seats=(0, 1), treasury=10000)
    original_ids = None
    for turn in range(61):
        if turn == 24:
            world.scholarship.seats.append(Seat(region=2, kind=ACADEMY, name="Later academy",
                                               founded_turn=24, lord=1, scholars=10.))
        world.turn = turn
        C.prepare_adoption_effort(world)
        C.tick_scientific_claims(world)
        if turn == 23:
            original_ids = [(trial.id, trial.claim, trial.parent, trial.funded_turn)
                            for trial in world.scientific_claims.trials]
    state = world.scientific_claims
    assert len(state.claims) == 2 and len(state.trials) == 4
    assert state.trial_spent == sum(trial.cost for trial in state.trials) == 8
    assert [(trial.id, trial.claim, trial.parent, trial.funded_turn) for trial in state.trials] == original_ids
    assert 2 in state.seat_ids and not any(trial.seat == 2 for trial in state.trials)
    assert state.effort_spent > 0  # research stops, existing paid adoption can continue
    assert state.cohort == 0 and state.started_turn == 0


def test_failed_legacy_measurements_consume_the_same_four_paid_slots(monkeypatch):
    world = _world(seats=(0, 1), treasury=10000)
    before = sum(civ.treasury for civ in world.civilizations)
    def fail_measurement(*args):
        raise ValueError("controlled measurement failure")
    monkeypatch.setattr(C, "evaluate_trial", fail_measurement)
    for turn in range(49):
        _tick(world, turn)
    state = world.scientific_claims
    assert len(state.claims) == 2 and len(state.trials) == 4
    assert all(trial.status == "failed" for trial in state.trials)
    assert state.failed == 4 and state.receipts == []
    assert state.trial_spent == before - sum(civ.treasury for civ in world.civilizations) == 8
    assert [trial.id for trial in state.trials] == [0, 1, 2, 3]


def test_manual_cohort_rotation_changes_an_already_funded_legacy_measurement():
    world = _world(seats=(0,))
    _tick(world, 0)
    rotated = world.model_copy(deep=True)
    rotated.scientific_claims.cohort += 1
    _tick(world, 1)
    _tick(rotated, 1)
    original = [(trial.observed_control, trial.observed_treatment) for trial in world.scientific_claims.trials]
    changed = [(trial.observed_control, trial.observed_treatment) for trial in rotated.scientific_claims.trials]
    assert original != changed  # why agenda IDs must not mutate this legacy namespace
    assert [(trial.id, trial.inputs, trial.control_output, trial.treatment_output)
            for trial in world.scientific_claims.trials] == [
        (trial.id, trial.inputs, trial.control_output, trial.treatment_output)
        for trial in rotated.scientific_claims.trials]
