# M43b: Supply Shock Detection, Trade Dependency & Raider Incentive — Design Spec

> **Status:** Draft
>
> **Author:** Cici (Opus 4.6)
>
> **Reviewed by:** Tate (design decisions)
>
> **Depends on:** M43a (Transport, Perishability & Stockpiles), M42 (Goods Production & Trade)
>
> **Blocked by:** None (M43a merged)

---

## Goal

M43a builds the physical infrastructure — transport costs, perishability, stockpiles. M43b builds the strategic and narrative layer on top. Detect when supply shocks happen, classify which regions are trade-dependent, modify civ behavior (raiding wealthy neighbors), and surface all of it for narration and the curator pipeline.

Shock propagation is **emergent** from M43a's stockpile mechanics — a deficit in region A reduces exports to region B, which depletes B's stockpile, which reduces B's exports to C. M43b does not simulate propagation. It detects and labels the emergent outcomes.

## Scope

**In scope:**
- `detect_supply_shocks()` — delta + absolute gate detection, emitting standard `Event` objects to the curator
- `EconomyTracker` — lightweight persistent object holding per-region per-category trailing averages (EMA) for stockpiles and imports
- Trade dependency classification — `import_share` and `trade_dependent` per region on `EconomyResult`
- Raider WAR utility modifier — scaled additive bonus in `compute_weights()` from max adjacent enemy food stockpile
- Narration context — trade dependency and shock data surfaced in `AgentContext` / `CivThematicContext`
- Curator integration — shock events as standard `Event` source with new `CAUSAL_PATTERNS` entries

**Out of scope:**
- Shock propagation simulation (emergent from M43a — no BFS, no wave state machine, no attenuation constant)
- Per-good pricing or demand curves (future milestone)
- Target selection changes in `_resolve_war()` (raider modifier affects WAR weight only, not target choice)
- EMBARGO action weight modification from trade dependency data (trade dependency classification is consumed by curator and narration only; strategic embargo targeting is a future milestone)
- Per-good substitution (future milestone)

**No Rust changes.** Like M43a, M43b is entirely Python-side. No new FFI signals, no modified signal types/ranges.

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Shock propagation is emergent; M43b detects and labels only | M43a's stockpile mechanics produce natural 1-hop/turn propagation with attenuation determined by intermediate stockpile depth and production buffers. No explicit propagation algorithm needed. M43a Decision 7 (reframed): "M43a contains no fixed shock attenuation constant. Attenuation is emergent. M43b validates the emergent rate targets ~50%." |
| 2 | Detection uses delta trigger + absolute severity gate | Delta alone fires on false positives (rich region fluctuating). Absolute alone fires on chronically poor regions that aren't news. Delta detects "something changed"; absolute gate determines "is it actually a crisis." |
| 3 | Delta computed on raw stockpile, severity gated on `food_sufficiency` | `food_sufficiency` is capped at 2.0, compressing the upper range. A region going from 500 to 250 food units might show as `food_sufficiency` 2.0 → 2.0. Raw stockpile captures the real magnitude. The absolute gate uses `food_sufficiency` because that's the crisis signal Rust satisfaction sees. |
| 4 | EMA trailing average (α=0.33), not deque | Exponential moving average with 3-turn effective window. Simpler than maintaining a deque of 3 values, same smoothing behavior. Turn 1 initialized to current stockpile — first-turn shocks impossible by construction. |
| 5 | Trade dependency uses per-turn flow with `food_demand` denominator | `import_share = food_imports / max(food_demand, 0.1)`. Captures structural dependency ("what fraction of our food needs are met by imports"). A region that imports 80% of its food demand is trade-dependent regardless of stockpile buffer. The buffer is a separate signal affecting crisis speed, not dependency classification. |
| 6 | Raider modifier is scaled additive, same pattern as holy war bonus | Binary threshold is too coarse (artificial cliff at threshold). Scaled gives smooth pressure proportional to the prize. Additive (not multiplicative) ensures independent strategic incentive — maximum impact on peace-oriented civs, diminishing impact on already-aggressive civs. The 2.5x weight cap handles degenerate stacking. |
| 7 | Raider checks max adjacent enemy stockpile, not sum | Raider motivation comes from the rich target, not from aggregate wealth of mediocre neighbors. Three poor villages collectively having enough grain doesn't trigger raiding behavior that makes narrative sense. |
| 8 | Raider and holy war bonuses stack intentionally | A religious crusade against a wealthy heretic city gets both bonuses. Historically one of the most common war motivations. No special-case interaction — the 2.5x cap handles combined excesses. |
| 9 | Shock events use standard `Event` model with affected-civ-first actors | No new event class. `event_type="supply_shock"`, `source="economy"`. Affected civ listed first in `actors` because the curator uses `actors[0]` for clustering and role assignment — the famine is Tyre's story, the drought is Aram's story. Upstream civ listed second enables shared-actor causal linking. |
| 10 | Economy result stored as `world._economy_result` (underscore prefix) | Transient per-turn attribute. Set in Phase 2, consumed in Phase 8, overwritten each turn. Underscore prefix ensures Pydantic excludes it from bundle serialization. Follows `_conquered_this_turn` pattern from M41. |

---

## Data Model

### EconomyTracker

Lightweight persistent object for trailing averages. Lives on `simulation.py`'s run state (same level as `world`), not on `Region` or `WorldState`. Not world state — transient analytics state.

```python
class EconomyTracker:
    """Persistent economy analytics state across turns. Not world state."""

    def __init__(self):
        self.trailing_avg: dict[str, dict[str, float]] = {}
        # trailing_avg[region_name][category] = EMA value for stockpile
        self.import_avg: dict[str, dict[str, float]] = {}
        # import_avg[region_name][category] = EMA value for imports

    def update_stockpile(self, region_name: str, category: str, current: float):
        key = self.trailing_avg.setdefault(region_name, {})
        if category not in key:
            key[category] = current  # first turn: initialize to current
        else:
            key[category] = 0.67 * key[category] + 0.33 * current

    def update_imports(self, region_name: str, category: str, current: float):
        key = self.import_avg.setdefault(region_name, {})
        if category not in key:
            key[category] = current
        else:
            key[category] = 0.67 * key[category] + 0.33 * current
```

Two EMA tracks: `trailing_avg` for stockpile levels (shock detection), `import_avg` for import levels (upstream source classification). Same α=0.33 pattern for both.

### Category Goods Mapping

```python
CATEGORY_GOODS = {
    "food": frozenset({"grain", "fish", "botanicals", "exotic", "salt"}),
    "raw_material": frozenset({"timber", "ore"}),
    "luxury": frozenset({"precious"}),
}
```

Consistent with M42's three categories and M43a's `FOOD_GOODS` / `ALL_GOODS`.

### ShockContext (narration model)

```python
class ShockContext(BaseModel):
    region: str
    category: str
    severity: float
    upstream_source: str | None = None
```

Used in `AgentContext.active_shocks`. BaseModel for consistency with other models nested in `AgentContext` and `NarrationContext`.

### Model Extensions

**AgentContext (models.py):**

```python
class AgentContext(BaseModel):
    # ... existing fields ...
    # M43b: Trade & supply context
    trade_dependent_regions: list[str] = Field(default_factory=list)
    active_shocks: list[ShockContext] = Field(default_factory=list)
```

**CivThematicContext (models.py):**

```python
class CivThematicContext(BaseModel):
    # ... existing fields ...
    # M43b: Trade vulnerability summary
    trade_dependency_summary: str | None = None
    # e.g. "3 of 5 regions are trade-dependent (>60% food imports)"
```

### Trade Dependency on EconomyResult

Per-region fields on `EconomyResult`, computed inside `compute_economy()` where `food_demand` is a local variable:

```python
import_share: dict[str, float]       # region_name → food_imports / max(food_demand, 0.1)
trade_dependent: dict[str, bool]     # region_name → import_share > TRADE_DEPENDENCY_THRESHOLD
```

`import_share` is computed inside `compute_economy()` after trade flow resolution (steps 2d-2e), where `food_demand` is locally available. The result is placed directly on `EconomyResult`. This avoids exposing `food_demand` as a separate field — the consumer only needs the ratio.

### EconomyResult Fields Added by M43b

M43b adds six new fields to `EconomyResult`. Three of these (`imports_by_region`, `inbound_sources`, `stockpile_levels`) require modifications to `compute_economy()` to retain data that is currently computed but discarded.

| Field | Type | How Added | Used By |
|---|---|---|---|
| `food_sufficiency` | `dict[str, float]` | Already on `EconomyResult` from M43a (step 2h). No promotion needed — field exists. | `detect_supply_shocks()` severity gate |
| `imports_by_region` | `dict[str, dict[str, float]]` | `region_name → {category → import_total}`. M42's trade flow loop computes per-region imports into `RegionGoods.imports[category]` (transient). M43b captures these into `EconomyResult` before `RegionGoods` is discarded. | `classify_upstream_source()` import drop check |
| `inbound_sources` | `dict[str, list[str]]` | `dest_region → [source_region_names]`. **New tracking.** M42's trade flow loop computes allocations per route but discards source-destination pairings. M43b modifies the trade flow loop to record which source regions supplied each destination. ~5 lines of bookkeeping in the allocation loop. | `classify_upstream_source()` partner lookup |
| `stockpile_levels` | `dict[str, dict[str, float]]` | `region_name → {category → stockpile_total}`. Reads from `Region.stockpile.goods` (persistent world state) after M43a step 2g. Category totals aggregated via `CATEGORY_GOODS`. | `classify_upstream_source()` partner stockpile check |
| `import_share` | `dict[str, float]` | Computed inside `compute_economy()` where `food_demand` is available. | Trade dependency classification, narration |
| `trade_dependent` | `dict[str, bool]` | Derived from `import_share` vs threshold. | Raider modifier, narration, curator |

**Key new work:** `inbound_sources` requires modifying `compute_economy()`'s trade flow allocation loop to accumulate `{dest_region: [source_regions]}` as routes are processed. Currently the loop computes flow volumes per route but doesn't retain the source-destination mapping. The modification is small (~5 lines: initialize dict before loop, append source name when flow > 0) but must be scoped as M43b work, not assumed from M42/M43a.

---

## Detection Logic

### detect_supply_shocks()

Runs in Phase 2, AFTER all M43a stockpile operations complete and AFTER `economy_tracker.update()`:

```python
def detect_supply_shocks(
    world: WorldState,
    stockpiles: dict[str, RegionStockpile],
    economy_tracker: EconomyTracker,
    economy_result: EconomyResult,
    region_map: dict[str, Region],
) -> list[Event]:
    shocks = []
    for name, sp in stockpiles.items():
        region = region_map[name]
        owner_civ = get_civ(world, region.controller)
        for cat, goods in CATEGORY_GOODS.items():
            current = sum(sp.goods.get(g, 0.0) for g in goods)
            avg = economy_tracker.trailing_avg.get(name, {}).get(cat, current)
            # Delta trigger: significant drop from trailing average
            if avg > 0 and current / avg < (1.0 - SHOCK_DELTA_THRESHOLD):
                # Absolute gate (food only): food_sufficiency must be below crisis floor
                if cat == "food":
                    food_suff = economy_result.food_sufficiency[name]
                    if food_suff >= SHOCK_SEVERITY_FLOOR:
                        continue  # delta but no crisis
                    severity = 1.0 - (food_suff / SHOCK_SEVERITY_FLOOR)
                else:
                    # Non-food: severity from delta magnitude alone
                    severity = min(1.0 - (current / max(avg, 0.1)), 1.0)

                upstream = classify_upstream_source(
                    world, economy_tracker, economy_result, name, cat, region_map,
                )
                shocks.append(Event(
                    turn=world.turn,
                    event_type="supply_shock",
                    actors=[owner_civ.name] + ([upstream] if upstream else []),
                    description=f"Supply shock: {cat} in {name}",
                    consequences=[],
                    importance=5 + int(severity * 4),  # 5-9 range
                    source="economy",
                    shock_region=name,
                    shock_category=cat,
                ))
    return shocks
```

`food_sufficiency` sourced from `EconomyResult` (computed in M43a step 2h). Passed explicitly via `economy_result` parameter — no magic attribute lookup.

### Shock Event Metadata

Two optional fields added to `Event` (models.py) for structured shock data:

```python
class Event(BaseModel):
    # ... existing fields ...
    # M43b: Structured shock metadata (None for non-shock events)
    shock_region: str | None = None
    shock_category: str | None = None
```

Set only on `supply_shock` events. Consumed by `build_agent_context_for_moment()` when populating `ShockContext`. Avoids fragile string parsing of `ev.description`. Follows the pattern of optional milestone-specific fields on shared models (e.g., `GreatPerson.origin_region` from M40).

### classify_upstream_source()

Identifies whether a shock is import-driven by comparing current imports against the import EMA:

```python
def classify_upstream_source(
    world: WorldState,
    economy_tracker: EconomyTracker,
    economy_result: EconomyResult,
    region_name: str,
    category: str,
    region_map: dict[str, Region],
) -> str | None:
    """Find upstream civ if shock is import-driven.

    Compares current import level against import EMA. If imports dropped
    significantly, identifies the trade partner whose stockpile also dropped
    (confirming upstream disruption vs embargo). Returns source civ name,
    or None if shock is local (drought, conquest, or embargo without
    upstream production loss).
    """
    current_imports = economy_result.imports_by_region[region_name].get(category, 0.0)
    avg_imports = economy_tracker.import_avg.get(region_name, {}).get(category, current_imports)

    if avg_imports <= 0 or current_imports / avg_imports > (1.0 - SHOCK_DELTA_THRESHOLD):
        return None  # imports didn't drop significantly — local cause

    # Find the trade partner whose stockpile also dropped (upstream disruption)
    for source_name in economy_result.inbound_sources.get(region_name, []):
        source_stockpile = economy_result.stockpile_levels.get(source_name, {}).get(category, 0.0)
        source_avg = economy_tracker.trailing_avg.get(source_name, {}).get(category, source_stockpile)
        if source_avg > 0 and source_stockpile / source_avg < (1.0 - SHOCK_DELTA_THRESHOLD):
            # Upstream source also experienced a stockpile drop — cascade confirmed
            return region_map[source_name].controller

    return None  # imports dropped but no upstream stockpile crash — likely embargo
```

Uses the import EMA on `EconomyTracker` to detect import-driven shocks without storing exact previous-turn data. Same α=0.33 pattern as stockpile tracking.

---

## Raider WAR Modifier

### Placement in compute_weights()

After the holy war modifier (line ~773 in current `action_engine.py`), same additive pattern:

```python
# M43b: Raider incentive — wealthy adjacent enemy stockpiles attract WAR
if hasattr(self.world, '_economy_result') and self.world._economy_result is not None:
    adjacent_enemy_regions = _get_adjacent_enemy_regions(civ, self.world)
    if adjacent_enemy_regions:
        max_adjacent_food = max(
            sum(r.stockpile.goods.get(g, 0.0) for g in FOOD_GOODS)
            for r in adjacent_enemy_regions
        )
        if max_adjacent_food > RAIDER_THRESHOLD:
            raider_bonus = RAIDER_WAR_WEIGHT * min(
                max_adjacent_food / RAIDER_THRESHOLD - 1.0,
                RAIDER_CAP,
            )
            weights[ActionType.WAR] += raider_bonus
```

### _get_adjacent_enemy_regions()

New utility function. Composes existing adjacency data and relationship lookups:

```python
def _get_adjacent_enemy_regions(
    civ: Civilization, world: WorldState,
) -> list[Region]:
    """Find regions adjacent to civ's territory that are controlled by hostile/suspicious civs.

    Composes:
    - civ.regions (list[str]) for owned region names
    - region.adjacencies (adjacency list) for neighbors
    - world.relationships for disposition filtering
    """
    enemy_civs = set()
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                enemy_civs.add(other_name)
    if not enemy_civs:
        return []

    region_map = {r.name: r for r in world.regions}
    own_regions = {name for name in civ.regions}
    adjacent_enemy = []
    for rname in own_regions:
        region = region_map.get(rname)
        if region is None:
            continue
        for adj_name in region.adjacencies:
            adj_region = region_map.get(adj_name)
            if adj_region and adj_region.controller in enemy_civs:
                adjacent_enemy.append(adj_region)

    return adjacent_enemy
```

New function — does not reuse `_resolve_war()` internals (which are tightly coupled to war resolution logic with contested region selection and fog of war). The adjacency walk + disposition filter is straightforward enough to write fresh. Implementation plan should note this is a new ~20-line utility, not a refactor of existing code.

### economy_result on WorldState

Transient per-turn attribute following the `_conquered_this_turn` pattern:

```python
# In simulation.py Phase 2, after compute_economy():
world._economy_result = economy_result

# Consumed in Phase 8 by compute_weights() via self.world._economy_result
# Overwritten each turn. Not persisted to bundle.
# Underscore prefix excludes from Pydantic serialization.
```

---

## Curator Integration

### CAUSAL_PATTERNS Additions

Seven new entries in `curator.py`:

```python
# M43b: Supply shock causal patterns
("drought", "supply_shock", 5, 3.0),      # drought causes local shock
("war", "supply_shock", 3, 2.0),          # conquest disrupts supply
("embargo", "supply_shock", 3, 3.0),      # embargo cuts supply lines
("supply_shock", "famine", 5, 3.0),       # shock causes famine
("supply_shock", "rebellion", 10, 2.0),   # shock causes unrest
("supply_shock", "migration", 10, 2.0),   # shock causes flight
("supply_shock", "supply_shock", 3, 2.5), # propagation chain linking
```

The shock-to-shock entry (`supply_shock → supply_shock`, max gap 3 turns) links cascading shocks into a single narrative arc. Without it, a famine propagating across three regions appears as three independent events instead of one causal chain.

### Shared-Actor Filter

No curator code changes needed. The upstream civ name in `actors[1]` ensures the shared-actor filter in `compute_causal_links()` connects upstream drought events (actor: Aram) to downstream shock events (actors: [Tyre, Aram]). The intersection `{Aram}` satisfies the filter.

Actor ordering: affected civ first (`actors[0]`), upstream source second. The curator uses `actors[0]` for clustering and role assignment — the famine is Tyre's story, not Aram's.

---

## Narration Context

### AgentContext Population

In `build_agent_context_for_moment()` (narrative.py). This function currently does not receive `economy_result` — M43b adds it as an optional parameter (`economy_result: EconomyResult | None = None`) and threads it from the narration pipeline caller.

```python
# M43b: Trade dependency and shock context
if economy_result is not None:
    # Trade-dependent regions for this moment's civs
    moment_civs = {ev.actors[0] for ev in moment.events if ev.actors}
    ctx.trade_dependent_regions = [
        rname for rname, dep in economy_result.trade_dependent.items()
        if dep and region_map[rname].controller in moment_civs
    ]
    # Active shocks from structured event metadata (not string parsing)
    ctx.active_shocks = [
        ShockContext(
            region=ev.shock_region,
            category=ev.shock_category,
            severity=(ev.importance - 5) / 4.0,
            upstream_source=ev.actors[1] if len(ev.actors) > 1 else None,
        )
        for ev in moment.events
        if ev.event_type == "supply_shock"
    ]
```

Only includes regions relevant to the moment's actors. Token-efficient — no global dump.

**Shock event structured metadata:** Rather than parsing region/category from `ev.description` (fragile string splitting), shock events store structured metadata. See "Shock Event Metadata" section below.

### CivThematicContext Population

**Deferred:** `CivThematicContext` is defined in `models.py` but never constructed anywhere in the current codebase. The `NarrationContext.civ_context` field exists as dead infrastructure. The `trade_dependency_summary` field is added to the model (ready for future use), but the population code below cannot be wired until `CivThematicContext` construction is implemented in a future milestone. The field defaults to `None`.

When `CivThematicContext` construction is wired, add this population logic inline:

```python
# M43b: Trade dependency summary
if economy_result is not None:
    civ_regions = [r for r in world.regions if r.controller == civ.name]
    dep_count = sum(
        1 for r in civ_regions
        if economy_result.trade_dependent.get(r.name, False)
    )
    if dep_count > 0:
        ctx.trade_dependency_summary = (
            f"{dep_count} of {len(civ_regions)} regions are trade-dependent "
            f"(>{int(TRADE_DEPENDENCY_THRESHOLD * 100)}% food imports)"
        )
```

### Narrator Prompt Serialization

In `build_agent_context_block()`:

```python
if ctx.trade_dependent_regions:
    lines.append(f"Trade-dependent regions: {', '.join(ctx.trade_dependent_regions)}")
if ctx.active_shocks:
    for shock in ctx.active_shocks:
        lines.append(
            f"Supply crisis in {shock.region}: {shock.category} "
            f"(severity {shock.severity:.1f}, "
            f"source: {shock.upstream_source or 'local'})"
        )
```

Structured data available to the LLM narrator. The narrator decides salience — same pattern as M40's relationship context.

---

## Phase 2 Integration

### Modified Turn Loop Sub-Sequence

M43b adds three steps after M43a's stockpile operations:

```
2a-2l: M42/M43a unchanged (production through stockpile cap)
--- M43b additions ---
2m: economy_tracker.update_stockpile() — EMA update for all regions/categories
2n: economy_tracker.update_imports() — EMA update for import levels
2o: detect_supply_shocks() — delta + absolute gate → list[Event]
    Append shock events to turn event list
2p: Store world._economy_result (transient, for Phase 8 raider modifier)
--- existing Phase 2: trade income (agents=off path), tribute, treasury ---
```

Ordering: `compute_economy()` first (returns `EconomyResult` with updated stockpiles, trade flows, `import_share`, `trade_dependent`), then `economy_tracker.update()` (both tracks), then `detect_supply_shocks()`. This ensures the tracker has current-turn data before detection runs, and detection has access to both the current state and the trailing average.

---

## Constants

All new constants in `economy.py` with `[CALIBRATE]` markers:

### Shock Detection

| Constant | Initial Value | Tuning Target |
|---|---|---|
| `SHOCK_DELTA_THRESHOLD` | 0.30 | 30% drop from trailing avg triggers detection |
| `SHOCK_SEVERITY_FLOOR` | 0.8 | `food_sufficiency` below this = food crisis |

### Trade Dependency

| Constant | Initial Value | Tuning Target |
|---|---|---|
| `TRADE_DEPENDENCY_THRESHOLD` | 0.6 | >60% food import share = trade dependent |

### Raider Mechanic

| Constant | Initial Value | Tuning Target |
|---|---|---|
| `RAIDER_THRESHOLD` | `[CALIBRATE]` | Stockpile level that starts attracting raiders. Depends on M43a stockpile equilibrium levels — set after M43a 200-seed data available. |
| `RAIDER_WAR_WEIGHT` | 0.15 | Base additive WAR bonus at 1× overshoot |
| `RAIDER_CAP` | 2.0 | Max overshoot multiplier (bonus caps at 0.30) |

### RNG Stream Offsets

No new RNG sources in M43b. All detection and classification is deterministic.

---

## Testing

### Unit Tests

- `EconomyTracker.update_stockpile()`: EMA converges to constant input, responds to step change
- `EconomyTracker.update_imports()`: same EMA behavior
- `detect_supply_shocks()`: fires on delta + below severity floor, does NOT fire on delta alone (above floor), does NOT fire on chronically low (no delta)
- `detect_supply_shocks()`: non-food categories use delta-only severity (no `food_sufficiency` gate)
- `classify_upstream_source()`: returns upstream civ when imports dropped; returns None when shock is local
- Trade dependency: `import_share` computed correctly from `food_imports / food_demand`
- Trade dependency: `trade_dependent` flips at threshold
- Raider modifier: zero when no adjacent enemy regions, zero when below threshold, scaled correctly above threshold, capped at `RAIDER_WAR_WEIGHT * RAIDER_CAP`
- Raider modifier: uses max (not sum) across adjacent enemy regions
- `_get_adjacent_enemy_regions()`: returns correct regions for hostile/suspicious neighbors, empty for friendly/allied
- Shock event actors: affected civ first, upstream civ second (when present)
- Shock event importance: scales from 5 (severity 0.0) to 9 (severity 1.0)

### Curator Integration Tests

- Shock events flow through `curate()` pipeline without error
- `CAUSAL_PATTERNS` entries link drought → supply_shock when events share an actor and are within max_gap
- supply_shock → supply_shock links produce chain (propagation arc)
- Shock events cluster with related famine/migration events in nearby turns

### Integration Tests

- **Shock detection end-to-end:** Engineer a drought (reduce production to 0 in a region). Verify `supply_shock` event emitted within 2 turns.
- **Trade dependency classification:** Create a region importing >60% food. Verify `trade_dependent = True`. Cut imports (embargo). Verify `food_sufficiency` drops.
- **Raider modifier:** Set up a civ adjacent to a hostile civ with large food stockpile. Verify WAR weight increases above baseline. Verify WAR weight at baseline when stockpile is below threshold.
- **Narration context:** Verify `AgentContext.trade_dependent_regions` populated for trade-dependent regions. Verify `active_shocks` populated when shock events exist in moment.
- **`--agents=off` compatibility:** Shock detection and trade dependency classification work in all modes (computed in Phase 2, which runs regardless of agent mode). Raider modifier also fires in aggregate mode — `_economy_result` is set in Phase 2 for all modes. This is correct: the raider modifier affects civ-level action weights, not agent-level behavior. The action engine runs in both aggregate and agent modes.

### 200-Seed Regression (M43b-Specific)

- **Emergent shock attenuation:** Measure price/sufficiency impact at 1, 2, 3 hops from an engineered production drop. Target: ~50% attenuation per hop (emergent from M43a stockpile mechanics). If outside 30-80% range, indicates M43a constant tuning issue, not M43b architecture problem.
- **Shock frequency:** Supply shock events should appear 2-5 times per 500-turn run (not every drought, only significant ones).
- **Trade dependency distribution:** 10-30% of regions should be trade-dependent in a typical run. If 0% or >50%, threshold needs calibration.
- **Raider WAR frequency:** Civs adjacent to wealthy targets should engage in 10-20% more wars than baseline. Not a dominant effect — raiding is one incentive among many.
- **Satisfaction distribution:** No regression from M43a baseline. Shock detection is read-only; raider modifier is small additive.
- **Action distribution:** WAR frequency should increase marginally (raider bonus). Other action types unchanged. Verify no action dominance from raider stacking with holy war.

---

## File Impact

| File | Changes |
|---|---|
| `src/chronicler/economy.py` | `EconomyTracker` class, `detect_supply_shocks()`, `classify_upstream_source()`, `_get_adjacent_enemy_regions()`, `CATEGORY_GOODS`, shock detection constants, `RAIDER_*` constants. Modify `compute_economy()`: add `inbound_sources` tracking (~5 lines in trade flow loop), compute `import_share`/`trade_dependent`, promote `food_sufficiency` and `stockpile_levels` to `EconomyResult` fields, capture `imports_by_region` from transient `RegionGoods`. |
| `src/chronicler/action_engine.py` | Raider WAR modifier block in `compute_weights()` after holy war bonus (~15 lines) |
| `src/chronicler/simulation.py` | `EconomyTracker` instantiation in run setup, wire `economy_tracker.update()` + `detect_supply_shocks()` into Phase 2 after M43a stockpile ops, store `world._economy_result` |
| `src/chronicler/curator.py` | 7 new `CAUSAL_PATTERNS` entries |
| `src/chronicler/models.py` | `ShockContext` BaseModel, `shock_region`/`shock_category` optional fields on `Event`, `trade_dependent_regions: list[str]` and `active_shocks: list[ShockContext]` on `AgentContext`, `trade_dependency_summary: str | None` on `CivThematicContext` |
| `src/chronicler/narrative.py` | `build_agent_context_for_moment()` gains `economy_result` parameter, populates trade/shock fields. `build_agent_context_block()` serializes them. `CivThematicContext` population gains dependency summary (inline where context is built). |

**No Rust changes.** No new FFI signals, no `satisfaction.rs`, `region.rs`, `agent.rs`, `tick.rs`, or `signals.rs` changes. M43b is entirely Python-side.

### New utility note

`_get_adjacent_enemy_regions()` is a new ~20-line utility function. It composes `civ.regions`, `region.adjacencies`, and `world.relationships` disposition filtering. It does NOT reuse `_resolve_war()` internals (which are tightly coupled to contested region selection and fog of war). The adjacency walk + disposition filter is straightforward enough to write fresh.
