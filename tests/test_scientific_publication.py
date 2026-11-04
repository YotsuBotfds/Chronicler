"""Opt-in publication semantics, separate from the retained natural cohort."""
from __future__ import annotations

from copy import deepcopy
import random

import numpy as np
import pytest

from chronicler import scientific_claims as C
from chronicler.models import WorldState
from chronicler.scientific_claims_state import FUNDED_CONTEXT_PUBLICATION, LEGACY_PUBLICATION
from test_scientific_claims import _world, _tick, _run


def _v2():
    world = _world()
    world.scientific_claims.publication_rule = FUNDED_CONTEXT_PUBLICATION
    return world


def test_legacy_rule_is_default_and_omitted_from_old_state_and_summary():
    world = _world()
    assert world.scientific_claims.publication_rule == LEGACY_PUBLICATION
    assert "publication_rule" not in world.scientific_claims.model_dump()
    restored = WorldState.model_validate_json(world.model_dump_json())
    assert restored.scientific_claims.publication_rule == LEGACY_PUBLICATION
    assert restored.model_dump_json() == world.model_dump_json()
    _tick(restored, 0)
    restored.turn = 1
    assert "publication_rule" not in C.snapshot_summary(restored)


@pytest.mark.parametrize("start", [2, 5, 8, 11])
def test_each_season_boundary_archives_funded_context_without_current_policy_use(start, monkeypatch):
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    legacy, amended = _world(), _v2()
    for world in (legacy, amended):
        _tick(world, start)
    funded = [(t.control_output, t.treatment_output, deepcopy(t.inputs)) for t in amended.scientific_claims.trials]

    def no_new_measurement(*a, **kw):
        raise AssertionError("publication re-evaluated physical truth")

    monkeypatch.setattr(C, "evaluate_trial", no_new_measurement)
    for world in (legacy, amended):
        _tick(world, start + 1)
        assert world.scientific_claims.trial_spent == 4
    assert all(t.status == "cancelled" for t in legacy.scientific_claims.trials)
    assert legacy.scientific_claims.receipts == []
    assert all(t.status == "completed" for t in amended.scientific_claims.trials)
    assert [(t.control_output, t.treatment_output, t.inputs) for t in amended.scientific_claims.trials] == funded
    assert len(amended.scientific_claims.receipts) == 2
    assert C.confidence(amended, 0, 0) == .5  # current context does not match
    assert C.prepare_adoption_effort(amended) == {}
    amended.turn = start + 12
    assert C.confidence(amended, 0, 0) == pytest.approx(2 / 3)
    assert C.confidence(amended, 0, 1) == pytest.approx(1 / 3)


@pytest.mark.parametrize("change", ["soil", "water", "climate", "grain", "practice", "nomadic"])
def test_changed_current_eligibility_does_not_rewrite_valid_funded_measurement(change, monkeypatch):
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    world = _v2()
    _tick(world, 0)
    region = world.regions[0]
    region_before, practices = region.model_copy(deep=True), deepcopy(world.techniques.rows)
    phase = world.climate_config.phase_offset
    if change in ("soil", "water"):
        setattr(region.ecology, change, .1)
    elif change == "climate":
        world.climate_config.phase_offset = 1
    elif change == "grain":
        region.resource_types[0] = 1
    elif change == "nomadic":
        from chronicler.nomads import set_nomads_enabled
        set_nomads_enabled(world, True)
        world.nomads.modes[0] = 2
    else:
        world.techniques.rows = [r for r in world.techniques.rows if r[:2] != (0, C.TECHNIQUE_INDEX["irrigation"])]
    funded = [(t.control_output, t.treatment_output, deepcopy(t.inputs)) for t in world.scientific_claims.trials]
    _tick(world, 1)
    assert all(t.status == "completed" for t in world.scientific_claims.trials)
    assert [(t.control_output, t.treatment_output, t.inputs) for t in world.scientific_claims.trials] == funded
    assert C.confidence(world, 0, 0) == .5
    world.regions[0], world.techniques.rows = region_before, practices
    world.climate_config.phase_offset = phase
    if change == "nomadic":
        world.nomads.modes[0] = 0
    assert C.confidence(world, 0, 0) == pytest.approx(2 / 3)


def test_surviving_academy_keeps_funded_records_across_controller_change():
    world = _v2()
    _tick(world, 0)
    payer = world.scientific_claims.trials[0].payer
    world.regions[0].controller = world.civilizations[1].name
    _tick(world, 1)
    assert all(t.status == "completed" and t.payer == payer for t in world.scientific_claims.trials)
    assert len(world.scientific_claims.receipts) == 2


def test_replacement_academy_cannot_revive_original_seat_trial():
    world = _v2()
    _tick(world, 0)
    replacement = world.scholarship.seats[0].model_copy(deep=True)
    replacement.name = "Replacement Academy"
    world.scholarship.seats[0].fallen_turn = 1
    world.scholarship.seats.append(replacement)
    _tick(world, 1)
    assert len(world.scholarship.seats) - 1 in world.scientific_claims.seat_ids
    assert all(t.status == "cancelled" and t.seat == 0 for t in world.scientific_claims.trials)
    assert world.scientific_claims.receipts == []


def test_later_rule_change_does_not_rewrite_past_cancellations():
    world = _world()
    _tick(world, 2)
    _tick(world, 3)
    assert all(t.status == "cancelled" for t in world.scientific_claims.trials)
    past = [t.model_dump() for t in world.scientific_claims.trials]
    world.scientific_claims.publication_rule = FUNDED_CONTEXT_PUBLICATION
    _tick(world, 4)
    assert [t.model_dump() for t in world.scientific_claims.trials] == past
    assert world.scientific_claims.receipts == [] and world.scientific_claims.trial_spent == 4


@pytest.mark.parametrize("loss", ["fallen", "level", "population"])
def test_lost_publication_access_still_cancels_without_refund_or_receipt(loss):
    world = _v2()
    before = sum(c.treasury for c in world.civilizations)
    _tick(world, 0)
    if loss == "fallen":
        world.scholarship.seats[0].fallen_turn = 1
    elif loss == "level":
        world.scholarship.seats[0].level = 0
    else:
        world.regions[0].population = 0
    events = _tick(world, 1)
    assert all(t.status == "cancelled" for t in world.scientific_claims.trials)
    assert world.scientific_claims.cancelled == 2 and world.scientific_claims.receipts == []
    assert sum(c.treasury for c in world.civilizations) == before - 4
    assert all(e.event_type == "scientific_trial_cancelled" for e in events)


@pytest.mark.parametrize("corruption", ["context", "date", "method", "output", "source", "environment", "dependence"])
def test_invalid_funded_record_fails_without_a_replacement_measurement(corruption):
    world = _v2()
    _tick(world, 0)
    trial = world.scientific_claims.trials[0]
    if corruption == "context":
        trial.inputs["context"]["season"] = 3
    elif corruption == "date":
        trial.inputs["turn"] = 7
    elif corruption == "method":
        trial.method = "unrecorded"
    elif corruption == "output":
        trial.control_output = float("nan")
    elif corruption == "source":
        trial.source_data = ""
    elif corruption == "environment":
        trial.environment_block = "different"
    else:
        trial.dependence_group = ""
    events = _tick(world, 1)
    assert trial.status == "failed" and trial.resolved_turn == 1
    assert world.scientific_claims.failed == 1 and world.scientific_claims.trial_spent == 4
    assert not any(r.trial == trial.id for r in world.scientific_claims.receipts)
    event = next(e for e in events if e.event_id == trial.event_id)
    assert event.event_type == "scientific_trial_failed" and event.causes == [trial.funded_event_id]


@pytest.mark.parametrize("control", ["withhold_information", "uninformative_tests", "local_only"])
def test_new_publication_keeps_registered_information_controls_and_costs(control, monkeypatch):
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    world = _v2()
    if control == "local_only":
        world.scientific_claims.transmission_enabled = False
    else:
        setattr(world.scientific_claims, control, True)
    _tick(world, 2)
    _tick(world, 3)
    state = world.scientific_claims
    assert all(t.status == "completed" for t in state.trials) and state.trial_spent == 4
    if control == "withhold_information":
        assert state.receipts == [] and state.withheld_results == 2
    elif control == "local_only":
        assert len(state.receipts) == 2 and state.messages == []
        assert all(r.seat == r.sender for r in state.receipts)
    else:
        assert len(state.receipts) == 2 and all(t.supports is False for t in state.trials)
        assert all(t.observed_treatment == t.observed_control for t in state.trials)


def test_null_funded_output_remains_completed_uninformative(monkeypatch):
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    world = _v2()
    world.regions[0].resource_suspensions[0] = 4
    _tick(world, 2)
    _tick(world, 3)
    assert all(t.status == "completed" and not t.informative for t in world.scientific_claims.trials)
    assert C.confidence(world, 0, 0) == .5


def test_publication_preserves_existing_rngs_goods_and_repeat_tick_state():
    world = _v2()
    _tick(world, 2)
    py_rng, np_rng = random.getstate(), np.random.get_state()
    regions = [r.model_dump_json() for r in world.regions]
    _tick(world, 3)
    assert random.getstate() == py_rng
    after = np.random.get_state()
    assert after[0] == np_rng[0] and np.array_equal(after[1], np_rng[1]) and after[2:] == np_rng[2:]
    assert [r.model_dump_json() for r in world.regions] == regions
    before = world.model_dump_json()
    assert _tick(world, 3) == []
    assert world.model_dump_json() == before


def test_new_publication_survives_exact_checkpoint_and_exposes_only_explicit_rule(tmp_path, monkeypatch):
    from chronicler.run_checkpoint import save_world, load_world
    monkeypatch.setattr(C, "MEASUREMENT_NOISE", 0.)
    world = _v2()
    _tick(world, 2)
    world.turn = 3
    checkpoint = tmp_path / "before-publication.ckpt"
    save_world(checkpoint, world)
    resumed = load_world(checkpoint)
    assert resumed.scientific_claims.publication_rule == FUNDED_CONTEXT_PUBLICATION
    _run(world, 3, 17)
    _run(resumed, 3, 17)
    assert resumed.model_dump_json() == world.model_dump_json()
    assert C.snapshot_summary(resumed)["publication_rule"] == FUNDED_CONTEXT_PUBLICATION


def test_full_turn_pipeline_archives_season_boundary_and_resumes_identically(tmp_path):
    from chronicler.models import ActionType
    from chronicler.run_checkpoint import save_world, load_world
    from chronicler.simulation import run_turn
    world = _v2()
    world.turn = 2
    world.tuning_overrides["climate.trend_share"] = 1.
    for region in world.regions:
        region.terrain, region.population, region.carrying_capacity = "plains", 60, 1000

    def advance(state, count):
        for _ in range(count):
            run_turn(state, lambda *args: ActionType.DEVELOP, lambda *args: "", seed=state.seed + state.turn)
            assert C.snapshot_summary(state)["source_turn"] == state.turn - 1

    advance(world, 1)
    assert len(world.scientific_claims.trials) == 2
    assert all(t.status == "running" and t.funded_turn == 2 for t in world.scientific_claims.trials)
    path = tmp_path / "full-turn-publication.ckpt"
    save_world(path, world)
    resumed = load_world(path)
    advance(world, 13)
    advance(resumed, 13)
    assert resumed.model_dump_json() == world.model_dump_json()
    originals = [t for t in world.scientific_claims.trials if t.parent < 0]
    assert all(t.status == "completed" and t.resolved_turn == 3 for t in originals)
    assert all(any(r.trial == t.id and r.received_turn == 3 for r in world.scientific_claims.receipts)
               for t in originals)
