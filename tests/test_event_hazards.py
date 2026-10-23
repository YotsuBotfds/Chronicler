"""Decaying-hazard event model, leader mortality and absorption pacing.

Correction 2026-10 (docs/integration/extinction-fix-2026-10.md): the old
non-decaying probability cascade drove rebellion/migration/border incidents/
leader death to probability 1.0 and every default world went extinct.
"""
from __future__ import annotations

import math
import random

import pytest

from chronicler.events import (
    BORDER_INCIDENT_RECIPROCITY_ALPHA,
    ENVIRONMENT_EVENTS,
    EVENT_CASCADE_RULES,
    HAZARD_DECAY,
    HAZARD_DECAY_TAU,
    PLAGUE_CONTACT_ALPHA,
    RANDOM_EVENT_TYPES,
    HazardContext,
    accession_age,
    base_hazard,
    civ_event_hazard,
    decay_excitations,
    ensure_leader_birth_turn,
    hazard_probability,
    ingest_turn_events,
    leader_age,
    leader_mortality_components,
    leader_mortality_hazard,
    pick_mortality_cause,
    rule_branching_ratio,
)
from chronicler.models import (
    ActiveCondition,
    Civilization,
    Event,
    Leader,
    NamedEvent,
    Region,
    VassalRelation,
    WorldState,
)
from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES, generate_world


def _civ(name: str, regions: list[str], **kw) -> Civilization:
    return Civilization(
        name=name,
        population=kw.pop("population", 40),
        military=30, economy=40, culture=kw.pop("culture", 40),
        stability=kw.pop("stability", 50),
        leader=kw.pop("leader", Leader(name=f"{name} I", trait="cautious", reign_start=0)),
        regions=regions,
        **kw,
    )


def _region(name: str, controller: str | None, adj: list[str], **kw) -> Region:
    return Region(
        name=name, terrain=kw.pop("terrain", "plains"),
        carrying_capacity=kw.pop("carrying_capacity", 50),
        resources="fertile", controller=controller, adjacencies=adj,
        population=kw.pop("population", 20), **kw,
    )


def _line_world() -> WorldState:
    """A - B adjacent; C isolated (no border, no trade)."""
    regions = [
        _region("ra", "A", ["rb"]),
        _region("rb", "B", ["ra"]),
        _region("rc", "C", []),
    ]
    civs = [_civ("A", ["ra"]), _civ("B", ["rb"]), _civ("C", ["rc"])]
    return WorldState(
        name="hz", seed=7, regions=regions, civilizations=civs,
        event_probabilities=dict(DEFAULT_EVENT_PROBABILITIES),
    )


# --- hazard math ----------------------------------------------------------------

def test_base_hazard_limits():
    assert base_hazard(0.0) == 0.0
    assert base_hazard(None) == 0.0
    assert math.isinf(base_hazard(1.0))
    assert hazard_probability(base_hazard(1.0)) == 1.0
    # A per-turn probability converts back exactly at share 1.
    assert hazard_probability(base_hazard(0.05)) == pytest.approx(0.05)


def test_excitation_decays_exponentially_and_expires():
    world = _line_world()
    civ = world.civilizations[0]
    civ.event_excitation = {"rebellion": 0.1}
    for _ in range(5):
        decay_excitations(world)
    assert civ.event_excitation["rebellion"] == pytest.approx(0.1 * HAZARD_DECAY ** 5, abs=1e-5)
    assert HAZARD_DECAY == pytest.approx(math.exp(-1 / HAZARD_DECAY_TAU))
    for _ in range(200):
        decay_excitations(world)
    assert "rebellion" not in civ.event_excitation


def test_event_excites_cascade_targets_of_involved_civ_only():
    world = _line_world()
    ingest_turn_events(world, [Event(turn=0, event_type="leader_death", actors=["A"],
                                     description="", importance=5)])
    a, b, c = world.civilizations
    for target, alpha in EVENT_CASCADE_RULES["leader_death"].items():
        assert a.event_excitation[target] == pytest.approx(alpha)
    assert b.event_excitation == {}
    assert c.event_excitation == {}


def test_excitation_raises_then_relaxes_hazard():
    world = _line_world()
    a = world.civilizations[0]
    ctx = HazardContext(world)
    before = civ_event_hazard(world, a, 0, "rebellion", ctx)
    ingest_turn_events(world, [Event(turn=0, event_type="leader_death", actors=["A"],
                                     description="", importance=5)])
    excited = civ_event_hazard(world, a, 0, "rebellion", HazardContext(world))
    assert excited == pytest.approx(before + EVENT_CASCADE_RULES["leader_death"]["rebellion"])
    for _ in range(80):
        ingest_turn_events(world, [])
    assert civ_event_hazard(world, a, 0, "rebellion", HazardContext(world)) == pytest.approx(before)


def test_formerly_dead_cascade_sources_now_excite():
    world = _line_world()
    a = world.civilizations[0]
    ingest_turn_events(
        world,
        [Event(turn=0, event_type="tech_advancement", actors=["A"], description="", importance=5)],
        [
            NamedEvent(name="The A Coup", event_type="coup", turn=0, actors=["A"], description=""),
            NamedEvent(name="Legacy", event_type="legacy", turn=0, actors=["A"], description=""),
            NamedEvent(name="Fall", event_type="rival_fall", turn=0, actors=["A", "B"], description=""),
        ],
    )
    assert world.civilizations[1].event_excitation == {}  # rival_fall applies to the celebrant
    assert a.event_excitation["discovery"] > 0  # tech_advancement + legacy
    assert a.event_excitation["cultural_renaissance"] > 0
    assert a.event_excitation["rebellion"] == pytest.approx(EVENT_CASCADE_RULES["coup"]["rebellion"])
    assert a.event_excitation["border_incident"] == pytest.approx(
        EVENT_CASCADE_RULES["coup"]["border_incident"] + EVENT_CASCADE_RULES["rival_fall"]["border_incident"]
    )


def test_cascade_targets_are_all_live_hazards():
    live = set(ENVIRONMENT_EVENTS) | set(RANDOM_EVENT_TYPES) | {"leader_death"}
    for source, rules in EVENT_CASCADE_RULES.items():
        assert set(rules) <= live, (source, set(rules) - live)


def test_cascade_is_subcritical():
    # Expected offspring per event < 1 => excitation cascades die out.
    assert rule_branching_ratio() < 0.6


def test_plague_excites_contacts_not_isolated_civs():
    world = _line_world()
    ingest_turn_events(world, [Event(turn=0, event_type="plague", actors=["A"],
                                     description="", importance=5)])
    a, b, c = world.civilizations
    # Shared border (0.5) plus any active trade route (0.5), capped at 1.5.
    assert PLAGUE_CONTACT_ALPHA * 0.5 <= b.event_excitation.get("plague", 0.0) <= PLAGUE_CONTACT_ALPHA * 1.5
    assert "plague" not in c.event_excitation
    # The infected civ's survivors are immune for a while (self-inhibition).
    assert a.event_excitation["plague"] == pytest.approx(EVENT_CASCADE_RULES["plague"]["plague"])
    assert a.event_excitation["plague"] < 0


def test_only_hazard_draws_and_named_sources_excite_during_a_turn():
    """Climate migrations/disasters share event types but are not hazard draws."""
    from chronicler.events import record_hazard_event, take_turn_cascade_events
    world = _line_world()
    climate_migration = Event(turn=0, event_type="migration", actors=["A"], description="", importance=5)
    rolled = Event(turn=0, event_type="rebellion", actors=["B"], description="", importance=5)
    tech = Event(turn=0, event_type="tech_advancement", actors=["C"], description="", importance=5)
    record_hazard_event(world, rolled)
    events = take_turn_cascade_events(world, [climate_migration, rolled, tech])
    assert events == [rolled, tech]
    assert world._hazard_events == []
    ingest_turn_events(world, events)
    a, b, c = world.civilizations
    assert a.event_excitation == {}
    assert b.event_excitation["leader_death"] == pytest.approx(EVENT_CASCADE_RULES["rebellion"]["leader_death"])
    assert c.event_excitation["discovery"] == pytest.approx(EVENT_CASCADE_RULES["tech_advancement"]["discovery"])


def test_border_incident_excites_counterparty():
    world = _line_world()
    ingest_turn_events(world, [Event(turn=0, event_type="border_incident", actors=["A", "B"],
                                     description="", importance=5)])
    assert world.civilizations[1].event_excitation["border_incident"] == pytest.approx(
        BORDER_INCIDENT_RECIPROCITY_ALPHA
    )


def test_drivers_read_state():
    world = _line_world()
    a, b, c = world.civilizations
    ctx = HazardContext(world)
    # Border incidents need a border.
    assert civ_event_hazard(world, c, 2, "border_incident", ctx) == 0.0
    assert civ_event_hazard(world, a, 0, "border_incident", ctx) > 0.0
    # An ongoing plague/drought is not a new outbreak.
    world.active_conditions.append(ActiveCondition(condition_type="plague", affected_civs=["A"],
                                                   duration=4, severity=60))
    world.active_conditions.append(ActiveCondition(condition_type="drought", affected_civs=["A"],
                                                   duration=3, severity=50))
    ctx = HazardContext(world)
    assert civ_event_hazard(world, a, 0, "plague", ctx) == 0.0
    assert civ_event_hazard(world, a, 0, "drought", ctx) == 0.0
    assert civ_event_hazard(world, b, 1, "plague", ctx) > 0.0
    # Low stability raises rebellion hazard.
    calm = civ_event_hazard(world, b, 1, "rebellion", ctx)
    b.stability = 5
    assert civ_event_hazard(world, b, 1, "rebellion", HazardContext(world)) > 2 * calm


def test_drought_hazard_follows_climate_phase():
    world = _line_world()
    b = world.civilizations[1]
    world.turn = 0  # temperate
    temperate = civ_event_hazard(world, b, 1, "drought", HazardContext(world))
    world.turn = int(0.65 * world.climate_config.period)  # drought phase
    drought = civ_event_hazard(world, b, 1, "drought", HazardContext(world))
    assert drought > 2 * temperate


def test_hybrid_rebellion_is_rollup_of_agent_decisions():
    world = _line_world()
    world.agent_mode = "hybrid"
    a = world.civilizations[0]
    quiet = HazardContext(world, agent_unrest={0: (0.0, 0.0)})
    assert civ_event_hazard(world, a, 0, "rebellion", quiet) == 0.0
    assert civ_event_hazard(world, a, 0, "migration", quiet) == 0.0
    restless = HazardContext(world, agent_unrest={0: (0.05, 0.10)})
    lam0 = base_hazard(world.event_probabilities["rebellion"], 0.25)
    assert civ_event_hazard(world, a, 0, "rebellion", restless) == pytest.approx(lam0)
    lam0m = base_hazard(world.event_probabilities["migration"], 0.25)
    assert civ_event_hazard(world, a, 0, "migration", restless) == pytest.approx(2 * lam0m)
    # Off mode keeps the aggregate driver.
    world.agent_mode = None
    assert civ_event_hazard(world, a, 0, "rebellion", quiet) > 0.0


def test_base_rates_stay_constant_over_a_run():
    world = generate_world(seed=11, num_regions=8, num_civs=4)
    before = dict(world.event_probabilities)
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn
    for _ in range(30):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    assert world.event_probabilities == before


# --- leader age and mortality ----------------------------------------------------

def test_accession_age_ranges_and_determinism():
    for stype, (lo, hi) in {"heir": (18, 40), "general": (35, 55), "elected": (40, 62)}.items():
        ages = [accession_age(stype, 1, t, "C", "N") for t in range(200)]
        assert min(ages) >= lo and max(ages) <= hi
        assert ages == [accession_age(stype, 1, t, "C", "N") for t in range(200)]


def test_birth_turn_inferred_for_old_saves_and_persisted():
    world = _line_world()
    leader = world.civilizations[0].leader
    assert leader.birth_turn is None
    birth = ensure_leader_birth_turn(leader, world)
    assert leader.birth_turn == birth
    assert 25 <= leader.reign_start - birth <= 48
    clone = Leader.model_validate(leader.model_dump())
    assert clone.birth_turn == birth
    # Old payloads without the field still validate.
    legacy = {k: v for k, v in leader.model_dump().items() if k != "birth_turn"}
    assert Leader.model_validate(legacy).birth_turn is None


def test_successor_gets_birth_turn():
    from chronicler.leaders import generate_successor
    world = generate_world(seed=5, num_regions=6, num_civs=2)
    world.turn = 40
    civ = world.civilizations[0]
    new = generate_successor(civ, world, seed=world.seed)
    assert new.birth_turn is not None
    assert 18 <= world.turn - new.birth_turn <= 62


def test_mortality_rises_with_age():
    world = _line_world()
    civ = world.civilizations[1]
    ctx = HazardContext(world)
    civ.leader.birth_turn = -30
    young = leader_mortality_hazard(world, civ, ctx)
    civ.leader.birth_turn = -75
    old = leader_mortality_hazard(world, civ, ctx)
    assert old > 10 * young
    assert leader_age(civ.leader, world) == 75


def test_mortality_terms_war_coup_and_scaling():
    world = _line_world()
    a = world.civilizations[0]
    a.leader.birth_turn = -40
    base = leader_mortality_components(world, a, HazardContext(world))
    assert base["battle"] == 0.0 and base["coup"] == 0.0
    world.active_wars = [("A", "B")]
    a.stability = 0
    loaded = leader_mortality_components(world, a, HazardContext(world))
    assert loaded["battle"] > 0.0 and loaded["coup"] > 0.0
    world.event_probabilities["leader_death"] = 0.0
    assert leader_mortality_hazard(world, a, HazardContext(world)) == 0.0
    world.event_probabilities["leader_death"] = 1.0
    assert hazard_probability(leader_mortality_hazard(world, a, HazardContext(world))) == 1.0
    assert pick_mortality_cause({"natural": 0.0, "battle": 0.0, "coup": 1.0, "misfortune": 0.0}, 0.3) == "coup"


def test_mean_reign_is_plausible():
    """Monte-Carlo of the default natural hazard: reigns of a few decades."""
    world = _line_world()
    civ = world.civilizations[1]
    ctx = HazardContext(world)
    rng = random.Random(3)
    reigns = []
    for trial in range(400):
        accession = 25 + trial % 25
        for t in range(200):
            civ.leader.birth_turn = -accession - t
            p = hazard_probability(leader_mortality_hazard(world, civ, ctx))
            if rng.random() < p:
                reigns.append(t)
                break
        else:
            reigns.append(200)
    mean = sum(reigns) / len(reigns)
    assert 15 <= mean <= 40, mean


def test_coup_death_installs_usurper(monkeypatch):
    from chronicler.simulation import _apply_event_effects
    world = generate_world(seed=9, num_regions=6, num_civs=2)
    civ = world.civilizations[0]
    civ.stability = 60
    monkeypatch.setattr("chronicler.simulation.compute_crisis_probability", lambda *a, **k: 0.0)
    _apply_event_effects("leader_death", civ, world, cause="coup")
    assert civ.leader.succession_type == "usurper"


# --- twilight absorption pacing ---------------------------------------------------

def _absorption_world(n_small: int = 3) -> WorldState:
    """One large civ ('Big') bordering n small one-region civs."""
    regions = [_region("big", "Big", [f"s{i}" for i in range(n_small)], carrying_capacity=80,
                       population=60)]
    civs = [_civ("Big", ["big"], culture=70, stability=70, population=60)]
    for i in range(n_small):
        regions.append(_region(f"s{i}", f"Small{i}", ["big"], carrying_capacity=20, population=3,
                               terrain="desert"))
        civs.append(_civ(f"Small{i}", [f"s{i}"], population=3))
    world = WorldState(name="tw", seed=3, turn=100, regions=regions, civilizations=civs,
                       event_probabilities=dict(DEFAULT_EVENT_PROBABILITIES))
    for r in world.regions[1:]:
        r.ecology.soil = 0.1
        r.ecology.water = 0.1
    return world


def test_unviable_absorption_requires_persistence_and_is_paced():
    from chronicler.politics import (
        TWILIGHT_ABSORPTION_SPACING, TWILIGHT_UNVIABLE_STREAK,
        check_twilight_absorption, note_twilight_absorptions, prepare_twilight_absorption,
    )
    world = _absorption_world(3)
    absorbed_turns = []
    for _ in range(TWILIGHT_UNVIABLE_STREAK + 3 * TWILIGHT_ABSORPTION_SPACING):
        _, eligible = prepare_twilight_absorption(world)
        assert len(eligible) <= 1
        events = check_twilight_absorption(world, eligible=eligible)
        note_twilight_absorptions(world, events)
        absorbed_turns.extend(world.turn for e in events if e.event_type == "twilight_absorption")
        world.turn += 1
    assert absorbed_turns, "persistently unviable civs are still absorbed eventually"
    assert absorbed_turns[0] >= 100 + TWILIGHT_UNVIABLE_STREAK - 1
    gaps = [b - a for a, b in zip(absorbed_turns, absorbed_turns[1:])]
    assert all(g >= TWILIGHT_ABSORPTION_SPACING for g in gaps), absorbed_turns


def test_transient_unviability_does_not_absorb():
    from chronicler.politics import TWILIGHT_UNVIABLE_STREAK, prepare_twilight_absorption
    world = _absorption_world(1)
    for _ in range(TWILIGHT_UNVIABLE_STREAK - 2):
        _, eligible = prepare_twilight_absorption(world)
        assert not eligible
        world.turn += 1
    # The drought ends before the streak completes: capacity recovers.
    world.regions[1].ecology.water = 0.7
    world.regions[1].ecology.soil = 0.6
    _, eligible = prepare_twilight_absorption(world)
    assert not eligible and world.civilizations[1].unviable_turns == 0


def test_declining_state_becomes_tributary_before_annexation():
    from chronicler.politics import TRIBUTARY_ANNEX_TURNS, prepare_twilight_absorption
    world = _absorption_world(1)
    small = world.civilizations[1]
    small.population = 30
    world.regions[1].ecology.soil = 0.3
    world.regions[1].carrying_capacity = 60
    small.decline_turns = 45
    events, eligible = prepare_twilight_absorption(world)
    assert not eligible
    assert [e.event_type for e in events] == ["vassalization"]
    assert world.vassal_relations == [VassalRelation(overlord="Big", vassal="Small0", tribute_rate=0.15)]
    world.vassal_relations[0].turns_active = TRIBUTARY_ANNEX_TURNS
    events, eligible = prepare_twilight_absorption(world)
    assert events == [] and eligible == frozenset({1})


def test_federation_does_not_admit_member_it_would_eject():
    """A civ neutral towards a member used to join, be ejected and pay every turn."""
    from chronicler.models import Disposition, Federation, Relationship
    from chronicler.politics import check_federation_dissolution, check_federation_formation
    world = _line_world()
    world.regions[2].adjacencies = []
    world.federations = [Federation(name="F", members=["A", "B"], founded_turn=0)]
    rel = lambda d, t=10: Relationship(disposition=d, allied_turns=t)
    world.relationships = {
        "A": {"B": rel(Disposition.ALLIED), "C": rel(Disposition.ALLIED)},
        "B": {"A": rel(Disposition.ALLIED), "C": rel(Disposition.NEUTRAL, 0)},
        "C": {"A": rel(Disposition.ALLIED), "B": rel(Disposition.NEUTRAL, 0)},
    }
    before = [c.stability for c in world.civilizations]
    for _ in range(3):
        check_federation_formation(world)
        check_federation_dissolution(world)
    assert world.federations[0].members == ["A", "B"]
    assert [c.stability for c in world.civilizations] == before


# --- determinism -----------------------------------------------------------------

def _run_digest(tmp_path, mode: str, turns: int, seed: int = 21) -> str:
    import argparse
    import hashlib
    from chronicler.main import execute_run

    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    args = argparse.Namespace(
        seed=seed, turns=turns, civs=4, regions=8, output=str(tmp_path / mode / "chronicle.md"),
        state=None, resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents=mode, narrator="local", validation_sidecar=False,
        relationship_stats=False, pause_every=None,
    )
    execute_run(args, world=world)
    payload = world.model_dump_json(exclude={"agent_events_raw", "pending_shocks"})
    return hashlib.sha256(payload.encode()).hexdigest()


def test_same_seed_is_identical_off_mode(tmp_path):
    assert _run_digest(tmp_path / "a", "off", 40) == _run_digest(tmp_path / "b", "off", 40)


def test_same_seed_is_identical_hybrid_mode(tmp_path):
    pytest.importorskip("chronicler_agents")
    assert _run_digest(tmp_path / "a", "hybrid", 40) == _run_digest(tmp_path / "b", "hybrid", 40)


# --- multi-seed survival ------------------------------------------------------------

def _run_world(tmp_path, mode: str, seed: int, turns: int) -> WorldState:
    import argparse
    from chronicler.main import execute_run

    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    args = argparse.Namespace(
        seed=seed, turns=turns, civs=4, regions=8,
        output=str(tmp_path / f"{mode}_{seed}" / "chronicle.md"),
        state=None, resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents=mode, narrator="local", validation_sidecar=False,
        relationship_stats=False, pause_every=None,
    )
    execute_run(args, world=world)
    return world


@pytest.mark.slow
@pytest.mark.parametrize("mode", ["off", "hybrid"])
def test_default_worlds_survive_and_stay_multipolar(tmp_path, mode):
    """Regression for the 2026-10 extinction: default worlds must stay alive."""
    if mode == "hybrid":
        pytest.importorskip("chronicler_agents")
    alive_counts = []
    for seed in range(42, 48):
        world = _run_world(tmp_path, mode, seed, 200)
        population = sum(r.population for r in world.regions if r.controller)
        assert population > 0, f"{mode} seed {seed} went extinct"
        alive = sum(1 for c in world.civilizations if c.regions)
        assert alive >= 2, f"{mode} seed {seed} collapsed to {alive} polity"
        alive_counts.append(alive)
        # Base rates are constant; no hazard is pinned at certainty.
        assert all(p < 0.5 for p in world.event_probabilities.values())
    assert sum(1 for a in alive_counts if a >= 3) >= len(alive_counts) // 2, alive_counts
