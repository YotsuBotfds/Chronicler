# M13: Resource Foundations & Economic Dynamics — Design Spec

**Date:** 2026-03-13
**Branch:** (to be created from main after M11/M12 merge)
**Depends on:** M11 (viewer bundle), M10 (workflow features)
**Scope:** Prerequisites P1-P3 + M13a + M13b (six sequential phases)
**Note:** This spec supersedes the Phase 3 roadmap (`chronicler-phase3-roadmap.md`) for all M13 details. Where the roadmap and this spec disagree (resource generation algorithm, black market distance, mercenary dissolution threshold), this spec is authoritative.

## Overview

Phase 3 gives the simulation material foundations — economics, politics, geography, culture, and characters — so that emergent behavior replaces scripted narrative. M13 is the first milestone: resources, trade, treasury mechanics, and emergent economic events.

All mechanics are pure Python simulation — no LLM calls required. The narrative engine describes what happened; it doesn't decide what happens.

### Design Principles

- **Scenario author control with sensible defaults.** Resources, adjacencies, coordinates — all follow the same pattern: explicit scenario YAML overrides with auto-generation as fallback.
- **Ship what the milestone needs, nothing more.** Actions, reactions, and systems register when the backing mechanics exist, not before.
- **Test each phase before starting the next.** Six phases with clear boundaries, each independently verifiable.

### Phase Summary

| Phase | Name | Deliverable |
|-------|------|-------------|
| P1 | Stat Scale Migration | 0-100 stats, updated scenarios, centralized floors |
| P2 | Region Adjacency Graph | Adjacency model, k-nearest, graph utilities |
| P3 | Action Engine v2 | Registry pattern, categories, automatic effects |
| M13a | Resource Foundations | Resources, fertility, trade routes, embargo, INFORMATION era, `--simulate-only` |
| M13b-1 | Treasury Mechanics | Maintenance, war costs, development scaling, BUILD action |
| M13b-2 | Emergent Economic Events | Famine cascades, black markets, mercenaries, specialization |

---

## Phase P1: Stat Scale Migration

### Goal

Expand the 1-10 integer scale to 0-100 for all civ stats. Treasury becomes uncapped. Asabiya stays 0.0-1.0. This is a mechanical migration — no new gameplay, but the zero-floor for non-population stats is a deliberate design change enabling future twilight/collapse mechanics.

### Model Changes

**`Civilization` fields:**
- `population`: `Field(ge=1, le=100)` — floor stays at 1 (zero population = dead, no elimination mechanic yet)
- `military`: `Field(ge=0, le=100)` — zero means defenseless (deliberate)
- `economy`: `Field(ge=0, le=100)` — zero means no income (deliberate)
- `culture`: `Field(ge=0, le=100)` — zero means cultural void (deliberate)
- `stability`: `Field(ge=0, le=100)` — zero means total collapse (deliberate)
- `treasury`: unbounded `int`, no cap (remove `treasury_cap` from production phase)
- `asabiya`: unchanged (`0.0-1.0`)

**`Region` fields:**
- `carrying_capacity`: `Field(ge=1, le=100)` (scaled ×10)

**`CivSnapshot`:** Update type annotations to match new ranges.

### Centralized Stat Floors

New constant in `utils.py`:

```python
STAT_FLOOR: dict[str, int] = {
    "population": 1,
    "military": 0,
    "economy": 0,
    "culture": 0,
    "stability": 0,
}
```

All `clamp()` callsites reference `STAT_FLOOR[stat_name]` for the lower bound instead of hardcoding. This gives exactly one place to audit floors.

### `ActiveCondition.severity` Scaling

`ActiveCondition.severity` currently has `Field(ge=1, le=10)`. Scale to `Field(ge=1, le=100)` (×10). The production phase formula `c.severity // 3` for condition penalties becomes `c.severity` directly (at the 0-100 scale, severity IS the penalty amount). Starting condition severities in scenario YAMLs also scale ×10.

### `clamp()` Callsite Inventory

Every `clamp()` call must be updated. The rule: use `clamp(x, STAT_FLOOR[stat], 100)` for civ stats, `clamp(x, 1, 100)` for carrying_capacity. Complete list:

**`simulation.py` — `phase_environment`:**
- `civ.stability = clamp(...)` — floor: `STAT_FLOOR["stability"]` (0)
- `civ.economy = clamp(...)` — floor: `STAT_FLOOR["economy"]` (0)
- `civ.population = clamp(...)` — floor: `STAT_FLOOR["population"]` (1)

**`simulation.py` — `phase_production`:**
- `civ.population = clamp(...)` (growth) — floor: `STAT_FLOOR["population"]` (1)
- `civ.population = clamp(...)` (decline) — floor: `STAT_FLOOR["population"]` (1)

**`simulation.py` — `_resolve_develop`:**
- `civ.economy = clamp(...)` — floor: `STAT_FLOOR["economy"]` (0)
- `civ.culture = clamp(...)` — floor: `STAT_FLOOR["culture"]` (0)

**`simulation.py` — `_resolve_expand`:**
- `civ.military = clamp(...)` — floor: `STAT_FLOOR["military"]` (0)

**`simulation.py` — `resolve_war`:**
- `attacker.military = clamp(...)` — floor: `STAT_FLOOR["military"]` (0)
- `defender.military = clamp(...)` — floor: `STAT_FLOOR["military"]` (0)
- `defender.stability = clamp(...)` — floor: `STAT_FLOOR["stability"]` (0)
- `attacker.stability = clamp(...)` — floor: `STAT_FLOOR["stability"]` (0)

**`simulation.py` — `phase_consequences`:**
- `civ.stability = clamp(...)` (condition tick) — floor: `STAT_FLOOR["stability"]` (0)
- `civ.military = clamp(...)` (collapse) — floor: `STAT_FLOOR["military"]` (0)
- `civ.economy = clamp(...)` (collapse) — floor: `STAT_FLOOR["economy"]` (0)

**`simulation.py` — `_apply_event_effects`:**
- All stat modifications (leader_death, rebellion, discovery, etc.) — use respective `STAT_FLOOR` entries

**`action_engine.py` — `_apply_situational`:**
- No `clamp()` calls (uses weight multipliers, not stat mutations)

**`tech.py` — `apply_era_bonus`:**
- `setattr(civ, stat, clamp(current + amount, STAT_FLOOR[stat], 100))`

**`scenario.py` — model bounds:**
- `RegionOverride.carrying_capacity`: `Field(default=None, ge=1, le=100)`
- `CivOverride` stats: `population` `Field(default=None, ge=1, le=100)`, all others `Field(default=None, ge=0, le=100)`

### Threshold Migration

All hardcoded thresholds scale ×10:

**`simulation.py`:**
- `civ.stability <= 2` → `<= 20`
- `civ.stability > 3` → `> 30`
- `civ.military >= 3` → `>= 30`
- `civ.population >= 8` → `>= 80`
- `civ.culture >= 3` → `>= 30`
- `civ.culture >= 8` / `>= 10` → `>= 80` / `>= 100`
- Population growth/decline increments: `+1`/`-1` → `+5`/`-5`
- Stat modifications from events: `+1`/`-1` → `+10`/`-10`, `+2`/`-2` → `+20`/`-20`
- Collapse thresholds: `asabiya < 0.1 and stability <= 2` → `asabiya < 0.1 and stability <= 20`
- Collapse effects: `military // 2`, `economy // 2` → same formula (proportional at any scale)

**`action_engine.py`:**
- `civ.stability <= 2` → `<= 20`
- `civ.military >= 7` → `>= 70`
- `civ.treasury >= 20` → `>= 200`
- `civ.treasury <= 3` → `<= 30`
- `civ.population >= 8` → `>= 80`
- `civ.economy <= 3` → `<= 30`

**`tech.py`:**
- `TECH_REQUIREMENTS` tuples: all `(culture, economy, cost)` values ×10
- `ERA_BONUSES`: `+1` → `+10`, `+2` → `+20`

### Production Phase Updates

**Temporary — replaced in M13b-1.** These formulas are straight ×10 migrations of the current logic, not final economic balance. M13b-1 rewrites the production phase with proper treasury economics. P1's goal is a working simulation at the new scale, not economic realism.

- Income: `civ.economy + len(civ.regions) * 10` *(temporary; M13b-1 replaces with `economy // 5 + len(civ.regions) * 2`)*
- Military maintenance: `civ.military // 2` *(temporary; P3 replaces with tiered system in `apply_automatic_effects`)*
- Treasury cap: **removed entirely** (permanent)
- Population growth: `+5` when conditions met (was `+1`) *(permanent)*
- Population decline: `-5` when stability <= 20 (was `-1` at stability <= 2) *(M13b-1 tightens threshold to stability <= 10)*

### Scenario YAML Migration

Hard break — all 6 scenario files updated in-place. All stat values ×10. Example:

```yaml
# Before (Post-Collapse Minnesota)
population: 6
military: 3
economy: 7
carrying_capacity: 6

# After
population: 60
military: 30
economy: 70
carrying_capacity: 60
```

No schema versioning. We own all 6 files, there are no external consumers.

### Test Migration

All test assertions checking absolute stat values get ×10. This is mechanical find-and-replace. Relative comparisons (e.g., `civ.economy > civ.population`) remain unchanged.

### Verification

- All existing tests pass at new scale
- 50-turn smoke run with each scenario produces non-degenerate behavior
- No civ stats hit 0 (except possibly military/economy for collapsing civs — which is now valid)

---

## Phase P2: Region Adjacency Graph

### Goal

Add explicit region adjacency so that geographic relationships (trade routes, distance costs, chokepoints) have a structural foundation. Scenarios can author adjacencies; auto-generation fills gaps.

### Model Changes

**`Region`:**
```python
adjacencies: list[str] = Field(default_factory=list)
```

Scenario YAML can specify per-region:
```yaml
regions:
  - name: Iron Range
    terrain: forest
    adjacencies: [Boundary Waters, Twin Cities Ruins]
```

### New Module: `src/chronicler/adjacency.py`

**Computation order** (called after region placement in `world_gen.py` and after `apply_scenario`):

1. **Explicit scenario adjacencies** — already populated, skip these regions in later steps
2. **Sea route pass** — regions with terrain in `{"coast", "river"}` or resources `"maritime"` form a clique (all-to-all connections among sea-route-eligible regions)
   - TODO: Future milestones (M15+) may replace the clique with explicit sea lanes or distance-limited connections to avoid over-connecting coastal-heavy maps
3. **k-nearest fills gaps** — only for regions with fewer than `k` connections (default `k=3`) after steps 1-2. Uses Euclidean distance on `(x, y)` coordinates.
4. **Symmetrize** — if A→B exists, ensure B→A exists
5. **Validate connectivity** — `connected_components(regions)` must return 1 component. If disconnected, connect nearest pair across components.

**Graph utilities** (pure Python, `collections.deque`):

```python
def compute_adjacencies(regions: list[Region], k: int = 3) -> None: ...
def shortest_path(regions: list[Region], from_name: str, to_name: str) -> list[str] | None: ...
def graph_distance(regions: list[Region], from_name: str, to_name: str) -> int: ...
def is_chokepoint(regions: list[Region], name: str) -> bool: ...
def connected_components(regions: list[Region]) -> list[list[str]]: ...
```

- `graph_distance`: `len(shortest_path) - 1`, or `-1` if disconnected
- `is_chokepoint`: region is an articulation point (removal disconnects graph)
- No external dependencies (no scipy)

### Verification

- Unit tests for each graph utility
- Test that k-nearest on 12 regions produces a connected graph
- Test that scenario-authored adjacencies are preserved (not overwritten)
- Test that sea-route clique forms among coastal/river regions
- Test that k-nearest only fills gaps (doesn't pile onto already-connected regions)

---

## Phase P3: Action Engine v2

### Goal

Restructure the action engine into three categories (automatic, deliberate, reaction) with a registration pattern that lets future milestones add actions without touching the dispatcher.

### Action Categories

```python
class ActionCategory(str, Enum):
    AUTOMATIC = "automatic"
    DELIBERATE = "deliberate"
    REACTION = "reaction"
```

### Registration Pattern

Replace the if/else chain in `_resolve_action`:

```python
ACTION_REGISTRY: dict[ActionType, Callable] = {}

def register_action(action_type: ActionType):
    """Decorator that registers an action handler."""
    def decorator(fn):
        ACTION_REGISTRY[action_type] = fn
        return fn
    return decorator
```

Existing 5 actions (DEVELOP, DIPLOMACY, EXPAND, TRADE, WAR) get `@register_action` decorators. Dispatch becomes:

```python
def _resolve_action(civ, action, world):
    handler = ACTION_REGISTRY.get(action)
    if handler:
        return handler(civ, world)
    return Event(...)  # fallback
```

### Reaction Registry

```python
REACTION_REGISTRY: dict[str, Callable] = {}  # trigger_condition -> handler
```

Empty in P3. Loop in `phase_consequences` checks triggers each turn. First reactions arrive in M14 (DEFEND) and M16 (COUNTER_ESPIONAGE).

### ActionType Enum Expansion

Add `BUILD` and `EMBARGO` to `ActionType`. Both tagged as `DELIBERATE`. The enum variants and weight profiles exist in P3, but the `@register_action` decorated handlers ship in M13a (EMBARGO) and M13b-1 (BUILD).

### Automatic Effects

New function `apply_automatic_effects(world: WorldState) -> list[Event]`:

Runs as its own phase (Phase 2 in the new turn order, before Production — see turn phase order below). P3 implements:
- **Trade income:** `+2 treasury/turn` per active trade route to each partner (requires M13a trade routes — this line is a no-op until M13a lands, since no trade routes exist yet)
- **Military maintenance:** `military > 30` costs `(military - 30) // 10` treasury/turn. **This replaces the temporary `military // 2` from P1's production phase.** When P3 ships, remove the maintenance line from `phase_production` — maintenance now lives in `apply_automatic_effects` permanently.

Extension points for later milestones:
- Fertility recovery/degradation (M13a)
- Infrastructure upkeep (M15)
- Cultural assimilation (M16)
- Vassal tribute (M14)

### Weight Profile Updates

`TRAIT_WEIGHTS` extended with `BUILD` and `EMBARGO` columns for all 10 personality traits.

### Eligibility Updates

`get_eligible_actions` gains:
- `BUILD`: eligible when `treasury >= 10` and civ has at least 1 region
- `EMBARGO`: eligible when civ has at least 1 trade route and a HOSTILE/SUSPICIOUS neighbor

### Turn Phase Order at P3 Completion (10 phases)

The phase order established in P3 persists through the rest of M13:

1. Environment — natural events
2. **Automatic Effects** (new) — military maintenance; trade income is a no-op until M13a
3. Production — base income, condition penalties, population (P1 formulas, no treasury cap)
4. Technology — advancement checks
5. Action — deliberate actions via registry
6. Cultural Milestones — cultural threshold checks
7. Random Events — cascading probability table
8. Leader Dynamics — trait evolution
9. **Fertility** (new, no-op until M13a) — degradation/recovery tick
10. Consequences — condition durations, asabiya, collapse checks

Phases 2 and 9 are structurally present but contain no-op paths until M13a populates them.

### Verification

- All existing action tests pass with registry pattern
- Registry contains exactly 5 handlers after P3 (existing actions)
- `apply_automatic_effects` correctly applies military maintenance at new scale
- BUILD and EMBARGO appear in `ActionType` enum but have no registered handler
- Weight profiles include BUILD and EMBARGO for all traits

---

## Phase M13a: Resource Foundations

### Goal

Give the economy material foundations. Regions produce specific things; civs need diverse things. Trade routes create interdependence. Fertility creates environmental pressure.

### New Module: `src/chronicler/resources.py`

**Resource enum:**

```python
class Resource(str, Enum):
    GRAIN = "grain"
    TIMBER = "timber"
    IRON = "iron"
    FUEL = "fuel"
    STONE = "stone"
    RARE_MINERALS = "rare_minerals"
```

### Model Changes

**`Region`:**
```python
specialized_resources: list[Resource] = Field(default_factory=list)
fertility: float = Field(default=0.8, ge=0.0, le=1.0)
infrastructure_level: int = Field(default=0, ge=0)
famine_cooldown: int = Field(default=0, ge=0)  # turns until famine can trigger again
```

- Old `resources: str` field: **kept but deprecated.** Narrative engine may reference it. Both fields coexist through M13. Clean up in a later milestone.
- Migration function maps old values as fallback: `"fertile"` → `[GRAIN]`, `"mineral"` → `[IRON, STONE]`, `"timber"` → `[TIMBER]`, `"maritime"` → `[GRAIN, FUEL]`, `"barren"` → `[]`

**`WorldState`:**
```python
embargoes: list[tuple[str, str]] = Field(default_factory=list)
```

### Resource Auto-Generation

Terrain → resource probability table (each resource rolled independently):

| Terrain | grain | timber | iron | fuel | stone | rare_minerals |
|---------|-------|--------|------|------|-------|---------------|
| plains | 0.8 | 0.3 | 0.1 | 0.05 | 0.1 | 0.02 |
| forest | 0.3 | 0.8 | 0.1 | 0.1 | 0.05 | 0.05 |
| mountains | 0.05 | 0.1 | 0.6 | 0.1 | 0.7 | 0.2 |
| coast | 0.4 | 0.2 | 0.05 | 0.3 | 0.1 | 0.05 |
| desert | 0.05 | 0.02 | 0.2 | 0.4 | 0.3 | 0.15 |
| tundra | 0.02 | 0.1 | 0.3 | 0.3 | 0.1 | 0.2 |
| river | 0.7 | 0.3 | 0.05 | 0.05 | 0.15 | 0.02 |
| hills | 0.3 | 0.4 | 0.4 | 0.15 | 0.5 | 0.1 |

- Minimum 1 resource per region (re-roll if zero hits)
- Seeded: `world.seed + hash(region.name)`
- Scenario YAML override: `specialized_resources: [iron, rare_minerals]` — skips auto-generation for that region

### Resource Diversity Requirements for Tech Eras

Added as a gate in `check_tech_advancement`:

| Era | Required Resources | Additional Stat Requirements |
|-----|-------------------|------------------------------|
| BRONZE | iron AND timber (specific types required) | — |
| IRON | iron AND timber AND grain (specific types required) | — |
| CLASSICAL | any 3 unique resources | economy >= 40 |
| MEDIEVAL | any 4 unique resources | economy >= 50 |
| RENAISSANCE | any 4 unique resources | culture >= 60 |
| INDUSTRIAL | any 5 unique resources (must include fuel) | economy >= 70 |
| INFORMATION | any 5 unique resources | economy >= 80, culture >= 90 |

Early eras (BRONZE through IRON) require specific resource types — you need actual iron to enter the Iron Age. Later eras require resource diversity (count) rather than specific types, except INDUSTRIAL which requires fuel to represent industrialization.

A civ's available resources = union of `specialized_resources` across all controlled regions.

### INFORMATION Era

Added to `TechEra` enum after `INDUSTRIAL`.

```python
TechEra.INFORMATION = "information"
```

- `TECH_REQUIREMENTS[INDUSTRIAL]` = `(90, 80, 350)` (culture, economy, cost)
- `ERA_BONUSES[INFORMATION]` = `{"culture": 10, "economy": 5}`
- Update viewer: `format.ts` ERA_ORDER, `types.ts` TechEra union

### Fertility System

**Region field:** `fertility: float = Field(default=0.8, ge=0.0, le=1.0)`

**Effective capacity:** `int(region.carrying_capacity * region.fertility)`, minimum 1.

Note: The field remains named `carrying_capacity` (not renamed to `base_capacity`). The name is slightly misleading since actual capacity = `carrying_capacity * fertility`, but renaming would touch every callsite across the codebase for no functional benefit. A docstring on the field clarifies: "Base carrying capacity before fertility modifier."

**Per-turn tick** (new Phase 9: Fertility, runs after Leader Dynamics):
- **Degradation:** For each region with a controller, compute `avg_population = civ.population / len(civ.regions)`. If `avg_population > effective_capacity`: `fertility -= 0.02`
- **Recovery:** If `avg_population < effective_capacity * 0.5`: `fertility += 0.01`
- Clamped to `[0.0, 1.0]`

Note: Population is a civ-level stat, not per-region. The proxy `civ.population / len(civ.regions)` is intentionally crude — adequate for M13, more precise distribution can come in future milestones.

**Scenario YAML:** Can set initial fertility per region (defaults to 0.8 if unspecified).

### Trade Routes

**Definition:** A trade route exists between two civs when:
1. Civ A controls region X, Civ B controls region Y
2. X and Y are directly adjacent (adjacency graph edge)
3. Mutual disposition >= NEUTRAL
4. No active embargo between A and B

**Direct adjacency only.** No multi-hop pathfinding. TODO: Multi-hop trade routes via merchant characters in M15/M17.

```python
def get_active_trade_routes(world: WorldState) -> list[tuple[str, str]]:
    """Returns deduplicated list of (civ_a, civ_b) pairs with active routes."""
```

**Trade income** (in `apply_automatic_effects`):
- `+3 treasury/turn` if one civ controls both endpoint regions
- `+2 treasury/turn` to each civ if different civs control one endpoint each
- Stacks per route

### EMBARGO Action

Registered with `@register_action(ActionType.EMBARGO)` in this phase.

**Resolution:**
- Adds `(embargoing_civ, target_civ)` to `world.embargoes`
- All trade routes between the pair immediately deactivated
- Target: `stability -= 5` (economic shock)
- Embargoing civ also loses trade income from those routes

**Lifting:** Embargo removed automatically when:
- Disposition between the pair reaches FRIENDLY+ (regardless of which civ's DIPLOMACY action caused the improvement — the current `_resolve_diplomacy` targets the most hostile neighbor, so natural diplomatic recovery eventually lifts embargoes)
- Or: either civ loses all regions

Checked once per turn at the start of `apply_automatic_effects` before trade route computation.

**Embargo persists across turns** — it's a standing policy, not a one-turn action.

### `--simulate-only` Flag

**CLI:** New flag in `main.py`, mutually exclusive with `--live`.

**Behavior:**
- Runs full simulation loop
- Passes no-op narrator: `lambda world, events: ""`
- Writes `chronicle_bundle.json` with empty `chronicle_entries` list
- Viewer renders mechanical data without prose (existing components handle missing text gracefully)

**Performance target:** 500 turns, 5 civs, 15 regions < 5 seconds with `--simulate-only`.

### Scenario YAML Updates

All 6 files updated:
- Add `specialized_resources` per region (hand-authored where creative intent matters, auto-generated fallback for generic scenarios)
- Add `adjacencies` where topology matters (Minnesota gets full hand-authored adjacencies)
- Add `fertility` where initial conditions matter
- Old `resources: str` field kept for narrative backward compatibility

Example (Minnesota — Iron Range):
```yaml
- name: Iron Range
  terrain: forest
  carrying_capacity: 40
  resources: mineral          # kept for narrative
  specialized_resources: [iron, rare_minerals]
  adjacencies: [Boundary Waters, Twin Cities Ruins, Lake Country]
  fertility: 0.6
```

### Verification

- Resource auto-generation produces 1-6 resources per region, seeded deterministically
- Scenario-authored resources are preserved
- Tech advancement blocked when resource requirements not met
- INFORMATION era reachable with sufficient resources + stats
- Fertility degrades under overpopulation, recovers under low population
- Trade routes form between adjacent friendly civs, not between embargoed pairs
- EMBARGO cuts routes and applies stability penalty
- `--simulate-only` completes 500 turns in < 5s
- Existing scenarios still produce valid runs

---

## Phase M13b-1: Treasury Mechanics

### Goal

Money becomes interesting. Armies cost money, wars drain it, trade generates it. The basic economic loop — costs, income, and spending — becomes consequential.

### Military Maintenance Overhaul

Replaces the flat `military // 2` from production:

- Military <= 30: free (standing militia)
- Military > 30: costs `(military - 30) // 10` treasury/turn
- Applied in `apply_automatic_effects`

### Active Wars Tracking

**New field on `WorldState`:**
```python
active_wars: list[tuple[str, str]] = Field(default_factory=list)
```

- WAR action adds `(attacker, defender)` pair
- Cleared when: DIPLOMACY action reaches FRIENDLY+ between the pair, or one side loses all regions
- HOSTILE disposition is a separate concept — persists independently of active war status

### War Costs

- **Declaration:** WAR action costs `-10 treasury` upfront (replaces current `-2`)
- **Ongoing:** `-3 treasury/turn` per active war (keyed off `active_wars`, not disposition)
- **Bankruptcy pressure:** If `treasury <= 0` while in active war: `stability -= 5/turn`
- Applied in `apply_automatic_effects`

### Development Cost Scaling

DEVELOP action cost: `5 + economy // 10` treasury (replaces flat 3). Richer civs pay more — diminishing returns at the top.

### BUILD Action

Registered with `@register_action(ActionType.BUILD)`.

**Resolution:**
- Cost: 10 treasury
- Target: one of the civ's controlled regions (chosen by engine)
- Effect: increase `carrying_capacity += 10` OR `fertility += 0.1`
- **Choice logic:** Trait weights influence the decision. Default tiebreaker: if `fertility < 0.5`, restore fertility; else increase capacity. But personality modifies this:
  - `cautious`, `visionary`: bias toward fertility restoration
  - `ambitious`, `bold`, `aggressive`: bias toward capacity expansion
  - Others: use default tiebreaker
- Increments `region.infrastructure_level += 1`
- One BUILD per turn (it's the deliberate action)

### Production Phase Consolidation

Replaces the P1 production formulas (which were temporary ×10 migrations) with proper economic balance:

- **Base income:** `economy // 5 + len(civ.regions) * 2` *(replaces P1's `economy + regions * 10` — dramatic reduction to make treasury management meaningful)*
- **Trade income:** handled by `apply_automatic_effects` (separate phase)
- **Condition penalty:** `sum(severity for active conditions affecting civ)`
- **Treasury cap:** none (removed in P1, permanent)
- **Population growth:** `+5` when `economy > population` AND `stability > 20` AND population < sum of effective capacities
- **Population decline:** `-5` when `stability <= 10` *(tightened from P1's `<= 20` — M13b-1's treasury/war pressure creates enough instability that the threshold can be stricter without losing the mechanic)*

### Turn Phase Order (10 phases)

1. Environment — natural events
2. **Automatic Effects** — trade income, military maintenance, war costs, embargo leakage, mercenary decay
3. Production — base income, condition penalties, population growth/decline
4. Technology — advancement checks (now with resource diversity gate)
5. Action — deliberate actions (DEVELOP, DIPLOMACY, EXPAND, TRADE, WAR, BUILD, EMBARGO)
6. Cultural Milestones — cultural threshold checks
7. Random Events — cascading probability table
8. Leader Dynamics — trait evolution
9. **Fertility** — degradation/recovery tick
10. Consequences — condition durations, asabiya, collapse checks

### Viewer Bundle Extensions

**`TurnSnapshot` gains:**
- `trade_routes: list[tuple[str, str]]`
- `active_wars: list[tuple[str, str]]`
- `embargoes: list[tuple[str, str]]`
- `fertility: dict[str, float]` (region name → fertility)

**`CivSnapshot` gains:**
- `last_income: int`
- `active_trade_routes: int`

### Verification

- Military maintenance scales correctly: 0 at mil=30, 1 at mil=40, 7 at mil=100
- War declaration costs 10 treasury; ongoing costs 3/turn from `active_wars`
- Bankruptcy during war causes stability drain
- Active wars cleared by diplomacy or absorption, not by disposition change alone
- Development cost scales with economy
- BUILD action respects trait-weighted choice between fertility and capacity
- Production rewrite produces reasonable treasury trajectories over 100 turns
- Compare pre/post M13b-1 runs: "civs now actually go broke from long wars" is verifiable

---

## Phase M13b-2: Emergent Economic Events

### Goal

Layered on stable treasury mechanics. Famine, black markets, and mercenaries create emergent economic dynamics that stress-test and exploit the M13b-1 foundation.

### Famine Events

**Trigger:** Any region where `fertility < 0.3` and region has a controller.

**Effects on controlling civ:**
- `population -= 15`
- `stability -= 10`
- Note: This is a flat civ-wide hit regardless of how many regions the civ controls. Intentional at current abstraction level — "The famine in the southern provinces drained the empire's reserves." Per-region population can refine this in future milestones.

**Neighbor effects** (via adjacency graph):
- Adjacent regions controlled by *other* civs: `population += 5` (refugees), `stability -= 5` (refugee pressure)
- Adjacent regions controlled by *same* civ: no refugee effect (internal migration assumed)

**Chain reaction:** Refugee influx can push neighbor's population over effective capacity → accelerated fertility degradation → future famine. This cascade is emergent, not scripted.

**Named event:** Famine generates a named event with importance 8.

**Rate limit:** At most 1 famine check per region per turn. Additionally, a region that triggers famine enters a **5-turn cooldown** before it can trigger another famine (tracked as `famine_cooldown: int = 0` on Region, decremented each turn). Without this, a region at fertility 0.25 would trigger famine every single turn until population drops — rapid-fire famines rather than one devastating event followed by a recovery window.

### Black Markets

**Trigger:** Embargoed civ controls a region adjacent to any non-embargoed civ's region.

**Effects:**
- Embargoed civ gets 30% of normal trade benefit from that adjacency (rounded down, minimum 1 treasury)
- Embargoed civ: `stability -= 3` (corruption)
- Adjacent non-embargoed civ: `stability -= 1` (smuggling destabilizes both sides)

**Behavior:** Automatic — no action required. Checked in `apply_automatic_effects` after embargo filtering.

**Design intent:** Embargoes are leaky by design. You can't fully isolate a neighbor economically. This prevents embargo from being an unbeatable strategy and creates interesting tradeoffs (embargo hurts them but doesn't kill them, and it costs you stability too).

### Mercenary Companies

**New model:**
```python
class MercenaryCompany(BaseModel):
    strength: int = Field(ge=0)
    origin_civ: str
    location: str  # region name
    available: bool = True
    hired_by: str | None = None
```

**WorldState field:**
```python
mercenary_companies: list[MercenaryCompany] = Field(default_factory=list)
```

**New `Civilization` fields** (for mercenary spawn tracking):
```python
last_income: int = 0          # base + trade income from previous turn
merc_pressure_turns: int = 0  # consecutive turns where military > last_income
```

**CivSnapshot field:**
```python
last_income: int = 0
```

**Spawn trigger:** Civ where `military > last_income` for 3 consecutive turns.
- `last_income` updated at end of production phase each turn (base income + trade income)
- `merc_pressure_turns` incremented in `apply_automatic_effects` when `military > last_income`, reset to 0 otherwise
- Spawn fires when `merc_pressure_turns >= 3`
- Spawn: strength = `civ.military // 5`. Spawning civ: `military -= strength * 5`
- Location: one of the civ's controlled regions (random)
- **Cap:** 3 active mercenary companies world-wide. If cap reached, spawn is blocked.

**Hiring** (automatic, checked in `apply_automatic_effects`):
- Eligible hirers: civs currently in active war with `treasury >= strength * 3`
- **Priority:** Lower military gets first hire (underdog bias — desperate civs hire mercenaries). Ties broken by higher treasury (outbid).
- Hired civ: `military += strength`, `treasury -= strength * 3`
- Company: `available = False`, `hired_by = civ.name`

**Decay:** Unhired companies lose `-2 strength/turn`. Removed at strength <= 0, freeing a slot.

**Hired company lifecycle:** Lasts until the hiring civ's active war ends, then company disbands (removed).

### Economic Specialization

**Computed per turn** in `apply_automatic_effects` (not stored permanently):

- `primary_trade_resource`: the Resource that appears most across a civ's controlled regions
- If > 60% of a civ's trade routes involve regions containing the primary resource:
  - Bonus: `economy * 0.15` added to treasury income (flat amount, not stat modification)
  - Vulnerability: if those routes get embargoed, penalty of `economy * 0.20` from treasury income

Both bonus and penalty are truncated to integers (treasury is int). At economy=70: bonus = +10, penalty = -14. The asymmetry is intentional — losing specialized trade hurts more than having it helps.

This creates a natural tension — specialization is profitable but fragile.

### Viewer Bundle Extensions

**`TurnSnapshot` gains:**
- `mercenary_companies: list[dict]` (serialized MercenaryCompany)

(Other snapshot fields already added in M13b-1.)

### Testing Strategy

**Famine cascade test:**
- Set region fertility to 0.25, run 10 turns
- Verify controlling civ loses population and stability
- Verify adjacent civ gains population and loses stability (refugees)
- Verify chain reaction: refugee-receiving region's fertility degrades faster

**Black market test:**
- Embargo a civ with an adjacent non-embargoed neighbor
- Verify embargoed civ gets 30% trade leakage (min 1 treasury)
- Verify stability costs on both sides

**Mercenary spawn test:**
- Set `military > last_income` for 3 consecutive turns
- Verify company spawns with correct strength
- Verify spawning civ loses military proportionally

**Mercenary hiring test:**
- Two civs at war, mercenary available, both can afford
- Verify lower-military civ gets priority
- Verify treasury deduction and military increase

**Mercenary cap + decay test:**
- Spawn 3 companies (at cap)
- Verify 4th spawn blocked
- Decay one company to strength 0, verify removal
- Verify next spawn succeeds (slot freed)

**Economic specialization test:**
- Give civ 3 trade routes all involving grain-heavy regions
- Verify 15% economy bonus in treasury income
- Embargo those routes, verify 20% penalty

**Scale test:**
- `--simulate-only` 500 turns, 5 civs, 15 regions, all M13 mechanics active
- Must complete in < 5 seconds

---

## Cross-Cutting Concerns

### Narrative Engine

Each phase may expand prompt templates with new event types (famine, embargo, mercenary spawn, etc.). The narrative engine describes what happened; it doesn't decide what happens. No new LLM capabilities required.

Old `Region.resources: str` field kept for narrative backward compatibility through M13. Prompts can reference either field.

### Scenario Compatibility

All new fields have defaults:
- `specialized_resources`: empty (auto-generated)
- `adjacencies`: empty (auto-computed)
- `fertility`: 0.8
- `infrastructure_level`: 0
- `embargoes`: empty
- `active_wars`: empty
- `mercenary_companies`: empty

Old scenarios work unchanged — new mechanics activate based on the systems that produce them, not on scenario configuration.

### Viewer Extensions

Each phase adds snapshot fields. Viewer components render available data — existing StatGraphs, EventLog, and TerritoryMap handle new fields without new components. No viewer rewrites.

### Performance Budget

- `--simulate-only` 500 turns < 5 seconds for 5-civ, 15-region map
- Bundle < 20 MB
- All graph utilities O(V+E) where V = regions, E = adjacencies

### Dependency Chain

```
P1 (stat scale) → P2 (adjacency graph) → P3 (action engine v2)
    → M13a (resources, fertility, trade, embargo, --simulate-only)
    → M13b-1 (treasury mechanics, BUILD, active wars)
    → M13b-2 (famine, black markets, mercenaries, specialization)
```

Each phase testable in isolation before the next starts.
