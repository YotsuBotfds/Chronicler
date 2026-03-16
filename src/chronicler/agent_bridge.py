"""Bridge between Python WorldState and Rust AgentSimulator."""
from __future__ import annotations
from typing import TYPE_CHECKING
import pyarrow as pa
from chronicler_agents import AgentSimulator

if TYPE_CHECKING:
    from chronicler.models import Event, WorldState

TERRAIN_MAP = {
    "plains": 0, "mountains": 1, "coast": 2,
    "forest": 3, "desert": 4, "tundra": 5,
}

def build_region_batch(world: WorldState) -> pa.RecordBatch:
    return pa.record_batch({
        "region_id": pa.array(range(len(world.regions)), type=pa.uint16()),
        "terrain": pa.array([TERRAIN_MAP[r.terrain] for r in world.regions], type=pa.uint8()),
        "carrying_capacity": pa.array([r.carrying_capacity for r in world.regions], type=pa.uint16()),
        "population": pa.array([r.population for r in world.regions], type=pa.uint16()),
        "soil": pa.array([r.ecology.soil for r in world.regions], type=pa.float32()),
        "water": pa.array([r.ecology.water for r in world.regions], type=pa.float32()),
        "forest_cover": pa.array([r.ecology.forest_cover for r in world.regions], type=pa.float32()),
    })

class AgentBridge:
    def __init__(self, world: WorldState, mode: str = "demographics-only"):
        self._sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
        self._mode = mode

    def tick(self, world: WorldState) -> list[Event]:
        self._sim.set_region_state(build_region_batch(world))
        _agent_events = self._sim.tick(world.turn)
        if self._mode == "demographics-only":
            self._apply_demographics_clamp(world)
        return []

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

    def get_snapshot(self): return self._sim.get_snapshot()
    def get_aggregates(self): return self._sim.get_aggregates()
