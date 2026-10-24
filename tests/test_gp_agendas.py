"""Great-person agendas (``chronicler.gp_agendas``, ``--gp-agendas``).

Kernel extension (the M66b ruler-ambition kernel resolves every agenda),
each role's lifecycle, evidence completion and failure, the coup path,
bonds and succession backing, the action-weight bucket, transient-signal
reset, persistence, determinism and flag-off dormancy.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pytest

import chronicler.gp_agendas as G
from chronicler import provenance as prov
from chronicler import ruler_ambitions as g04
from chronicler.action_engine import ActionEngine
from chronicler.gp_agendas_state import GPAgendaState
from chronicler.models import (
    ActionType, Disposition, Event, FactionType, GreatPerson, TechEra, TurnSnapshot, WorldState,
)
from chronicler.simulation import run_turn
from chronicler.turn_artifacts import AgentRows, Stamp
from chronicler.world_gen import generate_world

T = g04.AmbitionType
ROOT = Path(__file__).resolve().parents[1]

# Seed-42 template world: 0 Ashkari Nomads (Obsidian Shore), 1 Kethani Empire
# (Amber Valley, Frostholm Tundra), 2 Thornwall Confederacy (Verdant Plains,
# Thornwood), 3 Selurian Republic (Ashara Desert). Kethani sees Thornwall and
# Selurian as suspicious and trades with Ashkari.
KETHANI, THORNWALL, SELURIAN, ASHKARI = 1, 2, 3, 0


def _world(seed: int = 42) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    G.set_gp_agendas_enabled(world, True)
    return world


def _gp(world, civ_idx: int, role: str, name: str, trait: str = "calculating") -> GreatPerson:
    civ = world.civilizations[civ_idx]
    gp = GreatPerson(name=name, role=role, trait=trait, civilization=civ.name,
                     origin_civilization=civ.name, born_turn=world.turn, region=civ.capital_region)
    civ.great_persons.append(gp)
    return gp


def _tick(world, events=(), phase10=None, acc=None):
    return G.tick_gp_agendas(world, list(events), acc=acc, phase10=phase10)


def _next(world, events=(), phase10=None):
    world.turn += 1
    return _tick(world, events, phase10)


def _rec(world, gp):
    return world.gp_agendas.records[G.gp_key(gp)]


def _types(events):
    return [e.event_type for e in events]


def _force(monkeypatch, kind: T, target=None):
    """Restrict declarations to ``kind`` (the real pool still decides targets)."""
    real = G._raw_pool

    def only(*args, **kwargs):
        pool = real(*args, **kwargs)
        if kind not in pool:
            return {}
        targets, motive = pool[kind]
        if target is not None:
            targets = [t for t in targets if t == target]
        return {kind: (targets, motive)} if targets else {}

    monkeypatch.setattr(G, "_raw_pool", only)


def _advance(world, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def _rows(world, beliefs_by_region: dict[str, list[int]]):
    region_index = {r.name: i for i, r in enumerate(world.regions)}
    regions, beliefs = [], []
    for name, beliefs_here in beliefs_by_region.items():
        regions += [region_index[name]] * len(beliefs_here)
        beliefs += beliefs_here
    batch = pa.RecordBatch.from_pydict({
        "id": pa.array(list(range(1, len(regions) + 1)), pa.uint32()),
        "region": pa.array(regions, pa.uint16()),
        "occupation": pa.array([0] * len(regions), pa.uint8()),
        "belief": pa.array(beliefs, pa.uint8()),
    })
    return SimpleNamespace(agents=AgentRows(stamp=Stamp(world.turn, "phase10_entry"), batch=batch))


# --- kernel ----------------------------------------------------------------------------

def _snap(**changes):
    return replace(g04.AmbitionSnapshot('gp', 'gp#1', 12, 5, .5, 0.), **changes)


def _reign(ambition):
    return g04.RulerAmbitions('gp', 'gp#1', ambition.generated_turn, ambition.generated_event_cursor,
                              (ambition,))


CAL = G.CALIBRATION


def test_kinds_are_appended_after_the_ruler_types_and_never_generated_for_rulers():
    names = [k.value for k in T]
    assert names[:7] == ['conquer_region', 'build_monument', 'establish_trade', 'religious_conversion',
                         'expand_territory', 'patron_of_arts', 'diplomatic_triumph']
    assert set(T) - set(list(T)[:7]) == set(g04.GP_AGENDA_TYPES)
    snapshot = g04.AmbitionSnapshot('Civ', 'r', 7, 10, .5, .2, owned_regions=('Home',),
                                    conquerable_regions=('Border',), military_eligible=True,
                                    arts_available=True)
    config = g04.AmbitionCalibration(3, 20, 40, .1, .05, tuple((k, 1e6 if k in g04.GP_AGENDA_TYPES else 1.)
                                                               for k in T))
    for draw in (0., .5, .99):
        made = g04.generate_ambitions(snapshot, config, (g04.SelectionDraw(draw, draw, draw),) * 3)
        assert all(a.ambition_type not in g04.GP_AGENDA_TYPES for a in made)


def test_agenda_window_and_targets_are_validated():
    g04.Ambition(T.LEAD_CAMPAIGN, 'Border', 2, 12, 0)
    for bad in (lambda: g04.Ambition(T.LEAD_CAMPAIGN, 'Border', 2, 11, 0),
                lambda: g04.Ambition(T.LEAD_CAMPAIGN, 'Border', 2, 43, 0),
                lambda: g04.Ambition(T.SEIZE_THRONE, 'Throne', 2, 12, 0),
                lambda: g04.Ambition(T.FOUND_SHRINE, None, 2, 12, 0),
                lambda: g04.Ambition(T.SPREAD_FAITH, 'Home', 2, 12, 0),
                lambda: g04.Ambition(T.CONQUER_REGION, 'Border', 2, 12, 0)):  # ruler window stays 20-40
        with pytest.raises(ValueError):
            bad()


@pytest.mark.parametrize('kind,event_type,target', [
    (T.SEIZE_THRONE, 'gp_coup', None), (T.FOUND_TRADING_HOUSE, 'trading_house_founded', None),
    (T.LEND_TO_CROWN, 'crown_loan', None), (T.FOUND_SHRINE, 'infrastructure_completed', 'Home'),
    (T.ADVANCE_LEARNING, 'tech_advancement', 'bronze'), (T.INVENT_TECHNIQUE, 'technique_invented', 'masonry'),
])
def test_evidence_goals_complete_on_target_and_after_the_cursor(kind, event_type, target):
    ambition = g04.Ambition(kind, target, 2, 15, 4)
    done = g04.evaluate_ambitions(_reign(ambition), _snap(), CAL, (g04.EvidenceEvent(12, 5, 'gp', event_type, target),))
    assert done.reign.ambitions[0].completed
    stale = g04.evaluate_ambitions(_reign(ambition), _snap(), CAL, (g04.EvidenceEvent(12, 4, 'gp', event_type, target),))
    assert not stale.reign.ambitions[0].completed and not stale.outcomes
    if target is not None:
        wrong = g04.evaluate_ambitions(_reign(ambition), _snap(), CAL,
                                       (g04.EvidenceEvent(12, 5, 'gp', event_type, 'Elsewhere'),))
        assert not wrong.outcomes


def test_thwarting_evidence_fails_early_and_completion_wins_the_same_turn():
    coup = g04.Ambition(T.SEIZE_THRONE, None, 2, 15, 4)
    failed = g04.evaluate_ambitions(_reign(coup), _snap(), CAL, (g04.EvidenceEvent(12, 5, 'gp', 'gp_coup_failed'),))
    assert failed.reign.ambitions[0].failed and failed.outcomes[0].event_type == 'ambition_failed'
    both = g04.evaluate_ambitions(_reign(coup), _snap(event_cursor=6), CAL,
                                  (g04.EvidenceEvent(12, 5, 'gp', 'gp_coup_failed'),
                                   g04.EvidenceEvent(12, 6, 'gp', 'gp_coup')))
    assert both.reign.ambitions[0].completed and not both.reign.ambitions[0].failed
    gone = g04.evaluate_ambitions(_reign(g04.Ambition(T.LEAD_CAMPAIGN, 'Border', 2, 15, 4)), _snap(), CAL,
                                  (g04.EvidenceEvent(12, 5, 'gp', 'holder_gone'),))
    assert gone.reign.ambitions[0].failed
    # Ruler ambitions never fail early, whatever the evidence.
    ruler = g04.Ambition(T.BUILD_MONUMENT, 'Home', 2, 25, 4)
    kept = g04.evaluate_ambitions(_reign(ruler), _snap(), CAL, (g04.EvidenceEvent(12, 5, 'gp', 'holder_gone'),))
    assert not kept.reign.ambitions[0].failed and not kept.outcomes


def test_protect_route_is_sustained_to_the_deadline_and_broken_by_evidence():
    protect = g04.Ambition(T.PROTECT_TRADE_ROUTE, '3', 2, 15, 4)
    early = g04.evaluate_ambitions(_reign(protect), _snap(active_trade_partners=('3',)), CAL)
    assert not early.outcomes
    on_time = g04.evaluate_ambitions(_reign(protect), _snap(turn=15, active_trade_partners=('3',)), CAL)
    assert on_time.reign.ambitions[0].completed
    lapsed = g04.evaluate_ambitions(_reign(protect), _snap(turn=15), CAL)
    assert lapsed.reign.ambitions[0].failed
    broken = g04.evaluate_ambitions(_reign(protect), _snap(active_trade_partners=('3',)), CAL,
                                    (g04.EvidenceEvent(12, 5, 'gp', 'trade_route_broken', '3'),))
    assert broken.reign.ambitions[0].failed
    other = g04.evaluate_ambitions(_reign(protect), _snap(active_trade_partners=('3',)), CAL,
                                   (g04.EvidenceEvent(12, 5, 'gp', 'trade_route_broken', '2'),))
    assert not other.outcomes


# --- generals --------------------------------------------------------------------------

def test_general_vows_a_campaign_wins_renown_and_takes_the_region(monkeypatch):
    world = _world()
    _force(monkeypatch, T.LEAD_CAMPAIGN, "Ashara Desert")
    general = _gp(world, KETHANI, "general", "Marshal Tovan", trait="bold")
    declared = _tick(world)
    assert _types(declared) == ["agenda_declared"]
    assert "vows to lead a campaign to take Ashara Desert" in declared[0].description
    agenda = _rec(world, general).agenda
    assert (agenda.ambition_type, agenda.target) == ("lead_campaign", "Ashara Desert")
    assert 10 <= agenda.deadline_turn - agenda.generated_turn <= 25
    prov.observe(world, declared)
    kethani = world.civilizations[KETHANI]
    prestige = kethani.prestige
    war = Event(turn=1, event_type="war", actors=["Kethani Empire", "Selurian Republic"],
                description="Kethani Empire attacked Selurian Republic: attacker_wins.", importance=8)
    world.turn = 1
    prov.observe(world, [war])
    deeds = _tick(world, [war])
    assert _types(deeds) == ["campaign_victory"]
    assert war.event_id in deeds[0].causes and declared[0].event_id in deeds[0].causes
    assert _rec(world, general).renown == G.VICTORY_RENOWN and kethani.prestige == prestige + 1
    # The region falls to Kethani: the state predicate settles the vow.
    desert = world.region_map["Ashara Desert"]
    world.civilizations[SELURIAN].regions.remove("Ashara Desert")
    desert.controller = "Kethani Empire"
    kethani.regions.append("Ashara Desert")
    world.turn = 2
    taken = Event(turn=2, event_type="annexation", actors=["Kethani Empire", "Selurian Republic"],
                  description="Kethani Empire annexes Ashara Desert.", region="Ashara Desert")
    prov.observe(world, [taken])
    out = _tick(world, [taken])
    fulfilled = next(e for e in out if e.event_type == "agenda_fulfilled")
    assert taken.event_id in fulfilled.causes and declared[0].event_id in fulfilled.causes
    assert _rec(world, general).agenda.completed and _rec(world, general).completed == 1
    assert world.gp_agendas.counts["fulfilled:general"] == 1


def test_peacetime_general_agitates_against_the_neighbour_he_covets(monkeypatch):
    world = _world()
    kethani, ashkari = world.civilizations[KETHANI], world.civilizations[ASHKARI]
    for a, b in ((kethani, world.civilizations[THORNWALL]), (kethani, world.civilizations[SELURIAN])):
        world.relationships[a.name][b.name].disposition = Disposition.FRIENDLY
    general = _gp(world, KETHANI, "general", "Marshal Tovan", trait="bold")
    _force(monkeypatch, T.LEAD_CAMPAIGN)
    _tick(world)
    assert _rec(world, general).agenda.target == "Obsidian Shore"  # a neutral neighbour's land
    monkeypatch.setattr(G, "AGITATION_P", 1.0)
    out = _next(world)
    assert _types(out) == ["war_agitation"]
    assert world.relationships[kethani.name][ashkari.name].disposition == Disposition.SUSPICIOUS
    # A cautious general does not covet a neutral neighbour.
    calm = _world()
    for name in ("Thornwall Confederacy", "Selurian Republic"):
        calm.relationships["Kethani Empire"][name].disposition = Disposition.FRIENDLY
    _gp(calm, KETHANI, "general", "Marshal Ivo", trait="cautious")
    assert _tick(calm) == []


def test_a_road_soured_by_a_generals_agitation_cites_it(monkeypatch):
    world = _world()
    for name in ("Thornwall Confederacy", "Selurian Republic"):
        world.relationships["Kethani Empire"][name].disposition = Disposition.FRIENDLY
    _gp(world, KETHANI, "general", "Marshal Tovan", trait="bold")
    merchant = _gp(world, KETHANI, "merchant", "Factor Oda")
    real = G._raw_pool

    def pool(*args, **kwargs):
        full = real(*args, **kwargs)
        wanted = T.LEAD_CAMPAIGN if args[5].role == "general" else T.PROTECT_TRADE_ROUTE
        return {wanted: full[wanted]} if wanted in full else {}

    monkeypatch.setattr(G, "_raw_pool", pool)
    _tick(world)
    assert _rec(world, merchant).agenda.target == str(ASHKARI)
    monkeypatch.setattr(G, "AGITATION_P", 1.0)
    monkeypatch.setattr(G, "INTERCEDE_P", 0.0)
    out = _next(world)
    agitation = next(e for e in out if e.event_type == "war_agitation")
    failed = next(e for e in out if e.event_type == "agenda_failed")
    assert "the trade road was cut" in failed.description
    assert prov.ensure_id(world, agitation) in failed.causes


def _plot(world, monkeypatch, *, grievance: bool = True):
    """A renowned general of Kethani under a weak ruler declares a coup."""
    monkeypatch.setattr(G, "_campaign_targets", lambda *a, **k: [])
    kethani = world.civilizations[KETHANI]
    world.turn = 10
    kethani.stability = 20
    kethani.factions.influence[FactionType.MILITARY] = 0.4
    general = _gp(world, KETHANI, "general", "Marshal Tovan", trait="bold")
    G.set_gp_agendas_enabled(world, True)
    rec = G.AgendaRecord(gp_name=general.name, born_turn=general.born_turn, role="general", civ=KETHANI,
                         renown=3)
    world.gp_agendas.records[G.gp_key(general)] = rec
    if grievance:
        world.provenance.keys[prov.key("legitimacy", kethani.name)] = "8:legitimacy_crisis:0"
    out = _tick(world)
    return general, out


def test_coup_cites_its_grievance_and_puts_the_general_on_the_throne(monkeypatch):
    world = _world()
    kethani = world.civilizations[KETHANI]
    old_ruler = kethani.leader.name
    general, declared = _plot(world, monkeypatch)
    assert _types(declared) == ["agenda_declared", "gp_rivalry_formed"]
    assert "8:legitimacy_crisis:0" in declared[0].causes
    assert _rec(world, general).agenda.ambition_type == "seize_throne"
    prov.observe(world, declared)
    monkeypatch.setattr(G, "COUP_ATTEMPT_P", 1.0)
    monkeypatch.setattr(G, "COUP_SUCCESS_RANGE", (1.0, 1.0))
    out = _next(world)
    coup = next(e for e in out if e.event_type == "gp_coup")
    assert declared[0].event_id in coup.causes and "8:legitimacy_crisis:0" in coup.causes
    assert kethani.leader.succession_type == "general"
    assert "Tovan" in kethani.leader.name and kethani.leader.trait == "bold"
    assert kethani.leader.predecessor_name == old_ruler
    assert general.fate == "ascended_to_leadership" and general not in kethani.great_persons
    assert any(ne.event_type == "coup" for ne in world.named_events)
    assert any(gp.role == "exile" and gp.name == old_ruler for c in world.civilizations
               for gp in c.great_persons)
    fulfilled = next(e for e in out if e.event_type == "agenda_fulfilled")
    assert prov.ensure_id(world, coup) in fulfilled.causes
    assert world.gp_agendas.counts["coups"] == 1
    # Next turn the departed holder's record is retired quietly.
    _next(world)
    assert G.gp_key(general) not in world.gp_agendas.records


def test_coup_without_a_grievance_cites_the_generals_ambition(monkeypatch):
    world = _world()
    general_key = "Marshal Tovan|10"
    world.provenance.keys[prov.key("gp_agenda_done", general_key)] = "9:agenda_fulfilled:0"
    general, declared = _plot(world, monkeypatch, grievance=False)
    assert G.gp_key(general) == general_key
    assert "9:agenda_fulfilled:0" in declared[0].causes


def test_coup_without_grievance_or_ambition_cites_the_realms_distress(monkeypatch):
    world = _world()
    world.active_wars.append(("Kethani Empire", "Thornwall Confederacy"))
    world.provenance.keys[prov.war_key("Kethani Empire", "Thornwall Confederacy")] = "3:war_declared:0"
    general, declared = _plot(world, monkeypatch, grievance=False)
    assert "3:war_declared:0" in declared[0].causes


def test_crushed_coup_kills_the_general_and_credits_the_loyalist(monkeypatch):
    world = _world()
    kethani = world.civilizations[KETHANI]
    loyal = _gp(world, KETHANI, "merchant", "Banker Ilse")
    world.gp_agendas.records[G.gp_key(loyal)] = G.AgendaRecord(
        gp_name=loyal.name, born_turn=0, role="merchant", civ=KETHANI, next_turn=99)
    world.gp_agendas.bonds.append(G.AgendaBond(kind="loyalty", a=G.gp_key(loyal), b="ruler:1", civ=KETHANI,
                                               ruler=kethani.leader.name, formed_turn=0, event_id="0:x:0"))
    ruler = kethani.leader.name
    general, declared = _plot(world, monkeypatch)
    stability = kethani.stability
    monkeypatch.setattr(G, "COUP_ATTEMPT_P", 1.0)
    monkeypatch.setattr(G, "COUP_SUCCESS_RANGE", (0.0, 0.0))
    out = _next(world)
    failed = next(e for e in out if e.event_type == "gp_coup_failed")
    assert "betrayed by Banker Ilse" in failed.description and "0:x:0" in failed.causes
    assert kethani.leader.name == ruler and general.fate == "dead" and not general.active
    assert kethani.stability == stability - G.COUP_FAILED_STABILITY
    assert _rec(world, loyal).renown == 1
    verdict = next(e for e in out if e.event_type == "agenda_failed")
    assert "coup was crushed" in verdict.description
    assert world.gp_agendas.counts["coups_failed"] == 1


def test_no_plot_against_a_strong_ruler_without_the_army_or_early_in_a_reign(monkeypatch):
    world = _world()
    monkeypatch.setattr(G, "_campaign_targets", lambda *a, **k: [])
    world.turn = 10
    kethani = world.civilizations[KETHANI]
    kethani.factions.influence[FactionType.MILITARY] = 0.4
    kethani.stability = 80
    general = _gp(world, KETHANI, "general", "Marshal Tovan", trait="bold")
    world.gp_agendas.records[G.gp_key(general)] = G.AgendaRecord(
        gp_name=general.name, born_turn=10, role="general", civ=KETHANI, renown=5)
    assert _tick(world) == []                      # a strong ruler
    kethani.stability = 20
    kethani.factions.influence[FactionType.MILITARY] = 0.1
    assert _tick(world) == []                      # the army is no power at court
    kethani.factions.influence[FactionType.MILITARY] = 0.4
    kethani.leader.reign_start = 8
    assert _tick(world) == []                      # the reign is too young
    kethani.leader.reign_start = 0
    assert _types(_tick(world))[0] == "agenda_declared"


# --- merchants -------------------------------------------------------------------------

def test_merchant_trade_mission_opens_the_route_and_fulfils_the_vow(monkeypatch):
    world = _world()
    merchant = _gp(world, KETHANI, "merchant", "Factor Oda")
    _force(monkeypatch, T.OPEN_TRADE_ROUTE, str(THORNWALL))
    declared = _tick(world)
    assert "open a trade route to Thornwall Confederacy" in declared[0].description
    prov.observe(world, declared)
    monkeypatch.setattr(G, "MISSION_P", 1.0)
    out = _next(world)
    assert _types(out)[:2] == ["trade_mission", "agenda_fulfilled"]
    assert world.relationships["Kethani Empire"]["Thornwall Confederacy"].disposition == Disposition.NEUTRAL
    assert prov.ensure_id(world, out[0]) in out[1].causes
    assert _rec(world, merchant).agenda.completed


def test_with_diplomacy_missions_leave_goodwill_and_agitation_a_grievance(monkeypatch):
    import chronicler.diplomacy as dp
    from chronicler.diplomacy_state import BORDER
    world = _world()
    dp.set_diplomacy_enabled(world, True)
    _gp(world, KETHANI, "merchant", "Factor Oda")
    _force(monkeypatch, T.OPEN_TRADE_ROUTE, str(THORNWALL))
    _tick(world)
    monkeypatch.setattr(G, "MISSION_P", 1.0)
    _next(world)
    for a, b in (("Kethani Empire", "Thornwall Confederacy"), ("Thornwall Confederacy", "Kethani Empire")):
        assert dp.memory(world, a, b).goodwill == pytest.approx(G.MISSION_GOODWILL)
    assert G._sour_disposition_step(world, "Kethani Empire", "Ashkari Nomads")
    assert dp.grievance(world, "Kethani Empire", "Ashkari Nomads", (BORDER,)) == pytest.approx(
        G.AGITATION_GRIEVANCE)
    assert dp.grievance(world, "Ashkari Nomads", "Kethani Empire") == 0.0


def test_protected_route_completes_on_the_deadline_or_breaks_on_an_embargo(monkeypatch):
    world = _world()
    merchant = _gp(world, KETHANI, "merchant", "Factor Oda")
    _force(monkeypatch, T.PROTECT_TRADE_ROUTE, str(ASHKARI))
    _tick(world)
    deadline = _rec(world, merchant).agenda.deadline_turn
    while world.turn < deadline - 1:
        assert _next(world) == []
    out = _next(world)
    # The ruler of Kethani is calculating (merchant faction): the merchant
    # who kept the road becomes the ruler's loyalist.
    assert _types(out) == ["agenda_fulfilled", "gp_alliance_formed"]
    # Broken: an embargo between the pair ends the vow early.
    world = _world()
    merchant = _gp(world, KETHANI, "merchant", "Factor Oda")
    _tick(world)
    world.turn += 1
    world.embargoes.append(("Kethani Empire", "Ashkari Nomads"))
    embargo = Event(turn=world.turn, event_type="embargo", actors=["Kethani Empire", "Ashkari Nomads"],
                    description="Kethani Empire embargoes Ashkari Nomads.")
    prov.observe(world, [embargo])
    out = _tick(world, [embargo])
    failed = next(e for e in out if e.event_type == "agenda_failed")
    assert "the trade road was cut" in failed.description and embargo.event_id in failed.causes


def test_trading_house_is_founded_paid_for_and_leaves_a_trade_good(monkeypatch):
    world = _world()
    for a, b in (("Kethani Empire", "Thornwall Confederacy"), ("Thornwall Confederacy", "Kethani Empire")):
        world.relationships[a][b].disposition = Disposition.NEUTRAL
    world.invalidate_trade_route_cache()
    merchant = _gp(world, KETHANI, "merchant", "Factor Oda")
    _force(monkeypatch, T.FOUND_TRADING_HOUSE)
    _tick(world)
    kethani = world.civilizations[KETHANI]
    treasury, influence = kethani.treasury, kethani.factions.influence[FactionType.MERCHANT]
    monkeypatch.setattr(G, "TRADING_HOUSE_P", 1.0)
    out = _next(world)
    assert _types(out)[:2] == ["trading_house_founded", "agenda_fulfilled"]
    assert kethani.treasury == treasury - G.TRADING_HOUSE_COST
    assert kethani.factions.influence[FactionType.MERCHANT] > influence
    intent = world._artifact_intents[-1]
    assert intent.artifact_type.value == "trade_good" and intent.creator_name == merchant.name
    from chronicler.artifacts import tick_artifacts
    created = tick_artifacts(world)
    assert any(e.event_type == "artifact_created" for e in created)
    # One house per region: the capital is taken, the next merchant builds elsewhere.
    assert world.gp_agendas.houses == {kethani.capital_region: world.turn}
    other = _gp(world, KETHANI, "merchant", "Factor Rhee")
    assert G._house_site(world.gp_agendas, kethani, other) == "Frostholm Tundra"
    world.gp_agendas.houses["Frostholm Tundra"] = world.turn
    assert G._house_site(world.gp_agendas, kethani, other) is None
    assert T.FOUND_TRADING_HOUSE not in G._raw_pool(world, G._Ctx(world, [], None), world.gp_agendas,
                                                    KETHANI, kethani, other, _rec(world, merchant), {})


def test_lending_merchant_deepens_crown_credit_and_completes_on_a_domestic_loan(monkeypatch):
    import chronicler.finance as F
    world = _world()
    F.set_finance_enabled(world, True)
    F._ensure(world)
    f = world.finance.civs[KETHANI]
    f.initialized, f.fiscal_stress, f.merchant_wealth, f.revenue_ema = True, 0.6, 100.0, 10.0
    kethani = world.civilizations[KETHANI]
    base = F._domestic_capacity(world, KETHANI, kethani, f)
    _gp(world, KETHANI, "merchant", "Factor Oda")
    _force(monkeypatch, T.LEND_TO_CROWN)
    _tick(world)
    assert G.crown_credit_factor(world, KETHANI) == 1.5
    assert F._domestic_capacity(world, KETHANI, kethani, f) == int(base * 1.5) or \
        F._domestic_capacity(world, KETHANI, kethani, f) > base
    world.turn += 1
    loan = Event(turn=world.turn, event_type="loan_taken", actors=["Kethani Empire"],
                 description="Kethani Empire borrows 40 from its merchant houses at 4.0%.", civs=["Kethani Empire"])
    prov.observe(world, [loan])
    out = _tick(world, [loan])
    assert _types(out)[:2] == ["crown_loan", "agenda_fulfilled"]
    assert loan.event_id in out[0].causes
    assert "gp_alliance_formed" in _types(out)  # a lender becomes the ruler's loyalist
    assert G.crown_credit_factor(world, KETHANI) == 1.0


# --- prophets --------------------------------------------------------------------------

def _coreligionists(world) -> int:
    """Make the Selurian Republic (Ashara Desert) hold Kethani's faith."""
    faith = world.civilizations[KETHANI].civ_majority_faith
    world.civilizations[SELURIAN].civ_majority_faith = faith
    return faith


def test_prophet_preaches_among_coreligionists_abroad_and_the_faith_takes_hold(monkeypatch):
    world = _world()
    prophet = _gp(world, KETHANI, "prophet", "Seer Anwe", trait="zealous")
    faith = _coreligionists(world)
    rows = {"Amber Valley": [faith] * 4, "Frostholm Tundra": [faith] * 3, "Ashara Desert": [3, 3, 3, 3, faith],
            "Thornwood": [2, 2, faith, faith]}
    _force(monkeypatch, T.SPREAD_FAITH)
    declared = _tick(world, phase10=_rows(world, rows))
    assert _rec(world, prophet).agenda.target == "Ashara Desert"
    prov.observe(world, declared)
    desert = world.region_map["Ashara Desert"]
    # The faith's own priests already hold the region's conversion slot: the
    # prophet adds his pressure to theirs.
    desert.conversion_rate_signal, desert.conversion_target_signal = 0.01, faith
    out = _next(world, phase10=_rows(world, rows))
    assert _types(out) == ["preaching"] and prophet.region == "Ashara Desert"
    preaching = prov.ensure_id(world, out[0])
    assert desert.conversion_target_signal == faith
    assert desert.conversion_rate_signal == pytest.approx(0.01 + G.PREACHING_RATE)
    rows["Ashara Desert"] = [faith, faith, faith, 3]
    out = _next(world, phase10=_rows(world, rows))
    fulfilled = next(e for e in out if e.event_type == "agenda_fulfilled")
    assert "bring the faith to Ashara Desert" in fulfilled.description
    assert preaching in fulfilled.causes  # the deed that brought it about


def test_preaching_an_empty_slot_brings_only_the_prophets_own_pressure(monkeypatch):
    """A rate left in a slot no faith holds (a martyrdom or conquest boost)
    converts no one; the prophet who takes the slot does not inherit it."""
    world = _world()
    _gp(world, KETHANI, "prophet", "Seer Anwe", trait="zealous")
    faith = _coreligionists(world)
    rows = {"Amber Valley": [faith] * 4, "Ashara Desert": [3, 3, 3, 3, faith]}
    _force(monkeypatch, T.SPREAD_FAITH, "Ashara Desert")
    _tick(world, phase10=_rows(world, rows))
    desert = world.region_map["Ashara Desert"]
    desert.conversion_rate_signal, desert.conversion_target_signal = 0.15, 0xFF
    assert _types(_next(world, phase10=_rows(world, rows))) == ["preaching"]
    assert desert.conversion_target_signal == faith
    assert desert.conversion_rate_signal == pytest.approx(G.PREACHING_RATE)


def test_prophets_preach_only_in_their_faiths_realms_and_never_into_persecution():
    """Own and co-religionist regions qualify; a realm of another faith, an
    unruled region and a persecuted region (live or left over) do not."""
    world = _world()
    kethani = world.civilizations[KETHANI]
    faith = kethani.civ_majority_faith
    rows = {"Amber Valley": [faith] * 4, "Frostholm Tundra": [2, 2, 2, faith], "Ashara Desert": [3, 3, 3, 3, faith],
            "Iron Peaks": [2, 2, faith]}
    ctx = G._Ctx(world, [], _rows(world, rows))
    # Ashara Desert's ruler holds another faith; Iron Peaks has no ruler.
    assert G._spread_targets(world, ctx, kethani) == ["Frostholm Tundra"]
    _coreligionists(world)
    assert G._spread_targets(world, ctx, kethani) == ["Ashara Desert", "Frostholm Tundra"]
    world.region_map["Ashara Desert"].persecution_intensity = 0.4
    world.region_map["Frostholm Tundra"].persecution_intensity = 0.2
    assert G._spread_targets(world, ctx, kethani) == []


def test_preaching_halts_under_persecution_or_a_change_of_faith_and_resumes_after(monkeypatch):
    world = _world()
    _gp(world, KETHANI, "prophet", "Seer Anwe", trait="zealous")
    faith = _coreligionists(world)
    selurian = world.civilizations[SELURIAN]
    rows = {"Amber Valley": [faith] * 4, "Ashara Desert": [3, 3, 3, 3, faith]}
    _force(monkeypatch, T.SPREAD_FAITH, "Ashara Desert")
    _tick(world, phase10=_rows(world, rows))
    desert = world.region_map["Ashara Desert"]
    desert.conversion_rate_signal, desert.conversion_target_signal = 0.0, 0xFF
    desert.persecution_intensity = 0.3
    assert _next(world, phase10=_rows(world, rows)) == []
    assert (desert.conversion_rate_signal, desert.conversion_target_signal) == (0.0, 0xFF)
    desert.persecution_intensity = 0.0
    selurian.civ_majority_faith = 3  # the realm turns to another faith
    assert _next(world, phase10=_rows(world, rows)) == []
    assert (desert.conversion_rate_signal, desert.conversion_target_signal) == (0.0, 0xFF)
    selurian.civ_majority_faith = faith
    assert _types(_next(world, phase10=_rows(world, rows))) == ["preaching"]
    assert desert.conversion_rate_signal == pytest.approx(G.PREACHING_RATE)


def test_preaching_signal_is_rebuilt_every_turn_and_leaves_no_residue(monkeypatch):
    """Multi-turn reset: the conversion builder rewrites the signal each Phase 10."""
    from chronicler.religion import compute_conversion_signals
    world = _world()
    prophet = _gp(world, KETHANI, "prophet", "Seer Anwe", trait="zealous")
    faith = _coreligionists(world)
    rows = {"Amber Valley": [faith] * 4, "Ashara Desert": [3, 3, 3, 3, faith]}
    _force(monkeypatch, T.SPREAD_FAITH, "Ashara Desert")
    desert_idx = next(i for i, r in enumerate(world.regions) if r.name == "Ashara Desert")

    def build():
        batch = _rows(world, rows).agents.batch
        compute_conversion_signals(world.regions, {desert_idx: 3}, world.belief_registry, batch, world=world)
        return world.regions[desert_idx].conversion_rate_signal

    build()
    _tick(world, phase10=_rows(world, rows))
    for _ in range(3):
        world.turn += 1
        built = build()
        _tick(world, phase10=_rows(world, rows))
        assert world.regions[desert_idx].conversion_rate_signal == pytest.approx(built + G.PREACHING_RATE)
    # The vow ends (the prophet retires): the next build carries no preaching.
    from chronicler.great_persons import _retire_person
    _retire_person(prophet, world.civilizations[KETHANI], world)
    world.turn += 1
    built = build()
    out = _tick(world, phase10=_rows(world, rows))
    assert "agenda_failed" in _types(out)
    assert world.regions[desert_idx].conversion_rate_signal == built
    world.turn += 1
    assert build() == built


def test_prophet_commissions_a_temple_that_becomes_a_pilgrimage_shrine(monkeypatch):
    from chronicler.infrastructure import tick_infrastructure
    from chronicler.models import InfrastructureType
    world = _world()
    prophet = _gp(world, KETHANI, "prophet", "Seer Anwe")
    _force(monkeypatch, T.FOUND_SHRINE, "Frostholm Tundra")
    _tick(world)
    kethani = world.civilizations[KETHANI]
    treasury = kethani.treasury
    out = _next(world)
    assert _types(out) == ["shrine_commissioned"]
    tundra = world.region_map["Frostholm Tundra"]
    assert tundra.pending_build.type == InfrastructureType.TEMPLES
    assert tundra.pending_build.faith_id == kethani.civ_majority_faith
    assert kethani.treasury < treasury
    completed = []
    for _ in range(3):
        world.turn += 1
        completed = tick_infrastructure(world)
        out = _tick(world, completed)
    done = next(e for e in completed if e.event_type == "infrastructure_completed")
    prov.observe(world, [done])
    assert "shrine_consecrated" in _types(out) and "agenda_fulfilled" in _types(out)
    temple = next(i for i in tundra.infrastructure if i.type == InfrastructureType.TEMPLES)
    assert temple.temple_prestige >= G.SHRINE_PRESTIGE
    assert _rec(world, prophet).agenda.completed


# --- scientists ------------------------------------------------------------------------

def test_scientist_vows_the_next_era_and_is_settled_by_the_advance():
    world = _world()
    scientist = _gp(world, KETHANI, "scientist", "Scholar Pell")
    declared = _tick(world)
    assert "carry learning into the bronze era" in declared[0].description
    world.turn += 1
    kethani = world.civilizations[KETHANI]
    kethani.tech_era = TechEra.BRONZE
    advance = Event(turn=world.turn, event_type="tech_advancement", actors=["Kethani Empire"],
                    description="Kethani Empire enters the bronze era")
    prov.observe(world, [advance])
    out = _tick(world, [advance])
    assert advance.event_id in out[0].causes and _rec(world, scientist).agenda.completed


def test_scientist_fails_when_time_runs_out():
    world = _world()
    scientist = _gp(world, KETHANI, "scientist", "Scholar Pell")
    _tick(world)
    deadline = _rec(world, scientist).agenda.deadline_turn
    out = []
    while world.turn < deadline:
        out = _next(world)
    assert _types(out) == ["agenda_failed"] and "time ran out" in out[0].description
    assert world.gp_agendas.log[-1].outcome == "failed"


def test_scientist_steers_the_civs_invention_to_the_vowed_technique(monkeypatch):
    import chronicler.techniques as TQ
    world = _world()
    TQ.set_techniques_enabled(world, True)
    TQ.tick_techniques(world)  # seed practice and known sets
    kethani = world.civilizations[KETHANI]
    kethani.culture = kethani.economy = 90
    kethani.treasury = 10_000
    scientist = _gp(world, KETHANI, "scientist", "Scholar Pell")
    candidates = G._invention_candidates(world, KETHANI, kethani)
    assert len(candidates) > 1
    target = candidates[-1]
    _force(monkeypatch, T.INVENT_TECHNIQUE, target)
    _tick(world)
    assert G.invention_targets(world, kethani) == {target}
    monkeypatch.setattr(TQ, "_draw", lambda *a, **k: 0.0)
    world.turn += 1
    events = TQ.tick_techniques(world)
    invented = [e for e in events if e.event_type == "technique_invented" and e.actors == ["Kethani Empire"]]
    label = TQ.TECHNIQUES[TQ.TECHNIQUE_INDEX[target]].label
    assert invented and label in invented[0].description
    prov.observe(world, invented)
    out = _tick(world, invented)
    assert _types(out)[0] == "agenda_fulfilled" and invented[0].event_id in out[0].causes
    assert _rec(world, scientist).agenda.completed


def test_scientists_vow_only_techniques_the_civ_has_a_site_for(monkeypatch):
    """``techniques._invent`` only chooses a technique with a site (an
    inhabited, suited region of the civ practising its prerequisites)."""
    import chronicler.techniques as TQ
    world = _world()
    TQ.set_techniques_enabled(world, True)
    TQ.tick_techniques(world)
    kethani = world.civilizations[KETHANI]
    candidates = G._invention_candidates(world, KETHANI, kethani)
    assert len(candidates) > 1
    barred = TQ.TECHNIQUE_INDEX[candidates[0]]
    real = TQ._suitability

    def unsuited(*args, **kwargs):
        rows = real(*args, **kwargs)
        for row in rows:
            row[barred] = False
        return rows

    monkeypatch.setattr(TQ, "_suitability", unsuited)
    assert G._invention_candidates(world, KETHANI, kethani) == candidates[1:]
    for name in kethani.regions:
        world.region_map[name].population = 0
    assert G._invention_candidates(world, KETHANI, kethani) == []


# --- holders who leave, bonds, succession ----------------------------------------------

def test_retirement_cuts_an_agenda_short_and_retires_the_record():
    from chronicler.great_persons import _retire_person
    world = _world()
    scientist = _gp(world, KETHANI, "scientist", "Scholar Pell")
    _tick(world)
    _retire_person(scientist, world.civilizations[KETHANI], world)
    out = _next(world)
    assert _types(out) == ["agenda_failed"] and "cut short by retirement" in out[0].description
    assert G.gp_key(scientist) not in world.gp_agendas.records
    assert world.gp_agendas.counts["failed:scientist"] == 1


def test_one_vow_per_civ_and_target():
    world = _world()
    first = _gp(world, KETHANI, "scientist", "Scholar Pell")
    second = _gp(world, KETHANI, "scientist", "Scholar Rhee")
    out = _tick(world)
    assert _types(out) == ["agenda_declared"]
    assert _rec(world, first).agenda is not None and _rec(world, second).agenda is None


def test_war_party_and_trade_party_feud_and_merchants_partner_across_borders(monkeypatch):
    world = _world()
    _gp(world, KETHANI, "general", "Marshal Tovan", trait="bold")
    real = G._raw_pool

    def pool(world_, ctx, state, civ_idx, civ, gp, rec, active):
        full = real(world_, ctx, state, civ_idx, civ, gp, rec, active)
        if gp.role == "general":
            return {T.LEAD_CAMPAIGN: (["Ashara Desert"], [])}
        return {T.OPEN_TRADE_ROUTE: full[T.OPEN_TRADE_ROUTE]} if T.OPEN_TRADE_ROUTE in full else {}

    monkeypatch.setattr(G, "_raw_pool", pool)
    _tick(world)
    merchant = _gp(world, KETHANI, "merchant", "Factor Oda")
    monkeypatch.setattr(G, "_kind_weight", lambda kind, gp: 1.0)
    rng_draws = iter([0.0, 0.99, 0.0])  # kind, target (the last: Selurian), duration

    def scripted(label, world_, *parts):
        if label == "declare":
            return SimpleNamespace(random=lambda: next(rng_draws))
        return SimpleNamespace(random=lambda: 0.99)  # no agitation, no mission

    monkeypatch.setattr(G, "_rng", scripted)
    out = _next(world)
    assert _rec(world, merchant).agenda.target == str(SELURIAN)
    feud = next(e for e in out if e.event_type == "gp_rivalry_formed")
    assert "Marshal Tovan" in feud.actors and "Factor Oda" in feud.actors
    assert [b.kind for b in world.gp_agendas.bonds] == ["feud"]
    # A Selurian merchant courting Kethani becomes Oda's partner; a second
    # suitor cannot also partner Oda (one partnership each).
    monkeypatch.setattr(G, "_rng", lambda label, world_, *parts: SimpleNamespace(
        random=lambda: 0.0 if label == "declare" else 0.99))  # first target: Kethani
    sel = _gp(world, SELURIAN, "merchant", "Factor Quell")
    out = _next(world)
    assert _rec(world, sel).agenda.target == str(KETHANI)
    assert "gp_alliance_formed" in _types(out)
    assert sorted(b.kind for b in world.gp_agendas.bonds) == ["feud", "partnership"]
    wren = _gp(world, THORNWALL, "merchant", "Factor Wren")
    assert G._form_bond(world, world.gp_agendas, "partnership", G.gp_key(merchant), G.gp_key(wren), KETHANI,
                        world.civilizations[KETHANI], merchant.name, wren.name, "again", []) is None
    assert sum(1 for b in world.gp_agendas.bonds if b.kind == "partnership") == 1


def test_allies_back_and_rivals_oppose_in_a_succession_crisis():
    from chronicler.factions import generate_faction_candidates
    world = _world()
    kethani = world.civilizations[KETHANI]
    plotter = _gp(world, KETHANI, "general", "Marshal Tovan")
    ally = _gp(world, KETHANI, "general", "Marshal Ivo")
    rival = _gp(world, KETHANI, "merchant", "Factor Oda")
    loyal = _gp(world, KETHANI, "merchant", "Banker Ilse")
    for gp in (plotter, ally, rival, loyal):
        world.gp_agendas.records[G.gp_key(gp)] = G.AgendaRecord(
            gp_name=gp.name, born_turn=0, role=gp.role, civ=KETHANI, next_turn=99)
    bonds = world.gp_agendas.bonds
    bonds.append(G.AgendaBond(kind="conspiracy", a=G.gp_key(ally), b=G.gp_key(plotter), civ=1, formed_turn=0))
    bonds.append(G.AgendaBond(kind="feud", a=G.gp_key(plotter), b=G.gp_key(rival), civ=1, formed_turn=0))
    bonds.append(G.AgendaBond(kind="loyalty", a=G.gp_key(loyal), b="ruler:1", civ=1, ruler=kethani.leader.name,
                              formed_turn=0))
    plain = generate_faction_candidates(kethani, generate_world(seed=42, num_regions=8, num_civs=4))
    cands = generate_faction_candidates(kethani, world)
    tovan = next(c for c in cands if c.get("gp_name") == "Marshal Tovan")
    assert tovan["backers"] == ["Marshal Ivo"] and tovan["opponents"] == ["Factor Oda"]
    internal = next(c for c in cands if c.get("source") == "internal" and c["faction"] == "merchant")
    assert internal["backers"] == ["Banker Ilse"]
    plain_internal = next(c for c in plain if c.get("source") == "internal" and c["faction"] == "merchant")
    assert internal["weight"] == pytest.approx(plain_internal["weight"] + G.BACKING_WEIGHT)
    # The crowned winner's backers become its loyalists; its rivals its opposition.
    new_leader = SimpleNamespace(name="Archon Tovan")
    out = G.note_succession(world, kethani, tovan, kethani.leader, new_leader)
    assert _types(out)[0] == "succession_backed" and "backing of Marshal Ivo" in out[0].description
    kinds = {(b.kind, b.a, b.ruler) for b in world.gp_agendas.bonds}
    assert ("loyalty", G.gp_key(ally), "Archon Tovan") in kinds
    assert ("opposition", G.gp_key(rival), "Archon Tovan") in kinds


def test_flag_off_candidates_carry_no_backing():
    from chronicler.factions import generate_faction_candidates
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    _gp(world, KETHANI, "general", "Marshal Tovan")
    assert all("backers" not in c and "opponents" not in c
               for c in generate_faction_candidates(world.civilizations[KETHANI], world))


# --- action weights --------------------------------------------------------------------

def test_open_agendas_ride_the_capped_governance_bucket(monkeypatch):
    from chronicler.governance_runtime import (
        GOVERNANCE_WEIGHT_CEILING, governance_weight_modifiers, set_governance_enabled,
    )
    world = _world()
    set_governance_enabled(world, True)
    _advance(world, 1)  # governance state on every civ
    kethani = world.civilizations[KETHANI]
    kethani.great_persons = [g for g in kethani.great_persons if g.role not in G.AGENDA_ROLES]
    world.gp_agendas = GPAgendaState()
    before = governance_weight_modifiers(kethani, world).get(ActionType.WAR, 1.0)
    for i in range(3):
        gp = _gp(world, KETHANI, "general", f"Marshal {i}")
        world.gp_agendas.records[G.gp_key(gp)] = G.AgendaRecord(
            gp_name=gp.name, born_turn=gp.born_turn, role="general", civ=KETHANI,
            agenda=G.GovernanceAmbition(ambition_type="lead_campaign", target=f"R{i}", generated_turn=0,
                                        deadline_turn=20, generated_event_cursor=0))
    factors = G.agenda_weight_factors(world, kethani)
    assert factors == {ActionType.WAR: pytest.approx(1.1 ** G.MAX_BIASED_PER_KIND)}
    after = governance_weight_modifiers(kethani, world).get(ActionType.WAR, 1.0)
    assert after == pytest.approx(min(GOVERNANCE_WEIGHT_CEILING, before * 1.21))
    engine = ActionEngine(world)
    engine.compute_weights(kethani)
    assert engine.last_buckets["governance"][ActionType.WAR] > 1.0 or after == before
    world.gp_agendas = None
    assert governance_weight_modifiers(kethani, world).get(ActionType.WAR, 1.0) == pytest.approx(before)


# --- runs, persistence, dormancy -------------------------------------------------------

def _run_world(seed: int = 42) -> WorldState:
    from chronicler.governance_runtime import set_governance_enabled
    world = _world(seed)
    world.campaigns_enabled = True
    set_governance_enabled(world, True)
    return world


def test_agendas_run_and_are_deterministic():
    a = _advance(_run_world(), 60)
    b = _advance(_run_world(), 60)
    assert a.model_dump_json() == b.model_dump_json()
    counts = a.gp_agendas.counts
    assert counts["declared"] > 0 and counts.get("fulfilled", 0) + counts.get("failed", 0) > 0


def test_save_load_resume_identity_with_live_agendas_and_bonds(tmp_path):
    first = _advance(_run_world(), 15)
    while not (any(G._is_open(r) for r in first.gp_agendas.records.values()) and first.gp_agendas.bonds):
        assert first.turn < 120, "no turn with an open agenda and a bond"
        _advance(first, 1)
    straight = _advance(_run_world(), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.gp_agendas == first.gp_agendas
    _advance(resumed, 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_switch_off_is_dormant_and_omitted(tmp_path):
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    assert world.gp_agendas is None and "gp_agendas" not in json.loads(world.model_dump_json())
    G.set_gp_agendas_enabled(world, True)
    assert "gp_agendas" in json.loads(world.model_dump_json())
    G.set_gp_agendas_enabled(world, False)
    assert world.gp_agendas is None and "gp_agendas" not in json.loads(world.model_dump_json())
    snap = TurnSnapshot(turn=0, civ_stats={}, region_control={}, relationships={})
    assert "gp_agendas" not in json.loads(snap.model_dump_json())
    data = json.loads(world.model_dump_json())
    path = tmp_path / "old.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = WorldState.load(path)
    assert loaded.gp_agendas is None and loaded.model_dump_json() == world.model_dump_json()


def test_feature_off_never_runs_agenda_code(monkeypatch):
    import chronicler.finance as F
    import chronicler.techniques as TQ
    from chronicler.governance_runtime import set_governance_enabled

    def boom(*a, **k):
        raise AssertionError("agenda code ran with the switch off")
    for name in ("tick_gp_agendas", "agenda_weight_factors", "crown_credit_factor", "invention_targets",
                 "back_candidates", "note_succession", "snapshot_summary"):
        monkeypatch.setattr(G, name, boom)
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.campaigns_enabled = True
    set_governance_enabled(world, True)
    F.set_finance_enabled(world, True)
    TQ.set_techniques_enabled(world, True)
    _advance(world, 40)
    assert world.gp_agendas is None


def test_cli_flag_gate_forwarding_snapshot_and_report(tmp_path):
    import argparse
    import importlib.util
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    assert parser.parse_args([]).gp_agendas is None
    assert parser.parse_args(["--gp-agendas"]).gp_agendas is True
    assert parser.parse_args(["--no-gp-agendas"]).gp_agendas is False
    spec = importlib.util.spec_from_file_location("m53b", ROOT / "scripts" / "m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._gp_agendas_args(argparse.Namespace(gp_agendas=True)) == ["--gp-agendas"]
    assert m53b._gp_agendas_args(argparse.Namespace(gp_agendas=False)) == ["--no-gp-agendas"]
    assert m53b._gp_agendas_args(argparse.Namespace(gp_agendas=None)) == []
    out = tmp_path / "on"
    execute_run(parser.parse_args(["--seed", "42", "--turns", "40", "--regions", "8", "--civs", "4",
                                   "--agents", "off", "--simulate-only",
                                   "--gp-agendas", "--output", str(out / "chronicle.md"),
                                   "--state", str(out / "state.json")]))
    state = json.loads((out / "state.json").read_text())
    assert "gp_agendas" in state
    bundle = json.loads((out / "chronicle_bundle.json").read_text())
    assert all("gp_agendas" in h for h in bundle["history"])
    spec = importlib.util.spec_from_file_location("gp_report", ROOT / "scripts" / "gp_agendas_report.py")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    row = report.run_metrics(out)
    assert row["on"] and row["declared"] == state["gp_agendas"]["counts"].get("declared", 0)
    off = tmp_path / "off"
    execute_run(parser.parse_args(["--seed", "42", "--turns", "3", "--regions", "8", "--civs", "4",
                                   "--agents", "off", "--simulate-only",
                                   "--output", str(off / "chronicle.md"), "--state", str(off / "state.json")]))
    assert "gp_agendas" not in json.loads((off / "state.json").read_text())
    assert not report.run_metrics(off)["on"]
    # Resume keeps the saved setting; --no-gp-agendas drops the state.
    resumed = WorldState.load(out / "state.json")
    assert resumed.gp_agendas is not None
    G.set_gp_agendas_enabled(resumed, False)
    assert resumed.gp_agendas is None


def test_hybrid_runs_with_agendas_are_deterministic(tmp_path):
    pytest.importorskip("chronicler_agents")
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    dumps = []
    for label in ("a", "b"):
        out = tmp_path / label
        execute_run(parser.parse_args(["--seed", "42", "--turns", "50", "--regions", "8", "--civs", "4",
                                       "--agents", "hybrid", "--simulate-only",
                                       "--gp-agendas", "--output", str(out / "chronicle.md"),
                                       "--state", str(out / "state.json")]))
        dumps.append((out / "state.json").read_text())
    assert dumps[0] == dumps[1]
    state = json.loads(dumps[0])
    assert state["gp_agendas"]["counts"].get("declared", 0) > 0
