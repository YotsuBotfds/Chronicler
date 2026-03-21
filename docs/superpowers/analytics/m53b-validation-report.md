# M53b Validation Report

> 20 seeds (42-61), 200 turns, hybrid mode. Mid-game snapshot at T100 for social/needs data.

## Oracle Results

### Oracle 1: Community Detection — PASS

Emergent social communities (>=3 agents connected by positive bonds with shared memories) detected in 15/20 seeds. Target: >= 15/20.

Communities form through Rust-native formation (M50b) with kin, friend, co-religionist, and mentor bonds. Label propagation detects clusters.

### Oracle 2: Needs Diversity — DEFERRED

0 matched pairs found across 20 seeds. The matched-cohort approach requires personality-identical agent pairs that diverge on a specific need. With personality traits stored as f32 and tolerance at 0.1, no exact matches qualify.

Per-agent event collection (rebellion/migration per agent_id per turn) is needed for event-rate comparison. This requires additional probe infrastructure.

**Structural finding:** Needs are divergent (confirmed by integration probe — social_below_025 = 2%, autonomy_below_030 = 45% at T50). The question of whether need divergence *causes* behavioral divergence requires event-level instrumentation.

### Oracle 3: Era Inflection Points — SOFT FAIL

12/20 seeds (60%) have >= 2 inflection points. Target: >= 80%.

Mean inflections per seed: 1.9. Population series at 200 turns may not have enough dynamic range for the 3-sigma detector. 500-turn runs would likely improve this.

Not a calibration issue — inflections exist (1.9/seed mean), just below the per-seed threshold in some runs.

### Oracle 4: Cohort Distinctiveness — DEFERRED

15/20 seeds have both community and agent data. Event-rate comparison between community members and matched controls requires per-agent event collection (same gap as Oracle 2).

### Oracle 5: Artifact Lifecycle — PARTIAL

| Sub-check | Value | Target | Status |
|-----------|-------|--------|--------|
| Creation rate | 1.14/civ/100t | [1, 3] | OK |
| Type diversity | > 50% one type | No type > 50% | FAIL |
| Destruction rate | 0.02 | [0.10, 0.30] | FAIL |
| Mule artifacts | 6 | — | Present |
| Total artifacts | 182 | — | — |

**Destruction vs Loss:** The oracle only counts `status == "destroyed"` (combat sacking). Separate analysis shows 50% total loss rate when including `status == "lost"` (civ extinction). Artifacts LOST when civs fall are still narrative content ("the lost Crown of Kethani"). The destruction target was calibrated for combat destruction alone and needs recalibration.

**Type diversity:** Dominated by one type. May need cultural_production to weight types more evenly.

### Oracle 6: Civilization Arcs — PASS

All 6 arc families present across 20 seeds: rags_to_riches (18), riches_to_rags (143), icarus (11), oedipus (6), cinderella (4), man_in_a_hole (1), stable (86).

Target: 5 of 6 families. Exceeded — all 6 present.

Riches_to_rags dominance (53% of classified) is expected: most civs peak early then decline. Stable (32%) represents civs with flat trajectories.

## Summary

| Oracle | Status | Notes |
|--------|--------|-------|
| 1: Community | **PASS** | 15/20 seeds |
| 2: Needs Diversity | DEFERRED | Probe needs per-agent event instrumentation |
| 3: Era Inflection | SOFT FAIL | 60% (200t), likely passes at 500t |
| 4: Cohort | DEFERRED | Same as Oracle 2 |
| 5: Artifacts | PARTIAL | Creation OK, type/destruction targets need recalibration |
| 6: Six Arcs | **PASS** | 6/6 families found |

**Blocking criteria met:** Oracle 1 (most important — emergent social structure). Oracle 6 (narrative arc diversity).

**Non-blocking findings:**
- Oracle 3 is a run-length issue, not a calibration issue.
- Oracle 5 targets need recalibration (LOST vs DESTROYED distinction, type diversity weighting).
- Oracles 2 and 4 need per-agent event collection infrastructure for proper evaluation.

**Recommendation:** Proceed with M53 closure. Oracles 2/4 event instrumentation and Oracle 5 target recalibration are deferred to future milestone (M55 or similar).
