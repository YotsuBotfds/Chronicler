# M41: Wealth & Class Stratification — Design Spec

> **Status:** Draft
>
> **Author:** Cici (Opus 4.6)
>
> **Reviewed by:** Tate (design decisions), Phoebe (spec review — S-1 through N-1 resolved)
>
> **Depends on:** M34 (Resources & Seasons), M36 (Cultural Identity), M37 (Belief), M38a (Temples & Clergy), M38b (Schisms & Persecution), M39 (Family & Lineage), M40 (Social Networks)
>
> **Prerequisites landed:** M34, M36, M37, M38a, M38b, M39, M40 all merged

---

## Goal

Add per-agent wealth accumulation driven by occupation and resource context, producing emergent class stratification via Gini coefficient and a per-agent class tension satisfaction penalty. Wealth is an agent-level property — it does not affect civ-level treasury or economy in M41.

## Scope

**In scope:**
- Per-agent `wealth` field in Rust SoA pool
- Occupation-specific accumulation with resource dispatch (organic vs extractive)
- Multiplicative wealth decay
- Per-civ Gini coefficient computed Python-side
- Per-agent class tension penalty in satisfaction formula
- Conquest bonus for soldiers
- Analytics and narration exposure

**Out of scope (deferred):**
- Market dynamics, supply/demand pricing — M42
- Treasury integration (`TAX_RATE × sum(merchant_wealth)`) — M42
- Tithe base swap (`compute_tithe_base` stays on `trade_income`) — M42
- Rebellion utility boost in `behavior.rs` — follow-up if indirect path proves insufficient
- Wealth inheritance at death — future mechanic (M39/M41 intersection)

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | M41 scoped to wealth + class stratification; market dynamics in M42 | Wealth accumulation needs stable base rates before market pricing modulates them. Designing both simultaneously creates tuning conflicts. |
| 2 | 0.40 non-ecological satisfaction cap unchanged; class tension is 4th term | Existing terms (cultural 0.15, religious 0.10, persecution 0.15) rarely saturate the budget — typical combined penalty is 0.15-0.28. Class tension takes remaining headroom naturally. |
| 3 | Priority clamping: three core terms first, class tension takes remainder | Cultural + religious + persecution computed first; class tension clamped to `(PENALTY_CAP - three_term_sum).max(0.0)`. When cap binds, class tension is eaten first — core identity/persecution penalties are never reduced by wealth effects. No proportional scaling. |
| 4 | Per-agent class tension, not uniform per-civ | The thesis of Phase 6 is agents as individuals. A uniform penalty makes per-agent wealth pointless for satisfaction. Poor agents feel inequality; rich agents don't. |
| 5 | Gini computed Python-side, penalty computed Rust-side | Python reads wealth from snapshot, computes Gini (numpy sort, trivial). Sends per-civ `gini_coefficient` signal. Rust computes per-agent penalty from pool wealth data — avoids round-tripping percentile weights across FFI. |
| 6 | Binary resource dispatch: organic vs extractive (two rates) | `FARMER_INCOME` for organic (crops, timber), `MINER_INCOME` for extractive (ore, precious). No per-resource-type rates — that's M42 granularity. Boom-bust emerges from yield depletion curve × higher miner rate. |
| 7 | Multiplicative decay, not additive | `wealth *= (1.0 - WEALTH_DECAY)`. Preserves relative distribution shape. Additive creates a hard poverty trap where low-income agents clamp to zero. Multiplicative gives each occupation a nonzero equilibrium at `income / WEALTH_DECAY` — directly tunable. |
| 8 | Born at `STARTING_WEALTH`, death wealth vanishes | `STARTING_WEALTH` represents baseline subsistence — not born into vacuum. Zero-wealth newborns would spike class tension during demographic booms (conflates "new generation" with "poverty crisis"). No inheritance in M41. |
| 9 | Satisfaction penalty only, no rebellion utility boost | Low satisfaction → loyalty erosion → rebellion via existing M32-M38 calibrated mechanics. Direct utility boost in `behavior.rs` short-circuits the layered architecture. Follow-up if indirect path proves insufficient. |
| 10 | No treasury integration in M41 | Treasury stays "keep" category. Wiring tax on merchant wealth makes treasury partially agent-derived, breaking `--agents=off` invariant for no narrative payoff without the M42 market system to give it meaning. |
| 11 | Priest tithe deferred to M42 | Per-priest tithe share requires a distribution model that doesn't exist yet. `compute_tithe_base` placeholder stays on `trade_income`. |
| 12 | Linear rank-to-weight mapping | `f(percentile) = 1.0 - percentile`. Simplest to implement, easiest to tune. Gini already captures distributional shape. Nonlinear mapping adds a second interacting curve to calibrate — unnecessary for M41. |
| 13 | Conquest bonus is part of wealth accumulation, not a separate phase | Applied during the accumulation step alongside occupation income. Not a separate mini-phase in the tick. |
| 14 | Income dispatches on primary resource slot only | Farmer/miner income uses `resource_yields[0]` and `resource_types[0]`. Secondary/tertiary resource slots are ignored for wealth purposes. A region with GRAIN in slot 0 and ORE in slot 1 pays farmers at the organic rate. |
| 15 | One-turn Gini lag is intentional | Python computes Gini from turn N snapshot; Rust uses it in turn N+1 satisfaction. On turn 1, Gini defaults to 0.0 (no class tension when all agents have identical starting wealth). Same one-turn latency pattern as M38b schism delay and M40 social edges. |
| 16 | Wealth tick runs before decisions | Agents earn income from their current occupation, then may switch occupation in the decision phase. Income is based on occupation at start of tick. |
| 17 | Merchant income uses temporary baseline, not trade_routes | `build_region_batch()` sends hardcoded zeros for `trade_route_count` (code health issue). Merchant formula becomes `MERCHANT_INCOME × MERCHANT_BASELINE` where `MERCHANT_BASELINE = 0.5` `[CALIBRATE]`. M42 replaces with real market-driven income. |
| 18 | `conquered_this_turn` stored as dict in simulation.py | Transient per-turn dict keyed by civ index, assembled during Phase 8 action resolution, passed to `agent_bridge.build_civ_signals()`. Not stored on civ model — it's transient per-turn data, not civ state. |

---

## Storage

### New SoA Field

```rust
// pool.rs
pub wealth: Vec<f32>,
```

- Initial value: `STARTING_WEALTH` `[CALIBRATE: 0.5]`
- Clamped to `[0.0, MAX_WEALTH]` `[CALIBRATE: MAX_WEALTH = 100.0]`
- Per-agent cost: 4 bytes (pool size ~68 → ~72 bytes per agent)
- Exposed via Arrow column in snapshot RecordBatch

### Scratch Vector

```rust
// Reusable per-tick temporary in AgentSimulator
pub wealth_percentiles: Vec<f32>,
```

Indexed by pool slot. Sized to `pool.capacity()` (includes dead slots). Only slots processed in the per-civ rank pass have valid values — dead slots contain undefined data. Allocated once, reused across ticks. Populated during per-civ rank computation, consumed by satisfaction in the same tick.

---

## Wealth Accumulation

### Tick Ordering

Within the Rust agent tick, wealth processing runs as a four-step sequence:

1. **Accumulation** — income by occupation + conquest bonus
2. **Decay** — multiplicative: `wealth *= (1.0 - WEALTH_DECAY)`
3. **Per-civ rank** — temp index, sort, write percentiles to scratch vector
4. **Satisfaction** — consumes percentiles + Gini signal from Python

### Occupation Income

All rates are `[CALIBRATE]` constants in `agent.rs`.

| Occupation | Formula | Inputs |
|---|---|---|
| Farmer (organic) | `FARMER_INCOME × resource_yields[0]` | RegionState `resource_types[0]` not extractive (primary slot only — Decision 14) |
| Farmer (extractive) | `MINER_INCOME × resource_yields[0]` | RegionState `resource_types[0]` is extractive (ORE or PRECIOUS) |
| Soldier | `SOLDIER_INCOME × (1.0 + AT_WAR_BONUS × at_war) + CONQUEST_BONUS × conquered_this_turn` | `civ_at_war` flag (existing), `conquered_this_turn` per-civ signal (new) |
| Merchant | `MERCHANT_INCOME × MERCHANT_BASELINE` | Temporary constant (Decision 17) — `trade_routes` is hardcoded zero in region batch. M42 replaces with real market income. |
| Scholar | `SCHOLAR_INCOME` | None |
| Priest | `PRIEST_INCOME` | None |

### Resource Type Dispatch

Binary check — two categories:

```rust
/// ORE=5, PRECIOUS=6 are extractive; all others are organic.
fn is_extractive(resource_type: u8) -> bool {
    resource_type == 5 || resource_type == 6
}
```

All other resource types (GRAIN=0, TIMBER=1, BOTANICALS=2, FISH=3, SALT=4, EXOTIC=7) use `FARMER_INCOME`.

### Decay

```rust
agent.wealth *= 1.0 - WEALTH_DECAY;  // [CALIBRATE: 0.02]
agent.wealth = agent.wealth.clamp(0.0, MAX_WEALTH);
```

Multiplicative decay. Per-occupation equilibrium wealth at `income / WEALTH_DECAY`. One multiply per agent, branchless.

### Birth and Death

- **Birth:** New agents (including M39 birth path) initialize at `STARTING_WEALTH`.
- **Death:** Wealth is implicitly reclaimed when the agent slot is freed. No inheritance mechanic — wealth vanishes. Future mechanic if dynasties need economic continuity.

---

## Conquest Bonus Signal

Soldier wealth accumulation includes a one-shot `CONQUEST_BONUS` when the agent's civ conquered territory this turn.

### Signal Path

- Action engine resolves EXPAND/WAR actions → conquest occurs → Python sets `conquered_this_turn` per civ (in `action_engine.py`, not accumulator — this is a boolean event flag, not a stat delta)
- Stored as a transient `dict[int, bool]` in `simulation.py` keyed by civ index (Decision 18). Assembled during Phase 8, passed to `agent_bridge.build_civ_signals()`. Not stored on the civ model.
- Crosses FFI as a per-civ boolean in the existing `CivSignals` struct (or equivalent)
- Rust reads during wealth accumulation step: `CONQUEST_BONUS × conquered_this_turn as i32 as f32`

### Transient Signal Rule

Per CLAUDE.md: `conquered_this_turn` is a one-turn flag. Must be cleared BEFORE the return in the builder function. Requires a 2+ turn integration test verifying the value resets after consumption.

---

## Gini Coefficient

### Computation (Python-side)

After the Rust tick produces a wealth snapshot:

1. Read `wealth` column from snapshot RecordBatch
2. Group by civ affinity
3. Per civ: sort wealth values, compute Gini via the standard formula:

```python
def compute_gini(wealth_array: np.ndarray) -> float:
    """Gini coefficient from a 1D array of non-negative values."""
    sorted_w = np.sort(wealth_array)
    n = len(sorted_w)
    if n == 0 or sorted_w.sum() == 0:
        return 0.0
    index = np.arange(1, n + 1)
    return (2.0 * (index * sorted_w).sum() / (n * sorted_w.sum())) - (n + 1) / n
```

4. Send `gini_coefficient` per civ as a civ-level signal to Rust via the existing signal path

### Signal Routing

Gini is sent as a new field on the per-civ signals struct — not a shock signal (it's not a transient event, it's a persistent metric). It persists until updated next turn.

### Timing

One-turn lag (Decision 15): Python computes Gini from turn N snapshot; Rust uses it in turn N+1 satisfaction. On turn 1, Gini defaults to 0.0 (no class tension when all agents have identical starting wealth). Same pattern as M38b schism delay and M40 social edge latency.

### Civ Affinity Grouping

Snapshot column `civ_affinity` is `UInt16` (pool stores `u8`, cast to `u16` in `ffi.rs`). Python groups by this column when computing per-civ Gini. The resulting Gini values are indexed by civ index (`u8`) when sent back as signals. Implementation must handle the `u16 → u8` cast at the grouping boundary.

---

## Class Tension Penalty

### Per-Civ Rank Computation (Rust-side)

Runs after wealth accumulation and decay, before satisfaction:

```rust
// Per-civ: collect (slot_index, wealth) for alive agents in this civ
let mut civ_agents: Vec<(u32, f32)> = Vec::new();
// ... populate from pool ...

// Sort ascending by wealth — total_cmp gives deterministic ordering, no panic on NaN
civ_agents.sort_by(|a, b| a.1.total_cmp(&b.1));

// Assign percentiles to scratch vector
// (count - 1).max(1) ensures: poorest = 0.0, richest = 1.0 (zero penalty)
// Single-agent civ: 0/1 = 0.0, but Gini is also 0.0, so penalty is zero.
let denom = (civ_agents.len() as f32 - 1.0).max(1.0);
for (rank, (slot, _wealth)) in civ_agents.iter().enumerate() {
    wealth_percentiles[*slot as usize] = rank as f32 / denom;
}
```

Temp vector allocated once per `AgentSimulator`, reused across ticks. At ~1K agents per civ, the sort is sub-microsecond.

### Satisfaction Integration

In `compute_satisfaction_with_culture`, class tension becomes the 4th non-ecological penalty term:

```rust
let class_tension_pen = gini_coefficient
    * (1.0 - wealth_percentiles[slot])
    * CLASS_TENSION_WEIGHT;  // [CALIBRATE: 0.15]

// Priority clamping: core identity/persecution penalties first,
// class tension takes whatever budget remains (Decision 3).
let three_term = cultural_pen + religious_pen + persecution_pen;
let class_tension_clamped = class_tension_pen.min((PENALTY_CAP - three_term).max(0.0));
// Safety cap: total never exceeds PENALTY_CAP even if core terms are retuned.
let total_non_eco_penalty = (three_term + class_tension_clamped).min(PENALTY_CAP);
```

- `gini_coefficient`: per-civ signal from Python (0.0 = perfect equality, 1.0 = one agent owns everything)
- `wealth_percentiles[slot]`: agent's position in civ wealth distribution (0.0 = poorest, 1.0 = richest)
- Linear mapping: poorest agent at Gini 0.6 → `0.6 × 1.0 × 0.15 = 0.09` penalty
- Richest agent at any Gini → `gini × 0.0 × 0.15 = 0.00` penalty
- Priority ordering: when cap binds, class tension is reduced first — cultural, religious, and persecution penalties are never diminished by wealth effects

### Penalty Budget Analysis

Worst-case stacking with all four terms at maximum:

| Term | Max | Typical |
|---|---|---|
| Cultural mismatch | 0.15 | 0.05-0.10 |
| Religious mismatch | 0.10 | 0.10 (binary) |
| Persecution | 0.15 | 0.00-0.08 |
| Class tension | 0.15 | 0.00-0.09 |
| **Sum** | **0.55** | **0.15-0.37** |
| **After cap** | **0.40** | **0.15-0.37** |

The cap binds only in extreme scenarios (full cultural mismatch + wrong belief + active persecution + impoverished in high-inequality civ). This is correct — that agent *should* be maximally unhappy, and the cap prevents satisfaction from going unreasonably negative.

---

## Constants

All constants registered in `agent.rs` with `[CALIBRATE]` markers:

| Constant | Initial Value | Tuning Target |
|---|---|---|
| `STARTING_WEALTH` | 0.5 | Wealth distribution shape at turn 500 (log-normal-ish) |
| `MAX_WEALTH` | 100.0 | Prevents runaway accumulation |
| `WEALTH_DECAY` | 0.02 | Per-occupation equilibrium: `income / 0.02` |
| `FARMER_INCOME` | TBD | Equilibrium ~10-20 (subsistence) |
| `MINER_INCOME` | TBD | Equilibrium ~25-50 (boom potential, yield-dependent) |
| `SOLDIER_INCOME` | TBD | Equilibrium ~5-15 (low peacetime, spikes in war) |
| `AT_WAR_BONUS` | TBD | Multiplier on soldier income during war |
| `CONQUEST_BONUS` | TBD | One-shot wealth gain on conquest |
| `MERCHANT_INCOME` | TBD | Equilibrium ~15-40 (with baseline, M42 replaces) |
| `MERCHANT_BASELINE` | 0.5 | Temporary constant — fraction of max merchant rate. M42 replaces with real market income. |
| `SCHOLAR_INCOME` | TBD | Equilibrium ~8-12 (flat, institutional) |
| `PRIEST_INCOME` | TBD | Equilibrium ~8-12 (flat, M42 adds tithe) |
| `CLASS_TENSION_WEIGHT` | 0.15 | Max class tension penalty for poorest agent at Gini 1.0 |

### RNG Stream Offsets

No new RNG sources in M41. Wealth accumulation is deterministic (income formula + decay). No random component.

---

## FFI Changes

### New Arrow Columns (snapshot → Python)

| Column | Type | Direction |
|---|---|---|
| `wealth` | `f32` | Rust → Python (snapshot) |

### New Signal Fields (Python → Rust)

| Signal | Type | Scope | Persistence |
|---|---|---|---|
| `gini_coefficient` | `f32` | Per-civ | Updated each turn (not transient) |
| `conquered_this_turn` | `bool` | Per-civ | **Transient** — cleared before return |

### Modified Structs

- `CivSignals` (or equivalent): add `gini_coefficient: f32` and `conquered_this_turn: bool`
- `compute_satisfaction_with_culture`: new parameters `gini_coefficient: f32`, `wealth_percentile: f32`

---

## Analytics & Narration

### Analytics Extractors (Python-side, in `analytics.py`)

- Per-civ Gini coefficient time series
- Per-civ mean/median/std wealth
- Per-civ wealth by occupation breakdown (farmer, soldier, merchant, scholar, priest)
- Per-civ wealth histogram (bucket distribution)

All computed from the snapshot RecordBatch in Python post-processing. Not included in `get_aggregates()` — wealth is agent-only data, not a civ-level aggregate.

### Narration Context

- Gini coefficient available in `AgentContext` for moment narration
- Wealth percentile available for named characters

### Bundle

No new top-level bundle fields. Gini and wealth stats included in existing analytics data structures.

---

## Testing

### Unit Tests (Rust)

- Wealth accumulation produces correct income per occupation
- Resource dispatch: extractive region → `MINER_INCOME`, organic → `FARMER_INCOME`
- Multiplicative decay: `wealth_after = wealth_before × (1.0 - WEALTH_DECAY)`
- Wealth clamped to `[0.0, MAX_WEALTH]`
- Newborn agents start at `STARTING_WEALTH`
- Per-civ rank computation: correct percentiles for known distributions
- Class tension penalty: poor agent at high Gini > rich agent at high Gini
- Class tension respects 0.40 penalty cap
- Conquest bonus applied only when `conquered_this_turn` is true

### Integration Tests

- **Transient signal:** `conquered_this_turn` resets after one tick (2+ turn test)
- **Distribution shape:** At turn 500, wealth distribution is not degenerate (not all agents at same value)
- **Gini bounds:** Gini coefficient stays in 0.3-0.7 range across civs (not stuck at 0 or 1)
- **Extractive boom-bust:** Region with mineral resources shows wealth spike then decline as yield depletes
- **`--agents=off` invariant:** Output is identical with and without wealth system (wealth is agent-only, no civ-level effects)

### Tier 2 Regression

- 200-seed before/after comparison
- Key metrics: satisfaction distribution, loyalty, rebellion rate, Gini spread
- No regression in existing M32-M38 calibrated behaviors

---

## File Impact

| File | Changes |
|---|---|
| `chronicler-agents/src/pool.rs` | Add `wealth: Vec<f32>` SoA field |
| `chronicler-agents/src/agent.rs` | Wealth constants, `is_extractive()` helper |
| `chronicler-agents/src/tick.rs` | Wealth accumulation, decay, rank computation phases |
| `chronicler-agents/src/satisfaction.rs` | `class_tension_pen` term in `compute_satisfaction_with_culture` |
| `chronicler-agents/src/signals.rs` | `gini_coefficient` and `conquered_this_turn` on CivSignals |
| `chronicler-agents/src/ffi.rs` | Expose `wealth` in Arrow snapshot, accept new signals |
| `src/chronicler/simulation.py` | Gini computation from snapshot, signal routing, `conquered_this_turn` dict assembly and passthrough |
| `src/chronicler/action_engine.py` | Set `conquered_this_turn` flag on civ when conquest occurs |
| `src/chronicler/analytics.py` | Wealth distribution extractors |
| `src/chronicler/narrative.py` | Gini in AgentContext |
| `src/chronicler/agent_bridge.py` | Pass Gini and conquest signals to Rust |
