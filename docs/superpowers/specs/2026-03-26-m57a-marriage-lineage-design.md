# M57a: Marriage Matching & Lineage Schema — Design Spec

> Date: 2026-03-26
> Status: Approved for implementation planning
> Depends on: M50 (Deep Relationships), M55a (Spatial Substrate)
> Prerequisite context: M50a/b, M51, M55a/b, M56a/b all landed

## Goal

Add proximity-based marriage formation at full agent scale and migrate lineage from single-parent to two-parent tracking. This is the invasive data-model half of the marriage milestone — it establishes the durable social and genealogical substrate without taking on household economics or joint behavior.

---

## 1. Marriage Formation

### Architecture

A dedicated `marriage_scan()` function in `formation.rs`, called **before** the existing `formation_scan()` in the tick. Marriage is a one-to-one matching problem with exclusivity constraints that do not fit the existing multi-bond-per-pair `evaluate_pair()` pattern.

**Cadence:** Own constant `MARRIAGE_CADENCE` (starting value: 4). Staggered: `region_idx % MARRIAGE_CADENCE == turn % MARRIAGE_CADENCE`.

**RNG:** Stream offset `1600` reserved in `agent.rs` `STREAM_OFFSETS`. Not consumed in v1 — the scored greedy matcher is fully deterministic without noise.

### Algorithm

1. Bucket alive agents by region (shared helper with `formation_scan`).
2. For each region on-cadence, collect eligible agents.
3. Enumerate eligible local pairs, compute marriage compatibility score.
4. Sort candidates by score with deterministic tie-break: pair hash derived from `(turn, region_idx, id_a, id_b)`, then agent-id ordering only if still tied.
5. Greedy accept: iterate sorted candidates, accept only if neither agent has been matched this pass.
6. Commit accepted pairs via `upsert_symmetric()` with `BondType::Marriage`.

### Eligibility Gates (all must pass)

- Both agents alive and marriage-eligible (age >= 16, matching `FERTILITY_AGE_MIN`, not `AGE_ADULT` which is 20).
- Neither has an existing `Marriage` bond.
- Same region.
- Spatial proximity: `distance(a, b) <= MARRIAGE_RADIUS` (starting value: 0.25 in normalized region coordinates).
- Not in hostile civ pair and not in active war pair.
- Not parent-child: neither agent appears in either parent slot of the other.
- Not siblings/half-siblings: no shared non-`PARENT_NONE` parent across either slot.

### Compatibility Score

Higher score = stronger match candidate. All weights are tunable constants.

| Factor | Effect |
|--------|--------|
| Same civ | Bonus (+0.3) |
| Same belief | Bonus (+0.2) |
| Cultural value proximity | Bonus (up to +0.15 per matching value) |
| Spatial closeness | Bonus (inverse distance, capped) |
| Cross-faith | Penalty (score reduction, not prohibition) |
| Cross-civ | Implicit (no same-civ bonus, still eligible) |

Age-gap penalty is deferred from v1. Can be added in a tuning pass if needed.

### Exclusivity & Lifecycle

- **Single spouse only.** One active `Marriage` bond per agent at any time.
- **Remarriage after death:** When a spouse dies, the `Marriage` bond is removed through explicit death-cleanup (not eviction). The surviving agent re-enters the eligible pool on subsequent marriage cadence ticks.
- **Bond persistence:** Once formed, a marriage bond does not auto-dissolve due to civ relation changes, border shifts, or migration. The bond persists until explicit removal (spouse death, or future divorce mechanics in M57b+).

### Eviction Protection

`Marriage` joins `Kin` as an eviction-protected bond type. Update `is_protected()` in `relationships.rs`:

```rust
pub fn is_protected(bond_type: u8) -> bool {
    bond_type == BondType::Kin as u8 || bond_type == BondType::Marriage as u8
}
```

If an agent's 8 relationship slots are full, protected bonds (Kin, Marriage) cannot be replaced. An agent with 1 Marriage + 2 Kin uses 3 protected slots, leaving 5 for social bonds.

### Shared Helpers

Extract from `formation.rs` for reuse by `marriage_scan()`:
- Region bucketing
- Deterministic regional ordering / hash
- `agent_id -> slot` lookup

`formation_scan()` itself does not need changes — it already skips pairs that have an existing bond of the evaluated type, and it does not evaluate `Marriage` as a formable type.

### Centralized Spouse Lookup

Add a helper in `relationships.rs`:
```rust
pub fn get_spouse_id(pool: &AgentPool, slot: usize) -> Option<u32>
```
Returns the target ID of the agent's `Marriage` bond, or `None`. In debug/test builds, `debug_assert!` that at most one Marriage bond exists. In release, deterministic fallback (first found).

---

## 2. Two-Parent Lineage Schema Migration

### Rust Pool Storage

Current: `parent_ids: Vec<u32>` — one value per agent slot.

New: Two parallel `Vec<u32>` arrays (SoA-consistent):
- `parent_id_0: Vec<u32>` — birth parent
- `parent_id_1: Vec<u32>` — second parent (spouse of birth parent at birth time, or `PARENT_NONE`)

Both initialize to `PARENT_NONE` on spawn and slot reuse.

Accessors:
- `parent_id_0(slot) -> u32`
- `parent_id_1(slot) -> u32`
- `parent_ids(slot) -> [u32; 2]` — convenience for iteration
- `has_parent(slot, agent_id) -> bool` — checks both slots

### Birth Path (`tick.rs`)

`BirthInfo` fields use semantic names:
```rust
struct BirthInfo {
    // ... existing fields ...
    birth_parent_id: u32,    // was: parent_id
    other_parent_id: u32,    // new: spouse at birth time, or PARENT_NONE
}
```

**At birth generation (parallel demographics phase):**
1. Record `birth_parent_id = pool.ids[slot]` (same as today).
2. Look up birth parent's Marriage bond via `get_spouse_id()`.
3. If found, record `other_parent_id = spouse_id`. If not, `other_parent_id = PARENT_NONE`.

**Critical rule:** Capture `other_parent_id` during birth generation, not sequential commit. The spouse may die later in the same tick — the child should still record that parent. This is intentional, not a bug.

**At birth resolution (sequential commit):**
- `pool.parent_id_0[new_slot] = birth.birth_parent_id`
- `pool.parent_id_1[new_slot] = birth.other_parent_id`

**No co-location check** when assigning `other_parent_id`. If the birth parent has a marriage bond, the spouse is recorded regardless of current location. Requiring co-location would be a hidden fertility-rule change, violating the Section 1 scope guard.

### FFI / Arrow Export

**Snapshot batch:** Replace single `parent_id` column with `parent_id_0` and `parent_id_1` (both `UInt32`). No backward-compatible `parent_id` alias — clean break to prevent stale consumers.

**Promotions batch:** Same — `parent_id` becomes `parent_id_0` + `parent_id_1`.

### Named Character Registry

`named_characters.rs` must widen in lockstep with the pool and FFI. If it carries singular lineage state, update to dual-parent. Promotions flow through this seam — if it lags, the promotions batch will silently lose the second parent.

### Python Models

`GreatPerson` in `models.py`:
- `parent_id: int` → `parent_id_0: int` + `parent_id_1: int`
- `parent_id_1` defaults to 0 (matches `PARENT_NONE`)
- New field: `lineage_house: int` (default 0) — see Section 3

Add a helper method:
```python
def parent_ids(self) -> tuple[int, int]:
    return (self.parent_id_0, self.parent_id_1)
```

`agent_bridge.py` snapshot/promotions column extraction updates from `parent_id` to `parent_id_0` / `parent_id_1`.

### Migration Safety

- `PARENT_NONE = 0` sentinel unchanged.
- All agents born before M57a naturally have `parent_id_1 = PARENT_NONE` — no backfill.
- `--agents=off`: no marriage formation, `parent_id_1` always `PARENT_NONE`.

---

## 3. Dynasty & Succession Compatibility

### Dynasty Assignment

`dynasty_id` stays **single-valued** per agent/GreatPerson. The child's operative dynasty is determined at the **lineage/promotion-record materialization seam** — not inside `check_promotion()` specifically, so ordinary agents and promoted GreatPeople share the same rule.

**Resolution rule (ordered):**
1. If exactly one parent has a dynasty → child takes that dynasty (regardless of slot).
2. If both parents share the same dynasty → child takes it.
3. If both parents have different dynasties → child takes birth parent's (slot 0) dynasty.
4. If neither parent has a dynasty → existing founder logic applies.

**`lineage_house`:** When rule 3 applies, record the other parent's operative `dynasty_id` as `lineage_house` on the GreatPerson. When both parents share the same dynasty or only one parent has one, `lineage_house` stays 0 (no distinct secondary house).

The birth-parent default in rule 3 is a **temporary substrate convention**, not a modeled constitutional law. Future succession-law systems (cognatic, agnatic, matrilineal) can override it.

**`lineage_house` usage in M57a:** Narration context only. Resolve to human-readable house name before narrator context (narrative.py renders house context as names, not raw IDs). No mechanical effect on legitimacy or faction power.

### Succession Legitimacy

**Either parent qualifies for direct-heir status.**

Current: `candidate.parent_id == ruler.agent_id`

New: `ruler.agent_id in candidate.parent_ids()` — using the `has_parent()` helper or `gp.parent_ids()` tuple.

`LEGITIMACY_DIRECT_HEIR = 0.15` and `LEGITIMACY_SAME_DYNASTY = 0.08` unchanged. Only the qualifying condition widens.

**Centralized helper:** Both `dynasties.py` and `factions.py` must use the same legitimacy check function, not duplicate tuple checks. Test behavior in both consumers (not structural centralization as a test assertion).

### Dynasty Detection

`check_promotion()` in `dynasties.py` consumes the already-determined lineage state when creating a GreatPerson — it does not invent dynasty assignment ad hoc.

---

## 4. Kin Bonds & Legacy Memory Widening

Both systems extend to dual-parent in M57a. This is lineage coherence, not household economics.

### Kin Bond Formation at Birth

Up to two `form_kin_bond()` calls per birth, one per distinct non-`PARENT_NONE` parent.

**At birth resolution in `tick.rs`:**
1. If `birth_parent_id != PARENT_NONE`: look up slot, call `form_kin_bond(parent_0_slot, child_slot, turn)`.
2. If `other_parent_id != PARENT_NONE` **and** `other_parent_id != birth_parent_id`: look up slot, call `form_kin_bond(parent_1_slot, child_slot, turn)`.

**Guards:** Same alive + ID-match check as today. If parent_1 died during the same tick, the kin bond doesn't form — the lineage record in `parent_id_1` still persists. Bond is best-effort; lineage is authoritative.

### Legacy Memory Inheritance on Death

Build reverse index from **both** parent slots:
```rust
for slot in 0..pool.capacity() {
    if pool.is_alive(slot) {
        let p0 = pool.parent_id_0[slot];
        if p0 != PARENT_NONE {
            parent_to_children.entry(p0).or_default().push(slot);
        }
        let p1 = pool.parent_id_1[slot];
        if p1 != PARENT_NONE && p1 != p0 {
            parent_to_children.entry(p1).or_default().push(slot);
        }
    }
}
```

Inheritance rule unchanged: top 2 memories by absolute intensity, halve intensity, apply legacy decay override, mark `is_legacy = true`, and **preserve the original event type** (Battle, DeathOfKin, etc.). Do not overwrite to a `LEGACY` event type — `MemoryEventType::Legacy` is vestigial in the live code. The `is_legacy` flag plus decay override is the correct M51 mechanism.

**Both-parents-die-same-turn:** Correct behavior. Child can inherit from both lines (up to 4 legacy memories). These compete for ring buffer slots normally.

**Duplicate defense:** `p1 != p0` check prevents double-indexing if malformed data puts the same parent in both slots.

### BirthOfKin / DeathOfKin Memory Intents

- **BirthOfKin:** Generate for both parents (if alive and distinct).
- **DeathOfKin:** Flows naturally from the widened reverse index — children receive the intent when either parent dies.

### MemoryIntent Identity Validation (Bug Fix)

**Hard requirement:** Deferred memory delivery must validate stable target identity, not just slot.

Current `MemoryIntent` stores only `agent_slot`. Dead slots are immediately reusable, so a newborn could inherit memories meant for a dead child whose slot was reused.

**Fix:** Extend `MemoryIntent` with `expected_agent_id: u32`. At write time in `write_all_memories()`, only write if:
- `pool.is_alive(slot)` **and**
- `pool.ids[slot] == expected_agent_id`

This fixes a pre-existing correctness issue that M57a's wider parent fanout makes more important. Tests belong in the memory suite (`test_legacy_memory.rs`, `test_memory.rs`), not only in M57a tests.

---

## 5. Narration, Analytics & Snapshot Visibility

### Whole-Stack Visibility Migration

These must all move together:
- Snapshot Arrow schema (`parent_id_0`, `parent_id_1`)
- Promotions Arrow schema (`parent_id_0`, `parent_id_1`)
- `GreatPerson` model (`parent_id_0`, `parent_id_1`, `lineage_house`)
- Named-character materialization in `named_characters.rs`

### Narrative Context

- `narrative.py` already maps `BondType::Marriage (2)` to `"marriage"`. Active marriage bonds show up in narrator relationship context via `agent_bonds`.
- When narrating a GreatPerson with `lineage_house != 0`, include secondary lineage context: *"of House X, with lineage ties to House Y through their other parent."* No gendered language — the model has parent slots, not sex semantics.
- Resolve `lineage_house` to human-readable house name before reaching narrator context.

### Marriage Formation Events

Marriage events are **not free** from the existing event pipeline. Named-character marriage formation needs explicit wiring — an analog to the existing `rivalry_formed` special-case in `simulation.py`. Add a `marriage_formed` event path for named characters that feeds the curator/narrator pipeline.

### Widowhood Events

**Deferred to M57b.** The current Rust dissolution path loses the dead spouse's identity in the Python-side dissolved-edge payload `(agent_id, 0, rel_type, turn)`. Clean widowhood narration requires widening dissolution tracking to preserve the counterparty ID. Out of scope for M57a.

### Diagnostics

**Transport path:** `marriage_scan()` returns a `MarriageStats` struct internally. In `tick.rs`, fold the marriage counters into the existing `FormationStats` by adding marriage-prefixed fields (not a second stats struct). The merged `FormationStats` flows through the existing pipeline: `tick_agents()` → `AgentSimulator.formation_stats` → `get_relationship_stats()` → Python-side history collector in `agent_bridge.py`. Externally, the stats map gains these keys:

- `marriages_formed`
- `marriage_pairs_evaluated`
- `marriage_pairs_rejected_hostile`
- `marriage_pairs_rejected_incest`
- `marriage_pairs_rejected_distance`
- `cross_civ_marriages`
- `same_civ_marriages`
- `cross_faith_marriages`
- `same_faith_marriages`

**Recommended but optional:** Post-run analytics extractor in `analytics.py` for marriage rate by civ and cross-civ frequency. Future settlement-based matching can use these diagnostics to evaluate urban vs rural marriage rates.

---

## 6. Scope Guard

### In Scope

- Marriage bond formation (Rust-native, scored greedy, separate pass)
- Marriage exclusivity (one spouse, remarriage after death)
- Marriage as eviction-protected bond type
- Two-parent lineage schema migration (whole stack)
- Dynasty resolution with birth-parent default + `lineage_house`
- Succession legitimacy widened to either parent
- Kin bonds to both parents at birth
- Legacy memory inheritance from both parents
- `MemoryIntent` identity validation fix
- `marriage_formed` named-character event wiring
- Diagnostic counters via existing stats map

### Out of Scope (M57b or later)

- Pooled household wealth
- Joint migration of spouses
- Widowhood policy beyond bond removal on death
- Widowhood narration events (requires dissolution tracking widening)
- Divorce / remarriage drama
- Fertility modifiers from marriage
- Settlement / urban matching context
- Succession law types (cognatic, agnatic, matrilineal)
- Age-gap penalties in matching
- Polygamy / complex household trees

### `--agents=off` Behavior

- No marriage formation path
- `parent_id_1` always `PARENT_NONE`
- `lineage_house` always 0
- Succession legitimacy check widens to both slots but has no effect
- No behavioral regression from current aggregate mode

### Legacy Python Code

Freeze `check_marriage_formation()` in `relationships.py` with a deprecation comment pointing to Rust `marriage_scan()` as authoritative. Narrow scope: deprecation targets the marriage helper and its fallback formation path only, not the rest of `relationships.py` (which contains live fallback logic and hostage codepaths).

---

## 7. Testing & Validation

### Rust Tests

**New file: `chronicler-agents/tests/test_m57a_marriage.rs`**
- Deterministic: same seed → same marriages, same parent pairs
- Exclusivity: no agent gets two Marriage bonds
- Eligibility: hostile rejected, incest rejected (both slots), age enforced, distance enforced
- Scored greedy: higher-score pairs win when agents overlap
- Pair-hash tie-break: no systematic low-id bias
- Cadence: only on-cadence regions processed
- Protected bond: Marriage not evictable
- Remarriage lifecycle: bond removed on death → survivor re-eligible → can remarry on later cadence tick
- Cross-civ: non-hostile co-located agents can marry; same-civ scores higher
- Cross-faith: different-belief agents can marry; same-belief scores higher
- Two-parent FFI round-trip: `parent_id_0`/`parent_id_1` through snapshot and promotions batches
- Birth parent capture: spouse recorded at birth-generation time, survives same-tick spouse death
- Duplicate parent defense: `parent_id_1 == parent_id_0` treated as single-parent

**Extend `chronicler-agents/tests/test_legacy_memory.rs`**
- `MemoryIntent.expected_agent_id` validation: stale slot → memory not written
- Both-parents-die-same-turn: child receives legacy from both lines

**Extend `chronicler-agents/tests/determinism.rs`**
- Marriage determinism across thread counts (1/4/8/16)
- Scored greedy + tie-break rules produce identical results

### Python Tests

**Extend `tests/test_dynasties.py`**
- Single-parent: unchanged from pre-M57a
- Two parents, one dynasty: child takes it regardless of slot
- Two parents, different dynasties: birth parent's dynasty, `lineage_house` records other
- Two parents, same dynasty: child takes it, `lineage_house` = 0
- Neither parent in dynasty: founder logic unchanged

**Extend `tests/test_m51_regnal.py`**
- Ruler as parent_0: direct-heir bonus applies
- Ruler as parent_1: direct-heir bonus applies
- Ruler in neither slot: no direct-heir bonus

**Extend `tests/test_agent_bridge.py`**
- Snapshot schema: `parent_id_0` / `parent_id_1` columns present
- Promotions schema: `parent_id_0` / `parent_id_1` columns present

**Extend `tests/test_events.py` or `tests/test_narrative.py`**
- `marriage_formed` named-character event fires correctly

**Off-mode test**
- `--agents=off`: no marriages, `parent_id_1` = `PARENT_NONE`, `lineage_house` = 0

### 200-Seed Regression

Pre/post M57a comparison on the existing regression harness.

Key metrics: population curves, dynasty counts, succession frequency, war rates, satisfaction distributions. Marriage should add visible dynastic marriages without destabilizing existing dynamics.

---

## 8. File Touch Map

### Rust

| File | Changes |
|------|---------|
| `agent.rs` | `MARRIAGE_CADENCE`, `MARRIAGE_RADIUS`, `MARRIAGE_STREAM_OFFSET = 1600` (reserved), marriage age threshold, compatibility weights |
| `pool.rs` | `parent_ids` → `parent_id_0` + `parent_id_1`, accessors, spawn/kill reset |
| `relationships.rs` | `is_protected()` adds Marriage, `get_spouse_id()` helper |
| `formation.rs` | `marriage_scan()`, shared helper extraction, `MarriageStats` |
| `tick.rs` | `BirthInfo` dual-parent fields, kin bond widening, reverse index widening, BirthOfKin for both parents |
| `ffi.rs` | Snapshot + promotions: `parent_id` → `parent_id_0` + `parent_id_1` |
| `named_characters.rs` | Dual-parent lineage state |
| `memory.rs` | `MemoryIntent.expected_agent_id`, validation in `write_all_memories()` |

### Python

| File | Changes |
|------|---------|
| `models.py` | `GreatPerson`: `parent_id_0`, `parent_id_1`, `lineage_house`, `parent_ids()` helper |
| `agent_bridge.py` | Snapshot/promotions column extraction, marriage stats passthrough |
| `dynasties.py` | Dynasty resolution rule, dual-parent `check_promotion()` consumption, shared legitimacy helper |
| `factions.py` | Succession candidate building with both parent IDs, shared legitimacy helper |
| `narrative.py` | `lineage_house` name resolution, secondary house narration context |
| `simulation.py` | `marriage_formed` event wiring for named characters |
| `relationships.py` | Deprecation comment on `check_marriage_formation()` |

### Tests

| File | Changes |
|------|---------|
| `chronicler-agents/tests/test_m57a_marriage.rs` | New: full marriage + lineage test suite |
| `chronicler-agents/tests/test_legacy_memory.rs` | `MemoryIntent` identity validation |
| `chronicler-agents/tests/determinism.rs` | Marriage determinism across thread counts |
| `tests/test_dynasties.py` | Dual-parent dynasty resolution |
| `tests/test_m51_regnal.py` | Either-parent legitimacy |
| `tests/test_agent_bridge.py` | Schema migration |
| `tests/test_events.py` or `tests/test_narrative.py` | `marriage_formed` event |

---

## 9. Decision Log

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Dynasty membership | Single `dynasty_id` + `lineage_house` | Keeps dynasty a clean tree; secondary house is metadata for future claims |
| 2 | Succession legitimacy | Either parent qualifies | Slot order is storage, not law; makes two-parent lineage politically real |
| 3 | Fertility pipeline | Unchanged; annotate second parent | Keeps M57a regression-safe; demographic teeth belong in M57b |
| 4 | Cross-civ marriage | Allowed when non-hostile, non-war, co-located | Makes secondary lineage link politically interesting; hostile/war pairs excluded |
| 5 | Marriage protection | Eviction-protected like Kin | Schema-bearing bond cannot silently vanish; removal only by explicit lifecycle events |
| 6 | Kin/memory widening | Both extended to dual-parent in M57a | Lineage coherence belongs with the lineage schema, not household economics |
| 7 | Settlement context | Deferred; pure M55a spatial proximity | Reduces coupling; settlement matching is a natural future extension |
| 8 | Formation architecture | Separate `marriage_scan()`, scored greedy | Exclusivity is a different control flow from multi-bond `evaluate_pair()` |
| 9 | Storage shape | Two parallel `Vec<u32>`: `parent_id_0` / `parent_id_1` | SoA-consistent, clean Arrow export, semantic birth-path names |
| 10 | RNG | Stream offset 1600 reserved, unused in v1 | Scored greedy is fully deterministic; noise can be added later |
| 11 | Remarriage | Allowed after spouse death | Bond removed by death cleanup; surviving agent re-enters eligible pool |
| 12 | Legacy Python code | Freeze `check_marriage_formation()` only | Narrow deprecation; rest of `relationships.py` is still live |
| 13 | Birth-time capture | Spouse recorded at generation, not commit | Spouse may die same tick; child should still record that parent |
| 14 | Co-location at birth | No check; marriage bond is sufficient | Hidden fertility gate would violate scope guard |
| 15 | Tie-break | Pair hash from `(turn, region, id_a, id_b)` | Prevents permanent low-id bias |
| 16 | Incest gate | Both parent slots checked for parent-child and sibling/half-sibling | One-generation rule; cousins deferred |
| 17 | Gendered language | None; "other parent" not "mother/father" | No sex model in M57a |
| 18 | Dynasty assignment point | Lineage materialization seam, not `check_promotion()` only | All agents need coherent dynasty, not just promoted ones |
