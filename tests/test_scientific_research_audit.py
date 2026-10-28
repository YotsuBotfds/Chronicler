"""Bounded reader fixtures, not scheduler or information-efficacy experiments."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from chronicler.expansion_audit import Limits, audit_bundle, render_markdown
from chronicler.historical_context import AsOf
from chronicler.scientific_research_audit import research_agenda_identity


@pytest.fixture
def bundle():
    # Literal producer output from one mechanical source-0 tick, two academies.
    return json.loads((Path(__file__).parent / "fixtures/scientific_research/source0.json").read_text())


def section(bundle):
    return bundle["history"][-1]["scientific_claims"]


def agenda(bundle):
    return section(bundle)["research_agendas"]


def codes(report):
    return {row["code"] for row in report["findings"]}


def later(bundle, source, *, append=False):
    row = deepcopy(bundle["history"][-1])
    row["turn"] = source + 1
    row["scientific_claims"]["source_turn"] = source
    bundle["world_state"]["turn"] = source + 1
    if append:
        bundle["history"].append(row)
    else:
        bundle["history"] = [row]
    return row["scientific_claims"]


def pause(state):
    raw = state["research_agendas"]
    raw["enabled"] = False
    raw["current_cycle_id"] = None
    raw["cycles"][0].update(closed_turn=state["source_turn"], close_reason="research_paused")
    raw["capacity"]["trials"]["reserved"] = 0
    raw["capacity"]["receipts"]["reserved"] = 4  # Two retained running trials, two seats.
    raw["capacity"]["messages"]["reserved"] = 4


def resolution(bundle, *, tid=0, cid=0, funded=0, parent=-1, seat=0):
    state = section(bundle)
    source = state["source_turn"]
    context = deepcopy(state["propositions"][cid]["context"])
    funded_id = f"{funded}:scientific_trial_funded:{tid}"
    resolved_id = f"{source}:scientific_trial_completed:{tid}"
    if not any(e["event_id"] == funded_id for e in bundle["events_timeline"]):
        bundle["events_timeline"].append(dict(turn=funded, event_type="scientific_trial_funded", event_id=funded_id,
            causes=[state["propositions"][cid]["event_id"], "0:scientific_research_agenda_opened:0"]))
    bundle["events_timeline"].append(dict(turn=source, event_type="scientific_trial_completed", event_id=resolved_id, causes=[funded_id]))
    state["completed"] = 1
    state["trials_resolved"] = [dict(id=tid, claim=cid, seat=seat, payer=0, funded_turn=funded,
        completion_turn=funded + 1, resolved_turn=source, cost=2, parent=parent,
        inputs={"turn": funded, "context": context}, control_output=10., treatment_output=10.5,
        observed_control=10., observed_treatment=10.5, informative=True, supports=True,
        status="completed", source_data="reader-fixture", dependence_group="reader-group",
        funded_event_id=funded_id, event_id=resolved_id)]


def test_literal_producer_summary_has_bounded_capacity_without_invented_archives(bundle):
    before = deepcopy(bundle)
    report = audit_bundle(bundle)
    assert report["finding_counts"] == {"error": 0, "warning": 0}
    assert report["scan_complete"] and bundle == before
    row = report["observed_mechanisms"]["scientific_claims"]
    finite = row["research_agendas"]
    assert finite["recorded_turns"] == finite["enabled_turns"] == 1
    assert finite["latest_capacity"]["trials"] == {"used": 2, "reserved": 2, "limit": 40}
    assert row["resolved_trial_receipts"] == 0
    assert finite["historical_trial_and_receipt_export_completeness"] == "not_inferred"
    assert report["verified_checks"]["scientific_claims.research_agendas.full_historical_trial_and_receipt_bodies"]["unavailable"] == 1
    assert finite["cycle_details"][0]["funding_deadline"] == 23  # Future plans are legitimate.


@pytest.mark.parametrize("kind", ["null", "schema", "rule", "activation", "opening", "closure", "blocked"])
def test_present_unknown_or_future_actual_metadata_fails_closed_and_redacts(bundle, kind):
    raw = agenda(bundle)
    if kind == "null":
        section(bundle)["research_agendas"] = None
    elif kind == "schema":
        raw["schema_version"] = 2
    elif kind == "rule":
        raw["rule"] = "PRIVATE_FUTURE_RULE"
    elif kind == "activation":
        raw["enabled_turn"] = 9
    elif kind == "opening":
        raw["cycles"][0]["opened_turn"] = 9
    elif kind == "closure":
        raw["cycles"][0].update(closed_turn=9, close_reason="PRIVATE_FUTURE_CLOSE")
    else:
        raw.update(blocked_turn=9, blocked_reason="PRIVATE_FUTURE_BLOCK")
    if isinstance(raw, dict):
        raw["cycles"][0]["announcement_event_id"] = "PRIVATE_FUTURE_BODY"
    report = audit_bundle(bundle)
    assert "unsupported_research_agenda_metadata" in codes(report)
    assert not report["scan_complete"]
    assert "PRIVATE_FUTURE" not in json.dumps(report) + render_markdown(report)
    assert research_agenda_identity(section(bundle), 0) == {
        "mode": "unknown", "enabled": None, "enabled_turn": None, "cycle_lineage": None}


def test_absence_remains_legacy_and_pure_identity_copies_lists(bundle):
    state = section(bundle)
    original = deepcopy(state)
    result = research_agenda_identity(state, 0)
    assert result["mode"] == "finite-retained-v1"
    result["cycle_lineage"][0]["participants"].append(99)
    assert state == original
    del state["research_agendas"]
    assert research_agenda_identity(state, 0)["mode"] == "legacy"
    assert "research_agendas" not in audit_bundle(bundle)["observed_mechanisms"]["scientific_claims"]
    assert research_agenda_identity(None, 0)["mode"] == "unknown"


@pytest.mark.parametrize("change,code", [
    ("capacity", "research_capacity_overcommitted"),
    ("used", "research_retained_count_mismatch"),
    ("archive", "research_retained_count_mismatch"),
    ("reservation", "research_reservation_mismatch"),
    ("messages", "research_reservation_mismatch"),
    ("membership", "research_trial_membership_mismatch"),
    ("topic", "research_cycle_topic_mismatch"),
    ("opening_plan", "research_opening_plan_mismatch"),
])
def test_capacity_membership_and_observable_reservation_conservation(bundle, change, code):
    raw = agenda(bundle)
    if change == "capacity": raw["capacity"]["receipts"]["reserved"] = 801
    elif change == "used": raw["capacity"]["topics"]["used"] = 3
    elif change == "archive": raw["archive"]["retained_trials"] = 3
    elif change == "reservation": raw["capacity"]["trials"]["reserved"] = 1
    elif change == "messages": raw["capacity"]["messages"]["reserved"] = 11
    elif change == "membership": raw["cycles"][0]["trials"] = [0]
    elif change == "topic": section(bundle)["propositions"][1]["context"]["soil_band"] = 1
    else: raw["next_open_turn"] = 24
    assert code in codes(audit_bundle(bundle))


def test_opening_membership_is_immutable_only_inside_continuous_recording(bundle):
    current = later(bundle, 1, append=True)
    current["research_agendas"]["cycles"][0]["participants"] = [0, 2]
    assert "changed_research_opening" in codes(audit_bundle(bundle))
    bundle["history"][-1]["turn"] = 6
    current["source_turn"] = 5
    bundle["world_state"]["turn"] = 6
    assert "changed_research_opening" not in codes(audit_bundle(bundle))


def test_canonical_metric_identity_cannot_change_in_continuous_finite_mode(bundle):
    current = later(bundle, 1, append=True)
    current["propositions"][0]["comparator"] = 4.
    assert "changed_canonical_research_topic" in codes(audit_bundle(bundle))


def test_legacy_adoption_has_unknown_original_roster_and_no_invented_deadlines(bundle):
    current = later(bundle, 1)
    raw = current["research_agendas"]
    raw.update(enabled_turn=1, current_cycle_id=None, next_open_turn=26)
    raw["cycles"][0].update(legacy_adopted=True, opening_roster_complete=False, opened_turn=None,
        closed_turn=1, close_reason="legacy funding closed prospectively at activation", announcement_event_id="",
        original_deadline=None, funding_deadline=None, next_open_not_before=None,
        opening_roster_scope="observed_at_legacy_activation")
    raw["capacity"]["trials"]["reserved"] = 0
    report = audit_bundle(bundle)
    assert not report["finding_counts"]["error"]
    assert report["verified_checks"]["scientific_claims.research_agendas.legacy_opening_roster_and_windows"]["unavailable"] == 1
    assert report["observed_mechanisms"]["scientific_claims"]["research_agendas"]["cycle_details"][0]["opened_turn"] is None
    raw["cycles"][0]["funding_deadline"] = 23
    assert "unsupported_research_agenda_metadata" in codes(audit_bundle(bundle))


def test_paused_plan_permits_actual_old_paid_work_resolution(bundle):
    current = later(bundle, 1, append=True)
    pause(current)
    resolution(bundle)
    report = audit_bundle(bundle)
    assert not report["finding_counts"]["error"]
    assert report["observed_mechanisms"]["scientific_claims"]["research_agendas"]["paused_turns"] == 1
    assert report["observed_mechanisms"]["scientific_claims"]["resolved_trial_receipts"] == 1


def test_paused_plan_rejects_new_funding_without_erasing_archive(bundle):
    pause(later(bundle, 1))
    bundle["events_timeline"].append(dict(turn=1,event_type="scientific_trial_funded",event_id="1:scientific_trial_funded:2"))
    report = audit_bundle(bundle)
    assert "funding_while_research_paused" in codes(report)
    assert report["observed_mechanisms"]["scientific_claims"]["research_agendas"]["latest_retained_archive_counts"]["retained_trials"] == 2


def paid_use(bundle):
    state = later(bundle, 6)
    pause(state)
    state["effort_spent"] = 1
    state["allocations"] = [dict(seat=0, recipe=recipe, claim_id=cid, share=.5,
        confidence=.8 if cid == 0 else .2, paid=int(cid == 0), event_id="")
        for cid, recipe in enumerate(("irrigation", "masonry"))]
    return state


def test_paid_use_joins_actual_phase4_claim_not_phase10_belief_or_recipe(bundle):
    paid_use(bundle)
    report = audit_bundle(bundle)
    assert not report["finding_counts"]["error"]
    rows = report["observed_mechanisms"]["scientific_claims"]["research_agendas"]["paid_allocation_details"]
    assert [r["claim_id"] for r in rows] == [0, 1]
    assert [r["phase4_confidence"] for r in rows] == [.8, .2]
    assert all(r["funded_topic_context"]["soil_band"] == 3 for r in rows)
    assert all(r["confidence"] == .5 for r in section(bundle)["beliefs"])


@pytest.mark.parametrize("missing", [None, 19])
def test_recipe_match_never_supplies_missing_actual_paid_topic(bundle, missing):
    state = paid_use(bundle)
    state["allocations"][0]["claim_id"] = missing
    report = audit_bundle(bundle)
    assert "unknown_paid_research_topic" in codes(report)
    rows = report["observed_mechanisms"]["scientific_claims"]["research_agendas"]["paid_allocation_details"]
    assert [row["claim_id"] for row in rows] == [1]


def test_actual_original_outside_inclusive_window_is_rejected(bundle):
    later(bundle, 13)
    resolution(bundle, funded=12)
    assert "research_trial_window_or_membership" in codes(audit_bundle(bundle))


def test_missing_old_parent_resolution_stays_unknown_despite_complete_retained_ids(bundle):
    later(bundle, 13)
    resolution(bundle, tid=1, cid=0, funded=12, parent=0, seat=1)
    report = audit_bundle(bundle)
    assert not report["finding_counts"]["error"]
    assert report["verified_checks"]["scientific_claims.research_agendas.replication_parent_body"]["unavailable"] == 1
    assert report["observed_mechanisms"]["scientific_claims"]["resolved_trial_receipts"] == 1
    assert report["observed_mechanisms"]["scientific_claims"]["research_agendas"]["historical_trial_and_receipt_export_completeness"] == "not_inferred"


def test_rows_details_and_asof_use_shared_bounds_and_no_final_world_fallback(bundle):
    later(bundle, 1, append=True)
    report = audit_bundle(bundle, limits=Limits(max_details=1))
    assert len(report["observed_mechanisms"]["scientific_claims"]["research_agendas"]["cycle_details"]) == 1
    assert report["details_omitted"]["agenda_cycle_details"] == 1
    bounded = audit_bundle(bundle, limits=Limits(max_rows=1))
    assert not bounded["scan_complete"] and "max_rows" in bounded["truncated_by"]
    before = audit_bundle(bundle, as_of=AsOf.before(0))
    assert before["observed_mechanisms"]["scientific_claims"]["recorded_turns"] == 0
    bundle["world_state"]["scientific_claims"] = deepcopy(section(bundle))
    bundle["history"] = [{"turn":2}]
    assert "research_agendas" not in audit_bundle(bundle)["observed_mechanisms"]["scientific_claims"]


def test_retained_plan_cannot_silently_disappear_on_the_next_recorded_turn(bundle):
    state = later(bundle, 1, append=True)
    del state["research_agendas"]
    assert "research_agenda_metadata_disappeared" in codes(audit_bundle(bundle))


@pytest.mark.parametrize("present", [True, False])
def test_bool_source_clock_is_never_a_dated_identity(bundle, present):
    state = section(bundle)
    state["source_turn"] = False
    if not present:
        state.pop("research_agendas")
    assert research_agenda_identity(state, 0)["mode"] == "unknown"


def test_closed_funding_membership_cannot_grow_in_continuous_coverage(bundle):
    pause(later(bundle, 1, append=True))
    state = later(bundle, 2, append=True)
    state["research_agendas"]["cycles"][0]["trials"].append(2)
    state["trials"] = 3
    state["trial_spent"] = 6
    state["research_agendas"]["capacity"]["trials"]["used"] = 3
    state["research_agendas"]["archive"]["retained_trials"] = 3
    assert "changed_research_closure" in codes(audit_bundle(bundle))


def test_exported_funding_after_actual_closure_is_rejected_even_inside_original_window(bundle):
    state = later(bundle, 3)
    pause(state)
    state["research_agendas"]["cycles"][0]["closed_turn"] = 1
    resolution(bundle, funded=2)
    assert "research_trial_window_or_membership" in codes(audit_bundle(bundle))


def test_late_complete_cycles_cannot_have_overlapping_actual_funding_history(bundle):
    state = later(bundle, 30)
    raw = state["research_agendas"]
    old = raw["cycles"][0]
    old.update(closed_turn=30, close_reason="reader_late_close")
    new = deepcopy(old)
    new.update(id=1, opened_turn=25, closed_turn=None, close_reason="", trials=[],
        announcement_event_id="25:scientific_research_agenda_opened:0",
        original_deadline=36, funding_deadline=48, next_open_not_before=50)
    raw["cycles"].append(new)
    raw.update(current_cycle_id=1, next_open_turn=50)
    raw["capacity"]["cycles"]["used"] = 2
    raw["capacity"]["trials"]["reserved"] = 4
    bundle["events_timeline"].append(dict(turn=25,event_type="scientific_research_agenda_opened",
        event_id=new["announcement_event_id"]))
    assert "early_research_opening" in codes(audit_bundle(bundle))


@pytest.mark.parametrize("key,value", [
    ("metric", "another_metric"), ("comparator", 1.), ("intervention", 2.),
    ("horizon", 2), ("threshold", .05), ("crew", 5),
])
def test_finite_rule_does_not_silently_qualify_different_measurement_protocol(bundle, key, value):
    row = section(bundle)["propositions"][0]
    if key == "crew": row["context"][key] = value
    else: row[key] = value
    assert "unsupported_canonical_research_protocol" in codes(audit_bundle(bundle))


def test_future_appended_agenda_body_cannot_change_past_audit(bundle):
    before = audit_bundle(bundle, as_of=AsOf.after(0))
    state = later(bundle, 2, append=True)
    state["research_agendas"].update(enabled_turn=999, blocked_reason="PRIVATE_FUTURE_BODY")
    state["research_agendas"]["cycles"][0]["participants"] = [98, 99]
    assert audit_bundle(bundle, as_of=AsOf.after(0)) == before


def test_recorded_paid_use_outside_its_actual_calendar_is_rejected(bundle):
    state = paid_use(bundle)
    state["source_turn"] = 7
    bundle["history"][0]["turn"] = bundle["world_state"]["turn"] = 8
    assert "research_paid_use_calendar_mismatch" in codes(audit_bundle(bundle))


def test_precise_same_source_legacy_paid_activation_is_unknown_not_corrupt(bundle):
    state = paid_use(bundle)
    raw = state["research_agendas"]
    raw.update(enabled=True, enabled_turn=6, next_open_turn=31)
    raw["cycles"][0].update(legacy_adopted=True, opening_roster_complete=False,
        announcement_event_id="", original_deadline=None, funding_deadline=None,
        next_open_not_before=None, opening_roster_scope="observed_at_legacy_activation")
    for row in state["allocations"]: row.pop("claim_id")
    report = audit_bundle(bundle)
    assert not report["finding_counts"]["error"]
    observed = report["observed_mechanisms"]["scientific_claims"]["research_agendas"]
    assert observed["paid_topic_attribution_complete"] is False
    assert observed["paid_allocation_details"] == []
    assert report["verified_checks"]["scientific_claims.research_agendas.actual_paid_canonical_topic"] == {
        "verified":0, "failed":0, "unavailable":2}
    # A later source with the same unknown rows is not the activation exception.
    later(bundle, 12)
    assert "unknown_paid_research_topic" in codes(audit_bundle(bundle))


def test_retained_rosters_cannot_name_more_institutions_than_lifetime_seat_count(bundle):
    agenda(bundle)["cycles"][0]["participants"].append(2)
    assert "research_retained_topic_or_roster_mismatch" in codes(audit_bundle(bundle))
