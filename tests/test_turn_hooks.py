"""Feature-hook order of ``run_turn_result`` (turn-loop consolidation, CON-4).

The golden ``tests/fixtures/turn_loop/hook_order.json`` was recorded with
``tests/support/turn_order_trace.py`` before any hook table existed: every
feature gate forced on or off, every hook target stubbed, core phases quieted
and the accumulator flushes recorded, over two turns per combination. A hook
table must reproduce each sequence unchanged.
"""
from __future__ import annotations

import pytest

from tests.support import turn_order_trace as T

GOLDEN = T.load()
RUN_NAMES = [f"{combination}/{mode}" for combination, mode in T.RUNS]


def test_golden_records_every_run_and_combination():
    assert GOLDEN["schema_version"] == T.SCHEMA_VERSION
    assert GOLDEN["turns"] == T.TURNS
    assert list(GOLDEN["runs"]) == RUN_NAMES
    assert GOLDEN["combinations"] == {name: list(features) for name, features in T.COMBINATIONS.items()}
    assert set(T.COMBINATIONS["all"]) == set(T.FEATURES)


@pytest.mark.parametrize("run", RUN_NAMES)
def test_hook_order_matches_golden(monkeypatch, run):
    combination, mode = run.split("/")
    assert T.trace(monkeypatch, combination, mode) == GOLDEN["runs"][run]


def _turns(rows):
    turn, out = [], []
    for row in rows:
        turn.append(tuple(row))
        if row == ["core", "narrator"]:
            out.append(turn)
            turn = []
    assert turn == []
    return out


@pytest.mark.parametrize("run", RUN_NAMES)
def test_phase10_order_and_flush_boundaries(run):
    combination, mode = run.split("/")
    on = set(T.COMBINATIONS[combination])
    turns = _turns(GOLDEN["runs"][run])
    assert len(turns) == T.TURNS
    for rows in turns:
        phase10 = [key for slot, key in rows if slot.startswith("p10.")]
        expected = [key for key in T.PHASE10_ORDER if key.split(".")[0] in on]
        assert phase10 == expected
        if not phase10:
            continue
        consequences = rows.index(("core", "phase_consequences"))
        first, last = (rows.index(next(r for r in rows if r[0].startswith("p10."))),
                       max(i for i, r in enumerate(rows) if r[0].startswith("p10.")))
        assert consequences < first
        flushes = [i for i, r in enumerate(rows) if r[0] == "flush"]
        if mode == "hybrid":
            # Phase 10 hooks run between the pre-tick flush and the Phase 10 flush.
            assert len(flushes) == 3 and flushes[0] < first and last < flushes[1]
        elif mode == "off":
            assert rows[flushes[0]] == ("flush", "apply") and flushes == flushes[:1] and flushes[0] < first
        else:
            assert flushes == flushes[:1] and rows[flushes[0]] == ("flush", "apply_keep")


def test_disabled_features_record_no_hook():
    for mode in ("off", "hybrid"):
        rows = GOLDEN["runs"][f"none/{mode}"]
        assert {slot for slot, _ in rows} <= {"core", "flush"}


def test_every_target_is_reached_by_some_run():
    seen = {tuple(row) for rows in GOLDEN["runs"].values() for row in rows}
    labels = {(slot, key) for slot, key, _, _ in T.TARGETS}
    labels |= {(slot, key) for target, (_, slot) in T.SECOND_SITE.items()
               for row_slot, key, row_target, _ in T.TARGETS if row_target == target}
    assert labels <= seen
