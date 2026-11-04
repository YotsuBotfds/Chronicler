"""Genuine execute_run cases for REMOTE full CI; excluded from offline chunks."""
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import random

import numpy as np
import pytest

from chronicler import main as M
from chronicler.practice_growth import PracticeGrowthObserver
from chronicler.run_checkpoint import read_checkpoint
from test_scientific_claims import _complete, _world


def rng_state():
    return random.getstate(), np.random.get_state()


def restore_rng(state):
    random.setstate(state[0])
    np.random.set_state(state[1])


def same_rng(left, right):
    assert left[0] == right[0]
    assert left[1][0] == right[1][0] and np.array_equal(left[1][1], right[1][1])
    assert left[1][2:] == right[1][2:]


@pytest.fixture(autouse=True)
def preserve_caller_rng():
    state = rng_state()
    try:
        yield
    finally:
        restore_rng(state)


def prepared_world(monkeypatch):
    # Reuse the paid-runtime fixture; normal execute_run owns all later turns.
    world = _world()
    world.tuning_overrides["climate.trend_share"] = 1.
    for region in world.regions:
        region.terrain, region.population, region.carrying_capacity = "plains", 60, 1000
    _complete(world, monkeypatch)
    world.turn = 12
    return world


def args_for(folder, world):
    return M._build_parser().parse_args([
        "--seed", str(world.seed), "--turns", "14", "--agents", "off", "--simulate-only",
        "--regions", str(len(world.regions)), "--civs", str(len(world.civilizations)),
        "--reflection-interval", "100", "--output", str(folder / "chronicle.md"),
        "--state", str(folder / "state.json"), "--checkpoint-turns", "13,14"])


class Harvest:
    def __init__(self, observer=None):
        self.observer, self.frames, self.states = observer, [], []

    def bind(self, save, config):
        self.config = config

    def live_record(self):
        return None

    def turn_end(self, world):
        self.states.append((world.turn, world.model_dump_json()))
        if self.observer is not None:
            self.frames.append(self.observer.read_latest(expected_source_turn=world.turn - 1))
        return False


def ordinary_outputs(folder):
    files = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(folder).as_posix()
        if name in {"checkpoint_turn_13.ckpt", "checkpoint_turn_14.ckpt"}:
            continue  # These trusted exact checkpoints are validated separately below.
        data = path.read_bytes()
        if name == "chronicle_bundle.json":
            bundle = json.loads(data)
            stamp = bundle["metadata"].pop("generated_at")
            assert isinstance(stamp, str) and datetime.fromisoformat(stamp).tzinfo is not None
            data = json.dumps(bundle, ensure_ascii=False, allow_nan=False).encode()
        files[name] = data
    return files


@pytest.mark.parametrize("default_form", ["omitted", "none"])
def test_execute_run_observer_preserves_real_outputs_payments_rng_and_checkpoint_state(
        tmp_path, monkeypatch, default_form):
    initial = rng_state()
    left = prepared_world(monkeypatch)
    ready = rng_state()
    restore_rng(initial)
    right = prepared_world(monkeypatch)
    same_rng(ready, rng_state())
    assert left.model_dump_json() == right.model_dump_json()
    before_spent = right.scientific_claims.effort_spent
    observer = PracticeGrowthObserver([(r, k) for r in range(len(right.regions))
                                      for k in ("irrigation", "masonry")], max_rows=10)
    plain, observed = Harvest(), Harvest(observer)
    a_dir, b_dir = tmp_path / "plain", tmp_path / "observed"
    defaults = {} if default_form == "omitted" else {"practice_observer": None}
    before = rng_state()
    a = M.execute_run(args_for(a_dir, left), world=left, turn_boundary=plain, **defaults)
    after = rng_state()
    restore_rng(before)
    b = M.execute_run(args_for(b_dir, right), world=right, turn_boundary=observed,
                      practice_observer=observer)
    same_rng(after, rng_state())
    assert a.output_dir == a_dir and b.output_dir == b_dir
    a_stats, b_stats = asdict(a), asdict(b)
    del a_stats["output_dir"], b_stats["output_dir"]
    assert a_stats == b_stats and a.total_turns == b.total_turns == 2
    assert left.turn == right.turn == 14
    assert left.model_dump_json() == right.model_dump_json()
    assert left.events_timeline == right.events_timeline
    assert left.scientific_claims.last_effort == right.scientific_claims.last_effort
    assert plain.states == observed.states and plain.config == observed.config
    assert ordinary_outputs(a_dir) == ordinary_outputs(b_dir)
    assert [frame.source_turn for frame in observed.frames] == [12, 13]
    assert [frame.attempt for frame in observed.frames] == [1, 2]
    groups, bookkept, zero_paid_grant, computed_paid = {}, {}, False, False
    for frame in observed.frames:
        assert frame.status == "captured" and frame.scope == "turn" and len(frame.rows) == 10
        for row in frame.rows:
            if row.kernel is not None and row.kernel.paid_growth_rhs is not None:
                computed_paid = True
            for payment in row.payments:
                assert row.allowance is not None and row.allowance > 0
                key = frame.source_turn, payment.seat, row.region
                assert key not in groups or groups[key] == payment.allocation_group_paid
                groups[key] = payment.allocation_group_paid
                bookkept[key] = bookkept.get(key, 0) + payment.bookkeeping_paid
                zero_paid_grant |= payment.bookkeeping_paid == 0
    assert groups == bookkept and sum(groups.values()) == right.scientific_claims.effort_spent - before_spent > 0
    assert zero_paid_grant and computed_paid
    header_keys = {"format", "version", "turn", "seed", "start_turn", "num_turns", "world",
                   "flags", "run_config", "exact", "lineage", "identity"}
    for turn in (13, 14):
        x = read_checkpoint(a_dir / f"checkpoint_turn_{turn}.ckpt")
        y = read_checkpoint(b_dir / f"checkpoint_turn_{turn}.ckpt")
        assert x.exact and y.exact and not x.mismatches and not y.mismatches
        assert set(x.header) == set(y.header) == header_keys | {"sections"}
        assert all(x.header[key] == y.header[key] for key in header_keys)
        assert x.state.world.model_dump_json() == y.state.world.model_dump_json()
        assert [h.model_dump_json() for h in x.state.history] == [h.model_dump_json() for h in y.state.history]
        assert len(x.state.history) == len(y.state.history) == turn - 12
        for name in ("chronicle_entries", "era_reflections", "pending_injections", "run_config", "live"):
            assert getattr(x.state, name) == getattr(y.state, name)
        for name in ("ecology_runtime", "politics_runtime"):
            l, r = getattr(x.state, name), getattr(y.state, name)
            assert (l is None) == (r is None)
            if l is not None:
                assert bytes(l.checkpoint_state()) == bytes(r.checkpoint_state())
        assert x.state.agent_bridge is y.state.agent_bridge is None
        assert "practice_observer" not in vars(y.state) and "practice_observer" not in y.state.run_config
        assert not any("observer" in key for key in vars(y.state.world))
    # Successful checkpoint writing/loading also proves the unpickleable handle was not retained.
    assert observer.read_latest(expected_source_turn=13).status == "captured"
    observer.close()
