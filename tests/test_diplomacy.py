"""Diplomacy: memory, treaty lifecycle and breach, the polity ladder, persistence, dormancy."""
from __future__ import annotations

import argparse
import json

import pytest

import chronicler.diplomacy as dp
from chronicler import provenance as prov
from chronicler.action_engine import ActionEngine
from chronicler.diplomacy_state import (
    BORDER, EMBARGO, FAITH, GRIEVANCE_KINDS, OCCUPATION, TREATY, WAR,
    DiplomacyState, DiplomaticMemory,
)
from chronicler.models import (
    ActionType, Disposition, Event, Relationship, TurnSnapshot, VassalRelation, WorldState,
)
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world
from war_fixtures import make_civ, make_region, start_war, war_world


# --- builders ---------------------------------------------------------------------------

def _world(seed: int = 42, *, diplomacy: bool = True, campaigns: bool = True) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = campaigns
    dp.set_diplomacy_enabled(world, diplomacy)
    return world


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def _three(seed: int = 7) -> WorldState:
    """war_world (A: Avalon, Brook; B: Crag, Dun, Edge) plus C holding Fen next to Brook and Crag."""
    world = war_world(seed=seed)
    fen = make_region("Fen", "C", 50)
    fen.adjacencies = ["Brook", "Crag"]
    world.region_map["Brook"].adjacencies.append("Fen")
    world.region_map["Crag"].adjacencies.append("Fen")
    world.regions.append(fen)
    world.civilizations.append(make_civ("C", ["Fen"], military=50, treasury=200, capital="Fen"))
    world.civilizations[-1].population = 50
    for a, b in (("A", "C"), ("C", "A"), ("B", "C"), ("C", "B")):
        world.relationships.setdefault(a, {})[b] = Relationship(disposition=Disposition.FRIENDLY)
    world.invalidate_region_map()
    world.invalidate_civ_map()
    dp.set_diplomacy_enabled(world, True)
    return world


def _idx(world, name):
    return world.civ_index_map[name]


def _no_noise(monkeypatch):
    monkeypatch.setattr(dp, "_noise", lambda *a, **k: 0.0)


# --- memory --------------------------------------------------------------------------------

def test_every_grievance_stock_decays_with_its_own_half_life():
    world = war_world()
    dp.set_diplomacy_enabled(world, True)
    for kind in range(len(GRIEVANCE_KINDS)):
        dp.add_grievance(world, "B", "A", kind, 64.0)
    dp.add_goodwill(world, "B", "A", 64.0)
    dp.adjust_trust(world, "B", "A", 50.0)
    mem = dp.memory(world, "B", "A")
    for kind, half_life in enumerate(dp.GRIEVANCE_HALF_LIFE):
        probe = war_world()
        dp.set_diplomacy_enabled(probe, True)
        dp.add_grievance(probe, "B", "A", kind, 64.0)
        for _ in range(int(half_life)):
            dp._decay_memories(probe)
        assert dp.memory(probe, "B", "A").grievance[kind] == pytest.approx(32.0, rel=1e-3), GRIEVANCE_KINDS[kind]
    # Faster kinds fade first: a border incident is long forgotten when lost land is not.
    for _ in range(96):
        dp._decay_memories(world)
    assert mem.grievance[BORDER] < 1.0 < mem.grievance[OCCUPATION]
    assert mem.goodwill == pytest.approx(64.0 * 0.5 ** (96 / dp.GOODWILL_HALF_LIFE), rel=1e-2)
    assert mem.trust == pytest.approx(50.0 * dp.TRUST_RETENTION ** 96, rel=1e-2)
    # Stocks too small to matter drop to exactly zero (compact, stable JSON).
    for _ in range(1200):
        dp._decay_memories(world)
    assert mem.grievance == [0.0] * len(GRIEVANCE_KINDS) and mem.goodwill == 0.0


def test_memory_caps_and_nudges_dispositions():
    world = war_world()
    dp.set_diplomacy_enabled(world, True)
    rel = world.relationships["B"]["A"]
    rel.disposition = Disposition.ALLIED
    dp.add_grievance(world, "B", "A", OCCUPATION, 80.0)
    assert dp.disposition_ceiling(rel.memory) == Disposition.SUSPICIOUS
    for _ in range(3):
        dp._apply_dispositions(world)
    assert rel.disposition == Disposition.SUSPICIOUS  # one step per turn, never below the cap
    dp._apply_dispositions(world)
    assert rel.disposition == Disposition.SUSPICIOUS
    # Goodwill offsets grievance; deep distrust caps on its own.
    mem = DiplomaticMemory(goodwill=40.0, grievance=[30.0, 0, 0, 0, 0, 0])
    assert dp.disposition_ceiling(mem) == Disposition.ALLIED
    assert dp.disposition_ceiling(DiplomaticMemory(trust=-60.0)) == Disposition.NEUTRAL
    # The other direction is untouched: memory is directed.
    assert world.relationships["A"]["B"].memory is None


def test_inputs_are_read_once_per_turn(monkeypatch):
    """Per-turn inputs (land, battles, incidents) are consumed once, not re-counted."""
    world = war_world()
    dp.set_diplomacy_enabled(world, True)
    dp.tick_diplomacy(world, [])  # first tick records the controllers mirror
    world.turn = 1
    region = world.region_map["Edge"]
    region.controller = "A"
    world.civ_map["B"].regions.remove("Edge")
    world.civ_map["A"].regions.append("Edge")
    incident = Event(turn=1, event_type="border_incident", actors=["A", "B"], description="")
    dp.tick_diplomacy(world, [incident])
    first = list(dp.memory(world, "B", "A").grievance)
    assert first[OCCUPATION] == pytest.approx(dp.GRIEVANCE_LAND_LOST)
    assert first[BORDER] == pytest.approx(dp.GRIEVANCE_BORDER)
    world.turn = 2
    dp.tick_diplomacy(world, [])
    second = dp.memory(world, "B", "A").grievance
    # Only decay since: no second land loss, no second incident.
    assert second[OCCUPATION] < first[OCCUPATION] and second[BORDER] < first[BORDER]


# --- treaties ------------------------------------------------------------------------------

def test_treaty_signs_runs_its_course_and_rewards_keeping(monkeypatch):
    world = _three()
    a, c = _idx(world, "A"), _idx(world, "C")
    treaty, event = dp.sign_treaty(world, "non_aggression", a, c)
    assert treaty.status == "active" and treaty.expiry_turn == dp.TREATY_DURATION["non_aggression"]
    assert event.event_type == "treaty_signed" and treaty.event_id == event.event_id
    assert treaty.name in world.relationships["A"]["C"].treaties
    assert world.diplomacy.counts["signed:non_aggression"] == 1
    monkeypatch.setattr(dp, "_renewal_ok", lambda w, t: False)
    events = []
    for turn in range(1, treaty.expiry_turn + 1):
        world.turn = turn
        events += dp.tick_diplomacy(world, [])
    assert treaty.status == "expired" and treaty.ended_turn == treaty.expiry_turn
    expired = [e for e in events if e.event_type == "treaty_expired"]
    assert len(expired) == 1 and treaty.event_id in expired[0].causes
    # Kept to the end: trust and goodwill both ways.
    assert dp.trust(world, "A", "C") > 0 and dp.trust(world, "C", "A") > 0
    assert dp.goodwill(world, "C", "A") > 0


def test_treaty_renews_when_both_parties_accept_again(monkeypatch):
    world = _three()
    treaty, _ = dp.sign_treaty(world, "trade_pact", _idx(world, "A"), _idx(world, "C"))
    monkeypatch.setattr(dp, "acceptance_utility", lambda *a, **k: 1.0)
    world.turn = treaty.expiry_turn
    events = dp.tick_diplomacy(world, [])
    assert treaty.status == "active" and treaty.expiry_turn == world.turn + dp.TREATY_DURATION["trade_pact"]
    assert [e.event_type for e in events] == ["treaty_renewed"]
    assert world.diplomacy.counts["renewed:trade_pact"] == 1


def test_war_declaration_breaks_protecting_treaty_with_consequences():
    world = _three()
    a, b = _idx(world, "A"), _idx(world, "B")
    treaty, signed = dp.sign_treaty(world, "non_aggression", a, b)
    attacker = world.civ_map["A"]
    prestige, stability = 30, attacker.stability
    attacker.prestige = prestige
    world.active_wars.append(("A", "B"))
    events = dp.on_war_declared(world, attacker, world.civ_map["B"], broken=[treaty])
    breach = [e for e in events if e.event_type == "treaty_broken"]
    assert treaty.status == "broken" and treaty.broken_by == a
    assert len(breach) == 1 and signed.event_id in breach[0].causes
    assert breach[0].actors == ["A", "B"]
    victim = dp.memory(world, "B", "A")
    assert victim.grievance[TREATY] == dp.GRIEVANCE_BREACH
    assert victim.grievance[WAR] == dp.GRIEVANCE_WAR_DECLARED
    assert victim.trust == dp.TRUST_BREACH_VICTIM + dp.TRUST_AGGRESSION
    assert dp.trust(world, "C", "A") == dp.TRUST_BREACH_WITNESS  # reputation with third parties
    assert attacker.prestige == prestige - dp.BREACH_PRESTIGE
    assert attacker.stability == stability - dp.BREACH_STABILITY
    assert world.diplomacy.counts["broken:non_aggression"] == 1
    assert prov.recall(world, "breach:" + prov.pair("A", "B")) == breach[0].event_id


def test_war_guard_protects_unless_breaking_pays(monkeypatch):
    _no_noise(monkeypatch)
    world = _three()
    a, b = world.civ_map["A"], world.civ_map["B"]
    assert dp.war_guard(world, a, b) == (True, [])
    treaty, _ = dp.sign_treaty(world, "non_aggression", _idx(world, "A"), _idx(world, "B"))
    assert dp.war_guard(world, a, b) == (False, [])
    dp.add_grievance(world, "A", "B", OCCUPATION, 90.0)  # revanche outweighs the pact
    assert dp.war_guard(world, a, b) == (True, [treaty])
    assert dp.revanche_bonus(world, a, b) == 1.0


def test_an_overlord_does_not_make_war_on_its_own_subject():
    world = _three()
    world.vassal_relations.append(VassalRelation(overlord="A", vassal="C", stage="vassal", stage_turn=0))
    assert dp.war_guard(world, world.civ_map["A"], world.civ_map["C"]) == (False, [])
    assert dp.war_guard(world, world.civ_map["B"], world.civ_map["C"]) == (True, [])


def test_upkeep_breaks_a_treaty_whose_parties_are_at_war_and_ends_dead_parties():
    world = _three()
    a, b, c = (_idx(world, n) for n in "ABC")
    peace, _ = dp.sign_treaty(world, "non_aggression", a, b)
    pact, _ = dp.sign_treaty(world, "trade_pact", a, c)
    world.active_wars.append(("B", "A"))  # e.g. a federation dragged them in
    world.civ_map["C"].regions = []
    world.turn = 1
    events = dp.tick_diplomacy(world, [])
    assert peace.status == "broken" and peace.broken_by == b
    assert pact.status == "ended"
    assert [e.event_type for e in events] == ["treaty_broken"]


def test_alliance_call_to_arms_is_answered_or_breached(monkeypatch):
    for join in (True, False):
        world = _three()
        b, c = _idx(world, "B"), _idx(world, "C")
        treaty, _ = dp.sign_treaty(world, "alliance", b, c)
        monkeypatch.setattr(dp, "_join_utility", lambda *a, j=join, **k: 1.0 if j else -1.0)
        world.active_wars.append(("A", "B"))
        events = dp.on_war_declared(world, world.civ_map["A"], world.civ_map["B"],
                                    enemies_before=set())
        if join:
            assert ("A", "C") in world.active_wars and treaty.status == "active"
            call = [e for e in events if e.event_type == "call_to_arms"]
            assert call and call[0].actors == ["C", "B", "A"] and treaty.event_id in call[0].causes
            assert dp.trust(world, "B", "C") == dp.TRUST_DEFENDED
        else:
            assert ("A", "C") not in world.active_wars
            assert treaty.status == "broken" and treaty.broken_by == c
            assert dp.trust(world, "B", "C") == dp.TRUST_BREACH_VICTIM + dp.TRUST_REFUSED_CALL


def test_joiner_bound_to_the_attacker_breaks_its_treaty():
    world = _three()
    a, c = _idx(world, "A"), _idx(world, "C")
    pact, _ = dp.sign_treaty(world, "non_aggression", a, c)
    world.active_wars += [("A", "B"), ("A", "C")]  # C joined B's defence (federation)
    dp.on_war_declared(world, world.civ_map["A"], world.civ_map["B"], enemies_before=set())
    assert pact.status == "broken" and pact.broken_by == c


def test_embargo_respects_pacts_unless_breaking_pays(monkeypatch):
    _no_noise(monkeypatch)
    world = _three()
    a, b = world.civ_map["A"], world.civ_map["B"]
    pact, _ = dp.sign_treaty(world, "trade_pact", _idx(world, "A"), _idx(world, "B"))
    assert dp.embargo_guard(world, a, b) == (False, [])
    dp.add_grievance(world, "A", "B", WAR, 60.0)
    allowed, broken = dp.embargo_guard(world, a, b)
    assert allowed and broken == [pact]
    events = dp.on_embargo(world, a, b, broken=broken)
    assert pact.status == "broken" and events[0].event_type == "treaty_broken"
    assert dp.memory(world, "B", "A").grievance[EMBARGO] == dp.GRIEVANCE_EMBARGO_IMPOSED


def test_a_standing_embargo_offends_only_while_its_imposer_is_unfriendly():
    world = _three()
    world.embargoes = [("B", "C"), ("C", "B")]  # embargoes are never lifted
    world.relationships["B"]["C"].disposition = Disposition.FRIENDLY
    world.relationships["C"]["B"].disposition = Disposition.SUSPICIOUS
    world.turn = 1
    dp.tick_diplomacy(world, [])
    assert world.embargoes == [("B", "C"), ("C", "B")]
    assert dp.grievance(world, "B", "C", (EMBARGO,)) == dp.GRIEVANCE_EMBARGO_TURN
    assert dp.grievance(world, "C", "B", (EMBARGO,)) == 0.0


def test_trade_pact_keeps_a_route_open_between_suspicious_partners():
    from chronicler.resources import _compute_active_trade_routes
    world = _three()
    for x, y in (("A", "C"), ("C", "A")):
        world.relationships[x][y].disposition = Disposition.SUSPICIOUS
    assert ("A", "C") not in _compute_active_trade_routes(world)
    dp.sign_treaty(world, "trade_pact", _idx(world, "A"), _idx(world, "C"))
    assert ("A", "C") in _compute_active_trade_routes(world)


def test_acceptance_is_decided_by_the_target(monkeypatch):
    world = _three()
    civ = world.civ_map["A"]
    offer = dp.Offer("non_aggression", _idx(world, "C"), 1.0, ())
    monkeypatch.setattr(dp, "_offers", lambda w, c: [offer])
    monkeypatch.setattr(dp, "acceptance_utility", lambda *a, noise=True, **k: 0.05 if not noise else -0.5)
    event = dp.resolve_diplomacy_action(civ, world)
    assert event.event_type == "diplomacy" and "rebuffed" in event.description
    assert not world.diplomacy.treaties and world.diplomacy.counts["rejected:non_aggression"] == 1
    assert dp._on_cooldown(world.diplomacy, _idx(world, "A"), _idx(world, "C"), "non_aggression", world.turn)
    monkeypatch.setattr(dp, "acceptance_utility", lambda *a, **k: 0.5)
    world.diplomacy.cooldowns.clear()
    event = dp.resolve_diplomacy_action(civ, world)
    assert world.diplomacy.active("non_aggression") and "concluded" in event.description
    # An offer the proposer expects to fail is not made at all.
    monkeypatch.setattr(dp, "acceptance_utility", lambda *a, **k: -1.0)
    assert dp.resolve_diplomacy_action(civ, world) is None


def test_tribute_installments_complete_or_default(monkeypatch):
    _no_noise(monkeypatch)
    from chronicler.models import TreatyRecord
    for can_pay in (True, False):
        world = war_world(treasury_b=200 if can_pay else 0)
        dp.set_diplomacy_enabled(world, True)
        world.civ_map["B"].military = world.civ_map["A"].military = 30
        record = TreatyRecord(turn=0, name="The Iron Pact", war_key="A|B", parties=["A", "B"],
                              winner="A", kind="negotiated", aim="tribute")
        peace, tribute = dp.on_campaign_peace(world, record, None, tribute_total=40)
        assert peace.kind == "peace" and tribute.kind == "tribute"
        assert tribute.parties == [_idx(world, "B"), _idx(world, "A")]
        events = []
        for turn in range(1, dp.TRIBUTE_INSTALLMENTS + 2):
            world.turn = turn
            events += dp.collect_treaty_tribute(world)
        if can_pay:
            assert tribute.status == "expired" and tribute.terms["paid"] == 40
            assert world.civ_map["B"].treasury == 160 and world.civ_map["A"].treasury == 340
        else:
            assert tribute.status == "broken" and tribute.broken_by == _idx(world, "B")
            assert tribute.terms["missed"] == dp.TRIBUTE_MAX_MISSED
            assert any(e.event_type == "treaty_broken" for e in events)


def test_campaign_peace_emits_a_peace_treaty_and_tribute_in_installments():
    world = war_world(treasury_b=100)
    dp.set_diplomacy_enabled(world, True)
    ctx, war = start_war(world)
    war.aim, war.score = "tribute", 40
    from chronicler.war.peace import conclude_peace
    record = conclude_peace(ctx, war, "negotiated", "A")
    assert record.treasury_paid == 0 and world.civ_map["B"].treasury == 100  # nothing paid at once
    kinds = {t.kind: t for t in world.diplomacy.treaties}
    assert set(kinds) == {"peace", "tribute"}
    peace_event = next(e for e in ctx.events if e.event_type == "peace_treaty")
    assert kinds["peace"].event_id == peace_event.event_id and kinds["peace"].name == record.name
    assert kinds["tribute"].terms["total"] == 20 + 20 and "over" in peace_event.description


def test_capitulation_that_would_extinguish_makes_a_vassal_instead(monkeypatch):
    assert dp.SPARE_LAST_REGION is False  # the lever is off by default: states fall as on base
    monkeypatch.setattr(dp, "SPARE_LAST_REGION", True)
    for on in (False, True):
        world = war_world()
        dp.set_diplomacy_enabled(world, on)
        ctx, war = start_war(world)
        war.aim = "conquest"
        from chronicler.war.occupation import start_occupation
        from chronicler.war.peace import conclude_peace
        for region in ("Crag", "Dun", "Edge"):
            start_occupation(ctx, world.region_map[region], world.civ_map["A"], war, None)
        record = conclude_peace(ctx, war, "capitulation", "A")
        if on:
            assert world.civ_map["B"].regions == ["Dun"]  # keeps its capital
            assert record.vassalized and sorted(record.regions_ceded) == ["Crag", "Edge"]
            vr = world.vassal_relations[0]
            assert (vr.overlord, vr.vassal, vr.stage) == ("A", "B", "vassal")
        else:
            assert world.civ_map["B"].regions == [] and not world.vassal_relations


def test_by_default_a_capitulation_still_extinguishes_under_diplomacy():
    world = war_world()
    dp.set_diplomacy_enabled(world, True)
    ctx, war = start_war(world)
    war.aim = "conquest"
    from chronicler.war.occupation import start_occupation
    from chronicler.war.peace import conclude_peace
    for region in ("Crag", "Dun", "Edge"):
        start_occupation(ctx, world.region_map[region], world.civ_map["A"], war, None)
    record = conclude_peace(ctx, war, "capitulation", "A")
    assert world.civ_map["B"].regions == [] and not record.vassalized and not world.vassal_relations


def test_instant_war_on_the_last_region_vassalizes_under_the_ladder(monkeypatch):
    from chronicler import action_engine as ae
    from chronicler.politics import choose_vassalize_or_absorb  # noqa: F401  (patched below)
    monkeypatch.setattr("chronicler.politics.choose_vassalize_or_absorb", lambda *a: False)
    monkeypatch.setattr(dp, "SPARE_LAST_REGION", True)
    world = _three()
    world.campaigns_enabled = False
    world.civ_map["A"].military = 100
    world.civ_map["C"].military = 1
    result = ae.resolve_war(world.civ_map["A"], world.civ_map["C"], world, seed=1)
    assert result.outcome == "attacker_wins"
    assert world.civ_map["C"].regions == ["Fen"]
    assert any(vr.vassal == "C" and vr.stage == "vassal" for vr in world.vassal_relations)


# --- polity ladder --------------------------------------------------------------------------

def _subject(world, stage="client", *, since=-100, integration=0.0):
    vr = VassalRelation(overlord="A", vassal="C", stage=stage, stage_turn=since,
                        integration=integration, tribute_rate=dp._tribute_rate(world, stage),
                        crown=world.civ_map["A"].leader.name if stage == "union" else None)
    world.vassal_relations.append(vr)
    return vr


def _strong_overlord(world):
    a, c = world.civ_map["A"], world.civ_map["C"]
    a.military, a.stability, a.population = 90, 60, 200
    c.military, c.stability, c.population = 5, 40, 20
    c.values = list(a.values)
    a.civ_majority_faith = c.civ_majority_faith = 1


def test_ladder_climbs_client_vassal_union_and_annexes(monkeypatch):
    _no_noise(monkeypatch)
    world = _three()
    _strong_overlord(world)
    vr = _subject(world, "client")
    world.turn = 200
    stages = []
    for turn in range(200, 320):
        world.turn = turn
        world.region_map["Fen"].adjacencies = ["Brook", "Crag"]
        events = dp.tick_diplomacy(world, [])
        for ev in events:
            stages.append(ev.event_type)
        if not world.civ_map["C"].regions:
            break
    assert stages[:2] == ["vassal_promoted", "vassal_promoted"]
    assert stages[-1] == "union_annexation"
    assert world.civ_map["C"].regions == [] and "Fen" in world.civ_map["A"].regions
    assert world.region_map["Fen"].controller == "A" and vr not in world.vassal_relations
    assert world.last_twilight_absorption_turn == world.turn
    assert world.exile_modifiers and world.exile_modifiers[-1].original_civ_name == "C"
    counts = world.diplomacy.counts
    assert counts["promoted:vassal"] == counts["promoted:union"] == counts["annexed"] == 1
    # Tribute follows the stage: 5% client, 15% vassal, 25% union.
    assert dp._tribute_rate(world, "client") < dp._tribute_rate(world, "vassal") < dp._tribute_rate(world, "union")


def test_ladder_loosens_step_by_step_when_the_overlord_weakens(monkeypatch):
    monkeypatch.setattr(dp, "LOOSEN_CHANCE", {"client": 1.0, "vassal": 1.0, "union": 1.0})
    monkeypatch.setattr(dp, "LOOSEN_MIN_TURNS", 0)
    world = _three()
    _strong_overlord(world)
    world.civ_map["A"].stability = 5  # torn by unrest
    vr = _subject(world, "union", integration=50.0)
    seen = []
    for turn in range(1, 5):
        world.turn = turn
        for ev in dp.tick_diplomacy(world, []):
            seen.append((ev.event_type, vr.stage if vr in world.vassal_relations else None))
    assert seen == [("vassal_loosened", "vassal"), ("vassal_loosened", "client"),
                    ("vassal_loosened", None)]
    assert not world.vassal_relations
    assert world.diplomacy.counts["weakness:unrest"] == 3


def test_union_crowns_part_when_the_overlord_ruler_changes(monkeypatch):
    monkeypatch.setattr(dp, "CROWN_PART_CHANCE", 1.0)
    world = _three()
    _strong_overlord(world)
    vr = _subject(world, "union", integration=10.0)
    world.civ_map["A"].leader.name = "A New Ruler"
    world.turn = 1
    events = dp.tick_diplomacy(world, [])
    assert vr.stage == "vassal" and vr.crown is None
    assert events[0].event_type == "vassal_loosened" and world.diplomacy.counts["crown_parted"] == 1
    # An integrated union simply passes to the new ruler.
    world2 = _three()
    _strong_overlord(world2)
    vr2 = _subject(world2, "union", integration=80.0)
    world2.civ_map["A"].leader.name = "A New Ruler"
    world2.turn = 1
    dp.tick_diplomacy(world2, [])
    assert vr2.stage == "union" and vr2.crown == "A New Ruler"


def test_a_revolt_by_the_rust_politics_pass_is_remembered():
    world = _three()
    _subject(world, "vassal")
    dp.tick_diplomacy(world, [])  # mirror the subject
    world.vassal_relations.clear()  # politics step: the vassal rebelled
    rebellion = Event(turn=1, event_type="vassal_rebellion", actors=["C", "A"], description="")
    world.turn = 1
    dp.tick_diplomacy(world, [rebellion])
    revolts = {k: v for k, v in world.diplomacy.counts.items() if k.startswith("revolt:")}
    assert sum(revolts.values()) == 1  # keyed by the stage it reached before revolting
    assert dp.memory(world, "A", "C").grievance[TREATY] == dp.GRIEVANCE_REVOLT
    assert dp.trust(world, "A", "C") == dp.TRUST_REVOLT


def test_vassal_rebellion_cites_the_subjection_only_with_diplomacy_on():
    world = _three()
    _subject(world, "vassal")
    entry = Event(turn=0, event_type="vassalization", actors=["A", "C"], description="")
    prov.observe_now(world, entry)
    prov.remember(world, prov.key("subject", "C"), entry)
    rebellion = Event(turn=0, event_type="vassal_rebellion", actors=["C", "A"], description="")
    assert entry.event_id in prov.CAUSE_RULES["vassal_rebellion"](world, rebellion)
    dp.set_diplomacy_enabled(world, False)
    assert entry.event_id not in prov.CAUSE_RULES["vassal_rebellion"](world, rebellion)


def test_twilight_decliner_becomes_a_client_instead_of_being_absorbed():
    from chronicler.politics import prepare_twilight_absorption
    for on in (False, True):
        world = _three()
        dp.set_diplomacy_enabled(world, on)
        c = world.civ_map["C"]
        c.decline_turns = 60
        world.civ_map["A"].stability = world.civ_map["B"].stability = 30  # too low for the legacy step
        world.turn = 100
        events, eligible = prepare_twilight_absorption(world)
        if on:
            assert eligible == frozenset() and world.vassal_relations[0].stage == "client"
            assert events[0].event_type == "vassalization" and "client" in events[0].description
            # Once a subject, the twilight gate never hands it to the absorption pass.
            assert prepare_twilight_absorption(world)[1] == frozenset()
        else:
            assert eligible == frozenset({_idx(world, "C")}) and not world.vassal_relations


def test_a_personal_union_leaves_foreign_policy_to_the_overlord():
    world = _three()
    _subject(world, "union")
    # Union partners regard each other as FRIENDLY at least, memory or not.
    world.relationships["C"]["A"].disposition = Disposition.SUSPICIOUS
    assert world.relationships["C"]["A"].memory is None
    dp._apply_dispositions(world)
    dp._apply_dispositions(world)
    assert world.relationships["C"]["A"].disposition == Disposition.FRIENDLY
    eligible = ActionEngine(world).get_eligible_actions(world.civ_map["C"])
    assert not set(eligible) & dp.UNION_FORBIDDEN
    world.vassal_relations[0].stage = "client"
    assert ActionType.DIPLOMACY in ActionEngine(world).get_eligible_actions(world.civ_map["C"])


def test_weight_bucket_is_clamped_and_recorded():
    world = _three()
    from chronicler.governance_runtime import set_governance_enabled
    set_governance_enabled(world, True)
    dp.add_grievance(world, "A", "B", OCCUPATION, 500.0)
    dp.sign_treaty(world, "trade_pact", _idx(world, "A"), _idx(world, "C"))
    mods = dp.weight_modifiers(world.civ_map["A"], world)
    assert mods[ActionType.WAR] == pytest.approx(1.4) and mods[ActionType.TRADE] == 1.2
    assert all(1 / 1.5 <= m <= 1.5 for m in mods.values())
    engine = ActionEngine(world)
    engine.compute_weights(world.civ_map["A"])
    assert "diplomacy" in engine.last_buckets


# --- runs, persistence and dormancy --------------------------------------------------------

def _fingerprint(world: WorldState) -> str:
    return world.model_dump_json()


def test_same_seed_runs_are_identical_and_treaties_happen():
    w1 = _advance(_world(11), 40)
    w2 = _advance(_world(11), 40)
    assert _fingerprint(w1) == _fingerprint(w2)
    assert w1.diplomacy.treaties, "40 turns of seed 11 sign treaties"


def test_save_load_resume_is_identical_with_live_treaties(tmp_path):
    seed, turns, split = 11, 40, 22
    straight = _world(seed)
    trace = []
    for _ in range(turns):
        _advance(straight, 1)
        trace.append(straight.model_dump_json())
    resumed = _advance(_world(seed), split)
    assert resumed.diplomacy.active(), "live treaties across the save point"
    assert any(rel.memory is not None for rels in resumed.relationships.values() for rel in rels.values())
    path = tmp_path / "state.json"
    resumed.save(path)
    resumed = WorldState.load(path)
    assert resumed.model_dump_json() == trace[split - 1]
    for turn in range(split, turns):
        _advance(resumed, 1)
        assert resumed.model_dump_json() == trace[turn], f"turn {turn + 1}"


def test_checkpoint_replay_continues_identically_with_diplomacy(tmp_path):
    from chronicler import checkpoint_replay as replay
    world = _world(11)
    report = replay.validate_replay(world, turns=36, split=18, checkpoint_path=tmp_path / "cp.json")
    assert report["status"] == "PASS" and report["compared_resumed_turns"] == 18


def test_feature_off_never_runs_diplomacy_code(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("diplomacy invoked while disabled")

    for name in ("tick_diplomacy", "collect_treaty_tribute", "resolve_diplomacy_action", "war_guard",
                 "on_war_declared", "embargo_guard", "on_embargo", "weight_modifiers",
                 "restrict_eligible", "on_campaign_peace", "on_external_peace", "make_subject",
                 "on_vassalized", "trade_pact_pairs", "snapshot_summary", "spares_last_region",
                 "note_instant_battle", "revanche_bonus"):
        monkeypatch.setattr(dp, name, forbidden)
    world = _advance(_world(42, diplomacy=False), 40)
    assert world.diplomacy is None
    dumped = world.model_dump(mode="json")
    assert "diplomacy" not in dumped
    assert all("memory" not in rel for rels in dumped["relationships"].values() for rel in rels.values())
    assert all("stage" not in vr for vr in dumped["vassal_relations"])


def test_dormant_fields_are_omitted_and_old_saves_load():
    world = _world(diplomacy=False)
    raw = json.loads(world.model_dump_json())
    assert "diplomacy" not in raw
    assert "memory" not in Relationship().model_dump()
    assert set(VassalRelation(overlord="A", vassal="B").model_dump()) == {
        "overlord", "vassal", "tribute_rate", "turns_active"}
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert "diplomacy" not in snap.model_dump()
    on = _world()
    raw_on = json.loads(on.model_dump_json())
    assert raw_on["diplomacy"]["treaties"] == []
    raw_on.pop("diplomacy")
    assert WorldState.model_validate(raw_on).diplomacy is None
    # A saved world round-trips its diplomacy state exactly.
    _advance(on, 25)
    again = WorldState.model_validate_json(on.model_dump_json())
    assert again.diplomacy == on.diplomacy and again.model_dump_json() == on.model_dump_json()


def test_disabling_drops_memory_and_ladder_fields():
    world = _three()
    dp.add_grievance(world, "A", "B", WAR, 5.0)
    _subject(world, "vassal")
    dp.set_diplomacy_enabled(world, False)
    assert world.diplomacy is None and world.relationships["A"]["B"].memory is None
    assert world.vassal_relations[0].stage is None


def _cli_args(tmp_path, *, diplomacy, turns=12, agents="off"):
    return argparse.Namespace(
        seed=11, turns=turns, civs=4, regions=8, output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, pause_every=None, simulate_only=True, agents=agents, diplomacy=diplomacy,
    )


def test_cli_flag_persists_and_bundle_carries_diplomacy_history(tmp_path):
    from chronicler.main import _build_parser, execute_run
    assert _build_parser().parse_args(["--diplomacy"]).diplomacy is True
    assert _build_parser().parse_args(["--no-diplomacy"]).diplomacy is False
    assert _build_parser().parse_args([]).diplomacy is None
    execute_run(_cli_args(tmp_path, diplomacy=True, turns=20))
    state = json.loads((tmp_path / "state.json").read_text())
    assert "diplomacy" in state
    bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text())
    assert all("diplomacy" in snap for snap in bundle["history"])
    assert set(bundle["history"][-1]["diplomacy"]) == {"treaties", "subjects", "top_grievances", "counts",
                                                       "pairs"}
    assert "diplomacy" in bundle["world_state"]
    # The viewer's pair matrix matches the final memories of living civs.
    ws = bundle["world_state"]
    living = [c["name"] for c in ws["civilizations"] if c["regions"]]
    expected = [
        (h, o, [round(m["trust"], 1), round(sum(m["grievance"]), 1)])
        for h in living for o in living
        if o != h and (m := ws["relationships"].get(h, {}).get(o, {}).get("memory")) is not None
    ]
    pairs = bundle["history"][-1]["diplomacy"]["pairs"]
    assert pairs and [(h, o, v) for h, row in pairs.items() for o, v in row.items()] == expected
    metrics = dp.extract_diplomacy_metrics([bundle])
    assert metrics["runs"] == 1 and metrics["by_seed"][0]["turns"] == len(bundle["history"])
    assert dp.extract_diplomacy_metrics([{"history": [{}]}]) == {}
    from chronicler.analytics import generate_report
    batch = tmp_path / "batch"
    for name in ("seed_1", "seed_2"):
        (batch / name).mkdir(parents=True)
        (batch / name / "chronicle_bundle.json").write_text(json.dumps(bundle))
    assert generate_report(batch)["diplomacy"]["runs"] == 2


def test_new_worlds_default_off_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import execute_run
    fresh = tmp_path / "fresh"
    execute_run(_cli_args(fresh, diplomacy=None, turns=3))
    saved = json.loads((fresh / "state.json").read_text())
    assert ("diplomacy" in saved) is dp.DEFAULT_ENABLED_FOR_NEW_WORLDS is False
    on = tmp_path / "on"
    execute_run(_cli_args(on, diplomacy=True, turns=3))
    resumed = _cli_args(on, diplomacy=None, turns=5)
    resumed.resume = str(on / "state.json")
    resumed.state = str(on / "resumed.json")
    execute_run(resumed)
    assert "diplomacy" in json.loads((on / "resumed.json").read_text())


def test_gate_runner_forwards_the_switch_only_when_explicit():
    from scripts.m53b_run_validation import _diplomacy_args
    assert _diplomacy_args(argparse.Namespace(diplomacy=None)) == []
    assert _diplomacy_args(argparse.Namespace(diplomacy=True)) == ["--diplomacy"]
    assert _diplomacy_args(argparse.Namespace(diplomacy=False)) == ["--no-diplomacy"]
    assert _diplomacy_args(argparse.Namespace()) == []


def test_report_script_reads_on_and_off_batches(tmp_path):
    from chronicler.main import execute_run
    from scripts.diplomacy_report import batch_numbers, markdown, summarize
    for label, flag in (("off", False), ("on", True)):
        run = tmp_path / label / "seed_11"
        run.mkdir(parents=True)
        execute_run(_cli_args(run, diplomacy=flag, turns=20))
    off = summarize(batch_numbers(tmp_path / "off"))
    on = summarize(batch_numbers(tmp_path / "on"))
    assert off["runs"] == on["runs"] == 1
    assert sum(off[f"signed_{k}"] for k in ("non_aggression", "alliance", "trade_pact")) == 0
    assert "| Wars |" in markdown(["off", "on"], [off, on])


# --- native hybrid ------------------------------------------------------------------------------

@pytest.mark.native
def test_hybrid_diplomacy_runs_are_deterministic():
    pytest.importorskip("chronicler_agents")
    from chronicler.agent_bridge import AgentBridge

    def run():
        world = _world(46)
        world.agent_mode = "hybrid"
        bridge = AgentBridge(world, mode="hybrid")
        for _ in range(30):
            engine = ActionEngine(world)
            run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                     lambda w, ev: "", seed=world.seed + world.turn, agent_bridge=bridge)
        return world

    first, second = run(), run()
    assert first.diplomacy == second.diplomacy
    assert first.model_dump_json() == second.model_dump_json()
    assert first.diplomacy.counts
