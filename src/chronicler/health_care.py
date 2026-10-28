"""Default-off rural occupational injury and spouse care, hybrid only.

Episodes persist in WorldState. Before goods production the native builder
resolves stable IDs, co-resident spouses and manual-work budgets. After the
agent tick, living patients recover and surviving actual workers may acquire
an episode for the following turn. Disease, combat and mortality are untouched.
"""
from __future__ import annotations
from copy import deepcopy
import math
from chronicler.health_care_state import HealthCareState, InjuryEpisode

DEFAULT_ENABLED_FOR_NEW_WORLDS = False


def health_care_on(world) -> bool:
    return isinstance(getattr(world, "health_care", None), HealthCareState)


def health_care_active(world) -> bool:
    return health_care_on(world) and getattr(world, "agent_mode", None) == "hybrid"


def set_health_care_enabled(world, enabled: bool) -> None:
    if enabled:
        if not health_care_on(world):
            world.health_care = HealthCareState()
    else:
        world.health_care = None


def validate_health_care(world) -> None:
    if health_care_on(world):
        state = world.health_care
        for name, low, high in (("injury_rate", 0., .25), ("impairment", 0., 1.),
                                ("care_fraction", 0., 1.), ("recovery_work", 1., 10.)):
            value = getattr(state, name)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"invalid health care {name}: expected {low}..{high}")
        ids = [e.agent_id for e in world.health_care.episodes]
        if len(ids) != len(set(ids)):
            raise ValueError("health care has duplicate injury agent IDs")


def prepare_health_care(world, bridge) -> None:
    if not health_care_active(world):
        return
    validate_health_care(world)
    state = world.health_care
    if state.last_tick_turn >= world.turn:
        raise ValueError("health care already completed this turn")
    sim = getattr(bridge, "_sim", None)
    if sim is None or not callable(getattr(sim, "prepare_health_work", None)):
        raise RuntimeError("--health-care requires a fresh native build with health work inputs")
    armies = getattr(getattr(world, "war_state", None), "armies", [])
    enlisted = sorted({int(aid) for army in armies for aid, _ in army.roster})
    cities = getattr(getattr(world, "cities", None), "cities", [])
    urban = sorted({int(city.settlement_id) for city in cities})
    state._prepared = sim.prepare_health_work(
        [e.agent_id for e in state.episodes], enlisted, urban,
        state.impairment, state.care_fraction if state.care_enabled else 0.0,
    )


def finish_health_care(world, bridge) -> list:
    if not health_care_active(world):
        return []
    state = world.health_care
    if state._prepared is None:
        raise RuntimeError("health care finish requires this turn's work preparation")
    rows, state._prepared = state._prepared, None
    alive, new, work = bridge._sim.finish_health_work(world.turn, state.injury_rate)
    alive = dict(alive)
    assignments = {int(aid): (int(region), int(giver), float(care)) for aid, region, giver, care in rows}
    by_region = {}
    civs = world.civ_index_map
    for region, impaired, care, recipients in work:
        r = world.regions[region]
        by_region[int(region)] = {
            "region": int(region), "region_name": r.name,
            "civ": civs.get(r.controller) if r.controller else None, "civ_name": r.controller,
            "episodes": 0, "new_injuries": 0, "recoveries": 0,
            "impaired_work": float(impaired), "care_work": float(care),
            "care_recipients": int(recipients), "recovery_progress": 0.0,
            "cared_recovery_progress": 0.0,
        }
    kept = []
    censored = 0
    for episode in state.episodes:
        if episode.agent_id not in alive:
            censored += 1
            continue
        region, giver, care = assignments[episode.agent_id]
        row = by_region[region]
        progress = min(episode.remaining, 1.0 + min(1.0, 5.0 * care))
        episode.remaining -= progress
        row["recovery_progress"] += progress
        if giver:
            row["cared_recovery_progress"] += progress
        if episode.remaining > 0.0:
            kept.append(episode)
        else:
            row["recoveries"] += 1
    for aid, region, current_region in new:
        kept.append(InjuryEpisode(agent_id=int(aid), onset_turn=world.turn,
                                  remaining=state.recovery_work, origin_region=int(region)))
        by_region[int(region)]["new_injuries"] += 1
        alive[int(aid)] = int(current_region)
    kept.sort(key=lambda e: e.agent_id)
    state.episodes = kept
    for episode in kept:
        # Native rows describe current living patients; new onsets supply region.
        region = alive[episode.agent_id]
        by_region[region]["episodes"] += 1
    metrics = ("episodes", "new_injuries", "recoveries", "impaired_work", "care_work",
               "care_recipients", "recovery_progress", "cared_recovery_progress")
    state.summary = {"source_turn": world.turn, "units": "worker-turns", "censored_episodes": censored,
                     **{k: sum(row[k] for row in by_region.values()) for k in metrics},
                     "regions": [by_region[r] for r in sorted(by_region)]}
    state.last_tick_turn = world.turn
    from chronicler.models import Event
    return [Event(turn=world.turn, event_type="occupational_injury", importance=3,
                  actors=[row["civ_name"]] if row["civ_name"] else [],
                  region=row["region_name"],
                  description=f"{row['new_injuries']} rural workers in {row['region_name']} suffer temporary work injuries.")
            for row in state.summary["regions"] if row["new_injuries"]]


def snapshot_summary(world) -> dict:
    if not health_care_active(world):
        return {}
    state = world.health_care
    if state.last_tick_turn != world.turn - 1 or state.summary.get("source_turn") != state.last_tick_turn:
        return {}
    return deepcopy(state.summary)
