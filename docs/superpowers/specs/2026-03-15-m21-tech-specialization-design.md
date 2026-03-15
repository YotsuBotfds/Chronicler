# M21: Tech Specialization -- Design Spec

**Date:** 2026-03-15
**Status:** Approved
**Prerequisites:** P4 (Regional Population) landed

## Overview

Divergent development paths for civilizations via deterministic tech focus selection on era advancement. A civ's geography and history choose its technology path -- no randomness, no LLM calls, no player choice.

When a civ advances to a new tech era (Classical through Information), it gains a **tech focus** selected deterministically from civ state at the moment of advancement. Each focus provides a stat modifier, action weight biases, and a unique gameplay capability. Only the active focus applies effects; focus history is retained for narrative and analytics.

## Data Model

### Civilization (models.py)

Two new fields:

```python
tech_focuses: list[str] = Field(default_factory=list)  # history of focus values
active_focus: str | None = None  # current era's focus
```

Stored as `str` (not enum) to keep models.py free of tech_focus.py imports and match the project's Pydantic serialization pattern. Empty/None defaults ensure backward compatibility with all existing scenarios and bundles.

### CivSnapshot (models.py)

One new field:

```python
active_focus: str | None = None
```

Populated alongside `tech_era` in the snapshot capture in main.py.

### CivThematicContext

Already has `active_tech_focus: str | None = None` (pre-wired by M20a). Populated from `civ.active_focus` in the narrator pipeline. No changes needed.

## New Module: src/chronicler/tech_focus.py

### TechFocus Enum

```python
class TechFocus(str, Enum):
    # Classical
    NAVIGATION = "navigation"
    METALLURGY = "metallurgy"
    AGRICULTURE = "agriculture"
    # Medieval
    FORTIFICATION = "fortification"
    COMMERCE = "commerce"
    SCHOLARSHIP = "scholarship"
    # Renaissance
    EXPLORATION = "exploration"
    BANKING = "banking"
    PRINTING = "printing"
    # Industrial
    MECHANIZATION = "mechanization"
    RAILWAYS = "railways"
    NAVAL_POWER = "naval_power"
    # Information
    NETWORKS = "networks"
    SURVEILLANCE = "surveillance"
    MEDIA = "media"
```

TRIBAL, BRONZE, and IRON eras have no focuses -- focuses start at CLASSICAL.

### ERA_FOCUSES Mapping

```python
ERA_FOCUSES: dict[TechEra, list[TechFocus]] = {
    TechEra.CLASSICAL: [TechFocus.NAVIGATION, TechFocus.METALLURGY, TechFocus.AGRICULTURE],
    TechEra.MEDIEVAL: [TechFocus.FORTIFICATION, TechFocus.COMMERCE, TechFocus.SCHOLARSHIP],
    TechEra.RENAISSANCE: [TechFocus.EXPLORATION, TechFocus.BANKING, TechFocus.PRINTING],
    TechEra.INDUSTRIAL: [TechFocus.MECHANIZATION, TechFocus.RAILWAYS, TechFocus.NAVAL_POWER],
    TechEra.INFORMATION: [TechFocus.NETWORKS, TechFocus.SURVEILLANCE, TechFocus.MEDIA],
}
```

## Scoring System

### Scoring Helpers

Six counting functions that query concrete model state:

- `_count_terrain(civ, world, terrain)` -- regions with matching `r.terrain`
- `_count_resource(civ, world, resource)` -- regions with matching `resource in r.specialized_resources`
- `_count_infra(civ, world, infra_type)` -- count of active infrastructure matching `infra_type` across civ regions (e.g., `roads` = `_count_infra(civ, world, InfrastructureType.ROADS)`)
- `_count_trade_routes(civ, world)` -- calls `get_active_trade_routes()` from resources.py, counts routes involving civ
- `_count_unclaimed_adjacent(civ, world)` -- builds adjacency set from civ-controlled regions, counts adjacent regions where `controller is None`
- `_count_border_regions(civ, world)` -- count of civ-controlled regions that have at least one adjacency controlled by a different civ

### Scoring Table

All 15 formulas grounded in verified model state:

| Era | Focus | Formula |
|---|---|---|
| Classical | NAVIGATION | `coastal x 3 + ports x 5` |
| Classical | METALLURGY | `iron_regions x 4 + mines x 5` |
| Classical | AGRICULTURE | `grain_regions x 3 + irrigated x 5 + civ.population x 0.1` |
| Medieval | FORTIFICATION | `fortifications x 5 + border_regions x 3 + military x 0.2` |
| Medieval | COMMERCE | `trade_routes x 5 + treasury x 0.1 + ports x 3` |
| Medieval | SCHOLARSHIP | `culture x 0.3 + great_persons x 5 + len(civ.traditions) x 3` |
| Renaissance | EXPLORATION | `regions x 3 + military x 0.15 + unclaimed_adjacent x 4` |
| Renaissance | BANKING | `treasury x 0.15 + economy x 0.3 + trade_routes x 3` |
| Renaissance | PRINTING | `culture x 0.2 + civ_movements x 5 + great_persons x 3` |
| Industrial | MECHANIZATION | `mines x 5 + iron_regions x 3 + economy x 0.2` |
| Industrial | RAILWAYS | `roads x 5 + regions x 3 + trade_routes x 2` |
| Industrial | NAVAL_POWER | `coastal x 5 + ports x 5 + military x 0.2` |
| Information | NETWORKS | `trade_routes x 5 + roads x 3 + economy x 0.2` |
| Information | SURVEILLANCE | `regions x 3 + stability x 0.3 + civ.population x 0.05` |
| Information | MEDIA | `culture x 0.3 + civ_movements x 5 + great_persons x 3` |

**Note on NAVIGATION:** Uses `port_count` (regions with active PORTS infrastructure), not `sea_trade_routes` which does not exist in the codebase. Ports are a buildable infrastructure type, making this a natural investment narrative.

**Note on `civ_movements`:** Must be filtered by civ adherence (`civ.name in movement.adherents` via `world.movements`), not global movement count.

**Note on `unclaimed_adjacent`:** Requires building the adjacency set from civ-controlled regions. Dedicated helper `_count_unclaimed_adjacent(civ, world)` to keep it clean. By Renaissance, unclaimed regions may be rare in dense scenarios, which biases EXPLORATION toward large militaristic civs -- thematically appropriate.

### M17 Great Person Scoring Bonuses (+5)

Applied during selection when GP is active:

- Scientist GP: +5 to SCHOLARSHIP, PRINTING, NETWORKS
- Merchant GP: +5 to COMMERCE, BANKING, RAILWAYS
- General GP: +5 to METALLURGY, FORTIFICATION, MECHANIZATION
- Prophet GP: +5 to AGRICULTURE, SCHOLARSHIP, MEDIA

Prophet and Scientist overlap on SCHOLARSHIP is intentional -- a civ with both gets +10, which can tip marginal decisions.

### M17 Tradition Scoring Bonuses (+3)

- Scholarly tradition: +3 to culture-adjacent focuses (SCHOLARSHIP, PRINTING, MEDIA)
- Martial tradition: +3 to military-adjacent focuses (METALLURGY, FORTIFICATION, MECHANIZATION)

### All-Zero Scoring Fallback

When all three scores for an era are 0 (e.g., forest/desert-only civ at Classical), fall back to highest civ stat mapped to the era's three focuses:

| Era | military -> | economy -> | culture -> |
|---|---|---|---|
| Classical | METALLURGY | NAVIGATION | AGRICULTURE |
| Medieval | FORTIFICATION | COMMERCE | SCHOLARSHIP |
| Renaissance | EXPLORATION | BANKING | PRINTING |
| Industrial | NAVAL_POWER | MECHANIZATION | RAILWAYS |
| Information | SURVEILLANCE | NETWORKS | MEDIA |

- Stat ties broken by `hash(world.seed, civ.name)`

This ensures selection always reflects something about the civ's developmental history, even for geographically impoverished civs.

### select_tech_focus()

```python
def select_tech_focus(civ: Civilization, world: WorldState) -> TechFocus | None:
```

Score all 3 options for the era, apply GP/tradition bonuses, check for all-zero fallback, break ties with `hash(world.seed, civ.name, focus.value)`. Returns `TechFocus | None` (None for pre-Classical eras).

## Focus Effects

### FocusEffect Structure

```python
@dataclass
class FocusEffect:
    stat_modifiers: dict[str, int]
    weight_modifiers: dict[ActionType, float]
    capability: str
```

Single `FOCUS_EFFECTS` dict maps `TechFocus -> FocusEffect`. Adding/tuning a focus is a data change, not a code change.

### Effects Table

| Focus | Stat Modifier | Weight Modifiers |
|---|---|---|
| NAVIGATION | economy +5 | EXPLORE x1.5, TRADE x1.3 |
| METALLURGY | military +15 | WAR x1.3, BUILD x1.2 |
| AGRICULTURE | economy +10 | BUILD x1.3, TRADE x1.2 |
| FORTIFICATION | military +10 | BUILD x1.5, WAR x1.2 |
| COMMERCE | economy +10 | TRADE x1.5, DIPLOMACY x1.2 |
| SCHOLARSHIP | culture +10 | INVEST_CULTURE x1.3, DIPLOMACY x1.2 |
| EXPLORATION | military +5 | EXPLORE x1.5, WAR x1.2 |
| BANKING | economy +15 | TRADE x1.3, EMBARGO x1.3 |
| PRINTING | culture +15 | INVEST_CULTURE x1.5, DIPLOMACY x1.3 |
| MECHANIZATION | economy +10 | BUILD x1.5, TRADE x1.2 |
| RAILWAYS | economy +5 | BUILD x1.3, TRADE x1.3 |
| NAVAL_POWER | military +15 | WAR x1.5, EXPLORE x1.2 |
| NETWORKS | economy +10 | TRADE x1.5, DIPLOMACY x1.2 |
| SURVEILLANCE | stability +10 | DIPLOMACY x1.3, WAR x1.2 |
| MEDIA | culture +15 | INVEST_CULTURE x1.5, TRADE x1.2 |

**Note on AGRICULTURE:** Stat modifier is `economy +10`, not `population +10`. Direct population modification conflicts with the P4 regional population sync pattern (`sync_civ_population` would overwrite it). Population benefits come through AGRICULTURE's unique capability (famine threshold reduction) instead.

### Effect Lifecycle

- `apply_focus_effects(civ, focus)` -- adds stat modifiers via `clamp()`, sets `civ.active_focus`, appends to `civ.tech_focuses`
- `remove_focus_effects(civ, focus)` -- subtracts stat modifiers via `clamp()`, called before new focus selection on era advancement
- Only active focus applies effects; history in `tech_focuses` is for narrative/analytics only
- Clamping asymmetry is expected: applying +15 military to a civ at 95 clamps to 100, removing -15 drops to 85. This is acceptable behavior.

### get_focus_weight_modifiers()

```python
def get_focus_weight_modifiers(civ: Civilization) -> dict[ActionType, float]:
```

Returns weight multipliers from active focus. Empty dict if no focus. Called by `compute_weights()`.

## Unique Capabilities

15 callsite integrations, each 3-5 lines. Simple string comparison (`civ.active_focus == "focus_name"`), no tech_focus.py import needed at callsites.

| Focus | Capability | Callsite | Implementation |
|---|---|---|---|
| NAVIGATION | Trade across 2 sea hops | resources.py `get_active_trade_routes()` | Extend adjacency to 2-hop coastal routes |
| METALLURGY | Mine fertility degradation -50% | simulation.py phase 9 fertility | `degradation *= 0.5` |
| AGRICULTURE | Famine threshold halved | simulation.py phase 9 famine check | `threshold *= 0.5` |
| FORTIFICATION | Fort build time -1 turn | infrastructure.py `handle_build()` | Reduce `turns_remaining` by 1 for FORTIFICATIONS |
| COMMERCE | Trade income +50% | action_engine.py `resolve_trade()` | Treasury gain x 1.5 if either civ has COMMERCE |
| SCHOLARSHIP | Tech treasury cost -20% | tech.py `check_tech_advancement()` | Apply discount before threshold check (effective_cost pattern) |
| EXPLORATION | Expand into harsh terrain earlier | action_engine.py `_resolve_expand()` | Bypass IRON era gate for harsh terrain |
| BANKING | Incoming embargo damage halved | action_engine.py `_resolve_embargo()` | Halve stability drain if target has BANKING |
| PRINTING | Movement adoption probability x2 | movements.py `_process_spread()` | Double `adoption_probability` before roll check (line 98) |
| MECHANIZATION | +2 treasury per active mine | simulation.py `phase_production()` | New 3-line block: count active mines across civ regions, add 2 treasury per mine |
| RAILWAYS | Trade route range +1 hop | resources.py `get_active_trade_routes()` | Extend trade adjacency to 2-hop via roads |
| NAVAL_POWER | Coastal defense +10 | action_engine.py `resolve_war()` | +10 defense if defender has NAVAL_POWER and region is coastal |
| NETWORKS | Trade income x2 | action_engine.py `resolve_trade()` | Treasury gain x 2 |
| SURVEILLANCE | Secession resistance | politics.py `check_secession()` | Secession triggers at `stability < 10` instead of `stability < 20` (line 102) |
| MEDIA | Propaganda acceleration x2 | culture.py `resolve_invest_culture()` | Double `PROPAGANDA_ACCELERATION` value (line 187) |

### Design Notes on Capabilities

- NAVIGATION and RAILWAYS both extend trade by 1 hop but through different mechanisms (sea vs road). They don't stack since only active focus applies and they're in different eras.
- COMMERCE (+50%) and NETWORKS (x2) are in different eras, no stacking. NETWORKS is strictly stronger, appropriate for Information era.
- SCHOLARSHIP must use the `effective_cost` pattern -- discount before the threshold check, not after:
  ```python
  effective_cost = int(cost * 0.8) if civ.active_focus == "scholarship" else cost
  if civ.treasury < effective_cost:
      return None
  civ.treasury -= effective_cost
  ```
- BANKING was changed from offensive (embargo damage doubled) to defensive (incoming embargo damage halved). Fires more often since economically strong civs are common embargo targets.
- MECHANIZATION adds a new +2 treasury per active mine mechanic in `phase_production()`. No existing mine income mechanic exists -- mines only cause fertility degradation in `infrastructure.py`. This is a small new block (~3 lines), not a modification of existing code.
- PRINTING doubles `adoption_probability` in `movements.py _process_spread()` (line 98). Movement `adherents` is `dict[str, int]` where values are variant offsets, not adherent counts. The capability affects adoption *probability*, not any numeric adherent value.
- MEDIA's capability is propaganda acceleration x2 in `culture.py resolve_invest_culture()` (line 187), not cultural projection range. At INFORMATION era, `culture_projection_range = -1` already grants global projection (tech.py line 48), making a range extension redundant. Doubling `PROPAGANDA_ACCELERATION` instead gives MEDIA a meaningful offensive cultural warfare capability.
- SURVEILLANCE: secession check at `politics.py` line 102 uses `civ.stability >= 20` (civs at stability 20+ are immune). With SURVEILLANCE, the threshold drops to 10, meaning the civ must be below stability 10 before secession triggers. This makes the civ *more resistant* to fracture.

## Simulation Integration

### Orchestration: Approach B

Focus selection lives in `phase_technology()` in simulation.py, not inside `check_tech_advancement()`. This follows the codebase pattern: simulation.py orchestrates, specialized modules compute. Keeps tech.py free of tech_focus.py imports.

### phase_technology() Hook

After `check_tech_advancement()` returns a successful event:

```python
if event:
    events.append(event)
    # M21: Remove old focus effects, select and apply new
    if civ.active_focus:
        old_focus = TechFocus(civ.active_focus)
        remove_focus_effects(civ, old_focus)
    new_focus = select_tech_focus(civ, world)
    if new_focus:
        apply_focus_effects(civ, new_focus)
        events.append(Event(
            turn=world.turn, event_type="tech_focus_selected",
            actors=[civ.name],
            description=f"{civ.name} develops {new_focus.value} specialization",
            importance=6,
        ))
```

No `try/except ValueError` on `TechFocus(civ.active_focus)` -- the only code that sets `active_focus` is `apply_focus_effects`, which always uses `focus.value` from a valid enum. Invalid strings can't enter through normal simulation flow.

### Snapshot Capture (main.py)

Alongside existing `tech_era=civ.tech_era`:

```python
active_focus=civ.active_focus,
```

### Tech Regression Integration (emergence.py)

`check_tech_regression()` has its own code path, separate from `phase_technology()`. After `remove_era_bonus(civ, old_era)` at line 578:

```python
# M21: Remove tech focus effects on regression
if civ.active_focus:
    from chronicler.tech_focus import TechFocus, remove_focus_effects
    remove_focus_effects(civ, TechFocus(civ.active_focus))
    civ.active_focus = None
```

Focus stays in `tech_focuses` history for narrative ("they once knew navigation"). Re-advancement selects fresh based on current state, which may produce a different focus. Inline import follows the pattern already used in emergence.py for rare code paths.

### Weight Cap in compute_weights() (action_engine.py)

2.5x global normalization added after streak-breaking logic (lines 587-593) and before the return at line 594. Implemented in M21 as it introduces the third multiplicative layer (trait x tradition x focus). Zeroed-out actions from streak logic are not affected.

```python
max_weight = max(weights.values())
if max_weight > 2.5:
    scale = 2.5 / max_weight
    for action in weights:
        weights[action] *= scale
```

This preserves relative ordering while capping absolute maximum. A slight suppression of non-dominant actions is the correct tradeoff -- prevents any single action from becoming near-certain.

## Files Modified

| File | Changes |
|---|---|
| `src/chronicler/tech_focus.py` (new) | TechFocus enum, ERA_FOCUSES, scoring, FOCUS_EFFECTS, select/apply/remove, weight modifiers (~250 lines) |
| `src/chronicler/models.py` | Add `tech_focuses`, `active_focus` to Civilization; add `active_focus` to CivSnapshot (~6 lines) |
| `src/chronicler/simulation.py` | Import tech_focus; hook in phase_technology after advancement (~15 lines) |
| `src/chronicler/action_engine.py` | Weight modifiers in compute_weights + 2.5x cap; COMMERCE/NETWORKS/EXPLORATION/BANKING/NAVAL_POWER callsite capabilities (~25 lines) |
| `src/chronicler/emergence.py` | Remove focus effects on tech regression (~5 lines) |
| `src/chronicler/main.py` | Populate active_focus in CivSnapshot (~1 line) |
| `src/chronicler/tech.py` | SCHOLARSHIP effective_cost pattern (~4 lines) |
| `src/chronicler/resources.py` | NAVIGATION and RAILWAYS 2-hop trade route extensions (~10 lines) |
| `src/chronicler/movements.py` | PRINTING adoption probability x2 in `_process_spread()` (~3 lines) |
| `src/chronicler/culture.py` | MEDIA propaganda acceleration x2 in `resolve_invest_culture()` (~3 lines) |
| `src/chronicler/politics.py` | SURVEILLANCE secession threshold -10 (~3 lines) |
| `src/chronicler/infrastructure.py` | FORTIFICATION build time -1 (~3 lines) |
| `tests/test_tech_focus.py` (new) | Comprehensive test suite (~150 lines) |

**Total:** ~350 lines production code, ~150 lines tests, across 12 source files + 1 test file.

**Suggested implementation order:** (1) Data model + core module, (2) orchestration + weight integration, (3) capabilities (independent, any order, each testable in isolation).

## Cross-Cutting Concerns

1. **M18 severity multiplier:** Focus effects are bonuses (additions), not damage. `remove_focus_effects` subtracts bonuses, not damage. Severity multiplier does not apply.
2. **Combined weight cap at 2.5x:** Traditions (M17) x tech focus (M21) x factions (M22, future) can stack. Cap implemented in M21. Value tunable via M19b. **Phoebe note:** Ship 2.5x, validate empirically. M19b analytics should track "action selection entropy per civ per era" — low entropy means one action dominates, meaning the cap is too permissive. If median entropy drops below 1.5 bits (~one action chosen >60% of the time), lower to 2.0x. Cap constant must be overridable via M19's tuning YAML.
3. **M22 forward compatibility:** Tech focus biases faction influence (+0.05 to matching faction). M22's responsibility -- M21 just exposes `civ.active_focus`. No M22 code in M21.
4. **Scenario compatibility:** All new fields have defaults (`tech_focuses=[]`, `active_focus=None`). Existing scenarios work unchanged.
