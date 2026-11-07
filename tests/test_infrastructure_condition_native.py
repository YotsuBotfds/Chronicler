"""B3 infrastructure condition on the real compiled extension.

Development worlds only: procedural 32x10 seed 31 (irrigation and roads
built from the first turns, wear works open from turn 30, a progressing
irrigation work at turn 36, conquest damage and scorched records) and
template seed 11 (with PL1, the works' first woodcutters leave region 2 at
turn 43). Every run uses ``--agents hybrid --grain-reserves
--grain-storage --repair-projects``.
"""
from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

FLAGS = ["--agents", "hybrid", "--simulate-only", "--grain-reserves", "--grain-storage", "--repair-projects"]
PROCEDURAL = ("--worldgen", "procedural", "--civs", "10", "--regions", "32")


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


def test_works_close_their_books_on_the_real_extension(tmp_path, monkeypatch):
    from chronicler import infrastructure_condition as IC
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path, "--seed", "31", "--turns", "60", *FLAGS, *PROCEDURAL, "--infrastructure-condition")
    history = _bundle(tmp_path)["history"]
    delivered = charged = 0
    for snap in history:
        record = snap["livelihoods"]["infrastructure_condition"]
        assert record["mode"] == "repair" and record["stage"] == "B3"
        for a in record["assets"]:
            assert a["status"] in ("serving", "failed")
            assert a["service"] == pytest.approx(min(1.0, a["condition"] / IC.SERVICE_FULL))
        for r in record["receipts"] or []:
            rate = IC.TIMBER_PER_WORK[r["kind"]]
            assert r["delivered"] <= r["requested"] + 1e-9
            assert r["timber_used"] == pytest.approx(r["delivered"] * rate)
            assert r["timber_held"] == pytest.approx(r["timber_used"] + r["timber_returned"])
            assert (r["status"] == "progress") == (r["delivered"] > 0)
            delivered += r["delivered"]
        for row in record["ledger"] or []:
            assert row["charged"] * 1000 + row["prepaid_before_milli"] == row["coin_cost_milli"] + row["prepaid_after_milli"]
            charged += row["charged"]
    last = history[-1]["livelihoods"]["infrastructure_condition"]
    assert delivered > 0 and charged > 0
    assert last["sink_milli"] == charged * 1000 == last["counters"]["charged"] * 1000
    assert last["counters"]["damages_conquest"] >= 1 and last["counters"]["assets_inactive"] >= 1
    json.dumps(last)


def test_exact_checkpoint_resume_inside_an_open_work(tmp_path, monkeypatch):
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "31", "--turns", "44", *FLAGS, *PROCEDURAL, "--infrastructure-condition",
         "--checkpoint-turns", "37")
    ckpt = straight / "checkpoint_turn_37.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = _bundle(straight), _bundle(resumed)
    record = a["history"][36]["livelihoods"]["infrastructure_condition"]
    assert record["works"], "the checkpoint must hold open works"
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()


def _without(value):
    if isinstance(value, dict):
        return {k: _without(v) for k, v in value.items() if k != "infrastructure_condition"}
    if isinstance(value, list):
        return [_without(v) for v in value]
    return value


def test_record_only_equals_the_switch_off_except_its_record(tmp_path, monkeypatch):
    off, on = tmp_path / "off", tmp_path / "on"
    _cli(monkeypatch, off, "--seed", "11", "--turns", "40", *FLAGS)
    _cli(monkeypatch, on, "--seed", "11", "--turns", "40", *FLAGS, "--infrastructure-condition",
         "--infrastructure-condition-mode", "record_only")
    a, b = _bundle(off), _bundle(on)
    assert b["history"][-1]["livelihoods"]["infrastructure_condition"]["assets"]
    assert _without(a["history"]) == _without(b["history"])
    assert _without(a["world_state"]) == _without(b["world_state"])
    sa, sb = (json.loads((p / "state.json").read_text(encoding="utf-8")) for p in (off, on))
    assert _without(sa) == _without(sb)


FLOW = ("--watershed", "--watershed-mode", "flow")


def test_exact_resume_inside_an_open_flood_with_damaged_works(tmp_path, monkeypatch):
    """Watershed flow x condition (procedural 13, 32x10, 10 civs): a flood starts
    at turn 30 in region 10 and damages its irrigation work once, at the onset;
    a checkpoint at turn 33 lies inside the open flood, and the resume is
    byte-identical with no second flood damage."""
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "13", "--turns", "37", *FLAGS, *PROCEDURAL, *FLOW,
         "--infrastructure-condition", "--checkpoint-turns", "33")
    ckpt = straight / "checkpoint_turn_33.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = _bundle(straight), _bundle(resumed)
    snap = next(s for s in a["history"] if s["turn"] == 33)
    assert any(e["start_turn"] < 33 for e in snap["livelihoods"]["watershed"]["flood_events"]["open"])
    floods = [d for d in snap["livelihoods"]["infrastructure_condition"]["damages"] if d["event"] == "flood"]
    assert floods and all(d["ref"] == f"flood:{d['region']}:{d['turn']}" for d in floods)
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()
    last = a["history"][-1]["livelihoods"]["infrastructure_condition"]["counters"]
    assert last["damages_flood"] == len(floods)                         # once, at the onset


TIMBER = ("--timber-stock", "--timber-supply")


def test_exact_resume_with_an_outstanding_timber_order(tmp_path, monkeypatch):
    """Template seed 11 with PL1: the works' need launched expedition 0 from
    region 2 at turn 43 (after RS2's rows); at the turn-45 checkpoint it is
    cutting with the works' order outstanding, and it delivers after the resume."""
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "11", "--turns", "49", *FLAGS, *TIMBER, "--infrastructure-condition",
         "--checkpoint-turns", "45")
    ckpt = straight / "checkpoint_turn_45.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = _bundle(straight), _bundle(resumed)
    launched = {r["eid"] for snap in a["history"]
                for r in snap["livelihoods"]["infrastructure_condition"].get("timber_needs") or []
                if r["status"] == "launched"}
    at = a["history"][44]["livelihoods"]
    live = {e["eid"] for e in at["timber_supply"]["expeditions"]}
    rows = at["infrastructure_condition"]["timber_needs"]
    assert launched & live and any(r["status"] == "expedition" and r["eid"] in launched for r in rows), \
        "the checkpoint must hold a live expedition the works' need launched"
    after = a["history"][-1]["livelihoods"]["timber_supply"]
    assert any(e["eid"] in launched and e["status"] == "delivered" for e in after["closed"])
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()
