"""RS3 veteran reintegration on the real compiled extension.

Natural activation on a procedural 32-region, 10-civ world (seed 302, where
campaigns raise, break and demobilise real armies within 45 turns) with
staffed workshops in operate mode. Rosters, releases, the native crew planner
and the pool are not mocked; an independent oracle (the roster difference
around each campaign tick, minus queued war deaths) checks the captures.
"""
from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

WORLD = ["--seed", "302", "--worldgen", "procedural", "--regions", "32", "--civs", "10",
         "--agents", "hybrid", "--simulate-only", "--workshops"]
TURNS = 45


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


def _bundle(folder):
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(folder / "chronicle_bundle.json")
    bundle["metadata"].pop("generated_at", None)
    return json.loads(json.dumps(bundle))


def _oracle(monkeypatch, *, raised_from: int = 0) -> dict[int, set[int]]:
    """Per turn, the stable ids that left a roster alive (not queued to die),
    from armies raised at ``raised_from`` or later."""
    import chronicler.war.armies as armies
    import chronicler.war.runtime as runtime
    released: dict[int, set[int]] = {}
    queued: set[int] = set()
    drafted: dict[int, int] = {}
    tick, sync, queue = runtime.tick_campaigns, runtime.end_of_turn_sync, armies.queue_deaths
    raise_army = runtime.raise_army

    def draft(*args, **kwargs):
        army = raise_army(*args, **kwargs)
        if army is not None:
            drafted.update((aid, army.raised_turn) for aid, _ in army.roster)
        return army

    def rosters(world):
        return {aid: army.raised_turn for army in world.war_state.armies for aid, _ in army.roster}

    def queue_deaths(ctx, ids):
        queued.update(int(a) for a in ids)
        return queue(ctx, ids)

    def wrap(fn):
        def run(world, *args, **kwargs):
            before = rosters(world)
            queued.clear()
            drafted.clear()
            out = fn(world, *args, **kwargs)
            # Drafted and released within one campaign tick count too.
            enlisted = {**before, **drafted}
            after = rosters(world)
            left = {aid for aid, raised in enlisted.items()
                    if aid not in after and aid not in queued and raised >= raised_from}
            released.setdefault(world.turn, set()).update(left)
            return out
        return run

    monkeypatch.setattr(armies, "queue_deaths", queue_deaths)
    monkeypatch.setattr(runtime, "raise_army", draft)
    monkeypatch.setattr(runtime, "tick_campaigns", wrap(tick))
    monkeypatch.setattr(runtime, "end_of_turn_sync", wrap(sync))
    return released


def _frames(bundle):
    out = {}
    for snap in bundle["history"]:
        record = snap["livelihoods"]["veteran_reintegration"]
        assert record["stage"] == "RS3" and record["source_turn"] == snap["turn"] - 1
        frame = record["frame"]
        assert frame is not None and frame["turn"] == record["source_turn"]
        out[frame["turn"]] = (snap, record, frame)
    return out


def test_captures_match_real_releases_and_priority_reorders_crews(tmp_path, monkeypatch):
    released = _oracle(monkeypatch)
    _cli(monkeypatch, tmp_path, *WORLD, "--turns", str(TURNS), "--veteran-reintegration")
    frames = _frames(_bundle(tmp_path))
    assert len(frames) == TURNS
    causes: dict[str, int] = {}
    prioritised = reordered = 0
    for turn, (snap, record, frame) in frames.items():
        assert frame["rows_dropped"] == 0
        # Every person who left a roster alive is captured, and nobody else.
        assert {c["agent_id"] for c in frame["captured"]} == released.get(turn, set()), turn
        assert frame["captured_total"] == len(released.get(turn, set()))
        for cause, n in frame["captured_by_cause"].items():
            causes[cause] = causes.get(cause, 0) + n
        # Placements: on the crew of a site that worked this turn, once each.
        receipts = {r["region"]: r for r in snap["livelihoods"]["workshops"]["receipts"] or []}
        placed = [p["agent_id"] for p in frame["placed"]]
        assert len(placed) == len(set(placed))
        for p in frame["placed"]:
            r = receipts[p["region"]]
            assert p["kind"] == "placed:crew" and p["agent_id"] in r["crew"] and r["allocated"] > 0
            prioritised += p["prioritised"]
        # The native planner put the offered veterans first, in the offered order.
        for region, ids in frame["offered"]:
            crew = receipts[region]["crew"]
            assert crew == [a for a in ids if a in crew] + sorted(a for a in crew if a not in ids)
            reordered += any(a in crew for a in ids) and crew != sorted(crew)
        for veteran in record["veterans"]:
            outcomes = veteran["outcomes"]
            assert all(o["turn"] <= turn for o in outcomes)
            assert [o["turn"] for o in outcomes] == sorted(o["turn"] for o in outcomes)
    assert set(causes) <= {"desertion", "scattered", "demobilised", "destroyed", "dissolved"}
    assert causes.get("demobilised", 0) > 0 and causes.get("scattered", 0) > 0
    counters = frames[TURNS - 1][1]["counters"]
    assert counters["captured"] == sum(causes.values()) > 20
    assert prioritised > 0 and reordered > 0 and counters["people_placed"] > 0
    assert counters["waiting_turns"] > 0 and counters.get("unmet_no_site", 0) > 0


def test_the_control_changes_nothing_but_its_own_record(tmp_path, monkeypatch):
    _cli(monkeypatch, tmp_path / "off", *WORLD, "--turns", str(TURNS))
    _cli(monkeypatch, tmp_path / "disabled", *WORLD, "--turns", str(TURNS), "--no-veteran-reintegration")
    _cli(monkeypatch, tmp_path / "control", *WORLD, "--turns", str(TURNS), "--veteran-reintegration",
         "--veteran-mode", "record_only")
    off, disabled, control = (_bundle(tmp_path / n) for n in ("off", "disabled", "control"))
    assert off == disabled                     # never enabled: no container key, flag or column
    assert all("veteran_reintegration" not in snap["livelihoods"] for snap in off["history"])
    would = 0
    for a, b in zip(off["history"], control["history"], strict=True):
        record = b["livelihoods"].pop("veteran_reintegration")
        assert record["mode"] == "record_only" and record["frame"]["priority_applied"] is False
        assert all(not p["prioritised"] for p in record["frame"]["placed"])
        would += sum(len(ids) for _, ids in record["frame"]["offered"] or [])
        assert a == b
    assert would > 0 and record["counters"]["captured"] > 20 and record["counters"].get("offered", 0) == 0
    ws = control["world_state"]
    ws["livelihoods"].pop("veteran_reintegration")
    assert ws == off["world_state"]


def test_exact_checkpoint_resume_inside_open_records(tmp_path, monkeypatch):
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, *WORLD, "--turns", "40", "--veteran-reintegration", "--checkpoint-turns", "30")
    ckpt = straight / "checkpoint_turn_30.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = _bundle(straight), _bundle(resumed)
    at = a["history"][29]["livelihoods"]["veteran_reintegration"]
    assert at["veterans"] and any(v["placements"] for v in at["veterans"]), "the checkpoint must hold live records"
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()


def test_a_rebuilt_pool_closes_records_and_its_redraft_makes_no_veteran(tmp_path, monkeypatch):
    first = tmp_path / "first"
    _cli(monkeypatch, first, *WORLD, "--turns", "22", "--veteran-reintegration")
    saved_world = json.loads((first / "state.json").read_text())
    saved = saved_world["livelihoods"]["veteran_reintegration"]
    open_ids = sorted(r["agent_id"] for r in saved["records"])
    armies = saved_world["war_state"]["armies"]
    assert open_ids and any(a["roster"] for a in armies), "the rebuild must meet records and rosters"
    released = _oracle(monkeypatch, raised_from=22)
    legacy = tmp_path / "legacy"
    # A legacy state-file resume spawns a new pool from region populations.
    _cli(monkeypatch, legacy, "--resume", str(first / "state.json"), "--turns", "32",
         "--agents", "hybrid", "--simulate-only", "--workshops", "--veteran-reintegration")
    frames = _frames(_bundle(legacy))
    assert sorted(frames) == list(range(22, 32))
    _, record, frame = frames[22]
    reset = sorted(o["agent_id"] for o in frame["outcomes"] if o["kind"] == "pool_reset")
    assert reset == open_ids and record["counters"]["pool_resets"] == saved["counters"].get("pool_resets", 0) + 1
    assert sorted(r["agent_id"] for r in record["closed"] if r["closed_reason"] == "pool_reset") == open_ids
    # Rosters kept or redrafted across the rebuild release nobody into the
    # records; armies raised after it are captured as usual.
    for turn, (_s, _r, f) in frames.items():
        assert {c["agent_id"] for c in f["captured"]} == released.get(turn, set()), turn
    final = frames[31][1]["counters"]
    assert final.get("captures_untrusted", 0) > 0
    state = json.loads((legacy / "state.json").read_text())["livelihoods"]["veteran_reintegration"]
    assert state["pool_reset_turn"] == 22
