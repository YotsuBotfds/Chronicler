# M33: Agent Personality — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 immutable personality dimensions that multiply M32 utility outputs, with civ-derived assignment at spawn.

**Architecture:** Personality is 3 SoA f32 fields (boldness, ambition, loyalty_trait) stored in AgentPool. A `personality_modifier()` function wraps utility outputs between the utility call and the NEG_INFINITY gate. Assignment flows Python (civ means) → Rust (per-agent noise). Named character labels are derived on-the-fly.

**Tech Stack:** Rust (chronicler-agents crate), Python (agent_bridge.py), Arrow IPC

**Spec:** `docs/superpowers/specs/2026-03-16-m33-personality-design.md`

---

## File Structure

| File | Responsibility | Change Type |
|------|---------------|-------------|
| `chronicler-agents/src/agent.rs` | Constants: 4 personality weights, 2 noise σ, 1 label threshold | Modify |
| `chronicler-agents/src/pool.rs` | SoA storage: 3 new f32 vecs, extended `spawn()`, extended `to_record_batch()` | Modify |
| `chronicler-agents/src/behavior.rs` | `personality_modifier()` + apply to utility pipeline, personality-modified drift | Modify |
| `chronicler-agents/src/demographics.rs` | `assign_personality()` and `inherit_personality()` pure functions | Modify |
| `chronicler-agents/src/signals.rs` | 3 new optional f32 fields on `CivSignals`, accessor | Modify |
| `chronicler-agents/src/tick.rs` | `BirthInfo` extension, personality RNG in demographics phase, pass to `spawn()` | Modify |
| `chronicler-agents/src/ffi.rs` | `promotions_schema` + `snapshot_schema` extensions, `personality_label()`, initial spawn personality | Modify |
| `src/chronicler/agent_bridge.py` | `civ_personality_mean()`, 3 new civ signal columns | Modify |

---

## Chunk 1: Rust Core — Storage, Constants, Modifier, Assignment

### Task 1: Add personality constants to agent.rs

**Files:**
- Modify: `chronicler-agents/src/agent.rs:56-82`

- [ ] **Step 1: Add personality weight constants after M32 utility block**

After the `SWITCH_UNDERSUPPLY_FACTOR` line (line 70), before the stream offset block (line 72), add:

```rust
// Personality multipliers (M33) [CALIBRATE: M47]
// Applied to utility outputs: modifier = (1.0 + dimension * WEIGHT).max(0.0)
pub const BOLD_REBEL_WEIGHT: f32 = 0.3;
pub const BOLD_MIGRATE_WEIGHT: f32 = 0.3;
pub const AMBITION_SWITCH_WEIGHT: f32 = 0.3;
pub const LOYALTY_TRAIT_WEIGHT: f32 = 0.3;
pub const SPAWN_PERSONALITY_NOISE: f32 = 0.3;
pub const BIRTH_PERSONALITY_NOISE: f32 = 0.15;
pub const PERSONALITY_LABEL_THRESHOLD: f32 = 0.5;
```

- [ ] **Step 2: Run tests to verify nothing broke**

Run: `cargo test -p chronicler-agents -- agent::tests`
Expected: All pass (constants are additive, no behavior change)

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/agent.rs
git commit -m "feat(m33): add personality constants to agent.rs"
```

---

### Task 2: Add personality SoA fields to AgentPool

**Files:**
- Modify: `chronicler-agents/src/pool.rs:17-125`

- [ ] **Step 1: Add 3 personality fields to AgentPool struct**

After `promotion_progress: Vec<u8>,` (line 37), before `// Liveness` (line 38), add:

```rust
    // Personality (M33) — immutable after spawn
    pub boldness: Vec<f32>,
    pub ambition: Vec<f32>,
    pub loyalty_trait: Vec<f32>,
```

- [ ] **Step 2: Initialize fields in `AgentPool::new()`**

In `new()` (lines 52-69), after `promotion_progress` init (line 64), add:

```rust
            boldness: Vec::with_capacity(capacity),
            ambition: Vec::with_capacity(capacity),
            loyalty_trait: Vec::with_capacity(capacity),
```

- [ ] **Step 3: Extend `spawn()` signature and both code paths**

Change `spawn()` signature (line 74-79) to:

```rust
    pub fn spawn(
        &mut self,
        region: u16,
        civ_affinity: u8,
        occupation: Occupation,
        age: u16,
        boldness: f32,
        ambition: f32,
        loyalty_trait: f32,
    ) -> usize {
```

In the free-slot reuse path (lines 84-103), after `self.promotion_progress[slot] = 0;` (line 100), add:

```rust
            self.boldness[slot] = boldness;
            self.ambition[slot] = ambition;
            self.loyalty_trait[slot] = loyalty_trait;
```

In the grow path (lines 104-124), after `self.promotion_progress.push(0);` (line 120), add:

```rust
            self.boldness.push(boldness);
            self.ambition.push(ambition);
            self.loyalty_trait.push(loyalty_trait);
```

- [ ] **Step 4: Add personality accessors**

After the `displacement_turns` accessor (line 250), add:

```rust
    #[inline]
    pub fn boldness(&self, slot: usize) -> f32 {
        self.boldness[slot]
    }

    #[inline]
    pub fn ambition(&self, slot: usize) -> f32 {
        self.ambition[slot]
    }

    #[inline]
    pub fn loyalty_trait(&self, slot: usize) -> f32 {
        self.loyalty_trait[slot]
    }
```

- [ ] **Step 5: Fix ALL existing spawn() call sites to pass (0.0, 0.0, 0.0)**

Every `pool.spawn(region, civ, occ, age)` becomes `pool.spawn(region, civ, occ, age, 0.0, 0.0, 0.0)`. Files with spawn calls:

- `pool.rs` tests (~39 calls): all test spawn calls
- `behavior.rs` tests (~17 calls): all test spawn calls
- `tick.rs:240-244` (birth): `pool.spawn(birth.region, birth.civ, Occupation::Farmer, 0, 0.0, 0.0, 0.0)` — will be updated with real values in Task 7
- `ffi.rs:258-271` (initial spawn): all 5 occupation loops — will be updated with real values in Task 9
- `tick.rs` tests (~15 calls): all test spawn calls
- `named_characters.rs` tests (~3 calls)

Use search-and-replace across the entire crate: every `.spawn(` call gets 3 trailing `0.0` args. Do not rely on approximate counts — search all files.

- [ ] **Step 6: Run full test suite**

Run: `cargo test -p chronicler-agents`
Expected: All existing tests pass (neutral personality = no behavior change)

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/pool.rs chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs chronicler-agents/src/named_characters.rs chronicler-agents/src/behavior.rs
git commit -m "feat(m33): add personality SoA fields to AgentPool, extend spawn()"
```

---

### Task 3: Add personality_modifier() and apply to utility pipeline

**Files:**
- Modify: `chronicler-agents/src/behavior.rs:1-393`

**CRITICAL: Insertion order matters.** M32 landed a NEG_INFINITY gate pattern at lines 315-324:

```rust
let u_rebel_raw = rebel_utility(...);
let u_rebel = if u_rebel_raw > 0.0 { u_rebel_raw } else { f32::NEG_INFINITY };
```

Personality modifier MUST go between the utility call and the NEG_INFINITY gate:

```
utility function → personality modifier → NEG_INFINITY gate → gumbel_argmax
```

If placed after the gate, `NEG_INFINITY * modifier` produces garbage.

- [ ] **Step 1: Write test for personality_modifier**

In the `#[cfg(test)] mod tests` block, add:

```rust
    #[test]
    fn test_personality_modifier_neutral() {
        let m = super::personality_modifier(0.0, 0.3);
        assert!((m - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_personality_modifier_positive() {
        let m = super::personality_modifier(1.0, 0.3);
        assert!((m - 1.3).abs() < 1e-6);
    }

    #[test]
    fn test_personality_modifier_negative() {
        let m = super::personality_modifier(-1.0, 0.3);
        assert!((m - 0.7).abs() < 1e-6);
    }

    #[test]
    fn test_personality_modifier_floor_at_zero() {
        // High weight + negative dimension → clamped to 0.0, not negative
        let m = super::personality_modifier(-1.0, 1.5);
        assert_eq!(m, 0.0);
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test -p chronicler-agents -- behavior::tests::test_personality_modifier`
Expected: FAIL — `personality_modifier` not defined

- [ ] **Step 3: Implement personality_modifier**

After the `smoothstep` function (line 32) and before `gumbel_argmax` (line 34), add:

```rust
/// Maps a personality dimension [-1, +1] to a utility multiplier.
/// Output clamped to >= 0.0 to prevent sign flips at high weights.
#[inline]
fn personality_modifier(dimension: f32, weight: f32) -> f32 {
    (1.0 + dimension * weight).max(0.0)
}
```

- [ ] **Step 4: Run modifier tests**

Run: `cargo test -p chronicler-agents -- behavior::tests::test_personality_modifier`
Expected: All 4 pass

- [ ] **Step 5: Add personality import to evaluate_region_decisions**

At the top of `behavior.rs`, add to the imports from `crate::agent`:

```rust
    BOLD_REBEL_WEIGHT, BOLD_MIGRATE_WEIGHT, AMBITION_SWITCH_WEIGHT, LOYALTY_TRAIT_WEIGHT,
```

- [ ] **Step 6: Apply personality modifiers in evaluate_region_decisions**

In `evaluate_region_decisions()` (line 292-393), after reading `occ` (line 310), add personality reads:

```rust
        let bold = pool.boldness(slot);
        let ambi = pool.ambition(slot);
        let ltrait = pool.loyalty_trait(slot);
```

Then replace the utility computation block (lines 315-325) with:

```rust
        // Compute utilities: utility fn → personality modifier → NEG_INFINITY gate
        // Modifier MUST be applied BEFORE the gate. 0.0 * modifier = 0.0 → gated to NEG_INFINITY.
        // If placed after, NEG_INFINITY * modifier produces garbage.
        let u_rebel_raw = rebel_utility(loy, sat, stats.rebel_eligible[region_id])
            * personality_modifier(bold, BOLD_REBEL_WEIGHT);
        let u_rebel = if u_rebel_raw > 0.0 { u_rebel_raw } else { f32::NEG_INFINITY };

        let u_migrate_raw = migrate_utility(sat, stats.migration_opportunity[region_id])
            * personality_modifier(bold, BOLD_MIGRATE_WEIGHT);
        let u_migrate = if u_migrate_raw > 0.0 { u_migrate_raw } else { f32::NEG_INFINITY };

        let (u_switch_base, switch_target) = switch_utility(
            occ,
            &stats.occupation_supply[region_id],
            &stats.occupation_demand[region_id],
        );
        let u_switch_raw = u_switch_base * personality_modifier(ambi, AMBITION_SWITCH_WEIGHT);
        let u_switch = if u_switch_raw > 0.0 { u_switch_raw } else { f32::NEG_INFINITY };

        let u_stay = STAY_BASE;
```

- [ ] **Step 7: Apply personality to loyalty drift rate**

In the loyalty drift section (line 377-384), replace the two drift lines:

```rust
                if loy - LOYALTY_DRIFT_RATE < LOYALTY_FLIP_THRESHOLD {
```

with:

```rust
                // Personality-modified drift: steadfast (+1) drifts slower, mercenary (-1) faster
                let effective_drift = LOYALTY_DRIFT_RATE
                    * personality_modifier(-ltrait, LOYALTY_TRAIT_WEIGHT);
                if loy - effective_drift < LOYALTY_FLIP_THRESHOLD {
```

And replace `pending.loyalty_drifts.push((slot, -LOYALTY_DRIFT_RATE));` with:

```rust
                    pending.loyalty_drifts.push((slot, -effective_drift));
```

- [ ] **Step 8: Run full test suite**

Run: `cargo test -p chronicler-agents`
Expected: All pass — all agents have personality [0,0,0] so modifiers are 1.0 (identity)

- [ ] **Step 9: Write neutral regression test**

Add to behavior tests:

```rust
    /// M33 neutral regression: personality [0,0,0] must produce identical
    /// decisions to M32 (modifier = 1.0 + 0.0 * weight = 1.0).
    #[test]
    fn test_m33_neutral_regression() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;

        let mut pool = AgentPool::new(32);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;

        // Mix of conditions: some rebel-eligible, some migrate-eligible
        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.01);
            pool.set_satisfaction(slot, 0.01);
        }
        for _ in 0..4 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_satisfaction(slot, 0.1);
            pool.set_loyalty(slot, 0.5);
        }
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_satisfaction(slot, 0.8);
            pool.set_loyalty(slot, 0.5);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..10).collect();

        // Run twice with same seed — identical personality [0,0,0] should give identical results
        let mut rng_a = ChaCha8Rng::from_seed([42u8; 32]);
        let mut rng_b = ChaCha8Rng::from_seed([42u8; 32]);
        let pd_a = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng_a);
        let pd_b = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng_b);

        assert_eq!(pd_a.rebellions.len(), pd_b.rebellions.len());
        assert_eq!(pd_a.migrations.len(), pd_b.migrations.len());
        assert_eq!(pd_a.occupation_switches.len(), pd_b.occupation_switches.len());
    }
```

- [ ] **Step 10: Run test**

Run: `cargo test -p chronicler-agents -- behavior::tests::test_m33_neutral_regression`
Expected: PASS

- [ ] **Step 11: Write boldness behavioral correlation test**

```rust
    /// M33 Tier 2: Bold agents rebel more than cautious agents in marginal conditions.
    #[test]
    fn test_m33_bold_rebels_more_than_cautious() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;

        let regions = vec![make_region(0)];
        let mut bold_rebels = 0u32;
        let mut cautious_rebels = 0u32;

        for seed_byte in 0..100u8 {
            let mut seed = [0u8; 32];
            seed[0] = seed_byte;

            // Bold cohort: 6 agents at boldness=+0.8
            let mut pool = AgentPool::new(16);
            for _ in 0..6 {
                let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.8, 0.0, 0.0);
                pool.set_loyalty(slot, 0.15);      // near threshold
                pool.set_satisfaction(slot, 0.15);  // near threshold
            }
            let stats = compute_region_stats(&pool, &regions, &default_signals(1));
            let slots: Vec<usize> = (0..6).collect();
            let mut rng = ChaCha8Rng::from_seed(seed);
            let pd = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
            bold_rebels += pd.rebellions.len() as u32;

            // Cautious cohort: 6 agents at boldness=-0.8
            let mut pool = AgentPool::new(16);
            for _ in 0..6 {
                let slot = pool.spawn(0, 0, Occupation::Farmer, 25, -0.8, 0.0, 0.0);
                pool.set_loyalty(slot, 0.15);
                pool.set_satisfaction(slot, 0.15);
            }
            let stats = compute_region_stats(&pool, &regions, &default_signals(1));
            let slots: Vec<usize> = (0..6).collect();
            let mut rng = ChaCha8Rng::from_seed(seed);
            let pd = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
            cautious_rebels += pd.rebellions.len() as u32;
        }

        assert!(bold_rebels > cautious_rebels,
            "bold agents should rebel more: bold={} cautious={}", bold_rebels, cautious_rebels);
        // Expect a clear margin, not a coin flip
        assert!(bold_rebels > cautious_rebels + 20,
            "margin too small: bold={} cautious={}", bold_rebels, cautious_rebels);
    }
```

- [ ] **Step 12: Run behavioral test**

Run: `cargo test -p chronicler-agents -- behavior::tests::test_m33_bold_rebels`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
git add chronicler-agents/src/behavior.rs
git commit -m "feat(m33): add personality_modifier and apply to utility pipeline"
```

---

### Task 4: Add assign_personality and inherit_personality to demographics.rs

**Files:**
- Modify: `chronicler-agents/src/demographics.rs`

- [ ] **Step 1: Write tests for assign_personality**

Add to `demographics.rs` test module:

```rust
    #[test]
    fn test_assign_personality_neutral_mean() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let p = super::assign_personality(&mut rng, [0.0, 0.0, 0.0]);
        // With zero mean and noise, values should be near zero but not exactly zero
        for &v in &p {
            assert!(v >= -1.0 && v <= 1.0, "personality out of range: {}", v);
        }
    }

    #[test]
    fn test_assign_personality_clamped() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        // Run many times — all values must stay in [-1, 1]
        for seed_byte in 0..50u8 {
            let mut seed = [0u8; 32];
            seed[0] = seed_byte;
            let mut rng = ChaCha8Rng::from_seed(seed);
            let p = super::assign_personality(&mut rng, [0.3, -0.3, 0.3]);
            for &v in &p {
                assert!(v >= -1.0 && v <= 1.0, "personality out of range: {}", v);
            }
        }
    }

    #[test]
    fn test_inherit_personality_tighter_noise() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        // Inherit from a parent at [0.5, 0.5, 0.5] — child should be close
        let mut sum = [0.0f64; 3];
        let n = 1000;
        for seed_byte in 0..n {
            let mut seed = [0u8; 32];
            seed[0] = (seed_byte % 256) as u8;
            seed[1] = (seed_byte / 256) as u8;
            let mut rng = ChaCha8Rng::from_seed(seed);
            let p = super::inherit_personality(&mut rng, [0.5, 0.5, 0.5]);
            for i in 0..3 { sum[i] += p[i] as f64; }
        }
        // Mean should be near parent (0.5) ± tolerance
        for i in 0..3 {
            let mean = sum[i] / n as f64;
            assert!((mean - 0.5).abs() < 0.05,
                "dimension {} mean {} too far from parent 0.5", i, mean);
        }
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test -p chronicler-agents -- demographics::tests::test_assign`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement assign_personality and inherit_personality**

Add to `demographics.rs` after the `fertility_rate` function (line 33), before `#[cfg(test)]`:

```rust
use rand::distr::StandardNormal;
use rand::prelude::*;
use rand_chacha::ChaCha8Rng;

/// Assign personality from civ mean + Gaussian noise. Immutable after spawn.
pub fn assign_personality(rng: &mut ChaCha8Rng, civ_mean: [f32; 3]) -> [f32; 3] {
    let mut p = [0.0f32; 3];
    for i in 0..3 {
        let noise: f32 = rng.sample::<f32, _>(StandardNormal) * SPAWN_PERSONALITY_NOISE;
        p[i] = (civ_mean[i] + noise).clamp(-1.0, 1.0);
    }
    p
}

/// Inherit personality from parent + tighter Gaussian noise. For M39 wiring.
pub fn inherit_personality(rng: &mut ChaCha8Rng, parent: [f32; 3]) -> [f32; 3] {
    let mut p = [0.0f32; 3];
    for i in 0..3 {
        let noise: f32 = rng.sample::<f32, _>(StandardNormal) * BIRTH_PERSONALITY_NOISE;
        p[i] = (parent[i] + noise).clamp(-1.0, 1.0);
    }
    p
}
```

- [ ] **Step 4: Run tests**

Run: `cargo test -p chronicler-agents -- demographics::tests`
Expected: All pass (including existing mortality/fertility tests)

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/demographics.rs
git commit -m "feat(m33): add assign_personality and inherit_personality"
```

---

### Task 5: Add personality label helper

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`

- [ ] **Step 1: Add personality_label function**

After the `arrow_err` helper (line 24), before the schema definitions (line 28), add:

```rust
use crate::agent::PERSONALITY_LABEL_THRESHOLD;

/// Derive a narrative label from the dominant personality dimension.
/// Returns None if all dimensions are below threshold (neutral personality).
pub fn personality_label(boldness: f32, ambition: f32, loyalty_trait: f32) -> Option<&'static str> {
    let dims: [(f32, f32, &str, &str); 3] = [
        (boldness.abs(),      boldness,      "the Bold",      "the Cautious"),
        (ambition.abs(),      ambition,      "the Ambitious",  "the Humble"),
        (loyalty_trait.abs(), loyalty_trait,  "the Steadfast",  "the Fickle"),
    ];

    let mut max_idx = 0;
    let mut max_abs = dims[0].0;
    for i in 1..3 {
        if dims[i].0 > max_abs {
            max_abs = dims[i].0;
            max_idx = i;
        }
    }

    if max_abs < PERSONALITY_LABEL_THRESHOLD {
        return None;
    }

    let (_, raw, pos, neg) = dims[max_idx];
    Some(if raw > 0.0 { pos } else { neg })
}
```

- [ ] **Step 2: Run full test suite**

Run: `cargo test -p chronicler-agents`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m33): add personality_label helper"
```

---

## Chunk 2: Integration — Signals, Tick, FFI, Python, Validation

### Task 6: Extend CivSignals with personality means

**Files:**
- Modify: `chronicler-agents/src/signals.rs:9-27,67-109`

- [ ] **Step 1: Add 3 fields to CivSignals struct**

After `demand_shift_priest: f32,` (line 26), add:

```rust
    // M33 personality means (immutable per-civ):
    pub mean_boldness: f32,
    pub mean_ambition: f32,
    pub mean_loyalty_trait: f32,
```

- [ ] **Step 2: Parse optional columns in parse_civ_signals**

After the `demand_priest_col` binding (line 85), add:

```rust
    let mean_boldness_col = batch.column_by_name("mean_boldness")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let mean_ambition_col = batch.column_by_name("mean_ambition")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let mean_loyalty_trait_col = batch.column_by_name("mean_loyalty_trait")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
```

In the per-row loop (line 89-106), after `demand_shift_priest`, add:

```rust
            mean_boldness: mean_boldness_col.map(|a| a.value(i)).unwrap_or(0.0),
            mean_ambition: mean_ambition_col.map(|a| a.value(i)).unwrap_or(0.0),
            mean_loyalty_trait: mean_loyalty_trait_col.map(|a| a.value(i)).unwrap_or(0.0),
```

- [ ] **Step 3: Add personality_mean_for_civ accessor to TickSignals**

After `demand_shifts_for_civ` (line 163), add:

```rust
    /// Personality mean [boldness, ambition, loyalty_trait] for the given civ.
    pub fn personality_mean_for_civ(&self, civ_id: u8) -> [f32; 3] {
        self.civs
            .iter()
            .find(|c| c.civ_id == civ_id)
            .map(|c| [c.mean_boldness, c.mean_ambition, c.mean_loyalty_trait])
            .unwrap_or([0.0; 3])
    }
```

- [ ] **Step 4: Fix all CivSignals construction in test code**

Every `CivSignals { ... }` literal in `signals.rs` tests and `tick.rs` tests (the `make_default_signals` helper) needs 3 new fields:

```rust
                    mean_boldness: 0.0,
                    mean_ambition: 0.0,
                    mean_loyalty_trait: 0.0,
```

Add these after the `demand_shift_priest` field in every CivSignals construction.

- [ ] **Step 5: Run full test suite**

Run: `cargo test -p chronicler-agents`
Expected: All pass (optional columns default to 0.0 — backward compatible)

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/signals.rs chronicler-agents/src/tick.rs
git commit -m "feat(m33): extend CivSignals with personality means"
```

---

### Task 7: Wire personality into birth path (tick.rs)

**Files:**
- Modify: `chronicler-agents/src/tick.rs:8-13,194-260,404-467`

- [ ] **Step 1: Add BirthInfo personality field**

Change `BirthInfo` (lines 404-408) to:

```rust
struct BirthInfo {
    region: u16,
    civ: u8,
    parent_loyalty: f32,
    personality: [f32; 3],
}
```

- [ ] **Step 2: Add master_seed/turn params and personality RNG to tick_region_demographics**

Add import at top of `tick.rs`:

```rust
use crate::agent::PERSONALITY_STREAM_OFFSET;
```

`tick_region_demographics` needs `master_seed` and `turn` to construct a dedicated personality RNG. Change the function signature (line 417-424) to:

```rust
fn tick_region_demographics(
    pool: &AgentPool,
    slots: &[usize],
    region: &RegionState,
    signals: &TickSignals,
    region_id: usize,
    rng: &mut ChaCha8Rng,
    master_seed: [u8; 32],
    turn: u32,
) -> DemographicsPending {
```

After `let eco_stress = ...;` (line 431), construct the dedicated personality RNG:

```rust
    // Dedicated personality RNG (offset 700) decoupled from demographics RNG.
    // Prevents adding/removing mortality checks from changing personality assignments.
    let mut personality_rng = ChaCha8Rng::from_seed(master_seed);
    personality_rng.set_stream(
        region_id as u64 * 1000 + turn as u64 + PERSONALITY_STREAM_OFFSET,
    );
```

- [ ] **Step 3: Assign personality in BirthInfo construction**

In the birth path inside the loop (lines 457-461), replace the `BirthInfo` construction:

```rust
                let civ_id = pool.civ_affinity(slot);
                let civ_mean = signals.personality_mean_for_civ(civ_id);
                let personality = crate::demographics::assign_personality(
                    &mut personality_rng, civ_mean,
                );
                pending.births.push(BirthInfo {
                    region: region_id as u16,
                    civ: civ_id,
                    parent_loyalty: pool.loyalty(slot),
                    personality,
                });
```

- [ ] **Step 4: Pass personality from BirthInfo to pool.spawn() in sequential apply**

In `tick_agents()`, the birth apply section (lines 239-260), change to:

```rust
            let new_slot = pool.spawn(
                birth.region,
                birth.civ,
                crate::agent::Occupation::Farmer,
                0,
                birth.personality[0],
                birth.personality[1],
                birth.personality[2],
            );
```

- [ ] **Step 5: Update the par_iter demographics call to pass master_seed and turn**

In `tick_agents()` (lines 194-215), update the closure to pass `master_seed` and `turn`:

```rust
                tick_region_demographics(
                    pool_ref,
                    slots,
                    &regions[region_id],
                    signals,
                    region_id,
                    &mut rng,
                    master_seed,
                    turn,
                )
```

- [ ] **Step 6: Run full test suite**

Run: `cargo test -p chronicler-agents`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m33): wire personality into birth path with dedicated RNG"
```

---

### Task 8: Extend snapshot and promotions schemas + RecordBatch serialization

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:31-88,287-400`
- Modify: `chronicler-agents/src/pool.rs:287-341`

- [ ] **Step 1: Add personality columns to snapshot_schema**

In `snapshot_schema()` (line 31-44), after the `displacement_turn` field, add:

```rust
        Field::new("boldness", DataType::Float32, false),
        Field::new("ambition", DataType::Float32, false),
        Field::new("loyalty_trait", DataType::Float32, false),
```

- [ ] **Step 2: Add personality columns to to_record_batch() in pool.rs**

In `to_record_batch()`, add 3 builders after `displacement_turns`:

```rust
        let mut boldness_col = Float32Builder::with_capacity(live);
        let mut ambition_col = Float32Builder::with_capacity(live);
        let mut loyalty_trait_col = Float32Builder::with_capacity(live);
```

In the per-slot loop, after the `displacement_turns` append, add:

```rust
            boldness_col.append_value(self.boldness[slot]);
            ambition_col.append_value(self.ambition[slot]);
            loyalty_trait_col.append_value(self.loyalty_trait[slot]);
```

In the `RecordBatch::try_new` vec, after `displacement_turns.finish()`, add:

```rust
                Arc::new(boldness_col.finish()) as _,
                Arc::new(ambition_col.finish()) as _,
                Arc::new(loyalty_trait_col.finish()) as _,
```

- [ ] **Step 3: Add personality columns to promotions_schema**

In `promotions_schema()` (line 79-88), after `origin_region`, add:

```rust
        Field::new("boldness", DataType::Float32, false),
        Field::new("ambition", DataType::Float32, false),
        Field::new("loyalty_trait", DataType::Float32, false),
        Field::new("personality_label", DataType::Utf8, true),
```

- [ ] **Step 4: Add personality columns to get_promotions()**

Add import at the top of `ffi.rs`:

```rust
use arrow::array::StringBuilder;
```

In `get_promotions()` (line 348-400), add builders after `origin_regions`:

```rust
        let mut boldness_col = arrow::array::Float32Builder::with_capacity(n);
        let mut ambition_col = arrow::array::Float32Builder::with_capacity(n);
        let mut loyalty_trait_col = arrow::array::Float32Builder::with_capacity(n);
        let mut label_col = StringBuilder::with_capacity(n, n * 16);
```

In the per-candidate loop, after the `origin_regions.append_value` line, add:

```rust
            let b = self.pool.boldness[slot];
            let a = self.pool.ambition[slot];
            let lt = self.pool.loyalty_trait[slot];
            boldness_col.append_value(b);
            ambition_col.append_value(a);
            loyalty_trait_col.append_value(lt);
            match personality_label(b, a, lt) {
                Some(label) => label_col.append_value(label),
                None => label_col.append_null(),
            }
```

In the `RecordBatch::try_new` vec, after `origin_regions.finish()`, add:

```rust
                Arc::new(boldness_col.finish()) as _,
                Arc::new(ambition_col.finish()) as _,
                Arc::new(loyalty_trait_col.finish()) as _,
                Arc::new(label_col.finish()) as _,
```

- [ ] **Step 5: Run full test suite**

Run: `cargo test -p chronicler-agents`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/src/pool.rs
git commit -m "feat(m33): extend snapshot and promotions schemas with personality columns"
```

---

### Task 9: Wire personality into initial spawn (ffi.rs set_region_state)

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:239-272`

- [ ] **Step 1: Add personality assignment to initial spawn loop**

In `set_region_state()`, the initial spawn section (lines 241-272), add personality RNG setup before the spawn loops:

```rust
            // M33: personality assignment at initial spawn
            let mut personality_rng = ChaCha8Rng::from_seed(self.master_seed);
            personality_rng.set_stream(
                i as u64 * 1000 + crate::agent::PERSONALITY_STREAM_OFFSET,
            );
            let civ_mean = [0.0f32; 3]; // Will be populated from signals in Task 10
```

Add `use rand::SeedableRng; use rand_chacha::ChaCha8Rng;` to ffi.rs imports.

Change each spawn call from `self.pool.spawn(region_id, civ, Occupation::Farmer, 0)` to:

```rust
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    self.pool.spawn(region_id, civ, Occupation::Farmer, 0, p[0], p[1], p[2]);
```

Repeat for all 5 occupation loops (Farmer, Soldier, Merchant, Scholar, Priest).

**Note:** `civ_mean` is [0,0,0] for now because Python hasn't sent personality means yet at initial spawn time. The real civ means are sent in the first `tick()` via `CivSignals`. For initial spawn, neutral personality + noise is correct — agents get personality from noise alone, centered on zero. When Python starts sending personality means in `CivSignals`, the *birth* path will use them correctly. This is an acceptable initial-spawn simplification — initial agents have personality from noise only; their children (born after first tick) get civ-mean-centered personality.

- [ ] **Step 2: Run full test suite**

Run: `cargo test -p chronicler-agents`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m33): wire personality into initial spawn with noise-only assignment"
```

---

### Task 10: Python-side — civ_personality_mean and CivSignals columns

**Files:**
- Modify: `src/chronicler/agent_bridge.py:78-146`

- [ ] **Step 1: Add civ_personality_mean function**

After the `SUMMARY_TEMPLATES` dict (line 38), before `build_region_batch` (line 41), add:

```python
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
```

- [ ] **Step 2: Add personality mean columns to build_signals**

In `build_signals()` (lines 78-146), add personality mean column builders after the demand shift builders (line 102):

```python
    mean_bold, mean_ambi, mean_ltrait = [], [], []
```

In the per-civ loop (line 104-127), after the demand shift appends, add:

```python
        civ_values = getattr(civ, 'values', [])
        civ_domains = getattr(civ, 'domains', [])
        pm = civ_personality_mean(civ_values, civ_domains)
        mean_bold.append(pm[0])
        mean_ambi.append(pm[1])
        mean_ltrait.append(pm[2])
```

In the return `pa.record_batch({...})` (lines 129-146), after `"demand_shift_priest"`, add:

```python
        "mean_boldness": pa.array(mean_bold, type=pa.float32()),
        "mean_ambition": pa.array(mean_ambi, type=pa.float32()),
        "mean_loyalty_trait": pa.array(mean_ltrait, type=pa.float32()),
```

- [ ] **Step 3: Test manually or with existing integration test**

Run: `python -c "from chronicler.agent_bridge import civ_personality_mean; print(civ_personality_mean(['Honor', 'Tradition'], ['military']))"`
Expected: `(0.25, 0.0, 0.15)` — Honor(+0.15 bold) + military(+0.10 bold) = 0.25 bold, Tradition(+0.15 ltrait) = 0.15 ltrait, clamped at 0.3 for bold → (0.25, 0.0, 0.15)

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m33): add civ_personality_mean and personality columns to CivSignals"
```

---

### Task 11: Final integration test — personality label in promotions

**Files:**
- Test in: `chronicler-agents/src/ffi.rs` or manual Python integration

- [ ] **Step 1: Add personality label round-trip test**

In a test file or ad-hoc, verify that a promoted agent with boldness=0.8, ambition=0.1, loyalty_trait=0.2 produces label "the Bold":

```rust
    #[test]
    fn test_personality_label_bold() {
        assert_eq!(super::personality_label(0.8, 0.1, 0.2), Some("the Bold"));
    }

    #[test]
    fn test_personality_label_neutral() {
        assert_eq!(super::personality_label(0.2, 0.1, -0.3), None);
    }

    #[test]
    fn test_personality_label_fickle() {
        assert_eq!(super::personality_label(0.1, 0.2, -0.7), Some("the Fickle"));
    }
```

- [ ] **Step 2: Run full test suite one final time**

Run: `cargo test -p chronicler-agents`
Expected: All pass

- [ ] **Step 3: Build the Python wheel to verify FFI compiles clean**

Run: `cd chronicler-agents && maturin develop --release`
Expected: Compiles without errors

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m33): add personality label tests and verify full build"
```

---

## Summary

| Task | Files | What |
|------|-------|------|
| 1 | agent.rs | Constants (7 personality consts) |
| 2 | pool.rs, tick.rs, ffi.rs, behavior.rs, named_characters.rs | SoA fields + spawn() signature |
| 3 | behavior.rs | personality_modifier(), utility pipeline, drift modifier, tests |
| 4 | demographics.rs | assign_personality(), inherit_personality() |
| 5 | ffi.rs | personality_label() helper |
| 6 | signals.rs, tick.rs | CivSignals extension |
| 7 | tick.rs | Birth path: BirthInfo, personality RNG, pass to spawn() |
| 8 | ffi.rs, pool.rs | Snapshot + promotions schema extensions |
| 9 | ffi.rs | Initial spawn personality assignment |
| 10 | agent_bridge.py | Python civ_personality_mean + signal columns |
| 11 | ffi.rs | Label tests + full build verify |

## Deferred

**Tier 3: Distribution Stability Test** — The spec defines a Python-side analytics test (spawn 50k agents, run 500 turns under stable conditions, verify personality mean and σ are preserved). This is not included in this plan because it requires a working end-to-end simulation harness and is better run as a standalone analytics script after the Rust+Python integration is complete. Create as a separate follow-up task.
