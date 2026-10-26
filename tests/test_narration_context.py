"""Narration coverage: event lines, bounded prompt lists, standing state,
recorded consequences and curator weights (docs/integration/narration-coverage.md)."""
from __future__ import annotations

import itertools

from chronicler import narration_context as nc
from chronicler.curator import (
    CHAIN_CURATION_WEIGHT,
    apply_narrative_weights,
    curate,
)
from chronicler.models import (
    CivSnapshot,
    Event,
    NamedEvent,
    NarrativeMoment,
    NarrativeRole,
    TechEra,
    TurnSnapshot,
)
from chronicler.narrative import NarrativeEngine, mechanical_narrative


_IDS = itertools.count()


def _ev(turn, etype, actors=("A",), imp=5, desc=None, eid=None, region=None, causes=(), **kw):
    return Event(turn=turn, event_type=etype, actors=list(actors), importance=imp,
                 description=f"{etype} at {turn}" if desc is None else desc,
                 event_id=eid or f"{turn}:{etype}:t{next(_IDS)}",
                 region=region, causes=list(causes), **kw)


def _moment(events, named=(), chains=(), turn_range=None):
    turns = [e.turn for e in events] or [0]
    return NarrativeMoment(
        anchor_turn=turns[0], turn_range=turn_range or (min(turns), max(turns)),
        events=list(events), named_events=list(named), score=1.0, causal_links=[],
        narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0, causal_chains=list(chains))


def _snap(turn, civs, **fields):
    return TurnSnapshot(
        turn=turn,
        civ_stats={name: CivSnapshot(
            population=100, military=50, economy=50, culture=50, stability=50, treasury=100,
            asabiya=0.5, tech_era=TechEra.CLASSICAL, trait="bold", regions=[],
            leader_name=leader, alive=True, capital_region=capital)
            for name, (leader, capital) in civs.items()},
        region_control={}, relationships={}, **fields)


# --- event lines -------------------------------------------------------------------

def test_events_recorded_without_a_description_get_a_label():
    assert nc.event_text(_ev(3, "drought", ["A", "B"], desc="")) == "Drought strikes A and B"
    assert nc.event_text(_ev(3, "border_incident", ["A", "B"], desc="")) == "A border incident between A and B"
    # Native politics triggers arrive without a description.
    assert nc.event_text(_ev(3, "proxy_detected", ["A", "B"], desc="")) == "A is exposed funding separatists in B"
    assert nc.event_text(_ev(3, "federation_formed", ["A", "B"], desc="")) == "A and B form a federation"
    assert nc.event_text(_ev(3, "strange_new_thing", ["A"], desc="", region="R")) == "Strange new thing in A (R)"


def test_the_label_historiography_writes_with_is_unchanged():
    """historiography writes its accounts during the run with curator.event_label:
    its text is saved output, so narration's labels must not leak into it."""
    from chronicler.curator import event_label
    assert event_label(_ev(3, "famine", desc="Famine strikes R.")) == "Famine strikes R."
    assert event_label(_ev(3, "drought", ["A", "B"], desc="")) == "drought strikes A and B"
    assert event_label(_ev(3, "proxy_detected", ["A", "B"], desc="")) == "proxy detected in A, B"
    assert event_label(_ev(3, "mass_migration", desc="12 farmers fled Hills for Plains")) == \
        "12 farmers fled Hills for Plains"


def test_a_recorded_description_is_kept_without_its_full_stop():
    assert nc.event_text(_ev(3, "famine", desc="Famine strikes R, devastating A.")) == \
        "Famine strikes R, devastating A"


def test_misleading_descriptions_say_no_more_than_the_record():
    same = _ev(3, "move_capital", desc="A relocated capital from Old Town to Old Town")
    assert nc.event_text(same) == "A spent on moving its capital but kept it at Old Town"
    moved = _ev(3, "move_capital", desc="A relocated capital from Old Town to New Town")
    assert nc.event_text(moved) == "A relocated capital from Old Town to New Town"
    undriven = _ev(3, "mass_migration", desc="12 farmers fled Hills for Plains")
    assert nc.event_text(undriven) == "12 farmers left Hills for Plains"
    driven = _ev(3, "mass_migration", desc="12 farmers fled hunger in Hills for Plains", driver="opp_food")
    assert nc.event_text(driven) == "12 farmers fled hunger in Hills for Plains"
    scholars = _ev(3, "brain_drain", desc="6 scholars fled Hills over 10 turns")
    assert nc.event_text(scholars) == "6 scholars left Hills over 10 turns"
    faithful = _ev(3, "Mass Migration",
                   desc="Religious minorities flee Hills due to persecution (minority_ratio=0.43)")
    assert nc.event_text(faithful) == ("Persecution presses the religious minorities of Hills "
                                       "(43% of its people) to flee")


def test_a_temple_recorded_by_faith_id_is_named_by_its_faith():
    ev = _ev(9, "temple_destroyed", desc="Temple of faith 3 replaced in Ashara Desert")
    assert nc.event_text(ev, {3: "Faith of Thornwall"}) == \
        "The temple of the Faith of Thornwall is replaced in Ashara Desert"
    assert nc.event_text(ev) == "Temple of faith 3 replaced in Ashara Desert"  # no registry: as recorded
    assert nc.event_text(ev, {4: "Other"}) == "Temple of faith 3 replaced in Ashara Desert"


def test_a_prompt_line_names_the_migration_driver_and_unnamed_actors():
    ev = _ev(4, "mass_migration", ["Sage Ilra"], desc="9 farmers left Hills to settle Plains",
             driver="frontier")
    line = nc.render_prompt_line(nc.PromptLine(ev, 5.0, 0))
    assert line == ("- [turn 4] mass_migration: 9 farmers left Hills to settle Plains "
                    "(importance 5; driven by open land to settle; with Sage Ilra)")


# --- bounded event lists ----------------------------------------------------------

def test_prompt_lists_are_bounded_and_count_the_rest():
    events = [_ev(10, "develop", ["A"], imp=3, eid=f"10:develop:{i}") for i in range(40)]
    events += [_ev(11, "war", [f"C{i}", "A"], imp=6, eid=f"11:war:{i}") for i in range(20)]
    events += [_ev(11, f"kind_{i}", [f"D{i}"], imp=5, eid=f"11:kind:{i}") for i in range(15)]
    events += [_ev(12, "secession", ["A", "B"], imp=9, eid="12:secession:0")]
    events += [_ev(12, "famine_ended", ["A"], imp=4, eid="12:famine_ended:0", episode="end")]
    lines, omitted = nc.select_prompt_events(events)
    assert len(lines) <= nc.MAX_PROMPT_EVENTS
    kinds = [ln.event.event_type for ln in lines]
    assert "secession" in kinds and "develop" not in kinds
    assert kinds.count("war") <= nc.MAX_LINES_PER_KIND
    listed = sum(len(ln.events) for ln in lines)
    assert listed + sum(omitted.values()) == len(events)
    assert omitted["develop"] == 40 and omitted["famine_ended"] == 1
    war = next(ln for ln in lines if ln.event.event_type == "war")
    assert len(war.folded) == 18  # 20 battles: two lines, the rest named in the first
    assert nc.render_omitted(omitted).startswith("Also recorded in these turns (not listed): 40 develop")


def test_repeats_of_a_kind_fold_into_one_line_naming_the_places():
    events = [_ev(20 + i, "famine", ["A"], imp=8, region=r, eid=f"{20 + i}:famine:0")
              for i, r in enumerate(["North", "South", "East"])]
    lines, omitted = nc.select_prompt_events(events)
    assert len(lines) == 1 and not omitted
    text = nc.render_prompt_line(lines[0])
    assert "2 more alike, turns 21-22: South, East" in text


def test_scarce_kinds_and_chain_steps_win_a_line():
    events = [_ev(5, f"common_{i}", ["A"], imp=7, eid=f"5:c:{i}") for i in range(14)]
    events.append(_ev(5, "free_city", ["A", "Free City of B"], imp=6, eid="5:free_city:0"))
    counts = {**{f"common_{i}": 400 for i in range(14)}, "free_city": 1}
    lines, _ = nc.select_prompt_events(events, type_counts=counts)
    assert "free_city" in [ln.event.event_type for ln in lines]
    lines, _ = nc.select_prompt_events(events[:13] + [_ev(5, "x", ["Z"], imp=6, eid="5:x:0")],
                                       chain_ids=["5:x:0"])
    assert "x" in [ln.event.event_type for ln in lines]


def test_selection_is_deterministic_and_keeps_recorded_order():
    events = [_ev(t, f"kind_{t % 5}", [f"C{t % 3}"], imp=4 + t % 5, eid=f"{t}:k:{t}") for t in range(60)]
    a = [ln.event.event_id for ln in nc.select_prompt_events(events)[0]]
    b = [ln.event.event_id for ln in nc.select_prompt_events(list(events))[0]]
    assert a == b
    turns = [int(eid.split(":")[0]) for eid in a]
    assert turns == sorted(turns)


# --- standing state ---------------------------------------------------------------

def test_standing_state_reads_rulers_wars_movements_reforms_cities_and_food(sample_world):
    kethani, dorrathi = sample_world.civilizations[0].name, sample_world.civilizations[1].name
    snap = _snap(31, {kethani: ("Empress Vaelith", "Verdant Plains"), dorrathi: ("Warchief Gorath", None)},
                 active_wars=[(kethani, dorrathi)],
                 agent_movements={
                     "living": [{"id": 0, "name": "the Plains Brotherhood", "creed": "liberty", "target": 0,
                                 "stage": "rising", "members": 40, "strength": 0.25, "stronghold": 0,
                                 "martyrs": 1, "leader": "Ilra"},
                                {"id": 1, "name": "the Faded", "creed": "sect", "target": 0,
                                 "stage": "gathering", "members": 0, "strength": 0.0, "stronghold": -1,
                                 "martyrs": 0}],
                     "ended": 0, "counters": {},
                     "reforms": [{"id": 0, "kind": "relief", "civ": 0, "since": 12, "movement": 0}]},
                 cities={"cities": [{"id": 3, "name": "Vael", "region": "Verdant Plains", "lord": kethani,
                                     "rank": 2, "residents": 30, "wealth": 10.0, "crafts": 0.5,
                                     "charter": 3, "unrest": 0.4, "satisfaction": 0.5}],
                         "fallen": 0, "counters": {}},
                 food={"sufficiency": [0.45, None, None, None, None], "aid": []})
    timeline = nc.TimelineView([
        _ev(27, "dearth", [kethani], imp=4, region="Verdant Plains", episode="onset", eid="27:dearth:0"),
        _ev(29, "famine", [kethani], imp=8, region="Verdant Plains", eid="29:famine:0"),
        _ev(30, "famine", [kethani], imp=8, region="Verdant Plains", eid="30:famine:0", episode="tick"),
    ])
    events = [_ev(30, "famine", [kethani], imp=8, region="Verdant Plains", eid="30:famine:0"),
              _ev(30, "war", [kethani, dorrathi], imp=7, eid="30:war:0")]
    lines = nc.standing_state_lines(snap, events, sample_world, timeline, at_turn=30)
    text = "\n".join(lines)
    assert f"Rulers: {kethani}: Empress Vaelith (capital Verdant Plains); {dorrathi}: Warchief Gorath" in text
    assert f"At war: {kethani} and {dorrathi}" in text
    assert (f"Movement: the Plains Brotherhood (liberty, rising) against {kethani}, 40 members "
            "(25% of its people), led by Ilra, strongest in Verdant Plains") in text
    assert "the Faded" not in text  # a movement without members is not standing
    assert f"Reform in force: the poor relief in {kethani} since turn 12" in text
    assert f"City: Vael (city in Verdant Plains, lord {kethani}), free city, unrest 0.40" in text
    assert "Food in Verdant Plains: food on hand covers 45% of need, famine recorded since turn 29 (2 reports)" in text
    assert len(lines) <= nc.MAX_STATE_LINES


def test_wars_come_from_the_campaign_record_when_it_exists(sample_world):
    kethani, dorrathi = sample_world.civilizations[0].name, sample_world.civilizations[1].name
    war = {"war": f"{kethani}:{dorrathi}", "attacker": kethani, "defender": dorrathi, "aim": "conquest",
           "aim_region": "Iron Peaks", "score": -6, "start_turn": 30, "battles": 2}
    snap = _snap(41, {kethani: ("Empress Vaelith", None)},
                 campaign={"armies": [], "battles": [], "occupations": [], "wars": [war]})
    events = [_ev(40, "war", [kethani, dorrathi], imp=7, eid="40:war:0")]
    text = "\n".join(nc.standing_state_lines(snap, events, sample_world, None, at_turn=40))
    assert (f"At war: {kethani} against {dorrathi} since turn 30 (conquest of Iron Peaks; "
            f"war score -6 for {kethani})") in text


def test_guilds_of_the_moment_s_regions_and_the_burghers(sample_world):
    kethani = sample_world.civilizations[0].name
    guild = {"id": 0, "name": "the Weavers of Vael", "city": 3, "region": "Verdant Plains", "kind": "craft",
             "masters": 4.5, "wealth": 12.0, "monopoly": True, "say": False, "levy": True}
    snap = _snap(41, {kethani: ("Empress Vaelith", None)},
                 guilds={"guilds": [guild], "dissolved": 0, "burghers": {kethani: 0.18}, "counters": {}})
    events = [_ev(40, "guild_levy", [kethani], imp=4, region="Verdant Plains", eid="40:guild_levy:0")]
    text = "\n".join(nc.standing_state_lines(snap, events, sample_world, None, at_turn=40))
    assert ("Guild: the Weavers of Vael (craft guild in Verdant Plains, 4.5 masters): a monopoly of wares; "
            "its city's dues raised") in text
    assert f"Burgher faction's influence at court: {kethani} 18%" in text


def test_a_martyred_leader_is_not_told_as_leading(sample_world):
    """A movement keeps its dead leader's name; the martyrdom event is the record."""
    kethani = sample_world.civilizations[0].name
    row = {"id": 0, "name": "the Brotherhood", "creed": "liberty", "target": 0, "stage": "pressing",
           "members": 9, "strength": 0.1, "stronghold": -1, "martyrs": 1, "leader": "Ilra"}
    snap = _snap(41, {kethani: ("Empress Vaelith", None)},
                 agent_movements={"living": [row], "ended": 0, "counters": {}})
    timeline = nc.TimelineView([_ev(33, "movement_martyr", [kethani, "Ilra"], eid="33:movement_martyr:0")])
    events = [_ev(40, "movement_demand", [kethani], eid="40:movement_demand:0")]
    text = "\n".join(nc.standing_state_lines(snap, events, sample_world, timeline, at_turn=40))
    assert "its leader Ilra martyred in turn 33" in text and "led by Ilra" not in text
    early = "\n".join(nc.standing_state_lines(snap, events, sample_world, timeline, at_turn=30))
    assert "led by Ilra" in early


def test_food_crisis_spans_follow_the_recorded_labels():
    tv = nc.TimelineView([
        _ev(5, "dearth", region="R", episode="onset", eid="5:d:0"),
        _ev(7, "famine", region="R", eid="7:f:0", episode="tick"),
        _ev(8, "famine", region="R", eid="8:f:0", episode="tick"),
        _ev(11, "famine_ended", region="R", eid="11:e:0", episode="end"),
    ])
    assert tv.food_crisis_at("R", 6) == (5, "dearth", 1)
    assert tv.food_crisis_at("R", 7) == (7, "famine", 1)
    assert tv.food_crisis_at("R", 10) == (7, "famine", 2)
    assert tv.food_crisis_at("R", 11) is None


def test_later_consequences_are_recorded_effects_outside_the_moment():
    cause = _ev(10, "war_declared", ["A", "B"], imp=7, eid="10:war_declared:0")
    timeline = nc.TimelineView([
        cause,
        _ev(11, "war", ["A", "B"], imp=6, eid="11:war:0", causes=["10:war_declared:0"]),
        _ev(30, "civ_conquered", ["A", "B"], imp=9, eid="30:civ_conquered:0", causes=["10:war_declared:0"]),
        _ev(31, "develop", ["A"], imp=3, eid="31:develop:0", causes=["10:war_declared:0"]),
        _ev(32, "war_ended", ["A", "B"], imp=6, eid="32:war_ended:0", causes=["10:war_declared:0"]),
    ])
    later = timeline.consequences([cause], end_turn=12)
    assert [e.event_type for e in later] == ["civ_conquered", "war_ended"]


# --- prompts and the mechanical chronicle --------------------------------------------

def test_prompt_carries_bounded_events_state_and_consequences(sample_world):
    kethani = sample_world.civilizations[0].name
    events = [_ev(40, "develop", [kethani], imp=3, eid=f"40:develop:{i}") for i in range(30)]
    events.append(_ev(41, "famine", [kethani], imp=8, region="Verdant Plains", eid="41:famine:0"))
    events.append(_ev(41, "rebellion", [kethani], imp=5, desc="", eid="41:rebellion:0"))
    events += [_ev(41, f"kind_{i}", [kethani], imp=5, eid=f"41:kind:{i}") for i in range(3)]
    sample_world.events_timeline = events + [
        _ev(50, "secession", [kethani, "Free Plains"], imp=9, eid="50:secession:0", causes=["41:famine:0"])]
    snap = _snap(42, {kethani: ("Empress Vaelith", "Verdant Plains")})
    engine = NarrativeEngine(sim_client=None, narrative_client=None)
    engine._world = sample_world
    [prep] = engine._prepare_narration_prompts([_moment(events)], [snap])
    prompt = prep["prompt"]
    assert prompt.count("\n- [turn ") <= nc.MAX_PROMPT_EVENTS + 1
    assert f"- [turn 41] rebellion: Rebellion breaks out in {kethani}" in prompt
    assert "30 develop" in prompt and "[develop]" not in prompt
    assert "LATER CONSEQUENCES" in prompt and f"[turn 50] secession: " not in prompt
    assert "- [turn 50] secession at 50" in prompt
    assert "STANDING STATE after turn 41" in prompt and "Empress Vaelith" in prompt
    assert "CAUSES leading to this moment" not in prompt  # recorded links travel as chains
    assert set(prep["shown_event_ids"]) == {"41:famine:0", "41:rebellion:0",
                                            "41:kind:0", "41:kind:1", "41:kind:2"}


def test_same_moments_give_the_same_prompts(sample_world):
    events = [_ev(t, f"k{t % 7}", [sample_world.civilizations[t % 2].name], imp=3 + t % 6,
                  eid=f"{t}:k:{t}") for t in range(80)]
    sample_world.events_timeline = events
    moments = [_moment(events[i:i + 20]) for i in range(0, 80, 20)]

    def build():
        engine = NarrativeEngine(sim_client=None, narrative_client=None)
        engine._world = sample_world
        return [p["prompt"] for p in engine._prepare_narration_prompts(moments, [])]

    assert build() == build()


def test_mechanical_chronicle_reads_the_listed_events_as_sentences():
    events = [_ev(10, "develop", ["A"], imp=3, desc="A invested in economy.", eid=f"10:d:{i}") for i in range(5)]
    events += [_ev(11, "famine", ["A"], imp=8, region=r, desc=f"Famine strikes {r}, devastating A.",
                   eid=f"11:f:{r}") for r in ("North", "South")]
    events.append(_ev(12, "drought", ["A"], desc="", eid="12:drought:0"))
    text = mechanical_narrative(_moment(events))
    assert text == ("A invested in economy (4 more times). Famine strikes North, devastating A "
                    "(and in South). Drought strikes A.")


def test_placeholder_movement_names_stay_out_of_landmarks():
    from chronicler.narrative import _landmark_line
    ne = NamedEvent(name="Schism of movement 3", event_type="movement_schism", turn=5, actors=["A", "B"],
                    description="[movement_3] Schism between A and B", importance=7)
    assert _landmark_line(ne) == "(turn 5): Schism between A and B"


# --- curator weights ------------------------------------------------------------------

def test_guild_and_faction_kinds_are_weighed_not_counted_away():
    for kind in ("guild_founded", "guild_privilege", "guild_privilege_lost", "guild_levy",
                 "guild_dissolved", "faction_dominance_shift"):
        assert kind not in nc.ROUTINE_TYPES
        assert not nc.is_bookkeeping(_ev(1, kind))


def test_routine_kinds_score_their_importance_and_no_more():
    events = [_ev(1, "develop", imp=3), _ev(1, "quarantine", imp=4)]
    scores = [9.0, 12.0]
    apply_narrative_weights(events, scores)
    assert scores == [3.0, 4.0]


def test_turning_points_gain_and_recurrent_kinds_decay():
    events = [_ev(1, "supervolcano", imp=10)] + [_ev(t, "epidemic", imp=8) for t in range(48)] \
        + [_ev(t, "scarce", imp=5) for t in range(3)]
    scores = [float(e.importance) for e in events]
    apply_narrative_weights(events, scores)
    assert scores[0] == 10 + 4.5
    assert scores[1] == 8 + 1.5 - 2.0          # log2(48 / 12) = 2
    assert scores[-1] == 5 + 1.0


def test_a_lone_catastrophe_is_curated_against_long_routine_chains():
    """Chains saturate in long runs: a supervolcano with no recorded sequel must
    still be told against windows of quarantines on long epidemic chains."""
    events = []
    prev = None
    for k in range(40):  # one long epidemic chain, one event per turn
        eid = f"{k}:epidemic:0"
        events.append(_ev(k, "epidemic", ["A"], imp=5, eid=eid, causes=[prev] if prev else []))
        events.append(_ev(k, "quarantine", ["B"], imp=4, eid=f"{k}:quarantine:0", causes=[eid]))
        prev = eid
    events.append(_ev(25, "supervolcano", ["C"], imp=10, eid="25:supervolcano:0"))
    moments, _ = curate(events, [], [], budget=2, seed=0)
    assert any(e.event_type == "supervolcano" for m in moments for e in m.events)
    assert 0 < CHAIN_CURATION_WEIGHT < 1


# --- agent context ---------------------------------------------------------------

def test_agent_context_keeps_the_moment_s_characters():
    """Characters the events name, then active characters of the civs involved;
    not every active character of the world."""
    from chronicler.models import GreatPerson
    from chronicler.narrative import build_agent_context_for_moment

    def gp(name, civ, agent_id, active=True):
        return GreatPerson(name=name, role="general", trait="bold", civilization=civ,
                           origin_civilization=civ, born_turn=0, source="agent", agent_id=agent_id,
                           active=active)

    events = [_ev(5, "local_rebellion", ["Named Rebel"], imp=7, source="agent", civs=["A"])]
    people = [gp("Elsewhere", "Z", 1), gp("Of A", "A", 2), gp("Named Rebel", "A", 3, active=False)]
    ctx = build_agent_context_for_moment(_moment(events), people, {})
    assert [c["name"] for c in ctx.named_characters] == ["Named Rebel", "Of A"]


# --- scripts ----------------------------------------------------------------------

def test_prompt_report_counts_listed_turning_points():
    from scripts.narration_prompts import impact_ranking, summarize

    events = [
        {"turn": 1, "event_type": "war_declared", "actors": ["A"], "importance": 8, "event_id": "1:w:0"},
        {"turn": 2, "event_type": "war", "actors": ["A"], "importance": 6, "event_id": "2:w:0",
         "causes": ["1:w:0"]},
        {"turn": 3, "event_type": "famine_ended", "actors": ["A"], "importance": 9, "event_id": "3:e:0",
         "episode": "end"},
    ]
    assert [e["event_type"] for _s, e in impact_ranking(events)] == ["war_declared", "war"]
    records = [{"prompt": "x" * 400, "system": "", "event_ids": ["1:w:0", "2:w:0"],
                "shown_event_ids": ["1:w:0"], "event_types": ["war_declared", "war"]}]
    out = summarize(records, {"events_timeline": events, "named_events": []}, top=5)
    assert out["turning_points"] == 1 and out["turning_points_listed"] == 1
    assert out["tokens_max_est"] == 100 and out["event_lines"] == 1


def test_narration_identity_ignores_only_the_narration(tmp_path):
    import json

    from scripts.narration_identity import compare

    for side, text in (("base", "old prose"), ("new", "new prose")):
        d = tmp_path / side
        d.mkdir()
        (d / "chronicle.md").write_text(text)
        (d / "state.json").write_text('{"turn": 3}')
        bundle = {"metadata": {"generated_at": side}, "events_timeline": [], "history": [],
                  "chronicle_entries": [{"narrative": text}], "gap_summaries": []}
        (d / "chronicle_bundle.json").write_text(json.dumps(bundle))
    checked, problems = compare(tmp_path / "base", tmp_path / "new")
    assert checked == 2 and problems == []
    (tmp_path / "new" / "state.json").write_text('{"turn": 4}')
    checked, problems = compare(tmp_path / "base", tmp_path / "new")
    assert len(problems) == 1 and problems[0].startswith("differs: state.json")
