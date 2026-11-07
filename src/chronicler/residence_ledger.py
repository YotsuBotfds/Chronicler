"""Residence ledger (X1, ``--residence-ledger``, default off): home, residence, attachment and displacement.

Requires ``--agents hybrid``. The lead-owned displacement contract of the
connected-world program, specified by audit A6 section 11 (definitions 11.1,
one writer 11.2, dated persistence 11.3, readers 11.4, relation to existing
records 11.5); integration page ``docs/integration/residence-ledger.md``.

Why. "Displaced" meant three different things, none fit for the consumers
that need it (C2 crowding, D3 war's human consequences, A6 adaptive
decisions): the native ``displacement_turns`` counter is "moved in the last 5
turns, whatever the reason", ``origin_region`` is the birth region (never
updated) and the bridge's ``displacement_by_region`` share repeats the counter
for narration. This package keeps one dated record of where each person lives,
where they belong and why they left, so each consumer selects its own subset
by ``cause`` and ``anchor``.

Definitions (audit 11.1):

* **Residence** ``res``: the native region after the tick. A merchant on a
  native trip keeps the residence last recorded (a trip is not a migration);
  a traveller alive when first seen is recorded at the end of the trip.
* **Location** (record only): the residence, except a merchant in transit
  (the snapshot region) and a person on an army roster (the army's region).
* **Attachment**: ``(army_id, army region)`` from the rosters after
  ``reconcile_rosters``, else none. Enlistment never re-homes.
* **Home**, dated ``home_since``: the residence at first observation (the
  birth region for a person born after it); it changes only when a voluntary
  or unclassified move is applied (a migrant re-homes at once) or when an open
  spell resettles after ``REHOME_TURNS`` turns at one residence.
* **Displacement spell**: opened when an applied move leaves home and its
  driver is in C1b's ``FLIGHT_DRIVERS`` (cause ``flight``) or
  ``HUNGER_DRIVERS`` (``hunger``); a household follower's event carries its
  lead's driver natively. ``anchor``: the home-region event dated in the
  ``ANCHOR_TURNS`` turns before the departure (``war``: a controller change,
  an occupation or a conquest; ``famine``: a famine or dearth report;
  ``persecution``: the region persecuted), first present in that order, every
  kind kept in ``anchor_kinds``; ``none`` without one. **Displaced** = an open
  spell. Closures: ``returned`` (residence equals home after a move),
  ``resettled`` (home becomes the residence: ``REHOME_TURNS`` at one residence,
  the only way a spell resettles), ``died``, ``pool_reset`` (the native pool
  was rebuilt) and ``unobserved_gap`` (turns the ledger did not observe, the
  switch turned off). Any onward move of a displaced person, voluntary or not,
  keeps the spell open and home unchanged (``moves`` counts it); only a
  person without an open spell re-homes at a voluntary or unclassified move
  (the lead's resolution of an ambiguity in audit 11.1, which reproduces the
  audit's section 10 measurements).
* **Separated** (computed on demand by :func:`separation`, never stored): a
  married partner, or a dependent child's parent, alive with a different
  residence or location, with the cause ``trip``, ``attached``, ``displaced``
  or ``migrated``.

Dating of an anchor. Region state is read at this hook: a conquest
(``last_conquered_turn``, Phase 5), an occupation (Phase 5), a battle fought
in the region (``war_state.battles`` of turn T, Phase 5 campaigns), a siege of
it (an army ``sieging`` there, Phase 5) and a famine onset (``famine_cooldown``
at its onset value, Phase 9 ecology) dated T happened before T's agent tick
and count for T's departures; a change of controller between two
civilizations without a conquest (secession, cession, absorption, mostly
Phase 10; a region gaining or losing its only controller is not war) and
persecution (``persecution_intensity``, computed in Phase 10) are read
against the ledger's previous reading, so they are dated T and count from
T+1 (the tick of T persecuted by T-1's reading, which is in the window). A
window reaching before the ledger watched the regions is ``anchor_partial``.

One writer (audit 11.2): the livelihoods ``phase10`` hook of turn T, after
``reconcile_rosters`` and every acting package, before D2's records and A1's
ledger, reads T's applied native migrations with their drivers
(``world.agent_events_raw``, as RS4 reads them), the post-tick snapshot,
``trip_agent_ids()``, the rosters and region state, and writes one frame
stamped ``source_turn = T``. Army dissolutions at the end-of-turn sync are
seen at T+1. Natively, ``apply_migrations`` relocates ordinary agents, and a
merchant trip unwound on a conquest leaves the traveller where it was (a
correction to audit 11.2; recorded as ``trip_relocations``); no native change
is needed. It registers no agent-tick hook (the post-tick snapshot hand-over
is unchanged). A consumer that reads in Phase 10 must come before this
package in ``LIVELIHOODS_SWITCHES``: after the writer, T's frame is a
same-turn read and is refused.

Contract. Record-only: it never writes simulation state, draws no random
number, builds no world lookup cache and changes nothing it observes, so with
the switch on every output except this record equals the switch off. State is
bounded (one row per observed living person by stable id, at most
``MAX_ROWS``), checkpointed and omitted while off; an exact resume restores
it; a rebuilt pool (a legacy resume) rebuilds nothing: its spells close as
``pool_reset`` and observation restarts (``observed_from``).

Readers (audit 11.4). A consumer at turn T+1 reads T's frame through
:func:`read_frame` (aggregates: C2 crowding, ruler decisions) or a person's
own row through an :class:`OwnRow` bound to that person
(:func:`own_row_accessor`, A6); D3 asks :func:`separation`. Each refuses
a same-turn or future read (:class:`LedgerReadRefused`) and returns None when
T was not observed (unknown, not zero). Decision modules may read nothing
else (``tests/test_residence_ledger_guard.py``). The bridge's displaced share
stays narration-only; RS4 keeps its own diaspora ledger; the native cooldown
and birth region are unchanged on the default path.
"""
from __future__ import annotations

import copy
from dataclasses import asdict

from chronicler.models import NO_MIGRATION_DRIVER, VOLUNTARY_MIGRATION_DRIVERS, migration_driver_name
from chronicler.quarantine_rules import FLIGHT_DRIVERS, HUNGER_DRIVERS
from chronicler.residence_ledger_state import (
    ANCHOR_TURNS, ANCHORS, CAUSES, CLOSURES, COUNTERS, EVENT_KINDS, LOG_KINDS, MAX_EVENTS, MAX_LOG, MAX_ROWS,
    MOVE_GROUPS, REGION_KEYS, REHOME_TURNS, SEPARATION_CAUSES, TOTAL_KEYS, LogRecord, RegionWatch,
    ResidenceLedgerState, ResidenceRow, Spell,
)

STAGE = "X1"
#: ``ecology._check_famine_yield`` sets ``famine_cooldown`` to this at a famine
#: (or dearth) report, after the turn's decrement: read at Phase 10, it dates
#: the onset to this turn.
FAMINE_ONSET_COOLDOWN = 5
#: Native ``agent::AGE_ADULT``: a child below it is a dependent (separation).
ADULT_AGE = 20
#: Native methods the writer needs.
NATIVE: tuple[str, ...] = ("get_snapshot", "trip_agent_ids")

_FLIGHT = frozenset(FLIGHT_DRIVERS)
_HUNGER = frozenset(HUNGER_DRIVERS)
#: What each record field means (copied into every snapshot record).
LABELS: dict[str, str] = {
    "residence": ("the native region a person lives in after the tick; a merchant on a native trip keeps the "
                  "residence last recorded (the trip is not a migration)"),
    "home": ("where a person belongs: the residence when first observed (the birth region for a person born "
             "since), changed only by a voluntary or unclassified move of a person who is not displaced (a "
             f"migrant re-homes at once) or by a displacement spell that resettles after {REHOME_TURNS} turns at "
             "one residence; never by enlistment"),
    "displaced": ("an open displacement spell: opened by an applied move that left home driven by flight "
                  "(memories of famine, battle, conquest or persecution; persecution; the safety need) or hunger "
                  "(food opportunity, material need); a household follower carries its lead's driver; an onward "
                  "move, voluntary or not, keeps it open; the opening driver is kept"),
    "anchor": (f"the home-region event dated in the {ANCHOR_TURNS} turns before the departure: war (a change of "
               "controller between civilizations, an occupation, a conquest, a battle or a siege), famine (a "
               "famine or dearth report), persecution; the first present in that order (anchor_any_* counts "
               "every kind present); none without one; anchor_partial: the window reaches before the ledger "
               "watched the regions"),
    "closures": (f"returned: back home after a move; resettled: {REHOME_TURNS} turns at one residence, which "
                 "becomes home; died; pool_reset: the native pool was rebuilt; unobserved_gap: turns the ledger did "
                 "not observe"),
    "attached": ("on an army roster after the rosters were reconciled, counted by home region; attached_away: "
                 "the army is in another region than home. Dissolutions at the end-of-turn sync are seen next turn"),
    "in_transit": "residents physically elsewhere on a merchant trip (location differs from residence)",
    "flows": ("arrivals and departures count every applied native move this turn (by driver group: flight, "
              "hunger, voluntary - frontier, wage, chain, urban, learning - and other); arrivals_displaced: "
              "movers whose spell is open after the move (arrivals_displaced_<anchor> by its anchor); opened, "
              "returned, resettled and died_displaced: spell openings (by departure region; opened_<cause>, "
              "opened_<anchor>) and closures (returned by home, returned_<anchor>; the others by residence); "
              "displaced_from_<anchor>: open spells by origin and anchor"),
    "comparisons": ("record-only counts of the measures this contract replaces: recent_movers_native (native "
                    "displacement counter above zero: moved in the last 5 turns) and away_from_birth_region "
                    "(native origin region)"),
    "unknown": ("history before observed_from is unknown, not zero; a frame of null is a turn the ledger did not "
                "observe"),
}


class LedgerReadRefused(RuntimeError):
    """A same-turn, future or other-turn read of the ledger (audit 11.3)."""


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def _state(world) -> ResidenceLedgerState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "residence_ledger", None) if container is not None else None


def _bump(state: ResidenceLedgerState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(f"undeclared residence-ledger counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + amount


def _log(state: ResidenceLedgerState, turn: int, kind: str, **detail) -> None:
    if kind not in LOG_KINDS:
        raise KeyError(f"undeclared residence-ledger log kind {kind!r}")
    state.log.append(LogRecord(turn=int(turn), kind=kind, detail=detail))
    if len(state.log) > MAX_LOG:
        state.log_dropped += len(state.log) - MAX_LOG
        del state.log[:-MAX_LOG]


def _end_epoch(state: ResidenceLedgerState, reason: str) -> int:
    """Close every open spell with ``reason`` (lifetime counters only) and drop
    the person rows; observation restarts at the next write. Returns the number
    of spells closed (from the rows; from ``open_spells_held`` when the rows were
    not kept, as in a state read from JSON)."""
    closed = sum(1 for row in state.rows.values() if row.spell is not None) if state.rows \
        else state.open_spells_held
    if closed:
        _bump(state, f"closed_{reason}", closed)
    state.rows = {}
    state.deferred = []
    state.travelling = []
    state.attached = []
    state.rows_held = state.open_spells_held = 0
    state.observed_from = None
    return closed


def set_residence_ledger_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable, or end with a dated record: open spells close as
    ``unobserved_gap`` (the ledger stops observing), person rows, the frame and
    the region watch are dropped; counters and the log are kept."""
    turn = int(getattr(world, "turn", 0))
    state = _state(world)
    if state is None:
        world.livelihoods.residence_ledger = state = ResidenceLedgerState(enabled=bool(value))
        if value:
            _bump(state, "switched_on")
            _log(state, turn, "switched_on")
        return
    if bool(value) == state.enabled:
        return
    state.enabled = bool(value)
    if value:
        _bump(state, "switched_on")
        _log(state, turn, "switched_on")
        return
    rows = len(state.rows)
    closed = _end_epoch(state, "unobserved_gap")
    _bump(state, "switched_off")
    _log(state, turn, "switched_off", frame_turn=state.frame_turn, rows=rows, spells_closed=closed)
    state.frame = state.events = state.frame_turn = state.pending = None
    state.events_dropped = 0
    state.regions = []
    state.watch_from = state.last_turn = None


def residence_ledger_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def on_pool_reset(world) -> None:
    """A rebuilt native pool (``livelihoods.bind_native_pool``, e.g. a legacy
    state-file resume): the saved stable ids name other people now. Open spells
    close as ``pool_reset`` (reported in this turn's frame) and observation
    restarts; nothing is rebuilt. A no-op in a fresh run (no rows yet)."""
    state = _state(world)
    if state is None or (not state.rows and not state.deferred and not state.rows_held):
        return
    turn = int(getattr(world, "turn", 0))
    events = [_event(aid, "pool_reset", row.spell, row.res, turn)
              for aid, row in sorted(state.rows.items()) if row.spell is not None]
    kept = bool(state.rows)
    rows = len(state.rows) if kept else state.rows_held
    closed = _end_epoch(state, "pool_reset")
    _bump(state, "pool_resets")
    _log(state, turn, "pool_reset", rows=rows, spells_closed=closed, rows_kept=kept,
         reason="native pool rebuilt: saved stable ids name other people")
    # Spells whose rows were not kept (a state read from JSON) are counted, not listed.
    state.pending = {"turn": turn, "events": events, "unlisted": closed - len(events)}


# ---------------------------------------------------------------------------
# The writer (livelihoods Phase 10)
# ---------------------------------------------------------------------------

def _event(aid: int, kind: str, spell: Spell, region: int, turn: int) -> dict:
    return {"id": int(aid), "kind": kind, "turn": int(turn), "region": int(region), "start": spell.start,
            "origin": spell.origin, "cause": spell.cause, "anchor": spell.anchor, "length": int(turn) - spell.start,
            "driver": spell.driver}



def _group(code: int | None) -> str:
    name = migration_driver_name(code)
    if name in _FLIGHT:
        return "flight"
    if name in _HUNGER:
        return "hunger"
    if name in VOLUNTARY_MIGRATION_DRIVERS:
        return "voluntary"
    return "other"


def _turn_moves(world, n_regions: int) -> tuple[list[tuple[int, int, int, int | None]], int]:
    """This turn's applied native migrations, in native order: (id, from, to,
    driver code or None), and the number of events naming an invalid route,
    which are counted and skipped (a record-only package never stops the run).
    Every applied move is one (L7's household moves included)."""
    raw = getattr(world, "agent_events_raw", None) or []
    out = []
    invalid = 0
    for e in reversed(raw):
        if e.turn != world.turn:
            break
        if e.event_type == "migration":
            frm, to = int(e.region), int(e.target_region)
            if not (0 <= frm < n_regions and 0 <= to < n_regions) or frm == to:
                invalid += 1
                continue
            code = int(e.migration_driver)
            out.append((int(e.agent_id), frm, to, None if code == NO_MIGRATION_DRIVER else code))
    out.reverse()
    return out, invalid


def _region_index(world, name) -> int | None:
    for i, region in enumerate(world.regions):
        if region.name == name:
            return i
    return None


class _Turn:
    """One write's accumulators (never stored)."""

    __slots__ = ("turn", "region", "totals", "events", "dropped", "pre", "prior", "partial")

    def __init__(self, turn: int, n_regions: int):
        self.turn = turn
        self.region = [dict.fromkeys(REGION_KEYS[1:], 0) for _ in range(n_regions)]
        self.totals = dict.fromkeys(TOTAL_KEYS, 0)
        self.events: list[dict] = []
        self.dropped = 0
        self.pre: list[set[str]] = []
        self.prior: list[tuple] = []
        self.partial = True

    def event(self, row: dict) -> None:
        if len(self.events) < MAX_EVENTS:
            self.events.append(row)
        else:
            self.dropped += 1


def _watch_regions(world, state: ResidenceLedgerState, t: _Turn) -> None:
    """Date this turn's region events (the anchors). ``t.pre``: kinds dated
    before T's tick; ``t.prior``: each kind's last turn before T."""
    turn = t.turn
    while len(state.regions) < len(world.regions):
        state.regions.append(RegionWatch())
    if state.watch_from is None:
        state.watch_from = turn
    t.partial = state.watch_from > turn - ANCHOR_TURNS
    fought = _battle_and_siege_regions(world, turn)
    for i, region in enumerate(world.regions):
        w = state.regions[i]
        t.prior.append((w.war, w.famine, w.persecution))
        conquered = region.last_conquered_turn == turn
        occupied = region.occupied_by is not None
        famine = region.famine_cooldown == FAMINE_ONSET_COOLDOWN
        changed = w.controller_seen and _civ_change(w.controller, region.controller)
        pre = set()
        if conquered or occupied or region.name in fought:
            pre.add("war")
        if famine:
            pre.add("famine")
        t.pre.append(pre)
        if conquered or occupied or changed or region.name in fought:
            w.war = turn
        if famine:
            w.famine = turn
        if region.persecution_intensity > 0:
            w.persecution = turn
        w.controller, w.controller_seen = region.controller, True


def _civ_change(before: str | None, after: str | None) -> bool:
    """A war-like change of controller: from one civilization to another (a
    region gaining or losing its only controller is not war; review m1)."""
    return before is not None and after is not None and before != after


def _battle_and_siege_regions(world, turn: int) -> set[str]:
    """Names of regions where a battle was fought in turn T (``war_state.battles``,
    appended by Phase 5 campaigns, so before T's agent tick) or an army is
    besieging (phase ``sieging``, set in Phase 5 and unchanged until the
    end-of-turn sync)."""
    state = getattr(world, "war_state", None)
    if state is None:
        return set()
    names = set()
    for battle in reversed(state.battles):
        if battle.turn != turn:
            if battle.turn < turn:
                break
            continue
        names.add(battle.region)
    for army in state.armies:
        if army.phase == "sieging":
            names.add(army.region)
    return names


def _anchor(t: _Turn, region: int) -> tuple[str, list[str]]:
    kinds = set(t.pre[region])
    for kind, last in zip(EVENT_KINDS, t.prior[region]):
        if last is not None and last >= t.turn - ANCHOR_TURNS:
            kinds.add(kind)
    present = [k for k in EVENT_KINDS if k in kinds]
    return (present[0] if present else "none"), present


def _close(state: ResidenceLedgerState, t: _Turn, aid: int, row: ResidenceRow, reason: str, region: int,
           *, relocation: bool = False) -> None:
    spell, row.spell = row.spell, None
    t.totals[reason] += 1
    _bump(state, f"closed_{reason}")
    key = {"returned": "returned", "resettled": "resettled", "died": "died_displaced"}.get(reason)
    if key is not None:
        t.region[region][key] += 1
    if reason == "returned":
        t.region[region][f"returned_{spell.anchor}"] += 1
        t.totals[f"returned_{spell.anchor}"] += 1
    event = _event(aid, reason, spell, region, t.turn)
    if relocation:
        event["relocation"] = True       # not an applied migration (a trip that ended away, or unexplained)
    t.event(event)


def _move(state: ResidenceLedgerState, t: _Turn, aid: int, row: ResidenceRow, frm: int, to: int,
          code: int | None, *, counted: bool = True) -> None:
    """Apply one move to a person's row (``counted``: an applied native move;
    False: an unexplained relocation, which updates the row only)."""
    turn = t.turn
    group = _group(code)
    if counted:
        t.totals["moves"] += 1
        t.totals[f"moves_{group}"] += 1
        _bump(state, "moves_seen")
        t.region[frm]["departures"] += 1
        t.region[frm][f"departures_{group}"] += 1
        t.region[to]["arrivals"] += 1
        t.region[to][f"arrivals_{group}"] += 1
        t.totals[f"arrivals_{group}"] += 1
        if row.res != frm:
            # The row missed a relocation: the native origin is authoritative.
            t.totals["move_origin_mismatches"] += 1
            _bump(state, "move_origin_mismatches")
            if row.spell is None:
                row.home = frm
            row.res = frm
    if row.spell is not None:
        if to == row.home:
            _close(state, t, aid, row, "returned", to, relocation=not counted)
        else:
            # Lead's resolution of 11.1: any onward move, voluntary or not, keeps the
            # spell open and home unchanged (only the residence and its date move).
            row.spell.moves += 1
    elif group in CAUSES:
        anchor, kinds = _anchor(t, frm)
        row.spell = Spell(start=turn, origin=row.home, cause=group, anchor=anchor, anchor_kinds=kinds,
                          anchor_partial=t.partial, driver=code)
        t.totals["opened"] += 1
        t.region[frm]["opened"] += 1
        for key in (f"opened_{group}", f"opened_{anchor}"):
            t.region[frm][key] += 1
            t.totals[key] += 1
        _bump(state, f"opened_{group}")
        _bump(state, f"opened_{anchor}")
        t.event(_event(aid, "opened", row.spell, to, turn))
    else:
        row.home, row.home_since = to, turn
        t.totals["rehomed"] += 1
        _bump(state, "rehomed")
    row.res, row.res_since = to, turn
    row.move_turn, row.move_from, row.move_driver = turn, frm, code
    if counted and row.spell is not None:
        t.region[to]["arrivals_displaced"] += 1
        t.region[to][f"arrivals_displaced_{row.spell.anchor}"] += 1
        t.totals[f"arrivals_displaced_{row.spell.anchor}"] += 1


def _unobserved(state: ResidenceLedgerState, turn: int, reason: str) -> list:
    state.frame = state.events = None
    state.events_dropped = 0
    state.frame_turn = turn
    _bump(state, "turns_unobserved")
    _log(state, turn, "unobserved", reason=reason)
    return []


def phase10(world, acc, economy_result, agent_bridge):
    """The one writer: update the rows from T's moves, snapshot, trips, rosters
    and region events, and write T's frame. Changes nothing else."""
    state = _state(world)
    turn = int(world.turn)
    if state.frame_turn is not None and state.frame_turn >= turn:
        raise RuntimeError("residence ledger written twice in one turn")
    pending, state.pending = state.pending, None
    sim = getattr(agent_bridge, "_sim", None) if agent_bridge is not None else None
    if sim is None:
        return _unobserved(state, turn, "no agent pool")
    if not all(callable(getattr(sim, name, None)) for name in NATIVE):
        raise RuntimeError("the residence ledger requires a native build with trip_agent_ids")
    n = len(world.regions)
    t = _Turn(turn, n)
    if pending is not None and pending.get("turn") == turn:
        for row in pending["events"]:
            t.totals["pool_reset"] += 1
            t.event(row)
        t.totals["pool_reset"] += pending.get("unlisted", 0)
        t.dropped += pending.get("unlisted", 0)
    if state.last_turn is not None and state.last_turn != turn - 1:
        # Turns the ledger did not observe: moves and returns may be missing.
        for aid, row in sorted(state.rows.items()):
            if row.spell is not None:
                t.totals["unobserved_gap"] += 1
                t.event(_event(aid, "unobserved_gap", row.spell, row.res, turn))
        closed = _end_epoch(state, "unobserved_gap")
        _bump(state, "gaps")
        _log(state, turn, "gap", last_turn=state.last_turn, spells_closed=closed)
        for w in state.regions:
            w.controller_seen = False
        state.watch_from = None
    _watch_regions(world, state, t)
    if state.observed_from is None:
        state.observed_from = turn
    first_epoch_turn = state.observed_from == turn

    snap = sim.get_snapshot()
    cols = [snap.column(name).to_pylist() for name in ("id", "region", "origin_region", "displacement_turn")]
    alive = {int(i): (int(r), int(o), int(d)) for i, r, o, d in zip(*cols)}
    trips = {int(i) for i in sim.trip_agent_ids()}
    rows = state.rows
    deferred = set(state.deferred)
    travelling = set(state.travelling)
    refused = 0

    def new_row(aid: int, home: int, res: int) -> ResidenceRow | None:
        nonlocal refused
        if len(rows) >= MAX_ROWS:
            refused += 1
            return None
        newborn = not first_epoch_turn and aid not in deferred
        deferred.discard(aid)
        row = rows[aid] = ResidenceRow(home=home, home_since=turn, res=res, res_since=turn, first_seen=turn)
        t.totals["new_rows"] += 1
        t.totals["newborn_rows"] += int(newborn)
        return row

    # 1. T's applied moves, in native order.
    moved: set[int] = set()
    moves, invalid = _turn_moves(world, n)
    if invalid:
        t.totals["invalid_moves"] += invalid
        _bump(state, "invalid_moves", invalid)
    for aid, frm, to, code in moves:
        row = rows.get(aid)
        if row is None:
            if aid not in alive:
                continue                  # never observed, and gone after the tick
            row = new_row(aid, frm, frm)  # first observed with this move: home is the region left
            if row is None:
                continue
        elif row.res != frm and aid in travelling:
            # A trip ended away from the residence in the same tick as this move.
            t.totals["trip_relocations"] += 1
            _bump(state, "trip_relocations")
            _move(state, t, aid, row, row.res, frm, None, counted=False)
        _move(state, t, aid, row, frm, to, code)
        moved.add(aid)

    # 2. Everyone else alive: first observations, travellers, unexplained relocations.
    for aid in sorted(alive):
        if aid in moved:
            continue
        region, origin, _d = alive[aid]
        row = rows.get(aid)
        if row is None:
            if aid in trips:
                deferred.add(aid)         # recorded at the end of the trip
                continue
            newborn = not first_epoch_turn and aid not in deferred
            home = origin if newborn else region
            row = new_row(aid, home, region)
            if row is not None and home != region:
                # A newborn living outside its birth region without a move: re-home it there.
                row.home = region
                t.totals["unexplained_relocations"] += 1
                _bump(state, "unexplained_relocations")
        elif aid not in trips and region != row.res:
            # Not an applied migration: a trip that ended away from the
            # residence (a native unwind on conquest leaves the traveller where
            # it was), else unexplained. Either is an unclassified relocation.
            key = "trip_relocations" if aid in travelling else "unexplained_relocations"
            t.totals[key] += 1
            _bump(state, key)
            _move(state, t, aid, row, row.res, region, None, counted=False)

    # 3. Deaths (in this tick, or since the last observed turn), in ascending id.
    for aid in sorted(rows.keys() - alive.keys()):
        row = rows.pop(aid)
        t.region[row.res]["deaths"] += 1
        t.totals["deaths"] += 1
        if row.spell is not None:
            _close(state, t, aid, row, "died", row.res)
    deferred = {aid for aid in deferred if aid in alive and aid not in rows}

    # 4. Resettlement after REHOME_TURNS at one residence, in ascending id.
    due = sorted(aid for aid, row in rows.items()
                 if row.spell is not None and turn - row.res_since >= REHOME_TURNS)
    for aid in due:
        row = rows[aid]
        _close(state, t, aid, row, "resettled", row.res)
        row.home, row.home_since = row.res, turn

    # 5. Attachment from the reconciled rosters (enlistment never re-homes): only
    #    the people attached at the last write are cleared (review m2).
    for aid in state.attached:
        row = rows.get(aid)
        if row is not None:
            row.army = row.army_region = None
    attached = set()
    for army in getattr(getattr(world, "war_state", None), "armies", None) or []:
        where = _region_index(world, army.region)
        for aid, _region in army.roster:
            row = rows.get(int(aid))
            if row is not None:
                row.army, row.army_region = army.army_id, where
                attached.add(int(aid))

    # 6. Stocks after the turn, and the frame.
    totals, reg = t.totals, t.region
    for aid, row in rows.items():
        r = reg[row.res]
        r["residents"] += 1
        spell = row.spell
        if spell is not None:
            r["displaced"] += 1
            r[f"displaced_{spell.cause}"] += 1
            r[f"displaced_{spell.anchor}"] += 1
            reg[spell.origin]["displaced_from"] += 1
            reg[spell.origin][f"displaced_from_{spell.anchor}"] += 1
            totals[f"displaced_from_{spell.anchor}"] += 1
            totals["displaced"] += 1
            totals[f"displaced_{spell.cause}"] += 1
            totals[f"displaced_{spell.anchor}"] += 1
            for kind in spell.anchor_kinds:
                totals[f"anchor_any_{kind}"] += 1
            totals["anchor_war_or_famine"] += int("war" in spell.anchor_kinds or "famine" in spell.anchor_kinds)
            totals["anchor_partial"] += int(spell.anchor_partial)
        if row.army is not None:
            reg[row.home]["attached"] += 1
            totals["attached"] += 1
            if row.army_region != row.home:
                reg[row.home]["attached_away"] += 1
                totals["attached_away"] += 1
        if aid in trips and alive[aid][0] != row.res:
            r["in_transit"] += 1
            totals["in_transit"] += 1
    totals["alive"] = len(alive)
    totals["observed"] = len(rows)
    totals["deferred"] = len(deferred)
    totals["recent_movers_native"] = sum(1 for _r, _o, d in alive.values() if d > 0)
    totals["away_from_birth_region"] = sum(1 for r, o, _d in alive.values() if r != o)
    regions = [{"region": i, **values} for i, values in enumerate(reg) if any(values.values())]
    if refused:
        _bump(state, "rows_refused", refused)
        _log(state, turn, "rows_refused", refused=refused, max_rows=MAX_ROWS)
    if t.dropped:
        _bump(state, "events_dropped", t.dropped)
    # ``rows`` keeps its deterministic insertion order (pickled as it is).
    state.rows_held, state.open_spells_held = len(rows), totals["displaced"]
    state.deferred = sorted(deferred)
    state.travelling = sorted(trips)
    state.attached = sorted(attached)
    state.frame = {"turn": turn, "observed_from": state.observed_from, "totals": totals, "regions": regions}
    state.events, state.events_dropped = t.events, t.dropped
    state.frame_turn = state.last_turn = turn
    _bump(state, "turns_observed")
    return []


# ---------------------------------------------------------------------------
# Readers (audit 11.4): T's frame to a consumer at T+1, never the same turn
# ---------------------------------------------------------------------------

def _dated(world, consumer_turn: int) -> ResidenceLedgerState | None:
    if not isinstance(consumer_turn, int) or isinstance(consumer_turn, bool):
        raise TypeError("consumer_turn must be the consumer's turn (an int)")
    if consumer_turn != int(world.turn):
        raise LedgerReadRefused(f"a consumer reads the residence ledger at its own turn: consumer_turn "
                                f"{consumer_turn} is not the world's turn {world.turn}")
    state = _state(world)
    if state is None or not residence_ledger_active(world) or state.frame_turn is None:
        return None
    if state.frame_turn >= consumer_turn:
        raise LedgerReadRefused(f"same-turn read refused: the residence ledger frame of turn {state.frame_turn} "
                                f"is readable from turn {state.frame_turn + 1}")
    if state.frame_turn != consumer_turn - 1 or state.frame is None:
        return None
    return state


def read_frame(world, *, consumer_turn: int) -> dict | None:
    """The aggregates of turn ``consumer_turn - 1`` (a copy): totals and region
    rows, no person. None: that turn was not observed (or the ledger is off).
    Refuses a same-turn or future read."""
    state = _dated(world, consumer_turn)
    return copy.deepcopy(state.frame) if state is not None else None


class OwnRow:
    """One person's own row as of turn T, bound to that person (A6: one's own
    experience; review m4).

    A6's dispatcher makes one per agent it decides for
    (:func:`own_row_accessor`) and hands it to that agent's decision, which
    reads only through it: :meth:`read` refuses any other id, and refuses once
    the world is no longer at the consumer turn the accessor was made for."""

    __slots__ = ("_world", "_agent_id", "_consumer_turn")

    def __init__(self, world, agent_id: int, consumer_turn: int):
        self._world, self._agent_id, self._consumer_turn = world, int(agent_id), int(consumer_turn)

    @property
    def agent_id(self) -> int:
        return self._agent_id

    def read(self, agent_id: int) -> dict | None:
        """The bound person's row (every key, None included), or None when the
        person or T was not observed. Refuses another person's id."""
        if int(agent_id) != self._agent_id:
            raise LedgerReadRefused(f"own row only: this accessor is bound to agent {self._agent_id}, "
                                    f"not {int(agent_id)}")
        state = _dated(self._world, self._consumer_turn)
        if state is None:
            return None
        row = state.rows.get(self._agent_id)
        if row is None:
            return None
        return {"id": self._agent_id, "source_turn": state.frame_turn, "home": row.home,
                "home_since": row.home_since, "res": row.res, "res_since": row.res_since,
                "first_seen": row.first_seen, "move_turn": row.move_turn, "move_from": row.move_from,
                "move_driver": row.move_driver, "spell": asdict(row.spell) if row.spell is not None else None,
                "army": row.army, "army_region": row.army_region}


def own_row_accessor(world, agent_id: int, *, consumer_turn: int) -> OwnRow:
    """An :class:`OwnRow` bound to ``agent_id`` for a consumer at
    ``consumer_turn`` (refuses a same-turn or other-turn consumer now)."""
    _dated(world, consumer_turn)
    return OwnRow(world, agent_id, consumer_turn)


def separation(world, agent_bridge, *, consumer_turn: int) -> dict | None:
    """Family separation computed on demand (D3), from T's rows and the native
    marriage bonds, parents and trips read now: exact from T's write to T+1's
    agent tick (nothing native changes in between); a call after T+1's tick
    pairs T's residences with T+1's bonds. Never stored; no per-turn cost."""
    state = _dated(world, consumer_turn)
    if state is None:
        return None
    from chronicler.ffi_constants import BOND_MARRIAGE
    sim = agent_bridge._sim
    rel = sim.get_all_relationships()
    snap = sim.get_snapshot()
    trips = {int(i) for i in sim.trip_agent_ids()}
    cols = [snap.column(name).to_pylist() for name in ("id", "region", "age", "parent_id_0", "parent_id_1")]
    live = {int(i): (int(r), int(a), int(p0), int(p1)) for i, r, a, p0, p1 in zip(*cols)}
    rows = state.rows
    pairs: set[tuple[int, int, str]] = set()
    for x, y, kind in zip(rel.column("agent_id").to_pylist(), rel.column("target_id").to_pylist(),
                          rel.column("bond_type").to_pylist()):
        if int(kind) == int(BOND_MARRIAGE) and int(x) in rows and int(y) in rows and int(x) != int(y):
            pairs.add((min(int(x), int(y)), max(int(x), int(y)), "spouse"))
    for child, (_r, age, p0, p1) in live.items():
        if age < ADULT_AGE and child in rows:
            for parent in (p0, p1):
                if parent != child and parent in rows:
                    pairs.add((child, parent, "parent"))

    def location(aid: int, row: ResidenceRow) -> int:
        if row.army is not None and row.army_region is not None:
            return row.army_region
        if aid in trips and aid in live:
            return live[aid][0]
        return row.res

    separated = []
    by_cause = dict.fromkeys(SEPARATION_CAUSES, 0)
    by_relation = {"spouse": 0, "parent": 0}
    for x, y, relation in sorted(pairs):
        rx, ry = rows[x], rows[y]
        lx, ly = location(x, rx), location(y, ry)
        cause = None
        if (x in trips or y in trips) and lx != ly:
            cause = "trip"
        elif (rx.army is not None or ry.army is not None) and lx != ly:
            cause = "attached"
        elif rx.res != ry.res:
            cause = "displaced" if rx.spell is not None or ry.spell is not None else "migrated"
        if cause is None:
            continue
        by_cause[cause] += 1
        by_relation[relation] += 1
        separated.append({"a": x, "b": y, "relation": relation, "cause": cause})
    return {"source_turn": state.frame_turn, "pairs": len(pairs), "separated": separated,
            "by_cause": by_cause, "by_relation": by_relation}


# ---------------------------------------------------------------------------
# Snapshot and record reading
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """The completed-turn record, dated by ``source_turn``; ``frame`` is None
    when that turn was not observed (unknown, not zero)."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source and state.frame is not None
    return {
        "schema_version": 1, "stage": STAGE, "source_turn": source, "observed_from": state.observed_from,
        # Copies: the record never aliases the ledger's own state.
        "frame": copy.deepcopy(state.frame) if fresh else None,
        "events": copy.deepcopy(state.events) if fresh else None,
        "events_dropped": state.events_dropped if fresh else 0,
        # Every declared counter, zeros included (a missing key is not a zero; review nit).
        "counters": {k: state.counters.get(k, 0) for k in COUNTERS},
        "log": [r.model_dump() for r in state.log], "log_dropped": state.log_dropped,
        "labels": dict(LABELS),
        "parameters": {"rehome_turns": REHOME_TURNS, "anchor_turns": ANCHOR_TURNS,
                       "famine_onset_cooldown": FAMINE_ONSET_COOLDOWN, "adult_age": ADULT_AGE,
                       "flight_drivers": list(FLIGHT_DRIVERS), "hunger_drivers": list(HUNGER_DRIVERS),
                       "voluntary_drivers": sorted(VOLUNTARY_MIGRATION_DRIVERS), "causes": list(CAUSES),
                       "anchors": list(ANCHORS), "move_groups": list(MOVE_GROUPS), "closures": list(CLOSURES),
                       "max_events": MAX_EVENTS, "max_rows": MAX_ROWS},
    }


#: Keys every observed frame carries (the record shape a reader may rely on).
FRAME_KEYS: tuple[str, ...] = ("turn", "observed_from", "totals", "regions")
#: Totals that are all zero in a recorded-zero frame.
_ZERO_KEYS: tuple[str, ...] = ("displaced", "attached", "moves", "opened", *CLOSURES, "deaths")


def record_status(snapshot) -> tuple[str, dict | None]:
    """How a reader treats one history snapshot's record (the reference for
    viewer and analysis readers): ``("absent", None)`` - the switch was never
    on or is off in that turn; ``("malformed", None)`` - present but not this
    record's shape; ``("unobserved", None)`` - the source turn was not observed
    (unknown, not zero); ``("recorded_zero", frame)`` - observed, and no one was
    displaced or attached and no one moved, left, returned, resettled or died;
    ``("recorded", frame)`` - observed with something in it."""
    livelihoods = snapshot.get("livelihoods") if isinstance(snapshot, dict) else None
    if not isinstance(livelihoods, dict) or "residence_ledger" not in livelihoods:
        return "absent", None
    record = livelihoods["residence_ledger"]
    source = record.get("source_turn") if isinstance(record, dict) else None
    if (not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("stage") != STAGE
            or not isinstance(source, int) or isinstance(source, bool) or "frame" not in record):
        return "malformed", None
    frame = record["frame"]
    if frame is None:
        return "unobserved", None
    totals = frame.get("totals") if isinstance(frame, dict) else None
    if (not isinstance(frame, dict) or any(key not in frame for key in FRAME_KEYS) or frame["turn"] != source
            or not isinstance(totals, dict) or any(not isinstance(totals.get(k), int) for k in TOTAL_KEYS)
            or not isinstance(frame["regions"], list)
            or any(not isinstance(r, dict) or any(not isinstance(r.get(k), int) for k in REGION_KEYS)
                   for r in frame["regions"])):
        return "malformed", None
    empty = all(totals[k] == 0 for k in _ZERO_KEYS)
    return ("recorded_zero" if empty else "recorded"), frame
