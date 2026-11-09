"""PL3 maintenance obligation (``--maintenance-obligation``, default off).

Requires ``--local-budgets`` (L9, hence ``--agents hybrid`` and
``--grain-reserves``) and ``--repair-projects`` (RS2). Modes
(``--maintenance-obligation-mode``): ``reserve`` (default) and the
crowding-out control ``reserve_only``. Phase plan:
``docs/superpowers/roadmaps/productive-recovery-phase.md`` (PL3); integration
page ``docs/integration/maintenance-obligation.md``.

Why. Under L9 a repairs envelope is awarded only when a constituency's
measured burden falls: an empty granary, or a workshop still above the 0.5
operating gate, relieves nothing, so most repairs proposals are refused
``no_support`` and RS2 stalls ``no_envelope`` (diagnosis D3). Maintenance is
valued only after failure.

What. In Phase 10 of turn T, when L9 decides the budget for T+1, each civ
reserves a bounded maintenance obligation through L9's existing obligation
path (``local_budgets._decide``; the reservation is recorded in
``Decision.reserved["maintenance"]`` and reduces the disposable treasury the
budget is drawn from, like the teaching and relocation reserves). The amount
is RS2's planned per-turn charges for the civ's open projects
(``repair_projects.planned_cost``: the cost of RS2's own full ``repairs``
proposal at the same dated observations), capped at ``MAX_BUDGET_SHARE`` of
the budget the civ would have without it:

    budget_before = floor(envelope_share x max(0, projected - floor - other obligations - committed))
    reserved = min(planned, floor(MAX_BUDGET_SHARE x budget_before))

``reserve``: RS2's ``repairs`` proposal asks only for the part beyond the
reservation (cost, expected work and relief scaled by the unreserved share),
and during T+1 RS2 may spend up to its envelope plus the reservation
(``repairs_limit``). The charge and the delivered work are split between the
reservation and the envelope pro rata to their amounts (:func:`split_charge`),
so a shortfall falls on both and the envelope's delivered ratio stays the work
delivered over the work its limit funded, as under L9 alone; L9 settles the
envelope's part as before (``spent <= amount``, kept or deferred from RS2's
receipts, the grievance response of a promise). The reservation is not a
promise: it has no sponsor and moves no grievance.

``reserve_only``: the same reservation (the same smaller budget for every
bargained service), while RS2 keeps its full proposal and is limited to its
bargained envelope; the whole reservation is returned unspent. It shows the
crowding-out cost without the repair benefit.

Closure, per civ and turn (``ReservationUse``, checked when written):
``reserved == used + returned`` and ``used + envelope_spent == charged``,
with ``charged`` RS2's whole-unit charge to the civ and ``used == 0`` in
``reserve_only``. A reservation is coins L9 did not budget; returning it
leaves them in the treasury (nothing moves). All parameters are declared
modeling choices, not calibrated.
"""
from __future__ import annotations

import math

from chronicler.local_budgets import Provider
from chronicler.maintenance_obligation_state import (
    COUNTERS, MODES, MaintenanceObligationState, ReservationDecision, ReservationUse,
)
from chronicler.switch_state import sub_state_getter

#: Largest share of the budget a civ would otherwise have that the
#: maintenance obligation may reserve (declared, uncalibrated).
MAX_BUDGET_SHARE = 0.5
#: L9 obligation group (``Decision.reserved`` key).
GROUP = "maintenance"
EPS = 1e-9


class _Turn:
    """One turn's execution rows, Phase 2 to Phase 10 (never checkpointed)."""

    def __init__(self, turn: int):
        self.turn = turn
        self.uses: dict[int, ReservationUse] = {}
        self.finished = False


_state = sub_state_getter("maintenance_obligation")


def _bump(state, key: str, amount=1) -> None:
    if key not in COUNTERS:
        raise KeyError(f"undeclared maintenance-obligation counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + amount


def set_maintenance_obligation_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--maintenance-obligation-mode``, default ``reserve``) or
    disable; an omitted mode keeps the saved one."""
    mode = getattr(args, "maintenance_obligation_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.maintenance_obligation = state = MaintenanceObligationState(mode=mode or MODES[0])
    else:
        t = state._turn
        if t is not None and t.turn == getattr(world, "turn", None) and not t.finished:
            raise RuntimeError("cannot change the maintenance obligation while a turn is pending")
        if mode is not None:
            state.mode = mode
    state.enabled = bool(value)


def maintenance_obligation_active(world) -> bool:
    """Enabled while L9 and RS2 are both active."""
    state = _state(world)
    if state is None or not state.enabled:
        return False
    container = world.livelihoods
    if getattr(container, "local_budgets", None) is None or getattr(container, "repair_projects", None) is None:
        return False
    from chronicler.local_budgets import local_budgets_active
    from chronicler.repair_projects import repair_projects_active
    return local_budgets_active(world) and repair_projects_active(world)


# ---------------------------------------------------------------------------
# L9 provider: the capped obligation
# ---------------------------------------------------------------------------

class _Obligation(Provider):
    """Registered in ``local_budgets.PROVIDERS``. It proposes nothing; its
    ``capped_obligation`` is read by ``local_budgets._decide`` after every
    other provider's obligation, with the budget the civ would have without
    it."""

    services: tuple[str, ...] = ()
    group = GROUP

    def active(self, world) -> bool:
        return maintenance_obligation_active(world)

    def capped_obligation(self, world, civ: int, obs, budget_before: int) -> int:
        state = _state(world)
        if state is None or not maintenance_obligation_active(world):
            return 0
        from chronicler.repair_projects import planned_cost
        planned = int(planned_cost(world, civ, obs))
        cap = int(math.floor(MAX_BUDGET_SHARE * max(0, int(budget_before)) + EPS))
        amount = max(0, min(planned, cap))
        staged = state._staged
        if staged is None or staged[0] != obs.turn:
            staged = state._staged = (obs.turn, {})
        if civ in staged[1]:
            raise RuntimeError("maintenance obligation decided twice for one civ and turn")
        staged[1][civ] = ReservationDecision(turn=obs.turn, civ=civ, planned=planned,
                                             budget_before=int(budget_before), cap=cap, reserved=amount)
        return amount


BUDGET_PROVIDER = _Obligation()


def _decided(world, civ: int, turn: int) -> ReservationDecision | None:
    state = _state(world)
    staged = state._staged if state is not None else None
    if staged is None or staged[0] != turn:
        return None
    return staged[1].get(civ)


def after_reservation(world, civ: int, obs, rows: list[dict]) -> list[dict]:
    """RS2's ``repairs`` proposal for the decision being made: in ``reserve``
    mode only the part beyond the civ's reservation (scaled, divisible as
    before); unchanged in ``reserve_only``."""
    state = _state(world)
    if state is None or state.mode != "reserve" or not rows:
        return rows
    d = _decided(world, civ, obs.turn)
    reserved = d.reserved if d is not None else 0
    if reserved <= 0:
        return rows
    out = []
    for row in rows:
        cost = int(row["cost"])
        left = cost - reserved
        if left < 1:
            continue
        scale = left / cost
        out.append({**row, "cost": left, "expected": row["expected"] * scale,
                    "relief": {k: v * scale for k, v in row["relief"].items() if v * scale > EPS},
                    "detail": {**row.get("detail", {}), "reserved": reserved}})
    return out


# ---------------------------------------------------------------------------
# Execution (turn T+1)
# ---------------------------------------------------------------------------

def _reserved(world, civ: int) -> int:
    from chronicler.local_budgets import reserved
    amount = reserved(world, civ, GROUP)
    return int(amount or 0)


def repairs_limit(world, civ: int, envelope: int) -> int:
    """RS2's spending limit this turn: its envelope plus, in ``reserve`` mode,
    the civ's reservation."""
    state = _state(world)
    if state is None or not maintenance_obligation_active(world) or state.mode != "reserve":
        return envelope
    return int(envelope) + _reserved(world, civ)


def finish_phase2(world, economy_result, agent_bridge, acc):
    """After RS2 charged this turn: split each civ's charge into the part the
    reservation paid and the envelope's (staged for L9's settlement)."""
    state = _state(world)
    t = state._turn
    if t is not None and t.turn == world.turn:
        raise RuntimeError("maintenance obligation already settled for this turn")
    t = state._turn = _Turn(world.turn)
    rs2 = world.livelihoods.repair_projects._turn
    ledger = {row.civ: row for row in (rs2.ledger if rs2 is not None and rs2.turn == world.turn and rs2.finished
                                       else [])}
    from chronicler.local_budgets import envelope
    for ci, civ in enumerate(world.civilizations):
        reserved = _reserved(world, ci)
        row = ledger.get(ci)
        if not reserved and row is None:
            continue
        charged = int(row.charged) if row is not None else 0
        amount = envelope(world, ci, "repairs")
        used, share = split_charge(charged, reserved if state.mode == "reserve" else 0, amount or 0)
        use = ReservationUse(turn=world.turn, civ=ci, reserved=reserved, envelope=amount, charged=charged,
                             used=used, returned=reserved - used, envelope_spent=charged - used,
                             envelope_share=share)
        check_use(use)
        t.uses[ci] = use
    t.finished = True
    return []


def split_charge(charged: int, reserved: int, envelope: int) -> tuple[int, float]:
    """The turn's RS2 charge split between the reservation and the bargained
    envelope pro rata to their amounts: the reservation pays
    ``floor(charged x reserved / (reserved + envelope))`` coins and the
    envelope the rest (never above its amount, since ``charged <= reserved +
    envelope``); the envelope's share of the delivered work is
    ``envelope / (reserved + envelope)``. A shortfall therefore falls on both
    in proportion, so the envelope's delivered ratio is the work delivered
    over the work its limit funded, as under L9 alone (review C 2026-11-06:
    paying from the reservation first left every shortfall on the promise,
    lowering its ratio and raising broken-promise grievance against L9
    alone). Returns ``(reservation coins, envelope work share)``."""
    whole = reserved + envelope
    if reserved <= 0 or whole <= 0:
        return 0, 1.0
    if charged > whole:
        raise RuntimeError("repair charge beyond the reservation and envelope")
    return (charged * reserved) // whole, envelope / whole


def check_use(row: ReservationUse) -> None:
    if row.reserved != row.used + row.returned or row.used + row.envelope_spent != row.charged \
            or min(row.reserved, row.used, row.returned, row.envelope_spent) < 0:
        raise RuntimeError(f"maintenance reservation of civ {row.civ} does not close")
    if row.envelope is not None and row.envelope_spent > row.envelope:
        raise RuntimeError(f"repairs of civ {row.civ} spent beyond their envelope and reservation")


def reservation_split(world, civ: int) -> tuple[int, float]:
    """This turn's split of RS2's charge to ``civ`` (:func:`split_charge`):
    the coins its reservation paid and the envelope's share of the delivered
    work; ``(0, 1.0)`` in ``reserve_only``, without a reservation or before
    Phase 2 settled."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != world.turn or not t.finished:
        return 0, 1.0
    use = t.uses.get(civ)
    return (int(use.used), float(use.envelope_share)) if use is not None else (0, 1.0)


def reservation_used(world, civ: int) -> int:
    """Coins of this turn's RS2 charge to ``civ`` that its reservation paid."""
    return reservation_split(world, civ)[0]


def rollback_phase2(world) -> None:
    state = _state(world)
    if state is not None and state._turn is not None and state._turn.turn == getattr(world, "turn", None):
        state._turn = None


def rollback_agent_tick(world, agent_bridge) -> None:
    rollback_phase2(world)


def phase10(world, acc, economy_result, agent_bridge):
    """After L9 settled this turn and decided the next: commit the turn's
    execution rows and the decision's reservations (dated)."""
    state = _state(world)
    t = state._turn
    if t is not None and t.turn == world.turn and t.finished:
        state.uses = [t.uses[c] for c in sorted(t.uses)]
        state.last_settled_turn = world.turn
        _bump(state, "settled_turns")
        for use in state.uses:
            _bump(state, "execution_civ_turns")
            _bump(state, "used_coins", use.used)
            _bump(state, "returned_coins", use.returned)
            _bump(state, "envelope_spent_coins", use.envelope_spent)
            _bump(state, "charged_coins", use.charged)
    else:
        if t is not None:
            _bump(state, "turns_discarded")
        state.uses = None
    state.frame_turn = world.turn
    state._turn = None
    staged = state._staged
    if staged is not None and staged[0] == world.turn:
        state.decisions = [staged[1][c] for c in sorted(staged[1])]
        state.decision_turn = world.turn
        for d in state.decisions:
            _bump(state, "decision_civ_turns")
            _bump(state, "planned_coins", d.planned)
            _bump(state, "capped_coins", d.cap)
            _bump(state, "reserved_coins", d.reserved)
            if d.planned > d.cap:
                _bump(state, "cap_binding")
    state._staged = None
    return []


def snapshot_summary(world) -> dict:
    """The completed-turn observation: the decision made in the source
    turn (``decisions``, for the turn after it) and the reservations used in
    it (``uses``); None when that turn decided or settled nothing (unknown,
    not zero)."""
    state = _state(world)
    source = world.turn - 1
    return {
        "schema_version": 1, "stage": "PL3", "mode": state.mode, "source_turn": source,
        "units": {"money": "treasury_units"},
        "decisions": [d.model_dump() for d in state.decisions] if state.decision_turn == source else None,
        "uses": [u.model_dump() for u in state.uses] if state.frame_turn == source and state.uses is not None
        else None,
        "counters": dict(state.counters),
        "parameters": {"max_budget_share": MAX_BUDGET_SHARE, "group": GROUP},
    }
