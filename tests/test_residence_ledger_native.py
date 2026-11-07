"""X1 residence ledger on the real compiled extension (hybrid runs).

Development worlds only (template 7, famine-heavy; procedural 32x10 seed 13,
with campaigns: armies, occupations, conquests), short horizons. Nothing is
mocked: the record-only identity, the frame invariants on natural runs, RS4's
agreement with the ledger (audit 11.5), an exact resume inside open spells, a
legacy state-file resume (a rebuilt pool rebuilds nothing) and an on-demand
separation read at the next turn.
"""
from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

HYBRID = ["--agents", "hybrid", "--simulate-only"]
TEMPLATE = ["--seed", "7"]
WAR_WORLD = ["--seed", "13", "--worldgen", "procedural", "--regions", "32", "--civs", "10"]
LEDGER = ["--residence-ledger"]


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
    """Remove only the record: every ``residence_ledger`` key, a ``livelihoods``
    container that held nothing else, and the manifest key of the switch."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "residence_ledger":
                continue
            item = _strip(item)
            if key == "livelihoods" and isinstance(item, dict) and set(item) <= {"schema_version"} \
                    and "residence_ledger" in value[key]:
                continue
            out[key] = item
        return out
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


def _frames(bundle):
    from chronicler.residence_ledger import record_status
    out = []
    for snap in bundle["history"]:
        status, frame = record_status(snap)
        assert status in ("recorded", "recorded_zero"), (snap.get("turn"), status)
        out.append((frame, snap["livelihoods"]["residence_ledger"]))
    return out


@pytest.mark.parametrize("case", ["template_remittances", "war_world"])
def test_with_the_ledger_on_every_output_but_its_record_equals_off(tmp_path, monkeypatch, case):
    argv = (HYBRID + TEMPLATE + ["--turns", "40", "--remittances"]) if case == "template_remittances" \
        else (HYBRID + WAR_WORLD + ["--turns", "40"])
    _cli(monkeypatch, tmp_path / "off", *argv)
    _cli(monkeypatch, tmp_path / "on", *argv, *LEDGER)
    off, on = _bundle(tmp_path / "off"), _bundle(tmp_path / "on")
    assert len(_frames(on)) == len(on["history"]) == 40
    assert "residence_ledger" in on["world_state"]["livelihoods"]
    assert _strip(on["history"]) == off["history"]
    assert _strip(on["world_state"]) == off["world_state"]
    assert _strip(on) == off
    states = [json.loads((tmp_path / side / "state.json").read_text()) for side in ("off", "on")]
    assert _strip(states[1]) == states[0]
    assert (tmp_path / "off" / "chronicle.md").read_bytes() == (tmp_path / "on" / "chronicle.md").read_bytes()
    assert (tmp_path / "off" / "agent_events.arrow").read_bytes() == (tmp_path / "on" / "agent_events.arrow").read_bytes()


def _check_frames(frames):
    from chronicler.residence_ledger_state import ANCHORS, CAUSES, CLOSURES
    previous = None
    for frame, record in frames:
        t, regions = frame["totals"], frame["regions"]
        assert sum(r["residents"] for r in regions) == t["observed"] == t["alive"] - t["deferred"]
        assert sum(r["displaced"] for r in regions) == t["displaced"] == sum(r["displaced_from"] for r in regions)
        assert sum(t[f"displaced_{c}"] for c in CAUSES) == t["displaced"]
        assert sum(t[f"displaced_{a}"] for a in ANCHORS) == t["displaced"]
        assert sum(r["departures"] for r in regions) == t["moves"] == sum(r["arrivals"] for r in regions)
        assert sum(r["opened"] for r in regions) == t["opened"]
        assert sum(r["attached"] for r in regions) == t["attached"] >= t["attached_away"]
        assert t["unexplained_relocations"] == 0 and t["move_origin_mismatches"] == 0, frame["turn"]
        events = record["events"]
        if record["events_dropped"] == 0:
            assert sum(1 for e in events if e["kind"] == "opened") == t["opened"]
            for reason in CLOSURES:
                assert sum(1 for e in events if e["kind"] == reason) == t[reason], (frame["turn"], reason)
        if previous is not None:
            closed = sum(t[reason] for reason in CLOSURES)
            assert t["displaced"] == previous["displaced"] + t["opened"] - closed, frame["turn"]
        previous = t


def test_natural_runs_keep_the_frame_invariants(tmp_path, monkeypatch):
    _cli(monkeypatch, tmp_path / "t7", *HYBRID, *TEMPLATE, "--turns", "60", *LEDGER)
    _cli(monkeypatch, tmp_path / "p13", *HYBRID, *WAR_WORLD, "--turns", "60", *LEDGER)
    template = _frames(_bundle(tmp_path / "t7"))
    war = _frames(_bundle(tmp_path / "p13"))
    _check_frames(template)
    _check_frames(war)
    for frames in (template, war):
        totals = [f["totals"] for f, _r in frames]
        assert max(t["displaced"] for t in totals) > 0 and sum(t["returned"] for t in totals) > 0
        assert sum(t["died"] for t in totals) > 0 and frames[0][0]["observed_from"] == 0
    # On the war world: armies away from their soldiers' homes, and war-anchored spells.
    assert max(f["totals"]["attached_away"] for f, _r in war) > 0
    assert war[-1][1]["counters"].get("opened_war", 0) > 0
    # Famine anchors dominate on the famine-heavy template world.
    counters = template[-1][1]["counters"]
    assert counters["opened_famine"] > counters.get("opened_war", 0)


def test_rs4_and_the_ledger_agree_on_origins_returns_and_deaths(tmp_path, monkeypatch):
    """Audit 11.5: RS4 keeps its own diaspora ledger; where the two describe the
    same journey they agree. A spell opened by a person's first RS4 departure
    has RS4's origin; a ledger return closes RS4's entry of that origin as a
    return in the same turn and vice versa; deaths close both in the same turn."""
    import chronicler.remittances as RM
    import chronicler.residence_ledger as RL
    closures: list[tuple[int, int, int, str]] = []           # (turn, id, origin, reason)
    rs4_before: dict[int, dict] = {}
    rs4_after: dict[int, dict] = {}
    spells_before: dict[int, dict] = {}
    ledger_events: dict[int, list] = {}
    rows_after: dict[int, dict] = {}
    original_close, original_tick, original_phase10 = RM._close, RM.after_agent_tick, RL.phase10

    def close(state, entry, turn, reason, out):
        closures.append((int(turn), entry.id, entry.origin, reason))
        return original_close(state, entry, turn, reason, out)

    def tick(world, bridge):
        rs4_before[world.turn] = {e.id: (e.origin, e.departure_turn) for e in world.livelihoods.remittances.entries}
        out = original_tick(world, bridge)
        rs4_after[world.turn] = {e.id: (e.origin, e.departure_turn) for e in world.livelihoods.remittances.entries}
        return out

    def phase10(world, acc, economy_result, bridge):
        state = world.livelihoods.residence_ledger
        spells_before[world.turn] = {aid: (r.spell.origin, r.home) for aid, r in state.rows.items() if r.spell}
        out = original_phase10(world, acc, economy_result, bridge)
        ledger_events[world.turn] = list(state.events)
        assert state.events_dropped == 0
        rows_after[world.turn] = {aid: (r.res, r.home, r.spell.origin if r.spell else None)
                                  for aid, r in state.rows.items()}
        return out

    monkeypatch.setattr(RM, "_close", close)
    monkeypatch.setattr(RM, "after_agent_tick", tick)
    monkeypatch.setattr(RL, "phase10", phase10)
    _cli(monkeypatch, tmp_path, *HYBRID, *TEMPLATE, "--turns", "60", "--remittances", *LEDGER)
    checked = {"opened": 0, "returned": 0, "rs4_returns": 0, "deaths": 0}
    rs4_closed = {(turn, aid): (origin, reason) for turn, aid, origin, reason in closures}
    for turn, events in ledger_events.items():
        for e in events:
            aid = e["id"]
            if e["kind"] == "opened" and aid not in rs4_before[turn] and aid in rs4_after[turn]:
                assert rs4_after[turn][aid] == (e["origin"], turn), (turn, e)       # the same departure
                checked["opened"] += 1
            if e["kind"] == "returned" and not e.get("relocation") \
                    and rs4_before[turn].get(aid, (None,))[0] == e["origin"]:
                assert rs4_closed.get((turn, aid)) == (e["origin"], "return"), (turn, e)
                checked["returned"] += 1
            if e["kind"] == "died" and aid in rs4_before[turn]:
                # Both close in the same turn: RS4 as a death, or as a return when this
                # tick's move reached RS4's origin first (an older journey than the spell's).
                origin, reason = rs4_closed[(turn, aid)]
                assert reason == "death" or (reason == "return" and origin != e["origin"]), (turn, e, reason)
    for (turn, aid), (origin, reason) in rs4_closed.items():
        if reason == "return":
            if aid in rows_after[turn]:                                         # (alive after the tick)
                assert rows_after[turn][aid][0] == origin                       # living back at the origin
            spell = spells_before[turn].get(aid)
            if spell is not None and spell[0] == origin:
                assert any(e["id"] == aid and e["kind"] == "returned" for e in ledger_events[turn])
            checked["rs4_returns"] += 1
        elif reason == "death":
            assert aid not in rows_after[turn]                                  # the ledger closed the row too
            checked["deaths"] += 1
    assert all(n > 0 for n in checked.values()), checked


def test_an_exact_resume_inside_open_spells_equals_the_straight_run(tmp_path, monkeypatch):
    from chronicler.run_checkpoint import read_checkpoint
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, *HYBRID, *TEMPLATE, "--turns", "24", *LEDGER, "--remittances",
         "--checkpoint-every", "1", "--checkpoint", str(tmp_path / "ck" / "turn_{turn:04d}.ckpt"))
    ck = read_checkpoint(tmp_path / "ck" / "turn_0012.ckpt").state
    state = ck.world.livelihoods.residence_ledger
    assert any(r.spell is not None for r in state.rows.values())               # open spells cross it
    assert state.frame_turn == 11 and state.last_turn == 11
    ck.agent_bridge.close()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(tmp_path / "ck" / "turn_0012.ckpt"))
    a, b = _bundle(straight), _bundle(resumed)
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert json.loads((straight / "state.json").read_text()) == json.loads((resumed / "state.json").read_text())


def test_a_legacy_state_file_resume_rebuilds_nothing(tmp_path, monkeypatch):
    first = tmp_path / "first"
    _cli(monkeypatch, first, *HYBRID, *TEMPLATE, "--turns", "12", *LEDGER)
    saved = json.loads((first / "state.json").read_text(encoding="utf-8"))["livelihoods"]["residence_ledger"]
    assert "rows" not in saved                                          # person rows are not output
    open_spells = saved["open_spells_held"]
    assert saved["last_turn"] == 11 and open_spells > 0 and saved["rows_held"] > 0
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(first / "state.json"), "--agents", "hybrid", "--simulate-only",
         "--turns", "16")
    bundle = _bundle(resumed)
    assert bundle["metadata"]["resume"]["kind"] == "legacy-state"
    frames = [(f, r) for f, r in _frames(bundle) if r["source_turn"] >= 12]
    first_frame, first_record = frames[0]
    assert first_frame["turn"] == 12 and first_frame["observed_from"] == 12
    assert first_frame["totals"]["pool_reset"] == open_spells and first_frame["totals"]["newborn_rows"] == 0
    assert first_record["events_dropped"] == open_spells                # counted, not listed by person
    assert first_frame["totals"]["displaced"] == first_frame["totals"]["opened"]          # nothing carried over
    assert [e["kind"] for e in first_record["log"]].count("pool_reset") == 1
    assert all(f["observed_from"] == 12 for f, _r in frames)
    _check_frames(frames)


def test_separation_is_read_at_the_next_turn_before_its_tick(tmp_path, monkeypatch):
    import chronicler.livelihoods as LV
    import chronicler.residence_ledger as RL
    reads = []
    original = LV.prepare_phase2

    def prepare(world, region_input, agent_bridge, snapshot, *, acc=None):
        state = world.livelihoods.residence_ledger
        if state.frame_turn is not None:
            out = RL.separation(world, agent_bridge, consumer_turn=world.turn)
            frame = RL.read_frame(world, consumer_turn=world.turn)
            reads.append((world.turn, out, frame))
        return original(world, region_input, agent_bridge, snapshot, acc=acc)

    monkeypatch.setattr(LV, "prepare_phase2", prepare)
    _cli(monkeypatch, tmp_path, *HYBRID, *WAR_WORLD, "--turns", "30", *LEDGER)
    assert len(reads) == 29 and all(out["source_turn"] == turn - 1 for turn, out, _f in reads)
    assert all(frame["turn"] == turn - 1 for turn, _o, frame in reads)
    totals = {cause: sum(out["by_cause"][cause] for _t, out, _f in reads) for cause in ("displaced", "migrated")}
    assert all(n > 0 for n in totals.values()), totals
    assert all(out["pairs"] > 0 for _t, out, _f in reads)
