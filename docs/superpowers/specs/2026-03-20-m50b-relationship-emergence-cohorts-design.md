# M50b: Relationship Emergence & Cohorts — Design Spec

> **Status:** Draft (dependent spec — assumes M50a contract)
> **Date:** 2026-03-20
> **Depends on:** M50a (Relationship Substrate, spec'd), M48 (Agent Memory, merged), M49 (Needs System, merged), M40 (Social Networks, merged)
> **Feeds:** M53a/b (Depth Tuning & Validation), M57a (Marriage & Households), M59a (Regional Knowledge Layer)

---

## 1. Goal & Scope Rule

Give agents the ability to form, maintain, and dissolve relationships emergently through a Rust-native formation engine. M50a provides the storage, drift, and interface substrate. M50b makes the social graph come alive — bonds form from shared experience and cultural proximity, strengthen through co-location, and dissolve when structurally invalid.

**Scope rule:** M50b owns formation intelligence, active dissolution, social-need blend plumbing, and cohort-facing instrumentation. M50a owns persistence, drift thermodynamics, and the FFI interface. M53 owns calibration of all `[CALIBRATE]` constants and the social-need alpha ramp.

**Dependent spec status:** This spec is written against an explicit Assumed M50a Contract (Section 2). After M50a's internal review, a contract reconciliation pass updates any provisional references. Implementation waits for M50a merge, but the spec does not.

---

## 2. Assumed M50a Contract

M50b depends on these M50a deliverables. Items marked `[PROVISIONAL]` may change names or signatures during M50a review.

| Contract Item | Source | Status |
|---------------|--------|--------|
| Per-agent SoA store (8 slots, 65 bytes/agent) | `pool.rs` | Spec'd |
| `BondType` enum (Mentor=0, Rival=1, Marriage=2, ExileBond=3, CoReligionist=4, Kin=5, Friend=6, Grudge=7) | `relationships.rs` `[PROVISIONAL]` | Spec'd — **ordinals must match M40 `RelationshipType` for values 0-4** |
| `is_protected(bond_type) -> bool` (Kin only in M50a) | `relationships.rs` `[PROVISIONAL]` | Spec'd |
| `is_positive_valence(bond_type) -> bool` | `relationships.rs` `[PROVISIONAL]` | Spec'd |
| `find_relationship(pool, slot, target_id, bond_type) -> Option<usize>` | `relationships.rs` `[PROVISIONAL]` | Spec'd |
| `read_rel(pool, slot, rel_idx) -> (u32, i8, u8, u16)` | `relationships.rs` `[PROVISIONAL]` | Spec'd |
| `write_rel(pool, slot, rel_idx, target_id, sentiment, bond_type, formed_turn)` | `relationships.rs` `[PROVISIONAL]` | Spec'd |
| `find_evictable(pool, slot) -> Option<usize>` | `relationships.rs` `[PROVISIONAL]` | Spec'd |
| `apply_relationship_ops(batch: RecordBatch)` on `AgentSimulator` | `ffi.rs` `[PROVISIONAL]` | Spec'd |
| Kin auto-formation in birth application path | `[PROVISIONAL]` | Spec'd |
| Deterministic sentiment drift per tick (phase 0.8 in `tick.rs`) | `tick.rs` | Spec'd |
| `get_social_edges()` projection (M40 compat) | `ffi.rs` | Spec'd |
| `replace_social_edges()` compatibility shim | `ffi.rs` | Spec'd |
| `get_agent_relationships()` per-GP FFI | `ffi.rs` `[PROVISIONAL]` | Spec'd |
| RNG stream offset 1100 reserved for M50 | `agent.rs` STREAM_OFFSETS | Spec'd |
| `rel_count: Vec<u8>` as occupancy signal | `pool.rs` | Spec'd |
| Packed-prefix invariant with swap-remove | `relationships.rs` | Spec'd |
| `UpsertSymmetric` atomicity (both sides or neither) | `ffi.rs` | Spec'd |
| `GreatPerson.agent_bonds` field (not `.relationships`) | `models.py` | Spec'd |

**Post-M50a reconciliation checklist:**
- Verify all `[PROVISIONAL]` function names and signatures match landed code.
- **Verify M50a `BondType` enum ordinals match M40 `RelationshipType` for values 0-4.** If M50a ships with a different ordering, file a blocking issue before M50b implementation.
- **Verify RNG stream offset 1100 is registered in `agent.rs` `STREAM_OFFSETS` block AND included in `test_stream_offsets_no_collision`.** If M50a does not register it, M50b implementation must register it as its first action. (Phoebe B-1)
- Confirm whether `replace_social_edges()` survives late M50a or dies in early M50b.
- Check if M50a added any new read APIs beyond `get_agent_relationships()`.
- Confirm `relationships.rs` module name and public API surface.
- ~~**[M50a bug] Stale parent slot in demographics apply loop.**~~ Fixed in M50a.
- ~~**[M50a bug] `apply_relationship_ops()` accepts `UpsertSymmetric(Kin)`.**~~ Fixed in M50a.
- ~~**[M50a gap] `kin_bond_failures` not observable from Python.**~~ Fixed in M50a.

---

## 3. Formation Engine

Rust-native formation pass running at staggered cadence, scanning co-located agent pairs for bond eligibility. Formation intelligence lives with the data it scans.

### 3.1 Scan Scheduling

Regions are bucketed into `FORMATION_CADENCE` groups (target: 5-8 `[CALIBRATE]`). Each tick, one bucket is eligible. Region assignment: `region_index % FORMATION_CADENCE`. This distributes formation work evenly across ticks and ensures deterministic scheduling.

On a formation tick for bucket B, the engine iterates all regions where `region_index % FORMATION_CADENCE == B`. For each region, it runs the full-scan formation pass over co-located agents.

### 3.2 Candidate Ordering

Within a region scan, the agent list is deterministically shuffled using a hash-based rotation seeded by `(turn, region_index)`. No RNG consumed — pure hash. This prevents low-ID agents from systematically socializing first when formation caps are hit.

After shuffling, pairs are iterated in order `(i, j)` where `i < j` over the shuffled list. Same seed + same state → same pair ordering → same formation results.

Building the per-region agent list: collect all alive agent slots where `pool.regions[slot] == region_index`, shuffle by `hash(turn, region_index, agent_id)` as sort key.

**Slot-vs-ID convention:** The shuffled list contains slot indices. Use `pool.ids[slot]` to obtain agent IDs for relationship store reads/writes (the store uses agent IDs, not slot indices). The formation scan also needs an `agent_id → slot` mapping for belief-divergence checks and target resolution — build a `HashMap<u32, usize>` once per region scan, reuse for all pairs and dissolution checks.

**Hash function constraint:** The shuffle hash must be a deterministic integer mix function that produces identical output across Rust compiler versions and platforms. Use a simple multiply + xor-shift mix over the three inputs (turn, region_index, agent_id). Do not use Rust's default `HashMap` hasher (RandomState), which is deliberately non-deterministic across runs.

### 3.3 Similarity Gate

Each bond type has its own deterministic eligibility check. The gate is not a universal similarity score — it's a per-type predicate that reflects what that bond means.

**Weighted compatibility score** (used by Friend and as a soft factor for Rival):

```
score = W_CULTURE * cultural_similarity
      + W_BELIEF  * (belief_match ? 1 : 0)
      + W_OCCUPATION * (occupation_match ? 1 : 0)
      + W_AFFINITY * (affinity_match ? 1 : 0)
```

Default weights: `W_CULTURE = 0.35, W_BELIEF = 0.35, W_OCCUPATION = 0.15, W_AFFINITY = 0.15` `[CALIBRATE]`. Culture and belief are identity-stable; occupation and affinity can flip. Total range [0.0, 1.0].

**Weighted cross-rank cultural similarity:**

```
For each value v in A's cultural slots (0, 1, 2):
    if v matches B's slot at the same rank → SAME_RANK_WEIGHT (1.0)
    elif v matches B's slot at a different rank → CROSS_RANK_WEIGHT (0.5)
    else → 0.0

cultural_similarity = sum of matched weights / 3.0
```

Each shared cultural value is counted at most once using its best positional match (same-rank wins over cross-rank — greedy assignment). Two agents sharing all three values in the same order: `3.0 / 3.0 = 1.0`. Same three values in different order: `1.5 / 3.0 = 0.5`. One shared value at same rank: `1.0 / 3.0 = 0.33`.

`SAME_RANK_WEIGHT` and `CROSS_RANK_WEIGHT` are `[CALIBRATE]` for M53.

### 3.4 Bond-Type Formation Rules

Each type has a gate (hard prerequisites) and deterministic eligibility logic.

**Friend:**
- Gate: `compatibility_score >= FRIEND_THRESHOLD` `[CALIBRATE]` (target: 0.50) AND `agents_share_memory(pool, a, b).is_some()`
- Sentiment: `FRIEND_INITIAL_SENTIMENT` `[CALIBRATE]` (~+30)
- Bond: `UpsertSymmetric` (both sides or neither)
- Triadic boost: if pair shares a positive contact above `TRIADIC_MIN_SENTIMENT` `[CALIBRATE]` (~+40), threshold relaxes by `TRIADIC_THRESHOLD_REDUCTION` `[CALIBRATE]` (~0.15). Capped at one shared contact — no stacking.

**CoReligionist:**
- Gate: `beliefs[a] == beliefs[b]` AND `beliefs[a] != BELIEF_NONE` AND region is minority-faith context (`belief_count_in_region < region_population * MINORITY_THRESHOLD` `[CALIBRATE]` (~0.40))
- No general similarity check — shared minority belief is sufficient.
- Sentiment: `CORELIGIONIST_INITIAL_SENTIMENT` `[CALIBRATE]` (~+25)
- Bond: `UpsertSymmetric`
- Note: minority context requires a per-region belief census. Build `HashMap<u8, usize>` of belief counts from a pre-pass over the region's alive agent slots at scan start. Cost: O(agents_in_region) per region per cadence tick, computed once and reused for all pairs.

**Rival:**
- Gate: same occupation AND `abs(wealth[a] - wealth[b]) < RIVAL_WEALTH_PROXIMITY` `[CALIBRATE]` (initial: 50.0) AND `compatibility_score >= RIVAL_SIMILARITY_FLOOR` `[CALIBRATE]` (target: 0.30 — lower than Friend, rivals are near-peers, not necessarily friends)
- Personality filter: at least one agent has `pool.ambition[slot] >= RIVAL_MIN_AMBITION` `[CALIBRATE]` (initial: 0.5)
- Sentiment: `RIVAL_INITIAL_SENTIMENT` `[CALIBRATE]` (~-20)
- Bond: `UpsertSymmetric`

**Mentor:**
- Gate: same occupation AND age gap `>= MENTOR_AGE_GAP` `[CALIBRATE]` (target: ~15, directional)
- The region scan iterates unordered pairs `(A, C)`. The Mentor rule evaluates both orientations: if `age[A] - age[C] >= MENTOR_AGE_GAP`, emit `UpsertDirected(A → C)`. If `age[C] - age[A] >= MENTOR_AGE_GAP`, emit `UpsertDirected(C → A)`. At most one direction fires per pair. If both are old enough to mentor each other (within gap), neither fires — peers don't mentor peers.
- No general similarity requirement — mentorship crosses cultural lines.
- Sentiment: `MENTOR_INITIAL_SENTIMENT` `[CALIBRATE]` (~+35)
- Bond: `UpsertDirected` (mentor → apprentice only, asymmetric type per M50a spec)
- **Historical semantics:** once formed, Mentor bonds persist regardless of occupation changes. Drift handles sentiment decay if they part ways. No active dissolution for Mentor.

**Grudge:**
- Gate: `agents_share_memory_with_valence(pool, a, b)` returns a match where at least one agent's intensity is negative AND agents have different `civ_affinity` (opposing sides)
- Overrides low similarity — grudges form across cultural lines.
- Sentiment: `GRUDGE_INITIAL_SENTIMENT` `[CALIBRATE]` (~-30)
- Bond: `UpsertSymmetric`

**ExileBond:**
- Gate: `origin_regions[a] != pool.regions[a]` (agent A is away from birth region) AND `origin_regions[b] != pool.regions[b]` (agent B is away from birth region) AND `region.controller_civ != 255` (region is controlled, not neutral — 255 is the uncontrolled sentinel) AND `region.controller_civ != civ_affinities[a]` AND `region.controller_civ != civ_affinities[b]` (both living under foreign rule)
- Optional sentiment boost when `origin_regions[a] == origin_regions[b]` (shared homeland), but not a hard gate.
- Sentiment: `EXILE_INITIAL_SENTIMENT` `[CALIBRATE]` (~+35)
- Bond: `UpsertSymmetric`

### 3.5 Triadic Closure

Implemented as a pair-local modifier inside the formation scan, not a separate pass. During the Friend eligibility check for pair `(A, C)`:

1. Compute `shared_positive_contacts(A, C)`: intersect `rel_target_ids` for both agents, filtering to slots where `is_positive_valence(bond_type)` AND `sentiment >= TRIADIC_MIN_SENTIMENT`. At 8 slots each, worst case 64 comparisons.
2. If at least one shared contact exists, reduce the Friend compatibility threshold by `TRIADIC_THRESHOLD_REDUCTION`.
3. `Rival` and `Grudge` bonds in the contact set are excluded.
4. Effect is capped at one bonus — multiple shared contacts don't stack further.

### 3.6 Formation Budgeting

To prevent explosive graph growth on a single cadence tick:

- **Per-agent cap:** Each agent may gain at most `MAX_NEW_BONDS_PER_PASS` `[CALIBRATE]` (target: 2) new bonds per formation pass. Tracked via a temporary per-scan counter, not persisted.
- **Per-region cap:** `MAX_NEW_BONDS_PER_REGION` `[CALIBRATE]` (target: ~50) total new bonds per region per pass. Once hit, remaining pairs are skipped. Bounds worst-case work and prevents a large homogeneous region from forming hundreds of bonds simultaneously.
- Caps apply to new bond creation only — upserts to existing bonds (sentiment updates) are uncapped.

### 3.7 Early Rejection Cascade

Within the pair loop, checks are ordered cheapest-first:

1. **Existing bond check:** `find_relationship(pool, a_slot, b_id, candidate_type).is_some()` → skip (already bonded for this type)
2. **Capacity check:** For symmetric bonds: both agents have `rel_count < 8` OR `find_evictable()` returns a non-protected slot → proceed. If either side is full with all protected, skip. For `UpsertDirected` (Mentor only): capacity check applies to source agent only.
3. **Budget check:** neither agent has hit `MAX_NEW_BONDS_PER_PASS` → proceed
4. **Type-specific gate:** the bond-type rules from 3.4
5. **Shared memory / similarity:** the expensive checks, only reached if all cheap gates pass

### 3.8 New Helper: `agents_share_memory_with_valence()`

```rust
/// M50b: Like agents_share_memory but returns per-agent signed intensities.
/// Returns (event_type, turn, intensity_a, intensity_b) of strongest shared match.
pub fn agents_share_memory_with_valence(pool: &AgentPool, a: usize, b: usize)
    -> Option<(u8, u16, i8, i8)>
```

Same scan logic as `agents_share_memory()`, returns signed intensities for both agents. Used by Grudge formation gate (`intensity_a < 0 OR intensity_b < 0`). Friend formation uses the existing `agents_share_memory()` (doesn't need sign).

### 3.9 RNG Usage

Formation uses the reserved M50 stream offset (1100). RNG is **not consumed** by the deterministic baseline. The hash-based scan rotation and all formation gates are pure functions of state. Stream offset 1100 remains genuinely unused until M53 activates probabilistic formation.

---

## 4. Dissolution Engine

Rust owns the full relationship lifecycle. Dissolution splits into two classes with different cadences.

### 4.1 Structural Invalidation — Every Tick

**Death cleanup:** After the demographics sequential-apply block in `tick.rs` (after `pool.kill()` calls at phase 5, before cultural drift at phase 6), collect dead agent IDs for the tick into a `HashSet<u32>`. Run a linear sweep over all alive agents' occupied relationship slots:

- If `rel_target_ids[slot][i]` is in the dead-ID set → swap-remove, decrement `rel_count`, clear tail sentinel.
- The dead agent's own slots don't need cleanup — their entire SoA row is already dead and won't be scanned.

**Implementation note:** Cleanup loops use `while i < rel_count[slot]` (not `for i in 0..rel_count`). After a swap-remove, `rel_count` decrements and the swapped-in entry at index `i` must be re-checked. Increment `i` only when no removal occurs.

Cost: O(alive_agents × avg_rel_count). At 50K agents × ~4 avg occupied slots = 200K slot reads per tick. The dead-ID set is a `HashSet<u32>` built once per tick from the death list.

### 4.2 Structural Invalidation — On Formation Cadence

**Belief-divergence cleanup:** During the staggered formation scan, before evaluating new pair candidates for a region, sweep all agents in that region's slot list:

- For each occupied slot with `bond_type == CoReligionist`: if `beliefs[agent] != beliefs[target]` (beliefs diverged) → swap-remove.
- Target resolution: targets may have migrated out of this region. Use a pool-wide `HashMap<u32, usize>` (id → slot) built once per cadence tick, not the per-region map from the formation scan.
- Uses the same `while i < rel_count` loop pattern.

**Mentor:** Historical semantics — Mentor bonds persist regardless of occupation changes. No active dissolution. Drift handles sentiment decay if they part ways.

### 4.3 Soft Decay — Drift + Eviction

Handles bonds between **living** agents who have drifted apart:

- **Sentiment drift (M50a):** Co-located bonds strengthen, separated bonds decay toward 0. Runs every tick at phase 0.8.
- **Eviction on slot pressure:** When a new bond needs a slot and all 8 are occupied, `find_evictable()` removes the weakest non-protected bond. Natural Dunbar-style pruning.
- No explicit dissolution for Friend, Rival, Grudge, ExileBond beyond drift. A friend who moves away decays naturally. A grudge between separated agents fades (slowly — negative decay is 3-5x slower per M50a).

### 4.4 Dissolution Ordering Within Tick

```
0.    Memory decay + Skill growth
0.5   Wealth tick
0.75  Needs update
0.8   Sentiment drift (M50a) — runs before demographics
1.    Satisfaction
2-4.  Region stats, Decisions, Apply decisions
5.    Demographics (deaths, births, kin auto-formation)
5.1   Death cleanup sweep (M50b) — bonds to this tick's dead agents removed
6.    Cultural drift + Conversion tick
6.5   War-survival marking, displacement decrement
7.    Memory intent collection + consolidated write
8.    Formation scan (M50b, staggered cadence — includes belief-divergence cleanup)
```

Death cleanup (5.1) runs every tick. Formation scan (8) runs only on eligible cadence ticks for the active bucket. M50a drift (0.8) runs before demographics — a bond to a soon-to-die agent gets one extra drift tick, then is eagerly cleaned at 5.1 the same tick. Tolerable.

---

## 5. Social-Need Blend

### 5.1 Blend Formula

Replace the current `social_restoration()` proxy in `needs.rs` with a blend:

```
social_restore = (1.0 - SOCIAL_BLEND_ALPHA) * pop_proxy + SOCIAL_BLEND_ALPHA * bond_factor
```

Where:
- `pop_proxy` = existing `social_restoration()` logic (population ratio × occupation multiplier × age multiplier × deficit)
- `bond_factor` = `SOCIAL_RESTORE_BOND * (positive_bond_count as f32 / SOCIAL_BOND_TARGET).min(1.0) * deficit`
- `positive_bond_count` = count of occupied slots with `is_positive_valence(bond_type)` and `sentiment > 0`
- `SOCIAL_BOND_TARGET` `[CALIBRATE]` (~4) = positive bonds for full social restoration
- `SOCIAL_RESTORE_BOND` `[CALIBRATE]` = base restoration rate from bonds (comparable to `SOCIAL_RESTORE_POP`)

### 5.2 Alpha Default

`SOCIAL_BLEND_ALPHA = 0.0` `[CALIBRATE]` at M50b ship. Behaviorally identical to the current proxy. When `alpha == 0.0`, the bond scan is skipped entirely (early return to existing logic). No performance cost at default. M53 ramps alpha.

### 5.3 Mentor Apprentice Credit

At `alpha = 0.0`, no bond scan runs — asymmetry doesn't manifest. When M53 ramps alpha, incoming-Mentor credit is an M53 refinement: precompute incoming mentor counts once per tick (not a per-agent full-pool scan inside `social_restoration()`). M53 also decides whether `positive_bond_count` means raw positive slots or unique positive counterpart IDs.

### 5.4 Occupation/Age Modifier Survival

When `alpha = 1.0`, the occupation and age multipliers from the population proxy are **intentionally dropped**. The bond-based factor replaces them — merchants and priests form more bonds (CoReligionist, trade contacts), older agents accumulate more bonds over time. The proxy's multipliers modeled the *absence* of relationship data; with real data, they become redundant.

M53 must verify: if bond-only restoration at `alpha = 1.0` shows less per-agent diversity than the proxy, re-introduce occupation weighting as a multiplier on `bond_factor`. This is a calibration decision, not a design invariant.

### 5.5 Proxy Removal Path

When M53 validates `alpha = 1.0` stability:
1. Pop-proxy branch becomes dead code
2. Remove proxy logic, simplify `social_restoration()` to bond-only
3. `// Pre-M50 proxy` comment in `needs.rs` becomes a deletion target

---

## 6. Turn Ordering & Override Policy

### 6.1 Formation Scan Placement

The formation scan runs as the last Rust-side operation inside `tick_agents()`, after all existing phases complete (see Section 4.4 for full ordering). Formation sees fully resolved tick state — deaths cleaned, drift applied, new kin bonds from births, cultural/belief updates landed.

### 6.2 Cross-Language Turn Order

Per turn:
```
1. Python phases 1-9 (simulation.py)
2. Rust tick_agents() — includes M50b formation scan at phase 8
3. Python Phase 10 (consequences, emergence, factions, succession, snapshots)
```

Rust formation runs inside step 2. Python's Phase 10 runs after Rust tick.

### 6.3 Python Formation Pass — Gated Off

`form_and_sync_relationships()` (simulation.py:1419) is the M40 Python-side formation coordinator. In any mode where Rust tick is active, M50b gates this call off:

```python
if agent_bridge is not None and not agent_bridge.rust_owns_formation:
    # Legacy M40 path — only active when Rust tick is not running
    from chronicler.relationships import form_and_sync_relationships
    ...
```

`rust_owns_formation` is a boolean on `AgentBridge`, set to `True` when M50b's Rust formation engine is active. Default `True` once M50b ships. Can be set to `False` for regression testing against the M40 baseline.

**`--agents=off` note:** In off mode, `AgentBridge` is `None` (only created for `demographics-only`, `shadow`, `hybrid` in `main.py`). The Phase 10 relationship pass is already gated behind `agent_bridge is not None`, so it never runs in off mode. Off mode has **no relationship formation** — neither M40 nor M50b. This is the existing behavior and M50b does not change it. If off-mode relationship narration is ever needed, it would require a separate Python-only formation path unrelated to M50b's scope.

### 6.4 `apply_relationship_ops()` Survival

The FFI method survives. Nothing in the normal per-turn loop calls it once `form_and_sync_relationships()` is gated off. Available for:
- Rare explicit Python-side overrides (curator-driven narrative interventions, test fixtures)
- The `replace_social_edges()` compatibility shim (if any downstream code still calls it)

Manually-placed bonds are subject to the same structural invalidation rules as any bond (death cleanup, belief-divergence cleanup). They are not immune to dissolution.

### 6.5 `replace_social_edges()` Shim

Survives M50b as an API surface but is no longer called in the per-turn loop once `form_and_sync_relationships()` is gated off. Remains functional for any code that still references it directly.

Deprecation log: first call emits `logger.info("replace_social_edges() shim active — legacy M40 path")`. One-time per run.

**Removal target:** After M50b ships and `relationships.py`'s formation functions are confirmed unused in agent modes, remove `form_and_sync_relationships()`, the shim, and the old `SocialGraph` struct as a cleanup task.

---

## 7. Deferred Hooks

### 7.1 Synthesis-Budget (Deferred to M53+)

**Concept:** Per-agent `synthesis_budget: u8` that depletes as M48 memories arrive. When budget hits 0, the agent becomes "formation-eligible" — concentrating formation activity around dramatic periods.

**M50b ships:** Dormant field reservation only. Add `synthesis_budget: Vec<u8>` to `AgentPool` SoA, initialized to `SYNTHESIS_BUDGET_MAX` `[CALIBRATE]` at spawn, decremented nowhere. 1 byte/agent. **Internal-only:** no snapshot column, no FFI getter, no Python sync.

**M53 activation path:** If fixed cadence produces either (a) excessive peacetime compute or (b) insufficient crisis-period formation, M53 may wire synthesis-budget as a formation-eligibility flag. The formation scan would then only evaluate pairs where at least one agent has `synthesis_budget == 0`. Flag resets after the scan processes that agent.

**Design constraint:** Synthesis-budget is a *filter* on the existing formation scan, not a replacement. Staggered cadence and deterministic pair evaluation remain unchanged.

### 7.2 Probabilistic Formation (Deferred to M53+)

**Concept:** Axelrod-style `P(form) = similarity^D` where D > 1 amplifies majority preference.

**M50b ships:** Deterministic bounded-confidence gates only. No RNG consumed for formation decisions. Stream offset 1100 remains genuinely unused.

**M53 activation path:** If deterministic gates produce graphs that are too blocky or too brittle, M53 may introduce probabilistic formation. This is a per-bond-type option — some types (CoReligionist, ExileBond) may remain deterministic even if Friend and Rival become probabilistic.

---

## 8. Instrumentation & M53 Validation Hooks

### 8.1 Per-Tick Counters (on AgentSimulator)

| Counter | Type | Incremented When |
|---------|------|-----------------|
| `bonds_formed` | u32 | New bond created (any type) during formation scan |
| `bonds_dissolved_death` | u32 | Bond removed by death cleanup sweep |
| `bonds_dissolved_structural` | u32 | Bond removed by belief-divergence or other structural invalidation |
| `bonds_evicted` | u32 | Bond displaced by eviction during formation |
| `formation_pairs_evaluated` | u32 | Total candidate pairs checked during formation scan |
| `formation_pairs_eligible` | u32 | Pairs that passed all gates (whether or not bond was created) |
| `kin_bond_failures_delta` | u32 | Kin auto-formation failures this tick (delta from M50a's cumulative `kin_bond_failures`) |

Counters reset to 0 at start of each tick. Note: M50a's `kin_bond_failures` on `AgentSimulator` is cumulative (uses `saturating_add`). `get_relationship_stats()` computes the per-tick delta by snapshotting the cumulative value at tick start. Exposed to Python via a `get_relationship_stats()` FFI method returning a dict. Logged at `logger.debug` level per tick when any counter is non-zero.

### 8.2 Per-Tick Distribution Snapshots

Computed once per tick after the formation scan, only when enabled by `--relationship-stats` CLI flag or during M53 runs. Off by default.

All metrics use **directed-slot semantics** — each occupied slot is one entry. Logical-bond normalization (deduplication of symmetric pairs) is M53b analytics scope.

| Metric | Computation | Purpose |
|--------|-------------|---------|
| `mean_rel_count` | Mean of `rel_count` across alive agents | Graph density tracking |
| `mean_positive_sentiment` | Mean sentiment of positive-valence occupied slots | Bond health |
| `bond_type_counts[8]` | Count of occupied slots per BondType | Type distribution |
| `cross_civ_bond_fraction` | Fraction of directed slots where `civ_affinity[src] != civ_affinity[target]` | Cultural boundary permeability |

Returned alongside per-tick counters via `get_relationship_stats()`.

### 8.3 Cohort Detection Hook (M53b Target)

M50b does not implement cohort detection. M50b provides the data M53b needs:

- Relationship store readable via `get_agent_relationships()` per agent (M50a contract).
- Memory data readable via `get_agent_memories()` (M48, merged).
- **Required:** `get_all_relationships() -> RecordBatch` bulk Arrow export of the full directed-slot store. Schema: `[agent_id: u32, target_id: u32, sentiment: i8, bond_type: u8, formed_turn: u16]`. O(alive_agents × avg_rel_count) rows. Used only by analytics/validation, not per-turn. (No `slot_idx` — internal slot ordering is not exposed to analytics.)
- M53b runs label propagation or connected-component analysis over the positive-bond subgraph.

### 8.4 Analytics Extractor

New `extract_relationship_metrics()` function in `analytics.py`, parallel to existing extractors. Reads per-tick stats from `get_relationship_stats()` and appends to turn-level analytics output. Available for the 200-seed health check pipeline.

---

## 9. Narration

### 9.1 New Bond Types in Narrator Context

M50a spec says new bond types (Kin, Friend, Grudge) are invisible to narration until M50b. M50b widens the renderer.

Build `AgentContext.relationships` from `gp.agent_bonds` in the context assembly at `build_agent_context_for_moment()` (narrative.py ~line 359), replacing the `social_edges` source when `rust_owns_formation` is true. Add new bond types to `rel_type_names` mapping:

| Bond Type | Render Template |
|-----------|----------------|
| Kin (5) | "{name} is kin to {target_name} (sentiment: {descriptor})" |
| Friend (6) | "{name} and {target_name} are friends since turn {formed_turn} (sentiment: {descriptor})" |
| Grudge (7) | "{name} holds a grudge against {target_name} (sentiment: {descriptor})" |

Sentiment descriptors: "deep" (|sentiment| > 80), "strong" (|sentiment| > 40), "mild" (|sentiment| > 0), "fading" (sentiment == 0 for positive types).

### 9.2 Unnamed Target Filtering

Only narrate bonds whose `target_id` resolves to a named character in the `name_map`. Bonds to unnamed agents are real in the simulation but invisible to the narrator.

**Filter tightening required:** The current M40 filter (narrative.py:366-370) skips edges where *neither* endpoint name is in `char_names`. This was safe because `social_edges` were already named-character-only. With `gp.agent_bonds` as the source, a named character bonded to an unnamed agent (most bonds — M50b forms bonds for all 50K agents) would render with a blank counterpart name. M50b must tighten the filter: skip any bond where `name_map.get(target_id)` returns `None`. Only named-to-named bonds enter the narration context.

### 9.3 Dissolved-Edge Narration Feed

Gating off `form_and_sync_relationships()` (Section 6.3) removes the only current producer of `world.dissolved_edges_by_turn`, which feeds narration context at `narrative.py:364` (`all_edges = social_edges + dissolved_edges`). M50b's Rust-side dissolution (Section 4) does not produce an equivalent event stream.

**M50b fix:** The death cleanup sweep (Section 4.1) and belief-divergence cleanup (Section 4.2) emit dissolution events into `AgentEvent` list (same pattern as existing death/rebellion/migration events in `tick.rs`). New event type: `event_type = 6` (dissolution), with `agent_id` = source agent, `target_region` repurposed as `bond_type`. Python-side `agent_bridge.py` collects these events and populates `world.dissolved_edges_by_turn` for narration.

This restores the dissolved-edge narration feed from Rust-side dissolution, replacing the Python-side feed that was gated off.

### 9.4 Legacy Path

In `--agents=off` mode, no relationship formation or narration occurs (see Section 6.3 note). The `read_social_edges()` rendering path is only reachable when `agent_bridge is not None` and `rust_owns_formation` is `False` (regression testing mode).

### 9.5 Sentiment in Narration

M40 edges had no sentiment. M50b relationships do. The narrator context gains sentiment descriptors that add emotional texture: "his bitter rival" vs "his grudging rival," "a deep bond of exile" vs "a fading bond from shared displacement," "kin, though the bond has grown cold."

These are prompt-level hints — the LLM decides salience. No new mechanical effects.

---

## 10. Scope Boundaries

### 10.1 In Scope

- Rust-native formation engine with staggered deterministic full scan
- 6 bond-type formation rules (Friend, CoReligionist, Rival, Mentor, Grudge, ExileBond)
- Weighted cross-rank cultural similarity gate
- `agents_share_memory_with_valence()` helper
- Triadic closure as pair-local modifier
- Per-agent and per-region formation budgeting
- Deterministic hash-based scan-order rotation
- Death cleanup sweep (every tick)
- Belief-divergence cleanup (on formation cadence)
- Social-need blend path (`alpha = 0.0` default)
- Gate off `form_and_sync_relationships()` in agent modes
- `rust_owns_formation` flag on `AgentBridge`
- `get_all_relationships()` bulk Arrow export (required)
- Per-tick formation/dissolution counters + distribution snapshots
- `get_relationship_stats()` FFI method
- Analytics extractor for relationship metrics
- Narration widening for Kin, Friend, Grudge bond types
- Dissolved-edge event emission from Rust dissolution (replaces Python-side feed)
- Tightened unnamed-target filter for `gp.agent_bonds` narration source
- Sentiment descriptors in narrator context
- Dormant `synthesis_budget` field reservation (1 byte/agent, internal-only)

### 10.2 Not In Scope

- Synthesis-budget activation (M53+)
- Probabilistic Axelrod-style formation (M53+)
- Social-need alpha ramp above 0.0 (M53)
- Cohort detection / label propagation (M53b)
- Incoming-Mentor credit scan for social need (M53)
- Diaspora tracking (Phase 8-9 horizon)
- Sibling inference (kin = direct parent-child only, from M50a)
- Marriage bond formation (M57)
- `replace_social_edges()` shim removal (post-M50b cleanup)
- `SocialGraph` struct deletion (post-M50b cleanup)
- `relationships.py` formation function removal (post-M50b cleanup)
- Spatial-hash proximity gating (M55)
- Agent-level diplomacy

---

## 11. Testing Strategy

### 11.1 Rust Unit Tests (formation)

- **Similarity gate:** weighted cross-rank culture overlap produces correct scores for identical, partially overlapping, and fully distinct cultural values. Best-match deduplication prevents double-counting.
- **Per-type gates:** each bond type's eligibility predicate tested with passing and failing inputs. Friend requires shared memory + threshold. CoReligionist requires belief match + minority context. Rival requires same occupation + wealth proximity + ambition gate. Mentor requires age gap + directionality (both orientations tested). Grudge requires negative-valence shared memory. ExileBond requires away-from-origin-region + foreign-rule conditions.
- **Triadic closure:** pair with shared positive contact gets threshold relaxation. Rival/Grudge contacts excluded. Cap at one bonus — multiple shared contacts don't stack.
- **Formation budgeting:** per-agent cap stops bond creation after limit. Per-region cap stops scan after limit.
- **Early rejection cascade:** ordering verified — existing bond check before capacity check before budget check before type gate before expensive checks.
- **Scan rotation:** hash-based shuffle produces different agent ordering for different `(turn, region)` inputs. Same `(turn, region, seed)` → same ordering.

### 11.2 Rust Unit Tests (dissolution)

- **Death cleanup:** bond to dead target removed. Swap-remove produces packed prefix. `while i < rel_count` pattern — swapped-in entry re-checked.
- **Belief-divergence:** CoReligionist bond removed when beliefs differ. Non-CoReligionist bonds unaffected by belief change.
- **Mentor historical:** Mentor bond survives occupation change.

### 11.3 Rust Integration Tests

- **Multi-turn formation:** run N ticks with agents sharing memory + culture → friend bonds form on cadence ticks, not between them.
- **Staggered scheduling:** region in bucket 0 gets scanned on tick 0, N, 2N. Region in bucket 1 gets scanned on tick 1, N+1, 2N+1.
- **Formation + drift interaction:** new friend bond formed → co-located → sentiment increases over subsequent ticks via M50a drift.
- **Death cleanup + formation interaction:** agent dies → bonds cleaned → next formation scan doesn't pair with dead agent.
- **Dissolution + formation cycle:** CoReligionist formed → agent converts → belief-divergence cleanup removes bond → if agent reconverts, eligible for new CoReligionist on next cadence.
- **Slot exhaustion with eviction:** 8 bonds formed → 9th candidate triggers eviction of weakest non-protected → new bond occupies evicted slot.

### 11.4 FFI Tests

- `get_all_relationships()` bulk export: returns correct Arrow schema, correct row count, data matches store state.
- `get_relationship_stats()` returns counters and distribution snapshots matching manual calculation.
- Formation counters increment correctly across a multi-tick run.

### 11.5 Python Integration Tests

- `rust_owns_formation` gate: when True, `form_and_sync_relationships()` is not called. When False, legacy path runs.
- `GreatPerson.agent_bonds` sync: populated from `get_agent_relationships()`, includes M50b-formed bonds (Friend, Grudge, etc.), not just kin.
- Social-need blend at `alpha = 0.0`: behavior identical to pre-M50b proxy.
- Narration context includes new bond types for named characters. Unnamed targets filtered out.
- Analytics extractor produces expected metrics structure.
- Determinism: same seed → identical relationship store after N turns.

### 11.6 Transient Signal Test

Formation scan state (per-agent bond counters, per-region counters) is temporary per-scan — verify no state leaks between cadence ticks. 2-turn test per CLAUDE.md rule.

---

## 12. Constants

All constants `[CALIBRATE]` for M53.

| Constant | Domain | Initial | Notes |
|----------|--------|---------|-------|
| `FORMATION_CADENCE` | Scheduling | 6 | Ticks between formation scans per bucket |
| `W_CULTURE` | Similarity | 0.35 | Weight for cultural similarity |
| `W_BELIEF` | Similarity | 0.35 | Weight for belief match |
| `W_OCCUPATION` | Similarity | 0.15 | Weight for occupation match |
| `W_AFFINITY` | Similarity | 0.15 | Weight for civ affinity match |
| `SAME_RANK_WEIGHT` | Culture | 1.0 | Same-rank cultural value match weight |
| `CROSS_RANK_WEIGHT` | Culture | 0.5 | Cross-rank cultural value match weight |
| `FRIEND_THRESHOLD` | Friend | 0.50 | Min compatibility score for friend formation |
| `FRIEND_INITIAL_SENTIMENT` | Friend | +30 | Starting sentiment |
| `MINORITY_THRESHOLD` | CoReligionist | 0.40 | Belief fraction below which minority context applies |
| `CORELIGIONIST_INITIAL_SENTIMENT` | CoReligionist | +25 | Starting sentiment |
| `RIVAL_WEALTH_PROXIMITY` | Rival | 50.0 | Max absolute wealth gap |
| `RIVAL_SIMILARITY_FLOOR` | Rival | 0.30 | Min compatibility score for rivals |
| `RIVAL_MIN_AMBITION` | Rival | 0.50 | Min ambition trait for personality gate |
| `RIVAL_INITIAL_SENTIMENT` | Rival | -20 | Starting sentiment |
| `MENTOR_AGE_GAP` | Mentor | 15 | Min age difference (directional) |
| `MENTOR_INITIAL_SENTIMENT` | Mentor | +35 | Starting sentiment |
| `GRUDGE_INITIAL_SENTIMENT` | Grudge | -30 | Starting sentiment |
| `EXILE_INITIAL_SENTIMENT` | ExileBond | +35 | Starting sentiment |
| `TRIADIC_MIN_SENTIMENT` | Triadic | +40 | Min sentiment for shared contact to count |
| `TRIADIC_THRESHOLD_REDUCTION` | Triadic | 0.15 | Friend threshold reduction from closure |
| `MAX_NEW_BONDS_PER_PASS` | Budgeting | 2 | Per-agent cap per formation scan |
| `MAX_NEW_BONDS_PER_REGION` | Budgeting | 50 | Per-region cap per formation scan |
| `SOCIAL_BLEND_ALPHA` | Needs | 0.0 | Blend weight (0 = proxy only, 1 = bonds only) |
| `SOCIAL_RESTORE_BOND` | Needs | 0.010 | Base restoration rate from bonds |
| `SOCIAL_BOND_TARGET` | Needs | 4.0 | Positive bonds for full social restoration |
| `SYNTHESIS_BUDGET_MAX` | Deferred | 100 | Dormant field initial value |

27 constants. Plus 8 from M50a = 35 total M50 constants for M53 calibration.

---

## 13. M53 Calibration Guidance

Items flagged during M50b design for M53's attention:

- **Social-need alpha ramp:** Start at 0.0, increase experimentally. Watch for regression in per-agent diversity (occupation/age effects disappearing). If bond-only restoration is too uniform, re-introduce occupation weighting as a multiplier on `bond_factor`.
- **Incoming-Mentor credit:** If enabling, precompute incoming mentor counts once per tick — not per-agent full-pool scan. Decide whether `positive_bond_count` means raw slots or unique counterpart IDs.
- **Synthesis-budget:** Evaluate whether fixed cadence overcomputes in peacetime or underreacts during crises. If so, wire synthesis-budget as a formation-eligibility flag.
- **Probabilistic formation:** If deterministic gates produce blocky/brittle graphs, introduce Axelrod `P = similarity^D` per-bond-type.
- **Persecution triple-stacking (from M49):** M38b + M48 + M49 Autonomy all push rebel/migrate. M50b's Grudge formation adds another channel. Monitor total rebel modifier budget.
- **ExileBond looseness:** If too many agents qualify (anyone who migrated), tighten with `civ_affinities[a] == civ_affinities[b]` filter.
- **Rival wealth proximity:** May need percentile-based measure if absolute gaps don't scale with simulation economy.
- **Conversion → CoReligionist cascade coupling:** Formation scan sees post-conversion state (phase 8 after conversion at phase 6). An agent who converts this tick is immediately CoReligionist-eligible. Cadence-gating limits the coupling, but monitor CoReligionist bond formation rate in regions undergoing active conversion to verify no conversion-lock feedback loop.
- **Grudge-bonded rebellion coordination:** Grudge bonds between co-persecuted agents of the same original civ may create coordinated rebellion cohorts without explicit group mechanics. Measure rebellion correlation among Grudge-bonded agent pairs — if Grudge bonds amplify rebel modifier stacking beyond the already-flagged persecution triple-stacking, the Grudge initial sentiment or formation gate may need tightening.
- **Grudge persistence after civ_affinity change:** Grudge formation requires different `civ_affinity`, but there is no dissolution rule for Grudge bonds when affinities converge post-formation. This is intentional — personal grudges persist after political realignment. Drift handles natural decay.
