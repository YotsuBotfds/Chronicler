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
