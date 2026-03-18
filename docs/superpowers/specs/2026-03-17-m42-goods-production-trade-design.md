# M42: Goods Production & Trade — Design Spec

> **Status:** Draft
>
> **Author:** Cici (Opus 4.6)
>
> **Reviewed by:** Phoebe (design decisions), pending Phoebe spec review
>
> **Depends on:** M34 (Resources & Seasons), M35 (Rivers & Trade Corridors), M41 (Wealth & Class Stratification)
>
> **Blocked by:** M41 (spec complete, awaiting implementation)

---

## Goal

Regions produce goods from their resources; merchants carry goods along trade routes; supply and demand create prices that drive agent economic behavior. This transforms the economy from abstract numbers into concrete flow of materials across geography, and completes the four M41 deferred economic integrations (treasury tax wiring, tithe base swap, per-resource market pricing, per-priest tithe share).

## Scope

**In scope:**
- Category-level goods model (3 categories: Food, Raw Material, Luxury) tied to M34 resource types
- Per-region production from farmer occupation counts × resource yields
- Per-category demand formulas (population, soldiers, wealthy agents)
- Merchant carry model: abstract flow along M35 trade routes, margin-weighted pro-rata allocation
- Trade route decomposition: civ-level routes resolved to region-level boundary pairs
- Per-region per-category price computation from supply/demand ratio
- Three FFI signals to Rust: `farmer_income_modifier`, `food_sufficiency`, `merchant_margin`
- M41 deferred integration: treasury tax, tithe base swap, per-resource pricing, per-priest tithe share
- New `economy.py` module with `compute_economy()` entry point
- Analytics: per-region per-category price time series

**Out of scope (deferred):**
- Per-good prices within categories (grain vs fish vs dates) — M43
- Perishability and shelf life — M43
- Stockpile accumulation and drawdown — M43
- Transport costs — M43
- Supply shock propagation — M43
- Route-level capacity limits — not planned (bottleneck is merchant count)

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Three category-level prices, not per-good | Perishability is what makes per-good distinction narratively meaningful, and that's M43. In M42, grain and fish are both "food that feeds people." Three categories (Food, Raw Material, Luxury) — Food aligns with existing `FOOD_TYPES`/`is_food()` plus SALT (see Categories section for details). Clean M43 upgrade path: subdivide Food category when perishability lands. |
| 2 | Pro-rata allocation on exportable surplus | Deterministic (no new RNG stream), avoids wealth-priority runaway concentration. Emergent merchant concentration comes from occupation switching (agents *choosing* to become merchants where margins are good), not from allocation mechanics favoring incumbents. |
| 3 | Abstract merchant carry (no physical relocation) | Merchants generate export flow while staying in their region. Physical movement would couple goods flow with agent migration — crossing the Python/Rust boundary. Goods economy is Python-side. |
| 4 | Three behavioral FFI signals, not raw prices | Rust shouldn't know about the goods model. It receives behavioral modifiers it can apply directly: `farmer_income_modifier`, `food_sufficiency`, `merchant_margin`. Python does economic reasoning, Rust receives behavioral inputs. |
| 5 | No stockpile in M42 | Production consumed or exported each turn. Unconsumed, unexported production vanishes. Keeps model stateless turn-to-turn. Buffers matter when there are shocks to absorb — M43's domain. |
| 6 | Module named `economy.py`, not `goods.py` | The four M41 deferred integrations are economic plumbing, not goods-specific. `economy.py` gives a coherent home for all M42 scope. |
| 7 | Demand and prices computed Python-side | Same boundary as Gini: Python reads snapshot, computes signals, sends to Rust. Per-region per-category demand/price computation is regional economic state, not per-agent behavior. |
| 8 | Single `BASE_PRICE` constant, not per-category | Category differences emerge from demand formulas — food demand is high (everyone eats) so food supply/demand ratios are lower. Luxury demand is low (only wealthy agents) so luxury prices are more volatile. One `BASE_PRICE`, three demand curves, three price behaviors. |
| 9 | `farmer_income_modifier` absorbs `is_extractive()` dispatch | M41's binary organic/extractive distinction gets absorbed into the price-derived modifier on the Python side. Extractive resources in deficit regions naturally produce higher modifiers. The two static constants (`FARMER_INCOME`, `MINER_INCOME`) collapse into `base_rate × farmer_income_modifier`. |
| 10 | Food sufficiency independent from Phase 9 famine, outside 0.40 penalty cap | Two different causes of hunger that stack. Phase 2 food sufficiency = goods-based (no farmers → no food). Phase 9 famine = ecology-based (drought, soil depletion). `food_sufficiency` is a material condition, not a social identity penalty — it stacks with war, overcrowding, and ecological penalties, all of which are outside the 0.40 non-ecological cap. The cap protects against social penalty stacking (cultural + religious + persecution + class tension). A region with no food should produce miserable agents regardless of social harmony. |
| 11 | `priest_tithe_share` on `CivSignals`, not `RegionState` | Tithes are civ-level. Duplicating across regions wastes space and creates consistency hazard if regions change hands mid-turn. Per-region behavioral modifiers go on `RegionState`, per-civ aggregate signals go on `CivSignals`. |
| 12 | Treasury tax and tithe base swap guarded by agent mode | In `--agents=off` mode, treasury tax uses existing aggregate trade income path unchanged. The merchant-wealth-based tax only activates when agents are running. Code path branch, not accumulator category change — treasury stays `keep`. |
| 13 | Two-level margin-weighted pro-rata for cross-category allocation | When exportable surplus spans multiple categories, allocate merchant capacity to categories by total margin share first, then within each category across routes by per-route margin. Deterministic, margin-maximizing. In M42, single-slot production means each region only produces one category, so Level 1 is degenerate (single category). The two-level structure exists for extensibility when secondary resource slots or M43 mechanics produce multi-category surplus. |
| 14 | Bidirectional flow per category on undirected routes | M35 trade routes are undirected. Flow direction determined per turn per category by price gradient. Same route can carry food A→B and metal B→A simultaneously. Route is the pipe, price gradient determines direction. |
| 15 | Civ-level trade routes decomposed to boundary region pairs | `get_active_trade_routes()` returns civ-level pairs. M42 decomposes each to region-level pairs at the boundary: for each civ-pair route, find all adjacent region pairs across the border. Multiple boundary pairs per route means long borders enable more trade throughput. Decomposition cached per turn (region ownership stable within a turn). |
| 16 | `merchant_margin` replaces `trade_route_count` in merchant satisfaction | The existing `(trade_route_count / 3.0).min(1.0) * 0.3` term was a placeholder based on route existence, not profitability. M42 replaces it with `merchant_margin * MERCHANT_MARGIN_WEIGHT`. M42 also retires `trade_route_count` from the merchant income formula — merchant income becomes arbitrage-driven via the carry model. The `trade_route_count` field on `RegionState` remains (other systems may reference it) but merchant economics no longer depends on it. |

---

## Goods Model

### Categories

Three category-level goods, aligned with existing `FOOD_TYPES`/`is_food()` classifications:

| Resource Type | Enum Value | Category | Demand Driver |
|---|---|---|---|
| GRAIN | 0 | Food | Population |
| TIMBER | 1 | Raw Material | Soldiers |
| BOTANICALS | 2 | Food | Population |
| FISH | 3 | Food | Population |
| SALT | 4 | Food | Population |
| ORE | 5 | Raw Material | Soldiers |
| PRECIOUS | 6 | Luxury | Wealthy agents |
| EXOTIC | 7 | Food | Population |

BOTANICALS and EXOTIC are classified as Food, matching the existing `FOOD_TYPES = frozenset({GRAIN, FISH, BOTANICALS, EXOTIC})` in `models.py` and `is_food()` in `satisfaction.rs`. SALT is also classified as Food in the M42 goods model for demand purposes — this extends beyond the existing `FOOD_TYPES`/`is_food()` definitions, which do not include SALT. The goods-level category mapping is separate from the mechanical yield-class system in `resource_class_index()` (where SALT is "Evaporite"). The original four-category design (with Special for salt) was dropped because it forced an artificial category for one resource type. Salt regions produce food-class goods that contribute to food supply and food pricing. The salt-as-preservative mechanic is M43's domain.

Luxury is PRECIOUS only (high-value durable trade goods). TIMBER and ORE are Raw Material. This asymmetry is correct — most ancient economies were food-dominated, with a small luxury trade in precious metals and a raw materials trade in timber/ore.

```python
def map_resource_to_category(resource_type: int) -> str:
    """Maps M34 resource types to three goods categories."""
    mapping = {
        0: "food",          # GRAIN
        1: "raw_material",  # TIMBER
        2: "food",          # BOTANICALS
        3: "food",          # FISH
        4: "food",          # SALT
        5: "raw_material",  # ORE
        6: "luxury",        # PRECIOUS
        7: "food",          # EXOTIC
    }
    return mapping[resource_type]
```

### Production

Per-region, determined by primary resource slot and farmer count:

```python
category = map_resource_to_category(region.resource_types[0])
production[category] = resource_yields[0] × farmer_count_in_region
```

Only farmers produce. Merchants, soldiers, scholars, priests generate no goods output. Production uses primary resource slot only (Decision 14 from M41 carries forward).

### Demand Formulas

Per-region per-category:

| Category | Formula | Notes |
|---|---|---|
| Food | `population × PER_CAPITA_FOOD` | Every agent eats |
| Raw Material | `soldier_count × RAW_MATERIAL_PER_SOLDIER` | Weapons/armor |
| Luxury | `count(wealth > LUXURY_DEMAND_THRESHOLD) × LUXURY_PER_WEALTHY_AGENT` | Per-region from M41 snapshot wealth array |

All demand computed Python-side from the previous turn's snapshot (same one-turn lag pattern as Gini).

### Price Formula

```python
supply = production + imports
demand = <category-specific formula>
price = BASE_PRICE × (demand / max(supply, 0.1))
```

Supply and demand are separate sides of the ratio — local consumption is not subtracted from supply (that would double-count demand). Consumption is a drawdown that happens after prices are set, affecting next turn's available supply through reduced production surplus.

No stockpile: production is consumed or exported each turn. Nothing carries over turn-to-turn. M43 adds stockpile buffering.

---

## Merchant Carry Model

### Abstract Flow

Merchants don't physically relocate. A merchant in region A with trade routes to B and C generates export flow from A without changing their `region` field in the agent pool. Goods economy stays entirely Python-side.

### Trade Route Decomposition

`get_active_trade_routes()` returns civ-level pairs (`list[tuple[str, str]]`). M42 decomposes these to region-level boundary pairs for price-gradient-based flow:

```python
def decompose_trade_routes(civ_a, civ_b, region_map):
    """Yield (region_a, region_b) pairs where regions are adjacent and belong to different civs."""
    for region_name in civ_a.regions:
        region = region_map[region_name]
        for neighbor_name in region.adjacency:
            if neighbor_name in civ_b_region_set:
                yield (region_name, neighbor_name)
```

Multiple boundary pairs per civ-level route is correct — a long border means more trade throughput. Merchant capacity bottleneck applies per-origin-region (merchants in region A service outbound flows from A), not per civ-level route.

Cache this decomposition per turn — region ownership doesn't change within a turn, and the trade flow computation iterates it multiple times (Decision 15).

### Capacity

Each merchant services one unit of goods flow per turn:

```
export_capacity = merchant_count_in_region × CARRY_PER_MERCHANT  [CALIBRATE: 1.0]
```

### Exportable Surplus

Local demand is served first — only true surplus flows out:

```python
exportable_surplus[category] = max(production[category] - demand[category], 0)
```

### Two-Level Pro-Rata Allocation

When exportable surplus spans multiple categories, allocation proceeds in two levels (Decision 13):

**Level 1 — Cross-category:** Allocate total merchant capacity to categories proportional to total available margin across all routes for that category:

```python
for category in categories:
    total_margin[category] = sum(
        max(dest_price[category] - origin_price[category], 0)
        for route in outbound_routes
    )
category_budget[category] = (total_margin[category] / sum(total_margin.values())) × export_capacity
```

**Level 2 — Per-route within category:** Allocate each category's merchant budget across routes by per-route margin:

```python
for route in outbound_routes:
    margin = max(dest_price[category] - origin_price[category], 0)
    route_flow[category][route] = (margin / total_margin[category]) × category_budget[category]
```

**Bounded by surplus:** Actual exports capped at exportable surplus:

```python
actual_exports[category] = min(sum(route_flow[category].values()), exportable_surplus[category])
```

No flow on negative-margin routes (`max(..., 0)` handles this). Zero total margin for a category → zero allocation to that category (no division by zero — guard with `max(sum, epsilon)`).

### Bidirectional Flow

M35 trade routes are undirected (A↔B). Flow direction computed per turn per category from price differentials. Same route can carry food A→B and metal B→A simultaneously. The route is the pipe; the price gradient determines flow direction per category (Decision 14).

### Trade Disruption

Bottleneck is merchant count in origin region, not route capacity. Trade disruption comes from:
- Losing merchants (war casualties, occupation switching away from merchant, migration)
- Losing routes (diplomatic breakdown — M35 existing mechanic)

---

## FFI Signals

### New RegionState Fields (Python → Rust)

Three floats per region, computed in Phase 2 step 2g:

| Signal | Type | Formula | Range | Purpose |
|---|---|---|---|---|
| `farmer_income_modifier` | `f32` | `clamp(demand / max(supply, 0.1), FLOOR, CAP)` for the category matching the region's primary resource | `[FLOOR, CAP]` `[CALIBRATE: 0.5, 3.0]` | Multiplies M41 base farmer income rate. Absorbs `is_extractive()` dispatch (Decision 9). |
| `food_sufficiency` | `f32` | `min(food_supply / max(food_demand, 0.1), 2.0)` | `[0.0, 2.0]` | Below 1.0 penalizes all-agent satisfaction. Outside the 0.40 non-ecological penalty cap — material condition, not social (Decision 10). Independent from Phase 9 famine. |
| `merchant_margin` | `f32` | `clamp(total_margin / max(route_count, 1) / MERCHANT_MARGIN_NORMALIZER, 0.0, 1.0)` | `[0.0, 1.0]` | Replaces `(trade_route_count / 3.0).min(1.0) * 0.3` in merchant satisfaction (Decision 16). |

**`farmer_income_modifier` detail:** The modifier is the price ratio for the region's production category. `BASE_PRICE` cancels out:

```python
category = map_resource_to_category(resource_types[0])
raw_modifier = demand[category] / max(supply[category], 0.1)
farmer_income_modifier = clamp(raw_modifier, FARMER_INCOME_MODIFIER_FLOOR, FARMER_INCOME_MODIFIER_CAP)
```

Floor prevents zero-incentive dead regions. Cap prevents extreme scarcity from creating absurd income spikes.

**`merchant_margin` detail:** Average total cross-category margin per route, normalized to 0.0–1.0:

```python
total_margin = sum(
    max(dest_price[cat] - origin_price[cat], 0)
    for route in outbound_routes
    for cat in categories
)
merchant_margin = clamp(total_margin / max(len(outbound_routes), 1) / MERCHANT_MARGIN_NORMALIZER, 0.0, 1.0)
```

`MERCHANT_MARGIN_NORMALIZER` `[CALIBRATE]` scales raw margins to bounded satisfaction input.

### Rust Wealth Accumulation Change

M41's farmer income formula changes from:

```rust
// M41 (before M42):
if is_extractive(resource_type) { MINER_INCOME × yield } else { FARMER_INCOME × yield }
```

To:

```rust
// M42:
BASE_FARMER_INCOME × farmer_income_modifier × yield
```

Single base rate × market-derived modifier. The `is_extractive()` function and separate `FARMER_INCOME`/`MINER_INCOME` constants are removed. The modifier encodes market conditions — extractive resources in deficit regions naturally produce higher modifiers than organic resources in surplus regions.

### New CivSignals Field (Python → Rust)

| Signal | Type | Scope | Persistence |
|---|---|---|---|
| `priest_tithe_share` | `f32` | Per-civ | Updated each turn (not transient) |

Computed as:

```python
tithe_base = sum(merchant_wealth for agent in civ if occupation == Merchant)
priest_tithe_share = TITHE_RATE × tithe_base / max(priest_count_in_civ, 1)
```

Priest wealth accumulation in Rust adds `priest_tithe_share` each tick:

```rust
// M42: Priest income = base + tithe share
PRIEST_INCOME + priest_tithe_share
```

### Signal Lifecycle

All M42 signals are recomputed each turn from fresh data and overwrite previous values. None are transient in the clear-before-return sense — no new transient signals in M42. The existing `conquered_this_turn` transient from M41 must continue to reset correctly after the `CivSignals` struct is modified.

### Snapshot Lag Pattern

```
Turn N Phase 10: snapshot captures farmer counts, wealth, occupations
Turn N+1 Phase 2: production uses turn N farmer counts (from snapshot)
Turn N+1 Phase 2g: signals computed from turn N+1 prices
Turn N+1 agent tick (between Phase 9 and 10): receives turn N+1 signals
```

One-turn lag on observation (snapshot inputs), same-turn delivery of signals. Same pattern as Gini (M41) and social edges (M40).

---

## M41 Deferred Integrations

Four items landing in M42. Treasury tax and per-resource pricing live in `economy.py`; tithe base swap and per-priest tithe share are computed in `economy.py` but the `compute_tithe_base()` function stays in `factions.py` (updated in place):

### 1. Treasury Tax Wiring

```python
# In compute_economy(), agent mode only:
treasury_tax[civ_idx] = TAX_RATE × sum(
    wealth for agent in civ if occupation == Merchant
)
```

Contributes to civ treasury through the accumulator as `keep`. In `--agents=off` mode, treasury tax computation continues using the existing aggregate trade income path unchanged (Decision 12). Code path branch — treasury stays `keep`, the *source* changes based on agent mode.

`TAX_RATE` is a new `[CALIBRATE]` constant (does not already exist in the codebase).

### 2. Tithe Base Swap

M38a's `compute_tithe_base(civ)` switches from `trade_income` to agent-derived merchant wealth:

```python
# Agent mode:
def compute_tithe_base(civ, snapshot) -> float:
    return sum(wealth for agent in civ if occupation == Merchant)

# --agents=off mode:
def compute_tithe_base(civ) -> float:
    return civ.trade_income  # existing path unchanged
```

`TITHE_RATE` already exists in `factions.py` (value 0.10). No duplicate.

### 3. Per-Resource Market Pricing

Already covered as the `farmer_income_modifier` FFI signal (see FFI Signals section). The price system modulates M41 base income rates through this single modifier. No separate implementation needed.

### 4. Per-Priest Tithe Share

Already covered as the `priest_tithe_share` CivSignals field (see FFI Signals section). Per-priest distribution of civ-level tithes, crossing FFI as a per-civ signal.

---

## Phase 2 Integration

### Turn Loop Placement

All goods computation runs as a sub-sequence within Phase 2, **before** existing trade income/tribute/treasury:

```
Phase 2 (Economy):
  2a. Production — farmer_count × resource_yield → output per category per region
  2b. Demand — category-specific formulas (pop, soldiers, wealthy agents)
  2c. Exportable surplus — max(production - demand, 0) per region per category
  2d. Trade flow — two-level margin-weighted pro-rata:
        Level 1: allocate merchant capacity across categories by total margin share
        Level 2: allocate each category's budget across routes by per-route margin
        Exports bounded by exportable surplus
  2e. Imports — sum inbound flows per region per category
  2f. Prices — supply (production + imports) vs demand → price per category per region
  2g. Signals — farmer_income_modifier (clamped), food_sufficiency, merchant_margin
        + priest_tithe_share on CivSignals
        + treasury_tax and tithe_base (agent mode only)
  --- existing Phase 2: trade income (agents=off path), tribute, treasury ---
```

Ordering rationale: production and consumption before you know what's tradeable. Trade flow before price update because imports change supply. Prices before FFI signals. All before existing Phase 2 treasury logic because the treasury tax wiring (M41 deferred) means treasury computation references agent-derived merchant wealth.

### Entry Point

```python
def compute_economy(
    world: WorldState,
    snapshot: RecordBatch,
    region_map: dict[str, Region],
    agent_mode: bool,
) -> EconomyResult:
    """Phase 2 goods sub-sequence: production → demand → surplus → trade → prices → signals."""
```

`simulation.py` calls `compute_economy()`, extracts results, applies to world state, passes signals to bridge.

### Data Container

```python
@dataclass
class RegionGoods:
    production: dict[str, float]    # category → output this turn
    imports: dict[str, float]       # category → inbound this turn
    exports: dict[str, float]       # category → outbound this turn
    prices: dict[str, float]        # category → current price

@dataclass
class EconomyResult:
    region_goods: dict[str, RegionGoods]       # region_name → transient goods state
    prices: dict[str, dict[str, float]]        # region_name → category → price (for analytics)
    farmer_income_modifiers: dict[str, float]   # region_name → modifier
    food_sufficiency: dict[str, float]          # region_name → sufficiency
    merchant_margins: dict[str, float]          # region_name → margin
    priest_tithe_shares: dict[int, float]       # civ_idx → share
    treasury_tax: dict[int, float]              # civ_idx → tax (agent mode only)
    tithe_base: dict[int, float]                # civ_idx → tithe base (agent mode only)
```

**`RegionGoods` is transient** — not persisted on `Region` or `WorldState`. It exists for the duration of Phase 2 processing and signal assembly. `simulation.py` extracts what it needs (signals for bridge, prices for analytics) and lets it drop. When M43 adds stockpiles, persistent economic state gets added to regions then.

Prices are included in `EconomyResult` for analytics extraction in Phase 10 (price time series are a core diagnostic for tuning).

---

## Constants

All new constants registered with `[CALIBRATE]` markers:

| Constant | Location | Initial Value | Tuning Target |
|---|---|---|---|
| `BASE_PRICE` | `economy.py` | 1.0 | Anchor for price ratios — actual prices diverge via demand curves |
| `PER_CAPITA_FOOD` | `economy.py` | TBD | Food demand at equilibrium = regional production capacity |
| `RAW_MATERIAL_PER_SOLDIER` | `economy.py` | TBD | Raw material demand proportional to military |
| `LUXURY_PER_WEALTHY_AGENT` | `economy.py` | TBD | Luxury demand from wealthy agents |
| `LUXURY_DEMAND_THRESHOLD` | `economy.py` | TBD | Around merchant equilibrium wealth from M41; successful merchants + boom farmers drive demand, subsistence farmers don't |
| `CARRY_PER_MERCHANT` | `economy.py` | 1.0 | Goods flow per merchant per turn |
| `FARMER_INCOME_MODIFIER_FLOOR` | `economy.py` | 0.5 | Prevents zero-incentive dead regions |
| `FARMER_INCOME_MODIFIER_CAP` | `economy.py` | 3.0 | Prevents extreme scarcity income spikes |
| `MERCHANT_MARGIN_NORMALIZER` | `economy.py` | TBD | Scales raw margin to 0.0–1.0 for satisfaction |
| `TAX_RATE` | `economy.py` | TBD | Treasury income from merchant wealth (agent mode) |
| `BASE_FARMER_INCOME` | `agent.rs` | TBD | Replaces `FARMER_INCOME` + `MINER_INCOME` pair from M41 |
| `FOOD_SHORTAGE_WEIGHT` | `satisfaction.rs` | 0.3 | Max food sufficiency penalty at zero supply |
| `MERCHANT_MARGIN_WEIGHT` | `satisfaction.rs` | 0.3 | Replaces old trade-route-count weight in merchant satisfaction |

**Existing constants referenced (not new):**
- `TITHE_RATE` — already in `factions.py` (0.10)
- M41 occupation income constants (except farmer — those get replaced)

### RNG Stream Offsets

No new RNG sources in M42. All allocation is deterministic (pro-rata). `GOODS_ALLOC_STREAM_OFFSET = 800` already exists in `agent.rs` — reserved but unused in M42. Remains reserved for M43 if stochastic elements are needed for perishability/supply shock mechanics.

---

## FFI Changes

### New RegionState Fields

| Field | Type | Direction |
|---|---|---|
| `farmer_income_modifier` | `f32` | Python → Rust |
| `food_sufficiency` | `f32` | Python → Rust |
| `merchant_margin` | `f32` | Python → Rust |

Added as Arrow columns in `build_region_batch()`. Not transient — overwritten each turn.

### New CivSignals Field

| Field | Type | Direction | Persistence |
|---|---|---|---|
| `priest_tithe_share` | `f32` | Python → Rust | Updated each turn (not transient) |

Added alongside existing `gini_coefficient` in `build_signals()`.

### Modified Rust Code

| File | Change |
|---|---|
| `region.rs` | Add `farmer_income_modifier`, `food_sufficiency`, `merchant_margin` to `RegionState` |
| `signals.rs` | Add `priest_tithe_share` to `CivSignals` parsing |
| `agent.rs` | Replace `FARMER_INCOME` + `MINER_INCOME` with `BASE_FARMER_INCOME`; remove `is_extractive()` |
| `tick.rs` | Farmer wealth: `BASE_FARMER_INCOME × farmer_income_modifier × yield`; Priest wealth: `PRIEST_INCOME + priest_tithe_share` |
| `satisfaction.rs` | Wire `food_sufficiency` penalty and `merchant_margin` replacement (see below) |

### Satisfaction Formula Changes

**`food_sufficiency` penalty (all agents, outside 0.40 cap):**

```rust
// Material condition penalty — stacks with war, overcrowding, ecological penalties.
// Outside the 0.40 non-ecological social penalty cap (Decision 10).
let food_penalty = if food_sufficiency < 1.0 {
    (1.0 - food_sufficiency) * FOOD_SHORTAGE_WEIGHT  // [CALIBRATE: 0.3]
} else {
    0.0
};
```

**`merchant_margin` in merchant satisfaction (replaces `trade_route_count` term):**

```rust
// M41 (before M42):
// let merchant_trade_sat = (trade_route_count as f32 / 3.0).min(1.0) * 0.3;

// M42: actual margin replaces route-count proxy
let merchant_trade_sat = merchant_margin * MERCHANT_MARGIN_WEIGHT;  // [CALIBRATE: 0.3]
```

Same weight (0.3), but driven by actual profitability instead of route existence. A merchant with three routes but no price differentials gets low satisfaction. A merchant with one route and a massive price gap gets high satisfaction.

M42 also retires `trade_route_count` from M41's merchant income formula (`MERCHANT_INCOME × (trade_routes / 3.0).min(1.0)`). Merchant income becomes arbitrage-driven via the carry model — wealth accumulation is `margin × goods_flow`, not a static rate. The `trade_route_count` field on `RegionState` remains (other systems may reference it) but merchant economics no longer depends on it.

### Regression Guard

Adding `priest_tithe_share` to `CivSignals` must not break `conquered_this_turn` transient reset. Include regression assertion in existing M41 transient signal test.

---

## Analytics & Narration

### Analytics Extractors (Python-side, in `analytics.py`)

- Per-region per-category price time series
- Per-region production/imports/exports per category per turn
- Per-civ aggregate trade volume (total exports across regions)
- Price spread: max(price) - min(price) across regions for each category (trade efficiency diagnostic)

All computed from `EconomyResult.prices` during Phase 10 analytics extraction.

### Narration Context

- Regional price data available in narration context (food prices spike → famine narrative)
- Trade flow data available for trade route narratives
- `food_sufficiency` available for hunger/prosperity narratives

### Bundle

No new top-level bundle fields. Price and trade data included in existing analytics data structures.

---

## Testing

### Unit Tests (Python)

- `map_resource_to_category` returns correct category for all 8 resource types (aligned with `FOOD_TYPES`/`is_food()`)
- Production formula: `farmer_count × yield` for matching category, zero for non-matching
- Demand formulas: correct values for known population/soldier/wealth/production inputs
- Price formula: `BASE_PRICE × (demand / max(supply, 0.1))` — verify surplus regions produce lower prices
- Pro-rata allocation: margin-weighted split sums to total capacity
- Two-level allocation: cross-category then per-route, bounded by exportable surplus
- No flow on negative-margin routes
- Signal clamping: `farmer_income_modifier` within `[FLOOR, CAP]`, `food_sufficiency` within `[0.0, 2.0]`, `merchant_margin` within `[0.0, 1.0]`
- No NaN, no infinity in any computed value
- Treasury tax and tithe base: correct values in agent mode, unchanged in `--agents=off`

### Conservation Law

```
for each category:
    sum(production) == sum(local_consumption) + sum(exports_delivered) + sum(unconsumed_waste)
```

Where unconsumed waste = surplus that couldn't be exported (no merchants, no routes, no margin). Total goods in system = total produced. No goods from nothing, no silent loss.

### Integration Tests

- **Price responsiveness:** Create two regions — high farmer count + low population (surplus) vs low farmer count + high population (deficit). Assert `price_surplus < price_deficit` for the same category.
- **Merchant behavior:** Multi-turn simulation. Verify merchant wealth accumulation correlates with route margin (merchants on high-margin routes gain more wealth).
- **Occupation response:** Engineer food deficit scenario. Verify farmer count increases over next 2-3 turns via occupation switching.
- **Bidirectional flow:** Two connected regions, one producing food and one producing raw materials. Verify food flows one direction and raw materials flow the other on the same route.
- **`--agents=off` invariance:** Phase 2 treasury computation unchanged when agents disabled. Existing aggregate path produces identical results to pre-M42 baseline.
- **`conquered_this_turn` regression:** Existing M41 transient signal test continues passing after `CivSignals` struct modification.
- **Food sufficiency / famine independence:** Region with good ecology but no farmers → low `food_sufficiency`, no Phase 9 famine trigger. Region with drought but many farmers → Phase 9 famine, but `food_sufficiency` may still be adequate.

### Tier 2 Regression (200-seed)

200-seed before/after comparison in `--agents=hybrid` mode. Key metrics:

- **Satisfaction distribution** — food sufficiency penalty is new; verify it doesn't crater satisfaction across the board
- **Wealth distribution shape** — `farmer_income_modifier` changes M41 wealth accumulation; verify Gini stays in reasonable range
- **Occupation distribution** — occupation switching responds to prices; verify no degenerate all-farmer or all-merchant outcomes
- **Rebellion and loyalty rates** — satisfaction changes propagate here; verify no regression
- **Treasury levels** — agent-mode tax wiring changes treasury income source; verify levels stay comparable

---

## File Impact

| File | Changes |
|---|---|
| `src/chronicler/economy.py` | **New file.** `compute_economy()`, `RegionGoods`, `EconomyResult`, all production/demand/price/flow/signal computation, M41 deferred integrations |
| `src/chronicler/simulation.py` | Phase 2: call `compute_economy()`, apply results, pass signals to bridge |
| `src/chronicler/agent_bridge.py` | Add `farmer_income_modifier`, `food_sufficiency`, `merchant_margin` to `build_region_batch()`; add `priest_tithe_share` to `build_signals()` |
| `src/chronicler/factions.py` | Update `compute_tithe_base()` to accept snapshot and use agent-derived merchant wealth in agent mode |
| `src/chronicler/analytics.py` | Price time series extractors, trade volume diagnostics |
| `chronicler-agents/src/region.rs` | Add `farmer_income_modifier`, `food_sufficiency`, `merchant_margin` to `RegionState` |
| `chronicler-agents/src/signals.rs` | Add `priest_tithe_share` to `CivSignals` |
| `chronicler-agents/src/agent.rs` | Replace `FARMER_INCOME` + `MINER_INCOME` with `BASE_FARMER_INCOME`; remove `is_extractive()` |
| `chronicler-agents/src/tick.rs` | Farmer income: `BASE_FARMER_INCOME × modifier × yield`; Priest income: `base + tithe_share` |
| `chronicler-agents/src/satisfaction.rs` | Add `food_sufficiency` penalty outside 0.40 cap; replace `trade_route_count` term with `merchant_margin * MERCHANT_MARGIN_WEIGHT` in merchant satisfaction |
