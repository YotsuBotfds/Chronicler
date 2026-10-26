"""Native checks of the population and entity corrections (real extension).

docs/integration/population-entities.md: the initial spawn makes exactly one
agent per person, and minerals are depleted by the ore the agent economy
actually produced (consumed by the next ecology tick, never reused).
"""
from __future__ import annotations

import pyarrow as pa
import pytest

from chronicler.agent_bridge import build_region_batch
from chronicler.columnar import pylist
from chronicler.economy import build_economy_region_input_batch
from chronicler.models import EMPTY_SLOT, Region, ResourceType, WorldState

pytestmark = pytest.mark.native


def _native():
    ca = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(ca, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")
    return ca


def _world(populations: list[int], **region_fields) -> WorldState:
    from chronicler.models import Civilization, Leader
    regions = [Region(name=f"R{k}", terrain="mountains", carrying_capacity=60, resources="mineral",
                      population=pop, controller="A", **region_fields)
               for k, pop in enumerate(populations)]
    civ = Civilization(name="A", population=sum(populations), military=30, economy=40,
                       culture=30, stability=50,
                       leader=Leader(name="Ruler", trait="cautious", reign_start=0),
                       regions=[r.name for r in regions])
    world = WorldState(name="T", seed=42, regions=regions, civilizations=[civ])
    world.agent_mode = "hybrid"
    return world


def _alive(sim) -> list[int]:
    pops = sim.get_region_populations()
    by_region = dict(zip(pylist(pops.column("region_id")), pylist(pops.column("alive_count"))))
    return [by_region.get(k, 0) for k in range(len(by_region))]


def test_initial_spawn_makes_one_agent_per_person():
    ca = _native()
    populations = [0, 1, 2, 5, 6, 7, 47, 100]
    world = _world(populations)
    sim = ca.AgentSimulator(num_regions=len(populations), seed=42)
    sim.set_region_state(build_region_batch(world))
    assert _alive(sim) == populations


ORE = int(ResourceType.ORE)


def _routes():
    return pa.record_batch({
        "origin_region_id": pa.array([], type=pa.uint16()),
        "dest_region_id": pa.array([], type=pa.uint16()),
        "is_river": pa.array([], type=pa.bool_()),
    })


def _mine_world():
    world = _world([60])
    region = world.regions[0]
    region.resource_types = [ORE, EMPTY_SLOT, EMPTY_SLOT]
    region.resource_base_yields = [1.0, 0.0, 0.0]
    region.resource_effective_yields = [1.0, 0.0, 0.0]
    region.resource_reserves = [1.0, 1.0, 1.0]
    region.resource_current_yields = [1.0, 0.0, 0.0]
    return world


def _economy(sim, world, labor_factor: float):
    batch = build_economy_region_input_batch(world)
    cols = {n: batch.column(n) for n in batch.schema.names}
    cols["farm_labor_factor"] = pa.array([labor_factor] * batch.num_rows, type=pa.float32())
    out = sim.tick_economy(pa.record_batch(cols), _routes(), 0, False, 1.0)
    return sum(pylist(pa.record_batch(out[0]).column("stockpile_ore")))


def _ecology(sim, turn: int) -> float:
    region_batch, _ = sim.tick_ecology(turn, 0, [False], [False])
    return pylist(pa.record_batch(region_batch).column("resource_reserve_0"))[0]


def test_a_mine_without_miners_keeps_its_reserves():
    ca = _native()
    world = _mine_world()
    sim = ca.AgentSimulator(num_regions=1, seed=42)
    sim.set_region_state(build_region_batch(world))
    reserves = []
    for turn in range(10):
        ore = _economy(sim, world, 0.0)    # no farm (or mine) labour at all
        assert ore == 0.0
        reserves.append(_ecology(sim, turn))
    assert reserves == [1.0] * 10


def test_ore_produced_depletes_and_is_consumed_once():
    ca = _native()
    world = _mine_world()
    sim = ca.AgentSimulator(num_regions=1, seed=42)
    sim.set_region_state(build_region_batch(world))
    assert _economy(sim, world, 1.0) > 0.0
    after_mining = _ecology(sim, 0)
    assert after_mining < 1.0
    # The output is consumed by that tick: an ecology tick without an
    # economy tick falls back to the labour proxy, never the old output.
    proxy = ca.AgentSimulator(num_regions=1, seed=42)
    proxy.set_region_state(build_region_batch(_mine_world()))
    proxy_loss = 1.0 - _ecology(proxy, 0)
    assert proxy_loss != pytest.approx(1.0 - after_mining, rel=1e-3)
    assert after_mining - _ecology(sim, 1) == pytest.approx(proxy_loss, rel=1e-3)
    # Half the labour, about half the ore and the depletion (the mine's own curve).
    full, half = (ca.AgentSimulator(num_regions=1, seed=42) for _ in range(2))
    for s in (full, half):
        s.set_region_state(build_region_batch(_mine_world()))
    ore_full, ore_half = _economy(full, world, 1.0), _economy(half, world, 0.5)
    loss_full, loss_half = 1.0 - _ecology(full, 0), 1.0 - _ecology(half, 0)
    assert ore_half < ore_full
    assert loss_half / loss_full == pytest.approx(ore_half / ore_full, rel=1e-3)


def test_the_off_mode_ecology_keeps_its_labour_proxy():
    ca = _native()
    if not isinstance(getattr(ca, "EcologySimulator", None), type):
        pytest.skip("requires the EcologySimulator")
    world = _mine_world()
    world.agent_mode = "off"
    eco = ca.EcologySimulator()
    eco.set_region_state(build_region_batch(world))
    region_batch, _ = eco.tick_ecology(0, 0, [False], [False])
    reserve = pylist(pa.record_batch(region_batch).column("resource_reserve_0"))[0]
    assert reserve < 1.0    # population / 5 workers, as before
