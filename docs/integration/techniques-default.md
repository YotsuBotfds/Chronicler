# Techniques on by default

Branch `feat/techniques-default`, based on `integrate/wave-4` at `c5f4df4`
(PR #21: epidemiology, finance and diplomacy on by default since
[wave3-defaults.md](wave3-defaults.md); techniques and maritime merged
default off). This branch re-gates techniques on those defaults, looks into
the needs oracle that blocked them, runs the full gate and turns techniques
on for new worlds. No oracle, threshold or technique parameter changes.

Every run below is hybrid, `PYTHONHASHSEED=0`, `--parallel 3`, on Linux with
Python 3.13 and a native extension built fresh from the branch's Rust
(unchanged since `92b6122`), with its compiled `AgentSimulator`,
`EcologySimulator` and `PoliticsSimulator` verified. "Defaults" means the
`c5f4df4` defaults: epidemiology, finance and diplomacy on, techniques off
(after this branch, `--no-techniques`).

## 1. Subset gates on the current defaults

20 seeds x 200 turns per set, the defaults against `--techniques` on the
same seeds at `c5f4df4`, compared with `chronicler.validation_compare`. In
the subset only community, needs and cohort are required; the rest is
informational.

| Oracle | 42-61 defaults / on | 62-81 defaults / on | 82-101 defaults / on | 102-121 defaults / on |
| --- | --- | --- | --- | --- |
| gate | PASS / PASS | PASS / **FAIL** | PASS / PASS | PASS / PASS |
| comparator | - / NO REGRESSION | - / **REGRESSION** (new required failure: needs) | - / NO REGRESSION | - / NO REGRESSION |
| community (seeds) | 20 / 20 | 20 / 20 | 20 / 20 | 20 / 20 |
| needs (seeds with the expected sign, 12 required; median effect) | 17, 0.68 / 17, 1.00 | 12, 0.44 / **11**, 0.32 | 18, 0.84 / 18, 1.21 | 17, 0.61 / 18, 1.23 |
| cohort (seeds; median effect) | 20, 1.11 / 20, 1.25 | 20, 1.34 / 20, 1.36 | 20, 1.31 / 20, 1.09 | 20, 1.27 / 20, 1.22 |
| era (seeds with inflections; silent-collapse seeds) | 20; 0 / 20; 0 | 20; 0 / 20; 0 | 20; 0 / 20; 0 | 20; 0 / 20; 0 |
| arcs | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| artifacts (creation per civ per 100 turns; loss) | PASS 2.01, 3.1% / PARTIAL 2.13, 2.6% | PASS 1.98, 4.4% / PASS 2.29, 2.2% | PARTIAL 1.77, 1.8% / PASS 1.89, 5.3% | PARTIAL 1.98, 1.9% / PARTIAL 2.42, 1.8% |
| regression | FAIL / FAIL (`civ_survival`) | FAIL (migration, `civ_survival`) / PASS (calibrated floor) | PASS strict / PASS strict | FAIL / FAIL (`civ_survival`) |
| satisfaction mean; late-run | 0.583; 0.610 / 0.580; 0.597 | 0.598; 0.605 / 0.599; 0.604 | 0.595; 0.604 / 0.591; 0.584 | 0.584; 0.591 / 0.588; 0.595 |
| migration per agent-turn | 0.0586 / 0.0577 | 0.0483 / 0.0474 | 0.0556 / 0.0539 | 0.0565 / 0.0560 |
| rebellion per agent-turn | 0.0429 / 0.0428 | 0.0227 / 0.0222 | 0.0537 / 0.0532 | 0.0518 / 0.0547 |
| all founders surviving | 0.25 / 0.25 | 0.25 / 0.20 | 0.15 / 0.05 | 0.25 / 0.35 |
| extinct worlds | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

The defaults batch on seeds 42-61 reproduces the wave3 all-on subset batch:
every required oracle's result is identical (era and regression differ only
because that saved report predates the recalibrated oracles). The
informational `civ_survival` failures are the 20-seed reading of the founder
band (`wave3-defaults.md`, section 3).

With techniques on, one gate fails: the needs oracle on seeds 62-81, 11 of
20 seeds against 12 required, as on the old base. 0 of 160 worlds go
extinct.

## 2. The needs oracle on seeds 62-81

**What it measures.** M53 oracle 2 (`validation_io.run_needs_oracle`,
`compute_needs_diversity`; M53 spec section 6.2) asks whether agents alike
in everything but one need behave differently. At a needs snapshot it pairs
agents with the same civ affinity, region and occupation, boldness, ambition
and loyalty within 0.1, and the need more than 0.2 apart, then counts the
pairing's event over the next 20 turns for the low-need and the high-need
agent: autonomy with rebellion, social, material and safety with migration,
purpose with occupation switches. A seed has the expected sign when some
snapshot and pairing has pairs, more events among the low-need agents and
|d| > 0.10. PASS needs 60% of seeds (12 of 20) and a median |d| > 0.10.

**Calibration.** The 12-of-20 and d > 0.1 thresholds are the M53 spec's.
The first implementation (`e2a74a0`, 2026-03-21) read one snapshot near
turn 100 and the pairing with the most pairs; the canonical gate then had
6 of 20 subset seeds and 10 of 200 full seeds. The next day `aff1b18`
("capture passing canonical baseline", with a large agent-model retune)
made every snapshot from turn 0 eligible and ranked candidates by expected
sign first, and the full gate read 199 of 200. A seed now passes if any of
about 18 snapshots (200 turns) or 48 (500 turns), times five pairings, comes
out the right way. The same commit made a rebellion raise the rebel's
autonomy by 0.10 (`chronicler-agents/src/tick.rs`). Neither has changed
since.

**Re-measured on the current defaults**, seeds with the expected sign:

| Seeds | 42-61 | 62-81 | 82-101 | 102-121 | All 80 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Defaults | 17 | 12 | 18 | 17 | 64 |
| `--techniques` | 17 | **11** | 18 | 18 | 64 |

Seeds 62-81 sit on the threshold without techniques too (14 on the old
`92b6122` base). They are the low-rebellion set: 0.023 agent rebellions per
agent-turn against 0.043-0.055 in the other three, in both arms, so the
autonomy pairing that decides most seeds has few events to find.

**Seed by seed.** Over the 80 paired worlds, 7 seeds qualify only without
techniques (49, 68, 70, 78, 88, 112, 113) and 7 only with them (48, 69, 71,
86, 111, 116, 121); 57 qualify in both and 9 in neither. An exact McNemar
test gives p = 1.0. On the old base the 60 seeds split 5 and 5. A failing
seed, in either arm, reports autonomy with no rebellion as its "best"
pairing (all 8 failing seeds of 62-81 without techniques, all 9 with them):
when no candidate qualifies, the oracle reports the one with the most
pairs, and autonomy nearly always has the most. That signature is not
specific to techniques.

**The link itself.** Recomputing `compute_needs_diversity` for every
snapshot and pairing the oracle reads and pooling the matched pairs over
all 80 seeds, with no best-of selection:

| Pairing | Arm | Pairs | Events, low-need agents | Events, high-need agents | Low / high (95% seed bootstrap) |
| --- | --- | ---: | ---: | ---: | --- |
| autonomy -> rebellion | defaults | 1,785 | 2,341 | 2,671 | 0.88 (0.82-0.94) |
| autonomy -> rebellion | techniques | 1,732 | 2,312 | 2,315 | 1.00 (0.91-1.09) |
| material -> migration | defaults | 254 | 212 | 179 | 1.18 (0.99-1.41) |
| material -> migration | techniques | 287 | 252 | 207 | 1.22 (1.03-1.44) |

Social, purpose and safety pairs are almost never found (0-3 per batch).
Techniques do not weaken either link; both read a little stronger with
techniques on. Techniques change no need, threshold or utility term: they
reach agents through the derived era and focus and through the economy, and
agent rebellion and migration per agent-turn move by at most 6% in either
direction (section 1).

**Why the autonomy link reads backwards.** A rebellion raises the rebel's
autonomy by 0.10, so a high autonomy reading often marks a recent rebel, and
recent rebels rebel again. Splitting the autonomy pairs by rebellions in the
20 turns before the snapshot (all 80 seeds): in 41% of pairs only the
high-autonomy agent had rebelled (740 of 1,785 without techniques, 712 of
1,732 with them), in under 1% only the low one. In those pairs the high
agent rebels 2.3 times in the next 20 turns against the low agent's 1.8
(2.1 against 1.8 with techniques). Where neither had rebelled (38% of
pairs) the expected direction shows weakly: 0.20 against 0.19 rebellions
per agent without techniques, 0.26 against 0.20 with them. The oracle
passes on the windows where chance runs the right way. That is a property
of the oracle and the agent model since `aff1b18`, the same in both arms;
it is an open item for the needs owners (section 6), not changed here.

**Decision.** No technique mechanism suppresses the need-behaviour link, and
the failing set is a one-seed miss on a set whose base sits on the
threshold: binomial noise. The oracle is not changed and no threshold
moves. The full gate, where the needs oracle is also required and reads 48
snapshots per world, decides.

## 3. The full gate

Full profile (seeds 42-241, 500 turns) with `--techniques` on the defaults
at `c5f4df4`, compared with the all-on full report of `wave3-defaults.md`
section 5 (seeds 42-241, `--epidemiology --finance --diplomacy` at
`a595a38`). No oracle code changed, so that report is the baseline as it
stands. The defaults were also re-run as a full gate at the flip commit
(`594aedb`) with `--no-techniques`: that report is identical to the all-on
report apart from its batch path, so the baseline is exactly the current
defaults, and that run supplies the defaults' eras and headline numbers
below.

| | Defaults (techniques off) | Techniques on |
| --- | ---: | ---: |
| Gate | PASS (strict) | PASS (strict) |
| `validation_compare` vs the defaults' full report | - | NO REGRESSION |
| Needs: seeds with the expected sign (120 required); median effect | 191; 1.00 | 188; 1.00 |
| Satisfaction, run mean | 0.596 | 0.594 |
| Late-run satisfaction (60-turn window) | 0.610 | 0.604 |
| Migration per agent-turn (floor 0.05) | 0.0524 | 0.0512 |
| Rebellion per agent-turn | 0.0482 | 0.0503 |
| All founders surviving (limit 0.20) | 0.155 | 0.110 |
| Extinct worlds | 0 | 0 |
| Final population, min / median / max | 41 / 168 / 302 | 36 / 170 / 349 |
| Era: silent-collapse seeds | 0 | 0 |
| Era: collapses (marked by the civ's own signals / by crises only) | 4,697 (2,660 / 2,037) | 4,678 (2,750 / 1,928) |
| Artifact creation per civ per 100 turns | 1.07 | 1.25 |
| Artifact loss | 5.7% | 5.1% |
| Cohort: seeds; median effect | 200; 1.71 | 200; 1.67 |
| Arcs: families; seeds with three types | 6; 164 | 6; 166 |

On the full profile the needs oracle loses 10 seeds and gains 7 (McNemar
p = 0.63), and pooled over every snapshot the low-against-high event ratios
are 1.02 without and 1.04 with techniques for autonomy and rebellion, 1.20
and 1.34 for material need and migration.

Headline per run (same 200 worlds, 500 turns; the defaults column equals
`wave3-defaults.md` section 5's all-on column):

| Per run | Defaults | Techniques on |
| --- | ---: | ---: |
| Population | 166 | 171 |
| Polities alive | 2.77 | 2.77 |
| Wars | 5.36 | 5.56 |
| Famine events | 328 | 318 |
| Epidemic deaths | 278 | 270 |
| State defaults | 1.78 | 1.58 |
| Treaties signed | 22.2 | 20.9 |
| PSI crises | 2.06 | 2.40 |
| Revolts | 3.06 | 2.89 |
| Trade actions | 48 | 367 |
| Expansions | 53.0 | 20.2 |
| Great persons born | 16.1 | 22.5 |
| Artifacts created | 21.4 | 25.0 |

Bronze opens the TRADE action, so trade actions rise about eightfold and
expansions fall by three fifths, as on the subsets in
[techniques.md](techniques.md#on-and-off-per-run); great persons (scientists
on reaching a new era) and the artifacts that follow them rise.

## 4. Eras and technology, before and after

Eras of living civs (civs holding land) over the 200 full-gate worlds.
Defaults: the old era advance and the M18 random regression. Techniques on:
eras derived from practised techniques.

| Turn | Defaults | Techniques on |
| --- | --- | --- |
| 100 | tribal 624, bronze 41, iron 7, classical 3, medieval 1, renaissance 1 (8% Bronze or later) | tribal 144, bronze 365, iron 153 (78% Bronze or later) |
| 200 | tribal 553, bronze 43, iron 19, classical 5, medieval 2, renaissance 1 (11%) | tribal 108, bronze 191, iron 296, classical 20 (82%) |
| 500 | tribal 494, bronze 32, iron 17, classical 9, medieval 2 (11%) | tribal 91, bronze 96, iron 203, classical 145, medieval 19 (84%) |

| Per run, 500 turns | Defaults | Techniques on |
| --- | ---: | ---: |
| Tech advances | 5.41 | 7.13 |
| Tech regressions | 4.89 | 1.51 |
| Techniques known per civ, t100 / t200 / t500 | - | 5.7 / 7.7 / 9.6 |
| Inventions | - | 13.4 |
| Gained via trade / people / soldiers / conquest | - | 6.4 / 14.9 / 0.1 / 0.2 |
| Lost: practice decayed / land lost | - | 3.2 / 0.9 |

On the defaults the eras stagnate: nine civs in ten stay tribal for 500
turns, and the few advances are nearly matched by M18 regressions (5.4
against 4.9 per run). With techniques four in five civs are past tribal by
turn 100; by turn 500 most are Iron or Classical and 19 are Medieval, and
regressions fall to 1.5 per run, each citing its causes
(the techniques lost, and the famine, disease, collapse or lost capital
behind them).

On the four subset sets (80 worlds, 200 turns) the same picture: at turn
200, 218 of 244 living civs are tribal on the defaults and 52 of 243 with
techniques; tech advances 1.9 against 5.0 per run, regressions 1.4 against
0.75.

## 5. The flip and verification

The condition (full gate PASS strict, 0 extinct worlds, no comparator
regression) is met, so techniques default on for new worlds (`594aedb`):
`techniques.DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, with the CLI help, the
module and live-server comments and `techniques.md` updated, and
`test_new_worlds_default_on_and_resume_keeps_saved_setting` checking that a
fresh world has techniques, that `--no-techniques` leaves them out, and that
an off world stays off on resume. Resumed, forked and caller-supplied worlds
keep their saved setting. `scripts/benchmark_headless.run` pins
`techniques=False` next to the other frozen-workload pins, so the golden
fixtures in `tests/fixtures/performance/` replay the same worlds: without
the pin `test_corrected_baseline_all_turns_and_rng` fails for its single,
standard and wide workloads; with it all 65 tests pass and no fixture
changes.

The slow `TestBundleSize` check (seed 1, 500 turns, 10 regions) grows from
33.70 to 36.56 MiB with techniques on: 1.12 MiB of per-turn technique
history (0.95 of it the viewer's per-region practice) and the extra events
and state of a world whose eras move. Its limit, raised before as each
system added per-turn data (5, 12, 20, 25, 35 MiB), is now 40 (`ae832c6`).

Verification on the final code (Linux, Python 3.13):

| Check | Result |
| --- | --- |
| `pytest -m "not slow" -n 2`, native extension built fresh and verified | 5,707 passed, 3 skipped, 526 subtests (the recorded `integrate/wave-4` base count is 5,707 passed, 3 skipped; the default test was rewritten in place) |
| No-Rust lane (fresh virtualenv without `chronicler_agents`, `pytest -n 2`, slow tests included) | 5,510 passed, 200 skipped. Before the bundle limit change, `TestBundleSize` failed at 36.56 MiB |
| `scripts/run_python_oracle_checks.py` (PR #19's one-line guard fix applied locally, not committed) | PASS: 1,721 passed, 7 skipped, 2 deselected; guard PASS, no native module loaded, no blocked I/O |
| Golden fixtures (`tests/fixtures/performance/`) | unchanged; `test_performance_equivalence` 65 passed |
| Rust | unchanged by this branch, so no `cargo test` |

The not-slow run was on `594aedb`; `ae832c6` changes only the slow-marked
size check.

## 6. Open items

* **Migration margin.** Migration per agent-turn is 0.0512 with techniques
  on against the strict 0.05 floor (0.0524 off). It is the tightest required
  margin of the full gate: a further 2% fall makes it a calibrated-floor
  pass, which the comparator reports as a regression against a strict
  baseline.
* **Founders all surviving** falls from 0.155 to 0.110 (the limit 0.20 is a
  ceiling): somewhat more state deaths over 500 turns, inside the band.
* **The needs oracle's autonomy pairing** is confounded by rebellion's own
  +0.10 autonomy (section 2): its pooled low-against-high ratio is 0.88 on
  the 200-turn defaults batches and 1.02 at 500 turns, and it passes through
  best-of selection. Fixing it (for example by leaving out agents who
  rebelled just before the snapshot) is a separate calibration with its own
  effect on the base, for the needs and agent-model owners.
* **Subset needs on seeds 62-81** stays one seed short with techniques on.
  It is noise on a low-rebellion seed set, but the subset comparator will
  keep reporting it until the oracle changes.
* **Still tribal.** About one living civ in six (91 of 554) is tribal at
  turn 500 with techniques on. Which polities stay tribal, and why, was not
  broken down here.
* Carried over from [techniques.md](techniques.md#open-items): scientists
  and treatises rise with moving eras (artifact creation 1.07 to 1.25 per
  civ per 100 turns, inside the 1-3 band), TRADE actions multiply once civs
  reach Bronze, Rust technique packets are cut.
