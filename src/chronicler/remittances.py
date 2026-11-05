"""RS4 migration, knowledge and household support (``--remittances``, default off).

Requires ``--agents hybrid``. A diaspora ledger built from the native
migrations actually applied each turn, and bounded remittances from settled
migrants to one Marriage or Kin partner left in the region they came from,
through the native pairwise operation ``wealth_transfer::remit`` under the
transfer purpose ``remittance`` (code 4).

The ledger. After a successful agent tick, this turn's native migration
events (type 2: every applied move, the L7 relocation moves included, as
the apply phase is the only native relocation of ordinary agents) update one
entry per person, keyed by stable id: ``{id, origin, departure_turn,
destination, arrival_turn}``. A first recorded move opens an entry; a later
move elsewhere is an onward move (new destination and arrival, the origin
kept); a move back to the origin closes the entry as a return. An entry
whose person is no longer alive after the tick closes as a death. Each
region records its losses (departures) and gains (arrivals, returns home)
separately, and its stock of open entries in both directions. Knowledge
flow: a mover who holds an RS1 workshop qualification at the destination
after the move (``apprenticeship.qualified_ids``) is a qualified departure
of the region left and a qualified arrival of the one reached. The native
pool keeps only the birth region and the events are not checkpointed, so
the ledger is the checkpointed record of who left where; it starts with the
first move observed while the switch is on.

Remittances. Every open entry is evaluated each turn, in ascending id:

* the sender is an alive adult, settled (displacement 0 and at least
  ``SETTLED_TURNS`` turns since the last arrival), not on a merchant trip,
  living at the ledger destination (so outside the origin), and has not
  already sent this turn;
* the recipient is exactly one partner of the sender's Marriage or Kin
  bonds with sentiment at least ``MIN_SENTIMENT``, alive, living in the
  origin and not on a trip: the spouse first, then the highest sentiment,
  then the lowest id. An eligible sender without one is an unmet sender
  (no bond, the partners all elsewhere, or on a trip);
* the remittance takes ``SHARE`` of the sender's wealth above
  ``RESERVE`` (whole milli-units, rounded down), at most ``CAP`` per turn;
  ``FEE`` of it is the courier's fee, paid to a disclosed courier sink
  (carriers, tolls and losses on the road: it leaves the economy).

``send`` (the default) applies the rows in one native call: both parties are
re-validated before any change (a dead, unknown or travelling party moves
nothing), the sender is never taken below zero, a recipient's ceiling excess
is refunded to the sender, and the (turn, purpose, batch) key applies once.
``record_only`` is the control: the same ledger, eligibility and amounts,
and nothing is sent.

Placement and exclusions. This runs in ``after_agent_tick``, after the L7
fares (``relocation_costs`` precedes it in ``LIVELIHOODS_SWITCHES``), on the
post-tick pool: this tick's deaths, swept bonds and applied moves are
already in it, and the credit reaches the recipient's household next tick.
After-tick hooks run only after a successful tick, and nothing is armed
before it, so a failed tick moves nothing. Remittances move existing wealth
between two people: they never touch food allocation, never create income
and never replace inheritance (``household.rs``, inside the tick). Exactly
once across exact checkpoints: ``last_settled_turn`` for the turn and
``last_sent_turn`` per sender. No randomness; every order is by stable id or
native event order. Parameters are declared, uncalibrated modeling choices.
"""
from __future__ import annotations

import math

from chronicler.ffi_constants import BOND_KIN, BOND_MARRIAGE
from chronicler.remittances_state import (
    COUNTERS, MAX_CLOSURES, MAX_ENTRIES, MAX_MOVES, MAX_RECEIPTS, MAX_UNMET, MODES, SENDER_REASONS,
    TRANSFER_STATUSES, UNLINKED_REASONS, Closure, DiasporaEntry, MoveRecord, PoolReset, RegionFlow,
    RemittanceReceipt, RemittancesState, UnmetSender,
)

SETTLED_TURNS = 5            # turns since the last arrival before a migrant may send
SHARE_PERMILLE = 100         # SHARE: 10% of wealth above the reserve
RESERVE_MILLI = 2000         # RESERVE: two wealth units the sender always keeps
CAP_MILLI = 1000             # CAP: at most one wealth unit per sender and turn
FEE_PERMILLE = 150           # FEE: 15% of the remittance to the courier sink
MIN_SENTIMENT = 20           # bond sentiment a recipient needs
ADULT_AGE = 20               # native ``agent::AGE_ADULT``
#: Native ``wealth_transfer::PURPOSES`` index of remittances.
PURPOSE_REMITTANCE = 4
REMIT_BATCH = 0
NO_MIGRATION_DRIVER = 255    # ``models.NO_MIGRATION_DRIVER``
_BONDS = {BOND_MARRIAGE: "marriage", BOND_KIN: "kin"}
_NATIVE = ("remit_wealth", "trip_agent_ids", "get_agent_relationships", "get_snapshot")
_FUNNEL = ("open_entries", *SENDER_REASONS, "eligible", "linked", *UNLINKED_REASONS, "no_surplus",
           "rows", *TRANSFER_STATUSES, "not_sent", "ledger_open", "ledger_qualified")
_TOTALS = ("requested_milli", "fee_requested_milli", "sent_milli", "fee_milli", "credited_milli",
           "refunded_milli", "debited_milli", "not_sent_milli")


def _state(world) -> RemittancesState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "remittances", None) if container is not None else None


def _bump(state: RemittancesState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def set_remittances_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--remittance-mode``, default ``send``) or disable; an
    omitted mode keeps the saved one."""
    mode = getattr(args, "remittance_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.remittances = state = RemittancesState(mode=mode or MODES[0])
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


def remittances_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def remittance_amount(wealth_milli: int) -> tuple[int, int]:
    """(amount for the recipient, courier fee) in milli-units for a sender's wealth."""
    surplus = max(0, int(wealth_milli) - RESERVE_MILLI)
    gross = min(surplus * SHARE_PERMILLE // 1000, CAP_MILLI)
    fee = gross * FEE_PERMILLE // 1000
    return gross - fee, fee


def choose_recipient(bonds, origin: int, alive: dict, trips: set):
    """The one recipient of a sender's bonds, or the reason there is none.

    ``bonds``: native (target id, sentiment, bond type, formed turn) rows of
    the sender; ``alive``: id -> (region, age, displacement, wealth milli).
    Returns ((recipient, bond kind, sentiment), None) or (None, reason)."""
    linked = [(int(t), int(s), int(b)) for t, s, b, _ in bonds or ()
              if int(b) in _BONDS and int(s) >= MIN_SENTIMENT]
    if not linked:
        return None, "no_bond"
    home = [c for c in linked if c[0] in alive and alive[c[0]][0] == origin]
    if not home:
        return None, "recipient_away"
    free = [c for c in home if c[0] not in trips]
    if not free:
        return None, "recipient_on_trip"
    target, sentiment, bond = min(free, key=lambda c: (c[2] != BOND_MARRIAGE, -c[1], c[0]))
    return (target, _BONDS[bond], sentiment), None


def _people(sim) -> dict[int, tuple[int, int, int, int]]:
    """Alive agents after the tick: id -> (region, age, displacement, wealth milli)."""
    snap = sim.get_snapshot()
    cols = [snap.column(name).to_pylist() for name in ("id", "region", "age", "displacement_turn", "wealth")]
    return {int(i): (int(r), int(a), int(d), max(0, math.floor(float(w) * 1000))) for i, r, a, d, w in zip(*cols)}


def _turn_migrations(world) -> list:
    """This turn's applied native migrations (event type 2), in native order."""
    raw = getattr(world, "agent_events_raw", None) or []
    out = []
    for e in reversed(raw):
        if e.turn != world.turn:
            break
        if e.event_type == "migration":
            out.append(e)
    out.reverse()
    return out


def _close(state, entry: DiasporaEntry, turn: int, reason: str, closures: list) -> None:
    closures.append(Closure(id=entry.id, origin=entry.origin, destination=entry.destination,
                            departure_turn=entry.departure_turn, closed_turn=turn, reason=reason))


def on_pool_reset(world) -> None:
    """A rebuilt native pool (``livelihoods.bind_native_pool``): the ledger's
    stable ids name other people now, so every open entry is closed, dated."""
    state = _state(world)
    if state is None or not state.entries:
        return
    n = len(state.entries)
    state.entries = []
    state.last_pool_reset = PoolReset(turn=int(world.turn), entries_closed=n,
                                      reason="native pool rebuilt: saved stable ids name other people")
    _bump(state, "pool_resets")
    _bump(state, "entries_closed_on_reset", n)


def after_agent_tick(world, agent_bridge) -> list:
    """Update the diaspora ledger from this tick's applied moves, then settle
    this turn's remittances once (``send``) or record them (``record_only``)."""
    state = _state(world)
    sim = agent_bridge._sim
    if not all(callable(getattr(sim, name, None)) for name in _NATIVE):
        raise RuntimeError("remittances require a fresh native build with remit_wealth")
    turn = int(world.turn)
    if state.last_settled_turn is not None and turn <= state.last_settled_turn:
        raise RuntimeError("remittances already settled for this turn")
    n_regions = len(world.regions)
    alive = _people(sim)
    trips = {int(i) for i in sim.trip_agent_ids()}
    entries = {e.id: e for e in state.entries}
    closures: list[Closure] = []
    flows: dict[int, RegionFlow] = {}

    def flow(r: int) -> RegionFlow:
        if r not in flows:
            flows[r] = RegionFlow(region=r)
        return flows[r]

    # A turn the ledger did not observe (the switch was off in between): it
    # may have missed moves and returns, so its entries are closed, dated.
    if state.last_settled_turn is not None and state.last_settled_turn != turn - 1 and entries:
        for aid in sorted(entries):
            _close(state, entries[aid], turn, "unobserved_gap", closures)
        _bump(state, "gap_closures", len(entries))
        entries = {}
    _bump(state, "turns")

    # 1. The ledger, from this tick's applied moves.
    from chronicler.apprenticeship import qualified_ids
    qualified: dict[int, set[int]] = {}
    moves: list[MoveRecord] = []
    for e in _turn_migrations(world):
        aid, frm, to = int(e.agent_id), int(e.region), int(e.target_region)
        if not (0 <= frm < n_regions and 0 <= to < n_regions) or frm == to:
            raise RuntimeError("native migration event names an invalid route")
        if to not in qualified:
            qualified[to] = {int(i) for i in qualified_ids(world, to)}
        q = aid in qualified[to]
        _bump(state, "moves_seen")
        flow(frm).departures += 1
        flow(to).arrivals += 1
        if q:
            flow(frm).qualified_departures += 1
            flow(to).qualified_arrivals += 1
            _bump(state, "qualified_departures")
            _bump(state, "qualified_arrivals")
        entry = entries.get(aid)
        if entry is None:
            if len(entries) >= MAX_ENTRIES:
                kind = "unrecorded"
                _bump(state, "entries_refused")
            else:
                entries[aid] = DiasporaEntry(id=aid, origin=frm, departure_turn=turn, destination=to,
                                             arrival_turn=turn, qualified=q)
                kind = "departure"
                _bump(state, "departures")
        elif to == entry.origin:
            kind = "return"
            flow(to).returns_home += 1
            _close(state, entries.pop(aid), turn, "return", closures)
            _bump(state, "returns")
            if q:
                _bump(state, "qualified_returns")
        else:
            entry.destination, entry.arrival_turn, entry.qualified = to, turn, q
            entry.moves += 1
            kind = "onward"
            _bump(state, "onward_moves")
        driver = int(e.migration_driver)
        moves.append(MoveRecord(id=aid, from_region=frm, to_region=to, kind=kind, qualified=q,
                                driver=None if driver == NO_MIGRATION_DRIVER else driver))
    # Deaths in this tick (or since the last observed turn) close their entries.
    for aid in sorted(entries):
        if aid not in alive:
            _close(state, entries.pop(aid), turn, "death", closures)
            _bump(state, "deaths")

    # 2. Senders, recipients and amounts, in ascending id.
    funnel = dict.fromkeys(_FUNNEL, 0)
    rows: list[tuple[int, int, int, int]] = []
    pending: list[RemittanceReceipt] = []
    unmet: list[UnmetSender] = []
    for aid in sorted(entries):
        entry = entries[aid]
        region, age, displacement, wealth = alive[aid]
        funnel["open_entries"] += 1
        _bump(state, "sender_turns_evaluated")
        if age < ADULT_AGE:
            reason = "child"
        elif displacement > 0 or turn - entry.arrival_turn < SETTLED_TURNS:
            reason = "unsettled"
        elif aid in trips:
            reason = "on_trip"
        elif region != entry.destination or region == entry.origin:
            reason = "elsewhere"
        elif entry.last_sent_turn is not None and entry.last_sent_turn >= turn:
            reason = "already_sent"
        else:
            reason = None
        if reason is not None:
            funnel[reason] += 1
            continue
        funnel["eligible"] += 1
        _bump(state, "eligible_sender_turns")
        surplus = max(0, wealth - RESERVE_MILLI)
        chosen, why = choose_recipient(sim.get_agent_relationships(aid), entry.origin, alive, trips)
        if chosen is None:
            funnel[why] += 1
            _bump(state, "unlinked_sender_turns")
            unmet.append(UnmetSender(id=aid, origin=entry.origin, destination=region, reason=why,
                                     surplus_milli=surplus))
            continue
        funnel["linked"] += 1
        _bump(state, "linked_sender_turns")
        amount, fee = remittance_amount(wealth)
        if amount <= 0:
            funnel["no_surplus"] += 1
            _bump(state, "no_surplus_sender_turns")
            continue
        recipient, bond, sentiment = chosen
        rows.append((aid, recipient, amount, fee))
        pending.append(RemittanceReceipt(turn=turn, sender=aid, recipient=recipient, bond=bond,
                                         sentiment=sentiment, origin=entry.origin, destination=region,
                                         wealth_milli=wealth, amount=amount, fee_requested=fee,
                                         status="not_sent"))

    # 3. Settlement: one native call for the turn (send), nothing (record_only).
    if rows and state.mode == "send":
        got = sim.remit_wealth(turn, REMIT_BATCH, rows)
        if len(got) != len(rows):
            raise RuntimeError("native remittance receipt does not match its rows")
        for receipt, row, (sender, recipient, sent, fee, credited, refunded, status) in zip(pending, rows, got):
            if (sender, recipient) != row[:2]:
                raise RuntimeError("native remittance receipt is out of order")
            if (min(sent, fee, credited, refunded) < 0 or sent != fee + credited + refunded
                    or sent > row[2] + row[3] or fee > row[3]):
                raise RuntimeError("native remittance receipt does not balance")
            receipt.sent, receipt.fee, receipt.credited, receipt.refunded = sent, fee, credited, refunded
            receipt.status = TRANSFER_STATUSES[status]
    totals = dict.fromkeys(_TOTALS, 0)
    for receipt in pending:
        entry = entries[receipt.sender]
        entry.last_sent_turn = turn
        funnel["rows"] += 1
        funnel[receipt.status] += 1
        _bump(state, "rows")
        _bump(state, "rows_" + receipt.status)
        totals["requested_milli"] += receipt.amount
        totals["fee_requested_milli"] += receipt.fee_requested
        if receipt.status == "not_sent":
            totals["not_sent_milli"] += receipt.amount + receipt.fee_requested
            continue
        totals["sent_milli"] += receipt.sent
        totals["fee_milli"] += receipt.fee
        totals["credited_milli"] += receipt.credited
        totals["refunded_milli"] += receipt.refunded
        totals["debited_milli"] += receipt.fee + receipt.credited
        if receipt.sent > 0:
            host, home = flow(receipt.destination), flow(receipt.origin)
            host.senders += 1
            host.outflow_milli += receipt.fee + receipt.credited
            host.fee_milli += receipt.fee
            host.refunded_milli += receipt.refunded
            home.recipients += 1
            home.inflow_milli += receipt.credited
        if receipt.credited > 0:
            entry.sent_turns += 1
            entry.credited_milli += receipt.credited
    if totals["debited_milli"] != totals["credited_milli"] + totals["fee_milli"] or \
            totals["sent_milli"] != totals["debited_milli"] + totals["refunded_milli"]:
        raise RuntimeError("remittances do not balance this turn")
    for key in ("requested_milli", "fee_requested_milli", "sent_milli", "fee_milli", "credited_milli",
                "refunded_milli", "not_sent_milli"):
        _bump(state, key, totals[key])

    # 4. The completed-turn frame: the ledger's stock after the turn, per region.
    for entry in entries.values():
        flow(entry.origin).diaspora_out += 1
        flow(entry.destination).diaspora_in += 1
        if entry.qualified:
            flow(entry.origin).qualified_out += 1
            flow(entry.destination).qualified_in += 1
            funnel["ledger_qualified"] += 1
    funnel["ledger_open"] = len(entries)
    state.entries = [entries[aid] for aid in sorted(entries)]
    state.last_settled_turn = turn
    state.frame_turn = turn
    state.moves, state.moves_dropped = moves[:MAX_MOVES], max(0, len(moves) - MAX_MOVES)
    state.closures, state.closures_dropped = closures[:MAX_CLOSURES], max(0, len(closures) - MAX_CLOSURES)
    state.receipts, state.receipts_dropped = pending[:MAX_RECEIPTS], max(0, len(pending) - MAX_RECEIPTS)
    state.unmet, state.unmet_dropped = unmet[:MAX_UNMET], max(0, len(unmet) - MAX_UNMET)
    state.regions = [flows[r] for r in sorted(flows)]
    state.funnel = funnel
    state.totals = totals
    return []


def snapshot_summary(world) -> dict:
    """The completed turn's copied frame (never final state); None: not observed."""
    state = _state(world)
    source = world.turn - 1
    observed = state.frame_turn == source

    def dump(items):
        return [x.model_dump() for x in items] if observed else None

    return {
        "schema_version": 1, "stage": "RS4", "mode": state.mode, "source_turn": source,
        "funnel": dict(state.funnel) if observed else None,
        "totals": dict(state.totals) if observed else None,
        "regions": dump(state.regions),
        "moves": dump(state.moves), "moves_dropped": state.moves_dropped if observed else None,
        "closures": dump(state.closures), "closures_dropped": state.closures_dropped if observed else None,
        "receipts": dump(state.receipts), "receipts_dropped": state.receipts_dropped if observed else None,
        "unmet": dump(state.unmet), "unmet_dropped": state.unmet_dropped if observed else None,
        "last_pool_reset": state.last_pool_reset.model_dump() if state.last_pool_reset is not None else None,
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "parameters": {"settled_turns": SETTLED_TURNS, "share_permille": SHARE_PERMILLE,
                       "reserve_milli": RESERVE_MILLI, "cap_milli": CAP_MILLI, "fee_permille": FEE_PERMILLE,
                       "min_sentiment": MIN_SENTIMENT, "adult_age": ADULT_AGE, "max_entries": MAX_ENTRIES},
    }
