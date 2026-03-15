"""Great Person generation, lifecycle, and modifier registry."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from chronicler.leaders import _pick_name, ALL_TRAITS

if TYPE_CHECKING:
    from chronicler.models import Civilization, GreatPerson, WorldState

# ---------------------------------------------------------------------------
# Task 2: Modifier registry
# ---------------------------------------------------------------------------

ROLE_MODIFIERS: dict[str, dict] = {
    "general":   {"domain": "military", "stat": "military",        "value": 10},
    "merchant":  {"domain": "trade",    "stat": "trade_income",    "value": 3,          "per": "route"},
    "scientist": {"domain": "tech",     "stat": "tech_cost",       "value": -0.30,      "mode": "multiplier"},
    "prophet":   {"domain": "culture",  "stat": "movement_spread", "value": "accelerated", "mode": "behavioral"},
}


def get_modifiers(civ: Civilization, domain: str) -> list[dict]:
    """Return all active modifier dicts for *civ* that apply to *domain*."""
    results = []
    for gp in civ.great_persons:
        if not gp.active or gp.is_hostage:
            continue
        if gp.role not in ROLE_MODIFIERS:
            continue
        mod_template = ROLE_MODIFIERS[gp.role]
        if mod_template["domain"] != domain:
            continue
        mod = {"source": f"{gp.role}_{gp.name}", **mod_template}
        results.append(mod)
    return results


# ---------------------------------------------------------------------------
# Task 3: Achievement-triggered generation
# ---------------------------------------------------------------------------

ROLE_COOLDOWNS: dict[str, int] = {
    "general":   20,
    "merchant":  20,
    "prophet":   25,
    "scientist": 20,
}

CATCH_UP_DISCOUNT = 0.75

# Window (in turns) in which war wins must cluster to trigger a general
_WAR_WIN_WINDOW = 20
_WAR_WIN_THRESHOLD = 3

# Scientist triggers
_TECH_ADVANCE_KEY = "tech_advanced"
_HIGH_ECONOMY_KEY = "high_economy_turns"
_HIGH_ECONOMY_STAT = 80
_HIGH_ECONOMY_TURNS = 10

# Global cap on living great persons
_GREAT_PERSON_CAP = 50


def _is_on_cooldown(civ_name: str, role: str, world: WorldState) -> bool:
    cooldowns = world.great_person_cooldowns.get(civ_name, {})
    last_spawn_turn = cooldowns.get(role)
    if last_spawn_turn is None:
        return False
    cooldown_duration = ROLE_COOLDOWNS.get(role, 20)
    return (world.turn - last_spawn_turn) < cooldown_duration


def _set_cooldown(civ_name: str, role: str, world: WorldState) -> None:
    if civ_name not in world.great_person_cooldowns:
        world.great_person_cooldowns[civ_name] = {}
    world.great_person_cooldowns[civ_name][role] = world.turn  # store spawn turn, not duration


def _total_great_persons(world: WorldState) -> int:
    return sum(len(c.great_persons) for c in world.civilizations)


def _retire_person(gp: GreatPerson, civ: Civilization, world: WorldState) -> None:
    gp.active = False
    gp.fate = "retired"
    gp.death_turn = world.turn
    if gp in civ.great_persons:
        civ.great_persons.remove(gp)
    world.retired_persons.append(gp)
    # Check for folk hero if civ is in dramatic circumstances
    context = _infer_dramatic_context(civ, world)
    if context:
        from chronicler.traditions import check_folk_hero
        became_hero = check_folk_hero(gp, civ, world, context=context)
        if became_hero:
            from chronicler.models import Event
            world.events_timeline.append(Event(
                turn=world.turn, event_type="folk_hero_created",
                actors=[civ.name],
                description=f"{gp.name} of {civ.name} becomes a folk hero after a dramatic {context}.",
                importance=6,
            ))


def _infer_dramatic_context(civ: Civilization, world: WorldState) -> str | None:
    """Infer dramatic death context from current civ state."""
    if any(civ.name in w for w in world.active_wars):
        return "war"
    if any(c.condition_type in ("drought", "plague", "volcanic_winter")
           and civ.name in c.affected_civs for c in world.active_conditions):
        return "disaster"
    if civ.succession_crisis_turns_remaining > 0:
        return "succession_crisis"
    return None


def _enforce_cap(civ: Civilization, world: WorldState) -> None:
    """If adding a GP would exceed the cap, retire the oldest active GP from *civ*."""
    if _total_great_persons(world) >= _GREAT_PERSON_CAP:
        active_sorted = sorted(
            [gp for gp in civ.great_persons if gp.active],
            key=lambda gp: gp.born_turn,
        )
        if active_sorted:
            _retire_person(active_sorted[0], civ, world)


def _create_great_person(role: str, civ: Civilization, world: WorldState) -> GreatPerson:
    """Instantiate a new GreatPerson, append it to civ.great_persons, and return it."""
    from chronicler.models import GreatPerson
    rng = random.Random(world.seed + world.turn + hash(civ.name) + hash(role))
    name = _pick_name(civ, world, rng)
    trait = rng.choice(ALL_TRAITS)
    gp = GreatPerson(
        name=name,
        role=role,
        trait=trait,
        civilization=civ.name,
        origin_civilization=civ.name,
        born_turn=world.turn,
    )
    civ.great_persons.append(gp)
    return gp


def check_great_person_generation(civ: Civilization, world: WorldState) -> list[GreatPerson]:
    """
    Check all achievement thresholds and spawn Great Persons as warranted.

    Returns a list of newly spawned GreatPerson objects.
    """
    spawned: list[GreatPerson] = []

    # --- Determine catch-up discount ---
    # A civ with 0 active great persons gets a discounted threshold.
    active_count = sum(1 for gp in civ.great_persons if gp.active)
    apply_discount = active_count == 0

    # ------------------------------------------------------------------
    # Threshold 1: General — 3 war wins within a 20-turn window
    # ------------------------------------------------------------------
    threshold_general = int(_WAR_WIN_THRESHOLD * CATCH_UP_DISCOUNT) if apply_discount else _WAR_WIN_THRESHOLD
    if not _is_on_cooldown(civ.name, "general", world):
        recent_wins = [t for t in civ.war_win_turns if world.turn - t <= _WAR_WIN_WINDOW]
        if len(recent_wins) >= threshold_general:
            _enforce_cap(civ, world)
            gp = _create_great_person("general", civ, world)
            _set_cooldown(civ.name, "general", world)
            spawned.append(gp)

    # ------------------------------------------------------------------
    # Threshold 2: Scientist — era advance OR sustained high economy
    # ------------------------------------------------------------------
    if not _is_on_cooldown(civ.name, "scientist", world):
        tech_trigger = civ.event_counts.get(_TECH_ADVANCE_KEY, 0) >= 1
        economy_trigger = (
            civ.economy >= _HIGH_ECONOMY_STAT
            and civ.event_counts.get(_HIGH_ECONOMY_KEY, 0) >= _HIGH_ECONOMY_TURNS
        )
        if tech_trigger or economy_trigger:
            _enforce_cap(civ, world)
            gp = _create_great_person("scientist", civ, world)
            _set_cooldown(civ.name, "scientist", world)
            spawned.append(gp)

    # ------------------------------------------------------------------
    # Threshold 3: Merchant — 4+ active trade routes for 10 consecutive turns
    # ------------------------------------------------------------------
    if not _is_on_cooldown(civ.name, "merchant", world):
        threshold_turns = 10
        if apply_discount:
            threshold_turns = int(threshold_turns * CATCH_UP_DISCOUNT)
        consecutive = civ.event_counts.get("high_trade_route_turns", 0)
        if consecutive >= threshold_turns:
            _enforce_cap(civ, world)
            gp = _create_great_person("merchant", civ, world)
            _set_cooldown(civ.name, "merchant", world)
            spawned.append(gp)
            civ.event_counts["high_trade_route_turns"] = 0

    # ------------------------------------------------------------------
    # Threshold 4: Prophet — first non-origin adoption OR origin with 3+ adherents
    # ------------------------------------------------------------------
    if not _is_on_cooldown(civ.name, "prophet", world):
        prophet_triggered = civ.event_counts.get("prophet_trigger", 0) > 0
        if prophet_triggered:
            _enforce_cap(civ, world)
            gp = _create_great_person("prophet", civ, world)
            _set_cooldown(civ.name, "prophet", world)
            spawned.append(gp)
            civ.event_counts["prophet_trigger"] = 0

    return spawned


# ---------------------------------------------------------------------------
# Task 4: Lifecycle management
# ---------------------------------------------------------------------------

def _compute_lifespan(seed: int, born_turn: int, name: str) -> int:
    """Return a deterministic lifespan in [20, 30] for a Great Person."""
    return 20 + ((seed + born_turn + hash(name)) % 11)


def check_lifespan_expiry(civ: Civilization, world: WorldState) -> list[GreatPerson]:
    """
    Retire any active Great Persons in *civ* whose lifespan has been exceeded.

    Returns the list of newly retired GreatPerson objects.
    """
    retired = []
    for gp in list(civ.great_persons):
        if not gp.active:
            continue
        lifespan = _compute_lifespan(world.seed, gp.born_turn, gp.name)
        if world.turn - gp.born_turn >= lifespan:
            _retire_person(gp, civ, world)
            retired.append(gp)
    return retired


def kill_great_person(
    gp: GreatPerson,
    civ: Civilization,
    world: WorldState,
    context: str = "unknown",
) -> GreatPerson:
    """
    Kill a Great Person in *context*.  Sets fate='dead', records death_turn,
    removes from civ, and moves to world.retired_persons.
    """
    gp.active = False
    gp.alive = False
    gp.fate = "dead"
    gp.death_turn = world.turn
    if gp in civ.great_persons:
        civ.great_persons.remove(gp)
    world.retired_persons.append(gp)
    # Check for folk hero elevation
    from chronicler.traditions import check_folk_hero
    became_hero = check_folk_hero(gp, civ, world, context=context)
    if became_hero:
        from chronicler.models import Event
        world.events_timeline.append(Event(
            turn=world.turn, event_type="folk_hero_created",
            actors=[civ.name],
            description=f"{gp.name} of {civ.name} becomes a folk hero after a dramatic {context}.",
            importance=6,
        ))
    return gp
