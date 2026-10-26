"""Contact and trade-flow ledger: one shared "who is in contact with whom" substrate.

Every turn the ledger folds the real movements of goods, people, soldiers and
pilgrims into an exponentially decayed, sparse, directed region x region
matrix with four channels:

* ``trade``    goods units delivered by agent merchants (native delivery
               records), or, with ``--agents off``, a route proxy along the
               boundary pairs of the goods trade routes; plus a small bump per
               successful TRADE action;
* ``people``   agent migrations (origin region -> destination region) and
               held hostages (origin capital -> captor capital);
* ``soldiers`` campaign armies in the field (home region -> current region);
* ``pilgrims`` great persons on pilgrimage (current region -> shrine region).

Civilization-pair aggregates are taken once per update with the region
controllers of that moment and saved with the matrix, so a save/load round
trip continues bit-identically:

* ``F_ab``  decayed goods value crossing a <-> b (``civ_flow``), which now
            defines ``Relationship.trade_volume`` (rounded, kept for
            compatibility);
* ``D_ab``  dependence of a on b: ``F_ab`` over a's recorded commerce
            (internal plus external goods flow, floored), in [0, 1].

The world field ``WorldState.contact_ledger`` doubles as the feature switch:
``None`` means off, in which case nothing in this module runs and every output
is identical to the pre-ledger simulation. All updates are O(edges); no
region x region dense structure is ever built.

Consumers (each guarded by ``ledger_enabled``): movement spread, the merchant
great-person trade-partner count, trade-partner disposition warmth, embargo and
war-declaration trade shocks, and pandemic spread. See
``docs/integration/contact-ledger.md``.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Iterable

from pydantic import BaseModel, Field, PrivateAttr

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import WorldState

# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE] values are documented in docs/integration/contact-ledger.md)
# ---------------------------------------------------------------------------

#: Default for worlds newly created by the CLI/batch/live entry points
#: (``--no-contact-ledger`` opts out; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = True

CHANNELS: tuple[str, ...] = ("trade", "people", "soldiers", "pilgrims")
TRADE, PEOPLE, SOLDIERS, PILGRIMS = range(4)
_CHANNEL_INDEX = {name: i for i, name in enumerate(CHANNELS)}

#: Per-turn retention per channel (value_t = value_{t-1} * decay + inflow_t).
#: 0.9 is a half-life of about 6.6 turns and a steady state of 10x the flow.
DECAY: tuple[float, ...] = (0.9, 0.9, 0.8, 0.9)
#: Edges whose channels all fall below this are dropped (keeps the matrix sparse).
PRUNE_EPSILON = 0.01
#: Stored values are rounded to this many decimals (compact, exact JSON).
QUANTUM_DIGITS = 6

#: Goods value recorded on the capital-to-capital edge per successful TRADE action.
TRADE_ACTION_VALUE = 1.0
#: ``--agents off`` route proxy: goods per boundary pair per turn, times
#: ``0.5 + (economy_a + economy_b) / 200`` (both civs' economy stats).
OFF_ROUTE_FLOW = 0.5
#: ``--agents off`` internal commerce proxy per intra-civ adjacency pair (dependence denominator only).
OFF_INTERNAL_FLOW = 0.5
#: Floor on a civ's recorded commerce in the dependence denominator.
COMMERCE_FLOOR = 5.0

#: Channel weights for the generic contact intensity used by idea/plague consumers.
CONTACT_WEIGHTS: tuple[float, ...] = (1.0, 1.0, 0.25, 2.0)

#: A civ pair counts as trade partners at this decayed goods flow.
TRADE_PARTNER_MIN_FLOW = 1.0
#: Merchant great person: living partners (F >= TRADE_PARTNER_MIN_FLOW) a civ
#: needs for a "high trade route turn". The legacy rule needs 4 relationships
#: that ever traded (dead civs included); live partners are far scarcer.
MERCHANT_HUB_PARTNERS = 3

# Movement spread: adoption percent per unit of civ contact (times compatibility/100),
# capped near the legacy per-pair magnitude (trade_volume percent rarely exceeded 20).
# Faster spread revives the dormant schism/co-adoption drift strongly enough to
# churn federations (see docs/integration/contact-ledger.md).
MOVEMENT_PCT_PER_CONTACT = 0.5
MOVEMENT_MAX_PCT = 20.0

# Disposition warmth for trade partners (accumulates into disposition_drift).
WARMTH_PER_TURN = 1
WARMTH_DEPENDENCE_BONUS = 1  # extra drift when either side's dependence >= WARMTH_DEPENDENCE_MIN
WARMTH_DEPENDENCE_MIN = 0.25
WARMTH_DRIFT_THRESHOLD = 10  # same threshold as apply_value_drift

# Trade shocks: stability lost per unit of dependence on the counterparty.
EMBARGO_DEPENDENCE_STABILITY = 10
WAR_DEPENDENCE_STABILITY = 8

# Pandemic spread: probability 1 - exp(-contact / scale) per exposed region pair.
PANDEMIC_CONTACT_SCALE = 5.0


# ---------------------------------------------------------------------------
# Persisted state
# ---------------------------------------------------------------------------

EdgeRow = tuple[int, int, float, float, float, float]
PairRow = tuple[str, str, float, float, float, float]


class _LedgerCache:
    """Derived lookups over a ledger's rows. Never serialized; a copy starts
    empty, and a cache (present, absent or stale) never makes two ledgers or
    worlds compare unequal (Pydantic compares private attributes)."""

    __slots__ = ("edge_map", "pair_map", "neighbors")

    def __init__(self) -> None:
        self.edge_map = None
        self.pair_map = None
        self.neighbors = None

    def __copy__(self) -> "_LedgerCache":
        return _LedgerCache()

    def __deepcopy__(self, memo: dict) -> "_LedgerCache":
        return _LedgerCache()

    def __reduce__(self):
        return (_LedgerCache, ())

    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, _LedgerCache)

    __hash__ = None  # type: ignore[assignment]


class ContactLedgerState(BaseModel):
    """Sparse decayed contact matrix plus the civ-pair aggregates of its last update.

    ``edges`` rows are ``(src_region_idx, dst_region_idx, trade, people,
    soldiers, pilgrims)`` sorted by ``(src, dst)``; ``pairs`` rows are
    ``(civ_a, civ_b, trade, people, soldiers, pilgrims)`` with ``civ_a <
    civ_b`` (undirected); ``commerce`` maps a civ to its recorded goods flow
    (internal plus external). ``last_inflow`` holds the four channel totals
    added by the last update.
    """

    last_update_turn: int = -1
    edges: list[EdgeRow] = Field(default_factory=list)
    pairs: list[PairRow] = Field(default_factory=list)
    commerce: dict[str, float] = Field(default_factory=dict)
    last_inflow: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    # Derived lookups (never serialized; rebuilt lazily after load/copy).
    _cache: _LedgerCache = PrivateAttr(default_factory=_LedgerCache)

    def invalidate(self) -> None:
        self._cache = _LedgerCache()

    def edge_map(self) -> dict[tuple[int, int], tuple[float, float, float, float]]:
        cache = self._cache
        if cache.edge_map is None:
            cache.edge_map = {(r[0], r[1]): tuple(r[2:6]) for r in self.edges}
        return cache.edge_map

    def pair_map(self) -> dict[tuple[str, str], tuple[float, float, float, float]]:
        cache = self._cache
        if cache.pair_map is None:
            cache.pair_map = {(r[0], r[1]): tuple(r[2:6]) for r in self.pairs}
        return cache.pair_map

    def neighbors(self) -> dict[int, list[int]]:
        """Region index -> sorted indices it has an edge with (either direction)."""
        cache = self._cache
        if cache.neighbors is None:
            nb: dict[int, set[int]] = {}
            for src, dst, *_ in self.edges:
                nb.setdefault(src, set()).add(dst)
                nb.setdefault(dst, set()).add(src)
            cache.neighbors = {k: sorted(v) for k, v in nb.items()}
        return cache.neighbors


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def ledger_enabled(world) -> bool:
    """True only for a real ledger (mocks and ``None`` read as off)."""
    return isinstance(getattr(world, "contact_ledger", None), ContactLedgerState)


def set_contact_ledger_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (creating an empty ledger) or disable the ledger on a world."""
    if enabled:
        if world.contact_ledger is None:
            world.contact_ledger = ContactLedgerState()
    else:
        world.contact_ledger = None


# ---------------------------------------------------------------------------
# Transient per-turn inputs (cleared by update_contact_ledger)
# ---------------------------------------------------------------------------

def _pending(world) -> list:
    pending = getattr(world, "_contact_pending", None)
    if pending is None:
        pending = []
        world._contact_pending = pending
    return pending


def _region_index(world) -> dict[str, int]:
    return {r.name: i for i, r in enumerate(world.regions)}


def _civ_anchor_region(world, civ, index: dict[str, int]) -> int | None:
    """Capital region index of a civ, else its first region, else None."""
    if civ is None:
        return None
    if civ.capital_region and civ.capital_region in index and civ.capital_region in civ.regions:
        return index[civ.capital_region]
    for name in civ.regions:
        if name in index:
            return index[name]
    return None


def record_trade_action(world, civ_a: str, civ_b: str) -> None:
    """A successful TRADE action: a small goods bump on the capital-to-capital edge."""
    if not ledger_enabled(world):
        return
    index = _region_index(world)
    civ_map = world.civ_map
    src = _civ_anchor_region(world, civ_map.get(civ_a), index)
    dst = _civ_anchor_region(world, civ_map.get(civ_b), index)
    if src is None or dst is None or src == dst:
        return
    _pending(world).append((src, dst, TRADE, TRADE_ACTION_VALUE))


def observe_phase2(world, routes: list[tuple[str, str]], agent_bridge=None) -> None:
    """Phase 2 goods inputs, read before the economy tick consumes them.

    Agent modes: the native merchant arrival records about to be consumed by
    ``tick_economy`` (each completed delivery is seen exactly once). ``--agents
    off``: the route proxy along goods-route boundary pairs, plus internal
    commerce along intra-civ adjacencies (dependence denominator).
    """
    if not ledger_enabled(world):
        return
    pending = _pending(world)
    n_regions = len(world.regions)
    if agent_bridge is not None:
        sim = getattr(agent_bridge, "_sim", None)
        if sim is None or not hasattr(sim, "get_pending_arrivals"):
            return
        batch = sim.get_pending_arrivals()
        if batch.num_rows == 0:
            return
        cols = [batch.column(c).to_pylist() for c in ("source_region", "dest_region", "qty")]
        for src, dst, qty in zip(*cols):
            if 0 <= src < n_regions and 0 <= dst < n_regions and src != dst and qty > 0:
                pending.append((int(src), int(dst), TRADE, float(qty)))
        return

    from chronicler.maritime import ledger_trade_adjuster
    adjust = ledger_trade_adjuster(world)  # None unless --maritime
    for src, dst, value in off_mode_trade_rows(world, routes):
        if adjust is not None:
            # Maritime: blockaded sea lanes carry nothing; pirates skim the rest.
            value = adjust(src, dst, value)
            if value <= 0:
                continue
        pending.append((src, dst, TRADE, value))


def off_mode_trade_rows(world, routes: list[tuple[str, str]]) -> list[tuple[int, int, float]]:
    """``--agents off`` goods proxy rows ``(src_idx, dst_idx, value)``, in order:
    each goods trade route's boundary pairs (both directions), then internal
    commerce along intra-civ adjacencies. Pure read; also used by maritime."""
    from chronicler.economy import decompose_trade_routes, filter_goods_trade_routes
    rows: list[tuple[int, int, float]] = []
    index = _region_index(world)
    region_map = world.region_map
    civ_map = world.civ_map
    for civ_a, civ_b in filter_goods_trade_routes(world, routes):
        a = civ_map.get(civ_a)
        b = civ_map.get(civ_b)
        if a is None or b is None:
            continue
        value = OFF_ROUTE_FLOW * (0.5 + (a.economy + b.economy) / 200.0)
        if value <= 0:
            continue
        a_regions = set(a.regions)
        b_regions = set(b.regions)
        for src_set, dst_set in ((a_regions, b_regions), (b_regions, a_regions)):
            for src, dst in sorted(decompose_trade_routes(src_set, dst_set, region_map)):
                rows.append((index[src], index[dst], value))
    for i, region in enumerate(world.regions):
        if region.controller is None:
            continue
        for adj in region.adjacencies:
            j = index.get(adj)
            if j is not None and j != i and world.regions[j].controller == region.controller:
                rows.append((i, j, OFF_INTERNAL_FLOW))
    return rows


def _end_of_turn_inputs(world, index: dict[str, int]) -> list[tuple[int, int, int, float]]:
    """Movements read from current state at the end of the turn."""
    rows: list[tuple[int, int, int, float]] = []
    n_regions = len(world.regions)
    # Agent migrations this turn (hybrid and shadow keep agent_events_raw).
    if world.agent_events_raw:
        from chronicler.history_index import history_index
        for e in history_index(world).agent_migrations_for_turn(world, world.turn):
            src, dst = e.region, e.target_region
            if 0 <= src < n_regions and 0 <= dst < n_regions and src != dst:
                rows.append((int(src), int(dst), PEOPLE, 1.0))
    civ_map = world.civ_map
    # Campaign armies away from home.
    for army in world.war_state.armies:
        if army.soldiers <= 0:
            continue
        src = index.get(army.home_region)
        dst = index.get(army.region)
        if src is not None and dst is not None and src != dst:
            rows.append((src, dst, SOLDIERS, float(army.soldiers)))
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if not gp.active:
                continue
            # Pilgrims on the road to their shrine.
            if gp.pilgrimage_destination is not None and gp.pilgrimage_return_turn is not None:
                src = index.get(gp.region) if gp.region else None
                if src is None:
                    src = _civ_anchor_region(world, civ, index)
                dst = index.get(gp.pilgrimage_destination)
                if src is not None and dst is not None and src != dst:
                    rows.append((src, dst, PILGRIMS, 1.0))
            # Hostages tie their home court to the captor's.
            if gp.is_hostage and gp.origin_civilization != civ.name:
                src = _civ_anchor_region(world, civ_map.get(gp.origin_civilization), index)
                dst = _civ_anchor_region(world, civ, index)
                if src is not None and dst is not None and src != dst:
                    rows.append((src, dst, PEOPLE, 1.0))
    return rows


# ---------------------------------------------------------------------------
# Per-turn update
# ---------------------------------------------------------------------------

def _q(value: float) -> float:
    return round(value, QUANTUM_DIGITS)


def update_contact_ledger(world: "WorldState") -> None:
    """Decay every edge, fold this turn's flows in, and refresh civ aggregates.

    Called once per turn after all phases. O(edges + inputs + civ pairs).
    Clears the transient pending inputs before returning.
    """
    ledger = world.contact_ledger
    pending = getattr(world, "_contact_pending", None) or []
    world._contact_pending = None  # same as a freshly loaded world
    if ledger is None:
        return
    index = _region_index(world)
    inputs = list(pending)
    inputs.extend(_end_of_turn_inputs(world, index))

    edges: dict[tuple[int, int], list[float]] = {}
    for row in ledger.edges:
        values = [row[2 + c] * DECAY[c] for c in range(4)]
        edges[(row[0], row[1])] = values
    inflow = [0.0, 0.0, 0.0, 0.0]
    for src, dst, channel, amount in inputs:
        values = edges.get((src, dst))
        if values is None:
            values = [0.0, 0.0, 0.0, 0.0]
            edges[(src, dst)] = values
        values[channel] += amount
        inflow[channel] += amount

    kept: list[EdgeRow] = []
    for key in sorted(edges):
        values = [_q(v) for v in edges[key]]
        if max(values) < PRUNE_EPSILON:
            continue
        kept.append((key[0], key[1], values[0], values[1], values[2], values[3]))
    ledger.edges = kept
    ledger.last_inflow = [_q(v) for v in inflow]
    ledger.last_update_turn = world.turn
    _refresh_aggregates(world, ledger)
    ledger.invalidate()
    _sync_trade_volume(world, ledger)


def _refresh_aggregates(world, ledger: ContactLedgerState) -> None:
    regions = world.regions
    pairs: dict[tuple[str, str], list[float]] = {}
    commerce: dict[str, float] = {}
    for src, dst, t, p, s, g in ledger.edges:
        if src >= len(regions) or dst >= len(regions):
            continue
        ca = regions[src].controller
        cb = regions[dst].controller
        if ca is None or cb is None:
            continue
        if t:
            commerce[ca] = commerce.get(ca, 0.0) + t
            if cb != ca:
                commerce[cb] = commerce.get(cb, 0.0) + t
        if ca == cb:
            continue
        key = (ca, cb) if ca < cb else (cb, ca)
        acc = pairs.get(key)
        if acc is None:
            acc = [0.0, 0.0, 0.0, 0.0]
            pairs[key] = acc
        acc[0] += t
        acc[1] += p
        acc[2] += s
        acc[3] += g
    ledger.pairs = [
        (a, b, _q(v[0]), _q(v[1]), _q(v[2]), _q(v[3]))
        for (a, b), v in sorted(pairs.items())
    ]
    ledger.commerce = {name: _q(commerce[name]) for name in sorted(commerce)}


def _sync_trade_volume(world, ledger: ContactLedgerState) -> None:
    """``Relationship.trade_volume`` is the rounded decayed goods flow F_ab."""
    pair_map = ledger.pair_map()
    for a, inner in world.relationships.items():
        for b, rel in inner.items():
            key = (a, b) if a < b else (b, a)
            values = pair_map.get(key)
            rel.trade_volume = int(round(values[TRADE])) if values else 0


# ---------------------------------------------------------------------------
# Query API (read-only; safe from any phase)
# ---------------------------------------------------------------------------

def _channel_index(channel: str | int) -> int:
    if isinstance(channel, int):
        return channel
    return _CHANNEL_INDEX[channel]


def flow(world, a: int | str, b: int | str, channel: str | int = "trade", *, directed: bool = False) -> float:
    """Decayed region-level flow a -> b (``directed``) or a <-> b on one channel."""
    if not ledger_enabled(world):
        return 0.0
    ledger = world.contact_ledger
    if isinstance(a, str) or isinstance(b, str):
        index = _region_index(world)
        a = index.get(a, -1) if isinstance(a, str) else a
        b = index.get(b, -1) if isinstance(b, str) else b
    c = _channel_index(channel)
    edge_map = ledger.edge_map()
    total = edge_map.get((a, b), (0.0, 0.0, 0.0, 0.0))[c]
    if not directed:
        total += edge_map.get((b, a), (0.0, 0.0, 0.0, 0.0))[c]
    return total


def region_contact(world, a: int, b: int, weights: Iterable[float] = CONTACT_WEIGHTS) -> float:
    """Weighted undirected contact intensity between two regions (all channels)."""
    ledger = world.contact_ledger
    if ledger is None:
        return 0.0
    edge_map = ledger.edge_map()
    zero = (0.0, 0.0, 0.0, 0.0)
    ab = edge_map.get((a, b), zero)
    ba = edge_map.get((b, a), zero)
    return sum(w * (x + y) for w, x, y in zip(weights, ab, ba))


def region_partners(world, region_idx: int) -> list[int]:
    """Sorted region indices with any recorded contact with ``region_idx``."""
    ledger = world.contact_ledger
    if ledger is None:
        return []
    return list(ledger.neighbors().get(region_idx, ()))


def civ_flow(world, civ_a: str, civ_b: str, channel: str | int = "trade") -> float:
    """F_ab on one channel: decayed flow between the two civs' regions (undirected)."""
    ledger = world.contact_ledger
    if ledger is None or civ_a == civ_b:
        return 0.0
    key = (civ_a, civ_b) if civ_a < civ_b else (civ_b, civ_a)
    values = ledger.pair_map().get(key)
    return values[_channel_index(channel)] if values else 0.0


def civ_contact(world, civ_a: str, civ_b: str, weights: Iterable[float] = CONTACT_WEIGHTS) -> float:
    """Weighted contact intensity between two civs over all channels."""
    ledger = world.contact_ledger
    if ledger is None or civ_a == civ_b:
        return 0.0
    key = (civ_a, civ_b) if civ_a < civ_b else (civ_b, civ_a)
    values = ledger.pair_map().get(key)
    if not values:
        return 0.0
    return sum(w * v for w, v in zip(weights, values))


def dependence(world, civ_a: str, civ_b: str) -> float:
    """D_ab: share of a's recorded commerce (floored) that crosses to b, in [0, 1]."""
    ledger = world.contact_ledger
    if ledger is None:
        return 0.0
    f = civ_flow(world, civ_a, civ_b, TRADE)
    if f <= 0:
        return 0.0
    output = max(COMMERCE_FLOOR, ledger.commerce.get(civ_a, 0.0))
    return min(1.0, f / output)


def top_partners(world, civ: str, channel: str | int = "trade", n: int = 5,
                 min_flow: float = 0.0) -> list[tuple[str, float]]:
    """A civ's partners by decayed flow on one channel, largest first (ties by name)."""
    ledger = world.contact_ledger
    if ledger is None:
        return []
    c = _channel_index(channel)
    out: list[tuple[str, float]] = []
    for (a, b), values in ledger.pair_map().items():
        if civ not in (a, b):
            continue
        v = values[c]
        if v > min_flow:
            out.append((b if a == civ else a, v))
    out.sort(key=lambda item: (-item[1], item[0]))
    return out[:n]


def merchant_hub_partners(world) -> int:
    """Live trade partners a merchant hub needs: every other living civ, and
    at least MERCHANT_HUB_PARTNERS.

    2026-10 correction (docs/integration/procedural-gates.md): the fixed
    three partners were calibrated on the four-civ template world, where
    they are every other civ. In ten-civ procedural worlds three of nine was
    ordinary (75-84% of living civ-turns, against 2-8% on templates) and a
    merchant great person was born in almost every civ on every 20-turn
    cooldown. With four living civs or fewer the threshold is unchanged.
    """
    living = sum(1 for c in world.civilizations if c.regions)
    return max(MERCHANT_HUB_PARTNERS, living - 1)


def trade_partner_count(world, civ: str, min_flow: float = TRADE_PARTNER_MIN_FLOW) -> int:
    """Number of living civs with decayed goods flow >= ``min_flow`` with ``civ``."""
    civ_map = world.civ_map
    return sum(
        1 for other, _ in top_partners(world, civ, TRADE, n=len(world.civilizations), min_flow=0.0)
        if civ_flow(world, civ, other) >= min_flow
        and (o := civ_map.get(other)) is not None and o.regions
    )


# ---------------------------------------------------------------------------
# Consumers
# ---------------------------------------------------------------------------

def movement_adoption_pct(world, adopter: str, civ: str, compatibility: int) -> float | None:
    """Movement spread weight: None means no contact (skip), else a percent chance."""
    contact = civ_contact(world, adopter, civ)
    if contact <= PRUNE_EPSILON:
        return None
    return min(MOVEMENT_MAX_PCT, MOVEMENT_PCT_PER_CONTACT * contact) * compatibility / 100


def apply_trade_warmth(world) -> None:
    """Trade partners warm up: drift toward friendlier dispositions (Phase 10).

    Pairs with decayed goods flow at least ``TRADE_PARTNER_MIN_FLOW`` add
    ``WARMTH_PER_TURN`` (+``WARMTH_DEPENDENCE_BONUS`` when either side depends
    on the other for ``WARMTH_DEPENDENCE_MIN`` of its commerce) to both
    directions' ``disposition_drift``. Crossing the usual threshold upgrades
    the disposition one step; trade alone never lifts a pair above FRIENDLY.
    """
    if not ledger_enabled(world):
        return
    from chronicler.culture import upgrade_disposition
    from chronicler.models import Disposition

    order = {d: i for i, d in enumerate(Disposition)}
    cap = order[Disposition.FRIENDLY]
    civ_map = world.civ_map
    for a, b, t, *_ in world.contact_ledger.pairs:
        if t < TRADE_PARTNER_MIN_FLOW:
            continue
        ca, cb = civ_map.get(a), civ_map.get(b)
        if ca is None or cb is None or not ca.regions or not cb.regions:
            continue
        delta = WARMTH_PER_TURN
        if max(dependence(world, a, b), dependence(world, b, a)) >= WARMTH_DEPENDENCE_MIN:
            delta += WARMTH_DEPENDENCE_BONUS
        for x, y in ((a, b), (b, a)):
            rel = world.relationships.get(x, {}).get(y)
            if rel is None or order.get(rel.disposition, cap) >= cap:
                continue
            rel.disposition_drift += delta
            if rel.disposition_drift >= WARMTH_DRIFT_THRESHOLD:
                rel.disposition = upgrade_disposition(rel.disposition)
                rel.disposition_drift = 0


def _stability_hit(world, civ, amount: int, acc) -> None:
    if amount <= 0 or civ is None or not civ.regions:
        return
    from chronicler.utils import STAT_FLOOR, civ_index, clamp
    if acc is not None:
        acc.add(civ_index(world, civ.name), civ, "stability", -amount, "signal")
    else:
        civ.stability = clamp(civ.stability - amount, STAT_FLOOR["stability"], 100)


def embargo_dependence_damage(world, imposer: str, target: str) -> tuple[int, int]:
    """(extra damage to target, self-damage to imposer) from mutual trade dependence."""
    if not ledger_enabled(world):
        return 0, 0
    to_target = int(round(EMBARGO_DEPENDENCE_STABILITY * dependence(world, target, imposer)))
    to_imposer = int(round(EMBARGO_DEPENDENCE_STABILITY * dependence(world, imposer, target)))
    return to_target, to_imposer


def apply_embargo_self_damage(world, imposer, amount: int, acc=None) -> None:
    _stability_hit(world, imposer, amount, acc)


def apply_war_trade_shock(world, attacker: str, defender: str, acc=None) -> None:
    """A new war severs trade: each side loses stability by its dependence on the other."""
    if not ledger_enabled(world):
        return
    civ_map = world.civ_map
    for x, y in ((attacker, defender), (defender, attacker)):
        amount = int(round(WAR_DEPENDENCE_STABILITY * dependence(world, x, y)))
        _stability_hit(world, civ_map.get(x), amount, acc)


def pandemic_spread_targets(world, source_idx: int) -> list[int]:
    """Candidate regions a plague can jump to from ``source_idx``: every region
    with recorded contact (any channel), sorted by index."""
    return region_partners(world, source_idx)


def pandemic_spread_probability(world, source_idx: int, target_idx: int) -> float:
    contact = region_contact(world, source_idx, target_idx)
    if contact <= 0:
        return 0.0
    return 1.0 - math.exp(-contact / PANDEMIC_CONTACT_SCALE)


# ---------------------------------------------------------------------------
# Viewer / analytics summaries
# ---------------------------------------------------------------------------

def snapshot_summary(world, top_n: int = 5) -> dict:
    """Small per-turn summary for ``TurnSnapshot.contact``."""
    ledger = world.contact_ledger
    totals = [0.0, 0.0, 0.0, 0.0]
    for row in ledger.edges:
        for c in range(4):
            totals[c] += row[2 + c]
    civ_map = world.civ_map
    living_pairs = [
        row for row in ledger.pairs
        if (ca := civ_map.get(row[0])) is not None and ca.regions
        and (cb := civ_map.get(row[1])) is not None and cb.regions
    ]
    trade_pairs = [row for row in living_pairs if row[2] >= TRADE_PARTNER_MIN_FLOW]
    top = sorted(trade_pairs, key=lambda r: (-r[2], r[0], r[1]))[:top_n]
    return {
        "edges": len(ledger.edges),
        "contact_pairs": len(living_pairs),
        "trade_pairs": len(trade_pairs),
        "inflow": {name: ledger.last_inflow[c] for c, name in enumerate(CHANNELS)},
        "stock": {name: _q(totals[c]) for c, name in enumerate(CHANNELS)},
        "top_trade_pairs": [
            {
                "a": a, "b": b, "trade": t,
                "dependence_ab": _q(dependence(world, a, b)),
                "dependence_ba": _q(dependence(world, b, a)),
            }
            for a, b, t, *_ in top
        ],
    }


def extract_contact_metrics(bundles: list[dict]) -> dict:
    """Analytics section from ``history[n].contact`` (empty when no bundle has it)."""
    runs = []
    for bundle in bundles:
        series = [h.get("contact") for h in bundle.get("history", []) if h.get("contact")]
        if not series:
            continue
        seed = bundle.get("metadata", {}).get("seed")
        trade_pairs = [s["trade_pairs"] for s in series]
        inflow = {name: sum(s["inflow"][name] for s in series) for name in CHANNELS}
        pair_counts: dict[str, int] = {}
        for s in series:
            for row in s["top_trade_pairs"]:
                key = f"{row['a']}|{row['b']}"
                pair_counts[key] = pair_counts.get(key, 0) + 1
        runs.append({
            "seed": seed,
            "turns": len(series),
            "mean_trade_pairs": sum(trade_pairs) / len(trade_pairs),
            "max_trade_pairs": max(trade_pairs),
            "turns_with_trade_pair": sum(1 for v in trade_pairs if v > 0),
            "total_inflow": inflow,
            "final_edges": series[-1]["edges"],
            "most_persistent_pairs": sorted(pair_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5],
        })
    if not runs:
        return {}
    return {
        "runs": len(runs),
        "mean_trade_pairs": sum(r["mean_trade_pairs"] for r in runs) / len(runs),
        "total_inflow": {name: sum(r["total_inflow"][name] for r in runs) for name in CHANNELS},
        "by_seed": runs,
    }
