"""RS3 veteran reintegration (``--veteran-reintegration``, default off).

People who leave a real army alive are recorded by native stable id, and
while they remain eligible they come first, among candidates who are
otherwise eligible, for the openings other packages already have: workshop
crews (the native crew planner's ``priority_ids``), apprenticeship seats
(RS1) and repair crews (RS2). Nothing is guaranteed and nothing is created:
with no opening there is no placement, and no person, money or skill comes
from this package. Requires ``--agents hybrid`` and at least one of
``--workshops``, ``--apprenticeship`` and ``--repair-projects``. Modes
(``--veteran-mode``): ``priority`` (default) and the control
``record_only``, which captures, tracks and reports who would have been put
first, without changing anyone's order.

Capture (the campaign layer, ``war/armies.py`` and ``war/runtime.py``; a
no-op unless this switch is active). Rosters hold ``(stable id, region
index)`` pairs. A record is made where the roster loses a living person:

* ``release_soldiers``: the ``leaving`` ids, cause ``desertion`` or
  ``scattered`` (a broken army's survivors, an army too small to hold
  together, a returning army with no reachable home);
* ``disband``: whoever is still on the roster when it is cleared, cause
  ``demobilised`` (a returning army at home) or ``destroyed``; a destroyed
  army's survivors were already released as ``scattered``;
* the two silent removals in ``war/runtime.py``: an army dropped because its
  civilization is gone or its region vanished (``_validate_armies``) or
  because its civilization died during Phase 10 (``end_of_turn_sync``),
  cause ``dissolved``.

Deaths (``apply_casualties``, ``reconcile_rosters``) are not releases. A
non-exact roster redraft (``rebind_rosters``, a rebuilt pool) releases
nobody; :func:`on_pool_reset` closes every record of the old pool, and when
the rebuild finds enlisted rosters (which the campaign layer then keeps with
stale ids or redrafts) later releases from armies raised before it are not
captured (counted as ``captures_untrusted``), so a redraft never makes a
veteran. Each record holds the served civilization's
index, the army id, the war ``(war_key, start_turn)`` the army was raised
for (the war record, active or ended, of that key that was open at the
army's ``raised_turn``; None when none is found), the cause, the release
turn and the residence region.

Timing and exactly-once. Campaigns run in Phase 5, after this turn's Phase 2
crew planning and before the native agent tick. Captures are only buffered
(transient, stamped with the turn and the native pool). Phase 2 offers and
crew placements, and outcomes other packages report (:func:`note_outcome`),
are staged the same way. Everything is committed once, in this package's
``phase10`` hook, after the agent tick succeeded and against its post-tick
snapshot (``last_settled_turn`` refuses a second commit). A failed Phase 2
or agent tick therefore commits nothing: staged rows of another turn or pool
are discarded and counted at the next hook. The only later capture,
``end_of_turn_sync`` after Phase 10, commits directly into the turn already
settled. A checkpoint is written at a turn boundary, when nothing is staged.

Eligibility (evaluated live whenever :func:`priority_ids` is asked): an open
record (alive at the last post-tick observation), adult (native
``AGE_ADULT``, the crew planner's age), released before this turn and within
``ELIGIBLE_TURNS``, not on any army roster, and resident in a region whose
controller is the civilization they served. Residence follows migration;
the priority is honored only where the served civilization rules.

Outcomes, dated: ``placed:crew`` (this package compares the turn's workshop
receipts with the open records: a veteran on the crew of a site that
operated, with work allocated), ``placed:apprentice`` and ``placed:repair``
(reported by RS1 and RS2), ``waiting`` (eligible and unplaced; per turn the
frame names why: ``UNMET_REASONS``), ``migrated``, ``control_lost`` (their
region is not ruled by the served civilization), and the closing
``remobilised`` (on a roster again; a later release opens a new record),
``died``, ``expired`` and ``pool_reset``. Consecutive placed turns in one
kind of opening at one site are one spell; a later spell is another
placement. Unique people placed are counted once. Declared, uncalibrated:
``ELIGIBLE_TURNS``.
"""
from __future__ import annotations

from bisect import insort

from chronicler.veteran_reintegration_state import (
    CAUSES, CLOSING, COUNTERS, MAX_ARCHIVE, MAX_FRAME_ROWS, MAX_OPEN, MAX_OUTCOMES, MAX_PLACED_IDS,
    MAX_SPELLS, MODES, OUTCOMES, PLACEMENTS, CaptureRow, FrameOutcome, FramePlacement, FrameWaiting,
    PlacementSpell, VeteranFrame, VeteranOutcome, VeteranRecord, VeteranReintegrationState,
)

#: Turns after release during which a veteran is eligible (declared, uncalibrated).
ELIGIBLE_TURNS = 20
#: Native ``agent::AGE_ADULT``: the workshop crew planner's adult age.
AGE_ADULT = 20
#: Native occupation code of farmers (crew candidates are urban farmers).
FARMER = 0


class _Phase2:
    """This turn's offers and crew observations, staged until Phase 10."""

    __slots__ = ("turn", "eligible", "offered", "sites", "facts", "placements", "reasons")

    def __init__(self, turn, eligible, offered, sites, facts):
        self.turn, self.eligible, self.offered, self.sites, self.facts = turn, eligible, offered, sites, facts
        self.placements: list[tuple[int, str, dict]] = []
        self.reasons: dict[int, str] = {}


def _state(world) -> VeteranReintegrationState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "veteran_reintegration", None) if container is not None else None


def _bump(state: VeteranReintegrationState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(key)
    if amount:
        state.counters[key] = state.counters.get(key, 0) + int(amount)


def set_veteran_reintegration_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--veteran-mode``, default ``priority``) or disable; an
    omitted mode keeps the saved one."""
    mode = getattr(args, "veteran_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.veteran_reintegration = state = VeteranReintegrationState(mode=mode or MODES[0])
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


def veteran_reintegration_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enlisted(world) -> dict[int, str]:
    """Every stable id on an army roster now, with its army id."""
    armies = getattr(getattr(world, "war_state", None), "armies", None) or []
    return {int(aid): army.army_id for army in armies for aid, _ in army.roster}


def _ruler(world, region: int) -> int | None:
    if not 0 <= region < len(world.regions):
        return None
    controller = world.regions[region].controller
    return world.civ_index_map.get(controller) if controller is not None else None


def _war_of(world, army) -> tuple[str | None, int | None]:
    """The war ``army`` was raised for: the record of its key open at its raise turn."""
    state = world.war_state
    best = None
    for war in (*state.wars, *state.ended_wars):
        if war.war_key != army.war_key or war.start_turn > army.raised_turn:
            continue
        if war.ended_turn is not None and war.ended_turn < army.raised_turn:
            continue
        if best is None or war.start_turn > best.start_turn:
            best = war
    return (best.war_key, best.start_turn) if best is not None else (None, None)


def _eligible(world, record: VeteranRecord, turn: int, enlisted) -> bool:
    return (record.status != "closed" and record.released_turn < turn
            and turn - record.released_turn <= ELIGIBLE_TURNS
            and record.age is not None and record.age >= AGE_ADULT
            and record.agent_id not in enlisted and _ruler(world, record.region) == record.civ)


def _ordered(state: VeteranReintegrationState, region: int, eligible: set[int]) -> list[int]:
    rows = [r for r in state.records if r.region == region and r.agent_id in eligible]
    return [r.agent_id for r in sorted(rows, key=lambda r: (r.released_turn, r.agent_id))]


def _eligible_ids(world, state: VeteranReintegrationState) -> set[int]:
    enlisted = _enlisted(world)
    return {r.agent_id for r in state.records if _eligible(world, r, world.turn, enlisted)}


def _observe(snapshot, wanted: set[int], names: tuple[str, ...]) -> dict[int, tuple[int, ...]]:
    """``{id: (values of names)}`` for wanted ids alive in the snapshot."""
    if not wanted:
        return {}
    from chronicler.columnar import batch_arrays, last_row_of, pylist
    arrays = batch_arrays(snapshot, ("id", *names))
    if arrays is not None:
        rows = last_row_of(arrays[0], wanted)
        return {aid: tuple(int(col[row]) for col in arrays[1:]) for aid, row in rows.items()}
    columns = [pylist(snapshot.column(name)) for name in ("id", *names)]
    out = {}
    for values in zip(*columns):
        aid = int(values[0])
        if aid in wanted:
            out[aid] = tuple(int(v) for v in values[1:])
    return out


def _check_detail(detail) -> dict | None:
    if detail is None:
        return None
    if not isinstance(detail, dict) or len(detail) > 8:
        raise TypeError("veteran outcome detail must be a small dict")
    for key, value in detail.items():
        if not isinstance(key, str) or not (value is None or isinstance(value, (bool, int, float, str))):
            raise TypeError("veteran outcome detail must map names to JSON scalars")
    return dict(detail)


class _Turn:
    """Frame rows collected while one turn is committed."""

    def __init__(self, state: VeteranReintegrationState, frame: VeteranFrame):
        self.state, self.frame = state, frame
        #: Ids captured in this frame's turn (a second release the same turn is a duplicate).
        self.captured: set[int] = {r.agent_id for r in frame.captured}

    def row(self, name: str, value) -> None:
        rows = getattr(self.frame, name)
        if len(rows) < MAX_FRAME_ROWS:
            rows.append(value)
        else:
            self.frame.rows_dropped += 1

    def outcome(self, record: VeteranRecord, turn: int, kind: str, detail: dict | None = None) -> None:
        record.outcomes.append(VeteranOutcome(turn=turn, kind=kind, detail=detail))
        if len(record.outcomes) > MAX_OUTCOMES:
            dropped = len(record.outcomes) - MAX_OUTCOMES
            del record.outcomes[:dropped]
            record.outcomes_dropped += dropped
            _bump(self.state, "outcomes_dropped", dropped)
        self.row("outcomes", FrameOutcome(agent_id=record.agent_id, record_id=record.record_id,
                                          kind=kind, detail=detail))

    def close(self, record: VeteranRecord, turn: int, reason: str, detail: dict | None = None) -> None:
        state = self.state
        self.outcome(record, turn, reason, detail)
        record.status, record.reason = "closed", None
        record.closed_turn, record.closed_reason = turn, reason
        state.records.remove(record)
        state.archive.append(record)
        del state.archive[:-MAX_ARCHIVE]
        _bump(state, "closed_" + reason)

    def place(self, record: VeteranRecord, turn: int, kind: str, detail: dict | None,
              prioritised: bool) -> None:
        state = self.state
        detail = dict(detail or {})
        site = detail.get("site")
        site = int(site) if isinstance(site, int) and not isinstance(site, bool) else None
        region = detail.get("region")
        region = int(region) if isinstance(region, int) and not isinstance(region, bool) else record.region
        if any(s.kind == kind and s.site == site and s.last_turn == turn for s in record.spells):
            return                                    # the same opening reported twice this turn
        spell = next((s for s in reversed(record.spells)
                      if s.kind == kind and s.site == site and s.last_turn == turn - 1), None)
        record.placed_turns += 1
        _bump(state, "placement_turns")
        if spell is not None:
            spell.last_turn, spell.turns = turn, spell.turns + 1
        else:
            record.spells.append(PlacementSpell(kind=kind, site=site, region=region, start_turn=turn,
                                                last_turn=turn, prioritised=prioritised))
            if len(record.spells) > MAX_SPELLS:
                del record.spells[0]
                _bump(state, "spells_dropped")
            record.placements += 1
            _bump(state, "placements")
            _bump(state, "placements_" + kind.split(":", 1)[1])
            if prioritised:
                _bump(state, "placed_prioritised")
            self.outcome(record, turn, kind, {**detail, "site": site, "region": region,
                                              "prioritised": prioritised})
            if record.agent_id not in state.ever_placed:
                if len(state.ever_placed) < MAX_PLACED_IDS:
                    insort(state.ever_placed, record.agent_id)
                    _bump(state, "people_placed")
                else:
                    _bump(state, "people_placed_unverified")
        record.status = "placed"
        self.row("placed", FramePlacement(agent_id=record.agent_id, kind=kind, region=region, site=site,
                                          prioritised=prioritised, new_spell=spell is None))

    def status(self, world, record: VeteranRecord, turn: int) -> None:
        """Label an open record after this turn's observation: why it is not
        eligible (``reason``, kept while placed) and its status (eligibility
        for the next turn's openings is still checked live)."""
        ruler = _ruler(world, record.region)
        reason = None
        if record.age is None:
            reason = "unobserved"
        elif record.age < AGE_ADULT:
            reason = "minor"
        elif ruler != record.civ:
            reason = "control_lost"
        if reason == "control_lost" and record.reason != "control_lost":
            self.outcome(record, turn, "control_lost",
                         {"region": record.region, "controller": -1 if ruler is None else ruler})
            _bump(self.state, "control_lost")
        record.reason = reason
        if any(s.last_turn == turn for s in record.spells):
            record.status = "placed"
        elif reason is None:
            if record.status != "waiting":
                self.outcome(record, turn, "waiting", {"region": record.region})
            record.status = "waiting"
        else:
            record.status = "ineligible"

    def capture(self, item) -> list[VeteranRecord]:
        """Open a record for each person of one buffered release."""
        state = self.state
        turn, _pool, army_id, civ, war_key, war_start, cause, rows = item
        made = []
        for aid, region in rows:
            if aid in self.captured:
                _bump(state, "capture_duplicates")
                continue
            self.captured.add(aid)
            for old in [r for r in state.records if r.agent_id == aid]:
                # Released again before any observation found them enlisted.
                self.close(old, turn, "remobilised", {"army_id": army_id})
            _bump(state, "captured")
            _bump(state, "captured_" + cause)
            self.frame.captured_total += 1
            self.frame.captured_by_cause[cause] = self.frame.captured_by_cause.get(cause, 0) + 1
            self.row("captured", CaptureRow(agent_id=aid, civ=civ, army_id=army_id, war_key=war_key,
                                            war_start=war_start, cause=cause, region=region))
            if len(state.records) >= MAX_OPEN:
                _bump(state, "capture_overflow")
                continue
            record = VeteranRecord(record_id=state.next_record_id, agent_id=aid, civ=civ, army_id=army_id,
                                   war_key=war_key, war_start=war_start, cause=cause, released_turn=turn,
                                   released_region=region, region=region, status="ineligible",
                                   reason="unobserved")
            state.next_record_id += 1
            state.records.append(record)
            made.append(record)
        return made


def _new_turn(state: VeteranReintegrationState, turn: int, offered) -> _Turn:
    return _Turn(state, VeteranFrame(turn=turn, priority_applied=state.mode == "priority", offered=offered))


def _counts(state: VeteranReintegrationState, frame: VeteranFrame, plan) -> dict[str, int]:
    """End-of-turn record statuses, and (only when Phase 2 was observed) how
    many were eligible for this turn's openings and how many of those waited."""
    statuses = [r.status for r in state.records]
    counts = {
        "open": len(state.records),
        "status_waiting": statuses.count("waiting"),
        "status_placed": statuses.count("placed"),
        "status_ineligible": statuses.count("ineligible"),
        "control_lost": sum(1 for r in state.records if r.reason == "control_lost"),
        "minor": sum(1 for r in state.records if r.reason == "minor"),
        "unobserved": sum(1 for r in state.records if r.reason == "unobserved"),
        "captured": frame.captured_total,
        "placed": sum(1 for p in frame.placed),
        "closed": sum(1 for r in state.archive if r.closed_turn == frame.turn),
    }
    if plan is not None:
        counts["eligible"] = len(plan.eligible)
        counts["waiting"] = sum(1 for _ in frame.waiting)
    return counts


# ---------------------------------------------------------------------------
# Capture (called from the campaign layer)
# ---------------------------------------------------------------------------

def capture_release(world, army, entries, cause: str, *, bridge=None, commit: bool = False) -> None:
    """Buffer the living people ``entries`` (``(stable id, region index)``
    roster pairs) who left ``army`` for ``cause`` (``CAUSES``). A no-op
    unless the switch is active. ``commit`` (end of turn, after Phase 10):
    record them into the turn already settled."""
    if cause not in CAUSES:
        raise ValueError(f"unknown veteran release cause {cause!r}")
    if not entries or not veteran_reintegration_active(world):
        return
    state = _state(world)
    if state.pool_reset_turn is not None and army.raised_turn < state.pool_reset_turn:
        # Its roster was bound to a rebuilt pool: kept stale ids or a redraft.
        _bump(state, "captures_untrusted", len(entries))
        return
    sim = getattr(bridge, "_sim", None) if bridge is not None else None
    civ = world.civ_index_map.get(army.civ, -1)
    war_key, war_start = _war_of(world, army)
    rows = tuple(sorted((int(aid), int(region)) for aid, region in entries))
    item = (world.turn, id(sim) if sim is not None else None, army.army_id, civ, war_key, war_start, cause, rows)
    if commit and state.last_settled_turn == world.turn and state.frame_turn == world.turn \
            and state.frame is not None:
        collector = _Turn(state, state.frame)
        for record in collector.capture(item):
            collector.status(world, record, world.turn)
        counts = _counts(state, state.frame, None)
        state.frame.counts = {**state.frame.counts, **counts}
        return
    state._captures.append(item)


# ---------------------------------------------------------------------------
# Livelihoods package protocol
# ---------------------------------------------------------------------------

def _discard_stale(state: VeteranReintegrationState, turn: int, pool) -> None:
    keep, stale = [], 0
    for item in state._captures:
        if item[0] == turn and item[1] == pool:
            keep.append(item)
        else:
            stale += len(item[7])
    state._captures = keep
    _bump(state, "captures_discarded", stale)
    notes = [n for n in state._noted if n[0] == turn]
    _bump(state, "notes_discarded", len(state._noted) - len(notes))
    state._noted = notes
    if state._phase2 is not None and state._phase2.turn != turn:
        state._phase2 = None


def _pool(agent_bridge):
    sim = getattr(agent_bridge, "_sim", None) if agent_bridge is not None else None
    return id(sim) if sim is not None else None


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Stage this turn's offers (what ``priority_ids`` gave, or would give,
    each workshop site region) and the offered people's crew facts."""
    state = _state(world)
    turn = world.turn
    _discard_stale(state, turn, _pool(agent_bridge))
    state._phase2 = None
    ids = _eligible_ids(world, state)
    eligible = {r.agent_id: r.region for r in state.records if r.agent_id in ids}
    sites = {}
    workshops = getattr(world.livelihoods, "workshops", None)
    from chronicler.workshops import workshops_active
    if workshops is not None and workshops_active(world):
        sites = {s.region: (s.site, s.settlement_id) for s in workshops.sites}
    offered = [(region, _ordered(state, region, eligible)) for region in sites]
    wanted = {aid for _, ids in offered for aid in ids}
    facts = _observe(snapshot, wanted, ("region", "occupation", "age", "settlement_id")) if wanted else {}
    state._phase2 = _Phase2(turn, eligible, offered, sites, facts)
    return region_input


def finish_phase2(world, economy_result, agent_bridge, acc) -> list:
    """Stage crew placements from this turn's workshop receipts and why each
    offered veteran was not placed."""
    state = _state(world)
    plan = state._phase2
    if plan is None or plan.turn != world.turn:
        return []
    workshops = getattr(world.livelihoods, "workshops", None)
    receipts = {}
    if workshops is not None and workshops.frame_turn == world.turn:
        receipts = {r.region: r for r in workshops.frame}
    open_ids = {r.agent_id for r in state.records}
    offered = {region: ids for region, ids in plan.offered}
    placed = set()
    for region in sorted(receipts):
        receipt = receipts[region]
        if workshops.mode == "observe" or receipt.allocated <= 0.0:
            continue
        for aid in receipt.crew:
            if aid in open_ids and aid not in placed:
                placed.add(aid)
                prioritised = state.mode == "priority" and aid in offered.get(region, ())
                plan.placements.append((aid, "placed:crew",
                                        {"site": receipt.site, "region": region, "prioritised": prioritised}))
    for region, ids in plan.offered:
        receipt = receipts.get(region)
        site = plan.sites.get(region)
        for aid in ids:
            if aid in placed:
                continue
            if receipt is None or site is None:
                reason = "unplaced"
            elif workshops.mode == "observe" or receipt.allocated <= 0.0:
                reason = "site_idle"
            else:
                fact = plan.facts.get(aid)
                crew_eligible = (fact is not None and fact[0] == region and fact[1] == FARMER
                                 and fact[2] >= AGE_ADULT and fact[3] == site[1])
                if not crew_eligible:
                    reason = "not_crew_eligible"
                elif len(receipt.crew) < receipt.eligible:
                    reason = "crew_full"
                else:
                    reason = "unplaced"
            plan.reasons[aid] = reason
    return []


def rollback_phase2(world) -> None:
    """A failed Phase 2: drop the staged offers and placements."""
    state = _state(world)
    if state is not None:
        state._phase2 = None


def rollback_agent_tick(world, agent_bridge) -> None:
    """A failed agent tick: nothing of this turn is committed."""
    state = _state(world)
    if state is not None:
        state._captures, state._noted, state._phase2 = [], [], None


def phase10(world, acc, economy_result, agent_bridge) -> list:
    """Commit this turn once, after the agent tick: placements, captures,
    and each open record's observation (death, re-enlistment, residence,
    expiry, control)."""
    state = _state(world)
    turn = world.turn
    if state.last_settled_turn is not None and turn <= state.last_settled_turn:
        raise RuntimeError("veteran records already settled for this turn")
    if agent_bridge is None or getattr(agent_bridge, "_sim", None) is None:
        raise RuntimeError("veteran reintegration requires the native agent pool")
    snapshot = agent_bridge.get_snapshot()
    if snapshot is None:
        raise RuntimeError("veteran reintegration requires the post-tick agent snapshot")
    _discard_stale(state, turn, _pool(agent_bridge))
    captures, notes, plan = state._captures, state._noted, state._phase2
    state._captures, state._noted, state._phase2 = [], [], None
    wanted = {r.agent_id for r in state.records} | {aid for item in captures for aid, _ in item[7]}
    observed = _observe(snapshot, wanted, ("region", "age"))
    enlisted = _enlisted(world)
    collector = _new_turn(state, turn, [(r, list(ids)) for r, ids in plan.offered] if plan else None)
    carry, state._carry = state._carry, None
    if carry is not None and carry[0] == turn:
        collector.frame.outcomes.extend(carry[1])
        collector.frame.rows_dropped += carry[2]
    if plan is not None:
        _bump(state, "offered" if state.mode == "priority" else "would_offer",
              len({aid for _, ids in plan.offered for aid in ids}))
    # 1. Placements (Phase 2 and other packages' reports precede this turn's releases).
    by_id = {r.agent_id: r for r in state.records}
    eligible = plan.eligible if plan is not None else {}
    for aid, kind, detail in (plan.placements if plan is not None else []):
        record = by_id.get(aid)
        if record is not None:
            collector.place(record, turn, kind, detail, bool(detail.get("prioritised")))
    for _turn, aid, kind, detail in notes:
        record = by_id.get(aid)
        if record is None or record.status == "closed":
            continue
        if kind in PLACEMENTS:
            prioritised = state.mode == "priority" and aid in eligible
            collector.place(record, turn, kind, detail, prioritised)
        elif kind in CLOSING:
            collector.close(record, turn, kind, detail)
        elif not any(o.turn == turn and o.kind == kind for o in record.outcomes):
            collector.outcome(record, turn, kind, detail)
    # 2. This turn's releases.
    for item in captures:
        collector.capture(item)
    # 3. Observe every open record against the post-tick pool.
    for record in sorted(state.records, key=lambda r: r.record_id):
        seen = observed.get(record.agent_id)
        if seen is None:
            collector.close(record, turn, "died", {"region": record.region})
            continue
        if record.agent_id in enlisted:
            collector.close(record, turn, "remobilised", {"army_id": enlisted[record.agent_id]})
            continue
        region, age = seen
        record.age = age
        if region != record.region:
            collector.outcome(record, turn, "migrated", {"from": record.region, "to": region})
            _bump(state, "migrations")
            record.region = region
        if turn - record.released_turn >= ELIGIBLE_TURNS:
            collector.close(record, turn, "expired", {"placed_turns": record.placed_turns})
            continue
        collector.status(world, record, turn)
    # 4. Who waited this turn, and why: eligible for this turn's openings at
    #    Phase 2 and placed nowhere (unknown without an observed Phase 2).
    for aid in sorted(plan.eligible) if plan is not None else ():
        record = by_id.get(aid)
        if record is None or any(s.last_turn == turn for s in record.spells):
            continue
        region = plan.eligible[aid]
        reason = plan.reasons.get(aid) or ("no_site" if region not in plan.sites else "unplaced")
        collector.row("waiting", FrameWaiting(agent_id=aid, region=region, reason=reason))
        _bump(state, "waiting_turns")
        _bump(state, "unmet_" + reason)
    frame = collector.frame
    frame.counts = _counts(state, frame, plan)
    state.frame, state.frame_turn, state.last_settled_turn = frame, turn, turn
    return []


def on_pool_reset(world) -> None:
    """A rebuilt native pool (``livelihoods.bind_native_pool``): open records
    name other people now and close with ``pool_reset``; ids for the
    unique-person count are dropped (the count is kept)."""
    state = _state(world)
    if state is None:
        return
    turn = world.turn
    if any(army.roster for army in getattr(getattr(world, "war_state", None), "armies", None) or []):
        # These rosters name the old pool; the campaign layer keeps or redrafts
        # them (``rebind_rosters``) and their later releases are not veterans.
        state.pool_reset_turn = turn
    current = getattr(world.livelihoods, "_pool_sim", None)
    stale = [item for item in state._captures if item[1] != current]
    if not (state.records or stale or state._noted or state.ever_placed):
        return
    collector = _new_turn(state, turn, None)
    for record in sorted(state.records, key=lambda r: r.record_id):
        collector.close(record, turn, "pool_reset")
    # Shown in the frame this turn's Phase 10 builds.
    state._carry = (turn, list(collector.frame.outcomes), collector.frame.rows_dropped)
    _bump(state, "captures_discarded", sum(len(item[7]) for item in stale))
    state._captures = [item for item in state._captures if item[1] == current]
    state._noted, state._phase2 = [], None
    state.ever_placed = []
    _bump(state, "pool_resets")


def snapshot_summary(world) -> dict:
    """The completed-turn observation (copied; never final state)."""
    state = _state(world)
    source = world.turn - 1
    observed = state.frame_turn == source and state.frame is not None
    open_records = sorted(state.records, key=lambda r: (r.released_turn, r.agent_id))
    shown = open_records[:64]
    return {
        "schema_version": 1, "stage": "RS3", "enabled": state.enabled, "mode": state.mode,
        "source_turn": source,
        # None: no veteran turn was committed in the source turn (unknown, not zero).
        "frame": state.frame.model_dump(mode="json") if observed else None,
        "veterans": [r.model_dump(mode="json") for r in shown],
        "veterans_omitted": len(open_records) - len(shown),
        "closed": [r.model_dump(mode="json") for r in state.archive if r.closed_turn == source],
        "counters": dict(state.counters),
        "parameters": {"eligible_turns": ELIGIBLE_TURNS, "adult_age": AGE_ADULT, "max_open": MAX_OPEN,
                       "max_outcomes": MAX_OUTCOMES, "max_frame_rows": MAX_FRAME_ROWS,
                       "costs": "none: placements are paid by the package that owns the opening"},
    }


# ---------------------------------------------------------------------------
# Cross-lane API
# ---------------------------------------------------------------------------

def open_record_ids(world) -> frozenset[int]:
    """Stable ids holding an open veteran record (eligible or not), whom other
    packages report placements for (``note_outcome``); empty while inactive.
    Unlike :func:`priority_ids` it is the same in ``record_only``."""
    state = _state(world)
    if state is None or not veteran_reintegration_active(world):
        return frozenset()
    return frozenset(r.agent_id for r in state.records if r.status != "closed")


def eligible_ids(world, region: int | None = None) -> list[int]:
    """Stable ids of veterans eligible now under RS3's rule, the same in both
    modes: an open record, released before this turn and at most
    ``ELIGIBLE_TURNS`` turns ago, adult (``AGE_ADULT``) at the last
    observation, on no army roster now, and resident in a region ruled by the
    civilization they served. ``region`` (an index in ``world.regions``)
    keeps those resident there; None keeps every region. Order: earliest
    release first, then ascending id (the order :func:`priority_ids` offers).
    ``[]`` while inactive. Admission by another package (PL3 recovery crews)
    reads this; the order is applied only through :func:`priority_ids`."""
    state = _state(world)
    if state is None or not veteran_reintegration_active(world):
        return []
    eligible = _eligible_ids(world, state)
    if region is not None:
        return _ordered(state, int(region), eligible)
    rows = [r for r in state.records if r.agent_id in eligible]
    return [r.agent_id for r in sorted(rows, key=lambda r: (r.released_turn, r.agent_id))]


def priority_ids(world, region: int) -> list[int]:
    """Stable ids of eligible veterans resident in ``region`` (an index in
    ``world.regions``), earliest release first, then id; ``[]`` in the
    ``record_only`` control or while inactive. Callers put them first among
    candidates who are otherwise eligible; nothing is guaranteed."""
    state = _state(world)
    if state is None or state.mode != "priority" or not veteran_reintegration_active(world):
        return []
    return eligible_ids(world, region)


def note_outcome(world, agent_id: int, kind: str, *, turn: int, detail: dict | None = None) -> None:
    """Report a veteran's dated outcome ``kind`` (one of ``OUTCOMES``, e.g.
    ``placed:apprentice``) at ``turn``; ``detail`` is a small JSON-safe dict
    (``site``, ``region``). Ids that are not open veteran records are
    ignored. Reports are staged and committed in this package's Phase 10
    hook of the same turn (a report for another turn is discarded), so call
    it before then: from Phase 2, the agent-tick hooks or an earlier
    package's Phase 10 hook."""
    if kind not in OUTCOMES:
        raise ValueError(f"unknown veteran outcome {kind!r}")
    detail = _check_detail(detail)
    state = _state(world)
    if state is None or not veteran_reintegration_active(world):
        return None
    aid = int(agent_id)
    if not any(r.agent_id == aid for r in state.records):
        return None
    state._noted.append((int(turn), aid, kind, detail))
    return None
