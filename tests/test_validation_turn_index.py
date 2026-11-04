"""Exact turn selection without repeated scans or schema/cache pollution."""
from __future__ import annotations

import copy
import json
import pickle
import struct
from array import array

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from chronicler import validation_io as V
from chronicler.artifact_io import strict_json_dumps


def _write(path, columns):
    table = pa.table(columns)
    with ipc.new_file(path, table.schema) as writer:
        writer.write_table(table)


def _reference(columns, turn):
    if not columns or not columns.get("turn"):
        return None
    rows = [i for i, value in enumerate(columns["turn"]) if int(value) == turn]
    if not rows:
        return None
    return {name: [column[i] for i in rows] for name, column in columns.items() if name != "turn"}


@pytest.mark.parametrize("turns", [
    [], [10], [10, 10, 20, 20, 30], [30, 10, 20, 10, 30], [20, 10, 0],
    [-1, -1, 0, 2], ["01", "1", "2", "10"], ["2", "01", "2", "1"],
])
def test_rows_and_duplicates_keep_the_original_order_for_sorted_and_legacy_tables(turns):
    source = {"turn": turns, "agent_id": [7] * len(turns), "row": list(range(len(turns)))}
    before = copy.deepcopy(source)
    indexed = V._IndexedColumns(source)
    for turn in (-1, 0, 1, 2, 10, 20, 30, 999):
        assert V._columns_for_turn(indexed, turn) == _reference(source, turn)
        assert V._columns_for_turn(source, turn) == _reference(source, turn)
    assert V._available_turns_from_columns(indexed) == sorted({int(turn) for turn in turns})
    assert source == before and list(indexed) == list(source)


def test_contiguous_turns_use_ranges_and_shuffled_turns_use_readonly_ordered_indices():
    ordered = V._IndexedColumns({"turn": array("q", [2, 2, 5, 5])})
    assert ordered._turn_rows.rows[2] == range(0, 2)
    assert ordered._turn_rows.rows[5] == range(2, 4)
    shuffled = V._IndexedColumns({"turn": [5, 2, 5, 2]})
    assert list(shuffled._turn_rows.rows[5]) == [0, 2]
    assert list(shuffled._turn_rows.rows[2]) == [1, 3]
    with pytest.raises(TypeError):
        shuffled._turn_rows.rows[5][0] = 1
    with pytest.raises(TypeError):
        ordered._turn_rows.rows[7] = range(0)


def test_loaded_values_keep_packed_types_nulls_booleans_and_signed_zero(tmp_path):
    path = tmp_path / "values.arrow"
    _write(path, {"turn": pa.array([10, 20, 10], type=pa.int16()),
                  "agent_id": pa.array([1, 2, 1], type=pa.uint32()),
                  "value": pa.array([-0.0, 1.25, 0.0], type=pa.float32()),
                  "nullable": [None, "middle", "last"], "flag": [True, False, True]})
    columns = V._read_arrow_columns(path)
    assert isinstance(columns["turn"], array) and columns["turn"].typecode == "q"
    assert isinstance(columns["value"], array) and columns["value"].typecode == "d"
    assert isinstance(columns["nullable"], list) and isinstance(columns["flag"], list)
    selected = V._columns_for_turn(columns, 10)
    assert selected == {"agent_id": [1, 1], "value": [-0.0, 0.0],
                        "nullable": [None, "last"], "flag": [True, True]}
    assert struct.pack("!d", selected["value"][0]) == struct.pack("!d", -0.0)
    assert list(columns) == ["turn", "agent_id", "value", "nullable", "flag"]


def test_reload_of_a_replaced_file_gets_a_new_index_even_at_the_same_path(tmp_path):
    path = tmp_path / "changed.arrow"
    _write(path, {"turn": [10, 10, 20], "row": [0, 1, 2]})
    original = V._read_arrow_columns(path)
    _write(path, {"turn": [20, 20, 10], "row": [3, 4, 5]})
    replaced = V._read_arrow_columns(path)
    assert original._turn_rows is not replaced._turn_rows
    assert V._columns_for_turn(original, 10) == {"row": [0, 1]}
    assert V._columns_for_turn(replaced, 10) == {"row": [5]}
    assert V._columns_for_turn(replaced, 20) == {"row": [3, 4]}


def test_plain_caller_dictionary_edits_are_observed_without_cache_keys():
    columns = {"turn": [10, 20, 10], "row": [0, 1, 2]}
    assert V._columns_for_turn(columns, 10) == {"row": [0, 2]}
    columns["turn"][0] = 20
    assert V._columns_for_turn(columns, 10) == {"row": [2]}
    columns["turn"].append(10)
    columns["row"].append(3)
    assert V._columns_for_turn(columns, 10) == {"row": [2, 3]}
    assert list(columns) == ["turn", "row"]


class _CountedTurns(list):
    visits = 0

    def __iter__(self):
        for value in super().__iter__():
            self.visits += 1
            yield value


def test_loaded_index_scans_turns_once_and_reuses_rows_without_extra_turn_visits():
    turns = _CountedTurns([turn for turn in range(100) for _ in range(20)])
    columns = V._IndexedColumns({"turn": turns, "row": list(range(len(turns)))})
    assert turns.visits == len(turns)
    for _ in range(3):
        assert V._available_turns_from_columns(columns) == list(range(100))
        for turn in range(100):
            selected = V._columns_for_turn(columns, turn)
            assert selected["row"] == list(range(turn * 20, (turn + 1) * 20))
    assert turns.visits == len(turns)


def test_graph_edge_and_memory_order_including_duplicate_ids_is_exact():
    relationships = {"turn": [20, 10, 20, 10], "agent_id": [9, 2, 1, 2],
                     "target_id": [1, 3, 9, 3], "bond_type": [2] * 4, "sentiment": [5, -1, 7, 8]}
    memories = {"turn": [10, 20, 10, 20], "agent_id": [2, 9, 2, 9],
                "event_type": [4, 3, 2, 1], "memory_turn": [9, 18, 8, 19], "valence_sign": [-1, 1, 1, -1]}
    snapshot = V._graph_snapshot_from_columns(V._IndexedColumns(relationships), V._IndexedColumns(memories), 10)
    assert snapshot == {"turn": 10, "edges": [(2, 3, 2, -1), (2, 3, 2, 8)],
                        "memory_signatures": {2: [(4, 9, -1), (2, 8, 1)]}}
    assert V._graph_snapshot_from_columns(V._IndexedColumns(relationships), None, 999) is None


@pytest.mark.parametrize("columns", [None, {}, {"turn": []}, {"other": [1, 2]}])
def test_missing_turn_inputs_keep_no_data_behavior(columns):
    assert V._columns_for_turn(columns, 10) is None
    assert V._available_turns_from_columns(columns) == []
    assert V._graph_snapshot_from_columns(columns, None, 10) is None
    assert V._needs_snapshot_from_columns(columns, 10) is None


def _run(indexed=False):
    turns = [10, 100, 110]
    count = 6
    needs = {"turn": [turn for turn in turns for _ in range(count)],
             "agent_id": list(range(count)) * len(turns), "region": [0] * (count * len(turns)),
             "civ_affinity": [0] * (count * len(turns)), "occupation": [0] * (count * len(turns))}
    for name in ("satisfaction", "safety", "autonomy", "social", "spiritual", "material", "purpose",
                 "boldness", "ambition", "loyalty_trait"):
        needs[name] = [0.2, 0.8] * (count * len(turns) // 2)
    rel = {"turn": [], "agent_id": [], "target_id": [], "bond_type": [], "sentiment": []}
    mem = {"turn": [], "agent_id": [], "event_type": [], "memory_turn": [], "valence_sign": []}
    for turn in turns:
        for a in range(count):
            for b in range(a + 1, count):
                for name, value in zip(rel, (turn, a, b, 2, 50)):
                    rel[name].append(value)
            for name, value in zip(mem, (turn, a, 0, 5, 1)):
                mem[name].append(value)
    columns = {"relationship_columns": rel, "memory_columns": mem, "needs_columns": needs}
    if indexed:
        columns = {key: V._IndexedColumns(value) for key, value in columns.items()}
    return {"seed": 42, "bundle": {"metadata": {"total_turns": 150}},
            "events": [{"turn": 105, "agent_id": 0, "event_type": 1}], "deaths": {}, **columns}


def test_cross_oracle_reuse_keeps_every_method_result_and_schema_identical(monkeypatch):
    plain = _run()
    indexed = _run(indexed=True)
    before = {key: dict(indexed[key]) for key in ("relationship_columns", "memory_columns", "needs_columns")}
    def forbidden(columns):
        raise AssertionError("a loaded table's turn index was rebuilt")
    functions = [(V.run_community_oracle, method) for method in (1, 2)]
    functions += [(V.run_needs_oracle, method) for method in V.NEEDS_METHOD_VERSIONS]
    functions += [(V.run_cohort_oracle, method) for method in V.COHORT_METHOD_VERSIONS]
    for function, method in functions:
        expected = function([copy.deepcopy(plain)], method_version=method)
        with monkeypatch.context() as guard:
            guard.setattr(V, "_build_turn_rows", forbidden)
            actual = function([indexed], method_version=method)
        assert strict_json_dumps(actual) == strict_json_dumps(expected)
    assert {key: dict(indexed[key]) for key in before} == before
    assert all(list(indexed[key]) == list(before[key]) for key in before)


def test_unaligned_tables_and_single_snapshot_fallback_keep_sample_domains():
    run = _run(indexed=True)
    run["needs_columns"] = V._IndexedColumns({"turn": [20, 100], "agent_id": [0, 1]})
    assert V._iter_joint_sample_turns(run, min_turn=0) == [100]
    assert V._iter_joint_sample_turns(run, min_turn=105) == []
    fallback = {"graph_snapshot": {"turn": 10, "edges": [], "memory_signatures": {}},
                "needs_snapshot": {"turn": 10, "columns": {"agent_id": [1]}}}
    assert V._iter_joint_sample_turns(fallback, min_turn=100) == [10]


def test_copy_and_pickle_rebuild_an_independent_index_with_identical_data():
    original = V._IndexedColumns({"turn": array("q", [20, 10, 20]), "row": [0, 1, 2]})
    for copied in (copy.deepcopy(original), pickle.loads(pickle.dumps(original))):
        assert copied == original and copied is not original
        assert copied._turn_rows is not original._turn_rows
        assert V._columns_for_turn(copied, 20) == {"row": [0, 2]}


def test_load_seed_runs_and_canonical_readers_share_the_exact_snapshot_values(tmp_path):
    bundle = {"metadata": {"seed": 42, "total_turns": 200}, "world_state": {}, "history": []}
    (tmp_path / "chronicle_bundle.json").write_text(json.dumps(bundle))
    source = _run()
    for key, filename in (("needs_columns", "validation_needs.arrow"),
                          ("relationship_columns", "validation_relationships.arrow"),
                          ("memory_columns", "validation_memory_signatures.arrow")):
        _write(tmp_path / filename, source[key])
    run = V.load_seed_runs(tmp_path)[0]
    assert V._load_canonical_needs_snapshot(tmp_path, 100) == V._needs_snapshot_from_columns(run["needs_columns"], 100)
    assert V._load_canonical_graph_snapshot(tmp_path, 100) == V._graph_snapshot_from_columns(
        run["relationship_columns"], run["memory_columns"], 100)
    assert all(isinstance(run[key], V._IndexedColumns) for key in
               ("needs_columns", "relationship_columns", "memory_columns"))
