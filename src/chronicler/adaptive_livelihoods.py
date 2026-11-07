"""A6: personal dated failures inform the existing native migration decision.

No Python movement path, provenance read, or same-turn residence read is used.
Rules 1 is the first audit's migration penalty; rules 2 additionally exposes
experienced work-offer refusals through ``accepts_offer``. Unknown work utility
is never invented. Regional and crew totals are never assigned to a person.
"""
from __future__ import annotations

from collections import defaultdict

from chronicler.adaptive_livelihoods_state import AdaptiveLivelihoodsState
from chronicler.utils import stable_hash_int

MAX_MEMORY = 16384
MAX_WORK = 16384
REFUSED_WINDOW, LEFT_WINDOW, QUICK_LEAVE_TURNS = 10, 20, 10
P_REFUSED, P_LEFT, P_CAP = 0.20, 0.15, 0.30
WORK_WINDOW = 10


def _state(world):
    return getattr(getattr(world, "livelihoods", None), "adaptive_livelihoods", None)


def adaptive_livelihoods_active(world):
    state = _state(world)
    return state is not None and state.enabled and world.agent_mode == "hybrid"


def set_adaptive_livelihoods_enabled(world, value, *, args=None, agent_mode=None):
    state = _state(world)
    mode = getattr(args, "adaptive_livelihoods_mode", None) if args else None
    rules = getattr(args, "adaptive_livelihoods_rules", None) if args else None
    if state is None:
        world.livelihoods.adaptive_livelihoods = AdaptiveLivelihoodsState(
            enabled=bool(value), mode=mode or "adapt", rules=rules or "2")
    else:
        if (mode is not None and mode != state.mode) or (rules is not None and rules != state.rules):
            raise ValueError("saved adaptive livelihoods mode/rules cannot change")
        state.enabled = bool(value)
        if not value:
            state.memory.clear()
            state.work.clear()
            state.frame = None


def _bump(state, name, amount=1):
    state.counters[name] = state.counters.get(name, 0) + amount


def _trim(state, name, limit):
    rows = getattr(state, name)
    rows.sort(key=lambda r: (r["turn"], r["id"], r.get("region", -1), r.get("kind", "")))
    if len(rows) > limit:
        _bump(state, name + "_dropped", len(rows) - limit)
        del rows[:-limit]


def penalty_rows(state, turn):
    """Build bounded penalties only from strictly older personal observations."""
    totals = defaultdict(float)
    for row in state.memory:
        age = turn - row["turn"]
        window, magnitude = (REFUSED_WINDOW, P_REFUSED) if row["kind"] == "refused" else (LEFT_WINDOW, P_LEFT)
        if 0 < age < window:
            totals[(row["id"], row["region"])] += magnitude * (1 - age / window)
    return [(aid, region, -min(P_CAP, value)) for (aid, region), value in sorted(totals.items())]


def accepts_offer(world, agent_id, kind):
    """A personal offer decision, not a labour booking; unknown means accept.

Only exact individual receipts may populate the work memory. Rules 2 refuses
an offer when the person's last ten turns in that kind paid no more than the
ordinary income and titled output actually forgone. Training is a separate
kind, so a failed paid job cannot silently preclude an unrelated course.
"""
    if not adaptive_livelihoods_active(world):
        return True
    state = _state(world)
    rows = [r for r in state.work if r["id"] == agent_id and r["kind"] == kind
            and 0 < world.turn - r["turn"] <= WORK_WINDOW and r.get("net_milli") is not None]
    decline = bool(rows) and sum(r["net_milli"] for r in rows) <= 0
    if decline:
        _bump(state, "would_decline_" + kind)
    return not (decline and state.rules == "2" and state.mode != "record_only")


def note_work(world, agent_id, kind, *, paid_milli, withheld_milli, title_forgone_milli=None):
    """Planners supply exact receipt components, or explicitly unknown title cost.

An unknown cost remains unknown and cannot cause a refusal. Once a planner
has measured a net utility it can be learned on the following turn only.
"""
    if not adaptive_livelihoods_active(world):
        return
    state = _state(world)
    row = {"turn": int(world.turn), "id": int(agent_id), "kind": str(kind),
           "paid_milli": int(paid_milli), "withheld_milli": int(withheld_milli),
           "title_forgone_milli": title_forgone_milli,
           "net_milli": None if title_forgone_milli is None else
                        int(paid_milli) - int(withheld_milli) - int(title_forgone_milli)}
    key = (row["turn"], row["id"], row["kind"])
    if not any((r["turn"], r["id"], r["kind"]) == key for r in state.work):
        state.work.append(row)
    _trim(state, "work", MAX_WORK)


def before_agent_tick(world, agent_bridge, economy_result=None):
    if not adaptive_livelihoods_active(world):
        return
    state = _state(world)
    if state.last_turn >= 0 and state.last_turn != world.turn - 1:
        state.memory.clear()
        state.work.clear()
        _bump(state, "unobserved_gaps")
    rows = penalty_rows(state, world.turn)
    if state.mode == "shuffled":
        snap = agent_bridge._sim.get_snapshot()
        homes = dict(zip(map(int, snap.column("id").to_pylist()), map(int, snap.column("region").to_pylist())))
        index = {r.name: i for i, r in enumerate(world.regions)}
        remapped = []
        permutations = {}
        for aid, target, magnitude in rows:
            origin = homes.get(aid)
            choices = sorted(index[n] for n in world.regions[origin].adjacencies if n in index) if origin is not None else []
            if aid not in permutations:
                shift = 1 + stable_hash_int("a6_shuffle", world.turn, aid) % (len(choices) - 1) if len(choices) > 1 else 0
                permutations[aid] = dict(zip(choices, choices[shift:] + choices[:shift]))
            if len(choices) > 1 and target in permutations[aid]:
                target = permutations[aid][target]
            else:
                _bump(state, "unshuffled")
            remapped.append((aid, target, magnitude))
        # A permutation is one-to-one: row count and every magnitude survive.
        rows = sorted(remapped)
    # Install an empty input in record_only so refusals are still observed.
    agent_bridge._sim.set_adaptive_migration(world.turn, [] if state.mode == "record_only" else rows)
    state.frame = {"turn": world.turn, "rows": rows, "rows_installed": 0 if state.mode == "record_only" else len(rows),
                   "refusals": [], "quick_departures": [], "receipt": None}


def rollback_agent_tick(world, agent_bridge):
    if adaptive_livelihoods_active(world):
        agent_bridge._sim.cancel_adaptive_migration()
        _state(world).frame = None


def after_agent_tick(world, agent_bridge):
    if not adaptive_livelihoods_active(world):
        return
    state = _state(world)
    receipt = agent_bridge._sim.take_adaptive_migration_receipt()
    if receipt is None or receipt[0] != world.turn:
        raise RuntimeError("adaptive migration requires this turn's native receipt")
    state.frame["receipt"] = receipt
    for aid, origin, target, gate in receipt[1]:
        row = {"turn": int(world.turn), "id": int(aid), "kind": "refused", "region": int(target),
               "origin": int(origin), "gate": gate}
        state.memory.append(row)
        state.frame["refusals"].append(row)
    _trim(state, "memory", MAX_MEMORY)


def phase10(world, acc, economy_result, agent_bridge):
    if not adaptive_livelihoods_active(world):
        return []
    state = _state(world)
    if state.last_turn == world.turn:
        raise RuntimeError("adaptive livelihoods already settled this turn")
    if state.frame is None or state.frame["turn"] != world.turn:
        raise RuntimeError("adaptive livelihoods missing this turn's decision frame")
    from chronicler.residence_ledger import own_row_accessor
    for event in getattr(world, "agent_events_raw", ()):
        if event.turn != world.turn or event.event_type != "migration":
            continue
        aid = int(event.agent_id)
        prior = own_row_accessor(world, aid, consumer_turn=world.turn).read(aid)
        if prior is not None and prior["res"] == int(event.region) and prior["move_turn"] is not None \
                and world.turn - prior["res_since"] <= QUICK_LEAVE_TURNS:
            row = {"turn": int(world.turn), "id": aid, "kind": "left_soon", "region": int(event.region)}
            state.memory.append(row)
            state.frame["quick_departures"].append(row)
    state.memory = [r for r in state.memory if 0 <= world.turn - r["turn"] < LEFT_WINDOW]
    state.work = [r for r in state.work if 0 <= world.turn - r["turn"] <= WORK_WINDOW]
    _trim(state, "memory", MAX_MEMORY)
    state.last_turn = world.turn
    return []


def on_pool_reset(world):
    state = _state(world)
    if state is not None:
        state.memory.clear()
        state.work.clear()
        state.frame = None
        state.last_turn = -1
        _bump(state, "pool_resets")


def snapshot_summary(world):
    if not adaptive_livelihoods_active(world):
        return {}
    state = _state(world)
    return {"schema_version": 1, "stage": "A6", "source_turn": state.last_turn, "mode": state.mode,
            "rules": state.rules, "frame": state.frame, "memory_rows": len(state.memory),
            "work_rows": len(state.work), "counters": dict(state.counters),
            "parameters": {"refused_window": REFUSED_WINDOW, "left_window": LEFT_WINDOW,
                           "work_window": WORK_WINDOW, "penalty_cap": P_CAP}}
