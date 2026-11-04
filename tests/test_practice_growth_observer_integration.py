"""Ordinary-World integration authored for REMOTE full CI, not offline chunks."""
import random

import numpy as np
import pytest

from chronicler import techniques as T
from chronicler.accumulator import StatAccumulator
from chronicler.models import ActionType
from chronicler.practice_growth import PracticeGrowthObserver
from chronicler.simulation import run_turn_result
from chronicler.techniques_state import TECHNIQUE_INDEX as K
from test_scientific_claims import _complete, _world


def rng_state():
    return random.getstate(), np.random.get_state()


def restore_rng(state):
    random.setstate(state[0]); np.random.set_state(state[1])


def assert_same_rng(left, right):
    assert left[0] == right[0]
    assert left[1][0] == right[1][0] and np.array_equal(left[1][1], right[1][1])
    assert left[1][2:] == right[1][2:]


@pytest.fixture(autouse=True)
def preserve_test_caller_streams():
    saved = rng_state()
    try:
        yield
    finally:
        restore_rng(saved)


@pytest.mark.parametrize("scope", ["phase", "turn"])
def test_genuine_world_dispatch_preserves_state_events_allocations_debits_and_rng(monkeypatch, scope):
    # The existing paid-runtime fixture already exercises this stable context
    # through fourteen real turns. Create two independent equal initial states.
    initial_rng = rng_state()
    left = _world(); restore_rng(initial_rng); right = _world()
    for w in (left, right):
        w.tuning_overrides["climate.trend_share"] = 1.
        for region in w.regions:
            region.terrain, region.population, region.carrying_capacity = "plains", 60, 1000
    if scope == "phase":
        setup_rng = rng_state(); _complete(left, monkeypatch); restore_rng(setup_rng); _complete(right, monkeypatch)
        left.turn = right.turn = 12
    assert left.model_dump_json() == right.model_dump_json()
    observer = PracticeGrowthObserver([(region, recipe) for region in range(len(right.regions))
                                       for recipe in ("irrigation", "masonry")])
    observed_positive_rhs = False
    selector = lambda *args: ActionType.DEVELOP
    narrator = lambda w, events: "|".join(event.event_id + ":" + event.event_type for event in events)
    for _ in range(1 if scope == "phase" else 14):
        source = left.turn; assert right.turn == source
        before = left.scientific_claims.effort_spent
        before_rng = rng_state()
        if scope == "phase":
            a_acc = StatAccumulator(); a = T.tick_techniques(left, acc=a_acc); a_acc.apply_keep(left)
        else:
            a = run_turn_result(left, selector, narrator, seed=left.seed + source)
        after_left_rng = rng_state(); restore_rng(before_rng)
        if scope == "phase":
            b_acc = StatAccumulator(); b = observer.run_phase(right, acc=b_acc); b_acc.apply_keep(right)
            assert a == b and left.turn == right.turn == source
        else:
            b = observer.run_turn_result(right, selector, narrator, seed=right.seed + source)
            assert a.chronicle_text == b.chronicle_text
            assert a.observation.source_turn == b.observation.source_turn == source
            assert a.observation.completed_turn == b.observation.completed_turn == source + 1
        assert_same_rng(after_left_rng, rng_state())
        assert left.model_dump_json() == right.model_dump_json()
        assert left.events_timeline == right.events_timeline
        assert [c.treasury for c in left.civilizations] == [c.treasury for c in right.civilizations]
        assert left.scientific_claims.last_effort == right.scientific_claims.last_effort
        frame = observer.read_latest(expected_source_turn=source)
        assert frame.status == "captured" and frame.scope == scope, frame.reason
        assert any(row.kernel is not None for row in frame.rows)
        actual = {(r, k): value for r, k, value, *_ in right.techniques.rows}
        groups = {}
        for row in frame.rows:
            key = row.region, K[row.recipe]
            assert row.final_present == (key in actual)
            if row.final_present: assert row.final_value.hex() == actual[key].hex()
            if row.payments: assert row.kernel is not None and row.allowance > 0
            if row.kernel is not None and row.kernel.paid_growth_rhs is not None and row.kernel.paid_growth_rhs > 0:
                observed_positive_rhs = True
                assert row.allowance > 0
            for payment in row.payments:
                groups[source, payment.seat, row.region] = payment.allocation_group_paid
        assert sum(groups.values()) == right.scientific_claims.effort_spent - before
    assert right.scientific_claims.effort_spent > 0 and observed_positive_rhs
    assert not any("observer" in key or "trace" in key for key in right.__dict__)
    observer.close()
