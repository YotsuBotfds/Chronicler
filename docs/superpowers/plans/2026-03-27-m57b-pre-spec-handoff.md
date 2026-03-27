# M57b: Pre-Spec Handoff

> Date: 2026-03-27
> Status: Ready for spec drafting
> Depends on: M57a (implemented on `m57a-marriage-lineage`)
> Note: M57a code review passed; the one remaining milestone-closeout item is the 200-seed regression sweep

## Goal

Equip the next spec-writing agent to draft **M57b: Households, Inheritance & Joint Migration** from the live post-M57a baseline, and to ask the user the few questions that determine what household simulation should *mean* before implementation details harden.

---

## Live Baseline After M57a

These are the important post-M57a facts the next agent should treat as authoritative:

- Rust marriage formation is live in [`chronicler-agents/src/formation.rs`](../../chronicler-agents/src/formation.rs):
  - `marriage_scan()` runs before `formation_scan()`
  - one spouse max
  - marriage is eviction-protected
  - cross-civ marriages are allowed when the civs are not at war
- Two-parent lineage is live in:
  - [`chronicler-agents/src/pool.rs`](../../chronicler-agents/src/pool.rs)
  - [`chronicler-agents/src/tick.rs`](../../chronicler-agents/src/tick.rs)
  - [`chronicler-agents/src/ffi.rs`](../../chronicler-agents/src/ffi.rs)
  - [`src/chronicler/models.py`](../../src/chronicler/models.py)
- Python dynasty logic now assumes:
  - single operative `dynasty_id`
  - optional secondary `lineage_house`
  - either parent qualifies for direct-heir legitimacy
  - see [`src/chronicler/dynasties.py`](../../src/chronicler/dynasties.py)
- Kin bonds and legacy memories already widen across both parents.
- Named-character marriage formation events are live in [`src/chronicler/simulation.py`](../../src/chronicler/simulation.py) as `marriage_formed`.
- Lineage-house narrator context is live in [`src/chronicler/narrative.py`](../../src/chronicler/narrative.py).

## Key Architectural Seams for M57b

These are the parts of the codebase M57b will most likely need to touch:

- **Wealth is still purely per-agent.**
  - See `wealth_tick()` in [`chronicler-agents/src/tick.rs`](../../chronicler-agents/src/tick.rs).
  - M41/M53 analytics, Gini, and wealth-percentile satisfaction all assume personal `pool.wealth[slot]`.
- **Migration is still purely per-agent.**
  - See `evaluate_region_decisions()` and `best_migration_target_for_agent()` in [`chronicler-agents/src/behavior.rs`](../../chronicler-agents/src/behavior.rs).
  - Tick application of migrations is in [`chronicler-agents/src/tick.rs`](../../chronicler-agents/src/tick.rs).
- **Marriage exists, but there is no household entity yet.**
  - No `household_id` in the pool or Python models.
  - Household membership would currently have to be derived from marriage bonds + parent links.
- **Death cleanup removes bonds, but widowhood payload is still lossy.**
  - [`chronicler-agents/src/formation.rs`](../../chronicler-agents/src/formation.rs) `death_cleanup_sweep()` emits only survivor `agent_id` + bond type.
  - [`src/chronicler/agent_bridge.py`](../../src/chronicler/agent_bridge.py) stores dissolved Rust edges as `(agent_id, 0, rel_type, turn)`.
  - If M57b wants explicit widowhood events or spouse-aware custody transfer on the Python side, dissolution tracking likely needs widening.
- **`--agents=off` still has to remain unchanged.**
  - Household behavior must stay agent-only.

---

## Roadmap Intent

Per [`docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`](../roadmaps/chronicler-phase7-roadmap.md), M57b is supposed to add:

- household-level economic context for married pairs
- inheritance behavior
- joint migration
- widowhood semantics

And it is *not* supposed to add:

- divorce
- polygamy
- complex household trees
- relationship-drama simulation for its own sake

That means the spec should stay focused on **economic and lineage coherence**, not social melodrama.

---

## Questions the Next Agent Should Ask the User

These are the high-value semantic questions. Most technical questions can be settled during drafting, but these ones shape the meaning of the simulation.

### 1. Should households become first-class entities in M57b, or stay derived from marriage + children?

Options:

- **A) Derived households**: no new `household_id`; a household is just a married pair plus dependent children inferred from existing links.
- **B) First-class household IDs**: add explicit household identity/state now.

Recommended lean:

- **A for M57b**, unless the user already knows they want stable household entities for viewer/bundle work immediately.

Why this matters:

- A keeps M57b narrower and avoids a new identity registry.
- B is cleaner for future viewer/analytics work, but widens the milestone substantially.

### 2. How should “pooled wealth” actually work?

Options:

- **A) Effective pooling only**: keep personal `wealth`, but satisfaction / material context / migration decisions look at spouse-combined wealth.
- **B) Shared household pot**: married wealth becomes one authoritative pool.
- **C) Hybrid**: personal wealth remains stored, but household calculations and widowhood/inheritance rules explicitly move assets between spouses/children.

Recommended lean:

- **C**.

Why:

- A is the safest for M41/M53 metrics, but weak for inheritance semantics.
- B is the cleanest household model, but it destabilizes wealth analytics immediately.
- C lets M57b model real transfer rules while preserving existing per-agent wealth infrastructure.

### 3. On parent death, who gets the dead spouse’s wealth first: surviving spouse or children?

Options:

- **A) Spouse-first**: survivor inherits the estate; children inherit later if both parents are gone.
- **B) Split**: survivor keeps part, children split part immediately.
- **C) Child-first**: children inherit directly; surviving spouse keeps only personal wealth.

Recommended lean:

- **A** for the first cut.

Why:

- It best preserves household continuity.
- It is the simplest widowhood rule.
- It avoids fragmenting wealth every time one parent dies.

### 4. How strict should joint migration be?

Options:

- **A) Hard household movement**: if one spouse migrates, the spouse and dependent children move with them.
- **B) Lead-follow with guardrails**: spouse/children usually follow, but not if the destination is catastrophically bad.
- **C) Soft influence only**: marriage strongly biases migration choices, but splits can still happen.

Recommended lean:

- **B**.

Why:

- A is simple but may produce absurd forced moves.
- C undercuts the point of M57b.
- B keeps households coherent without making marriage an unconditional teleport leash.

### 5. What counts as a “dependent child” for household/custody purposes?

Options:

- **A) All children below a fixed age threshold**
- **B) Children below adulthood (`AGE_ADULT`)**
- **C) No child household movement yet; only spouse-level migration/pooling**

Recommended lean:

- **B** unless the user strongly wants a separate childhood threshold.

Why:

- The code already has adulthood semantics.
- A second threshold adds more tuning than M57b likely needs.

### 6. In cross-civ marriages, should household behavior change political identity?

Options:

- **A) No**: each spouse keeps their own `civ_affinity`; household only shares wealth/location behavior.
- **B) Residence-first**: trailing spouse gradually adopts the destination/lead spouse’s polity.
- **C) Household primary polity**: the household itself gets a political home.

Recommended lean:

- **A**.

Why:

- `civ_affinity` already participates in multiple systems.
- Rewriting political identity on marriage/migration would blur M57b into assimilation/citizenship law.

### 7. Should M57b add any fertility effect for marriage, or keep demographics unchanged again?

Options:

- **A) Still no fertility modifier**
- **B) Mild married bonus / unmarried penalty**

Recommended lean:

- **A**, unless the user explicitly wants marriage to start reshaping population curves now.

Why:

- M57a already widened marriage into lineage, legitimacy, kin, and memory.
- M57b already has enough risk from wealth + migration + inheritance coupling.

### 8. Should widowhood add a remarriage cooldown, or stay immediately eligible?

Options:

- **A) Immediate re-eligibility after transfer/custody resolution**
- **B) Fixed widowhood cooldown**

Recommended lean:

- **A for now**.

Why:

- The current substrate already removes the marriage bond on death and allows remarriage.
- Adding a cooldown is a social-law feature, not a household-coherence requirement.

---

## Questions the Spec Writer Can Likely Settle Without User Input

These are probably design/implementation decisions rather than user-meaning decisions:

- Household logic should stay **agent-mode only**; `--agents=off` remains unchanged.
- M57b should continue to avoid divorce/polygamy/household trees.
- Any widowhood narration that needs dead-spouse identity probably requires widening dissolution payloads.
- Household consumers should integrate at the existing seams:
  - wealth / percentiles in [`chronicler-agents/src/tick.rs`](../../chronicler-agents/src/tick.rs)
  - migration decisions in [`chronicler-agents/src/behavior.rs`](../../chronicler-agents/src/behavior.rs)
  - death cleanup / dissolution in [`chronicler-agents/src/formation.rs`](../../chronicler-agents/src/formation.rs)

---

## Recommended Drafting Stance

Unless the user pushes in a different direction, I would draft M57b around this narrow shape:

- no first-class household registry yet
- household = married pair + dependent children
- per-agent wealth remains stored, but household behavior uses shared material context
- spouse death transfers wealth to the survivor first
- dependent children stay with the surviving spouse
- joint migration is default household behavior with a small “destination is catastrophically bad” escape hatch
- no fertility retuning yet

That gives M57b real behavioral bite without turning it into a full domestic-life simulation.

---

## Validation Expectations

The M57b spec should explicitly require:

- no regressions to M41 wealth analytics / Gini interpretation
- no regressions to M57a lineage/succession correctness
- no `--agents=off` behavior changes
- determinism preserved across thread counts
- targeted tests for widowhood transfer, dependent movement, and cross-civ marriage households

And before calling M57a fully closed, remember:

- the 200-seed regression is still pending

