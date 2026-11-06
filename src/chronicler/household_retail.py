"""L6b household food retail, option R (``--household-retail``, default off).

Requires ``--agents hybrid`` and ``--food-allocation`` (L2): it extends L2's
provisioning step. Design: ``docs/integration/household-retail-design.md``;
the lead's decisions and the binding FFI contract are in the phase plan
(``docs/superpowers/roadmaps/productive-recovery-phase.md``, section 2, PL4);
integration page ``docs/integration/household-retail.md``.

Pilot boundary (``--household-retail-boundary``), sticky: ``market``
(default) adds each ruling civilization's capital region the turn it first
qualifies; ``paid_work`` adds regions that have had an open L6a firm or a
paid RS2 repair crew; ``all`` adds every controlled region. A region leaves
the pilot only when it has no controller (or the switch goes off, or the
mode becomes ``record_only``): its holdings return to its commons, dated
(``pilot_closed``). Conquest alone does not remove a region.

Title (Phase 2). From the first pilot turn, the titled share ``THETA`` of
each pilot harvest (food slots and foraging) belongs to the region's Phase 2
farmers by stable id, in proportion to their food work ``u_i x (1 - h_i)``
(urban farm labour factor and health work loss, from the Phase 2 snapshot L2
uses). Each good's titled milli-food is split by largest remainder, ties by
ascending id. Opening stock, merchant imports, convoys and granary grain stay
commons. Owned food lives here, never in ``region.stockpile`` (the commons):
the native economy receives it as the optional ``retail_owned_<good>``
columns, counts it in availability and prices, draws its consumption only
from commons and reports the owned decay and storage overflow per good,
which are applied to claims pro rata. A farmer beyond the claims cap is not
titled (``claims_refused``); their share stays commons.

Provisioning (native phase 0.7, ``set_household_retail``): per pilot region
a price (the economy's post-trade food price clamped to [0.5, 3.0] x the
ration, milli per ration, floor), the free rations (commons draw-down and
granary release) and the owners' claims. The tick sells, pays and feeds;
``install_retail_income`` replaces pilot farmers' remaining ordinary farm
income. After the tick the frame and the income receipt are taken once,
refused when stale or repeated, and the claims are debited (own-eaten,
sold).

Lifecycles (by stable id): a dead owner's claim passes to the spouse (read
before the tick, alive after it), else equally to living children in the
claim's region (largest remainder, ascending id), else to the commons
(``escheat``). A migrant's claim stays in the origin's pool (sold there, eaten
only when present). Households are never stored, so a split or rejoin
creates nothing. A pilot region whose controller changed between Phase 2 and
the agent tick loses the conquest share of owned stock (``war_loss``);
occupation and siege requisitions do not reach owned stock (declared limit,
counted). A rebuilt native pool closes every claim to the commons.

Granary procurement (pinned seam in ``grain_reserves.tick_grain_reserves``):
a pilot market's sellable surplus counts commons plus owned grain; grain the
ruler buys in its own realm comes first from owners, pro rata to their
claims, and the cost the treasury already pays is credited to them by id in
Phase 10 (``transfer_wealth``, purpose ``food_procurement``), once per turn.
Foreign purchases take commons only.

Modes: ``retail`` (default); ``no_relief`` (THETA = 1, native mode 1);
``free_exchange`` (title, the same rounds at price 0, farm income kept,
procurement unpaid); ``record_only`` (Python computes the boundary and what
would be titled and priced, installs and holds nothing: the trajectory is
L2's alone).

Accounting: every identity of the design's section 10 that Python can see is
checked after each mutation and raised on failure (:func:`check_region`,
:func:`check_owner`, the frame checks). No randomness; every order is by
region index, stable id or good order. Parameters are declared modeling
choices, not calibrated.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from chronicler.household_retail_state import (
    BOUNDARIES, COMMONS_REASONS, COUNTERS, FLOW_KINDS, FLOW_SIGNS, MAX_CLAIMS, MAX_LOG, MAX_SAMPLE,
    MODES, NATIVE_MODES, RETAIL_GOODS, HouseholdRetailState, RegionFrame, RetailRecord, RetailRegion,
)

#: Titled share of each pilot harvest (``no_relief``: 1).
THETA = 0.9
#: The farm-earnings band the economy applies to its farmer income modifier.
PRICE_FLOOR = 0.5
PRICE_CAP = 3.0
#: Native ``wealth_transfer::PURPOSES`` indices (appended by PL4).
PURPOSE_FOOD_PURCHASE = 5
PURPOSE_FOOD_PROCUREMENT = 6
PROCUREMENT_BATCH = 0
FARMER = 0                  # native ``Occupation::Farmer``
ADULT_AGE = 20              # native ``agent::AGE_ADULT``
MILLI = 1000
GRAIN = 0                   # index of grain in RETAIL_GOODS
#: Pseudo-owners of titled food that stays commons (never claims).
UNTITLED, REFUSED = -1, -2
_PSEUDO = {UNTITLED: "untitled", REFUSED: "claims_refused"}

#: Native retail methods (the FFI contract), all or none.
NATIVE_METHODS: tuple[str, ...] = (
    "set_household_retail", "cancel_household_retail", "take_household_retail_frame",
    "install_retail_income", "cancel_retail_income", "take_retail_income_receipt",
)
#: Native Phase 2 result columns per pilot region (food units).
PHASE2_COLUMNS: tuple[str, ...] = tuple(
    f"retail_{kind}_{good}" for kind in ("titled", "owned_close", "owned_decay", "owned_overflow")
    for good in RETAIL_GOODS) + ("commons_consumed", "commons_sufficiency")
#: Region columns of the native provisioning frame Python checks. The FFI
#: contract fixes the frame's shape, not these names: they are this lane's
#: proposal for the native lane (see docs/integration/household-retail.md).
FRAME_COLUMNS: tuple[str, ...] = (
    "region", "price_milli", "free_rations", "free_given", "free_unallocated",
    "offered_milli", "own_eaten_milli", "sold_milli", "unsold_milli",
    "paid_milli", "credited_milli", "refunded_milli", "rations", "persons",
    "priced_out_persons", "offer_short_persons",
)
#: Tolerances: rations (f64 sums of f32 rations) and the f32 owned stock.
RATION_TOL = 1e-4
OWNED_TOL_MILLI = 3


class RetailAccountingError(RuntimeError):
    """A household retail identity does not hold."""


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def _state(world) -> HouseholdRetailState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "household_retail", None) if container is not None else None


def _bump(state: HouseholdRetailState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def _log(state: HouseholdRetailState, record: RetailRecord) -> None:
    state.log.append(record)
    if len(state.log) > MAX_LOG:
        drop = len(state.log) - MAX_LOG
        del state.log[:drop]
        state.log_dropped += drop


def set_household_retail_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--household-retail-mode`` and ``--household-retail-boundary``)
    or disable; omitted options keep the saved ones. Disabling, or switching to
    ``record_only``, closes every holding to its region's commons, dated."""
    mode = getattr(args, "household_retail_mode", None) if args is not None else None
    boundary = getattr(args, "household_retail_boundary", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.household_retail = state = HouseholdRetailState(
            mode=mode or MODES[0], boundary=boundary or BOUNDARIES[0])
    else:
        if mode is not None:
            state.mode = mode
        if boundary is not None:
            state.boundary = boundary
    state.enabled = bool(value)
    if not state.enabled or state.mode == "record_only":
        note = "switch off" if not state.enabled else "mode record_only holds no food"
        for reg in list(state.regions):
            _close_region(world, state, reg, "switch_off", note=note)


def household_retail_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


# ---------------------------------------------------------------------------
# Integer splits
# ---------------------------------------------------------------------------

def largest_remainder(total: int, weights) -> dict[int, int]:
    """Split ``total`` (a nonnegative integer) over ``(key, weight)`` pairs
    (nonnegative integer weights) by largest remainder; ties go to the
    smaller key. Returns only positive shares. Each share is at most
    ``ceil(total x weight / sum)``, so a pro rata debit never exceeds a claim."""
    total = int(total)
    items = [(int(k), int(w)) for k, w in weights if int(w) > 0]
    whole = sum(w for _, w in items)
    if total < 0:
        raise ValueError("cannot split a negative amount")
    if total == 0 or whole == 0:
        return {}
    out: dict[int, int] = {}
    order = []
    given = 0
    for key, w in items:
        q, r = divmod(total * w, whole)
        out[key] = q
        given += q
        order.append((-r, key))
    order.sort()
    for _, key in order[:total - given]:
        out[key] += 1
    return {k: v for k, v in sorted(out.items()) if v}


def _pro_rata(total: int, claims: dict[int, int]) -> dict[int, int]:
    if total > sum(claims.values()):
        raise RetailAccountingError("a debit exceeds the claims it is drawn from")
    return largest_remainder(total, claims.items())


def _draw(goods: list[int], total: int) -> list[int]:
    """Per-good amounts of a draw of ``total`` from a pooled mix, pro rata to
    its composition (largest remainder, ties by good order)."""
    if total > sum(goods):
        raise RetailAccountingError("a draw exceeds the owned stock")
    split = largest_remainder(total, enumerate(goods))
    return [split.get(g, 0) for g in range(len(goods))]


def to_milli(value) -> int:
    """A native f32 food quantity in whole milli-food, to the nearest (an f32
    holds no finer amount: ``f32(1.8)`` is 1800 milli, not 1799)."""
    value = float(value)
    if not math.isfinite(value):
        raise RetailAccountingError("native retail value is not finite")
    return max(0, math.floor(value * MILLI + 0.5))


# ---------------------------------------------------------------------------
# The turn's books (transient)
# ---------------------------------------------------------------------------

@dataclass
class _Book:
    """One pilot region's flows in one turn, from its state at first touch."""

    entry: RetailRegion
    open_goods: list[int]
    open_claims: dict[int, int]
    goods: dict[str, list[int]] = field(default_factory=dict)
    owners: dict[str, dict[int, int]] = field(default_factory=dict)
    commons: dict[str, int] = field(default_factory=dict)
    price_milli: int | None = None
    free_rations: float | None = None
    commons_consumed: float | None = None           # native f32, exact
    phase2: dict | None = None
    provisioning: dict | None = None
    would_be: dict | None = None


@dataclass
class _Phase2:
    turn: int
    pilots: list[int]
    theta: float
    farmers: dict[int, list[tuple[int, int]]]      # region -> [(id, micro-weight)], ascending id
    controllers: dict[int, str | None] = field(default_factory=dict)
    titled: bool = False


@dataclass
class _Installed:
    turn: int
    regions: dict[int, tuple[int, float]]           # region -> (price milli, free rations)
    claims: dict[tuple[int, int], int]              # (owner, region) -> installed milli-food
    income: bool


@dataclass
class _Procured:
    flow_index: int
    region: int
    taken: float                                    # food units sold from owners
    milli: int                                      # milli-food debited from claims
    owners: dict[int, int]


@dataclass
class _Turn:
    turn: int
    books: dict[int, _Book] = field(default_factory=dict)
    touched: set[int] = field(default_factory=set)  # commons written this turn
    phase2: _Phase2 | None = None
    installed: _Installed | None = None
    spouses: dict[int, int | None] | None = None
    procured: list[_Procured] = field(default_factory=list)
    money: dict | None = None
    income: dict | None = None
    sample: list | None = None
    sample_dropped: int = 0


def _turn(state: HouseholdRetailState, world) -> _Turn:
    t = state._turn
    if t is not None and t.turn == world.turn:
        return t
    if t is not None and t.procured:
        raise RuntimeError("household retail procurement of an earlier turn was never credited")
    state._turn = t = _Turn(turn=int(world.turn))
    return t


def _book(state: HouseholdRetailState, world, reg: RetailRegion) -> _Book:
    t = _turn(state, world)
    book = t.books.get(reg.region)
    if book is None or book.entry is not reg:
        if book is not None:
            raise RetailAccountingError(f"region {reg.region} entered the pilot twice in one turn")
        book = t.books[reg.region] = _Book(entry=reg, open_goods=list(reg.goods), open_claims=dict(reg.claims))
    return book


def _record(book: _Book, kind: str, per_good: list[int] | None, per_owner: dict[int, int]) -> None:
    if per_good is not None:
        row = book.goods.setdefault(kind, [0] * len(RETAIL_GOODS))
        for g, v in enumerate(per_good):
            row[g] += v
    owners = book.owners.setdefault(kind, {})
    for k, v in per_owner.items():
        owners[k] = owners.get(k, 0) + v
    total = sum(per_owner.values())
    book.entry.totals[kind] = book.entry.totals.get(kind, 0) + total


def _sorted_claims(reg: RetailRegion) -> None:
    reg.claims = {k: v for k, v in sorted(reg.claims.items()) if v > 0}


def _debit(state, world, reg: RetailRegion, kind: str, per_owner: dict[int, int], per_good: list[int],
           *, commons: str | None = None) -> None:
    """Remove ``per_owner`` from claims and ``per_good`` from goods (equal totals)."""
    if sum(per_owner.values()) != sum(per_good):
        raise RetailAccountingError(f"region {reg.region}: {kind} moves unequal claims and goods")
    book = _book(state, world, reg)
    for k, v in per_owner.items():
        if k in _PSEUDO:
            continue
        have = reg.claims.get(k, 0)
        if v < 0 or v > have:
            raise RetailAccountingError(f"region {reg.region}: {kind} of {v} exceeds owner {k}'s claim {have}")
        reg.claims[k] = have - v
    for g, v in enumerate(per_good):
        if v < 0 or v > reg.goods[g]:
            raise RetailAccountingError(f"region {reg.region}: {kind} of {v} exceeds {RETAIL_GOODS[g]} {reg.goods[g]}")
        reg.goods[g] -= v
    _sorted_claims(reg)
    _record(book, kind, per_good, per_owner)
    if commons is not None:
        _to_stockpile(state, world, reg.region, per_good)
        book.commons[commons] = book.commons.get(commons, 0) + sum(per_good)
        _bump(state, "to_commons_milli", sum(per_good))


def _to_stockpile(state, world, rid: int, per_good: list[int]) -> None:
    goods = world.regions[rid].stockpile.goods
    for g, v in enumerate(per_good):
        if v:
            name = RETAIL_GOODS[g]
            goods[name] = goods.get(name, 0.0) + v / MILLI
    if any(per_good) and state._turn is not None and state._turn.turn == world.turn:
        state._turn.touched.add(rid)


def check_region(reg: RetailRegion, book: _Book) -> None:
    """Owned pool per region and good: close = open + sum(sign x flow); claims
    sum to goods; nothing negative."""
    for g in range(len(RETAIL_GOODS)):
        expect = book.open_goods[g] + sum(FLOW_SIGNS[k] * row[g] for k, row in book.goods.items())
        if reg.goods[g] != expect or reg.goods[g] < 0:
            raise RetailAccountingError(
                f"region {reg.region}: owned {RETAIL_GOODS[g]} {reg.goods[g]} != {expect} from its flows")
    if sum(reg.claims.values()) != sum(reg.goods):
        raise RetailAccountingError(f"region {reg.region}: claims {sum(reg.claims.values())} != goods {sum(reg.goods)}")
    if any(v <= 0 for v in reg.claims.values()):
        raise RetailAccountingError(f"region {reg.region}: a claim is not positive")


def check_owner(reg: RetailRegion, book: _Book) -> None:
    """Per owner: claim close = open + sum(sign x flow); every flow moves claims
    and goods by the same total; inheritance moves claims only and conserves."""
    keys = set(book.open_claims) | set(reg.claims) | {k for d in book.owners.values() for k in d}
    for k in keys:
        expect = book.open_claims.get(k, 0) + sum(FLOW_SIGNS[kind] * d.get(k, 0) for kind, d in book.owners.items())
        if reg.claims.get(k, 0) != expect:
            raise RetailAccountingError(
                f"region {reg.region}: owner {k} holds {reg.claims.get(k, 0)}, flows give {expect}")
    for kind, row in book.goods.items():
        if sum(book.owners.get(kind, {}).values()) != sum(row):
            raise RetailAccountingError(f"region {reg.region}: {kind} differs between claims and goods")
    if sum(book.owners.get("inherited_in", {}).values()) != sum(book.owners.get("inherited_out", {}).values()):
        raise RetailAccountingError(f"region {reg.region}: inheritance does not conserve claims")


def _check(state, world, regs=None) -> None:
    t = state._turn
    if t is None or t.turn != world.turn:
        return
    for rid, book in t.books.items():
        if regs is not None and rid not in regs:
            continue
        check_region(book.entry, book)
        check_owner(book.entry, book)


# ---------------------------------------------------------------------------
# Boundary
# ---------------------------------------------------------------------------

def _close_region(world, state, reg: RetailRegion, reason: str, *, note: str | None = None) -> None:
    """Holdings to the region's commons; the region leaves the pilot."""
    if reason not in COMMONS_REASONS:
        raise KeyError(reason)
    total = sum(reg.goods)
    if reason != "switch_off":
        if total:
            _debit(state, world, reg, "to_commons", dict(reg.claims), list(reg.goods), commons=reason)
    else:
        # Configuration time, outside any turn: no turn book.
        _to_stockpile(state, world, reg.region, list(reg.goods))
        _bump(state, "to_commons_milli", total)
        reg.goods = [0] * len(RETAIL_GOODS)
        reg.claims = {}
    state.regions = [r for r in state.regions if r is not reg]
    _bump(state, "regions_closed")
    _log(state, RetailRecord(turn=int(world.turn), region=reg.region,
                             kind="pilot_closed" if reason != "switch_off" else "switch_off",
                             milli=total, note=note or reason))


def _capital_regions(world) -> list[tuple[int, str]]:
    names = {r.name: i for i, r in enumerate(world.regions)}
    out = []
    for civ in world.civilizations:
        if not civ.regions or civ.capital_region is None:
            continue
        rid = names.get(civ.capital_region)
        if rid is not None and world.regions[rid].controller == civ.name:
            out.append((rid, "capital"))
    return out


def _paid_work_regions(world) -> list[tuple[int, str]]:
    """Regions with an open L6a firm, or a paid RS2 repair crew in RS2's last
    frame (PL3's paid recovery crews pay through RS2's receipts)."""
    out = set()
    lv = getattr(world, "livelihoods", None)
    payroll = getattr(lv, "workshop_payroll", None)
    if payroll is not None and payroll.enabled:
        out.update(f.region for f in payroll.firms if f.status == "open")
    repair = getattr(lv, "repair_projects", None)
    if repair is not None and repair.enabled and repair.receipts:
        out.update(r.region for r in repair.receipts if r.wages_milli > 0)
    return [(rid, "paid_work") for rid in sorted(out)]


def _qualifying(world, state) -> list[tuple[int, str]]:
    if state.boundary == "market":
        found = _capital_regions(world)
    elif state.boundary == "paid_work":
        found = _paid_work_regions(world)
    else:
        found = [(rid, "all") for rid in range(len(world.regions))]
    rulers = {c.name for c in world.civilizations if c.regions}
    pilots = {r.region for r in state.regions}
    out = {}
    for rid, reason in found:
        if (0 <= rid < len(world.regions) and rid not in pilots and rid not in out
                and world.regions[rid].controller in rulers):
            out[rid] = reason
    return sorted(out.items())


def _update_boundary(world, state) -> None:
    for reg in list(state.regions):
        if world.regions[reg.region].controller is None:
            _close_region(world, state, reg, "pilot_closed", note="no controller")
    for rid, reason in _qualifying(world, state):
        reg = RetailRegion(region=rid, opened_turn=int(world.turn), reason=reason)
        state.regions.append(reg)
        _bump(state, "regions_opened")
        _log(state, RetailRecord(turn=int(world.turn), region=rid, kind="pilot_opened", note=reason))
    state.regions.sort(key=lambda r: r.region)
    for reg in state.regions:
        _book(state, world, reg)


def pilot_regions(world) -> list[int]:
    state = _state(world)
    return [r.region for r in state.regions] if state is not None else []


# ---------------------------------------------------------------------------
# Phase 2
# ---------------------------------------------------------------------------

def _column(snapshot, name):
    from chronicler.columnar import pylist
    return pylist(snapshot.column(name))


def _health_losses(world, people: dict[int, tuple]) -> dict[int, float]:
    """Per-person health work loss of this turn's health plan (native
    ``health_care::prepare`` semantics: an eligible patient loses the
    impairment, a caregiver the care fraction)."""
    hc = getattr(world, "health_care", None)
    rows = getattr(hc, "_prepared", None) if hc is not None else None
    if not rows:
        return {}
    from chronicler.health_care import health_care_active
    if not health_care_active(world):
        return {}
    armies = getattr(getattr(world, "war_state", None), "armies", [])
    enlisted = {int(aid) for army in armies for aid, _ in army.roster}
    urban = {int(c.settlement_id) for c in getattr(getattr(world, "cities", None), "cities", [])} - {0}
    impairment = float(hc.impairment)
    loss: dict[int, float] = {}
    for aid, _region, giver, care in rows:
        aid, giver = int(aid), int(giver)
        person = people.get(aid)
        if person is not None:
            _r, occupation, age, settlement = person
            if (occupation == FARMER and age >= ADULT_AGE and settlement not in urban
                    and aid not in enlisted):
                loss[aid] = impairment
        if giver:
            loss[giver] = float(care)
    return loss


def title_weights(world, snapshot, regions) -> dict[int, list[tuple[int, int]]]:
    """Each pilot region's Phase 2 farmers and their food work
    ``u_i x (1 - h_i)`` in integer micro-units, ascending id."""
    wanted = set(regions)
    if not wanted:
        return {}
    if snapshot is None:
        raise RuntimeError("household retail title requires the Phase 2 agent snapshot")
    cols = [_column(snapshot, name) for name in ("id", "region", "occupation", "age", "settlement_id")]
    people = {int(i): (int(r), int(o), int(a), int(s)) for i, r, o, a, s in zip(*cols)}
    from chronicler.cities import URBAN_FARM_LABOR
    cities = getattr(getattr(world, "cities", None), "cities", None) or []
    rank = {(int(c.region), int(c.settlement_id)): int(c.rank) for c in cities if c.settlement_id > 0}
    losses = _health_losses(world, people)
    out: dict[int, list[tuple[int, int]]] = {rid: [] for rid in sorted(wanted)}
    for aid in sorted(people):
        region, occupation, _age, settlement = people[aid]
        if region not in wanted or occupation != FARMER:
            continue
        city = rank.get((region, settlement))
        u = URBAN_FARM_LABOR[city] if city is not None else 1.0
        h = 0.0 if city is not None else min(1.0, max(0.0, losses.get(aid, 0.0)))
        out[region].append((aid, int(round(u * (1.0 - h) * 1_000_000))))
    return out


def _ration(world) -> float:
    from chronicler.economy import PER_CAPITA_FOOD
    from chronicler.tuning import get_override
    value = float(get_override(world, "economy.per_capita_food", PER_CAPITA_FOOD))
    if not (math.isfinite(value) and value > 0):
        raise ValueError("economy.per_capita_food must be positive")
    return value


def _patch_stockpiles(world, region_input, rids):
    """Rewrite the commons stock columns of regions whose commons this turn's
    closures changed after the batch was built (pool reset, closure)."""
    import pyarrow as pa
    names = list(region_input.schema.names)
    data = {n: region_input.column(n) for n in names}
    for good in RETAIL_GOODS:
        col = f"stockpile_{good}"
        if col not in data:
            raise RuntimeError(f"economy batch has no {col}")
        values = data[col].to_pylist()
        for rid in rids:
            values[rid] = world.regions[rid].stockpile.goods.get(good, 0.0)
        data[col] = pa.array(values, type=pa.float32())
    return pa.record_batch(data)


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Boundary, title weights and (unless record_only) the optional economy
    columns: ``retail_title_share`` (THETA; null outside the pilot) and
    ``retail_owned_<good>`` (owned stock at opening, food units)."""
    state = _state(world)
    t = _turn(state, world)
    if t.phase2 is not None:
        raise RuntimeError("household retail Phase 2 already prepared this turn")
    _update_boundary(world, state)
    if t.touched:
        region_input = _patch_stockpiles(world, region_input, sorted(t.touched))
        t.touched.clear()
    pilots = [r.region for r in state.regions]
    theta = 1.0 if state.mode == "no_relief" else THETA
    t.phase2 = _Phase2(turn=int(world.turn), pilots=pilots, theta=theta,
                       farmers=title_weights(world, snapshot, pilots))
    _check(state, world)
    if not pilots or state.mode == "record_only":
        return region_input
    import pyarrow as pa
    n = len(world.regions)
    share = [None] * n
    owned = [[0.0] * n for _ in RETAIL_GOODS]
    for reg in state.regions:
        share[reg.region] = theta
        for g, v in enumerate(reg.goods):
            owned[g][reg.region] = v / MILLI
    data = {name: region_input.column(name) for name in region_input.schema.names}
    if any(name.startswith("retail_") for name in data):
        raise RuntimeError("economy batch already carries retail columns")
    data["retail_title_share"] = pa.array(share, type=pa.float32())
    for g, good in enumerate(RETAIL_GOODS):
        data[f"retail_owned_{good}"] = pa.array(owned[g], type=pa.float32())
    return pa.record_batch(data)


def _would_be_title(world, economy_result, rid: int, theta: float) -> list[int]:
    """record_only: theta of this turn's food production per good (production ledger)."""
    from chronicler.economy import map_resource_to_good
    region = world.regions[rid]
    produced = [0.0] * len(RETAIL_GOODS)
    slots = economy_result.slot_output.get(region.name)
    if slots is None:
        raise RuntimeError("household retail record_only requires the native production ledger")
    for slot, out in enumerate(slots):
        good = map_resource_to_good(int(region.resource_types[slot]))
        if good in RETAIL_GOODS:
            produced[RETAIL_GOODS.index(good)] += float(out)
    produced[GRAIN] += float(economy_result.forage_output.get(region.name, 0.0))
    return [to_milli(theta * v) for v in produced]


def _split_title(state, t: _Turn, rid: int, titled: list[int], reg: RetailRegion | None):
    """Owner credits of each good's titled milli-food; refused and untitled
    shares go to pseudo-owners. Returns (per-owner totals, pseudo totals)."""
    farmers = t.phase2.farmers.get(rid, [])
    credits: dict[int, int] = {}
    pseudo = {UNTITLED: 0, REFUSED: 0}
    for amount in titled:
        split = largest_remainder(amount, farmers)
        if not split:
            pseudo[UNTITLED] += amount
        for aid, v in split.items():
            credits[aid] = credits.get(aid, 0) + v
    if reg is None:
        return credits, pseudo
    held = state.claims_count()
    admitted: dict[int, int] = {}
    for aid in sorted(credits):
        if aid in reg.claims or held < MAX_CLAIMS:
            if aid not in reg.claims:
                held += 1
            admitted[aid] = credits[aid]
        else:
            pseudo[REFUSED] += credits[aid]
    return admitted, pseudo


def finish_phase2(world, economy_result, agent_bridge, acc):
    """Title this turn's pilot harvest, then apply the owned decay and storage
    overflow the native economy reports, once per turn."""
    state = _state(world)
    t = _turn(state, world)
    p2 = t.phase2
    if p2 is None or p2.turn != world.turn:
        raise RuntimeError("household retail Phase 2 was not prepared this turn")
    if p2.titled or (state.last_title_turn is not None and world.turn <= state.last_title_turn):
        raise RuntimeError("household retail harvest already titled for this turn")
    p2.titled = True
    state.last_title_turn = int(world.turn)
    for rid in p2.pilots:
        p2.controllers[rid] = world.regions[rid].controller
    if not p2.pilots:
        return []
    if state.mode == "record_only":
        for rid in p2.pilots:
            titled = _would_be_title(world, economy_result, rid, p2.theta)
            credits, pseudo = _split_title(state, t, rid, titled, None)
            book = _book(state, world, state.region(rid))
            book.would_be = {"titled_milli": float(sum(titled)), "owners": float(len(credits)),
                             "farmers": float(len(p2.farmers.get(rid, []))),
                             "untitled_milli": float(pseudo[UNTITLED])}
        return []
    columns = getattr(economy_result, "household_retail", None) or {}
    for rid in p2.pilots:
        reg = state.region(rid)
        row = columns.get(rid)
        if row is None or any(row.get(name) is None for name in PHASE2_COLUMNS):
            raise RuntimeError("household retail requires a native economy that returns the retail columns")
        _title_region(world, state, t, reg, row)
    _check(state, world)
    return []


def _title_region(world, state, t: _Turn, reg: RetailRegion, row: dict) -> None:
    rid = reg.region
    book = _book(state, world, reg)
    book.phase2 = {k: round(float(row[k]), 6) for k in PHASE2_COLUMNS}
    book.commons_consumed = float(row["commons_consumed"])
    opening = list(reg.goods)
    titled = [to_milli(row[f"retail_titled_{good}"]) for good in RETAIL_GOODS]
    # Native identity per good (f32): close = open + titled - decay - overflow.
    from numpy import float32
    for g, good in enumerate(RETAIL_GOODS):
        sent = float(float32(opening[g] / MILLI))
        terms = (sent, float(row[f"retail_titled_{good}"]), -float(row[f"retail_owned_decay_{good}"]),
                 -float(row[f"retail_owned_overflow_{good}"]))
        close = float(row[f"retail_owned_close_{good}"])
        if (any(not math.isfinite(v) for v in (*terms, close)) or min(terms[1], -terms[2], -terms[3]) < 0
                or abs(close - math.fsum(terms)) > 1e-5 * max(1.0, math.fsum(abs(v) for v in terms))):
            raise RetailAccountingError(f"region {rid}: native owned {good} does not close")
    credits, pseudo = _split_title(state, t, rid, titled, reg)
    # Title: goods by good, claims by owner (pseudo-owners for what stays commons).
    for aid, v in credits.items():
        reg.claims[aid] = reg.claims.get(aid, 0) + v
    for g, v in enumerate(titled):
        reg.goods[g] += v
    held = {**dict(reg.claims), **{k: v for k, v in pseudo.items() if v}}
    _record(book, "titled", titled, {**credits, **{k: v for k, v in pseudo.items() if v}})
    _bump(state, "titled_milli", sum(credits.values()))
    _bump(state, "untitled_milli", pseudo[UNTITLED])
    if pseudo[REFUSED]:
        _bump(state, "claims_refused", 1)
        _log(state, RetailRecord(turn=int(world.turn), region=rid, kind="claims_refused",
                                 milli=pseudo[REFUSED], note="claims cap"))
    _bump(state, "owners_titled", len(credits))
    # Decay, then storage overflow: per good as the native reports (whole
    # milli, never above the stock), on claims pro rata.
    for kind, prefix in (("decay", "retail_owned_decay"), ("overflow", "retail_owned_overflow")):
        per_good = [min(to_milli(row[f"{prefix}_{good}"]), reg.goods[g]) for g, good in enumerate(RETAIL_GOODS)]
        total = sum(per_good)
        if not total:
            continue
        per_owner = _pro_rata(total, held)
        for k, v in per_owner.items():
            held[k] -= v
        _debit(state, world, reg, kind, per_owner, per_good)
        _bump(state, f"{kind}_milli", total)
    # The native owned close agrees within f32 and milli rounding (Python is
    # authoritative; it re-sends its own totals every turn, so nothing drifts).
    for g, good in enumerate(RETAIL_GOODS):
        native = float(row[f"retail_owned_close_{good}"]) * MILLI
        slack = OWNED_TOL_MILLI + 2e-5 * max(native, float(reg.goods[g]))
        if not native - slack <= reg.goods[g] <= native + slack:
            raise RetailAccountingError(f"region {rid}: owned {good} {reg.goods[g]} differs from native {native:.3f}")
    # What stays commons leaves the pool after its decay, pro rata to the mix.
    for key, reason in _PSEUDO.items():
        left = held.get(key, 0)
        if left:
            _debit(state, world, reg, "to_commons", {key: left}, _draw(reg.goods, left), commons=reason)


def rollback_phase2(world) -> None:
    state = _state(world)
    t = state._turn if state is not None else None
    if t is not None and t.turn == world.turn:
        t.phase2 = None


# ---------------------------------------------------------------------------
# Agent tick
# ---------------------------------------------------------------------------

def _released(world) -> dict[int, float]:
    from chronicler.grain_reserves import grain_reserves_active
    if not grain_reserves_active(world):
        return {}
    from chronicler.grain_reserves_state import RELEASED
    state = world.grain_reserves
    out: dict[int, float] = {}
    if state.flows_turn == world.turn:
        for f in state.flows:
            if f.kind == RELEASED:
                out[f.region] = out.get(f.region, 0.0) + float(f.amount)
    return out


def price_milli(world, economy_result, rid: int) -> int:
    """Ask in milli-units per ration: the economy's post-trade food price,
    clamped to [PRICE_FLOOR, PRICE_CAP], times the ration (floor)."""
    name = world.regions[rid].name
    prices = getattr(economy_result, "market_prices", {}).get(name)
    if not prices or "food" not in prices or not math.isfinite(float(prices["food"])):
        raise RuntimeError("household retail requires the native post-trade food price")
    p = min(PRICE_CAP, max(PRICE_FLOOR, float(prices["food"])))
    return int(math.floor(p * _ration(world) * MILLI))


def _spouse(rows) -> int | None:
    from chronicler.ffi_constants import BOND_MARRIAGE
    for target, _sentiment, bond, _formed in rows or ():
        if int(bond) == BOND_MARRIAGE:
            return int(target)
    return None


def _require(sim, names=NATIVE_METHODS) -> None:
    present = [callable(getattr(sim, name, None)) for name in names]
    if not all(present):
        raise RuntimeError("household retail requires a fresh native build with the retail provisioning methods")


def before_agent_tick(world, agent_bridge, economy_result) -> None:
    """Conquest loss, spouses of owners, then the one-tick installs."""
    state = _state(world)
    t = _turn(state, world)
    sim = agent_bridge._sim
    t.installed = None
    p2 = t.phase2 if t.phase2 is not None and t.phase2.turn == world.turn and t.phase2.titled else None
    # Conquest: a pilot region whose controller changed since Phase 2.
    if p2 is not None:
        from chronicler.economy import CONQUEST_STOCKPILE_SURVIVAL
        for rid, before in sorted(p2.controllers.items()):
            reg = state.region(rid)
            now = world.regions[rid].controller
            if reg is None or now == before or not sum(reg.goods):
                continue
            per_good = [v - math.floor(v * CONQUEST_STOCKPILE_SURVIVAL) for v in reg.goods]
            total = sum(per_good)
            if total:
                _debit(state, world, reg, "war_loss", _pro_rata(total, reg.claims), per_good)
                _bump(state, "war_loss_milli", total)
                _log(state, RetailRecord(turn=int(world.turn), region=rid, kind="war_loss", milli=total,
                                         note=f"{before} -> {now}"))
    # Declared limit: occupation and siege requisitions do not reach owned stock.
    armies = getattr(getattr(world, "war_state", None), "armies", [])
    for reg in state.regions:
        region = world.regions[reg.region]
        occupied = region.occupied_by is not None and region.occupied_by != region.controller
        besieged = any(a.phase == "sieging" and a.region == region.name and a.civ != region.controller
                       for a in armies)
        if sum(reg.goods) and (occupied or besieged):
            _bump(state, "requisition_exempt_region_turns")
    # Spouses of every owner, before the tick (inheritance after it).
    owners = sorted({aid for reg in state.regions for aid in reg.claims})
    if owners and not callable(getattr(sim, "get_agent_relationships", None)):
        raise RuntimeError("household retail requires get_agent_relationships")
    t.spouses = {aid: _spouse(sim.get_agent_relationships(aid)) for aid in owners}
    _check(state, world)
    if p2 is None or not p2.pilots:
        if p2 is None and state.regions:
            _bump(state, "turns_unobserved")
        return
    released = _released(world)
    ration = _ration(world)
    if state.mode == "record_only":
        for rid in p2.pilots:
            book = _book(state, world, state.region(rid))
            book.would_be = {**(book.would_be or {}), "price_milli": float(price_milli(world, economy_result, rid))}
        return
    from chronicler.food_allocation import food_allocation_active
    if not food_allocation_active(world):
        raise RuntimeError("household retail requires --food-allocation")
    _require(sim)
    regions: dict[int, tuple[int, float]] = {}
    rows = []
    for rid in p2.pilots:
        book = t.books[rid]
        price = 0 if state.mode == "free_exchange" else price_milli(world, economy_result, rid)
        free = (book.commons_consumed + released.get(rid, 0.0)) / ration
        book.price_milli, book.free_rations = price, free
        regions[rid] = (price, free)
        rows.append((rid, price, free))
    claims = {(aid, reg.region): milli for reg in state.regions if reg.region in regions
              for aid, milli in reg.claims.items() if milli > 0}
    claim_rows = [(aid, rid, milli) for (aid, rid), milli in sorted(claims.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    sim.set_household_retail(int(world.turn), NATIVE_MODES[state.mode], rows, claim_rows)
    t.installed = _Installed(turn=int(world.turn), regions=regions, claims=claims, income=False)
    if state.mode != "free_exchange":
        sim.install_retail_income(int(world.turn), sorted(regions))
        t.installed.income = True


def rollback_agent_tick(world, agent_bridge) -> None:
    """The before hooks or the agent tick raised: cancel installs the tick never took."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.installed is None:
        return
    installed, t.installed = t.installed, None
    sim = agent_bridge._sim
    sim.cancel_household_retail()
    if installed.income:
        sim.cancel_retail_income()


def provisioned_regions(world) -> set[int]:
    """Regions whose provisioning retail installed this turn (L2's seam)."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != world.turn or t.installed is None:
        return set()
    return set(t.installed.regions)


def _settle_frame(world, state, t: _Turn, installed: _Installed, frame, receipt) -> None:
    turn = int(world.turn)
    source, columns, rows, claim_rows, money_rows, sample, dropped = frame
    if int(source) != installed.turn or installed.turn != turn:
        raise RuntimeError("household retail receipt belongs to another turn")
    columns = [str(c) for c in columns]
    missing = [c for c in FRAME_COLUMNS if c not in columns]
    if missing:
        raise RuntimeError(f"household retail frame lacks columns {missing}")
    by_region: dict[int, dict] = {}
    for row in rows:
        if len(row) != len(columns):
            raise RuntimeError("household retail frame row does not match its columns")
        r = dict(zip(columns, (float(v) for v in row)))
        rid = int(r["region"])
        if rid in by_region or rid not in installed.regions or r["region"] != rid:
            raise RuntimeError("household retail frame names an unknown or repeated region")
        by_region[rid] = r
    if set(by_region) != set(installed.regions):
        raise RuntimeError("household retail frame does not cover the installed regions")
    # Claim rows: one per installed claim at most, debits within the claim.
    eaten: dict[int, dict[int, int]] = {rid: {} for rid in installed.regions}
    sold: dict[int, dict[int, int]] = {rid: {} for rid in installed.regions}
    seen = set()
    for owner, region, own, sale in claim_rows:
        key = (int(owner), int(region))
        own, sale = int(own), int(sale)
        if key in seen or key not in installed.claims:
            raise RuntimeError(f"household retail frame names an unknown or repeated claim {key}")
        seen.add(key)
        if own < 0 or sale < 0 or own + sale > installed.claims[key]:
            raise RetailAccountingError(f"claim {key}: eaten {own} + sold {sale} exceeds {installed.claims[key]}")
        if own:
            eaten[key[1]][key[0]] = own
        if sale:
            sold[key[1]][key[0]] = sale
    # Money rows: whole milli-units, debits = credits + refunds.
    money = {"paid": 0, "credited": 0, "refunded": 0}
    ids = set()
    for aid, paid, credited, refunded in money_rows:
        aid, paid, credited, refunded = int(aid), int(paid), int(credited), int(refunded)
        if aid in ids or min(paid, credited, refunded) < 0 or refunded > paid:
            raise RetailAccountingError(f"household retail money row of {aid} is invalid")
        ids.add(aid)
        money["paid"] += paid
        money["credited"] += credited
        money["refunded"] += refunded
    if money["paid"] != money["credited"] + money["refunded"]:
        raise RetailAccountingError("household retail payments do not balance")
    if state.mode == "free_exchange" and any(money.values()):
        raise RetailAccountingError("free_exchange moved money")
    ration_milli = _ration(world) * MILLI
    totals = {"paid_milli": 0, "credited_milli": 0, "refunded_milli": 0}
    for rid, r in sorted(by_region.items()):
        price, free = installed.regions[rid]
        offered = sum(v for (aid, reg), v in installed.claims.items() if reg == rid)
        own, sale = sum(eaten[rid].values()), sum(sold[rid].values())
        ints = {k: r[k] for k in ("price_milli", "offered_milli", "own_eaten_milli", "sold_milli", "unsold_milli",
                                   "paid_milli", "credited_milli", "refunded_milli")}
        if any(v != math.floor(v) or v < 0 for v in ints.values()):
            raise RetailAccountingError(f"region {rid}: provisioning milli columns are not whole")
        checks = (
            (int(r["price_milli"]) == price, "price differs from the install"),
            (abs(r["free_rations"] - free) <= RATION_TOL * max(1.0, free), "free rations differ from the install"),
            (abs(r["free_given"] + r["free_unallocated"] - r["free_rations"]) <= RATION_TOL * max(1.0, free),
             "free_given + free_unallocated != free_rations"),
            (min(r["free_given"], r["free_unallocated"]) >= -RATION_TOL, "negative free rations"),
            (int(r["offered_milli"]) == offered, "offered differs from the installed claims"),
            (int(r["own_eaten_milli"]) == own and int(r["sold_milli"]) == sale, "claim rows differ from the totals"),
            (own + sale == offered - int(r["unsold_milli"]), "own_eaten + sold != offered - unsold"),
            (int(r["paid_milli"]) == int(r["credited_milli"]) + int(r["refunded_milli"]), "payments do not balance"),
            (abs(r["rations"] - (r["free_given"] + (own + sale) / ration_milli))
             <= RATION_TOL * max(1.0, r["persons"]), "person rations != free_given + own_eaten + sold"),
            (r["rations"] <= r["persons"] + RATION_TOL, "a ration above one"),
        )
        for ok, message in checks:
            if not ok:
                raise RetailAccountingError(f"region {rid}: {message}")
        for key in totals:
            totals[key] += int(r[key])
    if (totals["paid_milli"], totals["credited_milli"], totals["refunded_milli"]) != \
            (money["paid"], money["credited"], money["refunded"]):
        raise RetailAccountingError("household retail money rows differ from the region totals")
    # Debit claims: own-eaten, then sold, each drawn from the pooled mix.
    for rid in sorted(by_region):
        reg = state.region(rid)
        book = _book(state, world, reg)
        book.provisioning = {k: round(v, 6) for k, v in by_region[rid].items()}
        for kind, rows_ in (("own_eaten", eaten[rid]), ("sold", sold[rid])):
            total = sum(rows_.values())
            if total:
                _debit(state, world, reg, kind, rows_, _draw(reg.goods, total))
                _bump(state, f"{kind}_milli", total)
        _bump(state, "priced_out_persons", int(by_region[rid]["priced_out_persons"]))
        _bump(state, "offer_short_persons", int(by_region[rid]["offer_short_persons"]))
    for key, value in money.items():
        _bump(state, f"{key}_milli", value)
    t.money = {**{f"{k}_milli": v for k, v in money.items()}, "rows": len(ids)}
    kept = []
    for aid, region, household, ration, fair, status in sample:
        if int(region) not in by_region or int(status) not in (0, 1, 2) or \
                not (-RATION_TOL <= float(ration) <= 1.0 + RATION_TOL):
            raise RetailAccountingError("household retail sample row is invalid")
        kept.append([int(aid), int(region), int(household), round(float(ration), 6), round(float(fair), 6),
                     int(status)])
    t.sample, t.sample_dropped = kept[:MAX_SAMPLE], int(dropped) + max(0, len(kept) - MAX_SAMPLE)
    # Income replacement receipt.
    if receipt is not None:
        rturn, rrows = receipt
        if int(rturn) != turn:
            raise RuntimeError("retail income receipt belongs to another turn")
        seen_ids = set()
        replaced = 0.0
        for aid, value in rrows:
            value = float(value)
            if int(aid) in seen_ids or not math.isfinite(value) or value < 0:
                raise RetailAccountingError("retail income receipt row is invalid")
            seen_ids.add(int(aid))
            replaced += value
        t.income = {"rows": len(seen_ids), "replaced": round(replaced, 6)}
        state.income_replaced_total = round(state.income_replaced_total + replaced, 6)
        _bump(state, "income_replaced_rows", len(seen_ids))


def _people_after(sim) -> dict[int, tuple[int, int, int]]:
    snap = sim.get_snapshot()
    cols = [_column(snap, name) for name in ("id", "region", "parent_id_0", "parent_id_1")]
    return {int(i): (int(r), int(a), int(b)) for i, r, a, b in zip(*cols)}


def _settle_deaths(world, state, t: _Turn, sim) -> None:
    """Dead owners' claims: spouse, else living children in the region, else commons."""
    owners = {aid for reg in state.regions for aid in reg.claims}
    if not owners:
        return
    alive = _people_after(sim)
    dead = sorted(aid for aid in owners if aid not in alive)
    if not dead:
        return
    if t.spouses is None:
        raise RuntimeError("household retail owners' spouses were not read before the tick")
    children: dict[tuple[int, int], list[int]] = {}
    for aid in sorted(alive):
        region, p0, p1 = alive[aid]
        for parent in {p0, p1} - {0}:
            children.setdefault((parent, region), []).append(aid)
    _bump(state, "deaths", len(dead))
    for reg in list(state.regions):
        for aid in [a for a in dead if a in reg.claims]:
            if aid not in t.spouses:
                raise RuntimeError(f"household retail owner {aid}'s spouse was not read before the tick")
            amount = reg.claims[aid]
            spouse = t.spouses[aid]
            heirs = [spouse] if spouse is not None and spouse in alive else children.get((aid, reg.region), [])
            shares = largest_remainder(amount, [(h, 1) for h in heirs]) if heirs else {}
            held = state.claims_count() - 1          # the deceased's entry closes either way
            given: dict[int, int] = {}
            for heir, share in shares.items():
                if heir in reg.claims or held < MAX_CLAIMS:
                    if heir not in reg.claims:
                        held += 1
                    given[heir] = share
            escheat = amount - sum(given.values())
            book = _book(state, world, reg)
            if given:
                reg.claims[aid] -= sum(given.values())
                for heir, share in given.items():
                    reg.claims[heir] = reg.claims.get(heir, 0) + share
                _record(book, "inherited_out", None, {aid: sum(given.values())})
                _record(book, "inherited_in", None, given)
                _bump(state, "inherited_milli", sum(given.values()))
                for heir, share in given.items():
                    _log(state, RetailRecord(turn=int(world.turn), region=reg.region, kind="inherited",
                                             milli=share, owner=aid, other=heir,
                                             note="spouse" if heirs == [spouse] else "child"))
            if escheat:
                refused = bool(shares) and len(given) < len(shares)
                if refused:
                    _bump(state, "claims_refused")
                _debit(state, world, reg, "to_commons", {aid: escheat}, _draw(reg.goods, escheat),
                       commons="escheat")
                _bump(state, "escheat_milli", escheat)
                _log(state, RetailRecord(turn=int(world.turn), region=reg.region, kind="escheat", milli=escheat,
                                         owner=aid, note="claims cap" if refused else "no heir in the region"))
            _sorted_claims(reg)


def after_agent_tick(world, agent_bridge) -> list:
    """Take this tick's frame and income receipt once, settle claims and money,
    then pass dead owners' claims on."""
    state = _state(world)
    t = _turn(state, world)
    sim = agent_bridge._sim
    turn = int(world.turn)
    if state.last_settled_turn is not None and turn <= state.last_settled_turn:
        raise RuntimeError("household retail already settled for this turn")
    installed, t.installed = t.installed, None
    if installed is not None:
        frame = sim.take_household_retail_frame()
        receipt = sim.take_retail_income_receipt() if installed.income else None
        if frame is None and receipt is None:
            # The tick never took the installs: drop them, sell nothing.
            sim.cancel_household_retail()
            if installed.income:
                sim.cancel_retail_income()
            _bump(state, "turns_not_taken")
        elif frame is None or (installed.income and receipt is None):
            raise RuntimeError("household retail frame and income receipt were not taken together")
        else:
            _settle_frame(world, state, t, installed, frame, receipt)
            _bump(state, "turns_settled")
    _settle_deaths(world, state, t, sim)
    state.last_settled_turn = turn
    t.spouses = None
    _check(state, world)
    return []


# ---------------------------------------------------------------------------
# Granary procurement seam (called from grain_reserves.tick_grain_reserves)
# ---------------------------------------------------------------------------

def procurement_owned_grain(world) -> list[float] | None:
    """Owned grain per region (food units) a pilot market may sell to its
    own ruler's granaries; None when retail holds none (the off path)."""
    state = _state(world)
    if state is None or not household_retail_active(world) or state.mode == "record_only":
        return None
    out = [0.0] * len(world.regions)
    for reg in state.regions:
        out[reg.region] = reg.goods[GRAIN] / MILLI
    return out if any(out) else None


def take_procured(world, rid: int, amount: float, flow_index: int) -> float:
    """A granary buys ``amount`` (food units) of owned grain in ``rid``: debit
    the owners pro rata to their claims (whole milli-food, rounded up, never
    above the owned grain) and record it for the Phase 10 credit. Returns the
    food units taken from owners."""
    state = _state(world)
    reg = state.region(rid)
    if reg is None or not math.isfinite(amount) or amount <= 0:
        raise RuntimeError("household retail procurement names no owned grain")
    milli = min(max(1, math.ceil(amount * MILLI - 1e-6)), reg.goods[GRAIN])
    if milli <= 0:
        raise RuntimeError("household retail procurement names no owned grain")
    taken = min(float(amount), milli / MILLI)
    per_owner = _pro_rata(milli, reg.claims)
    per_good = [milli] + [0] * (len(RETAIL_GOODS) - 1)
    _debit(state, world, reg, "procured", per_owner, per_good)
    _bump(state, "procured_milli", milli)
    t = _turn(state, world)
    t.procured.append(_Procured(flow_index=int(flow_index), region=rid, taken=taken, milli=milli, owners=per_owner))
    _check(state, world, {rid})
    return taken


def owned_grain_sold(world) -> dict[int, float]:
    """This turn's owned grain sold to granaries, per source region (food
    units): the resource ledger's market term."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != world.turn:
        return {}
    out: dict[int, float] = {}
    for p in t.procured:
        out[p.region] = out.get(p.region, 0.0) + p.taken
    return out


def _credit_procurement(world, state, t: _Turn, agent_bridge) -> dict:
    turn = int(world.turn)
    if state.last_procured_turn is not None and turn <= state.last_procured_turn:
        raise RuntimeError("household retail procurement already credited for this turn")
    from chronicler.grain_reserves_state import BOUGHT
    reserves = world.grain_reserves
    flows = reserves.flows if reserves is not None and reserves.flows_turn == turn else []
    credits: dict[int, int] = {}
    owed = 0
    for p in t.procured:
        if not 0 <= p.flow_index < len(flows):
            raise RuntimeError("household retail procurement names no purchase flow")
        f = flows[p.flow_index]
        if (f.kind != BOUGHT or f.source != p.region or f.seller != f.buyer or f.cost < 1
                or f.sent <= 0 or p.taken > f.sent * (1 + 1e-9) + 1e-9):
            raise RetailAccountingError("household retail procurement does not match its purchase flow")
        share = int(math.floor(f.cost * MILLI * min(1.0, p.taken / f.sent)))
        owed += share
        for aid, v in largest_remainder(share, p.owners.items()).items():
            credits[aid] = credits.get(aid, 0) + v
    if sum(credits.values()) != owed:
        raise RetailAccountingError("procurement credits do not sum to the owners' share")
    summary = {"flows": len(t.procured), "owed_milli": owed, "credited_milli": 0, "residual_milli": 0,
               "unpaid_milli": 0}
    _bump(state, "procurement_flows", len(t.procured))
    if state.mode == "free_exchange":
        # The control moves no money to owners: the cost stays with the old sink.
        summary["unpaid_milli"] = owed
        _bump(state, "procurement_unpaid_milli", owed)
    elif credits:
        rows = sorted(credits.items())
        got = agent_bridge._sim.transfer_wealth(turn, PURPOSE_FOOD_PROCUREMENT, PROCUREMENT_BATCH, rows)
        if len(got) != len(rows):
            raise RuntimeError("native procurement credit receipt does not match its rows")
        for (aid, amount), (gid, requested, applied, residual, _status) in zip(rows, got):
            if (int(gid), int(requested)) != (aid, amount) or int(applied) + int(residual) != amount \
                    or int(applied) < 0:
                raise RetailAccountingError("native procurement credit receipt does not balance")
            summary["credited_milli"] += int(applied)
            summary["residual_milli"] += int(residual)
        _bump(state, "procurement_credited_milli", summary["credited_milli"])
        _bump(state, "procurement_residual_milli", summary["residual_milli"])
    state.last_procured_turn = turn
    t.procured = []
    return summary


def phase10(world, acc, economy_result, agent_bridge) -> list:
    """Credit owners for grain their granaries bought (once), then close the
    turn's frame."""
    state = _state(world)
    t = _turn(state, world)
    procurement = _credit_procurement(world, state, t, agent_bridge) if t.procured else None
    _check(state, world)
    frames = []
    for rid in sorted(t.books):
        book = t.books[rid]
        reg = book.entry
        flows = {kind: sum(row) for kind, row in book.goods.items()}
        for kind in ("inherited_in", "inherited_out"):
            if book.owners.get(kind):
                flows[kind] = sum(book.owners[kind].values())
        frames.append(RegionFrame(
            region=rid, opened_turn=reg.opened_turn, open_milli=sum(book.open_goods), close_milli=sum(reg.goods),
            goods_close=list(reg.goods), owners=len(reg.claims),
            flows={k: flows[k] for k in FLOW_KINDS if flows.get(k)},
            commons={k: book.commons[k] for k in COMMONS_REASONS if book.commons.get(k)},
            price_milli=book.price_milli, free_rations=None if book.free_rations is None else round(book.free_rations, 6),
            phase2=book.phase2, provisioning=book.provisioning, would_be=book.would_be))
    _bump(state, "pilot_region_turns", len(state.regions))
    state.frame_turn = int(world.turn)
    state.frame = frames
    state.money = {**(t.money or {}), **({f"procurement_{k}": v for k, v in procurement.items()} if procurement else {})}
    state.income = dict(t.income or {})
    state.sample = list(t.sample or [])
    state.sample_dropped = t.sample_dropped
    state._turn = None
    return []


# ---------------------------------------------------------------------------
# Pool reset and snapshot
# ---------------------------------------------------------------------------

def on_pool_reset(world) -> None:
    """A rebuilt native pool: saved stable ids name other people now, so every
    claim is closed to its region's commons, dated (the regions stay in the
    pilot, sticky)."""
    state = _state(world)
    if state is None or not any(reg.claims for reg in state.regions):
        return
    _bump(state, "pool_resets")
    for reg in list(state.regions):
        total = sum(reg.goods)
        if total:
            _debit(state, world, reg, "to_commons", dict(reg.claims), list(reg.goods), commons="pool_reset")
        _log(state, RetailRecord(turn=int(world.turn), region=reg.region, kind="pool_reset", milli=total,
                                 note="native pool rebuilt: saved stable ids name other people"))
    _check(state, world)


def snapshot_summary(world) -> dict:
    """The completed turn's copied frame (never final state); None: not observed."""
    state = _state(world)
    source = world.turn - 1
    observed = state.frame_turn == source
    return {
        "schema_version": 1, "stage": "L6b", "mode": state.mode, "boundary": state.boundary,
        "source_turn": source,
        "regions": [f.model_dump() for f in state.frame] if observed else None,
        "money": dict(state.money) if observed else None,
        "income": dict(state.income) if observed else None,
        "sample": [list(row) for row in state.sample] if observed else None,
        "sample_dropped": state.sample_dropped if observed else None,
        "sample_columns": ["agent_id", "region", "household", "ration", "fair_share", "status"],
        "log": [r.model_dump() for r in state.log], "log_dropped": state.log_dropped,
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "income_replaced_total": state.income_replaced_total,
        "parameters": {"theta": 1.0 if state.mode == "no_relief" else THETA, "price_floor": PRICE_FLOOR,
                       "price_cap": PRICE_CAP, "max_claims": MAX_CLAIMS, "units": "milli_food_and_milli_wealth",
                       "goods": list(RETAIL_GOODS)},
    }
