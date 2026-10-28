"""In-world historiography (chronicler.historiography): chroniclers, archives,
biased accounts, contested accounts, narration, persistence, and the proof
that the layer changes no simulation output."""
from __future__ import annotations

import argparse
import ast
import json
import random
import shutil
from pathlib import Path

import pytest

import chronicler.historiography as H
from chronicler.curator import curate
from chronicler.governance_state import CivGovernance
from chronicler.llm import MechanicalClient
from chronicler.main import _build_parser, execute_run
from chronicler.memory import MemoryStream
from chronicler.models import (
    BattleRecord,
    Disposition,
    Event,
    FactionType,
    Infrastructure,
    InfrastructureType,
    TreatyRecord,
    WorldState,
)

ROOT = Path(__file__).resolve().parents[1]

try:
    from chronicler_agents import AgentSimulator  # noqa: F401
    HAS_RUST = True
except ImportError:
    HAS_RUST = False


# ---------------------------------------------------------------------------
# Hand-built worlds: two or three civs, each with its capital
# ---------------------------------------------------------------------------


@pytest.fixture
def world(make_world):
    w = make_world(num_civs=3)
    for civ, region in zip(w.civilizations, w.regions):
        civ.capital_region = region.name
    for name, inner in w.relationships.items():
        for other, rel in inner.items():
            rel.disposition = Disposition.NEUTRAL
    H.set_historiography_enabled(w, True)
    return w


def _ev(w, etype, actors, desc="", *, importance=7, causes=(), region=None, n=0, **kw):
    ev = Event(turn=w.turn, event_type=etype, actors=list(actors), description=desc,
               importance=importance, event_id=f"{w.turn}:{etype}:{n}", causes=list(causes),
               region=region, **kw)
    w.events_timeline.append(ev)
    return ev


def _end_turn(w):
    w.turn += 1
    H.observe_turn(w)


def _acc(w, chron, ev):
    return H.state_of(w) and next(
        (a for a in H.state_of(w).accounts if a.account_id == f"{chron}/{ev.event_id}"), None)


def _kinds(acc):
    return sorted(t.kind for t in acc.transforms)


def _battle(w, attacker, defender, winner, a_loss, d_loss, *, region=None, name="The Fight for X"):
    a, d = w.civilizations[attacker].name, w.civilizations[defender].name
    region = region or w.regions[defender].name
    w.war_state.battles.append(BattleRecord(
        turn=w.turn, name=name, kind="field", region=region, war_key=f"{a}|{d}",
        attacker=a, defender=d, attacker_soldiers=10, defender_soldiers=10,
        attacker_power=10, defender_power=10, attacker_losses=a_loss, defender_losses=d_loss,
        winner=None if winner is None else w.civilizations[winner].name))
    outcome = ("stalemate" if winner is None else
               "attacker_wins" if winner == attacker else "defender_wins")
    return _ev(w, "war", [a, d], f"{name}: {a} (10) vs {d} (10) at {region}: {outcome}. "
               f"Losses {a_loss}/{d_loss}.", region=region)


def _loyal(civ):
    civ.governance = CivGovernance(ruler_legitimacy=0.9)


def _disaffected(civ):
    civ.governance = CivGovernance(ruler_legitimacy=0.1)


# ---------------------------------------------------------------------------
# Bias rules
# ---------------------------------------------------------------------------


def test_victor_inflates_and_loser_minimizes_a_recorded_battle(world, monkeypatch):
    monkeypatch.setattr(H, "OMIT_DEFEAT", (0.0, 0.0))  # the loser's court always tells it
    _loyal(world.civilizations[0])
    ev = _battle(world, 0, 1, winner=0, a_loss=2, d_loss=6)
    _end_turn(world)
    win, lose = _acc(world, "court:0", ev), _acc(world, "court:1", ev)
    assert win.stance == "victory" and lose.stance == "defeat"
    inflate = next(t for t in win.transforms if t.kind == "inflate")
    assert inflate.detail["true"] == 6 and inflate.detail["claimed"] > 6
    assert "praise" in _kinds(win) and world.civilizations[0].leader.name in win.text
    minimize = next(t for t in lose.transforms if t.kind == "minimize")
    assert minimize.detail["true"] == 6 and minimize.detail["claimed"] < 6
    assert str(inflate.detail["claimed"]) in win.text
    # Every account tells the real event; the third civ was not there.
    assert all(a.event_id == ev.event_id for a in H.state_of(world).accounts)
    assert _acc(world, "court:2", ev) is None


def test_loyal_court_omits_a_defeat_and_the_omission_is_recorded(world, monkeypatch):
    monkeypatch.setattr(H, "OMIT_DEFEAT", (1.0, 0.0))
    _loyal(world.civilizations[1])
    ev = _battle(world, 0, 1, winner=0, a_loss=1, d_loss=5)
    _end_turn(world)
    lose = _acc(world, "court:1", ev)
    assert lose.text == "" and _kinds(lose) == ["omit"] and lose.cited == []
    assert H.state_of(world).counts["omitted"] == 1


def test_stalemate_claimed_as_victory_by_a_zealous_court(world, monkeypatch):
    monkeypatch.setattr(H, "CLAIM_STALEMATE_ZEAL", 0.0)
    ev = _battle(world, 0, 1, winner=None, a_loss=2, d_loss=2)
    _end_turn(world)
    for chron in ("court:0", "court:1"):
        acc = _acc(world, chron, ev)
        claim = next(t for t in acc.transforms if t.kind == "claim")
        assert claim.detail == {"true": "stalemate", "claimed": "victory"}
        assert "held the field" in acc.text


def test_blame_names_an_enemy_deed_from_the_cause_graph_not_the_true_cause(world):
    a, b = world.civilizations[0].name, world.civilizations[1].name
    world.relationships[b][a].disposition = Disposition.HOSTILE
    declared = _ev(world, "war_declared", [a, b], f"{a} goes to war with {b}.")
    _end_turn(world)
    occupied = _ev(world, "occupation", [a, b], f"{world.regions[1].name} is occupied.",
                   causes=[declared.event_id], region=world.regions[2].name)
    _end_turn(world)
    shortage = _ev(world, "famine", [b], "Famine strikes.", importance=8,
                   causes=[occupied.event_id], region=world.regions[1].name)
    _end_turn(world)
    acc = _acc(world, "court:1", shortage)
    blame = next(t for t in acc.transforms if t.kind == "blame")
    # The recorded (direct) cause is the occupation; the chronicler names the
    # war declaration instead, a real ancestor in the provenance graph.
    assert shortage.causes == [occupied.event_id]
    assert blame.detail == {"blamed": a, "cited": declared.event_id, "relation": "ancestor"}
    assert acc.cited == [declared.event_id] != shortage.causes
    assert "the fault lay with" in acc.text
    # Every cited id is an account the chronicler holds.
    assert H.state_of(world) and _acc(world, "court:1", declared).text


def test_aggressor_cites_a_held_pretext_against_its_target(world):
    a, b = world.civilizations[0].name, world.civilizations[1].name
    incident = _ev(world, "embargo", [b, a], f"{b} imposed a trade embargo on {a}.")
    _end_turn(world)
    war = _ev(world, "war_declared", [a, b], f"{a} goes to war with {b}.")
    _end_turn(world)
    acc = _acc(world, "court:0", war)
    blame = next(t for t in acc.transforms if t.kind == "blame")
    assert blame.detail["cited"] == incident.event_id and blame.detail["relation"] == "pretext"
    assert "to avenge" in acc.text
    # The victim tells it plainly.
    assert _kinds(_acc(world, "court:1", war)) == []


def test_disaster_attributed_to_divine_wrath_when_the_clergy_is_strong(world):
    civ = world.civilizations[0]
    civ.factions.influence[FactionType.CLERGY] = 0.6
    world.belief_registry = []
    from chronicler.models import Belief
    world.belief_registry.append(Belief(faith_id=0, name="Faith of Civ0", civ_origin=0,
                                        doctrines=[0, 0, 0, 0, 0]))
    civ.civ_majority_faith = 0
    _disaffected(civ)
    ev = _ev(world, "plague", [civ.name], "Plague strikes.", region=world.regions[0].name)
    _end_turn(world)
    acc = _acc(world, "court:0", ev)
    divine = next(t for t in acc.transforms if t.kind == "divine")
    assert divine.detail["target"] == "ruler" and divine.detail["who"] == civ.leader.name
    assert acc.cited == [] and "the gods were angered" in acc.text


def test_ruler_praised_by_a_loyal_court_and_condemned_by_a_disaffected_one(world):
    _loyal(world.civilizations[0])
    _disaffected(world.civilizations[1])
    glory0 = _ev(world, "cultural_work", [world.civilizations[0].name], "A masterwork.", n=0)
    unrest1 = _ev(world, "rebellion", [world.civilizations[1].name], "Rebellion.", n=0)
    _end_turn(world)
    assert "praise" in _kinds(_acc(world, "court:0", glory0))
    acc = _acc(world, "court:1", unrest1)
    assert "condemn" in _kinds(acc) and "misrule" in acc.text
    # Without governance the court reads its ruler's standing from stability.
    world.civilizations[2].governance = None
    world.civilizations[2].stability = 10
    unrest2 = _ev(world, "rebellion", [world.civilizations[2].name], "Rebellion.", n=1)
    _end_turn(world)
    assert "condemn" in _kinds(_acc(world, "court:2", unrest2))


def test_guild_events_are_chronicled_with_the_court_s_bias(world, monkeypatch):
    from chronicler.agent_movements import set_agent_movements_enabled
    from chronicler.agent_movements_state import COMMONS, GUILD, GUILD_CHARTER, Movement, Reform
    monkeypatch.setattr(H, "_unit", lambda *a: 0.99)   # a loyal court tells, not omits
    _loyal(world.civilizations[0])
    _disaffected(world.civilizations[1])
    a, b = world.civilizations[0].name, world.civilizations[1].name
    set_agent_movements_enabled(world, True)
    formed = _ev(world, "guild_founded", [a], "The masters of X form the Weavers' Guild of X",
                 importance=4)
    won = _ev(world, "guild_privilege", [a], "The Weavers' Guild of X wins the monopoly of its wares",
              importance=3)
    lost = _ev(world, "guild_privilege_lost", [b], "The Guild of Y loses a say in the city's dues",
               importance=3)
    kept = _ev(world, "guild_privilege_lost", [a], "The Weavers' Guild of X loses a say in the city's "
               "dues", importance=3, n=1)
    rising = _ev(world, "movement_founded", [b], "In Y, the Guild of Y takes up its cause against "
                 "the new dues", importance=5)
    charter = _ev(world, "movement_reform", [a], f"{a} confirms the privileges of the Weavers' Guild",
                  importance=6)
    commons = _ev(world, "movement_founded", [a], "In X, the discontented found the Levellers",
                  importance=5, n=1)
    t = world.turn
    world.agent_movements.movements = [
        Movement(name="the Guild of Y", creed=GUILD, founded_turn=t, home_region=1, target=1,
                 history=[(t, "founded", rising.event_id)]),
        Movement(name="the Weavers' Guild", creed=GUILD, founded_turn=t - 9, home_region=0, target=0,
                 history=[(t - 9, "founded", "old"), (t, "reform", charter.event_id)]),
        Movement(name="the Levellers", creed=COMMONS, founded_turn=t, home_region=0, target=0,
                 history=[(t, "founded", commons.event_id)]),
    ]
    _end_turn(world)
    assert _acc(world, "court:0", formed).stance == "glory"
    assert "praise" in _kinds(_acc(world, "court:0", formed))
    assert _acc(world, "court:0", won).stance == "glory"
    assert _acc(world, "court:0", charter).stance == "glory"
    acc = _acc(world, "court:0", kept)
    assert acc.stance == "decree" and acc.text.startswith("By the just decree of ")
    acc = _acc(world, "court:1", lost)
    assert acc.stance == "decree" and "misrule" in acc.text
    acc = _acc(world, "court:1", rising)
    assert acc.stance == "disgrace" and "condemn" in _kinds(acc)
    # Other movements' foundings keep their floor (7): not chronicled at 5.
    assert _acc(world, "court:0", commons) is None
    # A guild charter repealed is the ruler's decree too.
    repeal = _ev(world, "reform_repealed", [b], f"The ruler of {b} repeals the guild charter",
                 importance=6)
    world.agent_movements.reforms.append(Reform(kind=GUILD_CHARTER, civ=1, enacted_turn=t,
                                                repeal_event_id=repeal.event_id))
    _end_turn(world)
    assert _acc(world, "court:1", repeal).stance == "decree"
    # Without movements the guild kinds still read by type.
    world.agent_movements = None
    again = _ev(world, "guild_founded", [b], "The masters of Y form a guild", importance=4)
    _end_turn(world)
    assert _acc(world, "court:1", again).stance == "glory"


def test_peace_treaty_winner_read_from_the_treaty_record(world):
    a, b = world.civilizations[0].name, world.civilizations[1].name
    world.war_state.treaties.append(TreatyRecord(
        turn=world.turn, name="The Iron Peace", war_key=f"{a}|{b}", parties=[a, b], winner=b,
        kind="capitulation"))
    ev = _ev(world, "peace_treaty", [a, b], "The Iron Peace ends the war (capitulates): ...")
    _end_turn(world)
    assert _acc(world, "court:1", ev).stance == "victory"
    assert _acc(world, "court:0", ev).stance == "defeat"


def test_repeats_are_not_retold_within_the_window(world):
    a, b = world.civilizations[0].name, world.civilizations[1].name
    first = _ev(world, "border_incident", [a, b], importance=6)
    _end_turn(world)
    again = _ev(world, "border_incident", [a, b], importance=6)
    _end_turn(world)
    assert _acc(world, "court:0", first) is not None
    assert _acc(world, "court:0", again) is None
    world.turn += H.REPEAT_WINDOW
    later = _ev(world, "border_incident", [a, b], importance=6)
    _end_turn(world)
    assert _acc(world, "court:0", later) is not None


def test_minor_routine_and_closing_events_are_not_chronicled(world):
    name = world.civilizations[0].name
    _ev(world, "develop", [name], importance=9, n=0)
    _ev(world, "famine", [name], importance=4, n=1)
    _ev(world, "famine_ended", [name], importance=7, n=2)
    _ev(world, "famine", [name], importance=8, n=3, episode="tick")
    _end_turn(world)
    assert H.state_of(world).accounts == []


def test_temple_chronicler_sees_favour_and_wrath(world):
    from chronicler.models import Belief
    world.belief_registry = [Belief(faith_id=0, name="Faith of Civ0", civ_origin=0,
                                    doctrines=[0, 0, 0, 0, 0])]
    civ = world.civilizations[0]
    civ.civ_majority_faith = 0
    world.regions[0].infrastructure.append(Infrastructure(
        type=InfrastructureType.TEMPLES, builder_civ=civ.name, built_turn=0, faith_id=0,
        temple_prestige=3))
    _end_turn(world)  # the temple chronicler is founded
    win = _battle(world, 0, 1, winner=0, a_loss=1, d_loss=4)
    plague = _ev(world, "plague", [civ.name], "Plague.", region=world.regions[0].name)
    _end_turn(world)
    st = H.state_of(world)
    assert any(c.chronicler_id == "temple:0" for c in st.chroniclers)
    assert _acc(world, "temple:0", win).transforms[0].detail["mode"] == "favour"
    wrath = _acc(world, "temple:0", plague).transforms[0]
    assert wrath.kind == "divine" and wrath.detail["mode"] == "wrath"
    assert "the temple scribes of the Faith of Civ0" in [c.name for c in st.chroniclers]


def test_temple_archive_is_desecrated_only_with_its_own_temple(world, monkeypatch):
    from chronicler.models import Belief
    monkeypatch.setattr(H, "SURVIVAL", {**H.SURVIVAL, "desecration": 0.0})
    world.belief_registry = [Belief(faith_id=0, name="Faith of Civ0", civ_origin=0,
                                    doctrines=[0, 0, 0, 0, 0])]
    civ = world.civilizations[0]
    civ.civ_majority_faith = 0
    region = world.regions[0]
    region.infrastructure.append(Infrastructure(
        type=InfrastructureType.TEMPLES, builder_civ=civ.name, built_turn=0, faith_id=0))
    _end_turn(world)
    _ev(world, "plague", [civ.name], "Plague.", region=region.name)
    _end_turn(world)
    archive = next(a for a in H.state_of(world).archives if a.owner == "temple:0")
    _ev(world, "temple_destroyed", [], f"Temple of faith 1 replaced in {region.name}", importance=5)
    _end_turn(world)
    assert [x.cause for x in archive.losses] == ["plague"]
    _ev(world, "temple_destroyed", [], f"Temple of faith 0 replaced in {region.name}", importance=5)
    region.infrastructure[0].active = False
    _end_turn(world)
    assert [x.cause for x in archive.losses] == ["plague", "desecration"]
    assert archive.losses[-1].lost == 1
    # Without a standing temple the scribes fall silent and the archive is homeless.
    chron = next(c for c in H.state_of(world).chroniclers if c.chronicler_id == "temple:0")
    assert not chron.active and archive.region is None


# ---------------------------------------------------------------------------
# Archives
# ---------------------------------------------------------------------------


def _fill(world, civ_index, count):
    name = world.civilizations[civ_index].name
    for i in range(count):
        _ev(world, "cultural_work", [name], f"Work {i}.", n=i)
    _end_turn(world)


def test_a_sack_of_the_capital_destroys_part_of_the_archive(world, monkeypatch):
    monkeypatch.setattr(H, "SURVIVAL", {**H.SURVIVAL, "sack": 0.0})
    _fill(world, 1, 5)
    a, b = world.civilizations[0].name, world.civilizations[1].name
    sack = _ev(world, "occupation", [a, b], "Taken.", region=world.regions[1].name)
    _end_turn(world)
    st = H.state_of(world)
    archive = next(x for x in st.archives if x.owner == "court:1")
    assert archive.losses[-1].cause == "sack" and archive.losses[-1].event_id == sack.event_id
    lost = [x for x in st.accounts if x.chronicler == "court:1" and x.lost_turn is not None]
    assert len(lost) == archive.losses[-1].lost >= 5
    assert all(x.lost_cause == "sack" for x in lost)
    # The occupier's own archive stands elsewhere and is untouched.
    assert not next(x for x in st.archives if x.owner == "court:0").losses


def test_survival_follows_copies_and_literacy_techniques(world, monkeypatch):
    from chronicler.techniques import set_techniques_enabled
    from chronicler.techniques_state import TECHNIQUE_INDEX
    ctx = H._Turn(world, world._historiography)
    assert ctx.copies(1) == 1  # techniques off: one copy
    set_techniques_enabled(world, True)
    world.techniques.known = [[], [TECHNIQUE_INDEX["writing"], TECHNIQUE_INDEX["printing"]], []]
    ctx = H._Turn(world, world._historiography)
    assert ctx.copies(1) == 4 and ctx.copies(0) == 1
    # Same draws, more copies: never fewer survivors.
    survivors = {}
    for copies in (1, 4):
        w = world.model_copy(deep=True)
        w._historiography = H.HistoriographySlot(H.state_of(world).model_copy(deep=True))
        if copies == 1:
            w.techniques = None
        _fill(w, 1, 12)
        a, b = w.civilizations[0].name, w.civilizations[1].name
        _ev(w, "occupation", [a, b], "Taken.", region=w.regions[1].name)
        _end_turn(w)
        st = H.state_of(w)
        assert next(x for x in st.archives if x.owner == "court:1").losses[-1].copies == copies
        survivors[copies] = {x.account_id for x in st.accounts if x.lost_turn is None and x.text}
    assert survivors[1] <= survivors[4] and len(survivors[4]) > len(survivors[1])


def test_conquest_silences_the_chronicler_and_the_victor_keeps_the_story(world, monkeypatch):
    monkeypatch.setattr(H, "SURVIVAL", {**H.SURVIVAL, "conquest": 0.0})
    a, b = world.civilizations[0].name, world.civilizations[1].name
    battle = _battle(world, 0, 1, winner=0, a_loss=1, d_loss=3)
    _end_turn(world)
    world.regions[1].controller = a
    world.civilizations[1].regions = []
    world.civilizations[0].regions.append(world.regions[1].name)
    _ev(world, "civ_conquered", [a, b], f"{b} is extinguished.", importance=9)
    _end_turn(world)
    st = H.state_of(world)
    chron = next(c for c in st.chroniclers if c.chronicler_id == "court:1")
    archive = next(x for x in st.archives if x.owner == "court:1")
    assert not chron.active and archive.region is None
    assert archive.losses[-1].cause == "conquest"
    # Contested in the bundle: the loser's version is lost; the victor's survives.
    field = H.export(world)
    item = next(c for c in field["contested"] if c["event_id"] == battle.event_id)
    assert "lost" in item["divergence"]
    index = H.AccountIndex(field)
    told = index.telling_for(battle.event_id)
    assert told.startswith("As the Civ0 chronicles tell it") and "No account from the Civ1" in told
    # Later events are no longer told by the fallen.
    later = _ev(world, "cultural_work", [b], "Nothing.")
    _end_turn(world)
    assert _acc(world, "court:1", later) is None


def test_later_chroniclers_cite_only_surviving_accounts(world, monkeypatch):
    monkeypatch.setattr(H, "SURVIVAL", {**H.SURVIVAL, "flood": 0.0})
    b = world.civilizations[1].name
    drought = _ev(world, "drought", [b], "Drought.", importance=7)
    _end_turn(world)
    _ev(world, "flood", [b], "Flood.", importance=7, region=world.regions[1].name)
    _end_turn(world)
    assert _acc(world, "court:1", drought).lost_cause == "flood"
    famine = _ev(world, "famine", [b], "Famine.", importance=8, causes=[drought.event_id])
    _end_turn(world)
    # The drought's account is gone, so the chronicler cannot name the cause.
    assert _acc(world, "court:1", famine).cited == []
    assert not world._historiography.holds("court:1", drought.event_id)


# ---------------------------------------------------------------------------
# Contested accounts and narration helpers
# ---------------------------------------------------------------------------


def test_contested_account_is_a_narratable_unit(world, monkeypatch):
    monkeypatch.setattr(H, "OMIT_DEFEAT", (0.0, 0.0))
    _loyal(world.civilizations[0])
    ev = _battle(world, 0, 1, winner=0, a_loss=2, d_loss=6, name="The Battle of Reeds")
    _end_turn(world)
    field = H.export(world)
    item = next(c for c in field["contested"] if c["event_id"] == ev.event_id)
    assert {"magnitude", "ruler"} <= set(item["divergence"])
    index = H.AccountIndex(field)
    told = index.telling_for(ev.event_id)
    assert told.startswith("As the Civ") and "Though the Civ" in told and "the Battle of Reeds" in told
    assert index.contested_bonus()[ev.event_id] == min(H.CONTESTED_CAP, len(item["divergence"]))
    block, ids = index.prompt_block([ev])
    assert "IN-WORLD ACCOUNTS" in block and len(ids) == 2
    passage, ids2 = index.passage([ev])
    assert passage.startswith("In their own words: As the") and set(ids2) == set(ids)


def test_a_lost_archive_is_told_once_per_chronicle_and_temple_losses_only_alone():
    def row(eid, chron, text="x", lost=None, stance="victory"):
        return [eid, chron, 1, stance, [], [], text, lost, "sack" if lost else None]

    field = {
        "chroniclers": [{"id": "court:0", "name": "the A chronicles"},
                        {"id": "court:1", "name": "the B chronicles"},
                        {"id": "temple:0", "name": "the temple scribes of the Faith of A"}],
        "archives": [{"owner": "court:1", "losses": [
            {"turn": 5, "cause": "sack", "region_name": "Reeds", "event_id": "5:occupation:0"}]}],
        "account_columns": list(H.ACCOUNT_COLUMNS),
        "accounts": [row("1:war:0", "court:0"), row("1:war:0", "court:1", lost=5),
                     row("2:war:0", "court:0"), row("2:war:0", "court:1", lost=5),
                     row("3:famine:0", "court:0", stance="disaster"),
                     row("3:famine:0", "temple:0", lost=5, stance="disaster")],
        "contested": [{"event_id": "1:war:0", "divergence": ["lost"]},
                      {"event_id": "2:war:0", "divergence": ["lost"]}],
    }
    index = H.AccountIndex(field)
    ev = lambda eid: Event(turn=1, event_type=eid.split(":")[1], actors=[], description="d", event_id=eid)
    noted: set[str] = set()
    first, ids1 = index.passage([ev("1:war:0")], noted=noted)
    second, ids2 = index.passage([ev("2:war:0")], noted=noted)
    assert "No account from the B chronicles survives: their archive at Reeds was sacked (turn 5)." in first
    assert "No account" not in second and "court:1/2:war:0" not in ids2
    assert ids1 == ["court:0/1:war:0", "court:1/1:war:0"]
    famine, _ = index.passage([ev("3:famine:0")])
    assert "temple scribes" not in famine  # a surviving court voice: the temple loss is not noted


def test_divergence_kinds():
    plain = {"chronicler": "court:0", "stance": "neutral", "transforms": [], "text": "x", "cited": []}
    silent = {**plain, "chronicler": "court:1", "text": "", "transforms": [{"kind": "omit", "detail": {}}]}
    assert H.divergence([plain, silent]) == ["silence"]
    lost = {**plain, "chronicler": "court:1", "lost_turn": 3}
    assert H.divergence([plain, lost]) == ["lost"]
    win = {**plain, "stance": "victory"}
    assert "outcome" in H.divergence([win, {**win, "chronicler": "court:1"}])
    blamer = {**plain, "chronicler": "court:1",
              "transforms": [{"kind": "blame", "detail": {"blamed": "A", "cited": "1:x:0"}}]}
    assert H.divergence([plain, blamer]) == ["blame"]
    assert H.divergence([plain, {**plain, "chronicler": "court:1"}]) == []


def test_curator_contested_bonus_is_optional_and_only_adds(world):
    events = []
    for t in range(0, 40, 8):
        events.append(Event(turn=t, event_type="cultural_work", actors=["Civ0"], description=f"w{t}",
                            importance=5, event_id=f"{t}:cultural_work:0"))
    base = curate(events, [], [], budget=2, seed=1)
    assert curate(events, [], [], budget=2, seed=1, contested=None) == base
    assert curate(events, [], [], budget=2, seed=1, contested={}) == base
    boosted = curate(events, [], [], budget=2, seed=1, contested={"32:cultural_work:0": 3.0})
    assert any(m.anchor_turn == 32 for m in boosted[0])


def test_short_names_and_labels():
    assert H.short_name("Kethani Empire") == "Kethani"
    assert H.short_name("Upper Selurian Republic") == "Upper Selurian"
    assert H.short_name("Free Verdant Plains") == "Free Verdant Plains"
    assert H.faith_display("Faith of Thornwall Confederacy") == "the Faith of Thornwall"
    ev = Event(turn=3, event_type="proxy_detected", actors=["A", "B"], description="")
    assert H._label(ev) == "The agents of A are unmasked in B"


# ---------------------------------------------------------------------------
# Observation is read-only and draws no simulation randomness
# ---------------------------------------------------------------------------


def test_observation_reads_only(world, monkeypatch):
    import numpy as np
    monkeypatch.setattr(H, "OMIT_DEFEAT", (0.5, 0.5))
    a, b = world.civilizations[0].name, world.civilizations[1].name
    _battle(world, 0, 1, winner=0, a_loss=1, d_loss=2)
    _ev(world, "occupation", [a, b], "Taken.", region=world.regions[1].name)
    world.turn += 1
    before = world.model_dump_json()
    py_state, np_state = random.getstate(), np.random.get_state()
    caches = (world._region_map, world._civ_map, world._civ_index_map, world._history_index,
              world._active_trade_routes_cache)
    H.observe_turn(world)
    assert world.model_dump_json() == before
    assert random.getstate() == py_state
    assert all((x == y).all() if hasattr(x, "all") else x == y
               for x, y in zip(np.random.get_state(), np_state))
    assert (world._region_map, world._civ_map, world._civ_index_map, world._history_index,
            world._active_trade_routes_cache) == caches == (None, None, None, None, None)
    assert H.state_of(world).accounts


def test_no_simulation_module_imports_historiography():
    # narration_inputs.py reads saved bundles for --narrate and live range narration;
    # narration_provenance.py names the chroniclers' civs and faiths for narration.
    # history_forensics.py is a read-only bundle inspector, not a simulation module.
    allowed = {"main.py", "models.py", "live.py", "historiography.py", "narration_inputs.py",
               "narration_provenance.py", "history_forensics.py"}
    importers = []
    for path in sorted((ROOT / "src" / "chronicler").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                     else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            if any("historiography" in n for n in names):
                importers.append(path.name)
    assert set(importers) <= allowed, importers
    # The module itself draws nothing from the random or numpy streams.
    tree = ast.parse((ROOT / "src/chronicler/historiography.py").read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"random", "numpy"}


def test_slot_is_equality_neutral_and_copies_carry_the_state(world):
    other = world.model_copy(deep=True)
    other._historiography = None
    assert world == other
    clone = world.model_copy(deep=True)
    assert isinstance(clone._historiography, H.HistoriographySlot)
    assert clone._historiography.state is not world._historiography.state
    assert clone._historiography.state == world._historiography.state
    import pickle
    assert pickle.loads(pickle.dumps(world._historiography)).state == world._historiography.state
    assert "historiography" not in world.model_dump_json()


# ---------------------------------------------------------------------------
# Persistence: sidecar, old saves, resume identity
# ---------------------------------------------------------------------------


def test_sidecar_round_trip_and_stale_or_missing_sidecars(world, tmp_path):
    _fill(world, 0, 3)
    path = tmp_path / "state.json"
    world.save(path)
    assert H.sidecar_path(path) == tmp_path / "state.historiography.json"
    assert H.sidecar_path(path).exists()
    loaded = WorldState.load(path)
    assert H.state_of(loaded) == H.state_of(world)
    # The state file itself carries nothing of it.
    assert "historiography" not in path.read_text()
    # Old saves (no sidecar) load with the layer off.
    H.sidecar_path(path).unlink()
    assert H.state_of(WorldState.load(path)) is None
    # A sidecar from another turn is not trusted: chronicles restart.
    world.save(path)
    world.turn += 5
    world.save(tmp_path / "later.json")
    shutil.copy(tmp_path / "state.historiography.json", tmp_path / "later.historiography.json")
    restarted = WorldState.load(tmp_path / "later.json")
    assert H.state_of(restarted).accounts == [] and H.state_of(restarted).enabled_turn == world.turn
    # Saving with the layer off removes a stale sidecar.
    H.set_historiography_enabled(world, False)
    world.save(path)
    assert not H.sidecar_path(path).exists()


@pytest.fixture
def pure_python(monkeypatch):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


def _args(folder: Path, turns: int, **kw):
    args = argparse.Namespace(
        seed=42, turns=turns, civs=3, regions=6,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="off",
    )
    for key, value in kw.items():
        setattr(args, key, value)
    return args


def _bundle(folder: Path) -> dict:
    return json.loads((folder / "chronicle_bundle.json").read_text())


def _sim_view(bundle: dict) -> dict:
    out = {k: v for k, v in bundle.items() if k not in H_NARRATION}
    out["metadata"] = {k: v for k, v in bundle["metadata"].items() if k != "generated_at"}
    return out


H_NARRATION = ("historiography", "chronicle_entries", "gap_summaries", "narration_provenance")


def test_resume_from_a_checkpoint_continues_the_chronicles_identically(tmp_path, pure_python):
    full, part = tmp_path / "full", tmp_path / "part"
    copy_at = tmp_path / "at8"

    def hook(snapshot, text, events, named):
        if snapshot.turn == 9:
            shutil.copytree(full, copy_at)

    full.mkdir()
    execute_run(_args(full, 24, state_every=4), on_turn=hook)
    shutil.copytree(copy_at, part)
    world = WorldState.load(part / "state.json")
    assert world.turn == 8 and H.historiography_on(world)
    memories = {}
    for f in part.glob("memories_*.json"):
        stream = MemoryStream.load(f)
        memories[stream.civilization_name] = stream
    execute_run(_args(part, 24, state_every=4), world=world, memories=memories)
    assert (part / "state.historiography.json").read_bytes() == (full / "state.historiography.json").read_bytes()
    assert _bundle(part)["historiography"] == _bundle(full)["historiography"]
    assert (part / "state.json").read_bytes() == (full / "state.json").read_bytes()
    assert H.state_of(WorldState.load(full / "state.json")).accounts


def test_flag_on_changes_no_simulation_output(tmp_path, pure_python):
    """The outcome-neutral proof in the suite: state, snapshots, events, memories."""
    runs = {}
    for flag in (False, True):
        folder = tmp_path / ("on" if flag else "off")
        folder.mkdir()
        snaps = []
        execute_run(_args(folder, 40, historiography=flag, narrator="mechanical"),
                    narrative_client=MechanicalClient(),
                    on_turn=lambda s, t, e, n: snaps.append(s.model_dump_json()))
        runs[flag] = (folder, snaps)
    (off, off_snaps), (on, on_snaps) = runs[False], runs[True]
    assert on_snaps == off_snaps
    files_off = sorted(p.name for p in off.iterdir())
    files_on = sorted(p.name for p in on.iterdir())
    assert files_on == sorted(files_off + ["state.historiography.json"])
    for name in files_off:
        if name in ("chronicle_bundle.json", "chronicle.md"):
            continue
        assert (on / name).read_bytes() == (off / name).read_bytes(), name
    b_on, b_off = _bundle(on), _bundle(off)
    assert _sim_view(b_on) == _sim_view(b_off)
    assert "historiography" not in b_off and b_on["historiography"]["accounts"]
    # Narration differs: the flag-on chronicle tells the accounts.
    assert all("accounts" not in e for e in b_off["chronicle_entries"])
    assert any(e.get("accounts") for e in b_on["chronicle_entries"])
    assert "In their own words" not in (off / "chronicle.md").read_text()
    assert "In their own words" in (on / "chronicle.md").read_text()
    # Provenance: every account and every cited cause is a real event.
    events = {e["event_id"] for e in b_on["events_timeline"] if e.get("event_id")}
    field = b_on["historiography"]
    for raw in field["accounts"]:
        row = H.row_dict(raw)
        assert row["event_id"] in events and set(row["cited"]) <= events
        for tr in row["transforms"]:
            if tr["kind"] == "blame":
                assert tr["detail"]["cited"] in events
    ids = {H.row_dict(r)["account_id"] for r in field["accounts"]}
    ids |= {f"{c}/{e}" for c, eids in field["plain"].items() for e in eids}
    for entry in b_on["chronicle_entries"]:
        assert set(entry.get("accounts", [])) <= ids


def test_flag_off_never_runs_the_layer(tmp_path, pure_python, monkeypatch):
    """--no-historiography runs no historiography code and writes what a
    default-off build writes (the base comparison is scripts/historiography_identity.py)."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()

    def forbidden(*args, **kwargs):
        raise AssertionError("historiography ran while off")

    with monkeypatch.context() as m:
        m.setattr(H, "observe_turn", forbidden)
        m.setattr(H, "export", forbidden)
        m.setattr(H.AccountIndex, "__init__", forbidden)
        execute_run(_args(a, 12, historiography=False, narrator="mechanical"),
                    narrative_client=MechanicalClient())
        m.setattr(H, "DEFAULT_ENABLED_FOR_NEW_WORLDS", False)
        execute_run(_args(b, 12, narrator="mechanical"), narrative_client=MechanicalClient())
    for name in sorted(p.name for p in a.iterdir()):
        if name == "chronicle_bundle.json":
            assert _bundle(a) | {"metadata": None} == _bundle(b) | {"metadata": None}
        else:
            assert (a / name).read_bytes() == (b / name).read_bytes(), name
    assert not (a / "state.historiography.json").exists()
    assert "historiography" not in _bundle(a)
    assert all("accounts" not in e for e in _bundle(a)["chronicle_entries"])


def test_runs_are_deterministic(tmp_path, pure_python):
    outs = []
    for k in range(2):
        folder = tmp_path / f"r{k}"
        folder.mkdir()
        execute_run(_args(folder, 30))
        outs.append((folder / "state.historiography.json").read_bytes())
    assert outs[0] == outs[1]


def test_mechanical_chronicle_tells_the_accounts(tmp_path, pure_python):
    folder = tmp_path / "m"
    folder.mkdir()
    execute_run(_args(folder, 40, narrator="mechanical"), narrative_client=MechanicalClient())
    text = (folder / "chronicle.md").read_text()
    bundle = _bundle(folder)
    assert "In their own words:" in text
    assert any(e.get("accounts") for e in bundle["chronicle_entries"])


def test_narrate_bundle_uses_the_field_when_present(tmp_path, pure_python):
    from chronicler.main import _run_narrate
    folder = tmp_path / "n"
    folder.mkdir()
    execute_run(_args(folder, 40))
    for flag, expect in ((None, True), (False, False)):
        out = tmp_path / f"narrated_{flag}.json"
        args = _build_parser().parse_args(["--narrate", str(folder / "chronicle_bundle.json"),
                                           "--narrator", "mechanical", "--narrate-output", str(out)])
        args.historiography = flag
        _run_narrate(args)
        entries = json.loads(out.read_text())["chronicle_entries"]
        assert any("In their own words" in e["narrative"] for e in entries) is expect
    # An old bundle without the field narrates as before.
    bundle = _bundle(folder)
    bundle.pop("historiography")
    old = tmp_path / "old_bundle.json"
    old.write_text(json.dumps(bundle))
    args = _build_parser().parse_args(["--narrate", str(old), "--narrator", "mechanical",
                                       "--narrate-output", str(tmp_path / "old.json")])
    _run_narrate(args)
    assert H.AccountIndex.from_bundle(bundle) is None


def test_prompt_gains_the_accounts_block_only_with_an_index(tmp_path, pure_python):
    from chronicler.narrative import NarrativeEngine
    folder = tmp_path / "p"
    folder.mkdir()
    execute_run(_args(folder, 40))
    bundle = _bundle(folder)
    events = [Event.model_validate(e) for e in bundle["events_timeline"]]
    moments, _ = curate(events, [], [], budget=8, seed=42)
    engine = NarrativeEngine(MechanicalClient(), MechanicalClient())
    index = H.AccountIndex.from_bundle(bundle)
    engine._accounts = None
    plain = engine._prepare_narration_prompts(moments, [])
    engine._accounts = index
    rich = engine._prepare_narration_prompts(moments, [])
    assert not any("IN-WORLD ACCOUNTS" in p["prompt"] for p in plain)
    assert any("IN-WORLD ACCOUNTS" in p["prompt"] for p in rich)
    assert all(p["prompt"].startswith(q["prompt"].split("\n\nIN-WORLD")[0][:200])
               for p, q in zip(rich, plain))


def test_cli_flag_and_gate_forwarding():
    parser = _build_parser()
    assert parser.parse_args([]).historiography is None
    assert parser.parse_args(["--historiography"]).historiography is True
    assert parser.parse_args(["--no-historiography"]).historiography is False
    import importlib.util
    spec = importlib.util.spec_from_file_location("m53b", ROOT / "scripts/m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._historiography_args(argparse.Namespace(historiography=None)) == []
    assert m53b._historiography_args(argparse.Namespace(historiography=False)) == ["--no-historiography"]


def test_resumed_world_keeps_its_setting_and_can_switch(tmp_path, pure_python):
    folder = tmp_path / "s"
    folder.mkdir()
    execute_run(_args(folder, 6, historiography=False))
    world = WorldState.load(folder / "state.json")
    assert not H.historiography_on(world)
    # --historiography on resume starts the chronicles at the resume turn.
    execute_run(_args(folder, 10, historiography=True), world=world)
    st = H.state_of(WorldState.load(folder / "state.json"))
    assert st.enabled_turn == 6 and all(a.turn >= 6 for a in st.accounts)


def test_bundle_without_the_field_is_unchanged(world):
    from chronicler.bundle import assemble_bundle
    kwargs = dict(world=world, history=[], chronicle_entries=[], era_reflections={},
                  sim_model="s", narrative_model="n", interestingness_score=None)
    plain = assemble_bundle(**kwargs)
    assert "historiography" not in plain
    with_field = assemble_bundle(**kwargs, historiography={"version": 1})
    assert list(with_field)[-1] == "historiography"
    assert {k: v for k, v in with_field.items() if k != "historiography"} | {"metadata": None} \
        == plain | {"metadata": None}


@pytest.mark.skipif(not HAS_RUST, reason="Rust crate not built")
def test_native_hybrid_run_is_outcome_identical_with_the_flag(tmp_path):
    outs = {}
    for flag in (False, True):
        folder = tmp_path / str(flag)
        folder.mkdir()
        execute_run(_args(folder, 20, agents="hybrid", historiography=flag))
        outs[flag] = folder
    for name in ("state.json", "agent_events.arrow"):
        assert (outs[True] / name).read_bytes() == (outs[False] / name).read_bytes()
    assert _sim_view(_bundle(outs[True])) == _sim_view(_bundle(outs[False]))


# ---------------------------------------------------------------------------
# The frozen exact-trajectory oracles, with the layer switched on
# ---------------------------------------------------------------------------

_FIXTURES = ROOT / "tests" / "fixtures" / "performance"


def _frozen():
    # The live oracle: the 2026-10 population corrections rolled every
    # trajectory forward from the procedural open-item fixtures
    # (docs/integration/population-entities.md).
    baseline = json.loads((_FIXTURES / "corrected_population_2026_10.json").read_text())
    artifacts = json.loads((_FIXTURES / "corrected_artifacts_population_2026_10.json").read_text())
    return baseline, artifacts


@pytest.mark.parametrize("name", sorted(_frozen()[0]["workloads"]))
def test_frozen_oracles_hold_with_historiography_on(name, tmp_path, monkeypatch):
    """Every turn's snapshot, events and narration hash, the ordered RNG trace
    and every artifact byte match the frozen corrected oracle with chronicles
    kept; the only additions are the bundle field and the state sidecar."""
    import hashlib
    from scripts.benchmark_headless import rng_trace, run
    from scripts.third_wave_controls import legacy_artifact_bytes, legacy_event_dump
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.provenance.LEGACY_TIMELINE", True)
    baseline, artifacts = _frozen()
    expected = baseline["workloads"][name]
    turns = []

    def capture(snapshot, text, events, named):
        data = [snapshot.model_dump(mode="json"), text,
                [legacy_event_dump(event) for event in events],
                [event.model_dump(mode="json") for event in named]]
        turns.append(hashlib.sha256(json.dumps(
            data, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest())

    out = tmp_path / "artifacts"
    with rng_trace(tmp_path / "rng.jsonl") as trace:
        run({**expected["spec"], "historiography": True}, out, on_turn=capture)
    assert turns == expected["turn_sha256"]
    assert trace == expected["rng"]
    sidecar = out / "state.historiography.json"
    assert H.state_of(WorldState.load(out / "state.json")).accounts
    bundle = json.loads((out / "chronicle_bundle.json").read_bytes())
    assert bundle.pop("historiography")["accounts"]
    stripped = tmp_path / "stripped"
    stripped.mkdir()
    (stripped / "chronicle_bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    emitted = {}
    for path in sorted(out.iterdir()):
        if not path.is_file() or path == sidecar:
            continue
        source = stripped / path.name if path.name == "chronicle_bundle.json" else path
        data = legacy_artifact_bytes(source)
        if path.name not in ("state.json", "chronicle_bundle.json"):
            data = data.replace(b"\r\n", b"\n")
        emitted[path.name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    assert emitted == artifacts["workloads"][name]
