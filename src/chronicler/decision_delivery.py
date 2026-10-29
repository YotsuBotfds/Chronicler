"""Explicit, bounded Python access to the native decision-delivery observer.

Importing this module probes no native runtime and opens no files. Frames are
captured after normal AgentBridge processing; read_latest never calls Rust.
"""
from __future__ import annotations

from dataclasses import dataclass
import weakref

_ATTRIBUTE = "_decision_delivery_observer"
_MAX_ROWS = 65536
_MAX_BYTES = 32 * 1024 * 1024
_U32_MAX = 2**32 - 1
_REASONS = frozenset(("not_ready", "attempt_incomplete", "pool_replaced", "detached", "stale_request",
    "frame_contract", "event_link", "retention_limit", "capture_failed", "closed", "reset", "disable_failed"))


@dataclass(frozen=True)
class DeliveryReadout:
    status: str
    reason: str | None
    source_turn: int | None
    attempt: int
    bridge_mode: str
    decision_header: object | None = None
    decisions: object | None = None
    candidates: object | None = None
    move_header: object | None = None
    moves: object | None = None
    native_event_count: int | None = None
    applied_event_links_checked: int = 0


class _Refused(ValueError):
    def __init__(self, code, headers=None):
        if code not in _REASONS:
            raise ValueError("unregistered decision delivery reason")
        self.code, self.headers = code, headers
        super().__init__(code)


def _require(ok, code="frame_contract"):
    if not ok:
        raise _Refused(code)


def _fields(names, kind, nullable=False):
    return tuple((name, kind, nullable) for name in names.split())


_HEADER_START = _fields("schema_version", "uint16") + _fields("enabled", "bool") + _fields("source_turn", "uint32", True) + _fields("active_ablation", "uint8")
_DECISION_HEADER = _HEADER_START + _fields("decision_capture_complete applied_move_provenance_complete counterfactual_marginals_computed selection_is_explicit", "bool") + _fields(
    "agent_limit candidate_limit selected_ids_requested alive_seen_all selected_alive_seen trip_skipped_all evaluated_all displaced_all mobility_eligible_all admissible_candidates_all dropped_agent_rows dropped_candidate_rows", "uint64")
_MOVE_HEADER = _HEADER_START + _fields("selection_is_explicit capture_finished applied_move_provenance_complete counterfactual_marginals_computed native_event_ordinals_are_zero_based", "bool") + _fields(
    "move_limit selected_ids_requested operations_seen_all operations_selected dropped_move_rows tracking_admission_dropped tracked_origins_peak missing_applied_origins own_proposals_all replacement_removals_all follower_writes_all cancelled_existing_all blocked_nonproposers_all dedup_drops_all applied_all applied_selected", "uint64")
_DECISIONS = (_fields("agent_id", "uint32") + _fields("region", "uint16") + _fields("civ occupation", "uint8")
    + _fields("age displacement", "uint16") + _fields("status", "uint8") + _fields("selected_target", "uint16") + _fields("chosen_action", "uint8")
    + _fields("mobility_eligible needs_computed needs_migration_applied wealth_computed wealth_multiplier_applied community_anchor_computed final_utilities_valid loyalty_drift_observed", "bool")
    + tuple((f"need_{name}_bits", "uint32", False) for name in ("safety", "material", "social", "spiritual", "autonomy", "purpose"))
    + tuple((f"{prefix}_{name}_bits", "uint32", False) for name in ("rebel", "migrate", "switch", "stay") for prefix in ("need_raw", "need_capped", "utility"))
    + tuple((f"migration_need_{name}_bits", "uint32", False) for name in ("safety", "material", "social", "spiritual"))
    + tuple((f"migration_{name}_bits", "uint32", False) for name in ("base", "pre_needs", "post_needs", "post_pull", "post_wealth", "final"))
    + _fields("roots_bits home_bonds_bits opportunity_bits voluntary_pull_bits personal_wealth_bits effective_wealth_bits wealth_factor_bits community_anchor_bits autonomy_deficit_bits autonomy_factor_bits effective_drift_bits", "uint32"))
_CANDIDATES = (_fields("agent_id", "uint32") + _fields("region target", "uint16")
    + _fields("mobility_eligible hysteresis_kept became_best_at_iteration", "bool")
    + _fields("own_score_bits own_ratio_bits target_ratio_bits roots_bits post_roots_pull_bits applied_pull_bits target_base_score_bits river_bits pre_news_score_bits", "uint32")
    + tuple((f"{prefix}_{name}_bits", "uint32", False) for name in ("frontier", "wage", "chain", "urban", "learning") for prefix in ("gross", "net")))
_MOVES = (_fields("operation_ordinal", "uint64") + _fields("operation", "uint8") + _fields("applied", "bool")
    + _fields("bucket", "uint16") + _fields("agent_id", "uint32") + _fields("from_region to_region", "uint16")
    + _fields("role", "uint8") + _fields("lead_agent_id trigger_agent_id", "uint32", True) + _fields("reason", "uint8")
    + _fields("rejected_to_region", "uint16", True) + _fields("prior_count_valid", "bool") + _fields("prior_proposal_count", "uint64")
    + _fields("prior_from_region prior_to_region", "uint16", True) + _fields("origin_valid", "bool")
    + _fields("origin_operation_ordinal native_event_ordinal", "uint64", True) + _fields("migration_driver", "uint8", True))


def _batch(value, schema, limit):
    import pyarrow as pa

    result = pa.record_batch(value)
    _require(result.num_rows <= limit)
    _require(tuple((f.name, str(f.type), f.nullable) for f in result.schema) == schema)
    _require(not result.schema.metadata)
    _require(all(field.nullable or column.null_count == 0 for field, column in zip(result.schema, result.columns)))
    return result


def _event_links(events, moves, source_turn):
    import pyarrow as pa

    events = pa.record_batch(events)
    kinds = {"agent_id": "uint32", "event_type": "uint8", "region": "uint16",
             "target_region": "uint16", "turn": "uint32", "migration_driver": "uint8"}
    for name, kind in kinds.items():
        _require(name in events.schema.names and str(events.schema.field(name).type) == kind
                 and not events.schema.field(name).nullable, "event_link")
    columns = {name: events.column(name) for name in kinds}
    checked = 0
    for index in range(moves.num_rows):
        def value(name):
            return moves.column(name)[index].as_py()
        applied = value("applied")
        _require(applied == (value("operation") == 7), "event_link")
        if not applied:
            continue
        driver = value("migration_driver")
        _require(type(driver) is int, "event_link")
        ordinal = value("native_event_ordinal")
        _require(type(ordinal) is int and 0 <= ordinal < events.num_rows, "event_link")
        actual = tuple(columns[name][ordinal].as_py() for name in kinds)
        expected = (value("agent_id"), 2, value("from_region"), value("to_region"), source_turn, driver)
        _require(actual == expected, "event_link")
        checked += 1
    return events.num_rows, checked


class DecisionDeliveryObserver:
    """One explicit attachment; no automatic history, writer or callbacks."""

    @classmethod
    def attach(cls, bridge, *, max_agent_rows=4096, max_candidate_rows=16384,
               max_move_rows=16384, selected_agent_ids=None, max_retained_bytes=8 * 1024 * 1024):
        limits = (max_agent_rows, max_candidate_rows, max_move_rows)
        if any(type(n) is not int or not 1 <= n <= _MAX_ROWS for n in limits):
            raise ValueError("decision delivery row limits must be integers in 1..65536")
        if type(max_retained_bytes) is not int or not 1 <= max_retained_bytes <= _MAX_BYTES:
            raise ValueError("decision delivery byte limit must be an integer in 1..33554432")
        if selected_agent_ids is not None:
            if type(selected_agent_ids) not in (tuple, list) or len(selected_agent_ids) > _MAX_ROWS:
                raise ValueError("decision delivery selection must be a bounded list or tuple")
            if any(type(n) is not int or not 0 <= n <= _U32_MAX for n in selected_agent_ids):
                raise ValueError("decision delivery IDs must be exact uint32 integers")
            if any(a >= b for a, b in zip(selected_agent_ids, selected_agent_ids[1:])):
                raise ValueError("decision delivery IDs must be sorted and unique")
            selected_agent_ids = tuple(selected_agent_ids)
        if bridge.__dict__.get(_ATTRIBUTE) is not None:
            raise RuntimeError("decision delivery observer already attached")
        if bridge._mode not in ("hybrid", "shadow", "demographics-only"):
            raise ValueError("unsupported decision delivery bridge mode")
        sim = bridge._sim
        if not all(callable(getattr(sim, name, None)) for name in
                   ("configure_decision_delivery", "get_decision_delivery_frame", "get_decision_delivery_move_frame")):
            raise RuntimeError("fresh Stage 2 decision delivery extension required")
        observer = cls()
        observer._bridge = weakref.ref(bridge)
        observer._sim, observer._limits, observer._selected = sim, limits, selected_agent_ids
        observer._byte_limit, observer._mode = max_retained_bytes, bridge._mode
        observer._sequence, observer._source, observer._pending = 0, None, None
        observer._latest, observer._reason, observer._closed = None, "not_ready", False
        sim.configure_decision_delivery(True, max_agent_rows, max_candidate_rows,
            None if selected_agent_ids is None else list(selected_agent_ids), max_move_rows=max_move_rows)
        bridge.__dict__[_ATTRIBUTE] = observer
        return observer

    def _attached(self):
        bridge = self._bridge()
        return bridge is not None and bridge.__dict__.get(_ATTRIBUTE) is self

    def _unavailable(self, reason):
        if reason not in _REASONS:
            reason = "capture_failed"
        return DeliveryReadout("unavailable", reason, self._source, self._sequence, self._mode)

    def _begin(self, source_turn):
        self._latest, self._pending = None, None
        if self._closed:
            return None
        if not self._attached() or self._bridge()._sim is not self._sim:
            self._reason = "pool_replaced"
            return None
        self._sequence += 1
        self._source = source_turn if type(source_turn) is int and 0 <= source_turn <= _U32_MAX else None
        self._pending, self._reason = self._sequence, "attempt_incomplete"
        return self._pending

    def _capture(self, token, events):
        if token != self._pending or not self._attached():
            return
        self._pending = None
        self._latest = None
        try:
            _require(self._bridge()._sim is self._sim, "pool_replaced")
            _require(type(self._source) is int and 0 <= self._source <= _U32_MAX)
            first = self._sim.get_decision_delivery_frame()
            second = self._sim.get_decision_delivery_move_frame()
            _require(type(first) in (tuple, list) and len(first) == 3)
            _require(type(second) in (tuple, list) and len(second) == 2)
            h = _batch(first[0], _DECISION_HEADER, 1)
            mh = _batch(second[0], _MOVE_HEADER, 1)
            _require(h.num_rows == mh.num_rows == 1)
            a, b = h.to_pylist()[0], mh.to_pylist()[0]
            _require(a["schema_version"] == 1 and b["schema_version"] == 2)
            _require(a["enabled"] and b["enabled"] and a["source_turn"] == b["source_turn"] == self._source)
            _require(a["active_ablation"] == b["active_ablation"])
            _require(not a["applied_move_provenance_complete"] and not a["counterfactual_marginals_computed"] and not b["counterfactual_marginals_computed"])
            _require(b["capture_finished"] and b["native_event_ordinals_are_zero_based"])
            explicit, requested = self._selected is not None, len(self._selected or ())
            _require(all(row["selection_is_explicit"] == explicit and row["selected_ids_requested"] == requested for row in (a, b)))
            _require((a["agent_limit"], a["candidate_limit"], b["move_limit"]) == self._limits)
            decisions = _batch(first[1], _DECISIONS, self._limits[0])
            candidates = _batch(first[2], _CANDIDATES, self._limits[1])
            moves = _batch(second[1], _MOVES, self._limits[2])
            batches = (h, decisions, candidates, mh, moves)
            if sum(batch.get_total_buffer_size() for batch in batches) > self._byte_limit:
                raise _Refused("retention_limit", (h, mh))
            count, checked = _event_links(events, moves, self._source)
            self._latest = DeliveryReadout("captured", None, self._source, self._sequence, self._mode,
                h, decisions, candidates, mh, moves, count, checked)
            self._reason = "not_ready"
        except _Refused as exc:
            self._reason = exc.code
            if exc.headers is not None and sum(b.get_total_buffer_size() for b in exc.headers) <= self._byte_limit:
                self._latest = DeliveryReadout("unavailable", exc.code, self._source, self._sequence,
                    self._mode, decision_header=exc.headers[0], move_header=exc.headers[1])
        except Exception:
            self._reason = "capture_failed"

    def read_latest(self, *, expected_source_turn):
        if type(expected_source_turn) is not int or not 0 <= expected_source_turn <= _U32_MAX:
            raise ValueError("expected source turn must be an exact uint32 integer")
        if not self._attached():
            return self._unavailable(self._reason if self._closed else "detached")
        if self._bridge()._sim is not self._sim:
            return self._unavailable("pool_replaced")
        if self._source is not None and expected_source_turn != self._source:
            return self._unavailable("stale_request")
        return self._latest if self._latest is not None else self._unavailable(self._reason)

    def _stop(self, reason):
        self._latest, self._pending, self._closed, self._reason = None, None, True, reason
        bridge = self._bridge()
        owner = None if bridge is None else bridge.__dict__.get(_ATTRIBUTE)
        if owner is not None and owner is not self and getattr(owner, "_sim", None) is self._sim:
            self._reason = "detached"
            return self._unavailable(self._reason)
        try:
            self._sim.configure_decision_delivery(False)
        except Exception:
            self._reason = "disable_failed"
            return self._unavailable(self._reason)
        if bridge is not None and bridge.__dict__.get(_ATTRIBUTE) is self:
            bridge.__dict__.pop(_ATTRIBUTE)
        return self._unavailable(reason)

    def close(self):
        """Disable explicitly; a failure remains visible and can be retried."""
        if self._closed and self._reason != "disable_failed":
            return self._unavailable(self._reason)
        return self._stop("closed")
