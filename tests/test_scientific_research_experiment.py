"""Research policy forks are explicit, atomic and separate from exact resume."""
from copy import deepcopy
import pickle

import pytest

from chronicler.batch_manifest import file_sha256
from chronicler.expansion_experiment import apply_expansion_experiment, controls_for_state
from chronicler.run_checkpoint import save_world
from chronicler.scientific_research import set_research_agendas_enabled
from test_expansion_experiment import _request
from test_scientific_claims import _world, _tick
from test_scientific_research import advance, research_world


def _fork(world, tmp_path, **controls):
    path = tmp_path / "parent.ckpt"
    save_world(path, world)
    request = _request("scientific_claims")
    request.update(fork=True, controls=controls,
        parent_checkpoint={"path": str(path), "sha256": file_sha256(path)})
    return request


def test_declared_activation_adopts_legacy_archive_and_records_actual_mode_birth_and_cycle_lineage(tmp_path):
    world = _world(seats=(0, 1))
    _tick(world, 0)
    world.turn = 1
    before = deepcopy(world.scientific_claims.model_dump())
    request = _fork(world, tmp_path, research_enabled=True, publication_rule="funded-context-v2")
    receipt = apply_expansion_experiment(world, {}, request, resumed=True)
    state = world.scientific_claims
    assert state.trials and state.model_dump()["trials"] == before["trials"]
    assert state.trial_spent == before["trial_spent"] and state.last_tick_turn == 0
    policy = receipt["research_policy"]
    assert policy["before"] == {"mode": "legacy"}
    assert policy["requested_enabled"] is True
    assert policy["after"]["mode"] == "finite-retained-v1" and policy["after"]["enabled_turn"] == 1
    assert policy["after"]["cycles"][0]["legacy_adopted"] is True
    assert policy["after"]["host_seal"] == world.scholarship.scientific_research_identity.seal
    assert policy["after"]["academy_births"] == [b.model_dump() for b in state.research_agendas.academy_births]
    assert receipt["applied_before_turn"] == receipt["parent_checkpoint"]["turn"] == 1
    assert receipt["intervention_fork"] is True
    assert set(controls_for_state("scientific_claims", state)) == {
        "withhold_information", "transmission_enabled", "uninformative_tests", "publication_rule"}


@pytest.mark.parametrize("enabled", [False, True])
def test_finite_pause_resume_preserves_activation_host_records_and_does_not_blindly_set_metadata(tmp_path, enabled):
    world = research_world()
    advance(world, 0, 2)
    set_research_agendas_enabled(world, not enabled)
    state = world.scientific_claims
    before = deepcopy(state.model_dump())
    receipt = apply_expansion_experiment(world, {}, _fork(world, tmp_path, research_enabled=enabled), resumed=True)
    expected = deepcopy(before)
    expected["research_agendas"]["enabled"] = enabled
    assert state.model_dump() == expected
    assert "research_enabled" not in state.__dict__
    assert receipt["research_policy"]["before"]["enabled"] is not enabled
    assert receipt["research_policy"]["after"]["enabled"] is enabled
    assert receipt["research_policy"]["before"]["enabled_turn"] == receipt["research_policy"]["after"]["enabled_turn"] == 0


def test_information_control_fork_retains_finite_mode_and_separately_discloses_unchanged_lineage(tmp_path):
    world = research_world()
    advance(world, 0, 2)
    plan = deepcopy(world.scientific_claims.research_agendas.model_dump())
    receipt = apply_expansion_experiment(world, {}, _fork(world, tmp_path, withhold_information=True), resumed=True)
    assert world.scientific_claims.research_agendas.model_dump() == plan
    assert receipt["research_policy"]["requested_enabled"] is None
    assert receipt["research_policy"]["before"] == receipt["research_policy"]["after"]


@pytest.mark.parametrize("failure", ["bad_control", "bad_parent", "bad_registration", "missing_host", "replacement_host"])
def test_every_requested_control_and_identity_validates_before_policy_or_host_mutation(tmp_path, failure):
    world = research_world() if failure == "replacement_host" else _world(seats=(0, 1))
    request = _fork(world, tmp_path, research_enabled=True)
    if failure == "bad_control":
        request["controls"]["withhold_information"] = "false"
    elif failure == "bad_parent":
        request["parent_checkpoint"]["sha256"] = "0" * 64
    elif failure == "bad_registration":
        path = tmp_path / "registration.md"
        path.write_text("real registered data")
        request["registration"] = {"path": str(path), "sha256": "0" * 64}
    elif failure == "missing_host":
        world.scholarship = None
    else:
        from chronicler.scholarship_state import ScholarshipState
        world.scholarship = ScholarshipState(seats=deepcopy(world.scholarship.seats))
    before = pickle.dumps(world, protocol=5)
    with pytest.raises(ValueError):
        apply_expansion_experiment(world, {}, request, resumed=True)
    assert pickle.dumps(world, protocol=5) == before


@pytest.mark.parametrize("value", [None, 1, "true", {}, []])
def test_research_policy_control_requires_an_actual_boolean(tmp_path, value):
    world = _world(seats=(0, 1))
    before = pickle.dumps(world, protocol=5)
    with pytest.raises(ValueError):
        apply_expansion_experiment(world, {}, _fork(world, tmp_path, research_enabled=value), resumed=True)
    assert pickle.dumps(world, protocol=5) == before


def test_real_entrypoint_policy_fork_is_nonexact_and_checkpoint_configuration_records_actual_mode(tmp_path):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    from chronicler.run_checkpoint import read_checkpoint
    parser = _build_parser()
    parent = tmp_path / "parent"
    args = parser.parse_args(["--seed", "42", "--turns", "3", "--regions", "4", "--civs", "2",
        "--agents", "off", "--simulate-only", "--scholarship", "--techniques", "--scientific-claims",
        "--checkpoint-every", "1", "--checkpoint", str(parent / "turn_{turn}.ckpt"),
        "--output", str(parent / "chronicle.md"), "--state", str(parent / "state.json")])
    execute_run(args)
    checkpoint = parent / "turn_1.ckpt"
    loaded = read_checkpoint(checkpoint)
    request = _request("scientific_claims")
    request.update(fork=True, controls={"research_enabled": True},
        parent_checkpoint={"path": str(checkpoint), "sha256": file_sha256(checkpoint)})
    fork = tmp_path / "fork"
    args.output, args.state = str(fork / "chronicle.md"), str(fork / "state.json")
    args.checkpoint = str(fork / "turn_{turn}.ckpt")
    execute_run(args, checkpoint_resume=loaded, expansion_experiment=request)
    bundle = load_bundle(fork / "chronicle_bundle.json")
    assert bundle["metadata"]["resume"]["kind"] == "experiment-fork"
    assert bundle["metadata"]["resume"]["exact"] is False
    assert bundle["metadata"]["expansion_experiment"]["applied_before_turn"] == 1
    final = read_checkpoint(fork / "turn_3.ckpt")
    assert final.header["exact"] is False
    assert final.header["flags"]["scientific_research_agendas"] is True
    assert final.state.run_config["simulation_args"]["scientific_research_agendas"] is True
    assert final.state.run_config["lineage"][-1]["kind"] == "experiment-fork"
    assert final.state.run_config["lineage"][-1]["exact"] is False
