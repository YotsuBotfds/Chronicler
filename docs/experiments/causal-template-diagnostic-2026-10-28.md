# Existing template causal diagnostics — 2026-10-28

This is a **read-only diagnosis of completed original reports**, not a new
experiment, parameter fit or gate adjudication. Source is frozen
`5b5252eded6d45957347af744f01847d2f735ef3`, native
`43243cb026c6a6a141d15a5df743c96f8aca05c6bdc7c5ce1adbda8e31a6afd5`.
The recovered cohort has 200 seeds, 500 turns, eight regions/four civilizations,
scholarship enabled, and 800 forks for each of `needs` and `kin_roots`.
The original report SHA-256 is
`3485dfe796b8fb9f07aac0feeed63e15dad5f32910bede44ccafe30d94e0927c`.
The initial analysis used only that candidate. The following comparison was
added after the baseline independently completed; it does not assume that the
two versions produce the same world trajectories or exposure cohorts.

The original strict observational decision is PASS. Its causal components and
community specification are reported, not required. A causal-required read of
that same report fails. Neither outcome is rewritten here. These weaknesses
were already documented in [community anchoring, section 10](../integration/community-anchoring.md):
the 15–30% anchoring claim was not reproduced, stronger coefficients were not
adopted merely to meet the number, and observational cohort PASS is explicitly
non-discriminating. This result is not evidence of a newly introduced regression.

## Completed baseline comparison: one informational status crossing

Both original strict observational gates independently passed under their
unchanged requirements. Both separately fail a causal-required adjudication.
The baseline uses source `cb9fe70c81658fb65c6f511b821447f1d7b55b54` and the
same recorded native binary as the candidate. Its original report SHA-256 is
`d781ff1401364fbaf64ec2c8b8797189c1a6a7791fffb730bd3402938ab540bd`.

| Informational causal pairing | Baseline | Candidate | Report-level interpretation |
| --- | --- | --- | --- |
| Social → migration | RR 1.0886, lower 1.0549; FAIL minimum | RR 1.0794, lower 1.0497; FAIL minimum | Positive contrasts; both miss the point-estimate magnitude criterion. |
| Safety → migration | RR 1.1327, lower 1.0026; PASS | RR 1.0579, lower 0.9852; FAIL lower bound and minimum | A new informational subcomponent PASS→FAIL crossing. |
| Kin roots → fewer member moves | RR 0.9926, upper 1.0024; FAIL bound and minimum | RR 0.9848, upper 0.9957; FAIL minimum | Candidate clears the directional bound; neither reaches 15%. |
| Community share specification | FAIL; 25,550 of 25,550 groups above cap | FAIL; 25,676 of 25,677 above cap | The density feasibility problem persists. |

The bounds in this table are the **one-sided 95% deciding bounds**. Baseline
safety's two-sided 95% interval is `[0.9758, 1.2896]`; the candidate's is
`[0.9701, 1.1456]`. Its marginal one-sided pass does not conflict with a
two-sided interval containing one. The intervals overlap, but overlap itself
is not a paired test. The observed status crossing does **not** establish a
statistically significant deterioration between source versions.

Safety cohort composition also changes: baseline has 332 agent-forks in 28
seeds (26 informative), candidate 477 in 32 seeds (23 informative); counts
of plain/ablated moves are 367/324 versus 585/553. Matching seed labels does
not make these the same post-evolution agents or exposures. The needs/ablation
kernel equality proof rules out a direct edit of those seven files, not an
upstream trajectory, composition, random-stream-consumption or feedback effect.
Attribution requires a separate trace; the aggregate ratios do not identify it.

In the baseline, **none** of the 25,550 group observations lies in a region
with at least 100 living agents. Every one is therefore below the necessary
domain for a five-agent group to fit under the 5% cap. Candidate coverage
improves only to three observations; neither run tests that global claim in
a population-sufficient domain.

Independent original-result packets remain outside Git:

- Baseline packet SHA-256 `db5beb13641d521c3dbe1bd8502cbc56d067917996f9a4affa236cf531bec1f9`.
- Candidate packet SHA-256 `22188d886d021256f16f1664d257204be7b39fb0faf54f13bd1be30a64c18a9d`.
- Separate report-level comparison facts SHA-256 `23f87444d51ff5a034ccd9be7335e53fdb5e1bb745d6c0d8aa05528b44136733`.
- Seven-file byte-equality proof SHA-256 `0a2ef1c956772ef0d8d399b88b1e25825b0af4d6a585366ab7cc780941fa04dc`.

The comparison facts are in
`/workspace/chronicler-causal-diagnostic-evidence/paired-report-facts.json`.
This comparison rescores no gate, changes no requirement and makes no new
paired-significance claim. It leaves the original PASS decisions and both
causal-required FAIL adjudications intact.

## Community share is structurally infeasible for almost all observed groups

The actual detector requires at least five members. The acceptance criterion
requires community size divided by its region's living-agent population to be
at most 5%. Therefore even the smallest allowed community needs **at least
100 living agents in that region**. Exactly five of 100 passes; five of 99
fails, including the implementation's `1e-12` tolerance.

The report already retains the relevant denominators; no Arrow scan is needed:

| Candidate observations | Count |
| --- | ---: |
| Group observations across 8,200 sampled snapshots | 25,677 |
| Group observations in regions with at least 100 living agents | 3 |
| Group observations below that necessary population threshold | 25,674 (99.9883%) |
| Observed share failures | 25,676 |
| Share failures among the three population-eligible observations | 2 |
| Share passes among those three | 1 |
| Median regional population associated with a detected group | 44 |

These are repeated **group-snapshot observations**, not 25,677 independent
groups. Population eligibility is necessary, not sufficient: two of the three
eligible observations still exceed the share cap. The other 25,674 cannot pass
the cap regardless of how a detector partitions them into groups of five or more.
Other specification criteria pass in this cohort: groups appear in all 200
seeds, mean count is 3.1313 and median size is five.

The relevant source is `validation_communities.py`: `ORACLE1_MIN_SIZE`,
`ORACLE1_REGION_SHARE_MAX`, `ORACLE1_REGION_POPULATION_FOR_MIN_SIZE`,
`oracle1_snapshot`, and `run_community_spec`. The denominator counts distinct
living agent IDs in the needs sidecar at that snapshot. It is not a macro
population substituted for an agent count.

There is no verified “25 people per agent” resolution multiplier in this source.
`agent_bridge.build_region_batch` sends each region's population directly;
`ffi/mod.rs` initial allocation conserves exactly that many agents; hybrid
write-back sets region population to the native alive count.
`--agent-scale-mode exact/fast` selects execution algorithms, not agent density.
Increasing only the number of regions does not solve the per-region inequality.
Replacing the denominator with unweighted macro people would mix units.

## The causal failures are not all evidence of a zero effect

Rate ratios are **plain / ablated**. Migration rates here are numbers of moves
per initial agent-fork over twenty turns; they are not probabilities of moving
or rates per eligible decision. Agents can move more than once. The reported
standard errors cluster at seed, accounting for repeated forks within a world.

| Registered causal contrast | RR | One-sided 95% deciding bound | Two-sided 95% interval | Exact failure |
| --- | ---: | ---: | --- | --- |
| Social deficit → migration | 1.0794 | lower 1.0497 | [1.0440, 1.1148] | 10% minimum effect |
| Safety deficit → migration | 1.0579 | lower 0.9852 | [0.9701, 1.1456] | Lower bound and 10% minimum |
| Community members, kin roots → fewer moves | 0.9848 | upper 0.9957 | [0.9719, 0.9977] | 15% minimum effect |

Social shows a positive joint-needs contrast under this estimator. Its interval
still includes 1.10, so the failed point-estimate threshold does not establish
that the true effect is below 10%. Safety is inconclusive: only 477 agent-forks
in 32 seeds enter that cohort, with 23 informative seeds. Kin roots show a small
directional reduction (about 1.52%), not the required 15%; its cohort is 14,043
member-agent-forks across 800 forks and 199 informative seeds. Non-members'
informational migration ratio is 0.9854, descriptively similar; this is not a
community-specificity test or proof of no mechanism.

The `needs` arm reaches the actual Rust decision code: restored simulator
configuration → active `TickOptions.ablation` → zeroed need utility modifiers
and autonomy loyalty factor. The `kin_roots` arm removes marriage/home-bond
roots in `Mobility::drop_relationship_roots`, while age roots, chain pulls and
household following remain. I found no obvious unused-switch defect.
The seven critical needs/ablation/scoring files are unchanged between cb9 and
5b; changed macro trajectories can still change exposure and measured effects.

Community membership is not a mechanical-exposure indicator. The detector
accepts positive friend/co-religionist/kin edges; migration roots require
sentiment at least 20, adulthood, an available voluntary destination and other
gates. Only the relationship part of roots is removed, at most 0.06 under the
recorded constants. The cohort includes people who can follow a household or
move for unaffected reasons. It also consists of detected groups whose global
share specification has failed, not specification-certified communities.

## Exploratory timing pattern and prospective next questions

An outcome-informed split of the report's existing offset counts gives:

| Need cohort | First five ticks, plain / ablated | Remaining fifteen |
| --- | ---: | ---: |
| Social | 1,154 / 971 = 1.1885 | 2,829 / 2,719 = 1.0405 |
| Safety | 167 / 134 = 1.2463 | 418 / 419 = 0.9976 |

This split was chosen after seeing the report. It is **descriptive, not a new
passing endpoint**. Needs evolve before subsequent decisions, moves impose a
five-turn displacement cooldown, and holding a move back can defer it rather
than prevent it. The intervention removes all need channels jointly, so these
are not selective social-only or safety-only effects. This cohort has no
placebo arm; historical placebo studies cannot be imported as its control.

Useful next work can be specified before running anything:

1. **Expose the feasibility domain.** Surface the already measured population
   eligibility alongside share failures, retaining FAIL for the original global
   criterion. An eligible-domain-only result must be separately labelled and
   cannot certify the original claim. The available domain here is only three
   group observations, insufficient for a broad positive conclusion.
2. **Study sustained regional density.** A separately preregistered scenario
   can maintain enough regional population and resources through steady state
   to make the original five-member/5% claim testable. This changes the physical
   scenario, not a sampling resolution knob. Preserve the original cohort,
   thresholds and failure; record density, population survival and performance
   together. Larger worlds alone do not guarantee this domain.
3. **Decompose dose, gates and delay.** Before further calibration, specify
   controlled needs × migration opportunity × cooldown cases with other needs
   held high, plus kin-root exposure by age, marriage and home-bond strength.
   Retain the registered twenty-turn event endpoint; first eligible decision,
   first-move delay and later catch-up may be additional mechanism diagnostics.
   Do not shorten the window post hoc or select a favorable population.

No new simulation, checkpoint restore, native object, Arrow scan, threshold
change or parameter adjustment was used for this diagnosis. The external
fixed-report reader and derived facts are at
`/workspace/chronicler-causal-diagnostic-report.py` and
`/workspace/chronicler-causal-diagnostic-evidence/candidate-diagnostic.json`.
Derived receipt SHA-256:
`d7b8ce4863b68814579b142f278f8b8406f6d8fd76ed9094be898354d238972a`.
The original report's hash matched before and after the read.
