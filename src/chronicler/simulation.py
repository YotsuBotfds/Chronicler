"""Ten-phase simulation engine for the civilization chronicle.

Turn phases:
1. Environment — climate, conditions, terrain transitions, black swans
2. Economy / automatic effects — realized harvest, goods economy, trade routes, income, tribute, treasury
3. Production
4. Technology
5. Action selection + resolution (action engine)
6. Cultural milestones
7. Random events
8. Leader dynamics
9. Ecology — soil/water/forest tick, terrain transitions, famine checks
--- Agent tick (between Phase 9 and 10) ---
10. Consequences — emergence, factions, succession, named events, snapshot

The engine is deterministic given a seed. LLM narrates, never decides.

Performance note — Python critical path hotspots (audit batch I, 2026-04-01):
  Phase 10 (consequences) + settlement detection + economy post-processing all
  run single-threaded on the Python side, limiting 9950X utilization. These are
  the primary candidates for future Rust migration:
    - Phase 10 consequence evaluation (emergence, factions, succession)
    - Settlement detection (run_settlement_tick)
    - Economy post-processing (goods production, trade flow, pricing)
  Tracked as a performance follow-on for the next migration milestone (M60+).
"""
from __future__ import annotations

from chronicler import provenance
from chronicler.columnar import pylist
import logging
import random
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from chronicler.turn_artifacts import Phase10Inputs, TurnResult

from chronicler.events import (
    ENVIRONMENT_EVENTS,
    RANDOM_EVENT_TYPES,
    HazardContext,
    border_incident_partners,
    civ_event_hazard,
    hazard_probability,
    ingest_turn_events,
    leader_age,
    leader_mortality_components,
    pick_mortality_cause,
    record_hazard_event,
    take_turn_cascade_events,
)
# Historical module attributes (no longer used by the turn loop).
from chronicler.events import apply_probability_cascade, roll_for_event  # noqa: F401
from chronicler.settlements import run_settlement_tick
from chronicler.models import (
    ActionType,
    ActiveCondition,
    Civilization,
    CivShock,
    EMPTY_SLOT,
    Event,
    Leader,
    NamedEvent,
    TechEra,
    WorldState,
)
from chronicler.accumulator import normalize_shock
from chronicler.tech import check_tech_advancement
from chronicler.utils import (
    civ_index,
    clamp,
    get_civ,
    resolve_civ_faith_id,
    stable_hash_int,
    STAT_FLOOR,
    sync_civ_population,
    distribute_pop_loss,
    drain_region_pop,
    add_region_pop,
    stage_region_catastrophe_deaths,
)
from chronicler.diplomacy_state import diplomacy_on as _diplomacy_on
from chronicler.techniques_state import techniques_on as _techniques_on
from chronicler.gp_agendas_state import gp_agendas_on as _gp_agendas_on
from chronicler.emergence import get_severity_multiplier
from chronicler.leaders import (
    generate_successor, apply_leader_legacy, check_trait_evolution,
    check_rival_fall,
)
from chronicler.named_events import generate_tech_breakthrough_name
from chronicler.history_index import history_index
from chronicler.tech_focus import TechFocus, select_tech_focus, apply_focus_effects, remove_focus_effects
from chronicler.action_engine import resolve_action
from chronicler.succession import (
    compute_crisis_probability, trigger_crisis, tick_crisis,
    resolve_crisis, is_in_crisis, decay_grudges,
    apply_exile_pretender_drain, check_exile_restoration,
)
from chronicler.culture import tick_prestige, apply_value_drift, tick_cultural_assimilation, check_cultural_victories
from chronicler.movements import tick_movements
from chronicler.contact_ledger import ledger_enabled as _contact_ledger_on
from chronicler.epidemiology import epidemiology_enabled as _epidemiology_on
from chronicler.maritime import maritime_enabled as _maritime_on
from chronicler.nomads_state import nomads_on as _nomads_on
from chronicler.cities_state import cities_on as _cities_on
from chronicler.agent_movements_state import agent_movements_on as _agent_movements_on
from chronicler.guilds_state import guilds_on as _guilds_on
from chronicler.scholarship_state import scholarship_on as _scholarship_on
from chronicler.grain_reserves_state import grain_reserves_on as _grain_reserves_on
from chronicler.tuning import (
    K_DROUGHT_STABILITY, K_DROUGHT_ONGOING, K_PLAGUE_STABILITY,
    K_FAMINE_STABILITY, K_WAR_COST_STABILITY,
    K_CONDITION_ONGOING_DRAIN,
    K_MILITARY_FREE_THRESHOLD,
    K_REBELLION_STABILITY, K_LEADER_DEATH_STABILITY,
    K_BORDER_INCIDENT_STABILITY, K_RELIGIOUS_MOVEMENT_STABILITY,
    K_MIGRATION_STABILITY, K_STABILITY_RECOVERY,
    get_override,
)
from chronicler.arcs import classify_arc

logger = logging.getLogger(__name__)


def _agent_pool_tracks_population(world: WorldState) -> bool:
    """Return True when the Rust agent pool must see population shocks/deaths."""
    return getattr(world, "agent_mode", None) in {"demographics-only", "shadow", "hybrid"}


# Correction (2026-10): a plague outbreak killed a fixed 10 x severity people
# per civ, whatever its size. With per-civ hazards that is ~8% of a typical
# civ but wipes out a small or recovering one (500-turn worlds died this way
# once their population fell to a few dozen). The toll is now capped at a
# tenth of the civ's people; civs of 100+ lose exactly what they did before.
PLAGUE_POP_LOSS = 10
PLAGUE_MAX_POP_SHARE = 0.10


def _plague_pop_loss(civ_regions, mult: float) -> int:
    population = sum(r.population for r in civ_regions)
    return int(min(PLAGUE_POP_LOSS, PLAGUE_MAX_POP_SHARE * population) * mult)


def _agents_own_population(world: WorldState) -> bool:
    """Return True when Python-side population deltas must defer to Rust demographics."""
    return getattr(world, "agent_mode", None) in {"demographics-only", "hybrid"}


def _require_phase_acc_for_hybrid(world: WorldState, acc, phase_name: str) -> None:
    """Fail fast if a hybrid phase path is invoked without an accumulator."""
    if world.agent_mode == "hybrid" and acc is None:
        raise RuntimeError(
            f"{phase_name} requires acc in hybrid mode so shocks flow through "
            "the post-phase accumulator watermark"
        )


# --- Type aliases for callbacks ---

ActionSelector = Callable[[Civilization, WorldState], ActionType]
Narrator = Callable[[WorldState, list[Event]], str]


# --- Phase 1: Environment ---

def phase_environment(world: WorldState, seed: int, acc=None) -> list[Event]:
    """Check for natural disasters. At most one environment event per turn."""
    from chronicler.climate import get_climate_phase, check_disasters, process_migration

    events: list[Event] = []

    # Climate-driven disasters and migration
    climate_phase = get_climate_phase(world.turn, world.climate_config)

    # Decrement disaster cooldowns and resource suspensions
    for region in world.regions:
        for k in list(region.disaster_cooldowns):
            region.disaster_cooldowns[k] -= 1
        region.disaster_cooldowns = {k: v for k, v in region.disaster_cooldowns.items() if v > 0}
        # M35b: Reset capacity_modifier when all disaster cooldowns expire
        if not region.disaster_cooldowns and region.capacity_modifier != 1.0:
            region.capacity_modifier = 1.0
        for k in list(region.resource_suspensions):
            region.resource_suspensions[k] -= 1
        region.resource_suspensions = {k: v for k, v in region.resource_suspensions.items() if v > 0}
        for k in list(region.route_suspensions):
            region.route_suspensions[k] -= 1
        region.route_suspensions = {k: v for k, v in region.route_suspensions.items() if v > 0}

    disaster_events = check_disasters(world, climate_phase)
    events.extend(disaster_events)

    migration_events = process_migration(world, acc=acc)
    events.extend(migration_events)

    # Environment hazards (drought, plague, earthquake): per-civ decaying
    # hazards read real state (climate/water, endemic disease and contact,
    # terrain) instead of striking a random half of the living civs.
    hazard_ctx = HazardContext(world)
    for event_type in ENVIRONMENT_EVENTS:
        if event_type not in world.event_probabilities:
            continue
        if event_type == "plague" and _epidemiology_on(world):
            # Epidemiology replaces the hazard plague (tick_epidemics, Phase 1).
            continue
        affected: list[Civilization] = []
        rates: list[float] = []
        for civ_idx, civ in enumerate(world.civilizations):
            if not civ.regions:
                continue
            rate = civ_event_hazard(world, civ, civ_idx, event_type, hazard_ctx)
            p = hazard_probability(rate)
            if p <= 0.0:
                continue
            draw = random.Random(
                stable_hash_int("env_hazard", seed, civ_idx, event_type)
            ).random()
            if draw < p:
                affected.append(civ)
                rates.append(rate)
        if not affected:
            continue
        event = Event(
            turn=world.turn,
            event_type=event_type,
            actors=[c.name for c in affected],
            description="",  # Filled in by narrative engine
            importance=5,
        )
        # Provenance: the event that excited this hazard, where it mattered.
        provenance.cite(event, *(provenance.excitation_cause(world, c, event_type, r)
                                 for c, r in zip(affected, rates)))

        if event.event_type == "drought":
            for civ in affected:
                mult = get_severity_multiplier(civ, world)
                drain = int(get_override(world, K_DROUGHT_STABILITY, 3) * mult)
                if acc is not None:
                    civ_idx = civ_index(world, civ.name)
                    acc.add(civ_idx, civ, "stability", -drain, "signal")
                    acc.add(civ_idx, civ, "economy", -int(10 * mult), "signal")
                else:
                    civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
                    civ.economy = clamp(civ.economy - int(10 * mult), STAT_FLOOR["economy"], 100)
            world.active_conditions.append(
                ActiveCondition(
                    condition_type="drought",
                    affected_civs=event.actors,
                    duration=3,
                    severity=50,
                )
            )
        elif event.event_type == "plague":
            for civ in affected:
                mult = get_severity_multiplier(civ, world)
                civ_idx = civ_index(world, civ.name)
                # Direct mutation keeps Python-side phases honest, and the
                # one-turn catastrophe-death transient makes the same loss
                # survive Rust write-back in bridge-backed agent modes.
                civ_regions = [r for r in world.regions if r.controller == civ.name]
                actual_drains = distribute_pop_loss(civ_regions, _plague_pop_loss(civ_regions, mult))
                if _agent_pool_tracks_population(world):
                    for region, actual in zip(civ_regions, actual_drains):
                        stage_region_catastrophe_deaths(region, actual)
                sync_civ_population(civ, world)
                drain = int(get_override(world, K_PLAGUE_STABILITY, 3) * mult)
                if acc is not None:
                    acc.add(civ_idx, civ, "stability", -drain, "signal")
                else:
                    civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
            world.active_conditions.append(
                ActiveCondition(
                    condition_type="plague",
                    affected_civs=event.actors,
                    duration=4,
                    severity=60,
                )
            )
        elif event.event_type == "earthquake":
            for civ in affected:
                mult = get_severity_multiplier(civ, world)
                if acc is not None:
                    civ_idx = civ_index(world, civ.name)
                    acc.add(civ_idx, civ, "economy", -int(10 * mult), "signal")
                else:
                    civ.economy = clamp(civ.economy - int(10 * mult), STAT_FLOOR["economy"], 100)

        # Excitation from this event is ingested at end of turn
        # (events.ingest_turn_events); base rates stay constant.
        record_hazard_event(world, event)
        events.append(event)

    return events


# --- Phase 2: Automatic Effects ---

def apply_automatic_effects(
    world: WorldState,
    acc=None,
    cross_routes: list[tuple[str, str]] | None = None,
) -> list[Event]:
    """Phase 2: Automatic per-turn effects — maintenance, trade, specialization, mercs."""
    from chronicler.resources import get_active_trade_routes, get_self_trade_civs
    from chronicler.economy import filter_goods_trade_routes
    from chronicler.infrastructure import tick_infrastructure
    events: list[Event] = []

    # 0. Infrastructure tick (advance pending builds, mine degradation)
    infra_events = tick_infrastructure(world)
    events.extend(infra_events)

    # 1. Military maintenance: free up to threshold, then (mil-threshold)//10 per turn
    free_threshold = int(get_override(world, K_MILITARY_FREE_THRESHOLD, 30))
    for civ_idx, civ in enumerate(world.civilizations):
        if len(civ.regions) == 0:
            continue
        if civ.military > free_threshold:
            cost = (civ.military - free_threshold) // 10
            if acc is not None:
                acc.add(civ_idx, civ, "treasury", -cost, "keep")
            else:
                civ.treasury -= cost

    # 2. Trade income
    # H-6: Emit capability events here (Phase 2 is the authoritative call site)
    if cross_routes is None:
        cross_routes = get_active_trade_routes(world, emit_events=True)
    economic_cross_routes = filter_goods_trade_routes(world, cross_routes)
    for civ_a, civ_b in economic_cross_routes:
        a = get_civ(world, civ_a)
        b = get_civ(world, civ_b)
        if a:
            if acc is not None:
                a_idx = civ_index(world, a.name)
                acc.add(a_idx, a, "treasury", 2, "keep")
            else:
                a.treasury += 2
        if b:
            if acc is not None:
                b_idx = civ_index(world, b.name)
                acc.add(b_idx, b, "treasury", 2, "keep")
            else:
                b.treasury += 2
    for civ_name in sorted(get_self_trade_civs(world)):
        c = get_civ(world, civ_name)
        if c:
            if acc is not None:
                c_idx = civ_index(world, c.name)
                acc.add(c_idx, c, "treasury", 3, "keep")
            else:
                c.treasury += 3

    # Embargo set — used by both specialization and black market sections
    embargo_set = {(a, b) for a, b in world.embargoes} | {(b, a) for a, b in world.embargoes}

    # 3. Economic specialization
    for civ_idx, civ in enumerate(world.civilizations):
        controlled = [r for r in world.regions if r.controller == civ.name]
        if not controlled:
            continue
        resource_counts: dict = {}
        for r in controlled:
            for rtype in r.resource_types:
                if rtype == EMPTY_SLOT:
                    continue
                resource_counts[rtype] = resource_counts.get(rtype, 0) + 1
        if not resource_counts:
            continue
        primary = max(resource_counts, key=lambda r: resource_counts[r])
        civ_routes = [(a, b) for a, b in economic_cross_routes if civ.name in (a, b)]
        if not civ_routes:
            continue
        primary_routes = 0
        for a, b in civ_routes:
            route_regions = [r for r in world.regions
                            if r.controller in (a, b) and primary in r.resource_types]
            if route_regions:
                primary_routes += 1
        if len(civ_routes) > 0 and primary_routes / len(civ_routes) > 0.6:
            embargoed_routes = [(a, b) for a, b in civ_routes
                               if (a, b) in embargo_set or (b, a) in embargo_set]
            if embargoed_routes:
                penalty = int(civ.economy * 0.20)
                if acc is not None:
                    acc.add(civ_idx, civ, "treasury", -penalty, "keep")
                else:
                    civ.treasury -= penalty
            else:
                bonus = int(civ.economy * 0.15)
                if acc is not None:
                    acc.add(civ_idx, civ, "treasury", bonus, "keep")
                else:
                    civ.treasury += bonus

    # 4. Black market leakage for embargoed civs
    for civ_idx, civ in enumerate(world.civilizations):
        if not any(civ.name in pair for pair in embargo_set):
            continue
        # Check for adjacent non-embargoed neighbors
        for r in world.regions:
            if r.controller != civ.name:
                continue
            for adj_name in r.adjacencies:
                adj = next((ar for ar in world.regions if ar.name == adj_name), None)
                if adj and adj.controller and adj.controller != civ.name:
                    pair = tuple(sorted([civ.name, adj.controller]))
                    if pair not in embargo_set:
                        mult = get_severity_multiplier(civ, world)
                        if acc is not None:
                            acc.add(civ_idx, civ, "treasury", 1, "keep")
                            acc.add(civ_idx, civ, "stability", -int(3 * mult), "signal")
                        else:
                            civ.treasury += 1  # 30% of normal trade (2), min 1
                            civ.stability = clamp(civ.stability - int(3 * mult), STAT_FLOOR["stability"], 100)
                        break  # Only one black market route per civ per turn

    # 5. Ongoing war costs: -3/turn per active war
    # In accumulator mode, include already-queued keep mutations so the
    # zero-crossing check mirrors aggregate semantics instead of stale scalars.
    pending_war_treasury: dict[str, float] = {}
    if acc is not None and world.active_wars:
        for pending_idx, pending_civ in enumerate(world.civilizations):
            projected = float(pending_civ.treasury)
            for change in getattr(acc, "_changes", ()):
                if (
                    change.civ_id == pending_idx
                    and change.category == "keep"
                    and change.stat == "treasury"
                ):
                    projected += change.delta
            pending_war_treasury[pending_civ.name] = projected
    for war in world.active_wars:
        for civ_name in war:
            c = get_civ(world, civ_name)
            if c:
                war_mult = get_severity_multiplier(c, world)
                if acc is not None:
                    c_idx = civ_index(world, c.name)
                    pending_war_treasury[c.name] = pending_war_treasury.get(c.name, c.treasury) - 3
                    acc.add(c_idx, c, "treasury", -3, "keep")
                    if pending_war_treasury[c.name] <= 0:
                        drain = int(get_override(world, K_WAR_COST_STABILITY, 2) * war_mult)
                        acc.add(c_idx, c, "stability", -drain, "signal")
                else:
                    c.treasury -= 3
                    if c.treasury <= 0:
                        drain = int(get_override(world, K_WAR_COST_STABILITY, 2) * war_mult)
                        c.stability = clamp(c.stability - drain, STAT_FLOOR["stability"], 100)

    # 6. Mercenary system
    MAX_MERCS = 3
    for civ_idx, civ in enumerate(world.civilizations):
        if len(civ.regions) == 0:
            continue
        # Check merc pressure: military >> income
        if civ.military > 30 and civ.last_income > 0 and civ.military > civ.last_income * 3:
            civ.merc_pressure_turns += 1
        else:
            civ.merc_pressure_turns = max(0, civ.merc_pressure_turns - 1)
        # Spawn mercenary company after 3 turns of pressure
        if civ.merc_pressure_turns >= 3 and len(world.mercenary_companies) < MAX_MERCS:
            strength = min(10, civ.military // 5)
            if acc is not None:
                acc.add(civ_idx, civ, "military", -strength, "guard")
            else:
                civ.military = clamp(civ.military - strength, STAT_FLOOR["military"], 100)
            region = civ.regions[0] if civ.regions else "unknown"
            world.mercenary_companies.append({
                "strength": strength, "origin_civ": civ.name,
                "location": region, "available": True, "hired_by": None,
            })
            events.append(Event(
                turn=world.turn, event_type="mercenary_spawned",
                actors=[civ.name],
                description=f"A mercenary company forms from {civ.name}'s overextended military.",
                importance=5,
            ))
            civ.merc_pressure_turns = 0
    # Mercenary hiring: underdog priority in active wars
    for merc in world.mercenary_companies:
        if merc["strength"] <= 0 or not merc["available"] or merc["hired_by"]:
            continue
        # Find weakest belligerent with treasury
        candidates = []
        for war in world.active_wars:
            for civ_name in war:
                c = get_civ(world, civ_name)
                if c and c.regions and c.treasury >= 10:
                    candidates.append(c)
        if candidates:
            candidates.sort(key=lambda c: (c.military, -c.treasury))
            hirer = candidates[0]
            if acc is not None:
                hirer_idx = civ_index(world, hirer.name)
                acc.add(hirer_idx, hirer, "treasury", -10, "keep")
                acc.add(hirer_idx, hirer, "military", merc["strength"], "guard")
            else:
                hirer.treasury -= 10
                hirer.military = clamp(hirer.military + merc["strength"], STAT_FLOOR["military"], 100)
            merc["hired_by"] = hirer.name
            merc["available"] = False
    # Decay unhired mercs
    for merc in world.mercenary_companies:
        if merc["available"] and not merc["hired_by"]:
            merc["strength"] -= 2
    # Disband hired mercs whose war ended
    for merc in list(world.mercenary_companies):
        if merc["hired_by"]:
            hirer = get_civ(world, merc["hired_by"])
            still_at_war = any(merc["hired_by"] in w for w in world.active_wars)
            if not still_at_war or hirer is None or not hirer.regions:
                # M13 contracts disband rather than returning to the hire pool.
                # Military may have changed through combat or other effects;
                # do not infer a reversible grant from the current scalar.
                world.mercenary_companies.remove(merc)
    # Remove dead mercs
    world.mercenary_companies = [m for m in world.mercenary_companies if m["strength"] > 0]

    # 7. Reset last_income (re-accumulated during Phase 3)
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue
        civ.last_income = 0

    from chronicler.politics import apply_governing_costs, collect_tribute
    from chronicler.politics import apply_proxy_wars, apply_exile_effects
    from chronicler.politics import (
        apply_balance_of_power, apply_fallen_empire, apply_twilight,
        apply_long_peace, update_peak_regions,
    )
    events.extend(apply_governing_costs(world, acc=acc))
    # Phase 8 governance: institutional enforcement is paid right after the
    # base governing cost and recorded for late Phase 10 (M63a bookkeeping).
    if getattr(world, "governance", None) is not None:
        from chronicler.governance_runtime import fund_institutions_phase2
        events.extend(fund_institutions_phase2(world, acc=acc))
    events.extend(collect_tribute(world, acc=acc))
    if _diplomacy_on(world):
        # Diplomacy: installments of tribute treaties (keep category).
        from chronicler.diplomacy import collect_treaty_tribute
        events.extend(collect_treaty_tribute(world, acc=acc))
    events.extend(apply_proxy_wars(world, acc=acc))
    events.extend(apply_exile_effects(world, acc=acc))
    events.extend(apply_balance_of_power(world))
    events.extend(apply_fallen_empire(world, acc=acc))
    events.extend(apply_twilight(world, acc=acc))
    events.extend(apply_long_peace(world, acc=acc))
    update_peak_regions(world)

    # Phase 2 politics/disposition updates can change route availability.
    # Refresh once here so knowledge sharing and pandemic spread read current data.
    world.invalidate_trade_route_cache()
    refreshed_routes = get_active_trade_routes(world)

    # Trade knowledge sharing (fog of war)
    from chronicler.exploration import tick_trade_knowledge_sharing
    knowledge_events = tick_trade_knowledge_sharing(world, routes=refreshed_routes)
    events.extend(knowledge_events)

    # M17b: Exile pretender stability drain
    apply_exile_pretender_drain(world, acc=acc)

    # M17d: Tradition ongoing effects
    from chronicler.traditions import apply_tradition_effects
    apply_tradition_effects(world)

    # M17c: Hostage turn ticking
    from chronicler.relationships import tick_hostages
    bridge = getattr(world, "_agent_bridge", None)
    tick_hostages(world, acc=acc, bridge=bridge)

    # M18: Pandemic tick
    from chronicler.emergence import tick_pandemic
    events.extend(tick_pandemic(world, acc=acc, routes=refreshed_routes))

    # Trade-route caching is phase-scoped: clear the Phase 2 view so later
    # diplomacy/war/federation mutations rebuild from current world state.
    world.invalidate_trade_route_cache()

    return events


# --- Phase 3: Production ---

def phase_production(world: WorldState, acc=None) -> None:
    """Generate income and adjust population for each civilization."""
    from chronicler.ecology import effective_capacity
    for civ_idx, civ in enumerate(world.civilizations):
        if not civ.regions:
            # A fallen or exiled civ holds no land and produces nothing. Its
            # treasury waits unchanged for a possible restoration.
            civ.last_income = 0
            continue
        # Base income
        income = civ.economy // 5 + len(civ.regions) * 2
        # Condition penalty
        penalty = sum(c.severity for c in world.active_conditions if civ.name in c.affected_civs)
        if acc is not None:
            acc.add(civ_idx, civ, "treasury", max(0, income - penalty), "keep")
        else:
            civ.treasury += max(0, income - penalty)
        # Track last_income for mercenary spawn
        civ.last_income = max(0, income - penalty)
        # Population
        region_capacity = sum(
            effective_capacity(r)
            for r in world.regions if r.controller == civ.name
        )
        max_pop = min(1000, region_capacity)
        civ_regions = [r for r in world.regions if r.controller == civ.name]
        if civ.economy > civ.population // 3 and civ.stability > 10 and civ.population < max_pop:
            if civ_regions:
                growth = max(5, 5 * len(civ_regions))
                per_region = max(1, growth // len(civ_regions))
                if acc is not None and _agents_own_population(world):
                    acc.add(civ_idx, civ, "population", per_region * len(civ_regions), "guard")
                else:
                    for r in civ_regions:
                        add_region_pop(r, per_region)
                    sync_civ_population(civ, world)
        elif civ.stability <= 5 and civ.population > 1:
            if civ_regions:
                if acc is not None and _agents_own_population(world):
                    acc.add(civ_idx, civ, "population", -5, "guard")
                else:
                    target = max(civ_regions, key=lambda r: r.population)
                    drain_region_pop(target, 5)
                    sync_civ_population(civ, world)
        # Passive repopulation: empty controlled regions slowly recover
        if civ_regions:
            empty_count = sum(1 for r in civ_regions if r.population == 0)
            if acc is not None and _agents_own_population(world):
                if empty_count > 0:
                    acc.add(civ_idx, civ, "population", 3 * empty_count, "guard")
            else:
                for r in civ_regions:
                    if r.population == 0:
                        add_region_pop(r, 3)
                sync_civ_population(civ, world)

        # M21: MECHANIZATION gives +2 treasury per active mine
        if civ.active_focus == "mechanization":
            from chronicler.models import InfrastructureType
            mine_count = sum(
                1 for r in world.regions if r.controller == civ.name
                for i in r.infrastructure if i.type == InfrastructureType.MINES and i.active
            )
            if mine_count > 0:
                if acc is not None:
                    acc.add(civ_idx, civ, "treasury", mine_count * 2, "keep")
                else:
                    civ.treasury += mine_count * 2
                world.events_timeline.append(Event(
                    turn=world.turn, event_type="capability_mechanization",
                    actors=[civ.name], description=f"{civ.name} mechanization yields {mine_count * 2} from mines",
                    importance=1,
                ))

    # Stability recovery: passive per-turn recovery, halved during severe conditions.
    # B-1 fix: In hybrid mode, stability is overwritten by _write_back (mean_sat *
    # mean_loy * 100), so "keep" routing is dead code.  Route as "guard-shock" so
    # the recovery feeds the Rust tick as a positive shock signal.  --agents=off
    # applies it through acc.apply(); standalone acc=None callers mutate
    # directly.  Shadow/demographics-only flush with apply_keep() and do not
    # route shocks (C-10), so this recovery does not reach their aggregate
    # stability.
    for civ_idx, civ in enumerate(world.civilizations):
        if not civ.regions:
            continue
        if civ.stability < 50:
            base_recovery = int(get_override(world, K_STABILITY_RECOVERY, 20))
            has_severe_condition = any(
                c.severity >= 50 and civ.name in c.affected_civs
                for c in world.active_conditions
            )
            recovery = base_recovery // 2 if has_severe_condition else base_recovery
            if acc is not None:
                acc.add(civ_idx, civ, "stability", recovery, "guard-shock")
            else:
                civ.stability = clamp(civ.stability + recovery, STAT_FLOOR["stability"], 100)

    # M16a: Prestige decay and trade bonus
    tick_prestige(world, acc=acc)


# --- Phase 5: Action ---

_CRISIS_HALVED_STATS = ("economy", "culture", "military", "stability", "population")


def phase_action(
    world: WorldState,
    action_selector: ActionSelector,
    acc=None,
) -> list[Event]:
    """Each civilization takes one action from the constrained menu."""
    events: list[Event] = []

    for civ_idx, civ in enumerate(world.civilizations):
        if len(civ.regions) == 0:
            continue
        # Snapshot stat values before action (for crisis halving)
        in_crisis = is_in_crisis(civ)
        pre_stats: dict[str, int] = {}
        crisis_checkpoint = -1
        if in_crisis:
            pre_stats = {s: getattr(civ, s) for s in _CRISIS_HALVED_STATS}
            if acc is not None:
                crisis_checkpoint = acc.checkpoint()

        action = action_selector(civ, world)
        event = resolve_action(civ, action, world, acc=acc)

        # Crisis halving: reduce positive stat gains by 50%
        if in_crisis:
            if acc is not None:
                acc.halve_positive_deltas(civ_idx, _CRISIS_HALVED_STATS, crisis_checkpoint)
            else:
                for stat in _CRISIS_HALVED_STATS:
                    before = pre_stats[stat]
                    after = getattr(civ, stat)
                    if after > before:
                        halved = before + (after - before) // 2
                        setattr(civ, stat, max(halved, STAT_FLOOR.get(stat, 0)))

        # M-AF1 #3: Record the resolved action, not the selected action
        _action_values = {a.value for a in ActionType}
        resolved_action = event.event_type if event.event_type in _action_values else action.value
        history = world.action_history.setdefault(civ.name, [])
        history.append(resolved_action)
        if len(history) > 5:
            world.action_history[civ.name] = history[-5:]

        # Track action counts (for trait evolution)
        civ.action_counts[resolved_action] = civ.action_counts.get(resolved_action, 0) + 1

        # M52: Mule artifact on action success
        from chronicler.artifacts import emit_mule_artifact_intent
        for gp in civ.great_persons:
            if gp.mule and gp.active:
                emit_mule_artifact_intent(world, civ, gp, action.name)

        events.append(event)

    return events


# --- Asabiya dynamics (Turchin metaethnic frontier model) ---


def _apply_asabiya_to_regions(world: WorldState, civ_name: str, delta: float) -> None:
    """D-policy: apply asabiya delta to all regions controlled by a civ. Clamp [0, 1]."""
    for region in world.regions:
        if region.controller == civ_name:
            region.asabiya_state.asabiya = round(
                max(0.0, min(1.0, region.asabiya_state.asabiya + delta)), 4
            )


def apply_asabiya_dynamics(world: WorldState) -> None:
    """Update per-region asabiya via gradient frontier model, then aggregate to civ-level."""
    ASABIYA_FRONTIER_GROWTH_RATE = 0.05  # r0, calibrate in M61b
    ASABIYA_INTERIOR_DECAY_RATE = 0.02   # delta, calibrate in M61b
    # Defined but inactive (D5, D6) — wired in follow-up / M61b
    ASABIYA_POWER_DROPOFF = 5.0          # h, military projection distance decay  # noqa: F841
    ASABIYA_COLLAPSE_VARIANCE_THRESHOLD = 0.04  # variance collapse trigger  # noqa: F841

    region_map = world.region_map
    civ_by_name = {c.name: c for c in world.civilizations}

    # Step 1: Compute frontier fraction for each region
    for region in world.regions:
        valid_count = 0
        diff_civ = 0
        uncontrolled = 0
        for adj_name in region.adjacencies:
            adj = region_map.get(adj_name)
            if adj is None:
                continue
            valid_count += 1
            if adj.controller is None:
                uncontrolled += 1
            elif adj.controller != region.controller:
                diff_civ += 1
        region.asabiya_state.different_civ_count = diff_civ
        region.asabiya_state.uncontrolled_count = uncontrolled
        region.asabiya_state.frontier_fraction = (
            (diff_civ + uncontrolled) / valid_count if valid_count > 0 else 0.0
        )

    # Step 2: Apply gradient formula to each controlled region
    from chronicler.traditions import compute_folk_hero_asabiya_bonus

    for region in world.regions:
        if region.controller is None:
            continue
        s = region.asabiya_state.asabiya
        f = region.asabiya_state.frontier_fraction
        s_next = s + ASABIYA_FRONTIER_GROWTH_RATE * f * s * (1 - s) - ASABIYA_INTERIOR_DECAY_RATE * (1 - f) * s

        # Folk hero per-turn bonus (applied after gradient, matching legacy order)
        civ = civ_by_name.get(region.controller)
        if civ is not None:
            folk_bonus = compute_folk_hero_asabiya_bonus(civ)
            if folk_bonus > 0:
                s_next = s_next + folk_bonus * 0.1

        region.asabiya_state.asabiya = round(max(0.0, min(1.0, s_next)), 4)

    # Step 3: Aggregate to civ-level
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            civ.asabiya_variance = 0.0
            continue
        total_pop = 0
        weighted_sum = 0.0
        region_data: list[tuple[float, int]] = []  # (asabiya, pop)
        for rname in civ.regions:
            r = region_map.get(rname)
            if r is None:
                continue
            pop = r.population
            total_pop += pop
            weighted_sum += r.asabiya_state.asabiya * pop
            region_data.append((r.asabiya_state.asabiya, pop))

        if total_pop == 0:
            civ.asabiya_variance = 0.0
            continue  # Keep existing civ.asabiya

        mean_a = weighted_sum / total_pop
        variance = sum(p * (a - mean_a) ** 2 for a, p in region_data) / total_pop
        civ.asabiya = round(max(0.0, min(1.0, mean_a)), 4)
        civ.asabiya_variance = round(variance, 6)


# --- Phase 7: Random events ---

def _agent_unrest_shares(world: WorldState) -> dict[int, tuple[float, float]] | None:
    """Per-civ (rebel share, cross-border migrant share) from the last hybrid tick.

    Shares are relative to the civ's agent population before the moves
    (current population plus emigrants).  Moves between two regions of the
    same civ are internal and do not count as a migration crisis.
    """
    if world.agent_mode != "hybrid":
        return None
    bridge = getattr(world, "_agent_bridge", None)
    if bridge is None or not hasattr(bridge, "last_tick_unrest_by_region"):
        return None
    rebels_by_region, flows = bridge.last_tick_unrest_by_region()
    name_to_idx = {c.name: i for i, c in enumerate(world.civilizations)}
    owner: list[int | None] = [
        name_to_idx.get(region.controller) if region.controller else None
        for region in world.regions
    ]
    pop: dict[int, int] = {}
    rebels: dict[int, int] = {}
    crossings: dict[int, int] = {}
    emigrants: dict[int, int] = {}
    for region_idx, civ_idx in enumerate(owner):
        if civ_idx is None:
            continue
        pop[civ_idx] = pop.get(civ_idx, 0) + max(0, world.regions[region_idx].population)
        rebels[civ_idx] = rebels.get(civ_idx, 0) + rebels_by_region.get(region_idx, 0)
    for (src, dst), count in sorted(flows.items()):
        src_civ = owner[src] if 0 <= src < len(owner) else None
        dst_civ = owner[dst] if 0 <= dst < len(owner) else None
        if src_civ == dst_civ:
            continue
        if src_civ is not None:
            crossings[src_civ] = crossings.get(src_civ, 0) + count
            emigrants[src_civ] = emigrants.get(src_civ, 0) + count
        if dst_civ is not None:
            crossings[dst_civ] = crossings.get(dst_civ, 0) + count
    return {
        civ_idx: (
            rebels.get(civ_idx, 0) / max(1, total),
            crossings.get(civ_idx, 0) / max(1, total + emigrants.get(civ_idx, 0)),
        )
        for civ_idx, total in pop.items()
    }


def phase_random_events(world: WorldState, seed: int, acc=None) -> list[Event]:
    """Phase 7: per-civ decaying hazards for non-environment events.

    Each living civ rolls each hazard independently (see chronicler.events).
    In hybrid mode rebellion and migration are a roll-up of the agents' own
    rebel/migrant decisions from the previous tick rather than extra dice.
    Leader deaths come from the leader's age-based mortality hazard.
    """
    events: list[Event] = []
    ctx = HazardContext(world, agent_unrest=_agent_unrest_shares(world))
    event_types = [k for k in RANDOM_EVENT_TYPES if k in world.event_probabilities]
    for civ_idx, civ in enumerate(world.civilizations):
        if not civ.regions:
            continue
        for event_type in event_types:
            rate = civ_event_hazard(world, civ, civ_idx, event_type, ctx)
            p = hazard_probability(rate)
            if p <= 0.0:
                continue
            rng = random.Random(stable_hash_int("event_hazard", seed, civ_idx, event_type))
            if rng.random() >= p:
                continue
            actors = [civ.name]
            if event_type == "border_incident":
                partners = border_incident_partners(civ, ctx)
                if partners:
                    total = sum(w for _, w in partners)
                    pick = rng.random() * total
                    for name, weight in partners:
                        pick -= weight
                        if pick < 0:
                            actors.append(name)
                            break
                    else:
                        actors.append(partners[-1][0])
            event = Event(
                turn=world.turn,
                event_type=event_type,
                actors=actors,
                description="",  # Filled in by narrative engine
                importance=5,
            )
            provenance.cite(event, provenance.excitation_cause(world, civ, event_type, rate))
            _apply_event_effects(event_type, civ, world, acc=acc)
            record_hazard_event(world, event)
            events.append(event)

        if "leader_death" in world.event_probabilities:
            leader_event = _roll_leader_mortality(world, civ, civ_idx, seed, ctx, acc=acc)
            if leader_event is not None:
                record_hazard_event(world, leader_event)
                events.append(leader_event)

    from chronicler.politics import check_congress
    events.extend(check_congress(world, acc=acc))
    return events


def _roll_leader_mortality(
    world: WorldState, civ: Civilization, civ_idx: int, seed: int, ctx: HazardContext, acc=None,
) -> Event | None:
    """Age/war/coup/excitation mortality hazard for the civ's current leader."""
    if not civ.leader.alive or is_in_crisis(civ):
        return None
    components = leader_mortality_components(world, civ, ctx)
    p = hazard_probability(sum(components.values()))
    if p <= 0.0:
        return None
    rng = random.Random(stable_hash_int("leader_mortality", seed, civ_idx))
    if rng.random() >= p:
        return None
    cause = pick_mortality_cause(components, rng.random())
    old_leader = civ.leader
    age = leader_age(old_leader, world)
    reign = world.turn - old_leader.reign_start
    _timeline_mark = len(world.events_timeline)
    _apply_event_effects("leader_death", civ, world, acc=acc, cause=cause)
    cause_text = {
        "natural": f"dies at the age of {age}",
        "battle": f"falls in war at the age of {age}",
        "coup": "is overthrown and killed in a coup",
        "misfortune": f"dies amid the turmoil, aged {age}",
    }.get(cause, f"dies at the age of {age}")
    event = Event(
        turn=world.turn,
        event_type="leader_death",
        actors=[civ.name],
        description=f"{old_leader.name} of {civ.name} {cause_text} after a reign of {reign} years.",
        importance=5,
    )
    # Provenance: the mortality component that drew the death, and the
    # succession crisis the death just triggered (appended above).
    provenance.cite(event, *provenance.leader_death_causes(world, civ, cause))
    for ev in world.events_timeline[_timeline_mark:]:
        if ev.event_type == "succession_crisis" and ev.actors[:1] == [civ.name]:
            provenance.cite(ev, provenance.ensure_id(world, event))
    return event


def _apply_event_effects(
    event_type: str, civ: Civilization, world: WorldState, acc=None, cause: str | None = None,
) -> None:
    """Apply mechanical stat changes for a random event."""
    civ_idx = civ_index(world, civ.name)
    if event_type == "leader_death":
        import random as _random
        old_leader = civ.leader
        old_leader.alive = False
        mult = get_severity_multiplier(civ, world)
        drain = int(get_override(world, K_LEADER_DEATH_STABILITY, 4))
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "guard-shock")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
        apply_leader_legacy(civ, old_leader, world)
        check_rival_fall(civ, old_leader.name, world, acc=acc)
        # Check whether death triggers a succession crisis instead of immediate succession
        crisis_prob = compute_crisis_probability(civ, world)
        rng = _random.Random(
            stable_hash_int("leader_death_crisis", world.seed, world.turn, civ.name)
        )
        if crisis_prob > 0.0 and rng.random() < crisis_prob and not is_in_crisis(civ):
            trigger_crisis(civ, world)
            world.events_timeline.append(Event(
                turn=world.turn, event_type="succession_crisis",
                actors=[civ.name],
                description=f"A succession crisis erupts in {civ.name} after the death of {old_leader.name}.",
                importance=8,
            ))
        else:
            # A coup installs the usurper; other deaths use normal succession.
            force_type = "usurper" if cause == "coup" else None
            new_leader = generate_successor(
                civ, world, seed=world.seed, force_type=force_type, acc=acc,
            )
            civ.leader = new_leader
    elif event_type == "rebellion":
        mult = get_severity_multiplier(civ, world)
        drain = int(get_override(world, K_REBELLION_STABILITY, 4))
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
            acc.add(civ_idx, civ, "military", -int(10 * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
            civ.military = clamp(civ.military - int(10 * mult), STAT_FLOOR["military"], 100)
    elif event_type == "discovery":
        if acc is not None:
            # M-AF1 #1: positive guard-shock → positive shock signal → boosts
            # agent satisfaction (shock_pen is ADDED in compute_satisfaction).
            acc.add(civ_idx, civ, "culture", 10, "guard-shock")
            acc.add(civ_idx, civ, "economy", 10, "guard-shock")
        else:
            civ.culture = clamp(civ.culture + 10, STAT_FLOOR["culture"], 100)
            civ.economy = clamp(civ.economy + 10, STAT_FLOOR["economy"], 100)
    elif event_type == "religious_movement":
        mult = get_severity_multiplier(civ, world)
        drain = int(get_override(world, K_RELIGIOUS_MOVEMENT_STABILITY, 4))
        if acc is not None:
            # M-AF1 #1: positive culture boost via guard-shock (see discovery comment).
            acc.add(civ_idx, civ, "culture", 10, "guard-shock")
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.culture = clamp(civ.culture + 10, STAT_FLOOR["culture"], 100)
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
    elif event_type == "cultural_renaissance":
        if acc is not None:
            # M-AF1 #1: positive guard-shock → boosts satisfaction (see discovery comment).
            acc.add(civ_idx, civ, "culture", 20, "guard-shock")
            acc.add(civ_idx, civ, "stability", 10, "guard-shock")
        else:
            civ.culture = clamp(civ.culture + 20, STAT_FLOOR["culture"], 100)
            civ.stability = clamp(civ.stability + 10, STAT_FLOOR["stability"], 100)
        # M52: Cultural renaissance artifact production
        from chronicler.artifacts import (
            _prosperity_gate, select_cultural_artifact_type,
            CULTURAL_PRODUCTION_CHANCE,
        )
        from chronicler.models import ArtifactIntent
        import random as _rng_mod
        _art_rng = _rng_mod.Random(world.seed + world.turn + civ_idx + 8888)
        if _prosperity_gate(civ, world) and _art_rng.random() < CULTURAL_PRODUCTION_CHANCE:
            _art_type = select_cultural_artifact_type(civ, seed=world.seed + world.turn + civ_idx)
            _art_region = civ.capital_region or (civ.regions[0] if civ.regions else "unknown")
            world._artifact_intents.append(ArtifactIntent(
                artifact_type=_art_type,
                trigger="cultural_renaissance",
                creator_name=None,
                creator_born_turn=None,
                holder_name=None,
                holder_born_turn=None,
                civ_name=civ.name,
                region_name=_art_region,
                anchored=True if _art_type.value == "monument" else None,
                context=f"Produced during a cultural renaissance of {civ.name}",
            ))
    elif event_type == "migration":
        from chronicler.ecology import effective_capacity
        civ_regions = [r for r in world.regions if r.controller == civ.name]
        if civ_regions:
            if acc is not None and _agents_own_population(world):
                acc.add(civ_idx, civ, "population", 10, "guard")
            else:
                target = max(civ_regions, key=lambda r: effective_capacity(r) - r.population)
                add_region_pop(target, 10)
                sync_civ_population(civ, world)
        mult = get_severity_multiplier(civ, world)
        drain = int(get_override(world, K_MIGRATION_STABILITY, 4))
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
    elif event_type == "border_incident":
        mult = get_severity_multiplier(civ, world)
        drain = int(get_override(world, K_BORDER_INCIDENT_STABILITY, 2))
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)


def apply_injected_event(
    event_type: str, target_civ_name: str, world: WorldState, acc=None
) -> list[Event]:
    """Process a manually injected event targeting a single civ."""
    civ = get_civ(world, target_civ_name)
    if civ is None:
        return []

    civ_idx = civ_index(world, civ.name)

    event = Event(
        turn=world.turn,
        event_type=event_type,
        actors=[target_civ_name],
        description=f"[Injected] {event_type} strikes {target_civ_name}",
        importance=7,
    )

    if event_type == "drought":
        mult = get_severity_multiplier(civ, world)
        drain = int(get_override(world, K_DROUGHT_STABILITY, 3) * mult)
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -drain, "signal")
            acc.add(civ_idx, civ, "economy", -int(10 * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
            civ.economy = clamp(civ.economy - int(10 * mult), STAT_FLOOR["economy"], 100)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="drought",
                affected_civs=[target_civ_name],
                duration=3,
                severity=50,
            )
        )
    elif event_type == "plague":
        mult = get_severity_multiplier(civ, world)
        drain = int(get_override(world, K_PLAGUE_STABILITY, 3) * mult)
        civ_regions = [r for r in world.regions if r.controller == civ.name]
        if _epidemiology_on(world):
            # Epidemiology: the injection seeds the plague in the civ's capital;
            # its deaths come from the outbreak, not a fixed toll.
            from chronicler.epidemiology import seed_injection
            seed_injection(world, civ, event)
        elif civ_regions:
            actual_drains = distribute_pop_loss(civ_regions, _plague_pop_loss(civ_regions, mult))
            if _agent_pool_tracks_population(world):
                for region, actual in zip(civ_regions, actual_drains):
                    stage_region_catastrophe_deaths(region, actual)
            sync_civ_population(civ, world)
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -drain, "signal")
        else:
            civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="plague",
                affected_civs=[target_civ_name],
                duration=4,
                severity=60,
            )
        )
    elif event_type == "earthquake":
        mult = get_severity_multiplier(civ, world)
        if acc is not None:
            acc.add(civ_idx, civ, "economy", -int(10 * mult), "signal")
        else:
            civ.economy = clamp(civ.economy - int(10 * mult), STAT_FLOOR["economy"], 100)
    else:
        _apply_event_effects(event_type, civ, world, acc=acc)

    # Excitation is ingested with the turn's events (events.ingest_turn_events).
    record_hazard_event(world, event)
    return [event]


# --- Phase 10: Consequences ---

def phase_consequences(
    world: WorldState, acc=None, politics_runtime=None, *, phase10: Phase10Inputs | None = None,
) -> list[Event]:
    """Resolve cascading effects and tick condition durations. Returns collapse events."""
    if phase10 is not None:
        if phase10.source_turn != world.turn:
            raise ValueError("Phase 10 inputs belong to a different source turn")
        if phase10.agents is not None and (
            phase10.agents.stamp.source_turn != phase10.source_turn
            or phase10.agents.stamp.stage != "phase10_entry"
        ):
            raise ValueError("Phase 10 agent rows have a different observation stamp")
        _snap = phase10.agents.batch if phase10.agents is not None else None
        _row_args = {"agent_rows": phase10.agents}
    else:
        # Standalone compatibility path. Coordinated turns use only phase10.
        _row_args = {}
    _require_phase_acc_for_hybrid(world, acc, "phase_consequences()")
    for condition in world.active_conditions:
        condition.duration -= 1
        for civ_name in condition.affected_civs:
            civ = get_civ(world, civ_name)
            if civ and condition.severity >= 50:
                civ_idx = civ_index(world, civ.name)
                mult = get_severity_multiplier(civ, world)
                if condition.condition_type == "drought":
                    drain = int(get_override(world, K_DROUGHT_ONGOING, 2))
                else:
                    drain = int(get_override(world, K_CONDITION_ONGOING_DRAIN, 1))
                if acc is not None:
                    acc.add(civ_idx, civ, "stability", -int(drain * mult), "guard-shock")
                else:
                    civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)

    world.active_conditions = [c for c in world.active_conditions if c.duration > 0]

    # M16b: Movement lifecycle (runs before value drift — movements feed disposition)
    tick_movements(world)

    # M16a: Cultural effects (order matters — assimilation drain feeds asabiya)
    if phase10 is None:
        _snap = getattr(world, '_agent_snapshot', None)
    apply_value_drift(world, agent_snapshot=_snap, **_row_args)
    if _contact_ledger_on(world):
        # Contact ledger: trade partners warm up (drift toward friendlier).
        from chronicler.contact_ledger import apply_trade_warmth
        apply_trade_warmth(world)
    tick_cultural_assimilation(world, acc=acc, agent_snapshot=_snap, **_row_args)

    # M16c: Cultural victory tracking (runs LAST in culture effects)
    check_cultural_victories(world)

    # M37: Religion computations for next turn's Rust tick.
    # C-12 note: persecution_intensity and martyrdom_boost are REGION-level
    # fields, not civ-level stats.  They bypass the accumulator intentionally
    # because the accumulator only routes civ stats.  These feed the Rust
    # satisfaction formula via the region batch on the NEXT turn (one-turn
    # latency is by design).
    _persecution_events: list[Event] = []
    if phase10 is None:
        _snap = getattr(world, '_agent_snapshot', None)
    if _snap is not None and world.belief_registry:
        from chronicler.religion import (
            compute_majority_belief, compute_civ_majority_faith,
            compute_conversion_signals, decay_conquest_boosts,
            compute_persecution, compute_martyrdom_boosts,
            decay_martyrdom_boosts,
        )
        majority_beliefs = compute_majority_belief(_snap, **_row_args)
        civ_majority_with_ratio = compute_civ_majority_faith(_snap, **_row_args)

        # Store majority_belief on regions
        for rid, maj in majority_beliefs.items():
            if rid < len(world.regions):
                world.regions[rid].majority_belief = maj

        # Store civ_majority_faith and ratio on civilizations
        for cid, civ in enumerate(world.civilizations):
            entry = civ_majority_with_ratio.get(cid)
            if entry is not None:
                civ.civ_majority_faith, civ.majority_faith_ratio = entry

        # Build plain faith-id dict for downstream callers
        civ_faiths = {cid: faith_id for cid, (faith_id, _ratio) in civ_majority_with_ratio.items()}

        # Build civ lookup for conversion signal computation
        civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}

        # M-AF1 #11: Decay existing martyrdom boost before conversion signals consume it
        decay_martyrdom_boosts(world.regions)

        # Compute conversion signals (reads conquest_conversion_active one-shot)
        signals = compute_conversion_signals(
            world.regions, majority_beliefs, world.belief_registry, _snap,
            named_agents=(phase10.named_agents if phase10 is not None
                          else getattr(world, '_named_agents', None)),
            civ_majority_faiths=civ_faiths,
            civ_name_to_id=civ_name_to_id,
            world=world,
            **_row_args,
        )
        # Signals are written directly to region fields by compute_conversion_signals

        # Decay conquest conversion boosts
        decay_conquest_boosts(world.regions)

        # M38b: Persecution
        if not hasattr(world, '_persecuted_regions'):
            world._persecuted_regions = set()
        # H-14 fix: Clear regions whose persecution has ended (intensity=0)
        # so the one-shot event fires again if persecution restarts.
        # Without this, _persecuted_regions grows forever and suppresses
        # future persecution events for regions that were ever persecuted.
        world._persecuted_regions = {
            rname for rname in world._persecuted_regions
            if any(r.name == rname and r.persecution_intensity > 0
                   for r in world.regions)
        }
        _persecution_events = compute_persecution(
            world.regions, world.civilizations, world.belief_registry,
            _snap, world.turn, world._persecuted_regions, world=world,
            **_row_args,
        )
        compute_martyrdom_boosts(
            world.regions,
            (phase10.deaths if phase10 is not None
             else getattr(world, '_dead_agents_this_turn', None)),
        )

        # M38b: Schisms
        from chronicler.religion import detect_schisms, detect_reformation
        schism_events = detect_schisms(
            world.regions, world.civilizations, world.belief_registry,
            _snap, world.turn, world=world,
            **_row_args,
        )
        _persecution_events.extend(schism_events)
        reformation_events = detect_reformation(
            world.civilizations, world.belief_registry, current_turn=world.turn,
        )
        _persecution_events.extend(reformation_events)

        # M38b: Pilgrimages
        from chronicler.great_persons import check_pilgrimages
        all_temples = [
            (r.name, inf)
            for r in world.regions
            for inf in getattr(r, 'infrastructure', [])
            if getattr(inf, 'faith_id', -1) >= 0
        ]
        all_great_persons = [
            gp
            for c in world.civilizations
            for gp in getattr(c, 'great_persons', [])
        ]
        pilgrimage_events = check_pilgrimages(
            all_great_persons, all_temples, _snap, world.turn,
            **_row_args,
        )
        _persecution_events.extend(pilgrimage_events)
    elif world.belief_registry:
        # --agents=off: preserve persisted civ faith when present; otherwise
        # fall back to founding-faith registry order for older worlds.
        for i, civ in enumerate(world.civilizations):
            civ.civ_majority_faith = resolve_civ_faith_id(
                civ,
                world.belief_registry,
                civ_idx=i,
            )

    # M38a: Build conversion_deltas and priest counts for tick_factions
    conversion_deltas = None
    region_populations = None
    prev_priest_counts = getattr(world, '_prev_priest_counts', None)
    curr_priest_counts = None
    if _snap is not None:
        # Build per-region belief distribution
        rows = phase10.agents if phase10 is not None else None
        import numpy as np
        from chronicler.columnar import batch_arrays, first_appearance, ordered_counts
        belief_arrays = (rows.arrays("region", "belief") if rows is not None
                         else batch_arrays(_snap, ("region", "belief")))
        if belief_arrays is not None:
            # Same nested counts and insertion orders as the row loop below.
            current_beliefs = {rid: dict(counts) for rid, counts in ordered_counts(*belief_arrays).items()}
        else:
            region_col = rows.ints("region") if rows is not None else pylist(_snap.column("region"))
            belief_col = rows.ints("belief") if rows is not None else pylist(_snap.column("belief"))
            current_beliefs = {}
            for rid, bid in zip(region_col, belief_col):
                if rid not in current_beliefs:
                    current_beliefs[rid] = {}
                current_beliefs[rid][bid] = current_beliefs[rid].get(bid, 0) + 1

        prev_beliefs = getattr(world, '_prev_belief_distribution', {})
        civ_majority_faiths = {c.name: getattr(c, 'civ_majority_faith', -1) for c in world.civilizations}

        from chronicler.religion import compute_conversion_deltas
        conversion_deltas = compute_conversion_deltas(
            current_beliefs, prev_beliefs, civ_majority_faiths, world.regions
        )
        region_populations = {rid: sum(dist.values()) for rid, dist in current_beliefs.items()}
        world._prev_belief_distribution = current_beliefs

        # Priest counts for EVT_PRIEST_LOSS
        priest_arrays = (rows.arrays("occupation", "civ_affinity") if rows is not None
                         else batch_arrays(_snap, ("occupation", "civ_affinity")))
        curr_priest_counts = {}
        if priest_arrays is not None:
            occ_arr, civ_arr = priest_arrays
            priest_civs = civ_arr[(occ_arr == 4) & (civ_arr < len(world.civilizations))]
            per_civ = dict(zip(*(a.tolist() for a in np.unique(priest_civs, return_counts=True))))
            # Names in order of their first priest row, as the row loop inserted them.
            for civ_id in first_appearance(priest_civs):
                civ_name = world.civilizations[civ_id].name
                curr_priest_counts[civ_name] = curr_priest_counts.get(civ_name, 0) + per_civ[civ_id]
        else:
            occ_col = rows.ints("occupation") if rows is not None else pylist(_snap.column("occupation"))
            civ_col = rows.ints("civ_affinity") if rows is not None else pylist(_snap.column("civ_affinity"))
            for occ, civ_id in zip(occ_col, civ_col):
                if occ == 4:  # priest
                    # Need to map civ_id to civ_name
                    if civ_id < len(world.civilizations):
                        civ_name = world.civilizations[civ_id].name
                        curr_priest_counts[civ_name] = curr_priest_counts.get(civ_name, 0) + 1
        world._prev_priest_counts = curr_priest_counts

    collapse_events: list[Event] = []
    # M38b: flush buffered persecution events (computed in religion block above)
    collapse_events.extend(_persecution_events)
    # M54c: Route the Phase 10 politics sub-pass through Rust when a runtime
    # is available (both agent-backed modes and --agents=off).  Falls back to
    # the Python oracle when no runtime is present (e.g. bare unit tests that
    # call phase_consequences directly without constructing a simulator).
    # Twilight-absorption pacing: persistence streaks, tributaries, and the
    # (at most one) civ the politics pass may absorb this turn.
    from chronicler.politics import prepare_twilight_absorption, note_twilight_absorptions
    _tributary_events, _absorption_eligible = prepare_twilight_absorption(world)
    collapse_events.extend(_tributary_events)
    _politics_start = len(collapse_events)
    if politics_runtime is not None:
        from chronicler.politics import call_rust_politics, apply_politics_ops
        hybrid_mode = world.agent_mode == "hybrid"
        ops = call_rust_politics(
            politics_runtime, world, hybrid_mode, absorption_eligible=_absorption_eligible,
        )
        # M55b keeps collapse after regional aggregation. Rust politics still
        # computes step-11 collapse from the pre-aggregation civ scalar, so we
        # apply only steps 1-10 here and keep the collapse check below.
        collapse_events.extend(apply_politics_ops(world, [op for op in ops if op[0] != 11]))
    else:
        # Legacy Python oracle path (used by tests and as parity reference)
        from chronicler.politics import (
            check_capital_loss, check_secession, check_vassal_rebellion,
            check_federation_formation, check_federation_dissolution,
            update_allied_turns,
        )
        collapse_events.extend(check_capital_loss(world, acc=acc))
        collapse_events.extend(check_secession(world, acc=acc))
        update_allied_turns(world)
        collapse_events.extend(check_vassal_rebellion(world, acc=acc))
        collapse_events.extend(check_federation_formation(world))
        collapse_events.extend(check_federation_dissolution(world, acc=acc))
        from chronicler.politics import check_proxy_detection, check_restoration
        from chronicler.politics import check_twilight_absorption, update_decline_tracking
        collapse_events.extend(check_proxy_detection(world, acc=acc))
        collapse_events.extend(check_restoration(world, acc=acc))
        collapse_events.extend(check_twilight_absorption(world, eligible=_absorption_eligible))
        update_decline_tracking(world)
    note_twilight_absorptions(world, collapse_events[_politics_start:])

    apply_asabiya_dynamics(world)
    for civ in world.civilizations:
        if civ.asabiya < 0.1 and civ.stability <= 20:
            if len(civ.regions) > 1:
                civ_idx = civ_index(world, civ.name)
                lost = civ.regions[1:]
                civ.regions = civ.regions[:1]
                for region in world.regions:
                    if region.name in lost:
                        region.controller = None
                        region._controller_changed_this_turn = True
                # Audit T3-13 decision (2026-10 deferred backlog): intentional,
                # applied once. The halving is the base collapse loss and the
                # M18 severity multiplier (capped at 2.0) scales that loss a
                # single time on both routes; hybrid guard-shock deltas are
                # normalized, never re-multiplied. At the cap the loss equals
                # the whole stat, so collapse bottoms out at STAT_FLOOR.
                mult = get_severity_multiplier(civ, world)
                base_mil_target = clamp(civ.military // 2, STAT_FLOOR["military"], 100)
                base_eco_target = clamp(civ.economy // 2, STAT_FLOOR["economy"], 100)
                mil_loss = int((civ.military - base_mil_target) * mult)
                eco_loss = int((civ.economy - base_eco_target) * mult)
                collapsed_military = clamp(civ.military - mil_loss, STAT_FLOOR["military"], 100)
                collapsed_economy = clamp(civ.economy - eco_loss, STAT_FLOOR["economy"], 100)
                if acc is not None:
                    acc.add(civ_idx, civ, "military", collapsed_military - civ.military, "guard-shock")
                    acc.add(civ_idx, civ, "economy", collapsed_economy - civ.economy, "guard-shock")
                else:
                    civ.military = collapsed_military
                    civ.economy = collapsed_economy
                collapse_events.append(Event(
                    turn=world.turn,
                    event_type="collapse",
                    actors=[civ.name],
                    description=f"{civ.name} collapsed under internal pressure.",
                    importance=10,
                ))

    # Depopulation tracking for ruins
    from chronicler.exploration import mark_depopulated
    for region in world.regions:
        if region.controller is None and region.depopulated_since is None:
            mark_depopulated(region, world.turn)
        elif region.controller is not None and region.depopulated_since is not None:
            region.depopulated_since = None
            region.ruin_quality = 0

    # --- M17d: Event counts and tradition acquisition (runs before great person generation) ---
    from chronicler.traditions import update_event_counts, check_tradition_acquisition
    update_event_counts(world)
    acquired_traditions = check_tradition_acquisition(world)
    for civ_name, trad_name in acquired_traditions:
        collapse_events.append(Event(
            turn=world.turn, event_type="tradition_acquired",
            actors=[civ_name],
            description=f"{civ_name} acquires the tradition of {trad_name}.",
            importance=5,
        ))

    # --- M17: Great Person Consequences ---
    from chronicler.great_persons import (
        check_great_person_generation,
        check_lifespan_expiry,
        retire_orphaned_great_persons,
    )
    retired_orphans = retire_orphaned_great_persons(world)
    for gp in retired_orphans:
        collapse_events.append(Event(
            turn=world.turn,
            event_type="great_person_retired",
            actors=[gp.civilization],
            description=f"{gp.name} retires after the fall of {gp.civilization}.",
            importance=4,
        ))
    for civ in world.civilizations:
        if not civ.regions:
            continue
        new_persons = check_great_person_generation(civ, world)
        for gp in new_persons:
            born = Event(
                turn=world.turn, event_type="great_person_born",
                actors=[civ.name],
                description=f"A great {gp.role} emerges in {civ.name}: {gp.name}.",
                importance=6,
            )
            # Provenance: the achievement that triggered the role; later
            # deeds of this person cite the birth.
            provenance.cite(born, *provenance.great_person_causes(world, civ.name, gp.role))
            provenance.remember(world, provenance.key("gp", gp.name), born)
            collapse_events.append(born)
        check_lifespan_expiry(civ, world)

    # M17b: Exile restoration checks
    collapse_events.extend(check_exile_restoration(world, acc=acc))

    # M22: Faction tick — influence shifts, power struggles
    from chronicler.factions import tick_factions
    _economy_result = (phase10.economy if phase10 is not None
                       else getattr(world, '_economy_result', None))
    collapse_events.extend(tick_factions(world, acc=acc,
                                         conversion_deltas=conversion_deltas,
                                         region_populations=region_populations,
                                         prev_priest_counts=prev_priest_counts,
                                         curr_priest_counts=curr_priest_counts,
                                         economy_result=_economy_result))

    # M38a: Temple prestige tick
    from chronicler.infrastructure import tick_temple_prestige
    tick_temple_prestige(world, acc=acc)

    # Phase 8 governance (late Phase 10, after politics and tick_factions):
    # institutions, elites, capital, ambitions and PSI; effective N+1.
    if getattr(world, "governance", None) is not None:
        from chronicler.governance_runtime import tick_governance
        collapse_events.extend(tick_governance(world, acc=acc, phase10=phase10))

    return collapse_events


# --- Phase 4: Technology ---

def phase_technology(world: WorldState, acc=None) -> list[Event]:
    """Phase 4: Check tech advancement for each civ."""
    events = []
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue
        event = check_tech_advancement(civ, world, acc=acc)
        if event:
            events.append(event)
            # M21: Remove old focus effects, select and apply new
            if civ.active_focus:
                old_focus = TechFocus(civ.active_focus)
                remove_focus_effects(civ, old_focus)
            new_focus = select_tech_focus(civ, world)
            if new_focus:
                apply_focus_effects(civ, new_focus)
                events.append(Event(
                    turn=world.turn, event_type="tech_focus_selected",
                    actors=[civ.name],
                    description=f"{civ.name} develops {new_focus.value} specialization",
                    importance=6,
                ))
            # Count the advance for great person generation only when the
            # era is new to this civ (re-advancing after a regression is not).
            from chronicler.great_persons import note_tech_era_reached
            note_tech_era_reached(civ)
            name = generate_tech_breakthrough_name(civ.tech_era)
            world.named_events.append(NamedEvent(
                name=name, event_type="tech_breakthrough", turn=world.turn,
                actors=[civ.name], description=event.description, importance=7,
            ))
            # M16c: Check for paradigm shift
            from chronicler.tech import ERA_BONUSES
            era_bonuses = ERA_BONUSES.get(civ.tech_era, {})
            has_paradigm_shift = any(
                k in era_bonuses and era_bonuses[k] != 1.0
                for k in ("military_multiplier", "fortification_multiplier", "culture_projection_range")
            )
            if has_paradigm_shift:
                world.named_events.append(NamedEvent(
                    name=f"Paradigm Shift: {civ.tech_era.value.title()} Era",
                    event_type="paradigm_shift",
                    turn=world.turn,
                    actors=[civ.name],
                    description=f"{civ.name} enters the {civ.tech_era.value.title()} era, fundamentally changing the rules of engagement.",
                    importance=7,
                ))
    return events


def phase_cultural_milestones(world: WorldState, acc=None) -> list[Event]:
    """Check cultural milestone thresholds for named works."""
    from chronicler.named_events import generate_cultural_work
    events = []
    for civ_idx, civ in enumerate(world.civilizations):
        if len(civ.regions) == 0:
            continue
        for threshold in [80, 100]:
            marker = f"culture_{threshold}"
            if civ.culture >= threshold and marker not in civ.cultural_milestones:
                civ.cultural_milestones.append(marker)
                name = generate_cultural_work(civ, world, seed=world.seed)
                ne = NamedEvent(
                    name=name, event_type="cultural_work", turn=world.turn,
                    actors=[civ.name], description=f"{civ.name} produces a cultural masterwork",
                    importance=6,
                )
                world.named_events.append(ne)
                # M16a: Cultural works enhancement
                # M-AF1 #1: positive guard-shock → boosts satisfaction (see discovery comment).
                if acc is not None:
                    acc.add(civ_idx, civ, "culture", 5, "guard-shock")
                    acc.add(civ_idx, civ, "prestige", 2, "keep")
                else:
                    civ.culture = clamp(civ.culture + 5, STAT_FLOOR["culture"], 100)
                    civ.prestige += 2
                _apply_asabiya_to_regions(world, civ.name, 0.05)
                events.append(Event(
                    turn=world.turn, event_type="cultural_work", actors=[civ.name],
                    description=ne.description, importance=6,
                ))
                # A named cultural masterwork should always materialize as an artifact.
                from chronicler.artifacts import select_cultural_artifact_type
                from chronicler.models import ArtifactIntent
                _art_type = select_cultural_artifact_type(
                    civ,
                    seed=world.seed + world.turn + civ_idx,
                )
                _art_region = civ.capital_region or (civ.regions[0] if civ.regions else None)
                if _art_region is None:
                    continue
                world._artifact_intents.append(ArtifactIntent(
                    artifact_type=_art_type,
                    trigger="cultural_work",
                    creator_name=None,
                    creator_born_turn=None,
                    holder_name=None,
                    holder_born_turn=None,
                    civ_name=civ.name,
                    region_name=_art_region,
                    anchored=True if _art_type.value == "monument" else None,
                    context=f"Produced during a cultural milestone of {civ.name}",
                ))
    return events


def phase_leader_dynamics(world: WorldState, seed: int, acc=None) -> list[Event]:
    """Phase 8: Handle trait evolution, crisis ticks, grudge decay for all living leaders."""
    events = []
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue
        secondary = check_trait_evolution(civ, world)
        if secondary:
            events.append(Event(
                turn=world.turn, event_type="trait_evolution", actors=[civ.name],
                description=f"{civ.leader.name} of {civ.name} has become known as a {secondary}",
                importance=4,
            ))

        # Crisis state machine: tick and auto-resolve when timer hits 0
        if is_in_crisis(civ):
            tick_crisis(civ, world)
            if civ.succession_crisis_turns_remaining == 0:
                from chronicler.factions import resolve_crisis_with_factions
                crisis_events = resolve_crisis_with_factions(civ, world, acc=acc)
                events.extend(crisis_events)

        # Grudge decay — per-grudge rival alive status handled inside decay_grudges
        if civ.leader.grudges:
            decay_grudges(civ.leader, current_turn=world.turn, world=world)

    return events


def get_civ_capacities(world: WorldState) -> dict[int, int]:
    """Get total carrying capacity per civ for demand signal normalization."""
    region_map = world.region_map
    return {
        i: sum(region_map[rn].carrying_capacity for rn in civ.regions if rn in region_map)
        for i, civ in enumerate(world.civilizations)
    }


def update_war_frequency_accumulators(world: WorldState) -> None:
    """M47d: Per-turn update of war_weariness and peace_momentum on each living civ."""
    from chronicler.tuning import (
        K_WAR_WEARINESS_DECAY, K_WAR_WEARINESS_INCREMENT,
        K_WAR_PASSIVE_WEARINESS, K_PEACE_MOMENTUM_BONUS,
        K_PEACE_MOMENTUM_CAP, K_PEACE_MOMENTUM_WAR_DECAY,
        K_PEACE_MOMENTUM_DEFENDER_DECAY,
    )

    decay = get_override(world, K_WAR_WEARINESS_DECAY, 0.95)
    increment = get_override(world, K_WAR_WEARINESS_INCREMENT, 2.0)
    passive = get_override(world, K_WAR_PASSIVE_WEARINESS, 0.5)
    peace_bonus = get_override(world, K_PEACE_MOMENTUM_BONUS, 1.0)
    peace_cap = get_override(world, K_PEACE_MOMENTUM_CAP, 20.0)
    aggressor_decay = get_override(world, K_PEACE_MOMENTUM_WAR_DECAY, 0.5)
    defender_decay = get_override(world, K_PEACE_MOMENTUM_DEFENDER_DECAY, 0.95)

    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue  # dead civ guard

        # --- War weariness ---
        history = world.action_history.get(civ.name, [])
        chose_war = len(history) > 0 and history[-1] == ActionType.WAR.value

        if chose_war:
            civ.war_weariness = civ.war_weariness * decay + increment
        else:
            civ.war_weariness *= decay

        # Passive weariness from active wars
        for war in world.active_wars:
            if civ.name in war:
                civ.war_weariness += passive

        # --- Peace momentum ---
        # Aggressor decay (0.3x) only when civ CHOSE WAR this turn — punishes the act,
        # not the persistent state of an unresolved war. Weariness handles ongoing fatigue.
        # Being in active_wars (either side) uses the gentler defender decay.
        in_active_war = any(civ.name in w for w in world.active_wars)

        if chose_war:
            civ.peace_momentum *= aggressor_decay
        elif in_active_war:
            civ.peace_momentum *= defender_decay
        else:
            civ.peace_momentum = min(civ.peace_momentum + peace_bonus, peace_cap)


def reset_war_frequency_on_extinction(civ: Civilization) -> None:
    """M47d: Reset accumulators when civ loses all regions."""
    if len(civ.regions) == 0:
        civ.war_weariness = 0.0
        civ.peace_momentum = 0.0


def prune_inactive_wars(world: WorldState) -> None:
    """Drop wars whose participants no longer control any regions."""
    alive_civs = {civ.name for civ in world.civilizations if len(civ.regions) > 0}
    if not world.active_wars:
        return
    filtered_wars = [
        (attacker, defender)
        for attacker, defender in world.active_wars
        if attacker in alive_civs and defender in alive_civs
    ]
    if len(filtered_wars) == len(world.active_wars):
        return
    removed_keys = {
        f"{min(attacker, defender)}:{max(attacker, defender)}"
        for attacker, defender in world.active_wars
        if attacker not in alive_civs or defender not in alive_civs
    }
    world.active_wars = filtered_wars
    for key in removed_keys:
        world.war_start_turns.pop(key, None)


def _apply_treasury_tax_from_economy(world: WorldState, acc, economy_result) -> None:
    """Apply M42 treasury tax with deterministic fractional carryover.

    Economy tax is computed as a float. Carrying fractional remainders avoids
    persistent truncation bias where small civs can remain permanently tax-exempt.
    """
    if economy_result is None or acc is None:
        return

    prior_carry = getattr(world, "_treasury_tax_carry", {})
    next_carry: dict[int, float] = {}

    for civ_idx, tax in economy_result.treasury_tax.items():
        if civ_idx >= len(world.civilizations):
            continue

        gross = max(0.0, float(tax) + float(prior_carry.get(civ_idx, 0.0)))
        whole_tax = int(gross)
        next_carry[civ_idx] = gross - whole_tax
        if whole_tax > 0:
            acc.add(civ_idx, world.civilizations[civ_idx], "treasury", whole_tax, "keep")

    world._treasury_tax_carry = next_carry


def _capture_agent_snapshot(world: WorldState, agent_bridge: object):
    """Capture historical Phase 10 rows without publishing world scratch.

    An ``AgentBridge`` hands over the batch it read right after this turn's
    agent tick (the pool is unchanged since); other bridges export again.
    """
    # Looked up on the class, so stand-in bridges (mocks) keep exporting.
    take = getattr(type(agent_bridge), "take_post_tick_snapshot", None)
    if take is not None:
        held = take(agent_bridge, world.turn)
        if held is not None:
            return held
    try:
        return agent_bridge._sim.get_snapshot()
    except Exception:
        logger.exception("Failed to fetch agent snapshot for Phase 10 consumers")
        return None


# --- Turn orchestrator ---

def _start_population_check(world: WorldState):
    """(ledger, regions' total) when the debug population check is on for
    this turn (``CHRONICLER_CHECK_POPULATION`` set, Python-owned aggregate
    population, ``--agents off``), else None. See ``utils.PopulationLedger``."""
    import os
    from chronicler.utils import POPULATION_CHECK_ENV, start_population_ledger, stop_population_ledger
    if os.environ.get(POPULATION_CHECK_ENV, "") in ("", "0") or getattr(world, "agent_mode", None) not in (None, "off"):
        stop_population_ledger()
        return None
    return start_population_ledger(), sum(r.population for r in world.regions)


def _finish_population_check(world: WorldState, ledger, before: int) -> None:
    from chronicler.utils import stop_population_ledger
    stop_population_ledger()
    ledger.check(before, sum(r.population for r in world.regions), world.turn)


def run_turn(
    world: WorldState,
    action_selector: ActionSelector,
    narrator: Narrator,
    seed: int = 0,
    agent_bridge: object | None = None,
    economy_tracker: object | None = None,
    ecology_runtime: object | None = None,
    politics_runtime: object | None = None,
    force_settlement_detection: bool = False,
    pending_injections: list | None = None,
) -> str:
    """Execute one complete turn of the simulation. Returns chronicle text."""
    return run_turn_result(
        world, action_selector, narrator, seed, agent_bridge, economy_tracker,
        ecology_runtime, politics_runtime, force_settlement_detection, pending_injections,
    ).chronicle_text


def run_turn_result(
    world: WorldState,
    action_selector: ActionSelector,
    narrator: Narrator,
    seed: int = 0,
    agent_bridge: object | None = None,
    economy_tracker: object | None = None,
    ecology_runtime: object | None = None,
    politics_runtime: object | None = None,
    force_settlement_detection: bool = False,
    pending_injections: list | None = None,
) -> TurnResult:
    """Execute a turn and hand historical Phase 10 rows to the synchronous runner.

    The observation uses source turn N and completion label N+1. It is never
    stored on world or bridge. Failed turns abandon the owner, without rollback.
    """
    from chronicler.turn_artifacts import (
        AgentRows, Phase10Inputs, Stamp, TurnArtifacts, TurnObservation, TurnResult,
    )

    artifacts = TurnArtifacts(source_turn=world.turn)
    # Permanent faith ids (chronicler.faiths): a world built or loaded without
    # its table gets one; in a recorded run this changes nothing.
    from chronicler.faiths import ensure as _ensure_faiths
    _ensure_faiths(world)
    # Debug (CHRONICLER_CHECK_POPULATION=1, --agents off): every population
    # flow of the turn is recorded and the total checked against it at the end.
    _population_ledger = _start_population_check(world)
    from chronicler.experimental.fisheries import require_fishery_runtime
    require_fishery_runtime(world, ecology_runtime)
    if world.fishery_experiment.enabled and agent_bridge is not None:
        require_fishery_runtime(world, agent_bridge.ecology_simulator)
        require_fishery_runtime(world, agent_bridge._sim)
    from chronicler.accumulator import StatAccumulator
    from chronicler.resources import (
        clear_active_trade_routes_snapshot,
        get_active_trade_routes,
        set_active_trade_routes_snapshot,
    )

    turn_events: list[Event] = []
    from chronicler import provenance as _prov

    def _emit(events) -> None:
        # Causal provenance: id, cite and register each phase's events in
        # emission order, folding chronic repeats (outcome-neutral).
        turn_events.extend(_prov.observe(world, events))

    acc = StatAccumulator()
    clear_active_trade_routes_snapshot(world)
    # Hazard excitation: this turn's hazard draws (incl. injections) plus the
    # tech/succession/legacy sources it commits.
    world._hazard_events.clear()
    _hazard_timeline_start = len(world.events_timeline)
    _prov.begin_turn(world)
    _hazard_named_start = len(world.named_events)

    # Drain pending injections now that accumulator exists
    if pending_injections:
        while pending_injections:
            event_type, target_civ = pending_injections.pop(0)
            injected_events = apply_injected_event(event_type, target_civ, world, acc=acc)
            world.events_timeline.extend(injected_events)

    # --- M18: Start-of-turn snapshots ---
    for civ in world.civilizations:
        civ.regions_start_of_turn = len(civ.regions)
        civ.was_in_twilight = civ.decline_turns > 0
        civ.capital_start_of_turn = civ.capital_region

    prune_inactive_wars(world)

    # M-AF1 #14: Clear transient conquest conversion flags unconditionally
    for r in world.regions:
        r.conquest_conversion_active = False

    # H-20 fix: Initialize _conquered_this_turn at turn start.  Previously
    # only cleared mid-turn before bridge tick, so if the bridge was reset
    # independently or if the previous turn had no war resolution, the
    # attribute might not exist or carry stale data.
    world._conquered_this_turn = set()

    # W10 fix: Clear dead-agents transient so a failed tick_agents on the
    # prior turn does not cause spurious martyrdom boosts.
    world._dead_agents_this_turn = []

    # Phase 1: Environment
    _emit(phase_environment(world, seed=seed, acc=acc))

    # Epidemiology (replaces the hazard plague and the M18 pandemic tick):
    # introductions, regional SEIRS, deaths staged for the agent pool.
    if _epidemiology_on(world):
        from chronicler.epidemiology import tick_epidemics
        _emit(tick_epidemics(world, acc=acc))

    # M18: Black swan check (after climate disasters)
    from chronicler.emergence import check_black_swans
    _emit(check_black_swans(world, seed=seed, acc=acc))

    # M35b: Environmental events (condition-triggered, same phase)
    from chronicler.emergence import check_environmental_events
    import random as _random_m35b
    env_rng = _random_m35b.Random(seed + world.turn * 1013)
    _emit(check_environmental_events(world, env_rng))

    # --- M42/M54b: Goods economy (Phase 2 sub-sequence) ---
    # M54b: Route through Rust economy only when an agent-backed snapshot exists.
    # In --agents=off, production behavior stays frozen: there is no runtime
    # economy_result here, and compute_economy(agent_mode=False) remains an
    # oracle/test surface rather than an off-mode production path.
    phase2_trade_routes = get_active_trade_routes(world, emit_events=True)
    set_active_trade_routes_snapshot(world, phase2_trade_routes)
    if _contact_ledger_on(world) and agent_bridge is None:
        # Contact ledger, --agents off: goods-route proxy flows for this turn.
        from chronicler.contact_ledger import observe_phase2
        observe_phase2(world, phase2_trade_routes)
    if _maritime_on(world) and agent_bridge is None:
        # Maritime, --agents off: sea-lane trade and piracy on the route proxy.
        from chronicler.maritime import observe_phase2 as _maritime_phase2
        _maritime_phase2(world, phase2_trade_routes)

    economy_result = None
    snapshot = None
    if agent_bridge is not None:
        region_map = world.region_map
        snapshot = agent_bridge.get_snapshot()
        if snapshot is not None:
            # Lagged mutual aid moves existing stock (observed at N-1) before
            # this turn's inventory is packed; it does not read yields.
            if world.mutual_aid_enabled:
                from chronicler.mutual_aid import dispatch_mutual_aid, read_stockpile_commitments
                commitments = read_stockpile_commitments(world, agent_bridge._sim)
                _emit(dispatch_mutual_aid(world, snapshot, acc=acc, commitments=commitments))
            # Harvest uses this turn's climate/season and current ecology, with
            # no depletion or ecology mutation here. Phase 9 advances those
            # once for the following harvest. Recompute transient yields even
            # on turn zero and after restoring a save. Fishery catch limits are
            # applied separately by the lagged catch ratio/budget in Phase 2.
            from chronicler.climate import get_climate_phase
            from chronicler.ecology import refresh_resource_yields
            refresh_resource_yields(
                world, get_climate_phase(world.turn, world.climate_config),
            )
            from chronicler.resources import get_season_id
            from chronicler.economy import (
                build_economy_region_input_batch,
                build_economy_trade_route_batch,
                filter_goods_trade_routes,
                reconstruct_economy_result,
            )
            from chronicler.tuning import get_multiplier, K_TRADE_FRICTION
            economic_routes = filter_goods_trade_routes(world, phase2_trade_routes)
            region_input = build_economy_region_input_batch(world)
            if _cities_on(world):
                # Cities: city farmers' labour on the land and the crafts'
                # raw-material demand (optional economy columns).
                from chronicler.cities import with_economy_columns
                region_input = with_economy_columns(world, region_input, snapshot)
            trade_route_input = build_economy_trade_route_batch(
                world, active_trade_routes=economic_routes,
            )
            if _maritime_on(world):
                # Maritime: blockaded sea lanes carry no goods.
                from chronicler.maritime import filter_boundary_batch
                trade_route_input = filter_boundary_batch(
                    world, trade_route_input, "origin_region_id", "dest_region_id",
                )
            season_id = get_season_id(world.turn)
            is_winter = season_id == 3
            trade_friction = get_multiplier(world, K_TRADE_FRICTION)
            if _contact_ledger_on(world):
                # Contact ledger: read (never drain) the merchant deliveries
                # this economy tick is about to consume.
                from chronicler.contact_ledger import observe_phase2
                observe_phase2(world, phase2_trade_routes, agent_bridge)
            if getattr(world, "health_care", None) is not None:
                from chronicler.health_care import prepare_health_care
                prepare_health_care(world, agent_bridge)
            rust_return = agent_bridge._sim.tick_economy(
                region_input, trade_route_input,
                season_id, is_winter, trade_friction,
            )
            economy_result = reconstruct_economy_result(
                *rust_return, world,
                require_oracle_shadow=(world.agent_mode == "hybrid"),
            )
            if _grain_reserves_on(world):
                # Public granaries (--grain-reserves): cover the shortfall of
                # food on hand before anything reads this turn's sufficiency.
                from chronicler.grain_reserves import open_granaries
                _emit(open_granaries(world, economy_result, agent_bridge))
            artifacts.economy = economy_result
            agent_bridge.set_economy_result(economy_result)

            # M43b: Update tracker EMAs and detect supply shocks
            if economy_tracker is not None:
                from chronicler.economy import detect_supply_shocks, CATEGORY_GOODS
                for region in world.regions:
                    rname = region.name
                    for cat, goods in CATEGORY_GOODS.items():
                        stock_total = sum(region.stockpile.goods.get(g, 0.0) for g in goods)
                        economy_tracker.update_stockpile(rname, cat, stock_total)
                        imports_total = economy_result.imports_by_region.get(rname, {}).get(cat, 0.0)
                        economy_tracker.update_imports(rname, cat, imports_total)

                stockpiles = {r.name: r.stockpile for r in world.regions}
                shock_events = detect_supply_shocks(
                    world, stockpiles, economy_tracker, economy_result, region_map,
                )
                _emit(shock_events)

    if _grain_reserves_on(world) and agent_bridge is not None and economy_result is None:
        # Public granaries on a turn without an economy tick: owners and spoilage.
        from chronicler.grain_reserves import open_granaries
        _emit(open_granaries(world, None, agent_bridge))
    if world.mutual_aid_enabled:
        from chronicler.mutual_aid import observe_mutual_aid
        observe_mutual_aid(world, economy_result, snapshot)
    # Pre-economy rows have no Phase 10 view and no post-observation lifetime.
    del snapshot

    # Phase 2: Automatic Effects (NEW)
    _emit(apply_automatic_effects(world, acc=acc, cross_routes=phase2_trade_routes))

    # M42: Apply treasury tax (keep category)
    _apply_treasury_tax_from_economy(world, acc, economy_result)
    if _cities_on(world):
        # Cities: dues assessed in last turn's Phase 10, paid to the lords.
        from chronicler.cities import pay_dues
        pay_dues(world, acc)

    # Phase 3: Production
    phase_production(world, acc=acc)

    # Phase 3b (--finance): revenue, upkeep, court, debt service, borrowing,
    # debasement and default, after every ordinary income of the turn.
    if getattr(world, "finance", None) is not None:
        from chronicler.finance import tick_finance
        _emit(tick_finance(world, acc=acc, economy_result=economy_result, agent_bridge=agent_bridge))

    # Phase 4: Technology. With --techniques, per-region practice, diffusion
    # along the contact ledger, inventions and the era derived from them.
    if _techniques_on(world):
        from chronicler.techniques import tick_techniques
        _emit(tick_techniques(world, acc=acc))
    else:
        _emit(phase_technology(world, acc=acc))

    # Phase 5: Action (selection + resolution)
    _emit(phase_action(world, action_selector=action_selector, acc=acc))

    # Maritime (--maritime): fleets, naval battles, sea-zone control,
    # blockades and pirates, before campaigns so armies see this turn's sea.
    if _maritime_on(world):
        from chronicler.maritime import tick_maritime
        _emit(tick_maritime(world, acc=acc, agent_bridge=agent_bridge))

    # Nomads (--nomads): herds, transhumance, raids and tribute, hordes and
    # their conquest waves, sedentarization; before campaigns so the wars a
    # horde opens are fought this turn.
    if _nomads_on(world):
        from chronicler.nomads import tick_nomads
        _emit(tick_nomads(world, acc=acc, agent_bridge=agent_bridge))

    # M60: Campaigns (armies, logistics, battles, sieges, occupation, peace)
    if world.campaigns_enabled:
        from chronicler.war.runtime import tick_campaigns
        _emit(tick_campaigns(world, acc=acc, agent_bridge=agent_bridge))

    # M47d: Update war-weariness and peace momentum accumulators
    update_war_frequency_accumulators(world)

    # Phase 6: Cultural Milestones
    _emit(phase_cultural_milestones(world, acc=acc))

    # Phase 7: Random Events
    _emit(phase_random_events(world, seed=seed + 100, acc=acc))

    # Phase 8: Leader Dynamics
    _emit(phase_leader_dynamics(world, seed=seed, acc=acc))

    # Phase 9: Ecology (M23 — replaces phase_fertility)
    # M54a: ecology_runtime routes to Rust when available, else pure-Python.
    # Terrain succession is now inside tick_ecology (no separate call).
    from chronicler.ecology import tick_ecology
    from chronicler.climate import get_climate_phase
    climate_phase = get_climate_phase(world.turn, world.climate_config)

    # Determine the ecology runtime for this turn.
    # In agent modes, use the AgentSimulator via the split bridge.
    # In off mode, use the dedicated EcologySimulator (if provided).
    _eco_rt = ecology_runtime  # off-mode EcologySimulator (or None)
    if agent_bridge is not None:
        # Split bridge: sync regions ONCE, then ecology runs on synced state.
        agent_bridge.sync_regions(world)
        _eco_rt = agent_bridge.ecology_simulator
    elif _eco_rt is not None:
        # Off-mode: sync region state into the dedicated EcologySimulator.
        from chronicler.agent_bridge import build_region_batch
        _eco_rt.set_region_state(build_region_batch(world))

    # Production ledger (2026-10): what Phase 9 takes from each slot's stock
    # against this turn's realized output; built only for the validation
    # sidecar or CHRONICLER_CHECK_RESOURCES=1, and it only reads.
    from chronicler.production_ledger import finish_turn_ledger, start_turn_ledger
    _resource_ledger = start_turn_ledger(world, economy_result, agent_bridge)
    _emit(tick_ecology(
        world, climate_phase, acc=acc, ecology_runtime=_eco_rt,
        economy_result=economy_result, ledger=_resource_ledger,
    ))
    finish_turn_ledger(world, _resource_ledger, agent_bridge)
    del _resource_ledger

    artifacts.conquered_civ_ids = getattr(world, '_conquered_this_turn', set())
    world._conquered_this_turn = set()  # clear immediately before bridge consumption
    conquered_dict = {i: True for i in artifacts.conquered_civ_ids}
    death_output = []

    # Apply accumulated stat mutations and route agent signals
    if world.agent_mode == "hybrid" and agent_bridge is not None:
        acc.apply_keep(world)  # Apply treasury, prestige (asabiya now regional, M55b)
        shocks = acc.to_shock_signals()
        demands = acc.to_demand_signals(get_civ_capacities(world))
        # Fold pending_shocks from last turn's Phase 10
        shocks.extend(world.pending_shocks)
        world.pending_shocks.clear()
        # Tick existing demand signals to get the already-decayed demand shifts
        # consumed by Rust this turn, then queue new signals for next turn.
        demand_shifts = agent_bridge._demand_manager.tick()
        for ds in demands:
            agent_bridge._demand_manager.add(ds)
        # Run agent tick via split bridge (no second set_region_state)
        _emit(agent_bridge.tick_agents(
            world, shocks=shocks, demands=demand_shifts, conquered=conquered_dict,
            death_output=death_output,
        ))
    elif agent_bridge is not None:
        # C-10 fix: Shadow and demographics-only modes use apply_keep() to
        # match hybrid mode's stat application, making comparison fair.
        # "guard" mutations are intentionally skipped — agents produce them.
        acc.apply_keep(world)
        _emit(agent_bridge.tick_agents(
            world, conquered=conquered_dict, death_output=death_output,
        ))
    else:
        # --agents=off: apply ALL categories (no agents to produce guard stats)
        acc.apply(world)

    if getattr(world, "health_care", None) is not None and agent_bridge is not None:
        from chronicler.health_care import finish_health_care
        _emit(finish_health_care(world, agent_bridge))

    if agent_bridge is None:
        for region in world.regions:
            region.schism_convert_from = 0xFF
            region.schism_convert_to = 0xFF
            region._controller_changed_this_turn = False
            region._war_won_this_turn = False
            region._seceded_this_turn = False
            if hasattr(region, '_culture_investment_active'):
                del region._culture_investment_active

    from chronicler.economy import settle_pending_stockpile_bootstraps
    settle_pending_stockpile_bootstraps(world.regions)

    # Capture at the original post-bridge/post-bootstrap boundary. The runner
    # receives these historical rows only through the explicit result handoff.
    phase10_snapshot = None
    if agent_bridge is not None:
        phase10_snapshot = _capture_agent_snapshot(world, agent_bridge)
        if world.campaigns_enabled and phase10_snapshot is not None:
            # M60: natural deaths in the native tick shrink enlisted rosters.
            from chronicler.war.armies import reconcile_rosters
            reconcile_rosters(world, phase10_snapshot)

    # Preserve the prior completed publication gate used by Phase 5 and replay.
    world._economy_result = economy_result

    artifacts.deaths = tuple(death_output)
    artifacts.phase10 = Phase10Inputs(
        source_turn=artifacts.source_turn,
        agents=(AgentRows(batch=phase10_snapshot, stamp=Stamp(
            source_turn=artifacts.source_turn, stage="phase10_entry",
        )) if phase10_snapshot is not None else None),
        named_agents=(MappingProxyType(dict(agent_bridge.named_agents))
                      if agent_bridge is not None else None),
        economy=artifacts.economy,
        deaths=artifacts.deaths,
    )

    # M56a: Settlement detection
    settlement_events = run_settlement_tick(
        world, source_turn=artifacts.source_turn, force=force_settlement_detection,
        agent_rows=artifacts.phase10.agents,
    )
    _emit(settlement_events)

    # C-2 fix: Commit Phases 1-9 events to timeline BEFORE Phase 10 so that
    # update_event_counts(), check_great_person_generation(), and tick_factions()
    # can see same-turn events (war, trade, expand, famine, build, etc.).
    _pre_phase10_count = len(turn_events)
    world.events_timeline.extend(turn_events)

    # Phase 10: Consequences
    # In hybrid mode, Phase 10 helpers must record into the accumulator.
    # run_turn() converts the Phase 10 tail slice into pending_shocks after
    # the phase returns; helper-level pending_shocks fallbacks remain only for
    # standalone acc=None calls outside the main hybrid turn path.
    # In aggregate mode, pass acc=None so Phase 10 uses direct mutation (acc already applied).
    phase10_acc = acc if world.agent_mode == "hybrid" else None
    if world.agent_mode == "hybrid" and phase10_acc is None:
        raise RuntimeError("Hybrid Phase 10 requires an accumulator in run_turn()")
    _phase10_checkpoint = acc.checkpoint() if acc is not None else 0
    # M54c: Determine the politics runtime for this turn.
    # In agent modes, use the AgentSimulator via the bridge.
    # In off mode, use the dedicated PoliticsSimulator (if provided).
    _pol_rt = politics_runtime  # off-mode PoliticsSimulator (or None)
    if agent_bridge is not None:
        _pol_rt = agent_bridge._sim  # AgentSimulator has tick_politics()
    _emit(phase_consequences(
        world, acc=phase10_acc, politics_runtime=_pol_rt, phase10=artifacts.phase10,
    ))

    # Diplomacy (--diplomacy): memory, treaty upkeep and the polity ladder,
    # after politics so it sees this turn's revolts, absorptions and wars.
    if _diplomacy_on(world):
        from chronicler.diplomacy import tick_diplomacy
        _emit(tick_diplomacy(
            world, world.events_timeline[_hazard_timeline_start:] + turn_events[_pre_phase10_count:],
            acc=phase10_acc,
        ))

    # Great-person agendas (--gp-agendas): deeds, coups, outcomes, new vows
    # and bonds, reading this turn's events; effects read by later phases are
    # persisted state (effective N+1). Before the Phase 10 flush below.
    if _gp_agendas_on(world):
        from chronicler.gp_agendas import tick_gp_agendas
        _emit(tick_gp_agendas(
            world, world.events_timeline[_hazard_timeline_start:] + turn_events[_pre_phase10_count:],
            acc=phase10_acc, phase10=artifacts.phase10, agent_bridge=agent_bridge,
        ))

    # Cities (--cities): ranks, commerce and dues, unrest, charters, revolts
    # and free cities, sacks and walls, from this turn's agent rows; before
    # the Phase 10 flush below.
    if _cities_on(world):
        from chronicler.cities import tick_cities
        _emit(tick_cities(
            world, world.events_timeline[_hazard_timeline_start:] + turn_events[_pre_phase10_count:],
            acc=phase10_acc, phase10=artifacts.phase10, agent_bridge=agent_bridge,
            economy_result=artifacts.economy,
        ))

    # Agent movements (--agent-movements): members from this turn's rows,
    # pressure, demands and responses, risings, schisms, secessions and
    # emergence; before the Phase 10 flush below.
    if _agent_movements_on(world):
        from chronicler.agent_movements import tick_agent_movements
        _emit(tick_agent_movements(
            world, world.events_timeline[_hazard_timeline_start:] + turn_events[_pre_phase10_count:],
            acc=phase10_acc, phase10=artifacts.phase10, agent_bridge=agent_bridge,
        ))

    # Guilds (--guilds): guild masters and privileges, threats and guild
    # movements, levies, foundings and the burgher factions, after the cities
    # and movements of this turn; before the Phase 10 flush below.
    if _guilds_on(world):
        from chronicler.guilds import tick_guilds
        _emit(tick_guilds(
            world, world.events_timeline[_hazard_timeline_start:] + turn_events[_pre_phase10_count:],
            acc=phase10_acc, phase10=artifacts.phase10, agent_bridge=agent_bridge,
        ))

    # Seats of learning (--scholarship): rulers, patrons and upkeep, sacks,
    # famines and persecution, scholars, rises, falls and flight, foundings;
    # after cities and guilds of this turn, before the Phase 10 flush below.
    if _scholarship_on(world):
        from chronicler.scholarship import tick_scholarship
        _emit(tick_scholarship(
            world, world.events_timeline[_hazard_timeline_start:] + turn_events[_pre_phase10_count:],
            acc=phase10_acc, phase10=artifacts.phase10, agent_bridge=agent_bridge,
        ))

    # Public granaries (--grain-reserves): this turn's harvests and targets,
    # purchases toward them from real surplus; after the merchants planned
    # their trips, before the Phase 10 flush below.
    if _grain_reserves_on(world):
        from chronicler.grain_reserves import tick_grain_reserves
        _emit(tick_grain_reserves(
            world, acc=phase10_acc, economy_result=artifacts.economy, agent_bridge=agent_bridge,
        ))

    # C-1 fix: Second flush for Phase 10 keep mutations (stability drains,
    # faction effects, cultural assimilation treasury costs, etc.).
    # The watermark in apply_keep() ensures only new mutations since the first
    # flush get applied.  Phase 10 signal mutations go to pending_shocks for
    # next turn's agent tick.
    if world.agent_mode == "hybrid" and acc is not None:
        acc.apply_keep(world)
        # Phase 10 signal/guard-shock mutations → pending_shocks for next turn
        phase10_shocks = acc.to_shock_signals(since=_phase10_checkpoint)
        if phase10_shocks:
            world.pending_shocks.extend(phase10_shocks)

    prune_inactive_wars(world)
    if world.campaigns_enabled:
        from chronicler.war.runtime import end_of_turn_sync
        end_of_turn_sync(world)

    _relationship_mark = len(turn_events)
    # M40: Unified relationship formation and dissolution
    # One-turn latency: agent tick ran between Phase 9 and 10.
    # Rust reads edges from the previous turn's Phase 10 output. Intentional.
    if agent_bridge is not None:
        from chronicler.relationships import form_and_sync_relationships, compute_belief_data, REL_RIVAL, REL_MARRIAGE

        # M50b: gate off Python-side formation when Rust owns it
        if not agent_bridge.rust_owns_formation:
            # Build active agent IDs from all living named characters
            active_ids = set()
            for civ in world.civilizations:
                for gp in civ.great_persons:
                    if gp.active and gp.agent_id is not None:
                        active_ids.add(gp.agent_id)

            # Build belief data from the agent snapshot via bridge
            try:
                snap = agent_bridge.get_snapshot()
            except Exception:
                snap = None
            belief_by_agent, region_belief_fractions = compute_belief_data(
                snap, active_ids, world.regions,
            )

            dissolved = form_and_sync_relationships(
                world, agent_bridge, active_ids, belief_by_agent, region_belief_fractions,
            )
            if dissolved:
                # dissolved_edges_by_turn: at most ~10 edges/turn × 500 turns = ~5000 entries.
                # Cleaned up when world is garbage-collected (exclude=True, not serialized).
                existing = world.dissolved_edges_by_turn.get(world.turn, [])
                existing.extend(dissolved)
                world.dissolved_edges_by_turn[world.turn] = existing

        # Generate rivalry events for curator
        new_edges = agent_bridge.read_social_edges()
        gp_by_id = {}
        for civ in world.civilizations:
            for gp in civ.great_persons:
                if gp.agent_id is not None:
                    gp_by_id[gp.agent_id] = gp
        for edge in new_edges:
            if edge[2] == REL_RIVAL and edge[3] == world.turn:
                gp_a = gp_by_id.get(edge[0])
                gp_b = gp_by_id.get(edge[1])
                actors = []
                if gp_a:
                    actors.append(gp_a.civilization)
                if gp_b:
                    actors.append(gp_b.civilization)
                turn_events.append(Event(
                    turn=world.turn, event_type="rivalry_formed",
                    actors=actors,
                    description="A rivalry forms between great persons of opposing civilizations.",
                    importance=5,
                ))

        # M57a: Marriage formation events for named characters
        for edge in new_edges:
            if edge[2] == REL_MARRIAGE and edge[3] == world.turn:
                gp_a = gp_by_id.get(edge[0])
                gp_b = gp_by_id.get(edge[1])
                if gp_a and gp_b:
                    turn_events.append(Event(
                        turn=world.turn, event_type="marriage_formed",
                        actors=[gp_a.name, gp_b.name],
                        description=f"A marriage is forged between {gp_a.name} and {gp_b.name}.",
                        importance=6,
                        source="agent",
                    ))

    # Relationship-formation events above were appended without the observer.
    turn_events[_relationship_mark:] = _prov.observe(world, turn_events[_relationship_mark:])

    # --- M18: Tech regression (after consequences, before stress) ---
    from chronicler.emergence import check_tech_regression
    from chronicler.emergence import BLACK_SWAN_EVENT_TYPES
    black_swan_this_turn = any(e.event_type in BLACK_SWAN_EVENT_TYPES for e in turn_events)
    # T1-3: tech regression runs after every earlier accumulator flush, so it
    # follows the Phase 10 routing rule: hybrid records into the accumulator
    # (flushed just below), while off/shadow/demographics-only modes have
    # already flushed ``acc`` and must mutate directly (acc=None). Passing
    # ``acc`` in those modes silently dropped era-bonus removals.
    # With --techniques the era is derived from practice in Phase 4 (real
    # regression from lost practitioners); the M18 random regression is off.
    if not _techniques_on(world):
        _emit(check_tech_regression(
            world, black_swan_fired=black_swan_this_turn, acc=phase10_acc,
        ))

    # Third apply_keep flush: tech regression's remove_era_bonus routes through
    # acc as "keep" (V1 fix), but runs after the Phase 10 flush above.
    # Without this flush, era-bonus removals are silently dropped in hybrid mode.
    if world.agent_mode == "hybrid" and acc is not None:
        acc.apply_keep(world)

    # --- M18: Stress computation (feeds next turn) ---
    from chronicler.emergence import compute_all_stress
    compute_all_stress(world)

    # --- M18: Decrement black swan cooldown ---
    if world.black_swan_cooldown > 0:
        world.black_swan_cooldown -= 1

    # M52: Artifact processing
    from chronicler.artifacts import tick_artifacts
    artifact_events = tick_artifacts(world)
    _emit(artifact_events)

    # Causal provenance: close chronic episodes and expired conditions that
    # ended this turn (their end events join the post-Phase-10 commit).
    turn_events.extend(_prov.end_turn(world))

    # Record post-Phase-10 events (Phase 10 consequences, relationships,
    # tech regression, artifacts).  Pre-Phase-10 events were already committed
    # above (C-2 fix).
    world.events_timeline.extend(turn_events[_pre_phase10_count:])
    _prov.finish_turn(world)

    # Decaying hazards: decay one turn, then excite from this turn's hazard
    # draws and the tech/coup/legacy/rival-fall sources it committed.
    ingest_turn_events(
        world,
        take_turn_cascade_events(world, world.events_timeline[_hazard_timeline_start:]),
        world.named_events[_hazard_named_start:],
    )

    # M45: Arc classification — after events are on timeline, before snapshot.
    # classify_arc filters to events naming the character; the per-actor index
    # yields that same ordered subset without rescanning the whole timeline.
    dynasty_reg = agent_bridge.dynasty_registry if agent_bridge else None
    _history = history_index(world)
    for civ in world.civilizations:
        for gp in civ.great_persons:
            prev_type = gp.arc_type
            gp.arc_phase, new_type = classify_arc(
                gp, _history.events_for_actor(world, gp.name), dynasty_reg, world.turn
            )
            if new_type is not None and new_type != prev_type:
                gp.arc_type = new_type
                gp.arc_type_turn = world.turn
    # Recently dead — death is often the completing event
    for gp in world.retired_persons:
        if gp.death_turn == world.turn:
            prev_type = gp.arc_type
            gp.arc_phase, new_type = classify_arc(
                gp, _history.events_for_actor(world, gp.name), dynasty_reg, world.turn
            )
            if new_type is not None and new_type != prev_type:
                gp.arc_type = new_type
                gp.arc_type_turn = world.turn

    # Maritime, agent modes: the native merchant sea-crossing log (cargo and
    # raids) of this turn's agent tick, consumed by the next maritime tick.
    if _maritime_on(world) and agent_bridge is not None:
        from chronicler.maritime import observe_agent_sea_trade
        observe_agent_sea_trade(world, agent_bridge)

    # Contact ledger: decay, fold this turn's movements in, refresh civ-pair
    # aggregates (read by next turn's consumers). Clears its transient inputs.
    if _contact_ledger_on(world):
        from chronicler.contact_ledger import update_contact_ledger
        update_contact_ledger(world)

    # Finance: output, sacks, minting, specie flow and prices (read next turn).
    if getattr(world, "finance", None) is not None:
        from chronicler.finance import update_money
        update_money(world)

    # Chronicle (narrative generation)
    chronicle_text = narrator(world, turn_events)

    # Advance turn counter
    clear_active_trade_routes_snapshot(world)
    if _population_ledger is not None:
        _finish_population_check(world, *_population_ledger)
    world.turn += 1

    return TurnResult(
        chronicle_text=chronicle_text,
        observation=TurnObservation(
            source_turn=artifacts.source_turn,
            completed_turn=world.turn,
            phase10_agents=artifacts.phase10.agents,
        ),
    )


def get_injectable_event_types() -> list[str]:
    """Return sorted list of event types that can be injected."""
    from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES
    return sorted(DEFAULT_EVENT_PROBABILITIES.keys())
