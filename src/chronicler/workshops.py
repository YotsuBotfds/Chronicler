"""L1 staffed public workshops (``--workshops``, default off).

L1A (this landing) is the payer-independent contract: site selection, native
crew eligibility and actual craft-input reporting. Funded operation (the
``operate`` mode: treasury-paid construction/upkeep and the crew's work
replacing the region's craft ceiling) lands with L1B and is refused here.

Sites. Up to four open cities of rank >= 1, one per region, admitted in a
deterministic order (rank, size, settlement id) as cities exist; a closed
site (its city fell or vanished) is archived with its date and reason.

Crews. Each Phase 2, before the native economy tick, the native planner
(``AgentSimulator.plan_workshop_crews``) resolves at most eight living adult
urban farmers resident in the site's settlement and region, excluding trips,
army rosters and existing work reservations. Each contributes the city's
already-diverted farming time ``1 - URBAN_FARM_LABOR[rank]``; the farm factor
is untouched, so nothing is subtracted twice. In observe mode the crew is
available, not employed: no work is allocated or realized.

Inputs. After the tick, ``take_craft_inputs`` gives the region's actual
per-good raw input to its craft conversion; receipts copy it with the region's
actual craft output and its legacy craft ceiling. A region total is never
attributed to a site share. Missing native observations are recorded as
unknown (None), not zero.
"""
from __future__ import annotations

from chronicler.workshops_state import (
    MAX_CLOSED, MAX_CREW, MAX_SITES, WorkshopReceipt, WorkshopSite, WorkshopState,
)

#: Goods in native slot order (economy.FIXED_GOODS); only raw materials are crafted.
_RAW_GOODS = ("timber", "ore")


class _Plan:
    def __init__(self, turn: int, rows: list[dict], ceilings: dict[int, float | None]):
        self.turn = turn
        self.rows = rows
        self.ceilings = ceilings


def _state(world) -> WorkshopState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "workshops", None) if container is not None else None


def set_workshops_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    mode = getattr(args, "workshop_mode", None) if args is not None else None
    state = _state(world)
    if value and (mode or (state.mode if state is not None else "operate")) == "operate":
        raise ValueError("--workshop-mode operate (funded workshops) lands with L1B; "
                         "use --workshop-mode observe")
    if state is None:
        world.livelihoods.workshops = state = WorkshopState(mode=mode or "observe")
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


def workshops_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "cities", None) is not None


def _diverted(rank: int) -> float:
    from chronicler.cities import URBAN_FARM_LABOR
    return 1.0 - URBAN_FARM_LABOR[max(0, min(rank, len(URBAN_FARM_LABOR) - 1))]


def _close(state: WorkshopState, site: WorkshopSite, turn: int, reason: str) -> None:
    site.status, site.closed_turn, site.closed_reason = "closed", turn, reason
    state.sites.remove(site)
    state.closed.append(site)
    del state.closed[:-MAX_CLOSED]
    state.counters[f"closed_{reason}"] = state.counters.get(f"closed_{reason}", 0) + 1


def refresh_sites(world, state: WorkshopState) -> dict[int, object]:
    """Close sites whose city is gone; admit new cities up to the cap.

    Returns the live City object of each open site, keyed by site id.
    """
    cities = {c.settlement_id: c for c in world.cities.cities}
    fallen = {getattr(f, "settlement_id", None) for f in getattr(world.cities, "fallen", [])}
    for site in list(state.sites):
        city = cities.get(site.settlement_id)
        if city is None:
            _close(state, site, world.turn, "city_fell" if site.settlement_id in fallen else "city_missing")
        elif city.region != site.region:
            _close(state, site, world.turn, "region_changed")
    taken = {s.region for s in state.sites}
    candidates = sorted((c for c in cities.values()
                         if c.rank >= 1 and c.region not in taken
                         and c.settlement_id not in {s.settlement_id for s in state.closed}),
                        key=lambda c: (-c.rank, -c.size, c.settlement_id))
    for city in candidates:
        if len(state.sites) >= MAX_SITES:
            break
        if city.region in taken:
            continue
        state.sites.append(WorkshopSite(site=state.next_site, region=city.region,
                                        settlement_id=city.settlement_id, city_name=city.name,
                                        selected_turn=world.turn))
        state.next_site += 1
        taken.add(city.region)
        state.counters["selected"] = state.counters.get("selected", 0) + 1
    return {s.site: cities[s.settlement_id] for s in state.sites}


def _enlisted(world) -> list[int]:
    armies = getattr(getattr(world, "war_state", None), "armies", [])
    return sorted({int(aid) for army in armies for aid, _ in army.roster})


def _column(region_input, name: str):
    names = region_input.schema.names
    if name not in names:
        return None
    return region_input.column(names.index(name)).to_pylist()


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    state = _state(world)
    if getattr(state, "_plan", None) is not None:
        raise RuntimeError("workshop plan already pending")
    sim = getattr(agent_bridge, "_sim", None)
    if sim is None or not callable(getattr(sim, "plan_workshop_crews", None)) \
            or not callable(getattr(sim, "take_craft_inputs", None)):
        raise RuntimeError("workshops require a fresh native build with workshop crews")
    cities = refresh_sites(world, state)
    requests = []
    for site in state.sites:
        rank = int(cities[site.site].rank)
        requests.append((site.site, site.region, site.settlement_id, float(_diverted(rank)), MAX_CREW))
    rows = []
    if requests:
        for row, (site_id, _r, _s, diverted, _m) in zip(
                sim.plan_workshop_crews(requests, _enlisted(world)), requests, strict=True):
            (site, region, settlement, resident, trip, army, assigned, eligible,
             crew, ages, work) = row
            rows.append(dict(site=site, region=region, settlement_id=settlement,
                             rank=int(cities[site_id].rank), diverted_fraction=diverted,
                             resident_adult_farmers=resident, excluded_trip=trip,
                             excluded_army=army, excluded_assigned=assigned, eligible=eligible,
                             crew=list(crew), crew_ages=list(ages), work_available=float(work)))
    ceilings_col = _column(region_input, "craft_raw_demand")
    ceilings = {s.region: (float(ceilings_col[s.region]) if ceilings_col is not None else None)
                for s in state.sites}
    # Drop any stale observation from an earlier tick before this one runs.
    sim.take_craft_inputs()
    state._plan = _Plan(world.turn, rows, ceilings)
    return region_input


def finish_phase2(world, economy_result, agent_bridge, acc):
    state = _state(world)
    plan = getattr(state, "_plan", None)
    if plan is None or plan.turn != world.turn:
        raise RuntimeError("workshop plan missing for this turn")
    inputs = agent_bridge._sim.take_craft_inputs()
    if inputs is not None and len(inputs) != len(world.regions):
        raise RuntimeError("native craft inputs do not match the region count")
    from chronicler.economy import FIXED_GOODS
    frame = []
    for row in plan.rows:
        name = world.regions[row["region"]].name
        region_input = None
        if inputs is not None:
            region_input = {g: float(inputs[row["region"]][FIXED_GOODS.index(g)]) for g in _RAW_GOODS}
        frame.append(WorkshopReceipt(
            turn=plan.turn, **row,
            legacy_craft_ceiling=plan.ceilings.get(row["region"]),
            region_craft_output=(float(economy_result.craft_output.get(name, 0.0))
                                 if inputs is not None else None),
            region_craft_input=region_input,
        ))
    state.frame = frame
    state.frame_turn = plan.turn
    state.counters["planned_turns"] = state.counters.get("planned_turns", 0) + 1
    state.counters["crew_available_turns"] = (state.counters.get("crew_available_turns", 0)
                                              + sum(len(r.crew) for r in frame))
    state._plan = None
    return []


def rollback_phase2(world) -> None:
    state = _state(world)
    if state is not None:
        state._plan = None


def snapshot_summary(world) -> dict:
    state = _state(world)
    source = world.turn - 1
    frame = [r.model_dump() for r in state.frame] if state.frame_turn == source else None
    return {
        "schema_version": 1, "stage": "L1A", "mode": state.mode, "source_turn": source,
        "sites": [s.model_dump() for s in state.sites],
        "closed": [s.model_dump() for s in state.closed],
        # None: no completed Phase 2 observation for this turn (unknown, not zero).
        "receipts": frame,
        "counters": dict(state.counters),
    }
