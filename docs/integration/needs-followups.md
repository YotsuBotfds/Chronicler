# Needs follow-ups (2026-10)

> **Method 3 is superseded as the gate's method by method 4** (2026-10,
> [`validation-integrity.md`](validation-integrity.md) §1): the same
> criteria, with outcomes counted on turns t+1 .. t+20 after a turn-t
> snapshot instead of t .. t+19, because the snapshot is written after turn
> t's agent actions. `run_needs_oracle(..., method_version=3)` re-scores
> method 3 exactly; the numbers below are method 3's.

Branch `fix/needs-followups` from `main` `f5425dc` (PR #37, movements on by
default), merged without rebase. Three changes, each a correction in every
agent mode with no switch:

1. **Needs oracle method 3.** Method 2 plus a binding component: pairs
   whose lower-need agent is below its behavioural threshold and whose
   partner is at or above it, with their own seed-clustered lower bound. It
   decides PASS in the full profile; in the subset profile it is reported
   but does not decide (`validation_io.py`, `validation_gate.py`).
2. **Newborn needs.** A newborn takes its birth parent's safety, material,
   social, spiritual and autonomy needs instead of 0.5 (`needs.rs`,
   `tick.rs`).
3. **Autonomy after a move.** The displacement turns after a move no longer
   block autonomy restoration (`needs.rs`).

`--agents off` output and the golden fixtures do not change
([Identity](#7-identity-and-golden-fixtures)). Every run is Linux, Python
3.13, `PYTHONHASHSEED=0`, hybrid, with each tree's extension built fresh
(`maturin build/develop --release --locked`) and its compiled
`AgentSimulator`, `EcologySimulator` and `PoliticsSimulator` verified. "Main"
is `2ef3097` (PR #38 merged; extension SHA-256 `cf109460...cd90e`); the head
extension is `f8e1017e...c2f410`, built from `d44cf4f` (the tree of
`228d2f0`; later commits change documents only). Earlier sets: main
`f5425dc` (`028c1fd1...fc52a`), the head's needs at `89f3d67` on it
(`2b70c9bb...57273`) and `b5d41af` (`0cb2948c...7cdb8d`). "Terms off" is a
build in which
`compute_need_utility_modifiers` returns zeros and the autonomy deficit no
longer speeds loyalty drift (the variant of `needs-oracle-power.md`).

**Result.** In the subset profile the needs verdict is method 2's: every
subset of main and the head passes with the terms on (6 of 6), and the
binding component is reported beside it. Applied with full-profile rules,
the binding component fails the terms-zeroed subsets 6 of 6 and passes
5 of 6 with the terms on (the head's 82-101 reads -0.028 at subset scale,
so it decides only where it has power); 59 of 60 shuffled batches fail. In
the full gate it passes: +0.192, lower bound +0.168. Newborns no longer mark age: the gap between ages 0-4 and 20-39
falls from 0.02-0.09 to under 0.01 for safety, material, spiritual and
autonomy. Autonomy binds in 1.4% of good-condition agent-turns (5.3%).
The hunger mid range still fails the needs subset 42-61 and is not shipped.
Full gate PASS strict, NO REGRESSION against the trade-crafts report
(needs method 3: 176 of 200 seeds, binding pairs +0.192 with lower bound
+0.168; migration 0.0642, rebellion 0.0360, latest satisfaction 0.633, 0
extinct).

## 1. Oracle method 3: binding pairs

### Why

Method 2 pools matched pairs whose needs differ by more than 0.1. With the
terms zeroed it still passed 3 of 3 subsets on `ea08126`
(`needs-calibration.md` §4). The terms act only below a need's threshold, and
on main `f5425dc` 72% of method 2's informative pairs have their lower
agent above it (1,629 of 2,272 on subsets 42, 62 and 82). There the terms push no one, and
the association comes from other channels: conditions that drive the same
behaviour by other routes, the 0.5 start of newborns, recent migrants and
wealth.

### Method

Method 3 keeps method 2's matching (cell, traits within 0.1, prior rebels
out of the autonomy pairing), pooling, verdict rules and outputs, and adds a
second, separately matched set:

- **Binding pair.** In a snapshot and pairing, an agent below the need's
  threshold (`NEEDS_BEHAVIOUR_THRESHOLDS`, mirrored from `agent.rs`: safety
  and material 0.30, social, autonomy and purpose 0.35) and a partner of the
  same cell at or above it, traits within 0.1, the partner's need higher by
  more than 0.05 (`NEEDS_BINDING_DIVERGENCE`). Greedy first match, each
  agent in at most one binding pair (`_match_binding_pairs`).
- **Why straddle.** Below the threshold any positive push opens the decision
  gate (a hazard of about 12.6% a turn, `needs-calibration.md` §2), so a
  pair with both agents below has both gates open. A pair across the
  threshold is the contrast the terms create: one agent pushed, the other
  not.
- **Why 0.05.** The threshold sets the contrast, so the gap is half of
  method 2's; it leaves out pairs whose needs sit at the threshold and swap
  sides within a few turns. The gap was chosen from 0, 0.05 and 0.10 on the
  subset runs below ([Choice of rule](#choice-of-the-binding-rule)).
- **PASS** requires method 2's two criteria and, in the full profile, a
  one-sided 95% lower bound of the binding pairs' pooled net concordance
  above zero (same seed-clustered estimator, Student t with S - 1 degrees
  of freedom). No seed fraction: a seed has about ten informative binding
  pairs. A subset has about 200 informative binding pairs and the bound sits
  within one or two standard errors of zero, which would bring back the
  noisy subset verdicts method 2 removed, so the subset profile reports the
  component (`binding.status`, `informational_failed_criteria`, the gate's
  informational `needs_binding` row) without letting it decide.
  `validation_gate.NEEDS_BINDING_REQUIRED_PROFILES` is `("full",)`.

Result fields: `method_version: 3`; `profile` (the profile it was scored
for), `binding_required`, `binding_required_profiles` and `pooled_status`
(method 2's criteria alone); `failed_criteria` lists `binding_lower_bound`
when the component decides, `informational_failed_criteria` when it does
not; `binding` holds its `status`, `required`, the thresholds, the gap,
pairs, informative, concordant and discordant pairs, the estimate, its
standard error and bound, and the per-pairing tallies; each per-seed record
adds `binding` (`[pairs, concordant, discordant]`) and `binding_by_pairing`.
Method 2's fields keep their names and meaning. `run_needs_oracle(...,
require_binding=False)` scores method 2 alone (`method_version: 2`).

**Profiles.** `scripts/m53b_run_validation.py` passes its profile to
`python -m chronicler.validate --profile`; without `--profile` (a manual
re-score) the component decides, as in the full gate. The gate
(`adjudicate_validation_report`) applies each profile's rule to any method 3
result whatever profile it was scored for: in the subset profile the needs
status is method 2's and a failing component appears as an informational
`needs_binding` row; in the full profile it is required. The comparator
reads required failures from the gate, so a subset's informational binding
failure is never a new failure or a regression, and a full-profile one is.

### Sensitivity

20 seeds x 200 turns per subset. Needs shuffled: each need column permuted
within every (snapshot, civ, region, occupation) cell of the loaded
sidecars, five permutations per batch. Method 2's net concordance (lower
bound) and seeds with C > D; the binding pairs' net concordance (lower
bound) and informative pairs; method 3's verdict.

Main is `2ef3097` (PR #38 merged; its own extension `cf109460...cd90e`),
the head is this branch (same tree as the gated `d44cf4f`):

The verdicts are the gate's (`adjudicate_validation_report`) on results
scored for each profile; "full rules" applies the full profile's rule to the
subset's pairs:

| Set | Method 2: net (lb), seeds | Binding: net (lb), informative | Subset profile | Full rules |
| --- | --- | --- | --- | --- |
| main, terms on, 42-61 | +0.163 (+0.081), 14 | +0.297 (+0.173), 222 | PASS | PASS |
| main, terms on, 62-81 | +0.152 (+0.090), 17 | +0.167 (+0.072), 252 | PASS | PASS |
| main, terms on, 82-101 | +0.153 (+0.064), 16 | +0.151 (+0.006), 259 | PASS | PASS |
| main, terms off, 42-61 | +0.096 (-0.000), 14 | +0.029 (-0.086), 237 | FAIL | **FAIL** |
| main, terms off, 62-81 | +0.132 (+0.075), 15 | +0.078 (-0.046), 219 | PASS | **FAIL** |
| main, terms off, 82-101 | +0.090 (+0.011), 12 | -0.072 (-0.183), 250 | PASS | **FAIL** |
| head, terms on, 42-61 | +0.145 (+0.057), 14 | +0.172 (+0.111), 215 | PASS | PASS |
| head, terms on, 62-81 | +0.232 (+0.105), 15 | +0.358 (+0.252), 212 | PASS | PASS |
| head, terms on, 82-101 | +0.193 (+0.119), 18 | +0.103 (-0.028), 185 | PASS (binding informational) | FAIL |
| head, terms off, 42-61 | +0.127 (+0.022), 13 | +0.078 (-0.056), 193 | PASS | **FAIL** |
| head, terms off, 62-81 | +0.141 (+0.061), 16 | +0.098 (-0.021), 184 | PASS | **FAIL** |
| head, terms off, 82-101 | +0.136 (+0.027), 14 | +0.030 (-0.074), 202 | PASS | **FAIL** |

Needs shuffled, 60 batches (the 12 sets x 5): full rules fail 59. The one
pass is main, terms on, 62-81, permutation 3 (method 2 +0.028, 13 seeds;
binding +0.009). Method 2 alone, the subset verdict, passes 2 of the 60 and
the binding component alone 3; only that batch passes both. Before the
trade-crafts merge (`f5425dc`, head `89f3d67`) full rules failed all 60
shuffles of the same design; method 2 alone passed 3 of them.

So the binding component separates the terms from their absence at subset
scale (terms on 5 of 6, zeroed 0 of 6) but is too noisy to decide a subset:
with the terms on it falls to -0.028 on the head's 82-101. The subset
verdict is method 2's, which passes every terms-on subset and also 5 of the
6 terms-zeroed ones. The full gate, where the component decides, passes:
the binding pairs read +0.192 (lower bound +0.168) over 5,060 informative
pairs ([Gates](#5-gates)).

### Choice of the binding rule

Binding lower bound on subsets 42 / 62 / 82; terms on should pass (> 0),
terms off fail. The rule was chosen on main `f5425dc` (before the
trade-crafts merge), the head's needs at `89f3d67` on it, and `b5d41af`
(main before PR #37, movements off):

| Rule | Arm | main `f5425dc` | head `89f3d67` | `b5d41af` | on pass / off fail |
| --- | --- | --- | --- | --- | --- |
| lower agent below, method 2's pairs | on | +0.179 / -0.007 / +0.023 | +0.187 / +0.034 / -0.003 | +0.199 / +0.160 / +0.132 | 7 of 9 |
| | off | -0.108 / -0.037 / -0.092 | +0.063 / +0.039 / -0.015 | -0.010 / +0.070 / -0.179 | 6 of 9 |
| straddle, gap 0.10 | on | +0.162 / +0.031 / +0.057 | +0.153 / +0.071 / -0.096 | +0.233 / +0.120 / +0.160 | 8 of 9 |
| | off | -0.139 / -0.094 / -0.105 | +0.025 / +0.011 / +0.003 | +0.026 / +0.083 / -0.150 | 4 of 9 |
| **straddle, gap 0.05** | on | +0.184 / +0.069 / +0.041 | +0.157 / +0.099 / +0.015 | +0.195 / +0.074 / +0.179 | **9 of 9** |
| | off | -0.126 / -0.105 / -0.113 | +0.021 / -0.015 / -0.051 | -0.004 / +0.069 / -0.145 | **7 of 9** |
| straddle, no gap | on | +0.147 / +0.027 / +0.022 | +0.086 / +0.103 / -0.025 | +0.161 / +0.041 / +0.123 | 8 of 9 |
| | off | -0.139 / -0.052 / -0.068 | -0.032 / -0.010 / -0.012 | -0.021 / +0.073 / -0.119 | 8 of 9 |

Also tried and dropped: weighting a pair by its deficit difference (the
gate makes the push a step, not proportional), each pairing weighted
equally, a 5-turn outcome window, the binding pairs' concordance minus the
above-threshold pairs' (too little power with terms on), and leaving out
agents that migrated in the 10 turns before the snapshot (two thirds of the
informative pairs go).

The straddle rule at 0.05 is the only one that passes every terms-on set; it
fails 7 of 9 terms-off sets. On the merged main and head, run after the
choice:

| Rule | main on | main off | head on | head off | on pass / off fail |
| --- | --- | --- | --- | --- | --- |
| lower agent below | +0.128 / +0.065 / -0.008 | -0.103 / -0.047 / -0.143 | +0.151 / +0.208 / +0.068 | -0.079 / +0.035 / -0.065 | 5 of 6 / 5 of 6 |
| straddle, gap 0.10 | +0.089 / +0.087 / -0.004 | -0.078 / -0.082 / -0.167 | +0.148 / +0.216 / +0.020 | -0.081 / -0.007 / -0.084 | 5 of 6 / 6 of 6 |
| **straddle, gap 0.05** | +0.173 / +0.073 / +0.006 | -0.086 / -0.046 / -0.183 | +0.111 / +0.252 / -0.028 | -0.056 / -0.021 / -0.074 | **5 of 6 / 6 of 6** |
| straddle, no gap | +0.135 / +0.050 / +0.031 | -0.092 / +0.005 / -0.178 | +0.066 / +0.169 / +0.025 | -0.062 / -0.029 / -0.091 | 6 of 6 / 5 of 6 |

Over all four code versions the 0.05 and no-gap rules tie (14 of 15
terms-on sets pass, 13 of 15 terms-off sets fail). A subset has about 200
informative binding pairs, and the bound sits within one or two standard
errors of zero in several sets, so a verdict there turns on a few pairs.
The full gate has about 25 times as many ([Gates](#5-gates)).

### Re-scored batches

The kept needs and event sidecars, re-scored (`run_needs_oracle`):

| Set (code) | Method 2: net (lb), seeds | Binding: net (lb), informative | Method 3 |
| --- | --- | --- | --- |
| main 42-61 (`b5d41af`) | +0.228 (+0.170), 18 | +0.284 (+0.195), 268 | PASS |
| main 62-81 (`b5d41af`) | +0.155 (+0.097), 14 | +0.167 (+0.074), 240 | PASS |
| main 82-101 (`b5d41af`) | +0.234 (+0.160), 17 | +0.252 (+0.179), 206 | PASS |
| terms off 42-61 (`b5d41af`) | +0.123 (+0.047), 14 | +0.062 (-0.004), 241 | FAIL |
| terms off 62-81 (`b5d41af`) | +0.184 (+0.096), 15 | +0.189 (+0.069), 244 | PASS |
| terms off 82-101 (`b5d41af`) | +0.155 (+0.075), 15 | -0.025 (-0.145), 240 | FAIL |
| main 42-61 (`48b72be`, before calibration) | +0.179 (+0.101), 15 | +0.208 (+0.065), 96 | PASS |
| main 62-81 (`48b72be`) | +0.199 (+0.098), 15 | +0.333 (+0.181), 90 | PASS |
| main 82-101 (`48b72be`) | +0.330 (+0.245), 18 | +0.258 (-0.091), 62 | FAIL |
| terms off 42-61 / 62-81 / 82-101 (`48b72be`) | FAIL / PASS / PASS | lb -0.194 / -0.300 / -0.243 | FAIL x 3 |
| `--agent-movements` 42-61 (`48b72be`) | +0.138 (+0.049), 17 | +0.216 (+0.092), 74 | PASS |
| `--no-cities` 62-81 (`48b72be`) | +0.184 (+0.099), 13 | +0.013 (-0.199), 79 | FAIL |
| 500-turn probe 142-161 (`48b72be`) | +0.166 (+0.121), 17 | +0.058 (-0.083), 223 | FAIL |

The `48b72be` batches are `needs-oracle-power.md`'s
(`needs-oracle/power/slim`), scored with today's thresholds. Before the
calibration few agents fell below a threshold except on purpose, so the
binding pairs are few and mostly purpose. `needs-cal`'s batches were deleted
after their reports; only its reports remain, which cannot be re-scored. The
full-gate baselines' batches (trade-crafts, movements) were deleted too, so
the full comparison is method 2 against method 3 with re-baselining
flagged.

## 2. Newborn needs

A newborn starts from its birth parent's safety, material, social,
spiritual and autonomy needs, read after the tick's needs update and before
its deaths (`needs::inherited_needs`, `needs::set_newborn_needs`; the parent
snapshot sits beside the parent positions of M55a). No random draw. Purpose
follows the agent's own skill at its work and still starts at 0.5. Founders
spawned at world creation keep 0.5.

Needs probe (`needs-calibration.md` §1's read-only observer; template
worlds 42-51 and procedural 7-11 at 64 regions and 16 civs, 200 turns,
1.2 M agent-turns per arm), main `2ef3097` against the head, mean need by
age band:

| Need | Arm | 0-4 | 5-9 | 10-19 | 20-39 | 40+ | 0-4 minus 20-39 | Below threshold, ages 0-9 / 20-39 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| safety | main | 0.521 | 0.558 | 0.584 | 0.592 | 0.603 | -0.071 | 0.8% / 1.9% |
| | head | 0.601 | 0.603 | 0.604 | 0.596 | 0.601 | **+0.006** | 2.0% / 2.0% |
| material | main | 0.520 | 0.554 | 0.581 | 0.609 | 0.641 | -0.088 | 5.1% / 6.2% |
| | head | 0.617 | 0.595 | 0.594 | 0.611 | 0.642 | **+0.006** | 7.2% / 6.5% |
| social | main | 0.495 | 0.476 | 0.450 | 0.474 | 0.538 | +0.021 | 1.5% / 7.9% |
| | head | 0.489 | 0.466 | 0.440 | 0.469 | 0.535 | +0.019 | 8.0% / 9.3% |
| spiritual | main | 0.497 | 0.489 | 0.477 | 0.457 | 0.429 | +0.040 | 0.0% / 6.2% |
| | head | 0.393 | 0.392 | 0.392 | 0.399 | 0.398 | **-0.007** | 25.2% / 22.7% |
| autonomy | main | 0.512 | 0.515 | 0.515 | 0.531 | 0.543 | -0.019 | 2.3% / 10.3% |
| | head | 0.622 | 0.619 | 0.619 | 0.623 | 0.636 | **-0.001** | 5.6% / 5.1% |
| purpose | main | 0.481 | 0.441 | 0.411 | 0.399 | 0.379 | +0.082 | 0.0% / 6.4% |
| | head | 0.481 | 0.441 | 0.411 | 0.398 | 0.379 | +0.082 | 0.0% / 6.7% |

The gap between the youngest and adults shrinks from 0.02-0.09 to under
0.01 for safety, material, spiritual and autonomy, and the young bind about
as often as adults. Social had no gap in its mean (a child's fixed point,
0.53, sits near the start), but its young now bind (1.5% -> 8.0%). Purpose
is unchanged: it follows skill, not conditions.

Spiritual now settles at its own fixed points: below its threshold in 23.9%
of agent-turns (8.1% on main), 38% for minority faiths without a temple
(17%), 16% for the majority faith without one (5%). Why: it decays 0.010 a
turn and is restored only by a temple (0.020 x deficit) and sharing the
majority faith (0.015 x deficit), fixed points 0.72 with both, 0.51 with a
temple alone, 0.34 with the faith alone and 0 with neither; a newborn reset
to 0.5 needed about 20 turns to fall to the 0.30 threshold, so no agent
under 20 was below it on main, and an inherited need starts where the
parent's already is. Effect, measurable from the kept event sidecars of
subsets 42, 62 and 82 (main against head): migrations whose dominant driver
is the spiritual need rise from 0.7-1.0% to 1.9-3.4% of migrations (337,
468, 369 -> 1,525, 1,598, 981), part of the 1-7% rise in migrations;
conversion does not read the spiritual need, and the belief changes seen
between an agent's events move +13%, -5% and +12% (no consistent
direction). Sect recruitment by movements also reads it; its membership is
not in the kept sidecars. Spiritual's constants are M53's and uncalibrated
([Open](#9-open)).

Within a (civ, region, occupation) cell the needs now differ less: method
2's matched pairs fall from 4,927 to 2,055 on the three subsets (main
against head) and from 43,170 to 16,598 in the full gate.

## 3. Autonomy after a move

Every move is the agent's or its household's own decision; no code moves an
agent against its will. The five displacement turns after a move still bar
another move (`behavior.rs`), cost satisfaction (`DISPLACEMENT_PENALTY`) and
keep a recent emigrant out of chain migration's pull; they no longer block
autonomy restoration. No migration weight changed.

Probe as in §2, autonomy below its threshold (0.35):

| Condition | Main | Head |
| --- | ---: | ---: |
| good conditions (not persecuted, no fresh conquest by another civ, no martial law) | 5.31% | **1.38%** |
| good, settled / displaced (24% of good agent-turns) | 3.88% / 10.06% | 1.05% / 2.39% |
| self-ruled / foreign rule | 2.78% / 12.34% | 0.83% / 7.80% |
| bad conditions | 39.2% | 28.0% |
| own faith persecuted | 35.5% | 23.7% |

Good-condition binding falls from 5.3% to 1.4%, under the 3% target of
`needs-calibration.md` §2. The block also held movers down in bad
conditions, so bad-condition binding falls from 39% to 28%, still inside the
20-50% target. Rebellion follows: 0.0388 -> 0.0360 in the full gate.

## 4. Hunger magnitudes

The mid-range terms (famine deaths 1.00 -> 1.50 in Rust and the Python
mirror, famine births 0.45 -> 0.60; the dearth terms 0.10 and 0.15 are
already mid-range) were built on the head's needs before the trade-crafts
merge (`89f3d67` plus the edit) and run on the three subsets:

| Subset | Needs, method 2: net (lb), seeds | Binding net (lb) | Method 3 | Lowest final population (head) |
| --- | --- | --- | --- | ---: |
| 42-61 | +0.144 (+0.046), 13 | +0.122 (-0.026) | **FAIL** | 65 (80) |
| 62-81 | +0.183 (+0.077), 14 | +0.242 (+0.113) | PASS | 127 (124) |
| 82-101 | +0.247 (+0.159), 15 | +0.253 (+0.110) | PASS | 106 (125) |

A required subset fails, as it did under method 2 (`farmland-climate.md`
§6), so the shipped values stay: deaths 0.10 / 1.00, births 0.15 / 0.45. No
full gate was run with them; the variant was not re-run on the merged
world.

## 5. Gates

Guard rails: no extinct world, migration above 0.05 (strict), rebellion
0.02-0.08, latest satisfaction at most 0.65, needs strict PASS, era, cohort,
community, artifacts and arcs PASS, bundle guard 10.5 MB.

**Full gate** (200 seeds x 500 turns, `--parallel 3`, 3,437 s on a shared
machine), the head (tree of `d44cf4f`, extension `f8e1017e...c2f410`)
against the trade-crafts full report (PR #38's head `a9e3872`, the tree of
`main` `2ef3097`). Seed directories were deleted after the reports; the
needs and event sidecars were kept for re-scoring.

| | Main (trade-crafts report) | Head |
| --- | --- | --- |
| gate; compare | PASS strict | **PASS strict; NO REGRESSION** (needs method 2 -> 3, re-baselining flagged) |
| needs, all pairs: net (lb), seeds with C > D | +0.191 (+0.177), 190 of 200 | +0.222 (+0.204), 176 of 200 |
| needs, binding pairs: net (lb), informative | - | +0.192 (+0.168), 5,060 (159 seeds positive) |
| informative / matched pairs | 19,746 / 43,170 | 9,902 / 16,598 |
| C / D: autonomy, social, purpose, material, safety | 1395/379, 1725/1228, 504/429, 5997/4324, 2135/1630 | 241/117, 1606/1186, 520/470, 3571/1989, 113/89 |
| era (silent collapses), cohort, community | PASS (0), 200, 200 | PASS (0), 200, 200 |
| arcs (seeds with three types); artifacts (creation; loss) | 158; 1.68, 6.0% | 159; 1.66, 5.7% |
| migration per agent-turn | 0.0615 | 0.0642 |
| rebellion per agent-turn | 0.0388 | 0.0360 |
| satisfaction mean; latest | 0.616; 0.627 | 0.618; 0.633 |
| extinct worlds | 0 | 0 |
| final population min / median / max | 78 / 184.5 / 329 | 56 / 179 / 308 |

The in-run report was scored without a profile (binding required);
re-scored from the kept sidecars with `profile="full"` it is the same, PASS,
and the gate requires the component there.

The matched pairs fall from 43,170 to 16,598: with newborns at their
parents' needs and no displacement block, autonomy and safety barely vary
within a (civ, region, occupation) cell, so their pairings keep 358 and 202
informative pairs (from 1,774 and 3,765). The binding pairs by pairing
(C / D, net): autonomy 43/15 +0.48, social 448/339 +0.14, purpose 1036/839
+0.11, material 1458/825 +0.28, safety 30/27 +0.05.

**Subsets** (20 seeds x 200 turns, `--parallel 1`, one worker), head
against main `2ef3097` with its own extension. Main's in-run reports are
method 2; method 3 re-scores of its sidecars are in §1. In a subset only
community, needs and cohort are required:

| Seeds | Arm | Gate; compare | Needs (method) | Migration | Rebellion | Latest sat. | Extinct | Lowest population |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 42-61 | main | PASS | PASS (2) | 0.0657 | 0.0418 | 0.618 | 0 | 102 |
| 42-61 | head | **PASS; NO REGRESSION** | PASS (3) | 0.0686 | 0.0452 | 0.603 | 0 | 80 |
| 62-81 | main | PASS | PASS (2) | 0.0612 | 0.0266 | 0.622 | 0 | 116 |
| 62-81 | head | **PASS; NO REGRESSION** | PASS (3) | 0.0618 | 0.0184 | 0.635 | 0 | 144 |
| 82-101 | main | PASS | PASS (2) | 0.0656 | 0.0433 | 0.621 | 0 | 95 |
| 82-101 | head | FAIL (needs, binding bound) | FAIL (3) | 0.0669 | 0.0431 | 0.618 | 0 | 98 |

These in-run reports were scored before the subset profile made the binding
component informational; re-scored from the kept sidecars, the head's
needs verdict is PASS on all three in the subset profile (§1). 82-101 is not
a required gate. Informational: regression's civ-survival
check fails at 200 turns in every set but main 82-101, and the head's 62-81
reads rebellion 0.0184, under 0.02 (main 0.0266); both pass at 500 turns.
Artifacts read PARTIAL in every set but the head's 82-101.

## 6. Tick time

`scripts/agent_scale_benchmark.py`, seed 42, 20 warm-up and 8 measured
turns, two repeats, one job at a time, on a 4-core machine shared with
another agent's runs (means of the repeats):

| Alive (main / head) | Rust tick CPU, main | Head | Per agent | Rust tick wall, main / head |
| --- | ---: | ---: | ---: | --- |
| 22,440 / 23,651 | 245 ms | 278 ms | +8% | 171 / 178 ms |
| 55,571 / 54,125 | 1,230 ms | 1,290 ms | +8% | 803 / 733 ms |

The new per-tick work is one map of the birth parents' needs, built next to
the parent positions; the autonomy update loses a branch. The calibration
measured +6% and +10% on this machine for its own change
(`needs-calibration.md` §8); wall time here moved both ways.

## 7. Identity and golden fixtures

`--agents off`, 200 turns, main `2ef3097` and the head, each with its own
extension (`scripts/agent_movements_identity.py compare`): template seed 42,
9 files, and procedural seed 7 (64 regions, 16 civs), 21 files, 0
differences. The golden fixtures (`tests/test_performance_equivalence.py`)
pass unchanged; no `ORACLE_CHAIN` link was needed. The bundle guard world
writes 7.89 MB native and 8.61 MB no-Rust (guard 10.5 MB), as on main.

## 8. Verification

On the head with the subset profile rule (`acabc38`; extension
`f8e1017e...c2f410`, built fresh from `d44cf4f`, whose Rust is unchanged
since, and verified):

- `cargo test` (debuginfo off, on `d44cf4f`): 996 passed, 2 ignored.
- `pytest -m "not slow" -n 2`: 6,210 passed, 3 skipped, 526 subtests.
- `pytest -m slow -n 2`: 11 passed, 3 skipped.
- No-Rust suite (`chronicler_agents` absent, every test): 5,980 passed, 233
  skipped, 526 subtests.
- `scripts/run_python_oracle_checks.py`: PASS in 92.0 s, 2,153 passed, 33
  skipped; largest chunk `systems-2` 37.2 s of 110 s.

New and changed tests:

- `tests/test_validate.py`: method 3 on the material world (binding pairs
  equal the pairs when every low agent binds); a world whose association
  sits above the threshold and whose binding pairs are tied fails on
  `binding_lower_bound` while method 2 alone passes (`require_binding=False`
  reproduces method 2's fields); no binding pairs, no bound, FAIL;
  `_match_binding_pairs` (both below left out, at the threshold counts as
  above, the gap, traits); thresholds mirror `agent.rs` and
  `narrative._NEED_THRESHOLDS`. The method 2 test now expects
  `method_version` 3.
  Scored for the full profile the component decides; for the subset it is
  reported (`binding.status`, `informational_failed_criteria`) and the
  status is method 2's; both CLIs pass `--profile` to the needs oracle.
- `tests/test_validation_gate.py`: whatever profile a method 3 result was
  scored for, the subset gate passes it with an informational
  `needs_binding` row (text and markdown summaries) and the full gate fails
  it; a passing component and method 2 results keep their verdicts.
- `tests/test_validation_compare.py`: method 2 against method 3 is a method
  change, not a new failure, and re-baselining is flagged; method 3 against
  method 3 counts a new failure; a subset's informational binding failure
  is no regression, the same failure in the full profile is.
- `tests/test_m53b_run_validation.py`: the runner passes its profile to
  `chronicler.validate`.
- Rust: `needs::tests::test_autonomy_restores_after_a_move` and
  `tests/test_needs.rs::test_autonomy_restores_while_displaced` replace the
  two displacement-block tests; `tests/test_demographics_integration.rs::
  test_newborns_start_from_the_birth_parents_needs` checks every newborn of
  20 ticks against its parent (purpose 0.5).

`--parallel 1` in `batch.py` runs `cpu_count() - 1` workers (`parallel > 1`
is the only literal count). The subsets here set `PYTHON_CPU_COUNT=2` to run
one worker.

## 9. Open

- **Subset power.** A subset has 180-260 informative binding pairs and the
  bound sits within one or two standard errors of zero in several sets: the
  head's 82-101 fails it with the terms on (+0.103, bound -0.028), and one
  of 60 shuffles passes. So the component is informational in a subset, and
  a subset gate alone does not catch zeroed terms (method 2 passes 5 of 6
  terms-zeroed subsets); only the full gate requires the component.
- **The full gate and the zeroed terms.** With the terms zeroed the binding
  pairs read +0.03 to +0.10 on the head's subsets (material about +0.24,
  from wealth and household moves). At the full gate's precision (standard
  error 0.014) such a residual would pass the bound. A terms-off full gate
  was not run, so method 3 is shown to separate the terms from their
  absence at subset scale only.
- **What the binding pairs see.** On the head, pooled over the three
  subsets: social +0.25 on against -0.07 off, purpose +0.10 against -0.05,
  material +0.27 against +0.24 (its term barely shows), autonomy 6 and 4
  informative pairs. On main autonomy was the clearest pairing (+0.65 over
  63 pairs against +0.13 over 30); without the displacement block few
  agents in good conditions fall below its threshold, and those in bad
  conditions share their cell's condition.
- **Autonomy and safety pairings** keep 358 and 202 informative pairs in
  the full gate (1,774 and 3,765 on main): within a cell these needs no
  longer vary with age or a recent move.
- **Spiritual** binds 23.9% of agent-turns (8.1%), minority faiths without a
  temple 38%: the 0.5 start no longer refreshes it. Its decay and
  restoration are M53's; a calibration like `needs-calibration.md`'s is
  open. Full-gate migration rose 0.0615 -> 0.0642; how much of that is
  spiritual's push was not measured.
- **Purpose** keeps its age gradient (+0.08): newborns start at 0.5 and it
  follows skill.
- **Hunger magnitudes** stay at deaths 0.10 / 1.00, births 0.15 / 0.45: the
  mid range fails the needs subset 42-61 under method 3 too (§4).
- **Lowest final population** in the full gate 78 -> 56 (no world extinct).
- Rebellion on subset 62-81 reads 0.0184 at 200 turns (main 0.0266); 0.0360
  at 500 turns.
- `--parallel 1` runs `cpu_count() - 1` workers (§8).
