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
FACTION_MAP = {"military": 0, "merchant": 1, "cultural": 2, "clergy": 3}

EVENT_TYPE_MAP = {0: "death", 1: "rebellion", 2: "migration",
                  3: "occupation_switch", 4: "loyalty_flip", 5: "birth",
                  6: "dissolution"}
OCCUPATION_NAMES = {0: "farmers", 1: "soldiers", 2: "merchants", 3: "scholars", 4: "priests"}
ROLE_MAP = {0: "general", 1: "merchant", 2: "scientist", 3: "prophet", 4: "exile"}

# M48: Mule promotion constants [CALIBRATE M53]
MULE_PROMOTION_PROBABILITY = 0.12  # raised from 0.07: GP promotion is bursty, need higher rate to land Mules in >50% of seeds
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
    """Read yield from ecology module's last computation, or 0.0."""
    from chronicler.ecology import _last_region_yields
    ry = _last_region_yields.get(region.name)
    if ry is not None:
        return ry[slot]
    return 0.0


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
        "merchant_trade_income": pa.array(
            [economy_result.merchant_trade_incomes.get(r.name, 0.0) if economy_result else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        # M48: Per-region transient memory signals
        "controller_changed_this_turn": pa.array(controller_changed_vals, type=pa.bool_()),
        "war_won_this_turn": pa.array(war_won_vals, type=pa.bool_()),
        "seceded_this_turn": pa.array(seceded_vals, type=pa.bool_()),
    })


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


class AgentBridge:
    def __init__(self, world: WorldState, mode: str = "demographics-only",
                 shadow_output: Path | None = None,
                 validation_sidecar: bool = False,
                 output_dir: Path | None = None,
                 relationship_stats: bool = False):
        self._sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
        self._mode = mode
        self._event_window: deque = deque(maxlen=10)  # sliding window for event aggregation
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

    def set_economy_result(self, result):
        """Store M42 economy result for signal wiring."""
        self._economy_result = result

    def tick(self, world: WorldState, shocks=None, demands=None, conquered=None) -> list:
        self._sim.set_region_state(build_region_batch(world, self._economy_result))
        signals = build_signals(world, shocks=shocks, demands=demands, conquered=conquered,
                                gini_by_civ=self._gini_by_civ, economy_result=self._economy_result)
        agent_events = self._sim.tick(world.turn, signals)

        # M53: relationship stats collection (all modes)
        if self._collect_rel_stats:
            try:
                stats = self._sim.get_relationship_stats()
                self._relationship_stats_history.append(stats)
            except Exception:
                pass

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
                    civ_col = snap.column("civ_affinity").to_numpy()
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
                self.displacement_by_region = {}

            raw_events = self._convert_events(agent_events, world.turn)
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
            return summaries + char_events + death_events + dynasty_events
        elif self._mode == "shadow":
            agent_aggs = self._sim.get_aggregates()
            if self._shadow_logger:
                self._shadow_logger.log_turn(world.turn, agent_aggs, world)
            # M30 processing order (still track promotions in shadow mode)
            promotions_batch = self._sim.get_promotions()
            self._process_promotions(promotions_batch, world)
            raw_events = self._convert_events(agent_events, world.turn)
            self._process_deaths(raw_events, world)
            world.agent_events_raw.extend(raw_events)
            self._event_window.append(raw_events)
            # M53: sidecar snapshot (shadow mode)
            if self._sidecar and world.turn % 10 == 0:
                self._write_sidecar_snapshot(world)
            return []
        elif self._mode == "demographics-only":
            self._apply_demographics_clamp(world)
            # M53: sidecar snapshot (demographics-only mode)
            if self._sidecar and world.turn % 10 == 0:
                self._write_sidecar_snapshot(world)
            return []
        return []

    @property
    def relationship_stats(self) -> list:
        """M53: Per-tick relationship stats history (populated when --relationship-stats is set)."""
        return self._relationship_stats_history

    def _write_sidecar_snapshot(self, world: "WorldState") -> None:
        """M53: Write validation sidecar data at sample points (every 10 turns)."""
        turn = world.turn

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

        self._sidecar.write_graph_snapshot(turn=turn, edges=edges, memory_signatures=mem_sigs)

        # Needs snapshot
        try:
            needs_batch = self._sim.get_all_needs()
            self._sidecar.write_needs_snapshot(turn=turn, needs_batch=needs_batch)
        except Exception:
            pass

        # Agent aggregate: per-civ satisfaction mean/std from snapshot
        try:
            snap = self._sim.get_snapshot()
            agg: dict = {}
            if snap.num_rows > 0:
                from collections import defaultdict
                civ_data: dict = defaultdict(lambda: {"sats": []})
                civ_list = snap.column("civ_affinity").to_pylist()
                sat_list = snap.column("satisfaction").to_pylist()
                for i in range(len(civ_list)):
                    civ_data[civ_list[i]]["sats"].append(sat_list[i])
                for civ, cd in civ_data.items():
                    sats = cd["sats"]
                    n = len(sats)
                    mean_sat = sum(sats) / n if n > 0 else 0.0
                    std_sat = (sum((s - mean_sat) ** 2 for s in sats) / n) ** 0.5 if n > 1 else 0.0
                    agg[f"civ_{civ}"] = {
                        "satisfaction_mean": round(mean_sat, 4),
                        "satisfaction_std": round(std_sat, 4),
                        "agent_count": n,
                    }
            self._sidecar.write_agent_aggregate(turn=turn, aggregates=agg)
        except Exception:
            pass

    def _convert_events(self, batch, turn):
        """Convert Arrow events RecordBatch to AgentEventRecord list."""
        records = []
        for i in range(batch.num_rows):
            records.append(AgentEventRecord(
                turn=turn,
                agent_id=batch.column("agent_id")[i].as_py(),
                event_type=EVENT_TYPE_MAP[batch.column("event_type")[i].as_py()],
                region=batch.column("region")[i].as_py(),
                target_region=batch.column("target_region")[i].as_py(),
                civ_affinity=batch.column("civ_affinity")[i].as_py(),
                occupation=batch.column("occupation")[i].as_py(),
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
            parent_id = batch.column("parent_id")[i].as_py()
            role_id = batch.column("role")[i].as_py()
            trigger = batch.column("trigger")[i].as_py()
            origin_region = batch.column("origin_region")[i].as_py()
            role = ROLE_MAP[role_id]

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

            # Pick civ — use origin_region's controller
            civ = world.civilizations[0]
            if origin_region < len(world.regions):
                controller = world.regions[origin_region].controller
                if controller:
                    for c in world.civilizations:
                        if c.name == controller:
                            civ = c
                            break

            rng = random.Random(world.seed + world.turn + agent_id)
            name = _pick_name(civ, world, rng)
            trait = rng.choice(ALL_TRAITS)

            gp = GreatPerson(
                name=name,
                role=role,
                trait=trait,
                civilization=civ.name,
                origin_civilization=civ.name,
                born_turn=world.turn,
                source="agent",
                agent_id=agent_id,
                parent_id=parent_id,
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
                    pass
            else:
                # In surviving territory → refugee, not captured
                gp.captured_by = None
                host_id = host_civ_ids.get(gp.region, conqueror_civ_id)
                try:
                    self._sim.set_agent_civ(gp.agent_id, host_id)
                except Exception:
                    pass

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
                                    turn: int = 0) -> list:
        """Transition agent-source named characters on secession."""
        from chronicler.models import Event

        events = []
        seceding_set = set(seceding_regions)

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

            try:
                self._sim.set_agent_civ(gp.agent_id, new_civ_id)
            except Exception:
                pass

            events.append(Event(
                turn=turn,
                event_type="secession_defection",
                actors=[gp.name, old_civ.name, new_civ.name],
                description=f"{gp.name} defected with the secession of {gp.region}",
                importance=5, source="agent",
            ))

        return events

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

        # Build region-name lookup for civ population sums
        region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}

        # Civ stats from aggregates
        civ_ids = aggs.column("civ_id").to_pylist()
        for row_idx, civ_id in enumerate(civ_ids):
            if civ_id >= len(world.civilizations):
                continue
            civ = world.civilizations[civ_id]
            if len(civ.regions) == 0:
                continue  # Skip dead civs whose agents haven't loyalty-flipped
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
        self.named_agents.clear()
        self.gp_by_agent_id.clear()
        from chronicler.dynasties import DynastyRegistry
        self.dynasty_registry = DynastyRegistry()
        self._pending_dynasty_events.clear()
        self._origin_regions.clear()
        self._departure_turns.clear()
        self.displacement_by_region.clear()

    def close(self) -> None:
        if self._shadow_logger:
            self._shadow_logger.close()

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
