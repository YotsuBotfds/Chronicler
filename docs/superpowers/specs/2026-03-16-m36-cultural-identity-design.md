# M36: Cultural Identity

> **Status:** Design approved. Ready for implementation planning.
>
> **Depends on:** M34 (regional resources & seasons) for environmental bias coupling. M33 (agent personality) for SoA pool layout. M16 (memetic warfare) for existing culture.py functions being replaced/modified.
>
> **Scope:** Per-agent cultural values with drift, environmental shaping, and agent-driven assimilation replacing timer-based culture flipping. ~200-300 lines Rust, ~100-150 lines Python, ~250 lines tests.

---

## Overview

M16 introduced civ-level cultural values (Freedom, Order, Tradition, Knowledge, Honor, Cunning) and memetic warfare. Culture operates as a civ-level declaration — agents don't have individual values, and cultural assimilation flips on a 15-turn timer (`foreign_control_turns >= 15`).

M36 pushes cultural identity down to individual agents. Each agent carries 3 ranked cultural values that drift based on regional cultural pressure, environmental shaping, and named character influence. The timer-based assimilation check is replaced with an agent-driven threshold: a region assimilates when 60% of its agents hold the controller's primary value. This creates bottom-up cultural dynamics — conquest destabilizes culture, trade routes create cosmopolitan border regions, and named characters shape the values of the population around them.

**Design principle:** Cultural values are discrete identities, not continuous traits. An agent "holds Honor" or doesn't — there is no "partial Honor." Variation comes from the 3-slot structure (agents can hold different combinations) and from population-level distributions (a region where 70% hold Honor is more culturally cohesive than one where values are evenly split). M33 personality provides the continuous noise; M36 cultural identity provides the discrete social fabric.

---

## Design Decisions

### 3 Ranked Value Slots Per Agent

Each agent carries up to 3 cultural value indices as `u8`, drawn from the M16 VALUES enum (Freedom=0, Order=1, Tradition=2, Knowledge=3, Honor=4, Cunning=5). Slots are ordered by salience: slot 1 is the agent's primary identity, slot 3 is peripheral.

**Why 3, not 1:** Partial cultural overlap. Two agents sharing 2 of 3 values are culturally closer than agents sharing 0. This gives cultural distance a gradient (0/3, 1/3, 2/3, 3/3 overlap) rather than binary match/mismatch. Drift operates per-slot — an agent in an occupied region adopts one foreign value in slot 3 while retaining their core identity in slots 1-2. Gradual cultural erosion, not sudden flips.

**No duplicate values across an agent's 3 slots.** Each slot holds a distinct enum index. This keeps distance well-defined (range 0–3) and avoids degenerate {Honor, Honor, Honor} agents.

**Matches the civ-level pattern.** Civs already have multi-value identities. Agents inheriting the same structure means the assimilation check can compare per-slot distributions naturally.

### Cultural Distance = Set Intersection

```
distance(agent_a, agent_b) = 3 - |values_a ∩ values_b|
```

Slot-position-agnostic. Two agents with {Honor, Knowledge, Tradition} and {Knowledge, Tradition, Freedom} have distance 1. Cheap to compute in Rust — three equality checks with short-circuit on overlap count.

### Slot-Weighted Drift Resistance (3:2:1)

Drift probability multiplier per slot: slot 3 drifts at base rate, slot 2 at 2/3×, slot 1 at 1/3×. If `CULTURAL_DRIFT_RATE` is 0.06/tick, slot 3 has a 6% chance of shifting per tick, slot 2 has 4%, slot 1 has 2%.

Primary identity is stickier than peripheral values. A merchant on a trade route picks up cosmopolitan values in slot 3 long before their primary identity shifts.

### Region-Level Frequency Distribution for Drift

Drift target is NOT sampled from individual agents. Instead, a per-region value frequency count `[u16; 6]` is recomputed from scratch at the start of each culture tick — one linear pass over the region's agents. Named agents contribute 5× weight to the distribution (a famous poet doesn't influence culture through random encounters; they influence it by being famous).

**Why recompute, not maintain incrementally:** Migration (decisions phase), births/deaths (demographics phase), and drift itself all mutate the population. Maintaining a consistent incremental count across three phases is a consistency bug waiting to happen. A linear scan of contiguous `u8` values in SoA layout is microseconds.

**Why not per-agent sampling (O(n²)):** The abstraction is wrong. Culture spreads as ambient regional pressure, not agent-to-agent contagion. The frequency distribution is the natural data structure for "what cultural values are prevalent in this region."

### Resource-Driven Environmental Bias

Environmental shaping injects phantom weight into the frequency distribution for terrain-appropriate values, even when no agents currently hold them. The land "teaches" culture.

**Sparse mapping (14 nonzero entries out of 48):**

| Resource | Primary Bias | Secondary Bias | Rationale |
|----------|-------------|----------------|-----------|
| GRAIN | Tradition | Order | Agrarian societies: seasonal cycles, collective labor |
| TIMBER | Tradition | — | Settlement-building, land management |
| BOTANICALS | Knowledge | Cunning | Herbalism, medicine, trade in rare goods |
| FISH | Freedom | Cunning | Maritime mobility, trade contact, opportunism |
| SALT | Cunning | Freedom | Trade commodity, mercantile culture |
| ORE | Honor | Order | Mining discipline, martial application |
| PRECIOUS | Cunning | Knowledge | Wealth-seeking, craftsmanship |
| EXOTIC | Freedom | Knowledge | Long-distance trade, cosmopolitan contact |

**Phantom weight magnitude:** Capped at ~5% of region population. In a 200-agent region, terrain bias for Honor from ORE counts as roughly 10 phantom agents. Dominant signal in culturally cleared post-conquest regions (the land reasserts itself). Whisper against a homogeneous population.

**Slot-weighted resource bias:** Only the primary resource (slot 1) contributes full environmental bias. Slot 2 at 0.5×, slot 3 at 0.25×. Primary resource dominates regional cultural character. A mountain mining region with secondary fish gets a hint of maritime culture, but ORE's Honor/Order dominates.

**Multi-resource regions get union of biases, slot-weighted — not stacking.** This prevents diffuse "everything" bias in rich regions.

### Initial Assignment: Civ Inheritance

Agents spawned in a civ's territory copy that civ's values directly. If the civ has 2 values, slot 3 is filled from a weighted pool: neighboring civ values weighted by disposition, with fallback to random.

**Why not seeded variation:** M33 already solved intra-civ variation for personality via continuous noise. Cultural values are discrete enum indices — "noisy Honor" doesn't exist. Probabilistic variation on discrete categories creates agents with entirely different values from day one, which is a much stronger claim than slight personality variation. Drift creates variation within 20-30 turns via narratively meaningful mechanics (border contact, trade, conquest). Day-one random variation has no story behind it. Initial coherence also validates cleanly: turn 0, all agents in civ X hold civ X's values. Any deviation is the result of simulation mechanics.

### Assimilation: 60% Agent-Driven Threshold

A region's `cultural_identity` flips when 60% of its agents hold the controller's **primary value (slot 1)** in **any of their own 3 slots**.

- Keys on the controller's core identity — what makes them *them*
- Counts partial adoption (an agent with the controller's primary in their slot 3 counts)
- Harder bar than "any overlap" but softer than "must be in agent's slot 1"
- Produces emergent dynamics: a region at 55% can be tipped by `INVEST_CULTURE` actions

**Guard clause:** Don't check the 60% threshold until `foreign_control_turns >= 5`. Prevents flickering on brief occupations and avoids wasted distribution scans every turn for freshly contested regions.

**Post-assimilation:** Flip and done. The 40% minority continues drifting naturally. No consolidation pressure. The minority is emergent content — a powder keg for secession (M14), faction struggles (M22), and religious schism (M38b). The 60% majority exerts ongoing drift pressure; in stable regions the minority converges. In contested border regions it doesn't — and that's the interesting case.

**Event emission:** The assimilation flip is a significant state change. Emit through existing curator pipeline (one-line addition if not already emitted on `cultural_identity` change).

### Satisfaction Penalty: Cultural Mismatch

Cultural mismatch = distance between agent's values and controlling civ's values. Linear gradient within a -0.15 budget:

- Distance 0: no penalty (agent fully aligned with controller)
- Distance 1: -0.05 (minor mismatch, one foreign value)
- Distance 2: -0.10 (significant mismatch)
- Distance 3: -0.15 (total cultural alienation)

**Computed inline in satisfaction.rs.** The distance computation (9 equality checks for overlap count, one subtraction, one multiply) reads agent's `cultural_values` from the pool and `controller_values` from signals. Per-agent reads from contiguous SoA arrays — doesn't compromise the branchless spirit.

**Compare against controller's values, not region's cultural identity.** Agent in foreign-controlled region compares against the controller. Agent in own civ's territory has distance 0 by definition (skip the check). The edge case where region identity diverges from controller identity is a M40+ concern.

### Decision 10: Non-Ecological Satisfaction Penalty Cap

Total non-ecological penalties (cultural mismatch + future religious mismatch + future persecution) capped at **-0.4**. Wired at M36 as infrastructure — only cultural mismatch exists initially, but the cap, the `min()` on summed penalties, and the subtraction from base satisfaction all go in now. M37 and M38b add terms to the sum without touching cap logic.

```rust
// M36: wire penalty infrastructure
let cultural_penalty = cultural_distance as f32 * CULTURAL_MISMATCH_WEIGHT;
// M37 will add: let religious_penalty = ...;
// M38b will add: let persecution_penalty = ...;
let total_penalty = (cultural_penalty /* + future terms */).min(PENALTY_CAP);
let satisfaction = (base_satisfaction - total_penalty).clamp(0.0, 1.0);
```

**Why cap on sum, not individual terms:** If M47 tuning reduces cultural mismatch to -0.10, that frees -0.05 for religious or persecution without touching cap logic. The budget is communal. The cap prevents future milestones from accidentally blowing past -0.4 even if individual weights are miscalibrated.

**Intentional emergent behaviors:**

1. **Home-civ drift penalty.** An agent who picked up a foreign value through trade contact has distance 1 against their own controller. They feel -0.05 *at home*. Narratively correct: a cosmopolitan merchant who adopted foreign customs doesn't quite fit in. Trade brings economic benefit but cultural friction. Verify in M47 that the effect doesn't cascade.

2. **Occupier asymmetry.** Civ A's garrison agents in a conquered Civ B region compare against Civ A (the controller) — no penalty. They feel at home in a culturally hostile region. Defensible as institutional comfort. M40 social networks can add a "surrounded by foreigners" term later.

---

## Tick Architecture

### Phase Placement: 6th Rust Tick Phase

The culture drift tick runs as phase 6, after demographics:

```
skill → satisfaction → stats → decisions → demographics → culture_drift
```

**Why after demographics, not before satisfaction:** Mutation ordering guarantees. Each existing phase reads state set by a prior phase (this tick) or carried from last tick. No phase reads state that a later phase will mutate. Culture drift reads satisfaction (computed phase 2) and the frequency distribution (affected by migration in phase 4 and demographics in phase 5). Satisfaction reads cultural values from *last turn*. This makes the one-turn staleness explicit and uniform.

### Data Flow

```
Python → Rust (per-region signals, Arrow columns):
  resource_types[3], resource_yields[3]     (M34, existing)
  culture_investment_active: bool            (new — set in Phase 8 action engine)
  controller_values: [u8; 3]                 (new — padded with 0xFF for <3 values)

Rust culture_tick (phase 6 of tick):
  1. Recompute frequency [u16; 6] from region's agents
     - Named agents (is_named bit set) contribute NAMED_CULTURE_WEIGHT (5×)
  2. Add environmental bias from resource_types (sparse table, slot-weighted)
     - Phantom weight = population × ENV_BIAS_FRACTION (~0.05)
  3. Per-agent drift:
     - Slot-weighted probability: slot 3 = base, slot 2 = 2/3×, slot 1 = 1/3×
     - Dissatisfied agents drift faster (satisfaction < threshold → bonus probability)
     - If culture_investment_active: bonus weight to controller_values in distribution
     - Sample new value from distribution (excluding agent's current value in that slot)
     - Post-drift validation: no duplicate values across slots
  4. RNG: seeded deterministically per region+turn, separate stream from decisions

Rust → Python (via existing snapshot RecordBatch):
  cultural_values columns already in snapshot from SoA
  Python computes its own distribution for the assimilation check
  No new output columns needed
```

**INVEST_CULTURE signal lifetime:** Selected in Phase 8 (action engine), consumed in Rust tick between Phase 9-10. Same pattern as M27 `DemandSignals` — set in action resolution, consumed in Rust tick.

### culture.py Replacement

Three distinct functions change:

| Function | Change | Reads |
|----------|--------|-------|
| `tick_cultural_assimilation()` | Timer → 60% agent-driven | Per-civ cultural profile + controller slot-1 |
| `apply_value_drift()` | Civ-level → bottom-up aggregate | Per-civ cultural profile |
| INVEST_CULTURE handler | Direct mutation → signal flag | — (writes flag only) |
| `compute_civ_cultural_profile()` | **New helper** | Agent snapshot |

**`tick_cultural_assimilation()` — replacement, not modification.** Current: timer-based flip (`foreign_control_turns >= 15`). New: read agent cultural distribution from snapshot, check if 60% hold controller's slot-1 value in any slot. If yes, flip `cultural_identity`. The `foreign_control_turns >= 5` guard prevents flickering.

**`apply_value_drift()` — modified.** Current: civ-level disposition effects from value overlap between civs. New: reads per-civ cultural profile aggregated from agents. "What fraction of civ A's population shares any values with civ B's population?" A civ that conquered culturally diverse territory gets a messier aggregate profile, affecting diplomacy. Military expansion has a diplomatic cost through cultural dilution.

**`compute_civ_cultural_profile()` — new helper.** Computes `dict[int, Counter[u8]]` from the agent snapshot — per-civ value frequency across all regions. Called once at start of Phase 6 (Culture), passed to both `apply_value_drift()` and `tick_cultural_assimilation()`. One scan of the snapshot, two consumers.

**INVEST_CULTURE handler — modified.** No longer directly mutates cultural state. Sets `culture_investment_active = True` in the region's signals for the Rust tick. Same Python-actions → signal-flags → Rust-consumption pattern from M27.

**Snapshot timing:** Phase 6 (Culture) runs before the Rust tick (Phase 9-10). `compute_civ_cultural_profile()` reads the snapshot from the *previous* turn's Rust tick, which includes last turn's drift results. One-turn lag, consistent with the mutation ordering guarantee.

---

## Data Model

### Rust-Side SoA Extensions (pool.rs)

New fields in the agent pool:

```rust
// Cultural values — 3 ranked slots, distinct enum indices
pub cultural_value_0: Vec<u8>,   // Primary (stickiest, 1/3× drift rate)
pub cultural_value_1: Vec<u8>,   // Secondary (2/3× drift rate)
pub cultural_value_2: Vec<u8>,   // Tertiary (base drift rate)
```

**`is_named` bit:** Packed into spare bits of existing `life_events: u8` field. Set on named character promotion via Python bridge. Read during culture tick frequency computation (5× weight contribution). Composes with M40 social networks.

**Pool size growth:** +3 bytes per agent (58 → 61 bytes).

### Rust-Side Signal Extensions (signals.rs)

New per-region signal columns in Arrow RecordBatch:

```rust
culture_investment_active: bool,  // INVEST_CULTURE action this turn
controller_values: [u8; 3],       // Controlling civ's cultural values, 0xFF = empty slot
```

### New Rust Module: culture_tick.rs

Contains:
- `ENV_BIAS_TABLE: [[f32; 6]; 8]` — sparse resource→value bias table (14 nonzero entries)
- `fn compute_cultural_distribution(pool, region_agents, named_weight) → [u16; 6]`
- `fn apply_environmental_bias(dist, resource_types, resource_slot_weights, population) → [u16; 6]`
- `fn drift_agent(agent_idx, pool, distribution, drift_rate, slot_weights, rng) → bool`
- `fn culture_tick(pool, region_state, signals, rng)` — orchestrates phase 6

### Python-Side: No Model Changes

Cultural values live in the Rust agent pool, not in Python models. Python reads them from the snapshot RecordBatch when needed (assimilation check, civ profile aggregation). No new fields on Region or Civilization models.

### Constants

All `[CALIBRATE]` for M47:

| Constant | Default | Purpose |
|----------|---------|---------|
| `CULTURAL_DRIFT_RATE` | 0.06 | Base per-tick drift probability (applied to slot 3) |
| `DRIFT_SLOT_WEIGHTS` | [1/3, 2/3, 1.0] | Per-slot drift probability multiplier |
| `CULTURAL_MISMATCH_WEIGHT` | 0.05 | Per-distance-unit satisfaction penalty (× distance = total) |
| `PENALTY_CAP` | 0.40 | Max total non-ecological satisfaction penalty |
| `ASSIMILATION_THRESHOLD` | 0.60 | Fraction of agents holding controller's primary value to flip |
| `ASSIMILATION_GUARD_TURNS` | 5 | Min foreign_control_turns before checking threshold |
| `NAMED_CULTURE_WEIGHT` | 5 | Named character multiplier in frequency distribution |
| `ENV_BIAS_FRACTION` | 0.05 | Environmental phantom weight as fraction of region population |
| `ENV_SLOT_WEIGHTS` | [1.0, 0.5, 0.25] | Resource slot contribution to environmental bias |
| `DISSATISFIED_DRIFT_BONUS` | 0.03 | Extra drift probability when satisfaction < 0.4 |
| `INVEST_CULTURE_BONUS` | 0.10 | Extra drift weight toward controller values during investment |

---

## Validation

### Tier 1: Structural Unit Tests (Must Pass)

| Test | Verifies |
|------|----------|
| Distance computation: all 10 cases (0/3 through 3/3, order-independence) | Set intersection logic |
| Slot-weighted drift: 10K rolls at each slot, ratio within ±10% of 3:2:1 | Probability multiplier wiring |
| No-duplicate invariant: drift never produces {A, A, B} | Post-drift validation |
| Penalty cap: cultural=0.15 + future_terms=0.30 → clamped to 0.40 | Budget infrastructure |
| Zero-penalty neutral: all agents match controller → penalty=0.0, satisfaction identical to pre-M36 | **Critical.** Exact match, not statistical. |
| Env bias sparse table: each resource type produces correct bias vector | Table lookup |
| Named character 5× weight: distribution with 1 named agent ≈ 5 unnamed agents | Influence multiplier |
| `is_named` bit: set on promotion, survives tick, readable in satisfaction | SoA field lifecycle |
| Initial assignment: agents match civ values in slots 1-2, slot 3 from neighbor pool, no duplicates | World-gen contract |

### Tier 2: Regression Harness (200 Seeds × 200 Turns, Must Pass Tolerances)

| Test | Tolerance | Verifies |
|------|-----------|----------|
| Assimilation timing: occupied regions flip within 40-80 turns (median) | ±20 turns | Agent-driven assimilation produces reasonable timelines |
| INVEST_CULTURE acceleration: cultural investment assimilates 30-50% faster than organic | ±15% | Signal propagation + drift bonus |
| Satisfaction regression: with `--agents=off`, culture phase output bit-identical to pre-M36 | Exact | Aggregate mode untouched |
| Economy regression: treasury, trade, action distribution within ±10% of baseline | ±10% | Satisfaction penalty doesn't cascade into economic destabilization |
| `compute_civ_cultural_profile()` consistency: profile from snapshot matches direct agent query | Exact | Helper correctness |

The assimilation timing test is the critical regression. M16's timer flips at 15 turns. Agent-driven assimilation with slot-weighted drift should be slower (40-80 turns) because tertiary values drift first, then secondary, then primary — and the 60% check keys on the primary value appearing anywhere. If median assimilation is <30 turns, drift rate is too high. If >100 turns, INVEST_CULTURE becomes mandatory rather than strategic.

### Tier 3: Characterization (200 Seeds × 500 Turns, Documented Report)

No pass/fail — generates data for M47 calibration.

| Metric | What It Reveals |
|--------|-----------------|
| Geographic clustering: Moran's I spatial autocorrelation | Border regions more diverse than interior |
| Environmental correlation: per-resource-type value frequency | Mining regions trend Honor, coastal regions Freedom |
| Named character influence: drift rate in regions with/without named characters | Effect size of 5× weight |
| Cultural minority persistence: post-assimilation minority fraction after 100 additional turns | Convergence rate of the 40% residual |
| Satisfaction distribution shift: pre/post M36 histograms | Mean shift and variance change from mismatch penalties |

Report output: `docs/superpowers/analytics/m36-cultural-identity-report.md`. M47 reads this for calibration targets.

---

## File Changes

| File | Change | Lines (est.) |
|------|--------|-------------|
| `pool.rs` | Add `cultural_value_0/1/2: Vec<u8>`, pack `is_named` into `life_events` spare bits | ~25 |
| `culture_tick.rs` | **New module.** Frequency distribution, env bias, per-agent drift, orchestration | ~180 |
| `tick.rs` | Add phase 6 call to `culture_tick()` | ~10 |
| `satisfaction.rs` | Inline cultural distance computation, penalty cap infrastructure, subtraction from base | ~50 |
| `signals.rs` | Add `culture_investment_active`, `controller_values` to signal parsing | ~15 |
| `ffi.rs` | Extend RecordBatch schema with cultural value columns + new signal columns | ~20 |
| `lib.rs` | Module export for `culture_tick` | ~2 |
| `culture.py` | Replace `tick_cultural_assimilation()`, modify `apply_value_drift()`, add `compute_civ_cultural_profile()` | ~100 |
| `agent_bridge.py` | Add `culture_investment_active` and `controller_values` to signal columns | ~15 |
| `action_engine.py` | INVEST_CULTURE handler sets signal flag instead of direct mutation | ~10 |
| Tests (Rust) | Tier 1 unit tests for distance, drift, penalty cap, env bias | ~120 |
| Tests (Python) | Tier 1 initial assignment + Tier 2 regression harness | ~130 |

**Total:** ~200-300 lines Rust (production), ~125 lines Python (production), ~250 lines tests.

### What Doesn't Change

- `models.py` — cultural values live in Rust pool, not Python models
- `ecology.py` — resource/ecology mechanics unchanged
- `politics.py` — secession/federation mechanics unchanged (read cultural_identity, which still exists)
- `simulation.py` — turn loop phase ordering unchanged
- Bundle format — stays at current version
- `--agents=off` mode — culture phase output bit-identical to pre-M36

---

## Forward Dependencies

| Milestone | How M36 Enables It |
|-----------|-------------------|
| M37 (Belief Systems) | Adds `belief: u8` to agent pool. Religious mismatch penalty wires into the same satisfaction penalty sum with the cap M36 established. Religion drift can reuse the frequency distribution pattern. |
| M38a (Temples & Clergy) | Clergy faction influence on cultural drift — named clergy characters get cultural weight through the `is_named` mechanism. |
| M38b (Schisms & Persecution) | Persecution penalty uses the penalty cap budget. Cultural minorities (the 40% post-assimilation) become targets. Cultural distance feeds persecution targeting. |
| M39 (Family & Lineage) | Family members share cultural values — inheritance at birth uses parent values, not civ values. |
| M40 (Social Networks) | Cultural similarity as edge weight in social graphs. The `is_named` bit enables social influence calculations. "Surrounded by foreigners" penalty can use the frequency distribution. |
| M47 (Tuning Pass) | All `[CALIBRATE]` constants tuned here. Tier 3 report provides calibration targets. Assimilation timing band tightened from ±20 to ±10. |
