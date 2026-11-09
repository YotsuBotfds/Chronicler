"""Treasury seam (turn-loop consolidation, CON-3).

The golden ``tests/fixtures/turn_loop/accumulator_trace.json`` was recorded
with ``tests/support/accumulator_trace.py`` before the seam existed: every
``StatAccumulator.add`` and the end-of-turn civ stats of 12 ``--agents off``
turns per case. Every treasury refactor must reproduce it unchanged.
"""
from __future__ import annotations

import json

import pytest

from tests.support import accumulator_trace as AT

TRACE = AT.load()
TRACE_CASES = [(kind, seed, techniques) for kind, techniques in AT.CASES for seed in AT.SEEDS]


def _case_name(kind, seed, techniques):
    return f"{kind}_s{seed}" + ("_techniques" if techniques else "")


def test_accumulator_trace_golden_shape():
    assert TRACE["schema_version"] == AT.SCHEMA_VERSION
    assert TRACE["turns"] == AT.TURNS
    assert TRACE["stats"] == list(AT.TRACE_STATS)
    assert list(TRACE["cases"]) == [_case_name(*case) for case in TRACE_CASES]
    for rows in TRACE["cases"].values():
        assert [row[1] for row in rows if row[0] == "end"] == list(range(AT.TURNS))
        assert any(row[0] == "add" and row[3] == "treasury" for row in rows)


@pytest.mark.parametrize("kind,seed,techniques", TRACE_CASES,
                         ids=[_case_name(*case) for case in TRACE_CASES])
def test_accumulator_trace_matches_golden(kind, seed, techniques):
    records = AT.trace_run(AT.build_world(kind, seed, techniques), seed)
    assert json.loads(json.dumps(records)) == TRACE["cases"][_case_name(kind, seed, techniques)]
