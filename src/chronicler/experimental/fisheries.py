"""Renewable fish stock accounting in reference-worker yield units.

An open local fishery replenishes toward carrying stock, then harvest removes
biomass. The catch limit is an accounting constraint, not a yield bonus.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from chronicler.models import Region, WorldState


class FisheryConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    enabled: bool = False
    reserve_turns: float = Field(default=8.0, ge=2.0, le=100.0, allow_inf_nan=False)
    recovery_rate: float = Field(default=0.04, ge=0.0, le=0.25, allow_inf_nan=False)
    harvest_fraction: float = Field(default=0.25, gt=0.0, le=0.5, allow_inf_nan=False)
    reference_workers: int = Field(default=200, ge=1, le=10000)


@dataclass(frozen=True)
class FisheryStep:
    stock: float
    recovery: float
    harvest: float
    capacity: float
    yield_per_worker: float


def step_fishery(stock: float, base_yield: float, potential_yield: float,
                 workers: float, config: FisheryConfig) -> FisheryStep:
    """Recover, then harvest. Stock/recovery/harvest are fractions of capacity.

    Effort is bounded to four reference workforces. Yield remains per-worker;
    biomass is measured in yield units per reference workforce (not fish kg).
    With no workers there is no harvest, but potential yield remains available.
    """
    if (not all(isfinite(v) for v in (stock, base_yield, potential_yield))
            or not 0.0 <= stock <= 1.0 or min(base_yield, potential_yield, workers) < 0):
        raise ValueError("fishery inputs must be finite, nonnegative; stock must be in [0, 1]")
    recovery = config.recovery_rate * (1.0 - stock)
    available = stock + recovery
    capacity = base_yield * config.reserve_turns
    effort = min(workers / config.reference_workers, 4.0)
    requested = potential_yield * effort
    harvest_units = min(requested, available * capacity * config.harvest_fraction)
    harvest = harvest_units / capacity if capacity > 0.0 else 0.0
    actual_yield = harvest_units / effort if effort > 0.0 else potential_yield
    return FisheryStep(available - harvest, recovery, harvest, capacity, actual_yield)


def apply_fishery_feedback(world: WorldState, region_yields: dict[str, list[float]]) -> None:
    """Shared ecology post-pass. Disabled runs do not read or mutate experiment state."""
    config = world.fishery_experiment
    if not config.enabled:
        return
    from chronicler.models import ResourceType

    from chronicler.economy import occupied_resource_slot_count

    # The split bridge's live snapshot precedes this turn's agent tick. Prefer
    # actual farmers there; pure-Python/off-mode uses the existing ecology proxy.
    worker_counts = [max(0, region.population // 5) for region in world.regions]
    bridge = getattr(world, "_agent_bridge", None)
    if bridge is not None:
        snapshot = bridge.get_snapshot()
        if snapshot is not None:
            worker_counts = [0] * len(world.regions)
            for rid, occupation in zip(snapshot.column("region").to_pylist(),
                                       snapshot.column("occupation").to_pylist()):
                if occupation == 0 and 0 <= rid < len(worker_counts):
                    worker_counts[rid] += 1

    for rid, region in enumerate(world.regions):
        yields = region_yields[region.name]
        for slot, rtype in enumerate(region.resource_types):
            if rtype != ResourceType.FISH:
                # A removed fish resource cannot leave stale stock in its slot.
                region.fishery_stocks[slot] = 1.0
                region.fishery_yield_ratios[slot] = 1.0
                region.fishery_catch_budgets[slot] = None
                continue
            potential = yields[slot]
            # Goods production splits farmer labor equally across occupied
            # slots; fishing effort uses the same share, so biomass is not
            # debited for labor that the economy assigns to other resources.
            workers = worker_counts[rid] / max(1, occupied_resource_slot_count(region.resource_types))
            result = step_fishery(region.fishery_stocks[slot],
                                  region.resource_base_yields[slot], potential, workers, config)
            region.fishery_stocks[slot] = result.stock
            region.fishery_catch_budgets[slot] = (
                result.harvest * result.capacity * config.reference_workers
            )
            yields[slot] = result.yield_per_worker
            region.fishery_yield_ratios[slot] = (
                min(1.0, result.yield_per_worker / potential) if potential > 0.0 else 0.0
            )
        region.resource_current_yields = list(yields)


def fishery_enabled(world: WorldState) -> bool:
    config = getattr(world, "fishery_experiment", None)
    return isinstance(config, FisheryConfig) and config.enabled


def catch_budget(world: WorldState, region: Region, slot: int = 0) -> float | None:
    if fishery_enabled(world):
        from chronicler.models import ResourceType
        if region.resource_types[slot] == ResourceType.FISH:
            # No prior catch means no production credit; enabling cannot create fish.
            return region.fishery_catch_budgets[slot] or 0.0
    return None


def require_fishery_runtime(world: WorldState, runtime) -> None:
    """Reject stale native binaries before an enabled turn mutates any state."""
    if fishery_enabled(world) and runtime is not None and not callable(
            getattr(runtime, "apply_fishery_yield_patch", None)):
        raise RuntimeError("fishery experiment requires a rebuilt native extension with catch patch support")


def economy_yield(world: WorldState, region: Region, slot: int = 0) -> float:
    """Per-worker goods yield for one slot's Phase 2 harvest.

    Reads the realized ``resource_current_yields`` preview (season, climate,
    ecology, suspension and mineral reserves; see
    ``ecology.refresh_resource_yields``). When the fishery experiment is
    enabled, fish slots also carry the lagged catch ratio; the separate catch
    budget caps their allocated output. Permanent yields are never overwritten.
    """
    value = region.resource_current_yields[slot]
    if fishery_enabled(world):
        from chronicler.models import ResourceType
        if region.resource_types[slot] == ResourceType.FISH:
            value *= region.fishery_yield_ratios[slot]
    return value
