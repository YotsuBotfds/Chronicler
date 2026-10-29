"""Pure Arrow/fake-bridge contracts; no native runtime or world construction."""
from collections import deque
import builtins
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler.agent_bridge import AgentBridge
from chronicler import decision_delivery as delivery


def batch(fields, rows):
    schema = pa.schema([pa.field(name, pa.bool_() if kind == "bool" else getattr(pa, kind)(), nullable)
                        for name, kind, nullable in fields])
    defaults = {name: None if nullable else False if kind == "bool" else 0 for name, kind, nullable in fields}
    return pa.RecordBatch.from_pylist([dict(defaults, **row) for row in rows], schema=schema)


def event_batch(turn=11):
    columns = {
        "agent_id": pa.array([99, 7], type=pa.uint32()),
        "event_type": pa.array([0, 2], type=pa.uint8()),
        "region": pa.array([0, 0], type=pa.uint16()),
        "target_region": pa.array([0, 1], type=pa.uint16()),
        "turn": pa.array([turn, turn], type=pa.uint32()),
        "migration_driver": pa.array([0, 3], type=pa.uint8()),
    }
    schema = pa.schema([pa.field(name, value.type, nullable=False) for name, value in columns.items()])
    return pa.record_batch(list(columns.values()), schema=schema)


class FakeSim:
    def __init__(self):
        self.trace, self.config_calls, self.ticks = [], [], 0
        self.enabled, self.turn, self.selected = False, None, None
        self.limits = (4096, 16384, 16384)
        self.decision_overrides, self.move_overrides = {}, {}
        self.first_transform = self.second_transform = None
        self.fail_tick = self.fail_getter = self.fail_disable = False
        self.events = event_batch()

    def configure_decision_delivery(self, enabled, agents=4096, candidates=16384, selected=None, *, max_move_rows=16384):
        if not enabled and self.fail_disable:
            raise RuntimeError("private disable error")
        self.config_calls.append((enabled, agents, candidates, selected, max_move_rows))
        self.enabled, self.limits, self.selected = enabled, (agents, candidates, max_move_rows), selected

    def set_merchant_route_graph(self, value):
        self.trace.append("route")

    def tick(self, turn, signals):
        if self.fail_tick:
            raise TypeError("rejected before native entry; prior frame deliberately remains")
        self.trace.append("native")
        self.turn = turn
        self.ticks += 1
        self.events = event_batch(turn)
        return self.events

    def _headers(self):
        selected = self.selected is None or 7 in self.selected
        common = dict(enabled=self.enabled, source_turn=self.turn, active_ablation=0,
                      selection_is_explicit=self.selected is not None, selected_ids_requested=len(self.selected or ()))
        a = dict(common, schema_version=1, agent_limit=self.limits[0], candidate_limit=self.limits[1],
                 decision_capture_complete=True, selected_alive_seen=int(selected), alive_seen_all=1,
                 evaluated_all=1, admissible_candidates_all=1)
        b = dict(common, schema_version=2, move_limit=self.limits[2], capture_finished=True,
                 native_event_ordinals_are_zero_based=True, operations_seen_all=2,
                 operations_selected=2 if selected else 0, own_proposals_all=1, applied_all=1,
                 applied_selected=int(selected), dropped_move_rows=max(0, 2-self.limits[2]) if selected else 0,
                 applied_move_provenance_complete=not selected or self.limits[2] >= 2)
        a.update(self.decision_overrides); b.update(self.move_overrides)
        return a, b, selected

    def get_decision_delivery_frame(self):
        self.trace.append("decision-read")
        if self.fail_getter:
            raise RuntimeError("private getter error must never enter a readout")
        a, _, selected = self._headers()
        result = (batch(delivery._DECISION_HEADER, [a]),
                  batch(delivery._DECISIONS, [dict(agent_id=7, region=0, status=2, utility_migrate_bits=0x7f800000)] if selected else []),
                  batch(delivery._CANDIDATES, [dict(agent_id=7, region=0, target=1, roots_bits=0x80000000)] if selected else []))
        return self.first_transform(result) if self.first_transform else result

    def get_decision_delivery_move_frame(self):
        self.trace.append("move-read")
        _, b, selected = self._headers()
        rows = [dict(operation_ordinal=0, operation=1, agent_id=7, from_region=0, to_region=1, origin_valid=True),
                dict(operation_ordinal=1, operation=7, applied=True, agent_id=7, from_region=0, to_region=1,
                     origin_valid=True, origin_operation_ordinal=0, native_event_ordinal=1, migration_driver=3)]
        result = (batch(delivery._MOVE_HEADER, [b]), batch(delivery._MOVES, rows[:self.limits[2]] if selected else []))
        return self.second_transform(result) if self.second_transform else result

    def __getstate__(self):
        # Native persistence already excludes its observer; this fake permits
        # an independent test of the Python bridge's attachment exclusion.
        return {"ticks": self.ticks}

    def __setstate__(self, state):
        self.__init__()
        self.ticks = state["ticks"]


@pytest.fixture
def bridge(monkeypatch):
    import chronicler.agent_bridge as module
    import chronicler.economy as economy
    import chronicler.transaction_receipts as receipts

    result = AgentBridge.__new__(AgentBridge)
    result._sim, result._mode = FakeSim(), "hybrid"
    result._gini_by_civ, result._economy_result = {}, None
    result.sync_regions = lambda world: result._sim.trace.append("sync")
    def normal(events, world, **kwargs):
        result._sim.trace.extend(("writeback", "promotions", "deaths", "summaries", "normal-complete"))
        world.written = True
        return ["normal-result"]
    result._process_tick_results = normal
    monkeypatch.setattr(economy, "build_merchant_route_graph", lambda world: object())
    monkeypatch.setattr(module, "_city_route_graph", lambda world, graph: graph)
    monkeypatch.setattr(module, "build_signals", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "_send_movement_table", lambda *args: None)
    monkeypatch.setattr(receipts, "prepare_transaction_receipts", lambda *args: None)
    monkeypatch.setattr(receipts, "capture_transaction_receipts", lambda *args: None)
    return result


def run(bridge, method="tick", turn=11):
    world = SimpleNamespace(turn=turn)
    assert getattr(bridge, method)(world) == ["normal-result"]
    assert world.written
    return world


@pytest.mark.parametrize("method", ["tick", "tick_agents"])
@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_capture_runs_after_entire_normal_processor_for_both_entrypoints_and_modes(bridge, method, mode):
    bridge._mode = mode
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge, method)
    record = observer.read_latest(expected_source_turn=11)
    assert record.status == "captured" and record.bridge_mode == mode
    assert record.native_event_count == 2 and record.applied_event_links_checked == 1
    assert bridge._sim.trace[-3:] == ["normal-complete", "decision-read", "move-read"]
    assert record.moves.column("native_event_ordinal")[1].as_py() == 1
    assert record.decisions.column("utility_migrate_bits")[0].as_py() == 0x7f800000
    assert record.candidates.column("roots_bits")[0].as_py() == 0x80000000
    trace = list(bridge._sim.trace)
    assert observer.read_latest(expected_source_turn=11) is record
    assert bridge._sim.trace == trace


@pytest.mark.parametrize("method", ["tick", "tick_agents"])
def test_default_path_never_configures_or_reads_and_adds_no_attachment(bridge, method, monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail("disabled delivery API called")
    for name in ("configure_decision_delivery", "get_decision_delivery_frame", "get_decision_delivery_move_frame"):
        monkeypatch.setattr(bridge._sim, name, forbidden)
    original_import = builtins.__import__
    def no_optional_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "chronicler.decision_delivery" or (name == "chronicler" and "decision_delivery" in (fromlist or ())):
            pytest.fail("default tick imported optional adapter")
        return original_import(name, globals, locals, fromlist, level)
    monkeypatch.setattr(builtins, "__import__", no_optional_import)
    keys = set(bridge.__dict__)
    run(bridge, method)
    assert set(bridge.__dict__) == keys
    assert "_decision_delivery_observer" not in bridge.__getstate__()


@pytest.mark.parametrize("kwargs", [
    {"max_agent_rows": True}, {"max_agent_rows": 0}, {"max_agent_rows": 65537},
    {"max_candidate_rows": False}, {"max_candidate_rows": -1}, {"max_move_rows": 0}, {"max_move_rows": 65537},
    {"max_retained_bytes": True}, {"max_retained_bytes": 0}, {"max_retained_bytes": 33554433},
    {"selected_agent_ids": [True]}, {"selected_agent_ids": [-1]}, {"selected_agent_ids": [2**32]},
    {"selected_agent_ids": [2, 1]}, {"selected_agent_ids": [1, 1]}, {"selected_agent_ids": iter([1])},
    {"selected_agent_ids": list(range(65537))},
])
def test_invalid_configuration_cannot_touch_native_or_attach(bridge, kwargs):
    with pytest.raises(ValueError): delivery.DecisionDeliveryObserver.attach(bridge, **kwargs)
    assert not bridge._sim.config_calls and "_decision_delivery_observer" not in bridge.__dict__


def test_attachment_is_explicit_unique_and_requires_complete_stage2_api(bridge, monkeypatch):
    original = bridge._sim.get_decision_delivery_move_frame
    monkeypatch.setattr(bridge._sim, "get_decision_delivery_move_frame", None)
    with pytest.raises(RuntimeError, match="Stage 2"): delivery.DecisionDeliveryObserver.attach(bridge)
    assert not bridge._sim.config_calls
    monkeypatch.setattr(bridge._sim, "get_decision_delivery_move_frame", original)
    delivery.DecisionDeliveryObserver.attach(bridge)
    with pytest.raises(RuntimeError, match="already attached"): delivery.DecisionDeliveryObserver.attach(bridge)


@pytest.mark.parametrize("selection", [None, [], [7], [2**32-1]])
def test_selection_and_successful_empty_capture_keep_their_distinct_scope(bridge, selection):
    observer = delivery.DecisionDeliveryObserver.attach(bridge, selected_agent_ids=selection)
    assert observer.read_latest(expected_source_turn=11).reason == "not_ready"
    run(bridge)
    result = observer.read_latest(expected_source_turn=11)
    assert result.status == "captured"
    header = result.move_header.to_pylist()[0]
    assert header["selection_is_explicit"] == (selection is not None)
    assert header["selected_ids_requested"] == len(selection or ())
    assert result.moves.num_rows == (2 if selection is None or 7 in selection else 0)


@pytest.mark.parametrize("phase", ["prepare", "conversion", "normal"])
@pytest.mark.parametrize("method", ["tick", "tick_agents"])
def test_same_turn_failed_attempt_cannot_reuse_old_native_frame(bridge, monkeypatch, phase, method):
    import chronicler.agent_bridge as module
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge, method)
    first = observer.read_latest(expected_source_turn=11)
    if phase == "prepare":
        monkeypatch.setattr(module, "build_signals", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("prepare")))
    elif phase == "conversion":
        bridge._sim.fail_tick = True
    else:
        bridge._process_tick_results = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("normal processor"))
    with pytest.raises((ValueError, TypeError)): getattr(bridge, method)(SimpleNamespace(turn=11))
    result = observer.read_latest(expected_source_turn=11)
    assert result.status == "unavailable" and result.reason == "attempt_incomplete"
    assert result.attempt == first.attempt + 1 and result.moves is None
    assert bridge._sim.turn == 11  # Deliberately insufficient as freshness proof.


def test_successful_same_turn_retry_and_wrong_request_use_attempt_identity(bridge):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge); first = observer.read_latest(expected_source_turn=11)
    bridge._sim.fail_tick = True
    with pytest.raises(TypeError): bridge.tick(SimpleNamespace(turn=11))
    bridge._sim.fail_tick = False
    run(bridge)
    assert observer.read_latest(expected_source_turn=11).attempt == first.attempt + 2
    assert observer.read_latest(expected_source_turn=12).reason == "stale_request"


@pytest.mark.parametrize("bad", [True, -1, 2**32, 1.0, None])
def test_accessor_requires_actual_uint32_turn(bridge, bad):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    with pytest.raises(ValueError): observer.read_latest(expected_source_turn=bad)


@pytest.mark.parametrize("which, changes", [
    ("decision", {"schema_version": 2}), ("move", {"schema_version": 1}),
    ("decision", {"source_turn": None}), ("move", {"source_turn": 9}),
    ("decision", {"enabled": False}), ("move", {"active_ablation": 1}),
    ("decision", {"agent_limit": 5}), ("move", {"move_limit": 5}),
    ("decision", {"selection_is_explicit": True}), ("move", {"selected_ids_requested": 3}),
    ("move", {"capture_finished": False}), ("move", {"native_event_ordinals_are_zero_based": False}),
    ("decision", {"applied_move_provenance_complete": True}), ("move", {"counterfactual_marginals_computed": True}),
])
def test_bad_frame_contract_is_reporting_failure_after_normal_processing(bridge, which, changes):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    target = bridge._sim.decision_overrides if which == "decision" else bridge._sim.move_overrides
    target.update(changes)
    run(bridge)
    result = observer.read_latest(expected_source_turn=11)
    assert result.status == "unavailable" and result.reason == "frame_contract" and result.moves is None
    assert bridge._sim.ticks == 1


def test_getter_and_unexpected_hook_failures_never_interrupt_or_leak_old_payload(bridge, monkeypatch):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge)
    bridge._sim.fail_getter = True
    run(bridge)
    result = observer.read_latest(expected_source_turn=11)
    assert result.reason == "capture_failed" and result.moves is None and "private" not in repr(result)
    monkeypatch.setattr(observer, "_capture", lambda *args: (_ for _ in ()).throw(RuntimeError("private")))
    run(bridge)
    assert observer.read_latest(expected_source_turn=11).reason == "detached"


def test_begin_bookkeeping_failure_detaches_before_physics_without_reusing_old_data(bridge, monkeypatch):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge)
    monkeypatch.setattr(observer, "_begin", lambda *args: (_ for _ in ()).throw(RuntimeError("private")))
    run(bridge)
    assert observer.read_latest(expected_source_turn=11).reason == "detached"
    assert observer.read_latest(expected_source_turn=11).moves is None


@pytest.mark.parametrize("transform", [
    lambda first: first[:2],
    lambda first: (first[0].slice(0, 0), first[1], first[2]),
    lambda first: (first[0].rename_columns(["wrong"] + first[0].schema.names[1:]), first[1], first[2]),
    lambda first: (first[0], first[1].select(list(reversed(first[1].schema.names))), first[2]),
    lambda first: (first[0], first[1].replace_schema_metadata({"wrong": "metadata"}), first[2]),
])
def test_schema_shape_and_metadata_must_match_versioned_native_contract(bridge, transform):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    bridge._sim.first_transform = transform
    run(bridge)
    assert observer.read_latest(expected_source_turn=11).reason == "frame_contract"


def test_actual_null_under_nonnullable_uint32_bits_is_rejected(bridge):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    def null_bits(first):
        decisions = first[1]
        index = decisions.schema.get_field_index("utility_migrate_bits")
        field = decisions.schema.field(index)
        assert not field.nullable
        decisions = decisions.set_column(index, field, pa.array([None], type=pa.uint32()))
        assert decisions.column(index).null_count == 1 and not decisions.schema.field(index).nullable
        return first[0], decisions, first[2]
    bridge._sim.first_transform = null_bits
    run(bridge)
    result = observer.read_latest(expected_source_turn=11)
    assert result.reason == "frame_contract" and result.decisions is None


@pytest.mark.parametrize("field, bad", [("native_event_ordinal", 0), ("native_event_ordinal", 2),
                                       ("native_event_ordinal", None), ("agent_id", 8), ("to_region", 0),
                                       ("migration_driver", 4), ("applied", False)])
def test_applied_join_uses_actual_full_native_batch_not_filtered_migrations(bridge, field, bad):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    def corrupt(second):
        rows = second[1].to_pylist(); rows[1][field] = bad
        return second[0], batch(delivery._MOVES, rows)
    bridge._sim.second_transform = corrupt
    run(bridge)
    assert observer.read_latest(expected_source_turn=11).reason == "event_link"


def test_paired_null_applied_driver_cannot_match_a_malformed_native_event(bridge, monkeypatch):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    original_tick = bridge._sim.tick
    def malformed_events(turn, signals):
        events = original_tick(turn, signals)
        index = events.schema.get_field_index("migration_driver")
        events = events.set_column(index, events.schema.field(index), pa.array([0, None], type=pa.uint8()))
        assert not events.schema.field(index).nullable and events.column(index)[1].as_py() is None
        return events
    def null_applied_driver(second):
        rows = second[1].to_pylist(); rows[1]["migration_driver"] = None
        return second[0], batch(delivery._MOVES, rows)
    monkeypatch.setattr(bridge._sim, "tick", malformed_events)
    bridge._sim.second_transform = null_applied_driver
    run(bridge)
    result = observer.read_latest(expected_source_turn=11)
    assert result.reason == "event_link" and result.moves is None


def test_original_native_join_fields_require_the_native_nonnullable_schema(bridge, monkeypatch):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    original_tick = bridge._sim.tick
    def nullable_schema(turn, signals):
        events = original_tick(turn, signals)
        index = events.schema.get_field_index("turn")
        return events.set_column(index, pa.field("turn", pa.uint32(), nullable=True), events.column(index))
    monkeypatch.setattr(bridge._sim, "tick", nullable_schema)
    run(bridge)
    assert observer.read_latest(expected_source_turn=11).reason == "event_link"


def test_truncation_and_unknown_origin_are_preserved_not_repaired_from_events(bridge):
    observer = delivery.DecisionDeliveryObserver.attach(bridge, max_move_rows=1)
    bridge._sim.decision_overrides["decision_capture_complete"] = False
    run(bridge)
    result = observer.read_latest(expected_source_turn=11)
    assert result.status == "captured" and result.moves.num_rows == 1
    assert not result.move_header.to_pylist()[0]["applied_move_provenance_complete"]
    observer.close()
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    def unknown(second):
        rows = second[1].to_pylist(); rows[1].update(origin_valid=False, origin_operation_ordinal=None, role=255)
        return second[0], batch(delivery._MOVES, rows)
    bridge._sim.second_transform = unknown
    bridge._sim.move_overrides.update(applied_move_provenance_complete=False, missing_applied_origins=1)
    run(bridge)
    result = observer.read_latest(expected_source_turn=11)
    assert result.status == "captured" and result.applied_event_links_checked == 1
    assert not result.moves.column("origin_valid")[1].as_py()
    assert result.moves.column("role")[1].as_py() == 255


@pytest.mark.parametrize("limit", [1, 300])
def test_byte_limit_retains_only_validated_header_metadata_that_fits_and_no_rows(bridge, limit):
    observer = delivery.DecisionDeliveryObserver.attach(bridge, max_retained_bytes=limit)
    run(bridge)
    result = observer.read_latest(expected_source_turn=11)
    assert result.reason == "retention_limit" and result.moves is result.decisions is result.candidates is None
    if limit == 1:
        assert result.move_header is result.decision_header is None
    else:
        assert result.move_header.to_pylist()[0]["applied_selected"] == 1
        assert sum(b.get_total_buffer_size() for b in (result.move_header, result.decision_header)) <= limit
    assert result.native_event_count is None


def test_native_pool_replacement_and_close_failure_are_explicit(bridge):
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge)
    old = bridge._sim; bridge._sim = FakeSim()
    assert observer.read_latest(expected_source_turn=11).reason == "pool_replaced"
    assert observer.close().reason == "closed" and old.config_calls[-1][0] is False
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge)
    bridge._sim.fail_disable = True
    assert observer.close().reason == "disable_failed"
    run(bridge)
    assert observer.read_latest(expected_source_turn=11).reason == "disable_failed"
    bridge._sim.fail_disable = False
    assert observer.close().reason == "closed"
    assert "_decision_delivery_observer" not in bridge.__dict__


def test_detached_old_close_cannot_disable_new_attachment_on_same_simulator(bridge, monkeypatch):
    old = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge)
    monkeypatch.setattr(old, "_capture", lambda *args: (_ for _ in ()).throw(RuntimeError("unexpected hook failure")))
    run(bridge)
    assert old.read_latest(expected_source_turn=11).reason == "detached"
    newer = delivery.DecisionDeliveryObserver.attach(bridge)
    calls = list(bridge._sim.config_calls)
    assert old.close().reason == "detached"
    assert bridge._sim.config_calls == calls and bridge._sim.enabled
    assert bridge.__dict__["_decision_delivery_observer"] is newer
    run(bridge)
    assert newer.read_latest(expected_source_turn=11).status == "captured"
    assert old.read_latest(expected_source_turn=11).reason == "detached"
    assert newer.close().reason == "closed" and not bridge._sim.enabled


def test_pickle_omits_all_attachment_state_and_restore_does_not_recreate_it():
    bridge = AgentBridge.__new__(AgentBridge)
    bridge._mode, bridge._sim = "hybrid", FakeSim()
    before = pickle.dumps(bridge)
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    token = observer._begin(11); bridge._sim.turn = 11; observer._capture(token, event_batch())
    assert observer.read_latest(expected_source_turn=11).status == "captured"
    assert "_decision_delivery_observer" not in bridge.__getstate__()
    assert pickle.dumps(bridge) == before
    restored = pickle.loads(before)
    assert "_decision_delivery_observer" not in restored.__dict__
    assert not restored._sim.enabled


def test_reset_and_close_clear_enabled_observer_without_changing_ordinary_cleanup(bridge):
    bridge._event_window = deque()
    bridge._demand_manager = SimpleNamespace(reset=lambda: None)
    for name in ("named_agents", "gp_by_agent_id", "_origin_regions", "_departure_turns", "displacement_by_region", "_wealth_stats"):
        setattr(bridge, name, {})
    for name in ("_pending_dynasty_events", "_relationship_stats_history", "_household_stats_history", "_merchant_trip_stats_history", "_knowledge_stats_history"):
        setattr(bridge, name, [])
    bridge._sidecar = bridge._shadow_logger = None
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge); bridge.reset()
    assert observer.read_latest(expected_source_turn=11).reason == "reset"
    observer = delivery.DecisionDeliveryObserver.attach(bridge)
    run(bridge); bridge.close()
    assert observer.read_latest(expected_source_turn=11).reason == "closed"
    keys = set(bridge.__dict__); calls = len(bridge._sim.config_calls)
    bridge.reset(); bridge.close()
    assert set(bridge.__dict__) == keys and len(bridge._sim.config_calls) == calls
