"""Core data models for the civilization chronicle generator.

WorldState is the single source of truth. All simulation and narrative
modules read from and write to WorldState, which serializes to JSON.
"""
from __future__ import annotations

# Keep field available to existing models module callers.
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_serializer, model_validator

from chronicler.experimental.fisheries import FisheryConfig
from chronicler.governance_state import CivGovernance, GovernanceSettings
from chronicler.contact_ledger import ContactLedgerState
from chronicler.epidemiology import EpidemicState
from chronicler.finance import FinanceState
from chronicler.diplomacy_state import DiplomacyState, DiplomaticMemory
from chronicler.techniques_state import TechniqueState
from chronicler.maritime_state import MaritimeState
from chronicler.gp_agendas_state import GPAgendaState
from chronicler.nomads_state import NomadState

StockFraction = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


def _omit_dormant_governance(model: BaseModel, data):
    """Drop a ``None`` governance field so feature-off output stays byte-identical."""
    if isinstance(data, dict) and getattr(model, "governance", None) is None:
        data.pop("governance", None)
    return data


def _omit_dormant_contact_ledger(model: BaseModel, data):
    """Drop a ``None`` contact ledger so feature-off output stays byte-identical."""
    if isinstance(data, dict) and getattr(model, "contact_ledger", None) is None:
        data.pop("contact_ledger", None)
    return data


def _omit_dormant_finance(model: BaseModel, data):
    """Drop a ``None`` finance state so feature-off output stays byte-identical."""
    if isinstance(data, dict) and getattr(model, "finance", None) is None:
        data.pop("finance", None)
    return data


def _omit_none_fields(model: BaseModel, data, names: tuple[str, ...]):
    """Drop optional fields that are ``None`` (dormant feature state)."""
    if isinstance(data, dict):
        for name in names:
            if name in data and getattr(model, name, None) is None:
                del data[name]
    return data


# --- Enums ---

class TechEra(str, Enum):
    TRIBAL = "tribal"
    BRONZE = "bronze"
    IRON = "iron"
    CLASSICAL = "classical"
    MEDIEVAL = "medieval"
    RENAISSANCE = "renaissance"
    INDUSTRIAL = "industrial"
    INFORMATION = "information"


class Resource(str, Enum):
    GRAIN = "grain"
    TIMBER = "timber"
    IRON = "iron"
    FUEL = "fuel"
    STONE = "stone"
    RARE_MINERALS = "rare_minerals"


class ResourceType(int, Enum):
    """M34: Concrete resource types collapsed by mechanical equivalence."""
    GRAIN = 0
    TIMBER = 1
    BOTANICALS = 2
    FISH = 3
    SALT = 4
    ORE = 5
    PRECIOUS = 6
    EXOTIC = 7


EMPTY_SLOT = 255

# Mechanical class groupings for yield formula dispatch
FOOD_TYPES = frozenset({ResourceType.GRAIN, ResourceType.FISH, ResourceType.BOTANICALS, ResourceType.EXOTIC})
MINERAL_TYPES = frozenset({ResourceType.ORE, ResourceType.PRECIOUS})

# M37: Religion constants
DOCTRINE_THEOLOGY = 0
DOCTRINE_ETHICS = 1
DOCTRINE_STANCE = 2
DOCTRINE_OUTREACH = 3
DOCTRINE_STRUCTURE = 4


class Disposition(str, Enum):
    HOSTILE = "hostile"
    SUSPICIOUS = "suspicious"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    ALLIED = "allied"


class FactionType(str, Enum):
    MILITARY = "military"
    MERCHANT = "merchant"
    CULTURAL = "cultural"
    CLERGY = "clergy"


class Belief(BaseModel):
    """A faith in the world's belief registry."""
    faith_id: int = 0
    name: str
    civ_origin: int  # civ index that founded this faith
    doctrines: list[int] = Field(min_length=5, max_length=5)
    # [Theology, Ethics, Stance, Outreach, Structure], each -1/0/+1


class FactionState(BaseModel):
    influence: dict[FactionType, float] = Field(
        default_factory=lambda: {
            FactionType.MILITARY: 0.25,
            FactionType.MERCHANT: 0.25,
            FactionType.CULTURAL: 0.25,
            FactionType.CLERGY: 0.25,
        }
    )
    power_struggle: bool = False
    power_struggle_turns: int = 0
    power_struggle_cooldown: int = 0  # M19b: turns until next struggle eligible
    pending_faction_shift: str | None = Field(
        default=None,
        exclude=True,
    )  # M19b: transient post-normalization shift signal

    @model_validator(mode="after")
    def _ensure_clergy(self) -> "FactionState":
        if FactionType.CLERGY not in self.influence:
            self.influence[FactionType.CLERGY] = 0.08  # floor
        return self


class ActionType(str, Enum):
    EXPAND = "expand"
    DEVELOP = "develop"
    TRADE = "trade"
    DIPLOMACY = "diplomacy"
    WAR = "war"
    BUILD = "build"
    EMBARGO = "embargo"
    MOVE_CAPITAL = "move_capital"
    FUND_INSTABILITY = "fund_instability"
    EXPLORE = "explore"
    INVEST_CULTURE = "invest_culture"


class InfrastructureType(str, Enum):
    ROADS = "roads"
    FORTIFICATIONS = "fortifications"
    IRRIGATION = "irrigation"
    PORTS = "ports"
    MINES = "mines"
    TEMPLES = "temples"


class ArtifactType(str, Enum):
    RELIC = "relic"
    WEAPON = "weapon"
    MONUMENT = "monument"
    ARTWORK = "artwork"
    TREATISE = "treatise"
    MANIFESTO = "manifesto"
    TRADE_GOOD = "trade_good"


class ArtifactStatus(str, Enum):
    ACTIVE = "active"
    LOST = "lost"
    DESTROYED = "destroyed"


class ClimatePhase(str, Enum):
    TEMPERATE = "temperate"
    WARMING = "warming"
    DROUGHT = "drought"
    COOLING = "cooling"


class ActionCategory(str, Enum):
    AUTOMATIC = "automatic"
    DELIBERATE = "deliberate"
    REACTION = "reaction"


class SettlementStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DISSOLVING = "dissolving"
    DISSOLVED = "dissolved"


class Infrastructure(BaseModel):
    type: InfrastructureType
    builder_civ: str
    built_turn: int
    active: bool = True
    faith_id: int = -1
    temple_prestige: int = 0


class Artifact(BaseModel):
    artifact_id: int
    name: str
    artifact_type: ArtifactType
    anchored: bool
    origin_turn: int
    origin_event: str
    origin_region: str
    creator_name: str | None
    creator_civ: str
    owner_civ: str | None
    holder_name: str | None
    holder_born_turn: int | None
    anchor_region: str | None
    prestige_value: int
    status: ArtifactStatus
    history: list[str] = Field(default_factory=list)
    mule_origin: bool = False


class PendingBuild(BaseModel):
    type: InfrastructureType
    builder_civ: str
    started_turn: int
    turns_remaining: int
    faith_id: int = -1


class ClimateConfig(BaseModel):
    period: int = 75
    severity: float = 1.0
    start_phase: ClimatePhase = ClimatePhase.TEMPERATE
    phase_offset: int = 0  # M18: supervolcano advances climate by incrementing this


# --- Core entities ---

class RegionEcology(BaseModel):
    soil: float = 0.8
    water: float = 0.6
    forest_cover: float = 0.3


class RegionStockpile(BaseModel):
    """Persistent per-region per-good stockpile. Keys are good names (grain, timber, etc.)."""

    goods: dict[str, float] = Field(default_factory=dict)


class MutualAidState(BaseModel):
    """Lagged local food-stress memory, scoped to the current controller."""

    controller: str
    stress_streak: int = Field(default=0, ge=0)
    last_observed_turn: int
    food_sufficiency: float = Field(ge=0.0, le=2.0)


class MutualAidTransfer(BaseModel):
    turn: int
    controller: str
    donor: str
    recipient: str
    sent: dict[str, float]
    received: dict[str, float]
    transit_loss: float
    treasury_cost: int


class RegionAsabiya(BaseModel):
    """Per-region asabiya state with frontier diagnostics (M55b)."""
    asabiya: float = 0.5
    frontier_fraction: float = 0.0
    different_civ_count: int = 0
    uncontrolled_count: int = 0


class Settlement(BaseModel):
    settlement_id: int = 0
    name: str = ""
    display_name: str | None = None
    region_name: str
    founding_turn: int = 0
    last_seen_turn: int
    dissolved_turn: int | None = None
    population_estimate: int = 0
    peak_population: int = 0
    centroid_x: float = 0.0
    centroid_y: float = 0.0
    footprint_cells: list[tuple[int, int]] = Field(default_factory=list)
    status: SettlementStatus = SettlementStatus.CANDIDATE
    inertia: int = 0
    grace_remaining: int = 0
    candidate_passes: int = 0


class SettlementSummary(BaseModel):
    settlement_id: int
    name: str
    region_name: str
    population_estimate: int
    centroid_x: float
    centroid_y: float
    founding_turn: int
    status: str


class River(BaseModel):
    name: str
    path: list[str] = Field(min_length=2)


# --- Geography 2.0 (procedural worlds); None on template/scenario worlds ---

class RegionGeography(BaseModel):
    """Generator facts about one procedural region (read-only after world gen)."""
    elevation: float          # 0..1 above sea level, normalized over land
    moisture: float           # 0..1
    latitude: float           # signed, -1 (south pole) .. 1 (north pole)
    coastal: bool = False
    sea_zones: list[str] = Field(default_factory=list)  # bordering sea zone names


class SeaZone(BaseModel):
    """A named body of water. Sea zones are not ownable regions: they group
    ocean cells, and coastal regions that border the same zone may be joined
    by a sea lane."""
    name: str
    kind: str                 # "ocean", "sea" or "lake"
    x: float
    y: float
    cells: int
    coastal_regions: list[str] = Field(default_factory=list)
    neighbors: list[str] = Field(default_factory=list)


class WorldGeography(BaseModel):
    """Geography 2.0 metadata for a procedurally generated world."""
    generator: str = "procedural"
    version: int = 1
    cells: int = 0
    land_regions: int = 0
    sea_zones: list[SeaZone] = Field(default_factory=list)
    # Region pairs joined across water (each also listed in Region.adjacencies).
    sea_lanes: list[tuple[str, str]] = Field(default_factory=list)


_DORMANT_REGION_GEOGRAPHY = ("latitude_band", "geo")
# Optional region fields omitted from serialized output while None, so worlds
# that never use them keep their exact bytes.
_DORMANT_REGION_OPTIONAL = (*_DORMANT_REGION_GEOGRAPHY, "fishery_collapsed", "stockpile_bootstrap_pending")


class Region(BaseModel):
    name: str
    terrain: str  # plains, mountains, coast, forest, desert, tundra
    carrying_capacity: int
    population: int = 0
    resources: str  # fertile, mineral, timber, maritime, barren
    controller: Optional[str] = None
    x: float | None = None
    y: float | None = None
    cultural_identity: str | None = None
    foreign_control_turns: int = 0
    adjacencies: list[str] = Field(default_factory=list)
    specialized_resources: list[Resource] = Field(default_factory=list)
    ecology: RegionEcology = Field(default_factory=RegionEcology)
    stockpile: RegionStockpile = Field(default_factory=RegionStockpile)
    asabiya_state: RegionAsabiya = Field(default_factory=RegionAsabiya)
    settlements: list[Settlement] = Field(default_factory=list)
    low_forest_turns: int = 0
    forest_regrowth_turns: int = 0
    infrastructure: list[Infrastructure] = Field(default_factory=list)
    pending_build: PendingBuild | None = None
    # One-shot stockpile seeding for a region claimed while empty, fulfilled
    # when settlers arrive. Saved so a resumed run still seeds it; None while
    # nothing is pending (omitted from output).
    stockpile_bootstrap_pending: bool | None = None
    famine_cooldown: int = 0
    role: str = "standard"
    disaster_cooldowns: dict[str, int] = Field(default_factory=dict)
    resource_suspensions: dict[int, int] = Field(default_factory=dict)
    depopulated_since: int | None = None
    ruin_quality: int = 0
    route_suspensions: dict[str, int] = Field(default_factory=dict)
    resource_types: list[int] = Field(default_factory=lambda: [255, 255, 255])
    resource_base_yields: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    resource_reserves: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    fishery_stocks: list[StockFraction] = Field(
        default_factory=lambda: [1.0, 1.0, 1.0], min_length=3, max_length=3,
    )
    fishery_yield_ratios: list[StockFraction] = Field(
        default_factory=lambda: [1.0, 1.0, 1.0], min_length=3, max_length=3,
    )  # Persisted previous ecology tick's catch constraint for Phase 2 economy.
    fishery_catch_budgets: list[Annotated[float, Field(ge=0, allow_inf_nan=False)] | None] = Field(
        default_factory=lambda: [None, None, None], min_length=3, max_length=3,
    )  # None means no experiment tick has supplied a catch budget yet.
    # Fish slots whose stock is collapsed (narrated once on collapse and once on
    # recovery); None while no slot is collapsed (omitted from output).
    fishery_collapsed: list[int] | None = None
    river_mask: int = 0
    # M35b: Disease, Depletion & Environmental Events
    disease_baseline: float = 0.01
    endemic_severity: float = 0.01
    soil_pressure_streak: int = 0
    overextraction_streaks: dict[int, int] = Field(default_factory=dict)
    resource_effective_yields: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    resource_current_yields: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0],
        exclude=True,
    )  # M54a: transient per-turn yields (season+climate adjusted)
    capacity_modifier: float = 1.0  # Temporary capacity multiplier (flood=0.85, drought=0.5)
    prev_turn_water: float = -1.0  # Previous turn's water level for delta tracking (-1 = unset)
    # M37: Religion
    conquest_conversion_boost: float = 0.0      # decays over 10 turns
    majority_belief: int = 0xFF                  # computed from snapshot in Phase 10
    conquest_conversion_active: bool = False      # one-shot flag set by action engine
    conversion_rate_signal: float = 0.0          # for bridge
    conversion_target_signal: int = 0xFF         # for bridge
    # M38b: Persecution
    persecution_intensity: float = 0.0         # 0.0 = no persecution; computed in Phase 10
    martyrdom_boost: float = 0.0               # decays linearly, same lifecycle as conquest_conversion_boost
    schism_convert_from: int = 0xFF            # 255 = no schism this turn
    schism_convert_to: int = 0xFF              # 255 = no schism this turn
    last_conquered_turn: int = -1              # -1 = never conquered; set by WAR resolution
    # M60b: military occupier; ``controller`` remains the legal owner.
    occupied_by: str | None = None
    # Geography 2.0: 0 equatorial, 1 tropical, 2 temperate, 3 subpolar, 4 polar.
    # None (and ``geo`` None) on template worlds; both are omitted from
    # serialized output while None so those worlds keep their exact bytes.
    latitude_band: int | None = None
    geo: RegionGeography | None = None

    @model_serializer(mode="wrap")
    def _omit_dormant_geography(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            for key in _DORMANT_REGION_OPTIONAL:
                if key in data and getattr(self, key) is None:
                    del data[key]
        return data

    @field_validator("resource_suspensions", mode="before")
    @classmethod
    def _normalize_resource_suspensions(cls, value):
        """Accept legacy enum-string keys and normalize them to integer ids."""
        if value is None or not isinstance(value, dict):
            return value

        normalized: dict[int, int] = {}
        for key, turns in value.items():
            if isinstance(key, ResourceType):
                normalized[int(key)] = turns
                continue
            if isinstance(key, int):
                normalized[key] = turns
                continue
            if isinstance(key, str):
                if key.isdigit():
                    normalized[int(key)] = turns
                    continue

                enum_name = key.removeprefix("ResourceType.")
                try:
                    normalized[int(ResourceType[enum_name])] = turns
                    continue
                except KeyError:
                    pass

            normalized[key] = turns

        return normalized


class Leader(BaseModel):
    name: str
    trait: str
    reign_start: int
    alive: bool = True
    succession_type: str = "founder"
    predecessor_name: str | None = None
    rival_leader: str | None = None
    rival_civ: str | None = None
    secondary_trait: str | None = None
    grudges: list[dict] = Field(default_factory=list)
    agent_id: int | None = None
    dynasty_id: int | None = None
    throne_name: str | None = None
    regnal_ordinal: int = 0
    # Turn of birth (one turn = one year).  None for old saves and founders;
    # events.ensure_leader_birth_turn() infers a deterministic value on first use.
    birth_turn: int | None = None


class Civilization(BaseModel):
    # Note: validate_assignment=False for performance. Field constraints
    # (ranges, bounds) are enforced via manual clamp() calls, not Pydantic
    # validation. Do not add ge=/le= kwargs — they are silently ignored.
    name: str
    population: int = 0
    military: int = 0
    economy: int = 0
    culture: int = 0
    stability: int = 50
    tech_era: TechEra = TechEra.TRIBAL
    treasury: int = 0
    domains: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    leader: Leader
    goal: str = ""
    regions: list[str] = Field(default_factory=list)
    asabiya: float = 0.5
    asabiya_variance: float = 0.0
    cultural_milestones: list[str] = Field(default_factory=list)
    action_counts: dict[str, int] = Field(default_factory=dict)
    prestige: int = 0
    leader_name_pool: list[str] | None = None
    capital_region: str | None = None
    last_income: int = 0
    merc_pressure_turns: int = 0
    peak_region_count: int = 0
    decline_turns: int = 0
    stats_sum_history: list[int] = Field(default_factory=list)
    known_regions: list[str] | None = None
    great_persons: list[GreatPerson] = Field(default_factory=list)
    traditions: list[str] = Field(default_factory=list)
    legacy_counts: dict[str, int] = Field(default_factory=dict)
    event_counts: dict[str, int] = Field(default_factory=dict)
    war_win_turns: list[int] = Field(default_factory=list)
    folk_heroes: list[dict] = Field(default_factory=list)
    succession_crisis_turns_remaining: int = 0
    succession_candidates: list[dict] = Field(default_factory=list)
    civ_stress: int = 0  # M18: per-civ stress, recomputed each turn
    regions_start_of_turn: int = Field(default=0, exclude=True)  # M18: transient regression snapshot
    was_in_twilight: bool = Field(default=False, exclude=True)  # M18: transient regression snapshot
    capital_start_of_turn: str | None = Field(default=None, exclude=True)  # M18: transient regression snapshot
    tech_focuses: list[str] = Field(default_factory=list)  # M21: history of focus values
    active_focus: str | None = None  # M21: current era's focus
    factions: FactionState = Field(default_factory=FactionState)
    founded_turn: int = 0
    max_precap_weight: float = Field(
        default=0.0,
        exclude=True,
    )  # M19b: transient, tracked separately in snapshots for analytics
    civ_majority_faith: int = 0xFF  # M37: computed from agent snapshot each turn; 0xFF = unknown
    majority_faith_ratio: float = 0.0  # M37: ratio of majority faith holders; drives reformation
    previous_majority_faith: int = 0xFF  # initialized to civ_majority_faith at world-gen
    # M47d: War frequency calibration
    war_weariness: float = 0.0
    peace_momentum: float = 0.0
    regnal_name_counts: dict[str, int] = Field(default_factory=dict)
    # Decaying per-event-type hazard excitation (events.py Hawkes kernel).
    event_excitation: dict[str, float] = Field(default_factory=dict)
    # Consecutive Phase-10 checks this civ has been structurally unviable.
    unviable_turns: int = 0
    # Phase 8 governance carry (None = dormant; omitted from serialized output).
    governance: CivGovernance | None = None

    @model_serializer(mode="wrap")
    def _serialize_without_dormant_governance(self, handler):
        return _omit_dormant_governance(self, handler(self))


class Relationship(BaseModel):
    disposition: Disposition = Disposition.NEUTRAL
    # Names of the treaties this pair has signed (campaign peace treaties and,
    # with diplomacy on, every chronicler.diplomacy treaty).
    treaties: list[str] = Field(default_factory=list)
    # Legacy free-text field, never written by the simulation. Structured
    # grievance stocks live in ``memory`` (chronicler.diplomacy).
    grievances: list[str] = Field(default_factory=list)
    trade_volume: int = 0
    allied_turns: int = 0
    trade_contact_turns: int = 0
    disposition_drift: int = 0
    # Diplomatic memory of the holder toward the other civ: trust, goodwill and
    # decaying grievance stocks. None while diplomacy is off (omitted from output).
    memory: DiplomaticMemory | None = None

    @model_serializer(mode="wrap")
    def _omit_dormant_memory(self, handler):
        return _omit_none_fields(self, handler(self), ("memory",))


class GreatPersonDeed(BaseModel):
    """Structured deed with event-time provenance."""
    text: str
    region: str | None = None
    turn: int | None = None
    civ: str | None = None


class GreatPerson(BaseModel):
    name: str
    role: str  # "general", "merchant", "prophet", "scientist", "exile", "hostage"
    trait: str
    civilization: str
    origin_civilization: str
    alive: bool = True
    active: bool = True
    fate: str = "active"  # "active", "retired", "dead", "ascended", "exile"
    born_turn: int
    death_turn: int | None = None
    deeds: list[GreatPersonDeed] = Field(default_factory=list)

    @field_validator("deeds", mode="before")
    @classmethod
    def _normalize_deeds(cls, v):
        if not isinstance(v, list):
            return v
        result = []
        for item in v:
            if isinstance(item, str):
                result.append({"text": item})
            else:
                result.append(item)
        return result
    region: str | None = None
    captured_by: str | None = None
    is_hostage: bool = False
    hostage_turns: int = 0
    pre_hostage_role: str | None = None
    cultural_identity: str | None = None
    movement_id: str | None = None  # NOTE: Movement.id is str, not int
    recognized_by: list[str] = Field(default_factory=list)
    source: str = "aggregate"  # "aggregate" or "agent"
    agent_id: int | None = None
    parent_id_0: int = 0
    parent_id_1: int = 0  # M57a: other parent (spouse at birth), 0 = unknown
    lineage_house: int = 0  # M57a: secondary dynasty id for narration, 0 = none
    dynasty_id: int | None = None
    # M38b: Pilgrimages
    pilgrimage_destination: str | None = None
    pilgrimage_return_turn: int | None = None
    arc_type: str | None = None
    arc_phase: str | None = None
    arc_summary: str | None = None
    arc_type_turn: int | None = None
    pilgrimage_skill_bonus: float = 0.0
    # M40: Social Networks
    origin_region: str | None = None
    # M48: Mule promotion system
    mule: bool = False
    mule_artifact_created: bool = False
    mule_memory_event_type: Optional[int] = None
    utility_overrides: dict = Field(default_factory=dict)  # ActionType name -> multiplier
    memories: list = Field(default_factory=list)  # cached from Rust via FFI
    needs: Optional[dict] = None  # M49: cached from Rust via FFI, None in aggregate mode
    agent_bonds: Optional[list] = None  # M50a: synced from Rust per-agent store
    base_name: str | None = None  # M51: personal name without title, set at promotion

    def parent_ids(self) -> tuple[int, int]:
        """Return both parent IDs as a tuple."""
        return (self.parent_id_0, self.parent_id_1)


class ShockContext(BaseModel):
    """M43b: Structured shock data for narration context."""
    region: str
    category: str
    severity: float
    upstream_source: str | None = None


# Causal-provenance fields (docs/integration/causal-provenance.md). They are
# additive and omitted from serialized output while empty, so events without
# provenance (old saves, bundles, fixtures) keep their exact bytes.
_EVENT_PROVENANCE_DEFAULTS: tuple[tuple[str, object], ...] = (
    ("event_id", ""), ("causes", []), ("region", None), ("civs", []),
    ("episode", None), ("duration", None),
)


def _omit_empty_fields(data, defaults: tuple[tuple[str, object], ...]):
    if isinstance(data, dict):
        for key, empty in defaults:
            if key in data and data[key] == empty:
                del data[key]
    return data


class Event(BaseModel):
    turn: int
    event_type: str
    actors: list[str]
    description: str
    # Legacy free-text field, never written by the simulation. Recorded
    # provenance lives in ``causes`` (effect -> cause event ids).
    consequences: list[str] = Field(default_factory=list)
    importance: int = 5
    source: str = "aggregate"  # "aggregate" or "agent"
    # M43b: Structured shock metadata (None for non-shock events)
    shock_region: str | None = None
    shock_category: str | None = None
    # Causal provenance. ``event_id`` is "<emission turn>:<event_type>:<n>",
    # assigned without RNG draws when the turn loop observes the event;
    # ``causes`` lists the ids of the events that produced this one.
    event_id: str = ""
    causes: list[str] = Field(default_factory=list)
    region: str | None = None   # region name, when the event is regional
    civs: list[str] = Field(default_factory=list)  # civs involved when actors are not civs
    # Chronic conditions: "onset" (first turn), "tick" (a repeat kept for a
    # per-turn consumer) or "end" (closing event; ``duration`` in turns).
    episode: str | None = None
    duration: int | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_provenance(self, handler):
        return _omit_empty_fields(handler(self), _EVENT_PROVENANCE_DEFAULTS)


class NamedEvent(BaseModel):
    """A historically significant event with a generated name."""
    name: str
    event_type: str  # battle, treaty, cultural_work, tech_breakthrough, coup, legacy, rival_fall
    turn: int
    actors: list[str]
    region: str | None = None
    description: str
    importance: int = 5


_CONDITION_PROVENANCE_DEFAULTS: tuple[tuple[str, object], ...] = (
    ("condition_id", ""), ("cause_id", None), ("onset_turn", None),
)


class ActiveCondition(BaseModel):
    condition_type: str
    affected_civs: list[str]
    duration: int
    severity: int = 1
    # Causal provenance (omitted while empty): a stable id, the event that
    # created the condition, and the turn it began.
    condition_id: str = ""
    cause_id: str | None = None
    onset_turn: int | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_provenance(self, handler):
        return _omit_empty_fields(handler(self), _CONDITION_PROVENANCE_DEFAULTS)


class ChronicEpisode(BaseModel):
    """An open chronic condition (one onset event, repeats folded in)."""
    onset_id: str
    # Latest report kept on the timeline (the onset, or the latest tick).
    last_id: str = ""
    event_type: str
    onset_turn: int
    last_turn: int
    count: int = 1
    region: str | None = None
    category: str | None = None
    civs: list[str] = Field(default_factory=list)


class OpenCondition(BaseModel):
    """An ActiveCondition the provenance layer is waiting to see end."""
    condition_type: str
    affected_civs: list[str] = Field(default_factory=list)
    onset_turn: int
    cause_id: str | None = None


class Exciter(BaseModel):
    """The dominant source of one civ's hazard excitation for one event type."""
    event_id: str
    alpha: float
    turn: int


class ProvenanceState(BaseModel):
    """Persisted causal index (chronicler.provenance). Never read by the simulation.

    ``keys`` maps a semantic key (e.g. ``war:A|B``, ``occupation:<region>``,
    ``psi:<civ>``) to the id of the event that currently stands for it;
    ``exciters`` maps ``<civ>|<event type>`` to the event whose decaying
    hazard excitation is currently the largest.
    """
    keys: dict[str, str] = Field(default_factory=dict)
    episodes: dict[str, ChronicEpisode] = Field(default_factory=dict)
    conditions: dict[str, OpenCondition] = Field(default_factory=dict)
    exciters: dict[str, Exciter] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.keys or self.episodes or self.conditions or self.exciters)


_DORMANT_VASSAL_LADDER = ("stage", "stage_turn", "integration", "crown")


class VassalRelation(BaseModel):
    overlord: str
    vassal: str
    tribute_rate: float = 0.15
    turns_active: int = 0
    # Polity ladder (chronicler.diplomacy; None while diplomacy is off and
    # omitted from output): "client", "vassal" or "union", the turn the
    # stage began, accumulated integration (0..100) and, in a union, the
    # overlord ruler who wears both crowns.
    stage: str | None = None
    stage_turn: int | None = None
    integration: float | None = None
    crown: str | None = None

    @model_serializer(mode="wrap")
    def _omit_dormant_ladder(self, handler):
        return _omit_none_fields(self, handler(self), _DORMANT_VASSAL_LADDER)


class Federation(BaseModel):
    name: str
    members: list[str]
    founded_turn: int


class ProxyWar(BaseModel):
    sponsor: str
    target_civ: str
    target_region: str
    treasury_per_turn: int = 8
    turns_active: int = 0
    detected: bool = False


# --- M60: Campaigns, battles and occupation (default off; see docs/war/) ---

class Army(BaseModel):
    """A field army raised for one war. Persisted; identity is ``army_id``."""
    army_id: str
    name: str
    civ: str
    war_key: str
    region: str
    home_region: str
    objective: str | None = None
    phase: str = "rally"  # rally, marching, sieging, holding, regrouping, returning
    soldiers: int = 0
    raised: int = 0
    morale: int = 700  # M60a thousandths
    rations: int = 0  # carried cohort rations (M60a kits)
    supply_distance: int | None = None
    move_progress: int = 0
    siege_turns: int = 0
    general: str | None = None
    # Agent modes: enlisted native agents as (agent_id, region_index) pairs.
    roster: list[tuple[int, int]] = Field(default_factory=list)
    raised_turn: int = 0
    casualties: int = 0
    deserted: int = 0
    attrition: int = 0
    battles_won: int = 0
    battles_lost: int = 0
    unpaid_turns: int = 0
    last_combat_turn: int = -1


class Occupation(BaseModel):
    """Military occupation: ``owner`` keeps legal control, ``occupier`` holds it."""
    region: str
    owner: str
    occupier: str
    war_key: str
    since_turn: int
    unrest: int = 0  # 0..1000
    revolts: int = 0


class WarRecord(BaseModel):
    """Campaign-layer bookkeeping for one entry of ``WorldState.active_wars``."""
    war_key: str
    attacker: str
    defender: str
    aim: str = "conquest"  # conquest, tribute, vassalization, liberation
    aim_region: str | None = None
    start_turn: int
    score: int = 0  # attacker perspective, -100..100
    battle_points: int = 0
    battles: int = 0
    attacker_losses: int = 0
    defender_losses: int = 0
    last_combat_turn: int = -1
    ended_turn: int | None = None
    outcome: str | None = None


class BattleRecord(BaseModel):
    turn: int
    name: str
    kind: str  # field, skirmish, assault, revolt
    region: str
    war_key: str
    attacker: str
    defender: str
    attacker_soldiers: int
    defender_soldiers: int
    attacker_power: int
    defender_power: int
    attacker_losses: int
    defender_losses: int
    winner: str | None = None
    attacker_general: str | None = None
    defender_general: str | None = None


class TreatyRecord(BaseModel):
    turn: int
    name: str
    war_key: str
    parties: list[str]
    winner: str | None = None
    kind: str  # capitulation, negotiated, white_peace, external
    aim: str = "conquest"
    regions_ceded: list[str] = Field(default_factory=list)
    treasury_paid: int = 0
    vassalized: bool = False


class WarState(BaseModel):
    armies: list[Army] = Field(default_factory=list)
    wars: list[WarRecord] = Field(default_factory=list)
    ended_wars: list[WarRecord] = Field(default_factory=list)
    occupations: list[Occupation] = Field(default_factory=list)
    battles: list[BattleRecord] = Field(default_factory=list)
    treaties: list[TreatyRecord] = Field(default_factory=list)
    next_army_serial: int = 1
    raised_counts: dict[str, int] = Field(default_factory=dict)  # per-civ ordinal source
    last_raise_turn: dict[str, int] = Field(default_factory=dict)


class ExileModifier(BaseModel):
    original_civ_name: str
    absorber_civ: str
    conquered_regions: list[str]
    turns_remaining: int = 20
    recognized_by: list[str] = Field(default_factory=list)


class Movement(BaseModel):
    """M16b: An ideological movement that spreads between civilizations."""
    id: str
    origin_civ: str
    origin_turn: int
    value_affinity: str
    adherents: dict[str, int] = Field(default_factory=dict)


class PandemicRegion(BaseModel):
    """Tracks pandemic spread per-region. Part of M18 emergence system."""
    region_name: str
    severity: int  # 1-3, keyed off active infrastructure count
    turns_remaining: int  # 4-6, decrements each turn


class TerrainTransitionRule(BaseModel):
    """Configurable terrain transformation rule for ecological succession."""
    from_terrain: str
    to_terrain: str
    condition: str  # "low_forest" or "forest_regrowth"
    threshold_turns: int  # Consecutive turns before transform triggers


# --- M27: Agent integration data structures ---

@dataclass(slots=True)
class StatChange:
    civ_id: int
    stat: str
    delta: float
    category: str       # "guard", "guard-action", "guard-shock", "signal", "keep"
    stat_at_time: float  # stat value when mutation was recorded


@dataclass
class CivShock:
    """Normalized civ-level shock components sent across the Python/Rust boundary.

    Sign contract:
      negative values are harmful shocks that reduce satisfaction
      positive values are beneficial shocks that increase satisfaction
    Each component should stay within [-1.0, 1.0].
    """
    civ_id: int
    stability_shock: float = 0.0
    economy_shock: float = 0.0
    military_shock: float = 0.0
    culture_shock: float = 0.0


@dataclass
class DemandSignal:
    civ_id: int
    occupation: int      # 0=farmer, 1=soldier, 2=merchant, 3=scholar, 4=priest
    magnitude: float
    turns_remaining: int  # starts at 3


@dataclass(slots=True)
class AgentEventRecord:
    turn: int
    agent_id: int
    event_type: str
    region: int
    target_region: int
    civ_affinity: int
    occupation: int
    belief: int | None = None
    target_agent_id: int = 0
    formed_turn: int = 0


@dataclass
class ArtifactIntent:
    artifact_type: ArtifactType
    trigger: str
    creator_name: str | None
    creator_born_turn: int | None
    holder_name: str | None
    holder_born_turn: int | None
    civ_name: str
    region_name: str
    anchored: bool | None = None
    mule_origin: bool = False
    context: str = ""


@dataclass
class ArtifactLifecycleIntent:
    action: str
    losing_civ: str
    gaining_civ: str | None
    region: str
    is_capital: bool
    is_full_absorption: bool
    is_destructive: bool


# --- Top-level state ---

class WorldState(BaseModel):
    name: str
    seed: int
    turn: int = 0
    regions: list[Region] = Field(default_factory=list)
    civilizations: list[Civilization] = Field(default_factory=list)
    relationships: dict[str, dict[str, Relationship]] = Field(default_factory=dict)
    events_timeline: list[Event] = Field(default_factory=list)
    active_conditions: list[ActiveCondition] = Field(default_factory=list)
    event_probabilities: dict[str, float] = Field(default_factory=dict)
    named_events: list[NamedEvent] = Field(default_factory=list)
    used_leader_names: list[str] = Field(default_factory=list)
    action_history: dict[str, list[str]] = Field(default_factory=dict)
    war_start_turns: dict[str, int] = Field(default_factory=dict)
    scenario_name: str | None = None
    embargoes: list[tuple[str, str]] = Field(default_factory=list)
    active_wars: list[tuple[str, str]] = Field(default_factory=list)
    mercenary_companies: list[dict] = Field(default_factory=list)
    vassal_relations: list[VassalRelation] = Field(default_factory=list)
    federations: list[Federation] = Field(default_factory=list)
    proxy_wars: list[ProxyWar] = Field(default_factory=list)
    exile_modifiers: list[ExileModifier] = Field(default_factory=list)
    movements: list[Movement] = Field(default_factory=list)
    next_movement_id: int = 0
    peace_turns: int = 0
    balance_of_power_turns: int = 0
    climate_config: ClimateConfig = Field(default_factory=ClimateConfig)
    fishery_experiment: FisheryConfig = Field(default_factory=FisheryConfig)
    fog_of_war: bool = False
    retired_persons: list[GreatPerson] = Field(default_factory=list)
    # M40: Dissolved edges per turn for narration (not serialized to bundle)
    dissolved_edges_by_turn: dict[int, list[tuple]] = Field(default_factory=dict, exclude=True)
    great_person_cooldowns: dict[str, dict[str, int]] = Field(default_factory=dict)
    # M18: Emergence and Chaos
    stress_index: int = 0  # Global stress aggregate (max across civs)
    black_swan_cooldown: int = 0  # Turns until next black swan eligible
    chaos_multiplier: float = 1.0  # Scalar on black swan probability (from ScenarioConfig)
    black_swan_cooldown_turns: int = 30  # Configurable cooldown length (from ScenarioConfig)
    # Turn of the last twilight absorption (paces absorptions world-wide).
    last_twilight_absorption_turn: int | None = None
    pandemic_state: list[PandemicRegion] = Field(default_factory=list)
    pandemic_recovered: list[str] = Field(default_factory=list)  # Regions already hit; prevents re-infection
    terrain_transition_rules: list[TerrainTransitionRule] = Field(
        default_factory=lambda: [
            TerrainTransitionRule(from_terrain="forest", to_terrain="plains",
                                  condition="low_forest", threshold_turns=50),
            TerrainTransitionRule(from_terrain="plains", to_terrain="forest",
                                  condition="forest_regrowth", threshold_turns=100),
        ]
    )
    tuning_overrides: dict[str, float] = Field(default_factory=dict)
    # M27: Agent integration
    agent_mode: str | None = None       # None/"off", "demographics-only", "shadow", "hybrid"
    # Experimental social response; saved separately from ecology/demography.
    mutual_aid_enabled: bool = False
    mutual_aid_state: dict[str, MutualAidState] = Field(default_factory=dict)
    mutual_aid_last_dispatch_turn: int | None = None
    mutual_aid_last_transfers: list[MutualAidTransfer] = Field(default_factory=list)
    # M60: campaigns, battles and occupation (default off).
    campaigns_enabled: bool = False
    war_state: WarState = Field(default_factory=WarState)
    # Phase 8 governance runtime switch (None = disabled; omitted from output).
    governance: GovernanceSettings | None = None
    # Geography 2.0 metadata (procedural worlds only; omitted while None).
    geography: WorldGeography | None = None
    # Contact & trade-flow ledger (None = disabled; omitted from output).
    contact_ledger: ContactLedgerState | None = None
    # Regional SEIRS epidemiology (None = disabled; omitted from output).
    epidemics: EpidemicState | None = None
    # Money, credit and public finance (None = disabled; omitted from output).
    finance: FinanceState | None = None
    # Diplomacy: treaties, diplomatic memory and the polity ladder
    # (chronicler.diplomacy; None = disabled; omitted from output).
    diplomacy: DiplomacyState | None = None
    # Technology as diffusing techniques: per-region practice, civ known sets
    # (chronicler.techniques; None = disabled; omitted from output).
    techniques: TechniqueState | None = None
    # Maritime layer: fleets, sea-zone control, blockades, piracy, colonies
    # (chronicler.maritime; None = disabled; omitted from output).
    maritime: MaritimeState | None = None
    # Great-person agendas: objectives, deeds, coups, alliances and rivalries
    # (chronicler.gp_agendas; None = disabled; omitted from output).
    gp_agendas: GPAgendaState | None = None
    # Pastoral and nomadic peoples: subsistence modes, herds, raids, tribute,
    # hordes and sedentarization (chronicler.nomads; None = disabled;
    # omitted from output).
    nomads: NomadState | None = None
    # Causal provenance index (chronicler.provenance); omitted while empty.
    provenance: ProvenanceState = Field(default_factory=ProvenanceState)
    pending_shocks: list = Field(default_factory=list, exclude=True)   # list[CivShock]
    agent_events_raw: list = Field(default_factory=list, exclude=True)  # list[AgentEventRecord]
    # M35a: Rivers
    rivers: list[River] = Field(default_factory=list)
    # M37: Religion
    belief_registry: list[Belief] = Field(default_factory=list)  # max 16 faiths
    # M52: Artifacts & Significant Items
    artifacts: list[Artifact] = Field(default_factory=list)
    # M56a: Settlement detection
    dissolved_settlements: list[Settlement] = Field(default_factory=list)
    next_settlement_id: int = 1
    settlement_naming_counters: dict[str, int] = Field(default_factory=dict)
    settlement_candidates: list[Settlement] = Field(default_factory=list, exclude=True)
    # M47: Cached region lookup
    _region_map: dict[str, "Region"] | None = PrivateAttr(default=None)
    # Cached civ lookup for hot paths
    _civ_map: dict[str, "Civilization"] | None = PrivateAttr(default=None)
    _civ_index_map: dict[str, int] | None = PrivateAttr(default=None)
    # Cached trade-route lookups for hot read paths within a turn.
    _trade_route_cache_turn: int | None = PrivateAttr(default=None)
    _active_trade_routes_cache: list[tuple[str, str]] | None = PrivateAttr(default=None)
    _active_trade_route_pairs_cache: set[tuple[str, str]] | None = PrivateAttr(default=None)
    _self_trade_civs_cache: set[str] | None = PrivateAttr(default=None)
    # Hybrid-mode bridge hook for transient agent/civ synchronization.
    _agent_bridge: object | None = PrivateAttr(default=None)
    # M52: Transient artifact pipeline signals (not serialized)
    _artifact_intents: list = PrivateAttr(default_factory=list)
    _artifact_lifecycle_intents: list = PrivateAttr(default_factory=list)
    _artifact_prestige_by_civ: dict = PrivateAttr(default_factory=dict)
    # Transient: events rolled by the hazard phases this turn (consumed and
    # cleared by run_turn's excitation update; not serialized).
    _hazard_events: list = PrivateAttr(default_factory=list)
    # Derived, never serialized: incremental lookups over the history lists
    # (chronicler.history_index); rebuilt lazily after load or copy.
    _history_index: object | None = PrivateAttr(default=None)
    # Contact ledger: transient per-turn inputs, folded and cleared by
    # contact_ledger.update_contact_ledger at the end of the turn.
    _contact_pending: list | None = PrivateAttr(default=None)
    # Causal provenance: per-turn id counters and observation cursor
    # (chronicler.provenance.TurnIds; equality-neutral, never serialized).
    _provenance_turn: object | None = PrivateAttr(default=None)
    # In-world historiography (chronicler.historiography.HistoriographySlot;
    # None = off). Observational: never read by the simulation, never in
    # model_dump (state.json keeps its bytes); save/load carry it in a
    # ``<state>.historiography.json`` sidecar. Equality-neutral.
    _historiography: object | None = PrivateAttr(default=None)
    # In-world languages and names (chronicler.languages.LanguagesSlot; None =
    # off). Observational like the historiography: never read by the
    # simulation, never in model_dump; saved in a ``<state>.languages.json``
    # sidecar. Equality-neutral.
    _languages: object | None = PrivateAttr(default=None)

    @property
    def region_map(self) -> dict[str, "Region"]:
        if self._region_map is None:
            self._region_map = {r.name: r for r in self.regions}
        return self._region_map

    def invalidate_region_map(self) -> None:
        """Call after region list changes (conquest, expansion)."""
        self._region_map = None
        self.invalidate_trade_route_cache()

    @property
    def civ_map(self) -> dict[str, "Civilization"]:
        if self._civ_map is None or len(self._civ_map) != len(self.civilizations):
            self._civ_map = {c.name: c for c in self.civilizations}
        return self._civ_map

    @property
    def civ_index_map(self) -> dict[str, int]:
        if self._civ_index_map is None or len(self._civ_index_map) != len(self.civilizations):
            self._civ_index_map = {c.name: i for i, c in enumerate(self.civilizations)}
        return self._civ_index_map

    def invalidate_civ_map(self) -> None:
        """Call after structural civilization edits."""
        self._civ_map = None
        self._civ_index_map = None

    def invalidate_trade_route_cache(self) -> None:
        """Clear cached trade-route lookups after route-affecting mutations."""
        self._trade_route_cache_turn = None
        self._active_trade_routes_cache = None
        self._active_trade_route_pairs_cache = None
        self._self_trade_civs_cache = None

    @model_serializer(mode="wrap")
    def _serialize_without_dormant_governance(self, handler):
        data = _omit_dormant_finance(self, _omit_dormant_contact_ledger(
            self, _omit_dormant_governance(self, handler(self))))
        if isinstance(data, dict) and self.geography is None:
            data.pop("geography", None)
        if isinstance(data, dict) and self.epidemics is None:
            data.pop("epidemics", None)
        if isinstance(data, dict) and self.diplomacy is None:
            data.pop("diplomacy", None)
        if isinstance(data, dict) and self.techniques is None:
            data.pop("techniques", None)
        if isinstance(data, dict) and self.maritime is None:
            data.pop("maritime", None)
        if isinstance(data, dict) and self.gp_agendas is None:
            data.pop("gp_agendas", None)
        if isinstance(data, dict) and self.nomads is None:
            data.pop("nomads", None)
        if isinstance(data, dict) and self.provenance.is_empty():
            data.pop("provenance", None)
        return data

    def save(self, path: Path) -> None:
        """Persist world state to a JSON file."""
        parent = path.parent
        try:
            parent_is_dir = parent.is_dir()
        except OSError:
            parent_is_dir = False
        if not parent_is_dir:
            parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        # The chronicles and the languages travel beside the state (removed while off).
        from chronicler.historiography import save_sidecar
        save_sidecar(self, path)
        from chronicler.languages import save_sidecar as save_languages
        save_languages(self, path)

    @classmethod
    def load(cls, path: Path) -> WorldState:
        """Load world state from a JSON file (and its historiography and languages
        sidecars, if any)."""
        if not path.exists():
            raise FileNotFoundError(f"No state file at {path}")
        world = cls.model_validate_json(path.read_text(encoding="utf-8"))
        from chronicler.historiography import load_sidecar
        load_sidecar(world, path)
        from chronicler.languages import load_sidecar as load_languages
        load_languages(world, path)
        return world


# --- Snapshot models (for viewer bundle — never persisted to state.json) ---

class CivSnapshot(BaseModel):
    """Per-turn snapshot of a civilization's stats."""
    population: int
    military: int
    economy: int
    culture: int
    stability: int
    treasury: int
    asabiya: float
    asabiya_variance: float = 0.0
    tech_era: TechEra
    trait: str
    regions: list[str]
    leader_name: str
    alive: bool
    last_income: int = 0
    active_trade_routes: int = 0
    is_vassal: bool = False
    is_fallen_empire: bool = False
    in_twilight: bool = False
    federation_name: str | None = None
    gini: float = 0.0  # Wealth Gini coefficient (M41)
    urban_agents: int = 0
    urban_fraction: float = 0.0
    prestige: int = 0
    capital_region: str | None = None
    great_persons: list[dict] = Field(default_factory=list)
    traditions: list[str] = Field(default_factory=list)
    folk_heroes: list[dict] = Field(default_factory=list)
    active_crisis: bool = False
    civ_stress: int = 0
    active_focus: str | None = None  # M21: tech focus for viewer/analytics
    factions: FactionState | None = None
    action_counts: dict[str, int] = Field(default_factory=dict)  # M19b: cumulative action counts
    max_precap_weight: float = 0.0  # M19b: max absolute weight before base-scaled cap
    last_action: str | None = None  # M19b: most recent action taken
    # M47d: War frequency analytics
    war_weariness: float = 0.0
    peace_momentum: float = 0.0
    # Phase 8 governance per-turn stats (None when governance is disabled).
    governance: dict | None = None

    @model_serializer(mode="wrap")
    def _serialize_without_dormant_governance(self, handler):
        return _omit_dormant_governance(self, handler(self))


class RelationshipSnapshot(BaseModel):
    """Per-turn snapshot of disposition between two civs."""
    disposition: str


class TurnSnapshot(BaseModel):
    """Complete snapshot of world state at a single turn."""
    turn: int
    civ_stats: dict[str, CivSnapshot]
    region_control: dict[str, str | None]
    relationships: dict[str, dict[str, RelationshipSnapshot]]
    trade_routes: list[tuple[str, str]] = Field(default_factory=list)
    active_wars: list[tuple[str, str]] = Field(default_factory=list)
    embargoes: list[tuple[str, str]] = Field(default_factory=list)
    ecology: dict[str, dict[str, float]] = Field(default_factory=dict)
    mercenary_companies: list[dict] = Field(default_factory=list)
    vassal_relations: list[dict] = Field(default_factory=list)
    federations: list[dict] = Field(default_factory=list)
    proxy_wars: list[dict] = Field(default_factory=list)
    exile_modifiers: list[dict] = Field(default_factory=list)
    capitals: dict[str, str] = Field(default_factory=dict)
    peace_turns: int = 0
    region_cultural_identity: dict[str, str | None] = Field(default_factory=dict)
    movements_summary: list[dict] = Field(default_factory=list)
    stress_index: int = 0
    pandemic_regions: list[str] = Field(default_factory=list)
    climate_phase: str = ""
    active_conditions: list[dict] = Field(default_factory=list)
    per_pair_accuracy: dict[str, dict[str, float]] = Field(default_factory=dict)
    perception_errors: dict[str, dict[str, dict[str, int]]] = Field(default_factory=dict)
    # M56a: Settlement summary
    settlement_source_turn: int = 0
    settlement_count: int = 0
    candidate_count: int = 0
    total_settlement_population: int = 0
    active_settlements: list[SettlementSummary] = Field(default_factory=list)
    founded_this_turn: list[int] = Field(default_factory=list)
    dissolved_this_turn: list[int] = Field(default_factory=list)
    # M56b: Urban metrics
    urban_agent_count: int = 0
    urban_fraction: float = 0.0
    # M60: campaign layer (armies, battles, occupations, wars); None when off.
    # Omitted from serialization while None so default-off snapshots keep
    # their exact historical bytes.
    campaign: dict | None = None
    # Contact ledger per-turn summary; None (and omitted) when the ledger is off.
    contact: dict | None = None
    # Epidemiology per-turn summary; None (and omitted) when epidemiology is off.
    epidemics: dict | None = None
    # Money, credit and public finance per-turn summary; None (omitted) when off.
    finance: dict | None = None
    # Diplomacy per-turn summary; None (and omitted) when diplomacy is off.
    diplomacy: dict | None = None
    # Techniques per-turn summary; None (and omitted) when techniques are off.
    techniques: dict | None = None
    # Maritime per-turn summary; None (and omitted) when maritime is off.
    maritime: dict | None = None
    # Great-person agenda per-turn summary; None (and omitted) when off.
    gp_agendas: dict | None = None
    # Nomads per-turn summary; None (and omitted) when nomads are off.
    nomads: dict | None = None
    # Viewer only: per-region food sufficiency and the completed turn's relief
    # convoys (``mutual_aid.snapshot_summary``); None (and omitted) unless
    # mutual aid runs on an agent-backed economy.
    food: dict | None = None
    # Viewer only: the completed turn's agent migrations as
    # [from region index, to region index, agents]; None (and omitted)
    # without an agent pool that records events (hybrid, shadow).
    migration: list | None = None

    @model_serializer(mode="wrap")
    def _omit_dormant_campaign(self, handler):
        data = handler(self)
        for key in ("food", "migration"):
            if isinstance(data, dict) and data.get(key, 0) is None:
                data.pop(key)
        if isinstance(data, dict) and data.get("campaign", 0) is None:
            data.pop("campaign")
        if isinstance(data, dict) and data.get("contact", 0) is None:
            data.pop("contact")
        if isinstance(data, dict) and data.get("epidemics", 0) is None:
            data.pop("epidemics")
        if isinstance(data, dict) and data.get("finance", 0) is None:
            data.pop("finance")
        if isinstance(data, dict) and data.get("diplomacy", 0) is None:
            data.pop("diplomacy")
        if isinstance(data, dict) and data.get("techniques", 0) is None:
            data.pop("techniques")
        if isinstance(data, dict) and data.get("maritime", 0) is None:
            data.pop("maritime")
        if isinstance(data, dict) and data.get("gp_agendas", 0) is None:
            data.pop("gp_agendas")
        if isinstance(data, dict) and data.get("nomads", 0) is None:
            data.pop("nomads")
        return data


# --- M20a: Narration Pipeline v2 models ---

class NarrativeRole(str, Enum):
    """Narrative arc position for a curated moment."""
    INCITING = "inciting"
    ESCALATION = "escalation"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    CODA = "coda"


class CausalLink(BaseModel):
    """Connection between a cause event and its effect."""
    cause_turn: int
    cause_event_type: str
    effect_turn: int
    effect_event_type: str
    pattern: str  # e.g., "drought→famine"
    # Causal provenance (omitted while empty): the linked event ids and how
    # the link is known: "recorded" (the emitter stamped it in
    # ``Event.causes``) or "pattern" (type-pair fallback where no provenance
    # exists).
    cause_id: str = ""
    effect_id: str = ""
    provenance: str = "pattern"

    @model_serializer(mode="wrap")
    def _omit_empty_provenance(self, handler):
        return _omit_empty_fields(
            handler(self), (("cause_id", ""), ("effect_id", ""), ("provenance", "pattern")),
        )


class ChainStep(BaseModel):
    """One event in a causal chain."""
    event_id: str
    turn: int
    event_type: str
    description: str = ""
    region: str | None = None


class CausalChain(BaseModel):
    """A recorded cause-to-effect path, root cause first."""
    steps: list[ChainStep] = Field(default_factory=list)


class GapSummary(BaseModel):
    """Mechanical summary of unnarrated turns between curated moments."""
    turn_range: tuple[int, int]  # inclusive
    event_count: int
    top_event_type: str
    stat_deltas: dict[str, dict[str, int]]  # {civ_name: {stat_name: delta}}
    territory_changes: int


class NarrativeMoment(BaseModel):
    """Curator output: a selected narratively important moment."""
    anchor_turn: int
    turn_range: tuple[int, int]  # inclusive
    events: list[Event]
    named_events: list[NamedEvent]
    score: float
    causal_links: list[CausalLink]
    narrative_role: NarrativeRole
    bonus_applied: float  # internal, not serialized to bundle
    # Recorded "because" chains ending at events of this moment (root first).
    causal_chains: list[CausalChain] = Field(default_factory=list)


class AgentContext(BaseModel):
    """Agent narrative context for the narrator prompt (M30)."""
    named_characters: list[dict] = Field(default_factory=list)
    population_mood: str = "content"  # "desperate" > "restless" > "content"
    displacement_fraction: float = 0.0
    # M40: Social Networks — merged view of social edges + hostage state
    relationships: list[dict] = Field(default_factory=list)
    # M41: wealth inequality for narrator
    gini_coefficient: float = 0.0
    # M43b: Trade & supply context
    trade_dependent_regions: list[str] = Field(default_factory=list)
    active_shocks: list[ShockContext] = Field(default_factory=list)
    # M56b: Urbanization context
    urban_fraction_delta_20t: float = 0.0
    top_settlements: list[SettlementSummary] = Field(default_factory=list)


class ChronicleEntry(BaseModel):
    """A narrated chronicle entry covering a range of turns."""
    turn: int  # anchor turn
    covers_turns: tuple[int, int]  # inclusive range
    events: list[Event]
    named_events: list[NamedEvent]
    narrative: str  # LLM prose or mechanical fallback
    importance: float
    narrative_role: NarrativeRole
    causal_links: list[CausalLink]
    # Recorded causal chains (root first); omitted while empty.
    causal_chains: list[CausalChain] = Field(default_factory=list)
    # In-world accounts the narration drew on (ids in the bundle's
    # ``historiography.accounts``); omitted while empty.
    accounts: list[str] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_empty_chains(self, handler):
        return _omit_empty_fields(handler(self), (("causal_chains", []), ("accounts", [])))
