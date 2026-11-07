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
the existing byte comparator. Resume, browser journeys, held outcomes and main
CI remain separate gates and are not claimed by this pilot freeze receipt.
