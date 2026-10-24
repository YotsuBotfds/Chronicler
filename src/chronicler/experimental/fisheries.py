"""Renewable fish stock accounting in reference-worker yield units.

An open local fishery replenishes toward carrying stock, then harvest removes
biomass. The catch limit is an accounting constraint, not a yield bonus.

Worlds created by the CLI, batch and live entry points follow
``DEFAULT_ENABLED_FOR_NEW_WORLDS`` (``--fisheries`` / ``--no-fisheries``);
loaded, forked and caller-supplied worlds keep their saved
``WorldState.fishery_experiment``. See
docs/integration/fisheries-mutual-aid-promotion.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from chronicler.models import Region, WorldState


#: Default for worlds newly created by the CLI/batch/live entry points
#: (``--no-fisheries`` opts out; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = True

#: Reference workforce applied when a *new* world enables the fishery. The
#: class default (200) is kept so dormant configs serialize unchanged. With
#: recovery 0.04 and 8 reserve turns, a slot sustains about
#: ``recovery_rate * reserve_turns * reference_workers`` fishers at base yield:
#: 64 at 200, which no living-world region reaches (template coasts carry
#: 20-40 fishers), so the stock never constrained catch. 100 (about 32
#: fishers) lets the densest coasts overfish. [CALIBRATE]
NEW_WORLD_REFERENCE_WORKERS = 100

#: Narrated stock transitions (fractions of carrying stock). A slot collapses
#: below COLLAPSE_STOCK and is narrated as recovered once it is back at
#: RECOVERED_STOCK; the gap is hysteresis so a stock hovering at one threshold
#: does not repeat events.
COLLAPSE_STOCK = 0.25
RECOVERED_STOCK = 0.6


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

    from chronicler.ecology import goods_per_worker
    from chronicler.economy import PER_CAPITA_FOOD, food_first_slot_labor

    # The split bridge's live snapshot precedes this turn's agent tick. Prefer
    # actual farmers there; pure-Python/off-mode uses the existing ecology proxy.
    worker_counts = [max(0, region.population // 5) for region in world.regions]
    populations = [max(0, region.population) for region in world.regions]
    bridge = getattr(world, "_agent_bridge", None)
    if bridge is not None:
        snapshot = bridge.get_snapshot()
        if snapshot is not None:
            worker_counts = [0] * len(world.regions)
            populations = [0] * len(world.regions)
            for rid, occupation in zip(snapshot.column("region").to_pylist(),
                                       snapshot.column("occupation").to_pylist()):
                if 0 <= rid < len(worker_counts):
                    populations[rid] += 1
                    if occupation == 0:
                        worker_counts[rid] += 1

    for rid, region in enumerate(world.regions):
        yields = region_yields[region.name]
        # Goods production allocates farmer labor food-first across occupied
        # slots; fishing effort uses the same share, so biomass is not debited
        # for labor that the economy assigns to other resources. The split
        # compares goods yields with food demand, as the economy does.
        slot_workers = food_first_slot_labor(
            region.resource_types,
            [goods_per_worker(rt, y) for rt, y in zip(region.resource_types, yields)],
            worker_counts[rid],
            populations[rid] * PER_CAPITA_FOOD,
        )
        for slot, rtype in enumerate(region.resource_types):
            if rtype != ResourceType.FISH:
                # A removed fish resource cannot leave stale stock in its slot.
                region.fishery_stocks[slot] = 1.0
                region.fishery_yield_ratios[slot] = 1.0
                region.fishery_catch_budgets[slot] = None
                continue
            potential = yields[slot]
            workers = slot_workers[slot]
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


def fishery_stock_events(world: WorldState) -> list:
    """Collapse/recovery transitions after this tick's stock update.

    Reads the stocks ``apply_fishery_feedback`` just wrote and the persisted
    ``Region.fishery_collapsed`` memory; consumes no RNG and changes no yield.
    Disabled runs neither read nor mutate the memory.
    """
    if not fishery_enabled(world):
        return []
    from chronicler.models import Event, ResourceType

    events = []
    for region in world.regions:
        collapsed = set(region.fishery_collapsed or ())
        before = set(collapsed)
        for slot, rtype in enumerate(region.resource_types):
            if rtype != ResourceType.FISH:
                collapsed.discard(slot)  # removed fish resource: forget silently
                continue
            stock = region.fishery_stocks[slot]
            actors = [region.controller] if region.controller else []
            if slot not in collapsed and stock < COLLAPSE_STOCK:
                collapsed.add(slot)
                events.append(Event(
                    turn=world.turn, event_type="fishery_collapse", actors=actors,
                    description=(f"The fishing grounds of {region.name} collapse: years of heavy "
                                 f"fishing have left {stock:.0%} of the stock."),
                    importance=7,
                ))
            elif slot in collapsed and stock >= RECOVERED_STOCK:
                collapsed.discard(slot)
                events.append(Event(
                    turn=world.turn, event_type="fishery_recovery", actors=actors,
                    description=(f"Fish return to the waters of {region.name}; the stock has "
                                 f"recovered to {stock:.0%}."),
                    importance=6,
                ))
        if collapsed != before:
            region.fishery_collapsed = sorted(collapsed) or None
    return events


def set_fisheries_enabled(world: WorldState, enabled: bool, *, new_world: bool = False) -> None:
    """Switch the fishery on or off; a new world also gets its calibration.

    Only a world created in this run (``new_world``) receives
    ``NEW_WORLD_REFERENCE_WORKERS``; a loaded world keeps its saved
    parameters and only flips ``enabled``. Stocks, ratios and budgets are
    never touched here (disabling freezes them; re-enabling resumes them).
    """
    config = world.fishery_experiment
    if enabled and new_world:
        world.fishery_experiment = config.model_copy(
            update={"enabled": True, "reference_workers": NEW_WORLD_REFERENCE_WORKERS},
        )
    else:
        config.enabled = bool(enabled)


def fishery_enabled(world: WorldState) -> bool:
    config = getattr(world, "fishery_experiment", None)
    return isinstance(config, FisheryConfig) and config.enabled


def catch_budget(world: WorldState, region: Region, slot: int = 0) -> float | None:
    """The slot's production cap in goods: last tick's catch, if a fish slot.

    The stock model counts catch in M34 harvest-index units; the economy
    produces goods, so the budget is converted like the yield (see
    ``ecology.goods_per_worker``).
    """
    if fishery_enabled(world):
        from chronicler.models import ResourceType
        if region.resource_types[slot] == ResourceType.FISH:
            from chronicler.ecology import goods_per_worker
            # No prior catch means no production credit; enabling cannot create fish.
            return goods_per_worker(ResourceType.FISH, region.fishery_catch_budgets[slot] or 0.0)
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
    ``ecology.refresh_resource_yields``), converted from the M34 harvest index
    into goods per farmer (``ecology.goods_per_worker``). When the fishery
    experiment is enabled, fish slots also carry the lagged catch ratio; the
    separate catch budget caps their allocated output. Permanent yields are
    never overwritten.
    """
    from chronicler.ecology import goods_per_worker

    rtype = region.resource_types[slot]
    value = region.resource_current_yields[slot]
    if fishery_enabled(world):
        from chronicler.models import ResourceType
        if rtype == ResourceType.FISH:
            value *= region.fishery_yield_ratios[slot]
    return goods_per_worker(rtype, value)
