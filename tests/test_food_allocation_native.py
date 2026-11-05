"""L2 food allocation on the real compiled extension."""
import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def _run(tmp_path, *extra, seed=7, turns=60, per_capita_food=None):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    tmp_path.mkdir(parents=True, exist_ok=True)
    if per_capita_food is not None:
        # Constructed stress (labelled): raise per-capita demand so scarcity
        # occurs within a short test horizon.
        (tmp_path / "tuning.yaml").write_text(f"economy:\n  per_capita_food: {per_capita_food}\n")
        extra = (*extra, "--tuning", str(tmp_path / "tuning.yaml"))
    args = _build_parser().parse_args([
        "--seed", str(seed), "--turns", str(turns), "--civs", "4", "--regions", "8",
        "--agents", "hybrid", "--simulate-only",
        "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json"), *extra])
    execute_run(args)
    return load_bundle(tmp_path / "chronicle_bundle.json")


def _observations(bundle):
    return [s["livelihoods"]["food_allocation"] for s in bundle["history"]]


def test_allocations_close_every_turn_and_floor_means_differentiates_by_means(tmp_path):
    bundle = _run(tmp_path, "--food-allocation", "--food-allocation-regime", "floor_means",
                  per_capita_food=0.8)
    obs = _observations(bundle)
    observed = [o for o in obs if o["totals"] is not None]
    assert observed, "no allocation ran"
    scarce = [r for o in observed for r in o["regions"]]
    assert scarce, "no scarce region-turn to allocate"
    for r in scarce:
        assert r["allocated"] + r["unallocated"] == pytest.approx(r["rations_available"], rel=1e-6, abs=1e-6)
        assert 0.0 <= r["min_ration"] <= r["max_ration"] <= 1.0 + 1e-6
    # A traceable recipient-level difference, not only a regional average.
    assert any(r["max_ration"] - r["min_ration"] > 1e-3 for r in scarce)
    poor = sum(r["shortfall_poorer_half"] for r in scarce) / max(1, sum(r["people_poorer_half"] for r in scarce))
    rich = sum(r["shortfall_richer_half"] for r in scarce) / max(1, sum(r["people_richer_half"] for r in scarce))
    assert poor > rich


def test_equal_regime_is_an_exact_identity_control(tmp_path):
    off = _run(tmp_path / "off", per_capita_food=0.8)
    equal = _run(tmp_path / "equal", "--food-allocation", "--food-allocation-regime", "equal",
                 per_capita_food=0.8)
    scarce = [r for o in _observations(equal) if o["regions"] for r in o["regions"]]
    assert scarce
    for r in scarce:
        # Everyone eats exactly the regional ration; the share of people who
        # died after Phase 2 is unallocated, never shared out.
        assert r["min_ration"] == pytest.approx(r["sufficiency"], abs=1e-6)
        assert r["max_ration"] == pytest.approx(r["sufficiency"], abs=1e-6)
        dead = (r["phase2_alive"] - r["alive"]) * r["sufficiency"]
        assert r["unallocated"] == pytest.approx(dead, abs=1e-5)
    for a, b in zip(off["history"], equal["history"], strict=True):
        b = dict(b)
        assert b.pop("livelihoods")["food_allocation"]["regime"] == "equal"
        assert a == b
    ws = dict(equal["world_state"])
    ws.pop("livelihoods")
    assert ws == off["world_state"]
