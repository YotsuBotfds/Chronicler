"""Typed experiment controls preserve state and declare intervention lineage."""
from __future__ import annotations

from copy import deepcopy

import pytest

from chronicler.expansion_experiment import apply_expansion_experiment, controls_for_state
from chronicler.world_gen import generate_world


def _world(feature="harvest_forecasts"):
    from importlib import import_module
    world = generate_world(seed=42)
    getattr(import_module("chronicler." + feature), f"set_{feature}_enabled")(world, True)
    return world


def _request(feature="harvest_forecasts", **extra):
    return dict(schema_version=1, experiment="mechanism-probe", cohort="development", feature=feature,
                arm="control", controls={}, fork=False, **extra)


@pytest.mark.parametrize("feature,controls", [
    ("harvest_forecasts", {"policy": "withhold"}),
    ("ritual_gatherings", {"contact_enabled": False, "bonds_enabled": False}),
    ("health_care", {"care_enabled": False, "injury_rate": 0.0, "care_fraction": 0.1}),
    ("scientific_claims", {"withhold_information": True, "transmission_enabled": False,
                           "uninformative_tests": True}),
    ("scientific_claims", {"publication_rule": "funded-context-v2"}),
])
def test_only_controls_change_and_receipt_resolves_every_source_parameter(feature, controls):
    world = _world(feature)
    state = getattr(world, feature)
    before = deepcopy(state.model_dump())
    request = _request(feature)
    request["controls"] = controls
    config = {}
    receipt = apply_expansion_experiment(world, config, request, resumed=False)
    expected = {**before, **controls}
    assert state.model_dump() == expected
    assert receipt["controls_after"] == controls_for_state(feature, state)
    assert receipt["controls_before"] == {
        name: before.get(name, type(state).model_fields[name].default) for name in receipt["controls_after"]}
    assert receipt["source"]["package_digest"] and receipt["native"]["status"] in ("found", "absent")
    assert receipt["intervention_fork"] is False and receipt["applied_before_turn"] == 0
    assert config == {}  # execute_run owns storing the returned receipt.


@pytest.mark.parametrize("feature,controls", [
    ("harvest_forecasts", {"policy": "perfect-future"}),
    ("harvest_forecasts", {"reports": []}),
    ("ritual_gatherings", {"contact_enabled": 1}),
    ("health_care", {"care_enabled": "false"}),
    ("health_care", {"injury_rate": float("nan")}),
    ("health_care", {"impairment": 1.1}),
    ("health_care", {"episodes": []}),
    ("scientific_claims", {"withhold_information": "false"}),
    ("scientific_claims", {"transmission_enabled": 0}),
    ("scientific_claims", {"uninformative_tests": 1}),
    ("scientific_claims", {"trials": []}),
    ("scientific_claims", {"reported_allocations": {}}),
    ("scientific_claims", {"publication_rule": "future-context-v9"}),
    ("scientific_claims", {"publication_rule": True}),
])
def test_invalid_or_unregistered_changes_are_rejected_before_any_mutation(feature, controls):
    world = _world(feature)
    state = getattr(world, feature)
    before = state.model_dump()
    request = _request(feature)
    request["controls"] = controls
    with pytest.raises(ValueError):
        apply_expansion_experiment(world, {}, request, resumed=False)
    assert state.model_dump() == before


def test_an_experiment_cannot_silently_enable_a_system_or_relabel_a_resume():
    world = generate_world(seed=42)
    with pytest.raises(ValueError, match="enabled"):
        apply_expansion_experiment(world, {}, _request(), resumed=False)
    world = _world()
    with pytest.raises(ValueError, match="fork=True"):
        apply_expansion_experiment(world, {}, _request(), resumed=True)


def test_fork_records_actual_parent_hash_header_and_unchanged_progress(tmp_path):
    from chronicler.batch_manifest import file_sha256
    from chronicler.run_checkpoint import save_world
    world = _world()
    world.turn = 4
    world.harvest_forecasts.last_tick_turn = 3
    path = tmp_path / "parent.ckpt"
    save_world(path, world)
    request = _request()
    request.update(fork=True, controls={"policy": "shuffle"},
                   parent_checkpoint={"path": str(path), "sha256": file_sha256(path)})
    receipt = apply_expansion_experiment(world, {"expansion_experiment": {"arm": "parent"}},
                                       request, resumed=True)
    assert world.harvest_forecasts.last_tick_turn == 3
    assert receipt["parent_checkpoint"]["sha256"] == file_sha256(path)
    assert receipt["parent_checkpoint"]["identity"]["source"]["package_digest"]
    assert receipt["parent_checkpoint"]["seed"] == 42
    assert receipt["applied_before_turn"] == 4 and receipt["intervention_fork"] is True
    assert receipt["previous_experiment"] == {"arm": "parent"}


def test_wrong_parent_or_changed_registration_is_rejected_atomically(tmp_path):
    from chronicler.batch_manifest import file_sha256
    from chronicler.run_checkpoint import save_world
    world = _world()
    wrong = _world()
    wrong.turn = 5
    path = tmp_path / "other.ckpt"
    save_world(path, wrong)
    request = _request()
    request.update(fork=True, controls={"policy": "shuffle"},
                   parent_checkpoint={"path": str(path), "sha256": file_sha256(path)})
    with pytest.raises(ValueError, match="seed/turn"):
        apply_expansion_experiment(world, {}, request, resumed=True)
    assert world.harvest_forecasts.policy == "normal"
    registration = tmp_path / "registration.md"
    registration.write_text("Frozen direction, exposure, window and controls")
    request = _request()
    request.update(cohort="confirmatory", controls={"policy": "shuffle"},
                   registration={"path": str(registration), "sha256": file_sha256(registration)})
    registration.write_text("Changed after identity was frozen")
    with pytest.raises(ValueError, match="registration SHA"):
        apply_expansion_experiment(world, {}, request, resumed=False)
    assert world.harvest_forecasts.policy == "normal"


@pytest.mark.parametrize("controls", [{"withhold_information": True}, {"publication_rule": "funded-context-v2"}])
def test_scientific_fork_preserves_funded_trials_receipts_and_exact_control_history(tmp_path, controls):
    from chronicler.batch_manifest import file_sha256
    from chronicler.run_checkpoint import save_world
    from chronicler.scientific_claims_state import (
        ClaimContext, ScientificClaim, ScientificTrial, EvidenceReceipt,
    )
    world = _world("scientific_claims")
    state = world.scientific_claims
    state.started_turn, state.last_tick_turn, world.turn = 0, 0, 1
    state.claims = [ScientificClaim(id=0, recipe="irrigation", origin_seat=0, proposed_turn=0,
                                   context=ClaimContext(soil_band=3, water_band=2, season=0,
                                                        climate_phase="temperate"))]
    state.trials = [ScientificTrial(id=0, claim=0, seat=0, payer=0, funded_turn=-1,
                                    completion_turn=0, resolved_turn=0, cost=2, status="completed"),
                    ScientificTrial(id=1, claim=0, seat=1, payer=0, funded_turn=0,
                                    completion_turn=1, cost=2, parent=0,
                                    funded_event_id="0:scientific_trial_funded:0")]
    # Imported prior progress is never silently erased by an information arm.
    state.receipts = [EvidenceReceipt(seat=0, trial=0, received_turn=0, sender=0)]
    state.trial_spent = 4
    before = state.model_dump()
    checkpoint = tmp_path / "science-parent.ckpt"
    save_world(checkpoint, world)
    request = _request("scientific_claims")
    request.update(fork=True, controls=controls,
                   parent_checkpoint={"path": str(checkpoint), "sha256": file_sha256(checkpoint)})
    receipt = apply_expansion_experiment(world, {"expansion_experiment": {"arm": "parent"}},
                                        request, resumed=True)
    assert state.model_dump() == {**before, **controls}
    assert receipt["controls_before"] == {"withhold_information": False,
                                           "transmission_enabled": True, "uninformative_tests": False,
                                           "publication_rule": "current-context-v1"}
    assert receipt["controls_after"] == {**receipt["controls_before"], **controls}
    assert receipt["parent_checkpoint"]["turn"] == receipt["applied_before_turn"] == 1
    assert receipt["previous_experiment"] == {"arm": "parent"}


def test_confirmatory_label_requires_registration_without_claiming_it_is_a_gate(tmp_path):
    from chronicler.batch_manifest import file_sha256
    world = _world()
    request = _request()
    request["cohort"] = "confirmatory"
    with pytest.raises(ValueError, match="registration"):
        apply_expansion_experiment(world, {}, request, resumed=False)
    path = tmp_path / "frozen.md"
    path.write_text("Registered protocol")
    request["registration"] = {"path": str(path), "sha256": file_sha256(path)}
    receipt = apply_expansion_experiment(world, {}, request, resumed=False)
    assert receipt["cohort"] == "confirmatory"
    assert "gate_status" not in receipt
