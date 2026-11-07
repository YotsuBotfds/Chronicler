"""L6b household food retail, option R (``--household-retail``, default off).

Requires ``--agents hybrid`` and ``--food-allocation`` (L2): it extends L2's
provisioning step. Design: ``docs/integration/household-retail-design.md``;
the lead's decisions and the binding FFI contract are in the phase plan
(``docs/superpowers/roadmaps/productive-recovery-phase.md``, section 2, PL4);
integration page ``docs/integration/household-retail.md``.

Pilot boundary (``--household-retail-boundary``), sticky: ``market``
(default) adds each ruling civilization's capital region the turn it first
qualifies; ``paid_work`` adds regions that have had an open L6a firm, a
paid RS2 workshop repair crew, a paid PL3 granary crew or a PL1 expedition's
home region; ``all`` adds every controlled region; ``schedule`` (A2R) adds
each region of a frozen ``{region: opening turn}`` map
(``--household-retail-schedule``) from its turn, so an arm can replay another
arm's enrollment. A region leaves
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
creates nothing. A rebuilt native pool closes every claim to the commons.

War (``--household-retail-rules``, :data:`RULES_VERSION` for a new state; a
saved state keeps its version). Version 2: every war event that destroys the
region's commons food takes the same share of its owned stock, once per event,
at the event: a conquest (``action_engine.apply_region_conquest`` calls
:func:`on_conquest`: half of each good) and each siege turn and occupation
start (``war.occupation._requisition`` calls :func:`on_war_loss`: 15% and
20%), recorded with its cause, actor and victim. Version 1 (checkpoints 2-3):
a pilot region conquered since Phase 2 or since the agent tick loses the
conquest share once per turn (``war_loss``, inferred from
``last_conquered_turn``), and occupation and siege requisitions do not reach
owned stock (declared limit, counted).

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

Evidence (version 2, A2R): ``opened_turn`` keeps each region's first pilot
turn, so a bundle names its schedule (:func:`extract_schedule`); each
provisioned pilot region-turn records household-group cohorts (RL5,
:func:`cohorts`), exact or marked unknown; with granaries on, owned grain above
this turn's storage cap is lost to overflow before Phase 10 procurement (RL4,
:func:`phase10_before_reserves`).

Accounting: every identity of the design's section 10 that Python can see is
checked after each mutation and raised on failure (:func:`check_region`,
:func:`check_owner`, the frame checks). No randomness; every order is by
region index, stable id or good order. Parameters are declared modeling
choices, not calibrated.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from chronicler.household_retail_state import (
    BOUNDARIES, COHORT_FIELDS, COHORT_GROUPS, COMMONS_REASONS, COUNTERS, FLOW_KINDS, FLOW_SIGNS, MAX_CLAIMS,
    MAX_LOG, MAX_SAMPLE, MODES, NATIVE_MODES, RETAIL_GOODS, RULES_VERSION, WAR_CAUSES, HouseholdRetailState,
    RegionFrame, RetailRecord, RetailRegion,
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
    "priced_out_persons", "offer_short_persons", "withheld_dead_claims", "withheld_dead_milli",
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
    """Enable (with ``--household-retail-mode``, ``--household-retail-boundary``,
    ``--household-retail-rules``, default :data:`RULES_VERSION`, and for the
    ``schedule`` boundary ``--household-retail-schedule``) or disable; omitted
    options keep the saved ones. A saved state's rules version and schedule
    never change (a conflicting value is refused). Disabling, or switching to
    ``record_only``, closes every holding to its region's commons, dated."""
    mode = getattr(args, "household_retail_mode", None) if args is not None else None
    boundary = getattr(args, "household_retail_boundary", None) if args is not None else None
    rules = getattr(args, "household_retail_rules", None) if args is not None else None
    state = _state(world)
    if state is not None and rules is not None and str(rules) != state.rules:
        raise ValueError(rules_conflict(rules, state))
    requested = check_schedule_request(world, args, on=bool(value), saved=state)
    if state is None:
        version = int(rules) if rules is not None else RULES_VERSION
        world.livelihoods.household_retail = state = HouseholdRetailState(
            mode=mode or MODES[0], boundary=boundary or BOUNDARIES[0], rules_version=version,
            **({"opened_turn": {}, "intervals": {}} if version >= 2 else {}))
    else:
        if mode is not None:
            state.mode = mode
        if boundary is not None:
            state.boundary = boundary
    if requested is not None and state.schedule is None:
        state.schedule, state.schedule_sha256 = requested
    state.enabled = bool(value)
    if not state.enabled or state.mode == "record_only":
        note = "switch off" if not state.enabled else "mode record_only holds no food"
        for reg in list(state.regions):
            _close_region(world, state, reg, "switch_off", note=note)


def rules_conflict(rules, state: HouseholdRetailState) -> str:
    return (f"--household-retail-rules {rules} conflicts with the saved retail state (rules version "
            f"{state.rules_version}, which it keeps)")


# ---------------------------------------------------------------------------
# The schedule boundary (A2R)
# ---------------------------------------------------------------------------

_INDEX = re.compile(r"(0|[1-9][0-9]*)")


def canonical_schedule(schedule: dict) -> bytes:
    """A schedule's canonical JSON: ``{"<region index>": <opening turn or
    intervals>}``, compact, ascending region (an interval's open end is
    ``null``). Its SHA-256 is the schedule's digest, and the file
    :func:`write_schedule` writes holds exactly these bytes."""
    def value(v):
        return int(v) if isinstance(v, int) else [[int(a), None if b is None else int(b)] for a, b in v]
    return json.dumps({str(int(rid)): value(v) for rid, v in sorted(schedule.items())},
                      separators=(",", ":")).encode("ascii")


def schedule_digest(schedule: dict) -> str:
    return hashlib.sha256(canonical_schedule(schedule)).hexdigest()


def _turn_value(value) -> bool:
    return type(value) is int and value >= 0


def parse_schedule(data, n_regions: int) -> dict:
    """Validate a schedule: a JSON object keyed by decimal region indices whose
    values are either an opening turn (a non-negative integer: the region is
    eligible from that turn on, the approximate first-turn format) or exact
    intervals ``[[open, close], ..., [open, null]]`` (ascending, non-overlapping,
    ``open < close``, only the last may stay open: the region is eligible on the
    turns ``open <= turn < close``). Ascending region."""
    if not isinstance(data, dict):
        raise ValueError("a retail schedule is a JSON object {region index: opening turn or intervals}")
    out: dict = {}
    for key, value in data.items():
        if not isinstance(key, str) or _INDEX.fullmatch(key) is None:
            raise ValueError(f"retail schedule key {key!r} is not a region index")
        rid = int(key)
        if rid >= n_regions:
            raise ValueError(f"retail schedule names region {rid}; this world has regions 0-{n_regions - 1}")
        if isinstance(value, list):
            out[rid] = _parse_intervals(rid, value)
            continue
        if not _turn_value(value):
            raise ValueError(f"retail schedule opening turn of region {rid} must be a non-negative integer, "
                             f"not {value!r}")
        out[rid] = value
    return dict(sorted(out.items()))


def _parse_intervals(rid: int, value: list) -> list[list[int | None]]:
    if not value:
        raise ValueError(f"retail schedule intervals of region {rid} are empty")
    out: list[list[int | None]] = []
    for i, pair in enumerate(value):
        if not (isinstance(pair, list) and len(pair) == 2 and _turn_value(pair[0])
                and (pair[1] is None or (_turn_value(pair[1]) and pair[1] > pair[0]))):
            raise ValueError(f"retail schedule interval {pair!r} of region {rid} is not [open, close > open] "
                             "or [open, null]")
        if pair[1] is None and i != len(value) - 1:
            raise ValueError(f"retail schedule region {rid}: only the last interval may stay open")
        if out and pair[0] < out[-1][1]:
            raise ValueError(f"retail schedule region {rid}: intervals overlap or are out of order")
        out.append([pair[0], pair[1]])
    return out


def scheduled(value, turn: int) -> bool:
    """Whether a schedule entry (an opening turn or intervals) makes its region
    eligible on ``turn``."""
    if isinstance(value, int):
        return value <= turn
    return any(start <= turn and (end is None or turn < end) for start, end in value)


def _pairs_once(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"retail schedule repeats key {key!r}")
        seen[key] = value
    return seen


def load_schedule(path, n_regions: int) -> tuple[dict, str]:
    """Read and validate a ``--household-retail-schedule`` file; returns the
    schedule and its digest. Refused (``ValueError``) when unreadable, not
    JSON, a repeated key, an unknown region or a negative or non-integer turn."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError(f"--household-retail-schedule {path}: {exc.strerror or exc}") from None
    try:
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs_once)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"--household-retail-schedule {path} is not JSON: {exc}") from None
    try:
        schedule = parse_schedule(data, n_regions)
    except ValueError as exc:
        raise ValueError(f"--household-retail-schedule {path}: {exc}") from None
    return schedule, schedule_digest(schedule)


def schedule_conflict(path, digest: str, state: HouseholdRetailState | None) -> str:
    saved = state.schedule_sha256 if state is not None else None
    return (f"--household-retail-schedule {path} (sha256 {digest[:12]}) conflicts with the saved retail state "
            + (f"(schedule sha256 {saved[:12]}, which it keeps)" if saved else "(no schedule)"))


def check_schedule_request(world, args, *, on: bool, saved: HouseholdRetailState | None):
    """The schedule a configuration asks for, validated before any change:
    ``(schedule, digest)``, or None when no schedule file is given. Refused:
    a file without the switch or with another boundary, the ``schedule``
    boundary without a file (unless the saved state has one), an invalid file,
    and a file that differs from the saved state's schedule."""
    path = getattr(args, "household_retail_schedule", None) if args is not None else None
    given = getattr(args, "household_retail_boundary", None) if args is not None else None
    boundary = given or (saved.boundary if saved is not None else BOUNDARIES[0])
    if path is None:
        if on and boundary == "schedule" and (saved is None or saved.schedule is None):
            raise ValueError("--household-retail-boundary schedule requires --household-retail-schedule PATH "
                             "(a JSON object {region index: opening turn})")
        return None
    if not on:
        raise ValueError("--household-retail-schedule requires --household-retail")
    if boundary != "schedule":
        raise ValueError(f"--household-retail-schedule requires --household-retail-boundary schedule "
                         f"(the boundary is {boundary})")
    schedule, digest = load_schedule(path, len(world.regions))
    if saved is not None and saved.schedule_sha256 is not None and saved.schedule_sha256 != digest:
        raise ValueError(schedule_conflict(path, digest, saved))
    return schedule, digest


def schedule_resume_conflict(world, path, state: HouseholdRetailState | None) -> str | None:
    """An exact resume given ``--household-retail-schedule``: None when the
    file's schedule is the checkpoint's (by digest, wherever the file lives),
    else why it is refused."""
    try:
        _schedule, digest = load_schedule(path, len(world.regions))
    except ValueError as exc:
        return str(exc)
    if state is None or state.schedule_sha256 != digest:
        return schedule_conflict(path, digest, state)
    return None


def schedule_summary(state: HouseholdRetailState) -> dict | None:
    if state.schedule is None:
        return None
    return {"sha256": state.schedule_sha256, "turns": {str(k): v for k, v in sorted(state.schedule.items())}}


def _frame_intervals(records) -> tuple[dict[int, list[list[int | None]]], dict[int, list[int]]]:
    """Pilot intervals read from the completed-turn frames (approximate, for
    bundles without recorded intervals), and each region's framed turns. A run
    of consecutive framed turns ends at its last turn when that frame shows the
    region leaving the pilot (holdings to the commons as ``pilot_closed`` or
    ``switch_off``), else at the next turn; a run reaching the last record stays
    open. A closure with nothing held leaves no frame row, so it reads as a
    close one turn later at most."""
    last = int(records[-1]["source_turn"])
    turns: dict[int, list[int]] = {}
    closing: set[tuple[int, int]] = set()
    for record in records:
        turn = int(record["source_turn"])
        for frame in record.get("regions") or ():
            rid = int(frame["region"])
            turns.setdefault(rid, []).append(turn)
            commons = frame.get("commons") or {}
            if commons.get("pilot_closed") or commons.get("switch_off"):
                closing.add((rid, turn))
    out: dict[int, list[list[int | None]]] = {}
    for rid, ts in sorted(turns.items()):
        ts = sorted(set(ts))
        runs, first, prev = [], ts[0], ts[0]
        for turn in ts[1:]:
            if turn == prev + 1 and (rid, prev) not in closing:
                prev = turn
                continue
            runs.append((first, prev))
            first = prev = turn
        runs.append((first, prev))
        out[rid] = [[a, b if (rid, b) in closing else (None if b >= last else b + 1)] for a, b in runs]
        turns[rid] = ts
    return out, turns


def extract_schedule(bundle) -> dict:
    """The pilot schedule a bundle records, for ``--household-retail-schedule``:
    ``{"schedule": {region: [[open, close or None], ...]}, "source", "exact",
    "closures", "sha256", "regions_closed"}``. Exact (``source`` ``intervals``)
    from the last retail record's ``intervals`` (rules version 2 since S1),
    checked against the completed-turn frames; otherwise (``frames``) the
    intervals the frames imply, approximate (see :func:`_frame_intervals`).
    When ``opened_turn`` is present, each region's first interval must open
    on it. ``closures`` lists the (turn, region) pilot closures the logs show."""
    records = [s["livelihoods"]["household_retail"] for s in bundle.get("history") or []
               if isinstance(s, dict) and ((s.get("livelihoods") or {}).get("household_retail"))]
    if not records:
        raise ValueError("the bundle has no household retail record")
    derived, framed = _frame_intervals(records)
    closures = sorted({(int(r["turn"]), int(r["region"])) for record in records for r in record.get("log") or ()
                       if r.get("kind") in ("pilot_closed", "switch_off")})
    recorded = records[-1].get("intervals")
    if recorded is not None:
        schedule = {int(k): [[int(a), None if b is None else int(b)] for a, b in v] for k, v in recorded.items()}
        source = "intervals"

        def inside(rid: int, turn: int) -> bool:
            return any(a <= turn and (b is None or turn <= b) for a, b in schedule.get(rid, ()))
        disagree = sorted(rid for rid, ts in framed.items() if not all(inside(rid, t) for t in ts))
        if disagree:
            raise ValueError(f"the recorded intervals disagree with the frames for regions {disagree}")
    else:
        schedule, source = derived, "frames"
    opened = records[-1].get("opened_turn")
    if opened is not None:
        disagree = sorted(int(k) for k, v in opened.items() if not schedule.get(int(k)) or
                          schedule[int(k)][0][0] != int(v))
        if disagree:
            raise ValueError(f"opened_turn disagrees with the schedule for regions {disagree}")
    schedule = dict(sorted(schedule.items()))
    return {"schedule": schedule, "source": source, "exact": source == "intervals",
            "closures": [list(c) for c in closures], "sha256": schedule_digest(schedule),
            "regions_closed": int(records[-1].get("counters", {}).get("regions_closed", 0))}


def write_schedule(path, schedule: dict) -> str:
    """Write a schedule's canonical JSON to ``path``; returns its digest."""
    Path(path).write_bytes(canonical_schedule(schedule))
    return schedule_digest(schedule)


def household_retail_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def _v2(state: HouseholdRetailState) -> bool:
    return state.rules_version >= 2


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
    income_replaced: float | None = None
    income_rows: int | None = None
    merchant_food_departing: float | None = None
    owned_food_unloadable: int | None = None
    cohorts: dict | None = None
    cap_cut: dict | None = None


@dataclass
class _Phase2:
    turn: int
    pilots: list[int]
    theta: float
    #: region -> [(id, u, h)]: each Phase 2 farmer's urban farm-labour factor and
    #: health work loss, ascending id.
    work: dict[int, list[tuple[int, float, float]]]
    #: region -> the economy batch's final ``farm_labor_factor`` (after every
    #: earlier Phase 2 planner; 1 without the column).
    factor: dict[int, float] = field(default_factory=dict)
    #: region -> the commons food the economy batch carried (f32 values).
    commons_open: dict[int, float] = field(default_factory=dict)
    #: region -> [(id, micro-weight)] after the named crews' farm time
    #: (``finish_phase2``), ascending id.
    farmers: dict[int, list[tuple[int, int]]] = field(default_factory=dict)
    controllers: dict[int, str | None] = field(default_factory=dict)
    titled: bool = False
    #: Version 2: region -> this turn's per-good storage cap (food units, the
    #: native ``per_good_cap_factor x storage_population`` in f32), for RL4.
    cap: dict[int, float] = field(default_factory=dict)
    #: Version 2: everyone in a pilot region in the Phase 2 snapshot,
    #: ``id -> (region, age, occupation, parent_id_0, parent_id_1)`` (RL5).
    roster: dict[int, tuple[int, int, int, int, int]] | None = None


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
    #: RL4: this turn's storage-cap cut before procurement was applied (once).
    cap_cut_done: bool = False
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
    #: A4 titled trade's read of this turn's settlement (transient): per id
    #: (paid, credited, refunded), sold milli-food per (owner, region), the
    #: per-region money columns, and the procurement credits applied per id.
    money_rows: dict[int, tuple[int, int, int]] | None = None
    claim_sold: dict[tuple[int, int], int] | None = None
    region_money: dict[int, tuple[int, int, int]] | None = None
    procurement_credits: dict[int, int] | None = None


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
    if state.intervals is not None and state.intervals.get(reg.region) and state.intervals[reg.region][-1][1] is None:
        state.intervals[reg.region][-1][1] = int(world.turn)
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
    """Regions where paid work has been done, from each lane's last committed
    frame: an open L6a firm; a repair crew paid in RS2's receipts; a PL3
    granary crew paid in ``recovery_crews.receipts``; the home region of a
    PL1 woodcutting crew paid in ``timber_supply.receipts``."""
    out = set()
    lv = getattr(world, "livelihoods", None)
    payroll = getattr(lv, "workshop_payroll", None)
    if payroll is not None and payroll.enabled:
        out.update(f.region for f in payroll.firms if f.status == "open")
    repair = getattr(lv, "repair_projects", None)
    if repair is not None and repair.enabled and repair.receipts:
        out.update(r.region for r in repair.receipts if r.wages_milli > 0)
    crews = getattr(lv, "recovery_crews", None)
    if crews is not None and crews.enabled and crews.receipts:
        out.update(r.region for r in crews.receipts if r.kind == "granary" and r.wages_milli > 0)
    timber = getattr(lv, "timber_supply", None)
    if timber is not None and timber.enabled and timber.receipts:
        out.update(r.home for r in timber.receipts if r.wages_milli > 0)
    return [(rid, "paid_work") for rid in sorted(out)]


def _scheduled_regions(world, state) -> list[tuple[int, str]]:
    """The ``schedule`` boundary: every region of the frozen schedule eligible
    this turn (its opening turn has come, or this turn lies in one of its
    intervals); the controller filter and the closure of a region without a
    controller are the other boundaries'."""
    turn = int(world.turn)
    return [(rid, "schedule") for rid, value in sorted((state.schedule or {}).items()) if scheduled(value, turn)]


def _qualifying(world, state) -> list[tuple[int, str]]:
    if state.boundary == "market":
        found = _capital_regions(world)
    elif state.boundary == "paid_work":
        found = _paid_work_regions(world)
    elif state.boundary == "schedule":
        found = _scheduled_regions(world, state)
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


def _apply_conquests(world, state) -> None:
    """Version 2: :func:`_check_conquests_observed`. Version 1 (checkpoints
    2-3): a conquest destroys the conquest share of each pilot region's owned
    stock, once per conquest turn: the region's ``last_conquered_turn`` (set
    by ``action_engine.apply_region_conquest``, the path that destroys the
    market's stock, also for annexed occupations) is newer than the last loss
    applied and not before the region joined the pilot. A change of
    controller without a conquest (peaceful transfer, abandonment) destroys
    nothing. Checked before the economy and before the agent tick, so a
    conquest in any phase is applied before the next sale. Two conquests of
    one region in one turn (``--no-campaigns``) destroy it once (RL1)."""
    if _v2(state):
        _check_conquests_observed(world, state)
        return
    from chronicler.economy import CONQUEST_STOCKPILE_SURVIVAL
    for reg in state.regions:
        region = world.regions[reg.region]
        when = int(getattr(region, "last_conquered_turn", -1))
        if when < reg.opened_turn or when <= reg.war_loss_turn:
            continue
        reg.war_loss_turn = when
        per_good = [v - math.floor(v * CONQUEST_STOCKPILE_SURVIVAL) for v in reg.goods]
        total = sum(per_good)
        if total:
            _debit(state, world, reg, "war_loss", _pro_rata(total, reg.claims), per_good)
            _bump(state, "war_loss_milli", total)
        _log(state, RetailRecord(turn=int(world.turn), region=reg.region, kind="war_loss", milli=total,
                                 note=f"conquered by {region.controller} on turn {when}"))


def _check_conquests_observed(world, state) -> None:
    """Version 2: every conquest of a pilot region since it opened was applied
    by :func:`on_conquest` at the event; a ``last_conquered_turn`` newer than
    the last observed conquest is a conquest the hook never saw. In
    ``record_only`` nothing is held, so nothing was owed: the marker follows."""
    for reg in state.regions:
        when = int(getattr(world.regions[reg.region], "last_conquered_turn", -1))
        if when >= reg.opened_turn and when > reg.war_loss_turn:
            if state.mode == "record_only":
                reg.war_loss_turn = when
                continue
            raise RetailAccountingError(f"region {reg.region}: conquest on turn {when} not observed "
                                        f"(the last observed was turn {reg.war_loss_turn})")


def _war_share(goods: list[int], survival: float) -> list[int]:
    """Per good, the milli-food a war event destroys: ``v - floor(v x f)``,
    ``f`` read as its decimal value (0.85 is 17/20), so binary rounding never
    takes an extra milli; no randomness."""
    keep = Fraction(repr(float(survival)))
    if not 0 <= keep <= 1:
        raise ValueError(f"war survival factor {survival!r} is not in [0, 1]")
    return [v - (v * keep.numerator) // keep.denominator for v in goods]


def _civ(world, civ) -> tuple[int | None, str | None]:
    """A civilization (object or name) as (its index in ``world.civilizations``, its name)."""
    if civ is None:
        return None, None
    name = civ if isinstance(civ, str) else civ.name
    for i, c in enumerate(world.civilizations):
        if c is civ:
            return i, name
    return next((i for i, c in enumerate(world.civilizations) if c.name == name), None), name


def _region_index(world, region) -> int:
    for i, r in enumerate(world.regions):
        if r is region:
            return i
    names = [i for i, r in enumerate(world.regions) if r.name == region.name]
    if len(names) != 1:
        raise RetailAccountingError(f"region {region.name!r} is not one region of the world")
    return names[0]


def _war_entry(world, region) -> tuple[HouseholdRetailState, RetailRegion] | None:
    """The version-2 pilot entry a war event in ``region`` reaches, or None
    (retail off, inactive or version 1; the region outside the pilot). In
    ``record_only`` the entry holds nothing: the event is recorded with no
    loss, so a control arm keeps its war exposure (review A5, finding 2)."""
    state = _state(world)
    if state is None or not _v2(state) or not household_retail_active(world):
        return None
    reg = state.region(_region_index(world, region))
    if reg is None:
        return None
    if state.frame_turn is not None and state.frame_turn >= world.turn:
        raise RuntimeError("household retail war loss after this turn's frame was closed")
    return state, reg


def _apply_war_loss(world, state, reg: RetailRegion, survival: float, cause: str, actor, victim,
                    note: str) -> int:
    """Destroy ``v - floor(v x survival)`` of each owned good of ``reg``, claims
    pro rata (largest remainder, ties by id), once; count the event and log
    it (cause, actor and victim by index and name at the event), also when it
    destroys nothing (no owned food, or ``record_only``: milli 0)."""
    if cause not in WAR_CAUSES:
        raise ValueError(f"unknown war loss cause {cause!r}")
    book = _book(state, world, reg)
    per_good = _war_share(reg.goods, survival)
    total = sum(per_good)
    if total:
        _debit(state, world, reg, "war_loss", _pro_rata(total, reg.claims), per_good)
        _bump(state, "war_loss_milli", total)
        _bump(state, f"war_loss_{cause}_milli", total)
    reg.war_events = (reg.war_events or 0) + 1
    _bump(state, "war_events")
    # Every event is counted and logged with its cause, actor and victim, also
    # one that found nothing owned (review A5, finding 3).
    actor_id, actor_name = _civ(world, actor)
    victim_id, victim_name = _civ(world, victim)
    if state.mode == "record_only":
        note += " (record_only: nothing held)"
    _log(state, RetailRecord(turn=int(world.turn), region=reg.region, kind="war_loss", milli=total, note=note,
                             cause=cause, actor=actor_id, actor_name=actor_name,
                             victim=victim_id, victim_name=victim_name))
    check_region(reg, book)
    check_owner(reg, book)
    return total


#: How a conquest came about (``via``), for the record's note.
_CONQUEST_VIA = {
    "war": "won in war",
    "treaty": "ceded by treaty",
    "consolidated": "annexed after a long occupation",
    "owner_gone": "annexed as its former rulers vanish",
}


def on_conquest(world, region, attacker, defender, *, via: str = "war") -> int:
    """``action_engine.apply_region_conquest`` hook (version 2): the conquest
    destroys ``v - floor(v x CONQUEST_STOCKPILE_SURVIVAL)`` of each owned good
    of a pilot region at once, as it halves the commons, once per call (two
    conquests in one turn take it twice). ``via`` names the path (an aggregate
    WAR win, or an annexation: ``treaty``, ``consolidated``, ``owner_gone``).
    Returns the milli-food destroyed; a no-op outside version 2 or the pilot."""
    found = _war_entry(world, region)
    if found is None:
        return 0
    from chronicler.economy import CONQUEST_STOCKPILE_SURVIVAL
    state, reg = found
    reg.war_loss_turn = int(world.turn)
    how = _CONQUEST_VIA.get(via, via)
    _, attacker_name = _civ(world, attacker)
    _, defender_name = _civ(world, defender)
    return _apply_war_loss(world, state, reg, CONQUEST_STOCKPILE_SURVIVAL, "conquest", attacker, defender,
                           f"conquered by {attacker_name} from {defender_name} ({how})")


def on_war_loss(world, region, survival: float, *, cause: str | None, actor=None) -> int:
    """``war.occupation._requisition`` hook (version 2): a siege turn
    (``cause="siege"``) or an occupation start (``"occupation"``) destroys
    ``v - floor(v x survival)`` of each owned good of a pilot region, the share
    it takes of the commons, once per call. ``actor`` is the besieger or
    occupier; the victim is the region's ruler. Returns the milli-food
    destroyed; a no-op outside version 2 or the pilot."""
    found = _war_entry(world, region)
    if found is None:
        return 0
    if cause not in ("siege", "occupation"):
        raise ValueError(f"a requisition of owned stock needs its cause (siege or occupation), not {cause!r}")
    state, reg = found
    _, actor_name = _civ(world, actor)
    verb = "besieged" if cause == "siege" else "occupied"
    return _apply_war_loss(world, state, reg, survival, cause, actor, region.controller,
                           f"{verb} by {actor_name}")


def _update_boundary(world, state) -> None:
    if _v2(state) and state.opened_turn is None:
        # A version-2 state saved before A2R: start the map from its open regions.
        state.opened_turn = {r.region: r.opened_turn for r in sorted(state.regions, key=lambda r: r.region)}
    if _v2(state) and state.intervals is None:
        # Saved before the intervals: each open region's current interval only.
        state.intervals = {r.region: [[r.opened_turn, None]] for r in sorted(state.regions, key=lambda r: r.region)}
    for reg in list(state.regions):
        if world.regions[reg.region].controller is None:
            _close_region(world, state, reg, "pilot_closed", note="no controller")
    if state.boundary == "schedule" and state.schedule:
        # Interval schedules close a region when its interval ends (exact
        # replay); a region the schedule does not name stays (sticky).
        for reg in list(state.regions):
            value = state.schedule.get(reg.region)
            if value is not None and not scheduled(value, int(world.turn)):
                _close_region(world, state, reg, "pilot_closed", note="schedule interval ended")
    opened = False
    for rid, reason in _qualifying(world, state):
        reg = RetailRegion(region=rid, opened_turn=int(world.turn), reason=reason,
                           **({"war_events": 0} if _v2(state) else {}))
        state.regions.append(reg)
        _bump(state, "regions_opened")
        _log(state, RetailRecord(turn=int(world.turn), region=rid, kind="pilot_opened", note=reason))
        if state.opened_turn is not None and rid not in state.opened_turn:
            state.opened_turn[rid] = int(world.turn)
            opened = True
        if state.intervals is not None:
            state.intervals.setdefault(rid, []).append([int(world.turn), None])
            opened = True
    if opened:
        if state.opened_turn is not None:
            state.opened_turn = dict(sorted(state.opened_turn.items()))
        if state.intervals is not None:
            state.intervals = dict(sorted(state.intervals.items()))
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


def title_inputs(world, snapshot, regions) -> dict[int, list[tuple[int, float, float]]]:
    """Each pilot region's Phase 2 farmers with ``u_i`` (the urban farm-labour
    factor) and ``h_i`` (health work loss), ascending id."""
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
    out: dict[int, list[tuple[int, float, float]]] = {rid: [] for rid in sorted(wanted)}
    for aid in sorted(people):
        region, occupation, _age, settlement = people[aid]
        if region not in wanted or occupation != FARMER:
            continue
        city = rank.get((region, settlement))
        u = float(URBAN_FARM_LABOR[city]) if city is not None else 1.0
        h = 0.0 if city is not None else min(1.0, max(0.0, losses.get(aid, 0.0)))
        out[region].append((aid, u, h))
    return out


def weights_after_crews(work, removed=None) -> dict[int, list[tuple[int, int]]]:
    """Food-work weights ``w_i = max(0, u_i (1 - h_i) - r_i)`` in integer
    micro-units, where ``r_i`` is the farm time person ``i`` gave a named crew
    this turn (``removed``; the time is paid as a wage, never also titled)."""
    removed = removed or {}
    return {rid: [(aid, int(round(max(0.0, u * (1.0 - h) - removed.get(aid, 0.0)) * 1_000_000)))
                  for aid, u, h in rows] for rid, rows in work.items()}


def title_weights(world, snapshot, regions, removed=None) -> dict[int, list[tuple[int, int]]]:
    """Each pilot region's Phase 2 farmers and their food work after crews."""
    return weights_after_crews(title_inputs(world, snapshot, regions), removed)


def crew_farm_time(world, p2: "_Phase2", economy_result) -> tuple[dict[int, float], dict[int, float]]:
    """This turn's farm time given to named crews by pilot farmers, by id, and
    the named granary crews' farm time by region:

    * PL1 woodcutters (``timber_supply``): each crew member's farm share
      (``u_i``), scaled by the native ``woodcut_labor_away`` delivered over the
      expeditions' requests from that home region;
    * PL3 granary crews (``recovery_crews``): each member's worked share of
      the delivered storage work (``granary_shares``);
    * PL3 workshop crews: each member's farm time removed through
      ``farm_labor_factor``.

    The crews are planned earlier in Phase 2 and their receipts staged by the
    packages' own ``finish_phase2`` before this one (switch order)."""
    turn = int(world.turn)
    lv = getattr(world, "livelihoods", None)
    u_of = {aid: u for rows in p2.work.values() for aid, u, _h in rows}
    removed: dict[int, float] = {}
    granary: dict[int, float] = {}
    ts = getattr(lv, "timber_supply", None)
    tt = getattr(ts, "_turn", None) if ts is not None else None
    if tt is not None and tt.turn == turn:
        delivered = getattr(economy_result, "woodcut_labor_away_delivered", None) or {}
        by_home: dict[int, list] = {}
        for rec in tt.receipts:
            if rec.home in p2.work and rec.crew:
                by_home.setdefault(rec.home, []).append(rec)
        for home, recs in sorted(by_home.items()):
            requested = math.fsum(r.away_requested for r in recs)
            crew = [a for r in recs for a in r.crew]
            if abs(math.fsum(u_of.get(a, 0.0) for a in crew) - requested) > 1e-4 * max(1, len(crew)):
                raise RetailAccountingError(f"region {home}: woodcut crews' farm shares differ from their request")
            got = float(delivered.get(home, 0.0))
            scale = min(1.0, got / requested) if requested > 0 else 0.0
            for a in crew:
                if a in u_of:
                    removed[a] = removed.get(a, 0.0) + u_of[a] * scale
    rc = getattr(lv, "recovery_crews", None)
    rt = getattr(rc, "_turn", None) if rc is not None else None
    if rt is not None and rt.turn == turn:
        for rec in rt.receipts:
            if rec.region not in p2.work:
                continue
            for m in rec.members:
                if m.farm_time > 0:
                    removed[m.agent_id] = removed.get(m.agent_id, 0.0) + float(m.farm_time)
                    if rec.kind == "granary":
                        granary[rec.region] = granary.get(rec.region, 0.0) + float(m.farm_time)
    return removed, granary


def check_farm_labour(world, p2: "_Phase2", economy_result, removed, granary) -> None:
    """Sum of title weights == the economy's farm labour after the crews' farm
    time, per pilot region: ``sum(u_i (1 - h_i) - r_i)`` against ``farmers x
    farm_labor_factor - health loss - named granary work - woodcut labour
    away`` (anonymous storage work shrinks every title equally and is not a
    person's)."""
    wood = getattr(economy_result, "woodcut_labor_away_delivered", None) or {}
    storage = getattr(economy_result, "granary_work_delivered", None) or {}
    for rid, named in sorted(granary.items()):
        if named > float(storage.get(rid, 0.0)) + 1e-4:
            raise RetailAccountingError(
                f"region {rid}: granary crews' farm time {named:.6f} exceeds the storage work delivered")
    for rid, rows in p2.work.items():
        got = math.fsum(u * (1.0 - h) - removed.get(aid, 0.0) for aid, u, h in rows)
        health = math.fsum(h for _aid, _u, h in rows)
        expect = (len(rows) * p2.factor.get(rid, 1.0) - health - granary.get(rid, 0.0)
                  - float(wood.get(rid, 0.0)))
        if abs(got - expect) > 1e-3 + 1e-5 * len(rows):
            raise RetailAccountingError(
                f"region {rid}: title weights {got:.6f} differ from the farm labour after crews {expect:.6f}")


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


def _storage_caps(world, region_input, pilots) -> dict[int, float]:
    """This turn's per-good storage cap of each pilot region, as the native
    economy computes it from the batch: ``per_good_cap_factor x
    storage_population`` in f32 (food units)."""
    from numpy import float32
    from chronicler.economy import PER_GOOD_CAP_FACTOR
    from chronicler.tuning import get_override
    factor = float32(get_override(world, "economy.per_good_cap_factor", PER_GOOD_CAP_FACTOR))
    names = list(region_input.schema.names)
    if "storage_population" not in names:
        return {}
    pops = region_input.column(names.index("storage_population")).to_pylist()
    return {rid: float(factor * float32(pops[rid])) for rid in pilots}


def _roster(snapshot, pilots) -> dict[int, tuple[int, int, int, int, int]]:
    """Everyone in a pilot region in the Phase 2 snapshot (RL5): the people
    provisioned there at phase 0.7 are these, less any who die before it."""
    wanted = set(pilots)
    names = ("id", "region", "age", "occupation", "parent_id_0", "parent_id_1")
    cols = [_column(snapshot, name) for name in names]
    return {int(i): (int(r), int(a), int(o), int(p0), int(p1)) for i, r, a, o, p0, p1 in zip(*cols)
            if int(r) in wanted}


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Boundary, title weights and (unless record_only) the optional economy
    columns: ``retail_title_share`` (THETA; null outside the pilot) and
    ``retail_owned_<good>`` (owned stock at opening, food units)."""
    state = _state(world)
    t = _turn(state, world)
    if t.phase2 is not None:
        raise RuntimeError("household retail Phase 2 already prepared this turn")
    _update_boundary(world, state)
    _apply_conquests(world, state)                 # a conquest after the last agent tick
    if t.touched:
        region_input = _patch_stockpiles(world, region_input, sorted(t.touched))
        t.touched.clear()
    pilots = [r.region for r in state.regions]
    theta = 1.0 if state.mode == "no_relief" else THETA
    names = list(region_input.schema.names)
    factors = (region_input.column(names.index("farm_labor_factor")).to_pylist()
               if "farm_labor_factor" in names else None)
    stock = {good: region_input.column(names.index(f"stockpile_{good}")).to_pylist() for good in RETAIL_GOODS}
    t.phase2 = _Phase2(turn=int(world.turn), pilots=pilots, theta=theta,
                       work=title_inputs(world, snapshot, pilots),
                       factor={rid: float(factors[rid]) if factors is not None else 1.0 for rid in pilots},
                       commons_open={rid: math.fsum(float(stock[g][rid]) for g in RETAIL_GOODS) for rid in pilots})
    if _v2(state) and pilots and state.mode != "record_only":
        t.phase2.cap = _storage_caps(world, region_input, pilots)
        t.phase2.roster = _roster(snapshot, pilots)
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
    # Named crews' farm time is paid as a wage, never also titled (design 3.1).
    removed, granary = crew_farm_time(world, p2, economy_result)
    check_farm_labour(world, p2, economy_result, removed, granary)
    p2.farmers = weights_after_crews(p2.work, removed)
    crew = [aid for rows in p2.work.values() for aid, _u, _h in rows if removed.get(aid, 0.0) > 0]
    _bump(state, "crew_farm_time_person_turns", len(crew))
    _bump(state, "crew_farm_time_micro", int(round(math.fsum(removed.get(a, 0.0) for a in crew) * 1_000_000)))
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
        _check_food_ledger(world, p2, reg, row, economy_result)
        _title_region(world, state, t, reg, row)
    _check(state, world)
    return []


def _check_food_ledger(world, p2: "_Phase2", reg: RetailRegion, row: dict, economy_result) -> None:
    """Design 10, native Phase 2 in a pilot region (food units): the native food
    ledger closes, its opening is the commons sent plus the owned stock sent,
    and its closing is the commons returned plus the owned close. Skipped when
    the extension exports no ledger (unknown, not zero)."""
    ledger = (getattr(economy_result, "food_ledger", None) or {}).get(reg.region)
    if ledger is None:
        return
    from numpy import float32
    from chronicler.food_accounting import FOOD_LEDGER_FIELDS
    f = dict(zip(FOOD_LEDGER_FIELDS, (float(v) for v in ledger)))
    terms = [f["opening"], f["produced"], f["transport_net"], -f["craft_input"], f["clamp_correction"],
             -f["consumed"], -f["storage_loss"], -f["cap_overflow"]]
    scale = max(1.0, math.fsum(abs(v) for v in terms))
    owned_open = math.fsum(float(float32(v / MILLI)) for v in reg.goods)
    commons_close = math.fsum(float(world.regions[reg.region].stockpile.goods.get(g, 0.0)) for g in RETAIL_GOODS)
    owned_close = math.fsum(float(row[f"retail_owned_close_{g}"]) for g in RETAIL_GOODS)
    checks = ((f["closing"] - math.fsum(terms), "the native food ledger does not close"),
              (f["opening"] - p2.commons_open.get(reg.region, 0.0) - owned_open,
               "the food ledger's opening is not the commons plus the owned stock sent"),
              (f["closing"] - commons_close - owned_close,
               "the food ledger's closing is not the commons plus the owned close"))
    for residual, message in checks:
        if abs(residual) > 1e-5 * scale:
            raise RetailAccountingError(f"region {reg.region}: {message} (residual {residual:.6g})")


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
    # Decay, then storage overflow, fall on the stock carried into the turn:
    # the native applies both before this turn's title (which is on offer
    # whole at phase 0.7). Per good as the native reports (whole milli, never
    # above the stock), on the opening claims pro rata.
    held = dict(reg.claims)
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
    credits, pseudo = _split_title(state, t, rid, titled, reg)
    # Title: goods by good, claims by owner (pseudo-owners for what stays commons).
    for aid, v in credits.items():
        reg.claims[aid] = reg.claims.get(aid, 0) + v
    for g, v in enumerate(titled):
        reg.goods[g] += v
    _record(book, "titled", titled, {**credits, **{k: v for k, v in pseudo.items() if v}})
    _bump(state, "titled_milli", sum(credits.values()))
    _bump(state, "untitled_milli", pseudo[UNTITLED])
    if pseudo[REFUSED]:
        _bump(state, "claims_refused", 1)
        _log(state, RetailRecord(turn=int(world.turn), region=rid, kind="claims_refused",
                                 milli=pseudo[REFUSED], note="claims cap"))
    _bump(state, "owners_titled", len(credits))
    # The native owned close agrees within f32 and milli rounding (Python is
    # authoritative; it re-sends its own totals every turn, so nothing drifts).
    for g, good in enumerate(RETAIL_GOODS):
        native = float(row[f"retail_owned_close_{good}"]) * MILLI
        slack = OWNED_TOL_MILLI + 2e-5 * max(native, float(reg.goods[g]))
        if not native - slack <= reg.goods[g] <= native + slack:
            raise RetailAccountingError(f"region {rid}: owned {good} {reg.goods[g]} differs from native {native:.3f}")
    # What stays commons (this turn's title nobody holds) leaves the pool
    # whole, pro rata to the mix.
    for key, reason in _PSEUDO.items():
        left = pseudo.get(key, 0)
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
    # Conquest (this turn's war phase): version 1 applies the conquest share of
    # owned stock now; version 2 applied it at the event and checks it saw it.
    _apply_conquests(world, state)
    if not _v2(state):
        # Version 1's declared limit: occupation and siege requisitions do not
        # reach owned stock (version 2 applies them at the event).
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


def _settle_frame(world, state, t: _Turn, installed: _Installed, frame, receipt, alive=None) -> None:
    """``alive``: stable ids alive after the tick (the post-tick snapshot)."""
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
    if seen != set(installed.claims):
        raise RuntimeError("household retail frame lacks the row of an installed claim")
    eaten_or_sold = {(aid, rid) for rid in installed.regions for aid in (*eaten[rid], *sold[rid])}
    if alive is None:
        raise RuntimeError("household retail settlement requires the post-tick people")
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
        # A claim whose owner died before provisioning is withheld whole (its row
        # reads 0, 0; it stays in the offer and counts as unsold) and is
        # inherited after the tick. The withheld claims must be exactly some of
        # the zero rows of owners dead after the tick: natural deaths come after
        # phase 0.7, so a dead owner may also have been alive to sell.
        dead_zero = [v for (aid, reg), v in sorted(installed.claims.items())
                     if reg == rid and aid not in alive and (aid, reg) not in eaten_or_sold]
        ints = {k: r[k] for k in ("price_milli", "offered_milli", "own_eaten_milli", "sold_milli", "unsold_milli",
                                   "paid_milli", "credited_milli", "refunded_milli", "withheld_dead_claims",
                                   "withheld_dead_milli")}
        if any(v != math.floor(v) or v < 0 for v in ints.values()):
            raise RetailAccountingError(f"region {rid}: provisioning milli columns are not whole")
        checks = (
            (int(r["price_milli"]) == price, "price differs from the install"),
            (abs(r["free_rations"] - free) <= RATION_TOL * max(1.0, free), "free rations differ from the install"),
            (abs(r["free_given"] + r["free_unallocated"] - r["free_rations"]) <= RATION_TOL * max(1.0, free),
             "free_given + free_unallocated != free_rations"),
            (min(r["free_given"], r["free_unallocated"]) >= -RATION_TOL, "negative free rations"),
            (int(r["offered_milli"]) == offered, "offered differs from the installed claims"),
            (int(r["withheld_dead_milli"]) <= int(r["unsold_milli"]), "withheld dead claims exceed the unsold"),
            (_exact_subset(dead_zero, int(r["withheld_dead_claims"]), int(r["withheld_dead_milli"])),
             "withheld dead claims are not the claims of owners dead before selling"),
            (int(r["own_eaten_milli"]) == own and int(r["sold_milli"]) == sale, "claim rows differ from the totals"),
            (own + sale == offered - int(r["unsold_milli"]), "own_eaten + sold != offered - unsold"),
            (int(r["paid_milli"]) == int(r["credited_milli"]) + int(r["refunded_milli"]), "payments do not balance"),
            # Each buying household pays ceil(bought x price / ration): paid is
            # at least sold x price / ration and exceeds it by under one milli-unit
            # per household.
            (sale * price <= int(r["paid_milli"]) * ration_milli
             <= sale * price + int(r.get("buying_households", r["persons"])) * ration_milli,
             "paid differs from sold x price / ration beyond per-household rounding"),
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
    t.money_rows = {int(a): (int(p), int(c), int(r)) for a, p, c, r in money_rows}
    t.claim_sold = {(o, rid): v for rid in sold for o, v in sold[rid].items()}
    t.region_money = {rid: (int(r["paid_milli"]), int(r["credited_milli"]), int(r["refunded_milli"]))
                      for rid, r in by_region.items()}
    kept = []
    for aid, region, household, ration, fair, status in sample:
        if int(region) not in by_region or int(status) not in (0, 1, 2, 3) or \
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
        # Per region (design 9.2): a Phase 2 farmer's pilot region, else where
        # the person lives after the tick when that is a pilot region.
        region_of = {aid: rid for rid, rows in (t.phase2.work if t.phase2 is not None else {}).items()
                     for aid, _u, _h in rows}
        per_region: dict[int, list] = {}
        unattributed = 0.0
        for aid, value in rrows:
            value = float(value)
            if int(aid) in seen_ids or not math.isfinite(value) or value < 0:
                raise RetailAccountingError("retail income receipt row is invalid")
            seen_ids.add(int(aid))
            replaced += value
            rid = region_of.get(int(aid))
            if rid is None and alive is not None and int(aid) in alive and alive[int(aid)][0] in by_region:
                rid = alive[int(aid)][0]
            if rid is None:
                unattributed += value
            else:
                cell = per_region.setdefault(rid, [0.0, 0])
                cell[0] += value
                cell[1] += 1
        for rid, (value, rows_) in per_region.items():
            reg = state.region(rid)
            if reg is not None:
                book = _book(state, world, reg)
                book.income_replaced, book.income_rows = round(value, 6), rows_
        t.income = {"rows": len(seen_ids), "replaced": round(replaced, 6),
                    "unattributed": round(unattributed, 6)}
        state.income_replaced_total = round(state.income_replaced_total + replaced, 6)
        _bump(state, "income_replaced_rows", len(seen_ids))
    roster = t.phase2.roster if t.phase2 is not None and t.phase2.turn == turn else None
    if _v2(state) and roster is not None:
        # RL5: household-group cohorts (aggregates only; exact or unknown).
        income = {rid: t.books[rid].income_replaced or 0.0 for rid in by_region}
        for rid, record in cohorts(world, roster, by_region, money_rows, claim_rows, sample, receipt, alive,
                                   income).items():
            t.books[rid].cohorts = record


# ---------------------------------------------------------------------------
# RL5: household-group cohorts (version 2)
# ---------------------------------------------------------------------------

#: Groups whose members' classification depends on a parent's presence.
_CHILD_DEPENDENT = ("crew_children", "children_alone", "other")


def _crews(world) -> tuple[set[int], dict[int, int | None], list[tuple[list[int], int | None]]]:
    """This turn's named crews, from the packages' staged receipts (Phase 2,
    before their Phase 10 commit and its row cap): every member, the wage of
    each PL3 member (recorded per person), and the (crew, wages applied) of
    each PL1 expedition and RS2 repair receipt (recorded per crew). L6a firm
    workers are not crews here: the payroll pays owed wages pro rata to firm
    cash, former workers included, at Phase 10, and records no per-person split.
    A receipt without a wage field gives None (unknown, not zero)."""
    turn = int(world.turn)
    lv = getattr(world, "livelihoods", None)
    members: set[int] = set()
    wage: dict[int, int | None] = {}
    crews: list[tuple[list[int], int | None]] = []

    def staged(name):
        sub = getattr(lv, name, None)
        t = getattr(sub, "_turn", None) if sub is not None else None
        return t.receipts if t is not None and getattr(t, "turn", None) == turn else ()

    for rec in staged("recovery_crews"):
        for m in rec.members:
            aid = int(m.agent_id)
            members.add(aid)
            got = getattr(m, "wage_milli", None)
            before = wage.get(aid, 0)
            wage[aid] = None if got is None or before is None else before + int(got)
    for name in ("timber_supply", "repair_projects"):
        for rec in staged(name):
            crew = sorted({int(a) for a in rec.crew})
            members.update(crew)
            if crew:
                got = getattr(rec, "wages_milli", None)
                crews.append((crew, None if got is None else int(got)))
    return members, wage, crews


def cohort_group(aid: int, roster: dict, members: set[int], alive) -> tuple[str, bool]:
    """A provisioned person's household group (``COHORT_GROUPS``) from the
    Phase 2 roster, and whether it is certain at phase 0.7:

    * ``crew``: named on one of this turn's crews (any age);
    * ``crew_children``: a child (under ``ADULT_AGE``) with a crew parent in
      the region;
    * ``children_alone``: a child with no adult parent in the region (L2's
      household of its own: its members pay for it);
    * ``nonfarm_adults``: an adult off the crews who is not a farmer;
    * ``other``: an adult farmer off the crews, or a child living with an
      adult parent, none of them on a crew.

    A child's group is uncertain when an adult parent in the region is not
    alive after the tick: the parent may have died before provisioning."""
    region, age, occupation, p0, p1 = roster[aid]
    if aid in members:
        return "crew", True
    if age < ADULT_AGE:
        parents = [p for p in (p0, p1) if p and p in roster and roster[p][0] == region
                   and roster[p][1] >= ADULT_AGE]
        certain = all(p in alive for p in parents)
        if any(p in members for p in parents):
            return "crew_children", certain
        return ("other" if parents else "children_alone"), certain
    return ("nonfarm_adults" if occupation != FARMER else "other"), True


def cohorts(world, roster, by_region: dict[int, dict], money_rows, claim_rows, sample, receipt, alive,
            income_by_region: dict[int, float]) -> dict[int, dict]:
    """RL5: per provisioned pilot region, the household groups of the people
    provisioned there (``COHORT_GROUPS``): persons, priced out, money paid,
    refunded and credited, ordinary farm income replaced and crew wages.
    Aggregates only; no id leaves.

    Everything is exact or None (unknown, never zero), with the reasons in
    ``unknown``. The people provisioned in a region at phase 0.7 are its Phase
    2 roster less those who die before provisioning (nobody moves in between).
    Persons are exact when the roster's count equals the frame's ``persons``
    (and its children ``children``); priced out when the native sample holds
    every priced-out person of the region and each one's group is certain.
    Money, income and wages are per person (money rows, the income receipt,
    PL3 wages; PL1 and RS2 wages per crew, attributed when the whole crew
    lives in one region); a group's sum is unknown when a person whose group
    is uncertain contributes to it. ``paid``/``refunded`` are by the payer's
    region and must equal the region's totals; ``credited`` is by the region of
    the claim sold, to the seller's group (``credited_outside_milli``: sellers
    provisioned in no pilot region), and must equal the region's total. A
    seller who sold claims of several regions has one money row: the region's
    part is its credit less its one-region sellers', attributed when all such
    sellers of the region share a group. Income must equal the region's income
    replaced. A check that fails makes that field unknown."""
    members, wage, crews = _crews(world)
    region_of = {aid: info[0] for aid, info in roster.items()}
    groups: dict[int, tuple[str, bool]] = {aid: cohort_group(aid, roster, members, alive) for aid in roster}
    out: dict[int, dict] = {}
    acc = {rid: {g: dict.fromkeys(COHORT_FIELDS, 0) for g in COHORT_GROUPS} for rid in by_region}
    for rec in acc.values():
        for g in rec.values():
            g["income_replaced"] = 0.0
    unknown: dict[int, dict[str, str]] = {rid: {} for rid in by_region}
    shaky: dict[int, set[str]] = {rid: set() for rid in by_region}    # fields an uncertain person touched
    outside = dict.fromkeys(by_region, 0)

    def add(rid, aid, name, value):
        if rid not in acc or not value:
            return
        group, certain = groups[aid] if aid in groups else ("other", False)
        acc[rid][group][name] += value
        if not certain:
            shaky[rid].add(name)

    # Persons and priced out.
    residents: dict[int, list[int]] = {rid: [] for rid in by_region}
    for aid, rid in region_of.items():
        if rid in residents:
            residents[rid].append(aid)
    priced: dict[int, list[int]] = {rid: [] for rid in by_region}
    for aid, region, _household, _ration, _fair, status in sample:
        if int(status) == 1 and int(region) in priced:
            priced[int(region)].append(int(aid))
    for rid, row in by_region.items():
        ids = residents[rid]
        children = sum(1 for aid in ids if roster[aid][1] < ADULT_AGE)
        n2 = row.get("phase2_alive")
        if len(ids) != int(row["persons"]) or ("children" in row and children != int(row["children"])) \
                or (n2 is not None and len(ids) != int(n2)):
            unknown[rid]["persons"] = (f"the Phase 2 roster lists {len(ids)}, the tick provisioned "
                                       f"{int(row['persons'])}: who died before provisioning is not recorded")
        else:
            for aid in ids:
                acc[rid][groups[aid][0]]["persons"] += 1
        out_po = priced[rid]
        if len(out_po) != int(row["priced_out_persons"]):
            unknown[rid]["priced_out"] = (f"the native sample holds {len(out_po)} of "
                                          f"{int(row['priced_out_persons'])} priced-out persons")
        elif any(aid not in groups or region_of[aid] != rid or not groups[aid][1] for aid in out_po):
            unknown[rid]["priced_out"] = "a priced-out person's group is uncertain"
        else:
            for aid in out_po:
                acc[rid][groups[aid][0]]["priced_out"] += 1
    # Money: paid and refunded where the payer lives; credited where the claim was sold.
    sold_in: dict[int, set[int]] = {}
    for owner, region, _own, sale in claim_rows:
        if int(sale) > 0:
            sold_in.setdefault(int(owner), set()).add(int(region))
    single = dict.fromkeys(by_region, 0)          # credits of sellers who sold in one region only
    for aid, paid, credited, refunded in money_rows:
        aid, paid, credited, refunded = int(aid), int(paid), int(credited), int(refunded)
        if paid or refunded:
            rid = region_of.get(aid)
            add(rid, aid, "paid_milli", paid)
            add(rid, aid, "refunded_milli", refunded)
        regions = sold_in.get(aid, set())
        if credited and len(regions) == 1:
            (rid,) = regions
            if rid in single:
                single[rid] += credited
            if aid in groups:
                add(rid, aid, "credited_milli", credited)
            elif rid in outside:
                outside[rid] += credited
    # A seller who sold claims of several regions has one money row: what each
    # region paid them is the region's credit less its one-region sellers'
    # credits, exact as a total, and belongs to one group when every such
    # seller of the region is of that group (or provisioned in no pilot region).
    for rid in by_region:
        several = sorted(aid for aid, regions in sold_in.items() if rid in regions and len(regions) > 1)
        rest = int(by_region[rid]["credited_milli"]) - single[rid]
        if not several:
            continue
        kinds = {groups[aid] if aid in groups else ("outside", True) for aid in several}
        if rest < 0 or len(kinds) != 1:
            unknown[rid]["credited_milli"] = ("sellers of several groups also sold claims of other regions this turn"
                                              if rest >= 0 else "the region's credit is less than its one-region sellers'")
            continue
        (group, certain), = kinds
        if group == "outside":
            outside[rid] += rest
        elif rest:
            acc[rid][group]["credited_milli"] += rest
            if not certain:
                shaky[rid].add("credited_milli")
    # Ordinary farm income replaced, by the farmer's Phase 2 region.
    for aid, value in (receipt[1] if receipt is not None else ()):
        add(region_of.get(int(aid)), int(aid), "income_replaced", float(value))
    # Crew wages: PL3 per member; PL1 and RS2 per crew, when the crew lives in one region.
    for aid, amount in wage.items():
        if amount is None:
            if region_of.get(aid) in unknown:
                unknown[region_of[aid]]["wages_milli"] = "a crew receipt records no wage"
            continue
        add(region_of.get(aid), aid, "wages_milli", amount)
    for crew, amount in crews:
        homes = {region_of.get(a) for a in crew}
        if amount is None:
            for rid in homes & set(by_region):
                unknown[rid]["wages_milli"] = "a crew receipt records no wage"
            continue
        if not amount:
            continue
        if len(homes) == 1:
            add(next(iter(homes)), crew[0], "wages_milli", amount)
        else:
            for rid in homes & set(by_region):
                unknown[rid]["wages_milli"] = "a paid crew's members live in several regions"
    for rid, row in by_region.items():
        rec, why = acc[rid], unknown[rid]
        totals = {name: sum(rec[g][name] for g in COHORT_GROUPS) for name in COHORT_FIELDS}
        for name, column in (("paid_milli", "paid_milli"), ("refunded_milli", "refunded_milli")):
            if name not in why and totals[name] != int(row[column]):
                why[name] = f"its groups sum to {totals[name]}, the region's total is {int(row[column])}"
        if "credited_milli" not in why and totals["credited_milli"] + outside[rid] != int(row["credited_milli"]):
            why["credited_milli"] = (f"its groups and outside sellers sum to {totals['credited_milli'] + outside[rid]},"
                                     f" the region's total is {int(row['credited_milli'])}")
        expect = income_by_region.get(rid, 0.0)
        if "income_replaced" not in why and abs(totals["income_replaced"] - expect) > 1e-6 * max(1.0, expect):
            why["income_replaced"] = f"its groups sum to {totals['income_replaced']:.6f}, the region's is {expect:.6f}"
        groups_out = {}
        for g in COHORT_GROUPS:
            cell = {}
            for name in COHORT_FIELDS:
                value = rec[g][name]
                if name in why or (name in shaky[rid] and g in _CHILD_DEPENDENT):
                    value = None
                elif name == "income_replaced":
                    value = round(value, 6)
                cell[name] = value
            groups_out[g] = cell
        outside_milli = None if "credited_milli" in why else outside[rid]
        for name in sorted(shaky[rid] - set(why)):
            why[name] = ("unknown for the children's and other groups: a child whose parent may have died "
                         "before provisioning contributes to it")
        out[rid] = {"groups": groups_out, "credited_outside_milli": outside_milli,
                    "unknown": {k: why[k] for k in COHORT_FIELDS if k in why}}
    return out


def _exact_subset(values: list[int], count: int, total: int) -> bool:
    """Whether exactly ``count`` of ``values`` sum to exactly ``total``."""
    if count < 0 or total < 0 or count > len(values):
        return False
    reach: dict[int, set[int]] = {0: {0}}
    for v in values:
        for k in sorted(reach, reverse=True):
            if k < count:
                reach.setdefault(k + 1, set()).update(t + v for t in reach[k] if t + v <= total)
    return total in reach.get(count, set())


def _people_after(sim) -> dict[int, tuple[int, int, int]]:
    snap = sim.get_snapshot()
    cols = [_column(snap, name) for name in ("id", "region", "parent_id_0", "parent_id_1")]
    return {int(i): (int(r), int(a), int(b)) for i, r, a, b in zip(*cols)}


def _settle_deaths(world, state, t: _Turn, sim, alive=None) -> None:
    """Dead owners' claims: spouse, else living children in the region, else commons."""
    owners = {aid for reg in state.regions for aid in reg.claims}
    if not owners:
        return
    alive = _people_after(sim) if alive is None else alive
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
    alive = None
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
            alive = _people_after(sim)
            _settle_frame(world, state, t, installed, frame, receipt, alive)
            _bump(state, "turns_settled")
    _settle_deaths(world, state, t, sim, alive)
    state.last_settled_turn = turn
    t.spouses = None
    _check(state, world)
    return []


# ---------------------------------------------------------------------------
# Granary procurement seam (called from grain_reserves.tick_grain_reserves)
# ---------------------------------------------------------------------------

def procurement_owned_grain(world) -> list[float] | None:
    """Owned grain per region (food units) a pilot market may sell to its
    own ruler's granaries; None when retail holds none (the off path). Under
    rules version 2 it is already within this turn's storage cap
    (:func:`phase10_before_reserves`, RL4)."""
    state = _state(world)
    if state is None or not household_retail_active(world) or state.mode == "record_only":
        return None
    out = [0.0] * len(world.regions)
    for reg in state.regions:
        out[reg.region] = reg.goods[GRAIN] / MILLI
    return out if any(out) else None


def phase10_before_reserves(world, acc, economy_result, agent_bridge) -> list:
    """RL4, rules version 2 with granaries on: before Phase 10 procurement, a
    pilot market holding owned grain whose grain (commons plus owned) exceeds
    this turn's storage cap loses the excess, split pro rata between the two
    pools as the native opening cap splits it (each keeps ``pool x cap /
    (net commons + owned)``; owned in whole milli, rounded down), once per
    turn. As in the native cap, the commons count net of the grain merchants
    have committed to load or carry out (the native stockpile commitments,
    read without draining them; none without an agent bridge), and that
    committed grain is never cut: the departures still fit.

    This turn's title is on offer whole at phase 0.7 and the native caps the
    two pools together only at the next opening; between the tick and that
    opening a granary could otherwise buy grain the cap destroys (grain is
    fungible: any purchase from a pool above the cap shrinks the later cut by
    as much), so a pilot market could sell more than its storage holds. The
    owned loss is the frame's ``cap_overflow`` flow and the counter
    ``owned_grain_above_cap_milli``; the commons' share leaves
    ``region.stockpile`` and is counted in ``commons_grain_above_cap_milli``;
    both are on the frame's ``cap_cut``. The cut comes before the next
    opening's decay (the native decays the carried stock first, then caps),
    and fires whether or not a granary then buys there. Version 1,
    ``record_only``, runs without granaries (nothing can buy it) and markets
    without owned grain leave the cut to the next opening, as at checkpoints
    2-3."""
    state = _state(world)
    if state is None or not _v2(state) or state.mode == "record_only" or not state.regions:
        return []
    from chronicler.grain_reserves import grain_reserves_active
    if not grain_reserves_active(world):
        return []
    t = _turn(state, world)
    if t.cap_cut_done:
        return []
    t.cap_cut_done = True
    caps = t.phase2.cap if t.phase2 is not None and t.phase2.turn == world.turn else {}
    committed = None
    for reg in state.regions:
        owned = reg.goods[GRAIN]
        if not owned:
            continue
        cap = _storage_cap(world, reg.region, caps.get(reg.region))
        goods = world.regions[reg.region].stockpile.goods
        commons = float(goods.get("grain", 0.0))
        if owned / MILLI + commons <= cap + 1e-9:
            continue
        if committed is None:
            committed = _grain_committed(world, agent_bridge)
        held = min(commons, committed.get(reg.region, 0.0))
        net = commons - held
        total = owned / MILLI + net
        if total <= cap + 1e-9:
            continue
        keep_owned = min(owned, math.floor(owned * cap / total + 1e-9))
        keep_net = min(net, max(0.0, cap - keep_owned / MILLI))
        owned_cut, commons_cut = owned - keep_owned, net - keep_net
        if owned_cut:
            per_good = [owned_cut] + [0] * (len(RETAIL_GOODS) - 1)
            _debit(state, world, reg, "cap_overflow", _pro_rata(owned_cut, reg.claims), per_good)
            _bump(state, "owned_grain_above_cap_milli", owned_cut)
        commons_milli = int(round(commons_cut * MILLI))
        if commons_cut > 0:
            goods["grain"] = held + keep_net
            _bump(state, "commons_grain_above_cap_milli", commons_milli)
        if owned_cut or commons_milli:
            cut = {"owned_milli": owned_cut, "commons_milli": commons_milli}
            if held > 0:
                cut["committed_milli"] = int(round(held * MILLI))
            _book(state, world, reg).cap_cut = cut
    _check(state, world)
    return []


def _grain_committed(world, agent_bridge) -> dict[int, float]:
    """Grain merchants have committed to load or carry out of each region (the
    native stockpile commitments: reserved plus pending departure, read without
    draining them), food units; empty without an agent bridge."""
    if agent_bridge is None:
        return {}
    from chronicler.mutual_aid import read_stockpile_commitments
    by_name = read_stockpile_commitments(world, agent_bridge._sim)
    return {i: float(by_name.get(r.name, {}).get("grain", 0.0)) for i, r in enumerate(world.regions)}


def _storage_cap(world, rid: int, cap: float | None) -> float:
    """This turn's per-good storage cap of a region (``cap``; from the region's
    population when this turn's Phase 2 recorded none), food units."""
    if cap is not None:
        return cap
    from numpy import float32
    from chronicler.economy import PER_GOOD_CAP_FACTOR
    from chronicler.tuning import get_override
    return float(float32(get_override(world, "economy.per_good_cap_factor", PER_GOOD_CAP_FACTOR))
                 * float32(world.regions[rid].population))


def take_procured(world, rid: int, amount: float, flow_index: int) -> float:
    """A granary buys ``amount`` (food units) of owned grain in ``rid``: debit
    the owners pro rata to their claims (whole milli-food, rounded up, never
    above the owned grain) and record it for the Phase 10 credit. Returns the
    food units taken from owners, exactly ``milli / 1000``: the market's
    commons supply the rest of the purchase, and a sub-milli excess over it
    goes into the commons, so no food is lost or made."""
    state = _state(world)
    reg = state.region(rid)
    if reg is None or not math.isfinite(amount) or amount <= 0:
        raise RuntimeError("household retail procurement names no owned grain")
    milli = min(max(1, math.ceil(amount * MILLI - 1e-6)), reg.goods[GRAIN])
    if milli <= 0:
        raise RuntimeError("household retail procurement names no owned grain")
    taken = milli / MILLI
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
                or f.sent <= 0 or p.taken >= f.sent + 1.0 / MILLI):     # a sub-milli excess goes to the commons
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
            if int(applied):
                t.procurement_credits = {**(t.procurement_credits or {}), aid: int(applied)}
        _bump(state, "procurement_credited_milli", summary["credited_milli"])
        _bump(state, "procurement_residual_milli", summary["residual_milli"])
    state.last_procured_turn = turn
    t.procured = []
    return summary


def _record_departures(world, state, t: _Turn, agent_bridge) -> None:
    """Lead decision 7: merchants load commons only. Per pilot region-turn, the
    food merchants committed to loads and departures from the commons (the
    native commitments procurement reads) and the owned food they could not
    load: the foregone departures are at most the latter."""
    if not state.regions or agent_bridge is None:
        return
    from chronicler.economy import FOOD_GOODS
    from chronicler.mutual_aid import read_stockpile_commitments
    commitments = read_stockpile_commitments(world, agent_bridge._sim)
    for reg in state.regions:
        book = _book(state, world, reg)
        held = commitments.get(world.regions[reg.region].name, {})
        book.merchant_food_departing = round(math.fsum(float(held.get(g, 0.0)) for g in sorted(FOOD_GOODS)), 6)
        book.owned_food_unloadable = sum(reg.goods)


def phase10(world, acc, economy_result, agent_bridge) -> list:
    """Credit owners for grain their granaries bought (once), then close the
    turn's frame."""
    state = _state(world)
    t = _turn(state, world)
    procurement = _credit_procurement(world, state, t, agent_bridge) if t.procured else None
    _check(state, world)
    if getattr(getattr(world, "livelihoods", None), "titled_trade", None) is not None:
        # A4 titled trade's Phase 10 (movement, arrivals, returns, purchases),
        # inside this frame, so its flows are in the turn's books.
        from chronicler.titled_trade import retail_phase10, titled_trade_active
        if titled_trade_active(world):
            retail_phase10(world, acc, economy_result, agent_bridge)
            _check(state, world)
    _record_departures(world, state, t, agent_bridge)
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
            phase2=book.phase2, provisioning=book.provisioning, would_be=book.would_be,
            income_replaced=book.income_replaced, income_rows=book.income_rows,
            merchant_food_departing=book.merchant_food_departing,
            owned_food_unloadable_milli=book.owned_food_unloadable, cohorts=book.cohorts,
            cap_cut=book.cap_cut))
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
# A4 titled trade seams (``chronicler.titled_trade``)
# ---------------------------------------------------------------------------

def pilot_entry(world, rid: int) -> RetailRegion | None:
    """The open pilot entry of region ``rid`` (None outside the pilot)."""
    state = _state(world)
    return state.region(rid) if state is not None else None


def sell_to_merchant(world, rid: int, per_owner: dict[int, int]) -> list[int]:
    """A merchant buys ``per_owner`` milli-food of claims in ``rid``: debit the
    claims and the pooled goods pro rata to their composition (flow
    ``sold_merchant``); returns the goods taken per retail good. Title passes
    to the merchant's shipment; the caller pays the owners."""
    state = _state(world)
    reg = state.region(rid)
    total = sum(per_owner.values())
    if reg is None or total <= 0 or any(v <= 0 for v in per_owner.values()):
        raise RetailAccountingError("a merchant purchase names no owned food")
    per_good = _draw(reg.goods, total)
    _debit(state, world, reg, "sold_merchant", dict(per_owner), per_good)
    _check(state, world, {rid})
    return per_good


def consign(world, rid: int, holder: int, per_good: list[int], kind: str) -> bool:
    """A shipment's cargo becomes ``holder``'s claim in ``rid``'s pool (flow
    ``consigned_in`` at a destination, ``returned_in`` back at the origin).
    False, changing nothing, outside the pilot or when a new claim would
    exceed ``MAX_CLAIMS`` (the caller deposits the cargo in the commons)."""
    if kind not in ("consigned_in", "returned_in"):
        raise KeyError(kind)
    state = _state(world)
    reg = state.region(rid) if state is not None else None
    total = sum(per_good)
    if len(per_good) != len(RETAIL_GOODS) or total <= 0 or any(v < 0 for v in per_good):
        raise RetailAccountingError("a consignment names no cargo")
    if reg is None or (holder not in reg.claims and state.claims_count() >= MAX_CLAIMS):
        return False
    book = _book(state, world, reg)
    for g, v in enumerate(per_good):
        reg.goods[g] += v
    reg.claims[holder] = reg.claims.get(holder, 0) + total
    _sorted_claims(reg)
    _record(book, kind, list(per_good), {holder: total})
    _check(state, world, {rid})
    return True


def turn_settlement(world):
    """This turn's settlement as titled trade reads it: ``(money_rows,
    claim_sold, region_money, procurement_credits)`` (see ``_Turn``), each
    None when not observed this turn."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != world.turn:
        return None, None, None, None
    return t.money_rows, t.claim_sold, t.region_money, t.procurement_credits


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
        **({"schedule": schedule_summary(state)} if state.schedule is not None else {}),
        **({"rules_version": state.rules_version} if _v2(state) else {}),
        **({"opened_turn": {str(k): v for k, v in sorted(state.opened_turn.items())}}
           if _v2(state) and state.opened_turn is not None else {}),
        **({"intervals": {str(k): [list(i) for i in v] for k, v in sorted(state.intervals.items())}}
           if _v2(state) and state.intervals is not None else {}),
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
