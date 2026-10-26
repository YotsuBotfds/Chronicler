# Needs oracle: pooled matched pairs

> **Superseded as the gate's method by method 3** (2026-10,
> [`needs-followups.md`](needs-followups.md) §1): method 2's criteria stay
> and a binding component is added, the pairs that straddle a need's
> threshold with their own seed-clustered lower bound, required in the full
> profile and informational in the subset profile.
> `run_needs_oracle(..., require_binding=False)` scores method 2 alone.

Branch `fix/needs-oracle-power` from `origin/main` `48b72be` (PR #31, agent
movements, default off). Changed: the needs oracle
(`src/chronicler/validation_io.py`), the report comparator
(`src/chronicler/validation_compare.py`) and their tests. The simulation,
Rust, the sidecars, the gate profiles and every other oracle are unchanged.

**Status.** Method 2 pools every eligible snapshot and pairing of every seed,
and passes on a seed-clustered lower bound plus the M53 seed fraction. The
subset gates of main (42-61, 62-81, 82-101), routing with `--no-cities`
(62-81) and `--agent-movements` (42-61) pass. Shuffling needs within matched
cells fails 15 of 15 times; method 1 passed 10 of those 15. Zeroing every
need-driven behavior term in Rust is not reliably caught: it cuts the
pooled effect by about 40%, and 2 of 3 subsets still pass
([Sensitivity](#sensitivity)).
The 200 x 500 full gate has not been run with method 2.

## Method 1 and why it had few pairs

M53 oracle 2 tests one hypothesis: an agent whose need is lower than a
matched agent's has more of the event that need drives over the next 20
turns.

| Need | Event |
| --- | --- |
| autonomy | rebellion (agents with a rebellion on or before the snapshot left out) |
| social | migration |
| purpose | occupation switch |
| material | migration |
| safety | migration |

Two agents match when civ affinity, region and occupation are equal,
boldness, ambition and loyalty trait each differ by at most 0.1, and the
need differs by more than 0.2 (greedy first match, each agent in one pair).
Needs snapshots are every 10 turns from turn 0. A snapshot is eligible when
its window `[T, T + 20)` fits the run: 19 per 200-turn run, 49 per 500-turn
run.

Method 1 scored every eligible snapshot and pairing (19 x 5 = 95 candidates
per subset seed) and kept one per seed: the first by (expected sign, pairs,
|d|). A seed counted when that candidate had a positive rate difference and
|d| > 0.10. PASS took 60% of seeds and a median |d| above 0.10. The chosen
candidates held 34, 25 and 40 pairs on the three main subsets (1-4 per seed),
so a seed's verdict rested on one or two pairs. Best-of selection also passes
when needs carry no information: with needs shuffled within cells, method 1
passed 10 of 15 batches ([Sensitivity](#sensitivity)).

**Why pairs were scarce** (main 42-61, all 380 eligible snapshots):

- The worlds are small. A snapshot holds a median of 185 agents (83-345),
  stable over 200 turns, in about 55 (civ, region, occupation) cells. The
  largest cells hold 10-15 agents.
- A cell's agents share their region's restoration, so their needs barely
  spread. The median within-cell standard deviation is 0.10 for autonomy,
  0.06 material, 0.05 safety, 0.03 social and 0.03 purpose. A 0.2 gap is
  2-7 standard deviations.
- The 0.1 tolerance on three traits removes most remaining candidates.
- Events are not rare: per agent and 20-turn window, 1.23 migrations, 0.77
  rebellions and 0.97 occupation switches. Rebellion is rare among agents
  that never rebelled: 14 of 154 autonomy pairs differ in rebellions.
- The horizon matters less than the matching: 500 turns give 2.6 times the
  snapshots of 200.

Pairs pooled over every eligible snapshot and the five pairings, 42-61:

| Matching | Pairs | Informative (unequal counts) |
| --- | ---: | ---: |
| method 1's chosen candidates | 34 | - |
| gap 0.2, traits 0.1 (method 1 rules, all snapshots) | 230 | 63 |
| gap 0.2, traits 0.1, every qualifying pair (not one per agent) | 241 | 65 |
| gap 0.1, traits 0.1 (method 2) | 1,533 | 602 |
| gap 0.2, no trait matching | 6,394 | 2,153 |

Pooling alone, under method 1's rules, gives 63, 45 and 54 informative
pairs on the three main subsets. The net concordance is +0.11 (lower bound
-0.12), +0.33 (+0.03) and +0.48 (+0.23): not enough for a stable verdict.

## Method 2

Same hypothesis, pairings, directions, cells, trait tolerance, window and
prior-rebel exclusion. Two changes:

1. **All snapshots and pairings pooled.** Every matched pair of every eligible
   snapshot and pairing counts. A pair is concordant when the lower-need
   agent has more of the event, discordant when fewer, tied otherwise.
2. **Need gap 0.1** (was 0.2). The gap sets the contrast. The matching
   controls confounds: cell, traits, prior rebels. Loosening the trait
   tolerance would also add pairs, but it would weaken a confound control
   (boldness enters safety restoration and the migrate and rebel utilities).
   Gap 0.1 is at or above the within-cell spread of every need.

Per seed: concordant C, discordant D, net concordance (C - D) / (C + D), and
a one-sided exact sign-test p-value. The p-value is descriptive: a seed's
pairs share agents across overlapping windows.

Across seeds: the pooled net concordance sum(C - D) / sum(C + D). Each seed
is a cluster. The ratio estimator's variance is
`S / (S - 1) * sum((C_s - D_s - net * n_s)^2) / n^2` over the S seeds with
informative pairs.

**PASS** requires both:

- the one-sided 95% lower bound (Student t, S - 1 degrees of freedom) is
  above zero;
- at least 60% of analyzed seeds have C > D.

The report also gives the estimate and bound per pairing (informational).
At least two seeds with informative pairs are needed for a bound; a single
seed fails.

**Full profile strictness.** The 60% seed fraction (120 of 200) stays, now on
each seed's pooled pairs, which a seed passes less easily than its best of
245 candidates. The pooled bound is a second requirement. Under the null
(needs shuffled within cells), method 2 passed none of 15 batches and method
1 passed 10.

Sensitivity to the gap and tolerance on the three main subsets (net
concordance, lower bound, seeds with C > D of 20). Method 2 is the third row:

| Gap / traits | 42-61 | 62-81 | 82-101 |
| --- | --- | --- | --- |
| 0.20 / 0.10 | +0.11, -0.12, 10 | +0.33, +0.03, 9 | +0.48, +0.23, 14 |
| 0.15 / 0.10 | +0.20, +0.08, 14 | +0.32, +0.16, 13 | +0.42, +0.28, 17 |
| **0.10 / 0.10** | **+0.18, +0.10, 15** | **+0.20, +0.10, 15** | **+0.33, +0.24, 18** |
| 0.20 / 0.15 | +0.27, +0.13, 13 | +0.25, +0.04, 13 | +0.38, +0.25, 17 |
| 0.20 / 0.20 | +0.30, +0.20, 16 | +0.18, +0.03, 12 | +0.31, +0.22, 17 |

## Verdicts

Each set: 20 worlds x 200 turns, `scripts/m53b_run_validation.py --profile
subset --parallel 1`, hybrid, `PYTHONHASHSEED=0`, Linux, Python 3.13.17.
The native extension was built fresh from `48b72be`, verified, SHA-256
`cde64b3e...b5cf6a`. Method 1 is `run_needs_oracle_best_of`. It equals the
in-run reports of the same batches (checked on all five main and config
batches). The final in-run reports of method 2 equal the re-scores. Net
concordance and its standard error, lower bound, seeds with C > D / C < D:

| Set | Method 1 (seeds / 12; pairs) | Method 2 | Net (SE) | Lower bound | Seeds + / - | Informative / pairs |
| --- | --- | --- | --- | --- | --- | --- |
| main 42-61 | PASS 16 (34) | PASS | +0.179 (0.045) | +0.101 | 15 / 3 | 602 / 1,533 |
| main 62-81 | PASS 16 (25) | PASS | +0.199 (0.058) | +0.098 | 15 / 4 | 544 / 1,829 |
| main 82-101 | PASS 16 (40) | PASS | +0.330 (0.049) | +0.245 | 18 / 1 | 636 / 1,768 |
| routing, `--no-cities`, 62-81 | **FAIL** 8 (41) | PASS | +0.184 (0.049) | +0.099 | 13 / 6 | 561 / 1,815 |
| `--agent-movements`, 42-61 | PASS 12 (31) | PASS | +0.138 (0.051) | +0.049 | 17 / 3 | 596 / 1,524 |
| need terms off, 42-61 | PASS 14 (33) | **FAIL** | +0.089 (0.062) | -0.019 | 10 / 8 | 586 / 1,659 |
| need terms off, 62-81 | PASS 14 (31) | PASS | +0.158 (0.054) | +0.065 | 14 / 4 | 501 / 1,903 |
| need terms off, 82-101 | FAIL 11 (38) | PASS | +0.178 (0.042) | +0.104 | 14 / 5 | 608 / 1,673 |
| needs shuffled in cells, 15 batches | PASS 10 of 15 | **FAIL 15 of 15** | -0.089 to +0.048 | -0.158 to -0.021 | 6-13 | 531-650 |
| 500-turn probe, 142-161 | PASS 19 (39) | PASS | +0.166 (0.026) | +0.121 | 17 / 3 | 1,713 / 4,797 |

- **Main.** Estimates sit 3.4 to 6.7 standard errors above zero. All seed
  fractions are 15 or more of the 12 required. The gates pass, and every
  other oracle result is identical between method 1 and method 2 reports.
- **Routing with cities off, 62-81.** Method 1 fails it: 8 seeds against
  main's 16. Method 2 passes at the main sets' level (+0.18 against +0.20 on
  main 62-81).
- **Movements on, 42-61.** Method 1 drops 16 -> 12. Method 2 gives +0.138
  against main's +0.179, a difference of 0.6 combined standard errors. The
  bound stays positive and 17 seeds are positive. Within the pool, autonomy
  turns negative (22 / 31) while the other pairings hold. Movements recruit
  by need and restore needs on a reform.
- The movements and `--no-cities` runs are main's code (`48b72be`) with the
  switch. The figures in the city-markets and movements docs came from the
  feature branches before their merges; method 1 reads the same here (8 and
  12).

## Sensitivity

**Needs shuffled within cells** (5 permutations of each main subset,
applied to the loaded sidecars before scoring). Every need column is
permuted among the
agents of each (snapshot, civ, region, occupation) cell. Identities,
traits, cells and events are kept, so a need says nothing about its
agent's own behavior. Method 2 fails all 15. Method 1 passes all ten
shuffles of 42-61 and 82-101 and fails the five of 62-81.

**Unit tests** (`tests/test_validate.py`):

- a ten-seed world where lower-material agents migrate more passes;
- the same world fails with no link, reversed, or with needs permuted within
  cells;
- four strong seeds among ten pass the bound but fail the seed fraction;
- a single seed fails (no bound).

**Need-driven behavior terms off (Rust).** A build in which
`compute_need_utility_modifiers` returns zero modifiers and the autonomy
deficit no longer speeds loyalty drift. It is a temporary edit, built into
its own environment and reverted; extension `8640d9c6...`. Method 2 fails
42-61 and passes 62-81 and 82-101; method 1 passes two and fails one. So
neither method reliably catches it. Pooled over the three subsets
(concordant / discordant, net):

| Pairing | Main | Terms off | 500-turn probe (main) |
| --- | --- | --- | --- |
| autonomy | 74 / 50, +0.19 | 70 / 46, +0.21 | 58 / 61, -0.03 |
| social | 45 / 54, -0.09 | 38 / 59, -0.22 | 28 / 65, -0.40 |
| purpose | 80 / 47, +0.26 | 50 / 60, -0.09 | 53 / 53, 0.00 |
| material | 637 / 389, +0.24 | 572 / 403, +0.17 | 567 / 358, +0.23 |
| safety | 268 / 138, +0.32 | 237 / 160, +0.19 | 293 / 177, +0.25 |
| all | 1,104 / 678, +0.24 | 967 / 728, +0.14 | 999 / 714, +0.17 |

Turning the terms off cuts the pooled effect by about 40%, and purpose
reverses. The rest of the association does not come from the need terms.
The terms are threshold-gated (`needs.rs`): a need acts only below its
threshold. On 42-61 the share of agents below threshold per snapshot is:

| Need | Threshold | Share below |
| --- | ---: | ---: |
| safety | 0.30 | 0.0% |
| material | 0.30 | 0.09% |
| social | 0.25 | 0.01% |
| autonomy | 0.25 | 0.04% |
| purpose | 0.35 | 15% |
| spiritual (not paired) | 0.30 | 7.3% |

Needs do not enter satisfaction. Outside movements, their only effect on
behavior is these terms. The material and safety associations hold among
pairs where neither agent migrated in the 20 turns before the snapshot
(material 50 / 29 and 55 / 16, safety 22 / 7 and 24 / 5 on 42-61 and
82-101), and over 200 turns on 42-61 (material 30 / 20, safety 12 / 4).
So they are not left-over migrants. Agent differences the matching does not
see are the likely source: wealth percentile and urban status enter
material and safety restoration, and age enters social. Zeroing the term of
safety, material, social or autonomy alone would change almost no decision,
so no association test could see it. Method 2 catches needs that say
nothing about their agent's behavior, as the shuffle shows. It cannot
separate the need terms from the other channels.

## Full profile

Not run with method 2. The 500-turn probe (seeds 142-161, the subset
profile's sidecars with `--turns 500`) gives +0.166 with a lower bound of
+0.121, 17 of 20 seeds, and 86 informative pairs per seed. At 200 seeds the
same effect would give a lower bound near +0.15 and about 170 seeds against
120 required. That is a projection; the next full gate is the check.

## Compatibility

- **Result version.** The needs result carries `method: pooled_matched_pairs`
  and `method_version: 2` (3 from `needs-followups.md`). A result without `method_version` is method 1.
  `status`, `analyzed_seeds`, `required_seed_count`,
  `seeds_with_expected_sign`, `total_pairs`, `autonomy_excludes_prior_rebels`
  and `per_seed` keep their names. `median_effect_size` is gone, and per-seed
  entries no longer name a snapshot or need. The gate reads only `status`.
- **Comparator.** `validation_compare` reads each oracle's method version.
  When the two reports differ, that oracle's failures are not counted as new
  or resolved, so there is no regression from the method change.
  `oracle_method_changes` lists the oracle with both versions and statuses,
  `rebaseline_required` is true, and the markdown adds an "Oracle method
  changes" section. The current report's own gate decision still applies; a
  method 2 FAIL fails its gate. On the real reports, method 1 PASS (main
  42-61) against method 2 FAIL (terms off 42-61) was a new required failure,
  exit 2 under `--fail-on-regression`, with `origin/main`'s comparator. It is
  now no regression with re-baselining flagged. Method 1 FAIL against method
  2 PASS (`--no-cities` 62-81) is no longer reported as resolved. A
  non-integer `method_version` is rejected. Neither comparator crashes on
  either format.
- **Re-baselining.** A baseline report from before this branch compares as
  method 1. Re-score its batch with `python -m chronicler.validate
  --batch-dir BATCH --oracles all` and compare the new report. A report whose
  batch was deleted cannot be re-scored; its other oracles still compare.
  `run_needs_oracle_best_of` reproduces method 1 on any batch.
- **Fixtures.** No JSON fixture or golden file pins the needs result. Changed
  test expectations in `tests/test_validate.py`:
  - `test_run_needs_oracle_uses_all_sampled_turns` ->
    `test_needs_best_of_uses_all_sampled_turns`: method 1, unchanged
    expectations.
  - `test_needs_oracle_autonomy_confound_reverses_then_exclusion_restores`:
    the method 1 assertions (per-seed need, pairs, rate difference) move to
    `test_needs_best_of_autonomy_confound_reverses_then_exclusion_restores`.
    The method 2 test uses three seed copies: confounded, autonomy 24 pairs,
    12 / 12, net 0, FAIL; with the exclusion, 12 pairs, 12 / 0, PASS.
  - `test_needs_rebel_exclusion_leaves_other_pairings_unchanged`: method 1
    copy renamed `test_needs_best_of_...`. The method 2 test uses two seed
    copies, since one seed has no bound and fails. Per-seed records are
    equal with and without the exclusion, material `[3, 3, 0]`, PASS.
  - Unchanged: `compute_needs_diversity` (default gap 0.2, same pairs: its
    matching now shares `_match_needs_pairs`), `_needs_candidate_priority`,
    the prior-rebel helpers.
  - New: `_match_needs_pairs` equals method 1's all-agents scan (400 agents,
    gaps 0.1 and 0.2); the pooled estimate and sign test by hand; the
    pass/fail cases above; snapshots whose window overruns the run are
    skipped. In `tests/test_validation_compare.py`: method change not new,
    not resolved; same method still detects new failures; malformed version
    rejected; CLI on old against new reports.

## Identity

Seeds 42, 43 and 44, 200 turns, hybrid with `--validation-sidecar`, same
interpreter and extension, `PYTHONHASHSEED=0`. Run once with `origin/main`'s
Python source and once with this branch's, then compared by
`scripts/agent_movements_identity.py compare`: 330 files, 0 differences. The
re-run subset gates reproduced the first runs' needs and event sidecars byte
for byte (five sets).

## Run cost

Needs scoring alone, after loading, with other jobs sharing the 4 cores:

| Batch | `origin/main` (method 1) | Method 2 |
| --- | --- | --- |
| main 42-61, 62-81, 82-101 (20 x 200) | 4.1, 4.0, 5.0 s | 1.0, 0.4, 0.5 s |
| probe 142-161 (20 x 500) | 12.2 s | 1.5 s |

Method 1 scanned every later agent of the snapshot for each agent
(quadratic in the snapshot) and the whole event list per snapshot.
`_match_needs_pairs` scans only the agent's own cell and gives the same
pairs, and method 2 indexes events by turn. Method 2 costs less than the
oracle it replaces: about 3.5 s less per subset gate (about 60 s at
`--parallel 1`) and, extrapolated, about 100 s less for the 200 x 500 gate.
`run_needs_oracle_best_of` uses the same matcher (0.6-0.9 s and 2.3-2.7 s).

## Verification

Linux, Python 3.13.17, extension `cde64b3e...` (fresh from `48b72be`,
verified compiled `AgentSimulator`, `EcologySimulator`,
`PoliticsSimulator`):

| Check | Result |
| --- | --- |
| `pytest -m "not slow" -n 2` | 6,097 passed, 3 skipped, 526 subtests (main 6,080; 17 new) |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| No-Rust virtualenv without `chronicler_agents`, `pytest -n 2` (every test) | 5,878 passed, 222 skipped, 526 subtests (main 5,861 / 222) |
| `scripts/run_python_oracle_checks.py` | PASS in 72.1 s: 2,062 passed, 24 skipped (main 2,050 / 24); largest chunk 24.9 s of 110 s |
| Rust | unchanged (no `cargo test`) |

## Open

- The pooled effect is not specific to the need terms: about 60% of it
  survives zeroing them. A mechanism test needs needs that drop below
  their thresholds (only purpose and spiritual do) or a contrast that
  pairs below-threshold agents with matched ones above. Both are for the
  needs owners. (Done: needs bind since `needs-calibration.md`, and method
  3's binding pairs are that contrast, `needs-followups.md`.)
- Social is paired with more migration, but the Rust term makes a social
  deficit favor staying. Social pairs read -0.09 on the subsets and -0.40
  at 500 turns. The pairing and its direction are unchanged here.
- Spiritual, often below threshold (7%), has no pairing.
- Matching cannot see wealth, age, urban status or belief, which enter need
  restoration and behavior. The sidecar does not carry them.
- The 200 x 500 full gate with method 2.
