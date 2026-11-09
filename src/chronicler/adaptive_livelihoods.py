"""A6: personal dated failures inform the existing native migration decision.

No Python movement path, provenance read, or same-turn residence read is used.
Rules 1 is the first audit's migration penalty; rules 2 additionally exposes
experienced work-offer refusals through ``accepts_offer``. Unknown work utility
is never invented. Regional and crew totals are never assigned to a person.
"""
from __future__ import annotations

from collections import defaultdict
import heapq

from chronicler.adaptive_livelihoods_state import AdaptiveLivelihoodsState
from chronicler.utils import stable_hash_int
from chronicler.switch_state import sub_state_getter

MAX_MEMORY = 16384
MAX_WORK = 16384
REFUSED_WINDOW, LEFT_WINDOW, QUICK_LEAVE_TURNS = 10, 20, 10
P_REFUSED, P_LEFT, P_CAP = 0.20, 0.15, 0.30
WORK_WINDOW = 10


_state = sub_state_getter("adaptive_livelihoods")


def adaptive_livelihoods_active(world):
    state = _state(world)
    return state is not None and state.enabled and world.agent_mode == "hybrid"


def set_adaptive_livelihoods_enabled(world, value, *, args=None, agent_mode=None):
    state = _state(world)
    mode = getattr(args, "adaptive_livelihoods_mode", None) if args else None
    rules = getattr(args, "adaptive_livelihoods_rules", None) if args else None
    channels = getattr(args, "adaptive_livelihoods_decision_channels", None) if args else None
    effective_rules = rules or (state.rules if state is not None else "2")
    if channels is not None and effective_rules != "3":
        raise ValueError("adaptive livelihoods decision channels require rules3")
    if state is None:
        world.livelihoods.adaptive_livelihoods = AdaptiveLivelihoodsState(
            enabled=bool(value), mode=mode or "adapt", rules=rules or "2", decision_channels=channels or "all")
    else:
        if ((mode is not None and mode != state.mode) or (rules is not None and rules != state.rules)
                or (channels is not None and channels != state.decision_channels)):
            raise ValueError("saved adaptive livelihoods mode/rules/channels cannot change")
        state.enabled = bool(value)
        if not value:
            state.memory.clear()
            state.work.clear()
            state.known_residences.clear()
            state.trade_experience.clear()
            state.frame = None
            state._index_turn, state._work_index, state._offer_cache = None, {}, {}
            state._record_turn, state._record_keys, state._work_heap = None, set(), []


def _bump(state, name, amount=1):
    state.bump(name, amount)


def _personal_channel(state, channel):
    """Versioned personal decisions, independent of D3's dated war inputs."""
    return (state.mode != "record_only" and state.rules in ("2", "3")
            and (state.rules != "3" or state.decision_channels != "no_" + channel))


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


def _work_index(state, turn):
    if state._index_turn != turn:
        if state.last_turn >= 0 and state.last_turn != turn - 1:
            state.memory.clear()
            state.work.clear()
        state._index_turn, state._work_index, state._offer_cache = turn, {}, {}
        for row in state.work:
            if 0 < turn - row["turn"] <= WORK_WINDOW:
                state._work_index.setdefault((row["id"], row["kind"]), []).append(row)
    return state._work_index


def _declines(state, turn, agent_id, kind):
    history = _work_index(state, turn).get((int(agent_id), str(kind)), ())
    if kind in ("apprenticeship", "academy_training"):
        # An attended session is progress toward a real qualification/skill.
        # Do not pretend its benefit has zero monetary value. A new course is
        # refused only after repeated personal failed attendance without any
        # observed progress in the same window.
        return (sum(r.get("progress") is False for r in history) >= 2
                and not any(r.get("progress") is True for r in history))
    rows = [r for r in history if r.get("net_milli") is not None]
    return bool(rows) and sum(r["net_milli"] for r in rows) <= 0


def declined_ids(world, kind):
    """Dated choice exclusions for a planner, without claiming an offer occurred."""
    if not adaptive_livelihoods_active(world):
        return []
    state = _state(world)
    if not _personal_channel(state, "work"):
        return []
    return sorted(aid for aid, row_kind in _work_index(state, world.turn)
                  if row_kind == kind and _declines(state, world.turn, aid, kind))


def accepts_offer(world, agent_id, kind):
    """A new personal offer decision, deduplicated across planner probes.

    Training uses its exact progress receipts; paid work uses fully observed
    personal cash and forgone-title value. Unknown never means a monetary loss.
    A finite commitment already accepted is not silently terminated here.
    """
    if not adaptive_livelihoods_active(world):
        return True
    state = _state(world)
    _work_index(state, world.turn)
    key = (int(agent_id), str(kind))
    if key in state._offer_cache:
        return state._offer_cache[key]
    decline = _declines(state, world.turn, *key)
    accepted = not (decline and _personal_channel(state, "work"))
    if state.offer_turn != world.turn:
        state.offer_turn, state.offers, state.offers_dropped = world.turn, [], 0
    if decline:
        _bump(state, "would_decline_" + kind)
    if len(state.offers) < 256:
        state.offers.append({"turn": world.turn, "id": int(agent_id), "kind": str(kind),
                             "would_decline": decline, "accepted": accepted})
    else:
        state.offers_dropped += 1
    state._offer_cache[key] = accepted
    return accepted


def note_work(world, agent_id, kind, *, paid_milli, withheld_milli, title_forgone_milli=None,
              progress=None, source=None):
    """Exact personal components or null; group totals never stand in for them."""
    if not adaptive_livelihoods_active(world):
        return
    state = _state(world)
    known = all(v is not None for v in (paid_milli, withheld_milli, title_forgone_milli))
    row = {"turn": int(world.turn), "id": int(agent_id), "kind": str(kind),
           "paid_milli": int(paid_milli) if paid_milli is not None else None,
           "withheld_milli": int(withheld_milli) if withheld_milli is not None else None,
           "title_forgone_milli": title_forgone_milli, "progress": progress, "source": source,
           "net_milli": int(paid_milli) - int(withheld_milli) - int(title_forgone_milli) if known else None}
    key = (row["turn"], row["id"], row["kind"])
    if state._record_turn != world.turn:
        state._record_turn = world.turn
        state._record_keys = {(r["id"], r["kind"]) for r in state.work if r["turn"] == world.turn}
        state._work_heap = [((r["turn"], r["id"], r["kind"]), i) for i, r in enumerate(state.work)]
        heapq.heapify(state._work_heap)
    if key[1:] in state._record_keys:
        return
    state._record_keys.add(key[1:])
    if len(state.work) < MAX_WORK:
        heapq.heappush(state._work_heap, (key, len(state.work)))
        state.work.append(row)
    else:
        # Keep the newest deterministic keys in bounded O(log N), rather than
        # sorting the full history for every paid member at declared scale.
        if key > state._work_heap[0][0]:
            index = state._work_heap[0][1]
            heapq.heapreplace(state._work_heap, (key, index))
            state.work[index] = row
        _bump(state, "work_dropped")


def forgone_title(world, region, *, occupation=0):
    """Zero only when a personal title cannot exist; otherwise unobserved.

    The existing harvest receipt does not supply a person's counterfactual
    output without diverted work. Its regional harvest is not that person's
    forgone title and must not be divided among the crew as if it were known.
    """
    retail = getattr(getattr(world, "livelihoods", None), "household_retail", None)
    if occupation != 0 or retail is None or not retail.enabled or retail.mode == "record_only":
        return 0
    return None if retail.region(int(region)) is not None else 0


def record_payroll(world, work, receipt, transfers, regions):
    """Called before payroll truncates its full per-person money receipts."""
    if not adaptive_livelihoods_active(world):
        return
    paid_rows = defaultdict(int)
    for transfer in transfers:
        if transfer.kind == "wage" and transfer.payee[0] == "agent_wealth" and transfer.payer[0] == "workshop_cash":
            paid_rows[(transfer.payer[1], transfer.payee[1])] += transfer.applied
    for site, assignment in work.items():
        for aid, share in zip(assignment.crew, assignment.shares, strict=True):
            paid = paid_rows[(site, aid)]
            observed = receipt.get(aid) if receipt is not None else None
            # A combined paid-work row cannot be attributed to this job if
            # another paid share was present. Keep its cost explicitly null.
            withheld = round(observed[2] * 1000) if observed is not None and abs(observed[0] - share) <= 1e-6 else None
            note_work(world, aid, "workshop", paid_milli=paid, withheld_milli=withheld,
                      title_forgone_milli=forgone_title(world, regions[site]),
                      source="workshop_payroll:untruncated wages + keyed paid-work receipt")


def _known_residences(world, ids):
    """Dispatch one bound OwnRow to each live person's own information choice."""
    from chronicler.residence_ledger import own_row_accessor
    state = _state(world)
    live = set(map(int, ids))
    state.known_residences = {aid: seen for aid, seen in state.known_residences.items() if aid in live}
    own = {}
    for aid in sorted(live):
        row = own_row_accessor(world, aid, consumer_turn=world.turn).read(aid)
        own[aid] = row
        if row is not None:
            seen = state.known_residences.setdefault(aid, {})
            for region in (row["home"], row["res"], row["move_from"]):
                if region is not None:
                    seen[int(region)] = row["source_turn"]
    rows = sorted((date, aid, region) for aid, seen in state.known_residences.items()
                  for region, date in seen.items())
    if len(rows) > MAX_MEMORY:
        _bump(state, "known_residences_dropped", len(rows) - MAX_MEMORY)
        rows = rows[-MAX_MEMORY:]
        state.known_residences = {}
        for date, aid, region in rows:
            state.known_residences.setdefault(aid, {})[region] = date
    return own, [(aid, region) for date, aid, region in rows if date < world.turn]


def note_trade(world, agent_id, destination, outcome, cause, shipment, *, package="titled_trade"):
    """A holder's dated closed shipment, not knowledge of another merchant."""
    if not adaptive_livelihoods_active(world):
        return
    state = _state(world)
    row = {"turn": int(world.turn), "id": int(agent_id), "region": int(destination),
           "kind": "shipment", "outcome": str(outcome), "cause": cause, "shipment": int(shipment), "package": str(package)}
    state.trade_experience.append(row)
    _trim(state, "trade_experience", MAX_MEMORY)


def trade_destinations(world, sim, agent_ids):
    """None is the unchanged rules path; otherwise use dated own trade packets."""
    if not adaptive_livelihoods_active(world):
        return None
    state = _state(world)
    if not _personal_channel(state, "trade"):
        return None
    return {int(aid): set(map(int, destinations))
            for aid, destinations in sim.usable_trade_destinations(sorted(agent_ids), world.turn)}


def accepts_trade_destination(world, aid, destination, known):
    if known is None:
        return True
    state = _state(world)
    if destination not in known.get(int(aid), set()):
        _bump(state, "trade_unknown_destination")
        return False
    failed = any(r["id"] == aid and r["region"] == destination and 0 < world.turn - r["turn"] <= WORK_WINDOW
                 and r["outcome"] in ("returned", "released_returned", "seized", "route_lost", "recipient_lost", "carrier_released", "expired") for r in state.trade_experience)
    if failed:
        _bump(state, "trade_personal_return_refusal")
    return not failed


def before_agent_tick(world, agent_bridge, economy_result=None):
    if not adaptive_livelihoods_active(world):
        return
    state = _state(world)
    if state.last_turn >= 0 and state.last_turn != world.turn - 1:
        state.memory.clear()
        state.work.clear()
        state.known_residences.clear()
        state.trade_experience.clear()
        _bump(state, "unobserved_gaps")
    if state.rules == "3":
        _before_agent_tick_v3(world, agent_bridge, state)
        return
    rows = penalty_rows(state, world.turn)
    information = []
    if state.rules == "2":
        snap = agent_bridge._sim.get_snapshot()
        homes = dict(zip(map(int, snap.column("id").to_pylist()), map(int, snap.column("region").to_pylist())))
        own, known = _known_residences(world, homes)
        information = agent_bridge._sim.set_adaptive_information(world.turn, known)
        if state.mode == "record_only":
            agent_bridge._sim.cancel_adaptive_information()
        from chronicler.war_consequences import movement_rows
        scores = defaultdict(float)
        for aid, target, value in rows:
            scores[(aid, target)] += value
        attached = {int(aid) for army in getattr(getattr(world, "war_state", None), "armies", []) for aid, _ in army.roster}
        for aid, origin in sorted(homes.items()):
            for _, target, value in movement_rows(world, aid, origin, own[aid], attached=attached):
                scores[(aid, target)] += value
        rows = [(aid, target, max(-P_CAP, min(P_CAP, score)))
                for (aid, target), score in sorted(scores.items()) if score != 0]
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
    state.frame = {"turn": world.turn, "rows": rows[:256], "rows_total": len(rows),
                   "rows_dropped": max(0, len(rows) - 256), "rows_installed": 0 if state.mode == "record_only" else len(rows),
                   "refusals": [], "quick_departures": [], "receipt": None,
                   "known_destinations": information[:256], "known_destinations_total": len(information),
                   "known_destinations_dropped": max(0, len(information) - 256),
                   "information_gate_installed": state.rules == "2" and state.mode != "record_only"}


def _before_agent_tick_v3(world, agent_bridge, state):
    """Personal controls never erase or redirect D3's own physical targets.

    Rules1/2 above retain their historical control behavior for saved runs.
    Rows below describe actual installed input; would-be personal rows remain
    separate observations, not a claim about which input caused an outcome.
    """
    sim = agent_bridge._sim
    snap = sim.get_snapshot()
    homes = dict(zip(map(int, snap.column("id").to_pylist()), map(int, snap.column("region").to_pylist())))
    own, known = _known_residences(world, homes)
    information = sim.set_adaptive_information(world.turn, known)
    information_applied = _personal_channel(state, "information")
    if not information_applied:
        sim.cancel_adaptive_information()
    would = penalty_rows(state, world.turn)
    personal = list(would) if _personal_channel(state, "migration_experience") else []
    if state.mode == "shuffled":
        index = {r.name: i for i, r in enumerate(world.regions)}
        remapped, permutations = [], {}
        for aid, target, magnitude in personal:
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
        personal = sorted(remapped)
    from chronicler.war_consequences import movement_rows
    attached = {int(aid) for army in getattr(getattr(world, "war_state", None), "armies", []) for aid, _ in army.roster}
    war = [row for aid, origin in sorted(homes.items())
           for row in movement_rows(world, aid, origin, own[aid], attached=attached)]
    scores = defaultdict(float)
    for aid, target, value in [*personal, *war]:
        scores[(aid, target)] += value
    rows = [(aid, target, max(-P_CAP, min(P_CAP, score)))
            for (aid, target), score in sorted(scores.items()) if score != 0]
    sim.set_adaptive_migration(world.turn, rows)
    state.frame = {"turn": world.turn, "decision_channels": state.decision_channels,
                   "rows": rows[:256], "rows_total": len(rows), "rows_installed": len(rows),
                   "rows_dropped": max(0, len(rows) - 256),
                   "a6_rows": personal[:256], "a6_rows_total": len(personal),
                   "d3_rows": war[:256], "d3_rows_total": len(war),
                   "migration_rows_would": would[:256], "migration_rows_would_total": len(would),
                   "refusals": [], "quick_departures": [], "receipt": None,
                   "known_destinations": information[:256], "known_destinations_total": len(information),
                   "known_destinations_dropped": max(0, len(information) - 256),
                   "information_gate_installed": information_applied}


def rollback_agent_tick(world, agent_bridge):
    if adaptive_livelihoods_active(world):
        agent_bridge._sim.cancel_adaptive_migration()
        if _state(world).rules in ("2", "3"):
            agent_bridge._sim.cancel_adaptive_information()
        _state(world).frame = None


def after_agent_tick(world, agent_bridge):
    if not adaptive_livelihoods_active(world):
        return
    state = _state(world)
    receipt = agent_bridge._sim.take_adaptive_migration_receipt()
    if receipt is None or receipt[0] != world.turn:
        raise RuntimeError("adaptive migration requires this turn's native receipt")
    state.frame["receipt"] = (receipt[0], receipt[1][:256], *receipt[2:])
    state.frame["refusals_total"] = len(receipt[1])
    state.frame["refusals_dropped"] = max(0, len(receipt[1]) - 256)
    for aid, origin, target, gate in receipt[1]:
        row = {"turn": int(world.turn), "id": int(aid), "kind": "refused", "region": int(target),
               "origin": int(origin), "gate": gate}
        state.memory.append(row)
        if len(state.frame["refusals"]) < 256:
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
        from chronicler.war_consequences import note_migration
        note_migration(world, aid, int(event.region), int(event.target_region), prior)
        if prior is not None and prior["res"] == int(event.region) and prior["move_turn"] is not None \
                and world.turn - prior["res_since"] <= QUICK_LEAVE_TURNS:
            row = {"turn": int(world.turn), "id": aid, "kind": "left_soon", "region": int(event.region)}
            state.memory.append(row)
            state.frame["quick_departures_total"] = state.frame.get("quick_departures_total", 0) + 1
            if len(state.frame["quick_departures"]) < 256:
                state.frame["quick_departures"].append(row)
    state.memory = [r for r in state.memory if 0 <= world.turn - r["turn"] < LEFT_WINDOW]
    state.work = [r for r in state.work if 0 <= world.turn - r["turn"] <= WORK_WINDOW]
    state.trade_experience = [r for r in state.trade_experience if 0 <= world.turn - r["turn"] <= WORK_WINDOW]
    _trim(state, "memory", MAX_MEMORY)
    _trim(state, "work", MAX_WORK)
    state._record_turn, state._record_keys, state._work_heap = None, set(), []
    state.frame["quick_departures_dropped"] = max(0, state.frame.get("quick_departures_total", 0) - 256)
    state.frame["work"] = [dict(r) for r in state.work if r["turn"] == world.turn][:256]
    state.frame["work_dropped"] = max(0, sum(r["turn"] == world.turn for r in state.work) - 256)
    state.frame["offers"] = list(state.offers) if state.offer_turn == world.turn else []
    state.frame["offers_dropped"] = state.offers_dropped if state.offer_turn == world.turn else 0
    state.frame["trade"] = [dict(r) for r in state.trade_experience if r["turn"] == world.turn][:256]
    state.frame["trade_dropped"] = max(0, sum(r["turn"] == world.turn for r in state.trade_experience) - 256)
    state.last_turn = world.turn
    return []


def on_pool_reset(world):
    state = _state(world)
    if state is not None:
        state.memory.clear()
        state.work.clear()
        state.known_residences.clear()
        state.trade_experience.clear()
        state.frame = None
        state.last_turn = -1
        state.offer_turn, state.offers, state.offers_dropped = None, [], 0
        state._index_turn, state._work_index, state._offer_cache = None, {}, {}
        state._record_turn, state._record_keys, state._work_heap = None, set(), []
        _bump(state, "pool_resets")


def snapshot_summary(world):
    if not adaptive_livelihoods_active(world):
        return {}
    state = _state(world)
    return {"schema_version": 1, "stage": "A6", "source_turn": state.last_turn, "mode": state.mode,
            **({"decision_channels": state.decision_channels} if state.rules == "3" else {}),
            "rules": state.rules, "frame": state.frame, "memory_rows": len(state.memory),
            "work_rows": len(state.work), "counters": dict(state.counters),
            "parameters": {"refused_window": REFUSED_WINDOW, "left_window": LEFT_WINDOW,
                           "work_window": WORK_WINDOW, "penalty_cap": P_CAP}}
