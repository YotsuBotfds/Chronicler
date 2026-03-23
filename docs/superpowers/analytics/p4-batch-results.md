# P4 Batch Test Results

## Initial Validation (100 turns)

All 5 P4 checks pass. Regional population is working correctly:
- **2a** Non-uniform regional pop: PASS (r=0.86 capacity correlation)
- **2b** Population tracks capacity: PASS
- **2c** Famine fires regionally: PASS
- **2d** Total population reasonable: PASS
- **2e** Migration region-specific: PASS

## Iterative Tuning (1000 turns, 20 seeds each)

### Iteration Summary

| Iter | Change | Turn 1000 Median | Floor% | Empty% | Runaway | Score |
|------|--------|:----------------:|:------:|:------:|:-------:|:-----:|
| 1 | Baseline (pre-P4 constants) | 6 | 39.1% | 34.7% | 0 | 1/4 |
| 2 | Empty region repopulation (+2/turn) | 6 | 1.1% | 0.6% | 0 | 3/4 |
| 3 | Famine drain 8->5, fertility recovery 0.05->0.08 | 6 | 1.1% | 0.0% | 0 | 3/4 |
| 4 | Growth scaling 3*regions -> 5*regions | 11 | 3.8% | 0.7% | 0 | 3/4 |
| 5 | Repopulation +2 -> +3 | 9 | 2.4% | 0.0% | 0 | 3/4 |

Targets: median 15-40, floor <25%, empty <20%, runaway 0.

### What passed

- **Floor (civs at pop <= 1):** 39.1% -> 2.4%. Fixed by empty region repopulation.
- **Empty controlled regions:** 34.7% -> 0.0%. Fixed by empty region repopulation.
- **Runaway growth:** 0 across all iterations. `add_region_pop` caps at `effective_capacity`, which is the right safety valve.

### What didn't pass

**Median civ population** stuck at 6-11 (target 15-40). Root cause: secessions create many 1-region fragments in poor terrain (desert/tundra with effective_capacity 4-8). These fragments are *structurally incapable* of reaching pop 15 because their terrain caps them below that.

Among **2+ region civs only**, the median is ~17 at turn 1000, which passes the target. The overall median is dragged down by splinter civs, not by a growth/drain imbalance.

This is not a tuning problem — it's a question of whether the median target should account for secession fragments, or whether the secession mechanic itself needs to filter out unviable breakaway civs (e.g., don't secede a single desert region).

## Final Code Changes (all in simulation.py)

| Line | Before | After | Iteration |
|------|--------|-------|-----------|
| 389 | `economy > population` | `economy > population // 3` | Pre-iter |
| 389 | `stability > 20` | `stability > 10` | Pre-iter |
| 395 | `stability <= 10` | `stability <= 5` | Pre-iter |
| 391 | Growth to one region | Spread across all regions | Pre-iter |
| 391 | `growth = 5` (flat) | `growth = max(5, 5 * len(civ_regions))` | Iter 4 |
| 916 | `int(15 * mult)` | `int(5 * mult)` | Iter 3 |
| 887 | `pop < cap * 0.5` | `pop < cap * 0.75` | Pre-iter |
| 401-404 | (none) | Empty region repopulation +3/turn | Iter 2/5 |

## Tuning YAML (tuning_iter3.yaml)

```yaml
fertility:
  recovery_rate: 0.08  # default 0.05
```

## Known Issues

1. **Sync desync at civ population floor:** Civs with all-empty regions show `civ.population = 1` but `sum(region.population) = 0`. Intentional floor in `sync_civ_population`, not a bug.

2. **Large empire growth rate:** `5 * len(civ_regions)` gives a 6-region empire +30/turn distributed (+5/region). Capped by `effective_capacity` so no runaway observed, but worth monitoring in longer runs.

3. **Secession fragment viability:** Many secession breakaway civs are single-region splinters in poor terrain. They can never grow beyond their terrain cap (~4-8 for desert/tundra). Consider adding a minimum-region or minimum-capacity gate to the secession mechanic.

## Recommendation

The population economy is stable at 1000 turns for established civs. The remaining median gap is a game design question about secession, not a tuning problem. Options:
- Accept that secession fragments pull the median down (they add narrative variety)
- Add a secession gate: don't allow breakaway if the resulting civ would have total carrying capacity < 20
- Merge/absorb unviable splinter civs after N turns of pop <= floor
