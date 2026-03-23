"""Tests for batch narration: before/after summaries, narrate_batch, and --narrate CLI."""
import json
from unittest.mock import MagicMock
from chronicler.models import (
    TurnSnapshot, CivSnapshot, NarrativeMoment, NarrativeRole,
    Event, CausalLink, ChronicleEntry, GapSummary,
)
from chronicler.narrative import build_before_summary, build_after_summary, NarrativeEngine
from chronicler.curator import curate


def _make_snap(turn, civ, pop, mil, stab, regions):
    return TurnSnapshot(
        turn=turn,
        civ_stats={civ: CivSnapshot(
            population=pop, military=mil, economy=50, culture=50,
            stability=stab, treasury=100, asabiya=0.5,
            tech_era="classical", trait="aggressive",
            regions=regions, leader_name="Leader", alive=True,
        )},
        region_control={r: civ for r in regions},
        relationships={},
    )


def test_before_summary_reports_stat_changes():
    history = [
        _make_snap(1, "A", pop=100, mil=50, stab=50, regions=["r1"]),
        _make_snap(10, "A", pop=80, mil=70, stab=30, regions=["r1", "r2"]),
    ]
    moment = NarrativeMoment(
        anchor_turn=10, turn_range=(10, 10), events=[], named_events=[],
        score=5.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
    )
    summary = build_before_summary(history, moment, prev_moment=None)
    assert summary.splitlines() == [
        "- A population fell from 100 to 80",
        "- A military rose from 50 to 70",
        "- A stability fell from 50 to 30",
        "- A claimed r2",
    ]


def test_after_summary_looks_forward():
    history = [
        _make_snap(10, "A", pop=100, mil=50, stab=50, regions=["r1"]),
        _make_snap(30, "A", pop=50, mil=30, stab=10, regions=["r1"]),
    ]
    moment = NarrativeMoment(
        anchor_turn=10, turn_range=(10, 10), events=[], named_events=[],
        score=5.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
    )
    next_moment = NarrativeMoment(
        anchor_turn=30, turn_range=(30, 30), events=[], named_events=[],
        score=5.0, causal_links=[], narrative_role=NarrativeRole.RESOLUTION, bonus_applied=0,
    )
    summary = build_after_summary(history, moment, next_moment)
    assert summary.splitlines() == [
        "- A population will fall to 50",
        "- A military will fall to 30",
        "- A stability will fall to 10",
    ]


def test_narrate_batch_produces_entries():
    mock_client = MagicMock()
    mock_client.model = "test-model"
    mock_client.complete.return_value = "The war began at dawn."
    engine = NarrativeEngine(sim_client=mock_client, narrative_client=mock_client)
    moments = [
        NarrativeMoment(
            anchor_turn=10, turn_range=(8, 12),
            events=[Event(turn=10, event_type="war", actors=["A"], description="t", importance=8)],
            named_events=[], score=10.0, causal_links=[],
            narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
        ),
    ]
    history = [_make_snap(i, "A", 100, 50, 50, ["r1"]) for i in range(1, 15)]
    entries = engine.narrate_batch(moments, history, [])
    assert len(entries) == 1
    assert entries[0].narrative == "The war began at dawn."
    assert entries[0].narrative_role == NarrativeRole.CLIMAX


def test_narrate_batch_fallback_on_error():
    mock_client = MagicMock()
    mock_client.model = "test-model"
    mock_client.complete.side_effect = Exception("LLM unavailable")
    engine = NarrativeEngine(sim_client=mock_client, narrative_client=mock_client)
    moments = [
        NarrativeMoment(
            anchor_turn=10, turn_range=(10, 10),
            events=[Event(turn=10, event_type="war", actors=["A"], description="battle", importance=8)],
            named_events=[], score=10.0, causal_links=[],
            narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
        ),
    ]
    history = [_make_snap(i, "A", 100, 50, 50, ["r1"]) for i in range(1, 15)]
    entries = engine.narrate_batch(moments, history, [])
    assert len(entries) == 1
    assert entries[0].narrative == "battle"


def test_narrate_batch_progress_callback():
    mock_client = MagicMock()
    mock_client.model = "test-model"
    mock_client.complete.return_value = "Prose."
    engine = NarrativeEngine(sim_client=mock_client, narrative_client=mock_client)
    moments = [
        NarrativeMoment(
            anchor_turn=i*10, turn_range=(i*10, i*10),
            events=[Event(turn=i*10, event_type="war", actors=["A"], description="t", importance=5)],
            named_events=[], score=5.0, causal_links=[],
            narrative_role=NarrativeRole.ESCALATION, bonus_applied=0,
        )
        for i in range(1, 4)
    ]
    history = [_make_snap(i, "A", 100, 50, 50, ["r1"]) for i in range(1, 35)]
    progress_calls = []
    entries = engine.narrate_batch(
        moments, history, [],
        on_progress=lambda completed, total, eta: progress_calls.append((completed, total)),
    )
    assert len(entries) == 3
    assert len(progress_calls) == 3
    assert progress_calls[-1] == (3, 3)


def test_end_to_end_simulate_curate_narrate():
    """Full pipeline: curate hand-crafted events -> narrate -> verify bundle."""
    events = [
        Event(turn=1, event_type="drought", actors=["A"], description="drought hits", importance=7),
        Event(turn=3, event_type="war", actors=["A", "B"], description="war begins", importance=9),
        Event(turn=5, event_type="famine", actors=["A"], description="famine", importance=8),
        Event(turn=7, event_type="trade", actors=["B"], description="trade", importance=3),
        Event(turn=9, event_type="collapse", actors=["A"], description="collapse", importance=10),
    ]
    history = [_make_snap(i, "A", 100 - i*5, 50, 50 - i*3, ["r1"]) for i in range(1, 11)]

    # Curate
    moments, gaps = curate(events, named_events=[], history=history, budget=3, seed=42)

    assert len(moments) <= 3
    assert all(isinstance(m.narrative_role, NarrativeRole) for m in moments)

    # Narrate with mock LLM
    mock_client = MagicMock()
    mock_client.model = "test"
    mock_client.complete.return_value = "Chronicle prose."
    engine = NarrativeEngine(sim_client=mock_client, narrative_client=mock_client)

    entries = engine.narrate_batch(moments, history, gaps)

    assert len(entries) == len(moments)
    assert all(isinstance(e, ChronicleEntry) for e in entries)
    assert all(e.narrative == "Chronicle prose." for e in entries)

    # Verify bundle format
    bundle_data = {
        "chronicle_entries": [e.model_dump() for e in entries],
        "gap_summaries": [g.model_dump() for g in gaps],
    }
    raw = json.dumps(bundle_data, default=str)
    loaded = json.loads(raw)

    assert isinstance(loaded["chronicle_entries"], list)
    for entry_data in loaded["chronicle_entries"]:
        restored = ChronicleEntry.model_validate(entry_data)
        assert restored.narrative_role in list(NarrativeRole)

    # Verify gaps + entries don't overlap in turns
    moment_turns = set()
    for e in entries:
        for t in range(e.covers_turns[0], e.covers_turns[1] + 1):
            moment_turns.add(t)
    gap_turns = set()
    for g in gaps:
        for t in range(g.turn_range[0], g.turn_range[1] + 1):
            gap_turns.add(t)
    assert not (moment_turns & gap_turns), "Moment and gap turns should not overlap"
