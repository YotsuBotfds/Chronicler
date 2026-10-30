"""Pure row contracts and readonly Rust-constant witness; no native or World."""
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import struct

import pytest

from chronicler import decision_delivery as wire
from chronicler import kin_root_exposure as exposure


def bits(value):
    return struct.unpack("!I", struct.pack("!f", value))[0]


def f32(value):
    return struct.unpack("!f", struct.pack("!f", value))[0]


def record(schema, **values):
    result = {name: None if nullable else False if kind == "bool" else 0
              for name, kind, nullable in schema}
    result.update(values)
    return result


def decision(agent_id=1, **values):
    row = record(wire._DECISIONS, agent_id=agent_id, region=0, age=25, status=2,
        selected_target=1, chosen_action=3, mobility_eligible=True,
        final_utilities_valid=True, needs_computed=True, needs_migration_applied=True,
        wealth_computed=True, roots_bits=bits(.06), home_bonds_bits=bits(2),
        voluntary_pull_bits=bits(.44), migration_post_needs_bits=bits(.1),
        migration_post_pull_bits=bits(.54), migration_post_wealth_bits=bits(.54),
        wealth_factor_bits=bits(1))
    row.update(values)
    return row


def candidate(agent_id=1, **values):
    row = record(wire._CANDIDATES, agent_id=agent_id, region=0, target=1,
        mobility_eligible=True, hysteresis_kept=True, became_best_at_iteration=True,
        roots_bits=bits(.06), gross_frontier_bits=bits(.5), net_frontier_bits=bits(.44),
        post_roots_pull_bits=bits(.44), applied_pull_bits=bits(.44))
    row.update(values)
    return row


def frames(decisions=None, candidates=None, moves=None):
    decisions = [decision()] if decisions is None else decisions
    candidates = [candidate()] if candidates is None else candidates
    moves = [] if moves is None else moves
    dh = record(wire._DECISION_HEADER, schema_version=1, enabled=True, source_turn=7,
        decision_capture_complete=True, agent_limit=4096, candidate_limit=16384,
        alive_seen_all=len(decisions), selected_alive_seen=len(decisions),
        trip_skipped_all=sum(r["status"] == 1 for r in decisions),
        evaluated_all=sum(r["status"] == 2 for r in decisions),
        displaced_all=sum(r["status"] == 2 and bool(r["displacement"]) for r in decisions),
        mobility_eligible_all=sum(r["mobility_eligible"] for r in decisions),
        admissible_candidates_all=len(candidates))
    counts = ("own_proposals_all", "replacement_removals_all", "follower_writes_all",
              "cancelled_existing_all", "blocked_nonproposers_all", "dedup_drops_all", "applied_all")
    mh = record(wire._MOVE_HEADER, schema_version=2, enabled=True, source_turn=7,
        capture_finished=True, applied_move_provenance_complete=True,
        native_event_ordinals_are_zero_based=True, move_limit=16384,
        operations_seen_all=len(moves), operations_selected=len(moves),
        applied_selected=sum(r["applied"] for r in moves))
    for operation, name in enumerate(counts, 1):
        mh[name] = sum(r["operation"] == operation for r in moves)
    return dict(decision_header=dh, decision_rows=decisions, candidate_rows=candidates,
                move_header=mh, move_rows=moves)


def move_pair(role, agent_id=1, lead=None):
    origin = record(wire._MOVES, operation_ordinal=0, operation=1 if role == 0 else 3,
        agent_id=agent_id, from_region=0, to_region=1, role=role, lead_agent_id=lead,
        origin_valid=True)
    applied = dict(origin, operation_ordinal=1, operation=7, applied=True,
        origin_operation_ordinal=0, native_event_ordinal=0, migration_driver=0)
    return [origin, applied]


def test_empty_capture_never_becomes_a_causal_pass():
    result = exposure.summarize_kin_root_exposure(**frames([], [], []))
    assert result["status"] == "complete_capture"
    assert result["decisions"]["captured"] == 0
    assert result["twenty_turn_effect_estimate"] is None
    assert result["execution_attestation"] is None
    assert result["community_membership_observed"] is False


def test_selected_pull_reports_kin_dose_and_leaves_original_rows_unchanged():
    inputs = frames()
    before = deepcopy(inputs)
    result = exposure.summarize_kin_root_exposure(**inputs)
    assert inputs == before
    assert result["decisions"]["relationship_root_present"] == 1
    assert result["decisions"]["selected_root_sensitive_pull"] == 1
    assert result["same_destination_arithmetic"]["pull_delta_sum"] == pytest.approx(.06)
    assert result["same_destination_arithmetic"]["post_wealth_migrate_delta_sum"] == pytest.approx(.06)
    assert result["counterfactual_decisions_computed"] is False


def test_wealth_damper_shrinks_the_delivered_root_dose():
    row = decision(wealth_multiplier_applied=True, wealth_factor_bits=bits(.5),
                   migration_post_wealth_bits=bits(.27))
    result = exposure.summarize_kin_root_exposure(**frames([row]))
    assert result["decisions"]["wealth_attenuates_dose"] == 1
    assert result["same_destination_arithmetic"]["post_wealth_migrate_delta_sum"] == pytest.approx(.03)


def test_age_only_roots_are_not_counted_as_kin_exposure():
    age_root = f32(f32(.006) * 10)
    row = decision(age=45, roots_bits=bits(age_root), home_bonds_bits=bits(0))
    target = candidate(roots_bits=bits(age_root))
    result = exposure.summarize_kin_root_exposure(**frames([row], [target]))
    assert result["decisions"]["relationship_root_present"] == 0
    assert result["same_destination_arithmetic"]["pull_delta_sum"] == 0


def test_no_voluntary_mobility_does_not_ascribe_distress_moves_to_roots():
    row = decision(mobility_eligible=False, roots_bits=0, home_bonds_bits=0,
        voluntary_pull_bits=0, migration_post_pull_bits=bits(.1), migration_post_wealth_bits=bits(.1))
    target = candidate(mobility_eligible=False, roots_bits=0, gross_frontier_bits=0,
        net_frontier_bits=0, post_roots_pull_bits=0, applied_pull_bits=0)
    result = exposure.summarize_kin_root_exposure(**frames([row], [target]))
    assert result["decisions"]["selected_outward"] == 1
    assert result["decisions"]["mobility_eligible"] == 0
    assert result["same_destination_arithmetic"]["post_wealth_migrate_delta_sum"] == 0


def test_a_pull_fully_held_by_roots_still_has_a_visible_release_dose():
    row = decision(voluntary_pull_bits=0, migration_post_pull_bits=bits(.1), migration_post_wealth_bits=bits(.1))
    target = candidate(gross_frontier_bits=0, gross_chain_bits=bits(.04),
        net_frontier_bits=0, post_roots_pull_bits=0, applied_pull_bits=0)
    result = exposure.summarize_kin_root_exposure(**frames([row], [target]))
    assert result["decisions"]["selected_positive_pull"] == 0
    assert result["decisions"]["selected_root_sensitive_pull"] == 1
    assert result["same_destination_arithmetic"]["pull_delta_sum"] == pytest.approx(.04)


def test_trip_rows_are_not_counted_as_evaluated_displaced_deciders():
    row = decision(status=1, displacement=2, selected_target=0, mobility_eligible=False,
        final_utilities_valid=False, roots_bits=0, home_bonds_bits=0)
    result = exposure.summarize_kin_root_exposure(**frames([row], []))
    assert result["decisions"]["trip"] == 1
    assert result["decisions"]["evaluated"] == result["decisions"]["displaced"] == 0


def test_hysteresis_can_erase_a_positive_root_dose_before_delivery():
    row = decision(voluntary_pull_bits=0, migration_post_pull_bits=bits(.1), migration_post_wealth_bits=bits(.1))
    target = candidate(hysteresis_kept=False, applied_pull_bits=0)
    result = exposure.summarize_kin_root_exposure(**frames([row], [target]))
    assert result["candidates"]["root_sensitive_before_hysteresis"] == 1
    assert result["candidates"]["root_sensitive_after_hysteresis"] == 0
    assert result["same_destination_arithmetic"]["post_wealth_migrate_delta_sum"] == 0


def test_unselected_candidate_dose_is_not_misreported_as_selected_delivery():
    row = decision(voluntary_pull_bits=0, migration_post_pull_bits=bits(.1), migration_post_wealth_bits=bits(.1))
    selected = candidate(gross_frontier_bits=0, net_frontier_bits=0, post_roots_pull_bits=0, applied_pull_bits=0)
    other = candidate(target=2, became_best_at_iteration=False)
    result = exposure.summarize_kin_root_exposure(**frames([row], [selected, other]))
    assert result["candidates"]["unselected_root_sensitive"] == 1
    assert result["same_destination_arithmetic"]["post_wealth_migrate_delta_sum"] == 0


@pytest.mark.parametrize("role,label", [(0, "own"), (1, "spouse"), (2, "dependent")])
def test_applied_own_and_follower_roles_are_counted_separately(role, label):
    rows = [decision()]
    agent_id, lead = (1, None) if role == 0 else (2, 1)
    if role:
        rows.append(decision(2, selected_target=0, mobility_eligible=False, roots_bits=0, home_bonds_bits=0))
    result = exposure.summarize_kin_root_exposure(**frames(rows, moves=move_pair(role, agent_id, lead)))
    assert result["applied_moves"]["applied_" + label] == 1
    assert result["applied_moves"]["applied_origin_not_captured"] == 0
    assert result["applied_moves"]["applied_followers_with_captured_lead"] == int(role != 0)


def test_unknown_move_origin_stays_unknown_when_capture_is_partial():
    applied = record(wire._MOVES, operation=7, applied=True, role=255, agent_id=1,
        to_region=1, native_event_ordinal=0, migration_driver=0)
    inputs = frames(moves=[applied])
    inputs["move_header"].update(applied_move_provenance_complete=False, missing_applied_origins=1)
    result = exposure.summarize_kin_root_exposure(**inputs)
    assert result["status"] == "partial_capture"
    assert result["applied_moves"]["applied_unknown"] == 1
    assert result["applied_moves"]["applied_origin_not_captured"] == 1


def test_missing_selected_candidate_is_visible_in_partial_capture():
    inputs = frames(candidates=[])
    inputs["decision_header"].update(decision_capture_complete=False,
        dropped_candidate_rows=1, admissible_candidates_all=1)
    result = exposure.summarize_kin_root_exposure(**inputs)
    assert result["status"] == "partial_capture"
    assert result["decisions"]["selected_target_missing"] == 1
    assert result["same_destination_arithmetic"]["post_wealth_migrate_delta_sum"] == 0


def test_explicit_selection_is_never_presented_as_a_global_denominator():
    inputs = frames()
    inputs["decision_header"].update(selection_is_explicit=True, selected_ids_requested=2,
        alive_seen_all=3, evaluated_all=3, mobility_eligible_all=2, admissible_candidates_all=4)
    inputs["move_header"].update(selection_is_explicit=True, selected_ids_requested=2)
    result = exposure.summarize_kin_root_exposure(**inputs)
    assert result["denominator"] == "captured selected rows"
    assert result["coverage"]["alive_seen_all"] == 3
    assert result["decisions"]["captured"] == 1


@pytest.mark.parametrize("part", ["decision_header", "move_header", "decision_rows", "candidate_rows", "move_rows"])
@pytest.mark.parametrize("change", ["missing", "extra"])
def test_wire_row_field_drift_refuses(part, change):
    inputs = frames(moves=move_pair(0))
    row = inputs[part] if part.endswith("header") else inputs[part][0]
    if change == "missing":
        row.pop(next(iter(row)))
    else:
        row["invented"] = 0
    with pytest.raises(ValueError, match="row_fields"):
        exposure.summarize_kin_root_exposure(**inputs)


@pytest.mark.parametrize("field,value", [("agent_id", True), ("agent_id", -1),
    ("agent_id", 2**32), ("mobility_eligible", 1), ("age", 2**16)])
def test_wire_scalar_types_refuse_aliases_and_out_of_range_values(field, value):
    inputs = frames()
    inputs["decision_rows"][0][field] = value
    with pytest.raises(ValueError, match="unsigned_type|boolean_type"):
        exposure.summarize_kin_root_exposure(**inputs)


@pytest.mark.parametrize("field", ["roots_bits", "wealth_factor_bits", "need_safety_bits"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_observed_numbers_refuse(field, value):
    inputs = frames()
    inputs["decision_rows"][0][field] = bits(value)
    with pytest.raises(ValueError, match="nonfinite_number"):
        exposure.summarize_kin_root_exposure(**inputs)


@pytest.mark.parametrize("mask", [2, 3, 6, 15, 16])
def test_active_kin_ablation_or_unknown_bits_refuse(mask):
    inputs = frames()
    for key in ("decision_header", "move_header"):
        inputs[key]["active_ablation"] = mask
    with pytest.raises(ValueError, match="kin_roots_already_ablated"):
        exposure.summarize_kin_root_exposure(**inputs)


@pytest.mark.parametrize("field,value,reason", [("region", 4, "candidate_join"),
    ("agent_id", 999, "orphan_candidate"), ("net_frontier_bits", bits(.4), "net_pull_formula"),
    ("applied_pull_bits", 0, "hysteresis_pull")])
def test_candidate_identity_and_pull_inconsistencies_refuse(field, value, reason):
    inputs = frames()
    inputs["candidate_rows"][0][field] = value
    with pytest.raises(ValueError, match=reason):
        exposure.summarize_kin_root_exposure(**inputs)


@pytest.mark.parametrize("field,value,reason", [("roots_bits", bits(.09), "roots_formula"),
    ("wealth_factor_bits", bits(1.1), "wealth_factor"),
    ("voluntary_pull_bits", bits(.43), "selected_pull_join"),
    ("migration_post_pull_bits", bits(.53), "pull_stage"),
    ("migration_post_wealth_bits", bits(.53), "wealth_stage")])
def test_root_wealth_and_selected_stage_inconsistencies_refuse(field, value, reason):
    inputs = frames()
    inputs["decision_rows"][0][field] = value
    with pytest.raises(ValueError, match=reason):
        exposure.summarize_kin_root_exposure(**inputs)


def test_duplicate_agents_and_candidates_refuse():
    with pytest.raises(ValueError, match="duplicate_agent"):
        exposure.summarize_kin_root_exposure(**frames([decision(), decision()]))
    with pytest.raises(ValueError, match="duplicate_candidate"):
        exposure.summarize_kin_root_exposure(**frames(candidates=[candidate(), candidate()]))


@pytest.mark.parametrize("change", ["source_turn", "decision_version", "move_version", "complete_count", "not_finished"])
def test_header_join_and_coverage_inconsistencies_refuse(change):
    inputs = frames()
    if change == "source_turn": inputs["move_header"]["source_turn"] = 8
    elif change == "decision_version": inputs["decision_header"]["schema_version"] = 2
    elif change == "move_version": inputs["move_header"]["schema_version"] = 1
    elif change == "complete_count": inputs["decision_header"]["decision_capture_complete"] = False
    else: inputs["move_header"]["capture_finished"] = False
    with pytest.raises(ValueError):
        exposure.summarize_kin_root_exposure(**inputs)


@pytest.mark.parametrize("field,value,reason", [("role", 1, "applied_lead_role"),
    ("agent_id", 2, "move_origin_join"), ("from_region", 4, "move_origin_join"),
    ("to_region", 4, "move_origin_join")])
def test_applied_origin_join_refuses_mislabeled_moves(field, value, reason):
    moves = move_pair(0)
    moves[-1][field] = value
    with pytest.raises(ValueError, match=reason):
        exposure.summarize_kin_root_exposure(**frames(moves=moves))


def test_missing_move_origin_cannot_claim_complete_provenance():
    moves = move_pair(0)
    moves[-1]["origin_valid"] = False
    with pytest.raises(ValueError, match="missing_move_origin"):
        exposure.summarize_kin_root_exposure(**frames(moves=moves))


@pytest.mark.parametrize("role,change,reason", [(0, "follower_role", "own_proposal_role"),
    (1, "own_role", "follower_write_role"), (1, "missing_lead", "follower_write_role")])
def test_operation_role_semantics_refuse_inconsistent_origin_records(role, change, reason):
    moves = move_pair(role, 1 if role == 0 else 2, None if role == 0 else 1)
    if change == "follower_role": moves[0]["role"] = 1
    elif change == "own_role": moves[0]["role"] = 0
    else: moves[0]["lead_agent_id"] = None
    with pytest.raises(ValueError, match=reason):
        exposure.summarize_kin_root_exposure(**frames(moves=moves))


def test_move_operation_order_refuses_out_of_order_or_duplicated_ordinals():
    for rows in (list(reversed(move_pair(0))), [move_pair(0)[0], move_pair(0)[0]]):
        with pytest.raises(ValueError, match="operation_ordinal|missing_move_origin"):
            exposure.summarize_kin_root_exposure(**frames(moves=rows))


def test_input_row_limit_precedes_any_row_access():
    inputs = frames()
    inputs["decision_rows"] = [None] * (exposure.MAX_ROWS + 1)
    with pytest.raises(ValueError, match="input_row_limit"):
        exposure.summarize_kin_root_exposure(**inputs)


def test_input_byte_limit_is_shared_across_all_records(monkeypatch):
    inputs = frames()
    headers = sum(len((json.dumps(inputs[name], sort_keys=True, separators=(",", ":")) + "\n").encode())
                  for name in ("decision_header", "move_header"))
    monkeypatch.setattr(exposure, "MAX_INPUT_RECORD_BYTES", headers)
    with pytest.raises(ValueError, match="input_byte_limit"):
        exposure.summarize_kin_root_exposure(**inputs)


def test_report_has_fixed_aggregate_size_and_excludes_input_row_arrays():
    result = exposure.summarize_kin_root_exposure(**frames())
    assert len(json.dumps(result, sort_keys=True, allow_nan=False).encode()) < exposure.MAX_REPORT_BYTES
    assert not any(isinstance(value, list) for value in result.values())


def test_model_constants_match_the_native_arithmetic_source():
    root = Path(__file__).resolve().parents[1] / "chronicler-agents/src"
    mobility = (root / "migration_drivers.rs").read_text()
    agent = (root / "agent.rs").read_text()
    pairs = [("roots_free_age", "ROOTS_FREE_AGE", mobility),
        ("roots_per_year", "ROOTS_PER_YEAR", mobility), ("roots_married", "ROOTS_MARRIED", mobility),
        ("roots_per_home_bond", "ROOTS_PER_HOME_BOND", mobility),
        ("roots_home_bond_cap", "ROOTS_HOME_BOND_CAP", mobility),
        ("decision_temperature", "DECISION_TEMPERATURE", agent)]
    for key, name, source in pairs:
        found = re.search(r"pub const " + name + r": (?:f32|u16) = ([0-9.]+);", source)
        assert found is not None and float(found.group(1)) == exposure.MODEL_ARITHMETIC[key]


@pytest.mark.parametrize("personal,spouse,amplifies", [(0.0, .005, True),
    (.001, .001, True), (.005, .005, False), (.01, .01, False),
    (0.0, 0.0, False), (.005, 0.0, False)])
def test_low_and_zero_wealth_source_branches_preserve_recorded_factor_domain(personal, spouse, amplifies):
    # Source-arithmetic synthetic frame, never a compiled-capture attestation.
    personal, spouse = f32(personal), f32(spouse)
    effective = f32(personal + spouse)
    applied = effective > personal
    factor = f32(.88 * (1 / (f32(effective / max(personal, f32(.01))) ** 1.2))) if applied else 1.0
    row = decision(personal_wealth_bits=bits(personal), effective_wealth_bits=bits(effective),
        wealth_multiplier_applied=applied, wealth_factor_bits=bits(factor),
        migration_post_wealth_bits=bits(f32(f32(.54) * factor) if applied else f32(.54)))
    result = exposure.summarize_kin_root_exposure(**frames([row]))
    assert (factor > 1) is amplifies
    assert result["decisions"]["wealth_factor_above_one"] == int(amplifies)
    assert result["decisions"]["wealth_amplifies_dose"] == int(amplifies)
    assert result["same_destination_arithmetic"]["post_wealth_migrate_delta_sum"] == pytest.approx(.06 * factor, rel=2e-6, abs=2e-7)
    assert result["twenty_turn_effect_estimate"] is None


def test_negative_recorded_wealth_factor_refuses_even_when_marked_applied():
    row = decision(wealth_multiplier_applied=True, wealth_factor_bits=bits(-.5))
    with pytest.raises(ValueError, match="wealth_factor"):
        exposure.summarize_kin_root_exposure(**frames([row]))


@pytest.mark.parametrize("part", ["decision_header", "move_header", "decision_rows", "candidate_rows", "move_rows"])
def test_str_subclass_wire_field_names_refuse(part):
    class Alias(str):
        pass
    inputs = frames(moves=move_pair(0))
    row = inputs[part] if part.endswith("header") else inputs[part][0]
    key = next(iter(row))
    value = row.pop(key)
    row[Alias(key)] = value
    with pytest.raises(ValueError, match="field_name_type"):
        exposure.summarize_kin_root_exposure(**inputs)


def test_key_equality_callbacks_are_not_invoked_before_alias_refusal():
    comparisons = []
    class Alias(str):
        __hash__ = str.__hash__
        def __eq__(self, other):
            comparisons.append(other)
            return super().__eq__(other)
    inputs = frames()
    row = inputs["decision_rows"][0]
    value = row.pop("agent_id")
    row[Alias("agent_id")] = value
    comparisons.clear()
    with pytest.raises(ValueError, match="field_name_type"):
        exposure.summarize_kin_root_exposure(**inputs)
    assert comparisons == []


def test_applied_move_cannot_borrow_an_origin_from_another_bucket():
    moves = move_pair(0)
    moves[-1]["bucket"] = 1
    with pytest.raises(ValueError, match="move_origin_join"):
        exposure.summarize_kin_root_exposure(**frames(moves=moves))


@pytest.mark.parametrize("change", ["invalid_known_role", "valid_missing_ordinal",
    "unknown_with_valid_origin", "invalid_with_ordinal"])
def test_partial_capture_does_not_override_applied_origin_flags(change):
    moves = move_pair(0)
    applied = moves[-1]
    if change == "invalid_known_role": applied["origin_valid"] = False
    elif change == "valid_missing_ordinal": applied["origin_operation_ordinal"] = None
    elif change == "unknown_with_valid_origin": applied["role"] = 255
    else: applied.update(origin_valid=False, role=255)
    inputs = frames(moves=moves)
    inputs["move_header"].update(applied_move_provenance_complete=False, missing_applied_origins=1)
    with pytest.raises(ValueError, match="missing_move_origin"):
        exposure.summarize_kin_root_exposure(**inputs)


def test_explicit_selection_cannot_retain_more_living_agents_than_requested():
    inputs = frames()
    for header in ("decision_header", "move_header"):
        inputs[header].update(selection_is_explicit=True, selected_ids_requested=0)
    with pytest.raises(ValueError, match="selected_population_count"):
        exposure.summarize_kin_root_exposure(**inputs)


@pytest.mark.parametrize("kind", ["trip", "evaluated", "displaced", "mobility"])
def test_retained_decision_categories_cannot_exceed_global_counters(kind):
    if kind == "trip":
        row = decision(status=1, mobility_eligible=False, roots_bits=0, home_bonds_bits=0)
        inputs = frames([row], [])
        inputs["decision_header"].update(trip_skipped_all=0, evaluated_all=1)
    elif kind == "displaced":
        row = decision(displacement=1, selected_target=0, mobility_eligible=False, roots_bits=0, home_bonds_bits=0)
        inputs = frames([row], [])
        inputs["decision_header"]["displaced_all"] = 0
    else:
        inputs = frames()
        inputs["decision_header"]["mobility_eligible_all"] = 0
        if kind == "evaluated":
            inputs["decision_header"].update(evaluated_all=0, trip_skipped_all=1)
    with pytest.raises(ValueError, match="retained_decision_counts"):
        exposure.summarize_kin_root_exposure(**inputs)


def test_complete_unselected_capture_must_reconcile_global_eligibility():
    row = decision(mobility_eligible=False, roots_bits=0, home_bonds_bits=0,
        voluntary_pull_bits=0, migration_post_pull_bits=bits(.1), migration_post_wealth_bits=bits(.1))
    target = candidate(mobility_eligible=False, roots_bits=0, gross_frontier_bits=0,
        net_frontier_bits=0, post_roots_pull_bits=0, applied_pull_bits=0)
    inputs = frames([row], [target])
    inputs["decision_header"]["mobility_eligible_all"] = 1
    with pytest.raises(ValueError, match="complete_decision_counts"):
        exposure.summarize_kin_root_exposure(**inputs)
