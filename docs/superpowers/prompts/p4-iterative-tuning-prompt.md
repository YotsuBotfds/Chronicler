# Iterative Tuning Protocol — Population Economy (Post-P4)

## Goal

World population at turn 1000 should be *stable, not growing or collapsing*. Target metrics at turn 500 and turn 1000:

- Median civ population: 15–40 (not 1, not 100)
- Civs at floor (pop <= 1): < 25%
- Empty controlled regions: < 20%
- Zero runaway (no civ exceeds total regional carrying capacity)

## Loop

1. Run: `--seed-range 1-20 --turns 1000 --simulate-only --parallel`
2. Analyze: `--analyze` the output directory
3. Run the P4 validation script (from `p4-batch-testing-prompt.md`) against the batch
4. Check metrics against targets above
5. If targets not met, identify the dominant failure mode:
   - **Too many at floor** -> increase growth rate, reduce drain rates, or add population recovery for empty regions
   - **Too many empty regions** -> add passive population seeding to controlled regions with 0 pop (conquered regions should slowly repopulate)
   - **Median too low** -> growth gates are too restrictive or drain events fire too often
   - **Median too high** -> growth is unchecked, add population pressure from overcrowding
6. Adjust constants via `GameConfig` overrides (not hardcoded changes). Document each change.
7. Go to step 1. **Stop when all four targets are met for 3 consecutive batch runs.**

## Tuning levers (in priority order)

- `K_FAMINE_DRAIN` — currently `int(8 * mult)`, the single largest per-event pop loss
- Growth rate in `phase_production` — currently +5 flat, consider scaling with fertility or capacity
- Empty region repopulation — doesn't exist yet; controlled regions with pop 0 should gain +1-2/turn passively
- `K_FERTILITY_RECOVERY` — currently 0.05, controls how fast land recovers after famine
- Pandemic/supervolcano pop loss — currently 12 and 20, both huge relative to growth

## Key insight from the 50-seed 1000-turn batch

The world looks healthy at turn 100 but hollows out by turn 500. Median population hits 1 and stays there. 51% of civs are at floor. 32.8% of controlled regions are empty — including 49 plains regions. Famine fires in 100% of runs. The drain-exceeds-growth problem is structural, not a parameter tuning issue. **An empty-region repopulation mechanic is probably required**, not just constant tweaks.

## Rules

- Use `--tuning` YAML overrides, not hardcoded changes, for constant adjustments
- If a new mechanic is needed (like empty region repopulation), implement it minimally — 5-10 lines max
- Each iteration should change at most 2-3 constants. Don't shotgun.
- Save each batch's `batch_report.json` with a label so we can compare iterations
- Stop and report when targets are met or after 5 iterations, whichever comes first
