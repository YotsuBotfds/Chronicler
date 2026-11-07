"""Connected World transient native contracts; real extension, no paid APIs."""
from __future__ import annotations

import sys
import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def test_native_wealth_stages_close_through_births_deaths_and_migration(tmp_path, monkeypatch):
    import chronicler.main as main
    from chronicler.bundle_codec import load_bundle
    monkeypatch.setattr(sys, "argv", ["chronicler", "--agents", "hybrid", "--simulate-only",
        "--seed", "7", "--turns", "35", "--wealth-accounting",
        "--output", str(tmp_path / "chronicle.md")])
    main.main()
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    frames = [s["livelihoods"]["wealth_accounting"]["frame"] for s in bundle["history"]]
    assert sum(f["world"]["births"] for f in frames) > 0
    assert sum(f["world"]["deaths"] for f in frames) > 0
    assert sum(f["world"]["moved"] for f in frames) > 0
    for frame in frames:
        native = frame["native"]
        assert native["source_turn"] == frame["turn"]
        assert native["totals"]["decay"] <= 0
        # No typed package is enabled: every world balance change must be
        # explained by copied physical native stages, including inheritance.
        assert frame["world"]["typed_net_milli"] == 0
        assert frame["world"]["delta"] == pytest.approx(native["modeled_net"], abs=1e-8)


def test_transient_apis_refuse_invalid_rows_without_arming():
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    with pytest.raises(ValueError, match="invalid adaptive"):
        sim.set_adaptive_migration(1, [(1, 0, float("nan"))])
    with pytest.raises(ValueError, match="invalid adaptive"):
        sim.set_adaptive_migration(1, [(1, 0, 0.31)])
    with pytest.raises(ValueError, match="invalid adaptive"):
        sim.set_adaptive_migration(1, [(1, 0, 0.1), (1, 0, 0.2)])
    assert sim.cancel_adaptive_migration() is False
    with pytest.raises(ValueError, match="invalid enlisted"):
        sim.set_enlisted_service(1, [(1, 1.1)])
    assert sim.cancel_enlisted_service() is False
    sim.set_wealth_observation(1)
    with pytest.raises(ValueError, match="not completed"):
        sim.take_wealth_observation()
    with pytest.raises(ValueError, match="already pending"):
        sim.set_wealth_observation(1)
    assert sim.cancel_wealth_observation() is True
    assert sim.take_wealth_observation() is None
    assert sim.wealth_transfer_purposes()[10] == "restitution"


def test_movement_branch_input_requires_exact_prior_date_and_is_atomic():
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    with pytest.raises(ValueError, match="T-1"):
        sim.set_movement_branches(1, 1, [1], [1])
    with pytest.raises(ValueError, match="invalid"):
        sim.set_movement_branches(0, 1, [1], [])
    with pytest.raises(ValueError, match="duplicate"):
        sim.set_movement_branches(0, 1, [1,1], [1,1])
    sim.set_movement_branches(0, 1, [1], [1])
    with pytest.raises(ValueError, match="already pending"):
        sim.set_movement_branches(0, 1, [2], [1])


def test_information_gate_inputs_are_atomic_and_cancelled_by_owner():
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    with pytest.raises(ValueError, match="out of range"):
        sim.set_adaptive_information(1, [(1, 2)])
    assert sim.cancel_adaptive_information() is False
    assert sim.set_adaptive_information(1, [(1, 0)]) == []  # no living person yet
    with pytest.raises(ValueError, match="already pending"):
        sim.set_adaptive_information(1, [])
    assert sim.cancel_adaptive_information() is True
    assert sim.usable_trade_destinations([3, 1, 3], 1) == [(1, []), (3, [])]
    sim.set_movement_branches(0, 1, [1], [1])
    with pytest.raises(ValueError, match="another turn"):
        sim.cancel_movement_branches(2)
    assert sim.cancel_movement_branches(1) is True
    assert sim.cancel_movement_branches(1) is False


def test_information_tick_date_is_checked_before_mutation():
    import pyarrow as pa
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    sim.set_adaptive_information(1, [])
    with pytest.raises(ValueError, match="adaptive information must be installed for this tick"):
        sim.tick(2, pa.record_batch({"unused": [0]}))
    assert sim.cancel_adaptive_information() is True


def test_legacy_attribution_observer_refuses_active_adaptive_inputs_in_both_orders():
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    sim.configure_decision_delivery(True)
    with pytest.raises(ValueError, match="legacy decision observer"):
        sim.set_adaptive_migration(1, [(1, 0, 0.1)])
    with pytest.raises(ValueError, match="legacy decision observer"):
        sim.set_adaptive_information(1, [])
    assert sim.cancel_adaptive_migration() is False
    assert sim.cancel_adaptive_information() is False
    sim.configure_decision_delivery(False)
    sim.set_adaptive_migration(1, [(1, 0, 0.1)])
    with pytest.raises(ValueError, match="active adaptive inputs"):
        sim.configure_decision_delivery(True)
    with pytest.raises(ValueError, match="driver budget"):
        sim.get_migration_driver_stats()
    assert sim.cancel_adaptive_migration() is True
    # The record_only input has no behavioral effect or attribution gap.
    sim.set_adaptive_migration(1, [])
    sim.configure_decision_delivery(True)
    assert isinstance(sim.get_migration_driver_stats(), dict)


def test_native_wealth_observer_exact_resume_at_active_lifecycle_turns(tmp_path):
    from chronicler.main import execute_run
    from chronicler.run_checkpoint import read_checkpoint
    from test_run_checkpoint_native import _args, _outputs
    straight = tmp_path / "straight"
    execute_run(_args(straight, 35, "hybrid", seed=7, wealth_accounting=True,
        wealth_accounting_mode="strict", checkpoint_every=7, checkpoint=str(straight / "c{turn}.ckpt")))
    for turn in (14, 28):
        saved = read_checkpoint(straight / f"c{turn}.ckpt")
        assert saved.state.world.livelihoods.wealth_accounting._turn is None
        assert saved.state.agent_bridge._sim.take_wealth_observation() is None
        resumed = tmp_path / f"resume_{turn}"
        execute_run(_args(resumed, 35, "off"), checkpoint_resume=saved)
        assert _outputs(resumed) == _outputs(straight)
