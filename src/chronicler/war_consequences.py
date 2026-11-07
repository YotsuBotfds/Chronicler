"""D3: dated separation, wounds and return without another mortality authority.

Campaigns still select casualties. In active mode a declared 30% of selected
combat victims are released alive and receive the existing health authority's
injury episode only after that authority has finished the turn. Attrition is
never converted into an injury. Residence and army attachment stay distinct;
enlistment neither teleports nor prevents native migration.
"""
from __future__ import annotations

from chronicler.utils import stable_hash_int
from chronicler.war_consequences_state import WarConsequencesState

WOUND_SHARE = 0.30
MAX_HISTORY = 256


def _state(world):
    return getattr(getattr(world, "livelihoods", None), "war_consequences", None)


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


def note_release(world, army, entries, cause):
    for aid, region in entries:
        _note(world, "released", id=int(aid), region=int(region), army=army.army_id, cause=cause)


def before_agent_tick(world, agent_bridge, economy_result=None):
    if not war_consequences_active(world):
        return
    # Read the T-1 frame before either T's native tick or X1's sole writer.
    from chronicler.residence_ledger import separation
    _state(world).separation = separation(world, agent_bridge, consumer_turn=world.turn)


def on_pool_reset(world):
    state = _state(world)
    if state is None:
        return
    state.pending.clear()
    state.separation = state.frame = None
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
    state.last_turn = world.turn
    return []


def snapshot_summary(world):
    if not war_consequences_active(world):
        return {}
    state = _state(world)
    return {"schema_version": 1, "stage": "D3", "source_turn": state.last_turn,
            "mode": state.mode, "frame": state.frame, "history": state.history,
            "history_dropped": state.history_dropped, "counters": state.counters}
