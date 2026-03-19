"""M16a: Culture as property -- value drift, assimilation, prestige."""

from __future__ import annotations

from collections import Counter

from chronicler.agent_bridge import VALUE_TO_ID
from chronicler.models import ActiveCondition, Disposition, Event, NamedEvent, WorldState
from chronicler.utils import civ_index, clamp
from chronicler.emergence import get_severity_multiplier

VALUE_OPPOSITIONS: dict[str, str] = {
    "Freedom": "Order",
    "Order": "Freedom",
    "Liberty": "Order",
    "Tradition": "Knowledge",
    "Knowledge": "Tradition",
    "Honor": "Cunning",
    "Cunning": "Honor",
    "Piety": "Cunning",
    "Self-reliance": "Trade",
    "Trade": "Self-reliance",
}

_DISPOSITION_ORDER = list(Disposition)


def upgrade_disposition(current: Disposition) -> Disposition:
    idx = _DISPOSITION_ORDER.index(current)
    return _DISPOSITION_ORDER[min(idx + 1, len(_DISPOSITION_ORDER) - 1)]


def _downgrade_disposition(current: Disposition) -> Disposition:
    idx = _DISPOSITION_ORDER.index(current)
    return _DISPOSITION_ORDER[max(idx - 1, 0)]


def apply_value_drift(world: WorldState, agent_snapshot=None) -> None:
    """Accumulate disposition drift from shared/opposing values.

    When agent_snapshot is provided (M36 bottom-up path), compute drift from
    per-civ cultural value frequency profiles derived from agent data.
    When None, fall back to the M16 civ-level value comparison.
    """
    from chronicler.movements import SCHISM_DIVERGENCE_THRESHOLD

    civs = world.civilizations

    if agent_snapshot is not None:
        # --- M36 bottom-up path: derive drift from agent cultural profiles ---
        profiles = compute_civ_cultural_profile(agent_snapshot)
        # Build civ_id -> civ mapping using list index as civ_id
        civ_id_map = {i: civ for i, civ in enumerate(civs)}
        all_values = set()
        for prof in profiles.values():
            all_values.update(prof.keys())

        for i, civ_a in enumerate(civs):
            for j, civ_b in enumerate(civs):
                if j <= i:
                    continue
                prof_a = profiles.get(i, Counter())
                prof_b = profiles.get(j, Counter())
                total_a = sum(prof_a.values()) or 1
                total_b = sum(prof_b.values()) or 1
                shared_frac = sum(
                    min(prof_a.get(v, 0) / total_a, prof_b.get(v, 0) / total_b)
                    for v in all_values
                )
                from chronicler.tuning import get_multiplier, K_CULTURAL_DRIFT_SPEED
                net_drift = int((shared_frac - 0.3) * 10 * get_multiplier(world, K_CULTURAL_DRIFT_SPEED))
                if net_drift == 0:
                    continue

                for a_name, b_name in [(civ_a.name, civ_b.name), (civ_b.name, civ_a.name)]:
                    rel = world.relationships.get(a_name, {}).get(b_name)
                    if rel is None:
                        continue
                    rel.disposition_drift += net_drift
                    if rel.disposition_drift >= 10:
                        rel.disposition = upgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0
                    elif rel.disposition_drift <= -10:
                        rel.disposition = _downgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0
    else:
        # --- M16 civ-level fallback ---
        for i, civ_a in enumerate(civs):
            for civ_b in civs[i + 1:]:
                shared = sum(1 for v in civ_a.values if v in civ_b.values)
                opposing = sum(
                    1 for va in civ_a.values for vb in civ_b.values
                    if VALUE_OPPOSITIONS.get(va) == vb
                )
                net_drift = (shared * 2) - (opposing * 2)
                if net_drift == 0:
                    continue

                for a_name, b_name in [(civ_a.name, civ_b.name), (civ_b.name, civ_a.name)]:
                    rel = world.relationships.get(a_name, {}).get(b_name)
                    if rel is None:
                        continue
                    rel.disposition_drift += net_drift
                    if rel.disposition_drift >= 10:
                        rel.disposition = upgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0
                    elif rel.disposition_drift <= -10:
                        rel.disposition = _downgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0

    # Movement co-adoption effects (accumulate only — threshold applied next cycle)
    for movement in world.movements:
        adherent_names = list(movement.adherents.keys())
        for idx_a, name_a in enumerate(adherent_names):
            for name_b in adherent_names[idx_a + 1:]:
                divergence = abs(movement.adherents[name_a] - movement.adherents[name_b])
                movement_drift = 5 if divergence < SCHISM_DIVERGENCE_THRESHOLD else -5
                for a, b in [(name_a, name_b), (name_b, name_a)]:
                    rel = world.relationships.get(a, {}).get(b)
                    if rel is None:
                        continue
                    rel.disposition_drift += movement_drift


ASSIMILATION_THRESHOLD = 15
ASSIMILATION_STABILITY_DRAIN = 3
RECONQUEST_COOLDOWN = 10
ASSIMILATION_AGENT_THRESHOLD = 0.60
ASSIMILATION_GUARD_TURNS = 5


def compute_civ_cultural_profile(snapshot) -> dict[int, Counter]:
    """Aggregate per-civ cultural value frequency from agent snapshot."""
    if snapshot is None or snapshot.num_rows == 0:
        return {}
    civs = snapshot.column("civ_affinity").to_pylist()
    cv0 = snapshot.column("cultural_value_0").to_pylist()
    cv1 = snapshot.column("cultural_value_1").to_pylist()
    cv2 = snapshot.column("cultural_value_2").to_pylist()
    profiles: dict[int, Counter] = {}
    for i in range(len(civs)):
        civ_id = civs[i]
        if civ_id not in profiles:
            profiles[civ_id] = Counter()
        for val in (cv0[i], cv1[i], cv2[i]):
            if val != 0xFF and val < 6:
                profiles[civ_id][val] += 1
    return profiles


def tick_cultural_assimilation(world: WorldState, acc=None, agent_snapshot=None) -> None:
    """Tick cultural assimilation for all regions.

    When agent_snapshot is provided (hybrid/shadow mode), use agent-driven
    60% cultural value check.  When None (agents=off), fall back to M16
    timer-based path.
    """
    for region_idx, region in enumerate(world.regions):
        if region.controller is None:
            continue

        if region.cultural_identity is None:
            region.cultural_identity = region.controller
            continue

        if region.cultural_identity == region.controller:
            if region.foreign_control_turns > 0:
                region.foreign_control_turns = 0
                world.active_conditions.append(ActiveCondition(
                    condition_type="restless_population",
                    affected_civs=[region.controller],
                    duration=RECONQUEST_COOLDOWN,
                    severity=5,
                ))
            continue

        region.foreign_control_turns += 1
        assimilated = False

        if agent_snapshot is not None:
            # --- Agent-driven path ---
            if region.foreign_control_turns >= ASSIMILATION_GUARD_TURNS:
                controller_civ = next(
                    (c for c in world.civilizations if c.name == region.controller), None
                )
                if controller_civ and controller_civ.values:
                    primary_value = controller_civ.values[0]
                    target_val_id = VALUE_TO_ID.get(primary_value)
                    if target_val_id is not None:
                        # Count agents in this region holding the value
                        regions_col = agent_snapshot.column("region").to_pylist()
                        cv0 = agent_snapshot.column("cultural_value_0").to_pylist()
                        cv1 = agent_snapshot.column("cultural_value_1").to_pylist()
                        cv2 = agent_snapshot.column("cultural_value_2").to_pylist()
                        total = 0
                        holders = 0
                        for j in range(agent_snapshot.num_rows):
                            if regions_col[j] == region_idx:
                                total += 1
                                if target_val_id in (cv0[j], cv1[j], cv2[j]):
                                    holders += 1
                        if total > 0 and (holders / total) >= ASSIMILATION_AGENT_THRESHOLD:
                            assimilated = True
        else:
            # --- M16 timer-based fallback ---
            if region.foreign_control_turns >= ASSIMILATION_THRESHOLD:
                assimilated = True

        if assimilated:
            region.cultural_identity = region.controller
            region.foreign_control_turns = 0
            world.named_events.append(NamedEvent(
                name=f"Assimilation of {region.name}",
                event_type="cultural_assimilation",
                turn=world.turn,
                actors=[region.controller],
                region=region.name,
                description=f"{region.name} has been culturally assimilated by {region.controller}.",
                importance=6,
            ))
        elif region.foreign_control_turns >= RECONQUEST_COOLDOWN:
            controller = next(
                (c for c in world.civilizations if c.name == region.controller), None
            )
            if controller:
                mult = get_severity_multiplier(controller, world)
                if acc is not None:
                    ctrl_idx = civ_index(world, controller.name)
                    acc.add(ctrl_idx, controller, "stability", -int(ASSIMILATION_STABILITY_DRAIN * mult), "signal")
                else:
                    controller.stability = clamp(
                        controller.stability - int(ASSIMILATION_STABILITY_DRAIN * mult), 0, 100
                    )


PROPAGANDA_COST = 5
PROPAGANDA_ACCELERATION = 3
COUNTER_PROPAGANDA_COST = 3
CULTURE_PROJECTION_THRESHOLD = 60


def _counter_propaganda_reaction(world: WorldState, defender, region, seed: int, acc=None) -> int:
    if defender.treasury >= COUNTER_PROPAGANDA_COST:
        if acc is not None:
            defender_idx = civ_index(world, defender.name)
            acc.add(defender_idx, defender, "treasury", -COUNTER_PROPAGANDA_COST, "keep")
        else:
            defender.treasury -= COUNTER_PROPAGANDA_COST
        return -PROPAGANDA_ACCELERATION
    return 0


def resolve_invest_culture(civ, world: WorldState, acc=None):
    """Resolve INVEST_CULTURE action: project propaganda into a rival region."""
    import hashlib
    from chronicler.models import Event, NamedEvent
    from chronicler.tech import get_era_bonus

    projection_range = get_era_bonus(civ.tech_era, "culture_projection_range", default=1)
    global_projection = projection_range == -1

    candidates = [
        r for r in world.regions
        if r.controller is not None
        and r.controller != civ.name
        and r.cultural_identity != civ.name
    ]

    if global_projection:
        targets = candidates
    else:
        civ_regions = {r.name for r in world.regions if r.controller == civ.name}
        adjacent = set()
        for r in world.regions:
            if r.name in civ_regions:
                adjacent.update(r.adjacencies)
        targets = [r for r in candidates if r.name in adjacent]

    if not targets or civ.treasury < PROPAGANDA_COST:
        return Event(
            turn=world.turn, event_type="action", actors=[civ.name],
            description=f"{civ.name} attempts cultural influence but finds no valid target.",
            importance=1,
        )

    targets.sort(key=lambda r: r.foreign_control_turns, reverse=True)
    max_fct = targets[0].foreign_control_turns
    tied = [r for r in targets if r.foreign_control_turns == max_fct]
    if len(tied) > 1:
        salt = f"{world.seed}:{world.turn}:propaganda:{civ.name}"
        tied.sort(key=lambda r: hashlib.sha256(f"{salt}:{r.name}".encode()).hexdigest())
    target = tied[0]

    if acc is not None:
        civ_idx = civ_index(world, civ.name)
        acc.add(civ_idx, civ, "treasury", -PROPAGANDA_COST, "keep")
    else:
        civ.treasury -= PROPAGANDA_COST

    defender = next((c for c in world.civilizations if c.name == target.controller), None)
    adjustment = 0
    if defender:
        adjustment = _counter_propaganda_reaction(world, defender, target, world.seed, acc=acc)

    # M21: MEDIA doubles propaganda acceleration
    if civ.active_focus == "media":
        base_accel = PROPAGANDA_ACCELERATION * 2
        world.events_timeline.append(Event(
            turn=world.turn, event_type="capability_media",
            actors=[civ.name], description=f"{civ.name} media doubles propaganda acceleration",
            importance=1,
        ))
    else:
        base_accel = PROPAGANDA_ACCELERATION
    net_acceleration = base_accel + adjustment
    # M22: Power struggle reduces action effectiveness by 20%
    from chronicler.action_engine import _power_struggle_factor
    net_acceleration = int(net_acceleration * _power_struggle_factor(civ))
    target.foreign_control_turns += net_acceleration

    # M36: Set signal flag for Rust culture_tick to boost drift toward controller values
    target._culture_investment_active = True

    world.named_events.append(NamedEvent(
        name=f"Propaganda in {target.name}",
        event_type="propaganda_campaign",
        turn=world.turn,
        actors=[civ.name],
        region=target.name,
        description=f"{civ.name} projects cultural influence into {target.name}.",
        importance=5,
    ))

    return Event(
        turn=world.turn, event_type="invest_culture", actors=[civ.name],
        description=f"{civ.name} projects cultural influence into {target.name}.",
        importance=5,
    )


def check_cultural_victories(world: WorldState) -> None:
    """Check for cultural hegemony and universal enlightenment."""
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue
        others_combined = sum(c.culture for c in world.civilizations if c != civ)
        if civ.culture > others_combined:
            if not any(
                ne.event_type == "cultural_hegemony" and civ.name in ne.actors
                for ne in world.named_events
            ):
                world.named_events.append(NamedEvent(
                    name=f"Cultural Hegemony of {civ.name}",
                    event_type="cultural_hegemony",
                    turn=world.turn,
                    actors=[civ.name],
                    description=f"{civ.name} achieves cultural hegemony — their culture surpasses all others combined.",
                    importance=9,
                ))

    all_civ_names = {c.name for c in world.civilizations}
    for movement in world.movements:
        if set(movement.adherents.keys()) == all_civ_names:
            if not any(
                ne.event_type == "universal_enlightenment"
                and movement.id in ne.description
                for ne in world.named_events
            ):
                world.named_events.append(NamedEvent(
                    name=f"Universal Enlightenment ({movement.id})",
                    event_type="universal_enlightenment",
                    turn=world.turn,
                    actors=list(movement.adherents.keys()),
                    description=f"[{movement.id}] Universal enlightenment achieved — all civilizations have adopted this movement.",
                    importance=10,
                ))


def tick_prestige(world: WorldState, acc=None) -> None:
    """Decay prestige and award trade income bonus."""
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "prestige", -1, "keep")
        else:
            civ.prestige = max(0, civ.prestige - 1)
        trade_bonus = civ.prestige // 5
        if trade_bonus > 0:
            if acc is not None:
                civ_idx = civ_index(world, civ.name)
                acc.add(civ_idx, civ, "treasury", trade_bonus, "keep")
            else:
                civ.treasury += trade_bonus
