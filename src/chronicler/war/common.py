"""Shared context and helpers for the campaign layer.

Region identity is the index in ``world.regions`` (AGENTS.md); the adjacency
graph handed to the M60a kernel helpers is built from those indices. All
randomness uses ``random.Random(stable_hash_int("war", <namespace>, seed,
turn, ...))`` so results are process-stable and independent of call order in
other subsystems.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from chronicler.campaign_logistics import Region as KernelRegion
from chronicler.campaign_logistics import Topology, shortest_path, validated_graph
from chronicler.utils import STAT_FLOOR, civ_index, clamp, stable_hash_int
from chronicler.war.params import POLICY

if TYPE_CHECKING:
    from chronicler.models import Army, Civilization, Event, Region, WarRecord, WorldState

AGENT_POOL_MODES = frozenset({"demographics-only", "shadow", "hybrid"})


@dataclass
class WarContext:
    world: "WorldState"
    acc: object | None
    graph: dict[int, tuple[int, ...]]
    index: dict[str, int]
    names: list[str]
    bridge: object | None
    events: list = field(default_factory=list)
    # Per-civ fractional military-stat losses, flushed once per tick.
    military_loss: dict[str, float] = field(default_factory=dict)
    battle_regions: set = field(default_factory=set)

    @property
    def turn(self) -> int:
        return self.world.turn

    @property
    def agent_pool(self) -> bool:
        """True when the Rust agent pool owns population (enlist real agents)."""
        return (self.bridge is not None
                and getattr(self.world, "agent_mode", None) in AGENT_POOL_MODES)


def build_graph(world: "WorldState") -> tuple[dict[int, tuple[int, ...]], dict[str, int], list[str]]:
    """Return the kernel-validated adjacency graph over region indices.

    Adjacency is symmetrized defensively (the kernel rejects one-way edges);
    unknown names and self-edges are dropped.
    """
    names = [r.name for r in world.regions]
    index = {name: i for i, name in enumerate(names)}
    neighbors: dict[int, set[int]] = {i: set() for i in range(len(names))}
    for i, region in enumerate(world.regions):
        for adj in region.adjacencies:
            j = index.get(adj)
            if j is None or j == i:
                continue
            neighbors[i].add(j)
            neighbors[j].add(i)
    topology = Topology(
        version=f"world-adjacency-{len(names)}",
        regions=tuple(KernelRegion(i, tuple(sorted(nb))) for i, nb in sorted(neighbors.items())),
    )
    return validated_graph(POLICY, topology), index, names


def build_context(world: "WorldState", acc=None, bridge=None) -> WarContext:
    graph, index, names = build_graph(world)
    if bridge is None:
        bridge = getattr(world, "_agent_bridge", None)
    return WarContext(world=world, acc=acc, graph=graph, index=index, names=names, bridge=bridge)


def war_rng(ctx: WarContext, namespace: str, *parts) -> random.Random:
    return random.Random(stable_hash_int("war", namespace, ctx.world.seed, ctx.world.turn, *parts))


def bernoulli_round(expected_thousandths: int, rng: random.Random) -> int:
    """Integer part plus one more with probability of the fractional part."""
    whole, frac = divmod(max(0, int(expected_thousandths)), 1000)
    return whole + (1 if rng.randrange(1000) < frac else 0)


# --- graph helpers ---------------------------------------------------------------

def path_names(ctx: WarContext, start: str, goal: str) -> list[str]:
    a, b = ctx.index.get(start), ctx.index.get(goal)
    if a is None or b is None:
        return []
    return [ctx.names[i] for i in shortest_path(ctx.graph, a, b)]


def distances_from(ctx: WarContext, start: str) -> dict[str, int]:
    """Single-source BFS hop counts by region name."""
    origin = ctx.index.get(start)
    if origin is None:
        return {}
    dist = {origin: 0}
    queue = deque([origin])
    while queue:
        node = queue.popleft()
        for nb in ctx.graph[node]:
            if nb not in dist:
                dist[nb] = dist[node] + 1
                queue.append(nb)
    return {ctx.names[i]: d for i, d in dist.items()}


def nearest(ctx: WarContext, start: str, candidates: Iterable[str]) -> str | None:
    """Closest candidate by hop count; ties break on world region order."""
    dist = distances_from(ctx, start)
    best = None
    for name in candidates:
        if name not in dist:
            continue
        key = (dist[name], ctx.index[name])
        if best is None or key < best[0]:
            best = (key, name)
    return best[1] if best else None


# --- world helpers -----------------------------------------------------------------

def living_civ(world: "WorldState", name: str | None) -> "Civilization | None":
    if name is None:
        return None
    civ = world.civ_map.get(name)
    if civ is None or not civ.regions:
        return None
    return civ


def at_war(world: "WorldState", a: str, b: str) -> bool:
    return (a, b) in world.active_wars or (b, a) in world.active_wars


def holds(region: "Region", civ_name: str) -> bool:
    """Civ effectively holds the region: owns it unoccupied, or occupies it."""
    if region.occupied_by is not None:
        return region.occupied_by == civ_name
    return region.controller == civ_name


def held_regions(world: "WorldState", civ_name: str) -> list[str]:
    return [r.name for r in world.regions if holds(r, civ_name)]


def own_free_regions(world: "WorldState", civ_name: str) -> list[str]:
    return [r.name for r in world.regions
            if r.controller == civ_name and r.occupied_by in (None, civ_name)]


def armies_of(world: "WorldState", civ_name: str) -> list["Army"]:
    return [a for a in world.war_state.armies if a.civ == civ_name]


def war_for(world: "WorldState", key: str) -> "WarRecord | None":
    for war in world.war_state.wars:
        if war.war_key == key:
            return war
    return None


def other_side(war: "WarRecord", civ_name: str) -> str:
    return war.defender if civ_name == war.attacker else war.attacker


def is_fortified(world: "WorldState", region: "Region") -> bool:
    from chronicler.models import InfrastructureType
    if any(i.type == InfrastructureType.FORTIFICATIONS and i.active for i in region.infrastructure):
        return True
    owner = world.civ_map.get(region.controller) if region.controller else None
    if owner is not None and owner.capital_region == region.name:
        return True
    return any(s.status.value in ("active", "dissolving") for s in region.settlements)


# --- stat routing -------------------------------------------------------------------

def add_stat(ctx: WarContext, civ: "Civilization", stat: str, delta: float, category: str) -> None:
    """Route a stat mutation through the accumulator, or apply it directly."""
    if not delta:
        return
    if ctx.acc is not None:
        ctx.acc.add(civ_index(ctx.world, civ.name), civ, stat, delta, category)
        return
    if stat == "treasury":
        civ.treasury += int(delta)
    else:
        floor = STAT_FLOOR.get(stat, 0)
        setattr(civ, stat, clamp(int(getattr(civ, stat) + delta), floor, 100))


def projected_treasury(ctx: WarContext, civ: "Civilization") -> int:
    """Treasury including keep-category changes already queued this turn."""
    value = float(civ.treasury)
    if ctx.acc is not None:
        idx = civ_index(ctx.world, civ.name)
        # Keep changes before the watermark are already in civ.treasury.
        start = getattr(ctx.acc, "_keep_applied_up_to", 0)
        for change in getattr(ctx.acc, "_changes", ())[start:]:
            if change.civ_id == idx and change.stat == "treasury" and change.category == "keep":
                value += change.delta
    return int(value)


def spend(ctx: WarContext, civ: "Civilization", amount: int) -> int:
    """Spend up to ``amount`` of available treasury; return the amount paid."""
    if amount <= 0:
        return 0
    paid = max(0, min(amount, projected_treasury(ctx, civ)))
    if paid:
        add_stat(ctx, civ, "treasury", -paid, "keep")
    return paid


def note_military_loss(ctx: WarContext, civ_name: str, amount: float) -> None:
    if amount > 0:
        ctx.military_loss[civ_name] = ctx.military_loss.get(civ_name, 0.0) + amount


def flush_military_losses(ctx: WarContext) -> None:
    from chronicler.emergence import get_severity_multiplier
    for civ_name in sorted(ctx.military_loss):
        civ = living_civ(ctx.world, civ_name)
        if civ is None:
            continue
        loss = int(round(ctx.military_loss[civ_name] * get_severity_multiplier(civ, ctx.world)))
        if loss > 0:
            add_stat(ctx, civ, "military", -loss, "guard-action")
    ctx.military_loss.clear()


# --- events -----------------------------------------------------------------------------

def emit(ctx: WarContext, event_type: str, actors: list[str], description: str,
         importance: int = 5) -> "Event":
    from chronicler.models import Event
    event = Event(turn=ctx.world.turn, event_type=event_type, actors=list(actors),
                  description=description, importance=importance)
    ctx.events.append(event)
    return event


def name_event(ctx: WarContext, name: str, event_type: str, actors: list[str],
               region: str | None, description: str, importance: int) -> None:
    from chronicler.models import NamedEvent
    ctx.world.named_events.append(NamedEvent(
        name=name, event_type=event_type, turn=ctx.world.turn, actors=list(actors),
        region=region, description=description, importance=importance,
    ))
