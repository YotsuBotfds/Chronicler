"""Bridge between Python WorldState and Rust AgentSimulator."""
from __future__ import annotations
from dataclasses import dataclass
import logging
from collections import Counter, deque
from pathlib import Path
from typing import TYPE_CHECKING
import numpy as np
import pyarrow as pa
from chronicler_agents import AgentSimulator
from chronicler.demand_signals import DemandSignalManager
from chronicler.great_persons import _append_deed
from chronicler.leaders import _pick_name, strip_title, ALL_TRAITS
from chronicler.models import AgentEventRecord, CivShock, Event, GreatPerson
from chronicler.resources import get_season_step, get_season_id
from chronicler.shadow import ShadowLogger

if TYPE_CHECKING:
    from chronicler.models import WorldState

logger = logging.getLogger(__name__)

TERRAIN_MAP = {
    "plains": 0, "mountains": 1, "coast": 2,
    "forest": 3, "desert": 4, "tundra": 5,
    "river": 0,   # Maps to plains for Rust terrain modifiers
    "hills": 0,   # Maps to plains for Rust terrain modifiers
}
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
    "mass_migration": "{count} {occ_majority} fled {source_region} for {target_region}",
    "local_rebellion": "Rebellion erupted in {region} as {count} discontented {occ_majority} rose up",
    "demographic_crisis": "{region} lost {pct}% of its population over {window} turns",
    "occupation_shift": "{count} agents in {region} switched to {new_occupation}",
    "loyalty_cascade": "{count} residents of {region} shifted allegiance to {target_civ}",
    "economic_boom": "Economic boom in {region}: {count} workers switched to merchant trades over {window} turns",
    "brain_drain": "{count} scholars fled {region} over {window} turns",
}


# M36: Cultural value string → u8 index mapping (matches Rust enum order)
VALUE_TO_ID = {
    "Freedom": 0, "Order": 1, "Tradition": 2,
    "Knowledge": 3, "Honor": 4, "Cunning": 5,
}
VALUE_EMPTY = 0xFF

VALUE_PERSONALITY_MAP = {
    "Honor":     ( 0.15,  0.0,   0.0),
    "Freedom":   ( 0.15,  0.0,   0.0),
    "Cunning":   ( 0.0,   0.15,  0.0),
    "Knowledge": ( 0.0,   0.15,  0.0),
    "Tradition": ( 0.0,   0.0,   0.15),
    "Order":     ( 0.0,   0.0,   0.15),
}

DOMAIN_PERSONALITY_MAP = {
    "military": ( 0.10,  0.0,   0.0),
    "trade":    ( 0.0,   0.10,  0.0),
    "merchant": ( 0.0,   0.10,  0.0),
}


@dataclass(frozen=True, slots=True)
class AgentMemoryRecord:
    event_type: int
    source_civ: int
    turn: int
    intensity: int
    decay_factor: int
    is_legacy: bool = False


def compute_gini(wealth_array: np.ndarray) -> float:
    """Gini coefficient from a 1D array of non-negative values."""
    sorted_w = np.sort(wealth_array)
    n = len(sorted_w)
    if n == 0 or sorted_w.sum() == 0:
        return 0.0
    index = np.arange(1, n + 1)
    return float((2.0 * (index * sorted_w).sum() / (n * sorted_w.sum())) - (n + 1) / n)


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
    civ = next((c for c in world.civilizations if c.name == region.controller), None)
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


def build_region_batch(world: WorldState, economy_result=None) -> pa.RecordBatch:
    """Build extended region state Arrow batch (M26: adds controller, adjacency, etc.)."""
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}
    if len(world.regions) > 32:
        raise ValueError(
            "build_region_batch supports at most 32 regions (adjacency_mask is uint32)"
        )

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

    def _controller_values(region):
        """Denormalize controller civ's cultural values into per-region columns."""
        if region.controller is None:
            return [VALUE_EMPTY, VALUE_EMPTY, VALUE_EMPTY]
        ctrl_civ = next((c for c in world.civilizations if c.name == region.controller), None)
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
            civ_idx = next(
                (j for j, c in enumerate(world.civilizations) if c.name == civ_name),
                None,
            )
            if civ_idx is not None and civ_idx < len(world.belief_registry):
                initial_belief_arr.append(world.belief_registry[civ_idx].faith_id)
            else:
                initial_belief_arr.append(0xFF)
        else:
            initial_belief_arr.append(0xFF)

    def _has_temple(region, world):
        from chronicler.models import InfrastructureType
        controller_name = region.controller
        if controller_name is None:
            return False
        controller = next((c for c in world.civilizations if c.name == controller_name), None)
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
    for r in world.regions:
        r._controller_changed_this_turn = False
        r._war_won_this_turn = False
        r._seceded_this_turn = False

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
        # M35a: River mask
        "river_mask": pa.array([r.river_mask for r in world.regions], type=pa.uint32()),
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
        # M48: Per-region transient memory signals
        "controller_changed_this_turn": pa.array(controller_changed_vals, type=pa.bool_()),
        "war_won_this_turn": pa.array(war_won_vals, type=pa.bool_()),
        "seceded_this_turn": pa.array(seceded_vals, type=pa.bool_()),
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
    })


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
    dom_factions, fac_mil, fac_mer, fac_cul, fac_cle = [], [], [], [], []

    # Shock / demand column builders
    shock_map = {s.civ_id: s for s in (shocks or [])}
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
        fac_mil.append(civ.factions.influence.get(FactionType.MILITARY, 0.33))
        fac_mer.append(civ.factions.influence.get(FactionType.MERCHANT, 0.33))
        fac_cul.append(civ.factions.influence.get(FactionType.CULTURAL, 0.34))
        fac_cle.append(civ.factions.influence.get(FactionType.CLERGY, 0.08))

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

        civ_values = getattr(civ, 'values', [])
        civ_domains = getattr(civ, 'domains', [])
        pm = civ_personality_mean(civ_values, civ_domains)
        mean_bold.append(pm[0])
        mean_ambi.append(pm[1])
        mean_ltrait.append(pm[2])
        conquered_flags.append((conquered or {}).get(i, False))
        gini_vals.append((gini_by_civ or {}).get(i, 0.0))
        priest_tithe_shares.append(
            (economy_result.priest_tithe_shares.get(i, 0.0) if economy_result else 0.0)
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
            [get_multiplier(world, K_CULTURAL_DRIFT_SPEED)] * n_civs, type=pa.float32(),
        ),
        "religion_intensity_multiplier": pa.array(
            [get_multiplier(world, K_RELIGION_INTENSITY)] * n_civs, type=pa.float32(),
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


class AgentBridge:
    def __init__(self, world: WorldState, mode: str = "demographics-only",
                 shadow_output: Path | None = None,
                 validation_sidecar: bool = False,
                 output_dir: Path | None = None,
                 relationship_stats: bool = False):
        self._sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
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

    def _refresh_snapshot_metrics(self, world: "WorldState") -> None:
        """Update displacement, Gini, and wealth stats from the current snapshot."""
        try:
            snap = self._sim.get_snapshot()
            regions_col = snap.column("region").to_pylist()
            disp_col = snap.column("displacement_turn").to_pylist()
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

            wealth_col = snap.column("wealth").to_numpy()
            civ_col = np.array(
                self._resolve_polity_civ_ids(
                    world,
                    regions_col,
                    snap.column("civ_affinity").to_pylist(),
                ),
                dtype=np.int64,
            )
            new_gini: dict[int, float] = {}
            for civ_id in np.unique(civ_col):
                mask = civ_col == civ_id
                civ_wealth = wealth_col[mask]
                new_gini[int(civ_id)] = compute_gini(civ_wealth)
            occ_col = snap.column("occupation").to_numpy()
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
        except Exception:
            # Preserve prior values on failure â€” one bad turn must not wipe
            # accumulated history.
            logger.exception("Failed to compute displacement/Gini/wealth stats from snapshot")

    @property
    def ecology_simulator(self):
        """Expose the Rust simulator handle for ecology tick in agent modes."""
        return self._sim

    def sync_regions(self, world: WorldState) -> None:
        """Phase 1 of the split bridge: full region sync to Rust.

        Must be called exactly once per turn BEFORE ecology tick or agent tick.
        """
        self._sim.set_region_state(build_region_batch(world, self._economy_result))
        # M56b: Send settlement footprints for urban classification
        settlement_batch = build_settlement_batch(world)
        self._sim.set_settlement_footprints(settlement_batch)

    def tick_agents(self, world: WorldState, shocks=None, demands=None, conquered=None) -> list:
        """Phase 2 of the split bridge: send signals and run agent tick.

        Assumes sync_regions() was already called this turn.
        Does NOT call set_region_state() again.
        """
        # M58a: Sync merchant route graph before tick
        from chronicler.economy import build_merchant_route_graph
        route_batch = build_merchant_route_graph(world)
        self._sim.set_merchant_route_graph(route_batch)

        signals = build_signals(world, shocks=shocks, demands=demands, conquered=conquered,
                                gini_by_civ=self._gini_by_civ, economy_result=self._economy_result)
        agent_events = self._sim.tick(world.turn, signals)
        return self._process_tick_results(agent_events, world)

    def tick(self, world: WorldState, shocks=None, demands=None, conquered=None) -> list:
        """Compatibility wrapper: full sync + agent tick in one call.

        Use sync_regions() + tick_agents() separately when ecology runs between them.
        """
        self.sync_regions(world)

        # M58a: Sync merchant route graph before tick
        from chronicler.economy import build_merchant_route_graph
        route_batch = build_merchant_route_graph(world)
        self._sim.set_merchant_route_graph(route_batch)

        signals = build_signals(world, shocks=shocks, demands=demands, conquered=conquered,
                                gini_by_civ=self._gini_by_civ, economy_result=self._economy_result)
        agent_events = self._sim.tick(world.turn, signals)
        return self._process_tick_results(agent_events, world)

    def _process_tick_results(self, agent_events, world: WorldState) -> list:
        """Shared post-tick processing for both tick() and tick_agents()."""
        # M53: relationship stats collection (all modes)
        if self._collect_rel_stats:
            try:
                stats = self._sim.get_relationship_stats()
                self._relationship_stats_history.append(stats)
            except Exception:
                logger.exception("Failed to collect relationship stats from Rust tick")

        # M57b: household stats collection (always in agent modes)
        try:
            h_stats = self._sim.get_household_stats()
            self._household_stats_history.append(h_stats)
        except Exception:
            logger.exception("Failed to collect household stats from Rust tick")

        # M58a: merchant trip stats collection
        try:
            m_stats = self._sim.get_merchant_trip_stats()
            self._merchant_trip_stats_history.append(m_stats)
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
            }
            normalized_k_stats = {}
            for key, value in k_stats.items():
                normalized_k_stats[key] = int(value) if key in int_keys else float(value)
            normalized_k_stats["created_by_type"] = created_by_type
            normalized_k_stats["transmitted_by_type"] = transmitted_by_type
            self._knowledge_stats_history.append(normalized_k_stats)
        except Exception:
            logger.exception("Failed to collect knowledge stats from Rust tick")

        self._refresh_snapshot_metrics(world)

        if self._mode == "hybrid":
            self._write_back(world)
            # M30 processing order
            promotions_batch = self._sim.get_promotions()
            self._process_promotions(promotions_batch, world)  # step 1

            # Compute displacement fractions from snapshot
            try:
                snap = self._sim.get_snapshot()
                regions_col = snap.column("region").to_pylist()
                disp_col = snap.column("displacement_turn").to_pylist()
                region_totals = Counter(regions_col)
                region_displaced: Counter = Counter()
                for r, d in zip(regions_col, disp_col):
                    if d > 0:
                        region_displaced[r] += 1
                self.displacement_by_region = {
                    r: region_displaced[r] / total if total > 0 else 0.0
                    for r, total in region_totals.items()
                }
                # M41: compute per-civ Gini from wealth snapshot (hybrid mode only)
                if "wealth" in snap.schema.names:
                    wealth_col = snap.column("wealth").to_numpy()
                    civ_col = np.array(
                        self._resolve_polity_civ_ids(
                            world,
                            regions_col,
                            snap.column("civ_affinity").to_pylist(),
                        ),
                        dtype=np.int64,
                    )
                    new_gini: dict[int, float] = {}
                    for civ_id in np.unique(civ_col):
                        mask = civ_col == civ_id
                        civ_wealth = wealth_col[mask]
                        new_gini[int(civ_id)] = compute_gini(civ_wealth)
                    self._gini_by_civ = new_gini
                    occ_col = snap.column("occupation").to_numpy()
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
                            "gini": self._gini_by_civ.get(int(civ_id), 0.0),
                            "mean": float(np.mean(civ_wealth)),
                            "median": float(np.median(civ_wealth)),
                            "std": float(np.std(civ_wealth)),
                            "by_occupation": wealth_by_occ,
                        }
                    self._wealth_stats = stats
            except Exception:
                # Preserve prior Gini/wealth values on failure — one bad turn
                # must not wipe accumulated history (H-18 audit fix).
                self.displacement_by_region = {}
                logger.exception("Failed to compute displacement/Gini/wealth stats from snapshot")

            raw_events = self._convert_events(agent_events, world.turn)
            world._dead_agents_this_turn = [e for e in raw_events if e.event_type == "death"]
            death_events = self._process_deaths(raw_events, world)  # step 2
            world.agent_events_raw.extend(raw_events)

            # M50b: collect dissolution events from Rust tick
            dissolution_events = [e for e in raw_events if e.event_type == "dissolution"]
            if dissolution_events:
                dissolved_list = world.dissolved_edges_by_turn.get(world.turn, [])
                for e in dissolution_events:
                    # target_region field repurposed as bond_type in dissolution events
                    dissolved_list.append(
                        (e.agent_id, 0, e.target_region, world.turn)
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
                agent_ids = rel_batch.column("agent_id").to_pylist()
                target_ids = rel_batch.column("target_id").to_pylist()
                bond_types = rel_batch.column("bond_type").to_pylist()
                sentiments = rel_batch.column("sentiment").to_pylist()
                for i in range(len(agent_ids)):
                    edges.append((agent_ids[i], target_ids[i], bond_types[i], sentiments[i]))
        except Exception:
            edges = []
            logger.exception("Sidecar graph snapshot: failed to read relationships")

        try:
            mem_batch = self._sim.get_all_memories()
            mem_sigs: dict = {}
            if mem_batch.num_rows > 0:
                m_agent_ids = mem_batch.column("agent_id").to_pylist()
                m_event_types = mem_batch.column("event_type").to_pylist()
                m_turns = mem_batch.column("turn").to_pylist()
                m_intensities = mem_batch.column("intensity").to_pylist()
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
                    name: needs_batch.column(name).to_pylist()
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
                id_list = snap.column("id").to_pylist()
                civ_list = snap.column("civ_affinity").to_pylist()
                sat_list = snap.column("satisfaction").to_pylist()
                occ_list = snap.column("occupation").to_pylist()
                region_list = snap.column("region").to_pylist()
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

                id_list = snap.column("id").to_pylist()
                region_list = snap.column("region").to_pylist()
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
        """Convert Arrow events RecordBatch to AgentEventRecord list."""
        records = []
        belief_col = batch.column("belief") if "belief" in batch.schema.names else None
        for i in range(batch.num_rows):
            event_type_code = batch.column("event_type")[i].as_py()
            records.append(AgentEventRecord(
                turn=turn,
                agent_id=batch.column("agent_id")[i].as_py(),
                event_type=EVENT_TYPE_MAP.get(event_type_code, f"unknown_{event_type_code}"),
                region=batch.column("region")[i].as_py(),
                target_region=batch.column("target_region")[i].as_py(),
                civ_affinity=batch.column("civ_affinity")[i].as_py(),
                occupation=batch.column("occupation")[i].as_py(),
                belief=belief_col[i].as_py() if belief_col is not None else None,
            ))
        return records

    def _process_promotions(self, batch, world) -> list:
        """Process promotion RecordBatch → create GreatPerson instances.

        Also checks Python-side bypass triggers that Rust cannot evaluate:
        - Long displacement (50+ turns away from origin) → Exile
        - Serial migrant (3+ region changes) → Merchant
        - Occupation versatility (3+ switches) → Scientist
        These are checked against agent_events_raw history when the Rust-side
        trigger is 0 (skill-based), to see if a more specific role applies.
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
            if role is None:
                logger.warning("Unknown role_id %d for agent %d, skipping promotion", role_id, agent_id)
                continue

            # Python-side bypass: check event history for displacement / migrant / versatility
            if trigger == 0:  # skill-based — check if a bypass applies
                migration_events = [
                    e for e in world.agent_events_raw
                    if e.agent_id == agent_id and e.event_type == "migration"
                ]
                switch_count = sum(
                    1 for e in world.agent_events_raw
                    if e.agent_id == agent_id and e.event_type == "occupation_switch"
                )
                # Long displacement: 50+ turns since first migration away from origin
                if (migration_events
                        and agent_id in self._origin_regions
                        and agent_id in self._departure_turns
                        and (world.turn - self._departure_turns[agent_id]) >= 50):
                    role = "exile"
                elif len(migration_events) >= 3:
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
            region_name = world.regions[origin_region].name if origin_region < len(world.regions) else "unknown"
            _append_deed(gp, f"Promoted as {role} in {region_name}")
            civ.great_persons.append(gp)
            created.append(gp)
            self.named_agents[agent_id] = name
            self.gp_by_agent_id[agent_id] = gp
            dynasty_events = self.dynasty_registry.check_promotion(
                gp, self.named_agents, self.gp_by_agent_id,
            )
            for de in dynasty_events:
                de.turn = world.turn
                self._pending_dynasty_events.append(de)
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
                            _append_deed(gp, f"Mule: shaped by memory type {event_type}")

            # M52: GP artifact intent
            from chronicler.artifacts import emit_gp_artifact_intent
            emit_gp_artifact_intent(world, civ, gp)

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
                    ))
                    if e.agent_id in self.gp_by_agent_id:
                        _append_deed(self.gp_by_agent_id[e.agent_id], f"Returned to {target_name} after {turns_away} turns")
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
            ))
            if e.agent_id in self.gp_by_agent_id:
                _append_deed(self.gp_by_agent_id[e.agent_id], f"Migrated from {source_name} to {target_name}")

        return character_events

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
            _append_deed(gp, f"Exiled after conquest of {gp.region or conquered_civ.name}")

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
                importance=5, source="agent",
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
            _append_deed(gp, f"Defected to {new_civ.name} during secession")

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
                importance=5, source="agent",
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
            _append_deed(gp, f"Returned to {restored_civ.name} during restoration")

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
            _append_deed(gp, f"Absorbed into {absorber_civ.name} during twilight absorption")

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

        agent_ids = snapshot.column("id").to_pylist()
        region_ids = snapshot.column("region").to_pylist()
        civ_ids = snapshot.column("civ_affinity").to_pylist()

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

    def _aggregate_events(self, world, named_agents=None):
        """Check thresholds and emit summary Events."""
        if named_agents is None:
            named_agents = {}
        summaries = []
        current = list(self._event_window)[-1] if self._event_window else []
        region_names = {i: r.name for i, r in enumerate(world.regions)}

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
                summaries.append(Event(
                    turn=world.turn, event_type="mass_migration",
                    actors=self._named_actors_in_region(region_id, named_agents, current),
                    description=SUMMARY_TEMPLATES["mass_migration"].format(
                        count=len(events), occ_majority=occ_majority,
                        source_region=region_names.get(region_id, f"region {region_id}"),
                        target_region=region_names.get(target_id, f"region {target_id}"),
                    ),
                    importance=5, source="agent",
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
                    importance=7, source="agent",
                ))

        # Occupation shift: >25% of region switches in one tick
        for region_id, events in switches_by_region.items():
            region_pop = sum(1 for e in current if e.region == region_id)
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
                    importance=5, source="agent",
                ))

        # === Multi-turn patterns ===

        # Loyalty cascade: >=10 agents flip in one region over 5 turns
        loyalty_flips_by_region = {}
        window_depth = min(len(self._event_window), 5)
        window_list = list(self._event_window)
        for turn_events in window_list[-window_depth:]:
            for e in turn_events:
                if e.event_type == "loyalty_flip":
                    loyalty_flips_by_region[e.region] = loyalty_flips_by_region.get(e.region, 0) + 1
        for region_id, count in loyalty_flips_by_region.items():
            if count >= 10:
                recent_flips = [
                    e for turn_events in window_list[-window_depth:]
                    for e in turn_events
                    if e.event_type == "loyalty_flip" and e.region == region_id
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
                ))

        # Demographic crisis: region loses >30% over window
        if len(self._event_window) >= 2:
            deaths_by_region = {}
            births_by_region = {}
            for turn_events in self._event_window:
                for e in turn_events:
                    if e.event_type == "death":
                        deaths_by_region[e.region] = deaths_by_region.get(e.region, 0) + 1
                    elif e.event_type == "birth":
                        births_by_region[e.region] = births_by_region.get(e.region, 0) + 1
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
                                importance=7, source="agent",
                            ))

        # === M30 new event types ===

        # Economic boom: >=10 occupation switches TO merchant over 20-turn window
        # [CALIBRATE: post-M28, initial 10]
        merchant_switches_by_region = {}
        boom_window = min(len(self._event_window), 20)
        boom_events = [e for t in list(self._event_window)[-boom_window:] for e in t]
        for e in boom_events:
            if e.event_type == "occupation_switch" and e.occupation == 2:  # merchant
                merchant_switches_by_region[e.region] = \
                    merchant_switches_by_region.get(e.region, 0) + 1
        for region_id, count in merchant_switches_by_region.items():
            if count >= 10:
                summaries.append(Event(
                    turn=world.turn, event_type="economic_boom",
                    actors=self._named_actors_in_region(region_id, named_agents, boom_events),
                    description=SUMMARY_TEMPLATES["economic_boom"].format(
                        region=region_names.get(region_id, f"region {region_id}"),
                        count=count, window=boom_window,
                    ),
                    importance=5, source="agent",
                ))

        # Brain drain: >=5 scholars leave region over 10-turn window
        # [CALIBRATE: post-M28, initial 5]
        scholar_departures_by_region = {}
        drain_window = min(len(self._event_window), 10)
        drain_events = [e for t in list(self._event_window)[-drain_window:] for e in t]
        for e in drain_events:
            if e.event_type == "migration" and e.occupation == 3:  # scholar
                scholar_departures_by_region[e.region] = \
                    scholar_departures_by_region.get(e.region, 0) + 1
        for region_id, count in scholar_departures_by_region.items():
            if count >= 5:
                summaries.append(Event(
                    turn=world.turn, event_type="brain_drain",
                    actors=self._named_actors_in_region(region_id, named_agents, drain_events),
                    description=SUMMARY_TEMPLATES["brain_drain"].format(
                        count=count,
                        region=region_names.get(region_id, f"region {region_id}"),
                        window=drain_window,
                    ),
                    importance=5, source="agent",
                ))

        return summaries

    def _named_actors_in_region(self, region_id, named_agents, current_events):
        """Find named character names involved in events for a given region."""
        actors = []
        for e in current_events:
            if e.region == region_id and e.agent_id in named_agents:
                name = named_agents[e.agent_id]
                if name not in actors:
                    actors.append(name)
        return actors

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
        civ_ids = aggs.column("civ_id").to_pylist()
        for civ in world.civilizations:
            civ.regions = controlled_regions_by_civ.get(civ.name, [])
        for row_idx, civ_id in enumerate(civ_ids):
            if civ_id >= len(world.civilizations):
                continue
            civ = world.civilizations[civ_id]
            if len(civ.regions) == 0:
                civ.population = 0
                continue
            civ.population = int(controlled_population_by_civ.get(civ.name, 0))
            if civ.population < 1:
                civ.population = 1
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
        agent_a = batch.column("agent_a").to_pylist()
        agent_b = batch.column("agent_b").to_pylist()
        rel = batch.column("relationship").to_pylist()
        formed = batch.column("formed_turn").to_pylist()
        return list(zip(agent_a, agent_b, rel, formed))

    def replace_social_edges(self, edges: list[tuple]) -> None:
        """Replace all social edges in Rust. Each edge is (agent_a, agent_b, relationship, formed_turn)."""
        if self._sim is None:
            return
        if not edges:
            batch = pa.RecordBatch.from_arrays([
                pa.array([], type=pa.uint32()),
                pa.array([], type=pa.uint32()),
                pa.array([], type=pa.uint8()),
                pa.array([], type=pa.uint16()),
            ], names=["agent_a", "agent_b", "relationship", "formed_turn"])
        else:
            agent_a, agent_b, rel, formed = zip(*edges)
            batch = pa.record_batch([
                pa.array(agent_a, type=pa.uint32()),
                pa.array(agent_b, type=pa.uint32()),
                pa.array(rel, type=pa.uint8()),
                pa.array(formed, type=pa.uint16()),
            ], names=["agent_a", "agent_b", "relationship", "formed_turn"])
        self._sim.replace_social_edges(batch)

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
