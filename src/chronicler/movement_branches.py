"""D1c: locally funded movement branches abroad, opt-in and default off.

Phase 10 T observes members already abroad, excluding merchant trips and
people whose public army attachment is away from their native residence.
Up to 32 adult members per branch
(512 total), ordered by stable id, contribute 10 milli each from their actual
wealth to the host treasury for a local meeting/petition service. Three paid
members fund the branch for T+1. There is no branch balance, invented income,
need credit, or additional grievance/influence stack. Record-only pays nothing;
cost-only pays identically and supports no native membership behavior.

The next native tick consumes only a T-1 frame, once. A funded branch removes
the extra abroad lapse and permits ordinary recruitment in its host; existing
local exposure, adult/need conditions, news transport and mortality still own
their decisions. This does not deliver home-country news: members know their
own movement and organize locally. Published hostility and C1 closures block
the cross-border organizational permission, at funding and at delivery. No
same-turn/future residence-ledger data or provenance is consumed.
"""
from __future__ import annotations

import copy
import math

from pydantic import ValidationError

from chronicler import money
from chronicler.agent_movements_state import ENDED, GUILD, agent_movements_on
from chronicler.movement_branches_state import (
    BRANCH_BATCH, COUNTERS, DUES_MILLI, MAX_BRANCHES, MAX_PAYERS, MAX_PAYERS_TOTAL,
    MIN_PAYERS, MODES, Branch, BranchFrame, BranchRow, MovementBranchesState,
)

ADULT_AGE = 16                     # native movements::ADULT_AGE
PURPOSE = "branch_dues"


def _state(world):
    return getattr(getattr(world, "livelihoods", None), "movement_branches", None)


def movement_branches_active(world):
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def check_request(world, value, args, *, agent_mode, movements_on):
    state = _state(world)
    mode = getattr(args, "movement_branches_mode", None)
    if mode is not None and mode not in MODES:
        raise ValueError("unknown movement-branches mode")
    if mode is not None and (value is False or (value is None and not movement_branches_active(world))):
        raise ValueError("--movement-branches-mode requires --movement-branches")
    if value is False:
        return
    if state is not None and mode is not None and state.mode != mode:
        raise ValueError("a movement-branches mode change on resume is refused")
    if value is True or (value is None and movement_branches_active(world)):
        if agent_mode != "hybrid" or not movements_on:
            raise ValueError("--movement-branches requires --agents hybrid and --agent-movements; "
                             "pass --no-movement-branches to end a saved switch")


def set_movement_branches_enabled(world, value, *, args=None, agent_mode=None):
    mode = getattr(args, "movement_branches_mode", None)
    state = _state(world)
    if state is None:
        world.livelihoods.movement_branches = MovementBranchesState(enabled=bool(value), mode=mode or MODES[0])
    else:
        if mode is not None and mode != state.mode:
            raise ValueError("a movement-branches mode change on resume is refused")
        state.enabled = bool(value)
    if not value:
        state = _state(world)
        state.frame = None
        state.frame_turn = None


def _bump(state, key, amount=1):
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + amount


def on_pool_reset(world):
    state = _state(world)
    if state is None or state.frame is None:
        return
    # Old stable ids do not name people in the rebuilt native pool.
    state.frame = None
    state.frame_turn = None
    _bump(state, "pool_resets")


def _boundary(world, target, host):
    civs = world.civilizations
    if not (0 <= target < len(civs) and 0 <= host < len(civs)):
        return "ended"
    a, b = civs[target].name, civs[host].name
    if not civs[target].regions or not civs[host].regions:
        return "ended"
    if any({x, y} == {a, b} for x, y in world.active_wars):
        return "hostile"
    from chronicler.quarantine_rules import closed_pairs
    if tuple(sorted((a, b))) in closed_pairs(world):
        return "quarantined"
    return None


def phase10(world, acc=None, economy_result=None, agent_bridge=None):
    state = _state(world)
    if state is None or not state.enabled:
        return []
    turn = int(world.turn)
    if state.frame_turn is not None and state.frame_turn >= turn:
        raise RuntimeError("movement branches already settled this turn")
    sim = getattr(agent_bridge, "_sim", None)
    if sim is None or not agent_movements_on(world):
        state.frame = None
        state.frame_turn = None
        return []
    snap = sim.get_snapshot()
    ids, regions, ages, memberships, wealth = (
        snap.column(k).to_pylist() for k in ("id", "region", "age", "movement_id", "wealth"))
    trips = set(map(int, sim.trip_agent_ids()))
    region_ids = {region.name: i for i, region in enumerate(world.regions)}
    residence = {int(aid): int(region) for aid, region in zip(ids, regions, strict=True)}
    # Native region is residence, while a field army carries its own location.
    # A person knows their present attachment; no X1 frame is read and this
    # filter neither moves people nor changes native movement membership.
    away = {int(aid) for army in getattr(getattr(world, "war_state", None), "armies", None) or []
            for aid, _ in army.roster if region_ids.get(army.region) != residence.get(int(aid))}
    civ_ids = {c.name: i for i, c in enumerate(world.civilizations)}
    controllers = [civ_ids.get(r.controller) for r in world.regions]
    movements = world.agent_movements.movements
    groups = {}
    for aid, region, age, mid, held in zip(ids, regions, ages, memberships, wealth, strict=True):
        aid, region, mid = int(aid), int(region), int(mid)
        if age < ADULT_AGE or aid in trips or aid in away or not 0 <= region < len(controllers) or not 1 <= mid <= len(movements):
            continue
        movement, host = movements[mid - 1], controllers[region]
        # Guild membership belongs to one city; D1b supplies its cross-border organization.
        if host is None or host == movement.target or movement.stage == ENDED or movement.creed == GUILD:
            continue
        groups.setdefault((mid, host), []).append((aid, region, float(held)))
    known = {(b.movement, b.host): b for b in state.branches}
    refused = 0
    for mid, host in sorted(groups):
        if (mid, host) not in known:
            if len(state.branches) >= MAX_BRANCHES:
                refused += 1
                continue
            branch = Branch(branch=state.next_branch, movement=mid, host=host, first_turn=turn)
            state.next_branch += 1
            state.branches.append(branch)
            known[mid, host] = branch
            _bump(state, "branches")
    frame, remaining = BranchFrame(turn=turn, new_identities_refused=refused), MAX_PAYERS_TOTAL
    for branch in state.branches:
        people = sorted(groups.get((branch.movement, branch.host), ()))
        movement = movements[branch.movement - 1] if 1 <= branch.movement <= len(movements) else None
        target = movement.target if movement is not None else -1
        row = BranchRow(branch=branch.branch, movement=branch.movement, host=branch.host, target=target,
                        host_name=world.civilizations[branch.host].name,
                        target_name=world.civilizations[target].name if 0 <= target < len(world.civilizations) else "",
                        regions=sorted({r for _, r, _ in people}), members=len(people), status="empty")
        boundary = _boundary(world, target, branch.host)
        if movement is None or movement.stage == ENDED:
            row.status = "ended"
        elif boundary is not None:
            row.status = boundary
            _bump(state, "boundary_refused", int(bool(people)))
        elif state.mode == "record_only":
            row.status = "record_only"
        elif len(people) < MIN_PAYERS:
            row.status = "too_few" if people else "empty"
        else:
            payers = [aid for aid, _, held in people if math.isfinite(held) and math.floor(max(0, held) * 1000) >= DUES_MILLI]
            payers = payers[:min(MAX_PAYERS, remaining)]
            if len(payers) < MIN_PAYERS:
                row.status = "capacity" if remaining < MIN_PAYERS else "poor"
            else:
                region_of = {aid: r for aid, r, _ in people}
                bill = money.Bill(phase="phase10", purpose="branch_dues", batch=BRANCH_BATCH + branch.branch,
                                  payee=money.Account("civ_treasury", branch.host),
                                  lines=tuple((money.Account("agent_wealth", aid), DUES_MILLI) for aid in payers),
                                  regions=tuple(region_of[aid] for aid in payers))
                receipt = money.pay(world, bill, turn=turn, book=state.book, sim=sim, acc=acc)
                if not receipt.ok:
                    row.status = "payment_refused"
                else:
                    if receipt.applied != len(payers) * DUES_MILLI or receipt.residual:
                        raise money.MoneyError("movement branch contributions do not close")
                    row.payers, row.dues_milli = payers, receipt.applied
                    row.status = "funded" if state.mode == "funded" else "cost_only"
                    row.active_from = turn + 1 if state.mode == "funded" else None
                    remaining -= len(payers)
                    _bump(state, "paid_members", len(payers))
                    _bump(state, "dues_milli", receipt.applied)
                    _bump(state, "funded_branch_turns", int(state.mode == "funded"))
        frame.rows.append(row)
        _bump(state, "member_turns", row.members)
    money.check_book(state.book)
    state.frame, state.frame_turn = frame, turn
    _bump(state, "identity_capacity_refused", refused)
    _bump(state, "turns")
    discard = getattr(type(agent_bridge), "discard_post_tick_snapshot", None)
    if discard is not None:
        discard(agent_bridge)
    return []


def read_frame(world, *, consumer_turn):
    if not isinstance(consumer_turn, int) or isinstance(consumer_turn, bool):
        raise TypeError("consumer_turn must be an int")
    if consumer_turn != world.turn:
        raise RuntimeError("movement branches are read at the consumer's own turn")
    state = _state(world)
    if not movement_branches_active(world) or state.frame_turn is None:
        return None
    if state.frame_turn >= consumer_turn:
        raise RuntimeError("same-turn or future movement branch read refused")
    if state.frame_turn != consumer_turn - 1 or state.frame is None:
        return None
    return copy.deepcopy(state.frame)


def before_agent_tick(world, agent_bridge, economy_result):
    state = _state(world)
    if state.mode != "funded":
        return
    frame = read_frame(world, consumer_turn=int(world.turn))
    if frame is None:
        return
    sim = agent_bridge._sim
    if not hasattr(sim, "set_movement_branches"):
        raise RuntimeError("rebuild chronicler-agents to use --movement-branches")
    pairs = []
    for row in frame.rows:
        if row.status == "funded" and row.active_from == world.turn and _boundary(world, row.target, row.host) is None:
            pairs.append((row.movement, row.host))
    sim.set_movement_branches(frame.turn, int(world.turn), [m for m, _ in pairs], [h for _, h in pairs])


def rollback_agent_tick(world, agent_bridge):
    sim = getattr(agent_bridge, "_sim", None)
    cancel = getattr(sim, "cancel_movement_branches", None)
    if cancel is not None:
        cancel(int(world.turn))


def snapshot_summary(world):
    state = _state(world)
    source = int(world.turn) - 1
    return {"schema_version": 1, "stage": "D1c", "source_turn": source, "mode": state.mode,
            "frame": state.frame.model_dump() if state.frame is not None and state.frame_turn == source else None,
            "counters": dict(state.counters),
            "parameters": {"dues_milli": DUES_MILLI, "min_payers": MIN_PAYERS, "max_payers": MAX_PAYERS,
                           "max_payers_total": MAX_PAYERS_TOTAL, "max_branches": MAX_BRANCHES}}


def record_status(snapshot):
    livelihoods = snapshot.get("livelihoods") if isinstance(snapshot, dict) else None
    if livelihoods is not None and not isinstance(livelihoods, dict):
        return "malformed", None
    record = livelihoods.get("movement_branches") if livelihoods else None
    if record is None:
        return "off", None
    bad = ("malformed", None)
    if not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("stage") != "D1c" \
            or type(record.get("source_turn")) is not int or type(snapshot.get("turn")) is not int \
            or record.get("mode") not in MODES or record.get("source_turn") != snapshot.get("turn", -1) - 1:
        return bad
    if record.get("frame") is None:
        return "unobserved", None
    try:
        frame = BranchFrame.model_validate(record["frame"], strict=True)
    except ValidationError:
        return bad
    if frame.turn != record["source_turn"] or len(frame.rows) > MAX_BRANCHES or frame.new_identities_refused < 0:
        return bad
    seen, pairs, payers = set(), set(), set()
    for row in frame.rows:
        pair = (row.movement, row.host)
        if row.branch < 1 or row.movement < 1 or row.host < 0 or row.branch in seen or pair in pairs \
                or row.members < 0 or len(row.payers) > min(MAX_PAYERS, row.members) \
                or len(set(row.payers)) != len(row.payers) or any(a < 1 or a in payers for a in row.payers) \
                or row.dues_milli != len(row.payers) * DUES_MILLI:
            return bad
        if row.status in ("funded", "cost_only"):
            if len(row.payers) < MIN_PAYERS or (row.active_from != frame.turn + 1 if row.status == "funded" else row.active_from is not None):
                return bad
        elif row.payers or row.active_from is not None:
            return bad
        if (row.status == "funded" and record["mode"] != "funded") or (row.status == "cost_only" and record["mode"] != "cost_only"):
            return bad
        seen.add(row.branch)
        pairs.add(pair)
        payers.update(row.payers)
    if len(payers) > MAX_PAYERS_TOTAL:
        return bad
    return ("recorded" if frame.rows else "recorded_zero"), frame.model_dump()
