"""Deterministic action selection engine with personality, situational, and streak logic.

Also hosts all action handlers via a registration pattern. simulation.py dispatches
through resolve_action() — one direction only, no circular imports.
"""

from __future__ import annotations

import random
from typing import Callable, NamedTuple

from chronicler.models import (
    ActionType, Civilization, Disposition, Event, Leader, NamedEvent, TechEra, WorldState,
)
from chronicler.utils import clamp, STAT_FLOOR


class WarResult(NamedTuple):
    outcome: str  # "attacker_wins", "defender_wins", "stalemate"
    contested_region: str | None

# --- Registration pattern ---

ACTION_REGISTRY: dict[ActionType, Callable] = {}
REACTION_REGISTRY: dict[str, Callable] = {}


def register_action(action_type: ActionType):
    def decorator(fn):
        ACTION_REGISTRY[action_type] = fn
        return fn
    return decorator


# --- Constants (moved from simulation.py) ---

DISPOSITION_ORDER: dict[Disposition, int] = {
    Disposition.HOSTILE: 0, Disposition.SUSPICIOUS: 1,
    Disposition.NEUTRAL: 2, Disposition.FRIENDLY: 3, Disposition.ALLIED: 4,
}

DISPOSITION_UPGRADE: dict[Disposition, Disposition] = {
    Disposition.HOSTILE: Disposition.SUSPICIOUS,
    Disposition.SUSPICIOUS: Disposition.NEUTRAL,
    Disposition.NEUTRAL: Disposition.FRIENDLY,
    Disposition.FRIENDLY: Disposition.ALLIED,
    Disposition.ALLIED: Disposition.ALLIED,
}

HARSH_TERRAINS = {"tundra", "desert"}

_ERA_ORDER = list(TechEra)


def _era_at_least(era: TechEra, minimum: TechEra) -> bool:
    return _ERA_ORDER.index(era) >= _ERA_ORDER.index(minimum)


# --- Helpers ---

def _get_civ(world: WorldState, name: str) -> Civilization | None:
    for c in world.civilizations:
        if c.name == name:
            return c
    return None


# --- Action handlers ---

@register_action(ActionType.DEVELOP)
def _resolve_develop(civ: Civilization, world: WorldState) -> Event:
    """Invest in infrastructure: spend treasury to boost economy or culture."""
    cost = 5 + civ.economy // 10
    if civ.treasury >= cost:
        civ.treasury -= cost
        if civ.economy <= civ.culture:
            civ.economy = clamp(civ.economy + 10, STAT_FLOOR["economy"], 100)
            target = "economy"
        else:
            civ.culture = clamp(civ.culture + 10, STAT_FLOOR["culture"], 100)
            target = "culture"
        return Event(
            turn=world.turn, event_type="develop", actors=[civ.name],
            description=f"{civ.name} invested in {target}.", importance=3,
        )
    return Event(
        turn=world.turn, event_type="develop", actors=[civ.name],
        description=f"{civ.name} attempted development but lacked funds.", importance=2,
    )


@register_action(ActionType.EXPAND)
def _resolve_expand(civ: Civilization, world: WorldState) -> Event:
    """Claim an uncontrolled region."""
    civ_index = next((i for i, c in enumerate(world.civilizations) if c.name == civ.name), 0)
    rng = random.Random(world.turn * 1000 + civ_index)
    unclaimed = [r for r in world.regions if r.controller is None]
    # Filter out harsh terrain if below IRON era
    if not _era_at_least(civ.tech_era, TechEra.IRON):
        unclaimed = [r for r in unclaimed if r.terrain not in HARSH_TERRAINS]
    if unclaimed and civ.military >= 30:
        target = rng.choice(unclaimed)
        target.controller = civ.name
        civ.regions.append(target.name)
        civ.military = clamp(civ.military - 10, STAT_FLOOR["military"], 100)
        return Event(
            turn=world.turn, event_type="expand", actors=[civ.name],
            description=f"{civ.name} expanded into {target.name}.", importance=6,
        )
    return Event(
        turn=world.turn, event_type="expand", actors=[civ.name],
        description=f"{civ.name} could not expand — no available territory or insufficient military.",
        importance=2,
    )


@register_action(ActionType.TRADE)
def _resolve_trade_action(civ: Civilization, world: WorldState) -> Event:
    """Initiate trade with the friendliest neighbor."""
    best_partner = None
    best_disp = -1
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            d = DISPOSITION_ORDER.get(rel.disposition, 0)
            if d > best_disp:
                best_disp = d
                best_partner = _get_civ(world, other_name)

    if best_partner and best_disp >= 2:  # At least neutral
        resolve_trade(civ, best_partner, world)
        return Event(
            turn=world.turn, event_type="trade", actors=[civ.name, best_partner.name],
            description=f"{civ.name} traded with {best_partner.name}.", importance=3,
        )
    return Event(
        turn=world.turn, event_type="trade", actors=[civ.name],
        description=f"{civ.name} found no willing trade partners.", importance=2,
    )


@register_action(ActionType.DIPLOMACY)
def _resolve_diplomacy(civ: Civilization, world: WorldState) -> Event:
    """Attempt to improve relations with the most hostile neighbor."""
    from chronicler.named_events import generate_treaty_name

    worst_name = None
    worst_disp = 5
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            d = DISPOSITION_ORDER.get(rel.disposition, 2)
            if d < worst_disp:
                worst_disp = d
                worst_name = other_name

    if worst_name and civ.culture >= 30:
        # Improve relationship in both directions
        rel_out = world.relationships[civ.name][worst_name]
        rel_out.disposition = DISPOSITION_UPGRADE[rel_out.disposition]
        if worst_name in world.relationships and civ.name in world.relationships[worst_name]:
            rel_in = world.relationships[worst_name][civ.name]
            rel_in.disposition = DISPOSITION_UPGRADE[rel_in.disposition]
        new_disp = rel_out.disposition
        # Clear active war if disposition reaches FRIENDLY+
        if new_disp in (Disposition.FRIENDLY, Disposition.ALLIED):
            world.active_wars = [
                w for w in world.active_wars
                if not ({civ.name, worst_name} == {w[0], w[1]})
            ]
        # Generate named treaty for significant upgrades (requires CLASSICAL+ era)
        if new_disp in (Disposition.FRIENDLY, Disposition.ALLIED) and _era_at_least(civ.tech_era, TechEra.CLASSICAL):
            treaty_name = generate_treaty_name(civ.name, worst_name, world, seed=world.seed)
            world.named_events.append(NamedEvent(
                name=treaty_name, event_type="treaty", turn=world.turn,
                actors=[civ.name, worst_name],
                description=f"{civ.name} and {worst_name} sign {treaty_name}", importance=5,
            ))
        return Event(
            turn=world.turn, event_type="diplomacy", actors=[civ.name, worst_name],
            description=f"{civ.name} improved relations with {worst_name}.", importance=4,
        )
    return Event(
        turn=world.turn, event_type="diplomacy", actors=[civ.name],
        description=f"{civ.name} attempted diplomacy without success.", importance=2,
    )


@register_action(ActionType.WAR)
def _resolve_war_action(civ: Civilization, world: WorldState) -> Event:
    """Declare war on the most hostile neighbor."""
    from chronicler.named_events import generate_battle_name
    from chronicler.leaders import update_rivalries

    target_name = None
    worst_disp = None
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            if rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                continue
            d = DISPOSITION_ORDER[rel.disposition]
            if worst_disp is None or d < worst_disp:
                worst_disp = d
                target_name = other_name

    if target_name is None:
        # No HOSTILE/SUSPICIOUS target exists — fall back to peaceful action
        return _resolve_develop(civ, world)

    defender = _get_civ(world, target_name)
    if defender:
        result = resolve_war(civ, defender, world, seed=world.turn)
        # Track active war (both orderings)
        pair = (civ.name, target_name)
        pair_rev = (target_name, civ.name)
        if pair not in world.active_wars and pair_rev not in world.active_wars:
            world.active_wars.append(pair)
        # Generate named battle for decisive outcomes
        if result.outcome in ("attacker_wins", "defender_wins"):
            battle_region = None
            if defender.regions:
                battle_region = defender.regions[0]
            elif civ.regions:
                battle_region = civ.regions[0]
            if battle_region:
                battle_name = generate_battle_name(battle_region, civ.tech_era, world, seed=world.seed)
                world.named_events.append(NamedEvent(
                    name=battle_name, event_type="battle", turn=world.turn,
                    actors=[civ.name, target_name], region=battle_region,
                    description=f"{civ.name} vs {target_name}: {result.outcome}", importance=7,
                ))
            update_rivalries(civ, defender, world)
        # Hostage capture on decisive outcomes
        if result.outcome == "defender_wins":
            from chronicler.relationships import capture_hostage
            hostage = capture_hostage(civ, defender, world, contested_region=result.contested_region)
            if hostage:
                world.events_timeline.append(Event(
                    turn=world.turn, event_type="hostage_taken",
                    actors=[defender.name, civ.name],
                    description=f"{defender.name} takes {hostage.name} hostage from {civ.name}.",
                    importance=6,
                ))
        elif result.outcome == "attacker_wins":
            from chronicler.relationships import capture_hostage
            hostage = capture_hostage(defender, civ, world, contested_region=result.contested_region)
            if hostage:
                world.events_timeline.append(Event(
                    turn=world.turn, event_type="hostage_taken",
                    actors=[civ.name, defender.name],
                    description=f"{civ.name} takes {hostage.name} hostage from {defender.name}.",
                    importance=6,
                ))
        return Event(
            turn=world.turn, event_type="war", actors=[civ.name, target_name],
            description=f"{civ.name} attacked {target_name}: {result.outcome}.", importance=8,
        )
    return Event(
        turn=world.turn, event_type="war", actors=[civ.name],
        description=f"{civ.name} prepared for war but found no target.", importance=3,
    )


@register_action(ActionType.EMBARGO)
def _resolve_embargo(civ: Civilization, world: WorldState) -> Event:
    """Impose trade embargo on most hostile neighbor."""
    target_name = None
    if civ.name in world.relationships:
        for other, rel in world.relationships[civ.name].items():
            if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                if (civ.name, other) not in world.embargoes:
                    target_name = other
                    break
    if target_name:
        world.embargoes.append((civ.name, target_name))
        target = _get_civ(world, target_name)
        if target:
            target.stability = clamp(target.stability - 5, STAT_FLOOR["stability"], 100)
        return Event(
            turn=world.turn, event_type="embargo", actors=[civ.name, target_name],
            description=f"{civ.name} imposed a trade embargo on {target_name}.",
            importance=6,
        )
    return Event(
        turn=world.turn, event_type="embargo", actors=[civ.name],
        description=f"{civ.name} sought to embargo but found no target.", importance=2,
    )


from chronicler.infrastructure import handle_build as _infra_handle_build, scorched_earth_check
ACTION_REGISTRY[ActionType.BUILD] = _infra_handle_build
REACTION_REGISTRY["region_lost"] = scorched_earth_check


@register_action(ActionType.MOVE_CAPITAL)
def _resolve_move_capital(civ: Civilization, world: WorldState) -> Event:
    from chronicler.politics import resolve_move_capital
    return resolve_move_capital(civ, world)


@register_action(ActionType.FUND_INSTABILITY)
def _resolve_fund_instability(civ: Civilization, world: WorldState) -> Event:
    from chronicler.politics import resolve_fund_instability
    return resolve_fund_instability(civ, world)


@register_action(ActionType.INVEST_CULTURE)
def _resolve_invest_culture(civ: Civilization, world: WorldState) -> Event:
    from chronicler.culture import resolve_invest_culture
    return resolve_invest_culture(civ, world)


# --- Combat resolution (simplified Lanchester) ---

def resolve_war(
    attacker: Civilization,
    defender: Civilization,
    world: WorldState,
    seed: int = 0,
) -> WarResult:
    """Resolve combat between two civilizations. Returns WarResult namedtuple."""
    from chronicler.tech import tech_war_multiplier
    from chronicler.terrain import total_defense_bonus, ROLE_EFFECTS
    from chronicler.climate import get_climate_phase
    from chronicler.models import ClimatePhase, InfrastructureType

    rng = random.Random(seed)

    # Select contested region BEFORE combat
    defender_regions = [r for r in world.regions if r.controller == defender.name]
    contested = rng.choice(defender_regions) if defender_regions else None

    att_asabiya = attacker.asabiya
    def_asabiya = defender.asabiya

    # MEDIEVAL+ defender bonus: +0.2 asabiya (capped at 1.0)
    if _era_at_least(defender.tech_era, TechEra.MEDIEVAL):
        def_asabiya = min(def_asabiya + 0.2, 1.0)

    att_power = (attacker.military ** 2) * att_asabiya + rng.uniform(0, 3)
    def_power = (defender.military ** 2) * def_asabiya + rng.uniform(0, 3)

    att_power *= tech_war_multiplier(attacker.tech_era, defender.tech_era)
    def_power *= tech_war_multiplier(defender.tech_era, attacker.tech_era)

    # Terrain + role defense bonus
    if contested:
        climate_phase = get_climate_phase(world.turn, world.climate_config)
        if climate_phase == ClimatePhase.WARMING and contested.terrain == "mountains":
            role_defense = ROLE_EFFECTS.get(contested.role, ROLE_EFFECTS["standard"]).defense
            defense_bonus = role_defense
        else:
            defense_bonus = total_defense_bonus(contested)

        # Fortification bonus
        fort_bonus = 0
        for infra in contested.infrastructure:
            if infra.type == InfrastructureType.FORTIFICATIONS and infra.active:
                fort_bonus = 15
                break
        def_power += defense_bonus + fort_bonus

    # M17d: Martial tradition combat modifier
    if "martial" in attacker.traditions:
        att_power += 5
    if "martial" in defender.traditions:
        def_power += 5

    # War costs treasury regardless of outcome
    attacker.treasury = max(0, attacker.treasury - 20)
    defender.treasury = max(0, defender.treasury - 10)

    if att_power > def_power * 1.3:
        if contested:
            contested.controller = attacker.name
            attacker.regions.append(contested.name)
            defender.regions = [r for r in defender.regions if r != contested.name]
            # Scorched earth check
            reaction = REACTION_REGISTRY.get("region_lost")
            if reaction:
                scorch_events = reaction(world, defender, contested, seed)
                world.events_timeline.extend(scorch_events)
            # Fog: reveal conquered region adjacencies
            if world.fog_of_war and attacker.known_regions is not None:
                known_set = set(attacker.known_regions)
                known_set.add(contested.name)
                for adj in contested.adjacencies:
                    known_set.add(adj)
                attacker.known_regions = sorted(known_set)
        attacker.military = clamp(attacker.military - 10, STAT_FLOOR["military"], 100)
        defender.military = clamp(defender.military - 20, STAT_FLOOR["military"], 100)
        defender.stability = clamp(defender.stability - 10, STAT_FLOOR["stability"], 100)
        return WarResult("attacker_wins", contested.name if contested else None)
    elif def_power > att_power * 1.3:
        attacker.military = clamp(attacker.military - 20, STAT_FLOOR["military"], 100)
        defender.military = clamp(defender.military - 10, STAT_FLOOR["military"], 100)
        attacker.stability = clamp(attacker.stability - 10, STAT_FLOOR["stability"], 100)
        return WarResult("defender_wins", contested.name if contested else None)
    else:
        attacker.military = clamp(attacker.military - 10, STAT_FLOOR["military"], 100)
        defender.military = clamp(defender.military - 10, STAT_FLOOR["military"], 100)
        return WarResult("stalemate", None)


# --- Trade resolution ---

def resolve_trade(civ1: Civilization, civ2: Civilization, world: WorldState) -> None:
    """Resolve trade: both sides gain treasury proportional to their economy."""
    gain1 = max(1, civ2.economy // 3)
    gain2 = max(1, civ1.economy // 3)
    civ1.treasury += gain1
    civ2.treasury += gain2
    if civ1.name in world.relationships and civ2.name in world.relationships[civ1.name]:
        world.relationships[civ1.name][civ2.name].trade_volume += 1
    if civ2.name in world.relationships and civ1.name in world.relationships[civ2.name]:
        world.relationships[civ2.name][civ1.name].trade_volume += 1


# --- Dispatcher ---

def resolve_action(civ: Civilization, action: ActionType, world: WorldState) -> Event:
    """Dispatch an action to its registered handler."""
    # EXPLORE has a different signature (world, civ) rather than (civ, world)
    if action == ActionType.EXPLORE:
        from chronicler.exploration import handle_explore
        return handle_explore(world, civ)
    handler = ACTION_REGISTRY.get(action)
    if handler:
        result = handler(civ, world)
        if result is None:
            return Event(
                turn=world.turn, event_type="action", actors=[civ.name],
                description=f"{civ.name} rests.", importance=1,
            )
        return result
    return Event(
        turn=world.turn, event_type="action", actors=[civ.name],
        description=f"{civ.name} rests.", importance=1,
    )


# --- Weight profiles ---

TRAIT_WEIGHTS: dict[str, dict[ActionType, float]] = {
    "aggressive":   {ActionType.WAR: 2.0, ActionType.EXPAND: 1.3, ActionType.DEVELOP: 0.5, ActionType.TRADE: 0.8, ActionType.DIPLOMACY: 0.3, ActionType.BUILD: 0.3, ActionType.EMBARGO: 1.2, ActionType.MOVE_CAPITAL: 0.1, ActionType.FUND_INSTABILITY: 0.2, ActionType.EXPLORE: 0.8, ActionType.INVEST_CULTURE: 0.3},
    "cautious":     {ActionType.WAR: 0.2, ActionType.EXPAND: 0.5, ActionType.DEVELOP: 2.0, ActionType.TRADE: 1.3, ActionType.DIPLOMACY: 1.5, ActionType.BUILD: 1.5, ActionType.EMBARGO: 0.5, ActionType.MOVE_CAPITAL: 0.3, ActionType.FUND_INSTABILITY: 1.2, ActionType.EXPLORE: 0.5, ActionType.INVEST_CULTURE: 1.3},
    "opportunistic":{ActionType.WAR: 1.0, ActionType.EXPAND: 1.5, ActionType.DEVELOP: 0.8, ActionType.TRADE: 2.0, ActionType.DIPLOMACY: 0.7, ActionType.BUILD: 1.0, ActionType.EMBARGO: 0.8, ActionType.MOVE_CAPITAL: 0.1, ActionType.FUND_INSTABILITY: 0.5, ActionType.EXPLORE: 1.2, ActionType.INVEST_CULTURE: 0.8},
    "zealous":      {ActionType.WAR: 1.5, ActionType.EXPAND: 2.0, ActionType.DEVELOP: 1.3, ActionType.TRADE: 0.5, ActionType.DIPLOMACY: 0.4, ActionType.BUILD: 1.0, ActionType.EMBARGO: 0.8, ActionType.MOVE_CAPITAL: 0.1, ActionType.FUND_INSTABILITY: 0.5, ActionType.EXPLORE: 1.5, ActionType.INVEST_CULTURE: 0.5},
    "ambitious":    {ActionType.WAR: 1.2, ActionType.EXPAND: 1.8, ActionType.DEVELOP: 1.5, ActionType.TRADE: 1.0, ActionType.DIPLOMACY: 0.6, ActionType.BUILD: 1.2, ActionType.EMBARGO: 0.8, ActionType.MOVE_CAPITAL: 0.1, ActionType.FUND_INSTABILITY: 0.5, ActionType.EXPLORE: 1.5, ActionType.INVEST_CULTURE: 1.0},
    "calculating":  {ActionType.WAR: 0.7, ActionType.EXPAND: 0.8, ActionType.DEVELOP: 1.8, ActionType.TRADE: 1.5, ActionType.DIPLOMACY: 1.3, ActionType.BUILD: 1.3, ActionType.EMBARGO: 1.3, ActionType.MOVE_CAPITAL: 0.1, ActionType.FUND_INSTABILITY: 1.5, ActionType.EXPLORE: 0.8, ActionType.INVEST_CULTURE: 1.5},
    "visionary":    {ActionType.WAR: 0.4, ActionType.EXPAND: 1.0, ActionType.DEVELOP: 1.8, ActionType.TRADE: 1.3, ActionType.DIPLOMACY: 1.5, ActionType.BUILD: 1.5, ActionType.EMBARGO: 0.3, ActionType.MOVE_CAPITAL: 0.3, ActionType.FUND_INSTABILITY: 0.5, ActionType.EXPLORE: 1.2, ActionType.INVEST_CULTURE: 2.0},
    "bold":         {ActionType.WAR: 1.8, ActionType.EXPAND: 1.8, ActionType.DEVELOP: 0.6, ActionType.TRADE: 1.0, ActionType.DIPLOMACY: 0.5, ActionType.BUILD: 0.5, ActionType.EMBARGO: 0.8, ActionType.MOVE_CAPITAL: 0.1, ActionType.FUND_INSTABILITY: 0.2, ActionType.EXPLORE: 1.0, ActionType.INVEST_CULTURE: 0.4},
    "shrewd":       {ActionType.WAR: 0.5, ActionType.EXPAND: 0.7, ActionType.DEVELOP: 1.2, ActionType.TRADE: 2.0, ActionType.DIPLOMACY: 1.8, ActionType.BUILD: 1.0, ActionType.EMBARGO: 1.5, ActionType.MOVE_CAPITAL: 0.1, ActionType.FUND_INSTABILITY: 1.5, ActionType.EXPLORE: 1.2, ActionType.INVEST_CULTURE: 1.8},
    "stubborn":     {},
}

SECONDARY_TRAIT_ACTION: dict[str, ActionType] = {
    "warlike": ActionType.WAR, "builder": ActionType.DEVELOP, "merchant": ActionType.TRADE,
    "conqueror": ActionType.EXPAND, "diplomat": ActionType.DIPLOMACY,
}


class ActionEngine:
    def __init__(self, world: WorldState):
        self.world = world

    def get_eligible_actions(self, civ: Civilization) -> list[ActionType]:
        eligible = [ActionType.DEVELOP, ActionType.DIPLOMACY]
        unclaimed = [r for r in self.world.regions if r.controller is None]
        if civ.military >= 30 and unclaimed:
            eligible.append(ActionType.EXPAND)
        has_hostile = False
        if civ.name in self.world.relationships:
            for rel in self.world.relationships[civ.name].values():
                if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                    has_hostile = True
                    break
        if has_hostile:
            eligible.append(ActionType.WAR)
        if _era_at_least(civ.tech_era, TechEra.BRONZE):
            if civ.name in self.world.relationships:
                for rel in self.world.relationships[civ.name].values():
                    if rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                        eligible.append(ActionType.TRADE)
                        break
        # BUILD: treasury >= min build cost and has valid build regions
        from chronicler.infrastructure import valid_build_types, BUILD_SPECS
        min_cost = min(s.cost for s in BUILD_SPECS.values())
        if civ.treasury >= min_cost and civ.regions:
            has_valid = False
            for rname in civ.regions:
                region = next((r for r in self.world.regions if r.name == rname), None)
                if region and valid_build_types(region):
                    has_valid = True
                    break
            if has_valid:
                eligible.append(ActionType.BUILD)
        # EMBARGO: has trade route and hostile neighbor
        from chronicler.resources import get_active_trade_routes
        civ_routes = [r for r in get_active_trade_routes(self.world) if civ.name in r]
        if civ_routes and has_hostile:
            eligible.append(ActionType.EMBARGO)
        # MOVE_CAPITAL: treasury >= 15 and regions >= 2
        if civ.treasury >= 15 and len(civ.regions) >= 2:
            eligible.append(ActionType.MOVE_CAPITAL)
        # Vassal cannot declare war
        is_vassal = any(vr.vassal == civ.name for vr in self.world.vassal_relations)
        if is_vassal:
            eligible = [a for a in eligible if a != ActionType.WAR]
        # FUND_INSTABILITY: treasury >= 8, has hostile neighbor, not vassal
        if civ.treasury >= 8 and has_hostile and not is_vassal:
            eligible.append(ActionType.FUND_INSTABILITY)
        # EXPLORE: fog of war active, treasury >= 5, unknown adjacent regions
        from chronicler.exploration import is_explore_eligible
        if is_explore_eligible(self.world, civ):
            eligible.append(ActionType.EXPLORE)
        # M16c: INVEST_CULTURE requires culture >= 60 and valid targets
        if civ.culture >= 60:
            from chronicler.tech import get_era_bonus
            global_proj = get_era_bonus(civ.tech_era, "culture_projection_range", default=1) == -1
            civ_regions = {r.name for r in self.world.regions if r.controller == civ.name}
            adjacent = set()
            if not global_proj:
                for r in self.world.regions:
                    if r.name in civ_regions:
                        adjacent.update(r.adjacencies)
            has_valid_target = any(
                r.controller is not None
                and r.controller != civ.name
                and r.cultural_identity != civ.name
                and (global_proj or r.name in adjacent)
                for r in self.world.regions
            )
            if has_valid_target:
                eligible.append(ActionType.INVEST_CULTURE)
        return eligible

    def compute_weights(self, civ: Civilization) -> dict[ActionType, float]:
        eligible = self.get_eligible_actions(civ)
        base = 0.2
        weights: dict[ActionType, float] = {a: base for a in ActionType}
        for action in ActionType:
            if action not in eligible:
                weights[action] = 0.0
        trait = civ.leader.trait
        if trait == "stubborn":
            history = self.world.action_history.get(civ.name, [])
            last_action = history[-1] if history else None
            for action in ActionType:
                if weights[action] == 0.0:
                    continue
                if last_action and action.value == last_action:
                    weights[action] *= 2.0
                else:
                    weights[action] *= 0.8
        else:
            profile = TRAIT_WEIGHTS.get(trait, {})
            for action in ActionType:
                if weights[action] == 0.0:
                    continue
                weights[action] *= profile.get(action, 1.0)
        self._apply_situational(civ, weights)
        if civ.leader.secondary_trait:
            boosted = SECONDARY_TRAIT_ACTION.get(civ.leader.secondary_trait)
            if boosted and weights[boosted] > 0:
                weights[boosted] *= 1.3
        if civ.leader.rival_civ:
            if civ.name in self.world.relationships:
                rival_rel = self.world.relationships[civ.name].get(civ.leader.rival_civ)
                if rival_rel and rival_rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                    weights[ActionType.WAR] *= 1.5
        # Grudge bias: each high-intensity grudge boosts WAR weight toward the rival civ
        if civ.leader.grudges and weights[ActionType.WAR] > 0:
            for grudge in civ.leader.grudges:
                intensity = grudge.get("intensity", 0.0)
                if intensity >= 0.5:
                    # Check whether the grudge target is still a hostile neighbor
                    rival_civ = grudge.get("rival_civ")
                    if rival_civ and civ.name in self.world.relationships:
                        rel = self.world.relationships[civ.name].get(rival_civ)
                        if rel and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                            weights[ActionType.WAR] *= (1.0 + intensity * 0.5)
        # M17d: Tradition weight biases
        if "martial" in civ.traditions and ActionType.WAR in weights:
            weights[ActionType.WAR] *= 1.2
        if "diplomatic" in civ.traditions and ActionType.DIPLOMACY in weights:
            weights[ActionType.DIPLOMACY] *= 1.2

        # M21: Tech focus weight biases
        from chronicler.tech_focus import get_focus_weight_modifiers
        focus_mods = get_focus_weight_modifiers(civ)
        for action, mod in focus_mods.items():
            if action in weights and weights[action] > 0:
                weights[action] *= mod

        history = self.world.action_history.get(civ.name, [])
        streak_limit = 5 if civ.leader.trait == "stubborn" else 3
        if len(history) >= streak_limit:
            last_n = history[-streak_limit:]
            if len(set(last_n)) == 1:
                streaked = ActionType(last_n[0])
                weights[streaked] = 0.0
        # M21: Cap combined weight multiplier at 2.5x to prevent dominant action
        max_weight = max(weights.values()) if weights else 0
        if max_weight > 2.5:
            scale = 2.5 / max_weight
            for action in weights:
                weights[action] *= scale
        return weights

    def _apply_situational(self, civ: Civilization, weights: dict[ActionType, float]) -> None:
        if civ.stability <= 20:
            weights[ActionType.DIPLOMACY] *= 3.0
            weights[ActionType.WAR] *= 0.1
        has_hostile = False
        if civ.name in self.world.relationships:
            for rel in self.world.relationships[civ.name].values():
                if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                    has_hostile = True
                    break
        if civ.military >= 70 and has_hostile:
            weights[ActionType.WAR] *= 2.5
        if civ.treasury >= 200:
            weights[ActionType.EXPAND] *= 2.0
            weights[ActionType.TRADE] *= 1.5
        if civ.treasury <= 30:
            weights[ActionType.DEVELOP] *= 0.3
            weights[ActionType.EXPAND] *= 0.2
        if civ.population >= 80 and len(civ.regions) <= 2:
            weights[ActionType.EXPAND] *= 3.0
        if civ.economy <= 30:
            weights[ActionType.DEVELOP] *= 2.0
            weights[ActionType.TRADE] *= 1.5
        if not has_hostile:
            weights[ActionType.WAR] *= 0.1
        all_allied = True
        if civ.name in self.world.relationships:
            for rel in self.world.relationships[civ.name].values():
                if rel.disposition != Disposition.ALLIED:
                    all_allied = False
                    break
        else:
            all_allied = False
        if all_allied:
            weights[ActionType.DIPLOMACY] *= 0.1
        # M16c: Boost INVEST_CULTURE when rival-adjacent regions exist
        if ActionType.INVEST_CULTURE in weights and weights[ActionType.INVEST_CULTURE] > 0:
            weights[ActionType.INVEST_CULTURE] *= 2.0

    def select_action(self, civ: Civilization, seed: int) -> ActionType:
        weights = self.compute_weights(civ)
        actions = [a for a, w in weights.items() if w > 0]
        action_weights = [weights[a] for a in actions]
        if not actions:
            return ActionType.DEVELOP
        rng = random.Random(seed + self.world.turn + hash(civ.name))
        return rng.choices(actions, weights=action_weights, k=1)[0]
