"""Actual scalar kernel on tiny surrogates; no ordinary World/native runtime."""
import builtins
from dataclasses import FrozenInstanceError
import gc
import math
import pickle
import random
from types import SimpleNamespace as NS
import weakref

import pytest

from chronicler import practice_growth as P
from chronicler import techniques as T
from chronicler.techniques_state import TECHNIQUE_INDEX as K, TechniqueState


def world(rows=None, *, population=60, turn=7, regions=1):
    return NS(turn=turn, seed=42, civilizations=[], tuning_overrides={}, scholarship=None,
        scientific_claims=None, contact_ledger=None,
        regions=[NS(name=f"R{i}", controller=None, terrain="plains", river_mask=0,
                    resource_types=[0, 255, 255], adjacencies=[], population=population,
                    occupied_by=None, famine_cooldown=0) for i in range(regions)],
        techniques=TechniqueState(initialized_turn=0,
            rows=rows if rows is not None else [(0, K["irrigation"], .5, -1, T.CH_SEEDED, -1)]))


@pytest.fixture(autouse=True)
def fixed_rate(monkeypatch):
    monkeypatch.setattr(T, "_rate", lambda world: 1.0)


def effort(monkeypatch, values, *, event_id=""):
    import chronicler.scientific_claims as C
    calls = []
    def prepare(w, acc=None, *, events=None):
        calls.append((w.turn, acc))
        if w.scientific_claims.last_effort_turn != w.turn:
            w.scientific_claims.last_effort_turn = w.turn
            w.scientific_claims.last_effort = [
                NS(seat=0, region=0, recipe="irrigation", share=1/3, confidence=1/3, paid=1, event_id=event_id),
                NS(seat=0, region=0, recipe="masonry", share=2/3, confidence=2/3, paid=0, event_id=event_id)]
            w.debits += 1
        return dict(values)
    monkeypatch.setattr(C, "prepare_adoption_effort", prepare)
    return calls


def funded(w):
    w.scientific_claims = NS(last_effort_turn=-1, last_effort=[])
    w.debits = 0
    return w


def capture(monkeypatch, w, *, grants=None, recipe="irrigation", **options):
    if grants is not None:
        funded(w)
        effort(monkeypatch, grants)
    observer = P.PracticeGrowthObserver([(0, recipe)], **options)
    assert observer.run_phase(w) == []
    return observer, observer.read_latest(expected_source_turn=w.turn)


def test_real_scalar_phase_preserves_exact_state_rng_and_single_allocation(monkeypatch):
    rows = [(0, K[key], .5, -1, T.CH_SEEDED, -1) for key in ("irrigation", "masonry")]
    plain, observed = funded(world(rows)), funded(world(rows))
    grants = {(0, K["irrigation"]): .01/3, (0, K["masonry"]): .02/3}
    calls = effort(monkeypatch, grants)
    original = T._derive_eras
    def normal_random_marker(w, *args):
        w.marker = random.random()
        return original(w, *args)
    monkeypatch.setattr(T, "_derive_eras", normal_random_marker)
    rng = random.getstate()
    expected = T.tick_techniques(plain); expected_rng = random.getstate()
    random.setstate(rng)
    observer = P.PracticeGrowthObserver([(0, "masonry"), (0, "irrigation")])
    assert observer.run_phase(observed) == expected
    assert pickle.dumps(observed) == pickle.dumps(plain)
    assert random.getstate() == expected_rng
    assert len(calls) == 2 and plain.debits == observed.debits == 1
    result = observer.read_latest(expected_source_turn=7)
    assert result.status == "captured" and result.scope == "phase"
    assert [row.recipe for row in result.rows] == ["irrigation", "masonry"]
    irrigation, masonry = result.rows
    assert irrigation.payments[0].bookkeeping_paid == 1
    assert masonry.payments[0].bookkeeping_paid == 0 and masonry.payments[0].allocation_group_paid == 1
    assert irrigation.kernel.paid_growth_rhs > 0 and masonry.kernel.paid_growth_rhs > 0
    assert masonry.allowance.hex() == grants[0, K["masonry"]].hex()
    assert masonry.payments[0].event_id == "" and masonry.allocations_observed
    assert observer.read_latest(expected_source_turn=7) is result
    assert all("observer" not in key and "trace" not in key for key in observed.__dict__)


@pytest.mark.parametrize("kwargs", [
    {"max_rows": True}, {"max_rows": 0}, {"max_rows": 65},
    {"max_encoded_bytes": True}, {"max_encoded_bytes": 0}, {"max_encoded_bytes": 65537},
])
def test_invalid_limits_are_rejected_before_any_phase(kwargs):
    with pytest.raises(ValueError): P.PracticeGrowthObserver([], **kwargs)


@pytest.mark.parametrize("selection", [None, iter([]), [None], [[0]], [[True, "irrigation"]],
    [[-1, "irrigation"]], [[2**32, "irrigation"]], [[0, None]], [[0, "invented_recipe"]],
    [[0, "irrigation"], [0, "irrigation"]], [(i, "irrigation") for i in range(65)]])
def test_invalid_selection_is_rejected(selection):
    with pytest.raises(ValueError): P.PracticeGrowthObserver(selection)


@pytest.mark.parametrize("expected", [True, -1, 2**32, 1.0])
def test_expected_turn_is_an_exact_bounded_integer(expected):
    with pytest.raises(ValueError): P.PracticeGrowthObserver([]).read_latest(expected_source_turn=expected)


def test_paid_rhs_is_not_net_change_and_retains_actual_ordered_values(monkeypatch):
    monkeypatch.setattr(T, "ADOPT_RATE", 0.)
    observer, result = capture(monkeypatch, world(), grants={(0, K["irrigation"]): .01})
    row = result.rows[0]; kernel = row.kernel
    assert result.status == "captured" and kernel.paid_status == "computed"
    assert kernel.allowance_used == .01 and kernel.paid_growth_rhs.hex() == (.0025).hex()
    assert kernel.ordinary_growth == 0 and kernel.total_growth.hex() == (.0025).hex()
    # The original left-associated expression is one ULP below the .4975 literal.
    assert kernel.forgetting == .005 and kernel.pre_clip.hex() == "0x1.fd70a3d70a3d6p-2"
    assert row.final_value == .4975 < kernel.before and kernel.kept
    assert kernel.clipped == kernel.pre_clip and kernel.rounded == row.final_value


@pytest.mark.parametrize("case", ["no_effort", "zero_effort", "zero_disruption", "missing_prerequisite", "above_cap", "zero_practice"])
def test_blocked_not_computed_and_computed_zero_are_distinct(monkeypatch, case):
    recipe = "roads" if case == "missing_prerequisite" else "irrigation"
    p = 0. if case == "zero_practice" else .3 if case == "above_cap" else .5
    w = world([(0, K[recipe], p, -1, T.CH_SEEDED, -1)])
    grants = None if case == "no_effort" else {(0, K[recipe]): 0. if case == "zero_effort" else .01}
    if case == "zero_disruption": w.regions[0].occupied_by = "occupier"
    if case == "above_cap":
        original = T._suitability
        def unsuitable(*args):
            matrix = original(*args); matrix[0][K[recipe]] = False; return matrix
        monkeypatch.setattr(T, "_suitability", unsuitable)
    _, result = capture(monkeypatch, w, grants=grants, recipe=recipe)
    row = result.rows[0]; k = row.kernel
    expected = {"no_effort":"not_supplied", "zero_effort":"computed_zero", "zero_disruption":"computed_zero",
                "missing_prerequisite":"blocked_prerequisites", "above_cap":"blocked_headroom", "zero_practice":"blocked_headroom"}
    assert k.paid_status == expected[case]
    assert (k.paid_growth_rhs == 0) if case in ("zero_effort", "zero_disruption") else k.paid_growth_rhs is None
    if case == "above_cap": assert k.cap == .2 and row.final_value > .2
    if case == "zero_disruption": assert row.allowance > 0 and k.disruption == 0
    if case == "zero_practice": assert not row.final_present and k.rounded == 0


@pytest.mark.parametrize("case", ["no_source", "empty_population", "missing_region"])
def test_unobserved_assignment_never_invents_zero_or_a_gate_reason(monkeypatch, case):
    w = world(rows=[] if case == "no_source" else None, population=0 if case == "empty_population" else 60)
    selected = 99 if case == "missing_region" else 0
    observer = P.PracticeGrowthObserver([(selected, "irrigation")])
    observer.run_phase(w)
    row = observer.read_latest(expected_source_turn=7).rows[0]
    assert row.kernel is None and row.kernel_status == "unobserved"
    if case == "empty_population": assert row.final_present and row.final_value == .475
    else: assert not row.final_present and row.final_value is None


@pytest.mark.parametrize("p,expected", [(.0078125, .007812), (.0234375, .023438),
    (math.nextafter(.0078125, 0.), .007812), (math.nextafter(.0078125, 1.), .007813)])
def test_python_six_decimal_half_even_and_neighbor_rounding(monkeypatch, p, expected):
    monkeypatch.setattr(T, "ADOPT_RATE", 0.); monkeypatch.setattr(T, "BASE_FORGET", 0.)
    _, result = capture(monkeypatch, world([(0, K["irrigation"], p, -1, T.CH_SEEDED, -1)]))
    k = result.rows[0].kernel
    assert k.pre_clip.hex() == p.hex() and k.clipped.hex() == p.hex()
    assert k.rounded.hex() == expected.hex()


@pytest.mark.parametrize("case", ["upper_clip", "lower_clip", "below_drop", "at_drop", "paid_rounds_away"])
def test_clip_round_and_drop_are_separate_observed_stages(monkeypatch, case):
    monkeypatch.setattr(T, "ADOPT_RATE", 8. if case == "upper_clip" else 0.)
    monkeypatch.setattr(T, "BASE_FORGET", 3. if case == "lower_clip" else 0.)
    p = .001999 if case == "below_drop" else .002 if case == "at_drop" else .5
    grants = {(0, K["irrigation"]): 1e-8} if case == "paid_rounds_away" else None
    _, result = capture(monkeypatch, world([(0, K["irrigation"], p, -1, T.CH_SEEDED, -1)]), grants=grants)
    row = result.rows[0]; k = row.kernel
    if case == "upper_clip": assert k.pre_clip == 2.5 and k.clipped == k.rounded == row.final_value == 1.
    elif case == "lower_clip": assert k.pre_clip == -1. and k.clipped == k.rounded == 0 and not row.final_present
    elif case == "below_drop": assert k.rounded == .001999 and not k.kept and row.final_value is None
    elif case == "at_drop": assert k.rounded == row.final_value == .002 and k.kept
    else: assert k.paid_growth_rhs == 2.5e-9 and k.pre_clip > .5 and k.rounded == row.final_value == .5


def test_actual_scholar_carry_separates_kernel_result_from_final_commit():
    from chronicler.scholarship_state import ScholarshipState
    rows = [(r, K["masonry"], .5, -1, T.CH_SEEDED, -1) for r in [0, 1]]
    rows += [(0, K["roads"], .6, -1, T.CH_SEEDED, -1)]
    left, right = world(rows, regions=2), world(rows, regions=2)
    for w in [left, right]: w.scholarship = ScholarshipState(carries=[(0, 1, 0, 0)])
    T.tick_techniques(left)
    observer = P.PracticeGrowthObserver([(0, "roads"), (1, "roads")]); observer.run_phase(right)
    assert pickle.dumps(left) == pickle.dumps(right)
    source, destination = observer.read_latest(expected_source_turn=7).rows
    assert source.kernel.rounded > source.final_value
    assert destination.kernel is None and destination.final_value == .2
    assert right.scholarship.carries == []


@pytest.mark.parametrize("surface", ["selected", "kernel", "commit", "finish", "begin", "kernel_after", "commit_after", "begin_after"])
def test_reporting_failure_preserves_physics_and_cannot_resurrect_prior_payload(monkeypatch, surface):
    w, plain = world(), world()
    observer = P.PracticeGrowthObserver([(0, "irrigation")]); observer.run_phase(w)
    T.tick_techniques(plain)
    assert pickle.dumps(w) == pickle.dumps(plain)
    method = surface.removesuffix("_after")
    target = P._Capture if method in ("selected", "kernel", "commit") else observer
    name = method if method in ("selected", "kernel", "commit") else "_" + method
    original = getattr(target, name)
    def fail(*args, **kwargs):
        if surface.endswith("_after"): original(*args, **kwargs)
        raise RuntimeError("private diagnostic detail")
    monkeypatch.setattr(target, name, fail)
    T.tick_techniques(plain); observer.run_phase(w)
    assert pickle.dumps(w) == pickle.dumps(plain)
    result = observer.read_latest(expected_source_turn=7)
    assert result.status == "unavailable" and result.reason == "capture_failed" and not result.rows
    assert "private" not in repr(result)


def test_same_turn_physics_failure_invalidates_old_frame_and_propagates(monkeypatch):
    observer = P.PracticeGrowthObserver([(0, "irrigation")]); w = world(); observer.run_phase(w)
    def fail(*args): raise ValueError("ordinary physics failure")
    monkeypatch.setattr(T, "_rate", fail)
    with pytest.raises(ValueError, match="ordinary physics"): observer.run_phase(w)
    assert observer.read_latest(expected_source_turn=7).reason == "attempt_incomplete"


@pytest.mark.parametrize("result_api", [False, True])
def test_explicit_turn_api_routes_one_phase_and_seals_only_after_normal_turn_return(monkeypatch, result_api):
    import chronicler.simulation as simulation
    calls = []
    def turn(w, selector, narrator, *, _practice_trace=None):
        calls.append((selector, narrator)); T.tick_techniques(w, _practice_trace=_practice_trace)
        w.turn += 1
        return NS(chronicle_text="normal turn", marker=9)
    monkeypatch.setattr(simulation, "run_turn_result", turn)
    observer = P.PracticeGrowthObserver([(0, "irrigation")]); w = world()
    result = (observer.run_turn_result if result_api else observer.run_turn)(w, "selector", "narrator")
    assert (result.marker == 9) if result_api else result == "normal turn"
    assert calls == [("selector", "narrator")] and w.turn == 8
    record = observer.read_latest(expected_source_turn=7)
    assert record.status == "captured" and record.scope == "turn"
    assert observer.read_latest(expected_source_turn=8).reason == "stale_request"
    def late_failure(w, *args, _practice_trace=None):
        T.tick_techniques(w, _practice_trace=_practice_trace)
        raise LookupError("later ordinary turn phase")
    monkeypatch.setattr(simulation, "run_turn_result", late_failure)
    with pytest.raises(LookupError): observer.run_turn(w, "selector", "narrator")
    assert observer.read_latest(expected_source_turn=8).reason == "attempt_incomplete"


def test_bounded_payload_empty_selection_inactive_phase_and_close():
    observer = P.PracticeGrowthObserver([(0, "irrigation")], max_encoded_bytes=1); w = world()
    observer.run_phase(w)
    assert observer.read_latest(expected_source_turn=7).reason == "retention_limit"
    observer = P.PracticeGrowthObserver([]); observer.run_phase(w)
    assert observer.read_latest(expected_source_turn=7).rows == ()
    assert observer.read_latest(expected_source_turn=7).status == "captured"
    w.techniques = None; observer.run_phase(w)
    assert observer.read_latest(expected_source_turn=7).reason == "phase_unobserved"
    observer.close(); observer.run_phase(w)
    assert observer.read_latest(expected_source_turn=7).reason == "closed"
    with pytest.raises(TypeError, match="transient"): pickle.dumps(observer)


def test_default_phase_has_no_optional_import_fields_or_observation_calls(monkeypatch):
    w = world(); keys = set(w.__dict__); original_import = builtins.__import__
    def no_observer_import(name, *args, **kwargs):
        if name == "chronicler.practice_growth": pytest.fail("default imported practice observer")
        return original_import(name, *args, **kwargs)
    def forbidden(*args, **kwargs): pytest.fail("default used observer")
    monkeypatch.setattr(builtins, "__import__", no_observer_import)
    monkeypatch.setattr(P._Capture, "kernel", forbidden); monkeypatch.setattr(P._Capture, "commit", forbidden)
    T.tick_techniques(w)
    assert set(w.__dict__) == keys


def test_supplied_zero_without_allocation_is_distinct_from_missing_payment_observation(monkeypatch):
    import chronicler.scientific_claims as C
    w = funded(world()); w.scientific_claims.last_effort_turn = w.turn
    monkeypatch.setattr(C, "prepare_adoption_effort", lambda *args, **kwargs: {})
    observer = P.PracticeGrowthObserver([(0, "irrigation")]); observer.run_phase(w)
    row = observer.read_latest(expected_source_turn=7).rows[0]
    assert row.allowance == 0 and not row.allowance_present
    assert row.allocations_observed and row.payments == () and row.kernel.paid_status == "computed_zero"
    w.scientific_claims.last_effort_turn = 6
    monkeypatch.setattr(C, "prepare_adoption_effort", lambda *args, **kwargs: {(0, K["irrigation"]): .01})
    observer.run_phase(w); row = observer.read_latest(expected_source_turn=7).rows[0]
    assert row.allowance > 0 and row.kernel.paid_growth_rhs > 0
    assert not row.allocations_observed and row.payments == ()


@pytest.mark.parametrize("closed", [False, True])
def test_observer_and_retained_readout_never_own_the_surrogate_world(closed):
    class Surrogate(NS): pass
    w = Surrogate(**world().__dict__); ref = weakref.ref(w)
    observer = P.PracticeGrowthObserver([(0, "irrigation")]); observer.run_phase(w)
    record = observer.read_latest(expected_source_turn=7)
    if closed: observer.close()
    del w; gc.collect()
    assert ref() is None and record.rows[0].kernel is not None


def test_early_turn_failure_cannot_expose_a_previous_same_turn_phase(monkeypatch):
    import chronicler.simulation as simulation
    w = world(); observer = P.PracticeGrowthObserver([(0, "irrigation")]); observer.run_phase(w)
    def fail(*args, **kwargs): raise ValueError("before phase four")
    monkeypatch.setattr(simulation, "run_turn_result", fail)
    with pytest.raises(ValueError, match="before phase four"): observer.run_turn_result(w, None, None)
    record = observer.read_latest(expected_source_turn=7)
    assert record.status == "unavailable" and record.reason == "attempt_incomplete" and not record.rows


def test_cached_rows_are_immutable_and_selection_cannot_exceed_row_budget():
    with pytest.raises(ValueError): P.PracticeGrowthObserver([(0, "irrigation"), (1, "masonry")], max_rows=1)
    observer = P.PracticeGrowthObserver([(0, "irrigation")]); observer.run_phase(world())
    row = observer.read_latest(expected_source_turn=7).rows[0]
    with pytest.raises(FrozenInstanceError): row.final_value = 1.
    with pytest.raises(FrozenInstanceError): row.kernel.before = 0.


def test_begin_reporting_failure_has_no_old_source_identity(monkeypatch):
    w = world(); observer = P.PracticeGrowthObserver([(0, "irrigation")]); observer.run_phase(w)
    assert observer.read_latest(expected_source_turn=7).attempt == 1
    w.turn = 8
    def fail(*args): raise RuntimeError("begin diagnostic failure")
    monkeypatch.setattr(observer, "_begin", fail)
    observer.run_phase(w)
    record = observer.read_latest(expected_source_turn=8)
    assert record.reason == "capture_failed" and record.source_turn is None and record.attempt == 2


def test_unselected_pairs_do_not_construct_kernel_records(monkeypatch):
    rows = [(r, K[recipe], .5, -1, T.CH_SEEDED, -1) for r in [0, 1] for recipe in ["irrigation", "masonry"]]
    w = world(rows, regions=2); calls = []; original = P._Capture.kernel
    def record(self, region, technique, **values):
        calls.append((region, technique)); return original(self, region, technique, **values)
    monkeypatch.setattr(P._Capture, "kernel", record)
    observer = P.PracticeGrowthObserver([(0, "irrigation")]); observer.run_phase(w)
    assert calls == [(0, K["irrigation"])] and len(w.techniques.rows) == 4
    assert len(observer.read_latest(expected_source_turn=7).rows) == 1


@pytest.mark.parametrize("surface", ["begin", "finish"])
def test_cancellation_after_partial_reporting_clears_pending_and_published_frames(monkeypatch, surface):
    w, plain = world(), world()
    observer = P.PracticeGrowthObserver([(0, "irrigation")]); observer.run_phase(w); T.tick_techniques(plain)
    name = "_" + surface; original = getattr(observer, name)
    def interrupt(*args, **kwargs):
        original(*args, **kwargs)
        raise KeyboardInterrupt("caller cancellation")
    monkeypatch.setattr(observer, name, interrupt)
    if surface == "finish": T.tick_techniques(plain)
    with pytest.raises(KeyboardInterrupt): observer.run_phase(w)
    assert pickle.dumps(w) == pickle.dumps(plain)
    record = observer.read_latest(expected_source_turn=7)
    assert record.reason == "attempt_incomplete" and not record.rows and observer._pending is None
