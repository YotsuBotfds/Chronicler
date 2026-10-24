"""Techniques: registry, diffusion, decay and regression, era derivation, effects,
persistence and dormancy (``--techniques``)."""
from __future__ import annotations

import argparse
import json

import pytest

import chronicler.contact_ledger as cl
import chronicler.techniques as T
from chronicler import provenance as prov
from chronicler.action_engine import ActionEngine
from chronicler.models import (
    Disposition, Event, InfrastructureType, Infrastructure, Relationship, ResourceType, TechEra,
    TurnSnapshot, WorldState,
)
from chronicler.simulation import run_turn
from chronicler.techniques_state import (
    CHANNELS, DOMAINS, TECHNIQUE_INDEX, TECHNIQUES, TechniqueState, techniques_on,
)
from chronicler.world_gen import generate_world
from war_fixtures import make_civ, make_region

K = TECHNIQUE_INDEX


# --- builders ---------------------------------------------------------------------------

def _world(seed: int = 42, *, techniques: bool = True, campaigns: bool = True) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = campaigns
    cl.set_contact_ledger_enabled(world, True)
    T.set_techniques_enabled(world, techniques)
    return world


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def _pair(*, pop: int = 60, terrain_b: str = "plains", ledger: bool = True) -> WorldState:
    """Two civs: X holds Alpha, Y holds Beta (not adjacent); contact only via the ledger."""
    alpha = make_region("Alpha", "X", pop)
    beta = make_region("Beta", "Y", pop)
    beta.terrain = terrain_b
    civs = [make_civ("X", ["Alpha"], military=30, treasury=0, capital="Alpha", era=TechEra.TRIBAL),
            make_civ("Y", ["Beta"], military=30, treasury=0, capital="Beta", era=TechEra.TRIBAL)]
    for civ in civs:
        civ.population = pop
        civ.culture = civ.economy = 0  # no inventions unless a test wants them
    rels = {"X": {"Y": Relationship(disposition=Disposition.NEUTRAL)},
            "Y": {"X": Relationship(disposition=Disposition.NEUTRAL)}}
    world = WorldState(name="Pair", seed=3, regions=[alpha, beta], civilizations=civs, relationships=rels)
    if ledger:
        cl.set_contact_ledger_enabled(world, True)
    T.set_techniques_enabled(world, True)
    return world


def _edge(world, channel: int, value: float) -> None:
    row = [0, 1, 0.0, 0.0, 0.0, 0.0]
    row[2 + channel] = value
    world.contact_ledger.edges = [tuple(row)]
    world.contact_ledger.invalidate()


def _seed_practice(world, region: int, keys, level: float = 0.9, civ: int = 0) -> None:
    """Start a ticked state in which ``region`` practises ``keys`` (and civ knows them)."""
    st = world.techniques
    if st.initialized_turn is None:
        T.tick_techniques(world)  # initialize the mirrors
        world.turn += 1
    rows = {(r[0], r[1]): r for r in st.rows}
    for key in keys:
        rows[(region, K[key])] = (region, K[key], level, -1, T.CH_SEEDED, civ)
    st.rows = [rows[k] for k in sorted(rows)]
    known = set(st.known[civ])
    known.update(K[key] for key in keys)
    st.known[civ] = sorted(known)
    st.invalidate()


def _tick(world, turns: int = 1) -> list[Event]:
    out: list[Event] = []
    for _ in range(turns):
        events = T.tick_techniques(world)
        prov.observe(world, events)
        out.extend(events)
        world.turn += 1
    return out


def _level(world, region: int, key: str) -> float:
    return world.techniques.practice_map().get((region, K[key]), 0.0)


# --- registry -------------------------------------------------------------------------------

PINNED_ORDER = (
    "irrigation", "bronze_working", "masonry", "sailing", "writing", "herbalism",
    "iron_working", "coinage", "horsemanship", "ox_plough", "roads",
    "law_codes", "aqueducts", "celestial_navigation", "siegecraft", "physicians",
    "heavy_plough", "castles", "stirrup", "banking", "compass", "lazarets",
    "printing", "gunpowder", "double_entry", "ocean_navigation",
    "steam_power", "vaccination", "railways", "telegraph",
)


def test_registry_is_append_only_and_well_formed():
    # Stored rows index into these tuples: their order is a storage contract.
    assert tuple(t.key for t in TECHNIQUES)[:len(PINNED_ORDER)] == PINNED_ORDER
    assert DOMAINS == ("agriculture", "metallurgy", "construction", "navigation", "writing",
                       "medicine", "commerce", "military")
    assert CHANNELS[:4] == cl.CHANNELS
    assert 20 <= len(TECHNIQUES) <= 30
    assert {t.domain for t in TECHNIQUES} == set(range(len(DOMAINS)))
    for k, t in enumerate(TECHNIQUES):
        for p in t.prereqs:
            assert K[p] < k and TECHNIQUES[K[p]].tier <= t.tier, (t.key, p)
    for tier in range(1, 8):
        assert len(T._BY_TIER[tier]) >= T.ERA_QUORUM[tier] >= 1
    from chronicler import techniques_state as S
    assert (S.GRAIN, S.TIMBER, S.BOTANICALS, S.FISH, S.SALT, S.ORE, S.PRECIOUS, S.EXOTIC) == tuple(
        int(r) for r in ResourceType)
    assert T.sustain_need(1) < T.sustain_need(4) < T.sustain_need(7)


# --- diffusion ------------------------------------------------------------------------------

@pytest.mark.parametrize("channel,carrier", [
    (cl.TRADE, "merchants"), (cl.PEOPLE, "migrants"), (cl.SOLDIERS, "soldiers"),
    (cl.PILGRIMS, "pilgrims"),
])
def test_techniques_diffuse_along_ledger_channels_and_name_the_carrier(channel, carrier):
    world = _pair()
    _edge(world, channel, 40.0)
    _seed_practice(world, 0, ["writing"])
    src = Event(turn=0, event_type="technique_invented", actors=["X"], description="X writes", importance=5)
    prov.remember(world, prov.key("technique", "X", "writing"), src)
    events = _tick(world, 40)
    assert _level(world, 1, "writing") > T.GAIN_LEVEL
    adopted = [e for e in events if e.event_type == "technique_adopted"]
    assert len(adopted) == 1 and adopted[0].actors == ["Y"] and adopted[0].region == "Beta"
    assert carrier in adopted[0].description and "X" in adopted[0].description
    assert adopted[0].causes == [src.event_id], "the adoption cites how the source civ got it"
    assert world.techniques.counts[f"gained:{CHANNELS[channel]}"] == 1
    assert K["writing"] in world.techniques.known[1]


def test_no_contact_no_diffusion_and_ledger_off_falls_back_to_borders():
    world = _pair()
    _seed_practice(world, 0, ["writing"])
    _tick(world, 30)
    assert _level(world, 1, "writing") == 0.0
    # Without the ledger, a shared border carries techniques.
    world = _pair(ledger=False)
    world.regions[0].adjacencies = ["Beta"]
    world.regions[1].adjacencies = ["Alpha"]
    _seed_practice(world, 0, ["writing"])
    events = _tick(world, 80)
    assert _level(world, 1, "writing") > T.GAIN_LEVEL
    assert any("across the border" in e.description for e in events if e.event_type == "technique_adopted")


def test_prerequisites_gate_adoption():
    world = _pair()
    _edge(world, cl.TRADE, 40.0)
    _seed_practice(world, 0, ["writing", "coinage", "law_codes"])
    _tick(world, 12)
    # Beta must take up writing and coinage before written law can root there.
    assert _level(world, 1, "law_codes") == 0.0 or _level(world, 1, "writing") >= T.PREREQ_LEVEL
    world2 = _pair()
    _edge(world2, cl.TRADE, 40.0)
    _seed_practice(world2, 0, ["law_codes"])  # prerequisites unknown anywhere
    _tick(world2, 30)
    assert _level(world2, 1, "law_codes") == 0.0


def test_unsuited_region_is_capped():
    world = _pair(terrain_b="plains")
    world.regions[1].resource_types = [0, 255, 255]  # grain only: no fish, not coast
    _edge(world, cl.TRADE, 60.0)
    _seed_practice(world, 0, ["sailing"])
    world.regions[0].terrain = "coast"
    _tick(world, 120)
    assert 0.0 < _level(world, 1, "sailing") <= T.UNSUITED_CAP + 1e-9
    assert _level(world, 0, "sailing") > 0.8


def test_resources_can_be_imported_by_trade():
    world = _pair()
    world.regions[0].resource_types = [5, 255, 255]   # Alpha has ore
    world.regions[1].resource_types = [0, 255, 255]   # Beta has none
    _edge(world, cl.TRADE, 5.0)
    links = T._contacts(world, [0, 1])
    suit = T._suitability(world, [0, 1], links)
    assert suit[1][K["bronze_working"]], "ore imported along a trade flow supplies bronze working"
    assert not suit[1][K["herbalism"]]
    _edge(world, cl.PEOPLE, 5.0)  # migrants do not supply ore
    links = T._contacts(world, [0, 1])
    assert not T._suitability(world, [0, 1], links)[1][K["bronze_working"]]


# --- decay and regression ---------------------------------------------------------------------

def _bronze_civ(pop: int) -> WorldState:
    world = _pair(pop=pop)
    world.regions[0].resource_types = [5, 255, 255]
    world.civilizations[0].tech_era = TechEra.BRONZE
    world.civilizations[0].military = 40
    _seed_practice(world, 0, ["masonry", "writing", "bronze_working"])
    return world


def test_era_holds_with_enough_people():
    world = _bronze_civ(pop=80)
    events = _tick(world, 60)
    assert world.civilizations[0].tech_era == TechEra.BRONZE
    assert not [e for e in events if e.event_type in ("technique_lost", "tech_regression")]
    assert _level(world, 0, "writing") > 0.8


def test_depopulation_loses_techniques_and_regresses_the_era_with_causes():
    world = _bronze_civ(pop=4)  # far below what even tier-1 techniques need
    plague = Event(turn=0, event_type="epidemic", actors=["X"], description="plague", importance=6,
                   region="Alpha", shock_category="plague")
    prov.remember(world, prov.key("pandemic", "Alpha"), plague)
    military = world.civilizations[0].military
    events = _tick(world, 60)
    lost = [e for e in events if e.event_type == "technique_lost"]
    assert len(lost) >= 1 and all("dwindle" in e.description for e in lost)
    assert all(plague.event_id in e.causes for e in lost), "losses cite the disease that thinned the people"
    regress = [e for e in events if e.event_type == "tech_regression"]
    assert len(regress) == 1 and world.civilizations[0].tech_era == TechEra.TRIBAL
    assert set(regress[0].causes) <= {e.event_id for e in lost} and regress[0].causes
    assert world.civilizations[0].military == military - 10, "the bronze era bonus is removed"
    assert world.techniques.counts["era_down"] == 1
    assert world.techniques.counts["lost:decay"] == len(lost)


def test_losing_the_land_loses_its_techniques():
    world = _pair()
    world.regions[0].resource_types = [5, 255, 255]
    _seed_practice(world, 0, ["writing"])
    _tick(world, 2)
    # Y takes Alpha: X loses writing with the land, Y takes it up.
    world.regions[0].controller = "Y"
    world.civilizations[0].regions = []
    world.civilizations[1].regions = ["Alpha", "Beta"]
    conquest = Event(turn=world.turn, event_type="annexation", actors=["Y", "X"], description="taken",
                     importance=7, region="Alpha")
    prov.remember(world, prov.key("conquest", "Alpha"), conquest)
    events = _tick(world, 1)
    gained = [e for e in events if e.event_type == "technique_adopted"]
    assert len(gained) == 1 and gained[0].actors == ["Y"] and "newly held Alpha" in gained[0].description
    assert conquest.event_id in gained[0].causes
    assert world.techniques.counts["gained:conquest"] == 1
    assert world.techniques.known[0] == []  # a civ without land keeps no known set


def test_m18_random_regression_does_not_run_with_techniques(monkeypatch):
    import chronicler.emergence as em
    calls = []
    original = em.check_tech_regression
    monkeypatch.setattr(em, "check_tech_regression", lambda *a, **k: calls.append(1) or original(*a, **k))
    _advance(_world(42, techniques=True), 5)
    assert calls == []
    _advance(_world(42, techniques=False), 5)
    assert len(calls) == 5


# --- era derivation ------------------------------------------------------------------------------

def test_derived_era_step_quorum_and_hysteresis():
    tier1 = list(T._BY_TIER[1])
    known = set(tier1[:3])
    levels = {k: 0.3 for k in tier1[:3]}
    assert T.derived_era_step(0, known, levels) == 1
    assert T.derived_era_step(0, set(tier1[:2]), levels) == 0        # below quorum
    assert T.derived_era_step(1, known, {k: 0.15 for k in tier1[:3]}) == 0   # kept above KEEP
    assert T.derived_era_step(0, known, {k: 0.15 for k in tier1[:3]}) == 0   # not yet PRACTISED
    assert T.derived_era_step(1, known, {k: 0.05 for k in tier1[:3]}) == -1  # fell below KEEP
    assert T.derived_era_step(2, known, levels) == -1                  # tier 2 missing


def test_advance_keeps_the_old_era_events_bonus_and_focus():
    world = _bronze_civ(pop=80)
    world.civilizations[0].tech_era = TechEra.IRON
    world.regions[0].terrain = "coast"
    keys = ["masonry", "writing", "bronze_working", "iron_working", "coinage", "roads",
            "law_codes", "aqueducts", "siegecraft"]
    _seed_practice(world, 0, keys)
    for key in ("law_codes", "aqueducts", "siegecraft"):
        prov.remember(world, prov.key("technique", "X", key),
                      Event(turn=0, event_type="technique_invented", actors=["X"], description=key,
                            importance=5))
    culture = world.civilizations[0].culture
    events = _tick(world, 1)
    civ = world.civilizations[0]
    assert civ.tech_era == TechEra.CLASSICAL and civ.culture == culture + 10
    adv = [e for e in events if e.event_type == "tech_advancement"]
    assert len(adv) == 1 and len(adv[0].causes) == 3
    assert any(e.event_type == "tech_focus_selected" for e in events) and civ.active_focus
    assert any(ne.event_type == "tech_breakthrough" for ne in world.named_events)
    assert world.techniques.counts["era_up"] == 1


# --- invention ------------------------------------------------------------------------------

def test_invention_needs_the_research_inputs(monkeypatch):
    world = _pair()
    civ = world.civilizations[0]
    monkeypatch.setattr(T, "_draw", lambda *a, **k: 0.0)
    civ.treasury = 1000
    _tick(world, 3)
    assert world.techniques.counts.get("invented", 0) == 0, "culture and economy below the thresholds"
    civ.culture = civ.economy = 60
    civ.treasury = 10
    _tick(world, 1)
    assert world.techniques.counts.get("invented", 0) == 0, "treasury below the cost"
    civ.treasury = 1000
    events = _tick(world, 1)
    inv = [e for e in events if e.event_type == "technique_invented"]
    assert len(inv) == 1 and inv[0].actors == ["X"] and inv[0].region == "Alpha"
    k = K[next(t.key for t in TECHNIQUES if t.label in inv[0].description)]
    assert TECHNIQUES[k].tier == 1
    assert civ.treasury == 1000 - 100 // T.INVENTIONS_PER_ERA
    assert _level(world, 0, TECHNIQUES[k].key) >= T.INVENT_LEVEL * 0.9
    assert prov.recall(world, prov.key("technique", "X", TECHNIQUES[k].key)) == inv[0].event_id


def test_scholarship_focus_cheapens_and_speeds_research(monkeypatch):
    world = _pair()
    civ = world.civilizations[0]
    civ.culture = civ.economy = 60
    civ.treasury = 1000
    civ.active_focus = "scholarship"
    monkeypatch.setattr(T, "_draw", lambda *a, **k: 0.0)
    _tick(world, 1)
    assert civ.treasury == 1000 - int(100 / T.INVENTIONS_PER_ERA * T.SCHOLARSHIP_COST)
    assert any(e.event_type == "capability_scholarship" for e in world.events_timeline)
    plain = _pair()
    assert T._research_multiplier(world, civ, {}) > T._research_multiplier(plain, plain.civilizations[0], {})


def test_invention_draws_are_namespaced_hashes(monkeypatch):
    seen = []
    real = T._draw
    monkeypatch.setattr(T, "_draw", lambda ns, w, *p: seen.append((ns, p)) or real(ns, w, *p))
    world = _pair()
    world.civilizations[0].culture = world.civilizations[0].economy = 80
    world.civilizations[0].treasury = 1000
    _tick(world, 5)
    assert seen and all(ns == "technique_invent" for ns, _ in seen)


# --- effects --------------------------------------------------------------------------------

def test_effects_follow_practice():
    world = _pair()
    world.regions[0].terrain = "coast"
    world.regions[0].resource_types = [0, 3, 5]
    _seed_practice(world, 0, ["bronze_working", "iron_working", "masonry", "castles", "irrigation",
                              "ox_plough", "herbalism", "physicians", "lazarets", "law_codes",
                              "coinage", "banking", "sailing"])
    _tick(world, 1)
    x, y = world.civilizations
    assert T.military_factor(world, x, True) > 1.1 and T.military_factor(world, y, True) == 1.0
    assert T.military_factor(world, x, False) > 1.1
    assert T.build_cost(world, world.regions[0], InfrastructureType.FORTIFICATIONS, 15) < 15
    assert T.build_cost(world, world.regions[1], InfrastructureType.ROADS, 10) == 10
    cfr = T.epidemic_cfr_factors(world)
    assert cfr[0] < 1.0 and cfr[1] == 1.0
    assert T.quarantine_efficacy(world, "X", 0.7) > 0.7 and T.quarantine_efficacy(world, "Y", 0.7) == 0.7
    assert T.credit_factor(world, 0) > 1.2 and T.credit_factor(world, 1) == 1.0
    assert T.yield_multiplier(world, world.regions[0], ResourceType.GRAIN) > 1.05
    assert T.yield_multiplier(world, world.regions[0], ResourceType.FISH) > 1.0
    assert T.yield_multiplier(world, world.regions[0], ResourceType.ORE) == 1.0
    T.set_techniques_enabled(world, False)
    assert T.yield_multiplier(world, world.regions[0], ResourceType.GRAIN) == 1.0
    assert T.yield_multiplier(None, world.regions[0], ResourceType.GRAIN) == 1.0


def test_navigation_extends_trade_routes_two_hops_across_the_coast():
    from chronicler.resources import get_active_trade_routes
    world = _pair()
    sea = make_region("Gulf", None, 0)
    sea.terrain = "coast"
    world.regions.append(sea)
    world.regions[0].adjacencies = ["Gulf"]
    world.regions[1].adjacencies = ["Gulf"]
    sea.adjacencies = ["Alpha", "Beta"]
    world.regions[0].terrain = "coast"
    world.invalidate_region_map()
    assert get_active_trade_routes(world) == []
    _seed_practice(world, 0, ["sailing", "writing", "celestial_navigation"])
    world.invalidate_trade_route_cache()
    assert get_active_trade_routes(world) == [("X", "Y")]
    # Roads: two hops along a road through a held region.
    road = _pair()
    mid = make_region("Pass", "X", 30)
    mid.infrastructure = [Infrastructure(type=InfrastructureType.ROADS, builder_civ="X", built_turn=0)]
    road.regions.append(mid)
    road.civilizations[0].regions.append("Pass")
    road.regions[0].adjacencies = ["Pass"]
    road.regions[1].adjacencies = ["Pass"]
    mid.adjacencies = ["Alpha", "Beta"]
    road.invalidate_region_map()
    assert get_active_trade_routes(road) == [("X", "Y")]  # Pass borders Beta directly
    road.regions[1].adjacencies = []
    mid.adjacencies = ["Alpha"]
    road.invalidate_region_map()
    road.invalidate_trade_route_cache()
    assert get_active_trade_routes(road) == []


def test_build_action_pays_the_discounted_cost():
    from chronicler.infrastructure import handle_build
    world = _pair()
    _seed_practice(world, 0, ["masonry"])
    _tick(world, 1)
    civ = world.civilizations[0]
    civ.treasury = 100
    handle_build(civ, world)
    spent = 100 - civ.treasury
    from chronicler.infrastructure import BUILD_SPECS
    full = BUILD_SPECS[world.regions[0].pending_build.type].cost
    assert spent == T.build_cost(world, world.regions[0], world.regions[0].pending_build.type, full) < full


# --- runs, persistence and dormancy --------------------------------------------------------

def test_same_seed_runs_are_identical_and_techniques_spread():
    w1 = _advance(_world(11), 60)
    w2 = _advance(_world(11), 60)
    assert w1.model_dump_json() == w2.model_dump_json()
    assert w1.techniques.counts.get("invented", 0) > 0
    assert w1.techniques.rows


def test_save_load_resume_is_identical_mid_diffusion(tmp_path):
    seed, turns, split = 11, 90, 70
    straight = _world(seed)
    trace = []
    for _ in range(turns):
        _advance(straight, 1)
        trace.append(straight.model_dump_json())
    resumed = _advance(_world(seed), split)
    st = resumed.techniques
    assert any(T.DROP_LEVEL < row[2] < 0.9 for row in st.rows), "practice still spreading at the save point"
    assert st.counts.get("invented", 0) > 0
    path = tmp_path / "state.json"
    resumed.save(path)
    resumed = WorldState.load(path)
    assert resumed.model_dump_json() == trace[split - 1]
    for turn in range(split, turns):
        _advance(resumed, 1)
        assert resumed.model_dump_json() == trace[turn], f"turn {turn + 1}"


def test_checkpoint_replay_continues_identically_with_techniques(tmp_path):
    from chronicler import checkpoint_replay as replay
    report = replay.validate_replay(_world(11), turns=40, split=20, checkpoint_path=tmp_path / "cp.json")
    assert report["status"] == "PASS" and report["compared_resumed_turns"] == 20


def test_derived_caches_reset_each_tick_and_after_load():
    world = _advance(_world(11), 40)
    st = world.techniques
    before = dict(st.practice_map())
    assert st._cache.practice is not None
    _advance(world, 1)
    assert st._cache.practice is None or st.practice_map() == {(r[0], r[1]): r[2] for r in st.rows}
    assert st.practice_map() != before or st.rows  # rebuilt from the new rows
    loaded = WorldState.model_validate_json(world.model_dump_json())
    assert loaded.techniques._cache.practice is None
    assert loaded.techniques == world.techniques
    assert loaded.techniques.practice_map() == world.techniques.practice_map()
    r0 = world.regions[0]
    assert (T.yield_multiplier(loaded, loaded.regions[0], ResourceType.GRAIN)
            == T.yield_multiplier(world, r0, ResourceType.GRAIN))


def test_feature_off_never_runs_technique_code(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("techniques invoked while disabled")

    for name in ("tick_techniques", "military_factor", "build_cost", "extend_trade_routes",
                 "epidemic_cfr_factors", "quarantine_efficacy", "credit_factor", "snapshot_summary",
                 "_update_practice", "_invent", "_derive_eras"):
        monkeypatch.setattr(T, name, forbidden)
    import chronicler.epidemiology as ep
    import chronicler.finance as F
    world = _world(42, techniques=False)
    ep.set_epidemiology_enabled(world, True)
    F.set_finance_enabled(world, True)
    _advance(world, 40)
    assert world.techniques is None
    assert "techniques" not in world.model_dump(mode="json")


def test_dormant_state_is_omitted_and_old_saves_load():
    world = _world(techniques=False)
    assert "techniques" not in json.loads(world.model_dump_json())
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert "techniques" not in snap.model_dump()
    on = _world()
    raw = json.loads(on.model_dump_json())
    assert raw["techniques"]["rows"] == []
    raw.pop("techniques")
    assert WorldState.model_validate(raw).techniques is None
    _advance(on, 30)
    again = WorldState.model_validate_json(on.model_dump_json())
    assert again.techniques == on.techniques and again.model_dump_json() == on.model_dump_json()
    assert techniques_on(on) and not techniques_on(object())
    T.set_techniques_enabled(on, False)
    assert on.techniques is None


def test_switching_on_mid_history_seeds_the_eras_it_finds():
    world = _advance(_world(42, techniques=False), 5)
    civ = world.civilizations[0]
    civ.tech_era = TechEra.BRONZE
    T.set_techniques_enabled(world, True)
    _advance(world, 1)
    st = world.techniques
    assert st.initialized_turn == 5
    seeded = {r[1] for r in st.rows if r[4] == T.CH_SEEDED}
    assert {K["masonry"], K["writing"]} <= seeded
    assert all(TECHNIQUES[k].tier <= 1 for k in seeded)


def _cli_args(tmp_path, *, techniques, turns=12, agents="off"):
    return argparse.Namespace(
        seed=11, turns=turns, civs=4, regions=8, output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, pause_every=None, simulate_only=True, agents=agents, techniques=techniques,
    )


def test_cli_flag_persists_and_bundle_carries_technique_history(tmp_path):
    from chronicler.main import _build_parser, execute_run
    assert _build_parser().parse_args(["--techniques"]).techniques is True
    assert _build_parser().parse_args(["--no-techniques"]).techniques is False
    assert _build_parser().parse_args([]).techniques is None
    execute_run(_cli_args(tmp_path, techniques=True, turns=30))
    state = json.loads((tmp_path / "state.json").read_text())
    assert "techniques" in state
    bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text())
    assert all("techniques" in snap for snap in bundle["history"])
    assert set(bundle["history"][-1]["techniques"]) == {"known", "practised", "rows"}
    assert "techniques" in bundle["world_state"]
    metrics = T.extract_technique_metrics([bundle])
    assert metrics["runs"] == 1 and metrics["by_seed"][0]["turns"] == len(bundle["history"])
    assert T.extract_technique_metrics([{"history": [{}]}]) == {}
    from chronicler.analytics import generate_report
    batch = tmp_path / "batch"
    for name in ("seed_1", "seed_2"):
        (batch / name).mkdir(parents=True)
        (batch / name / "chronicle_bundle.json").write_text(json.dumps(bundle))
    assert generate_report(batch)["techniques"]["runs"] == 2


def test_new_worlds_default_off_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import execute_run
    fresh = tmp_path / "fresh"
    execute_run(_cli_args(fresh, techniques=None, turns=3))
    saved = json.loads((fresh / "state.json").read_text())
    assert ("techniques" in saved) is T.DEFAULT_ENABLED_FOR_NEW_WORLDS is False
    on = tmp_path / "on"
    execute_run(_cli_args(on, techniques=True, turns=3))
    resumed = _cli_args(on, techniques=None, turns=5)
    resumed.resume = str(on / "state.json")
    resumed.state = str(on / "resumed.json")
    execute_run(resumed)
    assert "techniques" in json.loads((on / "resumed.json").read_text())


def test_gate_runner_forwards_the_switch_only_when_explicit():
    from scripts.m53b_run_validation import _techniques_args
    assert _techniques_args(argparse.Namespace(techniques=None)) == []
    assert _techniques_args(argparse.Namespace(techniques=True)) == ["--techniques"]
    assert _techniques_args(argparse.Namespace(techniques=False)) == ["--no-techniques"]
    assert _techniques_args(argparse.Namespace()) == []


def test_report_script_reads_on_and_off_batches(tmp_path):
    from chronicler.main import execute_run
    from scripts.techniques_report import batch_numbers, markdown, summarize
    for label, flag in (("off", False), ("on", True)):
        run = tmp_path / label / "seed_11"
        run.mkdir(parents=True)
        execute_run(_cli_args(run, techniques=flag, turns=40))
    off = summarize(batch_numbers(tmp_path / "off"))
    on = summarize(batch_numbers(tmp_path / "on"))
    assert off["runs"] == on["runs"] == 1
    assert off["known_t_end"] == 0 and on["invented"] >= 0
    assert "| Tech advances |" in markdown(["off", "on"], [off, on])


# --- native hybrid ------------------------------------------------------------------------------

@pytest.mark.native
def test_hybrid_technique_runs_are_deterministic():
    pytest.importorskip("chronicler_agents")
    from chronicler.agent_bridge import AgentBridge

    def run():
        world = _world(46)
        world.agent_mode = "hybrid"
        bridge = AgentBridge(world, mode="hybrid")
        for _ in range(40):
            engine = ActionEngine(world)
            run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                     lambda w, ev: "", seed=world.seed + world.turn, agent_bridge=bridge)
        return world

    first, second = run(), run()
    assert first.techniques == second.techniques
    assert first.model_dump_json() == second.model_dump_json()
    assert first.techniques.rows
