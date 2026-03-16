# M32: Utility-Based Decision Model

> **Status:** Design approved. Ready for implementation planning.
>
> **Depends on:** Phase 5 complete (M25-M30 landed). No blocking dependencies.
>
> **Scope:** Replace the short-circuit decision priority in `behavior.rs` with weighted utility selection. ~365 lines Rust, 0 Python.

---

## Overview

Phase 5 agents evaluate decisions in priority order (rebel > migrate > switch > loyalty drift). The first triggered decision executes; the rest are skipped. This short-circuit model creates artificial priority — a farmer at both the rebellion and migration thresholds always rebels, never migrates, even if migration is the more rational choice.

M32 replaces short-circuit with utility-based selection: each action computes a continuous utility score, the agent picks the highest-utility action with Gumbel noise. Relative urgency determines behavior instead of hard priority.

**Backward compatibility:** The short-circuit model is the degenerate case of utility selection. With extreme weights and temperature 0, the utility model reproduces Phase 5 behavior exactly. A structural regression test verifies this.

---

## Design Decisions

### Loyalty Drift Is a Background Process, Not a Utility Action

Rebel, migrate, and switch occupation are mutually exclusive one-shot actions. Loyalty drift is a continuous float adjustment that happens alongside staying put. In Phase 5, drift runs for every agent in a multi-civ region unless a dramatic action (rebel/migrate/switch) fired first.

Making drift compete with other actions in utility selection would break cultural assimilation: happy agents in mixed-civ regions would always pick "stay" over "drift," preventing the gradual loyalty convergence that produces Phase 5's assimilation dynamics.

**Decision:** Utility selection governs `[rebel, migrate, switch, stay]`. Loyalty drift/recovery runs unconditionally after the selected action, using the same logic as Phase 5 (`behavior.rs` lines 276-309). Skipped only if the agent rebelled this tick (rebellion is the most extreme loyalty statement).

### ReLU+Saturation Utility Shape

Each utility function uses threshold-gated linear activation with a saturation cap:

```
utility = min(CAP, max(0, weighted_sum_of_inputs))
```

Three regimes:
1. **Above threshold:** utility = 0. No action considered. Hard floor preserved from Phase 5.
2. **Below threshold:** utility rises linearly. Relative urgency matters. More extreme agents act first when temperature is moderate.
3. **Deep below threshold:** utility saturates at CAP. All eligible agents have similar utility — approximates Phase 5's all-or-nothing behavior. This is what makes the structural regression test pass.

**Why not pure linear (no threshold):** An agent at satisfaction 0.7 would get nonzero rebel utility. Gumbel noise would occasionally push it over stay — producing incoherent rebellions from content agents that the LLM must narrate.

**Why not sigmoid:** Equivalent three-regime shape but with two extra parameters per action (midpoint, steepness). The ReLU+cap is branchless (`min(cap, max(0, linear))` = two instructions), transparent (every parameter has direct physical meaning), and calibration-friendly. Sigmoid is an M47 escape hatch if the sharp knee creates artifacts.

### Pre-Computed Migration Opportunity

Phase 5 conflates two concerns in the adjacency scan: "how attractive is migration?" (scalar) and "where should I go?" (region ID). The utility model separates them:

- **`migration_opportunity`** (per-region scalar): best adjacent mean satisfaction minus own mean satisfaction, clamped >= 0. Pre-computed in `RegionStats` during `compute_region_stats()`. O(regions x 32), trivial.
- **`best_migration_target`** (per-region ID): which adjacent region has the best mean satisfaction. Looked up only when an agent actually chose migration — not during utility evaluation.

The utility function is purely functional: `(satisfaction, opportunity) -> f32`. No scan, no side-effect.

**Forward compatibility:** M33 personality affects target selection (bold agents prefer contested regions), not opportunity magnitude. M33 re-ranks the small set of adjacent regions per-agent at decision-execution time, not utility-evaluation time. M34 extends opportunity to per-occupation scores. Neither invalidates the pre-computation pattern.

### Single Global Temperature

One `DECISION_TEMPERATURE` constant governs Gumbel noise for all actions. The CAP values implicitly control per-action noise sensitivity:

| Action | Cap / STAY_BASE | Noise Sensitivity | Behavioral Meaning |
|--------|----------------|-------------------|-------------------|
| Rebel | ~3.0x | Low — near-deterministic | Crisis response: when conditions are terrible, rebellion is near-certain |
| Migrate | ~2.0x | Moderate | Bad conditions strongly push migration, but not all agents flee |
| Switch | ~1.2x | High — frequently contested | Oversupply nudges switching, but many resist inertia |
| Stay | 1.0x (baseline) | Reference point | — |

This hierarchy maps directly to the deliberateness of each decision. Rebellion is a crisis response; occupation switching is an optimization. A single temperature produces this for free through the CAP ratios.

**Why not per-action temperature:** With 4 temperatures + 4 CAPs + weights + STAY_BASE, you get ~17 free parameters with non-obvious interactions. Doubling `REBEL_TEMP` has the same effect as halving `REBEL_CAP`. M47 already has 25+ constants to tune — adding redundant degrees of freedom guarantees wasted calibration iterations. Per-action temperature is reserved as an M47 escape hatch only if needed.

### Three-Tier Calibration Hierarchy

Documented in constants for M47 tuning:

1. **CAP ratios** — coarse-grained. Adjust relative priority between actions. Touch first.
2. **DECISION_TEMPERATURE** — medium-grained. Global exploration vs. exploitation. One knob, uniform effect.
3. **Utility weights** — fine-grained. Adjust gradient steepness within the ReLU active region. Touch last.

---

## Utility Functions

### Rebel

```rust
fn rebel_utility(loyalty: f32, satisfaction: f32, rebel_eligible: usize) -> f32 {
    let raw = W_REBEL * (max(0.0, REBEL_LOYALTY_THRESHOLD - loyalty)
                       + max(0.0, REBEL_SATISFACTION_THRESHOLD - satisfaction));
    min(REBEL_CAP, raw) * smoothstep(rebel_eligible, REBEL_MIN_COHORT - 2, REBEL_MIN_COHORT + 3)
}
```

- Zero when loyalty > threshold AND satisfaction > threshold. If only one dimension is below threshold, the agent still gets partial rebel utility from that dimension — an agent with terrible satisfaction but acceptable loyalty is not fully content.
- Linear rise below thresholds. Saturates at `REBEL_CAP`.
- Smoothstep cohort gate replaces Phase 5's hard `>= 5` cutoff. Effectively zero below 3 agents, full weight above 8.

### Migrate

```rust
fn migrate_utility(satisfaction: f32, migration_opportunity: f32) -> f32 {
    let raw = W_MIGRATE_SAT * max(0.0, MIGRATE_SATISFACTION_THRESHOLD - satisfaction)
            + W_MIGRATE_OPP * max(0.0, migration_opportunity - MIGRATE_HYSTERESIS);
    min(MIGRATE_CAP, raw)
}
```

- `migration_opportunity` pre-computed in `RegionStats`. Zero if no adjacent region is better.
- `MIGRATE_HYSTERESIS` (0.05) prevents oscillation — same as Phase 5's `+ 0.05` delta requirement.

### Switch Occupation

```rust
fn switch_utility(
    occ: usize, supply: &[usize; 5], demand: &[f32; 5],
) -> (f32, u8) {
    let own_supply = supply[occ] as f32;
    let own_demand = demand[occ].max(0.01);
    let oversupply = max(0.0, own_supply / own_demand - SWITCH_OVERSUPPLY_THRESH);

    let mut best_alt: u8 = occ as u8;
    let mut best_gap: f32 = 0.0;
    for alt in 0..OCCUPATION_COUNT {
        if alt == occ { continue; }
        let alt_supply = supply[alt] as f32;
        let alt_demand = demand[alt];
        let gap = max(0.0, alt_demand - alt_supply * SWITCH_UNDERSUPPLY_FACTOR);
        if gap > best_gap {
            best_gap = gap;
            best_alt = alt as u8;
        }
    }

    let utility = min(SWITCH_CAP, W_SWITCH * oversupply * best_gap);
    (utility, best_alt)
}
```

- **Multiplicative coupling:** `oversupply * undersupply_gap`. Zero when either term is zero — the AND gate from Phase 5 falls out naturally. No point switching away from an oversupplied role if there's nowhere useful to go.
- Returns `(utility, best_alternative_occupation)` tuple. Target captured during the O(4) scan — no redundant scan in the execution path.
- Per-agent: different agents have different current occupations, so utility varies per-agent within the same region (unlike migration, which is per-region).
- **Note:** The undersupply gap formula uses `alt_demand - alt_supply * SWITCH_UNDERSUPPLY_FACTOR` (factor-adjusted), while Phase 5 ranks alternatives by `alt_demand - alt_supply` (raw gap). Both have the same zero-crossing, but ranking among multiple undersupplied alternatives may differ. This is an intentional improvement — factor-adjusted gap is more meaningful for utility scaling.

### Stay

```rust
fn stay_utility() -> f32 {
    STAY_BASE
}
```

Constant inertia. At low temperature, any action with utility > `STAY_BASE` wins deterministically. At moderate temperature, Gumbel noise can push stay above weak action utilities.

---

## Selection Mechanism

### Gumbel Argmax

```rust
fn gumbel_argmax(utilities: &[f32], rng: &mut ChaCha8Rng, temperature: f32) -> usize {
    if temperature <= 0.0 {
        // Deterministic argmax — regression test path
        return utilities.iter().enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(i, _)| i)
            .unwrap_or(0);
    }

    let mut best_idx = 0;
    let mut best_val = f32::NEG_INFINITY;
    for (i, &u) in utilities.iter().enumerate() {
        let uniform = rng.gen::<f32>().max(f32::EPSILON); // guard U=0.0
        let gumbel = -temperature * (-uniform.ln()).ln();
        let perturbed = u + gumbel;
        if perturbed > best_val {
            best_val = perturbed;
            best_idx = i;
        }
    }
    best_idx
}
```

- Gumbel(0, beta) noise: `-beta * ln(-ln(U))` where U ~ Uniform(0,1). Equivalent to softmax sampling with temperature beta.
- **T=0 fast path:** Avoids `0.0 * -inf = NaN` from IEEE 754. Explicit deterministic argmax with `partial_cmp` for f32 ordering.
- **`f32::EPSILON` clamp:** Guards against `U=0.0` (probability ~2^-24) which produces `ln(0) = -inf`. Costs nothing, eliminates the edge case.
- **RNG draw count:** When T>0, each call consumes exactly 4 RNG draws (one per action). When T<=0, the deterministic fast path consumes zero draws (early return before the loop). Reproducibility is guaranteed within a given temperature setting — not across temperature changes. Agents are processed by slot index within each region for deterministic ordering.

### Smoothstep Helper

```rust
fn smoothstep(x: usize, edge0: usize, edge1: usize) -> f32 {
    if x <= edge0 { return 0.0; }
    if x >= edge1 { return 1.0; }
    let t = (x - edge0) as f32 / (edge1 - edge0) as f32;
    t * t * (3.0 - 2.0 * t)
}
```

Used for rebel cohort gate. Smooth S-curve from 0 to 1 between `edge0` and `edge1`.

---

## RegionStats Extensions

New fields in `RegionStats`:

```rust
/// Best adjacent mean satisfaction minus own mean satisfaction, clamped >= 0.
/// 0.0 if no adjacent regions or none are better.
pub migration_opportunity: Vec<f32>,
/// Region ID of best adjacent region. Only meaningful when migration_opportunity > 0.
pub best_migration_target: Vec<u16>,
```

Computed in `compute_region_stats()` after `mean_satisfaction` is finalized. One pass over adjacency masks: O(regions x 32).

---

## Evaluate Region Decisions — Refactored Structure

Function signature gains RNG:

```rust
pub fn evaluate_region_decisions(
    pool: &AgentPool,
    slots: &[usize],
    region: &RegionState,
    stats: &RegionStats,
    region_id: usize,
    rng: &mut ChaCha8Rng,
) -> PendingDecisions
```

Internal structure:

```rust
for &slot in slots {
    if !pool.is_alive(slot) { continue; }

    let sat = pool.satisfaction(slot);
    let loy = pool.loyalty(slot);
    let civ = pool.civ_affinity(slot);
    let occ = pool.occupation(slot) as usize;

    // 1. Compute utilities
    let u_rebel = rebel_utility(loy, sat, stats.rebel_eligible[region_id]);
    let u_migrate = migrate_utility(sat, stats.migration_opportunity[region_id]);
    let (u_switch, switch_target) = switch_utility(
        occ, &stats.occupation_supply[region_id], &stats.occupation_demand[region_id],
    );
    let u_stay = STAY_BASE;

    // 2. Gumbel argmax selection
    let chosen = gumbel_argmax(
        &[u_rebel, u_migrate, u_switch, u_stay],
        rng,
        DECISION_TEMPERATURE,
    );

    // 3. Execute chosen action
    match chosen {
        0 => pending.rebellions.push((slot, region_id as u16)),
        1 => pending.migrations.push((slot, region_id as u16,
                                      stats.best_migration_target[region_id])),
        2 => pending.occupation_switches.push((slot, switch_target)),
        3 => { /* stay — no action */ },
        _ => unreachable!(),
    }

    // 4. Loyalty drift (background — skipped only for rebels)
    if chosen != 0 && stats.civ_counts[region_id].len() > 1 {
        // ... same Phase 5 drift/recovery logic (lines 276-309) ...
    }
}
```

**`PendingDecisions` struct:** Unchanged. Same fields, same semantics. `loyalty_drifts` and `loyalty_flips` populated in step 4, not via utility selection.

---

## RNG Stream Registry (Decision 11)

New constants block in `agent.rs`:

```rust
// RNG stream offsets — central registry to prevent collisions.
// Each system gets a range of 100 offsets. Stream for region r at turn t:
//   stream = r as u64 * 1000 + t as u64 + OFFSET
pub const DECISION_STREAM_OFFSET: u64     = 0;
pub const DEMOGRAPHICS_STREAM_OFFSET: u64 = 100;
pub const MIGRATION_STREAM_OFFSET: u64    = 200;
// Phase 6 additions (reserved, wired when systems land):
pub const CULTURE_DRIFT_OFFSET: u64       = 500;
pub const CONVERSION_STREAM_OFFSET: u64   = 600;
pub const PERSONALITY_STREAM_OFFSET: u64  = 700;
pub const GOODS_ALLOC_STREAM_OFFSET: u64  = 800;
```

M32 wires `DECISION_STREAM_OFFSET` in `tick.rs`. M32 should also update the existing demographics RNG construction in `tick.rs` to use `DEMOGRAPHICS_STREAM_OFFSET` — a one-line edit that prevents a known stream collision (both currently use implicit offset 0) rather than deferring the collision to M47.

RNG construction in `tick.rs`:

```rust
let mut rng = ChaCha8Rng::from_seed(seed);
rng.set_stream(region_id as u64 * 1000 + turn as u64 + DECISION_STREAM_OFFSET);
```

---

## Constants

### New Constants (all `[CALIBRATE]` for M47)

| Constant | Value | Rationale |
|----------|-------|-----------|
| `STAY_BASE` | 0.5 | Reference point — all CAPs measured relative to this |
| `REBEL_CAP` | 1.5 | 3.0x STAY_BASE — rebellion near-certain when eligible |
| `MIGRATE_CAP` | 1.0 | 2.0x STAY_BASE — strong push, not overwhelming |
| `SWITCH_CAP` | 0.6 | 1.2x STAY_BASE — frequently contested with inertia |
| `DECISION_TEMPERATURE` | 0.3 | Moderate exploration; low enough for bounded divergence |
| `W_REBEL` | 3.75 | = REBEL_CAP / (LOY_THRESH + SAT_THRESH). Max distress hits cap. |
| `W_MIGRATE_SAT` | 1.67 | Scaled so max satisfaction deficit + typical opportunity hits MIGRATE_CAP |
| `W_MIGRATE_OPP` | 1.67 | Symmetric with satisfaction weight as starting point |
| `W_SWITCH` | 0.03 | At typical max oversupply ~2.0 and max gap ~10, product=20. 0.03*20=0.6=SWITCH_CAP. `[CALIBRATE]` — sensitive to population distribution. |
| `MIGRATE_HYSTERESIS` | 0.05 | Phase 5's adjacency delta requirement |

### Existing Constants (unchanged, from Phase 5)

| Constant | Value | Used In |
|----------|-------|---------|
| `REBEL_LOYALTY_THRESHOLD` | 0.2 | Rebel utility ReLU threshold |
| `REBEL_SATISFACTION_THRESHOLD` | 0.2 | Rebel utility ReLU threshold |
| `REBEL_MIN_COHORT` | 5 | Smoothstep center point |
| `MIGRATE_SATISFACTION_THRESHOLD` | 0.3 | Migrate utility ReLU threshold |
| `OCCUPATION_SWITCH_OVERSUPPLY` | 0.5 | Inverted: `1.0 / 0.5 = 2.0` used as `SWITCH_OVERSUPPLY_THRESH` |
| `OCCUPATION_SWITCH_UNDERSUPPLY` | 1.5 | Used as `SWITCH_UNDERSUPPLY_FACTOR` |
| `LOYALTY_DRIFT_RATE` | 0.02 | Background drift (unchanged) |
| `LOYALTY_RECOVERY_RATE` | 0.01 | Background recovery (unchanged) |
| `LOYALTY_FLIP_THRESHOLD` | 0.3 | Flip gate (unchanged) |

---

## Validation

Three-tier validation: structural regression, behavioral regression, shadow characterization.

### Tier 1: Structural Regression (Exact Match)

**Setup:** Extreme weights (W=10000), high CAPs (not clipping), T=0.

**Purpose:** Verify that the utility functions activate on the right conditions and argmax priority matches short-circuit priority. Any agent even epsilon below a Phase 5 threshold has utility >> STAY_BASE, reproducing binary gate behavior exactly.

**Assertion:** Given identical world state and agent pool, `PendingDecisions` from utility selection must match Phase 5 output **exactly** — same rebellions, same migrations, same switches, same loyalty drifts/flips.

**Priority preservation:** At T=0, argmax resolves via CAP ordering: `REBEL_CAP > MIGRATE_CAP > SWITCH_CAP > STAY_BASE`. An agent eligible for both rebel and migrate has higher rebel utility, matching Phase 5's implicit priority.

**Tests:**
- Port existing `behavior.rs` test scenarios (6 tests, lines 349-592). Each runs both Phase 5 `evaluate_region_decisions_v1` (preserved behind `#[cfg(test)]`) and M32's version. Assert identical `PendingDecisions`.
- Parametric test: 50 random seeds x 100 agents. Exact match at extreme weights + T=0.
- Individual utility function unit tests: 4 functions x ~3 edge cases each.
- `gumbel_argmax` deterministic path test (T=0 returns argmax).

### Tier 2: Behavioral Regression (Statistical)

**Setup:** Operational weights (W_REBEL=3.75, etc.), T=0.

**Why T=0:** Isolates weight-only divergence from noise-induced divergence, making tolerance bounds meaningful. At T>0, Gumbel noise would add variance that obscures whether the weights themselves produce bounded behavior.

**Purpose:** Verify that near-threshold softening is bounded. With operational weights, agents barely below Phase 5 thresholds may not act — this is **intended behavior** (the utility model captures threshold ambiguity that binary gates cannot). But aggregate rates must stay within tolerance.

**Methodology:** 200 seeds, 500 turns each, `--agents=hybrid`. Compare M32 vs Phase 5 aggregate rates.

**Tolerances:**
- Rebellion count within 20% of Phase 5 (fewer near-threshold rebels expected)
- Migration count within 15%
- Switch count within 25% (more variance from lower CAP ratio)
- Correlation structure preserved (same sign, magnitude within 0.1)

### Tier 3: Shadow Characterization (Documented Report)

**Setup:** Operational weights, T=0.3 (operational temperature).

**Purpose:** Characterize how the utility model diverges from Phase 5 under normal operation. Not a pass/fail test — a documented report for M47 calibration reference.

**Methodology:** 200 seeds, 500 turns each, `--agents=hybrid`. Collect per-seed:
- Total rebellions, migrations, switches
- Rebellion rate by satisfaction quartile
- Migration rate by satisfaction quartile
- Correlation structure: military/economy, culture/stability (via existing M19 analytics)

**Expected divergences (to document, not fix):**
- More single-dimension rebels (low loyalty + adequate satisfaction, or vice versa) — additive utility replaces Phase 5's AND gate. An agent with loyalty 0.05 but satisfaction 0.5 gets rebel utility > STAY_BASE. Arguably better behavior (disloyal agents should rebel regardless of economic satisfaction).
- More rebellions in sparsely populated regions — smoothstep cohort gate (3, 8) enables small-group rebellions that Phase 5's hard >= 5 cutoff would block.
- More migrations at satisfaction 0.25-0.30 (near threshold, Gumbel noise pushes some over)
- Fewer "rebel when could migrate" cases (utility comparison replaces hard priority)
- Slightly higher occupation switch variance (SWITCH_CAP close to STAY_BASE)

**Output:** `docs/superpowers/analytics/m32-shadow-comparison.md`. Run via existing M19 analytics batch runner.

---

## File Changes

| File | Change | Lines (est.) |
|------|--------|-------------|
| `agent.rs` | Add `STREAM_OFFSETS` block (Decision 11). Add new constants: CAPs, temperature, weights, hysteresis. Keep existing threshold names unchanged. | ~25 |
| `behavior.rs` | Replace `evaluate_region_decisions` internals. Add utility functions (`rebel_utility`, `migrate_utility`, `switch_utility`), `gumbel_argmax`, `smoothstep`. Extend `RegionStats` with `migration_opportunity` / `best_migration_target`. Preserve Phase 5 logic as `evaluate_region_decisions_v1` behind `#[cfg(test)]`. Add RNG parameter. | ~150 |
| `behavior.rs` (tests) | Tier 1 structural regression (6 ported scenarios + 1 parametric), utility function unit tests (4 functions x 3 cases), `gumbel_argmax` test. | ~175 |
| `tick.rs` | Construct per-region `ChaCha8Rng` from seed/turn/`DECISION_STREAM_OFFSET`. Pass to `evaluate_region_decisions`. | ~15 |

**Total:** ~365 lines Rust, 0 Python.

### What Doesn't Change

- `PendingDecisions` struct — same fields, same semantics
- `pool.rs` — no new agent fields (personality is M33)
- `satisfaction.rs` — untouched (upstream of decisions)
- Python simulation loop — no phase changes, no new events
- `agent_bridge.py` — FFI contract unchanged
- Narrator / curator — no new moment types
- Bundle format — stays at `bundle_version: 1`

---

## Forward Dependencies

| Milestone | How M32 Enables It |
|-----------|-------------------|
| M33 (Personality) | Personality multipliers on utility weights. Bold agents get higher rebel/migrate utility. Neutral personality [0,0,0] approximates M32 behavior. |
| M34 (Resources) | Migrate utility gains per-occupation opportunity scores (farmer-specific, merchant-specific). Same pre-computation pattern. |
| M35a (Rivers) | `migration_opportunity` computation expands to scan both `adjacency_mask` and `river_mask`. |
| M47 (Tuning) | Three-tier calibration hierarchy. Shadow comparison report provides M47's starting data. |
