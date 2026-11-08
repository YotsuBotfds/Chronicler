# Connected World correctness, causal evaluation and performance rework

Implementation and the preregistered bounded evaluation are complete and
independently checked. PR #99 merged after independent final review and all
nine exact-head Tests; all nine exact main CI jobs also passed. Source, controls,
cohort, horizon and budget stayed frozen throughout the held run.

## Source and boundaries

The starting reviewed main was `2726bf449d0e4d581a72034000ee0861a58ee439`
(#97; Tests `42397121718`, all nine jobs green). The formatter-only #98 merged
at `125a69066ea158a973ac5207f393e4eeb330aee8`; reviewed-head Tests
`42415795157` and exact main Tests `42417310582` passed all nine jobs.

Corrected production runtime is immutable
`8792be88dd36ba4d7c22e480de6a19dd64ea1300`. Final performance source
`1e047e7b6585d2cf13bb990f03f292c1067979c5` and held source
`b45c1e99572d4d6a60fb01fbd75cb7688aa54e93` have identical production
Python, Rust and script bytes. Their distinct Git identities are retained.
The fresh compiled extension is
`b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd`;
57 Rust/Cargo/build inputs have digest
`f55df55d453ac37694410246c4a9728c56f3f6148f679fde8efc21ffd8775acf`.
The native crate pyproject is separately pinned. Actual source, interpreter,
compiled-submodule paths and hashes are checked in the evidence; a shared
editable install is not accepted as a source identity.

All feature and version defaults remain unchanged. The corrected behavior
requires explicit `--adaptive-livelihoods-rules 3` and
`--public-health-crowding density_only`, with their parent features and existing
prerequisites. Legacy rules 1/2 and `legacy_displacement` remain reproducible.
No paid narration, deployment, purchase, credential/sharing change or restricted
qualification gate is included.

## Verified attribution and control defects

Native adaptive attribution emits driver 255 when it cannot establish a move's
reason. That uncertainty is honest. X1 classified it as `other`, immediately
rehomed the person and omitted a motive-classified displaced spell. Public
health then multiplied susceptibility by `1 + .25 * displaced_share`. Identical
physical moves received 1.25 with recorded hunger/flight versus 1 with an
unknown reason. No separately represented housing/contact fact justified it.

Explicit `density_only` removes only this unsupported additional multiplier.
Existing population/carrying-capacity, hunger, urban and sanitation terms stay.
Motive-classified X1 spells retain their historical meaning; unknown does not
become voluntary or forced displacement. New diagnostics count unique living
stable identities with a witnessed residence move in the last 20 turns, once
at the final residence. Returns, onward moves, death, household changes, trips,
slot reuse, row caps, observation gaps and restore are covered. A full share is
unknown until a complete observation window exists. It is not measured housing
pressure. X1 still has one Phase 10 writer and guarded T−1 consumers.

The downstream regression calls real epidemic introduction and case dynamics,
including density, hunger, urban effects, C2 care CFR and flux sanitation. With
the old reader substituted, susceptibility differs 2.1875 versus 1.75; corrected
reason labels give identical inputs and positive case trajectories. The composed fatality
multiplier remains .77 in that constructed test; this is not a 77% case-fatality
probability. This is a failing-old-code regression,
not a claim about real-world disease calibration.

A6 rules 2 record-only also erased D3 movement scores, and shuffled mode could
redirect D3 remembered-home scores. Explicit rules 3 retains D3 independently
while controlling personal migration experience, migration information, work
choices and trade choices. It records actual combined/capped installed inputs,
separate components and would-be personal inputs. Installed input counts and
combined native receipts do not identify which component caused an outcome.

See the [core review](../audits/connected-world/rework-core-independent-review-2026-11-07.md),
[downstream trace](../audits/connected-world/rework-downstream-c2-trace-2026-11-07.md)
and [contracts](../../integration/public-health.md).

## Historical CW6 findings remain adverse

The independent audit reproduces all 60 metric rows, ten first-world raw
bundles, source/native identities and report arithmetic. At the 120-turn
horizon, FULL minus A6 record-only increases regional food shortfall and
recorded epidemic deaths in all twelve held worlds:

| Stratum | Mean food-shortfall difference | Mean recorded epidemic-death difference |
| --- | ---: | ---: |
| Template, six worlds | +1110.364818 | +22.166667 |
| Procedural, six worlds | +1254.741389 | +151.333333 |

Food shortfall is a regional availability measure, not household affordability.
Famine and war cause-specific deaths are unrecorded, not zero. Pooled unknown
migration reasons are 85.0686% / 98.2899%; the world-average percentages differ
and are retained separately. FULL has more moves but fewer classified displaced
person-turns. The old multiplier nominally favors FULL, so removing it cannot
simply be assumed to explain or reverse the adverse result.

This old contrast combines personal decisions, D3 control ownership and legacy
crowding feedback. It does not isolate a wage effect. The earlier fixed-enrollment
result remains: wages increased household credits; expanded retail enrollment
and replaced farm income explained the earlier aggregate fall; priced-out-rate
effect remained null. Historical results have not been overwritten.

[Historical arithmetic, definitions and controls](../audits/connected-world/rework-cw6-evaluation-audit-2026-11-07.md).

## Fresh preregistered evaluation

The [frozen protocol](connected-world-rework-prereg-draft.md) specifies twelve
arms over template 4101–4106 and procedural 4201–4206, 120 turns each: 144 runs
on twelve fresh worlds. A refreshed audit checked 63 registry references and
14 distinct versions before start, with no collision or prior use. Earlier
reservations, used cohorts and the CW3 disk-full failure remain intact.

All arms retain A6 rules 3 and active D3. RD/AD are personal record-only/adapt
under density-only health; RL/AL retain the legacy additional multiplier.
MX/IX/WX/TX delete one personal component from AD. RPC/APC disable care-CFR and
sanitation benefits while retaining billing rules, supplies, guards and
quarantine controls. RNR/ANR use the joint ownership/free-pool allocation regime:
title fraction .9→1 and no retail means-tested priority; free food still exists.
These are not pure price controls, fixed realized spending or additive isolated
effects. Current retail access and regional availability are measured separately. The
retail “all” boundary is the same eligibility recipe across arms, not identical
realized enrollment: only qualifying controlled regions with a living ruler
enter, and controller/war trajectories can change coverage. Unobserved access
stays null or an explicitly incomplete observed subtotal.

Three primary outcomes and all world-level contrasts, nulls, harms, activation,
population denominators and descriptive uncertainty are preregistered. Each
stratum has six worlds; exact paired sign flips enumerate 64 assignments.
Bootstrap and sign-flip summaries describe this small enrolled sample. No
post-treatment activation filter, favorable-world selection or held-seed
replacement is allowed.

The source-bound 24-run pilot passed every 120-turn case and independent
arithmetic/control checks. Simulation 484.7 s plus extraction 68.5 s totals
553.2 s; six held worlds per stratum with fixed 1.5 margin project 1.383
core-hours, below the unchanged two-hour cap. Protocol SHA256 is
`51b8a336969f48b4beb6f5b3e543062eda71822b98513b337ceb2d010e6efe7a`.
The held run started 2026-11-07T22:41:33Z, identity `98c7bb2a…`; all reserved
seeds are potentially spent from that start. Only its existing output and
identity may be continued. Container recovery is not promised.

### Closed held results

**All 144 cases passed**, with no failures or missing outcomes. Simulation
2,934.7 s plus extraction 410.1 s totals 3,344.8 s / **0.92911 core-hours**,
below the unchanged two-hour cap. Independently measured descendant CPU is
3,352.51 s and wall time 3,357.92 s; the scopes differ and are retained.
The maximum single waited-for child/descendant RSS is 1,184,040 KiB, not a
simultaneous process-tree peak. All twelve seeds were recorded as used once,
after closure, without changing the cohort-content hash. All 171 post-record
registry/extractor tests pass.

The independent standard-library audit passes all 144 rows, source/control
receipts, rates, nulls and the six rendered primary rows. Raw first-world
readback passes all 24 retained cases / 2,880 snapshots, including Arrow,
outcome/person-turn arithmetic, prior PH/X1 clocks and food observations.
Bounded component samples leave 784 procedural merge-turns unverified; AD-p4201
has only 6/120 complete-component turns. All 1,440 retained first-template-world
merge-turns are reconstructible. This is distinct from complete per-person movement or housing
history, which the exported data do not provide.

| Primary, arm minus control | Template mean; paired bootstrap 95% | Procedural mean; paired bootstrap 95% |
| --- | ---: | ---: |
| AD − RD regional food shortfall | +812.431; [390.427, 1441.99] | +2081.886; [755.017, 3156.63] |
| AD − RD recorded epidemic deaths | +30.167; [6.167, 53.667] | +69.333; [−52.167, 159.333] |
| (AL − RL) − (AD − RD) epidemic deaths | −18.333; [−34.333, −4.333] | −43.167; [−137.5, 75.333] |

These are six paired worlds per stratum, not individual-level replicates.
Exact sign-flip extreme counts are 2/64 and 4/64 for food, 8/64 and 20/64 for
epidemic deaths, and 8/64 and 30/64 for the interaction. The intervals describe
this small enrolled sample; they do not qualify or calibrate the model.

| World | AD − RD food shortfall | AD − RD epidemic deaths | Crowding interaction, epidemic deaths |
| --- | ---: | ---: | ---: |
| t4101 | +557.492 | +69 | +3 |
| t4102 | +2320.660 | +40 | -15 |
| t4103 | +339.861 | +56 | -54 |
| t4104 | +908.553 | +0 | +0 |
| t4105 | +357.325 | -16 | -17 |
| t4106 | +390.697 | +32 | -27 |
| p4201 | +3731.215 | +209 | -145 |
| p4202 | +2536.929 | +92 | -198 |
| p4203 | +1092.864 | +37 | -39 |
| p4204 | +3201.734 | +141 | -47 |
| p4205 | -677.064 | +151 | -63 |
| p4206 | +2605.641 | -214 | +233 |

Food availability is worse in 11/12 worlds; recorded epidemic deaths increase
in nine, decrease in two and tie in one. Mean person-turns also rise by
2,282.333 / 10,072.333 (template / procedural). Mean paired differences per
1,000 person-turns remain adverse: food **+19.87074 / +15.34348** and epidemic
deaths **+0.94768 / +0.30204**. Some world signs change after normalization;
neither total nor rate alone describes welfare. The correction did not remove
the adverse outcomes. The negative crowding interaction measures the declared
recipe interaction; it is not proof that legacy crowding helps or that one fix
explains historical CW6.

All successful enrolled worlds remain included. Actual personal inputs,
independent D3 rows, work declines, supplied-care region-turns and extra
crowding factors are reported separately. Removing information lowers average
regional shortfall, but also lowers person-turns and endpoint civilization population;
that is not established welfare improvement. Removing work choices has exact
null primary differences in all six templates. Template RD/AD supplied-care
coverage is zero and their PH cost-only primary contrasts are exact nulls;
procedural care activation is sparse. These are limited mechanistic tests,
not broad clinical evidence or component-level attribution of native choices.

The joint `no_relief` regime can lower regional shortfall while increasing
**observed** priced-out person-turns in every world in both personal contexts.
Mean increases are +1,382.5 / +5,127.833 (RNR−RD) and
+1,390.333 / +4,817.5 (ANR−AD). These are observed provisioning subtotals,
not complete-world access censuses. All six procedural AD worlds have access
coverage gaps, 65–373 populated region-turns each; complete access totals stay
null. Across procedural AD, 659/720 component merges are sample-capped.
These limits prevent complete access or per-input mediation claims.

The inherited raw report headings incorrectly say “non-activated worlds
excluded.” CWR1's eligibility function always includes successful enrolled
worlds, including zero actual activation; every primary has all six pairs.
The [adjacent erratum and unchanged raw report](../audits/connected-world/rework-cwr1-held/README.md)
record that presentation defect without rewriting evidence. Metrics SHA256
is `6c56e3ffa725848c69aecf6f2edfcdf81adb18e5c5f038562e2c9d3c73ace9e0`;
raw report SHA256 is
`e5d64f1658265a64ed100d158d650d29eed1f0247d77ea980599c3a145eaf2c3`.

Historical CW6 remains adverse and unchanged. Comparing its outcomes with
CWR1 cannot identify one correction: rules/source, D3 ownership, crowding
recipe and seeds differ. Only preregistered within-CWR1 matched contrasts
identify the tested recipes. No parameter was tuned to old or fresh held
outcomes. This bounded screen is not either restricted qualification gate.

## Practical performance, same corrected simulation

The comparator is corrected, unoptimized `09403c15`, not historical CW6's
physically different rules-2 run. Every size, horizon, feature and observation
is retained. Five declared worlds have OFF/FULL controls; OFF retains the
prerequisite productive-recovery/care chain and is distinct from the no-switch
default identity test. CPU is measured separately from shared-host wall time.

| FULL declared case | Corrected baseline CPU | Final CPU |
| --- | ---: | ---: |
| Template 5, 200 turns | 21.499 s | 20.258 s |
| Procedural 32, seed 19, 200 turns | 79.064 s | 66.506 s |
| 18,801 initialized agents, 30 turns | 105.444 s | 69.552 s |
| 43,700 initialized agents, 20 turns | 60.837 s | 60.115 s |
| Procedural 48, seed 42, 150 turns | 51.438 s | 49.463 s |

The fixed FULL workload totals 318.28→265.89 CPU seconds, an observed 16.46%
reduction; the most expensive baseline case improves 34.04%. Small changes remain inconclusive
single observations, with OFF variability and the first candidate's adverse/null
results retained. Actual initial/peak populations remain declared and matched;
the historical `scaled52k` case initializes 43,700 and reaches 53,138.

The first measured bottleneck was repeated timber population scans and route/
price work. Caches are local to one synchronous planner, retain immutable
physical facts only, and refresh live wallet/eligibility before accepted
settlement. Their projection is created only when dispatch is attempted.
A bounded full 30-turn diagnostic then attributes 63.334/106.409 model CPU
seconds to titled-food dispatch. Two exact Fraction floors inside carrier/owner
loops are replaced by algebraically identical arbitrary-precision integer
operations. Claims, wallet rounding, ordering, prices and settlement stay live.
A 600-combination boundary oracle and old-code allocation regressions cover the
change. The interrupted recursive 20/30-turn diagnostic remains explicitly
incomplete and is not a timing baseline.

All ten final case pairs pass: 760 non-bundle/Arrow output pairs are byte-equal;
complete typed, key-ordered, signed-zero-aware bundles match after only the
`generated_at` normalization. Thirty-six checkpoint pairs have identical native,
world/history, all 37 private livelihood components, flags and configuration,
with 72 exact same-source reads. The independent review rehashes retained raw
artifacts and measurement CSVs. All predeclared operational CPU/RSS targets
pass; they are batch envelopes, not qualification thresholds.

FULL still costs 1.82–4.31× OFF and raw bundles remain 2.37–4.12× larger. RSS
improvements are small/mixed. Run peak and checkpoint-readback/bundle-load peak
are distinct; the final validator-only peak was not separately measured.
The [complete performance evidence](connected-world-rework/performance/README.md)
retains commands, budgets, source/native identities, per-turn CSVs, nulls,
adverse observations and computational failures.

History indexing reused identical locale formatters. All 48 desktop/phone timing samples (24 matched pairs) and locale/index/query equalities are retained. Long-case
median cold openings improve from roughly 4.5–8.8 seconds to 1.2–2.0 seconds;
stress-case gains are smaller. Slower file loads/selection and increased heap
in some cases remain disclosed. Optional deterministic gzip archives reduce
payload bytes 75.08–84.51%, preserving the exact original JSON. Keeping both
files adds storage. Browser loading is about 4–8% slower in the retained
samples; decoded memory is unchanged. Default JSON output is unchanged.

[Formatter evidence](connected-world-rework-viewer/README.md),
[archive evidence](connected-world-rework-storage/README.md),
[reader and archive journeys](connected-world-rework-viewer-compatibility/README.md).

## Compatibility and lifecycle evidence

Final runtime default-off identity passes nine cases and 399 file comparisons
against both original `8abc1acb` and preceding integrated main `125a6906`
(source-equivalent to the retained `830d0dc2` baseline): zero differences.
Raw and decoded bundles normalize only `metadata.generated_at`; no broader
projection is used. Actual source/import/native identities are retained.

Enabled AD rules-3/density-only exact resume passes fourteen selected active
branches plus two checkpoint-writing neutrality comparisons: 202 file
comparisons, zero differences. All eighteen raw Arrow outputs match the pilots;
source, native, flags and input guards remain stable. These are new same-source
private checkpoints. Procedural time 387.03 s fits its 600 s cap; template
174.53 s fits 350 s. The union covers actual migration, complete arrival
observation, care/individual episodes, paid work, D3 injury/evacuation/return,
food and timber cargo, money, requisition and restitution. Missing template
care/timber activations and unavailable procedural checkpoint-zero boundaries
remain explicit; template supplies all four D3 before/after boundaries.
These are observed predicates, not a complete personal diary or every possible
transition. [Plans, commands, raw comparisons and limits](connected-world-rework-resume/README.md).

The complete corrected 120-turn browser example validates 197,271 observations
and all source pointers. All 3,840 PH rows match prior X1 data. The corrected
same-turn difference counter is 2,163, with 3,808 independent adjacent-PH
checks; the earlier 2,392 receipt is retained as invalid/superseded. All 372
real desktop/phone assertions pass across snapshots 1, 22, 23 and 120. First
complete X1 arrival coverage occurs at snapshot 22; PH observes it at 23.
[Actual complete-window journeys](connected-world-rework-viewer-compatibility/complete-window-120.md).

The broad offline gate passes 76 chunks, 8,119 tests and 69 conditional skips,
maximum 31.99 s within the unchanged 110 s chunk limit. This source precedes
only the final exact-floor change; 70 focused trade tests and nine native
lifecycle checks cover that delta. Full Rust: 1,339 pass, two pre-existing
manual timing benches ignored. All nine Tests jobs pass on the final independently
reviewed head `72d89dde` (run `42426724513`); the merged tree is identical.
Exact #99 main Tests `42428257952` also passed all nine jobs. The appended cwr1 inverse is independently verified bidirectionally;
historical source and registry hash pins are preserved.

## Scope and remaining limits

The adopted implementation and the full original request are distinct. Ports
remain deferred because no maritime port-service consumer exists. Owned
cross-border wares are an unimplemented, unadopted audit proposal, not completed
food/timber procurement. The constructed visibility/redaction example is not
a separately simulated alternate story or a complete constructed per-slice
suite. [Scope disposition](../audits/connected-world/rework-scope-disposition-2026-11-07.md)
and the [current rework coverage](connected-world-rework-coverage.md) map all
31 original rows. The [historical coverage matrix](connected-world-final-coverage.md)
remains dated evidence of the adopted implementation.

The existing wealth balance is the single spendable balance, not a globally
conserved cash system. Regional epidemic fractions and individual health-care
episodes retain their separate authorities. Motives remain uncertain; recent
arrivals do not measure forced displacement, housing pressure or contact rates.
Regional food availability does not replace observed household access. Uniform
care and proxy environmental/report parameters are not pathogen-calibrated.
Cause-specific famine/war deaths are unrecorded. Endpoint ID birth/death counts
are not a full event census, and histories/knowledge samples retain explicit
bounds. Known legacy provenance/decision, merchant-origin/current-region income
and natural-death army-booking issues are not silently changed in default runs.

The restricted full 200-seed and procedural qualification gates and default
promotion are **unrun and unauthorized here**. Passing bounded screens, tests,
profiles or browser journeys does not imply those gates passed.

## Reproduction and integration

Use a matching verified native build and source. New paths preserve old evidence:

```sh
PYTHONPATH=src RAYON_NUM_THREADS=1 python scripts/cw_rework_screen.py run NEW/pilot \
  --screen CWR1 --cohort pilot --jobs 1 --keep-first
PYTHONPATH=src python scripts/cw_rework_screen.py check --screen CWR1 \
  --cohort pilot --metrics NEW/pilot/metrics.jsonl
PYTHONPATH=src python scripts/cw_bundle_archive.py --source RUN/chronicle_bundle.json \
  --output NEW/chronicle_bundle.json.gz
```

Fresh held seeds are consumed by the recorded start; do not rerun them as fresh
experiments. The independent stdlib checker and saved metrics/report support
read-only arithmetic reproduction without simulation. Exact commands, source
hashes, environment paths and controls are linked above; workspace lifetime is
not guaranteed.

**Integration:** #99 merged at `a5ccbbf528de82d8a4fa19dbebe7d6ab805b2b96`.
Its tree equals reviewed `72d89dde`; all nine
[premerge Tests](https://github.com/YotsuBotfds/Chronicler/actions/runs/42426724513)
passed. Exact [main Tests](https://github.com/YotsuBotfds/Chronicler/actions/runs/42428257952)
passed all nine jobs. The current
[registry and integration board](connected-world.json) records the verified runtime.

The final integration ledger and late independent audit add no runtime change.
The read-only [harm audit and archived-artifact reproduction](../audits/connected-world/rework-cwr1-independent/held-review-2026-11-07.md)
check all 242 rendered harm rows / 1,452 paired-world cells and 3,744 activation/
coverage observation cells. Its fresh staging recipe preserves original hashes;
no simulation or native agent module is invoked. This reporting PR follows the
same independent-review, green exact-head Tests and verified final main policy.
Its later verification is recorded in the PR and final handoff; the authoritative
current documentation CI is the Tests push run for current main HEAD.
