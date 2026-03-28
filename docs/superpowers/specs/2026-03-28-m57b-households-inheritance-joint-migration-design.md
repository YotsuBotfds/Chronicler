# M57b: Households, Inheritance & Joint Migration — Design Spec

> Date: 2026-03-28
> Status: Approved
> Depends on: M57a (Marriage Matching & Lineage Schema) — implemented on `m57a-marriage-lineage`
> Baseline: Same-machine `main` controls (`satisfaction_mean=0.4171`); M57b candidate compared via `ACCEPT_M57_BASELINE_EXCEPTION` policy

---

## Goal

Build household-level mechanics on top of M57a's marriage bond and two-parent lineage substrate. Married pairs pool wealth for behavior decisions, children inherit from parents on death, and families migrate together as a unit.

**Value:** Economic and lineage coherence. Households become the unit of material life — not relationship drama.

---

## Semantic Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Household entity | **Derived** | No `household_id`; household = married pair + dependent children, inferred from marriage bonds + parent links. Canonical derivation helper enables future promotion to first-class entity. |
| 2 | Pooled wealth | **Hybrid** | Per-agent `wealth` remains canonical storage. Derived `household_effective_wealth` drives behavior (migration). Explicit transfer ops on death/inheritance. Existing Gini/percentile pipelines unchanged. |
| 3 | Inheritance order | **Spouse-first** | Surviving spouse inherits full estate. Children inherit only when both parents are dead. Aging out of dependence does not trigger a payout. |
| 4 | Joint migration | **Lead-follow with catastrophe gate** | Household migrates together by default. If destination is catastrophic (war + severe food stress), migration is cancelled for the entire household — no split. |
| 5 | Dependent child | **`age < AGE_ADULT`** | Uses existing adulthood boundary. No second threshold. |
| 6 | Cross-civ identity | **No affinity mutation** | Marriage/household logic must not write `civ_affinity`. Joint migration may relocate cross-civ households, but identity remains per-agent. Any affinity change remains exclusively in existing drift/assimilation pathways. |
| 7 | Fertility | **No modifier** | Demographics unchanged. Births-by-marital-status diagnostics collected only. Marriage fertility modifier constants remain neutral. Any non-neutral fertility effect deferred to a dedicated follow-on milestone. |
| 8 | Remarriage cooldown | **Immediate re-eligibility** | After death transfer/custody resolution, normal marriage scan eligibility applies. No widowhood timer. |

### Cross-civ affinity spec rules (Decision 6)

1. Household/marriage logic **must not write** `civ_affinity`.
2. Joint migration may relocate cross-civ households, but identity remains per-agent.
3. Any affinity change remains exclusively in existing drift/assimilation pathways.
4. Tests must prove cross-civ marriage + migration does not change affinity unless a non-household system does.

---

## Architecture

**Approach:** Inline integration with function-boundary separation. Household behavior is inserted into existing tick phases at specific points. A new `household.rs` helper module provides pure functions — no lifecycle, no entity state.

**Execution invariants:**
1. Death transfer runs **before** marriage bond removal (otherwise spouse lookup is lossy).
2. Household-effective wealth is derived **post-transfer, pre-decision** (widowhood effects are coherent immediately).
3. Migration consolidation runs **before** move commit; catastrophe gate cancels for the whole household (no split).

---

## Section 1: Household Helper Module (`household.rs`)

New Rust module `chronicler-agents/src/household.rs` with pure helper functions.

### `household_effective_wealth(pool, slot, id_to_slot) -> f32`

Lightweight wealth combiner. Uses existing `get_spouse_id(pool, slot)` from `relationships.rs` to find spouse, resolves spouse slot via `id_to_slot` (passed as param — no linear `find_slot_by_id` fallback in hot paths). Sums both agents' `pool.wealth[slot]`. Returns personal wealth if unmarried. O(1) given the id-to-slot map.

### `resolve_dependents(pool, slot, spouse_slot, dependent_index) -> Vec<usize>`

Returns sorted-by-slot list of dependent children for a household. The `dependent_index` is a tick-local `HashMap<u32, Vec<usize>>` built once (reusing the existing `parent_to_children` pattern from `tick.rs:464`), filtered to agents under `AGE_ADULT`. The function looks up both spouses' agent IDs in this index, deduplicates, and excludes married children (marriage precedence — see Section 3). Deterministic: output sorted ascending by slot index.

### Wealth percentile semantics: stay personal

Percentile ranking in `wealth_tick()` Step 2 continues to rank agents by *personal* wealth. Gini (computed Python-side) also stays personal. The class tension formula `gini * (1 - percentile) * CLASS_TENSION_WEIGHT` remains unchanged.

**Design rationale:** Pooled wealth does not soften class tension while both spouses are alive. A poor spouse married to a rich spouse still feels class tension from their personal position in the civ's wealth distribution. This is intentional — household pooling affects *behavior* (migration decisions), not *perception* (satisfaction/class tension). Satisfaction, needs, and percentiles all remain individual-level.

Household-effective wealth affects behavior only:
- **Migration scoring:** `best_migration_target_for_agent` uses household-effective wealth to modulate migration utility/gating for married agents. Does not rewrite destination ranking — modulates the *decision threshold*.
- **Satisfaction:** No change. Personal percentiles.
- **Needs update:** No change. Individual-level.

### Python parity

Matching `household_effective_wealth()` in `agent_bridge.py` for diagnostics/analytics only. Not authoritative — Rust is canonical for simulation.

---

## Section 2: Death Transfer & Inheritance

### Insertion point

Inside the sequential death-apply loop (`tick.rs:503-557`), **before** DeathOfKin memory intents and legacy memory transfer, and before `pool.kill(slot)`. Inheritance transfer is the first operation on each dying agent — it needs live wealth and intact marriage bonds, and must complete before any other death-related processing.

**Canonical ordering per dying agent:**
1. `household_death_transfer` (reads wealth, finds spouse via bond, transfers)
2. DeathOfKin memory intents (existing)
3. Legacy memory transfer (existing)
4. `pool.kill(slot)`

### Precompute `full_dead_ids`

Collect all death slots from `demo_results` into a `HashSet<u32>` **before** entering the apply loop. This set is reused for both inheritance heir eligibility and later `death_cleanup_sweep()`. Single precomputation, no order-dependent accumulation.

### `household_death_transfer(pool, dying_slot, full_dead_ids, id_to_slot, parent_to_children) -> Vec<InheritanceEvent>`

Called per dying agent, in death-apply order (deterministic — `demo_results` is region-ordered, deaths within each region are slot-ordered).

**If surviving spouse exists AND not in `full_dead_ids`:**
- Transfer: `pool.wealth[spouse_slot] += pool.wealth[dying_slot]`, clamp to `MAX_WEALTH`
- Record clamped overflow as `inheritance_wealth_lost` stat
- Emit spouse `DeathOfKin` memory intent (existing `MemoryEventType::DeathOfKin`, no new type) — appended to the same `memory_intents` vec used by existing death-of-kin intents
- Return `InheritanceEvent { heir: spouse_slot, deceased_id, amount, overflow, transfer_type: SpouseInherit }`

**If no surviving spouse (unmarried, or spouse also in `full_dead_ids`):**
- First pass: dependent children (`age < AGE_ADULT`)
- Second pass if empty: all living children (adult included) — avoids burning estates when only children are adults
- Split equally: each heir gets `wealth / n`, clamped to `MAX_WEALTH`
- Return `InheritanceEvent` per child with `transfer_type: OrphanSplit` or `AdultChildSplit`

**If no heirs at all:** Wealth is lost on `pool.kill()`. Return empty vec.

### Heir eligibility — triple check

All heirs must satisfy:
1. `pool.is_alive(heir_slot)` — alive
2. `!full_dead_ids.contains(&heir_id)` — not dying this tick
3. `pool.ids[heir_slot] == heir_id` — stale-map defense

### Double-death handling

If both spouses are in `full_dead_ids`, neither qualifies as surviving spouse regardless of processing order. Both estates go directly to child split. Deterministic — uses full dead set, not accumulated-so-far.

### Custody

When one parent dies and a spouse survives, no custody *transfer* is needed. The surviving parent is already a parent (`parent_id_0`/`parent_id_1`). The household derivation helper picks up the surviving parent as household head on the next tick.

When both parents die, orphaned children (under `AGE_ADULT`) become independent immediately. No foster/adoption system. They keep their current region, occupation, and inherited wealth.

### Ordering guarantee (invariant #1)

`household_death_transfer()` runs BEFORE `death_cleanup_sweep()`. After transfer completes, `death_cleanup_sweep` removes the marriage bond normally. Wealth has already moved.

### Remarriage eligibility (Decision 8)

Remarriage eligibility begins only after death transfer/custody resolution is complete. No special widowhood timer. Normal `marriage_scan` cadence applies.

---

## Section 3: Joint Migration

### Insertion point

Between decision collection (`tick.rs:174`) and decision apply (`tick.rs:179`). After all `PendingDecisions` are collected from rayon, before any moves are committed.

### `consolidate_household_migrations(pool, pending_decisions: &mut [PendingDecisions], regions, contested_regions, id_to_slot)`

Mutates in place. Only touches `migrations`, `rebellions`, and `occupation_switches` vectors. **Never touches `loyalty_flips` or `loyalty_drifts`** — these are background operations that coexist with any primary action.

### Primary-action conflict policy

The current model enforces exactly one primary action per agent per tick via Gumbel argmax (`rebel | migrate | switch | stay`). Household follow must respect this invariant.

**Spouse conflict rule:**
- Trailing spouse chose **rebellion** → CANCEL lead's migration. Household stays. Rebellion stands.
- Trailing spouse chose **migrate** (different destination) → Replace with lead's destination. Primary action stays "migrate."
- Trailing spouse chose **switch** or **stay** → Replace primary action with "migrate" to lead's destination. Occupation switch discarded.

**Dependent conflict rule:**
- Dependents (`age < AGE_ADULT`, not married) **always follow the household**. Their independent primary action is replaced with follow-migration. Household coherence overrides individual agency below adulthood.

**Loyalty drift asymmetry:** When a dependent's rebellion is overridden to follow-migration, no drift gap is created. Rebels already skip loyalty drift (`behavior.rs:556`, `chosen != 0` guard). The overridden dependent had no drift computed regardless. Acceptable for M57b; explicitly stated.

### Algorithm

1. **Per-bucket processing** (one `PendingDecisions` per region): For each migration `(slot, from, to)`, find spouse via `get_spouse_id` + `id_to_slot`. Skip if unmarried or not co-located (`pool.regions[spouse_slot] != from`).

2. **Canonicalize pairs** via `(min(lead_slot, spouse_slot), max(...))` into a `HashSet`. Prevents double-processing when both spouses independently migrate.

3. **Sort proposals by canonical pair key** for deterministic processing.

4. **Pre-apply recheck:** Before each proposal, verify lead still has a migration entry in current bucket (defensive against multi-proposal edits).

5. **Determine lead:** Single migrating spouse leads. If both migrate, lower slot index leads. (Acknowledged as structurally biased — frozen for M57b.)

6. **Evaluate proposal:**
   - Check `bucket.rebellions` for trailing spouse → CANCEL
   - Catastrophe gate: `is_catastrophic = to < regions.len() && to < contested_regions.len() && contested_regions[to] && regions[to].food_sufficiency < CATASTROPHE_FOOD_THRESHOLD` → CANCEL

7. **CANCEL:** Remove lead from `bucket.migrations`. Remove trailing spouse from `bucket.migrations` (if present). Find dependents (using shared dependent-filter helper) and remove from `bucket.migrations`. Household stays in place, no member migrates.

8. **APPROVED:** Add trailing spouse to `bucket.migrations` with `(spouse_slot, from, to)`. Remove trailing spouse from `bucket.rebellions` / `bucket.occupation_switches`. Find dependents (same shared filter) and add to `bucket.migrations`, remove from `bucket.rebellions` / `bucket.occupation_switches`.

9. **Deduplicate** `bucket.migrations` by slot within each bucket after all proposals processed.

### Dependent filter (shared helper for APPROVED and CANCEL)

Used identically in both branches to prevent drift:
- Alive
- `age < AGE_ADULT`
- Co-located: `pool.regions[child_slot] == from`
- Parent match: `parent_id_0` or `parent_id_1` matches either spouse's agent ID
- **Not married:** `get_spouse_id(pool, child_slot).is_none()` — marriage creates independent household (resolves 16-19 age conflict with `MARRIAGE_MIN_AGE = 16`)

### Post-consolidation invariant

After consolidation, each slot appears in at most one of `migrations` / `rebellions` / `occupation_switches`. This is the highest-risk correctness seam — dedicated test required.

### New constants

- `CATASTROPHE_FOOD_THRESHOLD: f32` — `[CALIBRATE M47]`

### Acknowledged trade-off

Lower-slot lead bias is frozen for M57b. Future milestones can swap the tiebreaker (e.g., household-effective wealth, personality trait) without changing the consolidation architecture.

---

## Section 4: Diagnostics & Observability

### Tick-level stats (Rust)

Household counters are collected during tick execution and returned via a new `get_household_stats()` PyO3 method on `AgentSimulator` (same pattern as `get_relationship_stats()`). Returns `HashMap<String, f64>`.

Counters reset to zero at tick start (Rust side). `AgentSimulator` stores last-tick snapshot. Python appends to history list per-tick.

| Stat | Description |
|------|-------------|
| `inheritance_transfers_spouse` | Spouse-first wealth transfers |
| `inheritance_transfers_child` | Child-split transfers (orphan or adult) |
| `inheritance_wealth_lost` | Total wealth lost to `MAX_WEALTH` clamp |
| `household_migrations_follow` | Trailing spouses + dependents added by consolidation |
| `household_migrations_cancelled_rebellion` | Lead migrations cancelled by spouse rebellion |
| `household_migrations_cancelled_catastrophe` | Lead migrations cancelled by catastrophe gate |
| `household_dependent_overrides` | Dependent primary actions replaced by follow |
| `births_married_parent` | Births where `BirthInfo.other_parent_id != PARENT_NONE` |
| `births_unmarried_parent` | Births where `BirthInfo.other_parent_id == PARENT_NONE` |

### `births_by_marital_status` implementation

Counted inside the sequential birth-apply loop (`tick.rs:565+`). Uses `birth.other_parent_id != PARENT_NONE` from the already-captured `BirthInfo` record. No live bond lookup — uses birth-time marriage state. Robust against future ordering changes.

### Stats collection gating

Always collect household stats in agent modes (`hybrid`, `demographics-only`, `shadow`). No new CLI flag. Lightweight u32/f32 counter increments — negligible overhead. Ensures calibration data is never missing from regression runs.

**Independence:** Household stats export must be independent of `--relationship-stats` gating. Household diagnostics are never silently omitted from regression runs.

### Per-turn stats export pipeline (Python)

Same pattern as relationship stats:
- `AgentBridge.__init__`: `self._household_stats_history: list = []`
- `AgentBridge.tick()`: calls `self._sim.get_household_stats()` after tick, appends to history (in all agent modes)
- `AgentBridge.household_stats` property exposes the history list
- Stats written into bundle metadata alongside relationship stats

### Analytics extractor

`extract_household_stats(bundles)` — consumes bundle metadata (same pattern as `extract_bond_health` at `analytics.py:1705`). Returns per-turn time series of all household counters.

### No new `household_mode` flag

`world_state.agent_mode` (`models.py:706`) already exists and is serialized in bundles. Consumers check `agent_mode == "hybrid"` to determine whether household stats are meaningful.

### What this does NOT add

- No household-level entries in events timeline
- No new curator patterns for household events
- No per-household wealth tracking in bundles (derived on demand from agent snapshots)

---

## Section 5: Validation & Regression

### Regression gates

200-seed, 500-turn, `--agents hybrid`, `--parallel 24`. Full absolute gate set from `validate.py:1986-1994`:
- `satisfaction_mean`: `0.45 <= x <= 0.65`
- `satisfaction_std`: `0.10 <= x <= 0.25`
- `migration_rate_per_agent_turn`: `0.05 <= x <= 0.15`
- `rebellion_rate_per_agent_turn`: `0.02 <= x <= 0.08`
- `gini_in_range_fraction`: `>= 0.20` of final Ginis in `[0.30, 0.70]`
- `occupation_ok`: all occupation shares in `(0.0, 0.70]`
- `civ_survival_ok`: zero-survival fraction = 0.0, full-survival fraction <= 0.20
- `treasury_ok`: negative-treasury seed count <= max(1, 30% of seeds)

### Acceptance policy: `ACCEPT_M57_BASELINE_EXCEPTION`

Adopted from `docs/superpowers/analytics/m57-adjudication-2026-03-27.md:64-83`. Resolves the policy ambiguity that blocked M57a closure. One explicit policy.

**Requirements:**
1. **Three** fresh same-machine `main` control batches (200 seeds, 500 turns, hybrid, `--parallel 24`), all reproducing the same floor miss. Control artifact paths pinned in the adjudication record. "Same floor miss" = matching oracle vector + all control-relative metric deltas within tolerance.
2. Candidate preserves the same oracle status vector as controls.
3. `occupation_ok` remains `true`.
4. `satisfaction_mean` not worse than control mean.
5. `rebellion_rate_per_agent_turn` delta within `+0.002`.
6. `migration_rate_per_agent_turn` delta within `+0.003`; improvement allowed.
7. `gini_in_range_fraction` delta within `-0.010`; improvement allowed.
8. **Probe evidence** (mandatory, not boundary-only): isolation probes must show M57b systems are not the primary source of the floor miss.

### Expected regression movement

- `migration_rate_per_agent_turn`: Joint migration reduces independent events, adds household follows. Net direction unclear.
- `gini_in_range_fraction`: Spouse-first inheritance concentrates wealth. May shift Gini upward. Intentional.
- `rebellion_rate_per_agent_turn`: Dependent overrides remove some rebellions. Small downward pressure.

### Watch metrics (not formal gates)

`treasury`, `population`, `surviving_civs` — smoke indicators for unintended coupling.

### Targeted unit tests (Rust)

**Inheritance:**
- Spouse-first transfer (single death, wealth moves to spouse)
- Double-death same tick (both estates to children)
- Orphan split (no spouse, multiple children)
- Adult-child fallback (no dependents, adult children inherit)
- No heirs (wealth lost)
- MAX_WEALTH clamp overflow tracked
- Heir eligibility triple-check (alive, not in dead set, id matches slot)

**Joint migration:**
- Lead migrates, spouse follows
- Lead migrates, spouse rebelled → cancelled
- Catastrophe gate blocks → household stays
- Dependent follows
- Dependent with independent migration → overridden
- Married dependent (age 16-19) excluded from dependents
- Both spouses migrate different destinations → lower-slot leads
- Cancel removes all household member migrations (lead, spouse, dependents)

**Primary-action invariant:**
- After consolidation, each slot in at most one of `migrations`/`rebellions`/`occupation_switches`
- Dedicated test — highest-risk correctness seam

**Household helpers:**
- Effective wealth married/unmarried/widowed
- Dependents sorted, excludes married children, excludes dead children

**Determinism:**
- Same seed → identical household stats

### Targeted unit tests (Python)

- `births_by_marital_status` matches manual count
- `extract_household_stats` round-trips through bundle metadata
- Analytics parity helper matches Rust on snapshot data

### Integration tests

- **Wealth conservation (phase-local):** Within the death-apply phase: total wealth before = total wealth after transfers + clamp overflow + wealth lost to no-heirs. Checked per death-apply pass, not across turns.
- **Household co-location:** After joint migration, spouse and dependents share lead's destination region.
- **`--agents=off` invariants:** Household helper functions never called. No new code paths execute. Smoke test: N-turn run completes without error and produces same oracle status vector as pre-M57b.

---

## Section 6: Scope Guards

**M57b does NOT add:**
- Divorce
- Polygamy
- Complex household trees
- First-class `household_id` entity
- Fertility modifier (diagnostics only)
- Remarriage cooldown
- `civ_affinity` mutation from marriage/household
- Household-level events in curator/events timeline
- Changes to satisfaction formula, wealth percentiles, or class tension
- Changes to Gini computation
- Changes to `--agents=off` behavior

---

## Execution Order Summary

All M57b insertion points in the tick:

```
0.5   wealth_tick (UNCHANGED — income, decay, percentiles stay personal)
0.75  needs update (UNCHANGED)
0.8   relationship drift (UNCHANGED)
1.    satisfaction (UNCHANGED — consumes personal percentiles)
2.    region stats (UNCHANGED)
3.    decisions: evaluate_region_decisions (CHANGED — migration utility
        uses household_effective_wealth for married agents)
3.5   NEW: consolidate_household_migrations (post-decision, pre-apply)
4.    apply decisions (UNCHANGED — consumes rewritten pending_decisions)
4.5   spatial reset (UNCHANGED)
5.    demographics:
        precompute full_dead_ids from all demo_results (MOVED EARLIER)
        sequential death-apply loop (per dying agent, in order):
          1. NEW: household_death_transfer (reads wealth, finds spouse, transfers)
          2. existing: DeathOfKin memory intents
          3. existing: legacy memory transfer
          4. pool.kill(slot)
        births: NEW count births_married/unmarried from BirthInfo.other_parent_id
5.1   death_cleanup_sweep (UNCHANGED — reuses precomputed full_dead_ids)
6+    cultural drift, conversion, memory, marriage_scan, formation_scan
        (ALL UNCHANGED)
```

### Implementation-time checks

1. `full_dead_ids` must be precomputed once and reused for both inheritance eligibility and `death_cleanup_sweep` — no order-dependent behavior.
2. Household stats must be tick-reset and exported consistently in agent modes. `--agents=off` remains invariant/smoke-only with no household path execution.

---

## Files Touched

| File | Change |
|------|--------|
| `chronicler-agents/src/household.rs` | **NEW** — helper functions |
| `chronicler-agents/src/tick.rs` | Insertion points: death transfer, migration consolidation, birth counting |
| `chronicler-agents/src/behavior.rs` | Migration utility uses `household_effective_wealth` |
| `chronicler-agents/src/ffi.rs` | `get_household_stats` PyO3 method, household stat storage |
| `chronicler-agents/src/lib.rs` | Module export |
| `chronicler-agents/src/agent.rs` | `CATASTROPHE_FOOD_THRESHOLD` constant |
| `src/chronicler/agent_bridge.py` | Household stats collection, Python parity helper |
| `src/chronicler/analytics.py` | `extract_household_stats` extractor |
| `src/chronicler/main.py` | Household stats wiring into bundle metadata |

### New constants

| Constant | Type | Location | Note |
|----------|------|----------|------|
| `CATASTROPHE_FOOD_THRESHOLD` | `f32` | `agent.rs` | `[CALIBRATE M47]` |
