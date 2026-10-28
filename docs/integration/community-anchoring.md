# Community anchoring and the procedural needs-ablation design (2026-10)

Branch `feat/community-anchoring` from `main` `b1c9274` (PR #61, ablation
oracles). PR #61 left two open decisions (`ablation-oracles.md` section 8):
the kin roots anchor community members' migration by about 1%, where the
M53 spec claims 15-30%; and the procedural material pairing of the needs
ablation measured +6.7% [-5.3%, +18.7%] on a cohort of 3.6 agents a fork.
This branch adds a spec-faithful community anchoring term behind a switch
that is off by default (A), redesigns the forks of procedural worlds for
power and reruns the needs ablation (B).

RESULTS_SUMMARY

## 1. What M53 means by anchoring

The M53 spec (`docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`,
section 6.2):

* **Oracle 1** defines a community: "groups of 5+ agents with mutual bonds
  and shared memories", found by label propagation over "friend +
  co-religionist + kin edges weighted by sentiment", kept when at least 80%
  of members share a memory `(event_type, turn, valence_sign)`, and with a
  **kin-only exclusion**: "Pure dynastic/family clumps do not count".
  Acceptance: 3-15 communities a seed, median size 5-12, none above 5% of
  its region.
* **Oracle 4** compares the members of those communities with matched
  non-members (same civ, region, occupation, similar satisfaction):
  "community members show 15-30% less migration (social anchoring) OR
  20-40% higher rebellion co-participation (collective action)". Its
  failure investigation: "bond effects on utility too weak -> check
  relationship utility modifiers"; "memory -> utility pipeline
  disconnected".

So anchoring is meant to be **community-specific**: membership of a group
held together by mutual bonds that include non-kin ties and by shared
experience, acting on migration through the decision utility. It is not
generic kin: the spec excludes family clumps from what counts as a
community, and the household already moves together (`household.rs`).
The model's only anchor so far is the relationship part of a migrant's
roots (`ROOTS_MARRIED` 0.02 plus 0.02 per unit of home bonds, at most 0.06),
which acts only on the voluntary pulls and anchors non-members as much as
members (`ablation-oracles.md` section 3.3): kin and household roots, not
community.

**What the oracle measures instead.** Two defects of the community
detection make the cohort oracle's "members" nearly everyone (probes of
`main`, template seeds 42-61 x 222 turns and procedural 32 x 10 seeds
42-51, turns 100 and 200):

| | template | procedural |
| --- | ---: | ---: |
| communities per snapshot (median) | 2 | 10 |
| community size: median / p90 / max | 15 / 147 / 258 | 11 / 137 / 350 |
| communities above 5% of their main region | 100% | 99% |
| regions a community spans (median) | 3 | 4 |
| members' share of living agents (median) | 96% | 89% |

* `detect_communities` propagates labels over **every** edge, rivals and
  grudges included, unweighted, across regions (the spec names friend,
  co-religionist and kin edges weighted by sentiment).
* Its kin-only exclusion tests `bond_type != 0`, from a docstring that
  numbers kin 0; in the native enum 0 is **mentor** and kin is 5
  (`relationships.rs`), so a pure kin clump passes.
* `run_community_oracle` checks only that a seed has a community of 5+; the
  spec's size and count criteria are not checked.

Detected as oracle 1's text specifies (friend, co-religionist and kin edges,
positive, weighted by sentiment, within a region; the kin code corrected),
communities look like the spec's: 7 per snapshot in template worlds and 14
in procedural ones, median size 6 and 5, p90 9 and 8, holding 23% and 15%
of agents (`validation_ablation.detect_spec_communities`, informational).
Members of those communities migrate exactly as much as everyone else on
`main` (1.060 against 1.062 moves per agent over 20 turns, template; 1.226
against 1.216, procedural).

## 2. Design

### 2.1 The term (`chronicler-agents/src/community.rs`)

* **Community ties** of an agent: positive-valence bonds (mentor, exile
  bond, co-religionist, kin, friend; marriage excepted, since the spouse
  moves with the household) of sentiment at least 20 (the migration
  drivers' `BOND_MIN_SENTIMENT`) to a living agent of its own region with
  whom it shares a memory: the same event type with both memory turns in
  one 5-turn bucket, the key oracle 1 compares. A merchant away on a trade
  trip still counts.
* **Kin-only exclusion**: the ties count only when one is non-kin; an agent
  held by kin alone keeps its kin roots and household as before.
* **Anchor** = `COMMUNITY_ANCHOR` x counted ties / 4, the ties counted up
  to `COMMUNITY_FULL_TIES` 4 (with the agent, a group of five, oracle 1's
  smallest community).
* **Where it acts** (`behavior.rs`, `evaluate_region_decisions_with`): the
  anchor is subtracted from the migrate utility of an agent whose migrate
  gate is open (a positive utility toward a better region), after the
  household damper. It lowers the odds of moving against every other
  action by `exp(-anchor / T)` at the decision temperature T = 0.3 and
  never closes the gate: a reason to move stays one. Rebellion, occupation
  switches and staying are untouched (the anchor is not a stay bonus, which
  would also damp rebellion, the spec's other community effect).
* It draws no number: the decision keeps its four Gumbel draws per agent,
  so an anchored and an unanchored run share their random numbers up to the
  first changed decision. A Rust test checks that the anchor only ever
  turns a move into another choice, and that agents who did not move decide
  exactly as before.
* Cost: one pass over at most 8 bonds with at most 8 x 8 memory
  comparisons each, only for agents with the gate open and only with the
  switch on.

### 2.2 The switch

| Layer | What |
| --- | --- |
| World | `WorldState.community_anchoring`: `True` on, `None` off (dormant: omitted from every output, `tests/test_serialization_dormant_fields.py`); `chronicler.community_anchoring` (`DEFAULT_ENABLED_FOR_NEW_WORLDS = False`) |
| CLI | `--community-anchoring` / `--no-community-anchoring`; an explicit `--community-anchoring` with `--agents off` is refused; a saved setting is kept on resume |
| Live | new live worlds follow the default (off) |
| Native | `AgentSimulator.set_community_anchoring(enabled, full_anchor=None)`, getter `community_anchoring`; `TickOptions.community_anchoring` (`scale::CommunityAnchoring { enabled, full_anchor }`, `persist_struct!`; the checkpoint layout fingerprint changes, as for any new native field). The bridge sends it only when the world has it on: a plain run makes the native calls it always made |
| Tuning | `agents.community_full_anchor` overrides the full anchor (utility units) |
| Batch manifest | `community_anchoring` is a simulation argument (a report with it is another configuration) |
| Checkpoints | `feature_flags` records it; an exact resume adopts it and refuses `--no-community-anchoring` against a saved `True` |
| Gate runner | `--community-anchoring` is forwarded to every agent-mode run (not to the aggregate determinism run, whose manifest then records `None`); with it the default arms add `community_anchor` |
| Ablation | `--decision-ablation community_anchor` (`scale::ABLATE_COMMUNITY_ANCHOR`) switches the anchor off from the start turn; it is refused on a world without the switch |
| Diagnostics | `get_migration_driver_stats()["community_ties_k"]`: agents with the gate open by counted ties (zeros with the switch off); `get_community_ties()` lists every agent's ties as the decision counts them |

### 2.3 The validator's mirror

`validation_ablation.community_ties` recomputes the ties from a turn's
sidecars (relationships, memory signatures, the needs snapshot's regions).
A native test runs a 60-turn hybrid world with the switch on and checks that
the final pool's native ties (`get_community_ties`) equal the mirror computed
from the final sidecar snapshot, agent for agent.

## 3. Calibration and pre-registration

Written before any run with the switch on (the full text is kept with the
run reports, `preregistration.md`, and reproduced here).

**Target, from the spec's range.** An agent fully embedded in a community
of five (four counted ties) should make 22.5% fewer moves over the oracle's
20-turn window: the midpoint of 15-30%.

**From the decision model, not the oracle.** For an agent with the gate
open at move probability P, an odds ratio x lowers the per-turn hazard to
x / (1 - P + P x); P = 0.2 lies between a barely positive migrate utility
(0.13 against stay 0.58 at T = 0.3) and 0.3. The 20-turn count then moves
through the 5-turn settling lock, c = h / (1 + 5h), at the measured hazard
(0.053 moves per agent-turn, h = 0.072 per eligible turn). 22.5% fewer moves
needs x = 0.67: **`COMMUNITY_ANCHOR` = -0.3 ln 0.67 = 0.120143**. Fewer ties
scale the log-odds linearly. No agent is anchored beyond the band: a full
member makes about 22% fewer moves (25% as P -> 0).

**Predicted effects** (direct effect only, the exposure probes' plain moves
as weights):

| Cohort at the fork | template | procedural |
| --- | ---: | ---: |
| oracle community members (method 4's cohort) | 0.93 | 0.95 |
| oracle non-members | 0.92 | 0.95 |
| four counted ties | 0.77 | 0.78 |
| one to three counted ties | 0.88 | 0.90 |
| no counted tie | 1.00 | 1.00 |
| members of communities as oracle 1 specifies them | 0.90 | 0.91 |
| all agents | 0.93 | 0.95 |

The exposure: 45-53% of agents hold no counted tie, 11% (template) and 6%
(procedural) hold four; the oracle's members and non-members hold about the
same ties (template mean 1.62 against 1.44; a non-kin tie in 55% and 49%).

**Causal test** (arm `community_anchor`, forked exactly as the gate's
other arms, cohorts fixed from the plain run's turn-T sidecars, rate ratio
plain / ablated, seed-clustered one-sided 95% bound):

1. The pre-registered claim of cohort method 4 on the oracle's members: RR
   <= 0.85 and upper bound < 1. **Predicted to fail** (0.93, 0.95).
2. Mechanism (a candidate restated claim): agents with four counted ties:
   RR between 0.70 and 0.85, upper bound < 1. Predicted to pass (0.77-0.78).
3. Specificity: agents without a counted tie: 95% interval within
   0.97-1.03. Predicted to pass.
4. Dose: RR(four ties) < RR(one to three) < RR(none).

Broader effects are reported against `main`'s full-gate reports
(exploratory: another configuration), with the predicted fall of migration
per agent-turn of 5-7%. The constants were not changed after any measured
outcome.

CAUSAL_AND_GATES

## 6. The procedural material pairing: fork design 2

### 6.1 Real exposure

Per pairing, from the procedural and template full gates of PR #61
(`ablation-oracles.md` section 3.1; design 1): q is the share of forks with
a cohort (from the seeds with one over their forks, forks taken as
independent), size the mean cohort of a fork that has one, h the ablated
arm's events per agent-turn, SE the realized seed-clustered standard error.

| Pairing | template: q, size, h, SE | procedural: q, size, h, SE | synthetic model of PR #61, procedural (q, size) |
| --- | --- | --- | --- |
| autonomy -> rebellion | 0.16, 44, 0.087, 0.071 | 0.51, 67, 0.076, 0.078 | 0.61, 44 |
| social -> migration | 1.00, 3.9, 0.057, 0.022 | 1.00, 42, 0.060, 0.016 | 1.00, 50 |
| purpose -> switch | 1.00, 33, 0.047, 0.014 | 1.00, 70, 0.035, 0.022 | 1.00, 66 |
| material -> migration | 0.53, 34, 0.051, 0.017 | **0.40, 9.0**, 0.065, **0.060** | 0.72, 28 |
| safety -> migration | 0.03, 19, 0.045, 0.094 | **0.15, 8.2**, 0.050, **0.100** | 0.28, 11 |

The procedural material cohort is 3.6 agents a fork on average (720
agent-forks over 200 forks, 63 informative seeds), a fifth of the model's.
`scripts/synth_ablation_oracles.py` now carries these measured exposures
(`template_gate`, `procedural_gate`) and the candidate designs; with them it
still underestimates the realized SE of the sparse pairings (procedural:
material 0.040 against 0.060, safety 0.078 against 0.100, autonomy 0.034
against 0.078: regional waves and frailty spread wider than modelled). The
power below therefore takes each pairing's **realized** SE and scales it
by the model's SE ratio between designs, with the normal approximation of
the pre-registered criterion, P(RR >= 1.10 and RR - t SE > 1) at Student t
on the informative seeds (`calibrated_power.py` with the run reports).

### 6.2 Power and the choice of design

| Procedural full, 100 seeds | material +15% / +20% | safety +15% / +20% | autonomy +20% | needs component +20% |
| --- | ---: | ---: | ---: | ---: |
| every 100 turns, 2 forks (design 1) | 0.80 / 0.95 | 0.42 / 0.61 | 0.81 | **0.47** |
| every 50 turns, 4 forks | 0.88 / 0.99 | 0.65 / 0.86 | 0.96 | 0.82 |
| 200 seeds, 2 forks | 0.88 / 0.99 | 0.66 / 0.87 | 0.96 | 0.83 |
| **every 20 turns, 9 forks (design 2)** | **0.96 / 1.00** | **0.86 / 0.98** | **1.00** | **0.98** |

* With its real exposure the procedural needs component had about half the
  power PR #61's pre-registration stated (0.47 at +20%, not 0.97-0.99): the
  material pairing itself had 0.95 at +20% but only 0.80 at +15%, and the
  binding pairing was safety (0.61).
* Forks every 20 turns from turn 100 (100, 120, ..., 260) tile the turns
  101-280 with disjoint windows: every agent-turn of the steady state is in
  exactly one window, the most exposure forks can give without overlap. It
  is the smallest spacing that restores the stated component power (0.98 at
  +20%); every 50 turns gives 0.82. More seeds would cost a plain run of 300
  turns each (twice the batch for 200 seeds) where a fork costs 22 turns.
* Cost: 900 forks per arm instead of 200 (checkpoints 4.5 GB at the peak,
  removed per seed once forked).
* **Template worlds keep design 1** (every 100 turns, 800 forks per arm).
  Their realized power at +20% is lower than stated too: safety 0.66,
  autonomy 0.88, component 0.58 (safety's cohort is at 3% of forks). Raising
  it the same way would need forks every 20 turns, 19 a seed (3,800 a
  arm); this branch reports it and leaves it (section 10).

### 6.3 The procedural full gate with design 2

`main`'s simulation (switch off, so the plain batch is `main`'s: every
metric delta against `main`'s report is 0), 100 seeds x 300 turns, forks
at 100, 120, ..., 260, arms `needs`, `kin_roots` and `placebo` (900 forks
each), frozen tree `e67c083`, extension SHA-256 `8497d374...`:

| Pairing | design 1 (PR #61: forks 100, 200) | **design 2 (9 forks a seed)** | placebo, design 2 |
| --- | ---: | ---: | ---: |
| autonomy -> rebellion | 1.468 [1.312, 1.624] (6,786; 76) | 1.440 [1.324, 1.556] (31,021; 85) PASS | 0.988 [0.975, 1.002] |
| social -> migration | 1.165 [1.133, 1.196] (8,303; 100) | 1.167 [1.148, 1.187] (35,982; 100) PASS | 0.999 [0.989, 1.010] |
| purpose -> switch | 1.259 [1.215, 1.302] (13,978; 100) | 1.280 [1.259, 1.301] (59,305; 100) PASS | 0.999 [0.982, 1.015] |
| **material -> migration** | **1.067 [0.947, 1.187] (720; 63) FAIL** | **1.119 [1.093, 1.145] (13,631; 100) PASS**, lower bound 1.097 | 0.991 [0.973, 1.009] |
| safety -> migration | 1.211 [1.004, 1.418] (240; 22) | 1.132 [1.049, 1.215] (1,026; 61) PASS | 0.954 [0.865, 1.042] |
| spiritual -> migration (reported) | 1.219 [1.194, 1.244] | 1.222 [1.202, 1.242] | 0.998 [0.992, 1.003] |
| needs ablation component | FAIL (material) | **PASS** | FAIL in every pairing, as it must |

(agent-forks in the cohort; informative seeds.) The gate: PASS (strict),
NO REGRESSION against `main`'s report, every metric delta 0, needs 7 -> 8
and cohort 4 -> 5 under "Oracle method changes" (`rebaseline_required`).

* **Material passes.** With the terms, agents below the material threshold
  migrate 11.9% more [9.3%, 14.5%]; the one-sided bound (1.097) clears no
  effect, the estimate clears the +10% minimum. The realized SE is 0.013,
  better than the 0.028 the power calculation expected: the cohort is 19
  times design 1's, not 4.5 times.
* **Why design 1 saw so few.** Re-scored on design 2's forks at 100 and 200
  only, the arms reproduce PR #61's estimates exactly (material 1.0672
  [0.9471, 1.1873], 1,001 / 938 moves, 720 agent-forks; every pairing
  equal). Material shortage comes in waves: the cohort is 403 and 317 at
  turns 100 and 200 but 3,534 at 140 and 4,747 at 220 (per fork turn
  1,044, 3,534, 858, 1,119, 317, 4,747, 412, 1,197 from 120 on), and the
  effect at the two old fork turns was 1.16 and 0.97. Two fixed fork turns
  sampled two quiet moments of a wave-driven exposure; nine forks sample the
  waves.
* **The term behaves as specified.** The effect grows with the depth of the
  deficit (the push is 0.5 x (0.30 - material)): 1.097 for material 0.20-0.30
  (half the cohort, push below 0.05), 1.121 for 0.10-0.20, 1.181 below 0.10.
  The cohort's moves are mostly famine-memory moves (48% of the plain arm's
  largest terms; material need itself 8.5%): the need adds to a push already
  there, so its relative effect is moderate. Agents in no deficit move 3.6%
  more with the terms (spillover), a third of the pairing's effect.
* **Placebo.** Every pairing sits at 1 with nine forks a seed (largest
  departure safety 0.954, interval across 1); no pairing passes. The
  seed-clustered bound stays calibrated with the denser forks.
* **Safety** (1.132 [1.049, 1.215], 61 informative seeds against 22) and
  the other pairings are measured more tightly; autonomy and spiritual are
  as before.
* **Kin roots** (cohort component, design 2): members' migration 0.992
  [0.989, 0.996] (407,516 agent-forks), FAIL as before; placebo 0.997.
* Cost: plain batch 1,045 s (with nine checkpoints a seed), arms 4,094 s
  for three arms (2,700 forks, 3.3 s at turn 100 to 5.3 s at turn 260, mean
  4.3 s), validation 637 s; 1 h 36 min in all. The two default arms take
  about 45 minutes (four times design 1's 9 minutes).

## 8. Versions and re-scoring

* **Fork design** (`chronicler.ablation_arms`, `ABLATION_DESIGN` 2; the
  manifest's `schema_version` is its design and design 2 also records
  `design`): design 1 forks every 100 turns from turn 100 in every world;
  design 2 forks every 20 turns from turn 100 in procedural worlds
  (`fork_every`; read from the plain manifest's `simulation.worldgen`) and
  every 100 in template worlds. `load_ablation_arms` checks each manifest
  against its own design's fork turns for the batch's turns and world, and
  records `design` in the report's `ablation_arms` from design 2 on (design
  1 summaries keep their bytes).
* **Needs method 8** (`NEEDS_ORACLE_METHOD_VERSION`): method 7 on design-2
  arms (the components also carry `fork_design`); estimator, cohorts,
  window, minimum effect and criteria unchanged. **Cohort method 5**:
  method 4 on design-2 arms plus `community_ablation`, the community
  anchor's component (`NOT_RUN` without the arm; reported, never deciding,
  in either causal mode).
* **Re-scoring**: `run_oracles` picks the methods from the arms' design
  (`validation_io.ablation_methods`): design-1 arms are scored by needs
  method 7 and cohort method 4, exactly as on `main` (their components keep
  their fields: no `fork_design`, no community component; the tests check
  it); a batch without arms by methods 8 and 5 (`NOT_RUN` components). A
  method refuses arms of the other design (`run_needs_oracle(...,
  method_version=7)` re-scores design-1 arms). `needs_method_7_result` and
  `cohort_method_4_result` still re-score saved components.
* **Comparator**: method 7 -> 8 and 4 -> 5 are reported under "Oracle
  method changes" with `rebaseline_required`, never as new or resolved
  failures (`tests/test_validation_ablation.py`).
* **Gate**: the community component is listed under causal evidence as
  `cohort_community` ("decides": false) and, when it does not pass, among
  the informational rows (`cohort_community_ablation`); nothing it says
  changes a verdict.

## 9. Identity, resume and tests

Builds: fresh release extensions (`maturin develop --release --locked`,
`CARGO_TARGET_DIR` and the virtual environments outside the checkout),
the compiled submodule and its three simulator classes checked before any
run: `main` `b1c9274` (SHA-256 `6f5c5d6a...`, the same bytes as PR #61's
merged build) and this branch at `e67c083` (`8497d374...`), the tree every
gate and identity run used (a `git archive` export). The commits after it
change no simulation code (a tuning-key registration, tests, documents).

* **Switch off, byte-identical to `main`**: `scripts/turn_speed_identity.py`,
  the 9-case matrix (hybrid seeds 42, 7 and 1234, off-mode 42 and 7,
  procedural 48 regions hybrid and off, scaled 22k and 52k agents), `main`'s
  tree and extension against the branch's: **399 files, 0 differences**.
  Hybrid batches with validation sidecars, `main` against the branch:
  template seeds 42-51 x 200 turns **1,110 files**, procedural 32 x 10
  seeds 42-44 x 200 **351 files, 0 differences**. The procedural full
  gate's plain batch (design 2's checkpoints at nine turns) reproduces
  `main`'s report: every metric delta 0.
* **Exact resume with the switch on** (`scripts/checkpoint_identity.py`,
  resumed at every turn): hybrid seed 42 x 60 turns (59 resume points,
  1,780 files), procedural 32 x 8 seed 11 x 40 (39, 1,176), and seed 7 with
  scholarship and the `community_anchor` ablation from turn 20 x 60 (59,
  1,780): **0 differences**; each straight run with checkpoints equals the
  plain one.
* **Native**: the switch and its checkpoint state; the validator's ties
  equal the native ties agent for agent on a 60-turn run; an anchored run
  differs from the plain one, and its `community_anchor` arm from turn 0
  decides exactly as the plain run (the anchor draws nothing); a zero full
  anchor (tuning override) equals the plain run; an anchored run resumes
  exactly (`tests/test_community_anchoring_native.py`). Rust: the anchor
  only turns moves into other choices and draws the same numbers, off and
  ablated equal the plain decision, ties need a shared memory, a home
  region, a positive bond and a non-kin tie (`community.rs`,
  `behavior.rs` `ablation_tests`, `scale.rs`).
* **Tests**: `cargo test --locked` CARGO_COUNT; not-slow NOTSLOW_COUNT;
  `python scripts/run_python_oracle_checks.py` LANE_COUNT. New:
  `tests/test_community_anchoring.py`, `tests/test_community_anchoring_native.py`,
  the Rust tests above; updated: the ablation and validation tests for
  methods 8 and 5 and fork design 2 (both designs loaded and scored, each
  method refusing the other design's arms, the comparator's method
  changes), the dormant-field list, the migration budget's keys.

## 10. Decisions

DECISIONS_SECTION
