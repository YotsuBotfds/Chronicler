"""Costly, region-owned harvest gatherings (experimental, default off).

One occurrence at autumn step 8 of the existing twelve-turn resource calendar.
This is a local gathering: it neither teleports pilgrims nor invents attendance.
Only a selected, currently present adult with a same-turn migration receipt can
add cross-region contact. No generic happiness, legitimacy or spiritual bonus.

The coordinator calls after public-granary procurement closes its resource
ledger, before the Phase-10 keep flush. A fresh native snapshot establishes
presence at this hook; historical Phase-10 rows are never rewritten. The
gathering has its own explicit food-consumption and host-expense receipts.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import TYPE_CHECKING

from chronicler import faiths
from chronicler.ritual_gatherings_state import (
    GatheringOutcome, GatheringSchedule, RitualGatheringState, ritual_gatherings_on,
)

if TYPE_CHECKING:
    from chronicler.models import WorldState

DEFAULT_ENABLED_FOR_NEW_WORLDS = False
CADENCE = 12
SEASON_STEP = 8                 # autumn's last resource step; not another year unit
MAX_ATTENDEES = 32
MAX_BOND_OPS = 8                # per gathering, not per attendee
MAX_CONTACT_UNITS = 8           # per gathering, directed arrival source -> host
ADULT_AGE = 18
ELIGIBLE_OCCUPATIONS = frozenset({0, 3, 4})  # settled farmer/scholar/priest; see _presence
FOOD_PER_ATTENDEE = 0.05        # grain consumed, additional to ordinary eating [CALIBRATE]
KEEP_FOOD_TURNS = 2.0           # do not spend residents' near-term food buffer
HOST_BASE_COST = 1              # real treasury units [CALIBRATE]
HOST_GROUP_SIZE = 16
FRIEND_SENTIMENT = 20
REL_SLOTS = 8                   # existing native fixed relationship capacity
EPS = 1e-9


def ritual_gatherings_enabled(world) -> bool:
    return ritual_gatherings_on(world)


def ritual_gatherings_active(world) -> bool:
    """Saved state is dormant outside the authoritative hybrid goods/agent mode."""
    return ritual_gatherings_on(world) and getattr(world, "agent_mode", None) == "hybrid"


def set_ritual_gatherings_enabled(world: "WorldState", enabled: bool) -> None:
    if enabled:
        if not ritual_gatherings_on(world):
            world.ritual_gatherings = RitualGatheringState()
    else:
        world.ritual_gatherings = None


def _next_turn(turn: int) -> int:
    return turn + (SEASON_STEP - turn % CADENCE) % CADENCE


def _bump(state, key, value=1) -> None:
    state.counters[key] = round(state.counters.get(key, 0.0) + value, 9)


def _presence(world, bridge) -> dict[int, list[tuple[int, int]]]:
    """One snapshot and one row-bucketing pass, only on occurrence turns.

    Bound each region's candidate storage to 32 stable IDs while retaining its
    exact population count separately in the caller's economy demand. Rows in a
    native snapshot are all alive. Malformed/incomplete snapshots fail before
    any food or funds move; an absent bridge supplies no fictional attendees.
    """
    if bridge is None:
        return {}
    batch = bridge.get_snapshot()
    if batch is None:
        return {}
    from chronicler.columnar import pylist, schema_names
    required = ("id", "region", "age", "belief", "occupation")
    if not all(k in schema_names(batch) for k in required):
        raise ValueError("Harvest gathering snapshot requires id, region, age, belief and occupation")
    # The canonical snapshot has no merchant trip phase or deployed-roster
    # availability. Named characters also have Python pilgrimage/agenda travel
    # that may diverge from their native region. Exclude all these categories
    # rather than claiming their coarse pool region proves local availability.
    named = set(getattr(bridge, "named_agents", {}))
    for civ in world.civilizations:
        if civ.leader.agent_id is not None:
            named.add(civ.leader.agent_id)
        named.update(gp.agent_id for gp in civ.great_persons if gp.agent_id is not None)
    # A small heap per region avoids sorting/copying every agent into a bucket.
    import heapq
    buckets: dict[int, list[tuple[int, int]]] = {}
    seen: set[int] = set()
    columns = [pylist(batch.column(k)) for k in required]
    for aid, rid, age, belief, occupation in zip(*columns, strict=True):
        if (any(v is None or isinstance(v, bool) or not isinstance(v, int)
                for v in (aid, rid, age, belief, occupation))
                or not 0 <= aid <= 0xFFFFFFFF or not 0 <= rid < len(world.regions)
                or age < 0 or not 0 <= belief <= 255 or not 0 <= occupation <= 4 or aid in seen):
            raise ValueError("Harvest gathering snapshot has invalid or duplicate agent rows")
        seen.add(aid)
        if age < ADULT_AGE or occupation not in ELIGIBLE_OCCUPATIONS or aid in named:
            continue
        bucket = buckets.setdefault(rid, [])
        row = (-aid, belief)
        if len(bucket) < MAX_ATTENDEES:
            heapq.heappush(bucket, row)
        elif aid < -bucket[0][0]:
            heapq.heapreplace(bucket, row)
    return {rid: sorted((-aid, belief) for aid, belief in rows) for rid, rows in buckets.items()}


def _relationships(bridge, wanted: set[int]) -> dict[int, list[tuple[int, int, int, int]]]:
    """Read the native graph once, retaining only actual candidates' tiny rows."""
    if not wanted:
        return {}
    sim = getattr(bridge, "_sim", None)
    if sim is None or not hasattr(sim, "get_all_relationships"):
        raise RuntimeError("Harvest gatherings require the native relationship read API")
    batch = sim.get_all_relationships()
    from chronicler.columnar import pylist
    cols = [pylist(batch.column(k)) for k in
            ("agent_id", "target_id", "sentiment", "bond_type", "formed_turn")]
    rows = {aid: [] for aid in wanted}
    for aid, target, sentiment, kind, formed in zip(*cols, strict=True):
        if aid in rows:
            rows[aid].append((target, sentiment, kind, formed))
    return rows


def _bond_ops(attendees, edges, turn):
    """Disjoint pairs, no hostile pair, no eviction or protected-bond rewriting.

    An existing friendship can only strengthen; its native formed_turn survives
    an upsert. A full endpoint is skipped for a new friendship. The FFI remains
    authoritative and returns no success count, so receipts call these attempts.
    """
    from chronicler.ffi_constants import BOND_FRIEND, BOND_GRUDGE, BOND_RIVAL
    ids = [aid for aid, _belief in attendees]
    ops = []
    for a, b in zip(ids[::2], ids[1::2]):
        ra, rb = edges.get(a, []), edges.get(b, [])
        pair = [r for r in ra if r[0] == b] + [r for r in rb if r[0] == a]
        if any(r[1] < 0 or r[2] in (BOND_RIVAL, BOND_GRUDGE) for r in pair):
            continue
        fa = next((r for r in ra if r[0] == b and r[2] == BOND_FRIEND), None)
        fb = next((r for r in rb if r[0] == a and r[2] == BOND_FRIEND), None)
        if (fa is None and len(ra) >= REL_SLOTS) or (fb is None and len(rb) >= REL_SLOTS):
            continue
        sentiment = max([FRIEND_SENTIMENT] + [r[1] for r in (fa, fb) if r is not None])
        # Native's existing uint16 formed-turn format cannot represent a later
        # year. Do not wrap, clamp or introduce an unrelated bond at turn 65536.
        if not 0 <= turn <= 0xFFFF:
            continue
        ops.append({"op_type": 1, "agent_a": a, "agent_b": b, "bond_type": BOND_FRIEND,
                    "sentiment": sentiment, "formed_turn": turn})
        if len(ops) >= MAX_BOND_OPS:
            break
    return ops


def _arrival_receipts(world, wanted):
    """Only unambiguous, dated migrations ending in the actual attendee's host.

    Birth origin, civ affinity, historical migrations and planned pilgrimages
    cannot establish attendance. Multiple moves by an ID this turn are omitted
    conservatively because intermediate contacts have ambiguous attribution.
    """
    from chronicler.history_index import history_index
    per_id = {}
    for event in history_index(world).agent_migrations_for_turn(world, world.turn):
        if event.agent_id in wanted:
            per_id.setdefault(event.agent_id, []).append(event)
    return {aid: (rows[0].region, rows[0].target_region) for aid, rows in per_id.items()
            if len(rows) == 1 and rows[0].target_region != rows[0].region
            and 0 <= rows[0].region < len(world.regions)}


def _faith(world, attendees):
    counts = Counter(uid for _aid, slot in attendees if (uid := faiths.uid_of(world, slot)) is not None)
    if not counts:
        return None, None
    uid = min(counts, key=lambda k: (-counts[k], k))
    rec = faiths.record(world, uid)
    if rec is not None:
        return uid, rec.name
    belief = next((b for b in world.belief_registry if b.faith_id == uid), None)
    return uid, belief.name if belief is not None else None


def _reason(world, rid, attendees, economy, commitments, book, host, food, funds):
    region = world.regions[rid]
    if host < 0 or region.name not in world.civilizations[host].regions:
        return "no_host"
    if region.occupied_by is not None and region.occupied_by != region.controller:
        return "occupied"
    if not attendees:
        return "no_attendees"
    suff = economy.food_sufficiency.get(region.name) if economy is not None else None
    demand = economy.market_demand.get(region.name) if economy is not None else None
    if (suff is None or not math.isfinite(suff) or demand is None or not demand
            or not math.isfinite(demand[0]) or demand[0] < 0):
        return "unmeasured_food"
    if suff < 1.0 - EPS or (region.food_shortfall or 0) > EPS:
        return "shortage"
    grain = region.stockpile.goods.get("grain", 0.0)
    committed = commitments.get(region.name, {}).get("grain", 0.0)
    if not math.isfinite(grain) or grain < 0:
        raise ValueError("Harvest gathering market has invalid grain")
    if grain - committed - KEEP_FOOD_TURNS * demand[0] + EPS < food:
        return "food"
    if book.proj[host] < funds:
        return "funds"
    return None


def _event(world, schedule, outcome):
    """Only first occurrence, a cancellation change, recovery or changed host/faith."""
    changed = (schedule.last_status != outcome.status or schedule.last_reason != outcome.reason)
    if outcome.status == "held":
        salient = (schedule.first_held_turn is None or changed or schedule.last_host != outcome.host
                   or schedule.last_faith != outcome.faith)
        description = (f"{outcome.host_name} holds the harvest gathering in {outcome.region_name}; "
                       f"{len(outcome.attendee_ids)} present adults share {outcome.food:.2f} grain, "
                       f"costing the host {outcome.funds} treasury units.")
        kind = "harvest_gathering_held"
    else:
        salient = changed and outcome.reason not in ("no_host", "no_attendees", "unmeasured_food")
        description = (f"The harvest gathering in {outcome.region_name} is cancelled "
                       f"({outcome.reason}); no gathering food or funds are spent.")
        kind = "harvest_gathering_cancelled"
    if not salient:
        return None
    from chronicler.models import Event
    return Event(turn=world.turn, event_type=kind, actors=[outcome.host_name] if outcome.host_name else [],
                 description=description, importance=4 if outcome.status == "held" else 3,
                 civs=[outcome.host_name] if outcome.host_name else [], region=outcome.region_name)


def tick_ritual_gatherings(world: "WorldState", acc=None, *, phase10=None, agent_bridge=None,
                          economy_result=None) -> list:
    if not ritual_gatherings_active(world):
        return []
    state = world.ritual_gatherings
    if state.last_tick_turn == world.turn:
        return []
    if state.last_tick_turn > world.turn:
        raise ValueError("Harvest gathering state is ahead of the simulation turn")
    if phase10 is not None and phase10.source_turn != world.turn:
        raise ValueError("Harvest gathering inputs belong to a different source turn")
    if economy_result is None and phase10 is not None:
        economy_result = phase10.economy
    # The default calendar cannot be reset by a new ruler, faith or missing
    # ceremony. Newly added regions start at the next calendar boundary.
    existing = {}
    for schedule in state.schedules:
        if (not isinstance(schedule, GatheringSchedule) or isinstance(schedule.region, bool)
                or not isinstance(schedule.region, int) or not 0 <= schedule.region < len(world.regions)
                or schedule.region in existing
                or schedule.gathering_id != f"harvest:{schedule.region}"
                or schedule.next_turn % CADENCE != SEASON_STEP):
            raise ValueError("Harvest gathering schedules have invalid or duplicate regional identities/calendar")
        existing[schedule.region] = schedule
    for rid in range(len(world.regions)):
        if rid not in existing:
            schedule = GatheringSchedule(region=rid, gathering_id=f"harvest:{rid}",
                                         created_turn=world.turn, next_turn=_next_turn(world.turn))
            state.schedules.append(schedule)
            existing[rid] = schedule
    due = [existing[rid] for rid in sorted(existing)
           if existing[rid].next_turn <= world.turn and world.turn % CADENCE == SEASON_STEP
           and existing[rid].last_turn != world.turn]
    state.outcomes_turn = world.turn
    state.outcomes = []
    if not due:
        state.last_tick_turn = world.turn
        return []

    buckets = _presence(world, agent_bridge)
    from chronicler.finance import _Book
    book = _Book(world, acc)
    commitments = {}
    if agent_bridge is not None:
        from chronicler.mutual_aid import read_stockpile_commitments
        commitments = read_stockpile_commitments(world, agent_bridge._sim)
    # Eligibility is checked before spending, and full graph reads occur only
    # when an affordable gathering would actually attempt bonds.
    plans = []
    for schedule in due:
        rid = schedule.region
        region = world.regions[rid]
        attendees = buckets.get(rid, [])
        host = world.civ_index_map.get(region.controller, -1)
        food = len(attendees) * FOOD_PER_ATTENDEE
        funds = HOST_BASE_COST + math.ceil(len(attendees) / HOST_GROUP_SIZE)
        reason = _reason(world, rid, attendees, economy_result, commitments, book, host, food, funds)
        plans.append((schedule, attendees, host, food, funds, reason))
    wanted = {aid for _s, attendees, _h, _f, _c, reason in plans if reason is None
              for aid, _belief in attendees} if state.bonds_enabled else set()
    edges = _relationships(agent_bridge, wanted)
    # One indexed scan for this turn, not one scan per region. Even cost-only
    # controls retain the same actual attendance/arrival receipts for analysis.
    arrival_ids = {aid for _s, attendees, _h, _f, _c, reason in plans if reason is None
                   for aid, _belief in attendees}
    arrivals = _arrival_receipts(world, arrival_ids)
    events = []
    for schedule, attendees, host, food, funds, reason in plans:
        # A preceding region of the same host may have consumed the remaining
        # treasury. Recheck exact projected funds before this atomic expense.
        if reason is None and book.proj[host] < funds:
            reason = "funds"
        rid = schedule.region
        region = world.regions[rid]
        uid, name = _faith(world, attendees) if reason is None else (None, None)
        out = GatheringOutcome(gathering_id=schedule.gathering_id, turn=world.turn,
                               region=rid, region_name=region.name, host=host,
                               host_name=world.civilizations[host].name if host >= 0 else None,
                               faith=uid, faith_name=name,
                               status="cancelled" if reason else "held", reason=reason)
        _bump(state, "scheduled")
        if reason is None:
            grain = region.stockpile.goods.get("grain", 0.0)
            out.grain_before, out.funds_before = grain, book.proj[host]
            region.stockpile.goods["grain"] = max(0.0, grain - food)
            spent = -book.add(host, -funds)
            out.grain_after, out.funds_after = region.stockpile.goods["grain"], book.proj[host]
            out.attendee_ids = [aid for aid, _belief in attendees]
            out.food, out.funds = food, spent
            # These receipts deliberately track terminal consumption/expenses,
            # not a transfer into an imaginary stock or an agent-memory reward.
            assert math.isclose(out.grain_before - out.grain_after, food, abs_tol=EPS)
            assert out.funds_before - out.funds_after == spent == funds
            out.arrivals = [(aid, arrivals[aid][0]) for aid, _belief in attendees
                            if aid in arrivals and arrivals[aid][1] == rid]
            if state.contact_enabled:
                from chronicler.contact_ledger import record_gathering_arrivals
                out.contact_units = record_gathering_arrivals(world, rid, out.arrivals,
                                                              max_units=MAX_CONTACT_UNITS)
            if state.bonds_enabled:
                ops = _bond_ops(attendees, edges, world.turn)
                agent_bridge.apply_relationship_ops(ops)
                out.bond_ops = len(ops)
            _bump(state, "held")
            for key, value in (("attendees", len(attendees)), ("food", food), ("funds", spent),
                               ("contact_units", out.contact_units), ("bond_ops", out.bond_ops)):
                _bump(state, key, value)
        else:
            _bump(state, "cancelled")
        event = _event(world, schedule, out)
        if event is not None:
            events.append(event)
        schedule.last_turn, schedule.next_turn = world.turn, _next_turn(world.turn + 1)
        schedule.last_status, schedule.last_reason = out.status, out.reason
        if out.status == "held":
            if schedule.first_held_turn is None:
                schedule.first_held_turn = world.turn
            schedule.last_host, schedule.last_faith = out.host, out.faith
        state.outcomes.append(out)
    state.last_tick_turn = world.turn
    return events


def snapshot_summary(world: "WorldState") -> dict:
    """Read dated receipts only; no current-controller or final-faith fallback."""
    if not ritual_gatherings_active(world):
        return {}
    state = world.ritual_gatherings
    source_turn = world.turn - 1
    return {
        "source_turn": source_turn,
        "schedules": [{"gathering_id": s.gathering_id, "region": s.region,
                       "region_name": world.regions[s.region].name, "cadence": CADENCE,
                       "season_step": SEASON_STEP, "next_turn": s.next_turn,
                       "last_turn": s.last_turn, "last_status": s.last_status}
                      for s in state.schedules if 0 <= s.region < len(world.regions)],
        "outcomes": [o.model_dump() for o in state.outcomes if o.turn == source_turn
                     and state.outcomes_turn == source_turn],
        "counters": dict(state.counters),
    }
