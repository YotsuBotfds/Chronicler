"""D3: dated separation, wounds and return without another mortality authority.

Campaigns still select casualties. In active mode a declared 30% of selected
combat victims are released alive and receive the existing health authority's
injury episode only after that authority has finished the turn. Attrition is
never converted into an injury. Residence and army attachment stay distinct;
enlistment neither teleports nor prevents native migration.
"""
from __future__ import annotations

from copy import deepcopy

from chronicler.switch_state import sub_state_getter
from chronicler.utils import stable_hash_int
from chronicler.war_consequences_state import WarConsequencesState

WOUND_SHARE = 0.30
MAX_HISTORY = 256
MAX_EXPERIENCE = 16384
RETURN_WINDOW = 20
EVACUATE_PULL, RETURN_PULL = 0.20, 0.15


_state = sub_state_getter("war_consequences")


def war_consequences_active(world):
    state = _state(world)
    return state is not None and state.enabled and world.agent_mode == "hybrid"


def set_war_consequences_enabled(world, value, *, args=None, agent_mode=None):
    state = _state(world)
    mode = getattr(args, "war_consequences_mode", None) if args is not None else None
    if state is None:
        world.livelihoods.war_consequences = WarConsequencesState(enabled=bool(value), mode=mode or "active")
    else:
        if mode is not None and state.mode != mode:
            raise ValueError("a saved war-consequences mode cannot change")
        state.enabled = bool(value)
        if not value:
            state.pending.clear()
            state.separation = state.frame = None
            state.threats.clear()
            state.pending_threats.clear()
            state.returns.clear()


def _note(world, kind, **fields):
    state = _state(world)
    if not war_consequences_active(world):
        return
    row = {"turn": int(world.turn), "kind": kind, **fields}
    # Campaign hooks may run more than once in a turn, but a person can leave
    # a given army only once per cause. Stable keys also protect replayed hooks.
    key = (row["turn"], kind, fields.get("id"), fields.get("army"), fields.get("cause"))
    if state.noted_turn != world.turn:
        state.noted_turn, state.noted_keys, state._key_set = world.turn, [], set()
    if key in state._key_set:
        return
    state._key_set.add(key)
    state.noted_keys.append(key)
    if state.last_turn == world.turn and state.frame is not None:
        # End-of-turn demobilization follows livelihoods Phase 10. Record it
        # now instead of clearing it as stale at next turn's settlement.
        _commit_history(state, [row])
        events = state.frame["events"]
        if len(events) < MAX_HISTORY:
            events.append(row)
        else:
            state.frame["events_dropped"] += 1
    else:
        state.pending.append(row)


def _commit_history(state, rows):
    for row in rows:
        state.counters[row["kind"]] = state.counters.get(row["kind"], 0) + 1
    state.history.extend(rows)
    if len(state.history) > MAX_HISTORY:
        state.history_dropped += len(state.history) - MAX_HISTORY
        del state.history[:-MAX_HISTORY]


def _remember_return(state, aid, row):
    previous = state.returns.pop(int(aid), None)
    if previous is not None:
        # A later evacuation or release cannot replace a remembered home
        # with X1's newly assigned residence, or forget a witnessed war.
        if previous.get("home") is not None:
            row = {**row, "home": previous["home"], "home_source_turn": previous.get("home_source_turn")}
        row["wars"] = [list(key) for key in sorted({tuple(key) for key in previous["wars"] + row["wars"]})]
    if len(state.returns) >= MAX_EXPERIENCE:
        del state.returns[next(iter(state.returns))]
        state.counters["returns_dropped"] = state.counters.get("returns_dropped", 0) + 1
    state.returns[int(aid)] = row



def split_victims(world, army, victims, cause):
    """Return (dead, wounded) from the campaign's already selected stable ids.

No campaign RNG is consumed here. Only battle casualties are eligible;
attrition and other lethal causes keep their existing authority.
"""
    if not war_consequences_active(world):
        return list(victims), []
    state = _state(world)
    eligible = cause in ("battle", "combat")
    wounded = [entry for entry in victims if eligible and
               stable_hash_int("cw-d3-wound", world.seed, world.turn, army.army_id,
                               cause, int(entry[0])) % 10000 < int(WOUND_SHARE * 10000)]
    for aid, region in wounded:
        _note(world, "wounded" if state.mode == "active" else "would_wound",
              id=int(aid), region=int(region), army=army.army_id, cause=cause)
    if state.mode == "record_only":
        return list(victims), []
    wounded_set = set(wounded)
    return [entry for entry in victims if entry not in wounded_set], wounded


def _refresh_return_stock(world, state):
    if state.last_turn == world.turn and state.frame is not None:
        state.frame["return_experiences"] = len(state.returns)


def note_release(world, army, entries, cause):
    for aid, region in entries:
        _note(world, "released", id=int(aid), region=int(region), army=army.army_id, cause=cause)
        if war_consequences_active(world):
            wars = getattr(getattr(world, "war_state", None), "wars", []) + getattr(getattr(world, "war_state", None), "ended_wars", [])
            matching = [w for w in wars if w.war_key == getattr(army, "war_key", None)
                        and w.start_turn <= getattr(army, "raised_turn", world.turn)]
            if matching:
                war = max(matching, key=lambda w: w.start_turn)
                from chronicler.residence_ledger import LedgerReadRefused, own_row_accessor
                try:
                    prior = own_row_accessor(world, int(aid), consumer_turn=world.turn).read(int(aid))
                except LedgerReadRefused:
                    # Late demobilisation may follow X1's sole writer. An
                    # unavailable prior home stays unknown; never read T.
                    prior = None
                _remember_return(_state(world), aid, {"turn": int(world.turn), "kind": "released_service",
                    "wars": [[war.war_key, war.start_turn]],
                    "home": prior["home"] if prior is not None else None,
                    "home_source_turn": prior["source_turn"] if prior is not None else None})
                _refresh_return_stock(world, _state(world))


def movement_rows(world, aid, origin, prior, *, attached=()):
    """Dated local experience, supplied one's already-bound X1 row by A6.

    These are destination scores for native migration, never movement orders.
    A formal peace notice is not a claim that the destination is safe.
    """
    if not war_consequences_active(world) or prior is None:
        return []
    state = _state(world)
    if state.mode == "record_only":
        return []
    if int(aid) in attached:
        # An attached person's physical service location is not their native
        # residence. Do not turn a danger at home into a claimed evacuation.
        return []
    index = {r.name: i for i, r in enumerate(world.regions)}
    adjacent = sorted(index[n] for n in world.regions[origin].adjacencies if n in index)
    rows = []
    threat = state.threats.get(int(aid))
    if threat and threat["turn"] == world.turn - 1 and threat["region"] == origin:
        rows.extend((int(aid), dest, EVACUATE_PULL) for dest in adjacent)
    experience = state.returns.get(int(aid))
    home = experience.get("home") if experience is not None else None
    if experience and home in adjacent and home != origin and experience["turn"] < world.turn:
        notices = {(w.war_key, w.start_turn): w.ended_turn for w in getattr(world.war_state, "ended_wars", [])
                   if w.ended_turn is not None and w.ended_turn < world.turn}
        dates = [notices[tuple(key)] for key in experience["wars"] if tuple(key) in notices]
        # All personally witnessed conflicts must have a dated formal peace.
        if dates and len(dates) == len(experience["wars"]):
            age = world.turn - max(dates)
            if 0 < age < RETURN_WINDOW:
                rows.append((int(aid), int(home), RETURN_PULL * (1 - age / RETURN_WINDOW)))
    return rows


def note_migration(world, aid, origin, destination, prior):
    if not war_consequences_active(world) or prior is None:
        return
    state = _state(world)
    threat = state.threats.get(int(aid))
    if threat and threat["region"] == origin and 0 <= world.turn - threat["turn"] <= 1:
        _remember_return(state, aid, {"turn": int(world.turn), "kind": "evacuated", "wars": threat["wars"],
            "home": int(prior["home"]), "home_source_turn": prior.get("source_turn", world.turn - 1)})
        _note(world, "evacuated", id=int(aid), region=int(origin), destination=int(destination),
              home=prior["home"], cause="personally_witnessed_field_army")
    if int(aid) in state.returns and int(destination) == state.returns[int(aid)].get("home"):
        _note(world, "returned", id=int(aid), region=int(destination), cause=state.returns[int(aid)]["kind"])
        del state.returns[int(aid)]
    _refresh_return_stock(world, state)


def before_agent_tick(world, agent_bridge, economy_result=None):
    if not war_consequences_active(world):
        return
    # Read the T-1 frame before either T's native tick or X1's sole writer.
    from chronicler.residence_ledger import separation
    state = _state(world)
    state.separation = separation(world, agent_bridge, consumer_turn=world.turn)
    if state.separation is not None:
        state.separation["separated_total"] = len(state.separation["separated"])
        state.separation["separated_dropped"] = max(0, len(state.separation["separated"]) - MAX_HISTORY)
        state.separation["separated"] = state.separation["separated"][:MAX_HISTORY]
    campaign = getattr(world, "war_state", None)
    index = {r.name: i for i, r in enumerate(world.regions)}
    wars = {w.war_key: w for w in getattr(campaign, "wars", [])}
    dangers = {}
    from chronicler.utils import at_war
    for army in getattr(campaign, "armies", []):
        region = index.get(army.region)
        if region is None or army.soldiers <= 0:
            continue
        controller = world.regions[region].controller
        if controller is None or not at_war(world, controller, army.civ):
            continue
        war = wars.get(army.war_key)
        dangers.setdefault(region, set())
        if war is not None:
            dangers[region].add((war.war_key, war.start_turn))
    snap = agent_bridge._sim.get_snapshot()
    attached = {int(aid) for army in getattr(campaign, "armies", []) for aid, _ in army.roster}
    state.pending_threats = {int(aid): {"turn": int(world.turn), "region": int(region),
        "wars": [list(key) for key in sorted(dangers[int(region)])]}
        for aid, region in zip(snap.column("id").to_pylist(), snap.column("region").to_pylist())
        if int(region) in dangers and int(aid) not in attached}


def on_pool_reset(world):
    state = _state(world)
    if state is None:
        return
    state.pending.clear()
    state.noted_turn = None
    state.noted_keys.clear()
    state._key_set.clear()
    state.separation = state.frame = None
    state.threats.clear()
    state.pending_threats.clear()
    state.returns.clear()
    state.counters["pool_resets"] = state.counters.get("pool_resets", 0) + 1


def phase10(world, acc, economy_result, agent_bridge):
    if not war_consequences_active(world):
        return []
    state = _state(world)
    if state.last_turn == world.turn:
        raise RuntimeError("war consequences already settled this turn")
    rows = [r for r in state.pending if r["turn"] == world.turn]
    state.pending.clear()
    snap = agent_bridge._sim.get_snapshot()
    live = set(map(int, snap.column("id").to_pylist()))
    state.threats = {aid: row for aid, row in state.threats.items()
                     if aid in live and 0 <= world.turn - row["turn"] <= 1}
    state.threats.update({aid: row for aid, row in state.pending_threats.items()
                         if aid in live and row["turn"] == world.turn})
    state.pending_threats.clear()
    campaign = getattr(world, "war_state", None)
    active = {(w.war_key, w.start_turn) for w in getattr(campaign, "wars", [])}
    ended = {(w.war_key, w.start_turn): w.ended_turn for w in getattr(campaign, "ended_wars", [])
             if w.ended_turn is not None}
    def remembered(row):
        keys = list(map(tuple, row["wars"]))
        return (world.turn - row["turn"] <= RETURN_WINDOW or any(key in active for key in keys)
                or any(key in ended and world.turn - ended[key] <= RETURN_WINDOW for key in keys))
    state.returns = {aid: row for aid, row in state.returns.items() if aid in live and remembered(row)}
    for name in ("threats", "returns"):
        observations = getattr(state, name)
        if len(observations) > MAX_EXPERIENCE:
            keep = sorted(observations, key=lambda aid: (observations[aid]["turn"], aid))[-MAX_EXPERIENCE:]
            state.counters[name + "_dropped"] = state.counters.get(name + "_dropped", 0) + len(observations) - len(keep)
            setattr(state, name, {aid: observations[aid] for aid in keep})
    if state.mode == "active":
        from chronicler.health_care_state import InjuryEpisode
        health = world.health_care
        episodes = {e.agent_id: e for e in health.episodes}
        for row in rows:
            if row["kind"] != "wounded" or row["id"] not in live:
                continue
            old = episodes.get(row["id"])
            if old is not None:
                old.remaining = max(old.remaining, health.recovery_work)
            else:
                episodes[row["id"]] = InjuryEpisode(agent_id=row["id"], onset_turn=world.turn,
                    remaining=health.recovery_work, origin_region=row["region"])
        health.episodes = [episodes[aid] for aid in sorted(episodes)]
    _commit_history(state, rows)
    state.frame = {"turn": world.turn, "events": rows[:MAX_HISTORY],
                   "events_dropped": max(0, len(rows) - MAX_HISTORY), "separation": state.separation,
                   "separation_source": "T-1; computed before this turn's native tick",
                   "injury_authority": "health_care", "wound_share": WOUND_SHARE}
    state.frame["local_threats"] = len(state.threats)
    state.frame["return_experiences"] = len(state.returns)
    state.last_turn = world.turn
    return []


def snapshot_summary(world):
    if not war_consequences_active(world):
        return {}
    state = _state(world)
    return {"schema_version": 1, "stage": "D3", "source_turn": state.last_turn,
            "mode": state.mode, "frame": deepcopy(state.frame), "history": deepcopy(state.history),
            "history_dropped": state.history_dropped, "counters": dict(state.counters)}
