"""Narration describes dated records without inventing clinical/causal outcomes."""
from __future__ import annotations

import copy

import pytest

from chronicler import narration_context as NC
from chronicler.models import Event, TurnSnapshot
from chronicler.narration_expansion_context import expansion_state_facts
from chronicler.narration_provenance import FactIds


def _snap(**fields):
    return TurnSnapshot(turn=10, civ_stats={}, region_control={}, relationships={}, **fields)


def _event(kind="occupational_injury", region="Here"):
    return Event(turn=9, event_type=kind, actors=["A"], region=region, description="", importance=3)


def _health():
    return {"source_turn": 9, "units": "worker-turns", "regions": [{"region": 0, "region_name": "Here", "civ_name": "A",
             "episodes": 6, "impaired_work": 2.5, "care_work": 0.4, "recoveries": 3,
             "recovery_progress": 2, "cared_recovery_progress": 1}]}


def _gathering(status="held"):
    return {"source_turn": 9, "outcomes": [{"gathering_id": "harvest:0", "turn": 9,
        "region": 0, "region_name": "Here", "host_name": "Then-host", "faith_name": "Then-faith",
        "purpose": "harvest", "status": status, "reason": "occupied" if status == "cancelled" else None,
        "attendee_ids": [] if status == "cancelled" else [1, 4, 9], "food": 0 if status == "cancelled" else 0.15,
        "funds": 0 if status == "cancelled" else 2, "bond_ops": 0 if status == "cancelled" else 1,
        "contact_units": 0}]}


def _forecast(status="delivered"):
    return {"source_turn": 9, "reports": [{"id": "harvest:0:1:0", "recipient_region_name": "Here",
        "source_region_name": "There", "owner_name": "A", "issued_turn": 5,
        "delivered_turn": 7 if status == "delivered" else None, "expires_turn": 11,
        "status": status, "probability": 0.75, "confidence": 0.8, "target_start": 9, "target_end": 11,
        # These partial in-progress evaluation fields must never become an
        # assertion of the target interval's still-future outcome.
        "evaluation_sum": 0.1, "evaluation_count": 1, "outcome_shortfall": True}],
        "preparedness": [{"forecast_id": "harvest:0:1:0", "bought_during_warning": 12,
                           "paid_during_warning": 4, "extra_target": 5}]}


def _text(snapshot, civs=("A",), regions=("Here",), at=9):
    return "\n".join(text for _keys, text in expansion_state_facts(snapshot, civs, regions, at))


def test_missing_optional_snapshots_have_no_context_or_final_world_fallback():
    assert expansion_state_facts(_snap(), ["A"], ["Here"], 9) == []
    # The standing-state reader never asks the world for current optional state.
    world = type("FinalWorld", (), {"health_care": _health(), "ritual_gatherings": _gathering(),
                                    "harvest_forecasts": _forecast(), "regions": [], "civilizations": []})()
    assert NC.standing_state_lines(_snap(), [_event()], world) == []


def test_health_context_is_work_budget_not_clinical_or_avoided_death_claim():
    text = _text(_snap(health_care=_health()))
    assert "6 active temporary work-injury episodes" in text
    assert "2.50 worker-turns for impairment" in text and "0.40 worker-turns allocated to care" in text
    assert all(word not in text.lower() for word in ("clinical", "cured", "saved", "death", "grain lost", "recovered"))
    assert "3" not in text  # no clinical interpretation of the recoveries field


def test_unknown_health_units_and_unrecorded_gathering_purpose_are_not_inferred():
    health, gathering = _health(), _gathering()
    health.pop("units")
    gathering["outcomes"][0].pop("purpose")
    assert _text(_snap(health_care=health, ritual_gatherings=gathering)) == ""


def test_gathering_names_and_attempts_come_from_dated_receipts():
    text = _text(_snap(ritual_gatherings=_gathering()))
    assert "Then-host" in text and "3 selected local adults" in text
    assert "0.15 grain consumed and 2 treasury units spent" in text
    assert "1 friendship attempts" in text and "0 additional contact units" in text
    assert "pilgrims" not in text and "friendships formed" not in text


def test_gathering_cancellation_describes_only_recorded_zero_expenses():
    state = _gathering("cancelled")
    text = _text(_snap(ritual_gatherings=state))
    assert "because of enemy occupation" in text and "no gathering expense" in text
    state["outcomes"][0].pop("food")
    assert "no gathering expense" not in _text(_snap(ritual_gatherings=state))


@pytest.mark.parametrize("status,expected", [("delivered", "delivered on turn 7"),
                                            ("pending", "awaiting delivery"),
                                            ("withheld", "withheld from its recipient")])
def test_forecasts_are_dated_claims_and_delivery_state_is_explicit(status, expected):
    text = _text(_snap(harvest_forecasts=_forecast(status)))
    assert expected in text and "assessors estimate 75%" in text and "turns 9-11" in text
    assert "future outcome is not established" in text
    assert all(word not in text.lower() for word in ("calibrated", "actual shortfall", "excess spending", "avoided"))
    assert ("purchases during the warning: 12.00 grain for 4 treasury units" in text) == (status == "delivered")


@pytest.mark.parametrize("field,factory", [("health_care", _health),
    ("ritual_gatherings", _gathering), ("harvest_forecasts", _forecast)])
@pytest.mark.parametrize("source", [8, 10, None])
def test_stale_future_and_undated_snapshot_sections_are_not_current_facts(field, factory, source):
    state = factory()
    state["source_turn"] = source
    assert _text(_snap(**{field: state})) == ""


def test_later_moment_cannot_backfill_a_future_snapshot():
    assert _text(_snap(health_care=_health(), ritual_gatherings=_gathering(), harvest_forecasts=_forecast()), at=8) == ""


@pytest.mark.parametrize("change", ["future_issue", "future_delivery", "expired", "future_gathering"])
def test_future_row_data_is_rejected_within_an_otherwise_dated_section(change):
    forecast, gathering = _forecast(), _gathering()
    if change == "future_issue":
        forecast["reports"][0]["issued_turn"] = 12
    elif change == "future_delivery":
        forecast["reports"][0]["delivered_turn"] = 12
    elif change == "expired":
        forecast["reports"][0]["expires_turn"] = 8
    else:
        gathering["outcomes"][0]["turn"] = 12
    snapshot = _snap(**({"ritual_gatherings": gathering} if change == "future_gathering"
                        else {"harvest_forecasts": forecast}))
    assert _text(snapshot) == ""


def test_context_is_focused_bounded_deterministic_and_read_only():
    health, gathering, forecast = _health(), _gathering(), _forecast()
    for state, key in ((health, "regions"), (gathering, "outcomes"), (forecast, "reports")):
        state[key] *= 100
    snapshot = _snap(health_care=health, ritual_gatherings=gathering, harvest_forecasts=forecast)
    before = copy.deepcopy(snapshot.model_dump())
    facts = expansion_state_facts(snapshot, ["A"], ["Here"], 9)
    assert len(facts) == 3
    assert facts == expansion_state_facts(snapshot, ["A"], ["Here"], 9)
    assert snapshot.model_dump() == before
    assert expansion_state_facts(snapshot, ["Other"], ["Elsewhere"], 9) == []


def test_new_snapshot_facts_use_existing_citable_identity_contract():
    snapshot = _snap(health_care=_health(), ritual_gatherings=_gathering(), harvest_forecasts=_forecast())
    facts = NC.standing_state_facts(snapshot, [_event()])
    ids = FactIds([], [])
    refs = [ids.snapshot(snapshot.turn, kind, key) for keys, _text in facts for kind, key in keys]
    assert any(ref.startswith("s10.work_health.") for ref in refs)
    assert "s10.gathering.harvest:0" in refs
    assert "s10.harvest_report.harvest:0:1:0" in refs
    assert "s10.harvest_preparedness.harvest:0:1:0" in refs


def test_expansion_lines_share_the_existing_total_state_budget(monkeypatch):
    monkeypatch.setattr(NC, "MAX_STATE_LINES", 2)
    snapshot = _snap(health_care=_health(), ritual_gatherings=_gathering(), harvest_forecasts=_forecast())
    assert len(NC.standing_state_facts(snapshot, [_event()])) == 2


def test_prepared_prompts_keep_the_historical_snapshot_and_citation_dates():
    from unittest.mock import MagicMock
    from chronicler.models import NarrativeMoment, NarrativeRole
    from chronicler.narrative import NarrativeEngine

    engine = NarrativeEngine(sim_client=MagicMock(model="test"), narrative_client=MagicMock(model="test"))
    early = TurnSnapshot(turn=8, civ_stats={}, region_control={}, relationships={})
    late = _snap(health_care=_health(), ritual_gatherings=_gathering(), harvest_forecasts=_forecast())
    moments = []
    for turn in (7, 9):
        event = _event()
        event.turn = turn
        moments.append(NarrativeMoment(anchor_turn=turn, turn_range=(turn, turn), events=[event],
            named_events=[], score=5.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0))
    first, second = engine._prepare_narration_prompts(moments, [early, late])
    for label in ("Work impairment", "Local harvest gathering", "Harvest assessment for"):
        assert label not in first["prompt"] and label in second["prompt"]
    assert "s10.work_health" in second["prompt"] and "recorded turn 9" in second["prompt"]
    assert "s10.work_health" not in first["prompt"]


def test_optional_event_kinds_are_readable_and_recurring_bulletins_are_folded():
    expected = {
        "occupational_injury": "Temporary work injuries are reported in A (Here)",
        "harvest_forecast_issued": "A issues a harvest assessment (Here)",
        "harvest_forecast_delivered": "A harvest assessment reaches A (Here)",
        "harvest_forecast_resolved": "A harvest assessment for A is closed (Here)",
        "harvest_gathering_held": "A holds a local harvest gathering (Here)",
        "harvest_gathering_cancelled": "A local harvest gathering in A is cancelled (Here)",
    }
    for kind, text in expected.items():
        assert NC.event_text(_event(kind)) == text
        assert NC.is_routine(_event(kind)) == (not kind.startswith("harvest_gathering_"))
    events = [_event("harvest_forecast_delivered") for _ in range(100)]
    lines, omitted = NC.select_prompt_events(events)
    assert len(lines) <= NC.ROUTINE_FILL
    assert len(lines) + sum(len(line.folded) for line in lines) + sum(omitted.values()) == 100
