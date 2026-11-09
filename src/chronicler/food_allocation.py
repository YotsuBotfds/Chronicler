"""L2 household food allocation (``--food-allocation``, default off).

The Phase 2 economy withdraws food from each region exactly as before; this
package decides who eats it. After the native economy tick (before public
granaries release), it records each region's pre-release food sufficiency and
the Phase 2 native alive counts the demand was computed for. Before the
native agent tick it installs a one-tick allocation (``set_food_allocation``);
the tick allocates the region's post-release rations to living people under
the chosen rule (``chronicler-agents/src/provisioning.rs``) and routes each
person's own ration into needs, satisfaction and hunger mortality/fertility.
After the tick it takes the receipts once.

Rules (``--food-allocation-regime``): ``equal`` (the identity control: the
regional signal), ``floor_means`` (default: an equal subsistence floor, the
scarce remainder by household means) and ``targeted_relief`` (market food
equally, the public release to the poorest households first). Parameters are
declared modeling choices, overridable as tuning keys
``livelihoods.food.floor`` (0.5 rations) and ``livelihoods.food.target_share``
(0.5 of households). Migration, occupation targets and famine memories keep
the regional signal; the severe-hunger run stays regional.
"""
from __future__ import annotations

import math

from chronicler.food_allocation_state import REGIMES, SNAPSHOT_SAMPLE, FoodAllocationState
from chronicler.switch_state import sub_state_getter

FLOOR = 0.5
TARGET_SHARE = 0.5


_state = sub_state_getter("food_allocation")


def set_food_allocation_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    regime = getattr(args, "food_allocation_regime", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.food_allocation = state = FoodAllocationState(regime=regime or "floor_means")
    elif regime is not None:
        state.regime = regime
    state.enabled = bool(value)


def food_allocation_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def _parameters(world) -> tuple[float, float]:
    from chronicler.tuning import get_override
    floor = float(get_override(world, "livelihoods.food.floor", FLOOR))
    share = float(get_override(world, "livelihoods.food.target_share", TARGET_SHARE))
    if not (0.0 < floor <= 1.0 and 0.0 < share <= 1.0):
        raise ValueError("livelihoods.food.floor and target_share must be in (0, 1]")
    return floor, share


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Phase 2 native alive counts from the turn's existing snapshot.

    Uses the snapshot Phase 2 already holds; it never requests another one,
    which could rebuild the native snapshot cache at a new point in the turn.
    """
    state = _state(world)
    counts = [0] * len(world.regions)
    from chronicler.war_requisition import enlisted_ids
    enlisted = set(enlisted_ids(world))
    if enlisted:
        rows = zip(snapshot.column("id").to_pylist(), snapshot.column("region").to_pylist(), strict=True)
        regions = (r for aid, r in rows if int(aid) not in enlisted)
    else:
        regions = snapshot.column("region").to_pylist()
    for r in regions:
        if 0 <= r < len(counts):
            counts[r] += 1
    state._phase2 = (world.turn, None, counts)
    return region_input


def finish_phase2(world, economy_result, agent_bridge, acc):
    """Record pre-release sufficiency before public granaries change it."""
    state = _state(world)
    phase2 = state._phase2
    if phase2 is None or phase2[0] != world.turn:
        raise RuntimeError("food allocation counts missing for this turn")
    pre = [float(economy_result.food_sufficiency[reg.name]) if reg.name in economy_result.food_sufficiency
           else math.nan for reg in world.regions]
    state._phase2 = (world.turn, pre, phase2[2])
    return []


def rollback_phase2(world) -> None:
    state = _state(world)
    if state is not None:
        state._phase2 = None


def before_agent_tick(world, agent_bridge, economy_result) -> None:
    state = _state(world)
    phase2 = state._phase2
    state._installed = None
    if phase2 is None or phase2[0] != world.turn or phase2[1] is None:
        state.counters["turns_unobserved"] = state.counters.get("turns_unobserved", 0) + 1
        return
    sim = agent_bridge._sim
    if not callable(getattr(sim, "set_food_allocation", None)):
        raise RuntimeError("food allocation requires a fresh native build with provisioning")
    floor, share = _parameters(world)
    _, pre, counts = phase2
    sim.set_food_allocation(world.turn, REGIMES.index(state.regime), floor, share, pre, counts)
    state._installed = (world.turn, [math.isnan(value) for value in pre])


def rollback_agent_tick(world, agent_bridge) -> None:
    """The agent tick raised: drop an allocation the tick never took."""
    state = _state(world)
    if getattr(state, "_installed", None) is not None:
        state._installed = state._phase2 = None
        agent_bridge._sim.cancel_food_allocation()


def after_agent_tick(world, agent_bridge) -> list:
    state = _state(world)
    sim = agent_bridge._sim
    installed, state._installed, state._phase2 = state._installed, None, None
    if installed is None:
        return []
    installed, unknown_pre = installed
    frame = sim.take_food_allocation_frame()
    if frame is None:
        # The tick never took it: drop it rather than let it leak a turn.
        sim.cancel_food_allocation()
        state.counters["turns_not_taken"] = state.counters.get("turns_not_taken", 0) + 1
        return []
    turn, regime, columns, rows, sample, dropped = frame
    if turn != installed or REGIMES[regime] != state.regime:
        raise RuntimeError("native food allocation receipts do not match the request")
    rows = [dict(zip(columns, row)) for row in rows]
    retail = _retail_regions(world)
    if retail:
        # Household retail (L6b) provisioned these regions this tick; its own
        # receipts close them (``household_retail.after_agent_tick``).
        rows = [r for r in rows if int(r["region"]) not in retail]
    for r in rows:
        if unknown_pre[int(r["region"])]:
            r["relief_available"] = r["relief_to_targeted"] = 0.0      # excluded from totals; unknown below
    totals = {key: sum(r[key] for r in rows) for key in (
        "alive", "rations_available", "relief_available", "allocated", "unallocated",
        "relief_to_targeted", "shortfall", "below_floor", "people_poorer_half",
        "shortfall_poorer_half", "people_richer_half", "shortfall_richer_half",
        "children", "shortfall_children")}
    for r in rows:
        if r["scarce"] and abs(r["allocated"] + r["unallocated"] - r["rations_available"]) > 1e-6 * max(1.0, r["rations_available"]):
            raise RuntimeError(f"food allocation does not close in region {int(r['region'])}")
    totals["scarce_regions"] = sum(1 for r in rows if r["scarce"])
    state.frame_turn = turn
    state.regions = [{k: (int(v) if k in ("region", "scarce", "phase2_alive", "alive", "households",
                                         "below_floor", "fully_fed", "people_poorer_half",
                                         "people_richer_half", "children") else round(v, 6))
                      for k, v in r.items()} for r in rows if r["scarce"]]
    for r in state.regions:
        if unknown_pre[r["region"]]:
            # Without the pre-release sufficiency the release share is unknown,
            # not zero (targeted relief then shares everything as market food).
            r["relief_available"] = r["relief_to_targeted"] = None
    totals = {k: round(v, 6) for k, v in totals.items()}
    totals["relief_unknown_regions"] = sum(1 for r in rows if r["scarce"] and unknown_pre[int(r["region"])])
    state.totals = totals
    scarce = {int(r["region"]) for r in rows if r["scarce"]}
    state.sample = [[aid, region, household, round(ration, 6), targeted]
                    for aid, region, household, ration, targeted in sample if region in scarce][:SNAPSHOT_SAMPLE]
    state.sample_dropped = dropped
    for key in ("shortfall", "allocated", "unallocated", "relief_to_targeted",
                "shortfall_poorer_half", "shortfall_richer_half", "shortfall_children"):
        state.counters[key] = round(state.counters.get(key, 0.0) + totals[key], 6)
    state.counters["allocated_turns"] = state.counters.get("allocated_turns", 0) + 1
    state.counters["scarce_region_turns"] = state.counters.get("scarce_region_turns", 0) + totals["scarce_regions"]
    return []


def _retail_regions(world) -> set[int]:
    if getattr(getattr(world, "livelihoods", None), "household_retail", None) is None:
        return set()
    from chronicler.household_retail import provisioned_regions
    return provisioned_regions(world)


def snapshot_summary(world) -> dict:
    state = _state(world)
    source = world.turn - 1
    observed = state.frame_turn == source
    return {
        "schema_version": 1, "stage": "L2", "regime": state.regime, "source_turn": source,
        # None: no allocation ran for this turn (unknown, not zero).
        "totals": dict(state.totals) if observed else None,
        "regions": list(state.regions) if observed else None,
        "sample": list(state.sample) if observed else None,
        "sample_columns": ["agent_id", "region", "household", "ration", "targeted"],
        "counters": dict(state.counters),
    }
