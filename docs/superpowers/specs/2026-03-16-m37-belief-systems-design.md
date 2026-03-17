# M37: Belief Systems & Conversion

> **Status:** Design approved. Ready for implementation planning.
>
> **Depends on:** M36 (cultural identity) for penalty cap infrastructure, SoA pool layout with cultural values, and culture_tick stage pattern. M33 (agent personality) for BirthInfo struct and spawn parameter pattern. M32 (utility decisions) for satisfaction-driven behavior.
>
> **Scope:** Per-agent religious belief with event-driven conversion, culture-biased doctrine generation, holy war gradient, and satisfaction penalty. ~150-200 lines Rust, ~200-250 lines Python, ~250 lines tests.

---

## Overview

M36 adds per-agent cultural values that drift passively through ambient regional pressure — an agent absorbs the culture around them by living in a region. M37 adds a mechanically distinct religion system where beliefs are **stable by default**. An agent's `belief: u8` does not change unless an explicit trigger fires: priest presence, satisfaction-driven seeking, conquest conversion, or named character influence.

The distinction is intentional. Culture is the water that slowly erodes identity. Religion is the fire that someone has to light. Passive ambient drift produces a world where every multi-faith region homogenizes within 100 turns — that's culture again with different labels. Event-driven conversion creates durable religious minorities that persist until active pressure (missionaries, conquest, desperation) erodes them through narratable causes.

Each civilization starts with one faith, generated at world-gen with doctrines biased by the civ's cultural values. Doctrines are a Python-only lookup table (max 16 faiths × 5 axes). Rust never sees doctrines — Python pre-computes per-region conversion parameters, and Rust executes the per-agent probability rolls. This follows the M27 pattern: Python handles complex lookups, Rust handles hot per-agent loops.

**Design principle:** Beliefs are discrete identity, not continuous tendency. An agent holds faith A or faith B — there is no "partially converted." Variation comes from population-level distributions (a region that is 70% faith A and 30% faith B has religious tension; a region at 100% faith A does not). Conversion triggers create the transitions; demographics (parent inheritance) maintain minorities. The interplay between durable minorities and event-driven conversion is where M37's emergent behavior lives.

---

## Design Decisions

### Event-Driven Conversion, Not Ambient Drift

Religious conversion does not use M36's frequency-distribution ambient pressure model. People don't passively absorb a new faith from proximity. They convert because someone is actively working to convert them, because they're seeking meaning in hardship, because the state imposes it, or because a charismatic figure inspires them.

Beliefs are stable by default. An agent's `belief: u8` changes only when one of five triggers fires:

| Trigger | Mechanism | Rate Driver |
|---------|-----------|-------------|
| **Priest presence** | Regions with priest-occupation agents of a foreign faith have a per-tick conversion probability | Priest ratio in region |
| **Proselytizing doctrine** | Faiths with Proselytizing doctrine double outbound conversion rate; Insular faiths double resistance | Doctrine modifier baked into conversion_rate |
| **Satisfaction-driven seeking** | Agents below satisfaction threshold have elevated susceptibility ("seeking meaning in hardship") | Agent's own satisfaction state |
| **Conquest conversion** | Holy war victory forces immediate flip for 30% of population; non-militant conquest elevates priest conversion for 10 turns | Conquest type (militant vs non-militant) |
| **Named character influence** | Named prophet/priest character in a region multiplies conversion rate | Same pattern as M36 named character weight, but event-driven |

**No new action type.** The strategic lever is indirect: civs that produce more priests (via satisfaction, occupation distribution, faction dynamics from M22) spread faith faster. You don't click "spread religion" — you create conditions that produce priests.

**Key mechanical difference from M36:**

| | Culture (M36) | Religion (M37) |
|---|---|---|
| Default state | Slow drift toward regional majority | Stable — no change without trigger |
| Spread mechanism | Ambient frequency distribution | Priest-driven conversion events |
| Strategic lever | INVEST_CULTURE action | Priest production (indirect) |
| Named character role | Weight in frequency distribution | Conversion rate multiplier |
| Satisfaction interaction | Dissatisfied agents drift faster | Dissatisfied agents more susceptible |

### Hybrid Tick Architecture (Python Computes, Rust Rolls)

Neither pure-Rust nor pure-Python. Python pre-computes per-region conversion parameters using doctrine lookups, priest counts, and conquest state. Rust executes the per-agent probability rolls.

**Why not pure-Rust:** Rust would need the belief registry, doctrine table, priest-per-faith counts, named character faith, and conquest state. That replicates Python's domain model inside Rust — violates Decision 6 (Python-primary computation for complex lookups).

**Why not pure-Python:** No efficient write-back path. The M27 bridge pattern is Python sends region-level signals → Rust mutates agents → Python reads snapshot. Converting agents from Python means either per-agent `set_agent_belief()` FFI calls (O(n) FFI overhead, breaks the pattern) or batching changes for next tick (one-turn delay).

**Signal surface (3 values per region):**

| Signal | Type | Computed From |
|--------|------|---------------|
| `conversion_rate` | `f32` | Priest ratio × doctrine modifier × named character bonus. **0.0 = no conversion pressure** (Rust skips region entirely) |
| `conversion_target_belief` | `u8` | Dominant converting faith — the faith with the most priests of a foreign faith in the region |
| `conquest_conversion_active` | `bool` | Holy war victory flag — triggers 30% forced flip |

**Dominant-faith-only conversion.** A region with priests of faith A and faith B both trying to convert: the faith with the most priests wins the conversion slot. Minority faith's priests are drowned out. Historically defensible (dominant religious institutions suppress minority proselytizing) and mechanically simple. Multi-faith competition is M38b territory (schisms and persecution).

### Culture-Biased Doctrine Generation

Doctrine axes correlate with civ cultural values via weighted probability, not deterministic mapping. A civ with Honor as primary value is more likely to get Militant, not guaranteed. The correlation creates coherent civilizations; the noise creates occasional surprises (the Honor culture with an Ascetic pacifist faith — warrior monks who renounced violence).

**Why not random:** Random doctrines produce incoherent civilizations. A Freedom/Cunning maritime trading civ with a Militant/Hierarchical/Insular faith has no internal logic. The narrator can't make sense of it.

**Why not geography-influenced:** Geography already shapes culture (M36's environmental bias), and culture influences doctrine. Adding a direct geography→doctrine path creates double-counting. Let culture be the mediating layer.

**Bias table (weighted, not deterministic):**

| Cultural Value | Doctrine Bias | Weight |
|---|---|---|
| Honor | Militant (+1 Stance) | 0.6 |
| Freedom | Egalitarian (+1 Structure), Proselytizing (+1 Outreach) | 0.4 each |
| Order | Hierarchical (-1 Structure), Monotheism (-1 Theology) | 0.4 each |
| Tradition | Insular (-1 Outreach), Ascetic (-1 Ethics) | 0.4 each |
| Knowledge | Hierarchical (-1 Structure) | 0.5 |
| Cunning | Prosperity (+1 Ethics), Proselytizing (+1 Outreach) | 0.4 each |

**Generation algorithm:**

1. Start with all 5 axes at 0 (neutral).
2. For each of the civ's cultural values (up to 3), roll each biased axis against its weight. Success → set to the biased pole.
3. For any remaining neutral axes, 20% chance of random assignment (-1 or +1). Most stay 0.
4. Result: 2-3 non-neutral axes on average, culturally biased but not determined.

**Fixed registry in M37.** No new faiths emerge during simulation. The faith count is fixed after world-gen. Schisms (M38b) add dynamic faith creation with proper causality — a faith splits when doctrinal tension within a multi-cultural civ exceeds a threshold. Allowing new faiths in M37 without schism mechanics means either random emergence (narratively empty) or threshold-based splitting (which IS the schism system, implemented early).

### Holy War Gradient

All inter-faith wars have a religious dimension. The question is how much. Restricting holy war to Militant-doctrine-only creates a world where Pacifist faiths can conquer territories and the conquered population's religion is mechanically untouched.

**Gradient by attacker doctrine:**

| Condition | Conquest Conversion Rate | Narrative Frame |
|---|---|---|
| Militant attacker, different faith | 30% immediate flip | Holy war — forced conversion |
| Non-militant attacker, different faith | 0% immediate flip, elevated priest conversion rate for 10 turns | Secular conquest with religious friction |
| Same faith | 0% | No religious dimension |

**Militant holy war:** `conquest_conversion_active = True` signal → Rust does the 30% roll. Then the 10-turn conversion boost applies to the remaining 70%.

**Non-militant inter-faith conquest:** No forced flip. Python sets `conquest_conversion_boost: f32` on the Region model, decays linearly over 10 turns, added to base `conversion_rate` each turn.

**WAR weight modifier (Militant-only):**

```python
if attacker.civ_majority_faith != target.civ_majority_faith:
    if attacker_militant:
        war_weight += 0.15  # holy war bonus
    defender_stability += 5  # righteous defense (universal)
```

The +0.15 WAR weight makes Militant-doctrine civs actively *seek* inter-faith war. The +5 defender stability is universal — any faith feels righteous defending against foreign religion. Non-militant civs don't seek war for religious reasons; they impose religion after winning wars started for other reasons.

**`civ_majority_faith: u8`** computed per civ once per turn — most common belief among that civ's agents. One pass over the agent snapshot, computed alongside M36's `compute_civ_cultural_profile()`.

### Binary Satisfaction Penalty (Inline Rust)

Religious mismatch penalty is per-agent: agent's belief vs region's majority belief. Binary (match/mismatch), not gradient (unlike M36's cultural distance 0-3).

```rust
// M37: religious mismatch (added to M36's penalty sum)
let religious_penalty = if agent_belief != region.majority_belief {
    RELIGIOUS_MISMATCH_WEIGHT  // 0.10 [CALIBRATE]
} else {
    0.0
};
let total_penalty = (cultural_penalty + religious_penalty /* + M38b persecution */).min(PENALTY_CAP);
```

**Why binary, not doctrine-distance:** Doctrine similarity affects *conversion resistance* (Python-side), not *satisfaction penalty* (Rust-side). An agent surrounded by a different faith feels the same mismatch whether the doctrines are similar or opposite. You either share the faith or you don't.

**Budget within M36's penalty cap (-0.40):**

| Term | Max | Source |
|------|-----|--------|
| Cultural mismatch (M36) | -0.15 | Distance 3 × 0.05 |
| Religious mismatch (M37) | -0.10 | Binary mismatch |
| Persecution (M38b, future) | -0.15 | Remaining budget |
| **Total cap** | **-0.40** | M36 infrastructure |

**`majority_belief: u8`** added to RegionState, computed Python-side from agent belief distribution, written into region update RecordBatch alongside `controller_civ`. Serves both satisfaction (Rust reads it) and conversion logic (Python uses it to determine which faith is dominant).

### Parent Belief Inheritance

Newborn agents inherit their parent's belief via `BirthInfo`. One `u8` read from `pool.beliefs[parent_idx]` during demographics birth path construction.

**Why not region majority or civ majority:** Both erase religious minorities at the demographic level. If a conquered region is 60% faith A and 40% faith B, majority-based inheritance means every baby is faith A — within 50 turns of population replacement, faith B is extinct through a data model shortcut, not through conversion, persecution, or any narratable cause. Parent inheritance creates persistent minorities that convert only through the five event-driven triggers.

**BirthInfo extension:**

```rust
struct BirthInfo {
    region: u16,
    civ: u8,
    parent_loyalty: f32,
    personality: [f32; 3],  // M33
    belief: u8,             // M37: copied from parent
    // M39 will add: parent_id: u32
}
```

**Initial spawn at world-gen:** No parents exist. Python passes the civ's `faith_id` via spawn signals. All initial agents share their civ's founding faith.

---

## Tick Architecture

### Phase Placement: Rust Tick Stage 6

Conversion runs as Rust tick stage 6, after M36's culture drift (stage 5):

```
Rust tick stages (internal, not Python phases):
  0: skill → 1: satisfaction → 2: stats/decisions → 3: apply decisions → 4: demographics → 5: culture_drift (M36) → 6: conversion (M37)
```

Culture drift and conversion are independent per-agent operations on different SoA fields (`cultural_values` vs `belief`). Sequential stages, not merged. Clear separation means M47 can reason about each system's rates independently.

Note: The current codebase has stages 0-4. M36 adds stage 5 (culture_drift). M37 adds stage 6 (conversion).

### Data Flow

```
Python signal computation (Phase 10, before Rust tick):
  For each region:
    1. Count priests per faith from agent snapshot
    2. Identify dominant foreign faith (most priests of non-majority faith)
    3. Look up doctrine modifiers (Proselytizing 2×, Insular target 0.5×)
    4. Check for named prophet/priest characters (2× multiplier)
    5. Add conquest_conversion_boost if active (decays linearly over 10 turns)
    6. Compute final conversion_rate:
       conversion_rate = BASE_RATE × priest_ratio × doctrine_mod × named_char_mod + conquest_boost
       If no foreign-faith priests and no conquest boost: conversion_rate = 0.0

Python → Rust (per-region batch, build_region_batch in agent_bridge.py):
  conversion_rate: f32              (0.0 = skip region)
  conversion_target_belief: u8     (dominant converting faith)
  conquest_conversion_active: bool  (Militant holy war flag)
  majority_belief: u8              (for satisfaction, reused from distribution computation)

Rust conversion tick (stage 6):
  for each region where conversion_rate > 0.0:
    for each agent in region:
      if agent.belief == conversion_target_belief: skip
      probability = conversion_rate
      if agent.satisfaction < SUSCEPTIBILITY_THRESHOLD: probability *= SUSCEPTIBILITY_MULTIPLIER
      if conquest_conversion_active: probability = CONQUEST_CONVERSION_RATE  // override
      roll RNG → if hit: agent.belief = conversion_target_belief
  RNG: seeded deterministically per region+turn, separate stream from decisions and culture drift

Rust → Python (via existing snapshot RecordBatch):
  beliefs column from SoA pool (no new output columns needed beyond adding beliefs to snapshot)
  Python reads snapshot to compute majority_belief, civ_majority_faith for next turn
```

**Satisfaction reads existing stage-1 output.** Conversion in stage 6 reads `agent.satisfaction` computed in stage 1. No extra signal needed. The satisfaction value reflects *last turn's* belief state (one-turn staleness), consistent with M36's cultural penalty pattern.

### Python-Side Computation: Phase 10 (Consequences)

Three new computations in Phase 10, alongside M36's `compute_civ_cultural_profile()`:

| Computation | Output | Consumers |
|-------------|--------|-----------|
| `compute_majority_belief(snapshot)` | `dict[int, u8]` per region | Region batch signal, satisfaction |
| `compute_civ_majority_faith(snapshot)` | `u8` per civ stored on Civilization | Action engine WAR weight (Phase 5 next turn) |
| `compute_conversion_signals(regions, beliefs, doctrines)` | Per-region `(rate, target, conquest_active)` | Region batch for Rust tick |

One pass over the snapshot produces both majority_belief (per region) and civ_majority_faith (per civ). `compute_conversion_signals()` reads these plus doctrine table and priest counts to produce the three Rust signals.

### Conquest Conversion Boost Lifecycle

When a territory changes hands via WAR action (resolved in Phase 5):

1. Python checks: is the attacker's `civ_majority_faith` different from the region's `majority_belief`?
2. If different and attacker is Militant: set `conquest_conversion_active = True` on next Rust tick signal.
3. If different and attacker is non-Militant: set `region.conquest_conversion_boost = CONQUEST_BOOST_RATE` on the Region model.
4. Each turn, `compute_conversion_signals()` adds `conquest_conversion_boost` to the region's `conversion_rate`, then decays it: `boost -= CONQUEST_BOOST_RATE / CONQUEST_BOOST_DURATION`.
5. After `CONQUEST_BOOST_DURATION` turns, boost reaches 0.0 and stops contributing.

The `conquest_conversion_active` flag is one-shot: set for the first tick after conquest, then cleared. The 30% forced flip happens once. The ongoing boost (for both Militant and non-Militant inter-faith conquest) handles the remainder.

---

## Data Model

### Rust-Side SoA Extension (pool.rs)

New field in the agent pool:

```rust
pub beliefs: Vec<u8>,  // 1 byte per agent, indexes into Python-side belief_registry
```

**Pool size growth:** +1 byte per agent.

**spawn() extension:** Add `belief: u8` parameter. Initial agents receive civ's `faith_id` from Python. Birth agents receive parent's belief from BirthInfo.

### Rust-Side Region Batch Extensions (region.rs / ffi.rs)

New columns in the per-region Arrow RecordBatch (parsed into RegionState):

```rust
conversion_rate: f32,              // 0.0 = no conversion pressure (skip)
conversion_target_belief: u8,      // dominant converting faith
conquest_conversion_active: bool,   // Militant holy war forced flip
majority_belief: u8,               // for satisfaction comparison
```

### Python-Side: Belief Registry

New dataclass and WorldState field:

```python
class Belief(BaseModel):
    faith_id: int          # 0-15, index into registry
    name: str              # generated at world-gen
    civ_origin: int        # which civ founded this faith
    doctrines: list[int]   # length 5: [Theology, Ethics, Stance, Outreach, Structure]
                           # each -1, 0, or +1
```

```python
# On WorldState
belief_registry: list[Belief] = Field(default_factory=list)  # max 16, fixed after world-gen in M37
```

**Doctrine axis ordering:** Theology (-1 Mono/+1 Poly), Ethics (-1 Ascetic/+1 Prosperity), Stance (-1 Pacifist/+1 Militant), Outreach (-1 Insular/+1 Proselytizing), Structure (-1 Hierarchical/+1 Egalitarian).

### Python-Side: Civilization Extension

New field on Civilization model:

```python
civ_majority_faith: int = 0  # computed from agent snapshot each turn
```

### Python-Side: Region Extension

New field on Region model:

```python
conquest_conversion_boost: float = 0.0  # decays linearly over CONQUEST_BOOST_DURATION turns
```

### Python-Side: Constants for Doctrine Indices

```python
DOCTRINE_THEOLOGY = 0
DOCTRINE_ETHICS = 1
DOCTRINE_STANCE = 2
DOCTRINE_OUTREACH = 3
DOCTRINE_STRUCTURE = 4

# Doctrine values
POLE_NEGATIVE = -1  # Monotheism, Ascetic, Pacifist, Insular, Hierarchical
POLE_NEUTRAL = 0
POLE_POSITIVE = 1   # Polytheism, Prosperity, Militant, Proselytizing, Egalitarian
```

### Rust-Side: New Module (conversion_tick.rs)

Contains:

- `fn conversion_tick(pool, region_state, rng)` — orchestrates stage 6
- Per-agent conversion roll with satisfaction susceptibility check
- Conquest conversion override (30% probability when `conquest_conversion_active`)
- Region-skip optimization (when `conversion_rate == 0.0`)

### Constants

All `[CALIBRATE]` for M47:

| Constant | Default | Location | Purpose |
|----------|---------|----------|---------|
| `BASE_CONVERSION_RATE` | 0.03 | Python | Base per-tick conversion probability before modifiers |
| `PROSELYTIZING_MULTIPLIER` | 2.0 | Python | Outbound rate multiplier for Proselytizing doctrine |
| `INSULAR_RESISTANCE` | 0.5 | Python | Rate multiplier when target faith is Insular |
| `NAMED_PROPHET_MULTIPLIER` | 2.0 | Python | Conversion rate multiplier for named priest/prophet in region |
| `SUSCEPTIBILITY_THRESHOLD` | 0.4 | Rust | Satisfaction below this → elevated conversion susceptibility |
| `SUSCEPTIBILITY_MULTIPLIER` | 2.0 | Rust | Susceptibility bonus multiplier |
| `CONQUEST_CONVERSION_RATE` | 0.30 | Rust | Forced flip probability on Militant holy war |
| `CONQUEST_BOOST_RATE` | 0.05 | Python | Initial conversion boost after non-militant inter-faith conquest |
| `CONQUEST_BOOST_DURATION` | 10 | Python | Turns for conquest boost to decay to 0 |
| `RELIGIOUS_MISMATCH_WEIGHT` | 0.10 | Rust | Satisfaction penalty for belief ≠ majority_belief |
| `HOLY_WAR_WEIGHT_BONUS` | 0.15 | Python | WAR action weight bonus for Militant vs different faith |
| `HOLY_WAR_DEFENDER_STABILITY` | 5 | Python | Stability bonus for any faith defending against different faith |
| `DOCTRINE_BIAS_RANDOM_CHANCE` | 0.20 | Python | Chance of random doctrine on unbiased axes at world-gen |

---

## Validation

### Tier 1: Structural Unit Tests (Must Pass)

| Test | Verifies |
|------|----------|
| Doctrine generation: 1000 faiths for Honor-primary civ, Militant frequency ≈ 0.6 ± 0.05 | Culture-bias weight table |
| Doctrine generation: average 2-3 non-neutral axes per faith | Generation algorithm produces expected density |
| Conversion tick: region with `conversion_rate == 0.0` produces zero belief changes | Skip optimization |
| Conversion tick: 10K agents, conversion_rate = 1.0 → all non-target agents convert | Basic conversion wiring |
| Satisfaction penalty: agent belief == majority_belief → penalty = 0.0 | Match case |
| Satisfaction penalty: agent belief != majority_belief → penalty = RELIGIOUS_MISMATCH_WEIGHT | Mismatch case |
| Penalty cap: cultural=0.15 + religious=0.10 → total=0.25, under cap | Budget accounting |
| Penalty cap: cultural=0.15 + religious=0.10 + future=0.20 → clamped to 0.40 | Cap enforcement |
| Birth inheritance: newborn belief == parent belief | BirthInfo wiring |
| Initial spawn: world-gen agents all hold civ's faith_id | World-gen contract |
| Conquest conversion: conquest_conversion_active=true → ~30% of agents flip (statistical, ±5%) | Forced flip probability |
| Susceptibility: agents below threshold convert at 2× rate (statistical, 10K rolls) | Satisfaction gating |
| Dominant-faith-only: region with 2 converting faiths, only dominant faith converts | Signal computation |
| `majority_belief` computation: known distribution → correct majority | Aggregation |
| `civ_majority_faith` computation: known agent distribution → correct per-civ majority | Aggregation |

### Tier 2: Regression Harness (200 Seeds × 200 Turns, Must Pass Tolerances)

| Test | Tolerance | Verifies |
|------|-----------|----------|
| Proselytizing spread rate: Proselytizing faiths spread 1.5-2× faster than Insular faiths | ±0.3× | Doctrine modifier wiring |
| Holy war frequency: Militant-doctrine civs engage in 20-40% more wars than Pacifist-doctrine civs | ±10% | WAR weight bonus |
| Religious minority persistence: multi-faith regions without priest pressure maintain minority >30% after 100 turns | Must stay >30% | Stable-by-default design |
| Conquest conversion: Militant conquest → <50% original faith after 20 turns. Non-militant conquest → >60% original faith after 20 turns | ±10% | Gradient distinction |
| Economy regression: treasury, trade, action distribution within ±10% of pre-M37 baseline | ±10% | Satisfaction penalty doesn't cascade into destabilization |
| `--agents=off` regression: no belief-related behavior, output identical to pre-M37 | Exact | Fallback guard |
| Coexistence stability: isolated same-faith regions maintain 100% cohesion indefinitely | Exact | No false conversion triggers |

### Tier 3: Characterization (200 Seeds × 500 Turns, Documented Report)

No pass/fail — generates data for M47 calibration.

| Metric | What It Reveals |
|--------|-----------------|
| Conversion rate by doctrine type: per-doctrine-pair conversion velocity | Which doctrine combinations create fastest/slowest spread |
| Religious minority half-life: turns for a 40% minority to reach 20% under steady priest pressure | Conversion rate calibration target |
| Holy war cascade frequency: how often does a holy war trigger counter-holy-war | Militant feedback loop intensity |
| Satisfaction distribution shift: pre/post M37 histograms | Impact of religious mismatch penalty |
| Faith diversity over time: number of distinct faiths with >5% population share at turn 100, 200, 500 | Convergence vs pluralism |
| Named character conversion impact: conversion rate in regions with/without named prophets | Effect size of named character multiplier |

Report output: `docs/superpowers/analytics/m37-belief-systems-report.md`. M47 reads this for calibration targets.

---

## File Changes

| File | Change | Lines (est.) |
|------|--------|-------------|
| `pool.rs` | Add `beliefs: Vec<u8>`. Extend `spawn()` with `belief: u8` param; initialize in both free-slot reuse and grow-vec paths. | ~15 |
| `conversion_tick.rs` | **New module.** Per-agent conversion roll, satisfaction susceptibility, conquest override, region-skip. | ~80 |
| `tick.rs` | Add stage 6 call to `conversion_tick()`. Extend BirthInfo with `belief: u8`, copy from parent in demographics birth path. | ~15 |
| `satisfaction.rs` | Add religious mismatch comparison (`agent_belief != majority_belief`), add term to M36's penalty sum. | ~10 |
| `region.rs` | Add `conversion_rate`, `conversion_target_belief`, `conquest_conversion_active`, `majority_belief` to RegionState. | ~10 |
| `ffi.rs` | Extend region RecordBatch schema with 4 new columns. Add `beliefs` to snapshot output. Extend spawn FFI with belief param. | ~25 |
| `lib.rs` | Module export for `conversion_tick`. | ~2 |
| `models.py` | Add `Belief` dataclass, `belief_registry` on WorldState, `civ_majority_faith` on Civilization, `conquest_conversion_boost` on Region. | ~30 |
| `simulation.py` | Faith generation at world-gen: create belief_registry, assign initial beliefs per civ. | ~60 |
| `agent_bridge.py` | Add 4 conversion signals to `build_region_batch()`. Add belief to spawn signals. Compute `majority_belief` and `civ_majority_faith` from snapshot. | ~50 |
| `action_engine.py` | Holy war WAR weight modifier (+0.15 Militant, +5 defender stability). Check `civ_majority_faith` on attacker and target. | ~20 |
| `culture.py` or new `religion.py` | `compute_conversion_signals()`, `compute_majority_belief()`, `compute_civ_majority_faith()`, conquest conversion boost lifecycle. | ~80 |
| Tests (Rust) | Tier 1 unit tests: conversion roll, satisfaction penalty, birth inheritance, conquest override. | ~120 |
| Tests (Python) | Tier 1 doctrine generation + Tier 2 regression harness. | ~130 |

**Total:** ~150-200 lines Rust (production), ~240 lines Python (production), ~250 lines tests.

### What Doesn't Change

- `ecology.py` — resource/ecology mechanics unchanged
- `politics.py` — secession/federation mechanics unchanged
- `culture.py` — M36 cultural drift unchanged (separate system)
- Bundle format — stays at current version
- `--agents=off` mode — religion functions detect missing snapshot and skip; no belief-related behavior in agentless mode

---

## Forward Dependencies

| Milestone | How M37 Enables It |
|-----------|-------------------|
| M38a (Temples & Clergy) | Temples boost conversion rate in region (+50%). Clergy faction uses priest count (already computed for conversion signals). Temple destruction on conquest is a named event. |
| M38b (Schisms & Persecution) | Schisms create new faiths (consume remaining belief_registry slots). Persecution penalty uses the remaining -0.15 penalty cap budget. Cultural minorities from M36 + religious minorities from M37 become persecution targets. |
| M39 (Family & Lineage) | Family members share belief — inheritance at birth already uses parent's belief via BirthInfo. Family-based conversion resistance (harder to convert agents whose family shares their faith). |
| M40 (Social Networks) | Religious affinity as edge weight in social graphs. Priest networks for organized conversion. |
| M47 (Tuning Pass) | All `[CALIBRATE]` constants tuned. Tier 3 report provides calibration targets. Conversion rate bands tightened. |
