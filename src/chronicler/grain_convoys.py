"""Multi-leg public grain convoys under risk (``--grain-convoys``, default off).

Lane L4 of the livelihoods sprint (:mod:`chronicler.livelihoods` forwards the
switch and the phase hooks). Requires ``--grain-reserves
--public-grain-shipments``; see ``docs/integration/grain-convoys.md``.

Scope
    The public grain shipment pass buys foreign grain only from markets one
    step of the merchant route graph from the buyer's granary (one-hop paid
    orders, :mod:`chronicler.public_grain_shipments`, unchanged). Foreign
    markets two or three steps away are skipped there. A convoy serves exactly
    those multi-hop sources: after the granary pass (``phase10`` hook) the
    buyer spends what is left of its procurement budget on them, in the
    granary pass's own priority order, and the grain travels leg by leg.

Dispatch (Phase 10 of T, after the granary pass)
    The buyer pays the seller's ruler the market price at dispatch
    (``finance.transfer``); the grain leaves the origin market at once and
    loses ``TRANSIT_DECAY["grain"]`` on the way, booked at dispatch as a
    shipment's is. One choice is made from facts known at dispatch: an
    exposed route (fastest, no escort) or the least exposed route with a paid
    escort (``ESCORT_FEE_PER_LEG`` per edge, a disclosed public expenditure
    sink paid by the buyer's treasury: no wage, no recipient). An escort
    musters for ``ESCORT_MUSTER_TURNS`` before the first leg (slower) and
    beats off ``ESCORT_PROTECTION`` of the threats met. ``adaptive`` buys the
    escort only when its fee plus the residual expected loss is below the
    exposed route's expected loss (cargo valued at its price);
    ``cheapest`` never does, ``safest`` always does.

Movement (Phase 10 of each later turn, before the granary pass)
    A convoy takes at most one edge per turn (two turns on rough terrain,
    ``ROUGH_TERRAIN_COST``). At a node it judges its next edge by the facts of
    that turn only: closed when the next region has no ruler, is held by or
    hosts an army of a civ at war with the buyer, is under an embargo with
    the buyer, or the merchant route graph no longer carries the edge (war,
    embargo, disposition, suspended route, blockaded sea lane, besieged
    city). A closed edge means reroute (a new route of at most ``MAX_LEGS``
    edges, ``MAX_REROUTES`` per convoy), else wait (``MAX_WAIT`` turns), else
    turn back along the travelled road; a returning convoy blocked beyond the
    wait is stranded. On an open edge it may meet a threat: pirates on a sea
    lane (``skim_rate``), armies of the buyer's enemies at hand, the buyer's
    enemies holding a neighbouring region, brigands outside the buyer's land.
    Unescorted or not beaten off, a threat ends the convoy: a captor civ
    takes the grain to one of its markets (captured); pirates or brigands
    destroy it (lost). Draws come from ``random.Random(stable_hash_int(
    "grain_convoys", seed, convoy, dispatch turn, turn, leg, direction))``,
    never the global stream. The declared tuning key
    ``livelihoods.convoys.threat_scale`` (default 1, within [0, 1]) scales
    the drawn threat chance only; at 0 it is a cost-retaining risk ablation.

Outcomes (each cargo enters exactly one named destination, once)
    ``arrived``: the destination granary, whoever keeps it (keeper recorded;
    edible only when the next Phase 2 opening releases it); ``captured``: the
    captor's market; ``lost``: the loss sink; ``returned``: the origin market;
    ``stranded``: the market where it stands. Nothing is refunded.

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations`` (names are kept and checked). Treasury changes are
``keep``. Off by default: a world that never enabled the switch has no state
and none of this runs.
"""
from __future__ import annotations

import math
import random

from chronicler.grain_convoys_state import (
    ACTIVE_STATUSES, COUNTERS, MAX_ACTIVE, MAX_FRAME, MAX_ID, MAX_LEGS, MAX_PER_DEST,
    MAX_REROUTES, MAX_ROUTE_NODES, OPERATIONS, ROUTE_POLICIES,
    ConvoyTransition, GrainConvoy, GrainConvoyState, convoy_id,
)

# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/grain-convoys.md)
# ---------------------------------------------------------------------------

ESCORT_FEE_PER_LEG = 1        # treasury per route edge, paid at dispatch to the escort sink
ESCORT_PROTECTION = 0.75      # share of threats an escort beats off
ESCORT_MUSTER_TURNS = 1       # turns an escort takes to muster before the first leg
ROUGH_TERRAIN_COST = 1.5      # an edge touching terrain this costly takes two turns
MAX_WAIT = 2                  # consecutive turns a blocked convoy waits before turning back
MAX_AGE = 24                  # turns on the road before a blocked convoy is stranded
SEA_THREAT_PER_SKIM = 2.0     # threat on a sea lane per unit of its pirate skim rate
ARMY_THREAT = 0.25            # an enemy army at the edge's start or beside its end
FRONTIER_THREAT = 0.10        # an enemy holding a region beside the edge's end
BRIGAND_THREAT = 0.02         # an edge ending outside the buyer's own land
MAX_THREAT = 0.9              # cap of an edge's combined threat
RNG_NAMESPACE = "grain_convoys"
EPS = 1e-9
#: Declared tuning key (cost-retaining risk ablation): the threat
#: probabilities drawn on open edges are multiplied by it, in [0, 1]. At 0 no
#: capture or loss is drawn, while every route, leg, wait, reroute, escort
#: decision, escort fee and muster turn stays as with risk (route and escort
#: choices read the unscaled exposure). Default 1.0.
K_THREAT_SCALE = "livelihoods.convoys.threat_scale"

#: Event types (each with a readable line).
EVENT_TYPES: tuple[str, ...] = (
    "grain_convoy_dispatched", "grain_convoy_turned_back", "grain_convoy_arrived",
    "grain_convoy_captured", "grain_convoy_lost", "grain_convoy_returned", "grain_convoy_stranded",
)


# ---------------------------------------------------------------------------
# Switch (protocol of chronicler.livelihoods)
# ---------------------------------------------------------------------------

def _state(world) -> GrainConvoyState | None:
    container = getattr(world, "livelihoods", None)
    state = getattr(container, "grain_convoys", None) if container is not None else None
    if state is not None and type(state) is not GrainConvoyState:
        raise ValueError("unknown grain convoy state")
    return state


def set_grain_convoys_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (a fresh state, or the saved one kept) or disable new convoys.

    Disabling drains: convoys on the road keep moving until they finish.
    ``--convoy-route-policy`` given with the switch sets the dispatch policy.
    """
    policy = getattr(args, "convoy_route_policy", None) if args is not None else None
    if policy is not None and policy not in ROUTE_POLICIES:
        raise ValueError(f"convoy_route_policy must be one of {ROUTE_POLICIES}")
    state = _state(world)
    if state is None:
        if not value:
            return
        world.livelihoods.grain_convoys = state = GrainConvoyState()
    else:
        validate_convoys(world)
    state.enabled = bool(value)
    if policy is not None:
        state.route_policy = policy


def grain_convoys_active(world) -> bool:
    """Accepting convoys, draining some, or reporting the last turn's transitions."""
    state = _state(world)
    if state is None:
        return False
    return bool(state.enabled or state.convoys
                or (state.frame and state.frame_turn is not None and state.frame_turn >= world.turn - 1))


def threat_scale(world) -> float:
    """The validated ``livelihoods.convoys.threat_scale`` override (1.0 when unset)."""
    from chronicler.tuning import get_override
    value = get_override(world, K_THREAT_SCALE, 1.0)
    if (type(value) not in (int, float) or not math.isfinite(value) or not 0.0 <= value <= 1.0):
        raise ValueError(f"{K_THREAT_SCALE} must be a finite number in [0, 1]")
    return float(value)


def _ready(world, economy_result) -> bool:
    """Movement and dispatch run only where shipments themselves would."""
    from chronicler.grain_reserves import grain_reserves_active
    if economy_result is None or not grain_reserves_active(world):
        return False
    return getattr(world.grain_reserves, "shipments", None) is not None


# ---------------------------------------------------------------------------
# Then-current facts
# ---------------------------------------------------------------------------

def _holder(region) -> str | None:
    """Who effectively holds a region: its occupier, else its ruler."""
    return region.occupied_by if region.occupied_by is not None else region.controller


def _out_edges(graph: dict[int, list[int]]) -> dict[int, tuple[int, ...]]:
    """The permitted merchant graph (destination -> origins) as origin -> destinations."""
    out: dict[int, set[int]] = {}
    for dst, sources in graph.items():
        for src in sources:
            out.setdefault(int(src), set()).add(int(dst))
    return {src: tuple(sorted(dsts)) for src, dsts in out.items()}


def _leg_turns(world, a: int, b: int) -> int:
    from chronicler.economy import TERRAIN_COST
    rough = max(TERRAIN_COST.get(world.regions[a].terrain, 1.0),
                TERRAIN_COST.get(world.regions[b].terrain, 1.0))
    return 2 if rough >= ROUGH_TERRAIN_COST else 1


class _Facts:
    """One buyer's view of this turn's roads (read-only, built per pass)."""

    def __init__(self, world, buyer: int, out: dict[int, tuple[int, ...]]):
        self.world = world
        self.out = out
        regions = world.regions
        self.name = world.civilizations[buyer].name
        self.civ_index = {c.name: i for i, c in enumerate(world.civilizations)}
        index = {r.name: i for i, r in enumerate(regions)}
        self.adj = [tuple(sorted({index[n] for n in r.adjacencies if n in index and index[n] != i}))
                    for i, r in enumerate(regions)]
        self.hostile = {b if a == self.name else a for a, b in world.active_wars if self.name in (a, b)}
        self.hostile.discard(self.name)
        self.embargo = {b if a == self.name else a for a, b in world.embargoes if self.name in (a, b)}
        self.armies: dict[int, set[str]] = {}
        war = getattr(world, "war_state", None)
        for army in (war.armies if war is not None else ()):
            if army.civ in self.hostile and army.soldiers > 0 and army.region in index:
                self.armies.setdefault(index[army.region], set()).add(army.civ)
        from chronicler.maritime import maritime_enabled
        self.maritime = maritime_enabled(world)
        self._cache: dict[tuple[int, int], tuple[str | None, tuple]] = {}

    def hostile_holder(self, rid: int) -> bool:
        region = self.world.regions[rid]
        return _holder(region) in self.hostile or region.controller in self.hostile

    def judge(self, a: int, b: int) -> tuple[str | None, tuple]:
        """(closure reason or None, threat components) of the edge a -> b."""
        key = (a, b)
        if key in self._cache:
            return self._cache[key]
        regions = self.world.regions
        region = regions[b]
        holder = _holder(region)
        if region.controller is None:
            result = ("uncontrolled", ())
        elif self.hostile_holder(b):
            result = ("hostile_holder", ())
        elif b in self.armies:
            result = ("hostile_army", ())
        elif region.controller in self.embargo or holder in self.embargo:
            result = ("embargo", ())
        elif b not in self.out.get(a, ()):
            result = ("route_closed", ())
        else:
            parts: list[tuple[float, str, int, int]] = []
            if self.maritime:
                from chronicler.maritime import lane_zone, skim_rate
                zone = lane_zone(self.world, a, b)
                if zone is not None:
                    skim = skim_rate(self.world, zone)
                    if skim > 0:
                        parts.append((min(MAX_THREAT, SEA_THREAT_PER_SKIM * skim), "sea", -1, -1))
            near: dict[str, int] = {}
            for rid in (a, *self.adj[b]):
                if rid == b:
                    continue
                for civ in sorted(self.armies.get(rid, ())):
                    near.setdefault(civ, rid)
            for civ in sorted((c for c in near if c in self.civ_index), key=self.civ_index.get):
                parts.append((ARMY_THREAT, "army", self.civ_index[civ], near[civ]))
            frontier: dict[str, int] = {}
            for rid in self.adj[b]:
                other = _holder(regions[rid])
                if other in self.hostile and other not in near:
                    frontier.setdefault(other, rid)
            for civ in sorted((c for c in frontier if c in self.civ_index), key=self.civ_index.get):
                parts.append((FRONTIER_THREAT, "frontier", self.civ_index[civ], frontier[civ]))
            if holder != self.name:
                parts.append((BRIGAND_THREAT, "brigands", -1, -1))
            result = (None, tuple(parts))
        self._cache[key] = result
        return result

    def risk(self, a: int, b: int) -> float:
        closed, parts = self.judge(a, b)
        if closed is not None:
            return 1.0
        return _combine(p for p, *_ in parts)


def _combine(probabilities) -> float:
    keep = 1.0
    for p in probabilities:
        keep *= 1.0 - p
    return min(MAX_THREAT, 1.0 - keep)


def _routes(facts: _Facts, start: int, dest: int) -> list[list[int]]:
    """Simple paths start -> dest of at most ``MAX_LEGS`` open edges (sorted)."""
    found: list[list[int]] = []

    def walk(path: list[int]) -> None:
        node = path[-1]
        for nxt in facts.out.get(node, ()):
            if nxt in path or facts.judge(node, nxt)[0] is not None:
                continue
            if nxt == dest:
                found.append(path + [nxt])
            elif len(path) < MAX_LEGS:
                walk(path + [nxt])

    walk([start])
    return found


def _plan(world, facts: _Facts, path: list[int], *, escorted: bool, first: bool) -> tuple:
    """(turns, edges, risk, path): the route as known now."""
    turns = sum(_leg_turns(world, a, b) for a, b in zip(path, path[1:]))
    if escorted and first:
        turns += ESCORT_MUSTER_TURNS
    risk = 1.0 - math.prod(1.0 - facts.risk(a, b) for a, b in zip(path, path[1:]))
    return (turns, len(path) - 1, risk, path)


def _exposed_key(plan):
    return plan[0], plan[1], plan[2], plan[3]


def _safest_key(plan):
    return plan[2], plan[0], plan[1], plan[3]


def _captor_market(world, facts: _Facts, captor: int, preferred: list[int]) -> int | None:
    """A market of the captor civ: where it struck, else its capital, else its first region."""
    from chronicler.war.common import holds
    name = world.civilizations[captor].name
    for rid in preferred:
        if 0 <= rid < len(world.regions) and holds(world.regions[rid], name):
            return rid
    capital = world.civilizations[captor].capital_region
    for rid, region in enumerate(world.regions):
        if region.name == capital and holds(region, name):
            return rid
    for rid, region in enumerate(world.regions):
        if holds(region, name):
            return rid
    return None


# ---------------------------------------------------------------------------
# Admission
# ---------------------------------------------------------------------------

def _adjacent(world, a: int, b: int) -> bool:
    ra, rb = world.regions[a], world.regions[b]
    return rb.name in ra.adjacencies or ra.name in rb.adjacencies


def _check_turn(value, world) -> None:
    if value is not None and (type(value) is not int or not 0 <= value <= world.turn):
        raise ValueError("grain convoy state is ahead of world turn")


def validate_convoys(world) -> None:
    """Pure admission of saved convoys; reject edited universes before effects."""
    state = _state(world)
    if state is None:
        return
    if (type(state.schema_version) is not int or state.schema_version != 1
            or type(state.enabled) is not bool or state.route_policy not in ROUTE_POLICIES
            or type(state.next_convoy) is not int or not 0 <= state.next_convoy <= MAX_ID
            or len(state.convoys) > MAX_ACTIVE or len(state.frame) > MAX_FRAME
            or list(state.counters) != list(COUNTERS)
            or not all(type(v) is float and math.isfinite(v) and v >= 0 for v in state.counters.values())):
        raise ValueError("invalid grain convoy state")
    for turn in (state.moved_turn, state.dispatch_turn, state.frame_turn):
        _check_turn(turn, world)
    if not state.convoys:
        return
    from chronicler.grain_reserves_state import grain_reserves_on
    if not grain_reserves_on(world) or len(world.grain_reserves.granaries) != len(world.regions):
        raise ValueError("grain convoys on the road require the original granary universe")
    regions, civs = world.regions, world.civilizations
    seen: set[int] = set()
    per_dest: dict[int, int] = {}
    for c in state.convoys:
        if type(c) is not GrainConvoy:
            raise ValueError("unknown grain convoy record")
        if (not 0 <= c.convoy < state.next_convoy or c.convoy in seen
                or not 0 <= c.dispatch_turn <= world.turn or c.buyer == c.seller or c.source == c.dest
                or c.status not in ACTIVE_STATUSES or c.policy not in ROUTE_POLICIES):
            raise ValueError("invalid grain convoy identity, timing or status")
        seen.add(c.convoy)
        for index, name in ((c.source, c.source_name), (c.dest, c.dest_name)):
            if index >= len(regions) or regions[index].name != name:
                raise ValueError("grain convoy region was removed or replaced")
        for index, name in ((c.buyer, c.buyer_name), (c.seller, c.seller_name)):
            if index >= len(civs) or civs[index].name != name:
                raise ValueError("grain convoy civilization was removed or replaced")
        route = c.route
        if (len(route) > MAX_ROUTE_NODES or route[0] != c.source or route[-1] != c.dest
                or any(type(r) is not int or not 0 <= r < len(regions) for r in route)
                or any(not _adjacent(world, a, b) for a, b in zip(route, route[1:]))):
            raise ValueError("invalid grain convoy route")
        forward = c.status != "returning"
        if (not (0 <= c.leg <= len(route) - 2 if forward else 1 <= c.leg <= len(route) - 1)
                or (c.progress == 0) != (c.leg_turns == 0) or c.progress >= max(1, c.leg_turns)
                or c.leg_turns > 2 + ESCORT_MUSTER_TURNS or c.reroutes > MAX_REROUTES
                or c.repelled > c.threats or (not c.escorted and c.escort_fee != 0)):
            raise ValueError("invalid grain convoy progress")
        if (not all(math.isfinite(v) for v in (c.sent, c.net, c.loss, c.cargo))
                or abs(c.sent - c.net - c.loss) > 1e-9 * max(1.0, c.sent)
                or c.cargo > c.net + 1e-9 * max(1.0, c.net)):
            raise ValueError("grain convoy cargo does not balance")
        per_dest[c.dest] = per_dest.get(c.dest, 0) + 1
        if per_dest[c.dest] > MAX_PER_DEST:
            raise ValueError("grain convoy destination capacity exceeded")
    for row in state.frame:
        if (type(row) is not ConvoyTransition or row.turn != state.frame_turn
                or row.operation not in OPERATIONS or row.convoy >= state.next_convoy):
            raise ValueError("invalid grain convoy transition frame")


def _check_closure(world, state) -> None:
    """``CHRONICLER_CHECK_RESOURCES=1``: every committed grain is in one place."""
    from chronicler.production_ledger import resource_check_enabled
    if not resource_check_enabled():
        return
    k = state.counters
    placed = math.fsum([k["delivered"], k["captured_grain"], k["lost_grain"], k["returned_grain"],
                        k["stranded_grain"], *(c.cargo for c in state.convoys)])
    if abs(k["committed_net"] - placed) > 1e-9 * max(1.0, k["committed_net"]):
        raise AssertionError(f"resource ledger does not balance at turn {world.turn} (grain convoys): "
                             f"committed {k['committed_net']}, placed {placed}")
    if abs(k["sent"] - k["committed_net"] - k["transit_loss"]) > 1e-9 * max(1.0, k["sent"]):
        raise AssertionError(f"resource ledger does not balance at turn {world.turn} (grain convoys): "
                             f"sent {k['sent']} != committed {k['committed_net']} + transit {k['transit_loss']}")


# ---------------------------------------------------------------------------
# Granary pass hook: paid cargo on the road toward a granary is inbound
# ---------------------------------------------------------------------------

def add_convoy_inbound(world, inbound: list[float]) -> None:
    """Add cargo still heading for each granary (not returning) to ``inbound``."""
    state = _state(world)
    if state is None or not state.convoys:
        return
    for c in state.convoys:
        if c.status == "returning":
            continue
        if not 0 <= c.dest < len(inbound) or not math.isfinite(c.cargo) or c.cargo <= 0:
            raise ValueError("invalid grain convoy inbound cargo")
        inbound[c.dest] += c.cargo
    if not all(math.isfinite(v) for v in inbound):
        raise ValueError("grain convoy inbound commitments overflow")


def inbound_by_destination(world) -> list[float]:
    """Cargo still heading for each granary (zeros without convoys)."""
    totals = [0.0] * len(world.regions)
    add_convoy_inbound(world, totals)
    return totals


# ---------------------------------------------------------------------------
# Movement (Phase 10, before the granary pass)
# ---------------------------------------------------------------------------

def _start_frame(state, turn: int) -> None:
    state.frame = []
    state.frame_turn = turn


def _transition(world, c, operation: str, *, at: int, **fields) -> ConvoyTransition:
    status = c.status if operation in ("dispatched", "advanced", "waited", "turned_back") else operation
    return ConvoyTransition(
        id=convoy_id(c.dispatch_turn, c.convoy), convoy=c.convoy, turn=world.turn,
        operation=operation, buyer=c.buyer, buyer_name=c.buyer_name, source=c.source, dest=c.dest,
        at=at, at_name=world.regions[at].name, route=list(c.route), leg=c.leg, progress=c.progress,
        status=status, cargo=c.cargo, escorted=c.escorted, **fields)


def _event(world, c, kind: str, line: str, *, region: int, importance: int, civs=()):
    from chronicler.models import Event
    return Event(turn=world.turn, event_type=f"grain_convoy_{kind}", actors=[c.buyer_name],
                 civs=[c.seller_name, *civs], region=world.regions[region].name,
                 importance=importance, description=line)


def _draws(world, c, forward: bool) -> tuple[float, float]:
    from chronicler.utils import stable_hash_int
    rng = random.Random(stable_hash_int(RNG_NAMESPACE, world.seed, c.convoy, c.dispatch_turn,
                                        world.turn, c.leg, "f" if forward else "r"))
    return rng.random(), rng.random()


def _pick(parts: tuple, total: float, u: float):
    """The threat component the draw ``u < total`` falls in (proportional slices)."""
    weight = math.fsum(p for p, *_ in parts)
    edge = 0.0
    for part in parts:
        edge += total * part[0] / weight
        if u < edge:
            return part
    return parts[-1]


class _Move:
    """One convoy's outcome this turn, computed on a copy before any write."""

    def __init__(self, convoy):
        self.c = convoy
        self.transition = None
        self.events: list = []
        self.counters: dict[str, float] = {}
        self.finished = False
        self.granary: float = 0.0          # arrived cargo into ``c.dest``'s granary
        self.market: tuple[int, float] | None = None   # (region, cargo) into a market

    def bump(self, key: str, value: float = 1.0) -> None:
        self.counters[key] = self.counters.get(key, 0.0) + value


def _finish(world, facts, move: _Move, outcome: str, at: int, *, sink: str | None = None,
            sink_region: int | None = None, captor: int | None = None, **fields) -> None:
    c = move.c
    cargo = c.cargo
    move.finished = True
    keeper = None
    if outcome == "arrived":
        keeper = world.grain_reserves.granaries[c.dest].owner
        move.granary = cargo
        move.bump("arrived")
        move.bump("delivered", cargo)
        if keeper == -1:
            move.bump("unguarded_delivery", cargo)
        elif keeper != c.buyer:
            move.bump("captured_delivery", cargo)
        custody = world.civilizations[keeper].name if keeper >= 0 else "no ruler"
        line = (f"Grain convoy {convoy_id(c.dispatch_turn, c.convoy)} delivers {cargo:.1f} grain to the granary "
                f"in {c.dest_name}, kept by {custody}; {c.buyer_name} paid at dispatch.")
        move.events.append(_event(world, c, "arrived", line, region=c.dest, importance=2))
    elif outcome == "captured":
        move.market = (sink_region, cargo)
        move.bump("captured")
        move.bump("captured_grain", cargo)
        captor_name = world.civilizations[captor].name
        line = (f"{captor_name} seizes the grain convoy of {c.buyer_name} near {world.regions[at].name}: "
                f"{cargo:.1f} grain goes to the market of {world.regions[sink_region].name}.")
        move.events.append(_event(world, c, "captured", line, region=at, importance=4, civs=(captor_name,)))
    elif outcome == "lost":
        move.bump("lost")
        move.bump("lost_grain", cargo)
        by = {"piracy": "pirates", "raid": "raiders"}.get(sink, "an enemy with no market to hold it")
        line = (f"The grain convoy of {c.buyer_name} is lost to {by} near {world.regions[at].name}: "
                f"{cargo:.1f} grain, paid at dispatch, is gone.")
        move.events.append(_event(world, c, "lost", line, region=at, importance=3))
    elif outcome == "returned":
        move.market = (c.source, cargo)
        sink, sink_region = "origin_market", c.source
        move.bump("returned")
        move.bump("returned_grain", cargo)
        line = (f"The grain convoy of {c.buyer_name} is back in {c.source_name}; its {cargo:.1f} grain goes "
                f"back to the market there and the price paid is not refunded.")
        move.events.append(_event(world, c, "returned", line, region=c.source, importance=3))
    elif outcome == "stranded":
        move.market = (at, cargo)
        sink, sink_region = "stranded_market", at
        move.bump("stranded")
        move.bump("stranded_grain", cargo)
        line = (f"The grain convoy of {c.buyer_name} is stranded in {world.regions[at].name}; its "
                f"{cargo:.1f} grain goes to the market there.")
        move.events.append(_event(world, c, "stranded", line, region=at, importance=3))
    if c.escorted and c.threats == 0 and outcome in ("arrived", "returned", "stranded"):
        move.bump("escort_wasted")
        move.bump("escort_wasted_paid", c.escort_fee)
    move.transition = _transition(world, c, outcome, at=at, keeper=keeper, sink=sink,
                                  sink_region=sink_region, captor=captor, **fields)


def _advance(world, facts: _Facts, c, scale: float = 1.0) -> _Move:
    move = _Move(c)
    forward = c.status != "returning"
    rerouted = False
    closure = None
    threat = threat_risk = None
    repelled = False
    a = c.route[c.leg]
    if c.progress == 0:
        b = c.route[c.leg + 1] if forward else c.route[c.leg - 1]
        closed, parts = facts.judge(a, b)
        if closed is not None and forward and c.reroutes < MAX_REROUTES:
            plans = [_plan(world, facts, path, escorted=c.escorted, first=False)
                     for path in _routes(facts, a, c.dest)]
            plans = [p for p in plans if c.leg + len(p[3]) <= MAX_ROUTE_NODES]
            if plans:
                best = min(plans, key=_safest_key if c.escorted else _exposed_key)
                c.route = c.route[:c.leg + 1] + best[3][1:]
                c.reroutes += 1
                move.bump("reroutes")
                rerouted, closure = True, closed
                b = c.route[c.leg + 1]
                closed, parts = facts.judge(a, b)
        if closed is not None:
            closure = closed
            if world.turn - c.dispatch_turn > MAX_AGE:
                _finish(world, facts, move, "stranded", a, closure=closure, rerouted=rerouted)
                return move
            if c.waits < MAX_WAIT:
                c.waits += 1
                if forward:
                    c.status = "waiting"
                move.bump("waits")
                move.transition = _transition(world, c, "waited", at=a, closure=closure, rerouted=rerouted)
                return move
            if not forward:
                _finish(world, facts, move, "stranded", a, closure=closure, rerouted=rerouted)
                return move
            c.waits = 0
            c.status = "returning"
            move.bump("turned_back")
            if c.leg == 0:
                _finish(world, facts, move, "returned", a, closure=closure, rerouted=rerouted)
                return move
            line = (f"The grain convoy of {c.buyer_name} turns back at {world.regions[a].name}: the road to "
                    f"{world.regions[b].name} is closed ({closure.replace('_', ' ')}).")
            move.events.append(_event(world, c, "turned_back", line, region=a, importance=2))
            move.transition = _transition(world, c, "turned_back", at=a, closure=closure, rerouted=rerouted)
            return move
        # Open edge: one threat draw as the convoy takes it. The ablation
        # scale applies to the drawn chance only, never to route choice.
        risk = scale * _combine(p for p, *_ in parts)
        u, v = _draws(world, c, forward)
        if parts and u < risk:
            p, kind, captor, near = _pick(parts, risk, u)
            threat, threat_risk = kind, risk
            c.threats += 1
            move.bump("threats")
            if c.escorted and v < ESCORT_PROTECTION:
                c.repelled += 1
                move.bump("repelled")
                repelled = True
            elif captor >= 0:
                region = _captor_market(world, facts, captor,
                                        [near, b, a, *facts.adj[b], *facts.adj[a]])
                if region is None:
                    _finish(world, facts, move, "lost", a, sink="captor_without_market", captor=captor,
                            threat=threat, threat_risk=threat_risk, rerouted=rerouted)
                else:
                    _finish(world, facts, move, "captured", a, sink="captor_market", sink_region=region,
                            captor=captor, threat=threat, threat_risk=threat_risk, rerouted=rerouted)
                return move
            else:
                _finish(world, facts, move, "lost", a, sink="piracy" if kind == "sea" else "raid",
                        threat=threat, threat_risk=threat_risk, rerouted=rerouted)
                return move
        c.waits = 0
        if forward:
            c.status = "en_route"
        c.leg_turns = _leg_turns(world, a, b) + (
            ESCORT_MUSTER_TURNS if c.escorted and forward and c.leg == 0 else 0)
        c.progress = 1
    else:
        b = c.route[c.leg + 1] if forward else c.route[c.leg - 1]
        c.progress += 1
    if c.progress < c.leg_turns:
        move.transition = _transition(world, c, "advanced", at=a, rerouted=rerouted, closure=closure,
                                      threat=threat, threat_risk=threat_risk, repelled=repelled)
        return move
    # The edge is done: entering b, held now by an enemy of the buyer, ends in capture.
    if facts.hostile_holder(b):
        holder = _holder(world.regions[b])
        captor = facts.civ_index.get(holder, facts.civ_index.get(world.regions[b].controller, -1))
        c.threats += 1
        move.bump("threats")
        if captor >= 0:
            _finish(world, facts, move, "captured", b, sink="captor_market", sink_region=b, captor=captor,
                    threat="hostile_holder", rerouted=rerouted, closure=closure)
        else:
            _finish(world, facts, move, "lost", b, sink="raid", threat="hostile_holder",
                    rerouted=rerouted, closure=closure)
        return move
    c.leg += 1 if forward else -1
    c.progress = 0
    c.leg_turns = 0
    move.bump("legs")
    if forward and c.leg == len(c.route) - 1:
        _finish(world, facts, move, "arrived", b, rerouted=rerouted, closure=closure, threat=threat,
                threat_risk=threat_risk, repelled=repelled)
    elif not forward and c.leg == 0:
        _finish(world, facts, move, "returned", b, rerouted=rerouted, closure=closure, threat=threat,
                threat_risk=threat_risk, repelled=repelled)
    else:
        move.transition = _transition(world, c, "advanced", at=b, rerouted=rerouted, closure=closure,
                                      threat=threat, threat_risk=threat_risk, repelled=repelled)
    return move


def phase10_before_reserves(world, acc=None, economy_result=None, agent_bridge=None) -> list:
    """Advance every convoy at most one edge, by this turn's facts; deliver arrivals."""
    state = _state(world)
    if state is None:
        return []
    validate_convoys(world)
    scale = threat_scale(world)
    if not _ready(world, economy_result) or state.moved_turn == world.turn:
        return []
    from chronicler import grain_reserves as G
    from chronicler.grain_reserves_state import CONVOY_ARRIVED, ReserveFlow
    if not state.convoys:
        _start_frame(state, world.turn)
        state.moved_turn = world.turn
        return []
    out = _out_edges(G._route_graph(world))
    facts: dict[int, _Facts] = {}
    moves = []
    for convoy in state.convoys:
        buyer_facts = facts.get(convoy.buyer)
        if buyer_facts is None:
            buyer_facts = facts[convoy.buyer] = _Facts(world, convoy.buyer, out)
        moves.append(_advance(world, buyer_facts, convoy.model_copy(deep=True), scale))
    # Validate every write before making any.
    reserves = world.grain_reserves
    granary_after: dict[int, float] = {}
    market_after: dict[int, float] = {}
    for move in moves:
        if move.granary:
            granary = reserves.granaries[move.c.dest]
            granary_after[move.c.dest] = granary_after.get(move.c.dest, granary.grain) + move.granary
        if move.market is not None:
            rid, cargo = move.market
            goods = world.regions[rid].stockpile.goods
            market_after[rid] = market_after.get(rid, goods.get(G.GRAIN, 0.0)) + cargo
    counters = dict(state.counters)
    for move in moves:
        for key, value in move.counters.items():
            counters[key] += value
    if not all(math.isfinite(v) and v >= 0 for v in (*granary_after.values(), *market_after.values(),
                                                    *counters.values())):
        raise ValueError("grain convoy movement overflows")
    flows = G._flows(world, reserves)
    for move in moves:
        if move.granary:
            c = move.c
            flows.append(ReserveFlow(kind=CONVOY_ARRIVED, region=c.dest, amount=move.granary,
                                     source=c.source, seller=c.seller, buyer=c.buyer))
    for rid, grain in granary_after.items():
        reserves.granaries[rid].grain = grain
    for rid, grain in market_after.items():
        world.regions[rid].stockpile.goods[G.GRAIN] = grain
    state.convoys[:] = [move.c for move in moves if not move.finished]
    state.counters.clear()
    state.counters.update(counters)
    _start_frame(state, world.turn)
    state.frame.extend(move.transition for move in moves)
    state.moved_turn = world.turn
    _check_closure(world, state)
    return [event for move in moves for event in move.events]


# ---------------------------------------------------------------------------
# Dispatch (Phase 10, after the granary pass)
# ---------------------------------------------------------------------------

def _surplus(world, index, demand, commitments) -> list[float]:
    """The granary pass's sellable surplus, recomputed from the markets now."""
    from chronicler.economy import FOOD_GOODS
    from chronicler.grain_reserves import GRAIN, KEEP_TURNS
    out = []
    for rid, region in enumerate(world.regions):
        if region.controller not in index or demand[rid] <= 0 or region.population <= 0:
            out.append(0.0)
            continue
        held = commitments.get(region.name, {})
        goods = region.stockpile.goods
        free = {g: max(0.0, goods.get(g, 0.0) - held.get(g, 0.0)) for g in sorted(FOOD_GOODS)}
        out.append(max(0.0, min(free[GRAIN], math.fsum(free.values()) - KEEP_TURNS * demand[rid])))
    return out


def _dispatch(world, state, acc, *, buyer, seller, source, dest, sent, net, cost, fee,
              escorted, plan, exposed, safest):
    """Commit one paid convoy atomically (payment, escort sink, market debit, record)."""
    from chronicler.finance import _capture_exact_transfer, transfer
    from chronicler.grain_reserves import GRAIN, _transit_loss
    regions, civs = world.regions, world.civilizations
    goods = regions[source].stockpile.goods
    available = goods.get(GRAIN, 0.0)
    if (buyer == seller or source == dest or regions[source].controller != civs[seller].name
            or regions[dest].controller != civs[buyer].name
            or world.grain_reserves.granaries[dest].owner != buyer
            or type(cost) is not int or cost <= 0 or type(fee) is not int or fee < 0
            or (fee > 0) != escorted
            or not all(math.isfinite(v) and v > 0 for v in (sent, net))
            or sent > available or abs(net - sent * (1.0 - _transit_loss())) > 1e-9 * max(1.0, sent)):
        raise ValueError("grain convoy dispatch identities/cargo/payment are invalid")
    route = list(plan[3])
    record = GrainConvoy(
        convoy=state.next_convoy, source=source, source_name=regions[source].name, dest=dest,
        dest_name=regions[dest].name, buyer=buyer, buyer_name=civs[buyer].name, seller=seller,
        seller_name=civs[seller].name, dispatch_turn=world.turn, policy=state.route_policy, route=route,
        leg=0, progress=0, leg_turns=0, status="en_route", escorted=escorted, escort_fee=fee,
        sent=float(sent), net=float(net), loss=float(sent - net), cargo=float(net), paid=cost,
        waits=0, reroutes=0, threats=0, repelled=0,
        exposed_route=list(exposed[3]), exposed_risk=exposed[2], exposed_turns=exposed[0],
        escorted_route=list(safest[3]), escorted_risk=safest[2], escorted_turns=safest[0])
    transition = _transition(world, record, "dispatched", at=source, paid=cost, escort_fee=fee)
    names = " - ".join(regions[r].name for r in route)
    line = (f"{record.buyer_name} sends a grain convoy of {net:.1f} grain from {record.source_name} to "
            f"{record.dest_name} by {names} ({cost} treasury to {record.seller_name}"
            + (f", {fee} for an escort" if escorted else ", no escort")
            + f"); it is expected in {plan[0]} turns.")
    event = _event(world, record, "dispatched", line, region=dest, importance=2)
    reserves = world.grain_reserves
    payment = _capture_exact_transfer(world, buyer, seller, cost, acc=acc)
    old = (GRAIN in goods, available, len(state.convoys), len(state.frame), state.next_convoy,
           dict(state.counters), dict(reserves.counters))
    try:
        paid = transfer(world, buyer, seller, cost, acc=acc)
        if paid != cost:
            raise ValueError("grain convoy payment was partial")
        payment.check_specie()
        if fee:
            civ = civs[buyer]
            if acc is not None:
                acc.add(buyer, civ, "treasury", -fee, "keep")
            else:
                civ.treasury -= fee
        goods[GRAIN] = available - sent
        state.convoys.append(record)
        state.frame.append(transition)
        state.next_convoy += 1
        for key, value in (("dispatched", 1), ("sent", sent), ("committed_net", net),
                           ("transit_loss", sent - net), ("paid", cost), ("escorted", int(escorted)),
                           ("escort_paid", fee)):
            state.counters[key] += value
        for key, value in (("sent", sent), ("transit_loss", sent - net), ("paid_foreign", cost)):
            reserves.counters[key] += value
        if not all(math.isfinite(v) for v in (*state.counters.values(), *reserves.counters.values())):
            raise ValueError("grain convoy dispatch counters overflow")
    except Exception:
        had, grain, convoys_len, frame_len, next_convoy, counters, reserve_counters = old
        payment.restore()
        if had:
            goods[GRAIN] = grain
        else:
            goods.pop(GRAIN, None)
        del state.convoys[convoys_len:]
        del state.frame[frame_len:]
        state.next_convoy = next_convoy
        state.counters.clear()
        state.counters.update(counters)
        reserves.counters.clear()
        reserves.counters.update(reserve_counters)
        raise
    return event


def phase10(world, acc=None, economy_result=None, agent_bridge=None) -> list:
    """After the granary pass: buy toward the remaining deficits from foreign
    markets two or three steps away (the ones the shipment pass skips)."""
    state = _state(world)
    if state is None:
        return []
    validate_convoys(world)
    if not _ready(world, economy_result) or state.dispatch_turn == world.turn:
        return []
    if state.frame_turn != world.turn:
        _start_frame(state, world.turn)
    state.dispatch_turn = world.turn
    reserves = world.grain_reserves
    shipments = reserves.shipments
    procurement = getattr(economy_result, "food_procurement_budget", None)
    if (not state.enabled or not shipments.accept_orders or shipments.last_arrivals_turn != world.turn
            or not procurement):
        return []
    from chronicler import grain_reserves as G
    from chronicler.finance import _projections
    from chronicler.public_grain_shipments import inbound_by_destination as shipment_inbound
    from chronicler.tuning import K_GRAIN_RESERVES_SHORTFALL_PRIORITY, get_override

    regions, civs = world.regions, world.civilizations
    index = G._civ_index(world)
    demand = [G._demand(economy_result, r.name) for r in regions]
    price = [G._food_price(economy_result, r.name) for r in regions]
    commitments: dict = {}
    if agent_bridge is not None and world.agent_mode == "hybrid":
        from chronicler.mutual_aid import read_stockpile_commitments
        commitments = read_stockpile_commitments(world, agent_bridge._sim)
    surplus = _surplus(world, index, demand, commitments)
    graph = G._route_graph(world)
    out = _out_edges(graph)
    inbound = shipment_inbound(world)
    add_convoy_inbound(world, inbound)
    projected = _projections(world, acc)
    budget = [max(0, min(int(procurement.get(ci, (0, 0))[1]), projected[ci])) if civs[ci].regions else 0
              for ci in range(len(civs))]
    spent = [0] * len(civs)
    keep = 1.0 - G._transit_loss()
    shortfall_priority = bool(get_override(world, K_GRAIN_RESERVES_SHORTFALL_PRIORITY, 0.0))
    granaries = reserves.granaries
    events: list = []
    for ci, civ in enumerate(civs):
        targets = [rid for rid, (r, g) in enumerate(zip(regions, granaries))
                   if g.owner == ci and r.controller == civ.name and demand[rid] > 0
                   and g.target - g.grain - inbound[rid] > G.EPS]
        if shortfall_priority:
            targets.sort(key=lambda rid: G._shortfall_order(
                granaries[rid], economy_result.food_sufficiency.get(regions[rid].name), rid))
        else:
            targets.sort(key=lambda rid: (granaries[rid].grain / granaries[rid].target,
                                          economy_result.food_sufficiency.get(regions[rid].name, 0.0), rid))
        facts = None
        for rid in targets:
            granary = granaries[rid]
            hops = G._realm_hops(world, graph, rid, civ.name)
            steps: dict[int, int] = {}
            for own, h in hops.items():
                if h >= G.MAX_HOPS:
                    continue
                for src in graph.get(own, ()):
                    r = regions[src]
                    if r.controller is None or r.controller == civ.name or r.controller not in index:
                        continue
                    if src not in steps or h + 1 < steps[src]:
                        steps[src] = h + 1
            sources = sorted((s for s in steps if steps[s] >= 2 and surplus[s] > G.EPS and price[s] > 0),
                             key=lambda s: (price[s], steps[s], s))
            if not sources:
                continue
            state.counters["eligible"] += 1
            if budget[ci] <= 0:
                state.counters["no_budget"] += 1
                continue
            if facts is None:
                facts = _Facts(world, ci, out)
            for src in sources:
                deficit = granary.target - granary.grain - inbound[rid]
                if budget[ci] <= 0 or deficit <= G.EPS:
                    break
                p = price[src]
                if surplus[src] <= G.EPS:
                    continue
                paths = _routes(facts, src, rid)
                if not paths:
                    state.counters["no_route"] += 1
                    continue
                exposed = min((_plan(world, facts, path, escorted=False, first=True) for path in paths),
                              key=_exposed_key)
                safest = min((_plan(world, facts, path, escorted=True, first=True) for path in paths),
                             key=_safest_key)
                fee = ESCORT_FEE_PER_LEG * safest[1]
                most = int(math.floor(min(surplus[src], deficit / keep) * p + G.EPS))
                if state.route_policy == "cheapest":
                    escorted = False
                elif state.route_policy == "safest":
                    escorted = True
                else:
                    value = min(budget[ci], most)
                    escorted = fee + safest[2] * (1.0 - ESCORT_PROTECTION) * value < exposed[2] * value
                cost = min(budget[ci] - (fee if escorted else 0), most)
                if escorted and cost < 1 and state.route_policy == "adaptive":
                    escorted = False
                    cost = min(budget[ci], most)
                if cost < 1:
                    state.counters["unaffordable"] += 1
                    continue
                if (len(state.convoys) >= MAX_ACTIVE
                        or sum(c.dest == rid for c in state.convoys) >= MAX_PER_DEST):
                    state.counters["capacity_refusals"] += 1
                    break
                if state.next_convoy >= MAX_ID:
                    state.counters["identity_refusals"] += 1
                    break
                sent = min(surplus[src], cost / p)
                net = sent * keep
                fee_paid = fee if escorted else 0
                event = _dispatch(world, state, acc, buyer=ci, seller=index[regions[src].controller],
                                  source=src, dest=rid, sent=sent, net=net, cost=cost, fee=fee_paid,
                                  escorted=escorted, plan=safest if escorted else exposed,
                                  exposed=exposed, safest=safest)
                events.append(event)
                surplus[src] -= sent
                budget[ci] -= cost + fee_paid
                spent[ci] += cost + fee_paid
                inbound[rid] += net
    # The reported procurement budget stays the truth after convoy spending.
    for ci, amount in enumerate(spent):
        if amount and ci in procurement:
            initial, remaining = procurement[ci]
            procurement[ci] = (initial, remaining - amount)
    _check_closure(world, state)
    return events


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """The completed turn's convoys and transitions, copied (bounded, dated).

    ``transitions`` is None (unknown) when no pass recorded the source turn;
    an empty list means a pass ran and nothing happened.
    """
    state = _state(world)
    if state is None:
        return {}
    source = world.turn - 1
    names = [r.name for r in world.regions]

    def view(c) -> dict:
        row = c.model_dump()
        row["id"] = convoy_id(c.dispatch_turn, c.convoy)
        row["route_names"] = [names[r] if 0 <= r < len(names) else None for r in c.route]
        return row

    return {
        "schema_version": 1,
        "source_turn": source,
        "enabled": state.enabled,
        "route_policy": state.route_policy,
        "moved": state.moved_turn == source,
        "dispatch_ran": state.dispatch_turn == source,
        "active_count": len(state.convoys),
        "in_transit_cargo": math.fsum(c.cargo for c in state.convoys if c.status != "returning"),
        "returning_cargo": math.fsum(c.cargo for c in state.convoys if c.status == "returning"),
        "active": [view(c) for c in state.convoys[:MAX_ACTIVE]],
        "transitions": ([row.model_dump() for row in state.frame]
                        if state.frame_turn == source else None),
        "counters": dict(state.counters),
    }
