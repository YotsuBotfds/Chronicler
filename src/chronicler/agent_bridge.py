"""Bridge between Python WorldState and Rust AgentSimulator."""
from __future__ import annotations
import logging
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING
import pyarrow as pa
from chronicler_agents import AgentSimulator
from chronicler.demand_signals import DemandSignalManager
from chronicler.models import AgentEventRecord, CivShock
from chronicler.shadow import ShadowLogger

if TYPE_CHECKING:
    from chronicler.models import Event, WorldState

logger = logging.getLogger(__name__)

TERRAIN_MAP = {
    "plains": 0, "mountains": 1, "coast": 2,
    "forest": 3, "desert": 4, "tundra": 5,
}
FACTION_MAP = {"military": 0, "merchant": 1, "cultural": 2}


def build_region_batch(world: WorldState) -> pa.RecordBatch:
    """Build extended region state Arrow batch (M26: adds controller, adjacency, etc.)."""
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}

    adj_masks = []
    for r in world.regions:
        mask = 0
        for adj_name in r.adjacencies:
            if adj_name in region_name_to_idx:
                mask |= 1 << region_name_to_idx[adj_name]
        adj_masks.append(mask)

    contested_regions_set = set()
    for attacker, defender in world.active_wars:
        for r in world.regions:
            if r.controller == defender:
                contested_regions_set.add(r.name)

    return pa.record_batch({
        "region_id": pa.array(range(len(world.regions)), type=pa.uint16()),
        "terrain": pa.array([TERRAIN_MAP[r.terrain] for r in world.regions], type=pa.uint8()),
        "carrying_capacity": pa.array([r.carrying_capacity for r in world.regions], type=pa.uint16()),
        "population": pa.array([r.population for r in world.regions], type=pa.uint16()),
        "soil": pa.array([r.ecology.soil for r in world.regions], type=pa.float32()),
        "water": pa.array([r.ecology.water for r in world.regions], type=pa.float32()),
        "forest_cover": pa.array([r.ecology.forest_cover for r in world.regions], type=pa.float32()),
        "controller_civ": pa.array(
            [civ_name_to_id.get(r.controller, 255) if r.controller else 255 for r in world.regions],
            type=pa.uint8(),
        ),
        "adjacency_mask": pa.array(adj_masks, type=pa.uint32()),
        "trade_route_count": pa.array([0 for _ in world.regions], type=pa.uint8()),
        "is_contested": pa.array([r.name in contested_regions_set for r in world.regions], type=pa.bool_()),
    })


def build_signals(world: WorldState, shocks: list | None = None,
                  demands: dict | None = None) -> pa.RecordBatch:
    """Build civ-signals Arrow RecordBatch from current WorldState.

    Args:
        world: Current simulation state.
        shocks: Pre-summed shock values per civ (list[CivShock]).
        demands: Per-civ demand shifts (5 floats per civ), output of
            DemandSignalManager.tick().
    """
    from chronicler.factions import get_dominant_faction
    from chronicler.models import FactionType

    war_civs = set()
    for attacker, defender in world.active_wars:
        war_civs.add(attacker)
        war_civs.add(defender)

    civ_ids, stabilities, at_wars = [], [], []
    dom_factions, fac_mil, fac_mer, fac_cul = [], [], [], []

    # Shock / demand column builders
    shock_map = {s.civ_id: s for s in (shocks or [])}
    shock_stab, shock_eco, shock_mil, shock_cul = [], [], [], []
    ds_farmer, ds_soldier, ds_merchant, ds_scholar, ds_priest = [], [], [], [], []

    for i, civ in enumerate(world.civilizations):
        civ_ids.append(i)
        stabilities.append(min(civ.stability, 100))
        at_wars.append(civ.name in war_civs)
        dominant = get_dominant_faction(civ.factions)
        dom_factions.append(FACTION_MAP.get(dominant.value, 0))
        fac_mil.append(civ.factions.influence.get(FactionType.MILITARY, 0.33))
        fac_mer.append(civ.factions.influence.get(FactionType.MERCHANT, 0.33))
        fac_cul.append(civ.factions.influence.get(FactionType.CULTURAL, 0.34))

        # Per-civ shock values (default zeros via CivShock defaults)
        s = shock_map.get(i, CivShock(i))
        shock_stab.append(s.stability_shock)
        shock_eco.append(s.economy_shock)
        shock_mil.append(s.military_shock)
        shock_cul.append(s.culture_shock)

        # Per-civ demand shifts (5 occupation slots)
        d = (demands or {}).get(i, [0.0] * 5)
        ds_farmer.append(d[0])
        ds_soldier.append(d[1])
        ds_merchant.append(d[2])
        ds_scholar.append(d[3])
        ds_priest.append(d[4])

    return pa.record_batch({
        "civ_id": pa.array(civ_ids, type=pa.uint8()),
        "stability": pa.array(stabilities, type=pa.uint8()),
        "is_at_war": pa.array(at_wars, type=pa.bool_()),
        "dominant_faction": pa.array(dom_factions, type=pa.uint8()),
        "faction_military": pa.array(fac_mil, type=pa.float32()),
        "faction_merchant": pa.array(fac_mer, type=pa.float32()),
        "faction_cultural": pa.array(fac_cul, type=pa.float32()),
        "shock_stability": pa.array(shock_stab, type=pa.float32()),
        "shock_economy": pa.array(shock_eco, type=pa.float32()),
        "shock_military": pa.array(shock_mil, type=pa.float32()),
        "shock_culture": pa.array(shock_cul, type=pa.float32()),
        "demand_shift_farmer": pa.array(ds_farmer, type=pa.float32()),
        "demand_shift_soldier": pa.array(ds_soldier, type=pa.float32()),
        "demand_shift_merchant": pa.array(ds_merchant, type=pa.float32()),
        "demand_shift_scholar": pa.array(ds_scholar, type=pa.float32()),
        "demand_shift_priest": pa.array(ds_priest, type=pa.float32()),
    })


class AgentBridge:
    def __init__(self, world: WorldState, mode: str = "demographics-only",
                 shadow_output: Path | None = None):
        self._sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
        self._mode = mode
        self._event_window: deque = deque(maxlen=10)  # sliding window for event aggregation
        self._demand_manager = DemandSignalManager()
        self._shadow_logger: ShadowLogger | None = None
        if mode == "shadow" and shadow_output is not None:
            self._shadow_logger = ShadowLogger(shadow_output)

    def tick(self, world: WorldState, shocks=None, demands=None) -> list:
        self._sim.set_region_state(build_region_batch(world))
        signals = build_signals(world, shocks=shocks, demands=demands)
        agent_events = self._sim.tick(world.turn, signals)

        if self._mode == "hybrid":
            self._write_back(world)
            return []  # Event aggregation added in Task 13
        elif self._mode == "shadow":
            agent_aggs = self._sim.get_aggregates()
            if self._shadow_logger:
                self._shadow_logger.log_turn(world.turn, agent_aggs, world)
            return []
        elif self._mode == "demographics-only":
            self._apply_demographics_clamp(world)
            return []
        return []

    def _write_back(self, world: WorldState) -> None:
        """Write agent-derived stats to civ and region objects. Hybrid mode only."""
        aggs = self._sim.get_aggregates()
        region_pops = self._sim.get_region_populations()

        # Region populations from agent counts -- no clamp in hybrid mode
        pop_map = dict(zip(
            region_pops.column("region_id").to_pylist(),
            region_pops.column("alive_count").to_pylist(),
        ))
        for i, region in enumerate(world.regions):
            agent_pop = pop_map.get(i, 0)
            if agent_pop > region.carrying_capacity * 2.0:
                logger.warning(
                    "Region %d pop %d exceeds 2x capacity %d",
                    i, agent_pop, region.carrying_capacity,
                )
            region.population = agent_pop

        # Build region-name lookup for civ population sums
        region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}

        # Civ stats from aggregates
        civ_ids = aggs.column("civ_id").to_pylist()
        for row_idx, civ_id in enumerate(civ_ids):
            civ = world.civilizations[civ_id]
            # Sum population across regions owned by this civ (regions is list[str])
            civ.population = sum(
                world.regions[region_name_to_idx[rname]].population
                for rname in civ.regions
                if rname in region_name_to_idx
            )
            civ.military = aggs.column("military")[row_idx].as_py()
            civ.economy = aggs.column("economy")[row_idx].as_py()
            civ.culture = aggs.column("culture")[row_idx].as_py()
            civ.stability = aggs.column("stability")[row_idx].as_py()

    def _apply_demographics_clamp(self, world: WorldState) -> None:
        region_pops = self._sim.get_region_populations()
        pop_map = dict(zip(
            region_pops.column("region_id").to_pylist(),
            region_pops.column("alive_count").to_pylist(),
        ))
        for i, region in enumerate(world.regions):
            if region.controller is not None:
                agent_pop = pop_map.get(i, 0)
                region.population = min(agent_pop, int(region.carrying_capacity * 1.2))

    def reset(self) -> None:
        """Clear stateful data for batch mode reuse."""
        self._event_window.clear()
        self._demand_manager.reset()

    def close(self) -> None:
        if self._shadow_logger:
            self._shadow_logger.close()

    def get_snapshot(self): return self._sim.get_snapshot()
    def get_aggregates(self): return self._sim.get_aggregates()
