# Public-health screen freeze and evidence

The protocol in [the preregistration](../connected-world-screen-health.md) is
frozen at 200 turns, three arms and twelve fresh held worlds: 36 bounded runs.
This is not either restricted qualification gate and promotes no defaults.

The final timing pilot used source
`2dd4af5d544583e22e8416a60bb5131d1bd80674`, incorporating lead runtime
`43f02cca`. Actual Python imports resolved to `/workspace/cw-health/src`.
The CPython 3.13 environment `/workspace/cw-evidence-native` supplied the real
`AgentSimulator` extension, SHA256
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
All 56 Rust/build inputs independently matched the reviewed source aggregate
`38b21020673a028ce6bcd76e19fb3e0c01eed5893b89f1ce6ff6eda6cf8925a2`.
An earlier preflight against `shared/chronicler-native` found no native module;
no simulation ran through that interpreter.

Actual six-run receipts are retained under [pilot-v2](pilot-v2/): metrics,
source and extension identities, strict-check output and the generic report.
All six 200-turn runs passed, covering template 5 and procedural 19 in each
arm. Simulation plus extraction took **147.6 seconds**. Applying each actual
arm/stratum timing to six held worlds gives **0.246 core-hours**; the fixed
1.5 margin gives **0.369**, below **0.75**. Keep one simulation process at a
time and `RAYON_NUM_THREADS=1`.

Independent source review by the evidence lane approved `df0b270b` and
`2dd4af5d`. The separate read-only `health/pilot_review` agent then inspected
the raw actual bundles, not only their extracted metrics. It verified all six
world identities and completed histories, mortality tick/lifetime authority,
nonnegative gross and fresh-cash envelope slack, purpose-specific carry
closure, named wage credits and fully paid next-turn guard capacity. It
independently recomputed the timing projection and approved freeze readiness
on 2026-11-07. Focused strict-extractor tests passed **35/35**.

Every pilot arm recorded supplied care, maintained water, displacement,
staffed guards, dated reports and cash/carry transitions. These observations
establish executable readiness. The two reused development worlds establish
no efficacy claim. Adverse pilot results remain in the raw report: template
PA minus PC deaths per infectious-person-turn increased by **0.085265**,
while deaths per 1,000 end-turn person-turns decreased by **0.665199**.
PA minus shuffled-policy PS cross-polity arrivals increased by **5** template
and **9** procedural. No favorable-sign filter or activation-selected cohort
is used. Paid-worker income deductions without a native wealth-stage receipt
remain explicit unknown counts; reported deduction sums are observed subtotals.

The original actual pilot is retained as
`/workspace/evidence/health/pilot-v1`, with a compact
[failure receipt](pilot-v1-failure-summary.json). Its six simulations completed,
but the strict extractor rejected the actual channel list and explicit null
paid-income observations. The fixes corrected the constructed schema and
preserved unknowns; they changed no simulation behavior or primary definition.
All six simulations were repeated for pilot-v2 after independent review. No
held seed was spent while resolving these failures. The historical CW3 disk
failure is separate and remains untouched.

Reproduce the actual timing pilot and strict check from this checkout with:

```sh
PYTHONPATH=src RAYON_NUM_THREADS=1 /workspace/cw-evidence-native/bin/python scripts/cw_health_screen.py run /workspace/evidence/health/pilot-v2 --screen CW-health --cohort pilot --jobs 1 --keep-first
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_health_screen.py check --screen CW-health --metrics /workspace/evidence/health/pilot-v2/metrics.jsonl --cohort pilot
```

Choose a new output directory when reproducing; preserve the original evidence.
The raw PA procedural example is
`/workspace/evidence/health/pilot-v2/runs/PA-p19/chronicle_bundle.json`.
At completed snapshots 6, 7, 23 and 24 it records, respectively, a pending
delayed report, paid supplied care with prepaid wage carry, a fully paid
staffed border guard, and reuse of guard wage carry. A separate exact-resume
driver tests those actual saved states against uninterrupted execution using
the existing byte comparator. The completed receipts below cover the health
resume, browser and held gates. Whole-program integration and main CI remain
the lead's separate gates.

## Completed held screen

All **36/36** registered cases passed strict extraction on frozen source
`8d38f8b49e2db7635ee9ba074edde1d422fbc030`, with the same native artifact and
screen module as the actual pilot. The worktree remained clean and immutable
through the run. Each of template 3901–3906 and procedural 4001–4006 appears
once in each of PC, PS and PA, for 200 completed turns. All twelve worlds enter
each comparison; template 3905 had zero covered care and remains included.
Every primary ratio was defined. There were no failed or unrun held cases.
Simulation plus extraction took **820.0 seconds / 0.227778 core-hours**, below
the unchanged 0.75 ceiling.

The [complete report](held-v1/report.md), [metrics](held-v1/metrics.jsonl),
[source identity](held-v1/source.txt), [strict check](held-v1/check.txt),
[compact summary](held-v1/summary.json) and original run ledger are retained.
The separate independent `health/pilot_review` agent checked all 36 unique
case identities and all six retained first-world raw bundles, including
metadata/history, modes, T−1 exposure, mortality authority, cash and gross
envelopes, carry conservation, named credits, full paid guard capacity and
dated arrivals with valid polity actors. It independently matched the report's
paired summaries and all 64 sign-flip assignments in each stratum, and approved
the completed held evidence on 2026-11-07.

| Primary contrast | Template mean [min, max] | Procedural mean [min, max] |
| --- | --- | --- |
| PA−PC epidemic deaths per 1,000 end-turn person-turns | −0.291436 [−1.659973, +1.150341] | −0.222941 [−2.125897, +2.158216] |
| PA−PC epidemic deaths per infectious person-turn | −0.009231 [−0.049150, +0.022257] | −0.009507 [−0.052639, +0.038629] |
| PA−PS cross-polity epidemic arrivals | −7 [−18, +1] | +20.833333 [−45, +102] |

These are heterogeneous bounded results. Deaths per 1,000 person-turns rose in
two of six template and three of six procedural worlds. Mean absolute epidemic
deaths changed by −9 template and **+2.833333 procedural**, despite the lower
mean procedural person-turn rate. Evidence-policy arrivals increased in four
of six procedural worlds, with a maximum of **+102**. Mean food shortfall after
relief increased by **247.1719 template / 175.0409 procedural**; famine-region-
turns changed by **+11.333333 / −50**. The full report retains all harms and
per-world signs. This evidence supports no universal benefit, scientific
qualification or default promotion.

Paid-worker income deductions without a native wealth-stage observation remain
unknown. Care/guard unknown person-turn counts total **140/73 PC**, **127/65
PS**, and **141/71 PA**. Deduction sums are observed subtotals. Famine- and war-
cause mortality and forest outcomes are unrecorded in this screen, rather than
assumed zero. These treatment contrasts do not isolate wages or overturn the
earlier fixed-enrollment finding that wages raised household money credits.
They include disease, population, labor, migration and retail feedback.

The registry was not rewritten by this lane. The validated two
[marked rows](held-v1/registry-marked-rows.json) are returned to the lead for
id-based integration, preserving other lanes' registry amendments.

```sh
PYTHONPATH=src RAYON_NUM_THREADS=1 /workspace/cw-evidence-native/bin/python scripts/cw_health_screen.py run /workspace/evidence/health/held-v1 --screen CW-health --cohort held --jobs 1 --pilot /workspace/evidence/health/pilot-v2/metrics.jsonl --keep-first
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_health_screen.py check --screen CW-health --metrics /workspace/evidence/health/held-v1/metrics.jsonl --cohort held
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_health_screen.py report /workspace/evidence/health/held-v1/metrics.jsonl --screen CW-health
```

The cohort is now used: preserve these outputs and do not spend it again as a
fresh held cohort. Raw first-world examples remain outside git at
`/workspace/evidence/health/held-v1/runs/PA-p4001/chronicle_bundle.json` and
`/workspace/evidence/health/held-v1/runs/PA-t3901/chronicle_bundle.json`.

## Exact resume and actual browser journeys

The [resume report](resume/report.json), [actual-state plan](resume/plan.json)
and executed [driver](resume/driver.py) retain the complete command/configuration
and hashes. The PA-p19 timing world used naturally active completed snapshots:
6 pending delayed report; 7 paid supplied care with prepaid care carry;
23 fully paid staffed guard; 24 reuse of prepaid guard carry. No lifecycle
category was missing. Uninterrupted execution versus execution with a checkpoint
every turn compared **16 files with zero differences**. Each resumed branch
at 6, 7, 23 and 24 independently compared **16 files with zero differences**.
All processes ran serially, with no narration API. The source was the successful
pilot's Python code; later changes before the held run were documentation and
the public-health observation-date display only.

The bounded plain run took 34.64 seconds and checkpoint-every-turn run 196.22
seconds. Identity success does not imply negligible checkpoint overhead. These
measurements cover the natural 32-region world and do not replace the lead's
declared-scale profiling.

History's real production-viewer [browser receipt](browser/report.json) passed
**82 checks** across desktop and phone on the same natural PA-p19 bundle
SHA256 `76eb18ab7f22adc150005890997e5d71fe14a7aafa0960a07af470bcdc979fc0`,
at snapshots 6, 7, 23 and 24. It checked actual cash/envelope/care and guard
carry, patient food versus foreign cash or internal value, prior exposure dates,
delivered report ids and own-fatality observation, stable named guard ids,
next-turn capacity, explicit unobserved states, layout and runtime errors.
There were no construction markers or runtime errors. The
[phone snapshot](browser/phone-snapshot23.png) was also visually reviewed.
Measured saved-bundle load was 2,967ms desktop / 2,857ms phone; complete journeys
took 10,584ms / 8,605ms on this environment. These are bounded UI measurements.

## Remaining model and verification limits

Supplies are real grain from local or directly adjacent reachable commons.
Maintained irrigation service is the stated water/sanitation proxy; water
quality and medicines are not modeled. The policy uses delayed reports and a
recorded goods-contact cost proxy because imported food cost by origin is
unobserved. The screen does not isolate guards from all other feedback or care
from maintained-water protection. Regional epidemic fractions, individual
injury-care episodes and mortality authority remain separate. No individual
infection, treatment or survival is inferred from regional capacity or work.

The separately restricted full 200-seed and procedural qualification gates were
not run. Whole-program source compatibility, final union resume, declared-scale
profiling, independent PR review, reviewed-head CI, merges and final main CI are
recorded by the lead; this lane does not claim those gates from its own results.
