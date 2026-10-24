"""Columnar snapshot paths equal the row-by-row paths they shortcut.

Every columnar consumer keeps its row loop for batches with null cells. The
whole-run checks force those row loops (and a fresh Phase 10 snapshot export)
and require byte-identical artifacts; the unit checks pin each helper against
the loop it replaces.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import random

import numpy as np
import pyarrow as pa
import pytest

from chronicler import agent_bridge, columnar, great_persons, turn_artifacts

try:
    from chronicler_agents import AgentSimulator as _AgentSimulator
    _AGENTS_AVAILABLE = isinstance(_AgentSimulator, type)
except Exception:  # pragma: no cover - depends on the optional extension
    _AGENTS_AVAILABLE = False

arro3 = pytest.importorskip("arro3.core")


# --- helpers ------------------------------------------------------------------

def _loop_counts(keys, values):
    counts: dict = {}
    for k, v in zip(keys, values):
        if k not in counts:
            counts[k] = Counter()
        counts[k][v] += 1
    return counts


def _ordered(d):
    return [(k, list(c.items())) for k, c in d.items()]


@pytest.mark.parametrize("seed", range(20))
def test_ordered_counts_match_the_row_loop_including_order(seed):
    rng = random.Random(seed)
    n = rng.choice([0, 1, 2, 50, 3000])
    keys = [rng.choice([0, 1, 7, 300, 65535]) for _ in range(n)]
    values = [rng.choice([0, 3, 5, 255]) for _ in range(n)]
    got = columnar.ordered_counts(np.array(keys, dtype=np.uint16), np.array(values, dtype=np.uint8))
    assert _ordered(got) == _ordered(_loop_counts(keys, values))
    assert all(type(k) is int for k in got) and all(type(v) is int for c in got.values() for v in c)


def test_first_appearance_and_last_row_of_match_python():
    rng = random.Random(3)
    ids = [rng.randrange(40) for _ in range(500)]
    assert columnar.first_appearance(np.array(ids)) == list(dict.fromkeys(ids))
    full = {aid: i for i, aid in enumerate(ids)}
    wanted = [5, 17, 999, None, 0, 17]
    assert columnar.last_row_of(np.array(ids, dtype=np.uint32), wanted) == {
        w: full[w] for w in wanted if w is not None and w in full}


@pytest.mark.parametrize("array", [
    pa.array([True, False]), pa.array([1.5, -0.0, float("nan")], type=pa.float32()),
    pa.array([2 ** 63 + 1], type=pa.uint64()), pa.array([-3, 4], type=pa.int8()),
    pa.array(["a"]), pa.array([1, None], type=pa.int32()), pa.array([], type=pa.uint16()),
])
@pytest.mark.parametrize("flavor", ["pyarrow", "arro3"])
def test_pylist_equals_to_pylist(array, flavor):
    column = array if flavor == "pyarrow" else arro3.Array.from_arrow(array)
    expected, got = column.to_pylist(), columnar.pylist(column)
    assert [type(v) for v in got] == [type(v) for v in expected]
    assert repr(got) == repr(expected)


def test_agent_rows_arrays_are_read_only_and_none_with_nulls():
    batch = pa.record_batch({"a": pa.array([1, 2], type=pa.uint8()),
                             "b": pa.array([1, None], type=pa.uint8())})
    rows = turn_artifacts.AgentRows(turn_artifacts.Stamp(0, "phase10_entry"), batch)
    a = rows.array("a")
    assert a.tolist() == [1, 2] and not a.flags.writeable
    assert rows.array("b") is None
    assert rows.arrays("a", "b") is None and rows.arrays("a", "missing") is None
    assert rows.ints("b") == (1, None)


def test_named_actor_memo_matches_the_scan():
    from types import SimpleNamespace as E

    rng = random.Random(9)
    events = [E(region=rng.randrange(4), agent_id=rng.randrange(30)) for _ in range(400)]
    named = {i: f"n{i % 7}" for i in range(0, 30, 3)}
    bridge = agent_bridge.AgentBridge.__new__(agent_bridge.AgentBridge)
    plain = [bridge._named_actors_in_region(r, named, events) for r in range(5)]
    bridge._named_actor_memo = {}
    memo = [bridge._named_actors_in_region(r, named, events) for r in range(5)]
    assert memo == plain and any(plain)


@pytest.mark.parametrize("seed", range(6))
def test_windowed_event_summaries_match_the_window_scans(seed, sample_world):
    """Cached per-turn tallies and indexed named actors equal the old scans."""
    from collections import deque

    from legacy_aggregate_events import legacy_aggregate_events
    from chronicler.models import AgentEventRecord

    rng = random.Random(seed)
    bridge = agent_bridge.AgentBridge.__new__(agent_bridge.AgentBridge)
    bridge._sim = None  # region populations fall back to world values
    bridge._event_window = deque(maxlen=20)
    named = {}
    n_regions = len(sample_world.regions)
    types = ["migration", "rebellion", "occupation_switch", "loyalty_flip", "death", "birth"]
    for turn in range(30):
        events = [
            AgentEventRecord(turn, rng.randrange(400), rng.choice(types), rng.randrange(n_regions + 1),
                             rng.randrange(n_regions), rng.randrange(len(sample_world.civilizations) + 1),
                             rng.randrange(5))
            for _ in range(rng.choice([0, 40, 400]))
        ]
        bridge._event_window.append(events)
        if rng.random() < 0.5:
            named[rng.randrange(400)] = f"Named {rng.randrange(6)}"
        sample_world.turn = turn
        got = bridge._aggregate_events(sample_world, named)
        expected = legacy_aggregate_events(bridge, sample_world, named)
        # The legacy scans predate causal provenance: compare without the
        # region/civs stamps (asserted separately below).
        assert [e.model_dump(exclude={"region", "civs"}) for e in got] == [
            e.model_dump() for e in expected]
        for e in got:
            assert e.region is None or e.region in {r.name for r in sample_world.regions}
    assert len(bridge._window_stats_cache) <= 20


# --- whole runs: columnar paths forced off --------------------------------------

def _force_row_paths(monkeypatch):
    monkeypatch.setattr(columnar, "numeric_array", lambda column: None)
    monkeypatch.setattr(turn_artifacts, "numeric_array", lambda column: None)
    monkeypatch.setattr(great_persons, "numeric_array", lambda column: None)
    monkeypatch.setattr(agent_bridge, "_null_free", lambda snapshot, names: False)
    monkeypatch.setattr(agent_bridge.AgentBridge, "take_post_tick_snapshot", lambda self, turn: None)


def _hashes(root: Path) -> dict:
    out = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "chronicle_bundle.json":
            data = json.loads(path.read_text())
            data.get("metadata", {}).pop("generated_at", None)
            blob = json.dumps(data, sort_keys=True).encode()
        else:
            blob = path.read_bytes()
        out[path.name] = hashlib.sha256(blob).hexdigest()
    return out


def _run(tmp: Path, argv: list[str], scale: float = 1.0, *, probe=None):
    import chronicler.main as cm
    from chronicler.utils import sync_civ_population

    original = cm.generate_world

    def scaled(*args, **kwargs):
        world = original(*args, **kwargs)
        for region in world.regions:
            region.carrying_capacity = max(1, round(region.carrying_capacity * scale))
            region.population = round(region.population * scale)
        for civ in world.civilizations:
            sync_civ_population(civ, world)
        return world

    tmp.mkdir(parents=True, exist_ok=True)
    defaults = [] if "--regions" in argv else ["--regions", "8", "--civs", "4"]  # main()'s defaults
    args = cm._build_parser().parse_args(argv + defaults + [
        "--simulate-only", "--output", str(tmp / "chronicle.md"), "--state", str(tmp / "state.json")])
    args.reflection_interval = args.reflection_interval or 10
    cm.generate_world = scaled
    try:
        cm.execute_run(args, on_turn=probe)
    finally:
        cm.generate_world = original
    return _hashes(tmp)


@pytest.mark.native
@pytest.mark.skipif(not _AGENTS_AVAILABLE, reason="Rust agent extension not available")
@pytest.mark.parametrize("argv,scale", [
    (["--seed", "42", "--turns", "40", "--agents", "hybrid"], 1.0),
    (["--seed", "7", "--turns", "25", "--agents", "hybrid", "--regions", "24", "--civs", "8"], 1.0),
    (["--seed", "11", "--turns", "12", "--agents", "hybrid", "--regions", "12", "--civs", "4"], 25.0),
    (["--seed", "5", "--turns", "20", "--agents", "demographics-only"], 1.0),
    (["--seed", "5", "--turns", "20", "--agents", "shadow"], 1.0),
])
def test_runs_are_identical_with_row_paths_forced(argv, scale, tmp_path, monkeypatch):
    decoded = []
    real = turn_artifacts.numeric_array
    with monkeypatch.context() as patch:
        patch.setattr(turn_artifacts, "numeric_array",
                      lambda column: decoded.append(1) or real(column))
        columnar_run = _run(tmp_path / "columnar", argv, scale)
    assert decoded  # the shared view served NumPy columns
    with monkeypatch.context() as patch:
        _force_row_paths(patch)
        row_run = _run(tmp_path / "rows", argv, scale)
    assert columnar_run == row_run
    assert len(columnar_run) >= 5


@pytest.mark.native
@pytest.mark.skipif(not _AGENTS_AVAILABLE, reason="Rust agent extension not available")
def test_native_snapshot_cache_is_dropped_by_pool_changes():
    from chronicler.agent_bridge import AgentBridge
    from chronicler.world_gen import generate_world

    world = generate_world(seed=4, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    sim = AgentBridge(world, mode="hybrid")._sim
    if not hasattr(sim, "snapshot_is_cached"):
        pytest.skip("extension predates the snapshot cache")

    def table(batch):
        return pa.record_batch(batch)

    first = sim.get_snapshot()
    assert sim.snapshot_is_cached()
    assert table(sim.get_snapshot()).equals(table(first))
    # Read-only calls keep the batch.
    sim.get_promotions()
    sim.queue_targeted_deaths([])
    assert sim.snapshot_is_cached()
    # A pool-changing call drops it; the next export shows the change.
    agent_id = table(first).column("id")[0].as_py()
    old_civ = table(first).column("civ_affinity")[0].as_py()
    sim.set_agent_civ(agent_id, (old_civ + 1) % 4)
    assert not sim.snapshot_is_cached()
    changed = table(sim.get_snapshot())
    assert changed.column("civ_affinity")[0].as_py() == (old_civ + 1) % 4
    # Any other mutating call (even a no-op) also drops it; re-export equals the cache.
    sim.set_hybrid_economy_mode(True)
    assert not sim.snapshot_is_cached()
    assert table(sim.get_snapshot()).equals(changed)


@pytest.mark.native
@pytest.mark.skipif(not _AGENTS_AVAILABLE, reason="Rust agent extension not available")
def test_shared_phase10_snapshot_equals_a_fresh_export(tmp_path, monkeypatch):
    """The batch handed over after the tick equals exporting the pool again."""
    from chronicler import simulation

    original = simulation._capture_agent_snapshot
    compared = []

    def checked(world, bridge):
        held = bridge._post_tick_snapshot
        assert held is not None and held[0] == world.turn
        shared = original(world, bridge)
        assert shared is held[1] and bridge._post_tick_snapshot is None
        if hasattr(bridge._sim, "snapshot_is_cached"):
            # Drop the native cache with a call that changes nothing, so the
            # comparison is against a real export.
            bridge._sim.set_hybrid_economy_mode(bridge._mode == "hybrid")
        fresh = bridge._sim.get_snapshot()
        assert shared is not None
        assert pa.record_batch(shared).equals(pa.record_batch(fresh))
        compared.append(world.turn)
        return shared

    monkeypatch.setattr(simulation, "_capture_agent_snapshot", checked)
    _run(tmp_path / "run", ["--seed", "3", "--turns", "15", "--agents", "hybrid"], 4.0)
    assert len(compared) == 15
