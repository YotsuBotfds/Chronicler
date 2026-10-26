"""M24: Information Asymmetry — perception layer for cross-civ stat reads."""
from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Civilization, WorldState

from chronicler.models import Event, FactionType
from chronicler.factions import get_dominant_faction
from chronicler.resources import get_active_trade_route_pairs


def shares_adjacent_region(observer: Civilization, target: Civilization,
                           world: WorldState) -> bool:
    """True if observer controls a region adjacent to a region target controls."""
    # Consume the live list only as far as each adjacency lookup needs. Entries
    # retain the first region with a name, matching the old repeated scan.
    first_by_name = {}
    remaining_regions = iter(world.regions)
    for r in world.regions:
        if r.controller != observer.name:
            continue
        for adj_name in r.adjacencies:
            adj = first_by_name.get(adj_name)
            if adj is None:
                for candidate in remaining_regions:
                    name = candidate.name
                    first_by_name.setdefault(name, candidate)
                    if name == adj_name:
                        adj = candidate
                        break
            if adj and adj.controller == target.name:
                return True
    return False


def border_pairs(world: WorldState) -> set[tuple[str, str]]:
    """All ``(observer, target)`` controller pairs that share a border.

    ``(a, b) in border_pairs(world)`` equals ``shares_adjacent_region`` for
    civs named ``a`` and ``b`` on the same world state (adjacency names
    resolve to the first region with that name, as there). Built in one
    O(regions x degree) pass, so all-pairs callers avoid an O(regions) scan
    per pair.
    """
    first_by_name = {}
    for region in world.regions:
        first_by_name.setdefault(region.name, region)
    pairs: set[tuple[str, str]] = set()
    for region in world.regions:
        if region.controller is None:
            continue
        for adj_name in region.adjacencies:
            adj = first_by_name.get(adj_name)
            if adj is not None and adj.controller is not None:
                pairs.add((region.controller, adj.controller))
    return pairs


def has_active_trade_route(observer: Civilization, target: Civilization,
                           world: WorldState) -> bool:
    """True if an active trade route exists between observer and target."""
    pair = tuple(sorted([observer.name, target.name]))
    return pair in get_active_trade_route_pairs(world)


def in_same_federation(observer: Civilization, target: Civilization,
                       world: WorldState) -> bool:
    """True if both civs are members of the same federation."""
    for fed in world.federations:
        if observer.name in fed.members and target.name in fed.members:
            return True
    return False


def is_vassal_of(civ_a: Civilization, civ_b: Civilization,
                 world: WorldState) -> bool:
    """True if civ_a is a vassal of civ_b."""
    return any(vr.vassal == civ_a.name and vr.overlord == civ_b.name
               for vr in world.vassal_relations)


def at_war(observer: Civilization, target: Civilization,
           world: WorldState) -> bool:
    """True if observer and target are at war (direct or proxy)."""
    a, b = observer.name, target.name
    if (a, b) in world.active_wars or (b, a) in world.active_wars:
        return True
    for pw in world.proxy_wars:
        if (pw.sponsor == a and pw.target_civ == b) or \
           (pw.sponsor == b and pw.target_civ == a):
            return True
    return False


def _ledger_contact(observer: Civilization, target: Civilization, world: WorldState) -> bool:
    """Contact-ledger flow of any channel (goods, people, soldiers, pilgrims)
    between the two civs; False with the ledger off."""
    from chronicler.contact_ledger import civ_contact, ledger_enabled
    return ledger_enabled(world) and civ_contact(world, observer.name, target.name) > 0.0


def compute_accuracy(observer: Civilization, target: Civilization,
                     world: WorldState, *,
                     borders: set[tuple[str, str]] | None = None) -> float:
    """Compute intelligence accuracy from observer toward target.
    Stateless — recomputed from current relationships each turn.
    Returns 0.0 (no contact) to 1.0 (perfect knowledge). Self = 1.0.
    ``borders``: optional :func:`border_pairs` of the same, unchanged world
    state (identical result, cheaper for all-pairs loops).
    """
    if observer.name == target.name:
        return 1.0

    accuracy = 0.0

    if (
        (observer.name, target.name) in borders if borders is not None
        else shares_adjacent_region(observer, target, world)
    ):
        accuracy += 0.3
    if has_active_trade_route(observer, target, world):
        accuracy += 0.2
    if in_same_federation(observer, target, world):
        accuracy += 0.4
    if is_vassal_of(observer, target, world) or is_vassal_of(target, observer, world):
        accuracy += 0.5
    if at_war(observer, target, world):
        accuracy += 0.3

    # Hostages live on the captor's roster and report home about that captor.
    # This is one contact source per pair, regardless of the number held.
    hostage = any(gp.alive and gp.active and gp.is_hostage
                  and gp.origin_civilization == observer.name
                  and gp.civilization == target.name
                  for gp in target.great_persons)

    # Merchant and cultural factions and merchant great persons sharpen what a
    # state knows of realms it is in contact with; they reveal no realm it has
    # never met (2026-10 correction, docs/integration/procedural-gates.md).
    if accuracy > 0.0 or hostage or _ledger_contact(observer, target, world):
        # M22 faction bonus
        dominant = get_dominant_faction(observer.factions)
        if dominant == FactionType.MERCHANT:
            accuracy += 0.1
        elif dominant == FactionType.CULTURAL:
            accuracy += 0.05

        # M17 great person bonuses
        for gp in observer.great_persons:
            if gp.alive and gp.active and not gp.is_hostage:
                if gp.role == "merchant":
                    accuracy += 0.05

    if hostage:
        accuracy += 0.3

    # M17 grudge bonus
    for g in observer.leader.grudges:
        if g["rival_civ"] == target.name and g["intensity"] > 0.3:
            accuracy += 0.1

    return min(1.0, accuracy)


def get_perceived_stat(observer: Civilization, target: Civilization,
                       stat: str, world: WorldState,
                       max_value: int = 100) -> int | None:
    """Return observer's perceived value of target's stat.
    Returns None when accuracy is 0.0 (unknown civ — callsites should skip).
    Gaussian noise, σ = noise_range/2, clipped to ±noise_range, clamped 0–max_value.
    Deterministic: same observer/target/turn/stat → same result.
    max_value: upper clamp bound (default 100 for stats; use higher for treasury).
    """
    return _get_perceived_stat_with_accuracy(
        observer, target, stat, world, max_value,
        accuracy=compute_accuracy(observer, target, world),
    )


def _get_perceived_stat_with_accuracy(observer: Civilization, target: Civilization,
                                      stat: str, world: WorldState,
                                      max_value: int = 100, *, accuracy: float) -> int | None:
    """Apply perception noise using accuracy from the same read-only snapshot.

    Internal snapshot fast path: the caller must not mutate accuracy inputs
    between computing accuracy and this read. Ordinary simulation reads use
    get_perceived_stat, which always recomputes from the current world.
    """
    if accuracy == 0.0:
        return None

    actual = getattr(target, stat)
    noise_range = int((1.0 - accuracy) * 20)
    if noise_range == 0:
        return actual

    seed_bytes = f"{world.seed}:{observer.name}:{target.name}:{world.turn}:{stat}".encode()
    seed_int = int.from_bytes(hashlib.sha256(seed_bytes).digest()[:8], "little")
    rng = random.Random(seed_int)
    noise = int(rng.gauss(0, noise_range / 2))
    noise = max(-noise_range, min(noise_range, noise))
    return max(0, min(max_value, actual + noise))


def emit_intelligence_failure(attacker: Civilization, defender: Civilization,
                              perceived_mil: int, actual_mil: int,
                              world: WorldState) -> Event:
    """Emit event when a war was started on bad intel and the attacker lost."""
    return Event(
        turn=world.turn,
        event_type="intelligence_failure",
        actors=[attacker.name, defender.name],
        description=(
            f"{attacker.name} attacked {defender.name}, believing their military "
            f"strength was {perceived_mil} — it was actually {actual_mil}."
        ),
        importance=7,
    )
