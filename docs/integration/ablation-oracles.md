# Ablation oracles (2026-10)

Branch `feat/ablation-oracles` from `main` `2106ef2` (PR #57), fast-forwarded
to `8a68658` (PR #58, grain reserves: default off, byte-identical output with
it off) before any commit. PR #57 (`oracle-followups.md`) left two oracles
that measure associations, not effects:

* the **cohort verdict cannot fail**: every synthetic world passed it, worlds
  without an effect and with the reversed one included (best of 18
  snapshots, either behaviour's direction, the larger of two effects);
* the **needs oracle (method 5/6) is confounded by age**: a world whose needs
  do nothing but rise with age passes it in 90% of batches, and an age match
  that removes the confound costs it its power.

The simulation is deterministic and its mechanisms are ours to switch, so
this branch measures the causal effects directly: each seed is run as it
always is and also forked, at fixed turns, with one decision term switched
off; the same agents are then followed in both arms.

**Gate rules.** The causal verdicts are computed and reported in every
gate whose arms ran, labelled "causal evidence (not yet required)"; the
gate is still decided by needs method 6's observational verdict and cohort
method 3, as on `main` (cohort method 3 labelled "non-discriminating:
passes synthetic null and reversed worlds"). The arms run by default in
the full profile only. `--require-causal-oracles`
(`validation_gate.CAUSAL_ORACLES_REQUIRED`, off) makes the causal verdicts
decide once `main` passes them (section 6). Under these rules the four
gate reports of section 3 re-score to template full PASS, procedural full
PASS, template subset PASS and procedural subset FAIL (needs, as on
`main`), each identical to `main`'s own verdict on the same batch
(section 4.1).

**Causal evidence** (this branch merged with `main` `7c44ed8`, fresh
release build; arms forked from the plain gate batch at fixed turns):

| Full gate | Needs method 7 ablation | Cohort method 4 ablation (kin roots) | Gate (causal reported) | Gate (causal required) |
| --- | --- | --- | --- | --- |
| template 200 x 500 | PASS: all five pairings, +12% to +47% (one-sided lower bounds 1.07-1.35) | **FAIL**: members migrate 1.2% less with the roots, 0.988 [0.984, 0.993]; minimum 15% | PASS | **FAIL** (cohort) |
| procedural 100 x 300 | **FAIL**: material -> migration +6.7% [-5.3%, +18.7%]; the other four pass, +16.5% to +46.8% | **FAIL**: 0.996 [0.989, 1.003] | PASS | **FAIL** (needs, cohort) |

* **Synthetic worlds**: neither causal verdict passes a world without the
  effect, with the age confound or with the effect reversed (0 of 1,000
  batches at every scale); at +20% (needs) and -20% (cohort) the
  full-scale power is 97-99% and 100% (section 2).
* **Real worlds**: the placebo arm sits at 1 in every pairing. The need
  terms have the effects the M49 spec asks for in every pairing but one:
  **in procedural worlds material shortage raises migration by 6.7%, below
  the +10% minimum and not distinguishable from no effect** (section 3.1).
  **The kin roots, the model's community anchoring, have about a twelfth
  of the effect the M53 spec asks for** (section 3.3). Both are open
  decisions (section 8), not fixed here: no threshold moved.
* **Old versions**: needs method 6 and cohort method 3 re-score every
  batch exactly as `main` does; the comparator reports the method changes
  as `rebaseline_required` (section 4).
* **Cost**: the two default arms take about 1.1-1.2 times the plain
  batch's time in the template full gate and 0.6 times in the procedural
  one (section 5).

## 1. Design

### 1.1 The switch

No switch existed: the earlier "need terms zeroed" builds and sets
(`needs-calibration.md` section 4, `needs-followups.md`,
`needs-oracle-power.md`) were source patches of `needs.rs` and
`behavior.rs`. This branch adds a runtime one, off by default
(`chronicler-agents/src/scale.rs`, `DecisionAblation` in `TickOptions`):

| Arm | What is switched off from the start turn | What stays |
| --- | --- | --- |
| `needs` | `compute_need_utility_modifiers` in the decision (rebel, migrate, switch and stay utilities; the migrate push of the budget's need terms) and the autonomy factor of loyalty drift | needs evolve as before; movement recruitment still reads them |
| `kin_roots` | the relationship part of a migrant's roots: `ROOTS_MARRIED` and `ROOTS_PER_HOME_BOND` x home bonds (`Mobility::drop_relationship_roots`) | the age part of roots; home bonds still decide whether chain migration pulls; the household wealth damper |
| `placebo` | nothing: the decision draws come from another stream (`DECISION_PLACEBO_STREAM_OFFSET`, 2600) | every term |

* It draws no number: the decision keeps its four Gumbel draws per agent
  whatever the utilities (`gumbel_argmax`), so up to the first changed
  decision the arms share their random numbers (common random numbers).
* `TickOptions.ablation` is persisted (`persist_struct!`; the checkpoint
  layout fingerprint changes, as it does for any new native field).
* `AgentSimulator.set_decision_ablation(names, start_turn)` and the getter
  `decision_ablation`; Python sends it only for `--decision-ablation NAME
  --ablation-start-turn T` (`chronicler.decision_ablation`), so a plain run
  makes exactly the native calls it made before. Both options are
  simulation arguments in the batch manifest.

### 1.2 Arms: forks from the plain run's checkpoints

Divergence is the problem a second, independent arm per seed would have:
from the first changed decision the two worlds drift apart (wars, famines and
uprisings happen in one of them), so who is in need at turn 300 differs
between arms, and comparing rates over whole runs compares different
populations: a need term that moves its agents out of the deficit faster
also changes who is counted as in deficit. This branch compares the same
agents instead:

* **Fork.** The gate's plain batch writes an exact checkpoint after each fork
  turn T (`--checkpoint-turns`, the world turn T + 1, holding tick T and its
  sidecars; `chronicler.run_checkpoint`). For each seed, fork turn and arm,
  `chronicler.ablation_arms` resumes it with the arm's term off from tick
  T + 1 and runs to turn T + W + 2 (the final tick's forced settlement
  detection falls after the window). The plain run is the other arm. A fork
  equals a run ablated from turn T + 1 from the start (native test), and
  the validator checks every fork's agent event stream against the plain
  run's, row for row, up to T.
* **Cohort at the fork.** Agents are chosen from the plain run's turn-T
  sidecars, which both arms share: below a need's behavioural threshold
  (needs), community members (`detect_communities`, cohort). No later state
  selects them.
* **Window.** W = 20 turns, ticks T+1 .. T+20, the observational oracles'
  window. The first tick differs only through the ablated term (common
  random numbers); later ticks also through its consequences and through
  chance as the worlds drift. Divergence adds noise, not bias: the cohort
  is fixed before the arms differ, and the seed-clustered bound counts the
  noise. Each result reports the events by window turn (the effect's
  profile), the agents in no deficit at the fork (`unexposed`: spillover
  and drift), and, when run, the placebo arm (the null with full drift).
* **Fork turns** (pre-registered): every multiple of 100 from 100 with
  T + W < the run's turns: template full 100, 200, 300, 400; procedural
  full 100, 200; subsets 100. One fork per seed leaves the safety pairing
  without cohort at turn 100 (no wars yet in template worlds); forks later
  in the run reach the wars.

The other designs: an arm per seed run whole and compared by aggregate rates
per seed doubles the gate and compares diverged populations (above); a
single fork per seed (`--decision-ablation` from turn 0 to T + W) re-runs T
turns per fork and exposes a quarter of the agents the four forks do; the
forks from checkpoints cost W + 2 turns each and reuse the plain run.

### 1.3 Estimates and criteria

Per pairing, per seed s (its forks summed): the cohort's events in the
plain arm P_s and in the ablated arm A_s. The effect is the rate ratio
RR = sum P_s / sum A_s (the same agents, so a ratio of rates); its
seed-clustered variance is the ratio estimator's,
S / (S - 1) x sum (P_s - RR A_s)^2 / (sum A_s)^2 over the S seeds whose cohort
had an event, with Student t on S - 1 degrees of freedom (one-sided bound;
two-sided 95% interval reported). The pre-registration
(`preregistration.md` with the run reports, outside the repository, written
before any arm ran; reproduced here)
fixed:

| Oracle | Cohort at T | Event | Direction | Minimum effect (source) | PASS |
| --- | --- | --- | --- | --- | --- |
| needs, autonomy | autonomy < 0.35 | rebellion | more with the term | +10% (M49 spec tier 2: "10-20% more likely than baseline") | lower bound of RR > 1 and RR >= 1.10 |
| needs, social | social < 0.35 | migration | more | +10% | as above |
| needs, purpose | purpose < 0.35 | occupation switch | more | +10% | as above |
| needs, material | material < 0.30 | migration | more | +10% | as above |
| needs, safety | safety < 0.30 | migration | more | +10% | as above |
| needs, spiritual (reported) | spiritual < 0.30 | migration | more | +10% | not deciding |
| cohort | community member | migration | fewer with the term | -15% (M53 spec oracle 4: "15-30% less migration") | upper bound of RR < 1 and RR <= 0.85 |

The needs component passes when all five required pairings pass. The
thresholds are the native ones (`agent.rs`; the test
`test_needs_pairings_mirror_the_observational_oracle` checks they are the
observational oracle's). Rebellion is reported for the cohort, not
deciding: no community term enters the rebel decision, so this switch
cannot test "collective action".

### 1.4 Versions

* **Needs method 7** (`NEEDS_ORACLE_METHOD_VERSION`): method 6's whole
  result is its observational component (its fields unchanged,
  `observational_status`, `observational_criterion`) plus `ablation` (and
  `placebo` when that arm ran). `required_components` names the deciding
  ones (`validation_gate.needs_components_required`, section 6);
  `run_needs_oracle(..., method_version=6)` re-scores method 6 exactly.
* **Cohort method 4** (`COHORT_ORACLE_METHOD_VERSION`): method 3's whole
  result as its observational component (`observational_status`,
  `observational_note`: "non-discriminating: passes synthetic null and
  reversed worlds") plus the kin-roots `ablation` (`NOT_RUN` without the
  arm) and `placebo`. `run_cohort_oracle(..., method_version=3)` re-scores
  method 3 exactly.
* Both ablation components carry `label`: "causal evidence (not yet
  required)", or "causal evidence (required)" with causal oracles required
  (section 6). `needs_method_7_result` and `cohort_method_4_result`
  (`chronicler.validation_io`) build the results from saved components.
* The comparator reports needs 6 -> 7 and cohort 3 -> 4 as method changes
  (`rebaseline_required`), never as new or resolved failures.

### 1.5 The gate

`scripts/m53b_run_validation.py --ablation-oracles` (on by default in the
full profile, opt-in in the subset, which cannot measure the safety
pairing; `--no-ablation-oracles` opts out, leaving both ablation components
`NOT_RUN`; `--ablation-arms` chooses arms, default `needs,kin_roots`;
`--require-causal-oracles` makes the ablations decide, section 6, and
needs the arms): the batch gets
`--checkpoint-turns`, the arms are forked into `ablation_<first seed>`
beside the batch (a used directory is refused before anything runs), and
`chronicler.validate --ablation-dir` checks `ablation_manifest.json` (the
plain batch manifest's SHA-256, seeds, the pre-registered fork turns and
window, every kept file's SHA-256, each fork's recorded ablation, and the
shared history) before the oracles read the forks. `run_manifest.json`
records the arms, forks, the seconds of each phase and
`causal_oracles_required`. The gate summary lists both ablation components
under "Causal evidence (not yet required)" with their effects, and the
cohort row reads "method 3 (observational), non-discriminating: passes
synthetic null and reversed worlds".

## 2. Synthetic worlds

`scripts/synth_ablation_oracles.py` (in the repository): 1,000 replicate
batches per world and scale, forked as the gate forks (template full: 200
seeds x 4 forks, about 170 agents a fork; procedural full: 100 x 2, about
550; subsets: 20 x 1). Per fork and cohort the share of forks with a cohort,
its size and the base hazard are the gate worlds' (measured on probes of
`main`: template seeds 42-61 x 122 and 42-49 x 422 turns, procedural 42-47 x
222; safety, for example, has a cohort at 7% of template forks and 28% of
procedural ones); each agent has a frailty (gamma, cv 1), each seed and fork
its own rate (log-normal 0.4 and 0.3). The plain arm's hazard is the
ablated arm's times 1 + effect for the cohort. The arms share each agent's
draw with probability exp(-(t-1)/5) at window turn t and get independent
world shocks per turn (log-normal, spread growing to 0.5, 1.0 for
rebellions, as the draws decorrelate: what drifts apart in one arm only).
The verdict reads only the per-seed tallies, scored by the oracles' own
`ablation_ratio` and `judge`; `--check-pipeline` rebuilds sidecars and arms
for a few batches and checks the components give the same tallies.

PASS rates (needs: the component, all five required pairings, then each
pairing; cohort: members' migration). Worlds: no effect; no effect with the
cohort older and the old moving less (the age confound that passes method 5
in 90% of batches); reversed (needs -20%, cohort +20%); a true effect below
the minimum (needs +5%, cohort -5%); at it (+10%, -15%); and above:

| Template full (200 x 4 forks) | Needs effect | Needs component | autonomy | social | purpose | material | safety | spiritual (reported) | Cohort effect | Cohort |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no effect | 0 | **0.000** | 0.000 | 0.000 | 0.000 | 0.000 | 0.005 | 0.000 | 0 | **0.000** |
| no effect, age confound | 0 | **0.000** | 0.000 | 0.000 | 0.000 | 0.000 | 0.008 | 0.000 | 0 | **0.000** |
| reversed | -0.20 | **0.000** | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | +0.20 | **0.000** |
| below the minimum | +0.05 | 0.000 | 0.007 | 0.016 | 0.000 | 0.000 | 0.094 | 0.000 | -0.05 | 0.000 |
| at the minimum | +0.10 | 0.008 | 0.176 | 0.460 | 0.403 | 0.428 | 0.464 | 0.446 | -0.15 | 0.485 |
| above | +0.15 | 0.683 | 0.750 | 0.989 | 1.000 | 0.999 | 0.912 | 1.000 | -0.20 | 1.000 |
| above | +0.20 | **0.989** | 0.994 | 1.000 | 1.000 | 1.000 | 0.995 | 1.000 | -0.25 | 1.000 |
| above | +0.30 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | -0.30 | 1.000 |

| Procedural full (100 x 2 forks) | Needs effect | Needs component | autonomy | social | purpose | material | safety | spiritual | Cohort effect | Cohort |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no effect | 0 | **0.000** | 0.000 | 0.000 | 0.000 | 0.000 | 0.018 | 0.000 | 0 | **0.000** |
| no effect, age confound | 0 | **0.000** | 0.001 | 0.000 | 0.000 | 0.000 | 0.033 | 0.000 | 0 | **0.000** |
| reversed | -0.20 | **0.000** | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | +0.20 | **0.000** |
| below the minimum | +0.05 | 0.000 | 0.012 | 0.000 | 0.000 | 0.006 | 0.129 | 0.001 | -0.05 | 0.000 |
| at the minimum | +0.10 | 0.008 | 0.217 | 0.412 | 0.498 | 0.423 | 0.460 | 0.398 | -0.15 | 0.488 |
| above | +0.15 | 0.597 | 0.739 | 0.998 | 0.996 | 0.987 | 0.829 | 0.999 | -0.20 | 1.000 |
| above | +0.20 | **0.966** | 0.984 | 1.000 | 1.000 | 1.000 | 0.982 | 1.000 | -0.25 | 1.000 |
| above | +0.30 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | -0.30 | 1.000 |

| Subsets (20 x 1 fork) | Needs effect | Template: needs component | autonomy | social | purpose | material | safety | Procedural: needs component | safety | Cohort effect | Template cohort | Procedural cohort |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no effect | 0 | 0.000 | 0.056 | 0.039 | 0.028 | 0.044 | 0.033 | 0.000 | 0.041 | 0 | **0.000** | **0.000** |
| no effect, age confound | 0 | 0.000 | 0.063 | 0.034 | 0.044 | 0.045 | 0.017 | 0.000 | 0.041 | 0 | **0.000** | **0.000** |
| reversed | -0.20 | 0.000 | 0.005 | 0.000 | 0.000 | 0.001 | 0.002 | 0.000 | 0.003 | +0.20 | **0.000** | **0.000** |
| below the minimum | +0.05 | 0.000 | 0.081 | 0.082 | 0.137 | 0.139 | 0.030 | 0.000 | 0.096 | -0.05 | 0.008 | 0.003 |
| at the minimum | +0.10 | 0.001 | 0.141 | 0.179 | 0.475 | 0.337 | 0.037 | 0.004 | 0.160 | -0.15 | 0.506 | 0.484 |
| above | +0.20 | 0.003 | 0.223 | 0.369 | 0.930 | 0.685 | 0.076 | 0.117 | 0.290 | -0.25 | 0.998 | 0.998 |
| above | +0.30 | 0.017 | 0.353 | 0.581 | 0.999 | 0.917 | 0.097 | 0.344 | 0.440 | -0.30 | 1.000 | 1.000 |

* **Both verdicts fail when they should.** Without an effect, with the age
  confound, and reversed, the needs component and the cohort verdict pass
  in no batch at any scale (0 of 1,000 each). The bounds are calibrated:
  in the no-effect worlds the one-sided bound clears no effect in
  3.5-6.3% of full-scale batches per pairing (nominal 5%) and the 95%
  intervals cover the true ratio in 93.3-95.6%; at subset scale, with few
  informative seeds, 3.9-8.0% and 91.3-95.1%. A single pairing passes a
  no-effect world in at most 3.3% of full-scale batches (safety, the
  sparsest) and 6.3% of subset batches; the minimum effect is what keeps
  a significant but small association from passing.
* **Power.** At full scale every needs pairing is detected at +20% (98-100%;
  the component 97-99%), and at +15% all but autonomy and safety; the
  component's power at +15% is 60-68% because all five must pass. At
  exactly the minimum each pairing passes about half the time, as it
  should. The cohort verdict detects -20% in every batch, at full and
  subset scale.
* **Subsets cannot carry the needs component**: one fork per seed leaves
  safety without informative seeds in most template subsets (its cohort
  exists at 7% of forks), and the component passes 2-34% of +30% worlds.
  This is why the subset profile keeps the observational verdict (section 6).
* **The model's exposure against the gates'**: the gates' cohorts per fork
  (section 3.1) are within 20% of the model's, or larger, for autonomy,
  social, purpose, spiritual and template material, but smaller for safety (a third of the
  model's in template worlds, 40% in procedural ones) and for procedural
  material (a fifth: 3.6 agents a fork, not 20; the probes were 6 seeds).
  Those pairings have less power than the tables show; their realized
  intervals (section 3.1) are what count.

For comparison, the observational verdicts on synthetic worlds
(`oracle-followups.md`): cohort methods 2 and 3 pass every world, no effect
and reversed included (100%); needs method 5 (method 6's verdict) passes a
no-effect world with the age confound in 90% of batches and terms-zeroed
gate subsets in 8 of 15 (`procedural-drift.md` section 1.5).

## 3. Gate worlds

This branch merged with `main` `7c44ed8` (PR #59), as `d6b63e5`; fresh
release extension (SHA-256 `6f5c5d6a...`); every gate into a fresh, empty
output root, with the arms `needs`, `kin_roots` and `placebo` (the placebo
for calibration; the gate's default is the first two). The plain batches
are `main`'s: with the switch unset and `--checkpoint-turns` writing only
the checkpoints (section 7), the full gates' comparisons with the mine-soil
reports of `7c44ed8` (the same seeds and turns) show every metric delta 0,
NO REGRESSION, and the two method changes (`rebaseline_required`).

These gates ran before the revision of section 6, with the causal verdicts
required (the subsets with their arms, now opt-in); section 4.1 re-scores
their reports under the revised rules.

| Gate | Seeds x turns | Forks per arm (fork turns) | Needs observational (method 6) | Needs ablation | Cohort observational (method 3) | Cohort ablation |
| --- | --- | --- | --- | --- | --- | --- |
| template full | 200 x 500 | 800 (100, 200, 300, 400) | PASS | PASS | PASS | **FAIL** |
| procedural full | 100 x 300 | 200 (100, 200) | PASS | **FAIL**: material | PASS | **FAIL** |
| template subset | 20 x 200 | 20 (100) | PASS | FAIL (not measurable) | PASS | **FAIL** |
| procedural subset | 20 x 200 | 20 (100) | FAIL, as on `main` | FAIL (not measurable) | PASS | **FAIL** |

### 3.1 Needs: what the need terms do

Rate ratio of the cohort's events with the terms over without them, 95%
interval (events with / without; agent-forks in the cohort; informative
seeds):

| Pairing | Template full | Procedural full | Template subset | Procedural subset |
| --- | ---: | ---: | ---: | ---: |
| autonomy < 0.35 -> rebellion | 1.469 [1.329, 1.609] (14,086 / 9,589; 5,500; 97) PASS | 1.468 [1.312, 1.624] (15,227 / 10,373; 6,786; 76) PASS | 1.373 [0.630, 2.115] (350 / 255; 133; 6) **FAIL** | 1.187 [0.945, 1.429] (1,392 / 1,173; 659; 10) **FAIL** |
| social < 0.35 -> migration | 1.121 [1.077, 1.164] (3,933 / 3,510; 3,086; 198) PASS | 1.165 [1.133, 1.196] (11,573 / 9,938; 8,303; 100) PASS | 1.124 [0.858, 1.389] (100 / 89; 87; 16) **FAIL** | 1.216 [1.149, 1.284] (1,238 / 1,018; 892; 20) PASS |
| purpose < 0.35 -> switch | 1.276 [1.248, 1.304] (31,448 / 24,641; 26,018; 200) PASS | 1.259 [1.215, 1.302] (12,148 / 9,651; 13,978; 100) PASS | 1.172 [1.004, 1.340] (756 / 645; 681; 20) PASS | 1.208 [1.099, 1.316] (1,366 / 1,131; 1,665; 20) PASS |
| material < 0.30 -> migration | 1.144 [1.110, 1.178] (16,624 / 14,531; 14,360; 189) PASS | 1.067 [0.947, 1.187] (1,001 / 938; 720; 63) **FAIL** | 0.965 [0.434, 1.497] (83 / 86; 74; 5) **FAIL** | 0.875 [0.689, 1.061] (98 / 112; 70; 10) **FAIL** |
| safety < 0.30 -> migration | 1.230 [1.035, 1.424] (514 / 418; 466; 22) PASS | 1.211 [1.004, 1.418] (293 / 242; 240; 22) PASS | n/a (cohort 0) **FAIL** | 0.548 [0.186, 0.911] (17 / 31; 24; 3) **FAIL** |
| spiritual < 0.30 -> migration (reported) | 1.197 [1.168, 1.226] (25,665 / 21,441; 21,747; 195) | 1.219 [1.194, 1.244] (62,062 / 50,900; 44,966; 100) | 1.234 [1.119, 1.349] (707 / 573; 601; 17) | 1.252 [1.166, 1.337] (6,393 / 5,107; 4,622; 20) |
| ablation component | **PASS** | **FAIL** | **FAIL** (informational) | **FAIL** (informational) |

The pre-merge build (`8a68658` with this branch, before PR #59) gave the
template full gate the same verdicts, every ratio within 0.03 of these.

* **Template full: every pairing passes.** The terms raise rebellion among
  agents short of autonomy by 47%, occupation switches among those short of
  purpose by 28%, and migration among those short of safety, material
  goods and company by 23%, 14% and 12%. Closest to the minimum is social
  (1.121, one-sided bound 1.084); the lowest bound is safety's (1.069, on
  22 informative seeds).
* **Procedural full: material fails, the other four pass.** Agents short
  of material goods migrate 6.7% more with the terms, 95% interval -5.3%
  to +18.7%, one-sided bound 0.967: neither criterion holds. The cohort is
  small (720 agent-forks, 3.6 a fork, 63 informative seeds; template full
  18 a fork) and moves a lot either way (1.3-1.4 migrations per agent in
  20 turns). The effect is +15% over the first five ticks (303 against 264
  moves) and +4% after; agents in no deficit migrate 3.8% [2.3%, 5.4%]
  more with the terms, so little of the material pairing's effect is
  specific to the shortage. This is the pre-registered test failing on
  `main`, not a threshold question: the same criterion passes every other
  required pairing in both full gates. Method 6's observational verdict
  passes the same batch (net +0.0892, 72 of 100 seeds), as it passes
  age-confounded nulls.
* **Subsets** (20 seeds, one fork) measure purpose, spiritual and, in
  procedural worlds, social, and leave the rest open: the template subset
  had no agent below the safety threshold at turn 100, the procedural
  subset 24 (3 informative seeds), and material 5-10 informative seeds.
  The procedural subset's safety estimate, 0.548 [0.186, 0.911] from 17
  against 31 moves on 3 seeds (2 degrees of freedom), and its material
  0.875 [0.689, 1.061] on 10 are reversed where the full gate measures
  1.211 and 1.067: a subset's few informative seeds make even its
  intervals unreliable (section 6: why subsets keep the observational
  verdict).
* **Agents in no deficit at the fork** respond too (template full,
  86,835 agent-forks): migration 1.027 [1.017, 1.037], rebellion 1.034
  [1.012, 1.055], switches 1.093 [1.076, 1.110]. Some fall below a
  threshold within the window, and the terms act on the world they share
  (vacated posts, departures). The pairing effects are 4-9 times these for
  migration, 14 times for rebellion and 3 times for switches: the effect
  is concentrated where the need is short, as the mechanism says.
* **Divergence.** The effect is there on the first ablated tick, when the
  arms differ only through the term (common random numbers), and persists
  as the worlds drift: template full, first tick / ticks 1-5 / ticks 6-20:
  autonomy 1.55 / 1.52 / 1.45, social 1.46 / 1.19 / 1.09, purpose 1.16 /
  1.24 / 1.30, material 1.30 / 1.21 / 1.12, safety 2.10 / 1.59 / 1.12,
  spiritual 1.32 / 1.25 / 1.18. Migration pairings fade (a migrant leaves
  the deficit and the region), switches build up. The 20-turn aggregate is
  the pre-registered statistic: it is the conservative one for migration.

### 3.2 Placebo: the null on real worlds

| Placebo arm | Template full | Procedural full | Template subset | Procedural subset |
| --- | ---: | ---: | ---: | ---: |
| autonomy -> rebellion | 1.002 [0.978, 1.027] | 0.998 [0.968, 1.028] | 1.061 [0.842, 1.279] | 0.955 [0.863, 1.047] |
| social -> migration | 0.976 [0.936, 1.015] | 0.999 [0.978, 1.020] | 0.943 [0.763, 1.124] | 0.947 [0.907, 0.988] |
| purpose -> switch | 0.993 [0.971, 1.015] | 0.995 [0.961, 1.030] | 1.065 [0.852, 1.278] | 0.902 [0.781, 1.022] |
| material -> migration | 1.003 [0.981, 1.026] | 0.971 [0.900, 1.041] | 0.912 [0.469, 1.355] | 1.065 [0.893, 1.238] |
| safety -> migration | 0.928 [0.787, 1.068] | 1.131 [0.896, 1.367] | n/a (cohort 0) | 1.133 [-1.559, 3.826] |
| spiritual -> migration | 1.009 [0.990, 1.028] | 1.003 [0.991, 1.014] | 1.020 [0.910, 1.130] | 0.980 [0.956, 1.002] |

The placebo arm changes only the decision's random stream: no pairing
passes in any gate, and at full scale the ratios sit at 1 (within 3% for
every pairing but safety, 0.93 and 1.13 with intervals across 1). Scored
on 10 disjoint groups of seeds (20 template seeds, the subset's size; 10
procedural), the one-sided bound cleared 1 in 2 of 57 and 1 of 58
measured group-pairings (2.6% together, nominal 5%), and one passed
(template safety, in a group with few informative seeds): the reason a
subset cannot decide on safety. The kin-roots placebo, community members'
migration: template full 0.997 [0.986, 1.007], procedural full 0.997
[0.988, 1.007].

### 3.3 Cohort: the kin roots anchor about 1%, not 15-30%

| Gate | Members' migration | Members' rebellion (reported) | Non-members' migration (reported) |
| --- | ---: | ---: | ---: |
| template full | 0.988 [0.984, 0.993] (135,462 / 137,058; 127,910; 200) | 1.004 [0.993, 1.015] | 0.980 [0.965, 0.995] |
| procedural full | 0.996 [0.989, 1.003] (114,355 / 114,836; 91,678; 100) | 1.011 [0.991, 1.031] | 0.995 [0.981, 1.009] |
| template subset | 0.974 [0.937, 1.012] (3,056 / 3,137; 3,159; 19) | 1.014 [0.957, 1.071] | 0.877 [0.663, 1.091] |
| procedural subset | 1.000 [0.978, 1.022] (11,764 / 11,768; 9,565; 20) | 1.055 [0.968, 1.143] | 1.017 [0.966, 1.068] |

**`main` fails the principled cohort test.** With the kin roots, community
members migrate 1.2% less over the 20 turns after a fork (template full;
the bound below 1, fewer in 118 seeds, more in 58), about a twelfth of
the M53 spec's minimum (15-30% less); in procedural worlds 0.4% less,
0.996 [0.989, 1.003], not distinguishable from none. In template worlds
the effect is already 1.3% on the first ablated tick (8,154 against 8,260
moves), so it is not diluted by divergence: the term is small. Why: a migrant's relationship roots are at
most 0.06 (`ROOTS_MARRIED` 0.02 plus `ROOTS_PER_HOME_BOND` 0.02 for each of
at most two units of home bonds), and roots only reduce the voluntary
pulls (frontier, wage, chain, urban, learning; `net_of_roots`); distress
moves and the need terms ignore them. Nor is the anchor a community's:
non-members, with home bonds and spouses of their own, are anchored as
much (template full 0.980). The observational method 3 passes the same
batches (section 4), as it passes every synthetic world, the reversed one
included: what it sees is an association of membership, not the effect of
the term that is meant to produce it.

The thresholds were not moved and the oracle was not changed to pass: the
kin-roots ablation fails on `main` in every gate. Until it is decided
(section 8) the gate reports it as causal evidence and decides the cohort
oracle by method 3, as `main` does; method 3's PASS is no evidence. The
options: (a) strengthen the anchoring mechanism until it does what the M53
spec says (a behavioural change with its own gates); (b) restate the
oracle's claim, for instance that the roots anchor at all (bound below 1
with no minimum effect), by a new pre-registration; or (c) keep the
ablation reported. The branch takes (c) for now and neither (a) nor (b).

## 4. Old versions on the same batches

Each gate batch was also scored by `main`'s validator (`7c44ed8`, needs
method 6, cohort method 3) and the two reports compared:

| Batch | Needs 6 (main) | Needs 7 | Cohort 3 (main) | Cohort 4 | Comparator |
| --- | --- | --- | --- | --- | --- |
| Template full | PASS (net +0.1648, bound +0.1433, 156 of 200; binding PASS) | PASS | PASS (200 of 200) | **FAIL** | NO REGRESSION, `rebaseline_required` |
| Procedural full | PASS (net +0.0892, bound +0.0646, 72 of 100; binding PASS) | **FAIL** | PASS (100 of 100) | **FAIL** | NO REGRESSION, `rebaseline_required` |
| Template subset | PASS (net +0.1964, bound +0.0817, 14 of 20; binding PASS) | PASS | PASS (20 of 20) | **FAIL** | NO REGRESSION, `rebaseline_required` |
| Procedural subset | FAIL (net +0.0464, bound -0.0207, 11 of 20; binding FAIL) | FAIL | PASS (20 of 20) | **FAIL** | NO REGRESSION, `rebaseline_required` |

* `run_needs_oracle(..., method_version=6)` and `run_cohort_oracle(...,
  method_version=3)` on this branch re-score each batch exactly as `main`
  does (equal results, every field); method 7's observational fields are
  method 6's; every other oracle's result is equal; the reports differ only
  in the new `ablation_arms` key.
* The comparator (`validation_compare`) reports needs 6 -> 7 and cohort
  3 -> 4 under "Oracle method changes" with `rebaseline_required`, never as
  new or resolved required failures; with `main`'s report as the baseline
  each gate is NO REGRESSION.
* The full gates' plain batches equal the mine-soil gates' (`7c44ed8`):
  needs 6 and cohort 3 on them reproduce those reports' figures.

### 4.1 The four reports under the revised rules

The batches are deleted; their reports are kept. Each was re-scored
without re-running anything: needs method 7 from `main`'s method 6 result on
that batch (equal to this branch's re-score, above) and the kept ablation
and placebo components (`needs_method_7_result`); cohort method 4 from
`main`'s method 3 result and the kept kin-roots component
(`cohort_method_4_result`); then the gate (`adjudicate_validation_report`,
strict regression for the full profile) with the causal verdicts reported
and required, and on `main`'s own report:

| Gate | Causal reported (default) | `main`'s report | Causal required |
| --- | --- | --- | --- |
| template full | **PASS** | PASS | FAIL: cohort |
| procedural full | **PASS** | PASS | FAIL: cohort, needs |
| template subset | **PASS** | PASS | FAIL: cohort |
| procedural subset | **FAIL**: needs (observational) | FAIL: needs | FAIL: cohort, needs |

The default verdicts equal `main`'s required failures in all four. A
template subset gate run afresh on the revised code with
`--ablation-oracles` (arms `needs,kin_roots`, fresh output root) confirms
it end to end: PASS, exit 0; its ablation components equal the earlier
subset's field for field, its cohort observational component equals
`main`'s method 3 result, both labelled and listed as causal evidence;
batch 108 s, 40 forks 60 s, validation 17 s.

## 5. Cost

Four cores shared with other agents' runs (the load varied between runs,
so compare phases within a row); three workers for the full gates, one and
two for the template and procedural subsets; wall seconds from the run
manifests.

| Gate | Plain batch | Arms (3) | Of which `needs` + `kin_roots` | Validation | Forks | Fork seconds (mean) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Template full | 1,499 | 2,557 | 1,709 | 467 | 2,400 | 3.07 |
| Procedural full | 856 | 802 | 535 | 430 | 600 | 3.80 |
| Template subset | 136 | 109 | 73 | 15 | 60 | 1.74 |
| Procedural subset | 229 | 140 | 92 | 46 | 60 | 4.43 |
| Template full, pre-merge build | 1,139 | 2,115 | 1,407 | 469 | 2,400 | 2.53 |

* A fork costs 2-4 s: a process start, the checkpoint's restore and 22
  turns with their outputs, about three times a batch turn per turn.
  Later forks cost more (template full: 2.4 s at turn 100, 3.8 s at 400:
  larger worlds). The three arms cost the same; the default two are two
  thirds of the arm time: 1.1-1.2 times the plain batch's in the template
  full gate, 0.6 times in the procedural one.
* With the default arms the template full gate takes about 50-61 minutes
  (batch, two arms and validation: 3,015 s pre-merge, 3,675 s official),
  the arms adding about 87% to the batch and validation; the procedural full
  gate about 30 minutes (1,821 s), the arms adding 42%. Subsets run no
  arms by default; with `--ablation-oracles` they take 1-2 minutes more.
* Not subsampled and not shortened: four forks per seed is what gives
  safety a cohort (7% of template forks have one; 22 of 200 template seeds
  were informative), and the synthetic power at +20% (97-99%) is for all
  200 x 4 (100 x 2) forks. Halving the seeds would halve the arm time and
  cost power where it is lowest.
* Disk: the plain batch keeps the checkpoints until the arms have forked
  them (template full 1.2 GB for 800; procedural full about 0.75 GB for 200);
  each fork keeps its agent events (zstd) and `fork.json` (template full:
  291 MB for three arms).
* Validation reads every fork: 467 s for the template full report.

## 6. What the gate requires

**Now (`CAUSAL_ORACLES_REQUIRED = False`, the default): the observational
components decide, as on `main`.** The needs oracle's status is method 6's
verdict (its binding component required in the full profile only, as
before); the cohort oracle's is method 3's, shown as "method 3
(observational), non-discriminating: passes synthetic null and reversed
worlds". Both ablation components are computed wherever their arms ran and
reported: in the report (`label`, `component_statuses`), in the gate
decision (`causal_evidence`, `causal_oracles_required`) and in the summary
under "Causal evidence (not yet required)"; a failing one is listed as
`needs_ablation` or `cohort_ablation` among the informational non-PASS
rows. Cohort method 3's PASS is no evidence: it passes every synthetic
world, reversed ones included; it decides only because the causal
replacement fails on `main` and the decision of section 8 is not taken.

**With causal oracles required** (`--require-causal-oracles` on the gate
runner, `chronicler.validate` or `chronicler.validation_gate`, or the
constant set to True; the runner refuses it without arms):

* **Needs, full profile: the ablation component decides.** It measures what
  the oracle claims (the need terms change what agents in need do), it
  passes no synthetic world without the effect, with the age confound or
  reversed (0 of 1,000 at both full scales) and detects +20% in 97-99% of
  batches (section 2); on the gate worlds its placebo arm sits at 1 in
  every pairing (section 3.2). The observational component (method 6's
  verdict) stays in the report and is listed as `needs_observational` when
  it fails, without deciding: it passes the age-confounded null in 90% of
  batches and 8 of 15 terms-zeroed subsets (`oracle-followups.md`,
  `procedural-drift.md` section 1.5).
* **Needs, subset profile: the observational component still decides**;
  the ablation is reported. One fork per seed leaves too few agents in
  danger: safety has a cohort at 7% of template forks, the merged template
  subset had none, and the component passes 2-34% of synthetic +30% worlds
  at subset scale. Requiring it would fail every subset whatever the code.
  This is also why the subset runs no arms unless asked.
* **Outside a profile** (`chronicler.validate` without `--profile`) both
  needs components decide.
* **Cohort, every profile: the kin-roots ablation decides.** It has power
  at both scales (every community has members at the fork: 99.8% at -25%
  in subsets, 100% at -20% at full scale, section 2); without the arm it
  is `NOT_RUN`, a required failure.
* On the four reports this mode fails every gate (section 4.1): it is for
  after the two decisions of section 8.

Nothing was tuned to the results: fork turns, window, cohorts, minimum
effects and criteria are the pre-registration's (written before any arm
ran), and no threshold changed after the real gates; the revision changes
which verdict decides, not how any verdict is computed. Tests cover both
modes (`tests/test_validation_ablation.py`, `tests/test_decision_ablation.py`).

## 7. Identity, resume and tests

Builds: fresh release extensions (`maturin develop --release --locked`,
`CARGO_TARGET_DIR` and the virtual environments outside the checkout):
`main` `7c44ed8` (extension SHA-256 `da65b716...`, the mine-soil
baselines' build) and this branch merged with it, `d6b63e5` (`6f5c5d6a...`);
the compiled submodule and its three simulator classes were checked before
any run.

* **Switch unset, byte-identical**: `scripts/turn_speed_identity.py`, the
  9-case matrix (hybrid seeds 42, 7 and 1234, off-mode 42 and 7, procedural
  48 regions hybrid and off, scaled 22k and 52k agents), `7c44ed8` against
  `d6b63e5`: 399 files compared, 0 differences.
* **`--checkpoint-turns` writes nothing else differently**: template seed
  42 and procedural seed 7 x 230 turns with checkpoints at 101 and 201
  against the same runs without: 258 files, 0 differences (merged build).
* **Exact resume with each ablation on** (`scripts/checkpoint_identity.py`,
  resumed at every turn, before and after the start turn): needs from turn 30
  (`hybrid_s42`, 59 resume points, 1,780 files), kin roots from 20 with
  scholarship on (`hybrid_s7_scholarship`, 59, 1,780), placebo from 10
  (`shadow_s42`, 39, 429): 0 differences; each straight run with
  checkpoints equals the plain one. A resume repeats the saved ablation; a
  different one is refused.
* **Gate forks**: each gate's validator checked every fork's agent events
  against the plain run's up to the fork turn (`history_identity` in the
  report); a fork from a checkpoint equals a run ablated from the start
  (native test).
* **Tests** (merged tree): `cargo test --locked` 1,061 passed, 2 ignored;
  not-slow 6,708 passed, 3 skipped; `python
  scripts/run_python_oracle_checks.py` PASS in 107.2 s (12 chunks, 2,709
  passed). New: `tests/test_decision_ablation.py`,
  `tests/test_decision_ablation_native.py`,
  `tests/test_validation_ablation.py` and the Rust `ablation_tests`,
  `scale.rs` and `migration_drivers.rs` tests (switch off equals no
  switch, each arm changes only its term, no draw consumed, persisted
  options, the observational pairings mirrored, re-scoring methods 6 and
  3, fork history check, manifest refusals, comparator method changes).
* **Tests of the revised gate rules** (Python only; the extension is
  unchanged, SHA-256 `6f5c5d6a...` rebuilt identically): both modes of
  needs method 7 and cohort method 4, the gate's decisions, labels,
  payload and summary with the causal verdicts reported and required, a
  report's recorded mode against the gate's flag, the runner's default arms
  (full only) and its causal flag. MERGED_TESTS

## 8. Open

Two decisions stand between the causal verdicts and
`--require-causal-oracles` (or `CAUSAL_ORACLES_REQUIRED = True`):

1. **Kin anchoring against the M53 claim** (section 3.3). The M53 spec
   says community members migrate 15-30% less; the model's anchoring term,
   the relationship part of roots, moves members' migration by 1.2%
   (template) and 0.4% (procedural), and non-members' as much. Either the
   anchoring is strengthened (a behavioural change with its own gates) or
   the claim is restated by a new pre-registration. Until then cohort
   method 3, non-discriminating, decides.
2. **Power of the procedural material pairing** (section 3.1). In the
   procedural full gate the need terms move the migration of agents short
   of material goods by +6.7% [-5.3%, +18.7%]: the interval holds both no
   effect and the +10% minimum. The cohort is small (720 agent-forks, 3.6
   a fork; the synthetic model assumed 20, section 2) and its agents move
   a lot either way. Before the needs ablation can decide procedural
   gates, either the exposure is raised (more forks or seeds for this
   pairing, measured for power on the real cohort sizes) or the material
   term's effect in procedural worlds is examined as a model question.

Also open:

* **Subsets keep the observational needs verdict**, with its weakness
  (section 6), and run no arms by default; only the full gate's needs
  ablation could be causal.
* **Collective action**: no community term enters the rebel decision, so
  there is nothing to ablate for it; the cohort's rebellion is reported.
* **Spiritual** stays reported, as in method 6; its ablation effect is
  +19-25% wherever it was measured.
* **Fork cost** is mostly process start, restore and output (2-4 s for 22
  turns); forking a seed's arms within one process would save part of it.
* **Provenance**: these runs' trees were `git archive` exports, so their
  batch and ablation manifests record the package digest and extension
  SHA-256 but no git revision; the revisions are the ones named here.
