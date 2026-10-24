"""Causal provenance: event identity, recorded causes, chronic episodes,
cause-graph curation, mechanical "because" chains and outcome identity.

See docs/integration/causal-provenance.md.
"""
from __future__ import annotations

import json

import pytest

from chronicler import provenance
from chronicler.action_engine import ActionEngine
from chronicler.curator import (
    CauseGraph,
    compute_chain_scores,
    compute_causal_links,
    curate,
)
from chronicler.models import (
    ActiveCondition,
    CausalChain,
    ChainStep,
    Event,
    NarrativeMoment,
    NarrativeRole,
    WorldState,
)
from chronicler.narrative import mechanical_narrative, render_because
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world

PROVENANCE_EVENT_FIELDS = ("event_id", "causes", "region", "civs", "episode", "duration")


def _world(seed: int = 42) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = True
    return world


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def _strip_world(world: WorldState) -> dict:
    data = json.loads(world.model_dump_json())
    data.pop("provenance", None)
    data["events_timeline"] = [
        {k: v for k, v in ev.items() if k not in PROVENANCE_EVENT_FIELDS}
        for ev in data["events_timeline"] if ev.get("episode") != "end"
    ]
    for ev in data["events_timeline"]:
        if ev["event_type"] == "supply_shock":
            ev.pop("importance", None)
    data["active_conditions"] = [
        {k: v for k, v in c.items() if k not in ("condition_id", "cause_id", "onset_turn")}
        for c in data["active_conditions"]
    ]
    return data


@pytest.fixture(scope="module")
def run_off():
    return _advance(_world(42), 60)


# --- identity ------------------------------------------------------------------

def test_every_event_gets_a_unique_deterministic_id(run_off):
    ids = [ev.event_id for ev in run_off.events_timeline]
    assert all(ids)
    assert len(ids) == len(set(ids))
    for ev in run_off.events_timeline:
        turn, etype, n = ev.event_id.split(":")
        assert int(turn) == ev.turn and etype == ev.event_type and int(n) >= 0
    again = _advance(_world(42), 60)
    assert [(e.event_id, e.causes) for e in again.events_timeline] == [
        (e.event_id, e.causes) for e in run_off.events_timeline
    ]


def test_causes_resolve_to_earlier_events(run_off):
    by_id = {ev.event_id: ev for ev in run_off.events_timeline}
    linked = [ev for ev in run_off.events_timeline if ev.causes]
    assert linked, "expected recorded causes in a 60-turn run"
    for ev in linked:
        for cid in ev.causes:
            assert cid in by_id, f"{ev.event_id} cites unknown {cid}"
            assert cid != ev.event_id
            assert by_id[cid].turn <= ev.turn


def test_conditions_get_ids_and_causes(run_off):
    world = _world(7)
    _advance(world, 40)
    for cond in world.active_conditions:
        assert cond.condition_id.split(":")[1] == f"condition.{cond.condition_type}"
    by_id = {ev.event_id: ev for ev in world.events_timeline}
    for ev in world.events_timeline:
        if ev.event_type in ("drought_ended", "plague_ended"):
            assert ev.episode == "end" and ev.duration >= 1
            assert all(by_id[c].event_type == ev.event_type[:-len("_ended")] for c in ev.causes)


def _disable_observer(monkeypatch):
    monkeypatch.setattr(provenance, "observe", lambda world, events=(): list(events))
    monkeypatch.setattr(provenance, "end_turn", lambda world: [])
    monkeypatch.setattr(provenance, "finish_turn", lambda world: None)
    monkeypatch.setattr(provenance, "observe_now", lambda world, event: None)


def test_provenance_does_not_change_simulation_outcomes(monkeypatch):
    """Same seed with the turn-loop observer disabled (no ids, no folding):
    the legacy-timeline run is identical once provenance fields are set aside,
    and the production run differs only in its (folded) timeline."""
    production = _advance(_world(11), 50)
    monkeypatch.setattr(provenance, "LEGACY_TIMELINE", True)
    legacy = _advance(_world(11), 50)
    _disable_observer(monkeypatch)
    without = _advance(_world(11), 50)
    assert sum(1 for ev in without.events_timeline if ev.event_id) < len(without.events_timeline) // 10
    assert any(ev.episode in ("onset", "tick") for ev in legacy.events_timeline)
    assert _strip_world(legacy) == _strip_world(without)
    prod, base = _strip_world(production), _strip_world(without)
    prod_events, base_events = prod.pop("events_timeline"), base.pop("events_timeline")
    assert prod == base
    # Production only folds repeats: its timeline is an ordered subsequence.
    it = iter(base_events)
    assert all(any(ev == other for other in it) for ev in prod_events)


def test_save_load_resumes_with_the_same_ids(tmp_path):
    straight = _advance(_world(5), 30)
    first = _advance(_world(5), 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.provenance == first.provenance
    _advance(resumed, 15)
    assert [(e.event_id, e.causes, e.episode) for e in resumed.events_timeline] == [
        (e.event_id, e.causes, e.episode) for e in straight.events_timeline
    ]


def test_old_saves_and_events_load_and_serialize_unchanged():
    legacy = {"turn": 3, "event_type": "famine", "actors": ["A"], "description": "d",
              "consequences": [], "importance": 8, "source": "aggregate",
              "shock_region": None, "shock_category": None}
    ev = Event.model_validate(legacy)
    assert ev.event_id == "" and ev.causes == [] and ev.region is None
    assert ev.model_dump() == legacy
    cond = ActiveCondition(condition_type="drought", affected_civs=["A"], duration=2)
    assert "condition_id" not in cond.model_dump()
    world = _world(3)
    raw = json.loads(world.model_dump_json())
    assert "provenance" not in raw
    assert WorldState.model_validate(raw).provenance.is_empty()


# --- chronic episodes ------------------------------------------------------------

def _shock(world, region="R1", cat="food"):
    return Event(turn=world.turn, event_type="supply_shock", actors=["Civ"], importance=9,
                 description=f"Supply shock: {cat} in {region}", source="economy",
                 shock_region=region, shock_category=cat)


def test_chronic_condition_emits_onset_and_end_with_duration():
    world = WorldState(name="t", seed=1)
    kept: list[Event] = []
    for turn in range(5):
        world.turn = turn
        provenance.begin_turn(world)
        kept += provenance.observe(world, [_shock(world)])
        kept += provenance.end_turn(world)
    world.turn = 5
    provenance.begin_turn(world)
    kept += provenance.observe(world, [])
    ended = provenance.end_turn(world)
    assert [e.episode for e in kept] == ["onset"]
    assert kept[0].importance == 6  # supply-shock onsets are capped
    assert len(ended) == 1
    end = ended[0]
    assert end.event_type == "supply_shock_ended" and end.episode == "end"
    assert end.duration == 5 and end.causes == [kept[0].event_id]
    assert not world.provenance.episodes


def test_famine_repeats_stay_as_ticks_with_their_own_causes():
    world = WorldState(name="t", seed=1)
    out: list[Event] = []
    for turn in (0, 5, 10):
        world.turn = turn
        provenance.begin_turn(world)
        out += provenance.observe(world, [Event(
            turn=turn, event_type="famine", actors=["Civ"], description="Famine",
            importance=8, region="R1")])
        out += provenance.end_turn(world)
    assert [e.episode for e in out] == ["onset", "tick", "tick"]
    assert all(out[0].event_id not in e.causes for e in out[1:])
    ep = world.provenance.episodes["famine|R1|"]
    assert ep.onset_id == out[0].event_id and ep.last_id == out[2].event_id
    assert provenance.open_episode(world, "famine", "R1") == out[2].event_id


def test_condition_end_event_cites_the_creating_event():
    world = WorldState(name="t", seed=1)
    world.turn = 4
    provenance.begin_turn(world)
    drought = Event(turn=4, event_type="drought", actors=["Civ"], description="")
    world.active_conditions.append(ActiveCondition(condition_type="drought", affected_civs=["Civ"],
                                                   duration=3, severity=50))
    provenance.observe(world, [drought])
    cond = world.active_conditions[0]
    assert cond.condition_id == "4:condition.drought:0"
    assert cond.cause_id == drought.event_id and cond.onset_turn == 4
    world.active_conditions.clear()
    world.turn = 7
    provenance.begin_turn(world)
    ended = provenance.end_turn(world)
    assert [e.event_type for e in ended] == ["drought_ended"]
    assert ended[0].duration == 3 and ended[0].causes == [drought.event_id]


# --- curator -----------------------------------------------------------------------

def _ev(turn, etype, actors, imp=5, eid=None, causes=(), desc=None):
    return Event(turn=turn, event_type=etype, actors=list(actors), importance=imp,
                 description=desc if desc is not None else f"{etype} at {turn}",
                 event_id=eid or "", causes=list(causes))


def test_cause_graph_depth_and_root_bonus():
    events = [
        _ev(1, "war_declared", ["A", "B"], eid="1:war_declared:0"),
        _ev(3, "war", ["A", "B"], eid="3:war:0", causes=["1:war_declared:0"]),
        _ev(3, "occupation", ["A", "B"], eid="3:occupation:0", causes=["3:war:0"]),
        _ev(6, "famine", ["B"], eid="6:famine:0", causes=["3:occupation:0", "9:missing:0"]),
        _ev(8, "secession", ["B", "C"], eid="8:secession:0", causes=["6:famine:0"]),
    ]
    graph = CauseGraph(events)
    assert graph.edge_count == 4  # the unresolved id is ignored
    assert graph.depth_down()[0] == 4 and graph.depth_up()[4] == 4
    bonus = compute_chain_scores(graph)
    assert bonus[0] == max(bonus) > 0
    assert graph.chain_to(4) == [0, 1, 2, 3, 4]
    links = compute_causal_links(events, [5.0] * len(events), graph=graph)
    assert {link.provenance for link in links} == {"recorded"}
    assert links[0].cause_id == "1:war_declared:0" and links[0].effect_id == "3:war:0"


def test_patterns_link_only_effects_without_recorded_causes():
    events = [
        _ev(1, "drought", ["A"], eid="1:drought:0"),
        _ev(2, "drought", ["A"], eid="2:drought:0"),
        _ev(4, "famine", ["A"], eid="4:famine:0"),                      # no provenance
        _ev(5, "famine", ["A"], eid="5:famine:0", causes=["1:drought:0"]),  # recorded
    ]
    scores = [5.0] * 4
    links = compute_causal_links(events, scores)
    patterns = [link for link in links if link.provenance == "pattern"]
    recorded = [link for link in links if link.provenance == "recorded"]
    assert len(recorded) == 1 and recorded[0].effect_id == "5:famine:0"
    # One fallback link for the unexplained famine, to the most recent drought.
    assert [(p.cause_id, p.effect_id) for p in patterns] == [("2:drought:0", "4:famine:0")]
    assert scores[1] == 8.0 and scores[0] == 5.0


def test_curator_ranks_a_deep_root_cause_above_an_isolated_spike():
    chain = [_ev(10, "war_declared", ["A", "B"], imp=5, eid="10:war_declared:0")]
    for k in range(1, 6):
        chain.append(_ev(10 + k, "war", ["A", "B"], imp=5, eid=f"{10 + k}:war:0",
                         causes=[chain[-1].event_id]))
    lone = _ev(60, "earthquake", ["C"], imp=9, eid="60:earthquake:0")
    moments, _ = curate(chain + [lone], [], [], budget=1, seed=0)
    assert moments[0].anchor_turn == 10
    assert moments[0].causal_chains
    steps = moments[0].causal_chains[0].steps
    assert steps[0].event_id == "10:war_declared:0" and len(steps) >= 2


def test_episode_followers_never_anchor_a_moment():
    onset = _ev(5, "famine", ["A"], imp=8, eid="5:famine:0")
    onset.episode = "onset"
    end = _ev(5, "famine_ended", ["A"], imp=9, eid="5:famine_ended:0", causes=["5:famine:0"])
    end.episode = "end"
    moments, _ = curate([onset, end], [], [], budget=1, seed=0)
    assert moments[0].events[0] is onset
    graph = CauseGraph([onset, end])
    assert graph.depth_down()[0] == 0  # a closing event is not a consequence


def test_old_bundle_events_still_link_by_pattern():
    legacy = [Event.model_validate({"turn": 5, "event_type": "drought", "actors": ["A"],
                                    "description": "d", "importance": 5}),
              Event.model_validate({"turn": 9, "event_type": "famine", "actors": ["A"],
                                    "description": "f", "importance": 8})]
    moments, _ = curate(legacy, [], [], budget=1, seed=0)
    assert [link.pattern for link in moments[0].causal_links] == ["drought→famine"]
    assert moments[0].causal_chains == []


# --- narration ---------------------------------------------------------------------

def _chain(*steps):
    return CausalChain(steps=[ChainStep(event_id=f"{t}:x:{i}", turn=t, event_type="x", description=d)
                              for i, (t, d) in enumerate(steps)])


def test_mechanical_chronicle_says_because():
    chain = _chain((0, "A goes to war with B."), (6, "Amber Valley is occupied"),
                   (9, "Famine strikes Amber Valley"))
    assert render_because(chain) == (
        "Famine strikes Amber Valley (turn 9), because Amber Valley is occupied (turn 6), "
        "because A goes to war with B (turn 0).")
    moment = NarrativeMoment(anchor_turn=9, turn_range=(9, 9), events=[], named_events=[],
                             score=1.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX,
                             bonus_applied=0.0, causal_chains=[chain])
    told: set[str] = set()
    first = mechanical_narrative(moment, told)
    assert "because Amber Valley is occupied" in first
    again = mechanical_narrative(moment, told)
    assert "(turn 6, as told above)" in again and "turn 0" not in again


def test_narrator_prompt_lists_recorded_chains():
    from chronicler.narrative import NarrativeEngine

    chain = _chain((0, "A goes to war with B"), (9, "Famine strikes Amber Valley"))
    moment = NarrativeMoment(anchor_turn=9, turn_range=(9, 9),
                             events=[_ev(9, "famine", ["B"], imp=8)], named_events=[],
                             score=1.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX,
                             bonus_applied=0.0, causal_chains=[chain])
    engine = NarrativeEngine(sim_client=None, narrative_client=None)
    prompt = engine._prepare_narration_prompts([moment], [])[0]["prompt"]
    assert "CAUSAL CHAINS" in prompt
    assert "[turn 0] A goes to war with B -> [turn 9] Famine strikes Amber Valley" in prompt


def test_mechanical_narrator_renders_without_an_llm():
    from chronicler.llm import MechanicalClient
    from chronicler.narrative import NarrativeEngine

    chain = _chain((0, "A goes to war with B"), (9, "Famine strikes Amber Valley"))
    moment = NarrativeMoment(anchor_turn=9, turn_range=(9, 9),
                             events=[_ev(9, "famine", ["B"], imp=8, desc="Famine strikes Amber Valley.")],
                             named_events=[], score=1.0, causal_links=[],
                             narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0,
                             causal_chains=[chain])
    engine = NarrativeEngine(sim_client=None, narrative_client=MechanicalClient())
    [entry] = engine.narrate_batch([moment], [])
    assert "because A goes to war with B (turn 0)" in entry.narrative
    assert entry.causal_chains == [chain]
    assert "causal_chains" in entry.model_dump()
