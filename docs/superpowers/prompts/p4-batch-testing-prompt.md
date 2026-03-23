# P4 Batch Testing & Tuning — Cici Prompt

## Context

P4 (Regional Population) just landed. Population now lives on `Region` objects instead of being a single `int` on `Civilization`. The civ-level `population` field is a denormalized cache (sum of controlled regions), synced after every phase that mutates population.

**What changed:** 9 source files, ~147 lines. All 967 tests pass (220 P4-relevant). Phoebe's review verdict: ship. Three post-review fixes applied: `max_pop` cap raised from 100 to 1000, stale pandemic comment fixed, scenario override sync added.

## Task

Run a batch of simulations to validate P4's behavior at scale, then flag anything that looks off. This is a smoke test and tuning assessment, not a full analytics pass.

## Step 1: Batch Run

Run a 20-seed batch, simulate-only (no LLM), 100 turns each:

```bash
cd /path/to/chronicler
python -m chronicler --seed-range 1-20 --turns 100 --civs 4 --regions 8 --simulate-only --parallel --output output/p4_test/chronicle.md
```

Then generate the analytics report:

```bash
python -m chronicler --analyze output/p4_test/batch_1
```

## Step 2: P4-Specific Checks

After the batch completes, write a quick Python script that reads the bundles and checks these P4-specific properties. Run it against the batch output directory.

### 2a. Regional population is non-uniform
For each seed at the final turn, check that regions controlled by the same civ have *different* population values. If all regions of a civ have identical population, P4 didn't work — the old fake-division behavior is leaking through.

### 2b. Population tracks capacity
Check correlation between `region.population` and `effective_capacity(region)` across all regions at the final turn. Expect a positive correlation — fertile regions should generally have more people than barren ones. If correlation is near zero, growth/distribution isn't working.

### 2c. Famine fires regionally
Look at famine events in the event timeline. Check that famine-affected regions have lower population than non-famine regions of the same civ. If a civ with 3 regions has famine in a desert region, the desert should have visibly less population than the civ's plains region.

### 2d. Total population is reasonable
Check the distribution of civ-level population across all seeds at turn 100. The cap is now `min(1000, region_capacity)`, so large empires can grow well beyond 100. Report the mean, median, and range. Watch for: most civs stuck at 1 (drain too high), runaway growth past total regional capacity (growth unchecked), or suspicious clustering at specific values.

### 2e. Migration moves population between specific regions
Look at migration events in the timeline. For each migration, verify that the source region's population decreased and at least one adjacent region's population increased. If migration events exist but all regions have identical population, the migration is writing to civ-level instead of region-level.

## Step 3: Tuning Assessment

Based on the batch results, flag any of these known risks:

1. **Runaway population growth** — With the cap at 1000, check whether large empires (5+ regions) grow without bound or if growth naturally levels off as regions approach carrying capacity. If civs routinely exceed total carrying capacity of their regions, the growth logic has a leak.

2. **Population collapse** — If most civs hit 1 and stay there, drain rates are too high relative to growth. Check whether the regional distribution is concentrating all losses on single regions (the `distribute_pop_loss` spikiness I flagged in the review).

3. **Empty regions** — Count how many controlled regions have `population = 0` at turn 100. Some is expected (newly conquered, post-famine), but if >30% of controlled regions are empty, growth isn't distributing to new acquisitions.

4. **Secession population split** — Check that when a secession happens, the breakaway civ's population roughly matches the sum of its region populations, and the parent civ's population dropped by the same amount. Look for any case where secession creates or destroys population.

## Step 4: Report

Write a short summary (not a full analytics report) with:
- Batch stats: seeds run, turns, total events
- P4 validation results (pass/fail for each 2a–2e check)
- Tuning flags (any of the Step 3 risks observed)
- Recommended tuning changes (if any), with specific constants and suggested values

Save as `p4-batch-results.md` in the project root.

## What NOT To Do

- Don't change any simulation code. This is observation only.
- Don't run LLM narration — simulate-only is sufficient.
- Don't compare against a pre-P4 baseline (we don't have one cached). This is a forward-looking validation.
- Don't do a full M19-style analytics report. Keep it focused on P4-specific behavior.
