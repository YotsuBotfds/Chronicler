"""Scalar caller/observer surrogates only; no World, native runtime or physics."""
from dataclasses import asdict
import json
import pickle
import random
from types import SimpleNamespace as NS

import numpy as np
import pytest

from chronicler import practice_growth as P
from scripts import research_practice_adapter as A
from scripts import research_practice_recorder as R


class Observer:
    def __init__(self, folder, *, error=None, read_error=None):
        self.folder, self.error, self.read_error = folder, error, read_error
        self.calls, self.reads, self.closes = [], [], 0

    def run_turn_result(self, world, *args, **kwargs):
        baseline = json.loads((self.folder / "practice-counter-baseline.json").read_bytes())
        assert baseline["initial_effort_spent"] == world.scientific_claims.effort_spent
        self.calls.append((world, args, kwargs))
        if self.error:
            raise self.error
        source = world.turn
        world.turn += 1
        rows = tuple(P.PracticeGrowthRow(region, recipe, 0., False, True, (), None, False, None)
                     for region, recipe in R.SELECTED)
        size = len(R.encoded([asdict(row) for row in rows]))
        self.frame = P.PracticeGrowthReadout("captured", None, source, len(self.calls), "turn", rows, size)
        self.result = NS(observation=NS(source_turn=source, completed_turn=world.turn))
        return self.result

    def read_latest(self, *, expected_source_turn):
        self.reads.append(expected_source_turn)
        if self.read_error:
            raise self.read_error
        assert self.frame.source_turn == expected_source_turn
        return self.frame

    def close(self):
        self.closes += 1


def setup(tmp_path, *, role="active", effort=9, expected=9, error=None, read_error=None):
    observer = Observer(tmp_path, error=error, read_error=read_error)
    world = NS(seed=2001, turn=0 if role == "parent" else 60,
               scientific_claims=NS(effort_spent=effort))
    owner = A.StudyPracticeOwner(tmp_path, seed=2001, role=role, observer=observer,
                                 expected_checkpoint_effort=None if role == "parent" else expected)
    return owner, observer, world


@pytest.mark.parametrize("role", R.ROLES)
def test_actual_nonzero_baseline_precedes_one_call_with_exact_handoff(tmp_path, role):
    owner, observer, world = setup(tmp_path, role=role)
    token = object()
    try:
        result = owner.run_turn_result(world, token, marker=token)
        assert result is observer.result
        assert observer.calls == [(world, (token,), dict(marker=token))]
        assert owner.baseline["initial_effort_spent"] == owner.recorder.initial == 9
        assert owner.baseline["expected_checkpoint_effort"] == (None if role == "parent" else 9)
        assert owner.pending == (0 if role == "parent" else 60)
        assert owner.attempted == owner.completed == 1 and not observer.reads
        record = owner.record_turn_end(world)
        assert record["accounting"] == dict(status="matched", before=9, after=9, delta=0, groups=[])
        assert observer.reads == [record["expected_source_turn"]] and owner.pending is None
    finally:
        owner.close()


@pytest.mark.parametrize("expected", [None, True, -1, 2**32])
def test_fork_requires_typed_checkpoint_counter(tmp_path, expected):
    with pytest.raises(R.TraceContractError):
        setup(tmp_path, expected=expected)
    assert list(tmp_path.iterdir()) == []


def test_mismatched_actual_counter_refuses_before_any_call_or_journal(tmp_path):
    owner, observer, world = setup(tmp_path, expected=8)
    with pytest.raises(R.TraceContractError, match="checkpoint effort differs"):
        owner.run_turn_result(world)
    assert owner.failed and observer.calls == [] and list(tmp_path.iterdir()) == []
    owner.close()


@pytest.mark.parametrize("error", [ValueError("observer failed"), KeyboardInterrupt(), SystemExit(7)])
def test_no_retry_after_any_observer_failure_or_cancellation(tmp_path, error):
    owner, observer, world = setup(tmp_path, error=error)
    try:
        with pytest.raises(type(error)):
            owner.run_turn_result(world)
        assert owner.attempted == 1 and owner.completed == 0 and owner.failed
        with pytest.raises(R.TraceContractError):
            owner.run_turn_result(world)
        assert len(observer.calls) == 1 and world.turn == 60
    finally:
        owner.close()


def test_failed_baseline_write_never_calls_observer_or_overwrites_original(tmp_path):
    path = tmp_path / "practice-counter-baseline.json"
    path.write_bytes(b"preserved")
    owner, observer, world = setup(tmp_path)
    try:
        with pytest.raises(FileExistsError):
            owner.run_turn_result(world)
        assert owner.failed and observer.calls == [] and path.read_bytes() == b"preserved"
    finally:
        owner.close()


def test_unrecorded_boundary_cannot_advance_physics(tmp_path):
    owner, observer, world = setup(tmp_path)
    try:
        owner.run_turn_result(world)
        with pytest.raises(R.TraceContractError):
            owner.run_turn_result(world)
        assert owner.failed and len(observer.calls) == 1 and world.turn == 61
    finally:
        owner.close()


@pytest.mark.parametrize("error", [ValueError("metadata read"), KeyboardInterrupt()])
def test_reporting_failure_does_not_replay_completed_physics(tmp_path, error):
    owner, observer, world = setup(tmp_path, read_error=error)
    try:
        result = owner.run_turn_result(world)
        with pytest.raises(type(error)):
            owner.record_turn_end(world)
        assert result is observer.result and world.turn == 61 and owner.completed == 1
        with pytest.raises(R.TraceContractError):
            owner.run_turn_result(world)
        assert len(observer.calls) == 1 and owner.pending == 60
    finally:
        owner.close()


@pytest.mark.parametrize("field,value", [("seed", 2002), ("seed", True), ("turn", 59), ("turn", True)])
def test_wrong_world_clock_or_seed_never_calls_observer(tmp_path, field, value):
    owner, observer, world = setup(tmp_path)
    setattr(world, field, value)
    try:
        with pytest.raises(R.TraceContractError):
            owner.run_turn_result(world)
        assert owner.failed and not observer.calls
    finally:
        owner.close()


@pytest.mark.parametrize("field,value", [("source_turn", 59), ("source_turn", True),
                                        ("completed_turn", 62), ("completed_turn", True)])
def test_malformed_result_clock_retains_one_call_without_success(tmp_path, field, value):
    owner, observer, world = setup(tmp_path)
    original = observer.run_turn_result
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        setattr(result.observation, field, value)
        return result
    observer.run_turn_result = changed
    try:
        with pytest.raises(R.TraceContractError):
            owner.run_turn_result(world)
        assert world.turn == 61 and len(observer.calls) == 1 and owner.completed == 0 and owner.failed
    finally:
        owner.close()


def test_finish_incomplete_cannot_publish_positive_index(tmp_path):
    owner, observer, world = setup(tmp_path)
    try:
        owner.run_turn_result(world)
        owner.record_turn_end(world)
        with pytest.raises(R.TraceContractError):
            owner.finish()
        assert owner.failed and not (tmp_path / "practice-trace-index.json").exists()
    finally:
        owner.close()


def test_transience_no_world_retention_rng_and_idempotent_close(tmp_path):
    owner, observer, world = setup(tmp_path)
    before_py, before_np = random.getstate(), np.random.get_state()
    owner.run_turn_result(world)
    owner.record_turn_end(world)
    with pytest.raises(TypeError, match="transient"):
        pickle.dumps(owner)
    assert all(value is not world for value in vars(owner).values())
    owner.close()
    owner.close()
    assert observer.closes == 1 and owner.recorder.closed and random.getstate() == before_py
    after_np = np.random.get_state()
    assert before_np[0] == after_np[0] and np.array_equal(before_np[1], after_np[1])
    assert before_np[2:] == after_np[2:]
    with pytest.raises(R.TraceContractError):
        owner.run_turn_result(world)
    assert len(observer.calls) == 1
