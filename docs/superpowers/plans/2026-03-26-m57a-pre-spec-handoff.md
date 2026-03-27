# M57a Pre-Spec Handoff

> Date: 2026-03-26  
> Audience: spec-writing / question-gathering agent  
> Purpose: lock an implementation-ready spec for `M57a: Marriage Matching & Lineage Schema`, and surface the smallest set of user decisions that actually matter before spec freeze.

## Status Snapshot

- There is no dedicated `M57a` spec or implementation plan in the repo yet.
- Canonical roadmap: `M57a` is a Phase 7 scale-track milestone, estimate `2.5-3.5` days, depending on `M50` and `M55a`.
- The live baseline is already beyond the older Phase 7 draft assumptions:
  - `M50a`, `M50b`, `M51`, `M55a`, `M55b`, `M56a`, and `M56b` are all landed or verified in the current repo state.
- `M57a` is explicitly the substrate half only:
  - marriage matching
  - two-parent lineage schema migration
  - compatibility with dynasty/succession logic
- `M57b` still owns:
  - pooled household wealth
  - inheritance behavior
  - joint migration
  - widowhood / child custody

## Canonical Requirements (Roadmap)

Source: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

- Goal: add proximity-based marriage formation and migrate lineage from single-parent to two-parent tracking.
- Matching: eligible nearby agents form marriage bonds from compatibility + opportunity, not global optimization.
- Schema migration: current single-parent lineage becomes a two-parent structure with `PARENT_NONE` sentinels for missing parents.
- Scope guard: do not absorb household economics or widowhood into this milestone.
- Gate: marriage bonds form correctly, births + lineage resolution still work, and dynasty/succession logic does not destabilize.

Additional roadmap context that matters:
- `M51` already assumes children can inherit legacy memories from both parents once the marriage/lineage system exists (`M57a+`).
- Phase 7 roadmap finalization already resolved that the two-parent migration belongs inside M57, not as a separate prerequisite.

## Current Code Reality (Live Baseline)

### Formation / relationship ownership

- In live agent-backed runs, Rust owns relationship formation:
  - `src/chronicler/agent_bridge.py`: `rust_owns_formation = True`
  - `src/chronicler/simulation.py`: Python relationship formation is gated off when Rust owns formation
- Rust relationship substrate already reserves the marriage slot:
  - `chronicler-agents/src/relationships.rs`: `BondType::Marriage = 2`
- `narrative.py` already knows how to render bond type `2` as `"marriage"`.

### Spatial substrate already exists

- Agents already have per-region spatial coordinates:
  - `chronicler-agents/src/pool.rs`: `x`, `y`
  - `chronicler-agents/src/ffi.rs`: snapshot exports `x`, `y`
- Rust already has a region-local deterministic pair scan:
  - `chronicler-agents/src/formation.rs`: `formation_scan()`
- M56b also added `settlement_id`, but the roadmap only requires M55a-level spatial proximity for M57a.

### Lineage is still single-parent everywhere that matters

- Rust storage is plural-in-name but singular-in-semantics:
  - `chronicler-agents/src/pool.rs`: `parent_ids: Vec<u32>`
- FFI exports singular parent fields:
  - `chronicler-agents/src/ffi.rs`: snapshot and promotions batch both export `parent_id`
- Python models are singular:
  - `src/chronicler/models.py`: `GreatPerson.parent_id`
- Python dynasty logic is singular:
  - `src/chronicler/dynasties.py`: `check_promotion()` only reads `child.parent_id`
  - `compute_dynasty_legitimacy()` only checks candidate `parent_id`
- Python succession candidate building is singular:
  - `src/chronicler/factions.py`: GP successor candidates include only `parent_id`

### Birth / memory / kin logic is also single-parent today

- Rust birth path carries one parent:
  - `chronicler-agents/src/tick.rs`: `BirthInfo.parent_id`
- M51 legacy memory transfer uses one reverse index:
  - `tick.rs`: `parent_id -> Vec<child_slot>`
- M50 kin formation currently bonds the child to one parent:
  - `chronicler-agents/src/relationships.rs`: `form_kin_bond(parent_slot, child_slot, turn)`

### Legacy code that should not drive the new spec

- `src/chronicler/relationships.py` still contains an old Python-side `check_marriage_formation()` for the M40 named-character social-edge path.
- That path is not authoritative in live hybrid mode and should not be treated as the preferred M57a seam unless the spec intentionally revives a fallback path.
- `src/chronicler/validate.py` contains a stale bond-type comment with ordinals that do not match the live Rust relationship enum. Use `relationships.rs` as the source of truth.

## Non-Negotiables To Preserve

- Determinism:
  - stable ordering
  - explicit tie-breaks
  - no `HashMap` iteration order assumptions
- If M57a introduces RNG for matching, reserve a unique stream offset in `chronicler-agents/src/agent.rs` and extend the collision test.
- `BondType` ordinals must stay stable across Rust, Python, and narration:
  - `Marriage` must remain `2`
- `--agents=off` semantics must remain valid.
  - Recommended M57a behavior in off mode: no marriage formation, no synthetic fallback beyond the existing aggregate baseline.
- New transient Python->Rust signals still follow the repo rule:
  - clear before return from the builder
  - add a multi-turn reset test
- M57a must preserve its scope guard.
  - no pooled wealth
  - no joint migration
  - no widowhood logic
  - no divorce / polygamy / full household tree modeling

## Recommended Architecture Lean

### 1. Keep marriage formation Rust-native

- Best seam: extend the existing Rust relationship pipeline, not the old Python social-edge path.
- Why:
  - formation is already Rust-owned
  - the marriage bond enum slot already exists
  - M55a already provides spatial locality
  - M57a is a scale milestone, not a named-character-only flavor layer

### 2. Keep matching local and deterministic

- Prefer same-region matching with spatial opportunity from `x/y`.
- Use deterministic pair evaluation, not global optimization.
- Treat same-settlement / urban context as optional follow-on weighting, not a default dependency.

### 3. Treat the lineage migration as whole-stack

- This is not just a pool-field change.
- The spec needs one coherent migration across:
  - Rust pool storage
  - birth path
  - snapshot / promotions FFI
  - Python `GreatPerson`
  - dynasty detection
  - succession legitimacy
  - M51 legacy-memory inheritance
  - M50 kin-bond birth wiring

### 4. Keep dynasty membership single-valued unless you intentionally widen the model

- Current downstream systems expect one `dynasty_id`.
- Widening to dual-house membership is a larger semantic change than M57a strictly needs.
- Safest default: two-parent lineage, one deterministic dynasty assignment.

## Scope Recommendation

In-scope for M57a:
- Marriage bond formation at full-agent scale.
- Marriage exclusivity / lifecycle basics needed to make the bond meaningful.
- Two-parent lineage schema migration.
- Minimal updates to dynasties, succession legitimacy, kin bonds, and legacy-memory inheritance so the system remains coherent.
- Minimal narration / analytics / snapshot visibility required for validation.

Out-of-scope for M57a:
- Household pooled income / wealth.
- Inheritance of money or artifacts.
- Joint migration.
- Widowhood policy beyond bond removal by death.
- Divorce / remarriage drama systems beyond the minimum rule needed for coherence.
- Settlement- or market-driven marriage economics.

## Likely File Touch Map

Python:
- `src/chronicler/models.py`
- `src/chronicler/agent_bridge.py`
- `src/chronicler/dynasties.py`
- `src/chronicler/factions.py`
- `src/chronicler/leaders.py`
- `src/chronicler/narrative.py`
- `src/chronicler/relationships.py` if legacy fallback is kept or explicitly retired
- `src/chronicler/main.py` / bundle surfaces if snapshot contracts change

Rust:
- `chronicler-agents/src/agent.rs`
- `chronicler-agents/src/pool.rs`
- `chronicler-agents/src/tick.rs`
- `chronicler-agents/src/ffi.rs`
- `chronicler-agents/src/relationships.rs`
- `chronicler-agents/src/formation.rs`
- `chronicler-agents/src/named_characters.rs`

Tests:
- `tests/test_agent_bridge.py`
- `tests/test_dynasties.py`
- succession / leader tests touching legitimacy or regnal metadata
- snapshot / bundle tests if schemas change
- Rust relationship / tick / memory tests
- a dedicated M57a Rust integration test file would be reasonable

## Design Decisions Agent Should Lock In The Spec

1. Whether marriage is implemented as a new `formation.rs` gate or a separate marriage pass.
2. The opportunity rule:
   - same region only
   - spatial radius
   - same-settlement boost or no settlement dependency
3. Marriage exclusivity:
   - single spouse only
   - remarriage after death yes/no
   - hostile / cross-civ / cross-faith eligibility
4. The concrete two-parent storage shape:
   - `Vec<[u32; 2]>`
   - two parallel arrays
   - Arrow exposure shape
5. Parent slot semantics:
   - ordered vs unordered
   - whether slot 0 stays the current birth parent
6. Birth attribution:
   - keep the current fertility pipeline and annotate second parent
   - or change parent selection / fertility mechanics now
7. Dynasty resolution when parents have different dynasties.
8. Succession legitimacy rule:
   - current ruler counts as either parent
   - or only the primary / slot-0 parent
9. Whether M51 legacy-memory transfer becomes dual-parent immediately.
10. Whether kin bonding at birth now links the child to both parents.
11. Whether `Marriage` becomes a protected relationship type alongside `Kin`.
12. Whether the legacy Python marriage code is deleted, frozen, or kept as a test-only / compatibility surface.

## High-Value Questions To Bring Back

These are the user decisions most worth asking explicitly. Recommended defaults are included so the spec can keep moving if answers are sparse.

1. Should `dynasty_id` stay single-valued per child in M57a, or do you want dual-house lineage semantics immediately?
   Recommended: keep `dynasty_id` single-valued in M57a and choose one parent deterministically.

2. For succession legitimacy, should the current ruler count as the direct-heir parent if they are either parent, or only the primary / slot-0 parent?
   Recommended: either parent.

3. Should M57a keep the existing fertility / birth pipeline and simply attach a second parent when the birth parent has a spouse, or should marriage already change fertility / parent selection rules?
   Recommended: keep the current fertility pipeline and annotate second parent.

4. Should cross-civ marriages be allowed in M57a when agents are co-located and not hostile, or should marriage stay same-civ only for the first cut?
   Recommended: allow cross-civ marriages only when co-located and non-hostile, with same-civ still easier.

5. Should `Marriage` be eviction-protected like `Kin` in the 8-slot relationship store?
   Recommended: yes.

6. Should M57a immediately extend M51 legacy-memory inheritance and kin-bond creation to both parents, or leave those single-parent until M57b?
   Recommended: extend both-parent lineage effects now, because the roadmap already frames that as `M57a+`.

7. Do you want settlement / urban context to matter for matching in M57a, or should the first cut stay purely on M55a spatial proximity?
   Recommended: pure M55a spatial proximity for M57a.

## Validation Expectations

- Unit tests:
  - deterministic marriage matching
  - exclusivity / no duplicate spouse
  - protected-slot behavior if marriage becomes protected
  - two-parent schema round-trip through FFI
- Integration tests:
  - births preserve two-parent lineage
  - dynasty detection still works after the migration
  - succession legitimacy recognizes the intended parent rule
  - legacy-memory transfer and kin bonds behave correctly under two-parent lineage if included
- Determinism tests:
  - same seed, same marriages, same parent pairs, same dynasty outcomes
- Off-mode tests:
  - `--agents=off` still behaves as a no-op for marriage formation

## Expected Output From The Next Agent

- A single M57a pre-implementation spec that:
  - uses the live Rust-owned formation baseline
  - defines the two-parent migration end-to-end
  - resolves dynasty / succession / legacy-memory compatibility
  - states exactly what is deferred to M57b
- A short user-facing question set based on the 7 questions above, with recommended defaults and rationale.
