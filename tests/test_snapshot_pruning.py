"""Bundle version 5: dead civilizations leave the per-turn history snapshots.

See src/chronicler/snapshot_pruning.py and docs/performance/dead-civ-pruning.md.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json

import pytest

from chronicler.bundle_codec import load_bundle
from chronicler.snapshot_pruning import (
    PRUNED_BUNDLE_VERSION,
    SnapshotPruner,
    live_civ_names,
    prune_bundle,
    prune_history,
    restore_bundle,
    restore_history,
)


def _text(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _rows(history) -> str:
    """The civ_stats of a history as JSON text (values, types and key order)."""
    return _text([snap["civ_stats"] for snap in history])


def _row(regions, treasury=10, **extra):
    row = {"population": 5 if regions else 0, "treasury": treasury, "stability": 40,
           "asabiya": 0.5, "regions": list(regions), "alive": bool(regions),
           "federation_name": None, "factions": {"influence": {"military": 0.25}}}
    row.update(extra)
    return row


def _snapshot(turn, rows, exiles=(), capitals=None):
    names = list(rows)
    return {
        "turn": turn,
        "civ_stats": rows,
        "region_control": {"r1": "A"},
        "relationships": {a: {b: {"disposition": "neutral"} for b in names if b != a} for a in names},
        "exile_modifiers": [{"original_civ_name": n, "absorber_civ": "A", "conquered_regions": ["r2"],
                             "turns_remaining": 5, "recognized_by": []} for n in exiles],
        "capitals": capitals if capitals is not None else {n: "r1" for n in names},
        "region_cultural_identity": {"r2": "B"},
        "per_pair_accuracy": {a: {b: 0.3 for b in names if b != a} for a in names},
        "perception_errors": {a: {b: {"military": 1} for b in names if b != a} for a in names},
    }


def _history():
    """A lives; B dies at turn 3 (final row) and is pruned from 4; C dies at
    turn 2 but is in exile until turn 4 (restorable), so it keeps its rows
    until its final row at turn 5; D is dead from the first snapshot."""
    history = []
    for turn in range(1, 9):
        rows = {
            "A": _row(["r1"], treasury=100 + turn),
            "B": _row(["r2"] if turn < 3 else [], treasury=50 + (turn - 3) * 4 if turn >= 3 else 50),
            "C": _row(["r3"] if turn < 2 else [], treasury=7),
            "D": _row([], treasury=1),
        }
        exiles = ["C"] if 2 <= turn <= 4 else []
        history.append(_snapshot(turn, rows, exiles))
    return history


class TestDefinition:
    def test_live_names_are_landed_or_restorable(self):
        snap = _snapshot(1, {"A": _row(["r1"]), "B": _row([]), "C": _row([])}, exiles=["C"])
        assert live_civ_names(snap) == {"A", "C"}

    def test_legacy_rows_without_regions_use_alive(self):
        snap = {"civ_stats": {"A": {"alive": True}, "B": {"alive": False}}, "exile_modifiers": []}
        assert live_civ_names(snap) == {"A"}

    def test_recorded_civs_per_turn(self):
        pruned, _ = prune_history(_history())
        recorded = {snap["turn"]: list(snap["civ_stats"]) for snap in pruned}
        assert recorded == {
            1: ["A", "B", "C", "D"],   # the first snapshot records every civ
            2: ["A", "B", "C"],        # C is in exile (restorable); D was never live
            3: ["A", "B", "C"],        # B's final row (it died this turn)
            4: ["A", "C"],
            5: ["A", "C"],             # C's final row: its exile ended at turn 4
            6: ["A"], 7: ["A"], 8: ["A"],
        }

    def test_final_row_is_the_death_row(self):
        history = _history()
        pruned, _ = prune_history(history)
        assert pruned[2]["civ_stats"]["B"] == history[2]["civ_stats"]["B"]
        assert pruned[2]["civ_stats"]["B"]["alive"] is False

    def test_pair_tables_and_capitals_follow_civ_stats(self):
        pruned, _ = prune_history(_history())
        for snap in pruned:
            names = set(snap["civ_stats"])
            assert set(snap["capitals"]) == names
            for field in ("relationships", "per_pair_accuracy", "perception_errors"):
                assert set(snap[field]) == names
                for inner in snap[field].values():
                    assert set(inner) <= names

    def test_world_records_and_region_fields_are_kept(self):
        history = _history()
        pruned, _ = prune_history(history)
        for old, new in zip(history, pruned):
            for key in ("exile_modifiers", "region_control", "region_cultural_identity", "turn"):
                assert new[key] == old[key]

    def test_non_civ_names_in_pair_tables_are_kept(self):
        history = _history()
        for snap in history:
            snap["relationships"]["Ghost"] = {"B": {"disposition": "neutral"}, "A": {"disposition": "hostile"}}
        pruned, _ = prune_history(history)
        assert pruned[-1]["relationships"]["Ghost"] == {"A": {"disposition": "hostile"}}

    def test_restored_civ_is_recorded_again(self):
        history = _history()
        history[6]["civ_stats"]["B"] = _row(["r2"], treasury=3)  # restored at turn 7
        history[7]["civ_stats"]["B"] = _row(["r2"], treasury=4)
        pruned, tails = prune_history(history)
        assert [("B" in snap["civ_stats"]) for snap in pruned] == [True, True, True, False, False, False, True, True]
        assert [seg["from_turn"] for seg in tails["B"]] == [4]
        assert _rows(restore_history(pruned, tails)) == _rows(history)

    def test_a_row_that_changes_shape_stays(self):
        history = _history()
        del history[5]["civ_stats"]["B"]["factions"]
        pruned, tails = prune_history(copy.deepcopy(history))
        # Turn 6 drops a field and turn 7 regains it: both rows stay recorded.
        assert "B" in pruned[5]["civ_stats"] and "B" in pruned[6]["civ_stats"]
        assert [(seg["from_turn"], seg["snapshots"]) for seg in tails["B"]] == [(4, 2), (8, 1)]
        assert _rows(restore_history(pruned, tails)) == _rows(history)

    def test_live_stream_pruner_matches_bundle_history(self):
        history = _history()
        pruned, _ = prune_history(copy.deepcopy(history))
        stream = SnapshotPruner(record_tails=False)
        assert [stream.prune(snap) for snap in history] == pruned
        assert stream.finish() == {}


class TestRuns:
    def test_treasury_drift_is_one_arithmetic_run(self):
        _, tails = prune_history(_history())
        assert tails["B"] == [{"from_turn": 4, "snapshots": 5, "changes": {"treasury": [[5, 54, 4]]}}]
        assert tails["C"] == [{"from_turn": 6, "snapshots": 3, "changes": {}}]
        assert "D" in tails and tails["D"][0]["from_turn"] == 2

    def test_restore_is_exact(self):
        history = _history()
        pruned, tails = prune_history(copy.deepcopy(history))
        restored = restore_history(pruned, tails)
        assert _rows(restored) == _rows(history)
        # Everything but the civ rows is the pruned snapshot itself.
        for new, old in zip(restored, pruned):
            assert {k: v for k, v in new.items() if k != "civ_stats"} == {
                k: v for k, v in old.items() if k != "civ_stats"}

    @pytest.mark.parametrize("values", [
        [3, 3, 9, 9, 9, 2],                 # constant runs of ints
        [1, 2, 4, 8, 16],                   # no progression
        [5, 6, 7, 7, 7, 8, 9],               # progression, constant, progression
        [0.5, 0.25, 0.25, 0.125],           # floats are constant runs
        [1, 1.0, True, 1],                  # same value, different JSON types
        [{"a": 1, "b": 2}, {"b": 2, "a": 1}, {"a": 1, "b": 2}],  # key order matters
        [[1], [1, 2], None, "x", "x"],
    ])
    def test_any_field_drift_round_trips(self, values):
        history = []
        for turn, value in enumerate([0] + [0] + values, start=1):
            rows = {"A": _row(["r1"]), "B": _row(["r2"] if turn == 1 else [], treasury=0, drift=0)}
            if turn > 2:
                rows["B"]["drift"] = value
            history.append(_snapshot(turn, rows))
        pruned, tails = prune_history(copy.deepcopy(history))
        assert all("B" not in snap["civ_stats"] for snap in pruned[2:])
        assert _rows(restore_history(pruned, tails)) == _rows(history)

    def test_bad_tails_are_rejected(self):
        pruned, tails = prune_history(_history())
        broken = copy.deepcopy(tails)
        broken["B"][0]["from_turn"] = 99
        with pytest.raises(ValueError, match="does not match"):
            restore_history(pruned, broken)
        broken = copy.deepcopy(tails)
        broken["B"][0]["snapshots"] = 9
        with pytest.raises(ValueError):
            restore_history(pruned, broken)


class TestBundle:
    def _v4(self):
        return {"world_state": {"civilizations": []}, "history": _history(), "events_timeline": [],
                "metadata": {"seed": 1, "generated_at": "x", "bundle_version": 4, "extra": 1}}

    def test_prune_bundle_layout(self):
        v5 = prune_bundle(self._v4())
        assert list(v5) == ["world_state", "history", "pruned_civ_stats", "events_timeline", "metadata"]
        assert list(v5["metadata"]) == ["seed", "generated_at", "bundle_version", "extra"]
        assert v5["metadata"]["bundle_version"] == PRUNED_BUNDLE_VERSION
        assert prune_bundle(v5) is v5

    def test_restore_bundle_round_trip(self):
        v4 = self._v4()
        restored = restore_bundle(prune_bundle(copy.deepcopy(v4)))
        assert "pruned_civ_stats" not in restored
        assert _text(restored["history"]) != _text(v4["history"])  # dead pairs are gone
        assert _text([s["civ_stats"] for s in restored["history"]]) == _text([s["civ_stats"] for s in v4["history"]])

    def test_version_4_bundles_pass_through(self):
        v4 = self._v4()
        assert restore_bundle(v4) is v4
        assert restore_history(v4["history"], None) == v4["history"]


# --- A real run: seed 1, 5 civs, 10 regions (the bundle-size world), 50 turns.
# Thornwall Confederacy loses its last region at turn 33, stays restorable in
# exile and is pruned from turn 44 with its treasury still growing. The world
# predates the Wave 8 defaults (docs/integration/defaults-wave8.md): with
# great-person agendas or nomads on, Thornwall survives these 50 turns, so the
# three Wave 8 switches are pinned off.

# 120 turns: the Dorrathi Clans lose their last region at turn 76, are kept
# through their exile to turn 85 and are pruned from turn 87, the turn after
# the exile ends; the Kethani Empire loses its land at turn 66, is kept
# through its exile to turn 75 and is pruned from 77 (the Thornwall
# Confederacy likewise from 104). Before the 2026-10 population corrections
# (docs/integration/population-entities.md: arrivals no longer trim a
# crowded region, famine refugees conserved) the Dorrathi fell at turn 104
# and were pruned from 115, and the Kethani Empire, landless at turn 60, was
# restored at turn 64 (unpruned). Before the 2026-10 merchant-hub correction (docs/integration/procedural-gates.md: a hub of
# five living civs trades with all four others) the Thornwall Confederacy
# fell at turn 70 with no exile and was pruned from 71; before the farmland
# and regional-climate corrections (docs/integration/farmland-climate.md) it
# fell at turn 44 and was pruned from 55.
PRUNED_CIV = "Dorrathi Clans"
PRUNED_FROM = 87
RUN_TURNS = 120


def _run(tmp_path, monkeypatch, *, turns=RUN_TURNS):
    from chronicler.main import execute_run
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    snapshots = []
    args = argparse.Namespace(seed=1, turns=turns, civs=5, regions=10,
                              output=str(tmp_path / "chronicle.md"), state=str(tmp_path / "state.json"),
                              resume=None, reflection_interval=50, llm_actions=False, scenario=None,
                              pause_every=None, simulate_only=True, agents="off",
                              maritime=False, gp_agendas=False, nomads=False)
    with contextlib.redirect_stdout(io.StringIO()):
        execute_run(args, on_turn=lambda snap, *_: snapshots.append(snap.model_dump(mode="json")))
    return snapshots, load_bundle(tmp_path / "chronicle_bundle.json")


@pytest.fixture(scope="module")
def real_run(tmp_path_factory):
    with pytest.MonkeyPatch.context() as monkeypatch:
        return _run(tmp_path_factory.mktemp("pruned_run"), monkeypatch)


class TestRealRun:
    def test_bundle_prunes_the_dead(self, real_run):
        in_memory, bundle = real_run
        # Pruning arrived in version 5; version 6 writes the pruned history as deltas.
        assert bundle["metadata"]["bundle_version"] == 6
        segments = bundle["pruned_civ_stats"][PRUNED_CIV]
        assert segments[0]["from_turn"] == PRUNED_FROM
        # A civ without land earns nothing, so its pruned rows never change.
        assert segments[0]["changes"] == {}
        by_turn = {snap["turn"]: snap for snap in bundle["history"]}
        final = by_turn[PRUNED_FROM - 1]["civ_stats"][PRUNED_CIV]
        assert final["regions"] == [] and final["alive"] is False
        # Kept while its exile lived.
        assert any(e["original_civ_name"] == PRUNED_CIV for e in by_turn[PRUNED_FROM - 2]["exile_modifiers"])
        after = range(PRUNED_FROM, RUN_TURNS + 1)
        assert all(PRUNED_CIV not in by_turn[t]["civ_stats"] for t in after)
        assert all(PRUNED_CIV not in by_turn[t]["relationships"] for t in after)
        # An exile keeps a landless civ recorded: Kethani, landless from turn
        # 66, keeps its rows through its exile and is pruned only after it.
        assert [s["from_turn"] for s in bundle["pruned_civ_stats"]["Kethani Empire"]] == [77]
        assert by_turn[70]["civ_stats"]["Kethani Empire"]["regions"] == []
        assert any(e["original_civ_name"] == "Kethani Empire" for e in by_turn[70]["exile_modifiers"])
        # Snapshots handed to callbacks still carry every civ (the simulation's view).
        assert all(PRUNED_CIV in snap["civ_stats"] for snap in in_memory)

    def test_bundle_history_is_the_pruned_in_memory_history(self, real_run):
        in_memory, bundle = real_run
        pruned, tails = prune_history(copy.deepcopy(in_memory))
        assert _text(pruned) == _text(bundle["history"])
        assert _text(tails) == _text(bundle["pruned_civ_stats"])
        restored = restore_history(bundle["history"], bundle["pruned_civ_stats"])
        assert _text([s["civ_stats"] for s in restored]) == _text([s["civ_stats"] for s in in_memory])

    def test_world_state_is_complete(self, real_run, tmp_path_factory):
        _, bundle = real_run
        names = [c["name"] for c in bundle["world_state"]["civilizations"]]
        assert PRUNED_CIV in names
        assert PRUNED_CIV in bundle["world_state"]["relationships"]

    def test_validation_oracles_read_identical_inputs(self, real_run, tmp_path):
        """Every bundle-reading oracle reports the same on the version-4 and version-5 bundle."""
        from chronicler.validate import run_oracles
        from chronicler.validation_io import load_seed_runs
        _, bundle = real_run
        v4 = restore_bundle(copy.deepcopy(bundle))
        v4["metadata"] = {**v4["metadata"], "bundle_version": 4}
        reports = {}
        seed_runs = {}
        for tag, data in (("v4", v4), ("v5", bundle)):
            seed_dir = tmp_path / tag / "seed_1"
            seed_dir.mkdir(parents=True)
            (seed_dir / "chronicle_bundle.json").write_text(_text(data), encoding="utf-8")
            report = run_oracles(tmp_path / tag, ["era", "arcs", "regression", "artifacts"])
            report.pop("batch_dir")
            reports[tag] = report
            runs = load_seed_runs(tmp_path / tag)
            seed_runs[tag] = [{k: v for k, v in run.items() if k not in ("bundle_path", "seed_dir")}
                              for run in runs]
        for run4, run5 in zip(seed_runs["v4"], seed_runs["v5"]):
            run4["bundle"]["metadata"] = run5["bundle"]["metadata"]
        assert _text(seed_runs["v4"]) == _text(seed_runs["v5"])
        assert _text(reports["v4"]) == _text(reports["v5"])

    def test_analytics_report_is_identical(self, real_run, tmp_path):
        from chronicler.analytics import generate_report
        _, bundle = real_run
        v4 = restore_bundle(copy.deepcopy(bundle))
        reports = {}
        for tag, data in (("v4", v4), ("v5", bundle)):
            for seed in (1, 2):
                seed_dir = tmp_path / tag / f"seed_{seed}"
                seed_dir.mkdir(parents=True)
                (seed_dir / "chronicle_bundle.json").write_text(_text(data), encoding="utf-8")
            report = generate_report(tmp_path / tag)
            report["metadata"].pop("timestamp")
            reports[tag] = _text(report).replace(str(tmp_path / tag), "BATCH")
        assert reports["v4"] == reports["v5"]

    def test_governance_metrics_handle_pruned_history(self, real_run):
        from chronicler.governance_metrics import extract_governance_metrics
        _, bundle = real_run
        assert extract_governance_metrics([bundle]) == extract_governance_metrics([restore_bundle(bundle)])

    def test_curator_reads_pruned_and_restored_history(self, real_run):
        from chronicler.curator import curate
        from chronicler.models import Event, NamedEvent, TurnSnapshot
        _, bundle = real_run
        events = [Event.model_validate(e) for e in bundle["events_timeline"]]
        named = [NamedEvent.model_validate(e) for e in bundle["named_events"]]
        full = [TurnSnapshot.model_validate(s) for s in restore_bundle(bundle)["history"]]
        pruned = [TurnSnapshot.model_validate(s) for s in bundle["history"]]
        for history in (full, pruned):
            moments, gaps = curate(events=events, named_events=named, history=history, budget=8, seed=1)
            assert moments
        # Gap summaries no longer report a dead civ's treasury drift.
        _, gaps = curate(events=events, named_events=named, history=pruned, budget=8, seed=1)
        late = [g for g in gaps if g.turn_range[0] >= PRUNED_FROM]
        assert all(PRUNED_CIV not in g.stat_deltas for g in late)


def test_live_bundle_load_keeps_the_omitted_rows(real_run):
    from chronicler.live import _build_init_data_from_bundle, _validate_legacy_live_bundle
    _, bundle = real_run
    payload = {**bundle, "chronicle_entries": {}, "gap_summaries": []}
    validated = _validate_legacy_live_bundle(payload)
    assert validated["pruned_civ_stats"] == bundle["pruned_civ_stats"]
    init = _build_init_data_from_bundle(validated)
    assert init["pruned_civ_stats"] == bundle["pruned_civ_stats"]
    restored = restore_history(init["history"], init["pruned_civ_stats"])
    assert all(PRUNED_CIV in s["civ_stats"] for s in restored)
