# M43a: Transport, Perishability & Stockpiles — Design Spec

> **Status:** Draft
>
> **Author:** Cici (Opus 4.6)
>
> **Reviewed by:** Tate (design decisions)
>
> **Depends on:** M42 (Goods Production & Trade), M34 (Resources & Seasons), M35 (Rivers & Trade Corridors)
>
> **Blocked by:** M42 (spec complete, awaiting implementation)

---

## Goal

Make geography matter for trade. Transport costs create economic zones where coastal and river regions are natural hubs. Perishability limits food trade range while luxury crosses continents. Stockpiles buffer production shocks, and salt becomes strategically valuable as a preservative. This transforms M42's stateless per-turn economy into one with persistent material state and geographic differentiation.

## Scope

**In scope:**
- Per-route transport cost computation (terrain, infrastructure, season modifiers) as pre-allocation margin reduction in M42's trade flow
- Per-good perishability as post-allocation volume attrition on delivered goods
- `RegionStockpile` model with `dict[str, float]` persistent on `Region`, accumulating surplus after trade
- Per-good stockpile decay with per-good rates (grain fast, dates slow, durables zero)
- Salt preservation: proportional to salt-to-food ratio, capped at 50% decay reduction
- Conquest stockpile destruction (50% loss on region change)
- Conservation law update (global balance across production, consumption, transit loss, storage loss, cap overflow)
- `food_sufficiency` updated to read from pre-consumption stockpile rather than single-turn production

**Out of scope (M43b):**
- Supply shock detection (`ShockEvent` for curator)
- Trade dependency classification (>60% food import)
- Raider WAR utility modifier from stockpile levels
- Narration context for trade dependency

**Out of scope (future):**
- Per-good pricing and demand curves
- Per-good substitution (dates vs grain)
- Transport perishability modified by salt (stockpile-only for now)
- Road infrastructure mechanic (placeholder constant ready to wire)

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | `RegionStockpile` with `dict[str, float]`, not fields on `Region` or persistent `RegionGoods` | Flow (transient `RegionGoods`) stays separate from stock (persistent `RegionStockpile`). Dict handles M42 category keys → M43 per-good keys cleanly. Parallels `RegionEcology` nesting pattern. |
| 2 | Transport cost as pre-allocation margin reduction; perishability as post-allocation volume attrition | Two distinct mechanisms: "should we ship?" (economic) vs "how much arrives?" (physical). Perishability-as-margin is circular (depends on volume, which depends on allocation). Transport cost is per-route, not per-category. |
| 3 | Category-level pricing/allocation unchanged from M42; per-good tracking only for stockpile and decay | Perishability requires per-good distinction (grain ≠ dates). Pricing doesn't — yet. Production mix bridges category-level trade to per-good stockpile. Per-good pricing is a future milestone. |
| 4 | Salt preservation proportional to salt-to-food ratio, capped at 50% | Binary threshold is crude. Proportional scaling means abundant salt preserves well, a trickle barely helps. Cap prevents salt from eliminating decay entirely. |
| 5 | Salt doesn't decay (mineral) | Salt is `DECAY_RATE = 0.0`. Depletes only through population consumption via normal food demand. Accumulates as strategic reserve. |
| 6 | Single-pass Phase 2, no within-turn price convergence | Transport cost filtering removes routes → prices shift → could reopen routes. This feedback plays out over turns via one-turn lag, not within Phase 2. Geographic price gradients emerge over 3-5 turns. |
| 7 | M43a contains no fixed shock attenuation constant | Attenuation behavior is emergent from stockpile depth and production buffers. M43b validates the emergent rate targets ~50%. No 0.5 multiplier in any formula. |
| 8 | Conquest stockpile destruction in `_resolve_war()` | 50% of stockpile lost when region changes hands during action resolution in `_resolve_war()` (`action_engine.py`). Applied at point of conquest, before Phase 10 snapshot. |
| 9 | `food_sufficiency` from pre-consumption stockpile | Ordering: stockpile += supply → compute `food_sufficiency` from pre-consumption stockpile → demand drawdown → storage decay → cap. Pre-consumption is backwards-compatible with M42 at equilibrium after initialization buffer is consumed (turns 3+): `food_available = production + imports` = M42's `food_supply`, producing `food_sufficiency = 1.0`. Turn 1-2 `food_sufficiency` will be higher than M42 due to initial buffer (Decision 11) — this is a feature, not a regression. Post-consumption would produce 0.0 at equilibrium — a satisfaction crash. |
| 10 | Stockpile capacity cap proportional to population | `PER_GOOD_CAP_FACTOR * population` per good per region. Unbounded accumulation pins `food_sufficiency` at ceiling and produces meaningless outlier values. Cap proportional to population — larger regions store more, per-capita storage bounded. |
| 11 | Stockpile initialization with subsistence buffer | `stockpile[primary_food] = INITIAL_BUFFER * population`. Avoids 5-turn starvation transient that's purely an artifact of M43a landing, not an emergent outcome. Target: ~2 turns consumption at equilibrium demand. |

---

## Data Model

### New Pydantic Model

```python
# Per-good key set used across stockpile, perishability, and consumption
FOOD_GOODS = frozenset({"grain", "fish", "botanicals", "exotic", "salt"})
ALL_GOODS = frozenset({"grain", "timber", "botanicals", "fish", "salt", "ore", "precious", "exotic"})

class RegionStockpile(BaseModel):
    goods: dict[str, float] = Field(default_factory=dict)
    # Per-good keys: members of ALL_GOODS
    # Values: accumulated units, capped per PER_GOOD_CAP_FACTOR * population
```

`FOOD_GOODS` includes salt — salt is Food (M42 Decision 1). Salt is consumed through the demand drawdown loop like any other food good: population eats salt proportional to its share of the food stockpile. This is the mechanism for salt depletion referenced in Decision 5. The salt preservation code explicitly excludes salt from `total_food` via `if g != "salt"` because salt doesn't preserve itself — that's a special case in the preservation formula, not a membership question.

### Nested on Region

```python
class Region(BaseModel):
    ...
    ecology: RegionEcology = Field(default_factory=RegionEcology)
    stockpile: RegionStockpile = Field(default_factory=RegionStockpile)
```

### Mapping Function

```python
def map_resource_to_good(resource_type: int) -> str:
    """Maps M34 resource type enum to per-good stockpile key."""
    mapping = {
        0: "grain", 1: "timber", 2: "botanicals", 3: "fish",
        4: "salt", 5: "ore", 6: "precious", 7: "exotic",
    }
    return mapping[resource_type]
```

M42's `map_resource_to_category()` still used for pricing/allocation. `map_resource_to_good()` used for stockpile operations. The bridge: when category-level trade delivers food to a region, the per-good composition is determined by the source region's `resource_types[0]` via `map_resource_to_good()`.

---

## Transport Cost

Per-route cost computed from terrain of both endpoints and seasonal modifier:

```python
def compute_transport_cost(
    region_a: Region, region_b: Region, world: WorldState,
) -> float:
    """Per-route transport cost. Subtracted from raw margin for effective margin."""
    base = TRANSPORT_COST_BASE
    terrain_factor = max(
        TERRAIN_COST[region_a.terrain], TERRAIN_COST[region_b.terrain]
    )  # worst terrain on route determines cost
    river = RIVER_DISCOUNT if is_river_route(region_a, region_b, world) else 1.0
    coastal = COASTAL_DISCOUNT if is_coastal_route(region_a, region_b) else 1.0
    seasonal = WINTER_MODIFIER if world.season == "winter" else 1.0
    infra = INFRASTRUCTURE_DISCOUNT  # placeholder 1.0 — no roads yet
    return base * terrain_factor * infra * min(river, coastal) * seasonal
```

### Terrain Cost Table

| Terrain | Factor | Notes |
|---|---|---|
| Plains | 1.0 | Reference terrain |
| Forest | 1.3 | Moderate impediment |
| Desert | 1.5 | Harsh crossing |
| Mountain | 2.0 | Most expensive land route |
| Coast | 0.6 | Port routes cheapest |

### Route Type Detection

- **River route:** Both `region_a.name` and `region_b.name` appear in the same `River.regions` list (M35a `world.rivers`).
- **Coastal route:** Both regions have `terrain == "coast"`. Port-to-port between adjacent coastal regions.
- **Infrastructure (roads):** Not currently modeled. `INFRASTRUCTURE_DISCOUNT = 1.0` (no effect). Placeholder for future mechanic. Transport cost formula includes the term so it's ready to wire when roads land.
- **`min(river, coastal)`:** A route takes the better of river or coastal discount. In practice a route is one or the other, but the min handles edge cases without branching.

### Integration with M42 Trade Flow

Transport cost plugs into M42's pro-rata allocation by replacing raw margin:

```python
effective_margin = max(dest_price[cat] - origin_price[cat] - transport_cost, 0)
# Zero effective margin → zero flow (route filtered)
```

This replaces `raw_margin` in both Level 1 (cross-category) and Level 2 (per-route) pro-rata allocation. Routes where transport cost exceeds the price gap get zero flow automatically. Merchants are "smart" — they factor in transport costs before allocating.

Transport cost is per-route, not per-category. The same cost applies to food, raw material, and luxury on a given route. Per-category differentiation happens in perishability (post-allocation), not transport costs (pre-allocation).

---

## Perishability

### Transit Decay (Post-Allocation Volume Attrition)

After category-level allocation determines how much flows on each route, category-level flows are decomposed to per-good using the source region's production mix, then perishability reduces delivered volume:

```python
# Per-route, per-good: compute decay before summing into destination stockpile
for route in inbound_routes:
    source_good = map_resource_to_good(source_region.resource_types[0])
    delivered = shipped_on_route * (1.0 - TRANSIT_DECAY[source_good])
    # Sum delivered into destination's per-good import total
    imports[source_good] += delivered
```

Transit decay is computed per-route-per-good before aggregating imports into the destination stockpile. Since each source region produces one good (single-resource-slot production, M41 Decision 14), each route delivers one good type, and the per-route and per-good approaches are equivalent. The ordering matters: decay first, then aggregate — not aggregate then decay — because different inbound routes may deliver different goods at different decay rates.

All M42 routes are adjacent boundary pairs (hop distance = 1 per M42 Decision 15). No `hop_distance` variable. If a future milestone adds caravan routes spanning multiple hops, the formula extends to `(1.0 - TRANSIT_DECAY[good]) ** hops`.

A route carrying "food" from a grain region loses 5% to transit decay. The same route from a fish region loses 8%. The category-level allocation decides volume; the per-good decay determines what arrives.

### Storage Decay (Per-Turn Stockpile Attrition)

Each turn, goods in stockpile decay at per-good rates, modified by salt preservation:

```python
total_food = sum(stockpile.goods[g] for g in FOOD_GOODS if g != "salt")
salt_ratio = stockpile.goods.get("salt", 0.0) / max(total_food, 0.1)
preservation = min(salt_ratio * SALT_PRESERVATION_FACTOR, MAX_PRESERVATION)

for good in stockpile.goods:
    if good == "salt":
        continue  # mineral, zero decay
    rate = STORAGE_DECAY[good]
    if good in FOOD_GOODS:
        rate *= (1.0 - preservation)
    stockpile.goods[good] *= (1.0 - rate)
```

Salt preservation:
- Proportional to salt-to-food ratio. ~20% salt-to-food ratio reaches the 50% cap.
- Only affects food goods. Raw material and luxury decay (if any) is not salt-dependent.
- Salt itself has `STORAGE_DECAY = 0.0`. It depletes only through population consumption (normal food demand).

### Decay Rate Tables

| Good | Transit Decay (per hop) | Storage Decay (per turn) | 1/e Decay Time |
|---|---|---|---|
| Grain | 0.05 (5%) | 0.03 | ~30 turns without salt |
| Fish | 0.08 (8%) | 0.06 | ~15 turns |
| Botanicals | 0.04 (4%) | 0.02 | ~50 turns (dried herbs) |
| Exotic | 0.06 (6%) | 0.04 | ~25 turns |
| Salt | 0.0 | 0.0 | Indefinite (mineral) |
| Timber | 0.01 (1%) | 0.005 | ~200 turns (very slow rot) |
| Ore | 0.0 | 0.0 | Indefinite (mineral) |
| Precious | 0.0 | 0.0 | Indefinite (mineral) |

Transit decay is higher than storage decay — goods on a cart exposed to elements deteriorate faster than goods in a granary.

---

## Stockpile

### Accumulation

Per-region, per-good. Surplus after trade and consumption accumulates:

```python
stockpile[good] += (local_production[good] - exported[good]) + imported[good]
```

Where:
- `local_production[good]` = per-good production via `map_resource_to_good(resource_types[0])` × farmer count × yield
- `exported[good]` = per-good decomposition of category-level exports. A grain region's "food" exports are grain.
- `imported[good]` = per-good decomposition of category-level imports via source region production mix. Imports from a grain region are grain; imports from a fish region are fish.

Single-resource-slot production (M42 Decision 14 / M41 Decision 14) means each region produces one good, simplifying the per-good decomposition: all of a region's production and exports in a given category map to one good key.

### Consumption

Demand drawdown from stockpile with non-negative clamping:

```python
for good in FOOD_GOODS:
    consumed = min(demand_for_good, stockpile.goods.get(good, 0.0))
    stockpile.goods[good] = stockpile.goods.get(good, 0.0) - consumed
    # Unmet demand = demand - consumed
    # Not tracked mechanically; captured by food_sufficiency < 1.0
```

Demand distribution across food goods: proportional to stockpile composition. If a region's food stockpile is 60% grain and 40% fish, consumption draws 60% from grain and 40% from fish.

Unmet demand has no separate tracking. The gap between `food_sufficiency` and 1.0 (computed pre-consumption in step 2h) already signals the deficit to Rust satisfaction.

### Capacity Cap

```python
stockpile.goods[good] = min(stockpile.goods[good], PER_GOOD_CAP_FACTOR * population)
```

Per-good, per-region. Larger regions store more. `PER_GOOD_CAP_FACTOR` `[CALIBRATE]` — target: cap should bind only for regions with sustained surplus, not at equilibrium.

### Initialization

At world setup:

```python
primary_good = map_resource_to_good(region.resource_types[0])
region.stockpile.goods[primary_good] = INITIAL_BUFFER * population
```

`INITIAL_BUFFER` `[CALIBRATE]` — target: ~2 turns consumption at equilibrium demand. Prevents starvation transient in turns 1-5.

### Conquest Destruction

In `_resolve_war()` when a region changes hands:

```python
for good in region.stockpile.goods:
    region.stockpile.goods[good] *= CONQUEST_STOCKPILE_SURVIVAL  # 0.5
```

50% of each good destroyed. Applied at point of conquest, before Phase 10 snapshot.

---

## Phase 2 Integration

### Modified Turn Loop Sub-Sequence

All stockpile operations run within Phase 2, extending M42's goods computation:

```
2a: Production (M42 unchanged)
2b: Demand (M42 unchanged)
2c: Surplus (M42 unchanged)
2d: Trade flow — MODIFIED: effective_margin replaces raw_margin in pro-rata allocation
2e: Imports — MODIFIED: per-good perishability attrition on delivered goods
2f: Prices (M42 unchanged)
--- M43a additions ---
2g: Stockpile accumulation (production - exports + imports → per-good stockpile)
2h: food_sufficiency from pre-consumption stockpile
2i: Demand drawdown from stockpile (clamped to available)
2j: Storage decay (with salt preservation)
2k: Cap stockpile
2l: Remaining signals (farmer_income_modifier, merchant_margin — M42 unchanged)
--- existing Phase 2: trade income (agents=off path), tribute, treasury ---
```

### food_sufficiency Change

M42 computes from single-turn supply/demand:
```python
# M42:
food_sufficiency = min(food_supply / max(food_demand, 0.1), 2.0)
```

M43a changes source to pre-consumption stockpile:
```python
# M43a (step 2h, after stockpile accumulation, before demand drawdown):
food_stockpile = sum(stockpile.goods.get(g, 0.0) for g in FOOD_GOODS)
food_sufficiency = min(food_stockpile / max(food_demand, 0.1), 2.0)
```

Backwards-compatible at equilibrium after initialization buffer is consumed (turns 3+): `food_stockpile = production + 0 (depleted buffer) + imports`, matching M42's `food_supply = production + imports`. Produces `food_sufficiency = 1.0`. Turn 1-2 `food_sufficiency` will be higher than M42 due to initial buffer (Decision 11) — this is a feature, not a regression.

Stockpile buffer effect: a region with 3 turns of grain reserves has `food_stockpile = 3 × demand`, producing `food_sufficiency = min(3.0, 2.0) = 2.0` even if this turn's production drops to zero. This is exactly what buffers should do — smoothing single-turn production shocks.

---

## FFI Changes

**No new FFI signals.** M43a modifies the source of `food_sufficiency` (stockpile-based instead of single-turn production) but the signal itself, its type (`f32`), its range (`[0.0, 2.0]`), and its Rust consumption in `satisfaction.rs` are all M42-unchanged. The Rust side doesn't know or care whether Python computed `food_sufficiency` from production or from stockpile — it receives the same float.

`farmer_income_modifier` and `merchant_margin` also unchanged in type and range. Transport costs affect the Python-side margin computation that feeds `merchant_margin`, but the signal to Rust is the same normalized `[0.0, 1.0]` float.

**No Rust code changes.** M43a is entirely Python-side. This significantly reduces risk and testing surface compared to milestones that cross the FFI boundary.

---

## Constants

All new constants in `economy.py` with `[CALIBRATE]` markers:

### Transport

| Constant | Initial Value | Tuning Target |
|---|---|---|
| `TRANSPORT_COST_BASE` | 0.10 | 10% goods value per hop baseline |
| `TERRAIN_COST["plains"]` | 1.0 | Reference terrain |
| `TERRAIN_COST["forest"]` | 1.3 | Moderate impediment |
| `TERRAIN_COST["desert"]` | 1.5 | Harsh crossing |
| `TERRAIN_COST["mountain"]` | 2.0 | Most expensive land route |
| `TERRAIN_COST["coast"]` | 0.6 | Port routes cheapest |
| `RIVER_DISCOUNT` | 0.5 | River routes half cost |
| `COASTAL_DISCOUNT` | 0.6 | Port-to-port cheap |
| `INFRASTRUCTURE_DISCOUNT` | 1.0 | Placeholder — no roads yet |
| `WINTER_MODIFIER` | 1.5 | Winter increases transport cost |

### Transit Perishability (Per Hop)

| Constant | Initial Value | Notes |
|---|---|---|
| `TRANSIT_DECAY["grain"]` | 0.05 | 5% loss per hop |
| `TRANSIT_DECAY["fish"]` | 0.08 | Most perishable food |
| `TRANSIT_DECAY["botanicals"]` | 0.04 | Herbs, moderate |
| `TRANSIT_DECAY["exotic"]` | 0.06 | Tropical, moderate-high |
| `TRANSIT_DECAY["salt"]` | 0.0 | Mineral, no decay |
| `TRANSIT_DECAY["timber"]` | 0.01 | Slight breakage |
| `TRANSIT_DECAY["ore"]` | 0.0 | Mineral, no decay |
| `TRANSIT_DECAY["precious"]` | 0.0 | Durable, no decay |

### Storage Decay (Per Turn)

| Constant | Initial Value | 1/e Decay Time |
|---|---|---|
| `STORAGE_DECAY["grain"]` | 0.03 | ~30 turns without salt |
| `STORAGE_DECAY["fish"]` | 0.06 | ~15 turns |
| `STORAGE_DECAY["botanicals"]` | 0.02 | ~50 turns (dried herbs) |
| `STORAGE_DECAY["exotic"]` | 0.04 | ~25 turns |
| `STORAGE_DECAY["salt"]` | 0.0 | Indefinite (mineral) |
| `STORAGE_DECAY["timber"]` | 0.005 | ~200 turns (very slow rot) |
| `STORAGE_DECAY["ore"]` | 0.0 | Indefinite (mineral) |
| `STORAGE_DECAY["precious"]` | 0.0 | Indefinite (mineral) |

### Salt Preservation

| Constant | Initial Value | Tuning Target |
|---|---|---|
| `SALT_PRESERVATION_FACTOR` | 2.5 | ~20% salt-to-food ratio hits cap |
| `MAX_PRESERVATION` | 0.5 | Decay halved at most |

### Stockpile

| Constant | Initial Value | Tuning Target |
|---|---|---|
| `PER_GOOD_CAP_FACTOR` | `5.0 * PER_CAPITA_FOOD` | ~5 turns of per-capita consumption before cap binds. Derived from M42's `PER_CAPITA_FOOD`. |
| `INITIAL_BUFFER` | `2.0 * PER_CAPITA_FOOD` | ~2 turns of per-capita consumption at equilibrium. Derived from M42's `PER_CAPITA_FOOD`. |
| `CONQUEST_STOCKPILE_SURVIVAL` | 0.5 | 50% lost on conquest |

### RNG Stream Offsets

No new RNG sources in M43a. All allocation and decay is deterministic. `GOODS_ALLOC_STREAM_OFFSET = 800` in `agent.rs` remains reserved but unused.

---

## Analytics & Narration

### Analytics Extractors

- Per-region per-good stockpile level time series
- Per-route transport cost (diagnostic for geographic differentiation)
- Per-region effective margin vs raw margin (transport cost filtering diagnostic)
- Transit loss per route per category (perishability diagnostic)

All computed from `EconomyResult` and `RegionStockpile` during Phase 10 analytics extraction.

### Narration Context

- Stockpile levels available for prosperity/famine narratives
- Salt stockpile data for "preserved granaries" narratives
- Transport cost data available for trade route narratives (arduous mountain crossings vs easy river trade)

### Bundle

No new top-level bundle fields. Stockpile data included in existing analytics data structures.

---

## Testing

### Unit Tests

- `map_resource_to_good()` returns correct key for all 8 resource types
- Transport cost: terrain factor, river discount, coastal discount, winter modifier compose correctly
- Effective margin: `max(raw_margin - transport_cost, 0)` — positive, zero, and negative cases
- Transit perishability: `shipped * (1 - TRANSIT_DECAY[good])` for each good
- Storage decay: per-good rates applied correctly
- Salt preservation: proportional to salt-to-food ratio, capped at `MAX_PRESERVATION`
- Salt preservation at zero food: no division by zero (guarded by `max(total_food, 0.1)`)
- Stockpile cap: enforced per-good at `PER_GOOD_CAP_FACTOR * population`
- Stockpile initialization: primary food good seeded at `INITIAL_BUFFER * population`
- Conquest destruction: each good multiplied by `CONQUEST_STOCKPILE_SURVIVAL`
- Consumption clamping: `min(demand, stockpile)` — never goes negative
- Demand distribution: proportional to stockpile composition across food goods

### Conservation Law

Global balance across all regions per turn:

```
sum(old_stockpile) + sum(production) =
    sum(new_stockpile) + sum(consumption) + sum(transit_loss) + sum(storage_loss) + sum(cap_overflow)
```

Where `transit_loss = sum(shipped) - sum(delivered)` across all routes. `consumption` includes salt consumed through the demand drawdown loop (salt is in `FOOD_GOODS` and depletes proportionally). This accounts for every unit of goods. Nothing from nothing, nothing silently vanishes. Updates M42's conservation test to include stockpile persistence, transit decay, and storage decay terms.

### Integration Tests

- **Geographic price gradient:** Mountain-separated regions have wider price spreads than river-connected regions (transport costs filter mountain routes, river routes stay profitable at smaller margins)
- **Perishability range:** Food trade concentrates in 1-2 hop radius (grain exports lose 5% per hop, profitable only at meaningful margins). Luxury trade unaffected by decay.
- **Salt strategic value:** Salt-producing regions' neighbors have slower food stockpile depletion than non-salt-connected regions over 10 turns
- **Stockpile buffer:** Engineer production drop (drought). Region with stockpile maintains `food_sufficiency > 0.8` for 2-3 turns. Region without stockpile drops immediately.
- **Conquest destruction:** Region changes hands, stockpile drops ~50%. `food_sufficiency` drops correspondingly.
- **M42 backward compatibility:** `food_sufficiency` at equilibrium (production = demand, no buffer) produces same value as M42 (1.0). No satisfaction regression.
- **`--agents=off` invariance:** Stockpile accumulates but no FFI signals change (agents=off uses aggregate path)

### 200-Seed Regression (M43a-Specific)

- **Satisfaction distribution:** Stockpile buffers should reduce `food_sufficiency` volatility vs M42 baseline (fewer spikes to 0.0, smoother curves)
- **Price spread across regions:** Transport costs should create geographic differentiation (coastal/river clusters tighter spreads than mountain-separated regions)
- **Salt trade volume:** Salt-producing regions should have above-average export volume
- **Stockpile levels:** Distribution should not pin at cap (cap too low) or be negligible (cap too high)
- **Wealth distribution:** `farmer_income_modifier` unchanged but trade patterns shift — verify Gini stays in M42 range

---

## File Impact

| File | Changes |
|---|---|
| `src/chronicler/models.py` | Add `RegionStockpile` model, nest on `Region` as `stockpile: RegionStockpile` |
| `src/chronicler/economy.py` | `map_resource_to_good()`, transport cost computation, perishability attrition, stockpile accumulation/decay/cap, salt preservation, `TRANSIT_DECAY` and `STORAGE_DECAY` tables, consumption clamping, modified `compute_economy()` entry point, updated `food_sufficiency` source |
| `src/chronicler/simulation.py` | Stockpile initialization in world setup, pass stockpile to `compute_economy()` |
| `src/chronicler/action_engine.py` | Conquest stockpile destruction in `_resolve_war()` |
| `src/chronicler/analytics.py` | Stockpile level time series extractors, transport cost diagnostics |

**No Rust changes.** No new FFI signals, no modified signal types/ranges, no `satisfaction.rs`, `region.rs`, `agent.rs`, `tick.rs`, or `signals.rs` changes. M43a is entirely Python-side.
