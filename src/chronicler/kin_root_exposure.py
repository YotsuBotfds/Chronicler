"""Bounded analysis of already captured decision-delivery rows.

This module opens no files, calls no simulator and draws no random numbers.
It consumes the existing observer's wire fields, not a new capture format.
Projected doses keep the recorded destination fixed; they are neither sampled
counterfactual decisions nor estimates of the twenty-turn causal endpoint.
"""
from __future__ import annotations

import json
import math
import struct
from types import MappingProxyType

from .decision_delivery import (
    _CANDIDATES, _DECISION_HEADER, _DECISIONS, _MOVE_HEADER, _MOVES,
)

MAX_ROWS = 65_536
MAX_INPUT_RECORD_BYTES = 32 * 1024 * 1024
MAX_REPORT_BYTES = 64 * 1024
_DRIVERS = ("frontier", "wage", "chain", "urban", "learning")
# These source-owned arithmetic constants have an explicit Rust-source witness
# in the contract cases. They describe this reader, not a configurable policy.
MODEL_ARITHMETIC = MappingProxyType({
    "roots_free_age": 35, "roots_per_year": 0.006,
    "roots_married": 0.02, "roots_per_home_bond": 0.02,
    "roots_home_bond_cap": 2.0, "decision_temperature": 0.3,
})


def _require(ok, reason):
    if not ok:
        raise ValueError("kin_root_exposure:" + reason)


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _f32(value):
    try:
        result = struct.unpack("!f", struct.pack("!f", value))[0]
    except (OverflowError, struct.error):
        raise ValueError("kin_root_exposure:f32_range") from None
    _require(math.isfinite(result), "f32_range")
    return result


def _float(bits):
    return struct.unpack("!f", struct.pack("!I", bits))[0]


def _sum32(values):
    total = values[0]
    for value in values[1:]:
        total = _f32(total + value)
    return total


def _net(gross, roots):
    total = _sum32(gross)
    if total <= roots or total <= 0:
        return [0.0] * 5
    scale = _f32(_f32(total - roots) / total)
    return [_f32(value * scale) for value in gross]


class _Budget:
    def __init__(self):
        self.bytes = 0

    def row(self, value, schema):
        _require(type(value) is dict and set(value) == {name for name, _, _ in schema}, "row_fields")
        result = value.copy()
        for name, kind, nullable in schema:
            item = result[name]
            if nullable and item is None:
                continue
            if kind == "bool":
                _require(type(item) is bool, "boolean_type")
            else:
                width = int(kind.removeprefix("uint"))
                _require(type(item) is int and 0 <= item < 2**width, "unsigned_type")
            if name.endswith("_bits"):
                number = _float(item)
                gated = name.startswith("utility_") or name == "migration_final_bits"
                _require(math.isfinite(number) or (gated and number == -math.inf), "nonfinite_number")
        self.bytes += len(_canonical(result))
        _require(self.bytes <= MAX_INPUT_RECORD_BYTES, "input_byte_limit")
        return result

    def rows(self, values, schema):
        for value in values:
            yield self.row(value, schema)


def summarize_kin_root_exposure(*, decision_header, decision_rows, candidate_rows,
                                move_header, move_rows):
    """Summarize builtin rows obtained from the five existing Arrow batches.

    Headers are one row each; the other arguments are exact builtin lists of
    exact builtin dictionaries with the current decision_delivery fields.
    Input is bounded to 65,536 rows across all three bodies and 32 MiB of
    canonical JSON+LF records. The aggregate report is at most 64 KiB.
    Truncation and explicit selection stay visible; invalid schemas/joins or
    already-ablated kin roots refuse. Caller-supplied rows attest no execution.
    """
    bodies = (decision_rows, candidate_rows, move_rows)
    _require(all(type(body) is list for body in bodies), "body_type")
    _require(sum(map(len, bodies)) <= MAX_ROWS, "input_row_limit")
    budget = _Budget()
    dh = budget.row(decision_header, _DECISION_HEADER)
    mh = budget.row(move_header, _MOVE_HEADER)
    _require(dh["schema_version"] == 1 and mh["schema_version"] == 2, "schema_version")
    _require(dh["enabled"] and mh["enabled"] and mh["capture_finished"], "capture_unavailable")
    _require(dh["source_turn"] is not None and dh["source_turn"] == mh["source_turn"], "source_turn")
    _require(dh["active_ablation"] == mh["active_ablation"] <= 15
             and not dh["active_ablation"] & 2, "kin_roots_already_ablated")
    _require(not dh["applied_move_provenance_complete"]
             and not dh["counterfactual_marginals_computed"]
             and not mh["counterfactual_marginals_computed"]
             and mh["native_event_ordinals_are_zero_based"], "header_semantics")
    _require(dh["selection_is_explicit"] == mh["selection_is_explicit"]
             and dh["selected_ids_requested"] == mh["selected_ids_requested"] <= MAX_ROWS,
             "selection_join")
    if not dh["selection_is_explicit"]:
        _require(dh["selected_ids_requested"] == 0
                 and dh["selected_alive_seen"] == dh["alive_seen_all"], "unselected_header")
    for actual, limit in ((len(decision_rows), dh["agent_limit"]),
                          (len(candidate_rows), dh["candidate_limit"]),
                          (len(move_rows), mh["move_limit"])):
        _require(1 <= limit <= MAX_ROWS and actual <= limit, "declared_row_limit")
    _require(len(decision_rows) + dh["dropped_agent_rows"] == dh["selected_alive_seen"]
             <= dh["alive_seen_all"], "decision_count")
    _require(dh["trip_skipped_all"] + dh["evaluated_all"] == dh["alive_seen_all"]
             and dh["displaced_all"] <= dh["evaluated_all"]
             and dh["mobility_eligible_all"] <= dh["evaluated_all"] - dh["displaced_all"],
             "decision_global_counts")
    _require(dh["decision_capture_complete"] ==
             (dh["dropped_agent_rows"] == dh["dropped_candidate_rows"] == 0), "decision_complete")
    _require(len(candidate_rows) <= dh["admissible_candidates_all"], "candidate_count")
    if not dh["selection_is_explicit"]:
        _require(len(candidate_rows) + dh["dropped_candidate_rows"] == dh["admissible_candidates_all"], "candidate_count")
    _require(len(move_rows) + mh["dropped_move_rows"] == mh["operations_selected"]
             <= mh["operations_seen_all"], "move_count")
    _require(sum(mh[name] for name in ("own_proposals_all", "replacement_removals_all",
        "follower_writes_all", "cancelled_existing_all", "blocked_nonproposers_all",
        "dedup_drops_all", "applied_all")) == mh["operations_seen_all"], "move_global_counts")
    _require(mh["applied_move_provenance_complete"] ==
             (mh["dropped_move_rows"] == mh["tracking_admission_dropped"] == mh["missing_applied_origins"] == 0),
             "move_complete")

    agents = {}
    dc = dict.fromkeys(("captured", "trip", "evaluated", "displaced", "mobility_eligible",
        "relationship_root_present", "selected_home", "selected_outward", "selected_target_missing",
        "selected_positive_pull", "selected_root_sensitive_pull", "positive_post_wealth_dose",
        "wealth_attenuates_dose"), 0)
    for row in budget.rows(decision_rows, _DECISIONS):
        key = row["agent_id"]
        _require(key not in agents, "duplicate_agent")
        _require(row["status"] in (1, 2), "decision_status")
        trip = row["status"] == 1
        _require(not trip or not row["mobility_eligible"], "trip_mobility")
        _require(not row["displacement"] or not row["mobility_eligible"], "displaced_mobility")
        _require(trip or row["final_utilities_valid"], "missing_final_utilities")
        roots = _float(row["roots_bits"])
        home = _float(row["home_bonds_bits"])
        _require(roots >= 0 and home >= 0, "negative_roots")
        age_roots = _f32(_f32(MODEL_ARITHMETIC["roots_per_year"])
                         * max(row["age"] - MODEL_ARITHMETIC["roots_free_age"], 0))
        if row["mobility_eligible"]:
            home_roots = _f32(_f32(MODEL_ARITHMETIC["roots_per_home_bond"])
                             * min(home, MODEL_ARITHMETIC["roots_home_bond_cap"]))
            possible = [_f32(_f32(age_roots + married) + home_roots)
                        for married in (0.0, _f32(MODEL_ARITHMETIC["roots_married"]))]
            _require(roots in possible, "roots_formula")
        else:
            _require(roots == home == 0, "ineligible_roots")
        factor = _float(row["wealth_factor_bits"])
        _require(0 <= factor <= 1, "wealth_factor")
        _require(not row["wealth_multiplier_applied"] or row["wealth_computed"], "wealth_validity")
        if not row["wealth_multiplier_applied"]:
            _require(factor == 1, "unapplied_wealth_factor")
        dc["captured"] += 1
        dc["trip" if trip else "evaluated"] += 1
        dc["displaced"] += not trip and bool(row["displacement"])
        dc["mobility_eligible"] += row["mobility_eligible"]
        dc["relationship_root_present"] += row["mobility_eligible"] and roots > age_roots
        dc["selected_home" if row["selected_target"] == row["region"] else "selected_outward"] += not trip
        agents[key] = {"row": row, "age_roots": age_roots, "selected_seen": False}

    cc = dict.fromkeys(("captured", "positive_gross", "root_sensitive_before_hysteresis",
        "root_sensitive_after_hysteresis", "unselected_root_sensitive"), 0)
    dose = {"pull_delta_sum": 0.0, "post_wealth_migrate_delta_sum": 0.0,
            "post_wealth_migrate_delta_max": 0.0}
    pairs = set()
    for row in budget.rows(candidate_rows, _CANDIDATES):
        _require(row["agent_id"] in agents, "orphan_candidate")
        agent = agents[row["agent_id"]]
        decision = agent["row"]
        _require(row["region"] == decision["region"] and row["mobility_eligible"] == decision["mobility_eligible"]
                 and row["roots_bits"] == decision["roots_bits"], "candidate_join")
        key = (row["agent_id"], row["target"])
        _require(key not in pairs, "duplicate_candidate")
        pairs.add(key)
        gross = [_float(row["gross_" + name + "_bits"]) for name in _DRIVERS]
        net = [_float(row["net_" + name + "_bits"]) for name in _DRIVERS]
        _require(all(value >= 0 for value in gross + net), "negative_pull")
        _require(row["mobility_eligible"] or not any(gross), "ineligible_pull")
        expected = _net(gross, _float(row["roots_bits"]))
        _require(net == expected and _float(row["post_roots_pull_bits"]) == _sum32(net), "net_pull_formula")
        applied = _sum32(net) if row["hysteresis_kept"] else 0.0
        _require(_float(row["applied_pull_bits"]) == applied, "hysteresis_pull")
        projected = _sum32(_net(gross, agent["age_roots"])) if row["mobility_eligible"] else 0.0
        raw_delta = projected - _sum32(net)
        _require(raw_delta >= 0, "negative_projected_dose")
        delta = raw_delta if row["hysteresis_kept"] else 0.0
        cc["captured"] += 1
        cc["positive_gross"] += _sum32(gross) > 0
        cc["root_sensitive_before_hysteresis"] += raw_delta > 0
        cc["root_sensitive_after_hysteresis"] += delta > 0
        selected = row["target"] == decision["selected_target"]
        cc["unselected_root_sensitive"] += delta > 0 and not selected
        if not selected:
            continue
        agent["selected_seen"] = True
        _require(_float(decision["voluntary_pull_bits"]) == applied, "selected_pull_join")
        before = _float(decision["migration_post_needs_bits"])
        old_pull_stage = _f32(before + applied) if applied > 0 else before
        _require(_float(decision["migration_post_pull_bits"]) == old_pull_stage, "pull_stage")
        factor = _float(decision["wealth_factor_bits"])
        old_wealth_stage = _f32(old_pull_stage * factor) if decision["wealth_multiplier_applied"] else old_pull_stage
        _require(_float(decision["migration_post_wealth_bits"]) == old_wealth_stage, "wealth_stage")
        new_pull = projected if row["hysteresis_kept"] else 0.0
        new_pull_stage = _f32(before + new_pull) if new_pull > 0 else before
        new_wealth_stage = _f32(new_pull_stage * factor) if decision["wealth_multiplier_applied"] else new_pull_stage
        post_delta = new_wealth_stage - old_wealth_stage
        _require(post_delta >= 0, "negative_post_wealth_dose")
        dc["selected_positive_pull"] += applied > 0
        dc["selected_root_sensitive_pull"] += delta > 0
        dc["positive_post_wealth_dose"] += post_delta > 0
        dc["wealth_attenuates_dose"] += delta > 0 and post_delta < delta
        dose["pull_delta_sum"] += delta
        dose["post_wealth_migrate_delta_sum"] += post_delta
        dose["post_wealth_migrate_delta_max"] = max(dose["post_wealth_migrate_delta_max"], post_delta)
    for agent in agents.values():
        row = agent["row"]
        if row["status"] == 2 and row["selected_target"] != row["region"] and not agent["selected_seen"]:
            dc["selected_target_missing"] += 1
    _require(not dh["decision_capture_complete"] or dc["selected_target_missing"] == 0, "missing_selected_candidate")

    mc = {"captured_operations": 0, "applied_own": 0, "applied_spouse": 0,
          "applied_dependent": 0, "applied_unknown": 0, "applied_own_with_captured_decision": 0,
          "applied_followers_with_captured_lead": 0, "applied_origin_not_captured": 0}
    operations = {}
    previous_ordinal = -1
    for row in budget.rows(move_rows, _MOVES):
        ordinal = row["operation_ordinal"]
        _require(previous_ordinal < ordinal < mh["operations_seen_all"], "operation_ordinal")
        previous_ordinal = ordinal
        _require(1 <= row["operation"] <= 7 and row["applied"] == (row["operation"] == 7), "move_operation")
        _require(row["role"] in (0, 1, 2, 255) and row["reason"] in (0, 1, 2), "move_role")
        if row["operation"] == 1:
            _require(row["role"] == 0 and row["lead_agent_id"] is None and row["origin_valid"], "own_proposal_role")
        if row["operation"] == 3:
            _require(row["role"] in (1, 2) and row["lead_agent_id"] is not None
                     and row["origin_valid"], "follower_write_role")
        if row["applied"] and row["role"] != 255:
            _require((row["role"] == 0) == (row["lead_agent_id"] is None), "applied_lead_role")
        operations[ordinal] = row
        mc["captured_operations"] += 1
        if not row["applied"]:
            continue
        role = ("own", "spouse", "dependent")[row["role"]] if row["role"] < 3 else "unknown"
        mc["applied_" + role] += 1
        mc["applied_own_with_captured_decision"] += role == "own" and row["agent_id"] in agents
        mc["applied_followers_with_captured_lead"] += role in ("spouse", "dependent") and row["lead_agent_id"] in agents
        origin = operations.get(row["origin_operation_ordinal"]) if row["origin_valid"] else None
        if origin is None:
            mc["applied_origin_not_captured"] += 1
            _require(not mh["applied_move_provenance_complete"], "missing_move_origin")
        else:
            _require(origin["operation"] in (1, 3) and origin["operation_ordinal"] < ordinal
                     and all(origin[name] == row[name] for name in
                         ("agent_id", "from_region", "to_region", "role", "lead_agent_id")), "move_origin_join")
    applied = sum(mc["applied_" + role] for role in ("own", "spouse", "dependent", "unknown"))
    _require(applied <= mh["applied_selected"] <= mh["applied_all"], "applied_count")
    if mh["dropped_move_rows"] == 0:
        _require(applied == mh["applied_selected"], "applied_count")

    complete = dh["decision_capture_complete"] and mh["applied_move_provenance_complete"]
    report = {"kind": "KIN_ROOT_CAPTURED_EXPOSURE", "schema_version": 1,
        "status": "complete_capture" if complete else "partial_capture",
        "source_turn": dh["source_turn"], "active_ablation": dh["active_ablation"],
        "selection_is_explicit": dh["selection_is_explicit"],
        "denominator": "captured selected rows" if dh["selection_is_explicit"] else "captured rows of this native pool",
        "coverage": {name: dh[name] for name in ("alive_seen_all", "selected_alive_seen", "dropped_agent_rows", "dropped_candidate_rows")},
        "move_coverage": {name: mh[name] for name in ("operations_seen_all", "operations_selected", "dropped_move_rows", "tracking_admission_dropped", "missing_applied_origins")},
        "decisions": dc, "candidates": cc, "applied_moves": mc,
        "same_destination_arithmetic": dose, "model_arithmetic": MODEL_ARITHMETIC.copy(),
        "input_record_bytes": budget.bytes,
        "input_byte_domain": "sum of canonical JSON+LF headers and rows; no outer envelope",
        "execution_attestation": None, "community_membership_observed": False,
        "counterfactual_decisions_computed": False, "twenty_turn_effect_estimate": None,
        "scope": "Recorded destination, other terms, gates and wealth factor held fixed. No new target search, random draws, household recomposition or temporal continuation."}
    _require(len(_canonical(report)) <= MAX_REPORT_BYTES, "report_byte_limit")
    return report
