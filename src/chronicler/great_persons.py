"""Great Person generation, lifecycle, and modifier registry."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from chronicler.leaders import _pick_name, ALL_TRAITS
from chronicler.religion import (
    PILGRIMAGE_DURATION_MIN,
    PILGRIMAGE_DURATION_MAX,
    PILGRIMAGE_SKILL_BOOST,
    _PRIEST_OCCUPATION,
)
from chronicler.utils import stable_hash_int

if TYPE_CHECKING:
    from chronicler.models import Civilization, GreatPerson, WorldState

# ---------------------------------------------------------------------------
# M45: Deeds tracking
# ---------------------------------------------------------------------------

DEEDS_CAP = 10


def _append_deed(gp: "GreatPerson", deed: str) -> None:
    """Append a deed to a GreatPerson, capping at DEEDS_CAP entries."""
    gp.deeds.append(deed)
    if len(gp.deeds) > DEEDS_CAP:
        gp.deeds = gp.deeds[-DEEDS_CAP:]


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
    return sum(1 for c in world.civilizations for gp in c.great_persons if gp.active)


def _retire_person(gp: GreatPerson, civ: Civilization, world: WorldState) -> None:
    gp.active = False
    gp.alive = False
    gp.fate = "retired"
    _append_deed(gp, f"Retired in {gp.region or 'unknown'}")
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
    """If adding a GP would exceed the cap, retire the oldest active GP globally."""
    if _total_great_persons(world) >= _GREAT_PERSON_CAP:
        oldest_gp = None
        oldest_civ = None
        for owner in world.civilizations:
            for gp in owner.great_persons:
                if not gp.active:
                    continue
                if oldest_gp is None or gp.born_turn < oldest_gp.born_turn:
                    oldest_gp = gp
                    oldest_civ = owner
        if oldest_gp is not None and oldest_civ is not None:
            _retire_person(oldest_gp, oldest_civ, world)


def _create_great_person(role: str, civ: Civilization, world: WorldState) -> GreatPerson:
    """Instantiate a new GreatPerson, append it to civ.great_persons, and return it."""
    from chronicler.models import GreatPerson
    rng = random.Random(
        stable_hash_int("great_person_spawn", world.seed, world.turn, civ.name, role)
    )
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
            civ.event_counts["tech_advanced"] = 0  # Only reset on actual spawn
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

    # M52: GP artifact intent (aggregate mode)
    from chronicler.artifacts import emit_gp_artifact_intent
    for gp in spawned:
        emit_gp_artifact_intent(world, civ, gp)

    return spawned


# ---------------------------------------------------------------------------
# Task 4: Lifecycle management
# ---------------------------------------------------------------------------

def _compute_lifespan(seed: int, born_turn: int, name: str) -> int:
    """Return a deterministic lifespan in [20, 30] for a Great Person."""
    return 20 + (stable_hash_int("great_person_lifespan", seed, born_turn, name) % 11)


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


def retire_orphaned_great_persons(world: WorldState) -> list[GreatPerson]:
    """Retire active great persons whose civilization no longer controls land."""
    retired: list[GreatPerson] = []
    for civ in world.civilizations:
        if civ.regions:
            continue
        for gp in list(civ.great_persons):
            if not gp.active:
                continue
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
    _append_deed(gp, f"Died in {gp.region or 'unknown'}")
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


# ---------------------------------------------------------------------------
# M38b: Pilgrimage subsystem
# ---------------------------------------------------------------------------

def check_pilgrimages(
    great_persons: list,
    temples: list,
    snapshot,
    current_turn: int,
) -> list:
    """Check for pilgrimage departures and returns.

    temples: list of (region_name, Infrastructure) tuples
    Returns a list of Event objects.
    """
    from chronicler.models import Event

    events: list[Event] = []

    # Build O(1) lookup: agent_id → row index in snapshot
    agent_idx_map: dict[int, int] = {}
    if snapshot is not None and snapshot.num_rows > 0:
        ids = snapshot.column("id").to_pylist()
        agent_idx_map = {aid: i for i, aid in enumerate(ids)}

    # Pre-extract snapshot columns for fast row lookup
    _snap_occupation: list | None = None
    _snap_loyalty_trait: list | None = None
    _snap_loyalty: list | None = None
    _snap_belief: list | None = None
    if snapshot is not None and snapshot.num_rows > 0:
        _snap_occupation = snapshot.column("occupation").to_pylist()
        _snap_loyalty_trait = snapshot.column("loyalty_trait").to_pylist()
        _snap_loyalty = snapshot.column("loyalty").to_pylist()
        try:
            _snap_belief = snapshot.column("belief").to_pylist()
        except (KeyError, Exception):
            _snap_belief = None

    def _agent_belief(gp) -> int | None:
        """Return agent's belief id, or None if unavailable."""
        if _snap_belief is None or gp.agent_id is None:
            return None
        idx = agent_idx_map.get(gp.agent_id)
        if idx is None:
            return None
        return _snap_belief[idx]

    def _agent_occupation(gp) -> int | None:
        """Return agent's occupation id, or None if unavailable."""
        if _snap_occupation is None or gp.agent_id is None:
            return None
        idx = agent_idx_map.get(gp.agent_id)
        if idx is None:
            return None
        return _snap_occupation[idx]

    def _agent_loyalty(gp) -> float:
        """Return agent's loyalty_trait, or 0.0 if unavailable."""
        if _snap_loyalty_trait is None or gp.agent_id is None:
            return 0.0
        idx = agent_idx_map.get(gp.agent_id)
        if idx is None:
            return 0.0
        return _snap_loyalty_trait[idx]

    def _agent_dynamic_loyalty(gp) -> float:
        """Return agent's dynamic loyalty, or 0.0 if unavailable."""
        if _snap_loyalty is None or gp.agent_id is None:
            return 0.0
        idx = agent_idx_map.get(gp.agent_id)
        if idx is None:
            return 0.0
        return _snap_loyalty[idx]

    # --- Phase 1: Process returns ---
    for gp in great_persons:
        if gp.pilgrimage_return_turn is None:
            continue
        if current_turn >= gp.pilgrimage_return_turn:
            destination = gp.pilgrimage_destination or "unknown"
            gp.pilgrimage_skill_bonus = PILGRIMAGE_SKILL_BOOST
            gp.arc_type = "Prophet"  # Guard-compat shim: classifier confirms idempotently (M45 Decision 18)
            _append_deed(gp, "Returned from pilgrimage as Prophet")
            gp.pilgrimage_destination = None
            gp.pilgrimage_return_turn = None
            events.append(Event(
                turn=current_turn,
                event_type="pilgrimage_return",
                actors=[gp.name, gp.civilization],
                description=(
                    f"{gp.name} of {gp.civilization} returns from pilgrimage to "
                    f"{destination}, transformed into a Prophet."
                ),
                importance=5,
            ))

    # --- Phase 2: Process departures ---
    faiths_departed: set[int] = set()

    for gp in great_persons:
        # Skip already on pilgrimage
        if gp.pilgrimage_return_turn is not None:
            continue
        # Skip already a Prophet
        if gp.arc_type == "Prophet":
            continue

        # Get belief from snapshot
        belief = _agent_belief(gp)
        if belief is None or belief == 0xFF:
            continue

        # One departure per faith per turn
        if belief in faiths_departed:
            continue

        # Check occupation == priest OR loyalty_trait > 0.5
        occupation = _agent_occupation(gp)
        loyalty_trait = _agent_loyalty(gp)
        if occupation != _PRIEST_OCCUPATION and loyalty_trait <= 0.5:
            continue

        # Check dynamic loyalty > 0.5
        dynamic_loyalty = _agent_dynamic_loyalty(gp)
        if dynamic_loyalty <= 0.5:
            continue

        # Find highest-prestige temple matching faith
        matching_temples = [
            (rn, t) for rn, t in temples
            if getattr(t, 'faith_id', -1) == belief
        ]
        if not matching_temples:
            continue

        best_region, best_temple = max(
            matching_temples, key=lambda x: x[1].temple_prestige
        )

        # Send GP on pilgrimage
        gp.pilgrimage_destination = best_region
        duration_span = PILGRIMAGE_DURATION_MAX - PILGRIMAGE_DURATION_MIN + 1
        duration = PILGRIMAGE_DURATION_MIN + (
            stable_hash_int(
                "pilgrimage_duration",
                current_turn,
                gp.name,
                gp.civilization,
                gp.agent_id,
                belief,
                best_region,
            ) % duration_span
        )
        gp.pilgrimage_return_turn = current_turn + duration
        _append_deed(gp, f"Departed on pilgrimage to {best_region}")
        faiths_departed.add(belief)

        events.append(Event(
            turn=current_turn,
            event_type="pilgrimage_departure",
            actors=[gp.name, gp.civilization],
            description=(
                f"{gp.name} of {gp.civilization} departs on pilgrimage to "
                f"{best_region}."
            ),
            importance=4,
        ))

    return events
