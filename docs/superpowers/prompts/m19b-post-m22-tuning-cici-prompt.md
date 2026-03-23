# M19b Post-M22 Tuning Pass — Cici Session Prompt

> Copy this prompt into a fresh Cici session after M22 (Factions & Succession Integration) lands.
> This is the second M19b pass. The first pass (pre-M21) fixed the stability death spiral and wired 8 dead hooks. This pass validates M21 (Tech Specialization) and M22 (Factions & Succession) integration and tunes their constants.

---

You are running the second M19b tuning pass for Chronicler. M21 (Tech Specialization) and M22 (Factions & Succession Integration) have both landed. This pass validates that the new systems produce healthy distributions and interact correctly with each other and the base simulation.

## Context

**First M19b pass results (pre-M21, for comparison):**
- Stability median @ turn 100: 35 (was 0 in baseline)
- Zero-stability rate @ turn 100: 12% (was 99%)
- Stability recovery (+20/turn when < 50) and culture-based regression resistance were added
- All M14-M18 mechanics fire at ≥ 10%
- 8 distinct tech eras represented at turn 500

**What M21 added:**
- 15 tech focuses across 5 eras (Classical → Information)
- Stat modifiers on focus selection (e.g., METALLURGY: +15 military)
- Action weight biases per focus (e.g., METALLURGY: WAR ×1.5, BUILD ×1.3)
- Unique capabilities (e.g., COMMERCE: trade income ×1.5)
- 2.5x global weight cap in `compute_weights()`

**What M22 added:**
- Three factions (military, merchant, cultural) with zero-sum normalized influence
- Dominant-only exponentiation formula for action weights (`faction_weight ** influence`)
- Power struggles (trigger: two factions within 0.05, both > 0.30; resolve after 5 turns)
- Faction-weighted succession candidates and crisis resolution
- Faction modifier on crisis probability (power struggle ×1.4, leader alignment ×0.8 or ×1.3)
- Secession viability fix: capacity-weighted region selection + absorption safety net
- 3 new event types: `power_struggle_started`, `power_struggle_resolved`, `faction_dominance_shift`
- `FOCUS_FACTION_MAP`: 7 merchant, 5 military, 3 cultural tech focus → faction mapping

## Exit Criteria (all must pass simultaneously)

### Preserved from First Pass (regression check)
1. Stability median > 30 at turn 100 (first pass achieved 35)
2. Stability σ > 15 at turn 100 (first pass achieved ~22)
3. Every M14-M18 mechanic fires in ≥ 10% of 200 runs
4. No degenerate 100% negative event pattern
5. 3+ tech eras at turn 500

### New: M21 Tech Specialization
6. **Focus distribution per era:** Each of the 3 focuses per era is selected by ≥ 15% of civs reaching that era. No single focus > 60% in any era. (Tests that geography + state produce variety, not monoculture.)
7. **Focus-geography correlation:** Coastal civs select NAVIGATION at ≥ 2× the rate of landlocked civs. Mountain/iron civs select METALLURGY at ≥ 2× the rate of plains civs. (Tests that scoring helpers reflect geography.)
8. **Weight cap effectiveness:** Action selection entropy per civ per era ≥ 1.5 bits median. (Tests that the 2.5× cap prevents any single action from dominating. Entropy < 1.5 bits means one action is chosen > 60% of the time.)
9. **Focus capability firing:** Each unique capability (NAVIGATION coastal settlement, AGRICULTURE famine recovery, COMMERCE trade bonus, etc.) fires in ≥ 5% of runs where a civ holds that focus for 20+ turns.

### New: M22 Factions & Succession
10. **Faction dominance distribution at turn 100:** No single faction type is dominant in > 50% of all civs. (Tests that the system produces faction variety, not universal military dominance.)
11. **Faction dominance distribution at turn 500:** At least 2 faction types each dominant in ≥ 20% of surviving civs. (Tests long-run faction diversity.)
12. **Power struggle frequency:** Power struggles occur in ≥ 15% of civ-lifetimes (civs alive for 100+ turns) by turn 500. Fewer than 5% = trigger threshold too tight; more than 40% = influence shifts too compressed. (Note: measure per-civ, not per-run. A 5% per-civ rate with 8 civs gives ~34% per-run — passing a per-run metric despite being too low per-civ.)
13. **Power struggle resolution balance:** No single faction type wins > 60% of power struggles. (Tests that win counting and event detection are balanced across faction types.)
14. **Faction-succession correlation:** When a succession crisis resolves during or after a power struggle, the winning faction's influence increases by ≥ 0.10 in ≥ 70% of cases. (Tests that resolution shifts are actually applied.)
15. **Secession viability — median population:** Median civ population at turn 500 ≥ 12 (first pass achieved ~9 pre-M22, secession viability fix should raise this). No more than 10% of surviving civs with total effective capacity < 10.
16. **New event types firing:** `power_struggle_started` ≥ 15%, `power_struggle_resolved` ≥ 15%, `faction_dominance_shift` ≥ 30% of 200 runs.

### New: Combined System Interactions
17. **Weight stacking under cap:** Median pre-cap weight across all civs/actions is < 3.5x. The 2.5x cap fires on ≥ 5% of weight calculations (it exists for a reason) but < 50% (it shouldn't be the primary balancing mechanism).
18. **FOCUS_FACTION_MAP merchant skew validation:** Merchant-dominant civs at turn 500 are NOT > 50% of surviving civs. (The 7/5/3 distribution is asymmetric by design — merchant factions have more tech focus inputs but weaker single-event swings. If merchant dominates, the shift table offsets aren't working.)
19. **Trait × tradition × focus × faction interaction:** No civ maintains the same action as its top-weighted choice for > 80% of turns in a 100-turn window. (Tests that the combined modifier stack doesn't create locked-in behavior.)

## Process

**Step 1: Baseline with M21 + M22.**
```bash
chronicler --seed-range 1-200 --turns 500 --simulate-only --output output.md --state state.json --parallel 30
chronicler --analyze ./batch_1 --checkpoints 25,50,100,200,500
```
Save as `m19b_post_m22_baseline.json`.

**Parallelism:** Tate's machine is a 9950X — use `--parallel 30` on all batch runs (leaves 2 threads free for OS + other tasks). This applies to every `--seed-range` invocation in this prompt, including tuned batches in Steps 5-8.

**Step 2: Read analytics report.** For each exit criterion, report the metric value and whether it passes. Present as a summary table to Tate. Flag any regressions from the first M19b pass.

**Step 3: New analytics queries.** Some exit criteria require new analytics that don't exist yet. Before running the first batch, check whether the analytics module can compute:
- Action selection entropy per civ (criterion 8)
- Faction dominance distribution across civs at a checkpoint (criteria 10, 11)
- Power struggle frequency and resolution balance (criteria 12, 13)
- Pre-cap weight distribution (criterion 17)
- Top-action persistence over 100-turn windows (criterion 19)
- Focus distribution per era (criterion 6)

If any are missing, implement them in the analytics module first (each should be a small function reading CivSnapshot or events_timeline data). Flag any that require new data in CivSnapshot beyond what M21 and M22 already populate.

**Step 4: Propose tuning adjustments.** For each failing criterion, propose constant changes. Priority order:
1. Fix regressions from first pass first (stability, mechanic firing rates)
2. Then tune M22 constants (influence shift magnitudes, power struggle thresholds)
3. Then tune M21 constants (scoring weights, stat modifier magnitudes)
4. Combined interaction issues last (weight cap value, FOCUS_FACTION_MAP reassignment)

**🚩 FLAG FOR TATE** before applying any tuning.yaml. Present changes as a table.

**Step 5-8:** Same iteration loop as the first M19b prompt — run tuned batch, compare, adjust, iterate. Max 2-3 constants per iteration.

**🚩 FLAG FOR TATE** if:
- Fixing a faction criterion breaks a stability criterion (M22 adding too much drain)
- The 2.5× weight cap needs to change (affects both M21 and M22 balance)
- The `FOCUS_FACTION_MAP` 7/5/3 distribution needs rebalancing (design decision, not tuning)
- Power struggle frequency per-civ is < 5% or > 40% (may need threshold changes, not constant tuning)
- Merchant dominance > 50% at turn 500 (FOCUS_FACTION_MAP skew not offset by shift table)
- You've done 5+ iterations without convergence

**Step 9: Bake and verify.** Same as first pass — bake final values into GameConfig/defaults, run without --tuning, confirm exit criteria.

**Step 10: Write report.** Save as `docs/superpowers/analytics/m19b-post-m22-tuning-report.md`. Include:
- Baseline vs final for all 19 exit criteria
- Constants changed (with before/after values)
- Any new analytics functions added
- Interaction effects observed (e.g., "reducing power struggle stability drain improved criterion 1 without affecting criterion 12")
- Regressions from first pass baseline (if any) and how they were resolved

## Available Tuning Constants

### From First Pass (may need re-tuning)
All `K_*` constants from the first M19b prompt are still available. The stability economy may shift after M21/M22 land — power struggle drain, focus stat modifiers, and faction-weighted action selection all affect stability indirectly.

### M21 Constants (tech_focus.py)
- Focus stat modifier magnitudes (e.g., METALLURGY military +15) — in `FOCUS_EFFECTS` dict
- Focus weight modifier values (e.g., METALLURGY WAR ×1.5) — in `FOCUS_EFFECTS` dict
- Scoring helper weights (`_count_terrain`, `_count_resource`, `_count_infra` thresholds)
- GP bonus (+5) and tradition bonus (+3) in `_GP_BONUSES` / `_TRADITION_BONUSES`
- 2.5× global weight cap in `compute_weights()`

### M22 Constants (factions.py)
- Influence shift magnitudes (shift table: war win +0.10, trade +0.08, etc.)
- Influence floor (0.05) in normalization
- Power struggle trigger threshold (gap < 0.05, both > 0.30)
- Power struggle duration (forced resolution after 5 turns)
- Power struggle stability drain (-3/turn × severity multiplier)
- Action effectiveness penalty during power struggle (`_power_struggle_factor()` in action_engine.py:61-63, returns 0.8 when `power_struggle` is True)
- Resolution influence shift (+0.15)
- GP per-turn faction bonus (+0.03 general/merchant/prophet, +0.02 scientist)
- Outsider chance in crisis resolution (10%)
- Faction candidate weight threshold (influence < 0.15 = too weak to field)
- External backer candidate weight (0.1)
- GP candidate faction boost (+0.10 if GP faction matches dominant)

### M22 Constants (succession.py)
- Crisis probability: power struggle modifier (×1.4)
- Crisis probability: leader alignment thresholds (> 0.5 → ×0.8, < 0.2 → ×1.3)
- Exile restoration: same-faction modifier (×0.3), opposing-faction modifier (×1.5)
- Grudge inheritance: same-faction rate (0.7), different-faction rate (0.3), neutral rate (0.5)

### M22 Constants (politics.py)
- Secession score formula: `distance * 0.7 + capacity * 0.3`
- Absorption safety net: capacity threshold (< 10), age threshold (> 30 turns)

## Important Notes

- All analytics should read from `chronicle_bundle.json` / CivSnapshot data — NOT import from simulation modules
- The `FOCUS_FACTION_MAP` distribution (7/5/3) is a design decision. If merchant dominance is a problem, first try adjusting influence shift magnitudes before proposing map changes. Flag map changes for Tate.
- Power struggle frequency is sensitive to both trigger thresholds AND influence shift magnitudes. If factions are too compressed (everyone near 0.33), struggles trigger too often. If one faction runs away, they never trigger. The shift table magnitudes control how fast influence moves.
- The 2.5× weight cap affects M21 focus weights AND M22 faction weights. Changing it is a cross-system decision. Don't change without flagging.
- CivSnapshot should now include `active_focus` (M21) and `factions` (M22). If either is missing from snapshots, that's a bug — flag it.
