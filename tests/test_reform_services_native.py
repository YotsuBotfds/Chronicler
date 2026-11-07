"""D1a poor relief as a real service on the real compiled extension (hybrid runs).

Development world only: template seed 7 with retail at the default market
boundary (a poor relief is granted at turn 68 and again at 83 on this source;
the funds buy owners' food from turn 75). Nothing is mocked.
"""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

BASE = ["--seed", "7", "--agents", "hybrid", "--simulate-only", "--food-allocation", "--household-retail"]


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


def _bundle(folder):
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(folder / "chronicle_bundle.json")
    bundle["metadata"].pop("generated_at", None)
    return bundle


def _strip(value):
    """Remove only this package's record (and a livelihoods container that held nothing else)."""
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k != "reform_services"}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def _frames(bundle):
    from chronicler.reform_services import record_status
    out = []
    for snap in bundle["history"]:
        status, frame = record_status(snap)
        assert status in ("recorded", "recorded_zero"), (snap.get("turn"), status)
        out.append(frame)
    return out


def test_nothing_changes_before_a_relief_is_granted(tmp_path, monkeypatch):
    """Until the first poor relief (turn 68), the switch changes nothing but its own record."""
    _cli(monkeypatch, tmp_path / "off", *BASE, "--turns", "66")
    _cli(monkeypatch, tmp_path / "on", *BASE, "--turns", "66", "--reform-services")
    off, on = _bundle(tmp_path / "off"), _bundle(tmp_path / "on")
    frames = _frames(on)
    assert all(not f["civs"] and not f["purchases"] for f in frames)
    assert _strip(on) == _strip(off)


def test_service_buys_food_and_the_cost_only_control_pays_the_same_treasury(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path / "service", *BASE, "--turns", "100", "--reform-services")
    _cli(monkeypatch, tmp_path / "control", *BASE, "--turns", "100", "--reform-services",
         "--reform-services-mode", "cost_only")
    service, control = _bundle(tmp_path / "service"), _bundle(tmp_path / "control")
    sf, cf = _frames(service), _frames(control)
    bought = [p for f in sf for p in f["purchases"]]
    assert bought and all(p["credited_milli"] + p["residual_milli"] == p["cost_milli"] for p in bought)
    assert sum(len(f["deliveries"]) for f in sf) >= len(bought) - 1        # the last may await next turn
    assert not any(f["purchases"] or f["deliveries"] for f in cf)
    assert sum(c["sunk_units"] for f in cf for c in f["civs"]) > 0
    # The fund never exceeds its cap and closes each turn.
    for f in sf:
        for c in f["civs"]:
            assert 0 <= c["fund_close_milli"] <= max(c["cap_milli"], c["fund_open_milli"])
            assert (c["fund_open_milli"] + c["to_fund_milli"] - c["spent_milli"] - c["refunded_milli"]
                    == c["fund_close_milli"])
    # Until the first purchase or refund, the treasuries are the same in both modes:
    # the deposit debits exactly what the control sinks.
    first = min(f["turn"] for f in sf if f["purchases"] or any(c["refunded_milli"] for c in f["civs"]))
    for s_snap, c_snap in zip(service["history"], control["history"]):
        if s_snap["turn"] > first:
            break
        assert [c["treasury"] for c in s_snap["civ_stats"].values()] == \
            [c["treasury"] for c in c_snap["civ_stats"].values()]
    # The retail frames record every relief purchase as a flow of the owned pool.
    retail = sum(r["flows"].get("relief_bought", 0) for s in service["history"]
                 for r in (s["livelihoods"]["household_retail"]["regions"] or []))
    assert retail == sum(p["food_milli"] for p in bought)


def test_exact_resume_with_an_open_purchase_and_a_holding_fund(tmp_path, monkeypatch):
    """The turn-85 checkpoint (after turn 84) holds purchases awaiting their delivery reading and two funds."""
    argv = [*BASE, "--turns", "90", "--reform-services"]
    _cli(monkeypatch, tmp_path / "straight", *argv, "--checkpoint-turns", "85")
    from chronicler.run_checkpoint import read_checkpoint
    loaded = read_checkpoint(tmp_path / "straight" / "checkpoint_turn_85.ckpt")
    rs = loaded.state.world.livelihoods.reform_services
    assert rs.pending and len(rs.funds) == 2
    _cli(monkeypatch, tmp_path / "resumed", "--resume", str(tmp_path / "straight" / "checkpoint_turn_85.ckpt"),
         "--simulate-only")
    assert _bundle(tmp_path / "resumed") == _bundle(tmp_path / "straight")
