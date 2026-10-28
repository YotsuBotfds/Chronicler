"""Read-only expansion audits distinguish arithmetic, observation and efficacy."""
from __future__ import annotations
import copy
import hashlib
import json
import pytest
from chronicler.bundle_codec import dumps_bundle
from chronicler.expansion_audit import AuditError, Limits, audit_bundle, audit_path, main, render_markdown
from chronicler.historical_context import AsOf


def event(turn, kind, causes=()):
    return {"turn": turn, "event_type": kind, "event_id": f"{turn}:{kind}:0",
            "region": "Here", "actors": ["A"], "causes": list(causes)}


def health(turn):
    values = dict(episodes=6, new_injuries=1, recoveries=1, impaired_work=2.5,
                  care_work=.4, care_recipients=2, recovery_progress=3., cared_recovery_progress=1.)
    return {"source_turn": turn, "units": "worker-turns", **values,
            "regions": [{"region": 0, "region_name": "Here", "civ_name": "Then-host", **values}]}


def forecast(turn):
    resolved, delivered = turn >= 12, turn >= 7
    return dict(id="harvest:0:1:0", issued_turn=5, delivery_turn=7, expires_turn=11,
        target_start=9, target_end=11, source_region=1, source_region_name="There",
        recipient_region=0, recipient_region_name="Here", owner=0, owner_name="Then-host",
        probability=.75, confidence=.8, predicted_ratio=.4,
        status="resolved" if resolved else "delivered" if delivered else "pending",
        delivered_turn=7 if delivered else None, resolved_turn=12 if resolved else None,
        evaluation_sum=1.2 if resolved else 0., evaluation_count=3 if resolved else 0,
        observed_ratio=.4 if resolved else None, outcome_shortfall=True if resolved else None,
        brier=.0625 if resolved else None, issued_event_id="5:harvest_forecast_issued:0",
        delivered_event_id="7:harvest_forecast_delivered:0" if delivered else "")


def gathering(turn):
    held = turn >= 8
    return {"source_turn": turn, "schedules": [{"gathering_id": "harvest:0", "region": 0,
                "last_turn": 8 if held else None, "next_turn": 20 if held else 8}],
        "outcomes": [dict(gathering_id="harvest:0", turn=8, region=0, region_name="Here",
            host=0, host_name="Then-host", faith=1, purpose="harvest", status="held",
            attendee_ids=[1, 4, 9], arrivals=[[1, 1]], food=.15, funds=2, bond_ops=1,
            contact_units=1, grain_before=10, grain_after=9.85, funds_before=100, funds_after=98)] if turn == 8 else [],
        "counters": dict(scheduled=int(held), held=int(held), cancelled=0, attendees=3 if held else 0,
            food=.15 if held else 0, funds=2 if held else 0, contact_units=int(held), bond_ops=int(held))}


@pytest.fixture
def bundle():
    events = [event(5, "harvest_forecast_issued"),
        event(7, "harvest_forecast_delivered", ["5:harvest_forecast_issued:0"]),
        event(7, "harvest_preparedness", ["7:harvest_forecast_delivered:0"]),
        event(8, "harvest_preparedness", ["7:harvest_forecast_delivered:0"]),
        event(12, "harvest_forecast_resolved", ["5:harvest_forecast_issued:0", "7:harvest_forecast_delivered:0"])]
    history = []
    for turn in range(5, 13):
        prep = [dict(forecast_id="harvest:0:1:0", region=0, region_name="Here", owner=0,
            owner_name="Then-host", base_target=10, extra_target=5,
            bought_during_warning=12, paid_during_warning=4)] if turn in (7, 8) else []
        history.append({"turn": turn + 1, "health_care": health(turn), "ritual_gatherings": gathering(turn),
            "harvest_forecasts": {"source_turn": turn, "reports": [forecast(turn)] if turn < 12 else [],
                "outcomes": [forecast(turn)] if turn >= 12 else [], "preparedness": prep,
                "counters": dict(issued=1, delivered=int(turn >= 7), resolved=int(turn >= 12),
                    bought_during_warning=24 if turn >= 8 else 12 if turn == 7 else 0,
                    paid_during_warning=8 if turn >= 8 else 4 if turn == 7 else 0)},
            "contact": {"inflow": {"pilgrims": int(turn == 8)}},
            "grain_reserves": {"source_turn": turn,
                "flows": [dict(kind="bought", region=0, buyer=0, amount=12, cost=4)] if prep else []}})
    return {"metadata": {"seed": 42, "bundle_version": 6}, "world_state": {"turn": 13},
            "history": history, "events_timeline": events}


def codes(result):
    return {f["code"] for f in result["findings"]}


def test_linked_receipts_verify_arithmetic_and_keep_observation_separate(bundle):
    result = audit_bundle(bundle)
    assert result["status"] == "no_violations_in_recorded_coverage"
    assert result["finding_counts"] == {"error": 0, "warning": 0}
    assert result["scan_complete"]
    h = result["observed_mechanisms"]["health_care"]
    assert h["episode_turns"] == 48 and h["new_injuries"] == 8 and h["censored_episodes"] is None
    f = result["observed_mechanisms"]["harvest_forecasts"]
    assert f["unique_report_ids"] == f["delivered_report_ids"] == f["closed_report_ids"] == f["scored_report_ids"] == 1
    chain = f["report_chains"][0]
    assert chain["issued_event_id"] == "5:harvest_forecast_issued:0"
    assert chain["delivered_event_id"] == "7:harvest_forecast_delivered:0"
    assert chain["preparation_event_ids"] == ["7:harvest_preparedness:0", "8:harvest_preparedness:0"]
    assert chain["resolution_event_ids"] == ["12:harvest_forecast_resolved:0"]
    assert (chain["preparation_receipts"], chain["grain_bought"], chain["funds_paid"]) == (2, 24, 8)
    g = result["observed_mechanisms"]["ritual_gatherings"]
    assert (g["occurrences"], g["held"], g["food"], g["funds"], g["selected_attendances"]) == (1, 1, .15, 2, 3)
    assert result["verified_checks"]["harvest_forecasts.brier_arithmetic"]["verified"] == 1
    assert result["coverage"]["systems"]["health_care"]["unknown_completed_turn_spans"] == [[0, 4]]
    assert result["requires_interventions"]


def test_shared_v6_decoder_and_read_only_legacy(bundle):
    before = copy.deepcopy(bundle)
    assert audit_bundle(json.loads(dumps_bundle(bundle))) == audit_bundle(bundle)
    assert bundle == before


def test_start_end_asof_and_legitimate_future_plans(bundle):
    before = audit_bundle(bundle, as_of=AsOf.before(7))
    after = audit_bundle(bundle, as_of=AsOf.after(7))
    assert before["observed_mechanisms"]["harvest_forecasts"]["delivered_report_ids"] == 0
    assert after["observed_mechanisms"]["harvest_forecasts"]["delivered_report_ids"] == 1
    assert not before["findings"] and not after["findings"]
    assert before["observed_mechanisms"]["harvest_forecasts"]["report_chains"][0]["brier"] is None
    assert audit_bundle(bundle, as_of=AsOf.before(0))["status"] == "no_recorded_expansion_history"


def test_old_bundles_never_use_final_states_to_fill_history():
    result = audit_bundle({"world_state": {"turn": 100, "health_care": {"episodes": 999},
        "ritual_gatherings": gathering(8)}, "history": [{"turn": 1}, {"turn": 100}]})
    assert result["status"] == "no_recorded_expansion_history"
    assert result["observed_mechanisms"]["ritual_gatherings"]["occurrences"] == 0
    assert result["coverage"]["systems"]["health_care"]["unknown_completed_turn_spans"] == [[0, 99]]


@pytest.mark.parametrize("system", ["health_care", "harvest_forecasts", "ritual_gatherings"])
def test_section_stamp_rejects_body_and_aggregate(bundle, system):
    bundle["history"] = [bundle["history"][0]]
    bundle["history"][0][system]["source_turn"] = 99
    result = audit_bundle(bundle)
    assert "section_source_mismatch" in codes(result)
    assert result["coverage"]["systems"][system]["recorded_snapshots"] == 0


@pytest.mark.parametrize("field,value,code", [("episodes", -1, "negative_quantity"),
    ("care_work", float("nan"), "invalid_quantity"), ("care_recipients", .5, "fractional_count"),
    ("care_work", 99, "regional_total_mismatch")])
def test_health_negative_nonfinite_fractional_and_totals(bundle, field, value, code):
    bundle["history"][0]["health_care"][field] = value
    result = audit_bundle(bundle)
    assert code in codes(result) and result["status"] == "issues_found"
    json.dumps(result, allow_nan=False)


def test_censored_episodes_are_separate_from_retirements(bundle):
    for snapshot in bundle["history"]:
        state = snapshot["health_care"]
        state["censored_episodes"] = state["regions"][0]["censored_episodes"] = 2
    h = audit_bundle(bundle)["observed_mechanisms"]["health_care"]
    assert h["censored_episodes"] == 16 and h["episode_retirements"] == 8


@pytest.mark.parametrize("change,code", [("negative", "negative_quantity"), ("balance", "expense_balance_mismatch"),
    ("attendance", "invalid_attendance"), ("empty", "cost_or_attendance_missing"),
    ("contact", "bounded_effect_exceeded"), ("inflow", "contact_inflow_mismatch"),
    ("arrival", "invalid_arrival_receipt"), ("cancel", "improper_cancellation")])
def test_gathering_invariants(bundle, change, code):
    snapshot = bundle["history"][3]
    row = snapshot["ritual_gatherings"]["outcomes"][0]
    if change == "negative": row["food"] = -1
    elif change == "balance": row["grain_after"] = 5
    elif change == "attendance": row["attendee_ids"] = [1, 1, 9]
    elif change == "empty": row["attendee_ids"] = []
    elif change == "contact": row["contact_units"] = 9
    elif change == "inflow": snapshot["contact"]["inflow"]["pilgrims"] = 0
    elif change == "arrival": row["arrivals"] = [[5000, 1]]
    else: row["status"] = "cancelled"
    assert code in codes(audit_bundle(bundle))


def test_replayed_occurrence_not_double_counted(bundle):
    bundle["history"][4]["ritual_gatherings"]["outcomes"] = copy.deepcopy(bundle["history"][3]["ritual_gatherings"]["outcomes"])
    result = audit_bundle(bundle)
    assert "replayed_gathering_receipt" in codes(result)
    assert result["observed_mechanisms"]["ritual_gatherings"]["occurrences"] == 1


def test_duplicate_and_conflicting_snapshots(bundle):
    bundle["history"].append(copy.deepcopy(bundle["history"][3]))
    result = audit_bundle(bundle)
    assert "duplicate_snapshot" in codes(result) and result["observed_mechanisms"]["ritual_gatherings"]["occurrences"] == 1
    bundle["history"][-1]["ritual_gatherings"]["outcomes"][0]["food"] = 99
    result = audit_bundle(bundle)
    assert "conflicting_snapshot" in codes(result) and result["observed_mechanisms"]["ritual_gatherings"]["occurrences"] == 0


def test_repeated_reports_and_equal_distinct_turn_purchases_are_legitimate(bundle):
    result = audit_bundle(bundle)
    assert not result["findings"] and result["observed_mechanisms"]["harvest_forecasts"]["preparation_receipts"] == 2
    bundle["history"][2]["harvest_forecasts"]["preparedness"] *= 2
    result = audit_bundle(bundle)
    assert "duplicate_preparation_receipt" in codes(result)
    assert result["observed_mechanisms"]["harvest_forecasts"]["preparation_receipts"] == 2


@pytest.mark.parametrize("change,code", [("issue", "future_or_undated_report"),
    ("delivery", "future_or_inverted_delivery"), ("resolution", "future_or_inverted_resolution"),
    ("evaluation", "future_evaluation_evidence"), ("outcome", "premature_outcome_evidence"),
    ("gathering", "future_or_undated_gathering"), ("schedule", "future_schedule_outcome"),
    ("payment", "preparation_date_mismatch")])
def test_future_actual_evidence_withheld(bundle, change, code):
    if change == "gathering":
        bundle["history"][3]["ritual_gatherings"]["outcomes"][0].update(turn=999, host_name="SECRET-FUTURE", food=1234567)
    elif change == "schedule":
        bundle["history"][0]["ritual_gatherings"]["schedules"][0]["last_turn"] = 999
    elif change == "payment":
        bundle["history"][2]["harvest_forecasts"]["preparedness"][0].update(paid_turn=999, paid_during_warning=1234567)
    else:
        row = bundle["history"][0]["harvest_forecasts"]["reports"][0]
        if change == "issue": row.update(issued_turn=999, owner_name="SECRET-FUTURE", id="SECRET-FUTURE")
        elif change == "delivery": row.update(delivered_turn=999, status="delivered")
        elif change == "resolution": row.update(resolved_turn=999, status="resolved", brier=1234567)
        elif change == "evaluation": row.update(evaluation_count=3, evaluation_sum=1234567)
        else: row.update(observed_ratio=1234567, brier=1234567)
    result = audit_bundle(bundle, as_of=AsOf.after(8))
    assert code in codes(result)
    for text in (json.dumps(result), render_markdown(result)):
        assert "SECRET-FUTURE" not in text and "1234567" not in text


def test_purchase_flow_and_brier_reconciliation(bundle):
    bundle["history"][2]["grain_reserves"]["flows"][0]["cost"] = 99
    bundle["history"][-1]["harvest_forecasts"]["outcomes"][0]["brier"] = .5
    assert {"purchase_flow_mismatch", "brier_mismatch"}.issubset(codes(audit_bundle(bundle)))


def test_counter_regression_only_in_continuous_recorded_span(bundle):
    bundle["history"][4]["ritual_gatherings"]["counters"]["funds"] = 0
    assert "counter_regression" in codes(audit_bundle(bundle))
    bundle["history"][3].pop("ritual_gatherings")
    assert "counter_regression" not in codes(audit_bundle(bundle))
    assert audit_bundle(bundle)["coverage"]["systems"]["ritual_gatherings"]["unknown_completed_turn_spans"] == [[0, 4], [8, 8]]


def test_event_ids_dangling_ambiguous_future(bundle):
    row = bundle["history"][0]["harvest_forecasts"]["reports"][0]
    row["issued_event_id"] = "missing"
    assert "dangling_event_id" in codes(audit_bundle(bundle))
    bundle["events_timeline"].append(copy.deepcopy(bundle["events_timeline"][0]))
    assert "ambiguous_event_id" in codes(audit_bundle(bundle))
    row["issued_event_id"] = "7:harvest_forecast_delivered:0"
    assert "future_or_undated_event_reference" in codes(audit_bundle(bundle, as_of=AsOf.after(5)))


@pytest.mark.parametrize("limits,limit", [(Limits(max_snapshots=2), "max_snapshots"),
    (Limits(max_rows=1), "max_rows"), (Limits(max_events=1), "max_events")])
def test_bounds_never_claim_complete_pass(bundle, limits, limit):
    for data in (bundle, json.loads(dumps_bundle(bundle))):
        result = audit_bundle(data, limits=limits)
        assert not result["scan_complete"] and limit in result["truncated_by"]
        assert result["status"] != "no_violations_in_recorded_coverage"


def test_finding_limit_preserves_error_count_and_marks_partial(bundle):
    for snapshot in bundle["history"]: snapshot["health_care"]["episodes"] = -1
    result = audit_bundle(bundle, limits=Limits(max_findings=1))
    assert len(result["findings"]) == 1 and result["finding_counts"]["error"] > 1
    assert not result["scan_complete"] and "max_findings" in result["truncated_by"]


def test_same_read_hash_and_parse(bundle, tmp_path, monkeypatch):
    path = tmp_path / "bundle.json"
    raw = dumps_bundle(bundle).encode()
    path.write_bytes(raw)
    import chronicler.expansion_audit as module
    original = module.json.loads
    def replace(data, *args, **kwargs):
        path.write_text("{}")
        return original(data, *args, **kwargs)
    monkeypatch.setattr(module.json, "loads", replace)
    result = audit_path(path)
    assert result["source"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["observed_mechanisms"]["ritual_gatherings"]["held"] == 1


def test_exports_deterministic_escaped_and_source_untouched(bundle, tmp_path, capsys):
    bundle["history"][3]["ritual_gatherings"]["outcomes"][0]["host_name"] = "<img> [link](https://evil) | **markup**"
    path = tmp_path / "bundle.json"
    path.write_text(dumps_bundle(bundle))
    a, b = audit_path(path), audit_path(path)
    assert a == b and render_markdown(a) == render_markdown(b)
    assert "<img" not in render_markdown(a) and "[link](" not in render_markdown(a)
    raw = path.read_bytes()
    assert main([str(path), "--format", "json", "--json", str(tmp_path / "r.json"), "--markdown", str(tmp_path / "r.md")]) == 0
    assert json.loads(capsys.readouterr().out) == a and path.read_bytes() == raw


def test_overwrite_protection_including_hardlinks(bundle, tmp_path, capsys):
    path = tmp_path / "bundle.json"
    path.write_text(dumps_bundle(bundle))
    raw = path.read_bytes()
    linked = tmp_path / "linked.json"
    linked.hardlink_to(path)
    for dest in (path, linked):
        assert main([str(path), "--json", str(dest)]) == 2
        assert "must not overwrite" in capsys.readouterr().err and path.read_bytes() == raw
    out = tmp_path / "same"
    assert main([str(path), "--json", str(out), "--markdown", str(out)]) == 2
    assert "different files" in capsys.readouterr().err


def test_byte_limit_partial_empty_invalid_exit_codes(bundle, tmp_path, capsys):
    path = tmp_path / "bundle.json"
    path.write_text(dumps_bundle(bundle))
    with pytest.raises(AuditError, match="max_file_bytes"): audit_path(path, limits=Limits(max_file_bytes=10))
    assert main([str(path), "--max-snapshots", "1"]) == 3
    capsys.readouterr()
    path.write_text("{}")
    assert main([str(path)]) == 3
    capsys.readouterr()
    path.write_text("[]")
    assert main([str(path)]) == 2 and "JSON object" in capsys.readouterr().err


def test_missing_optional_event_timeline_is_unknown_not_a_dangling_claim(bundle):
    bundle.pop("events_timeline")
    result = audit_bundle(bundle)
    assert "dangling_event_id" not in codes(result)
    assert result["verified_checks"]["harvest_forecasts.event_links"]["unavailable"] > 0


def test_attendee_cannot_be_selected_in_two_simultaneous_local_regions(bundle):
    row = copy.deepcopy(bundle["history"][3]["ritual_gatherings"]["outcomes"][0])
    row.update(gathering_id="harvest:1", region=1, region_name="Another")
    bundle["history"][3]["ritual_gatherings"]["outcomes"].append(row)
    assert "attendee_multiple_regions" in codes(audit_bundle(bundle))


def test_recorded_stable_attendance_and_owner_names_are_exported_not_backfilled(bundle):
    bundle["world_state"]["civilizations"] = [{"name": "SECRET-FINAL-RULER"}]
    result = audit_bundle(bundle)
    row = result["observed_mechanisms"]["ritual_gatherings"]["occurrence_details"][0]
    assert row["attendee_ids"] == [1, 4, 9] and row["host_name"] == "Then-host"
    assert row["arrival_membership_receipts"] == [{"agent_id": 1, "source_region": 1}]
    assert "SECRET-FINAL-RULER" not in json.dumps(result)


def test_zero_pathway_observations_are_descriptive_not_efficacy_findings(bundle):
    for snapshot in bundle["history"]:
        state = snapshot["ritual_gatherings"]
        state["counters"]["contact_units"] = 0
        for row in state["outcomes"]:
            row["contact_units"] = 0
        snapshot["health_care"]["care_work"] = 0
        snapshot["health_care"]["regions"][0]["care_work"] = 0
    result = audit_bundle(bundle)
    assert any("no positive recorded" in s for s in result["descriptive_observations"])
    assert any("zero recorded caregiver" in s for s in result["descriptive_observations"])
    assert not result["finding_counts"]["error"]


def test_planned_fields_can_be_future_while_actuals_cannot(bundle):
    snapshot = bundle["history"][0]
    report = snapshot["harvest_forecasts"]["reports"][0]
    report.update(delivery_turn=100, expires_turn=1000, target_start=200, target_end=202)
    snapshot["ritual_gatherings"]["schedules"][0]["next_turn"] = 10000
    assert not audit_bundle({**bundle, "history": [snapshot]}, as_of=AsOf.after(5))["findings"]


@pytest.mark.parametrize("where", ["outcome_id", "schedule_id", "preparation_id", "table"])
def test_malformed_optional_receipts_diagnose_without_tracebacks(bundle, where):
    if where == "outcome_id": bundle["history"][3]["ritual_gatherings"]["outcomes"][0]["gathering_id"] = []
    elif where == "schedule_id": bundle["history"][0]["ritual_gatherings"]["schedules"][0]["gathering_id"] = []
    elif where == "preparation_id": bundle["history"][2]["harvest_forecasts"]["preparedness"][0]["forecast_id"] = []
    else: bundle["history"][0]["health_care"]["regions"] = "bad"
    assert audit_bundle(bundle)["finding_counts"]["error"] > 0


def test_aggregate_overflow_is_reported_and_json_remains_finite(bundle):
    for snapshot in bundle["history"]:
        snapshot["health_care"]["impaired_work"] = 1e308
        snapshot["health_care"]["regions"][0]["impaired_work"] = 1e308
    result = audit_bundle(bundle)
    assert "aggregate_overflow" in codes(result)
    assert result["observed_mechanisms"]["health_care"]["impaired_worker_turns"] is None
    json.dumps(result, allow_nan=False)


def test_real_shuffled_seed43_negative_warning_increment_is_actionable():
    report = forecast(7)
    report.update(id="harvest:2:0:6", issued_turn=29, delivery_turn=31, delivered_turn=31,
                  expires_turn=35, target_start=33, target_end=35, source_region=0,
                  source_region_name="Verdant Plains", recipient_region=6,
                  recipient_region_name="Stormbreak Cliffs", owner=1, owner_name="Selurian Republic",
                  issued_event_id="", delivered_event_id="")
    prep = dict(forecast_id=report["id"], region=6, owner=1, base_target=4.126938305182808,
                extra_target=-1.126938305182808, bought_during_warning=0, paid_during_warning=0)
    result = audit_bundle({"history": [{"turn": 33, "harvest_forecasts": {
        "source_turn": 32, "reports": [report], "outcomes": [], "preparedness": [prep], "counters": {}}}]})
    finding = next(f for f in result["findings"] if f["code"] == "negative_quantity")
    assert finding["record_id"] == "harvest:2:0:6" and finding["source_turn"] == 32
    assert finding["evidence"]["extra_target"] == -1.126938305182808
    assert result["status"] == "issues_found"
