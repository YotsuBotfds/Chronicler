# M33: Agent Personality

> **Status:** Design approved. Ready for implementation planning.
>
> **Depends on:** M32 (Utility-Based Decision Model) landed. Personality multipliers apply to M32's utility outputs.
>
> **Scope:** Add 3 personality dimensions that multiply M32 utility outputs, with civ-derived assignment at spawn. ~200 lines Rust, ~50 lines Python.

---

## Overview

M32 gives every agent the same utility function shape — two agents with identical satisfaction, loyalty, and occupation respond identically. M33 adds personality: three continuous dimensions that scale utility outputs, making agents respond differently to the same conditions. A bold agent rebels more readily; an ambitious agent switches occupation more aggressively; a steadfast agent resists loyalty drift.

Personality is immutable — set once at spawn (or birth), never mutated. It represents innate disposition. Satisfaction and loyalty capture situational response. These are orthogonal: a bold agent with high satisfaction doesn't rebel (boldness amplifies near-zero rebel utility to near-zero). A cautious agent with terrible satisfaction does rebel — just less readily.

**Backward compatibility:** Personality [0,0,0] produces modifier 1.0 on all utilities — exact M32 behavior. The neutral regression test verifies this.

---

## Design Decisions

### Pure Multiplier on Final Utility Output

Personality multiplies the capped utility output, not internal weights. The modifier is applied after `min(CAP, max(0, ...))` but before `gumbel_argmax`:

```rust
let u_rebel = rebel_utility(loy, sat, rebel_eligible)
    * personality_modifier(boldness, BOLD_REBEL_WEIGHT);
```

**Why not multiply internal weights (e.g., scale W_REBEL by boldness):** M32 establishes a three-tier calibration hierarchy: CAP ratios → temperature → weights. Personality scaling internal weights injects a fourth calibration surface between weights and CAPs — a bold agent's effective W_REBEL would change the saturation point relative to REBEL_CAP, making CAP ratios meaningless for that agent. Multiplying the output preserves the hierarchy: M47 tunes weights and CAPs once; personality tilts the result.

Additionally, scaling W_REBEL changes the slope inside the ReLU active region. A bold agent hits REBEL_CAP earlier (at less extreme dissatisfaction), reducing gradient discrimination among bold agents — past saturation, all bold agents are equally likely to rebel regardless of how bad things are. That's the opposite of intent: boldness should make agents rebel more readily, not make them uniformly rebel-eager past a lower bar.

### Stay Utility Is Personality-Neutral

`stay_utility()` returns `STAY_BASE` unmodified by personality. Personality tilts the relative attractiveness of actions vs inertia, not the inertia baseline. This means personality affects whether agents prefer action over staying, without changing the threshold at which any action becomes viable.

### Personality Is Immutable

Set once at spawn (from civ-level distribution + noise) or birth (from parent + noise, wired in M39). Never mutated by life events, environmental conditions, or time.

**Why not drift in response to events:** Satisfaction and loyalty already capture "agent changed by experience." If personality drifted in response to the same events, a feedback loop emerges: rebellion → boldness increases → more likely to rebel → boldness increases further. This runaway attractor either needs damping constants (more calibration for M47) or collapses the personality distribution into bimodal clusters — exactly what the distribution stability test catches.

Immutability also makes M39 inheritance meaningful. A dynasty's personality trajectory is a genuine narrative signal ("Kiran the Bold's granddaughter inherited his recklessness") because boldness is a trait, not a mood. Drift would cause convergence within stable regions, erasing inherited personality before narration can use it.

If M40+ wants life-event-driven personality shifts, the clean addition is a separate `experience` modifier that stacks with innate personality — preserving the innate trait for inheritance and narration while layering learned behavior on top.

### Civ-Derived Personality Means

Each civilization gets a mean personality vector derived from its cultural values (M16) and domains at world gen. Per-agent noise dominates, but the population-level mean per civ reflects cultural identity.

**Why not random from seed hash:** Civs already have well-designed cultural values that capture exactly the distinctions personality should express. Hashing a seed to get arbitrary numbers throws that data away and forces the narrator to reconcile "why is this Order/Tradition civ full of reckless rebels?"

**Why values over mutable civ stats:** Values are assigned at world gen and barely change (M16 drift is slow). Military/economy/stability stats change rapidly — a fragile basis for a fixed personality mean. Values are the closest thing to "civ personality" that already exists.

### Target Re-Ranking Deferred to M35a

M32's spec notes: "M33 personality affects target selection (bold agents prefer contested regions), not opportunity magnitude." This re-ranking is deferred out of M33's scope. "Contested region" isn't well-defined until M34 (resource competition) and M36 (cultural identity) provide richer data. M35a (Rivers & Trade Corridors) already modifies migration corridors and is the natural place to consolidate the "where do migrants go?" logic — one re-ranking pass incorporating personality + rivers + resources rather than three separate passes across three milestones.

M33 without re-ranking is a complete milestone with clear validation criteria.

---

## Personality Dimensions

Three continuous floats, each in [-1.0, +1.0]:

| Dimension | -1.0 (Low) | +1.0 (High) | Utility Effect |
|-----------|-----------|-------------|----------------|
| **Boldness** | Cautious — avoids risk | Bold — seeks conflict | Multiplier on rebel and migrate utility |
| **Ambition** | Content — stays put | Ambitious — seeks advancement | Multiplier on switch utility |
| **Loyalty Trait** | Mercenary — drifts easily | Steadfast — resists change | Divisor on loyalty drift rate |

Storage: 3 × f32 = 12 bytes per agent. Pool grows ~44 → ~56 bytes/agent. Per-region at 500 agents = 6 KB personality data, within L1 cache.

---

## Personality Modifier

```rust
/// Maps a personality dimension [-1, +1] to a utility multiplier.
/// Output clamped to >= 0.0 to prevent sign flips at high weights.
#[inline]
fn personality_modifier(dimension: f32, weight: f32) -> f32 {
    (1.0 + dimension * weight).max(0.0)
}
```

Properties:
- Dimension 0.0 → modifier 1.0 → exact M32 behavior
- Dimension +1.0, weight 0.3 → modifier 1.3
- Dimension -1.0, weight 0.3 → modifier 0.7
- `max(0.0)` floor prevents calibration footguns: if M47 pushes a weight above 1.0, a maximally-negative dimension produces 0.0 (action fully suppressed) rather than a negative utility that flips Gumbel selection semantics

---

## Utility Integration

### Application Points

Personality multiplies the output of each capped utility, before Gumbel selection:

```rust
// Inside the per-agent utility evaluation loop:
let u_rebel = rebel_utility(loy, sat, rebel_eligible)
    * personality_modifier(boldness, BOLD_REBEL_WEIGHT);

let u_migrate = migrate_utility(sat, migration_opportunity)
    * personality_modifier(boldness, BOLD_MIGRATE_WEIGHT);

let (u_switch_raw, switch_target) = switch_utility(occ, supply, demand);
let u_switch = u_switch_raw
    * personality_modifier(ambition, AMBITION_SWITCH_WEIGHT);

let u_stay = stay_utility(); // no personality effect

// Gumbel argmax over [u_rebel, u_migrate, u_switch, u_stay]
```

Note: `switch_utility` returns `(f32, u8)` — destructure before applying the modifier.

### Loyalty Drift Modifier

Loyalty drift is a background process (M32 Decision 1), not a utility action. Personality modifies the drift rate directly:

```rust
let effective_drift = LOYALTY_DRIFT_RATE
    * personality_modifier(-loyalty_trait, LOYALTY_TRAIT_WEIGHT);
//                         ^ negated: steadfast (+1) → slower drift (modifier < 1.0)
//                           mercenary (-1) → faster drift (modifier > 1.0)
```

Recovery rate (`LOYALTY_RECOVERY_RATE`) is left unmodified by personality. Steadfast agents recovering faster is thematically reasonable but adds another calibration knob — M47 can add it if needed.

### Noise-to-Signal Interaction

Personality affects the Gumbel noise-to-signal ratio. A bold agent's higher rebel utility means the same Gumbel(0, T) noise has proportionally less influence — bold agents are more decisively rebellious (less stochastic), which is the correct behavior. Under option B (scaling internal weights), noise magnitude on a differently-sloped utility curve would couple personality to temperature sensitivity in non-obvious ways during M47 calibration.

### Effective Utility Ranges

At starting weights (0.3) and M32 CAPs:

| Action | Raw Cap | Bold/Ambitious (+1.0) | Cautious/Content (-1.0) | vs STAY_BASE |
|--------|---------|----------------------|------------------------|-------------|
| Rebel | 1.5 | 1.95 | 1.05 | Both > 0.5 — even cautious agents rebel under extreme distress |
| Migrate | 1.0 | 1.30 | 0.70 | Both > 0.5 — cautious agents still flee bad conditions |
| Switch | 0.6 | 0.78 | 0.42 | Content agent's 0.42 < 0.5 — inertia wins, content agents rarely switch. Correct. |

---

## Personality Assignment

### Civ Personality Mean (Python-Side)

Computed once per civ at world gen. Pure function of immutable civ data:

```python
VALUE_PERSONALITY_MAP = {
    # value → (boldness, ambition, loyalty_trait) contribution
    "Honor":     ( 0.15,  0.0,   0.0),
    "Freedom":   ( 0.15,  0.0,   0.0),
    "Cunning":   ( 0.0,   0.15,  0.0),
    "Knowledge": ( 0.0,   0.15,  0.0),
    "Tradition": ( 0.0,   0.0,   0.15),
    "Order":     ( 0.0,   0.0,   0.15),
}

DOMAIN_PERSONALITY_MAP = {
    # domain substring → (boldness, ambition, loyalty_trait) contribution
    "military": ( 0.10,  0.0,   0.0),
    "trade":    ( 0.0,   0.10,  0.0),
    "merchant": ( 0.0,   0.10,  0.0),
}

def civ_personality_mean(
    values: list[str], domains: list[str],
) -> tuple[float, float, float]:
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

Civ means are clamped to [-0.3, +0.3]. With per-agent noise σ=0.3, individual agents vary widely — a Tradition+Order civ has mean loyalty_trait = +0.3, so ~62% of agents have positive loyalty_trait. A clear statistical tendency, not determinism.

### CivSignals Extension

Civ means cross to Rust via `CivSignals` (in `signals.rs`), sent every tick alongside existing civ signal columns:

```rust
pub mean_boldness: f32,
pub mean_ambition: f32,
pub mean_loyalty_trait: f32,
```

Python computes once at world gen, passes every tick. Cost: 3 floats × ~24 civs = 288 bytes. The parallel demographics phase reads `signals.civs[civ_id].mean_boldness` etc. at birth time.

### Per-Agent Noise (Rust-Side)

```rust
fn assign_personality(rng: &mut ChaCha8Rng, civ_mean: [f32; 3]) -> [f32; 3] {
    let mut p = [0.0f32; 3];
    for i in 0..3 {
        let noise = rng.sample::<f32, _>(StandardNormal) * SPAWN_PERSONALITY_NOISE;
        p[i] = (civ_mean[i] + noise).clamp(-1.0, 1.0);
    }
    p
}
```

Uses `PERSONALITY_STREAM_OFFSET = 700` from the RNG stream registry.

### Spawn Flow

1. Python computes `civ_personality_mean(civ.values, civ.domains)` → 3 floats per civ
2. Python sends civ means in `CivSignals` Arrow columns every tick
3. At initial spawn: Rust `spawn()` receives 3 personality params (civ mean + noise, computed by caller)
4. At birth during tick: parallel demographics phase reads `signals.civs[civ_id]` means, calls `assign_personality(rng, civ_mean)`, stores result in `BirthInfo`
5. Sequential apply phase passes pre-computed personality to `pool.spawn()`
6. Personality is set — never written again

### Birth Path Integration

`BirthInfo` (in `tick.rs`) is extended to carry personality:

```rust
struct BirthInfo {
    region: u16,
    civ: u8,
    parent_loyalty: f32,
    personality: [f32; 3],  // pre-computed in parallel phase
}
```

The parallel phase (`tick_region_demographics`) has the per-region RNG. It calls `assign_personality(rng, civ_mean)` and stores the result in `BirthInfo`. The sequential apply phase passes the final values to `pool.spawn()` — no RNG needed in the sequential path.

When M39 lands, the parallel phase switches from `assign_personality(rng, civ_mean)` to `inherit_personality(rng, parent_personality)`. The parent's personality is accessible in the parallel phase (iterating over parent slots). `BirthInfo` carries the result the same way — a one-line swap.

### Birth Inheritance (M39 Forward-Compatible)

Implemented and unit-tested in M33, but not wired into the birth path until M39:

```rust
fn inherit_personality(rng: &mut ChaCha8Rng, parent: [f32; 3]) -> [f32; 3] {
    let mut p = [0.0f32; 3];
    for i in 0..3 {
        let noise = rng.sample::<f32, _>(StandardNormal) * BIRTH_PERSONALITY_NOISE;
        p[i] = (parent[i] + noise).clamp(-1.0, 1.0);
    }
    p
}
```

`BIRTH_PERSONALITY_NOISE = 0.15` — tighter than spawn noise (0.3). Children resemble parents but aren't copies.

### Pool.spawn() Signature

Extended to accept personality:

```rust
pub fn spawn(
    &mut self,
    region: u16,
    civ_affinity: u8,
    occupation: u8,
    age: u16,
    boldness: f32,
    ambition: f32,
    loyalty_trait: f32,
) -> usize
```

Existing call sites (tests, initial spawn) pass `0.0, 0.0, 0.0` until wired with real values. Both the free-slot reuse path and the grow path set personality fields from the parameters.

---

## Named Character Labels

### Label Derivation

Pure function of immutable personality — computed on-the-fly, not stored:

```rust
fn personality_label(boldness: f32, ambition: f32, loyalty_trait: f32) -> Option<&'static str> {
    let dims = [
        (boldness.abs(),      boldness,      "the Bold",      "the Cautious"),
        (ambition.abs(),      ambition,      "the Ambitious",  "the Humble"),
        (loyalty_trait.abs(), loyalty_trait,  "the Steadfast",  "the Fickle"),
    ];

    let (max_abs, raw, pos_label, neg_label) = dims
        .iter()
        .max_by(|a, b| a.0.partial_cmp(&b.0).unwrap())?;

    if *max_abs < 0.5 {
        return None; // neutral personality — no label
    }

    Some(if *raw > 0.0 { pos_label } else { neg_label })
}
```

- Threshold ±0.5 — only agents with a strong dominant dimension get a label
- Ties broken by iteration order (boldness > ambition > loyalty_trait) — rare for continuous values
- `None` → no personality epithet in narration

### Promotion RecordBatch

Four new columns in the promotion RecordBatch:

| Column | Type | Notes |
|--------|------|-------|
| `boldness` | `Float32` | Raw value for Python-side analytics |
| `ambition` | `Float32` | Raw value |
| `loyalty_trait` | `Float32` | Raw value |
| `personality_label` | `Utf8` (nullable) | Pre-computed label, null for neutral |

Note: `personality_label` introduces the first `Utf8` column in the promotion schema — use `StringBuilder` / `StringArray` (not a numeric builder).

### Snapshot RecordBatch

Three new columns in the full agent snapshot (`to_record_batch()`):

| Column | Type | Notes |
|--------|------|-------|
| `boldness` | `Float32` | Needed for Tier 3 validation and analytics |
| `ambition` | `Float32` | |
| `loyalty_trait` | `Float32` | |

The label is not included in the snapshot — it's derivable from the raw values and only meaningful for named characters.

### Narration Integration

The narrator receives the label as part of named character context:

> *Kiran the Bold (boldness: 0.82) led the rebellion in the mountain province...*

The label gives the narrator a character hook. The raw value is included for cases where the narrator wants to express degree.

---

## Constants

### New Constants (all `[CALIBRATE]` for M47)

| Constant | Value | Rationale |
|----------|-------|-----------|
| `BOLD_REBEL_WEIGHT` | 0.3 | At REBEL_CAP=1.5: bold effective max=1.95, cautious=1.05, both above STAY_BASE |
| `BOLD_MIGRATE_WEIGHT` | 0.3 | Symmetric with rebel weight as starting point |
| `AMBITION_SWITCH_WEIGHT` | 0.3 | At SWITCH_CAP=0.6: ambitious=0.78 > STAY_BASE, content=0.42 < STAY_BASE. Content agents rarely switch — correct. |
| `LOYALTY_TRAIT_WEIGHT` | 0.3 | Steadfast drift rate × 0.7, mercenary × 1.3 |
| `SPAWN_PERSONALITY_NOISE` | 0.3 | σ for N(0, σ) at spawn. Wide enough for individual variation; civ mean still detectable in population |
| `BIRTH_PERSONALITY_NOISE` | 0.15 | σ for N(0, σ) at birth (M39). Children resemble parents. |
| `PERSONALITY_LABEL_THRESHOLD` | 0.5 | Absolute dimension value above which a label is assigned |

### RNG Stream Registry Addition

```rust
pub const PERSONALITY_STREAM_OFFSET: u64 = 700;
```

Per the M32 registry. Spacing of 100 prevents collisions.

---

## Validation

Three tiers, following M32's validation pattern.

### Tier 1: Neutral Regression (Exact Match)

**Setup:** All agents personality [0,0,0]. Same world state as M32 tests.

**Assertion:** `PendingDecisions` from M33-augmented utility selection must match M32 output **exactly**. All modifiers = `1.0 + 0.0 * 0.3 = 1.0` — multiplication by 1.0 is identity.

**Tests:**
- Run 100 turns with all-zero personality. Compare `PendingDecisions` counts per action type against M32 baseline. Exact match required — not statistical, because the math is identical.
- Loyalty drift rate unchanged (modifier = `1.0 + 0.0 * 0.3 = 1.0`).

### Tier 2: Behavioral Correlation (Statistical)

**Setup:** Controlled personality, conditions in the marginal regime of the ReLU (not saturated).

**Why marginal regime matters:** If conditions are too extreme, both bold and cautious agents saturate at near-CAP utility. Both groups rebel at ~100%. The chi-squared test finds no significant difference — not because personality doesn't work, but because the test saturated both groups. Conditions must produce utility in the linear region (~0.3-0.8 before modifier).

**Test conditions:** Near-threshold satisfaction and loyalty (e.g., loyalty=0.15, satisfaction=0.15). Raw rebel utility ≈ 0.375 — below STAY_BASE for cautious agents (×0.7 = 0.26), above for bold agents (×1.3 = 0.49). This is the regime where personality actually tips marginal agents.

**Three independent tests, one per dimension:**

1. **Boldness → rebellion:** 10k agents, 5k boldness=+0.8, 5k boldness=-0.8, all other dimensions 0.0. 200 turns, multi-civ region, near-threshold conditions. Assert: bold cohort rebellion rate > cautious, p < 0.01 (chi-squared).
2. **Ambition → occupation switch:** Same structure. Near-equilibrium supply/demand so switch utility is in the linear region.
3. **Loyalty trait → drift rate:** Measure mean loyalty change per turn for steadfast vs mercenary cohorts. Assert: steadfast drift magnitude < mercenary, p < 0.01.

### Tier 3: Distribution Stability (Statistical)

**Setup:** Stable conditions — single civ controlling all regions, adequate satisfaction, no multi-civ regions, no rebellion triggers. Only demographic churn is age-dependent mortality (personality-independent) + birth replacement (uses civ means).

**Why stable conditions:** The test isolates birth-assignment stability from behavioral feedback loops. Bold agents rebel more (Tier 2 proves this); if rebellion carries mortality risk, surviving populations drift toward lower boldness. That's emergent selection pressure, not a bug — but it would fail the stability assertion. Personality-correlated survival effects are a M47 calibration concern, not an M33 correctness concern.

**Methodology:**
- Spawn 50k agents from a civ with mean [0.1, 0.1, 0.1] and σ=0.3
- Run 500 turns (births and deaths active, stable ecology)
- At turn 500, compute mean and σ of each personality dimension across living agents

**Assertions:**
- Mean within 0.05 of initial civ mean (0.1) per dimension
- σ within 0.05 of `SPAWN_PERSONALITY_NOISE` (0.3)

Validates that birth assignment (using civ means, not parent inheritance in M33) preserves population distribution under neutral conditions.

### What We're NOT Testing in M33

- Target re-ranking (deferred to M35a)
- Parent inheritance wiring (M39 — `inherit_personality` is unit-tested in isolation only)
- Cross-dimension interaction effects (boldness × ambition) — single-dimension isolation is sufficient; interaction is a M47 calibration concern
- Personality-correlated survival effects — a M47 concern, not a correctness concern

### Test Locations

- **Rust-side:** Tier 1 (neutral regression) and Tier 2 (behavioral correlation) as integration tests in `behavior.rs`
- **Python-side:** Tier 3 (distribution stability) as an analytics script using the snapshot RecordBatch personality columns

---

## File Changes

| File | Change | Lines (est.) |
|------|--------|-------------|
| `agent.rs` | Add 7 personality constants (4 weights, 2 noise σ, 1 label threshold) + `PERSONALITY_STREAM_OFFSET = 700` to stream registry | ~10 |
| `pool.rs` | Add 3 SoA fields (`boldness`, `ambition`, `loyalty_trait`). Extend `spawn()` with 3 personality params. Both free-slot and grow paths set personality. Add 3 Float32 columns to `to_record_batch()`. | ~40 |
| `behavior.rs` | Add `personality_modifier()`. Apply modifiers to rebel/migrate/switch utility outputs after cap, before Gumbel. Destructure `switch_utility` tuple before multiplying. Apply negated loyalty_trait modifier to drift rate. | ~20 |
| `tick.rs` | Expand `BirthInfo` with `personality: [f32; 3]`. Compute personality in parallel demographics phase via `assign_personality(rng, civ_mean)` reading civ means from `CivSignals`. Pass personality through to `pool.spawn()`. | ~25 |
| `signals.rs` | Add `mean_boldness`, `mean_ambition`, `mean_loyalty_trait` to `CivSignals`. Parse from Arrow columns. | ~15 |
| `demographics.rs` | Add `assign_personality()` and `inherit_personality()` functions. | ~20 |
| `ffi.rs` | Promotion RecordBatch: add `boldness`, `ambition`, `loyalty_trait` (Float32) + `personality_label` (Utf8 nullable) columns. Add `personality_label()` helper. | ~30 |
| `agent_bridge.py` | Add `civ_personality_mean()` with value/domain maps. Pass civ means in `CivSignals` Arrow columns. Pass personality in initial spawn RecordBatch. | ~40 |
| Tests (Rust) | Tier 1: neutral regression. Tier 2: 3 behavioral correlation tests. `assign_personality` / `inherit_personality` unit tests. `personality_modifier` edge cases. `personality_label` unit tests. | ~100 |
| Tests (Python) | Tier 3: distribution stability analytics script. | ~50 |

**Total:** ~200 lines Rust, ~50 lines Python, ~150 lines tests.

### What Doesn't Change

- `PendingDecisions` struct — same fields, same semantics
- M32 utility functions (`rebel_utility`, `migrate_utility`, `switch_utility`, `stay_utility`) — unchanged internals, personality applied externally
- `satisfaction.rs` — untouched (upstream of decisions)
- `region.rs` — no new region fields
- Narrator / curator — narrator receives label via promotion RecordBatch, no structural changes
- Bundle format — stays at `bundle_version: 1`

---

## Forward Dependencies

| Milestone | How M33 Enables It |
|-----------|-------------------|
| M34 (Regional Resources) | Per-occupation migration opportunity scores can be personality-weighted |
| M35a (Rivers & Trade) | Migration target re-ranking incorporates personality (bold → contested regions, ambitious → resource-rich). Consolidates personality + river + resource re-ranking in one pass. |
| M36 (Cultural Identity) | Cultural values cluster geographically influenced by agent personality distributions |
| M37 (Belief Systems) | Personality affects conversion likelihood (bold agents more likely to adopt new faiths) |
| M39 (Family & Lineage) | Personality inheritance from parent via `inherit_personality()`. Birth path switches from `assign_personality(rng, civ_mean)` to `inherit_personality(rng, parent_personality)` — one-line swap. |
| M40 (Social Networks) | Personality similarity affects social bond formation and strength |
| M47 (Tuning Pass) | Recalibrate 7 personality constants alongside M32's 10+ constants. Starting weights (0.3) and the effective utility range table provide M47's baseline. |
