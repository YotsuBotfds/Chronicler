"""Real health startup/catalog and saved-option seams, without native calls."""
from __future__ import annotations

import pickle

import pytest

from chronicler import feature_catalog as FC
from chronicler import livelihoods as LV
from chronicler import main
from chronicler import public_health as PH
from chronicler.world_gen import generate_world
from test_feature_catalog import _Accepted, _disagreements, sentinel_runtimes  # noqa: F401


FLAGS = ["--agents", "hybrid", "--simulate-only", "--grain-reserves", "--local-budgets",
         "--infrastructure-condition", "--infrastructure-condition-mode", "wear_only",
         "--residence-ledger", "--epidemic-care", "--public-health", "--quarantine-mode", "closure"]


def _started(tmp_path, flags):
    world = generate_world(seed=5, num_regions=8, num_civs=4)
    args = main._build_parser().parse_args(["--seed", "5", "--turns", "4", *FLAGS, *flags])
    with pytest.raises(_Accepted):
        main._configure_run(args, world, True, tmp_path / "chronicle.md")
    return world, args


def test_health_catalog_agrees_with_actual_startup(tmp_path, sentinel_runtimes):
    FC._features.cache_clear()
    assert _disagreements(tmp_path, ["public_health"]) == []


@pytest.mark.parametrize("mode,policy,delay", [("active", "evidence", "0"), ("cost_only", "shuffled", "20")])
def test_health_cli_options_reach_real_serialized_state(tmp_path, sentinel_runtimes, mode, policy, delay):
    world, args = _started(tmp_path, ["--public-health-mode", mode, "--public-health-policy", policy,
                                     "--public-health-report-delay", delay])
    state = world.livelihoods.public_health
    assert state.enabled and state.mode == mode and state.policy == policy and state.report_delay == int(delay)
    assert isinstance(state.report_delay, int)
    assert pickle.loads(pickle.dumps(world)).livelihoods.public_health.model_dump() == state.model_dump()
    forwarded = LV.livelihoods_arguments(args)
    assert f"--public-health-mode={mode}" in forwarded and f"--public-health-report-delay={delay}" in forwarded


def test_health_and_wealth_accounting_can_start_together_after_itemization(tmp_path, sentinel_runtimes):
    world, _args = _started(tmp_path, ["--wealth-accounting"])
    assert world.livelihoods.public_health.enabled
    assert world.livelihoods.epidemic_care.enabled and world.livelihoods.wealth_accounting.enabled


def test_saved_health_delay_is_compared_as_integer_value(tmp_path, sentinel_runtimes):
    world, _args = _started(tmp_path, ["--public-health-report-delay", "3"])
    state = world.livelihoods.public_health
    state.report_turn = 2
    parser = main._build_parser()
    before = state.model_dump()
    same = parser.parse_args(["--public-health", "--public-health-report-delay", "3"])
    assert LV.livelihoods_resume_conflicts(world, same, {}) == []
    PH.set_public_health_enabled(world, True, args=same, agent_mode="hybrid")
    assert state.model_dump() == before
    conflict = parser.parse_args(["--public-health-report-delay", "4"])
    assert len(LV.livelihoods_resume_conflicts(world, conflict, {})) == 1
    with pytest.raises(ValueError, match="conflicts with the saved world"):
        PH.set_public_health_enabled(world, True, args=conflict, agent_mode="hybrid")
    assert state.model_dump() == before


def test_explicit_health_off_keeps_never_enabled_world_identical():
    world = generate_world(seed=5, num_regions=8, num_civs=4)
    before = world.model_dump_json()
    LV.configure_livelihoods(world, main._build_parser().parse_args(["--no-public-health"]), agent_mode="hybrid")
    assert world.model_dump_json() == before and world.livelihoods is None
