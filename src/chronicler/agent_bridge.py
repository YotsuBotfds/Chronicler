"""Bridge between Python WorldState and Rust AgentSimulator."""
from __future__ import annotations
from dataclasses import dataclass
import logging
from collections import Counter, deque
from itertools import repeat, starmap
from pathlib import Path
from typing import TYPE_CHECKING
import numpy as np
import pyarrow as pa
from chronicler.columnar import group_rows, ordered_counts, pylist
from chronicler.demand_signals import DemandSignalManager
from chronicler.ffi_constants import (
    MAX_CIV_RECORDS, MAX_NATIVE_REGIONS, TERRAIN_MAP, VALUE_EMPTY, VALUE_TO_ID,
    check_civ_capacity, river_ids_from_mask,
)
from chronicler.great_persons import _append_deed
from chronicler.history_index import history_index
from chronicler.leaders import _pick_name, strip_title, ALL_TRAITS
from chronicler.models import (
    NO_MIGRATION_DRIVER, AgentEventRecord, CivShock, Event, GreatPerson, migration_driver_name,
)
from chronicler.resources import get_season_step, get_season_id
from chronicler.shadow import ShadowLogger
from chronicler.utils import resolve_civ_faith_id

if TYPE_CHECKING:
    from chronicler.models import WorldState


def _load_agent_simulator_class():
    """Import the Rust AgentSimulator only when constructing an AgentBridge."""
    try:
        from chronicler_agents import AgentSimulator
    except ImportError as exc:
        raise RuntimeError(
            "chronicler_agents Rust extension is required for --agents modes. "
            "Build/install it from chronicler-agents with `maturin develop --release`."
        ) from exc
    if not isinstance(AgentSimulator, type):
        raise RuntimeError("chronicler_agents AgentSimulator is not a real native extension class")
    return AgentSimulator


logger = logging.getLogger(__name__)

# M58a: Fixed good slot ordering — mirrors economy.FIXED_GOODS (avoid circular import)
_FIXED_GOODS: tuple[str, ...] = (
    "grain", "fish", "salt", "timber", "ore", "botanicals", "precious", "exotic",
)
FACTION_MAP = {"military": 0, "merchant": 1, "cultural": 2, "clergy": 3}

EVENT_TYPE_MAP = {0: "death", 1: "rebellion", 2: "migration",
                  3: "occupation_switch", 4: "loyalty_flip", 5: "birth",
                  6: "dissolution"}
OCCUPATION_NAMES = {0: "farmers", 1: "soldiers", 2: "merchants", 3: "scholars", 4: "priests"}
ROLE_MAP = {0: "general", 1: "merchant", 2: "scientist", 3: "prophet", 4: "exile"}

# M48: Mule promotion constants [FROZEN M53 SOFT]
MULE_PROMOTION_PROBABILITY = 0.12  # [FROZEN M53 SOFT] raised from 0.07
MULE_MAPPING = {
    0: {"DEVELOP": 3.0, "TRADE": 2.0, "WAR": 0.3},        # Famine
    1: {"WAR": 3.0, "DIPLOMACY": 0.5},                      # Battle
    2: {"WAR": 3.0, "EXPAND": 2.0, "DIPLOMACY": 0.3},      # Conquest
    3: {"FUND_INSTABILITY": 3.0, "TRADE": 0.5},             # Persecution
    4: {"EXPAND": 3.0, "TRADE": 2.0},                       # Migration
    6: {"WAR": 2.5, "EXPAND": 2.0},                         # Victory
    9: {"DIPLOMACY": 3.0, "WAR": 0.3},                      # DeathOfKin
    10: {"INVEST_CULTURE": 3.0, "BUILD": 2.0},              # Conversion
    11: {"DIPLOMACY": 2.5, "INVEST_CULTURE": 2.0},          # Secession
}

SUMMARY_TEMPLATES = {
    # Without a recorded driver (extensions and files before it).
    "mass_migration": "{count} {occ_majority} fled {source_region} for {target_region}",
    "local_rebellion": "Rebellion erupted in {region} as {count} discontented {occ_majority} rose up",
    "demographic_crisis": "{region} lost {pct}% of its population over {window} turns",
    "occupation_shift": "{count} agents in {region} switched to {new_occupation}",
    "loyalty_cascade": "{count} residents of {region} shifted allegiance to {target_civ}",
    "economic_boom": "Economic boom in {region}: {count} workers switched to merchant trades over {window} turns",
    "brain_drain": "{count} scholars fled {region} over {window} turns",
}


# A mass migration's description by its dominant driver (the largest utility
# term of most of its moves, ``models.MIGRATION_DRIVER_NAMES``). The
# simulation decides the driver; the description only reads it.
MASS_MIGRATION_BY_DRIVER = {
    "frontier": "{count} {occ_majority} left {source_region} to settle {target_region}",
    "wage": "{count} {occ_majority} left {source_region} for work in {target_region}",
    "chain": "{count} {occ_majority} followed kin from {source_region} to {target_region}",
    "urban": "{count} {occ_majority} left {source_region} for the city in {target_region}",
    "famine_memory": "{count} {occ_majority} fled hunger in {source_region} for {target_region}",
    "opp_food": "{count} {occ_majority} fled hunger in {source_region} for {target_region}",
    "persecution": "{count} {occ_majority} fled persecution in {source_region} for {target_region}",
    "persecution_memory": "{count} {occ_majority} fled persecution in {source_region} for {target_region}",
    "battle_memory": "{count} {occ_majority} fled war in {source_region} for {target_region}",
    "conquest_memory": "{count} {occ_majority} fled war in {source_region} for {target_region}",
    "low_satisfaction": "{count} {occ_majority} left hardship in {source_region} for {target_region}",
    "safety_need": "{count} {occ_majority} left hardship in {source_region} for {target_region}",
    "material_need": "{count} {occ_majority} left hardship in {source_region} for {target_region}",
    "spiritual_need": "{count} {occ_majority} left hardship in {source_region} for {target_region}",
    "opp_satisfaction": "{count} {occ_majority} left {source_region} for better prospects in {target_region}",
    "opp_capacity": "{count} {occ_majority} left {source_region} for better prospects in {target_region}",
    "opp_river": "{count} {occ_majority} left {source_region} for better prospects in {target_region}",
    "opp_news": "{count} {occ_majority} left {source_region} for better prospects in {target_region}",
}


def dominant_migration_driver(events) -> str | None:
    """The driver most of these migration records carry (ties: the lower
    term index); None when none carries one."""
    counts = Counter(e.migration_driver for e in events
                     if migration_driver_name(e.migration_driver) is not None)
    if not counts:
        return None
    code = min(counts, key=lambda c: (-counts[c], c))
    return migration_driver_name(code)


VALUE_PERSONALITY_MAP = {
    "Honor":     ( 0.15,  0.0,   0.0),
    "Freedom":   ( 0.15,  0.0,   0.0),
    "Cunning":   ( 0.0,   0.15,  0.0),
    "Knowledge": ( 0.0,   0.15,  0.0),
    "Tradition": ( 0.0,   0.0,   0.15),
    "Order":     ( 0.0,   0.0,   0.15),
}

DOMAIN_PERSONALITY_MAP = {
    "warfare":     ( 0.10,  0.0,   0.0),
    "expansion":   ( 0.10,  0.0,   0.0),
    "commerce":    ( 0.0,   0.10,  0.0),
    "maritime":    ( 0.0,   0.10,  0.0),
    "scholarship": ( 0.0,   0.0,   0.10),
    "faith":       ( 0.0,   0.0,   0.10),
    "diplomacy":   ( 0.0,   0.05,  0.05),
}


@dataclass(frozen=True, slots=True)
class AgentMemoryRecord:
    event_type: int
    source_civ: int
    turn: int
    intensity: int
    decay_factor: int
    is_legacy: bool = False


def _merge_counts(dicts) -> dict:
    """Sum count dicts in order; keys keep their first-seen order."""
    merged: dict = {}
    for counts in dicts:
        for key, value in counts.items():
            merged[key] = merged.get(key, 0) + value
    return merged


def compute_gini(wealth_array: np.ndarray) -> float:
    """Gini coefficient from a 1D array of non-negative values."""
    sorted_w = np.sort(np.asarray(wealth_array, dtype=np.float64))
    n = len(sorted_w)
    if n == 0:
        return 0.0
    if not np.isfinite(sorted_w).all():
        return float("nan")
    scale = sorted_w[-1]
    if scale == 0:
        return 0.0
    # Each sorted gap separates i poorer and n-i richer residents. Summing
    # these nonnegative pairwise differences avoids cancellation near equality.
    # Scale before reductions to avoid overflow, but subtract before scaling to
    # preserve adjacent-float gaps that normalizing each value could round away.
    total = (sorted_w / scale).sum()
    index = np.arange(1, n, dtype=np.float64)
    gaps = np.diff(sorted_w) / scale
    return float(np.dot(index * (n - index), gaps) / (n * total))


def civ_personality_mean(
    values: list[str], domains: list[str],
) -> tuple[float, float, float]:
    """Compute personality mean from civ cultural values and domains."""
    mean = [0.0, 0.0, 0.0]
    for v in values:
        if v in VALUE_PERSONALITY_MAP:
            for i in range(3):
                mean[i] += VALUE_PERSONALITY_MAP[v][i]
    for d in domains:
        for key, contrib in DOMAIN_PERSONALITY_MAP.items():
            if key in d.lower():
                for i in range(3):
                    mean[i] += contrib[i]
    return tuple(max(-0.3, min(0.3, m)) for m in mean)


def _merge_civ_shocks(shocks: list[CivShock] | None) -> dict[int, CivShock]:
    """Merge duplicate civ shock entries into one unit-range shock per civ."""
    merged: dict[int, CivShock] = {}
    for shock in shocks or []:
        current = merged.get(shock.civ_id)
        if current is None:
            merged[shock.civ_id] = CivShock(
                civ_id=shock.civ_id,
                stability_shock=shock.stability_shock,
                economy_shock=shock.economy_shock,
                military_shock=shock.military_shock,
                culture_shock=shock.culture_shock,
            )
            continue
        current.stability_shock = max(-1.0, min(1.0, current.stability_shock + shock.stability_shock))
        current.economy_shock = max(-1.0, min(1.0, current.economy_shock + shock.economy_shock))
        current.military_shock = max(-1.0, min(1.0, current.military_shock + shock.military_shock))
        current.culture_shock = max(-1.0, min(1.0, current.culture_shock + shock.culture_shock))
    return merged


def _get_yield(region, slot: int) -> float:
    """Read current-turn yield from the Region model (set by ecology write-back)."""
    yields = getattr(region, "resource_current_yields", None)
    if yields is not None and slot < len(yields):
        return yields[slot]
    return 0.0


def _has_infra(region, infra_type_name: str) -> bool:
    """Check whether a region has an active infrastructure of the given type."""
    from chronicler.models import InfrastructureType
    target = getattr(InfrastructureType, infra_type_name, None)
    if target is None:
        return False
    return any(i.active and i.type == target for i in region.infrastructure)


def _get_active_focus(region, world) -> int:
    """Return the controlling civ's tech focus as u8, 0 = None."""
    if region.controller is None:
        return 0
    civ_by_name = getattr(world, "civ_map", None)
    if not isinstance(civ_by_name, dict):
        civ_by_name = {c.name: c for c in world.civilizations}
    civ = civ_by_name.get(region.controller)
    if civ is None or not civ.active_focus:
        return 0
    # Map TechFocus string values to sequential u8 IDs (1-indexed, 0 = None)
    TECH_FOCUS_MAP = {
        "navigation": 1, "metallurgy": 2, "agriculture": 3,
        "fortification": 4, "commerce": 5, "scholarship": 6,
        "exploration": 7, "banking": 8, "printing": 9,
        "mechanization": 10, "railways": 11, "naval_power": 12,
        "networks": 13, "surveillance": 14, "media": 15,
    }
    return TECH_FOCUS_MAP.get(civ.active_focus, 0)


def _get_suspension_for_slot(region, slot: int) -> bool:
    """Check whether the given resource slot is currently suspended."""
    # resource_suspensions is dict[int, int] keyed by resource_type enum int,
    # but we need suspension status by slot index.
    if slot >= len(region.resource_types):
        return False
    rtype = region.resource_types[slot]
    if rtype == 255:  # no resource in this slot
        return False
    return region.resource_suspensions.get(rtype, 0) > 0


def _decode_agent_memory_row(row) -> AgentMemoryRecord:
    if len(row) == 5:
        return AgentMemoryRecord(
            event_type=row[0],
            source_civ=row[1],
            turn=row[2],
            intensity=row[3],
            decay_factor=row[4],
            is_legacy=False,
        )
    if len(row) == 6:
        return AgentMemoryRecord(
            event_type=row[0],
            source_civ=row[1],
            turn=row[2],
            intensity=row[3],
            decay_factor=row[4],
            is_legacy=bool(row[5]),
        )
    raise ValueError(f"Unexpected agent memory row shape: {row}")


def _get_agent_memory_records(sim, agent_id: int) -> list[AgentMemoryRecord]:
    raw = sim.get_agent_memories(agent_id) or []
    return [_decode_agent_memory_row(row) for row in raw]


def _validated_civ_signal(
    civ_id: int,
    field_name: str,
    value: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Validate a free-form civ f32 signal before it crosses into Rust."""
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f"{field_name} for civ {civ_id} must be finite, got {value!r}")
    if minimum is not None and value < minimum:
        raise ValueError(
            f"{field_name} for civ {civ_id} must be >= {minimum}, got {value}"
        )
    if maximum is not None and value > maximum:
        raise ValueError(
            f"{field_name} for civ {civ_id} must be <= {maximum}, got {value}"
        )
    return value


def _require_snapshot_pylist(snapshot: pa.RecordBatch, field_name: str) -> list:
    """Read a required snapshot column as a Python list."""
    if snapshot is None:
        raise ValueError("snapshot is unavailable")
    if field_name not in snapshot.schema.names:
        raise KeyError(f"snapshot missing required column {field_name!r}")
    return pylist(snapshot.column(field_name))


def _require_snapshot_numpy(snapshot: pa.RecordBatch, field_name: str) -> np.ndarray:
    """Read a required snapshot column as a NumPy array."""
    if snapshot is None:
        raise ValueError("snapshot is unavailable")
    if field_name not in snapshot.schema.names:
        raise KeyError(f"snapshot missing required column {field_name!r}")
    return snapshot.column(field_name).to_numpy()


def _null_free(snapshot, field_names) -> bool:
    """True when every named column exists and has no null cell.

    Columnar fast paths require this; the native snapshot schema is non-null.
    Other batches keep the row-by-row paths and their None semantics.
    """
    if snapshot is None:
        return False
    try:
        names = snapshot.schema.names
        return all(name in names and snapshot.column(name).null_count == 0 for name in field_names)
    except AttributeError:
        return False


def _city_route_graph(world: WorldState, batch):
    """``--cities``: cities an enemy besieges or occupies are cut off from the
    merchant graph (``cities.merchant_route_graph``); unchanged otherwise."""
    from chronicler.cities_state import cities_on
    if not cities_on(world):
        return batch
    from chronicler.cities import merchant_route_graph
    return merchant_route_graph(world, batch)


_MARKET_CATEGORIES: tuple[str, ...] = ("food", "raw_material", "luxury")


def _market_columns(world: WorldState, economy_result) -> dict[str, pa.Array]:
    """``market_demand_<category>`` and ``market_supply_<category>`` per region:
    the native economy's demand and post-trade supply (0 without a result).
    The merchant planner prices every good from them (``merchant::market_price``)."""
    columns = {}
    for prefix, attr in (("market_demand", "market_demand"), ("market_supply", "market_supply")):
        values = getattr(economy_result, attr, None) or {}
        for c, cat in enumerate(_MARKET_CATEGORIES):
            columns[f"{prefix}_{cat}"] = pa.array(
                [float(values[r.name][c]) if r.name in values else 0.0 for r in world.regions],
                type=pa.float32(),
            )
    return columns


def _send_movement_table(world: WorldState, bridge) -> None:
    """Agent movements (switch on only): this tick's movement table."""
    from chronicler.agent_movements_state import agent_movements_on
    if agent_movements_on(world):
        from chronicler.agent_movements import send_to_native
        send_to_native(world, bridge)


def build_region_batch(world: WorldState, economy_result=None) -> pa.RecordBatch:
    """Build extended region state Arrow batch (M26: adds controller, adjacency, etc.)."""
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    civ_by_name = getattr(world, "civ_map", None)
    if not isinstance(civ_by_name, dict):
        civ_by_name = {c.name: c for c in world.civilizations}
    civ_index_by_name = getattr(world, "civ_index_map", None)
    if not isinstance(civ_index_by_name, dict):
        civ_index_by_name = {c.name: i for i, c in enumerate(world.civilizations)}
    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}
    if len(world.regions) > MAX_NATIVE_REGIONS:
        raise ValueError(
            f"build_region_batch supports at most {MAX_NATIVE_REGIONS} regions "
            "(region ids are uint16)"
        )
    check_civ_capacity(world)

    # Geography 2.0: sorted neighbour/river id lists replace the former uint32
    # bitmasks (which capped worlds at 32 regions). Ascending order matches
    # the old bit walk, so <=32-region worlds tick identically.
    adjacency_lists = [
        sorted({region_name_to_idx[a] for a in r.adjacencies if a in region_name_to_idx})
        for r in world.regions
    ]
    river_lists = [river_ids_from_mask(r.river_mask) for r in world.regions]

    contested_regions_set = set()
    if getattr(world, "campaigns_enabled", False):
        # M60: only regions that actually see armies, battles or occupation.
        from chronicler.war.runtime import contested_region_names
        contested_regions_set = contested_region_names(world)
    else:
        for attacker, defender in world.active_wars:
            for r in world.regions:
                if r.controller == defender:
                    contested_regions_set.add(r.name)

    def _controller_values(region):
        """Denormalize controller civ's cultural values into per-region columns."""
        if region.controller is None:
            return [VALUE_EMPTY, VALUE_EMPTY, VALUE_EMPTY]
        ctrl_civ = civ_by_name.get(region.controller)
        if ctrl_civ is None:
            return [VALUE_EMPTY, VALUE_EMPTY, VALUE_EMPTY]
        vals = [VALUE_TO_ID.get(v, VALUE_EMPTY) for v in ctrl_civ.values[:3]]
        while len(vals) < 3:
            vals.append(VALUE_EMPTY)
        return vals

    # M37: Build initial_belief per region before the batch dict
    initial_belief_arr = []
    for region in world.regions:
        civ_name = region.controller
        if civ_name and world.belief_registry:
            civ_idx = civ_index_by_name.get(civ_name)
            if civ_idx is not None:
                initial_belief_arr.append(
                    resolve_civ_faith_id(
                        civ_by_name[civ_name],
                        world.belief_registry,
                        civ_idx=civ_idx,
                    )
                )
            else:
                initial_belief_arr.append(0xFF)
        else:
            initial_belief_arr.append(0xFF)

    def _has_temple(region, world):
        from chronicler.models import InfrastructureType
        controller_name = region.controller
        if controller_name is None:
            return False
        controller = civ_by_name.get(controller_name)
        if controller is None:
            return False
        cmf = getattr(controller, 'civ_majority_faith', -1)
        _temples_type = getattr(InfrastructureType, 'TEMPLES', None)
        if _temples_type is None:
            return False
        for infra in region.infrastructure:
            if (infra.active and infra.type == _temples_type
                    and getattr(infra, 'faith_id', -1) == cmf and cmf >= 0):
                return True
        return False

    # Read culture investment flags into locals, then clear (one-turn signal)
    culture_investment_vals = [getattr(r, '_culture_investment_active', False) for r in world.regions]
    for r in world.regions:
        if hasattr(r, '_culture_investment_active'):
            del r._culture_investment_active

    # Read schism values into locals, then clear (one-turn signals)
    schism_from_vals = [r.schism_convert_from for r in world.regions]
    schism_to_vals = [r.schism_convert_to for r in world.regions]
    for r in world.regions:
        r.schism_convert_from = 0xFF
        r.schism_convert_to = 0xFF

    # M48: Read per-region memory transient signals into locals, then clear
    controller_changed_vals = [getattr(r, '_controller_changed_this_turn', False) for r in world.regions]
    war_won_vals = [getattr(r, '_war_won_this_turn', False) for r in world.regions]
    seceded_vals = [getattr(r, '_seceded_this_turn', False) for r in world.regions]
    catastrophe_death_vals = [
        max(0, min(int(getattr(r, '_catastrophe_deaths_this_turn', 0) or 0), 0xFFFF))
        for r in world.regions
    ]
    for r in world.regions:
        r._controller_changed_this_turn = False
        r._war_won_this_turn = False
        r._seceded_this_turn = False
        r._catastrophe_deaths_this_turn = 0

    # M55a: is_capital — any alive civ has this region as capital
    alive_civs = [c for c in world.civilizations if c.regions]
    is_capital_flags = [
        any(c.capital_region == r.name for c in alive_civs)
        for r in world.regions
    ]

    # M55a: temple_prestige — max prestige of any active temple in the region
    from chronicler.models import InfrastructureType
    temple_prestiges = []
    for r in world.regions:
        max_prest = 0.0
        for inf in r.infrastructure:
            if inf.type == InfrastructureType.TEMPLES and inf.active:
                max_prest = max(max_prest, float(getattr(inf, 'temple_prestige', 0) or 0))
        temple_prestiges.append(max_prest)

    columns = {
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
        "adjacency": pa.array(adjacency_lists, type=pa.list_(pa.uint16())),
        "trade_route_count": pa.array(
            [economy_result.trade_route_counts.get(r.name, 0) if economy_result else 0
             for r in world.regions], type=pa.uint8(),
        ),
        "is_contested": pa.array([r.name in contested_regions_set for r in world.regions], type=pa.bool_()),
        # M34: Resource state
        "resource_type_0": pa.array([r.resource_types[0] for r in world.regions], type=pa.uint8()),
        "resource_type_1": pa.array([r.resource_types[1] for r in world.regions], type=pa.uint8()),
        "resource_type_2": pa.array([r.resource_types[2] for r in world.regions], type=pa.uint8()),
        "resource_yield_0": pa.array([_get_yield(r, 0) for r in world.regions], type=pa.float32()),
        "resource_yield_1": pa.array([_get_yield(r, 1) for r in world.regions], type=pa.float32()),
        "resource_yield_2": pa.array([_get_yield(r, 2) for r in world.regions], type=pa.float32()),
        "resource_reserve_0": pa.array([r.resource_reserves[0] for r in world.regions], type=pa.float32()),
        "resource_reserve_1": pa.array([r.resource_reserves[1] for r in world.regions], type=pa.float32()),
        "resource_reserve_2": pa.array([r.resource_reserves[2] for r in world.regions], type=pa.float32()),
        # M54a: Ecology schema — full-sync inputs
        "disease_baseline": pa.array([r.disease_baseline for r in world.regions], type=pa.float32()),
        "capacity_modifier": pa.array([r.capacity_modifier for r in world.regions], type=pa.float32()),
        "resource_base_yield_0": pa.array([r.resource_base_yields[0] for r in world.regions], type=pa.float32()),
        "resource_base_yield_1": pa.array([r.resource_base_yields[1] for r in world.regions], type=pa.float32()),
        "resource_base_yield_2": pa.array([r.resource_base_yields[2] for r in world.regions], type=pa.float32()),
        "resource_effective_yield_0": pa.array([r.resource_effective_yields[0] for r in world.regions], type=pa.float32()),
        "resource_effective_yield_1": pa.array([r.resource_effective_yields[1] for r in world.regions], type=pa.float32()),
        "resource_effective_yield_2": pa.array([r.resource_effective_yields[2] for r in world.regions], type=pa.float32()),
        "resource_suspension_0": pa.array([_get_suspension_for_slot(r, 0) for r in world.regions], type=pa.bool_()),
        "resource_suspension_1": pa.array([_get_suspension_for_slot(r, 1) for r in world.regions], type=pa.bool_()),
        "resource_suspension_2": pa.array([_get_suspension_for_slot(r, 2) for r in world.regions], type=pa.bool_()),
        "has_irrigation": pa.array([_has_infra(r, "IRRIGATION") for r in world.regions], type=pa.bool_()),
        "has_mines": pa.array([_has_infra(r, "MINES") for r in world.regions], type=pa.bool_()),
        "active_focus": pa.array([_get_active_focus(r, world) for r in world.regions], type=pa.uint8()),
        "prev_turn_water": pa.array([r.prev_turn_water for r in world.regions], type=pa.float32()),
        "soil_pressure_streak": pa.array([r.soil_pressure_streak for r in world.regions], type=pa.int32()),
        "overextraction_streak_0": pa.array([r.overextraction_streaks.get(0, 0) for r in world.regions], type=pa.int32()),
        "overextraction_streak_1": pa.array([r.overextraction_streaks.get(1, 0) for r in world.regions], type=pa.int32()),
        "overextraction_streak_2": pa.array([r.overextraction_streaks.get(2, 0) for r in world.regions], type=pa.int32()),
        "season": pa.array([get_season_step(world.turn) for _ in world.regions], type=pa.uint8()),
        "season_id": pa.array([get_season_id(world.turn) for _ in world.regions], type=pa.uint8()),
        # M35a rivers: ids of the rivers each region lies on (from river_mask).
        "rivers": pa.array(river_lists, type=pa.list_(pa.uint16())),
        # M35b: Endemic disease severity
        "endemic_severity": pa.array([r.endemic_severity for r in world.regions], type=pa.float32()),
        # M36: Cultural identity signals
        "culture_investment_active": pa.array(culture_investment_vals, type=pa.bool_()),
        "controller_values_0": pa.array(
            [_controller_values(r)[0] for r in world.regions], type=pa.uint8(),
        ),
        "controller_values_1": pa.array(
            [_controller_values(r)[1] for r in world.regions], type=pa.uint8(),
        ),
        "controller_values_2": pa.array(
            [_controller_values(r)[2] for r in world.regions], type=pa.uint8(),
        ),
        # M37: Conversion signals
        "conversion_rate": pa.array(
            [r.conversion_rate_signal for r in world.regions], type=pa.float32(),
        ),
        "conversion_target_belief": pa.array(
            [r.conversion_target_signal for r in world.regions], type=pa.uint8(),
        ),
        "conquest_conversion_active": pa.array(
            [r.conquest_conversion_active for r in world.regions], type=pa.bool_(),
        ),
        "majority_belief": pa.array(
            [r.majority_belief for r in world.regions], type=pa.uint8(),
        ),
        "initial_belief": pa.array(initial_belief_arr, type=pa.uint8()),
        "has_temple": pa.array([_has_temple(r, world) for r in world.regions], type=pa.bool_()),
        "persecution_intensity": pa.array(
            [r.persecution_intensity for r in world.regions], type=pa.float32()
        ),
        # The faith the intensity was measured against (255 = none): the tick
        # persecutes everyone outside it, not everyone outside the majority.
        "persecuting_faith": pa.array(
            [0xFF if r.persecuting_faith is None else r.persecuting_faith for r in world.regions],
            type=pa.uint8(),
        ),
        "schism_convert_from": pa.array(schism_from_vals, type=pa.uint8()),
        "schism_convert_to": pa.array(schism_to_vals, type=pa.uint8()),
        # M42: Goods economy signals
        "farmer_income_modifier": pa.array(
            [economy_result.farmer_income_modifiers.get(r.name, 1.0) if economy_result else 1.0
             for r in world.regions], type=pa.float32(),
        ),
        "food_sufficiency": pa.array(
            [economy_result.food_sufficiency.get(r.name, 1.0) if economy_result else 1.0
             for r in world.regions], type=pa.float32(),
        ),
        # Hunger: the severe-shortage run up to the previous turn (Phase 9
        # extends it after this batch is built; the native demographic tick
        # adds the current turn itself).
        "food_severe_turns": pa.array(
            [min(0xFFFF, r.food_severe_turns or 0) for r in world.regions], type=pa.uint16(),
        ),
        "merchant_margin": pa.array(
            [economy_result.merchant_margins.get(r.name, 0.0) if economy_result else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        # M58b: Route planning reads oracle margin in hybrid mode when available,
        # while satisfaction keeps using realized merchant_margin.
        "merchant_route_margin": pa.array(
            [
                (
                    economy_result.oracle_imports.get(r.name, {}).get(
                        "margin",
                        economy_result.merchant_margins.get(r.name, 0.0),
                    )
                    if economy_result
                    else 0.0
                )
                for r in world.regions
            ],
            type=pa.float32(),
        ),
        "merchant_trade_income": pa.array(
            [economy_result.merchant_trade_incomes.get(r.name, 0.0) if economy_result else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        # Merchant routing (2026-10): the economy's demand and post-trade
        # supply per category, the planner's market prices (0 = no market).
        **_market_columns(world, economy_result),
        # M48: Per-region transient memory signals
        "controller_changed_this_turn": pa.array(controller_changed_vals, type=pa.bool_()),
        "war_won_this_turn": pa.array(war_won_vals, type=pa.bool_()),
        "seceded_this_turn": pa.array(seceded_vals, type=pa.bool_()),
        "catastrophe_deaths_this_turn": pa.array(catastrophe_death_vals, type=pa.uint16()),
        # M55a: Spatial substrate signals
        "is_capital": pa.array(is_capital_flags, type=pa.bool_()),
        "temple_prestige": pa.array(temple_prestiges, type=pa.float32()),
        # M58a: Per-good stockpile levels for merchant cargo availability
        # Slot ordering matches economy.FIXED_GOODS:
        #   0=grain, 1=fish, 2=salt, 3=timber, 4=ore, 5=botanicals, 6=precious, 7=exotic
        **{
            f"stockpile_{g}": pa.array(
                [r.stockpile.goods.get(good_name, 0.0) if r.stockpile else 0.0
                 for r in world.regions],
                type=pa.float32(),
            )
            for g, good_name in enumerate(_FIXED_GOODS)
        },
    }
    from chronicler.climate import climate_trend_share, region_harvest_shocks
    if climate_trend_share(world) < 1.0:
        # Regional climate: this turn's harvest shock of each region (crop
        # loss of its bad harvest year; without the column Rust reads 0).
        columns["harvest_shock"] = pa.array(region_harvest_shocks(world), type=pa.float32())
    farm_productivity = getattr(economy_result, "farm_productivity", None) if economy_result else None
    if farm_productivity:
        # Diminishing returns to farm labour: output per farmer against constant
        # returns scales farmer income (without the column Rust reads 1.0).
        columns["farm_productivity"] = pa.array(
            [farm_productivity.get(r.name, 1.0) for r in world.regions], type=pa.float32(),
        )
    if world.geography is not None:
        # Geography 2.0: latitude-band climate exposure for this turn's phase
        # (template worlds omit the column; Rust then uses 1.0).
        from chronicler.climate import get_climate_phase
        from chronicler.geography import climate_exposure
        phase = get_climate_phase(world.turn, world.climate_config)
        columns["climate_exposure"] = pa.array(
            [climate_exposure(r.latitude_band, phase) for r in world.regions], type=pa.float32(),
        )
    from chronicler.cities_state import cities_on
    if cities_on(world):
        # --cities: each region's draw on its hinterland (the Rust urban
        # driver), recomputed from persisted city state for every batch;
        # without the column Rust reads 0.
        from chronicler.cities import region_pulls
        columns["city_pull"] = pa.array(region_pulls(world), type=pa.float32())
    return pa.record_batch(columns)


def build_region_postpass_patch_batch(world: WorldState) -> pa.RecordBatch:
    """Build a narrow post-pass patch batch for Rust after Python ecology post-processing.

    Side-effect free. Must not clear one-turn signals.
    Schema: region_id(u16), population(u16), soil(f32), water(f32),
            forest_cover(f32), terrain(u8), carrying_capacity(u16).
    """
    return pa.record_batch({
        "region_id": pa.array(range(len(world.regions)), type=pa.uint16()),
        "population": pa.array([r.population for r in world.regions], type=pa.uint16()),
        "soil": pa.array([r.ecology.soil for r in world.regions], type=pa.float32()),
        "water": pa.array([r.ecology.water for r in world.regions], type=pa.float32()),
        "forest_cover": pa.array([r.ecology.forest_cover for r in world.regions], type=pa.float32()),
        "terrain": pa.array([TERRAIN_MAP[r.terrain] for r in world.regions], type=pa.uint8()),
        "carrying_capacity": pa.array([r.carrying_capacity for r in world.regions], type=pa.uint16()),
    })


def build_settlement_batch(world: WorldState) -> pa.RecordBatch:
    """Build settlement footprint Arrow batch for Rust-side grid construction.

    Includes ACTIVE and DISSOLVING settlements. Excludes CANDIDATE and DISSOLVED.
    Sorted by (region_id, settlement_id, cell_y, cell_x).
    """
    from chronicler.models import SettlementStatus

    if world.next_settlement_id > 65535:
        raise ValueError(
            f"next_settlement_id ({world.next_settlement_id}) exceeds u16 max 65535"
        )

    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}
    rows: list[tuple[int, int, int, int]] = []

    for region in world.regions:
        region_id = region_name_to_idx[region.name]
        for settlement in region.settlements:
            if settlement.status not in (SettlementStatus.ACTIVE, SettlementStatus.DISSOLVING):
                continue
            for cell_x, cell_y in settlement.footprint_cells:
                rows.append((region_id, settlement.settlement_id, cell_y, cell_x))

    # Deterministic sort: (region_id, settlement_id, cell_y, cell_x)
    rows.sort()

    if not rows:
        return pa.RecordBatch.from_pydict(
            {
                "region_id": pa.array([], type=pa.uint16()),
                "settlement_id": pa.array([], type=pa.uint16()),
                "cell_x": pa.array([], type=pa.uint8()),
                "cell_y": pa.array([], type=pa.uint8()),
            }
        )

    region_ids, settlement_ids, cell_ys, cell_xs = zip(*rows)
    return pa.RecordBatch.from_pydict(
        {
            "region_id": pa.array(region_ids, type=pa.uint16()),
            "settlement_id": pa.array(settlement_ids, type=pa.uint16()),
            "cell_x": pa.array(cell_xs, type=pa.uint8()),
            "cell_y": pa.array(cell_ys, type=pa.uint8()),
        }
    )


def build_signals(world: WorldState, shocks: list | None = None,
                  demands: dict | None = None,
                  conquered: dict[int, bool] | None = None,
                  gini_by_civ: dict[int, float] | None = None,
                  economy_result=None) -> pa.RecordBatch:
    """Build civ-signals Arrow RecordBatch from current WorldState.

    Args:
        world: Current simulation state.
        shocks: Civ shock entries for the current tick. Duplicate civ ids are
            merged and saturated into one unit-range row per civ.
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
    dom_factions, fac_mil, fac_mer, fac_cul, fac_cle = [], [], [], [], []

    # Shock / demand column builders
    shock_map = _merge_civ_shocks(shocks)
    shock_stab, shock_eco, shock_mil, shock_cul = [], [], [], []
    ds_farmer, ds_soldier, ds_merchant, ds_scholar, ds_priest = [], [], [], [], []
    mean_bold, mean_ambi, mean_ltrait = [], [], []
    conquered_flags = []
    gini_vals = []
    priest_tithe_shares = []

    from chronicler.tuning import get_multiplier, K_CULTURAL_DRIFT_SPEED, K_RELIGION_INTENSITY
    n_civs = len(world.civilizations)

    for i, civ in enumerate(world.civilizations):
        civ_ids.append(i)
        stabilities.append(min(civ.stability, 100))
        at_wars.append(civ.name in war_civs)
        dominant = get_dominant_faction(civ.factions)
        dom_factions.append(FACTION_MAP.get(dominant.value, 0))
        fac_mil.append(_validated_civ_signal(
            i, "faction_military",
            civ.factions.influence.get(FactionType.MILITARY, 0.33),
            minimum=0.0, maximum=1.0,
        ))
        fac_mer.append(_validated_civ_signal(
            i, "faction_merchant",
            civ.factions.influence.get(FactionType.MERCHANT, 0.33),
            minimum=0.0, maximum=1.0,
        ))
        fac_cul.append(_validated_civ_signal(
            i, "faction_cultural",
            civ.factions.influence.get(FactionType.CULTURAL, 0.34),
            minimum=0.0, maximum=1.0,
        ))
        fac_cle.append(_validated_civ_signal(
            i, "faction_clergy",
            civ.factions.influence.get(FactionType.CLERGY, 0.08),
            minimum=0.0, maximum=1.0,
        ))

        # Per-civ shock values (default zeros via CivShock defaults)
        s = shock_map.get(i, CivShock(i))
        shock_stab.append(_validated_civ_signal(
            i, "shock_stability", s.stability_shock, minimum=-1.0, maximum=1.0,
        ))
        shock_eco.append(_validated_civ_signal(
            i, "shock_economy", s.economy_shock, minimum=-1.0, maximum=1.0,
        ))
        shock_mil.append(_validated_civ_signal(
            i, "shock_military", s.military_shock, minimum=-1.0, maximum=1.0,
        ))
        shock_cul.append(_validated_civ_signal(
            i, "shock_culture", s.culture_shock, minimum=-1.0, maximum=1.0,
        ))

        # Per-civ demand shifts (5 occupation slots)
        d = (demands or {}).get(i, [0.0] * 5)
        ds_farmer.append(_validated_civ_signal(i, "demand_shift_farmer", d[0]))
        ds_soldier.append(_validated_civ_signal(i, "demand_shift_soldier", d[1]))
        ds_merchant.append(_validated_civ_signal(i, "demand_shift_merchant", d[2]))
        ds_scholar.append(_validated_civ_signal(i, "demand_shift_scholar", d[3]))
        ds_priest.append(_validated_civ_signal(i, "demand_shift_priest", d[4]))

        civ_values = getattr(civ, 'values', [])
        civ_domains = getattr(civ, 'domains', [])
        pm = civ_personality_mean(civ_values, civ_domains)
        mean_bold.append(_validated_civ_signal(
            i, "mean_boldness", pm[0], minimum=-0.3, maximum=0.3,
        ))
        mean_ambi.append(_validated_civ_signal(
            i, "mean_ambition", pm[1], minimum=-0.3, maximum=0.3,
        ))
        mean_ltrait.append(_validated_civ_signal(
            i, "mean_loyalty_trait", pm[2], minimum=-0.3, maximum=0.3,
        ))
        conquered_flags.append((conquered or {}).get(i, False))
        gini_vals.append(_validated_civ_signal(
            i, "gini_coefficient", (gini_by_civ or {}).get(i, 0.0),
            minimum=0.0, maximum=1.0,
        ))
        priest_tithe_shares.append(
            _validated_civ_signal(
                i,
                "priest_tithe_share",
                (economy_result.priest_tithe_shares.get(i, 0.0) if economy_result else 0.0),
                minimum=0.0,
            )
        )

    cultural_drift_multiplier = _validated_civ_signal(
        -1,
        "cultural_drift_multiplier",
        get_multiplier(world, K_CULTURAL_DRIFT_SPEED),
        minimum=0.0,
    )
    religion_intensity_multiplier = _validated_civ_signal(
        -1,
        "religion_intensity_multiplier",
        get_multiplier(world, K_RELIGION_INTENSITY),
        minimum=0.0,
    )

    return pa.record_batch({
        "civ_id": pa.array(civ_ids, type=pa.uint8()),
        "stability": pa.array(stabilities, type=pa.uint8()),
        "is_at_war": pa.array(at_wars, type=pa.bool_()),
        "dominant_faction": pa.array(dom_factions, type=pa.uint8()),
        "faction_military": pa.array(fac_mil, type=pa.float32()),
        "faction_merchant": pa.array(fac_mer, type=pa.float32()),
        "faction_cultural": pa.array(fac_cul, type=pa.float32()),
        "faction_clergy": pa.array(fac_cle, type=pa.float32()),
        "shock_stability": pa.array(shock_stab, type=pa.float32()),
        "shock_economy": pa.array(shock_eco, type=pa.float32()),
        "shock_military": pa.array(shock_mil, type=pa.float32()),
        "shock_culture": pa.array(shock_cul, type=pa.float32()),
        "demand_shift_farmer": pa.array(ds_farmer, type=pa.float32()),
        "demand_shift_soldier": pa.array(ds_soldier, type=pa.float32()),
        "demand_shift_merchant": pa.array(ds_merchant, type=pa.float32()),
        "demand_shift_scholar": pa.array(ds_scholar, type=pa.float32()),
        "demand_shift_priest": pa.array(ds_priest, type=pa.float32()),
        "mean_boldness": pa.array(mean_bold, type=pa.float32()),
        "mean_ambition": pa.array(mean_ambi, type=pa.float32()),
        "mean_loyalty_trait": pa.array(mean_ltrait, type=pa.float32()),
        "conquered_this_turn": pa.array(conquered_flags, type=pa.bool_()),
        "gini_coefficient": pa.array(gini_vals, type=pa.float32()),
        "priest_tithe_share": pa.array(priest_tithe_shares, type=pa.float32()),
        "cultural_drift_multiplier": pa.array(
            [cultural_drift_multiplier] * n_civs, type=pa.float32(),
        ),
        "religion_intensity_multiplier": pa.array(
            [religion_intensity_multiplier] * n_civs, type=pa.float32(),
        ),
    })


def configure_ecology_runtime(simulator, world: "WorldState") -> None:
    """Wire river topology and ecology config onto a Rust simulator.

    Works for both AgentSimulator and EcologySimulator — both expose
    set_river_topology() and set_ecology_config() with identical signatures.

    Reads tuning overrides from world.tuning_overrides; falls back to
    EcologyConfig::default() values when no override is present.
    """
    from chronicler.tuning import get_override

    # --- River topology ---
    if world.rivers:
        region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}
        river_paths = []
        for river in world.rivers:
            path_indices = [region_name_to_idx[rn] for rn in river.path if rn in region_name_to_idx]
            if path_indices:
                river_paths.append(path_indices)
        simulator.set_river_topology(river_paths)

    # --- Ecology config (tuning YAML → Rust EcologyConfig) ---
    # Each field falls back to the same default as Rust EcologyConfig::default().
    simulator.set_ecology_config(
        soil_degradation=get_override(world, "ecology.soil_degradation_rate", 0.005),
        soil_recovery=get_override(world, "ecology.soil_recovery_rate", 0.05),
        mine_soil_degradation=get_override(world, "ecology.mine_soil_degradation_rate", 0.03),
        soil_recovery_pop_ratio=get_override(world, "ecology.soil_recovery_pop_ratio", 0.75),
        agriculture_soil_bonus=get_override(world, "ecology.agriculture_soil_bonus", 0.02),
        metallurgy_mine_reduction=get_override(world, "ecology.metallurgy_mine_reduction", 0.5),
        mechanization_mine_mult=get_override(world, "ecology.mechanization_mine_multiplier", 2.0),
        soil_pressure_threshold=get_override(world, "ecology.soil_pressure_threshold", 0.7),
        soil_pressure_streak_limit=int(get_override(world, "ecology.soil_pressure_streak_limit", 30)),
        soil_pressure_degradation_mult=get_override(world, "ecology.soil_pressure_degradation_multiplier", 2.0),
        water_drought=get_override(world, "ecology.water_drought_rate", 0.04),
        water_recovery=get_override(world, "ecology.water_recovery_rate", 0.03),
        irrigation_water_bonus=get_override(world, "ecology.irrigation_water_bonus", 0.03),
        irrigation_drought_mult=get_override(world, "ecology.irrigation_drought_multiplier", 1.5),
        cooling_water_loss=get_override(world, "ecology.cooling_water_loss", 0.02),
        warming_tundra_water_gain=get_override(world, "ecology.warming_tundra_water_gain", 0.05),
        water_factor_denominator=get_override(world, "ecology.water_factor_denominator", 0.5),
        forest_clearing=get_override(world, "ecology.forest_clearing_rate", 0.02),
        forest_regrowth=get_override(world, "ecology.forest_regrowth_rate", 0.01),
        cooling_forest_damage=get_override(world, "ecology.cooling_forest_damage_rate", 0.01),
        forest_pop_ratio=get_override(world, "ecology.forest_pop_ratio", 0.5),
        forest_regrowth_water_gate=get_override(world, "ecology.forest_regrowth_water_gate", 0.3),
        cross_effect_forest_soil=get_override(world, "ecology.cross_effect_forest_soil_bonus", 0.01),
        cross_effect_forest_threshold=get_override(world, "ecology.cross_effect_forest_threshold", 0.5),
        disease_severity_cap=get_override(world, "ecology.disease_severity_cap", 0.15),
        disease_decay_rate=get_override(world, "ecology.disease_decay_rate", 0.25),
        flare_overcrowding_threshold=get_override(world, "ecology.flare_overcrowding_threshold", 0.8),
        flare_overcrowding_spike=get_override(world, "ecology.flare_overcrowding_spike", 0.04),
        flare_army_spike=get_override(world, "ecology.flare_army_spike", 0.03),
        flare_water_spike=get_override(world, "ecology.flare_water_spike", 0.02),
        flare_season_spike=get_override(world, "ecology.flare_season_spike", 0.02),
        depletion_rate=get_override(world, "ecology.depletion_rate", 0.009),
        exhausted_trickle_fraction=get_override(world, "ecology.exhausted_trickle_fraction", 0.04),
        reserve_ramp_threshold=get_override(world, "ecology.reserve_ramp_threshold", 0.25),
        resource_abundance_multiplier=get_override(world, "multiplier.resource_abundance", 1.0),
        overextraction_streak_limit=int(get_override(world, "ecology.overextraction_streak_limit", 35)),
        overextraction_yield_penalty=get_override(world, "ecology.overextraction_yield_penalty", 0.10),
        workers_per_yield_unit=int(get_override(world, "ecology.workers_per_yield_unit", 200)),
        deforestation_threshold=get_override(world, "ecology.deforestation_threshold", 0.2),
        deforestation_water_loss=get_override(world, "ecology.deforestation_water_loss", 0.05),
    )
    # Regional climate (2026-10): the trend share and the water a harvest
    # shock takes. Not sent at share 1.0 (the native defaults: global schedule).
    from chronicler.climate import climate_trend_share, harvest_shock_water_loss
    trend = climate_trend_share(world)
    if trend < 1.0:
        simulator.set_climate_config(trend, harvest_shock_water_loss(world, trend))


# Native agent-scale modes (see chronicler-agents/src/scale.rs). "exact" is the
# byte-identical reference; "fast" bounds per-agent work in dense regions.
AGENT_SCALE_MODES = ("exact", "fast")


def configure_economy_runtime(simulator, world: "WorldState") -> None:
    """Wire economy config onto a Rust AgentSimulator.

    Reads tuning overrides from world.tuning_overrides; falls back to
    EconomyConfig::default() values when no override is present.
    """
    from chronicler.tuning import get_override
    from chronicler.economy import (
        BASE_PRICE, PER_CAPITA_FOOD, RAW_MATERIAL_PER_SOLDIER,
        LUXURY_PER_WEALTHY_AGENT, LUXURY_DEMAND_THRESHOLD,
        CARRY_PER_MERCHANT, FARMER_INCOME_MODIFIER_FLOOR,
        FARMER_INCOME_MODIFIER_CAP, MERCHANT_MARGIN_NORMALIZER,
        TAX_RATE, TRADE_DEPENDENCY_THRESHOLD, PER_GOOD_CAP_FACTOR,
        SALT_PRESERVATION_FACTOR, MAX_PRESERVATION,
    )
    simulator.set_economy_config(
        base_price=get_override(world, "economy.base_price", BASE_PRICE),
        per_capita_food=get_override(world, "economy.per_capita_food", PER_CAPITA_FOOD),
        raw_material_per_soldier=get_override(world, "economy.raw_material_per_soldier", RAW_MATERIAL_PER_SOLDIER),
        luxury_per_wealthy_agent=get_override(world, "economy.luxury_per_wealthy_agent", LUXURY_PER_WEALTHY_AGENT),
        luxury_demand_threshold=get_override(world, "economy.luxury_demand_threshold", LUXURY_DEMAND_THRESHOLD),
        carry_per_merchant=get_override(world, "economy.carry_per_merchant", CARRY_PER_MERCHANT),
        farmer_income_modifier_floor=get_override(world, "economy.farmer_income_modifier_floor", FARMER_INCOME_MODIFIER_FLOOR),
        farmer_income_modifier_cap=get_override(world, "economy.farmer_income_modifier_cap", FARMER_INCOME_MODIFIER_CAP),
        merchant_margin_normalizer=get_override(world, "economy.merchant_margin_normalizer", MERCHANT_MARGIN_NORMALIZER),
        tax_rate=get_override(world, "economy.tax_rate", TAX_RATE),
        trade_dependency_threshold=get_override(world, "economy.trade_dependency_threshold", TRADE_DEPENDENCY_THRESHOLD),
        per_good_cap_factor=get_override(world, "economy.per_good_cap_factor", PER_GOOD_CAP_FACTOR),
        salt_preservation_factor=get_override(world, "economy.salt_preservation_factor", SALT_PRESERVATION_FACTOR),
        max_preservation=get_override(world, "economy.max_preservation", MAX_PRESERVATION),
        tatonnement_max_passes=int(get_override(world, "economy.tatonnement_max_passes", 3)),
        tatonnement_damping=get_override(world, "economy.tatonnement_damping", 0.2),
        tatonnement_convergence=get_override(world, "economy.tatonnement_convergence", 0.01),
        tatonnement_price_clamp_lo=get_override(world, "economy.tatonnement_price_clamp_lo", 0.5),
        tatonnement_price_clamp_hi=get_override(world, "economy.tatonnement_price_clamp_hi", 2.0),
    )
    configure_merchant_cargo(simulator, world)


def configure_merchant_cargo(simulator, world: "WorldState") -> None:
    """Bulk trade: send the merchant cargo configuration when a tuning key
    overrides it (the native defaults are ``economy.MERCHANT_CARGO``)."""
    from chronicler.economy import MERCHANT_CARGO
    from chronicler.tuning import (
        K_CARGO_FILL, K_LAND_CARGO_CAP, K_RIVER_CARGO_CAP, K_SEA_CARGO_CAP,
    )
    keys = (K_LAND_CARGO_CAP, K_RIVER_CARGO_CAP, K_SEA_CARGO_CAP, K_CARGO_FILL)
    overrides = getattr(world, "tuning_overrides", None) or {}
    if not any(k in overrides for k in keys):
        return
    land, river, sea, fill = (float(overrides.get(k, MERCHANT_CARGO[i])) for i, k in enumerate(keys))
    simulator.set_merchant_cargo_config(land, river, sea, bool(fill))


class AgentBridge:
    def __init__(self, world: WorldState, mode: str = "demographics-only",
                 shadow_output: Path | None = None,
                 validation_sidecar: bool = False,
                 output_dir: Path | None = None,
                 relationship_stats: bool = False,
                 agent_scale_mode: str = "exact"):
        if agent_scale_mode not in AGENT_SCALE_MODES:
            raise ValueError(
                f"agent_scale_mode must be one of {AGENT_SCALE_MODES}, got {agent_scale_mode!r}"
            )
        AgentSimulator = _load_agent_simulator_class()
        self._sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
        # Exact mode is the native default; only a non-default mode is sent,
        # so exact runs make exactly the calls they always made.
        if agent_scale_mode != "exact":
            if not hasattr(self._sim, "set_agent_scale_mode"):
                raise RuntimeError(
                    "the installed chronicler_agents extension predates agent scale modes; "
                    "rebuild it to use --agent-scale-mode fast"
                )
            self._sim.set_agent_scale_mode(agent_scale_mode)
        self.agent_scale_mode = agent_scale_mode
        self._mode = mode
        world._agent_bridge = self
        # M54a: Wire river topology and ecology config from tuning overrides
        configure_ecology_runtime(self._sim, world)
        # M54b: Wire economy config from tuning overrides
        configure_economy_runtime(self._sim, world)
        # M58b: Enable hybrid economy mode so tick_economy consumes delivery buffer
        self._sim.set_hybrid_economy_mode(mode == "hybrid")
        # M54c: Wire politics config from tuning overrides
        from chronicler.politics import configure_politics_runtime
        configure_politics_runtime(self._sim, world)
        # Prime the simulator once at bridge construction so the first Phase 2
        # economy tick sees the live world population rather than an empty pool.
        self._sim.set_region_state(build_region_batch(world))
        # Keep 20 turns so economic_boom aggregation can actually use its 20-turn horizon.
        self._event_window: deque = deque(maxlen=20)  # sliding window for event aggregation
        self._demand_manager = DemandSignalManager()
        self._shadow_logger: ShadowLogger | None = None
        if mode == "shadow" and shadow_output is not None:
            self._shadow_logger = ShadowLogger(shadow_output)
        self.named_agents: dict[int, str] = {}  # agent_id → character name
        self.gp_by_agent_id: dict[int, GreatPerson] = {}  # M39: agent_id → GreatPerson
        from chronicler.dynasties import DynastyRegistry
        self.dynasty_registry = DynastyRegistry()
        self._pending_dynasty_events: list = []
        self._origin_regions: dict[int, int] = {}  # agent_id → origin_region (for exile_return)
        self._departure_turns: dict[int, int] = {}  # agent_id → turn they left origin_region
        self.displacement_by_region: dict[int, float] = {}  # region_id → fraction displaced
        self._gini_by_civ: dict[int, float] = {}  # M41: per-civ Gini from last tick
        self._wealth_stats: dict[int, dict] = {}  # M41: per-civ wealth stats from last tick
        self._economy_result = None  # M42: economy result for signal wiring
        self.rust_owns_formation = True  # M50b: Rust owns formation in agent modes
        # M53: Validation sidecar
        self._sidecar = None
        if validation_sidecar and output_dir is not None:
            from chronicler.sidecar import SidecarWriter
            self._sidecar = SidecarWriter(output_dir)
        # M53: Relationship stats collection
        self._collect_rel_stats = relationship_stats
        self._relationship_stats_history: list = []
        # M57b: Household stats collection (always in agent modes)
        self._household_stats_history: list = []
        # M58a: Merchant trip stats collection
        self._merchant_trip_stats_history: list = []
        # M59a: Knowledge stats collection (always in agent modes)
        self._knowledge_stats_history: list = []
        # Agent movements: a fresh pool is re-seeded from the saved members once.
        self._movements_seeded = False

    def set_economy_result(self, result):
        """Store M42 economy result for signal wiring."""
        self._economy_result = result

    def _resolve_polity_civ_ids(
        self,
        world: "WorldState",
        region_ids: list[int],
        fallback_civ_ids: list[int],
    ) -> list[int]:
        """Resolve per-agent polity ids from current region control with affinity fallback."""
        name_to_id = {civ.name: idx for idx, civ in enumerate(world.civilizations)}
        resolved: list[int] = []
        for region_id, fallback_civ_id in zip(region_ids, fallback_civ_ids):
            controller_id = None
            region_idx = int(region_id)
            if 0 <= region_idx < len(world.regions):
                controller_name = world.regions[region_idx].controller
                if controller_name is not None:
                    controller_id = name_to_id.get(controller_name)
            resolved.append(controller_id if controller_id is not None else int(fallback_civ_id))
        return resolved

    def _resolve_polity_civ_id_array(
        self, world: "WorldState", region_ids: np.ndarray, fallback_civ_ids: np.ndarray,
    ) -> np.ndarray:
        """``_resolve_polity_civ_ids`` over integer arrays (same ids)."""
        name_to_id = {civ.name: idx for idx, civ in enumerate(world.civilizations)}
        controller_ids = np.full(len(world.regions) + 1, -1, dtype=np.int64)
        for idx, region in enumerate(world.regions):
            if region.controller is not None:
                controller_id = name_to_id.get(region.controller)
                if controller_id is not None:
                    controller_ids[idx] = controller_id
        regions = np.asarray(region_ids, dtype=np.int64)
        in_range = (regions >= 0) & (regions < len(world.regions))
        # Out-of-range regions read the trailing -1 (no controller).
        controller = controller_ids[np.where(in_range, regions, len(world.regions))]
        return np.where(controller >= 0, controller, np.asarray(fallback_civ_ids, dtype=np.int64))

    def _refresh_snapshot_metrics(self, world: "WorldState") -> None:
        """Update displacement, Gini, and wealth stats from the current snapshot."""
        try:
            snap = self._sim.get_snapshot()
        except (AttributeError, KeyError, TypeError, ValueError):
            logger.exception("Failed to compute displacement/Gini/wealth stats from snapshot")
            return
        self._post_tick_snapshot = (world.turn, snap)
        if _null_free(snap, ("region", "displacement_turn", "wealth", "civ_affinity", "occupation")):
            try:
                self._refresh_snapshot_metrics_columnar(world, snap)
            except (AttributeError, KeyError, TypeError, ValueError):
                logger.exception("Failed to compute displacement/Gini/wealth stats from snapshot")
            return
        self._refresh_snapshot_metrics_rows(world, snap)

    def _refresh_snapshot_metrics_columnar(self, world: "WorldState", snap) -> None:
        """Columnar ``_refresh_snapshot_metrics_rows`` for null-free snapshots.

        Same dict key orders (regions by first appearance, civs ascending) and
        the same per-civ wealth arrays in row order, so every NumPy reduction
        and the Gini see identical inputs.
        """
        regions = np.asarray(_require_snapshot_numpy(snap, "region"), dtype=np.int64)
        displaced = np.asarray(_require_snapshot_numpy(snap, "displacement_turn")) > 0
        self.displacement_by_region = {}
        for region, counts in ordered_counts(regions, displaced).items():
            # Keys in order of first appearance; counts[1] = displaced rows.
            total = counts[0] + counts[1]
            self.displacement_by_region[region] = counts[1] / total if total > 0 else 0.0

        if "wealth" not in snap.schema.names:
            return

        wealth_col = _require_snapshot_numpy(snap, "wealth")
        civ_col = self._resolve_polity_civ_id_array(
            world, regions, np.asarray(_require_snapshot_numpy(snap, "civ_affinity"), dtype=np.int64),
        )
        occ_col = _require_snapshot_numpy(snap, "occupation")
        occ_names = ["farmer", "soldier", "merchant", "scholar", "priest"]
        # Rows of each civ in row order, as the boolean masks selected them.
        groups = group_rows(civ_col)
        new_gini: dict[int, float] = {}
        for civ_id, rows in groups:
            new_gini[civ_id] = compute_gini(wealth_col[rows])
        stats: dict[int, dict] = {}
        for civ_id, rows in groups:
            civ_wealth = wealth_col[rows]
            civ_occ = occ_col[rows]
            wealth_by_occ = {}
            for occ_idx, name in enumerate(occ_names):
                occ_mask = civ_occ == occ_idx
                if occ_mask.any():
                    wealth_by_occ[name] = float(np.mean(civ_wealth[occ_mask]))
            stats[civ_id] = {
                "gini": new_gini.get(civ_id, 0.0),
                "mean": float(np.mean(civ_wealth)),
                "median": float(np.median(civ_wealth)),
                "std": float(np.std(civ_wealth)),
                "by_occupation": wealth_by_occ,
            }
        self._gini_by_civ = new_gini
        self._wealth_stats = stats

    def _refresh_snapshot_metrics_rows(self, world: "WorldState", snap) -> None:
        """Row-by-row metrics; kept for snapshots with null cells."""
        try:
            regions_col = _require_snapshot_pylist(snap, "region")
            disp_col = _require_snapshot_pylist(snap, "displacement_turn")
            region_totals = Counter(regions_col)
            region_displaced: Counter = Counter()
            for r, d in zip(regions_col, disp_col):
                if d > 0:
                    region_displaced[r] += 1
            self.displacement_by_region = {
                r: region_displaced[r] / total if total > 0 else 0.0
                for r, total in region_totals.items()
            }

            if "wealth" not in snap.schema.names:
                return

            wealth_col = _require_snapshot_numpy(snap, "wealth")
            civ_col = np.array(
                self._resolve_polity_civ_ids(
                    world,
                    regions_col,
                    _require_snapshot_pylist(snap, "civ_affinity"),
                ),
                dtype=np.int64,
            )
            new_gini: dict[int, float] = {}
            for civ_id in np.unique(civ_col):
                mask = civ_col == civ_id
                civ_wealth = wealth_col[mask]
                new_gini[int(civ_id)] = compute_gini(civ_wealth)
            occ_col = _require_snapshot_numpy(snap, "occupation")
            occ_names = ["farmer", "soldier", "merchant", "scholar", "priest"]
            stats: dict[int, dict] = {}
            for civ_id in np.unique(civ_col):
                mask = civ_col == civ_id
                civ_wealth = wealth_col[mask]
                civ_occ = occ_col[mask]
                wealth_by_occ = {}
                for occ_idx, name in enumerate(occ_names):
                    occ_mask = civ_occ == occ_idx
                    if occ_mask.any():
                        wealth_by_occ[name] = float(np.mean(civ_wealth[occ_mask]))
                stats[int(civ_id)] = {
                    "gini": new_gini.get(int(civ_id), 0.0),
                    "mean": float(np.mean(civ_wealth)),
                    "median": float(np.median(civ_wealth)),
                    "std": float(np.std(civ_wealth)),
                    "by_occupation": wealth_by_occ,
                }
            self._gini_by_civ = new_gini
            self._wealth_stats = stats
        except (AttributeError, KeyError, TypeError, ValueError):
            # Preserve prior values on failure â€” one bad turn must not wipe
            # accumulated history.
            logger.exception("Failed to compute displacement/Gini/wealth stats from snapshot")

    def take_post_tick_snapshot(self, turn: int):
        """Hand over the snapshot fetched after this turn's agent tick, once.

        ``_process_tick_results`` reads the pool right after the tick; nothing
        between there and the Phase 10 capture writes the native pool (bridge
        post-processing and stockpile settlement only read it or Python
        state), so the coordinator reuses that batch instead of exporting the
        pool again. Returns None when no batch of this turn is held.
        """
        held = getattr(self, "_post_tick_snapshot", None)
        self._post_tick_snapshot = None
        if held is not None and held[0] == turn:
            return held[1]
        return None

    @property
    def ecology_simulator(self):
        """Expose the Rust simulator handle for ecology tick in agent modes."""
        return self._sim

    def sync_regions(self, world: WorldState) -> None:
        """Phase 1 of the split bridge: full region sync to Rust.

        Must be called exactly once per turn BEFORE ecology tick or agent tick.
        """
        self._post_tick_snapshot = None
        self._sim.set_region_state(build_region_batch(world, self._economy_result))
        # M56b: Send settlement footprints for urban classification
        settlement_batch = build_settlement_batch(world)
        self._sim.set_settlement_footprints(settlement_batch)

    def tick_agents(
        self, world: WorldState, shocks=None, demands=None, conquered=None, *,
        death_output: list[AgentEventRecord] | None = None,
    ) -> list:
        """Phase 2 of the split bridge: send signals and run agent tick.

        Assumes sync_regions() was already called this turn.
        Does NOT call set_region_state() again.
        """
        # M58a: Sync merchant route graph before tick
        from chronicler.economy import build_merchant_route_graph
        route_batch = build_merchant_route_graph(world)
        if getattr(world, "maritime", None) is not None:
            # Maritime: blockaded lanes removed, per-lane raid risk attached.
            from chronicler.maritime import merchant_route_graph
            route_batch = merchant_route_graph(world, route_batch)
        route_batch = _city_route_graph(world, route_batch)
        self._sim.set_merchant_route_graph(route_batch)

        signals = build_signals(world, shocks=shocks, demands=demands, conquered=conquered,
                                gini_by_civ=self._gini_by_civ, economy_result=self._economy_result)
        _send_movement_table(world, self)
        agent_events = self._sim.tick(world.turn, signals)
        return self._process_tick_results(agent_events, world, death_output=death_output)

    def tick(
        self, world: WorldState, shocks=None, demands=None, conquered=None, *,
        death_output: list[AgentEventRecord] | None = None,
    ) -> list:
        """Compatibility wrapper: full sync + agent tick in one call.

        Use sync_regions() + tick_agents() separately when ecology runs between them.
        """
        self.sync_regions(world)

        # M58a: Sync merchant route graph before tick
        from chronicler.economy import build_merchant_route_graph
        route_batch = build_merchant_route_graph(world)
        if getattr(world, "maritime", None) is not None:
            # Maritime: blockaded lanes removed, per-lane raid risk attached.
            from chronicler.maritime import merchant_route_graph
            route_batch = merchant_route_graph(world, route_batch)
        route_batch = _city_route_graph(world, route_batch)
        self._sim.set_merchant_route_graph(route_batch)

        signals = build_signals(world, shocks=shocks, demands=demands, conquered=conquered,
                                gini_by_civ=self._gini_by_civ, economy_result=self._economy_result)
        _send_movement_table(world, self)
        agent_events = self._sim.tick(world.turn, signals)
        return self._process_tick_results(agent_events, world, death_output=death_output)

    def _process_tick_results(
        self, agent_events, world: WorldState, *,
        death_output: list[AgentEventRecord] | None = None,
    ) -> list:
        """Shared post-tick processing; optionally publish ordered borrowed deaths.

        The coordinator supplies a fresh output list for each invocation. The
        legacy world list remains available to standalone bridge callers.
        """
        self._post_tick_snapshot = None
        # M53: relationship stats collection (all modes)
        if self._collect_rel_stats:
            try:
                stats = self._sim.get_relationship_stats()
                self._relationship_stats_history.append(stats)
            except Exception:
                logger.exception("Failed to collect relationship stats from Rust tick")

        # M57b: household stats collection (always in agent modes)
        # Native map iteration is not export order. Canonicalize completed
        # records at history ingestion, leaving values and nested maps intact.
        try:
            h_stats = self._sim.get_household_stats()
            self._household_stats_history.append(dict(sorted(h_stats.items())))
        except Exception:
            logger.exception("Failed to collect household stats from Rust tick")

        # M58a: merchant trip stats collection
        try:
            m_stats = self._sim.get_merchant_trip_stats()
            self._merchant_trip_stats_history.append(dict(sorted(m_stats.items())))
        except Exception:
            pass

        # M59a: knowledge stats collection
        try:
            k_stats = self._sim.get_knowledge_stats()
            created_by_type = {
                "threat": int(k_stats.pop("created_threat", 0)),
                "trade": int(k_stats.pop("created_trade", 0)),
                "religious": int(k_stats.pop("created_religious", 0)),
            }
            transmitted_by_type = {
                "threat": int(k_stats.pop("transmitted_threat", 0)),
                "trade": int(k_stats.pop("transmitted_trade", 0)),
                "religious": int(k_stats.pop("transmitted_religious", 0)),
            }
            int_keys = {
                "packets_created",
                "packets_refreshed",
                "packets_transmitted",
                "packets_expired",
                "packets_evicted",
                "packets_dropped",
                "live_packet_count",
                "agents_with_packets",
                "max_age",
                "max_hops",
                "merchant_plans_packet_driven",
                "merchant_plans_bootstrap",
                "merchant_no_usable_packets",
                "migration_choices_changed_by_threat",
                "migration_choices_changed_by_religion",
                "loyalty_drifts_damped_by_rally",
            }
            normalized_k_stats = {}
            for key, value in k_stats.items():
                normalized_k_stats[key] = int(value) if key in int_keys else float(value)
            normalized_k_stats["created_by_type"] = created_by_type
            normalized_k_stats["transmitted_by_type"] = transmitted_by_type
            self._knowledge_stats_history.append(dict(sorted(normalized_k_stats.items())))
        except Exception:
            logger.exception("Failed to collect knowledge stats from Rust tick")

        self._refresh_snapshot_metrics(world)

        if self._mode == "hybrid":
            self._write_back(world)
            # M30 processing order
            promotions_batch = self._sim.get_promotions()
            self._process_promotions(promotions_batch, world)  # step 1

            raw_events = self._convert_events(agent_events, world.turn)
            world._dead_agents_this_turn = [e for e in raw_events if e.event_type == "death"]
            if death_output is not None:
                death_output.extend(world._dead_agents_this_turn)
            death_events = self._process_deaths(raw_events, world)  # step 2
            world.agent_events_raw.extend(raw_events)

            # M50b: collect dissolution events from Rust tick
            dissolution_events = [e for e in raw_events if e.event_type == "dissolution"]
            if dissolution_events:
                dissolved_list = world.dissolved_edges_by_turn.get(world.turn, [])
                for e in dissolution_events:
                    # target_region field repurposed as bond_type in dissolution events
                    dissolved_list.append(
                        (e.agent_id, e.target_agent_id, e.target_region, e.formed_turn)
                    )
                world.dissolved_edges_by_turn[world.turn] = dissolved_list

            char_events = self._detect_character_events(raw_events, world)  # step 3

            self._event_window.append(raw_events)
            summaries = self._aggregate_events(world, self.named_agents)  # step 4

            # M39: drain dynasty events and check splits
            dynasty_events = self._pending_dynasty_events
            self._pending_dynasty_events = []
            split_events = self.dynasty_registry.check_splits(
                self.gp_by_agent_id, world.turn,
            )
            dynasty_events.extend(split_events)

            # M48: Sync memories for active named characters
            for civ_obj in world.civilizations:
                for gp in civ_obj.great_persons:
                    if gp.active and gp.agent_id is not None:
                        memory_records = _get_agent_memory_records(self._sim, gp.agent_id)
                        gp.memories = [
                            {
                                "event_type": m.event_type,
                                "source_civ": m.source_civ,
                                "turn": m.turn,
                                "intensity": m.intensity,
                                "decay_factor": m.decay_factor,
                                "is_legacy": m.is_legacy,
                            }
                            for m in memory_records
                        ]
                        # M49: Sync needs for active named characters
                        raw_needs = self._sim.get_agent_needs(gp.agent_id)
                        if raw_needs is not None:
                            gp.needs = {
                                "safety": raw_needs[0], "material": raw_needs[1],
                                "social": raw_needs[2], "spiritual": raw_needs[3],
                                "autonomy": raw_needs[4], "purpose": raw_needs[5],
                            }
                        # M50a: relationship sync
                        raw_bonds = self._sim.get_agent_relationships(gp.agent_id)
                        if raw_bonds is not None:
                            gp.agent_bonds = [
                                {"target_id": b[0], "sentiment": b[1], "bond_type": b[2], "formed_turn": b[3]}
                                for b in raw_bonds
                            ]

            # M53: sidecar snapshot (hybrid mode)
            if self._sidecar and world.turn % 10 == 0:
                self._write_sidecar_snapshot(world)
            # M58b: economy sidecar (separate sampling: turn >= 100, every 10 turns)
            self._write_economy_sidecar(world, self._economy_result)
            return summaries + char_events + death_events + dynasty_events
        elif self._mode == "shadow":
            agent_aggs = self._sim.get_aggregates()
            if self._shadow_logger:
                self._shadow_logger.log_turn(world.turn, agent_aggs, world)
            # M30 processing order (still track promotions in shadow mode)
            promotions_batch = self._sim.get_promotions()
            self._process_promotions(promotions_batch, world)
            raw_events = self._convert_events(agent_events, world.turn)
            world._dead_agents_this_turn = [e for e in raw_events if e.event_type == "death"]
            if death_output is not None:
                death_output.extend(world._dead_agents_this_turn)
            self._process_deaths(raw_events, world)
            world.agent_events_raw.extend(raw_events)
            self._event_window.append(raw_events)
            # M53: sidecar snapshot (shadow mode)
            if self._sidecar and world.turn % 10 == 0:
                self._write_sidecar_snapshot(world)
            # M58b: economy sidecar (separate sampling: turn >= 100, every 10 turns)
            self._write_economy_sidecar(world, self._economy_result)
            return []
        elif self._mode == "demographics-only":
            world._dead_agents_this_turn = []
            self._apply_demographics_clamp(world)
            # M53: sidecar snapshot (demographics-only mode)
            if self._sidecar and world.turn % 10 == 0:
                self._write_sidecar_snapshot(world)
            # M58b: economy sidecar (separate sampling: turn >= 100, every 10 turns)
            self._write_economy_sidecar(world, self._economy_result)
            return []
        return []

    @property
    def relationship_stats(self) -> list:
        """M53: Per-tick relationship stats history (populated when --relationship-stats is set)."""
        return self._relationship_stats_history

    @property
    def household_stats(self) -> list:
        """M57b: Per-tick household stats history."""
        return self._household_stats_history

    @property
    def merchant_trip_stats(self) -> list:
        """M58a: Per-tick merchant trip stats history."""
        return self._merchant_trip_stats_history

    @property
    def knowledge_stats(self) -> list:
        """M59a: Per-tick knowledge stats history."""
        return self._knowledge_stats_history

    def write_final_sidecar_snapshot(self, world: "WorldState") -> None:
        """Capture the true post-loop state for validation sidecars.

        Regular sidecar sampling happens inside the turn loop before the main
        runner increments `world.turn`, so a 500-turn run would otherwise end
        with the last aggregate snapshot at turn 490. Writing one final sample
        after the loop keeps the validator aligned with the actual final bundle
        state.
        """
        if not self._sidecar:
            return
        self._write_sidecar_snapshot(world)

    def _write_sidecar_snapshot(self, world: "WorldState") -> None:
        """M53: Write validation sidecar data at sample points (every 10 turns)."""
        turn = world.turn
        agg: dict = {}
        snap = None
        needs_data = None

        # Graph + memory snapshot
        try:
            rel_batch = self._sim.get_all_relationships()
            edges = []
            if rel_batch.num_rows > 0:
                agent_ids = pylist(rel_batch.column("agent_id"))
                target_ids = pylist(rel_batch.column("target_id"))
                bond_types = pylist(rel_batch.column("bond_type"))
                sentiments = pylist(rel_batch.column("sentiment"))
                for i in range(len(agent_ids)):
                    edges.append((agent_ids[i], target_ids[i], bond_types[i], sentiments[i]))
        except Exception:
            edges = []
            logger.exception("Sidecar graph snapshot: failed to read relationships")

        try:
            mem_batch = self._sim.get_all_memories()
            mem_sigs: dict = {}
            if mem_batch.num_rows > 0:
                m_agent_ids = pylist(mem_batch.column("agent_id"))
                m_event_types = pylist(mem_batch.column("event_type"))
                m_turns = pylist(mem_batch.column("turn"))
                m_intensities = pylist(mem_batch.column("intensity"))
                for i in range(len(m_agent_ids)):
                    aid = m_agent_ids[i]
                    if aid not in mem_sigs:
                        mem_sigs[aid] = []
                    valence = -1 if m_intensities[i] < 0 else 1
                    mem_sigs[aid].append((m_event_types[i], m_turns[i], valence))
        except Exception:
            mem_sigs = {}
            logger.exception("Sidecar graph snapshot: failed to read memories")

        self._sidecar.write_graph_snapshot(turn=turn, edges=edges, memory_signatures=mem_sigs)

        # Needs snapshot
        try:
            needs_batch = self._sim.get_all_needs()
            self._sidecar.write_needs_snapshot(turn=turn, needs_batch=needs_batch)
            if hasattr(needs_batch, "to_pydict"):
                needs_data = needs_batch.to_pydict()
            elif hasattr(needs_batch, "column_names"):
                needs_data = {
                    name: pylist(needs_batch.column(name))
                    for name in needs_batch.column_names
                }
        except Exception:
            needs_data = None
            logger.exception("Sidecar needs snapshot: failed to read/write needs")

        # Agent aggregate: per-civ satisfaction, occupations, mean needs, memory occupancy
        try:
            snap = self._sim.get_snapshot()
            if snap.num_rows > 0:
                from collections import Counter, defaultdict

                civ_data: dict = defaultdict(
                    lambda: {
                        "sats": [],
                        "occupations": Counter(),
                        "controlled_occupations": Counter(),
                        "regions": Counter(),
                        "agent_ids": [],
                        "controlled_agent_count": 0,
                    }
                )
                id_list = pylist(snap.column("id"))
                civ_list = pylist(snap.column("civ_affinity"))
                sat_list = pylist(snap.column("satisfaction"))
                occ_list = pylist(snap.column("occupation"))
                region_list = pylist(snap.column("region"))
                polity_civ_ids = self._resolve_polity_civ_ids(world, region_list, civ_list)
                for i in range(len(civ_list)):
                    civ_bucket = civ_data[polity_civ_ids[i]]
                    region_id = int(region_list[i])
                    occupation_id = int(occ_list[i])
                    civ_bucket["sats"].append(sat_list[i])
                    civ_bucket["occupations"][occupation_id] += 1
                    civ_bucket["regions"][region_id] += 1
                    civ_bucket["agent_ids"].append(int(id_list[i]))
                    if 0 <= region_id < len(world.regions) and world.regions[region_id].controller is not None:
                        civ_bucket["controlled_occupations"][occupation_id] += 1
                        civ_bucket["controlled_agent_count"] += 1

                mem_slots_by_agent = Counter()
                for agent_id, signatures in mem_sigs.items():
                    mem_slots_by_agent[int(agent_id)] = len(signatures)

                need_keys = ("safety", "autonomy", "social", "spiritual", "material", "purpose")
                need_sums_by_civ: dict[int, dict[str, float]] = defaultdict(lambda: {key: 0.0 for key in need_keys})
                need_counts_by_civ: Counter = Counter()
                if needs_data is not None and needs_data.get("region") and needs_data.get("civ_affinity"):
                    need_polity_ids = self._resolve_polity_civ_ids(
                        world,
                        needs_data["region"],
                        needs_data["civ_affinity"],
                    )
                    for idx, civ in enumerate(need_polity_ids):
                        need_counts_by_civ[civ] += 1
                        for need_key in need_keys:
                            need_sums_by_civ[civ][need_key] += float(needs_data[need_key][idx])

                def _quartiles(values: list[float]) -> tuple[float, float, float]:
                    if not values:
                        return (0.0, 0.0, 0.0)
                    ordered = sorted(values)
                    n = len(ordered)
                    return (
                        ordered[int((n - 1) * 0.25)],
                        ordered[int((n - 1) * 0.50)],
                        ordered[int((n - 1) * 0.75)],
                    )

                for civ, cd in civ_data.items():
                    sats = cd["sats"]
                    n = len(sats)
                    mean_sat = sum(sats) / n if n > 0 else 0.0
                    std_sat = (sum((s - mean_sat) ** 2 for s in sats) / n) ** 0.5 if n > 1 else 0.0
                    q25, q50, q75 = _quartiles(sats)
                    need_means = {}
                    if need_counts_by_civ[civ] > 0:
                        for need_key in need_keys:
                            need_means[need_key] = round(
                                need_sums_by_civ[civ][need_key] / need_counts_by_civ[civ], 4
                            )
                    memory_slot_mean = 0.0
                    if cd["agent_ids"]:
                        memory_slot_mean = sum(mem_slots_by_agent.get(agent_id, 0) for agent_id in cd["agent_ids"]) / len(cd["agent_ids"])
                    agg[f"civ_{civ}"] = {
                        "satisfaction_mean": round(mean_sat, 4),
                        "satisfaction_std": round(std_sat, 4),
                        "satisfaction_q25": round(q25, 4),
                        "satisfaction_q50": round(q50, 4),
                        "satisfaction_q75": round(q75, 4),
                        "agent_count": n,
                        "occupation_counts": dict(cd["occupations"]),
                        "controlled_agent_count": int(cd["controlled_agent_count"]),
                        "controlled_occupation_counts": dict(cd["controlled_occupations"]),
                        "need_means": need_means,
                        "memory_slot_occupancy_mean": round(memory_slot_mean, 4),
                        "gini": round(self._gini_by_civ.get(int(civ), 0.0), 4),
                    }
            self._sidecar.write_agent_aggregate(turn=turn, aggregates=agg)
        except Exception:
            logger.exception("Sidecar agent aggregate: failed to build/write aggregate snapshot")

        # Condensed community summary for full-gate structural checks
        try:
            if snap is not None and getattr(snap, "num_rows", 0) > 0:
                from collections import Counter, defaultdict
                from chronicler.validate import detect_communities

                id_list = pylist(snap.column("id"))
                region_list = pylist(snap.column("region"))
                id_to_region = {
                    int(id_list[idx]): int(region_list[idx])
                    for idx in range(len(id_list))
                }

                communities = detect_communities(edges, mem_sigs)
                region_summary: dict = defaultdict(
                    lambda: {
                        "cluster_count": 0,
                        "sizes": [],
                        "dominant_memory_type": None,
                        "max_cluster_fraction": 0.0,
                    }
                )
                region_population = Counter(id_to_region.values())

                for community in communities:
                    region_counts = Counter(
                        id_to_region.get(int(agent_id))
                        for agent_id in community
                        if int(agent_id) in id_to_region
                    )
                    if not region_counts:
                        continue
                    dominant_region, dominant_region_size = region_counts.most_common(1)[0]
                    if dominant_region is None:
                        continue
                    memory_type_counts = Counter()
                    for agent_id in community:
                        for event_type, _memory_turn, _valence in mem_sigs.get(int(agent_id), []):
                            memory_type_counts[int(event_type)] += 1

                    summary = region_summary[f"region_{dominant_region}"]
                    summary["cluster_count"] += 1
                    summary["sizes"].append(len(community))
                    if memory_type_counts:
                        summary["dominant_memory_type"] = memory_type_counts.most_common(1)[0][0]
                    population = region_population.get(dominant_region, 0)
                    if population > 0:
                        summary["max_cluster_fraction"] = max(
                            summary["max_cluster_fraction"],
                            round(dominant_region_size / population, 4),
                        )

                self._sidecar.write_community_summary(turn=turn, summary=dict(region_summary))
        except Exception:
            logger.exception("Sidecar community summary: failed to build/write summary")

    def _write_economy_sidecar(self, world, economy_result) -> None:
        """M58b: Write economy convergence snapshot if sidecar active and sampling conditions met."""
        if not self._sidecar or economy_result is None:
            return
        if world.turn < 100 or world.turn % 10 != 0:
            return

        region_names = [r.name for r in world.regions]
        self._sidecar.write_economy_snapshot(world.turn, {
            "turn": world.turn,
            "oracle_trade_volume_by_category": {
                rname: economy_result.oracle_imports.get(rname, {"food": 0, "raw_material": 0, "luxury": 0})
                for rname in region_names
            },
            "agent_trade_volume_by_category": {
                rname: {
                    "food": economy_result.imports_by_region.get(rname, {}).get("food", 0),
                    "raw_material": economy_result.imports_by_region.get(rname, {}).get("raw_material", 0),
                    "luxury": economy_result.imports_by_region.get(rname, {}).get("luxury", 0),
                }
                for rname in region_names
            },
            "post_trade_margin_by_region": {
                rname: economy_result.merchant_margins.get(rname, 0.0)
                for rname in region_names
            },
            "food_sufficiency_by_region": {
                rname: economy_result.food_sufficiency.get(rname, 0.0)
                for rname in region_names
            },
            "oracle_margins_by_region": {
                rname: economy_result.oracle_imports.get(rname, {}).get("margin", 0.0)
                for rname in region_names
            },
            "oracle_food_sufficiency_by_region": {
                rname: economy_result.oracle_imports.get(rname, {}).get("food_sufficiency", 0.0)
                for rname in region_names
            },
            "imports_by_region_by_category": {
                rname: economy_result.imports_by_region.get(rname, {})
                for rname in region_names
            },
            "conservation": economy_result.conservation,
        })

    def _convert_events(self, batch, turn):
        """Convert Arrow events RecordBatch to AgentEventRecord list.

        Reads each column once (``to_pylist`` yields the same Python values
        as per-row ``as_py()``) and builds records in row order.
        """
        num_rows = batch.num_rows
        if num_rows == 0:
            return []
        names = batch.schema.names

        def column(name):
            return pylist(batch.column(name))

        def optional_column(name, default):
            return column(name) if name in names else [default] * num_rows

        event_type_codes = column("event_type")
        type_map = EVENT_TYPE_MAP
        type_names = {code: type_map.get(code, f"unknown_{code}") for code in set(event_type_codes)}
        # Positional construction in AgentEventRecord field order: turn,
        # agent_id, event_type, region, target_region, civ_affinity,
        # occupation, belief, target_agent_id, formed_turn, migration_driver.
        return list(starmap(AgentEventRecord, zip(
            repeat(turn, num_rows),
            column("agent_id"),
            [type_names[code] for code in event_type_codes],
            column("region"),
            column("target_region"),
            column("civ_affinity"),
            column("occupation"),
            optional_column("belief", None),
            optional_column("target_agent_id", 0),
            optional_column("formed_turn", 0),
            optional_column("migration_driver", NO_MIGRATION_DRIVER),
        )))

    def _process_promotions(self, batch, world) -> list:
        """Process promotion RecordBatch → create GreatPerson instances.

        Rust (``NamedCharacterRegistry::find_candidates``) is the only
        promotion gate. For skill-gated candidates (trigger 0) Python then
        relabels the role from the agent's full event history, which the Rust
        pool does not keep (it has life-event bits and a short displacement
        cooldown, not lifetime counts):
        - Serial migrant (3+ migrations) → Merchant
        - Occupation versatility (3+ switches) → Scientist

        Agent promotions never produce the ``exile`` role. On a GreatPerson
        ``exile`` means a deposed-leader pretender (``succession.py``: it
        drains its origin civ's stability and can be restored to the throne).
        The former "long displacement → exile" relabel could never fire (it
        read state tracked only for already-promoted agents) and would have
        turned displaced commoners into throne claimants, so it was removed;
        role id 4 from Rust is rejected for the same reason.
        """
        import random
        from chronicler.models import GreatPerson

        created = []
        for i in range(batch.num_rows):
            agent_id = batch.column("agent_id")[i].as_py()
            parent_id_0 = batch.column("parent_id_0")[i].as_py()
            parent_id_1 = batch.column("parent_id_1")[i].as_py()
            role_id = batch.column("role")[i].as_py()
            trigger = batch.column("trigger")[i].as_py()
            origin_region = batch.column("origin_region")[i].as_py()
            role = ROLE_MAP.get(role_id)
            if role is None or role == "exile":
                logger.warning("Unknown role_id %d for agent %d, skipping promotion", role_id, agent_id)
                continue

            # Python-side role relabels from event history (skill-gated only)
            if trigger == 0:
                # Counts over agent_events_raw, served incrementally by the index.
                migration_count, switch_count = history_index(world).agent_event_counts(
                    world, agent_id,
                )
                if migration_count >= 3:
                    role = "merchant"
                elif switch_count >= 3:
                    role = "scientist"

            # M-AF1 #8: authoritative civ from Rust agent pool
            civ_id = batch.column("civ_id")[i].as_py()
            if civ_id < len(world.civilizations):
                civ = world.civilizations[civ_id]
            else:
                # Fallback: region controller (should not happen)
                civ = world.civilizations[0]
                if origin_region < len(world.regions):
                    controller = world.regions[origin_region].controller
                    if controller:
                        for c in world.civilizations:
                            if c.name == controller:
                                civ = c
                                break

            # Best-effort origin_civilization from region controller
            # (may differ from civ if agent migrated)
            origin_civ = civ
            if origin_region < len(world.regions):
                controller = world.regions[origin_region].controller
                if controller:
                    for c in world.civilizations:
                        if c.name == controller:
                            origin_civ = c
                            break

            rng = random.Random(world.seed + world.turn + agent_id)
            name = _pick_name(civ, world, rng)
            trait = rng.choice(ALL_TRAITS)

            gp = GreatPerson(
                name=name,
                role=role,
                trait=trait,
                civilization=civ.name,
                origin_civilization=origin_civ.name,
                born_turn=world.turn,
                source="agent",
                agent_id=agent_id,
                parent_id_0=parent_id_0,
                parent_id_1=parent_id_1,
            )
            gp.base_name = strip_title(gp.name)
            # M40: Set origin_region from promotions batch
            if origin_region < len(world.regions):
                gp.origin_region = world.regions[origin_region].name
                gp.region = gp.origin_region
            region_name = world.regions[origin_region].name if origin_region < len(world.regions) else "unknown"
            _append_deed(gp, f"Promoted as {role} in {region_name}", region=region_name, turn=world.turn, civ=gp.civilization)
            civ.great_persons.append(gp)
            created.append(gp)
            self.named_agents[agent_id] = name
            self.gp_by_agent_id[agent_id] = gp
            self._origin_regions[agent_id] = origin_region

            # M48: Mule promotion roll
            if gp.agent_id is not None:
                mule_rng = random.Random(world.seed + world.turn * 7919 + gp.agent_id)
                if mule_rng.random() < MULE_PROMOTION_PROBABILITY:
                    memories = _get_agent_memory_records(self._sim, gp.agent_id)
                    if memories:
                        strongest = max(memories, key=lambda m: abs(m.intensity))
                        event_type = strongest.event_type
                        if event_type in MULE_MAPPING:
                            gp.mule = True
                            gp.mule_memory_event_type = event_type
                            gp.utility_overrides = MULE_MAPPING[event_type]
                            _append_deed(gp, f"Mule: shaped by memory type {event_type}", region=gp.region, turn=world.turn, civ=gp.civilization)

            # M52: GP artifact intent
            from chronicler.artifacts import emit_gp_artifact_intent
            emit_gp_artifact_intent(world, civ, gp)

        for gp in created:
            dynasty_events = self.dynasty_registry.check_promotion(
                gp, self.named_agents, self.gp_by_agent_id,
            )
            for de in dynasty_events:
                de.turn = world.turn
                self._pending_dynasty_events.append(de)

        return created

    def _process_deaths(self, raw_events, world) -> list:
        """Cross-reference death events against named_agents. Return Events for named character deaths."""
        from chronicler.models import Event

        death_events = []
        for e in raw_events:
            if e.event_type != "death":
                continue
            if e.agent_id not in self.named_agents:
                continue

            name = self.named_agents[e.agent_id]
            region_name = (world.regions[e.region].name
                          if e.region < len(world.regions) else f"region {e.region}")

            # Find and transition the GreatPerson
            found = False
            for civ in world.civilizations:
                if found:
                    break
                for gp in list(civ.great_persons):
                    if gp.agent_id == e.agent_id:
                        was_exile = gp.fate == "exile"
                        gp.alive = False
                        gp.active = False
                        gp.fate = "dead"
                        gp.death_turn = world.turn
                        civ.great_persons.remove(gp)
                        world.retired_persons.append(gp)

                        desc = (f"{name} died in exile in {region_name}"
                                if was_exile
                                else f"{name} died in {region_name}")
                        death_events.append(Event(
                            turn=world.turn,
                            event_type="character_death",
                            actors=[name, civ.name],
                            description=desc,
                            importance=6,
                            source="agent",
                            region=(region_name if e.region < len(world.regions) else None),
                        ))
                        found = True
                        break

        # M39: post-loop extinction check
        extinction_events = self.dynasty_registry.check_extinctions(
            self.gp_by_agent_id, world.turn,
        )
        death_events.extend(extinction_events)

        return death_events

    def _detect_character_events(self, raw_events, world) -> list:
        """Detect notable_migration and exile_return from migration events."""
        from chronicler.models import Event

        character_events = []
        for e in raw_events:
            if e.event_type != "migration":
                continue
            if e.agent_id not in self.named_agents:
                continue

            name = self.named_agents[e.agent_id]
            origin = self._origin_regions.get(e.agent_id)
            source_name = (world.regions[e.region].name
                          if e.region < len(world.regions) else f"region {e.region}")
            target_name = (world.regions[e.target_region].name
                          if e.target_region < len(world.regions) else f"region {e.target_region}")

            # Track departure from origin
            if origin is not None and e.region == origin and e.target_region != origin:
                self._departure_turns.setdefault(e.agent_id, world.turn)

            # Exile return: named char returns to origin_region after 30+ turns away
            if (origin is not None
                    and e.target_region == origin
                    and e.agent_id in self._departure_turns):
                turns_away = world.turn - self._departure_turns[e.agent_id]
                if turns_away >= 30:
                    character_events.append(Event(
                        turn=world.turn,
                        event_type="exile_return",
                        actors=[name],
                        description=f"{name} returned to {target_name} after {turns_away} turns in exile",
                        importance=6,
                        source="agent",
                        **self._character_place(e.agent_id, target_name),
                    ))
                    if e.agent_id in self.gp_by_agent_id:
                        self.gp_by_agent_id[e.agent_id].region = target_name
                        _append_deed(self.gp_by_agent_id[e.agent_id], f"Returned to {target_name} after {turns_away} turns", region=target_name, turn=world.turn, civ=self.gp_by_agent_id[e.agent_id].civilization)
                    del self._departure_turns[e.agent_id]
                    continue  # don't also emit notable_migration

            # Notable migration: any named character moves
            character_events.append(Event(
                turn=world.turn,
                event_type="notable_migration",
                actors=[name],
                description=f"{name} migrated from {source_name} to {target_name}",
                importance=4,
                source="agent",
                driver=migration_driver_name(e.migration_driver),
                **self._character_place(e.agent_id, source_name),
            ))
            if e.agent_id in self.gp_by_agent_id:
                self.gp_by_agent_id[e.agent_id].region = target_name
                _append_deed(self.gp_by_agent_id[e.agent_id], f"Migrated from {source_name} to {target_name}", region=target_name, turn=world.turn, civ=self.gp_by_agent_id[e.agent_id].civilization)

        return character_events

    def _character_place(self, agent_id, region_name) -> dict:
        """Provenance fields of a named character's event: where, and whose."""
        gp = self.gp_by_agent_id.get(agent_id)
        civs = [gp.civilization] if gp is not None and gp.civilization else []
        return {"region": region_name, "civs": civs}

    def apply_conquest_transitions(self, conquered_civ, conqueror_civ,
                                   conquered_regions: list[str],
                                   conqueror_civ_id: int,
                                   host_civ_ids: dict | None = None,
                                   turn: int = 0) -> list:
        """Transition agent-source named characters on conquest.

        Args:
            conquered_civ: The conquered civilization object.
            conqueror_civ: The conquering civilization object.
            conquered_regions: List of region names that were conquered.
            conqueror_civ_id: Numeric civ ID (u8) for the conqueror (for FFI).
            host_civ_ids: Map of region_name → civ_id for refugees in surviving territory.
            turn: Current turn number for event timestamps.
        """
        from chronicler.models import Event

        events = []
        conquered_region_set = set(conquered_regions)
        if host_civ_ids is None:
            host_civ_ids = {}

        for gp in list(conquered_civ.great_persons):
            if gp.source != "agent" or gp.agent_id is None:
                continue

            gp.fate = "exile"
            gp.active = False
            _append_deed(gp, f"Exiled after conquest of {gp.region or conquered_civ.name}", region=gp.region, turn=turn, civ=gp.civilization)

            if gp.region in conquered_region_set:
                # In conquered territory → hostage
                gp.captured_by = conqueror_civ.name
                try:
                    self._sim.set_agent_civ(gp.agent_id, conqueror_civ_id)
                except Exception:
                    logger.exception(
                        "Failed to set GP civ during conquest exile (agent_id=%s, new_civ_id=%s)",
                        gp.agent_id,
                        conqueror_civ_id,
                    )
            else:
                # In surviving territory → refugee, not captured
                gp.captured_by = None
                host_id = host_civ_ids.get(gp.region, conqueror_civ_id)
                try:
                    self._sim.set_agent_civ(gp.agent_id, host_id)
                except Exception:
                    logger.exception(
                        "Failed to set GP civ during conquest exile fallback (agent_id=%s, new_civ_id=%s)",
                        gp.agent_id,
                        host_id,
                    )

            events.append(Event(
                turn=turn,
                event_type="conquest_exile",
                actors=[gp.name, conquered_civ.name, conqueror_civ.name],
                description=f"{gp.name} of {conquered_civ.name} exiled after conquest by {conqueror_civ.name}",
                importance=5, source="agent", region=gp.region,
            ))

        return events

    def apply_secession_transitions(self, old_civ, new_civ,
                                    seceding_regions: list[str],
                                    new_civ_id: int,
                                    turn: int = 0,
                                    *,
                                    world: "WorldState | None" = None,
                                    old_civ_id: int | None = None) -> list:
        """Transition agent-source named characters on secession."""
        from chronicler.models import Event

        events = []
        seceding_set = set(seceding_regions)
        transferred_agent_ids: set[int] = set()

        if world is not None and old_civ_id is not None:
            transferred_agent_ids = self._transfer_region_agents_to_civ(
                world=world,
                region_names=seceding_set,
                old_civ_id=old_civ_id,
                new_civ_id=new_civ_id,
            )

        for gp in list(old_civ.great_persons):
            if gp.source != "agent" or gp.agent_id is None:
                continue
            if gp.region not in seceding_set:
                continue

            gp.civilization = new_civ.name
            # origin_civilization stays unchanged
            old_civ.great_persons.remove(gp)
            new_civ.great_persons.append(gp)
            _append_deed(gp, f"Defected to {new_civ.name} during secession", region=gp.region, turn=turn, civ=new_civ.name)

            if gp.agent_id not in transferred_agent_ids:
                try:
                    self._sim.set_agent_civ(gp.agent_id, new_civ_id)
                except Exception:
                    logger.exception(
                        "Failed to set GP civ during secession defection (agent_id=%s, new_civ_id=%s)",
                        gp.agent_id,
                        new_civ_id,
                    )

            events.append(Event(
                turn=turn,
                event_type="secession_defection",
                actors=[gp.name, old_civ.name, new_civ.name],
                description=f"{gp.name} defected with the secession of {gp.region}",
                importance=5, source="agent", region=gp.region,
            ))

        return events

    def apply_restoration_transitions(
        self,
        absorber_civ,
        restored_civ,
        restored_regions: list[str],
        absorber_civ_id: int,
        restored_civ_id: int,
        *,
        world: "WorldState | None" = None,
    ) -> None:
        """Realign agent-source affiliation when an exiled civ is restored."""
        restored_set = set(restored_regions)
        transferred_agent_ids: set[int] = set()

        if world is not None:
            transferred_agent_ids = self._transfer_region_agents_to_civ(
                world=world,
                region_names=restored_set,
                old_civ_id=absorber_civ_id,
                new_civ_id=restored_civ_id,
            )

        for gp in list(absorber_civ.great_persons):
            if gp.source != "agent" or gp.agent_id is None:
                continue
            if gp.region not in restored_set:
                continue

            gp.civilization = restored_civ.name
            absorber_civ.great_persons.remove(gp)
            restored_civ.great_persons.append(gp)
            _append_deed(gp, f"Returned to {restored_civ.name} during restoration", region=gp.region, turn=world.turn if world is not None else None, civ=restored_civ.name)

            if gp.agent_id not in transferred_agent_ids:
                try:
                    self._sim.set_agent_civ(gp.agent_id, restored_civ_id)
                except Exception:
                    logger.exception(
                        "Failed to set GP civ during restoration transition (agent_id=%s, new_civ_id=%s)",
                        gp.agent_id,
                        restored_civ_id,
                    )

    def apply_absorption_transitions(
        self,
        losing_civ,
        absorber_civ,
        absorbed_regions: list[str],
        losing_civ_id: int,
        absorber_civ_id: int,
        *,
        world: "WorldState | None" = None,
    ) -> None:
        """Realign agent-source affiliation when a civ is peacefully absorbed."""
        absorbed_set = set(absorbed_regions)
        transferred_agent_ids: set[int] = set()

        if world is not None:
            transferred_agent_ids = self._transfer_region_agents_to_civ(
                world=world,
                region_names=absorbed_set,
                old_civ_id=losing_civ_id,
                new_civ_id=absorber_civ_id,
            )

        for gp in list(losing_civ.great_persons):
            if gp.source != "agent" or gp.agent_id is None:
                continue
            if gp.region not in absorbed_set:
                continue

            gp.civilization = absorber_civ.name
            losing_civ.great_persons.remove(gp)
            absorber_civ.great_persons.append(gp)
            _append_deed(gp, f"Absorbed into {absorber_civ.name} during twilight absorption", region=gp.region, turn=world.turn if world is not None else None, civ=absorber_civ.name)

            if gp.agent_id not in transferred_agent_ids:
                try:
                    self._sim.set_agent_civ(gp.agent_id, absorber_civ_id)
                except Exception:
                    logger.exception(
                        "Failed to set GP civ during absorption transition (agent_id=%s, new_civ_id=%s)",
                        gp.agent_id,
                        absorber_civ_id,
                    )

    def realign_region_agents_to_civ(
        self,
        *,
        world: "WorldState",
        region_names: set[str],
        old_civ_id: int,
        new_civ_id: int,
    ) -> set[int]:
        """Move ordinary agents in the specified regions from one polity to another."""
        return self._transfer_region_agents_to_civ(
            world=world,
            region_names=region_names,
            old_civ_id=old_civ_id,
            new_civ_id=new_civ_id,
        )

    def _transfer_region_agents_to_civ(
        self,
        *,
        world: "WorldState",
        region_names: set[str],
        old_civ_id: int,
        new_civ_id: int,
    ) -> set[int]:
        """Move agents in the specified regions from one civ slot to another."""
        if not region_names:
            return set()

        try:
            snapshot = self._sim.get_snapshot()
        except Exception:
            logger.exception("Failed to fetch agent snapshot for region-to-civ realignment")
            return set()

        if snapshot is None or getattr(snapshot, "num_rows", 0) == 0:
            return set()

        region_name_to_id = {
            region.name: region_idx for region_idx, region in enumerate(world.regions)
        }
        target_region_ids = {
            region_name_to_id[name]
            for name in region_names
            if name in region_name_to_id
        }
        if not target_region_ids:
            return set()

        agent_ids = pylist(snapshot.column("id"))
        region_ids = pylist(snapshot.column("region"))
        civ_ids = pylist(snapshot.column("civ_affinity"))

        transferred: set[int] = set()
        for idx, agent_id in enumerate(agent_ids):
            if int(region_ids[idx]) not in target_region_ids:
                continue
            if int(civ_ids[idx]) != int(old_civ_id):
                continue
            try:
                self._sim.set_agent_civ(int(agent_id), int(new_civ_id))
                transferred.add(int(agent_id))
            except Exception:
                logger.exception(
                    "Failed to set agent civ during region realignment (agent_id=%s, new_civ_id=%s)",
                    int(agent_id),
                    int(new_civ_id),
                )
                continue

        return transferred

    def last_tick_unrest_by_region(
        self,
    ) -> tuple[dict[int, int], dict[tuple[int, int], int]]:
        """Rebels per region and migrant flows per (from, to) region pair.

        Read-only view of the most recent tick in the bridge's event window
        (no transient state); the civ-level rebellion/migration hazards in
        hybrid mode roll these up.
        """
        rebels: dict[int, int] = {}
        flows: dict[tuple[int, int], int] = {}
        if not self._event_window:
            return rebels, flows
        for e in self._event_window[-1]:
            if e.event_type == "rebellion":
                rebels[e.region] = rebels.get(e.region, 0) + 1
            elif e.event_type == "migration":
                key = (e.region, e.target_region)
                flows[key] = flows.get(key, 0) + 1
        return rebels, flows

    def _aggregate_events(self, world, named_agents=None):
        """Check thresholds and emit summary Events."""
        # Named-actor lookups index each event list once per call (see
        # _named_actors_in_region); the memo lives only for this call.
        self._named_actor_memo = {}
        try:
            return self._aggregate_event_summaries(world, named_agents)
        finally:
            self._named_actor_memo = None

    def _aggregate_event_summaries(self, world, named_agents=None):
        if named_agents is None:
            named_agents = {}
        summaries = []
        current = list(self._event_window)[-1] if self._event_window else []
        region_names = {i: r.name for i, r in enumerate(world.regions)}
        region_populations = {
            idx: int(getattr(region, "population", 0) or 0)
            for idx, region in enumerate(world.regions)
        }
        try:
            region_pops = self._sim.get_region_populations()
            region_ids = pylist(region_pops.column("region_id"))
            alive_counts = pylist(region_pops.column("alive_count"))
            region_populations.update({
                int(region_id): int(alive_count)
                for region_id, alive_count in zip(region_ids, alive_counts)
            })
        except (AttributeError, KeyError, TypeError, ValueError):
            logger.debug("Falling back to region.population values for event aggregation")

        # === Single-tick patterns ===

        # Group current events by type and region
        migrations_by_source = {}
        rebellions_by_region = {}
        switches_by_region = {}
        for e in current:
            if e.event_type == "migration":
                migrations_by_source.setdefault(e.region, []).append(e)
            elif e.event_type == "rebellion":
                rebellions_by_region.setdefault(e.region, []).append(e)
            elif e.event_type == "occupation_switch":
                switches_by_region.setdefault(e.region, []).append(e)

        # Mass migration: >=8 agents leave one region in one tick
        for region_id, events in migrations_by_source.items():
            if len(events) >= 8:
                occ_counts = Counter(e.occupation for e in events)
                occ_majority = OCCUPATION_NAMES[occ_counts.most_common(1)[0][0]]
                targets = Counter(e.target_region for e in events)
                target_id = targets.most_common(1)[0][0]
                driver = dominant_migration_driver(events)
                template = MASS_MIGRATION_BY_DRIVER.get(driver, SUMMARY_TEMPLATES["mass_migration"])
                summaries.append(Event(
                    turn=world.turn, event_type="mass_migration",
                    actors=self._named_actors_in_region(region_id, named_agents, current),
                    description=template.format(
                        count=len(events), occ_majority=occ_majority,
                        source_region=region_names.get(region_id, f"region {region_id}"),
                        target_region=region_names.get(target_id, f"region {target_id}"),
                    ),
                    importance=5, source="agent", driver=driver, **self._summary_place(world, region_id),
                ))

        # Local rebellion: >=5 agents rebel in one region
        for region_id, events in rebellions_by_region.items():
            if len(events) >= 5:
                occ_counts = Counter(e.occupation for e in events)
                occ_majority = OCCUPATION_NAMES[occ_counts.most_common(1)[0][0]]
                summaries.append(Event(
                    turn=world.turn, event_type="local_rebellion",
                    actors=self._named_actors_in_region(region_id, named_agents, current),
                    description=SUMMARY_TEMPLATES["local_rebellion"].format(
                        count=len(events), occ_majority=occ_majority,
                        region=region_names.get(region_id, f"region {region_id}"),
                    ),
                    importance=7, source="agent", **self._summary_place(world, region_id),
                ))

        # Occupation shift: >25% of region switches in one tick
        for region_id, events in switches_by_region.items():
            region_pop = region_populations.get(region_id, 0)
            if region_pop > 0 and len(events) / region_pop > 0.25:
                new_occ_counts = Counter(e.occupation for e in events)
                new_occ = OCCUPATION_NAMES[new_occ_counts.most_common(1)[0][0]]
                summaries.append(Event(
                    turn=world.turn, event_type="occupation_shift",
                    actors=self._named_actors_in_region(region_id, named_agents, current),
                    description=SUMMARY_TEMPLATES["occupation_shift"].format(
                        count=len(events),
                        region=region_names.get(region_id, f"region {region_id}"),
                        new_occupation=new_occ,
                    ),
                    importance=5, source="agent", **self._summary_place(world, region_id),
                ))

        # === Multi-turn patterns ===

        # Per-turn tallies of each window list, merged in window order (the
        # same counts and first-seen key order as scanning the lists).
        window_list = list(self._event_window)
        window_stats = [self._window_list_stats(turn_events) for turn_events in window_list]

        # Loyalty cascade: >=10 agents flip in one region over 5 turns
        window_depth = min(len(self._event_window), 5)
        recent_stats = window_stats[len(window_stats) - window_depth:]
        loyalty_flips_by_region = _merge_counts(s["loyalty_flips"] for s in recent_stats)
        for region_id, count in loyalty_flips_by_region.items():
            if count >= 10:
                recent_flips = [
                    e for s in recent_stats for e in s["flips_by_region"].get(region_id, ())
                ]
                target_civ_counts = Counter(e.civ_affinity for e in recent_flips)
                target_civ_id = target_civ_counts.most_common(1)[0][0]
                target_civ_name = (world.civilizations[target_civ_id].name
                                  if target_civ_id < len(world.civilizations)
                                  else f"civ {target_civ_id}")
                summaries.append(Event(
                    turn=world.turn, event_type="loyalty_cascade",
                    actors=self._named_actors_in_region(region_id, named_agents, recent_flips),
                    description=SUMMARY_TEMPLATES["loyalty_cascade"].format(
                        count=count,
                        region=region_names.get(region_id, f"region {region_id}"),
                        target_civ=target_civ_name,
                    ),
                    importance=6, source="agent",
                    **self._summary_place(world, region_id, also=target_civ_name),
                ))

        # Demographic crisis: region loses >30% over window
        if len(self._event_window) >= 2:
            deaths_by_region = _merge_counts(s["deaths"] for s in window_stats)
            births_by_region = _merge_counts(s["births"] for s in window_stats)
            for region_id, deaths in deaths_by_region.items():
                births = births_by_region.get(region_id, 0)
                net_loss = deaths - births
                if region_id < len(world.regions):
                    region = world.regions[region_id]
                    if region.population > 0 and net_loss > 0:
                        loss_pct = net_loss / (region.population + net_loss) * 100
                        if loss_pct > 30:
                            summaries.append(Event(
                                turn=world.turn, event_type="demographic_crisis",
                                actors=self._named_actors_in_region(region_id, named_agents, current),
                                description=SUMMARY_TEMPLATES["demographic_crisis"].format(
                                    region=region_names.get(region_id, f"region {region_id}"),
                                    pct=int(loss_pct),
                                    window=len(self._event_window),
                                ),
                                importance=7, source="agent", **self._summary_place(world, region_id),
                            ))

        # === M30 new event types ===

        # Economic boom: >=10 occupation switches TO merchant over 20-turn window
        # [CALIBRATE: post-M28, initial 10]
        boom_window = min(len(self._event_window), 20)
        boom_lists = window_list[len(window_list) - boom_window:]
        merchant_switches_by_region = _merge_counts(  # switches to merchant
            s["merchant_switches"] for s in window_stats[len(window_stats) - boom_window:])
        for region_id, count in merchant_switches_by_region.items():
            if count >= 10:
                summaries.append(Event(
                    turn=world.turn, event_type="economic_boom",
                    actors=self._named_actors_in_lists(region_id, named_agents, boom_lists),
                    description=SUMMARY_TEMPLATES["economic_boom"].format(
                        region=region_names.get(region_id, f"region {region_id}"),
                        count=count, window=boom_window,
                    ),
                    importance=5, source="agent", **self._summary_place(world, region_id),
                ))

        # Brain drain: >=5 scholars leave region over 10-turn window
        # [CALIBRATE: post-M28, initial 5]
        drain_window = min(len(self._event_window), 10)
        drain_lists = window_list[len(window_list) - drain_window:]
        scholar_departures_by_region = _merge_counts(  # scholar migrations
            s["scholar_departures"] for s in window_stats[len(window_stats) - drain_window:])
        for region_id, count in scholar_departures_by_region.items():
            if count >= 5:
                summaries.append(Event(
                    turn=world.turn, event_type="brain_drain",
                    actors=self._named_actors_in_lists(region_id, named_agents, drain_lists),
                    description=SUMMARY_TEMPLATES["brain_drain"].format(
                        count=count,
                        region=region_names.get(region_id, f"region {region_id}"),
                        window=drain_window,
                    ),
                    importance=5, source="agent", **self._summary_place(world, region_id),
                ))

        return summaries

    @staticmethod
    def _summary_place(world, region_id, also: str | None = None) -> dict:
        """Provenance fields of a regional agent summary: the region and the
        civ(s) involved (summaries name characters, not civs, as actors)."""
        if not (0 <= region_id < len(world.regions)):
            return {}
        region = world.regions[region_id]
        civs = [region.controller] if region.controller else []
        if also and also not in civs and any(c.name == also for c in world.civilizations):
            civs.append(also)
        return {"region": region.name, "civs": civs}

    def _window_list_stats(self, events) -> dict:
        """Per-region tallies of one turn's event list in the event window.

        Window lists are not modified after they are appended, so each is
        tallied once (cached by identity and length while in the window)
        instead of on every turn it stays in the window. Dict keys are in
        first-seen order, as the per-turn scans built them.
        """
        cache = getattr(self, "_window_stats_cache", None)
        if cache is None:
            cache = self._window_stats_cache = {}
        entry = cache.get(id(events))
        if entry is not None and entry[0] is events and entry[1] == len(events):
            return entry[2]
        loyalty: dict = {}
        flips: dict = {}
        deaths: dict = {}
        births: dict = {}
        merchants: dict = {}
        scholars: dict = {}
        for e in events:
            event_type = e.event_type
            if event_type == "loyalty_flip":
                loyalty[e.region] = loyalty.get(e.region, 0) + 1
                flips.setdefault(e.region, []).append(e)
            elif event_type == "death":
                deaths[e.region] = deaths.get(e.region, 0) + 1
            elif event_type == "birth":
                births[e.region] = births.get(e.region, 0) + 1
            elif event_type == "occupation_switch":
                if e.occupation == 2:  # merchant
                    merchants[e.region] = merchants.get(e.region, 0) + 1
            elif event_type == "migration":
                if e.occupation == 3:  # scholar
                    scholars[e.region] = scholars.get(e.region, 0) + 1
        try:
            agent_ids = np.fromiter((e.agent_id for e in events), dtype=np.int64, count=len(events))
            order = np.argsort(agent_ids, kind="stable")
            sorted_ids = agent_ids[order]
        except (TypeError, ValueError, OverflowError):  # non-integer ids: scanned instead
            order = sorted_ids = None
        stats = {
            "loyalty_flips": loyalty, "flips_by_region": flips, "deaths": deaths, "births": births,
            "merchant_switches": merchants, "scholar_departures": scholars,
            "sorted_agent_ids": sorted_ids, "agent_order": order,
        }
        live = {id(turn_events) for turn_events in self._event_window}
        for key in [key for key in cache if key not in live]:
            del cache[key]
        cache[id(events)] = (events, len(events), stats)
        return stats

    def _named_actors_in_lists(self, region_id, named_agents, event_lists):
        """``_named_actors_in_region`` over the concatenation of event lists.

        Looks up only the named agents' rows (sorted agent ids per list)
        instead of scanning every event; names keep first-seen event order.
        """
        memo = getattr(self, "_named_actor_memo", None)
        key = ("lists", tuple(id(events) for events in event_lists), id(named_agents))
        entry = memo.get(key) if memo is not None else None
        if entry is None:
            named_ids = list(named_agents)
            stats_by_list = [self._window_list_stats(events) for events in event_lists]
            indexed = (all(type(aid) is int and -(1 << 63) <= aid < (1 << 63) for aid in named_ids)
                       and all(s["sorted_agent_ids"] is not None for s in stats_by_list))
            if not named_ids:
                by_region = {}
            elif indexed:
                hits = []
                query = np.asarray(named_ids, dtype=np.int64)
                for pos, stats in enumerate(stats_by_list):
                    sorted_ids, order = stats["sorted_agent_ids"], stats["agent_order"]
                    lo = np.searchsorted(sorted_ids, query, side="left")
                    hi = np.searchsorted(sorted_ids, query, side="right")
                    for aid, a, b in zip(named_ids, lo.tolist(), hi.tolist()):
                        for row in order[a:b].tolist():
                            hits.append((pos, row, aid))
                hits.sort()
                by_region: dict = {}
                for pos, row, aid in hits:
                    names = by_region.setdefault(event_lists[pos][row].region, [])
                    name = named_agents[aid]
                    if name not in names:
                        names.append(name)
            else:
                # Non-integer ids or keys: scan, as _named_actors_in_region does.
                by_region = {}
                for events in event_lists:
                    for e in events:
                        if e.agent_id in named_agents:
                            names = by_region.setdefault(e.region, [])
                            name = named_agents[e.agent_id]
                            if name not in names:
                                names.append(name)
            entry = (tuple(event_lists), named_agents, by_region)
            if memo is not None:
                memo[key] = entry
        return list(entry[2].get(region_id, ()))

    def _named_actors_in_region(self, region_id, named_agents, current_events):
        """Find named character names involved in events for a given region.

        Inside ``_aggregate_events`` each event list is scanned once into
        per-region name lists (same names, same first-seen order).
        """
        memo = getattr(self, "_named_actor_memo", None)
        if memo is None:
            actors = []
            for e in current_events:
                if e.region == region_id and e.agent_id in named_agents:
                    name = named_agents[e.agent_id]
                    if name not in actors:
                        actors.append(name)
            return actors
        key = (id(current_events), id(named_agents))
        entry = memo.get(key)
        if entry is None:
            by_region: dict = {}
            for e in current_events:
                if e.agent_id in named_agents:
                    name = named_agents[e.agent_id]
                    names = by_region.setdefault(e.region, [])
                    if name not in names:
                        names.append(name)
            # Holding the lists keeps their ids from being reused in this call.
            entry = memo[key] = (current_events, named_agents, by_region)
        return list(entry[2].get(region_id, ()))

    def _write_back(self, world: WorldState) -> None:
        """Write agent-derived stats to civ and region objects. Hybrid mode only."""
        aggs = self._sim.get_aggregates()
        region_pops = self._sim.get_region_populations()

        # Region populations from agent counts -- no clamp in hybrid mode
        pop_map = dict(zip(
            pylist(region_pops.column("region_id")),
            pylist(region_pops.column("alive_count")),
        ))
        for i, region in enumerate(world.regions):
            agent_pop = pop_map.get(i, 0)
            if agent_pop > region.carrying_capacity * 2.0:
                logger.warning(
                    "Region %d pop %d exceeds 2x capacity %d",
                    i, agent_pop, region.carrying_capacity,
                )
            region.population = agent_pop

        controlled_regions_by_civ: dict[str, list[str]] = {
            civ.name: [] for civ in world.civilizations
        }
        controlled_population_by_civ: Counter = Counter()
        for region in world.regions:
            if region.controller is None:
                continue
            if region.controller not in controlled_regions_by_civ:
                continue
            controlled_regions_by_civ[region.controller].append(region.name)
            controlled_population_by_civ[region.controller] += region.population

        # Civ stats from aggregates
        civ_ids = pylist(aggs.column("civ_id"))
        for civ in world.civilizations:
            civ.regions = controlled_regions_by_civ.get(civ.name, [])
        for row_idx, civ_id in enumerate(civ_ids):
            if civ_id >= len(world.civilizations):
                continue
            civ = world.civilizations[civ_id]
            if len(civ.regions) == 0:
                civ.population = 0
                civ.military = 0
                civ.economy = 0
                civ.culture = 0
                civ.stability = 0
                continue
            civ.population = int(controlled_population_by_civ.get(civ.name, 0))
            if civ.population < 1:
                civ.population = 1
            civ.military = aggs.column("military")[row_idx].as_py()
            civ.economy = aggs.column("economy")[row_idx].as_py()
            civ.culture = aggs.column("culture")[row_idx].as_py()
            civ.stability = min(100, max(0, aggs.column("stability")[row_idx].as_py()))

    def _apply_demographics_clamp(self, world: WorldState) -> None:
        region_pops = self._sim.get_region_populations()
        pop_map = dict(zip(
            pylist(region_pops.column("region_id")),
            pylist(region_pops.column("alive_count")),
        ))
        for i, region in enumerate(world.regions):
            if region.controller is not None:
                agent_pop = pop_map.get(i, 0)
                region.population = min(agent_pop, int(region.carrying_capacity * 1.2))

    def reset(self) -> None:
        """Clear stateful data for batch mode reuse."""
        self._event_window.clear()
        self._demand_manager.reset()
        self.named_agents.clear()
        self.gp_by_agent_id.clear()
        from chronicler.dynasties import DynastyRegistry
        self.dynasty_registry = DynastyRegistry()
        self._pending_dynasty_events.clear()
        self._origin_regions.clear()
        self._departure_turns.clear()
        self.displacement_by_region.clear()
        self._gini_by_civ.clear()
        self._wealth_stats.clear()
        self._economy_result = None
        self._relationship_stats_history.clear()
        self._household_stats_history.clear()
        self._merchant_trip_stats_history.clear()  # fix: was missing from reset()
        self._knowledge_stats_history.clear()

    def close(self) -> None:
        if self._shadow_logger:
            self._shadow_logger.close()
        if self._sidecar:
            self._sidecar.close()

    def get_snapshot(self): return self._sim.get_snapshot()
    def get_aggregates(self): return self._sim.get_aggregates()

    def read_social_edges(self) -> list[tuple]:
        """Read current social edges from Rust as a list of (agent_a, agent_b, relationship, formed_turn) tuples."""
        if self._sim is None:
            return []
        batch = self._sim.get_social_edges()
        if batch is None or batch.num_rows == 0:
            return []
        agent_a = pylist(batch.column("agent_a"))
        agent_b = pylist(batch.column("agent_b"))
        rel = pylist(batch.column("relationship"))
        formed = pylist(batch.column("formed_turn"))
        return list(zip(agent_a, agent_b, rel, formed))

    def apply_relationship_ops(self, ops: list[dict]) -> None:
        """Apply batched relationship ops to the Rust store.
        Each op: {"op_type": int, "agent_a": int, "agent_b": int,
                  "bond_type": int, "sentiment": int, "formed_turn": int}
        """
        if not ops:
            return
        arrays = [
            pa.array([o["op_type"] for o in ops], type=pa.uint8()),
            pa.array([o["agent_a"] for o in ops], type=pa.uint32()),
            pa.array([o["agent_b"] for o in ops], type=pa.uint32()),
            pa.array([o["bond_type"] for o in ops], type=pa.uint8()),
            pa.array([o.get("sentiment", 0) for o in ops], type=pa.int8()),
            pa.array([o.get("formed_turn", 0) for o in ops], type=pa.uint16()),
        ]
        batch = pa.RecordBatch.from_arrays(arrays, names=[
            "op_type", "agent_a", "agent_b", "bond_type", "sentiment", "formed_turn"
        ])
        self._sim.apply_relationship_ops(batch)
