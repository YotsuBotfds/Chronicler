"""D1b cross-border guild leagues on the real compiled extension (hybrid runs).

Development world only: procedural 32x10 seed 13 (the first league forms at
turn 20 on this source, more join by turn 55, and a member's levy is claimed
from turn 119). Nothing is mocked.
"""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

WORLD = ["--seed", "13", "--worldgen", "procedural", "--regions", "32", "--civs", "10", "--agents", "hybrid",
         "--simulate-only"]


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
    """Remove only the record: every ``guild_leagues`` key, and a ``livelihoods``
    container that held nothing else."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "guild_leagues":
                continue
            item = _strip(item)
            if key == "livelihoods" and isinstance(item, dict) and set(item) <= {"schema_version"} \
                    and "guild_leagues" in value[key]:
                continue
            out[key] = item
        return out
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def _frames(bundle):
    from chronicler.guild_leagues import record_status
    out = []
    for snap in bundle["history"]:
        status, frame = record_status(snap)
        assert status in ("recorded", "recorded_zero"), (snap.get("turn"), status)
        out.append(frame)
    return out


def test_nothing_changes_before_the_first_league(tmp_path, monkeypatch):
    _cli(monkeypatch, tmp_path / "off", *WORLD, "--turns", "19")
    _cli(monkeypatch, tmp_path / "on", *WORLD, "--turns", "19", "--guild-leagues")
    off, on = _bundle(tmp_path / "off"), _bundle(tmp_path / "on")
    assert all(not f["leagues"] and not f["changes"] for f in _frames(on))
    assert _strip(on) == _strip(off)


def test_leagues_form_pay_dues_and_claim_recorded_levies(tmp_path, monkeypatch):
    _cli(monkeypatch, tmp_path / "mutual", *WORLD, "--turns", "125", "--guild-leagues")
    _cli(monkeypatch, tmp_path / "control", *WORLD, "--turns", "125", "--guild-leagues",
         "--guild-league-mode", "dues_only")
    mutual, control = _frames(_bundle(tmp_path / "mutual")), _frames(_bundle(tmp_path / "control"))
    founded = [c for f in mutual for c in f["changes"] if c["kind"] == "founded"]
    assert founded and len({c["league"] for c in founded}) == len(founded)       # ids never reused
    for f in mutual:
        for row in f["leagues"]:
            assert row["fund_close_milli"] <= max(row["cap_milli"], row["fund_open_milli"])
            assert len({m["lord"] for m in row["members"]}) == len(row["members"]) <= 4    # one per realm
    paid = [p for f in mutual for p in f["payouts"]]
    assert paid and all(0 < p["paid_milli"] <= min(p["loss_milli"], 2000) for p in paid)
    assert all(p["kind"] in ("levy", "sack") and p["event_id"] for p in paid)
    assert sum(len(f["dues"]) for f in control) > 0
    assert all(p["paid_milli"] == 0 for f in control for p in f["payouts"])


def test_exact_resume_with_leagues_holding_funds(tmp_path, monkeypatch):
    argv = [*WORLD, "--turns", "70", "--guild-leagues"]
    _cli(monkeypatch, tmp_path / "straight", *argv, "--checkpoint-turns", "60")
    from chronicler.run_checkpoint import read_checkpoint
    state = read_checkpoint(tmp_path / "straight" / "checkpoint_turn_60.ckpt").state
    gl = state.world.livelihoods.guild_leagues
    assert gl.leagues and all(league.fund_milli > 0 for league in gl.leagues) and gl.links
    _cli(monkeypatch, tmp_path / "resumed", "--resume", str(tmp_path / "straight" / "checkpoint_turn_60.ckpt"),
         "--simulate-only")
    assert _bundle(tmp_path / "resumed") == _bundle(tmp_path / "straight")
