# M49: Needs System — Design Spec

> **Status:** Draft. Phoebe design review (6 sections, 5 brainstorming questions with individual + holistic review).
>
> **Phase 7 Depth Track.** Second milestone after M48. Depends on: M48 (merged).
>
> **Scope:** 6 per-agent needs as f32 floats in the Rust SoA pool. Needs decay per tick, restore from conditions, and modify agent decision utilities. Needs do NOT modify satisfaction. Additive to existing systems — no restructuring of satisfaction, behavior, or demographics.

---

## 1. Storage Layout

### SoA Fields on AgentPool

6 new `Vec<f32>` fields, placed between the M48 memory block and the `alive` field in `pool.rs`:

```rust
// M49: Needs system (6 × f32 per agent)
pub need_safety: Vec<f32>,
pub need_material: Vec<f32>,
pub need_social: Vec<f32>,
pub need_spiritual: Vec<f32>,
pub need_autonomy: Vec<f32>,
pub need_purpose: Vec<f32>,
```

**Total new storage:** 24 bytes/agent. At 50K = 1.2MB. At 1M = 24MB. 10% of Phase 7 per-agent budget (242 bytes).

### Lifecycle

- **`spawn()`:** All 6 needs initialized to `STARTING_NEED = 0.5` inside spawn(), both reuse and grow branches. No spawn signature change — follows wealth/memory precedent of internal initialization.
- **`kill()`:** No explicit cleanup. Spawn overwrites all fields on slot reuse.

### Module Structure

New file: `chronicler-agents/src/needs.rs`. Contains decay, restoration, utility modifier computation, and FFI helper.

`lib.rs` gains `pub mod needs;` after `pub mod memory;`, with re-exports for integration tests.

### `--agents=off` Compatibility

Needs are Rust-only SoA fields. Not in the Arrow snapshot batch (`to_record_batch`), not in `compute_aggregates()`, not visible to Python analytics in aggregate mode. `--agents=off` output is bit-identical.

---

## 2. Need Definitions

6 needs, each an f32 in [0.0, 1.0]. 0.0 = completely unmet, 1.0 = fully met.

| Need | What it represents | Drain source | Restore source |
|------|--------------------|-------------|----------------|
| Safety | Physical security | War, disease, famine | Peace, health, adequate food |
| Material | Economic well-being | Constant decay | Wealth, food sufficiency |
| Social | Community connection | Constant decay | Population density, occupation (pre-M50 proxy) |
| Spiritual | Religious fulfillment | Constant decay | Temple, faith-majority alignment |
| Autonomy | Political freedom | Foreign occupation, persecution, displacement | Self-governance, no persecution |
| Purpose | Meaningful activity | Constant decay | Skilled work, active military service |

### Safety vs. Autonomy Distinction

These two needs have genuinely independent conditions grounded in different RegionState/CivSignals fields:

- **Safety** = physical threat. Drains from: `is_at_war` (CivSignals), `endemic_severity` (RegionState), `food_sufficiency < threshold` (RegionState). An unconquered warzone has Safety unmet, Autonomy met.
- **Autonomy** = political oppression. Drains from: `controller_civ != civ_affinity` (RegionState vs pool), `persecution_intensity` (RegionState), `displacement_turns > 0` (pool). A conquered peaceful region has Autonomy unmet, Safety met.

The "conquered-but-safe" state — Safety met, Autonomy unmet — is one of the most historically important simulation states. It drives occupation dynamics, diaspora formation, and liberation narratives.

### Autonomy and `civ_affinity` Semantics

`civ_affinity` (pool field) represents the agent's current political allegiance, which changes on loyalty flip. It is NOT an ethnic or origin marker. An agent who loyalty-flipped to the conqueror's civ feels autonomous under the new regime. This is the intended behavior — political Autonomy measures whether the agent lives under their *chosen* government, not where their ancestors came from. The assimilation feedback loop (unmet Autonomy → faster loyalty drift → flip resolves Autonomy) is historically correct.

If the loop proves too forgiving in M53, add `origin_region` distance as a secondary Autonomy condition.

---

## 3. Decay

### Uniform Linear Decay

All agents' needs decay at the same 6 constant rates per tick. No per-agent variation in decay. Differentiation comes entirely from restoration.

```rust
pub fn decay_needs(pool: &mut AgentPool, alive_slots: &[usize]) {
    for &slot in alive_slots {
        pool.need_safety[slot] = (pool.need_safety[slot] - SAFETY_DECAY).max(0.0);
        pool.need_material[slot] = (pool.need_material[slot] - MATERIAL_DECAY).max(0.0);
        pool.need_social[slot] = (pool.need_social[slot] - SOCIAL_DECAY).max(0.0);
        pool.need_spiritual[slot] = (pool.need_spiritual[slot] - SPIRITUAL_DECAY).max(0.0);
        pool.need_autonomy[slot] = (pool.need_autonomy[slot] - AUTONOMY_DECAY).max(0.0);
        pool.need_purpose[slot] = (pool.need_purpose[slot] - PURPOSE_DECAY).max(0.0);
    }
}
```

Decay is linear (constant subtraction). Restoration is proportional (see Section 4). The combination of linear decay + proportional restoration produces graceful equilibria — see Section 8.

### Why Uniform

Occupation-modified decay creates discontinuities on occupation switch (a merchant switching to soldier gets an instantaneous change in decay vector despite no change in actual conditions). Personality-modified decay creates bifurcated calibration surfaces and threshold sensitivity. Per-agent restoration (Section 4) provides the diversity engine. Uniform decay is the simple baseline that creates urgency uniformly.

If M53 calibration shows insufficient behavioral diversity with uniform decay + per-agent restoration, the response is richer restoration conditions, not per-agent decay modifiers.

### Decay Constants

| Constant | Need | Starting Value | Ticks 0.5→0.3 | Notes |
|----------|------|---------------|----------------|-------|
| `SAFETY_DECAY` | Safety | 0.015 | 13 | Fast — danger should feel immediate |
| `MATERIAL_DECAY` | Material | 0.012 | 17 | Moderate — material security is stickier |
| `SOCIAL_DECAY` | Social | 0.008 | 25 | Slowest — social bonds persist |
| `SPIRITUAL_DECAY` | Spiritual | 0.010 | 20 | Moderate |
| `AUTONOMY_DECAY` | Autonomy | 0.015 | 13 | Fast — political pressure is acute |
| `PURPOSE_DECAY` | Purpose | 0.012 | 17 | Moderate |

All `[CALIBRATE M53]`. All in `agent.rs`.

### Oscillation Mitigation

Linear decay + proportional restoration naturally dampens oscillation near equilibrium. As need approaches equilibrium from below, restoration weakens (proportional to `1 - need`) while decay stays constant. This prevents the sawtooth oscillation that linear-linear models produce at threshold boundaries. If oscillation is still observed at M53, add hysteresis on threshold detection.

---

## 4. Restoration

### Hybrid Proportional Restoration

All restoration is **proportional to the deficit** `(1.0 - need)`:

```rust
need += RESTORE_RATE * condition_value * (1.0 - need);
```

This creates diminishing returns — restoration is strong when need is low, weak when nearly full. Combined with linear decay, this produces stable equilibria (Section 8) and prevents needs from permanently clamping at 1.0 in peacetime.

Binary conditions (from bools on RegionState/CivSignals) contribute `RATE × (1.0 - need)` when true, 0 when false. Continuous conditions (from f32 fields) contribute `RATE × condition_value × (1.0 - need)`.

Each need has at least one **per-agent** condition that varies between agents in the same region, preventing needs from mirroring satisfaction.

### Per-Need Restoration Conditions

#### Safety

| Condition | Type | Source field | Rate formula |
|-----------|------|-------------|-------------|
| Not at war | Binary | `CivSignals.is_at_war` (for agent's civ) | `+SAFETY_RESTORE_PEACE` if false |
| Low disease | Continuous | `RegionState.endemic_severity` | `+SAFETY_RESTORE_HEALTH × (1.0 - endemic_severity).max(0.0)` |
| Adequate food | Continuous | `RegionState.food_sufficiency` | `+SAFETY_RESTORE_FOOD × food_sufficiency.min(1.5)` if > 0.8 |
| **Boldness (per-agent)** | Modifier | `pool.boldness[slot]` | All Safety restoration ×`(1.0 + boldness × BOLD_SAFETY_RESTORE_WEIGHT)` via `personality_modifier()` |

Bold agents shake off danger faster. Cautious agents need more sustained safety to feel secure.

#### Material

| Condition | Type | Source field | Rate formula |
|-----------|------|-------------|-------------|
| Food sufficient | Continuous | `RegionState.food_sufficiency` | `+MATERIAL_RESTORE_FOOD × food_sufficiency.min(1.5)` |
| **Wealth (per-agent)** | Continuous | `wealth_percentiles[slot]` | `+MATERIAL_RESTORE_WEALTH × wealth_pct` |

Wealthy agents feel materially secure even in moderate regions. Poor agents have persistent Material deficit.

**Note:** `wealth_percentiles` is a transient buffer passed to `tick_agents()`, not stored on pool. The `update_needs()` function receives it as a parameter, same as `update_satisfaction()`.

#### Social

| Condition | Type | Source field | Rate formula |
|-----------|------|-------------|-------------|
| Region populated | Continuous | `RegionState.population / carrying_capacity` | `+SOCIAL_RESTORE_POP × (pop as f32 / cap as f32).min(1.0)` if ratio > 0.3. Guard for cap == 0. |
| **Occupation (per-agent)** | Modifier | `pool.occupations[slot]` | Merchants: ×1.5, Priests: ×1.3 (inherently social occupations) |
| **Age (per-agent)** | Modifier | `pool.ages[slot]` | `× (age as f32 / 40.0).min(1.0)` — older agents have more established social connections |

**Pre-M50 proxy.** Social restoration lives behind an isolated `social_restoration()` function marked `// Pre-M50 proxy — replace with relationship count when M50 lands`. M50 swaps the implementation without changing the needs tick signature.

#### Spiritual

| Condition | Type | Source field | Rate formula |
|-----------|------|-------------|-------------|
| Temple present | Binary | `RegionState.has_temple` | `+SPIRITUAL_RESTORE_TEMPLE` if true |
| **Belief matches majority (per-agent)** | Binary | `pool.beliefs[slot]` vs `RegionState.majority_belief` | `+SPIRITUAL_RESTORE_MATCH` if equal AND `majority_belief != 0xFF` (BELIEF_NONE sentinel guard) |

Minority-faith agents restore Spiritual slower even in a temple region — the temple belongs to the wrong faith.

#### Autonomy

| Condition | Type | Source field | Rate formula |
|-----------|------|-------------|-------------|
| Self-governed | Binary | `RegionState.controller_civ == pool.civ_affinities[slot]` | `+AUTONOMY_RESTORE_SELF_GOV` if true |
| No persecution | Binary | `RegionState.persecution_intensity` | `+AUTONOMY_RESTORE_NO_PERSC` if == 0.0 |
| **Not displaced (per-agent)** | Gate | `pool.displacement_turns[slot]` | If > 0, ALL Autonomy restoration blocked regardless of other conditions |

Displacement completely suppresses Autonomy restoration. A recently migrated agent cannot feel autonomous regardless of political conditions.

#### Purpose

| Condition | Type | Source field | Rate formula |
|-----------|------|-------------|-------------|
| **Skilled work (per-agent)** | Continuous | `pool.skills[slot * 5 + occ]` | `+PURPOSE_RESTORE_SKILL × skill_level` |
| **Soldier at war (per-agent)** | Binary | `pool.occupations[slot] == 1` AND `CivSignals.is_at_war` | `+PURPOSE_RESTORE_WAR` if both true |

Purpose has no regional/civ conditions — it is the most internal need. A highly skilled scholar has Purpose; a novice farmer does not. A soldier at war has Purpose; a soldier in peacetime does not.

### Clamping

After decay and restoration: `need = need.clamp(0.0, 1.0)`.

### Equilibrium Documentation

With linear decay and proportional restoration, the equilibrium for each need:

At equilibrium: `D = R_total × (1 - eq)`, solving: `eq = 1 - D / R_total`.

Where `R_total` = sum of all active restoration rates (the rates multiply `(1 - need)` per tick), `D` = constant decay rate.

- When `R_total > D`: equilibrium above 0, need is partially met. Higher `R_total` → need closer to 1.0.
- When `R_total < D`: no positive equilibrium, need decays to 0.0 (crisis).
- When `R_total = D`: equilibrium at 0.0 (knife-edge, unlikely in practice).

Example: Safety with `SAFETY_DECAY = 0.015` and total restoration rate 0.037 in peacetime → `eq = 1 - 0.015/0.037 = 0.59` (well above threshold 0.3).

The constants table in Section 8 includes equilibrium estimates for typical peacetime and crisis scenarios.

---

## 5. Behavioral Effects

### Utility Modifier Architecture

Needs produce additive modifiers on the 4 decision utilities (rebel, migrate, switch, stay), following the M48 `MemoryUtilityModifiers` pattern:

```rust
pub struct NeedUtilityModifiers {
    pub rebel: f32,
    pub migrate: f32,
    pub switch_occ: f32,
    pub stay: f32,
}
```

### Threshold-Gated Formula

Each need contributes only when below its behavioral threshold:

```rust
let deficit = (THRESHOLD - need_value).max(0.0);
modifier += deficit * WEIGHT;
```

A need at 0.7 with threshold 0.3 produces zero effect. A need at 0.1 with threshold 0.3 produces `0.2 × WEIGHT`.

This matches the established pattern in `behavior.rs`: `rebel_utility` fires only below `REBEL_SATISFACTION_THRESHOLD = 0.2`, `migrate_utility` fires only below `MIGRATE_SATISFACTION_THRESHOLD = 0.3`.

### Need-to-Utility Mapping

| Need | Below threshold → affects | Rationale |
|------|--------------------------|-----------|
| Safety | **migrate** +, **stay** - | Flee danger |
| Material | **migrate** +, **switch_occ** + | Seek food/wealth, change to profitable work |
| Social | **stay** +, **migrate** - | Resist leaving populated areas |
| Spiritual | **migrate** + | Seek temple regions (propensity only in M49; destination scoring deferred to M53) |
| Autonomy | **rebel** +, loyalty drift accelerated | Resist political oppression |
| Purpose | **switch_occ** + | Change to meaningful work |

### Behavioral Weights

| Constant | Need | Starting Value | Max Contribution | Notes |
|----------|------|---------------|-----------------|-------|
| `SAFETY_WEIGHT` | Safety | 0.7 | 0.21 | Strong — physical danger drives flight |
| `MATERIAL_WEIGHT` | Material | 0.5 | 0.15 | Moderate |
| `SOCIAL_WEIGHT` | Social | 0.5 | 0.125 | Moderate — community holds agents |
| `SPIRITUAL_WEIGHT` | Spiritual | 0.4 | 0.12 | Gentler — spiritual seeking is subtle |
| `AUTONOMY_WEIGHT` | Autonomy | 0.8 | 0.24 | Strongest — political oppression drives rebellion |
| `PURPOSE_WEIGHT` | Purpose | 0.4 | 0.14 | Gentle nudge toward meaningful work |

Max contribution = `THRESHOLD × WEIGHT` (at full deficit, need = 0.0).

All `[CALIBRATE M53]`. Weights chosen to be competitive with existing additive modifiers: persecution direct boost 0.30 (M38b), memory persecution boost ~0.10 (M48).

### Behavioral Thresholds

| Constant | Need | Starting Value |
|----------|------|---------------|
| `SAFETY_THRESHOLD` | Safety | 0.3 |
| `MATERIAL_THRESHOLD` | Material | 0.3 |
| `SOCIAL_THRESHOLD` | Social | 0.25 |
| `SPIRITUAL_THRESHOLD` | Spiritual | 0.3 |
| `AUTONOMY_THRESHOLD` | Autonomy | 0.3 |
| `PURPOSE_THRESHOLD` | Purpose | 0.35 |

All `[CALIBRATE M53]`.

### Needs-Only Additive Modifier Cap

M49 needs modifiers are capped per utility channel. The existing M38b and M48 modifiers are uncapped (they work as shipped).

```rust
let needs_rebel = needs_mods.rebel.min(NEEDS_MODIFIER_CAP);
rebel_util += needs_rebel;
```

`NEEDS_MODIFIER_CAP = 0.30` `[CALIBRATE M53]`. Needs can add at most 0.30 to any single utility channel. This prevents needs from dominating while keeping them competitive with existing modifier sources. The cap applies only to M49 needs modifiers — persecution (M38b) and memory (M48) modifiers are not retroactively affected.

### Needs as Independent Trigger

Need-driven modifiers CAN push a utility above zero even when the base utility function returns 0.0. A "content but politically oppressed" agent (satisfaction 0.6, loyalty 0.5 — both above rebellion thresholds) with unmet Autonomy need gets `rebel_util = 0.0 + autonomy_modifier`. If the modifier is positive, the agent can rebel from Autonomy need alone.

**This is the intended behavior.** It is the whole point of distinguishing needs from satisfaction. Satisfaction measures "how am I doing?" — Autonomy need measures "what am I missing?" An agent who is materially comfortable but politically subjugated should be able to rebel.

M53 calibration target: needs-only rebellions (base rebel utility was zero) should be < 5% of total rebellions.

### Autonomy and Loyalty Drift

Unmet Autonomy need accelerates negative loyalty drift (toward civ flip). Applied as a multiplier on drift rate, affecting only the negative direction (not recovery):

```rust
let autonomy_deficit = (AUTONOMY_THRESHOLD - pool.need_autonomy[slot]).max(0.0);
let autonomy_factor = 1.0 + autonomy_deficit * AUTONOMY_DRIFT_WEIGHT;
let effective_drift = LOYALTY_DRIFT_RATE
    * personality_modifier(-ltrait, LOYALTY_TRAIT_WEIGHT)
    * autonomy_factor;
```

`AUTONOMY_DRIFT_WEIGHT = 2.0` `[CALIBRATE M53]`. At max deficit (0.3), drift rate increases by `0.3 × 2.0 = 0.6`, so total multiplier is 1.6×.

Flip threshold interaction is intentional: accelerated drift from unmet Autonomy can cause civ flips, which resolves the Autonomy need (agent's new civ_affinity matches controller). This models political assimilation under pressure.

### Negative Modifiers and the NEG_INFINITY Gate

Social need's `migrate -` modifier can push `migrate_util` below 0.0 even when the base is positive, causing it to be gated to `NEG_INFINITY`. This means strong community attachment can completely disable migration for agents who would otherwise flee. This is intentional — deeply rooted agents resist leaving even under pressure. Combined with M48's prosperity memory migrate penalty, agents can become migration-locked.

M53 monitoring target: agents with both strong Social need AND prosperity memories should not form permanent trapped populations in declining regions.

### Insertion Point in `behavior.rs`

After M48 memory modifiers, before NEG_INFINITY gates:

```
base utilities → personality modifiers → persecution boosts (M38b)
→ memory modifiers (M48) → NEED MODIFIERS (M49) → needs cap
→ NEG_INFINITY gate → gumbel_argmax
```

---

## 6. Tick Integration

### Tick Ordering

Needs update inserts between `wealth_tick` and `update_satisfaction` in `tick_agents()` (`tick.rs`). The insertion point is at lines 81-86 (no code between these two calls — clean gap).

```
M48 memory decay → skill growth → wealth_tick →
NEEDS DECAY + RESTORATION (M49) →
update_satisfaction → region stats → decisions →
apply decisions → demographics → culture → conversion →
M48 memory write
```

Needs read current-turn RegionState and CivSignals (set before Rust tick begins via Arrow batch). Decisions at the later step read the freshly-computed need values.

### Function Signature

```rust
pub fn update_needs(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    wealth_percentiles: &[f32],
) {
    let alive_slots: Vec<usize> = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s))
        .collect();
    // 1. Decay all 6 needs (linear subtraction, clamp to 0.0)
    decay_needs(pool, &alive_slots);
    // 2. Restore based on conditions (proportional to deficit: R * (1 - need))
    restore_needs(pool, &alive_slots, regions, signals, wealth_percentiles);
    // 3. Clamp to [0.0, 1.0] (restoration can't overshoot given proportional model, but defensive)
    clamp_needs(pool, &alive_slots);
}
```

`wealth_percentiles` is a transient buffer passed through `tick_agents()`, computed inside `wealth_tick()`. It is NOT stored on pool. The needs function receives it as a parameter, matching the pattern where `update_satisfaction` receives the same buffer. Dead agent slots in `wealth_percentiles` contain stale values — only read for alive agents.

### RNG

M49 needs tick is **fully deterministic** — no RNG consumption. Decay rates are constants, restoration conditions are deterministic reads from RegionState/CivSignals/pool fields. Stream offset 1000 reserved but unused. If a future milestone adds stochastic need events, offset 1400+ is available (existing highest: `MULE_STREAM_OFFSET = 1300`).

---

## 7. FFI & Narration

### FFI Exposure

New PyO3 method on `AgentSimulator`, following the M48 `get_agent_memories()` pattern:

```rust
fn get_agent_needs(&self, agent_id: u32) -> Option<(f32, f32, f32, f32, f32, f32)> {
    // O(N) scan for agent_id — acceptable for ~5-15 named character queries/turn
    // Returns (safety, material, social, spiritual, autonomy, purpose)
    // None if agent not found or dead
}
```

### GreatPerson Field

New field on `GreatPerson` in `models.py`:

```python
needs: dict = Field(default_factory=dict)  # cached from Rust via FFI
```

Synced in `AgentBridge.tick()` hybrid branch, immediately after the memory sync (lines 504-513):

```python
# M49: Sync needs for active named characters
raw_needs = self._sim.get_agent_needs(gp.agent_id)
if raw_needs is not None:
    gp.needs = {
        "safety": raw_needs[0], "material": raw_needs[1],
        "social": raw_needs[2], "spiritual": raw_needs[3],
        "autonomy": raw_needs[4], "purpose": raw_needs[5],
    }
```

### Narrator Context

When any need is below its behavioral threshold, the narrator receives it in the character context block. Satisfied needs are listed briefly (not omitted) so the narrator can see contrast — "content but spiritually adrift" requires knowing the agent IS content.

```python
NEED_DESCRIPTIONS = {
    "safety": "feels unsafe",
    "material": "wants for material comfort",
    "social": "is isolated",
    "spiritual": "is spiritually adrift",
    "autonomy": "chafes under foreign rule",
    "purpose": "lacks a sense of purpose",
}
```

Placed in `narrative.py` after `MEMORY_DESCRIPTIONS`.

Example narrator context:
```
Character: General Kiran (the Bold)
Needs: Safety satisfied, Material satisfied, Social LOW (0.18),
       Spiritual satisfied, Autonomy LOW (0.12), Purpose satisfied
  - is isolated
  - chafes under foreign rule
```

Only below-threshold needs get descriptive strings. This is a deliberate departure from M48's "omit the uninteresting" memory pattern — for needs, the narrator should see both the contentment and the deficit to create dramatic tension.

---

## 8. Constants Registry

### Complete Inventory

**Decay (6 constants):**

| Constant | Starting Value | `[CALIBRATE M53]` |
|----------|---------------|-|
| `SAFETY_DECAY` | 0.015 | |
| `MATERIAL_DECAY` | 0.012 | |
| `SOCIAL_DECAY` | 0.008 | |
| `SPIRITUAL_DECAY` | 0.010 | |
| `AUTONOMY_DECAY` | 0.015 | |
| `PURPOSE_DECAY` | 0.012 | |

**Behavioral thresholds (6 constants):**

| Constant | Starting Value | `[CALIBRATE M53]` |
|----------|---------------|-|
| `SAFETY_THRESHOLD` | 0.3 | |
| `MATERIAL_THRESHOLD` | 0.3 | |
| `SOCIAL_THRESHOLD` | 0.25 | |
| `SPIRITUAL_THRESHOLD` | 0.3 | |
| `AUTONOMY_THRESHOLD` | 0.3 | |
| `PURPOSE_THRESHOLD` | 0.35 | |

**Behavioral weights (6 constants):**

| Constant | Starting Value | Max Contribution | `[CALIBRATE M53]` |
|----------|---------------|------------------|-|
| `SAFETY_WEIGHT` | 0.7 | 0.21 | |
| `MATERIAL_WEIGHT` | 0.5 | 0.15 | |
| `SOCIAL_WEIGHT` | 0.5 | 0.125 | |
| `SPIRITUAL_WEIGHT` | 0.4 | 0.12 | |
| `AUTONOMY_WEIGHT` | 0.8 | 0.24 | |
| `PURPOSE_WEIGHT` | 0.4 | 0.14 | |

**Restoration rates (~30 constants):**

| Constant | Need | Starting Value | Notes |
|----------|------|---------------|-------|
| `SAFETY_RESTORE_PEACE` | Safety | 0.020 | Binary: not at war |
| `SAFETY_RESTORE_HEALTH` | Safety | 0.010 | Continuous: (1 - endemic_severity) |
| `SAFETY_RESTORE_FOOD` | Safety | 0.008 | Continuous: food_sufficiency if > 0.8 |
| `BOLD_SAFETY_RESTORE_WEIGHT` | Safety | 0.3 | Per-agent: boldness modifier weight |
| `MATERIAL_RESTORE_FOOD` | Material | 0.012 | Continuous: food_sufficiency |
| `MATERIAL_RESTORE_WEALTH` | Material | 0.015 | Per-agent: wealth_percentile |
| `SOCIAL_RESTORE_POP` | Social | 0.010 | Continuous: pop/cap ratio |
| `SOCIAL_RESTORE_POP_THRESHOLD` | Social | 0.3 | Pop/cap ratio below which no restoration |
| `SOCIAL_MERCHANT_MULT` | Social | 1.5 | Per-agent: merchant occupation multiplier |
| `SOCIAL_PRIEST_MULT` | Social | 1.3 | Per-agent: priest occupation multiplier |
| `SPIRITUAL_RESTORE_TEMPLE` | Spiritual | 0.020 | Binary: has_temple |
| `SPIRITUAL_RESTORE_MATCH` | Spiritual | 0.015 | Per-agent: belief == majority_belief (with BELIEF_NONE guard) |
| `AUTONOMY_RESTORE_SELF_GOV` | Autonomy | 0.020 | Binary: controller_civ == civ_affinity |
| `AUTONOMY_RESTORE_NO_PERSC` | Autonomy | 0.010 | Binary: persecution_intensity == 0 |
| `PURPOSE_RESTORE_SKILL` | Purpose | 0.020 | Per-agent: skill_level in current occupation |
| `PURPOSE_RESTORE_WAR` | Purpose | 0.015 | Per-agent: soldier + civ at war |

**Infrastructure (3 constants):**

| Constant | Starting Value | Notes |
|----------|---------------|-------|
| `NEEDS_MODIFIER_CAP` | 0.30 | Max needs-only additive modifier per utility channel |
| `AUTONOMY_DRIFT_WEIGHT` | 2.0 | Multiplier on loyalty drift from Autonomy deficit |
| `STARTING_NEED` | 0.5 | Spawn value for all 6 needs |

**Total: ~51 constants.** All in `agent.rs`. All `[CALIBRATE M53]`.

**Comparison:** M48 added 39 calibratable constants. M49 adds ~51. Combined Rust-side calibration surface for M53: ~90 constants.

### Equilibrium Estimates

Under typical conditions. Formula: `eq = 1 - D / R_total` (linear decay, proportional restoration). Crisis conditions where all restoration drops to zero produce `eq → 0.0`.

| Need | D | R_total (peacetime) | Peacetime eq | Crisis R_total | Crisis eq | Threshold |
|------|---|--------------------|--------------|-|-|-----------|
| Safety | 0.015 | 0.037 (peace + health + food, neutral bold) | 0.59 | 0.008 (food only, at war + disease) | 0.00 (D > R) | 0.30 |
| Material | 0.012 | 0.027 (good food + median wealth) | 0.56 | 0.005 (famine, poor) | 0.00 (D > R) | 0.30 |
| Social | 0.008 | 0.015 (populated, farmer age 30) | 0.47 | 0.004 (depopulated, young) | 0.00 (D > R) | 0.25 |
| Spiritual | 0.010 | 0.035 (temple + majority faith) | 0.71 | 0.000 (no temple, minority) | 0.00 | 0.30 |
| Autonomy | 0.015 | 0.030 (self-governed, no persecution) | 0.50 | 0.000 (conquered, persecuted, displaced) | 0.00 | 0.30 |
| Purpose | 0.012 | 0.035 (skilled + soldier at war) | 0.66 | 0.008 (unskilled, peacetime) | 0.00 (D > R) | 0.35 |

These are approximate. Exact values depend on per-agent modifiers (boldness, wealth percentile, occupation, age, belief alignment). Peacetime eq should sit comfortably above threshold. Crisis eq should sit below threshold to trigger behavioral effects. All `[CALIBRATE M53]`.

---

## 9. Tiered Calibration Strategy (M53)

### Tier 1: Decay Rates (6 constants)

Set once. Validate via half-life measurement: how many ticks from 0.5 to threshold under continuous decay with no restoration?

**Target:** 15-30 ticks to reach behavioral threshold from neutral spawn (0.5).

### Tier 2: Thresholds + Weights (12 constants)

Calibrate with estimated restoration rates. For each need, manually set one agent below threshold with all others above, measure behavioral shift.

**Target:** Need-triggered action should be 10-20% more likely than baseline (not 2×, not invisible). Use 200-seed runs, compare action distributions for agents with one need below threshold vs. agents with all needs met.

### Tier 3: Restoration Conditions (~30 constants)

Calibrate via population statistics: run 200 seeds, measure "need activation fraction" — what % of agents have each need below threshold?

**Duty cycle targets per need:**

| Need | Peacetime activation | Crisis activation |
|------|---------------------|-------------------|
| Safety | < 5% | 30-50% (contested regions) |
| Material | 10-15% (poor agents) | 40-60% (famine) |
| Social | 15-20% (young, isolated) | 30-40% (depopulated) |
| Spiritual | 10-15% (minority faith, no temple) | 50-70% (conquest conversion) |
| Autonomy | 5-10% (displaced, minority) | 60-80% (conquered population) |
| Purpose | 15-25% (unskilled, peacetime soldiers) | 20-30% (stable) |

**Cross-need target:** In peacetime, 10-20% of agents should have at least one need below threshold. In crisis, 40-70%.

### Restoration Sufficiency Check

After Tier 3 calibration: do agents with identical occupation, region, and satisfaction produce measurably different need profiles? If no, the per-agent restoration conditions are not providing sufficient diversity. Response: add more per-agent conditions or increase per-agent modifier weights. Do NOT add per-agent decay — that path was evaluated and rejected (Section 3, Q3).

---

## 10. M53 Calibration Flags

| Flag | Target | Source |
|------|--------|--------|
| Persecution triple-stacking | M38b direct + M48 memory + M49 Autonomy all push rebel/migrate | Q1 Phoebe review |
| Famine double-counting | M48 famine memory migrate boost + M49 Material need migrate boost | Q2 Phoebe review |
| Needs-only rebellion rate | < 5% of total rebellions should be needs-triggered (base utility = 0) | Holistic Phoebe review |
| Need activation fraction | Peacetime 10-20%, crisis 40-70% | Holistic Phoebe review |
| Migration sloshing | Single-destination herding amplified by need-driven migration cohorts | Q5 Phoebe review |
| Sawtooth oscillation | Linear decay + restoration oscillation at threshold boundary | Section 5 Phoebe review |
| Duty cycle per need | Safety ~30% unmet in contested, ~5% peaceful (see Section 9 targets) | Section 5 Phoebe review |
| Social proxy adequacy | Pre-M50 proxy (occupation + age + population) vs actual relationship signal | Q2 Phoebe review |
| Negative modifier trapping | Social + prosperity memory can migration-lock agents in declining regions | Section 3 Phoebe review |
| Autonomy assimilation loop | Unmet Autonomy → drift → flip → Autonomy restored (may be too forgiving) | Section 2 Phoebe review |

---

## 11. Scope

### In Scope

- 6 SoA f32 fields on AgentPool (`needs.rs`, `pool.rs`)
- Uniform decay per tick (`needs.rs`)
- Hybrid restoration with per-agent conditions (`needs.rs`)
- Threshold-gated utility modifiers in `behavior.rs` (rebel/migrate/switch/stay)
- Loyalty drift acceleration from Autonomy need
- Needs-only additive modifier cap
- `get_agent_needs()` FFI method (`ffi.rs`)
- `GreatPerson.needs` field and sync (`models.py`, `agent_bridge.py`)
- `NEED_DESCRIPTIONS` and narrator context rendering (`narrative.py`)
- ~51 constants in `agent.rs`

### Excluded (deferred)

- **Migration destination modification** — needs only boost propensity to migrate, not where to go. Need-weighted regional attractiveness (option C from Q5) deferred to M53 if migration patterns lack diversity.
- **Memory → needs coupling** — needs read current-turn conditions only, not M48 memory state. Memory-needs interaction deferred to M53 after independent calibration.
- **Satisfaction formula changes** — needs modify decisions, NOT satisfaction. The Rust satisfaction formula is unchanged.
- **Arrow snapshot batch changes** — needs not included in `to_record_batch()` or `compute_aggregates()`.
- **New RNG streams** — fully deterministic. Stream offset 1000 reserved but unused.
- **Per-agent decay variation** — evaluated and rejected. Diversity from restoration.
- **`--agents=off` changes** — needs are Rust-only, invisible in aggregate mode.

---

## 12. File Map

### New Files

| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/needs.rs` | NeedUtilityModifiers struct, decay, restoration, utility modifier computation, update_needs entry point |
| `chronicler-agents/tests/test_needs.rs` | Rust unit/integration tests |
| `tests/test_needs.py` | Python integration tests (--agents=off invariant, narration rendering) |

### Modified Files

| File | Changes |
|------|---------|
| `chronicler-agents/src/lib.rs` | Add `pub mod needs;` + re-exports |
| `chronicler-agents/src/agent.rs` | ~51 need constants after M48 memory block |
| `chronicler-agents/src/pool.rs` | 6 SoA fields, spawn init, new() capacity |
| `chronicler-agents/src/tick.rs` | Insert `update_needs()` call between wealth_tick and update_satisfaction |
| `chronicler-agents/src/behavior.rs` | Need utility modifiers after M48 memory modifiers, needs-only cap, Autonomy drift acceleration |
| `chronicler-agents/src/ffi.rs` | `get_agent_needs()` pymethod |
| `src/chronicler/models.py` | `GreatPerson.needs` field |
| `src/chronicler/agent_bridge.py` | Needs sync in hybrid branch after memory sync |
| `src/chronicler/narrative.py` | `NEED_DESCRIPTIONS`, `render_needs()`, needs context in `build_agent_context_block()` |

---

## 13. Phoebe Review Observations

Items flagged during the 6-section Phoebe design review. Not blocking — documented for implementer and M53 awareness.

1. **Persecution `is_at_war` lookup path.** Safety restoration reads `is_at_war` from CivSignals. The spec should clarify: look up via agent's own `civ_affinity`, not via `controller_civ`. A conquered agent whose civ is at war but whose region controller is at peace should have Safety unmet.

2. **`personality_modifier()` visibility.** The boldness modifier on Safety restoration should use the existing `personality_modifier()` function from `behavior.rs`. This function is currently private (`fn`, not `pub fn`). Implementation must make it `pub fn` or extract to a shared utility. Centralizes the convention.

3. **Purpose has no regional condition.** Intentional — Purpose is the most internal need. If M53 shows Purpose is too disconnected from external events, add a regional condition at that point.

4. **Constants count update.** The Phase 7 roadmap (line 179) estimates ~24 M49 constants. Actual count is ~51. Update the roadmap when M49 implementation begins.

5. **Equilibrium estimates are approximate.** They depend on per-agent modifier stacking and should be verified numerically during M53 Tier 3 calibration, not trusted as spec-time calculations.
