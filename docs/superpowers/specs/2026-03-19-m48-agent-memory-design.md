# M48: Agent Memory — Design Spec

> **Status:** Approved. Phoebe design review (8 sections) + spec review (4 blocking items fixed, 12 observations noted).
>
> **Phase 7 Depth Track.** First milestone after M47. Depends on: M47 tuning pass (Phase 6 baseline).
>
> **Scope:** Per-agent memory ring buffer (Rust SoA) + Mule promotion system (Python-side). Additive to existing systems — no restructuring of satisfaction, behavior, or demographics.

---

## 1. Storage Layout

### Ring Buffer (SoA on AgentPool)

8 slots per agent. Each slot is 8 bytes:

```
event_type:   u8    — enum index (0-15)
source_civ:   u8    — civ index of the actor/cause (NOT agent_id)
turn:         u16   — turn the event occurred
intensity:    i8    — emotional weight (-128 to +127, signed)
decay_factor: u8    — precomputed per-tick decay factor (0 = permanent)
_reserved:    [u8; 2]  — reserved for future use, not allocated
```

**Field naming:** `source_civ`, not `actor_id`. Agent IDs are `u32`; this field is a `u8` civ index. Unambiguous.

**Reserved bytes are NOT allocated.** The 2-byte reserved space is documented capacity for future milestones (e.g., `region_id: u8` if spatial memory context proves necessary). The Vec is not created until a milestone needs it.

### New SoA Fields

```rust
// Memory ring buffer (8 slots per agent)
memory_event_types:   Vec<[u8; 8]>,    // 8 bytes/agent
memory_source_civs:   Vec<[u8; 8]>,    // 8 bytes/agent
memory_turns:         Vec<[u16; 8]>,   // 16 bytes/agent
memory_intensities:   Vec<[i8; 8]>,    // 8 bytes/agent
memory_decay_factors: Vec<[u8; 8]>,    // 8 bytes/agent

// Write gating
memory_gates: Vec<u8>,                 // 1 byte/agent — bitfield

// Occupancy tracking
memory_count: Vec<u8>,                 // 1 byte/agent — 0-8 occupied slots
```

**Total new storage:** 50 bytes/agent. At 50K agents = 2.5MB.

**SoA rationale:** `Vec<[T; 8]>` (arrays-of-arrays) rather than flat interleaved. The decay loop reads all 8 intensities + all 8 decay_factors per agent — contiguous per-field access is cache-friendly. Write path accesses a single slot (indexed by count/eviction) across multiple fields — sparse and acceptable.

### Lifecycle

- **`spawn()`:** Explicitly zero-initialize all 7 memory SoA fields. `memory_count = 0`. `memory_gates = 0`. All slot arrays zeroed. Both the free-list reuse branch AND the grow branch in `pool.rs` must set these fields — the existing spawn code does field-by-field assignment (lines 114-142), not bulk zeroing.
- **`kill()`:** No explicit cleanup. Dead agent's memory is ignored. The next `spawn()` into that slot will explicitly zero-initialize.

---

## 2. Decay & Eviction

### Half-Life Parameterization

Constants define half-lives in turns (human-readable, tuning-friendly):

```rust
// agent.rs — event type defaults
const FAMINE_HALF_LIFE: f32 = 40.0;    // [CALIBRATE]
const BATTLE_HALF_LIFE: f32 = 25.0;    // [CALIBRATE]
// ... etc (see Section 3 registry)
```

At memory creation time, convert to per-tick decay factor:

```rust
fn factor_from_half_life(half_life: f32) -> u8 {
    // factor = 255 * (1 - 0.5^(1/half_life))
    let rate = 1.0 - 0.5_f32.powf(1.0 / half_life);
    (rate * 255.0).round() as u8
}
```

Inverse for debugging:

```rust
fn half_life_from_factor(factor: u8) -> f32 {
    if factor == 0 { return f32::INFINITY; } // permanent sentinel
    let rate = factor as f32 / 255.0;
    (0.5_f32.ln() / (1.0 - rate).ln()).abs()
}
```

**Roundtrip test tolerance:** `< 15%` relative error for half-lives 1-50, `< 25%` for 50-100 (u8 granularity gets coarser at longer half-lives).

**Conversion is cold-path only.** `factor_from_half_life()` runs at memory creation (~thousands of events per turn). The decay loop (hot path, 8 × agent_count slots) uses the precomputed u8 directly.

### Per-Tick Decay (Hot Path)

```rust
// Integer arithmetic only, no floats
let new_intensity = (intensity as i16 * (255 - decay_factor) as i16) / 255;
intensity = new_intensity as i8;
```

- `decay_factor = 0` → permanent: `intensity × 255 / 255 = intensity`
- Truncation toward zero is intentional — intensity-1 memories are noise and should be overwritable
- Deterministic, no RNG consumed
- i16 intermediate avoids overflow (max: 127 × 255 = 32,385, within i16 range)

### Tick Placement

Memory decay runs as the **first tick operation** ("Phase -0.5"), before skill growth. Satisfaction reads freshly-decayed values.

### Eviction Policy

- `memory_count < 8`: write to `slot[count]`, increment count. No eviction.
- `memory_count == 8`: find slot with minimum `|intensity|`. Tie-break: lowest slot index (deterministic). Overwrite that slot. Count stays at 8.
- Intensity-0 slots (naturally decayed to noise) are always first eviction candidates.

**NOT FIFO.** A cursor-based approach would evict the oldest memory regardless of significance. Intensity-based eviction protects strong memories (including M51 legacy memories) from being overwritten by trivial events.

### LEGACY Bypass

LEGACY memories (M51) write `decay_factor = 0` directly, bypassing the conversion function. The registry entry is "decay_factor: 0 (direct write)" — NOT "half-life: 0" (which would compute instant erasure). However, per Section 3, Legacy default half-life is 100 turns (very long, not permanent), to protect the 8-slot budget when M57 enables two-parent inheritance.

---

## 3. Event Type Registry

### 14 Types (+ 2 Reserved)

```rust
pub const MEMORY_EVENT_TYPES: usize = 16;

#[repr(u8)]
pub enum MemoryEventType {
    Famine       = 0,
    Battle       = 1,
    Conquest     = 2,
    Persecution  = 3,
    Migration    = 4,
    Prosperity   = 5,
    Victory      = 6,
    Promotion    = 7,
    BirthOfKin   = 8,
    DeathOfKin   = 9,
    Conversion   = 10,
    Secession    = 11,
    // 12-13 reserved for Phase 8
    Legacy       = 14,  // M51 only — direct decay_factor write
    // 15 reserved
}
```

**`from_u8()` implementation:** Returns `None` for reserved slots 12, 13, 15. Prevents stale buffer data from mapping to valid types.

### Default Profiles

All `[CALIBRATE]` for M53.

| Type | Default Intensity | Half-Life (turns) | Gated? |
|------|:-:|:-:|:-:|
| Famine | -80 | 40 | Yes (bit 2) |
| Battle | -60 | 25 | Yes (bit 0) |
| Conquest | -70 | 30 | No |
| Persecution | -90 | 50 | Yes (bit 3) |
| Migration | -30 | 15 | No |
| Prosperity | +50 | 20 | Yes (bit 1) |
| Victory | +60 | 20 | No |
| Promotion | +70 | 30 | No |
| BirthOfKin | +40 | 25 | No |
| DeathOfKin | -80 | 35 | No |
| Conversion | +50 / -50 | 20 | No |
| Secession | -60 | 20 | No |
| Legacy | varies | 100 | No |

**CONVERSION sign rule:** Default +50 (voluntary conversion). Override to -50 when `conquest_conversion_active` is true in `conversion_tick.rs`. Single conditional at the write site.

**Intensity is signed at the registry level.** Positive = good, negative = bad. BATTLE is always negative (trauma) regardless of which side won — VICTORY captures the positive dimension separately.

### Gate Bit Assignments

`memory_gates: u8` bitfield:

| Bit | Event Type | Set When | Clears When |
|-----|-----------|----------|-------------|
| 0 | Battle | Memory written | Agent is NOT soldier OR region is NOT contested |
| 1 | Prosperity | Memory written | `wealth < PROSPERITY_THRESHOLD` |
| 2 | Famine | Memory written | `food_sufficiency >= 1.0` |
| 3 | Persecution | Memory written | `persecution_intensity == 0` in agent's region |
| 4-7 | Reserved | — | — |

**No region tracking.** Gate conditions encode the relevant state directly. An agent migrating from a contested to a peaceful region clears the BATTLE gate via the "NOT contested" condition check. No separate gate-region storage needed.

### Mule Event-Type to Action Mapping

Drives `utility_overrides` at Mule promotion (Section 6). 9 mappings. Events not listed don't produce Mule variants.

| Dominant Memory | Boosted Actions | Suppressed Actions |
|---|---|---|
| Famine | DEVELOP ×3.0, TRADE ×2.0 | WAR ×0.3 |
| Battle | WAR ×3.0 | DIPLOMACY ×0.5 |
| Conquest | WAR ×3.0, EXPAND ×2.0 | DIPLOMACY ×0.3 |
| Persecution | FUND_INSTABILITY ×3.0 | TRADE ×0.5 |
| Migration | EXPAND ×3.0, TRADE ×2.0 | — |
| Victory | WAR ×2.5, EXPAND ×2.0 | — |
| DeathOfKin | DIPLOMACY ×3.0 | WAR ×0.3 |
| Secession | DIPLOMACY ×2.5, INVEST_CULTURE ×2.0 | — |
| Conversion | INVEST_CULTURE ×3.0, BUILD ×2.0 | — |

**Negative Conversion (forced) maps to INVEST_CULTURE + BUILD.** Documented as intentional — zealous converts are historically the most fervent builders.

**Persecution at -90 dominates Mule-type distribution.** M53 adds Mule-type frequency targets to monitor this.

All boost/suppression values are `[CALIBRATE]` for M53. Starting range: 2.0-4.0× for boosts, 0.1-0.5× for suppressions.

---

## 4. Write Architecture

### Consolidated Write Phase

Memory writes are **NOT** scattered across tick phases. Instead:

1. Each tick phase collects **write intents** into a pending list:

```rust
struct MemoryIntent {
    agent_slot: usize,
    event_type: u8,
    source_civ: u8,
    intensity: i8,
}
```

2. After all tick phases complete, a single `write_memories()` pass processes all intents:
   - Check gate bit (skip if gated event type and bit already set)
   - Check `memory_count`: if < 8, append to next slot; if == 8, evict min `|intensity|`
   - Compute `decay_factor` from event type defaults via lookup table
   - Set gate bit if applicable
   - Update `memory_count`

3. **Same-turn feedback prevention.** All writes happen after all phases. No phase can read a memory written during the same tick. Satisfaction reads previous turn's memory state (memory decay runs first in tick, satisfaction runs after).

**Full delay chain:** Event occurs (end of tick T) → memory written (end of tick T) → decay applied (start of tick T+1) → satisfaction/decision reads decayed value (tick T+1).

**Intent vector sizing:** `Vec::with_capacity(slots.len())` per region to avoid reallocs in parallel phases.

### Intent Collection Sites

All Rust-side. Gate checks happen at write time (not collection time) to keep parallel phases read-only.

| Phase | Event Type | Trigger Condition |
|---|---|---|
| After satisfaction | Famine | `food_sufficiency < FAMINE_MEMORY_THRESHOLD` `[CALIBRATE]` AND gate bit 2 clear |
| After wealth tick | Prosperity | `wealth > PROSPERITY_THRESHOLD` `[CALIBRATE]` AND gate bit 1 clear |
| Decision apply | Battle | Soldier + contested region + survived + gate bit 0 clear |
| Decision apply | Migration | Agent migrated this turn |
| Decision apply | Victory | Soldier + `war_won_this_turn` signal set on region |
| Demographics | BirthOfKin | Agent gives birth (parent gets the memory) |
| Demographics | DeathOfKin | Agent dies with living children (children get memory via reverse index) |
| Conversion tick | Conversion | Agent changes belief. Intensity sign from `conquest_conversion_active` |
| Conversion tick | Persecution | Minority belief + persecution active + gate bit 3 clear |
| Named chars | Promotion | Agent promoted to named character |

**Signal-driven events** (Python → Rust via region batch):

| Signal | RegionState Field | Python Source | Intent |
|---|---|---|---|
| `controller_changed_this_turn` | `bool` | `_resolve_war_action()` in `action_engine.py` | Conquest — all agents in region |
| `war_won_this_turn` | `bool` | `_resolve_war_action()` in `action_engine.py` | Victory — soldiers in winning civ's contested regions |
| `seceded_this_turn` | `bool` | `check_secession()` in `politics.py` | Secession — all agents in region |

**Clear site (all three):** `simulation.py` before bridge tick. Same pattern as `conquered_this_turn`.

**Signal architecture note:** The existing `conquered_this_turn` is per-CIV (a `set[int]` on WorldState). These three M48 signals are per-REGION (boolean on `Region` objects). Different granularity — M48 needs to know which specific regions changed, not just which civs were conquered. Implementation: in `_resolve_war_action()`, when `region.controller = attacker.name` is set for a conquered region, also set `region.controller_changed_this_turn = True` on that region. For `war_won_this_turn`, set on the contested/target regions where the winning civ's soldiers are present (not all winner regions — only regions involved in the war action).

**Scope:** `controller_changed_this_turn` fires for **WAR conquest only**, not EXPAND or peaceful transfers. Matches existing `conquered_this_turn` semantics (CLAUDE.md: "conquered_this_turn fires for WAR conquest only, not EXPAND").

**Each signal requires:** `RegionState` field, `build_region_batch()` column, `signals.rs` parse line, and a **2-turn transient reset integration test** (per CLAUDE.md cross-cutting rule).

### Gate Bit Clearing

Also runs in the consolidated write pass, before intent processing:

| Bit | Clears When |
|-----|-------------|
| 0 (Battle) | Agent is NOT soldier OR region is NOT contested |
| 1 (Prosperity) | `wealth < PROSPERITY_THRESHOLD` |
| 2 (Famine) | `food_sufficiency >= 1.0` |
| 3 (Persecution) | `persecution_intensity == 0` in agent's region |

### DEATH_OF_KIN Reverse Index

Built once per tick immediately before the demographics sequential-apply phase begins, before any `pool.kill()` calls. Single O(n) scan: `parent_id → Vec<child_slot>`. When a parent dies, children are looked up in the map and DEATH_OF_KIN intents are added for each living child.

**Timing is critical:** The reverse index must reflect pre-death state. Building after deaths would reference recycled slots with new `parent_ids`.

### RNG

Memory writes are deterministic. No RNG consumed in M48. Offset 900 is reserved for future creation-time intensity variance (not consumed in M48).

### `--agents=off`

Memory SoA is Rust-side. `--agents=off` skips the agent tick entirely. No Python code reads memory except through the narration FFI query. Invariant maintained.

---

## 5. Behavioral Effects

Three channels. Satisfaction is the weakest; utility modifiers and bond formation carry the primary behavioral value.

### 5a. Satisfaction Modifier

**Inside the 0.40 non-ecological cap, lowest priority (5th term).**

Five-term priority clamping order:

```
cultural → religious → persecution → class_tension → memory
```

Formula:

```rust
let remaining = (PENALTY_CAP - cultural - religious - persecution - class_tension_clamped).max(0.0);
let memory_clamped = if memory_score < 0.0 {
    memory_score.max(-remaining)  // negative magnitude clamped to remaining budget
} else {
    memory_score  // positive memories reduce penalty freely (no cap on benefit)
};
// Total penalty floored at 0.0 — positive memories cannot create a net bonus beyond zero penalty
let total_penalty = (cultural + religious + persecution + class_tension_clamped + memory_clamped).max(0.0);
```

**Memory score computation:**

```rust
fn compute_memory_satisfaction_score(intensities: &[i8; 8], count: u8) -> f32 {
    let sum: i16 = intensities[..count as usize].iter()
        .map(|&i| i as i16)
        .sum();
    // Normalize: sum range is [-1024, +1016] for 8 full slots
    // Scale to [-0.15, +0.15] via MEMORY_SATISFACTION_WEIGHT
    (sum as f32 / 1024.0) * MEMORY_SATISFACTION_WEIGHT
}
```

- `MEMORY_SATISFACTION_WEIGHT` `[CALIBRATE]` — target range 0.10-0.15
- Positive memories (prosperity, victory) partially offset social penalties
- Negative memories (famine, persecution) add penalty within cap budget
- In worst-case agents (full 0.40 from social penalties), memory penalty is absorbed — correct by design (Q3 decision)

**One-turn lag.** Satisfaction reads memory state from previous turn's decay pass (memory decay runs first, satisfaction runs after skill growth).

### 5b. Decision Utility Modifiers

Per-event-type utility shifts on actual agent decisions (STAY, MIGRATE, SWITCH_OCCUPATION, REBEL — not civ-level actions like WAR).

| Memory Type | Utility Effect |
|---|---|
| Famine | MIGRATE +0.2 |
| Battle (bold agent) | STAY +0.1 in contested regions |
| Battle (cautious agent) | MIGRATE +0.15 |
| Conquest (conquered — `source_civ != agent.civ`) | MIGRATE +0.3 |
| Conquest (conqueror — `source_civ == agent.civ`) | STAY +0.1 |
| Persecution | REBEL +0.15, MIGRATE +0.2 |
| Prosperity | MIGRATE -0.2, SWITCH -0.1 |
| Victory | STAY +0.1 |
| DeathOfKin | MIGRATE -0.15 |

**Scaling:** Each modifier scales with `intensity / 128.0` (normalized to [-1.0, +1.0]). A fresh persecution memory at -90 gives ~70% of the full modifier. A decayed memory at -20 gives ~15%. Memories naturally lose behavioral influence as they fade.

**Additive, not multiplicative.** Applied before Gumbel noise selection in `evaluate_region_decisions()`. Shifts the probability distribution without dominating it.

**Conquest side differentiation** via `source_civ` comparison. Conquerors get garrison instinct (STAY), conquered get displacement pressure (MIGRATE).

**Persecution stacking:** Memory REBEL +0.15 stacks with existing `PERSECUTION_REBEL_BOOST` (+0.30). Combined +0.45 is strong but not near-certain. Reduced from +0.30 (original proposal) to +0.15 to avoid guaranteed rebellion.

All modifier magnitudes are `[CALIBRATE]` for M53.

### 5c. Bond Formation Input (M50 Interface)

M48 exposes a shared memory query that M50 consumes:

```rust
fn agents_share_memory(pool: &AgentPool, a: usize, b: usize) -> Option<(u8, u16)> {
    // Returns (event_type, turn) if agents a and b both have a memory
    // with matching event_type AND turn (within +/-1 turn tolerance)
    // Returns the strongest match (highest combined |intensity|)
    // Returns None if no shared memory exists
}
```

M48 implements the query. M50 wires it during bond formation checks. **No M48 behavioral effect from this.** The query exists but is not called until M50 lands.

---

## 6. Mule Promotions

**Prerequisite:** M48 memory ring buffer + `get_agent_memories(agent_id)` FFI method must be implemented before Mule logic.

### Trigger

When `_process_promotions` creates a new GreatPerson, roll against `MULE_PROMOTION_PROBABILITY` `[CALIBRATE]` (target: 5-10%).

**RNG:** Python-side `random.Random(world.seed + world.turn * 7919 + agent_id)`. Not Rust STREAM_OFFSETS (promotion runs Python-side). Multiplicative salt separation (turn × 7919) avoids correlation with the existing name-pick RNG at `agent_bridge.py:563` which uses `random.Random(world.seed + world.turn + agent_id)`. Cross-agent/cross-turn seed collisions are accepted (deterministic but correlated — same pattern as existing Python RNG usage).

### On Mule Promotion

1. Call `get_agent_memories(agent_id)` to retrieve the agent's ring buffer
2. Extract the strongest memory (highest `|intensity|`)
3. Look up `event_type` in the Mule mapping table (Section 3)
4. If event type has no mapping (Prosperity, BirthOfKin, Promotion, Legacy, reserved), Mule flag is NOT set — normal promotion
5. Build `utility_overrides: dict[ActionType, float]` from the mapping table
6. Set Mule fields on `GreatPerson`

### New Fields on GreatPerson (Python-side, models.py)

```python
mule: bool = False
mule_memory_event_type: Optional[int] = None  # MemoryEventType index
utility_overrides: dict[str, float] = Field(default_factory=dict)  # ActionType name -> multiplier
```

**`mule_promotion_turn` NOT added.** Use `born_turn` (which IS the promotion turn per CLAUDE.md gotcha).

### Time-Bounded Influence

- **Active window** (`MULE_ACTIVE_WINDOW` `[CALIBRATE]`, target 20-30 turns): full boost applied
- **Fade period** (`MULE_FADE_TURNS` `[CALIBRATE]`, target ~10 turns): boost linearly interpolates from full to 1.0 (multiplicative identity)
- **After fade:** utility_overrides effectively zeroed. Character remains GreatPerson but no longer distorts action weights.

```python
def get_mule_factor(gp: GreatPerson, action: ActionType, current_turn: int) -> float:
    if not gp.mule or not gp.active:
        return 1.0
    age = current_turn - gp.born_turn
    if age > MULE_ACTIVE_WINDOW + MULE_FADE_TURNS:
        return 1.0  # expired
    base = gp.utility_overrides.get(action.name, 1.0)
    if age <= MULE_ACTIVE_WINDOW:
        return base  # full boost
    # Fade: linear interpolation base -> 1.0
    fade_progress = (age - MULE_ACTIVE_WINDOW) / MULE_FADE_TURNS
    return base + (1.0 - base) * fade_progress
```

### Action Engine Integration

**Insertion point:** In `_compute_weights()`, AFTER all existing weight modifiers (including K_AGGRESSION_BIAS) and BEFORE the streak-breaker check and 2.5x proportional rescale cap. Execution order: ...aggression bias → **Mule loop** → streak-breaker → 2.5x cap.

```python
# After K_AGGRESSION_BIAS application:
for gp in [gp for gp in world.great_persons if gp.mule and gp.active and gp.civilization == civ.name]:
    for action in ActionType:
        factor = get_mule_factor(gp, action, world.turn)
        if weights[action] > 0:  # zero-weight (ineligible) actions stay zero
            weights[action] *= max(factor, 0.1)  # suppression floor at 0.1x
```

**Streak-breaker interaction:** If the Mule's boosted action is the streaked action, streak-breaker zeros it. **Intentional.** Pattern: war-war-war-pause-war-war-war. Mule influence resumes next turn.

**Multiple Mules:** Factors multiply. Opposing Mules partially cancel (×3.0 × ×0.3 = ×0.9). Subject to 2.5x proportional rescale cap.

**Dead Mule = immediate cutoff.** `gp.active` check in `get_mule_factor()`. Institutional momentum persists through game state (e.g., conquered territory), not continued weight modification. Fade-on-death deferred unless M53 shows abrupt cutoff looks bad.

### Frequency Math

At 50K agents, ~5-15 GreatPerson promotions per 100 turns. At 5-10% Mule rate, ~0-1 Mule per 100 turns. One Mule per era is the target frequency.

### M52 Artifact Interface

When the action engine selects an action matching a living Mule's boosted action during the active window AND the action succeeds, M52 creates a Mule artifact. M48 documents this interface contract. M52 implements the detection and artifact creation. The `mule_action_success` flag is a transient signal — transient reset test deferred to M52 spec.

---

## 7. Narration & FFI

### Selective Query

New PyO3 method on `AgentSimulator`:

```rust
#[pymethod]
fn get_agent_memories(&self, agent_id: u32) -> PyResult<Vec<(u8, u8, u16, i8, u8)>> {
    // Returns occupied memory slots as Vec<(event_type, source_civ, turn, intensity, decay_factor)>
    // Ordered by slot index (not sorted)
    // Returns empty vec if agent_id not found or dead
}
```

**Scaling note:** Requires O(N) slot scan (no ID-to-slot reverse index in pool). Fine for ~50 GreatPersons. If M50 needs bulk queries, add `get_memories_batch(agent_ids: Vec<u32>)`.

### Caching on GreatPerson

Memories cached on `GreatPerson.memories` during event processing in `agent_bridge.py`:

```python
# New field on GreatPerson (models.py)
memories: list[dict] = Field(default_factory=list)
# Each dict: {"event_type": int, "source_civ": int, "turn": int,
#             "intensity": int, "decay_factor": int}
```

**Sync timing:** After `_detect_character_events`, before arc classification, in the Phase 10 loop. Cached data naturally flows into bundle serialization for API batch re-narration.

**Dead character staleness:** Cached intensities may be slightly higher than true decayed values at render time. Documented as intentional cosmetic simplification.

### Memory Rendering

Static template registry. No events_timeline cross-reference. No spatial specificity (use "the fall of the Kethani" not "the siege of Ashfall"):

```python
MEMORY_DESCRIPTIONS = {
    0: "a great famine under the {civ}",
    1: "combat against the {civ}",
    2: "the fall of the {civ}",
    3: "persecution by the {civ}",
    4: "a migration from {civ} lands",
    5: "a time of prosperity",
    6: "victory over the {civ}",
    7: "a great achievement",
    8: "the birth of a child",
    9: "the death of kin",
    10: "a change of faith",
    11: "the fracture of the {civ}",
}

def render_memory(mem: dict, civ_names: list[str]) -> str:
    template = MEMORY_DESCRIPTIONS.get(mem["event_type"], "an event")
    civ_name = civ_names[mem["source_civ"]] if mem["source_civ"] < len(civ_names) else "unknown"
    return template.format(civ=civ_name, turn=mem["turn"])
```

### Narrator Context Format

In `build_agent_context_for_moment()`:

```
Character: General Kiran (the Bold)
Arc: Rise-and-Fall
Memories:
  - Survived combat against the Kethani (turn 180, strong)
  - Witnessed the fall of the Arameans (turn 205, fading)
  - Celebrated victory over the Tessarans (turn 240, vivid)
```

**Intensity thresholds for descriptors** `[CALIBRATE]`:
- `|intensity| > 60`: "vivid" / "strong"
- `|intensity| 30-60`: "fading"
- `|intensity| < 30`: omitted from narration context (too weak to mention)

### Mule Narrator Context

Appended when character has `mule = True`:

```
[MULE] Shaped by: a great famine under the Kethani (turn 85, intensity -72)
  Active influence: DEVELOP x3.0, TRADE x2.0, WAR x0.3
  Window: 15 turns remaining
```

### M53 Bulk Analytics (Deferred)

```rust
#[pymethod]
fn get_memory_summary(&self) -> PyResult<RecordBatch> {
    // Per-event-type: count, mean_intensity, median_intensity
    // Per-civ: memory_count distribution, dominant_event_type
    // Global: total_occupied_slots, mean_occupancy
}
```

Not implemented in M48. Interface contract documented for M53.

---

## 8. Validation & Testing

### Determinism

- Same seed produces identical memory state. Memory writes are deterministic (no RNG in M48). Mule promotion roll uses Python `random.Random(world.seed + world.turn + agent_id + 7919)`.
- `--agents=off` bit-identical output (memory system is Rust-side only, skipped entirely).

### Rust Unit Tests

| Test | Verifies |
|---|---|
| `test_memory_decay_basic` | Intensity decreases per tick at expected rate for various half-lives |
| `test_memory_decay_permanent` | `decay_factor=0` slot intensity unchanged across 100 ticks |
| `test_memory_eviction_min_intensity` | Full buffer evicts slot with lowest `\|intensity\|`, not oldest |
| `test_memory_eviction_tiebreak` | Ties broken by lowest slot index |
| `test_memory_gate_battle` | BATTLE intent skipped when gate bit 0 set; gate clears when not contested |
| `test_memory_gate_famine` | FAMINE intent skipped when gate bit 2 set; gate clears when food_sufficiency >= 1.0 |
| `test_memory_gate_prosperity` | PROSPERITY intent skipped when gate bit 1 set; gate clears when wealth < threshold |
| `test_memory_gate_persecution` | PERSECUTION intent skipped when gate bit 3 set; gate clears when persecution == 0 |
| `test_memory_spawn_zeroed` | New agent has all-zero memory fields |
| `test_memory_count_lifecycle` | Count increments from 0 to 8, stays at 8 after eviction writes |
| `test_halflife_roundtrip` | `half_life_from_factor(factor_from_half_life(N))` within tolerance for N=1..100 |
| `test_halflife_edge_cases` | factor=0 → INFINITY, factor=255 → ~1t, half_life=∞ → factor=0 |
| `test_decay_integer_truncation` | Intensity 1 with any nonzero factor decays to 0 in one tick |
| `test_consolidated_write_ordering` | Intents from multiple phases all write in single pass |
| `test_same_turn_no_feedback` | Satisfaction computed before memory writes; reads previous turn state |
| `test_utility_modifier_mapping` | Writes specific memory, computes utility, asserts correct action gets correct modifier with correct sign and scale |
| `test_memory_satisfaction_inside_cap` | Memory penalty clamped to remaining 0.40 budget after other terms |
| `test_mule_suppression_floor` | Suppression multiplier floors at 0.1x; zero-weight actions stay zero |

### Python Integration Tests

**All tests use `run_turn()` directly. Never `execute_run()`.** Avoids the hanging test pattern from M47 (LLM connection, narration/reflection path issues).

| Test | Verifies |
|---|---|
| `test_transient_signal_conquest` | `controller_changed_this_turn` set on conquest turn, cleared next turn |
| `test_transient_signal_war_won` | `war_won_this_turn` set on victory turn, cleared next turn |
| `test_transient_signal_secession` | `seceded_this_turn` set on secession turn, cleared next turn |
| `test_mule_promotion_determinism` | Same seed produces same Mule flag and overrides |
| `test_mule_active_window` | Mule boost applies during window, fades linearly, zeroes after |
| `test_mule_streak_interaction` | Streak-breaker zeros Mule's preferred action; resumes next turn |
| `test_mule_weight_cap` | Mule boost subject to 2.5x proportional rescale |
| `test_get_agent_memories_ffi` | FFI method returns correct slots for a known agent |
| `test_agents_off_unaffected` | `--agents=off` produces identical output with memory system present |

### 200-Seed Regression

**Explicitly deferred to M53.** M48 modifies the satisfaction formula and behavior model — existing metric regression is possible. But memory is uncalibrated until M53 tunes the ~45 constants. Running regression before calibration would produce noise, not signal.

### M53 Validation Targets (Documented, Not Tested in M48)

- Memory intensity distributions are not degenerate (not all zero, not all saturated)
- Utility modifiers produce measurable behavioral shifts (famine survivors migrate more)
- Mule frequency: ~0-1 per 100 turns at 50K agents
- Mule impact: measurable action distribution shift during active window
- Mule-type frequency distribution across event types (persecution dominance flag)
- Gate effectiveness: < 1.5 BATTLE writes per agent per battle (mean)
- Cross-system regression: mean satisfaction within 0.8-1.2× of M47 baseline across 200 seeds
- Cohort formation prerequisite: shared memories between co-located agents (measured but full cohort validation deferred to M53/M61)

---

## 9. Calibration Constants Summary

All `[CALIBRATE]` for M53. Grouped by tier for tiered tuning strategy.

### Tier 1: Structural Ratios (Intensities)

| Constant | Default | Section |
|---|:-:|:-:|
| FAMINE_DEFAULT_INTENSITY | -80 | 3 |
| BATTLE_DEFAULT_INTENSITY | -60 | 3 |
| CONQUEST_DEFAULT_INTENSITY | -70 | 3 |
| PERSECUTION_DEFAULT_INTENSITY | -90 | 3 |
| MIGRATION_DEFAULT_INTENSITY | -30 | 3 |
| PROSPERITY_DEFAULT_INTENSITY | +50 | 3 |
| VICTORY_DEFAULT_INTENSITY | +60 | 3 |
| PROMOTION_DEFAULT_INTENSITY | +70 | 3 |
| BIRTHOFKIN_DEFAULT_INTENSITY | +40 | 3 |
| DEATHOFKIN_DEFAULT_INTENSITY | -80 | 3 |
| CONVERSION_DEFAULT_INTENSITY | +50 (-50 forced) | 3 |
| SECESSION_DEFAULT_INTENSITY | -60 | 3 |

### Tier 2: Temporal (Half-Lives)

| Constant | Default | Section |
|---|:-:|:-:|
| FAMINE_HALF_LIFE | 40t | 3 |
| BATTLE_HALF_LIFE | 25t | 3 |
| CONQUEST_HALF_LIFE | 30t | 3 |
| PERSECUTION_HALF_LIFE | 50t | 3 |
| MIGRATION_HALF_LIFE | 15t | 3 |
| PROSPERITY_HALF_LIFE | 20t | 3 |
| VICTORY_HALF_LIFE | 20t | 3 |
| PROMOTION_HALF_LIFE | 30t | 3 |
| BIRTHOFKIN_HALF_LIFE | 25t | 3 |
| DEATHOFKIN_HALF_LIFE | 35t | 3 |
| CONVERSION_HALF_LIFE | 20t | 3 |
| SECESSION_HALF_LIFE | 20t | 3 |
| LEGACY_HALF_LIFE | 100t | 3 |

### Tier 3: Behavioral (Utility Modifiers)

| Constant | Default | Section |
|---|:-:|:-:|
| FAMINE_MIGRATE_BOOST | +0.20 | 5b |
| BATTLE_BOLD_STAY_BOOST | +0.10 | 5b |
| BATTLE_CAUTIOUS_MIGRATE_BOOST | +0.15 | 5b |
| CONQUEST_CONQUERED_MIGRATE_BOOST | +0.30 | 5b |
| CONQUEST_CONQUEROR_STAY_BOOST | +0.10 | 5b |
| PERSECUTION_REBEL_BOOST | +0.15 | 5b |
| PERSECUTION_MIGRATE_BOOST | +0.20 | 5b |
| PROSPERITY_MIGRATE_PENALTY | -0.20 | 5b |
| PROSPERITY_SWITCH_PENALTY | -0.10 | 5b |
| VICTORY_STAY_BOOST | +0.10 | 5b |
| DEATHOFKIN_MIGRATE_PENALTY | -0.15 | 5b |
| MEMORY_SATISFACTION_WEIGHT | 0.10-0.15 | 5a |

### Tier 4: Thresholds & Mule

| Constant | Default | Section |
|---|:-:|:-:|
| FAMINE_MEMORY_THRESHOLD | `[TBD]` | 4 |
| PROSPERITY_THRESHOLD | `[TBD]` | 4 |
| MEMORY_NARRATION_VIVID | 60 | 7 |
| MEMORY_NARRATION_FADING | 30 | 7 |
| MULE_PROMOTION_PROBABILITY | 5-10% | 6 |
| MULE_ACTIVE_WINDOW | 20-30t | 6 |
| MULE_FADE_TURNS | ~10t | 6 |
| Mule boost/suppression values (9 entries × 2-3 actions each) | 2.0-4.0× / 0.1-0.5× | 3 |

**~45 total constants.** M53 tunes in three tiered search spaces: structural ratios, temporal half-lives, behavioral perturbations. Each tier is 12-15 dimensions — tractable.

---

## 10. Roadmap Text Updates

The following Phase 7 roadmap text is superseded by this spec:

| Roadmap Text | Spec Decision |
|---|---|
| `actor_id: u16` | → `source_civ: u8` (Q2) |
| `decay_rate: u8` (raw) | → `decay_factor: u8` (precomputed from half-life, Q1 Option C) |
| "8 bytes × 8 slots = 64 bytes/agent" | → 50 bytes/agent (no reserved allocation, Q2/Section 1) |
| MULE_UTILITY_FLOOR (additive) | → MULE_BOOST_FACTOR (multiplicative, Q5) |
| LEGACY "permanent" | → 100t half-life (Section 3, Phoebe B-2) |

Update `chronicler-phase7-roadmap.md` M48 section to reference this spec after implementation begins.

---

## 11. Spec Review Notes

Observations from Phoebe spec review (non-blocking, documented for implementer awareness):

| # | Note | Action |
|---|------|--------|
| O-1 | Decay i16 intermediate: negative bound is -128 × 255 = -32,640, also within i16 range (-32,768). Both positive and negative bounds are safe. | Document both bounds in implementation comments. |
| O-2 | `life_events: u8` has only 1 bit remaining (bits 0-6 used). M48 does not need new bits (uses `memory_gates`), but Phase 7 milestones may. Proactive expansion to u16 is a candidate for M48 or earliest milestone that needs a new bit. | Flag in implementation plan. |
| O-3 | `agents_share_memory()` turn tolerance: u16 boundary at turn 0 checking turn-1 would underflow. Use `turn.abs_diff(other_turn) <= 1`. | Implement with `abs_diff`. |
| O-4 | Positive memory healing loop: uncapped positive memory score + satisfaction-fertility coupling could create demographic advantage for prosperous agents. | Add to M53 calibration targets. |
| O-5 | `MEMORY_SATISFACTION_WEIGHT` 0.10-0.15 range: primary calibration concern is interaction with remaining cap budget, not the weight in isolation. | Note in M53 calibration plan. |
| O-6 | DEATH_OF_KIN intent collection: intents collected DURING demographics (using pre-death reverse index), processed in consolidated write pass AFTER demographics completes. Two-step nature must be explicit in implementation. | Clarify in implementation plan. |
| O-7 | `war_won_this_turn`: flag set on contested/target regions where the war was fought (winner's soldiers present), not all winner regions globally. | Specified in Section 4 signal table. |
| O-9 | Consolidated write pass: must be the absolute last operation in `tick_agents()`, after displacement decrement, after conversion tick — after everything. | Verify in implementation. |
| O-11 | 200-seed regression deferred to M53 per spec. A 20-seed smoke test (no crashes, satisfaction distribution not degenerate) is valuable even before calibration. | Consider adding to integration test suite. |
| O-12 | `--agents=shadow` mode: memory writes are part of agent-side computation only. Shadow comparison metrics referencing satisfaction should account for the memory term difference between aggregate and agent paths. | Document in shadow mode notes. |
