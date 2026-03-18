# Phase 6 Progress — Living Society

> Forward-looking decisions and active items only. Implemented/merged content lives in git history.
>
> **Last updated:** 2026-03-17

---

## Active Pre-Merge Items

### M36: Cultural Identity (pre-merge, 1 fix needed)

- **`_culture_investment_active` sticky flag:** Set in `resolve_invest_culture()` but never reset. Once a region receives INVEST_CULTURE, flag persists forever, giving perpetual drift bonus. Fix: clear in `build_region_batch()` after reading, or reset at turn start.

### M38a: Temples & Clergy Faction (fixes applied, ready for merge)

Both pre-merge fixes landed on main:
- `a199c40` — tithe truncated to int
- `0bee24e` — temple conquest lifecycle wired into production code

---

## Locked Design Decisions for Upcoming Milestones

### M38b: Schisms, Pilgrimages & Persecution (spec and plan Phoebe-reviewed, implementation in progress)

- **B-1:** Neutral-axis schisms produce identical doctrines (`-0 = 0`). Fix: when axis value is 0, set to +1/-1 based on trigger context.
- **B-2:** Schism belief reassignment has one-turn delay (Phase 10 detection, agent tick already ran). Documented as intentional.
- **G-1:** Spec needs file changes table.
- **G-2:** Spec needs `--agents=off` section — all three subsystems depend on agent snapshots.
- **G-3:** Pilgrimage pseudocode uses `gp.agent.belief` but `GreatPerson` has `agent_id`, not `agent` ref. Clarify data access path (lookup via snapshot by `agent_id`).
- **G-4:** Trigger 4 needs `last_conquered_turn` on Region — specify default value for existing regions.

### M39: Family & Lineage (implementation in progress)

1. **Inherit at birth, drift handles assimilation.** Child inherits parent's cultural values and belief. M36 drift and M37 conversion apply normally afterward. No special inheritance flags.
2. **Dead ancestors valid, parent-child only (no grandparent chain).** Skip-a-generation requires pool lookback for non-promoted parents — unreliable when parent dies. `parent_id in named_agents` dict gives O(1) detection.
3. **Purely narrative for M39.** `dynasty_id` on `NamedCharacter` is the hook for future mechanical effects. No simulation coupling in M39.
4. **No seeding, 50-70 turn bootstrap.** Initial agents get `parent_id = PARENT_NONE`. First dynasties ~turn 50-70. Tier 2 regression needs ≥200 turns.
5. **Approach A: Rust owns `parent_id`, Python owns dynasty logic.** `parent_ids: Vec<u32>` in pool, exposed via Arrow column. Dynasty detection via `named_agents` dict lookup. No new FFI functions.

---

## Known Gotchas / Deferred Items

- **`_culture_investment_active` dead code pattern:** `build_region_batch()` in `agent_bridge.py` has cleanup code after `return` (lines after return are dead). Any new system using the same pattern (e.g., M38b schisms) must clear transient state BEFORE the return.
- **M34 farmer-as-miner:** Has forward dependency on M41 wealth dispatch.
- **M44 (API narration):** Free-floating — schedule flexibly between heavy milestones.
- **Viewer extensions (M21-M24, M40):** Tech focus badge, faction influence bar, ecology hover, intel indicator — all deferred to Phase 6 M46.
- **Spec-ahead strategy:** Tier 1 spec-able: M41, M44. Tier 2: M45.
