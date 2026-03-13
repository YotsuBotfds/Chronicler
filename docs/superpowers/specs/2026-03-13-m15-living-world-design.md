# M15: Living World — Design Spec

**Date:** 2026-03-13
**Branch:** (to be created from main after M13/M14 merge)
**Depends on:** M13b (resources, fertility, trade routes, adjacency graph, BUILD action, famine), M15 can run in parallel with M14
**Scope:** Four sequential phases: M15a → M15b → M15c → M15d
**Note:** This spec supersedes the Phase 3 roadmap (`chronicler-phase3-roadmap.md`) for all M15 details. Where the roadmap and this spec disagree, this spec is authoritative.

## Overview

The map is a living system that changes over centuries, rewards investment, punishes neglect. M15 makes terrain load-bearing for every military, economic, and environmental calculation. Civs build infrastructure that accumulates over time. Climate cycles and natural disasters reshape the map on long timescales. Unexplored regions hide opportunities and dangers.

All mechanics are pure Python simulation — no LLM calls required. The narrative engine describes what happened; it doesn't decide what happens.

### Design Principles

- **Geography is destiny.** Terrain type permanently constrains what a region can do. You can irrigate plains, but you can't irrigate a desert. Mountains are defensible but infertile. Coast enables trade but risks flooding. Every strategic decision starts with "what terrain do I have?"
- **Investment compounds, neglect cascades.** Infrastructure takes turns and treasury to build but persists through conquest. Mines degrade fertility. Droughts accelerate soil loss. Failing to irrigate before a drought hits has lasting consequences.
- **Four independent modules, one-directional dependencies.** `terrain.py` (pure functions on region properties) → `infrastructure.py` (build lifecycle, interacts with terrain) → `climate.py` (cycles and disasters, reads terrain and infrastructure) → `exploration.py` (visibility layer, self-contained). Each module is a single PR, testable before the next.

### Phase Summary

| Phase | Name | Module | Deliverable |
|-------|------|--------|-------------|
| M15a | Terrain & Chokepoints | `terrain.py` | Terrain defense/fertility/trade effects, region role classification |
| M15b | Infrastructure | `infrastructure.py` | Typed infrastructure, multi-turn builds, scorched earth reaction |
| M15c | Climate & Disasters | `climate.py` | Climate cycles, natural disasters, migration |
| M15d | Exploration & Ruins | `exploration.py` | Fog-of-war, EXPLORE action, first contact, ruins |

---

## Phase M15a: Terrain & Chokepoints

### Goal

Make `Region.terrain` load-bearing. Currently decorative — after M15a, terrain affects combat defense, trade income, fertility caps, and resource generation. Chokepoint inference extends the existing `adjacency.py` graph utilities.

### Model Changes

**`Region` (models.py):**
```python
role: str = "standard"  # standard, crossroads, frontier, chokepoint
```

Computed once at world generation from the adjacency graph. Immutable geography — not recomputed when borders change, only when adjacencies change (which currently only happens at world gen).

No other new fields. M15a uses existing `terrain`, `fertility`, `carrying_capacity`, `adjacencies`. Terrain effects are computed via pure functions exported from `terrain.py`.

### New Module: `src/chronicler/terrain.py`

Exports pure functions. No state. Other modules import and call these.

### Terrain Effects Table

```
Terrain     | Defense | Fertility Cap | Trade Mod | Notes
------------|---------|---------------|-----------|------
plains      | +0      | 0.9           | +0        | High food, no defense
forest      | +10     | 0.7           | +0        | Timber, decent defense
mountains   | +20     | 0.6           | +0        | Best defense, low food
coast       | +0      | 0.8           | +2        | Sea trade, flood risk
desert      | +5      | 0.3           | +0        | Rare minerals, harsh
tundra      | +10     | 0.2           | +0        | Iron/fuel, harsh defense
```

### Functions Exported

```python
TERRAIN_EFFECTS: dict[str, TerrainEffect]  # lookup table for the values above

def terrain_defense_bonus(region: Region) -> int:
    """Military defense modifier for combat in this region."""

def terrain_fertility_cap(region: Region) -> float:
    """Maximum fertility for this terrain type. Hard ceiling."""

def effective_capacity(region: Region) -> int:
    """int(base_capacity × min(fertility, terrain_fertility_cap)).
    Single source of truth — replaces all inline int(carrying_capacity * fertility) calls."""

def terrain_trade_modifier(region: Region) -> int:
    """Additional trade income for routes through this region (coast = +2, others = 0)."""
```

### Fertility Cap Interaction with M13

M13's fertility phase does `fertility += 0.01` (recovery) or `fertility -= 0.02` (degradation), clamped to `[0.0, 1.0]`. M15a adds a terrain-based cap below 1.0.

**The cap applies as a ceiling during the tick, not as a clawback.** Recovery formula: `fertility = min(fertility + 0.01, terrain_fertility_cap(region))`. A desert region at fertility 0.28 recovers to 0.29, then 0.30, then stops — it recovers *to* its natural cap, never *past* it. A degraded desert can heal to its natural state but no further.

**`effective_capacity` replaces all `int(carrying_capacity * fertility)` calls across the codebase.** M13's fertility phase, famine trigger, population growth, M14's capital reassignment — all import `terrain.effective_capacity` instead of computing inline.

### Integration Points

- **Combat (simulation.py, action phase):** WAR resolution adds `terrain_defense_bonus(defender_region)` to defender's military for that battle. Replaces the current flat comparison.
- **Fertility (simulation.py, phase 9):** Recovery capped by `terrain_fertility_cap()`. Degradation unchanged.
- **Trade (phase 2, automatic effects):** `terrain_trade_modifier()` added to trade route income for routes where either endpoint is coastal.

### Region Role Classification

`adjacency.py` already has `is_chokepoint()` from P2. M15a adds a unified classifier:

```python
def classify_regions(adjacencies: dict[str, list[str]]) -> dict[str, str]:
    """Classifies all regions. Called once at world generation.
    Returns {region_name: role_string}.

    - CROSSROADS: 3+ adjacencies
    - FRONTIER: exactly 1 adjacency
    - CHOKEPOINT: articulation point (only path between graph clusters)
    - STANDARD: everything else
    """
```

**Role effects:**
- **Crossroads** (3+ adjacencies): trade +3, defense -5. Hub regions are rich but exposed.
- **Frontier** (1 adjacency): defense +10, trade -2. Borderlands are defensible but isolated.
- **Chokepoint** (articulation point): trade toll +5 (income for controller), strategic value flag for action engine weighting.
- **Standard**: no modifier.

Role effects stack with terrain effects. A coastal crossroads gets terrain trade +2 and role trade +3 = +5 total. A mountain frontier gets terrain defense +20 and role defense +10 = +30.

Roles stored on `Region.role` at world generation. **Immutable geography** — roles do not change when borders change, because adjacencies don't change when borders change. The recomputation trigger is "when adjacencies change," which currently only happens at world generation.

### Testing

- Terrain defense: "mountain region adds +20 to defender's military in combat resolution."
- Fertility cap: "desert region fertility never exceeds 0.3 after 100 turns of depopulation."
- Fertility recovery to cap: "desert at 0.28 recovers to 0.29, 0.30, stays at 0.30."
- Effective capacity: "region with base_capacity=80, fertility=0.5, terrain_cap=0.6 → effective=40."
- Coastal trade modifier: "trade route with coastal endpoint gets +2 income."
- Chokepoint classification: "region with degree 1 → FRONTIER, degree 4 → CROSSROADS."
- Role stacking: "mountain frontier defense = 20 + 10 = 30."
- Regression: existing M13 scenario tests pass with terrain effects active.

---

## Phase M15b: Infrastructure

### Goal

Replace M13b-1's flat BUILD action (`carrying_capacity += 10` or `fertility += 0.1`) with typed infrastructure that persists through conquest, takes multiple turns to build, and interacts with terrain. The "rewards investment" half of M15.

### Model Changes

**`Region` (models.py) — replace `infrastructure_level`:**
```python
infrastructure: list[Infrastructure] = Field(default_factory=list)
pending_build: PendingBuild | None = None
```

`infrastructure_level: int` is dropped. It was "tracked but unused" per M13 spec — no migration needed.

**New models (models.py):**
```python
class InfrastructureType(str, Enum):
    ROADS = "roads"
    FORTIFICATIONS = "fortifications"
    IRRIGATION = "irrigation"
    PORTS = "ports"
    MINES = "mines"

class Infrastructure(BaseModel):
    type: InfrastructureType
    builder_civ: str
    built_turn: int
    active: bool = True  # False = scorched earth / disaster damage

class PendingBuild(BaseModel):
    type: InfrastructureType
    builder_civ: str
    started_turn: int
    turns_remaining: int
```

### Infrastructure Types

```
Type           | Cost | Build | Terrain Req  | Effect
---------------|------|-------|--------------|-------
roads          |  10  |   2   | —            | Trade +2 between connected regions
fortifications |  15  |   3   | —            | Defense +15 (stacks with terrain + role)
irrigation     |  12  |   2   | not desert   | Raises terrain fertility cap by +0.15
ports          |  15  |   3   | coast only   | Enables sea trade, trade +3
mines          |  10  |   2   | —            | Resource trade value ×1.5, fertility -0.03/turn
```

**Irrigation in desert is explicitly blocked.** Desert fertility cap 0.3 is a hard geographic constraint. If you want food in the desert, trade for it.

**No duplicate infrastructure types per region.** Can't build two fortifications. Can build roads + fortifications + irrigation in the same region over time.

**One build per region at a time.** `pending_build` is `None | PendingBuild`. Forces strategic choice: "do I fortify or irrigate first?"

### New Module: `src/chronicler/infrastructure.py`

### Key Design Decisions

**Irrigation raises the terrain fertility cap.** A plains region with irrigation has effective cap `0.9 + 0.15 = 1.05`, clamped to 1.0. A forest region goes from 0.7 to 0.85. Irrigation genuinely improves the region's potential — it doesn't just restore fertility, it raises the ceiling. Deserts excluded: geography wins.

**Mines degrade fertility as a running cost.** `-0.03/turn` is faster than natural recovery (`+0.01/turn`). A plains region at fertility 0.9 with a mine hits the famine threshold (0.3) in ~20 turns. **Mines are only viable in regions you're willing to irrigate or sacrifice.** The intended gameplay loop: mine + irrigation costs 22 treasury and 4 turns total — a significant investment that keeps the mine sustainable. Without irrigation, a mine is a ticking time bomb. This is documented as intentional design, not a balance oversight.

**Fortifications stack with terrain and role defense.** Mountains + fortifications = +35 defense. A fortified mountain pass is nearly impregnable — but it costs 15 treasury and 3 turns you could have spent irrigating.

### BUILD Action Handler

Replaces M13b-1's BUILD handler in the action registry.

**Eligibility check (in `get_eligible_actions`):** BUILD is eligible when the civ has at least one region with no `pending_build` AND at least one valid infrastructure type for that region (e.g., ports require coast, irrigation excluded in desert, no duplicate types). BUILD is **ineligible** if no valid build exists — the action engine never selects BUILD only to have it fail.

```python
def handle_build(world: WorldState, civ: Civilization, target_region: str) -> Event:
    """
    Target selection (weighted by action engine):
    - Fortifications: prioritize border regions adjacent to HOSTILE/SUSPICIOUS civs
    - Irrigation: prioritize regions where fertility < terrain_cap - 0.1
    - Roads: prioritize regions on active trade routes without roads
    - Ports: prioritize coastal regions without ports
    - Mines: prioritize regions with rare_minerals or iron resources

    Type selection priority (trait-weighted):
    - Aggressive traits → fortifications
    - Cautious/mercantile → roads, ports
    - Expansionist → irrigation
    - Default: whichever type provides highest marginal value for the civ
    """
```

Build starts on action turn. Each subsequent turn, `pending_build.turns_remaining -= 1` in automatic effects (phase 2). When `turns_remaining == 0`, infrastructure is created and `pending_build` cleared.

### Scorched Earth

**First use of the `REACTION_REGISTRY` from P3.** Registered as `REACTION_REGISTRY["region_lost"] = scorched_earth_check`. War resolution fires the `"region_lost"` trigger, the registry dispatches the handler. Validates the reaction architecture before M16 adds more reactions.

```python
def scorched_earth_check(
    world: WorldState, defender: Civilization, lost_region: Region
) -> list[Event]:
    """
    Triggered when defender loses a region in war.
    Probability of scorching = (1.0 - stability/100).
    Low stability → more likely to destroy rather than let the enemy have it.
    Aggressive trait: +0.2 probability.

    Binary: destroys ALL infrastructure if triggered (sets active=False).
    No cherry-picking. A desperate civ burns everything.
    """
```

Scorched earth is discoverable by inspecting the registry rather than buried in war resolution logic.

### Infrastructure Persistence

Active infrastructure persists through conquest. New controller benefits from roads, ports, mines left behind. Fortifications defend whoever holds the region. Scorched earth is the only way to deny value.

### Automatic Effects (Phase 2)

```python
def tick_infrastructure(world: WorldState) -> list[Event]:
    """Called from apply_automatic_effects in simulation.py."""
    # 1. Advance pending builds (turns_remaining -= 1, complete if 0)
    # 2. Apply mine fertility degradation (-0.03/turn per active mine)
    # 3. Road/port trade bonuses are read by trade income calculation (not applied here)
```

### Integration with Existing Systems

- **Trade income (phase 2):** Roads add +2 to trade routes between connected regions (both endpoints or either endpoint has roads). Ports add +3 and enable sea trade for the region. These modify the existing trade income calculation in `apply_automatic_effects`.
- **Combat (action phase):** Fortifications add +15 defense, stacking with `terrain_defense_bonus()` and role defense from M15a.
- **Fertility (phase 9):** Irrigation raises terrain fertility cap by +0.15 for that region. Mine degradation (-0.03/turn) applies before the standard fertility tick. Phase 9 order: mine degradation → standard fertility tick (degradation/recovery) → cap to `terrain_fertility_cap + irrigation_bonus`.
- **Famine (phase 10):** Irrigated regions are less likely to hit the 0.3 famine threshold. Infrastructure as famine prevention.

### Testing

- Build lifecycle: "BUILD roads in region, assert pending_build exists, advance 2 turns, assert roads in infrastructure list, pending_build is None."
- Terrain restriction: "BUILD ports in non-coastal region → BUILD ineligible, not selected."
- Desert irrigation blocked: "Desert region → irrigation not in valid types."
- No duplicates: "Region with roads → roads not in valid types for that region."
- One build at a time: "Region with pending_build → region excluded from BUILD target selection."
- BUILD eligibility: "Civ where all regions have pending builds → BUILD ineligible action."
- Scorched earth: "Defender with stability 10 loses region → 90% scorch probability. All infrastructure set active=False."
- Scorched earth registry: "REACTION_REGISTRY['region_lost'] resolves to scorched_earth_check."
- Mine degradation: "Region with mine, fertility 0.7, after 10 turns fertility = 0.7 - (0.03 × 10) = 0.4."
- Mine + irrigation combo: "Region with mine + irrigation, fertility cap raised by 0.15, mine degrades at 0.03/turn, net decline 0.02/turn with recovery."
- Irrigation cap raise: "Forest region with irrigation → effective fertility cap = 0.7 + 0.15 = 0.85."
- Fortification stacking: "Mountain region with fortifications → total defense = terrain 20 + fort 15 = 35."
- Persistence: "Civ A builds roads in region, Civ B conquers region → Civ B gets road trade bonus."
- Infrastructure destruction by earthquake: see M15c testing.

---

## Phase M15c: Climate, Disasters & Migration

### Goal

Long-cycle environmental pressure (climate) and short-burst shocks (disasters) that reshape the map over centuries. Migration is the connective tissue — climate and disasters push population along adjacency edges, creating cascading instability. This is the "punishes neglect" half of M15.

### Model Changes

**`WorldState` (models.py):**
```python
climate_config: ClimateConfig = Field(default_factory=ClimateConfig)
```

**`Region` (models.py):**
```python
disaster_cooldowns: dict[str, int] = Field(default_factory=dict)
# e.g. {"wildfire": 8} — turns remaining before this disaster type can recur
```

**New models (models.py):**
```python
class ClimatePhase(str, Enum):
    TEMPERATE = "temperate"
    WARMING = "warming"
    DROUGHT = "drought"
    COOLING = "cooling"

class ClimateConfig(BaseModel):
    period: int = 75
    severity: float = 1.0
    start_phase: ClimatePhase = ClimatePhase.TEMPERATE
```

No mutable climate state on WorldState. Climate phase is a pure function of turn number and config.

### New Module: `src/chronicler/climate.py`

### Climate as Pure Function

```python
PHASE_SCHEDULE = [
    (0.0,  ClimatePhase.TEMPERATE),  # 0-40% of period
    (0.4,  ClimatePhase.WARMING),    # 40-60%
    (0.6,  ClimatePhase.DROUGHT),    # 60-80%
    (0.8,  ClimatePhase.COOLING),    # 80-100%
]

def get_climate_phase(turn: int, config: ClimateConfig) -> ClimatePhase:
    """Pure function. No state. Deterministic from turn + config.
    Civs can see it coming — determinism is a feature, not a limitation."""
    position = (turn % config.period) / config.period
    # walk schedule backwards to find current phase
```

No `climate_offset` field — M18 can add one when it needs to mutate the cycle (supervolcano advances climate). YAGNI until then.

### Climate Effects on Terrain Fertility

Climate modifies the **fertility tick rate**, not just transient reads. Droughts cause lasting damage — topsoil loss, aquifer depletion. The deterministic cycle means civs can prepare (irrigate before drought, reduce population pressure), but failing to prepare has lasting consequences.

**During phase 9 (fertility tick):** degradation rate is multiplied by the inverse of the climate fertility multiplier. Recovery rate stays constant at +0.01/turn (recovering is always slow).

```
Phase     | Plains | Forest | Coast  | Desert | Tundra | Mountains
----------|--------|--------|--------|--------|--------|----------
temperate | ×1.0   | ×1.0   | ×1.0   | ×1.0   | ×1.0   | ×1.0
warming   | ×1.0   | ×1.0   | ×1.0*  | ×1.0   | ×2.0   | ×1.0**
drought   | ×0.5   | ×0.7   | ×1.0   | ×1.0   | ×1.0   | ×1.0
cooling   | ×0.8   | ×0.8   | ×0.8   | ×0.8   | ×0.3   | ×0.8
```

\* Coast during warming: flood risk 5%/turn (see disasters), not fertility rate change.
\*\* Mountains during warming: defense bonus removed (returns +0 instead of +20). Snow melts, passes open. A civ relying on mountain defense gets a ~15-turn window of vulnerability every 75 turns.

**Warming fertility is intentionally ×1.0 for plains/forest/coast.** Warming's pressure comes from flood risk and the tundra trap, not crop stress. Warming is a coastal/tundra phase, not a fertility phase.

**Severity scaling:** All multiplier deviations from 1.0 are scaled by `config.severity`.
- Drought plains: multiplier = `1.0 + (0.5 - 1.0) × severity`. At severity 1.0 → 0.5. At severity 0.5 → 0.75. At severity 0 → 1.0 (no effect).
- Degradation rate during drought on plains (severity 1.0): `-0.02 × (1/0.5)` = -0.04/turn.
- Degradation rate during drought on plains (severity 0.5): `-0.02 × (1/0.75)` ≈ -0.027/turn.

```python
def climate_fertility_multiplier(
    terrain: str, phase: ClimatePhase, severity: float
) -> float:
    """Returns multiplier for the terrain's fertility behavior this phase.
    Applied to degradation rate during phase 9: rate = base_rate × (1 / multiplier).
    Recovery rate always stays +0.01."""
```

**Cooling asymmetry (documented as intentional):** During cooling, degradation rate = `-0.02 × (1/0.8)` = -0.025, but recovery stays +0.01. Cooling slows degradation slightly but doesn't accelerate recovery. Cold periods are mildly protective of soil health — less activity means less damage. Tundra at ×0.3 is the exception: cooling is devastating for already-marginal land.

**Tundra warming trap:** Tundra fertility cap effectively doubles to 0.4 during warming. Tundra regions bloom. Civilizations that expand into tundra during warming get burned when cooling hits and the effective cap drops to `0.2 × 0.3 = 0.06`. Population that grew during the warm spell now far exceeds capacity → migration cascade.

### Natural Disasters

Terrain-dependent, low probability per turn. Run inside the existing **environment phase (phase 1)**, replacing the old scripted disaster events with terrain-driven mechanics.

```python
def check_disasters(world: WorldState) -> list[Event]:
    """Called from environment phase (phase 1). Replaces old random disaster logic."""
```

**Disaster table:**

```
Disaster   | Terrain    | Base Prob | Climate Mod        | Effects
-----------|------------|-----------|--------------------|---------
earthquake | mountains  | 2%/turn   | —                  | fertility -0.2, destroy 1 random active infrastructure
flood      | coast      | 3%/turn   | ×2 during warming  | fertility -0.1, destroy ports (set active=False)
wildfire   | forest     | 2%/turn   | ×2 during drought  | timber resource suspended 10 turns, fertility -0.15
sandstorm  | desert     | 3%/turn   | —                  | trade routes through region suspended 5 turns
```

**Cooldowns:** After a disaster fires, that disaster type can't recur in that region for 10 turns. Stored in `region.disaster_cooldowns`, decremented each turn in phase 1 before probability checks. Prevents back-to-back earthquakes from making mountain regions unplayable.

**Severity scaling:** Base probabilities multiplied by `config.severity`. At severity 0.5, earthquake = 1%/turn. At severity 2.0, earthquake = 4%/turn. Severity 0 disables disasters entirely.

**Probability is deterministic from seed.** Each region+turn+disaster_type combination produces a deterministic random value from `hash(world.seed, region.name, turn, disaster_type) % 10000 / 10000`. No `random.random()` calls.

**Infrastructure interaction (intentional cascading failures):**
- **Earthquake** destroys 1 random active infrastructure. An earthquake destroying irrigation in a mine-degraded region is disproportionately devastating — the mine keeps degrading fertility, famine hits ~8 turns later. This cascade is intended behavior, not a balance issue.
- **Flood** specifically targets ports (the coastal infrastructure). A port destroyed by flooding cuts sea trade income.
- **Wildfire** doesn't destroy infrastructure — fires burn forests, not stone buildings. It suspends the timber resource.
- **Sandstorm** doesn't destroy infrastructure — it temporarily blocks trade routes.

### Migration

Population displacement when a region can't support its people. Simple, deterministic, cascading.

```python
def process_migration(world: WorldState) -> list[Event]:
    """Called at end of phase 1 (environment), after disasters and climate effects.
    Runs after all fertility modifications for the turn."""
```

**Trigger:** `effective_capacity(region) < region_pop × 0.5`, where `region_pop = civ.population // len(civ.regions)` (same per-region population proxy as M13's fertility system).

This can be triggered by:
- Fertility degradation from overpopulation (M13)
- Mine degradation (M15b)
- Climate drought multiplier (M15c)
- Disaster fertility damage (M15c)
- Famine aftermath (M13b)

**Mechanics:**
1. Compute `region_pop = civ.population // len(civ.regions)`
2. Compute `surplus = region_pop - effective_capacity(region)`
3. Identify adjacent regions. Filter out regions controlled by civs with HOSTILE disposition toward the source civ's controller. Uncontrolled regions absorb into void (population lost).
4. Distribute surplus equally across eligible receiving regions.
5. For each receiving region: identify controlling civ, increment `controlling_civ.population += share`, apply `controlling_civ.stability -= 3` (refugee pressure).
6. Source civ: `civ.population -= surplus`.
7. If receiving regions are also at capacity, they become migration sources **next turn** (cascade).

**Migration events:** Importance scaled by population displaced: `min(5 + surplus // 10, 9)`. Large migrations are historically significant.

**No eligible receiving regions (all adjacent HOSTILE or uncontrolled):** Population drops anyway (`civ.population -= surplus`) but event type is "famine" not "exodus." The people starve rather than flee.

### Phase 1 Execution Order

The environment phase becomes:
1. Decrement disaster cooldowns for all regions
2. Compute current climate phase: `get_climate_phase(world.turn, world.climate_config)`
3. Check and apply disasters (terrain-dependent probabilities × climate modifiers × severity)
4. Process migration (reads post-disaster effective capacity via `terrain.effective_capacity`)

**Climate fertility multiplier is applied during phase 9 (fertility tick), not phase 1.** Phase 1 handles disasters and migration. Phase 9 handles the ongoing fertility degradation/recovery with climate-modified rates. These are separate concerns: disasters are discrete shocks, climate modifies long-term soil dynamics.

### Scenario Config

```yaml
climate:
  period: 75          # turns per full cycle
  severity: 1.0       # multiplier on all climate/disaster effects (0 = disabled)
  start_phase: temperate
```

Missing `climate` block → defaults above (period 75, severity 1.0, temperate start). Severity 0 effectively disables climate and disasters.

### Testing

- Climate phase: "turn 0, period 75 → temperate. Turn 30 → temperate. Turn 31 → warming. Turn 45 → warming. Turn 46 → drought. Turn 60 → drought. Turn 61 → cooling."
- Fertility multiplier: "plains in drought, severity 1.0 → degradation rate doubled to -0.04/turn."
- Severity scaling: "severity 0.5, drought plains → degradation rate ≈ -0.027/turn."
- Mountain defense in warming: "warming phase → terrain_defense_bonus(mountain_region) returns 0."
- Tundra warming trap: "tundra fertility cap effectively 0.4 during warming, population grows, cooling hits → cap drops to 0.06, migration cascade."
- Disaster cooldown: "earthquake fires, region cooldown set to 10, no earthquake possible for 10 turns."
- Disaster determinism: "same seed + same region + same turn → same disaster outcome."
- Earthquake-infrastructure: "earthquake in region with 3 active infrastructure → 1 random destroyed."
- Earthquake-irrigation cascade: "earthquake destroys irrigation in mined region → fertility degrades unchecked → famine within 10 turns."
- Flood-port: "flood in coastal region with port → port.active = False."
- Climate-disaster interaction: "drought + forest region → wildfire probability 4%/turn."
- Severity 0: "severity 0.0 → no disasters fire, climate multipliers all 1.0."
- Migration trigger: "region effective_capacity 20, region_pop 50 → migration fires, surplus 30."
- Migration distribution: "surplus 30, 3 eligible adjacent regions → each receiving civ gets +10 population, -3 stability."
- Migration hostile border: "all adjacent regions HOSTILE → no migration, population drops, famine event."
- Migration cascade: "drought causes migration from A→B, B already near capacity → B migrates to C next turn."
- Migration to uncontrolled region: "refugees to uncontrolled region → population lost to void."
- End-to-end climate cycle: "run 75 turns, verify phase transitions at correct turns, fertility tracks expected degradation/recovery curves per terrain type."

---

## Phase M15d: Exploration & Ruins

### Goal

Not all regions are known at simulation start. Civs discover the map through exploration, expansion, and trade contact. Depopulated regions decay into ruins that reward rediscovery. Most self-contained phase — adds a visibility layer without changing mechanics of discovered regions.

### Model Changes

**`Civilization` (models.py):**
```python
known_regions: list[str] | None = None
# None = omniscient (fog_of_war disabled). list[str] = fog active.
```

`list[str]` not `set[str]` — sets aren't JSON-native and would require custom serialization. Consistent with how `adjacencies` (also a list of strings) works. Functions that operate on `known_regions` convert to set internally for O(1) lookups.

`None` as omniscient sentinel means existing scenarios (no fog config) work unchanged — zero migration cost.

**`Region` (models.py):**
```python
depopulated_since: int | None = None   # turn when last controller was lost
ruin_quality: int = 0                   # peak active infrastructure count at time of depopulation
```

**`WorldState` (models.py):**
```python
fog_of_war: bool = False
```

**`ScenarioConfig` (scenario.py):**
```yaml
fog_of_war: true | false  # explicit override
# If omitted: true for ≥15 regions, false otherwise
```

### New Module: `src/chronicler/exploration.py`

### Fog of War

**Initialization:** At world gen, if `fog_of_war` is true, each civ's `known_regions` is seeded with:
- Home region(s) (all regions in `civ.regions`)
- All regions adjacent to home regions (from adjacency graph)

If `fog_of_war` is false, `known_regions` stays `None` (omniscient).

**Discovery vectors:**

1. **EXPLORE action** — reveals 1 unknown region adjacent to any known region. Cost: 5 treasury. See EXPLORE action section.

2. **Expansion** — conquering or colonizing a region reveals all its adjacencies. Added to `known_regions` during war/expansion resolution.

3. **Trade contact** — when a trade route activates between two civs, they share regions **within 2 hops of the trade route endpoints**, not their full known sets. Each subsequent turn of active trading shares 1 additional hop outward. Gradual cartographic exchange through sustained trade — more interesting than instant omniscience from a single contact.

4. **Migration from unknown regions** — when migration pushes population from an undiscovered region into a civ's known region, the source region is added to `known_regions`. Refugees arriving reveal where they fled from: "people fleeing drought in the western wastes" is a discovery event.

**What fog hides:**
- Civ can only target regions it knows about for WAR/EXPAND actions
- Trade routes can only be established through known regions
- Threats from unknown regions are invisible until they arrive

**What fog doesn't hide:**
- Climate phase is global knowledge (observable weather patterns)
- Disaster events in unknown regions are not reported to civs that don't know the region — narrative/viewer concern only, simulation runs all regions regardless

### EXPLORE Action

Registered in the action registry. Eligible when: `fog_of_war is True` AND civ has at least one known region adjacent to an unknown region AND `treasury >= 5`.

```python
def handle_explore(world: WorldState, civ: Civilization) -> Event:
    """
    Target selection: unknown region adjacent to a known region.
    Priority weighting:
    - Adjacent to capital or high-population regions (explore nearby first)
    - Regions adjacent to known resource-rich regions (follow the wealth)
    - Deterministic tiebreaker from world.seed + turn

    Cost: 5 treasury.
    Result: target region added to civ.known_regions.
    All target's adjacencies also added (you can see what's next to what you found).
    If target contains ruins: bonus discovery event (see Ruins section).
    If target controlled by unknown civ: first contact event (see First Contact).
    """
```

**Trait weighting for EXPLORE in `TRAIT_WEIGHTS`:**
- Expansionist: 1.5×
- Cautious: 0.5×
- Mercantile: 1.2× (seeking trade partners)

### First Contact

When two civs that have never had a relationship entry discover each other:

```python
def check_first_contact(
    world: WorldState, discovering_civ: str, discovered_civ: str
) -> Event | None:
    """
    Triggers when civ discovers a region controlled by another civ
    AND no relationship entry exists between them.

    Effects:
    - Creates relationship entry (starts NEUTRAL).
    - Event importance: 8 (major historical moment).
    - Symmetric: discovering civ's known_regions shared with discovered civ
      (mutual awareness — you can't observe a civilization without them noticing).
    - Both civs share regions within 2 hops of the contact point.
    """
```

### Ruins

**Depopulation tracking:** When a region's controller becomes `None` (conquest with depopulation, civ eliminated, twilight absorption from M14½):

```python
def mark_depopulated(region: Region, turn: int) -> None:
    """Called when region.controller becomes None."""
    region.depopulated_since = turn
    region.ruin_quality = len([i for i in region.infrastructure if i.active])
    # All infrastructure set to active=False (decay in abandoned region)
    for infra in region.infrastructure:
        infra.active = False
```

**Ruin formation:** A depopulated region becomes "ruins" after 20 turns uncontrolled. No model change needed — `depopulated_since` being 20+ turns ago *is* the ruin state. Checked via: `region.depopulated_since is not None and (current_turn - region.depopulated_since) >= 20`.

**Ruin discovery:** When a civ explores or expands into a ruin region:

```python
def discover_ruins(
    civ: Civilization, region: Region, current_turn: int
) -> Event | None:
    """
    Culture boost with diminishing returns based on discoverer's current culture:
    boost = ruin_quality × 5 × (1.0 - civ.culture / 100)

    A tribal civ at culture 20 finding quality-5 ruins: 25 × 0.8 = 20 culture.
    An advanced civ at culture 80 finding quality-5 ruins: 25 × 0.2 = 5 culture.
    Primitives learn more from ruins than sophisticates.

    Region stops being ruins: depopulated_since = None, ruin_quality = 0.
    ruin_quality 0 (no infrastructure when depopulated) → no boost, no event.

    Event importance: 6 + min(ruin_quality, 4).
    Quality-5 ruins = importance 10 discovery.
    """
```

**Ruins don't stack.** If a region is depopulated, repopulated, and depopulated again, `ruin_quality` is overwritten with the new infrastructure count. Older civilization's ruins are lost.

### Integration Points

- **Action engine (phase 4):** EXPLORE registered in action registry. Eligibility: fog active AND unknown adjacent regions exist AND treasury >= 5.
- **War/Expand resolution (phase 4):** After conquering a region, add all its adjacencies to conqueror's `known_regions`.
- **Trade route activation (phase 2):** When a new trade route activates, share `known_regions` within 2 hops of endpoints. Each turn of active trading: expand shared region radius by 1 hop. Check for first contact if newly visible regions reveal unknown civs.
- **Migration (phase 1):** Migration from unknown region into known region → source added to `known_regions`.
- **Consequences (phase 10):** Check for newly depopulated regions (controller lost) → call `mark_depopulated`. Check if any civ expanded into a ruin region → call `discover_ruins`.
- **Viewer:** Territory map shows fog-of-war per civ. Viewer can toggle which civ's perspective to show. Ruins get a distinct visual marker.

### Edge Cases

- **All regions known:** EXPLORE becomes ineligible. Fog effectively disabled for that civ.
- **Civ starts with 0 unknown adjacencies (small map):** EXPLORE ineligible from turn 1. Fog technically active but has no effect.
- **Fog disabled mid-game:** Not supported. Fog is a scenario-level setting, not toggleable.
- **Secession (M14):** Breakaway civ inherits parent's `known_regions` copy. They remember what the empire knew.
- **Vassal (M14):** Vassal and overlord share `known_regions` — overlord sees what vassal sees and vice versa.
- **Federation (M14):** All federation members share `known_regions`.

### Testing

- Fog initialization: "5-civ, 20-region map with fog → each civ knows home + adjacencies, not distant regions."
- EXPLORE action: "civ explores unknown adjacent region → region + its adjacencies added to known_regions, 5 treasury spent."
- EXPLORE eligibility: "civ with no unknown adjacent regions → EXPLORE ineligible."
- EXPLORE ineligible without fog: "fog_of_war=false → EXPLORE never eligible."
- Trade contact gradual sharing: "civ A trades with civ B → both learn regions within 2 hops of trade endpoints. Next turn: 3 hops. Turn after: 4 hops."
- First contact: "two isolated civs, A explores into B's territory → importance 8 event, relationship created at NEUTRAL, symmetric region sharing within 2 hops of contact point."
- Migration discovery: "drought causes migration from unknown region X into civ's known region Y → X added to civ's known_regions."
- Ruin formation: "region depopulated at turn 50, checked at turn 70 → ruin (20 turns elapsed)."
- Ruin discovery with diminishing returns: "civ at culture 20 finds quality-4 ruins → boost = 20 × 0.8 = 16 culture. Civ at culture 80 finds same → boost = 20 × 0.2 = 4."
- Ruin quality zero: "depopulated region with no infrastructure → ruin_quality 0, no boost, no event."
- Infrastructure decay on depopulation: "region depopulated → all infrastructure set active=False."
- Ruins don't stack: "region depopulated with 3 infra, repopulated, depopulated with 1 infra → ruin_quality = 1."
- Secession inheritance: "breakaway civ from M14 secession → inherits parent's known_regions."
- Vassal sharing: "vassal's known_regions shared with overlord."
- War target restriction: "civ cannot target unknown region for WAR/EXPAND."
- Fog auto-enable: "20-region map, no fog_of_war in config → fog_of_war defaults to true."
- Fog auto-disable: "8-region map, no fog_of_war in config → fog_of_war defaults to false."

---

## Cross-Cutting Concerns

### Narrative Engine

Each phase adds new event types. Templates expand to cover:
- M15a: terrain-influenced battle descriptions ("defenders held the mountain pass")
- M15b: infrastructure events ("roads connecting X to Y completed"), scorched earth ("retreating forces burned the granaries")
- M15c: climate/disaster events ("a great drought settled over the plains"), migration ("refugees poured across the border")
- M15d: exploration events ("scouts returned with tales of fertile lands to the west"), first contact ("messengers from a distant civilization arrived"), ruin discovery ("in the ruins of the old empire, they found knowledge lost for generations")

No new LLM capabilities needed — richer structured data in prompts.

### Viewer Extensions

M11 viewer's panel architecture extends incrementally:
- M15a: terrain overlay with defense/trade modifiers shown on hover
- M15b: infrastructure icons on regions (road lines, fort shields, irrigation drops, port anchors, mine picks)
- M15c: climate state indicator in header, disaster markers on affected regions
- M15d: fog-of-war overlay (per-civ perspective toggle), ruin markers

### Scenario Compatibility

All new mechanics have sensible defaults. Existing scenarios work without modification:
- Missing `role` → computed at world gen from adjacency graph
- Missing `infrastructure`/`pending_build` → empty list / None
- Missing `disaster_cooldowns` → empty dict
- Missing `climate` config → period 75, severity 1.0, temperate start
- Missing `fog_of_war` → false for < 15 regions, true for ≥ 15
- Missing `known_regions` → None (omniscient)
- Missing `depopulated_since`/`ruin_quality` → None / 0

### Testing Philosophy

Each phase testable in isolation with deterministic seeds:
- **Condition-based assertions:** "given this config, assert famine occurs within turns 10-15" (not exact turn — cascading nature means small upstream changes shift timing).
- **Invariant tests:** "fertility never exceeds terrain_fertility_cap + irrigation_bonus", "effective_capacity never negative", "disaster cooldown prevents recurrence within 10 turns", "EXPLORE costs exactly 5 treasury."
- **Regression tests:** existing M13/M14 scenario test suites pass at each phase.
- **Scale test:** 500 turns × 10 civs × 20 regions with `--simulate-only` completes in < 30 seconds.

### Performance Budget

- `effective_capacity` is called frequently (every region, every turn, multiple phases). Must be O(1) — lookup table, not computation.
- Climate phase: O(1) pure function.
- Disaster checks: O(regions) per turn, with early-exit on cooldown.
- Migration: O(regions) per turn, cascades limited to one wave per turn (next-turn continuation, not recursive).
- `known_regions` membership checks: convert list to set once per turn for O(1) lookups, not O(n) per check.
