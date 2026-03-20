# M51: Multi-Generational Memory — Design Spec

> **Status:** Draft
> **Date:** 2026-03-20
> **Depends on:** M48 (Agent Memory, merged), M39 (Family & Lineage, merged), M50a (Relationship Substrate, merged)
> **Feeds:** M53a/b (Depth Tuning & Validation), M57 (Marriage & Households — two-parent legacy)

---

## 1. Goal & Scope

When an agent dies, their strongest memories transfer to children as legacy memories, creating dynasties that carry ancestral grudges and pride across 2-3 generations. Dynasty lineage also feeds a bounded succession scoring system and per-civ royal numbering.

**Two internal tracks:**
- **Track A (Rust):** Legacy memory transfer on agent death — ring buffer mechanics, preserved event semantics, natural multi-generational decay.
- **Track B (Python):** Dynasty-aware succession scoring + regnal numbering — minimal Leader lineage bridge, additive legitimacy weight, per-civ name registry.

**Shared contract:** M39 lineage data (`parent_id`, `dynasty_id`). M57 two-parent inheritance deferred.

Implementation order: A first, B second. Separate PRs if desired.

---

## 2. Track A: Legacy Memory Transfer

### 2.1 Trigger & Flow

Legacy memory transfer occurs during the existing death processing block in `tick.rs` (lines 387-415), where the `parent_to_children: HashMap<u32, Vec<usize>>` reverse index is already built for DeathOfKin intents.

**Flow:**

1. Agent dies → existing code looks up children via `parent_to_children[dying_agent_id]`.
2. **Before `pool.kill(slot)`**: extract the dying agent's top `LEGACY_MAX_MEMORIES` (2) memories by `|intensity|` from their ring buffer. Ties broken by lowest slot index (deterministic, no RNG consumed).
3. For each extracted memory, compute inherited intensity: `inherited = original_intensity / 2` (integer division truncating toward zero).
4. **Post-halving filter:** Skip if `|inherited| < LEGACY_MIN_INTENSITY` (10). Don't waste child buffer slots on faint memories.
5. For each living child slot: emit a `MemoryIntent` with:
   - `event_type` = **original event type** (Famine, Persecution, Victory, etc. — NOT `Legacy`)
   - `source_civ` = original memory's `source_civ` (preserves who caused the ancestral event)
   - `intensity` = halved value from step 3
   - `is_legacy = true`
   - `decay_factor_override = Some(factor_from_half_life(LEGACY_HALF_LIFE))` (100-turn half-life)
6. Legacy intents join the existing `memory_intents: Vec<MemoryIntent>` and are written in the consolidated write phase at tick end (`write_all_memories()`, tick.rs line 604).

### 2.2 Semantic Preservation

Legacy memories preserve their original `event_type`. The `MemoryEventType::Legacy` enum value (14) is **not used as the event_type**. Instead, a per-slot bitmask tracks legacy status.

This means:
- `compute_memory_utility_modifiers()` (memory.rs:244) sees a Famine memory and applies the famine migration boost — grandchildren of famine survivors are more inclined to migrate.
- `compute_memory_satisfaction_score()` reads the original intensity — ancestral persecution weighs on satisfaction.
- `agents_share_memory()` matches on the original event_type — two siblings with legacy Battle memories from the same parent can form bonds through M50b's shared-memory gate.
- Narration renders the event-specific template with an "ancestral" prefix (see Section 5).

### 2.3 SoA Extension

New field on `AgentPool` (pool.rs):

```rust
pub memory_is_legacy: Vec<u8>,  // per-agent bitmask, bit N set = slot N is legacy
```

- 1 byte per agent. Matches `memory_gates` pattern.
- Initialized to `0` on spawn (both branches).
- On eviction/overwrite of a slot: clear the corresponding bit.
- On legacy write: set the corresponding bit.

### 2.4 MemoryIntent Extension

`MemoryIntent` (memory.rs:71) gains two fields:

```rust
pub struct MemoryIntent {
    pub agent_slot: usize,
    pub event_type: u8,
    pub source_civ: u8,
    pub intensity: i8,
    pub is_legacy: bool,                    // NEW: mark as legacy memory
    pub decay_factor_override: Option<u8>,  // NEW: override default decay factor
}
```

**Required changes to `write_single_memory()` (memory.rs:143):**

1. **Decay factor override:** After selecting `write_idx`, set `pool.memory_decay_factors[slot][write_idx] = intent.decay_factor_override.unwrap_or_else(|| default_decay_factor(intent.event_type))`. Currently line 166 unconditionally calls `default_decay_factor(intent.event_type)` — the override replaces this.
2. **Legacy bit set:** If `intent.is_legacy`, set bit `write_idx` in `pool.memory_is_legacy[slot]`.
3. **Legacy bit clear on eviction:** When an existing slot is evicted (the `min_idx` branch at count == 8), clear bit `min_idx` in `pool.memory_is_legacy[slot]` **before** writing the new data. This prevents stale legacy bits when a legacy memory is replaced by a non-legacy one.

All three changes happen inside `write_single_memory()`. No separate clearing operation needed elsewhere.

Non-legacy intents (all existing sites) use `is_legacy: false, decay_factor_override: None` — zero behavioral change.

### 2.5 Intensity Halving

Integer division truncating toward zero:

| Parent Intensity | Child Inherits | Grandchild | Great-grandchild | Great-great |
|-----------------|----------------|------------|------------------|-------------|
| -90 (Persecution) | -45 | -22 | -11 | -5 (below threshold) |
| +70 (Promotion) | +35 | +17 | +8 (below threshold) | — |
| -60 (Battle) | -30 | -15 | -7 (below threshold) | — |

Natural 2-3 generation persistence for strong memories, 1-2 for moderate ones.

### 2.6 Gate Interaction

`Legacy` is not a frequency-gated type. A child can receive legacy memories from their parent dying and a DeathOfKin intent in the same consolidated write — no conflict. Under M39 single-parent lineage, each child has exactly one tracked parent, so at most `LEGACY_MAX_MEMORIES` (2) legacy intents plus 1 DeathOfKin intent per child per parent death.

### 2.7 Eviction Interaction

Legacy memories enter the ring buffer as regular entries. If the child's buffer is full (8 slots), the standard min-|intensity| eviction applies. A legacy memory at intensity 45 survives until the child accumulates 8 memories all stronger than 45 — meaning the child's own life was more formative. This is correct behavior per the roadmap scope guard.

**Explicit non-goals:** Reserved legacy slots, temporary eviction protection windows, and any structural buffer changes. If playtests show legacy memories vanish too fast, first tune `LEGACY_HALF_LIFE` or inherited intensity scaling before adding structural protection.

### 2.8 FFI Extension

`get_agent_memories()` in `ffi.rs` (line 780) currently returns `Vec<(u8, u8, u16, i8, u8)>`. M51 extends this as an **append-only** 6-tuple:

```rust
Vec<(u8, u8, u16, i8, u8, bool)>
//   ^    ^    ^    ^    ^    ^
//   |    |    |    |    |    is_legacy (NEW)
//   |    |    |    |    decay_factor
//   |    |    |    intensity
//   |    |    turn
//   |    source_civ
//   event_type
```

Python consumer update:
- Memory sync in `agent_bridge.py` (~line 508): add `"is_legacy": m[5]` to the dict comprehension.
- Mule path in `agent_bridge.py` (~line 652): **no changes needed.** Uses index-based access (`m[3]` for intensity, `strongest[0]` for event_type) which is unaffected by the appended 6th element.

### 2.9 M57 Compatibility

Under M39 single-parent lineage, each child has exactly one tracked parent. When M57 adds two-parent tracking, the same intent collection pattern works — the `parent_to_children` reverse index maps parent_id → children. M57 would add a second parent_id field and build a second reverse index (or unify into a single map). M51 does not plan for this — the death path is parent-agnostic.

---

## 3. Track B: Succession Scoring & Royal Numbering

### 3.1 Leader Model Changes

New fields on `Leader` (models.py):

```python
class Leader(BaseModel):
    # ... existing fields ...
    agent_id: int | None = None       # Set only when ruler came from a GP
    dynasty_id: int | None = None     # Set only when ruler has dynasty membership
    throne_name: str | None = None    # Base name without title (e.g., "Kiran")
    regnal_ordinal: int = 0           # 0 = first holder (no numeral), >= 2 = "II", "III", ...
```

All fields are optional/defaulted — no existing serialization breaks. `agent_id` and `dynasty_id` are present only when the ruler ascended from an agent-backed GP. Abstract faction candidates and external candidates stay `None`.

**Invariant:** `regnal_ordinal` is 0 (first holder, no numeral displayed) or >= 2 ("II", "III", ...). Value 1 is never stored.

### 3.2 Regnal Name Registry

New field on `Civilization` (models.py):

```python
regnal_name_counts: dict[str, int] = Field(default_factory=dict)
```

Maps `throne_name → count of rulers who held that throne name` for this civ. Updated at succession time. Persisted in world state (serializes naturally as a dict).

### 3.3 Name Function Split

`_pick_name()` in `leaders.py` (line 154) is shared across GPs, hostages, agent promotions, and rulers. M51 **does not modify `_pick_name()`**. Instead:

**New function:** `_pick_regnal_name(civ, world, rng) -> tuple[str, str, int]` — returns `(title, throne_name, ordinal)`. Used only for ruler succession.

- **Per-civ scoping:** Allow intra-civ reuse of throne names (necessary for numbering to fire). Cross-civ collision avoidance handled by checking other civs' current ruler throne names (lightweight, not the full `used_leader_names` machinery).
- **Ordinal computation:** After selecting a throne name, check `civ.regnal_name_counts.get(throne_name, 0)`. If > 0, ordinal = count + 1. If 0, ordinal = 0 (first holder). Increment the counter.
- **Display name composition:** `f"{title} {throne_name}"` if ordinal == 0, else `f"{title} {throne_name} {to_roman(ordinal)}"`.
- Draws from the same cultural name pools as `_pick_name()` but without the global `used_leader_names` gate.

**`to_roman(n: int) -> str`** — trivial helper, handles 1-20 range (sufficient for any realistic game).

**`world.used_leader_names`:** Removed from normal successor name selection. Retained only for founding and secession leader generation (cross-civ collision avoidance where regnal numbering doesn't apply).

### 3.4 GP Ascension & Regnal Names

When a GP wins succession in `resolve_crisis_with_factions()` (factions.py line 596), the current code copies `gp_name` as-is to `new_leader.name`. M51 changes this:

1. Extract the base name from the GP (strip any existing title prefix — split on first space, take the last part).
2. Use the base name as `throne_name`.
3. Compute `regnal_ordinal` from `civ.regnal_name_counts`.
4. Compose display name: `f"{title} {throne_name}"` or `f"{title} {throne_name} {to_roman(ordinal)}"`.
5. Set `new_leader.throne_name`, `new_leader.regnal_ordinal`, `new_leader.agent_id`, `new_leader.dynasty_id`.

The GP's personal name becomes their throne name, numbered in the civ's regnal sequence.

### 3.5 Ruler Creation Sites

All sites that create a ruler must initialize regnal metadata:

| Site | File | Line | Action |
|------|------|------|--------|
| Founding rulers | `world_gen.py` | worldgen loop | Use `_pick_regnal_name()`, seed `regnal_name_counts[throne_name] = 1` |
| Normal succession | `leaders.py` `generate_successor()` | ~189 | Use `_pick_regnal_name()` instead of `_pick_name()` |
| Faction succession | `factions.py` `resolve_crisis_with_factions()` | ~582 | `_pick_regnal_name()` for non-GP winners; GP path per Section 3.4 |
| Restored civ creation | `politics.py` | ~1001 | Use `_pick_regnal_name()`, seed counter |
| Exile restoration | `succession.py` | ~298 | Use `_pick_regnal_name()`, seed counter |
| Scenario overrides | `scenario.py` | ~534 | Currently mutates `used_leader_names` directly; also seed `regnal_name_counts` |

### 3.6 Succession Scoring

New function in `dynasties.py`:

```python
def compute_dynasty_legitimacy(candidate: dict, civ: Civilization) -> float:
    """Compute additive legitimacy bonus for a succession candidate.

    Scoped to the incumbent ruling line — only the current ruler's lineage
    matters, not any living dynasty.

    Returns 0.0 for candidates with no lineage data or no match to the
    incumbent ruler.
    """
```

**Scoring rules:**

1. **Direct heir:** `candidate["parent_id"]` matches `civ.leader.agent_id`, where both are non-zero and non-None (`parent_id` uses `PARENT_NONE = 0` as the no-parent sentinel, `agent_id` uses `None`) → return `LEGITIMACY_DIRECT_HEIR` (0.15). Strongest claim.

2. **Same dynasty:** `candidate["dynasty_id"]` matches `civ.leader.dynasty_id` (both non-None) and rule 1 didn't match → return `LEGITIMACY_SAME_DYNASTY` (0.08). Cousin, sibling, or distant relative of the ruling house.

3. **No match:** Return 0.0. Abstract candidates, external candidates, GPs from unrelated dynasties.

**Integration point:** In `generate_faction_candidates()` (factions.py line 477-495), after building a GP candidate dict, call `compute_dynasty_legitimacy()` and add the result to the candidate's `weight`. Additive alongside existing faction influence weight — matches M22 design.

**Candidate dict extension:** GP candidates gain three fields:

```python
candidates.append({
    # ... existing fields (faction, type, source, gp_name, gp_trait, weight) ...
    "agent_id": gp.agent_id,
    "parent_id": gp.parent_id,
    "dynasty_id": gp.dynasty_id,
})
```

**Lineage bridge in GP winner block:** `resolve_crisis_with_factions()` (factions.py line 596-609), after the existing name/trait copy:

```python
new_leader.agent_id = winner.get("agent_id")
new_leader.dynasty_id = winner.get("dynasty_id")
```

### 3.7 Succession Event Legitimacy Phrasing

The `succession_crisis_resolved` event description in `resolve_crisis_with_factions()` gains legitimacy context based on the lineage match:

| Match | Phrase |
|-------|--------|
| Direct heir (`parent_id` match) | "by right of blood" |
| Same dynasty (`dynasty_id` match) | "of the ruling house" |
| No lineage | No special phrasing (default) |

String composition in the event description — baked into the event that enters the bundle and curator pipeline.

**Scope:** Legitimacy phrasing lives in `resolve_crisis_with_factions()` only. The older `resolve_crisis()` in succession.py is the legacy path — no M51 changes there.

---

## 4. Narration Integration

### 4.1 Legacy Memory Rendering

`narrative.py` already has `MEMORY_DESCRIPTIONS` (12 templates) and `render_memory()` with vivid/fading descriptors. M51 extends this:

- When `is_legacy` is true for a memory, prefix the description with an ancestral qualifier: "an inherited memory of..." / "an ancestral..." / "a fading legacy of..."
- The `event_type` template drives the content: a legacy Famine memory renders as "an ancestral memory of famine" (not generic "a legacy").
- Intensity descriptors ("vivid", "fading") apply to the current inherited intensity, not the original. A legacy at intensity 20 is "fading" even if the original was "vivid" at 90.

### 4.2 Regnal Names in Narration

Regnal numbering is structurally visible — `Leader.name` carries the full display string ("King Kiran II"). The narrator sees this in all contexts where leader names appear: succession events, war declarations, diplomacy, snapshots. No special narration wiring needed.

### 4.3 Dynasty Legacy in Character Context

For named characters (GreatPersons) with legacy memories, `build_agent_context_for_moment()` gains an "ancestral memory" block:

```
Ancestral memories: {name} carries {count} inherited memories —
  {event_type} from {turn_delta} turns ago (intensity: {descriptor})
```

Gives the narrator material for lines like "Kiran, who still carried his grandfather's memory of the Tessaran famine..."

---

## 5. Testing Strategy

### 5.1 Rust Unit Tests (Track A)

- **Legacy extraction:** Agent with 8 memories of varying intensity → extract top 2 by |intensity|, verify correct selection and tiebreak by slot index.
- **Intensity halving:** Integer truncation toward zero for positive and negative values. -90 → -45, +70 → +35, -11 → -5, +1 → 0 (below threshold, skipped).
- **Post-halving filter:** Memories with |inherited_intensity| < `LEGACY_MIN_INTENSITY` are not emitted.
- **Legacy bitmask:** Written memory has `memory_is_legacy` bit set. Original event_type preserved. Decay factor overridden to legacy half-life.
- **Eviction of legacy:** When child buffer is full, legacy memory at intensity 20 is evictable by a new memory at intensity 25. Legacy bit cleared on eviction.
- **Utility preservation:** Legacy Famine memory produces the same utility modifiers as a direct Famine memory (at lower intensity).
- **Satisfaction preservation:** Legacy memories contribute to `compute_memory_satisfaction_score()` at their inherited intensity.
- **Shared memory matching:** Two siblings with legacy Battle memories from the same parent (same event_type, same write-turn — the turn of parent death, not the original memory's turn) match via `agents_share_memory()`. Note: `write_all_memories()` stamps the current turn, so siblings inheriting from the same death event share identical turns. Distant relatives inheriting across different generations will NOT match (different write-turns).

### 5.2 Rust Integration Tests

- **Multi-generational decay:** Parent dies with Persecution at -90 → child gets -45 → child dies → grandchild gets -22 → grandchild dies → great-grandchild gets -11 → great-grandchild dies → great-great-grandchild gets -5 → below threshold, not transferred. Verify 3-generation persistence.
- **Legacy + own experience:** Child inherits 2 legacy memories, then accumulates 6 own. All 8 slots full. New intense experience evicts the weaker legacy. Verify correct eviction target.
- **DeathOfKin + legacy same tick:** Parent dies → child gets DeathOfKin intent AND legacy intents in the same consolidated write. All three intents land (no conflict, no double-gate).
- **Legacy does not leak:** Legacy extraction only happens during death processing. No legacy intents on subsequent ticks for the same death. Verify via 2-turn test.

### 5.3 Python Tests (Track B)

- **Regnal numbering:** First ruler "King Kiran" → ordinal 0, no numeral. Second ruler with same throne name → "King Kiran II", ordinal 2. Third → "King Kiran III".
- **Regnal counter persistence:** `civ.regnal_name_counts` survives serialization round-trip.
- **GP lineage bridge:** GP candidate with agent_id/parent_id/dynasty_id → wins succession → new Leader carries all three fields.
- **Legitimacy scoring:** Direct heir of agent-backed ruler gets +0.15. Same dynasty gets +0.08. Non-dynasty GP gets 0. Abstract candidate gets 0.
- **Legitimacy scoped to incumbent:** GP from a different living dynasty gets 0 bonus.
- **Worldgen seeding:** First ruler's throne_name and ordinal set correctly. `regnal_name_counts` initialized with count 1.
- **Name reuse scoping:** Per-civ reuse allowed (same throne name returns with next ordinal). Cross-civ collision avoidance for founding.
- **GP ascension regnal:** GP winner's base name becomes throne_name, ordinal computed from civ counter, display name composed with title + ordinal.
- **Narrative context:** Legacy memories render with "ancestral" prefix. Succession events include legitimacy phrasing.

### 5.4 FFI Tests

- `get_agent_memories()` 6-tuple: write legacy memory via intent → read via FFI → `is_legacy` is true, `event_type` is original.
- Backward compat: non-legacy memories return `is_legacy = false` as 6th element.

---

## 6. Scope Boundaries

### 6.1 In Scope

**Track A (Rust):**
- Legacy memory extraction on agent death (tick.rs death path)
- `memory_is_legacy: Vec<u8>` bitmask on AgentPool
- `MemoryIntent` extended with `is_legacy: bool` + `decay_factor_override: Option<u8>`
- `get_agent_memories()` FFI extended to 6-tuple with legacy flag
- Legacy narrative rendering ("ancestral memory of...")
- Character context block for legacy memories in `build_agent_context_for_moment()`

**Track B (Python):**
- `Leader.agent_id`, `Leader.dynasty_id`, `Leader.throne_name`, `Leader.regnal_ordinal`
- `Civilization.regnal_name_counts: dict[str, int]`
- `_pick_regnal_name()` — new function, separate from `_pick_name()`
- `to_roman()` helper (1-20 range)
- `compute_dynasty_legitimacy()` — additive weight on GP candidates
- GP candidate dict extended with `agent_id`, `parent_id`, `dynasty_id`
- Lineage bridge in `resolve_crisis_with_factions()` GP winner block
- GP ascension regnal name recomputation (not raw gp_name copy)
- Succession event legitimacy phrasing
- Regnal counter seeding at all 6 ruler creation sites
- `world.used_leader_names` restricted to founding/secession only

### 6.2 Not In Scope

- Multiple succession law types (M63)
- Synthetic lineage for abstract/non-GP leaders
- Two-parent legacy inheritance (M57)
- Full `leader_history` list on Civilization
- Genealogical distance computation beyond parent-child + dynasty-match
- Trait mixing rule from DYNASTY enrichment (low-risk add-on, not core)
- Legacy memory protection windows or reserved slots
- Probabilistic legacy transfer (deterministic only)
- Changes to `resolve_crisis()` in succession.py (legacy path)
- Changes to `_pick_name()` (shared character-name helper, untouched)

---

## 7. Constants

All `[CALIBRATE]` for M53.

| Constant | Domain | Initial | Notes |
|----------|--------|---------|-------|
| `LEGACY_HALF_LIFE` | Memory | 100.0 | Already in agent.rs, used as decay override |
| `LEGACY_MIN_INTENSITY` | Memory | 10 | Post-halving filter threshold |
| `LEGACY_MAX_MEMORIES` | Memory | 2 | Top-N extracted on death |
| `LEGITIMACY_DIRECT_HEIR` | Succession | 0.15 | Additive weight for ruler's child |
| `LEGITIMACY_SAME_DYNASTY` | Succession | 0.08 | Additive weight for same dynasty |

5 constants. Plus existing M48 memory constants (intensity values, half-lives per event type) that affect legacy behavior through inheritance.

---

## 8. M53 Calibration Guidance

- **Legacy persistence duration:** Monitor how many generations legacy memories survive across 200 seeds. Target: 2-3 for strong memories (|intensity| > 60), 1-2 for moderate. If too short, increase `LEGACY_HALF_LIFE` or reduce halving severity. If too long, decrease half-life.
- **Legacy eviction rate:** Track what fraction of legacy memories are evicted before natural decay. If > 50% evicted within 20 turns of inheritance, the child's own life is overwhelming ancestry too fast — consider increasing `LEGACY_MIN_INTENSITY` to only transfer impactful memories.
- **Legitimacy impact on succession:** Measure how often dynasty-linked GP candidates win succession with vs. without the legitimacy bonus. Target: noticeable but not dominant — dynasty candidates should win ~10-20% more often with the bonus, not 100%.
- **Legitimacy activation rate:** Track how often the legitimacy system fires at all. The lineage bridge only exists for GP-sourced rulers — if most rulers are non-GP (abstract faction/external candidates), `civ.leader.agent_id` is None and no scoring happens. Measure the fraction of successions where the incumbent ruler has lineage data. If < 20%, the system is decorative. If this is a problem, consider lightweight lineage inference (e.g., "heir" succession type could inherit the previous ruler's dynasty_id) in a future milestone.
- **Regnal numbering frequency:** Track how often ordinals > 0 appear. Target: 1-3 regnal repetitions per civ per 500-turn run in long-lived civs.
- **Shared legacy bonds:** Monitor sibling/cousin pairs with matching legacy memories who form M50b bonds. If too rare (< 5% of eligible pairs), legacy memories may be decaying too fast before formation scans reach them.
- **Persecution cascade amplification:** Legacy persecution memories add to the existing M38b + M48 + M49 triple-stacking concern. Monitor total rebel modifier budget for agents carrying both direct and legacy persecution memories.
