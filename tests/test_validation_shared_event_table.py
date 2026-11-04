"""Exact event/death views with one seed-local IPC read and no cache."""
import json
from pathlib import Path

import pytest

from chronicler import validation_io as V


def _seed(tmp_path, seed=42):
    seed_dir = tmp_path / f"seed_{seed}"
    seed_dir.mkdir()
    (seed_dir / "chronicle_bundle.json").write_text(json.dumps({
        "metadata": {"seed": seed, "total_turns": 20},
        "world_state": {"turn": 20, "agent_mode": "off", "regions": []},
        "history": [],
    }), encoding="utf-8")
    return seed_dir


def _write_rows(seed_dir, rows):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.ipc as ipc

    table = pa.table({
        "turn": pa.array([r[0] for r in rows], type=pa.uint64()),
        "agent_id": pa.array([r[1] for r in rows], type=pa.uint64()),
        "event_type": pa.array([r[2] for r in rows], type=pa.string()),
    })
    _write_table(seed_dir, table, ipc)


def _write_table(seed_dir, table, ipc):
    with ipc.new_file(seed_dir / "agent_events.arrow", table.schema) as writer:
        # Separate batches exercise chunked columns without changing row order.
        if table.num_rows:
            writer.write_table(table.slice(0, 1))
            writer.write_table(table.slice(1))
        else:
            writer.write_table(table)


def _read_spy(monkeypatch):
    import pyarrow.ipc as ipc

    original = ipc.open_file
    calls = {"open": 0, "read_all": 0}

    class Reader:
        def __init__(self, actual):
            self.actual = actual

        def read_all(self):
            calls["read_all"] += 1
            return self.actual.read_all()

    def open_file(path, *args, **kwargs):
        assert Path(path).name == "agent_events.arrow"
        calls["open"] += 1
        return Reader(original(path, *args, **kwargs))

    monkeypatch.setattr(ipc, "open_file", open_file)
    return calls


@pytest.mark.parametrize(("rows", "events", "deaths"), [
    ([], [], {}),
    ([(8, 3, "unknown"), (4, 7, None)], [], {}),
    ([(3, 8, "birth"), (4, 8, "death"), (5, 9, "dissolution")],
     [{"turn": 3, "agent_id": 8, "event_type": 5}], {8: 4}),
    ([(4, 7, "death"), (9, 8, "migration"), (1, 7, "death"),
      (8, 8, "rebellion"), (7, 9, "occupation_switch"), (1, 7, "death")],
     [{"turn": 9, "agent_id": 8, "event_type": 1},
      {"turn": 8, "agent_id": 8, "event_type": 2},
      {"turn": 7, "agent_id": 9, "event_type": 3}], {7: 1}),
    ([(None, None, "migration"), (8, 6, "loyalty_flip")],
     [{"turn": None, "agent_id": None, "event_type": 1}], {}),
    ([(2**64 - 1, 2**64 - 1, "death"), (0, 2**64 - 1, "death")],
     [{"turn": 2**64 - 1, "agent_id": 2**64 - 1, "event_type": 0}],
     {2**64 - 1: 0}),
])
def test_seed_event_views_match_standalone_values_with_one_read(
    tmp_path, monkeypatch, rows, events, deaths,
):
    seed_dir = _seed(tmp_path)
    _write_rows(seed_dir, rows)
    calls = _read_spy(monkeypatch)

    assert V._load_agent_events(seed_dir) == events
    assert V._load_agent_deaths(seed_dir) == deaths
    assert calls == {"open": 2, "read_all": 2}
    calls.update(open=0, read_all=0)

    (run,) = V.load_seed_runs(tmp_path)
    assert run["events"] == events
    assert run["deaths"] == deaths
    assert calls == {"open": 1, "read_all": 1}
    assert list(run) == [
        "bundle_path", "seed_dir", "seed", "world", "bundle", "events",
        "deaths", "relationship_columns", "memory_columns", "needs_columns",
        "graph_snapshot", "needs_snapshot", "validation_summary",
        "validation_community_summary", "world_population", "civ_trajectories",
        "civ_crisis_event_turns",
    ]


def test_missing_event_type_stays_empty(tmp_path, monkeypatch):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.ipc as ipc

    seed_dir = _seed(tmp_path)
    _write_table(seed_dir, pa.table({"other": [1, 2]}), ipc)
    calls = _read_spy(monkeypatch)
    assert V._load_agent_events(seed_dir) == []
    assert V._load_agent_deaths(seed_dir) == {}
    calls.update(open=0, read_all=0)
    (run,) = V.load_seed_runs(tmp_path)
    assert (run["events"], run["deaths"]) == ([], {})
    assert calls == {"open": 1, "read_all": 1}


@pytest.mark.parametrize("missing_pyarrow", [False, True])
def test_unavailable_event_input_never_opens_ipc(tmp_path, monkeypatch, missing_pyarrow):
    seed_dir = _seed(tmp_path)
    if missing_pyarrow:
        (seed_dir / "agent_events.arrow").write_bytes(b"not IPC")
        monkeypatch.setattr(V, "_has_pyarrow", lambda: False)

    assert V._load_agent_events(seed_dir) == []
    assert V._load_agent_deaths(seed_dir) == {}
    # No required event-consuming oracle: retain the existing no-data result.
    (run,) = V.load_seed_runs(tmp_path, selected_oracles=set())
    assert (run["events"], run["deaths"]) == ([], {})


@pytest.mark.parametrize("bad_input", ["corrupt", "missing_turn", "missing_id", "null_death_turn", "null_death_id"])
def test_rejected_input_keeps_standalone_exception(tmp_path, bad_input):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.ipc as ipc

    seed_dir = _seed(tmp_path)
    if bad_input == "corrupt":
        (seed_dir / "agent_events.arrow").write_bytes(b"invalid IPC")
    elif bad_input.startswith("missing_"):
        columns = {"event_type": ["death"], "turn": [1], "agent_id": [2]}
        del columns[{"missing_turn": "turn", "missing_id": "agent_id"}[bad_input]]
        _write_table(seed_dir, pa.table(columns), ipc)
    else:
        _write_rows(seed_dir, [(None if bad_input == "null_death_turn" else 1,
                               None if bad_input == "null_death_id" else 2, "death")])

    # The original load_seed_runs evaluates these independent APIs in this order.
    with pytest.raises(Exception) as standalone:
        V._load_agent_events(seed_dir)
        V._load_agent_deaths(seed_dir)
    assert type(standalone.value).__name__ == {
        "corrupt": "ArrowInvalid", "missing_turn": "KeyError",
        "missing_id": "KeyError", "null_death_turn": "TypeError",
        "null_death_id": "TypeError",
    }[bad_input]
    with pytest.raises(type(standalone.value)) as combined:
        V.load_seed_runs(tmp_path)
    assert str(combined.value) == str(standalone.value)


def test_event_table_is_fresh_for_each_seed_load_and_standalone_call(tmp_path, monkeypatch):
    seed_dir = _seed(tmp_path)
    _write_rows(seed_dir, [(2, 7, "birth")])
    calls = _read_spy(monkeypatch)
    (first,) = V.load_seed_runs(tmp_path)
    _write_rows(seed_dir, [(4, 8, "death")])
    (second,) = V.load_seed_runs(tmp_path)
    assert first["deaths"] == {}
    assert first["events"] == [{"turn": 2, "agent_id": 7, "event_type": 5}]
    assert second["deaths"] == {8: 4}
    assert second["events"] == [{"turn": 4, "agent_id": 8, "event_type": 0}]
    assert V._load_agent_events(seed_dir) == second["events"]
    assert V._load_agent_deaths(seed_dir) == second["deaths"]
    assert calls == {"open": 4, "read_all": 4}


def test_distinct_seeds_use_their_own_table(tmp_path, monkeypatch):
    _write_rows(_seed(tmp_path, 42), [(3, 8, "death")])
    _write_rows(_seed(tmp_path, 43), [(9, 8, "migration")])
    calls = _read_spy(monkeypatch)
    first, second = V.load_seed_runs(tmp_path)
    assert (first["seed"], first["deaths"]) == (42, {8: 3})
    assert (second["seed"], second["deaths"]) == (43, {})
    assert second["events"] == [{"turn": 9, "agent_id": 8, "event_type": 1}]
    assert calls == {"open": 2, "read_all": 2}


def test_bundle_shape_error_precedes_event_read(tmp_path, monkeypatch):
    seed_dir = _seed(tmp_path)
    _write_rows(seed_dir, [(1, 7, "migration")])
    calls = _read_spy(monkeypatch)

    def fail_shape(_bundle):
        raise ValueError("shape first")

    monkeypatch.setattr(V, "_world_shape", fail_shape)
    with pytest.raises(ValueError, match="shape first"):
        V.load_seed_runs(tmp_path)
    assert calls == {"open": 0, "read_all": 0}
