# Independent final CW6 held evidence review

**APPROVE the completed bounded evidence.** No source, native identity,
enrollment, control, accounting, physical closure, extraction, report arithmetic
or execution-budget blocker was found. This approval is not a favorable-effect,
scientific qualification or default-promotion finding. Enabled exact resume,
final PR review and pre-/post-merge CI remain separate lead-owned gates.

Reviewed runtime `eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac`, documentation
freeze `5ec73003837b5149091593ffa411d33dd32e9491`, and the completed files in
`/workspace/evidence/cw6/held/`. The freeze differs from the runtime only in
six documentation/compact pilot-receipt files. The frozen worktree was clean;
actual Python imports resolved to `/workspace/cw-screen-final/src`, with
CPython 3.13.5. The actual imported native extension hash was
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`;
all 56 Rust/build inputs recomputed to reviewed source fingerprint
`38b21020673a028ce6bcd76e19fb3e0c01eed5893b89f1ce6ff6eda6cf8925a2`.
Runner, screen, preregistration, metrics and report hashes are retained.

All **60 distinct cases** completed: five arms on template 781–786 and
procedural 881–886, each for 120 turns. Templates have eight regions/four
initial civilizations; procedural worlds have 32 regions/ten initial
civilizations. All 48 comparison-control records unconditionally include their
worlds; the other twelve are FULL root records. Mechanism activation selects
no primary comparison. Every primary is defined on all six worlds per stratum.
All return codes and strict problems are zero. An independent final invocation
of the real screen checker reported all **131 outcomes complete**.

Actual serial simulation time was **1,298.0 seconds** and extraction time
**169.4 seconds**, total **1,467.4 seconds / 0.407611 core-hours**. This is the
completed-run cost, below the unchanged 1.0-core-hour ceiling; the earlier
0.7805 margin projection is not substituted for execution evidence. Source
records 1,473.2 seconds elapsed wall time. The horizon amendment to 120 turns,
controls, outcomes and frozen preregistration precede held execution.

## Actual raw records and arithmetic

The evidence reviewer decoded all ten retained first-world bundles (five arms
each on procedural 881 and template 781), covering 1,200 completed snapshots.
The separate arithmetic reviewer used only stdlib JSON/Markdown processing to
audit the complete 60-case report. Neither reviewer ran another simulation.

The raw review independently recomputed native component rows into totals,
the six modeled wealth terms and actual transfers into world balance change,
native receipt differences, opening/closing continuity, all three primary
totals and actual population denominators. Every native balance discrepancy
was within `1e-8` (largest observed `2.2737367544323206e-13`). Source dates,
arm modes, rules-2 information neutrality, physical army supply/requisition
removal, credited rations/destruction, actual meal adequacy and absence of
duplicate army meals, timber cargo/escrow conservation and prior price dates agree.
All ten untruncated Arrow sidecar hashes, bytes, source dates and independently
recounted migration/unknown/death totals match the recorded metrics.

The arithmetic review independently matched **6 primary**, **256 secondary**
and **88 fixed-harm** report rows: per-world values, means, ranges, sign counts
and every reported paired sign-flip assignment count. Screen contrasts are
FULL minus control. Generic fixed harms retain control minus FULL; the signs
must not be interchanged. The six primary world comparisons enumerate all
64 sign assignments in each stratum.

| Primary, FULL minus named control | Template mean [range]; +/−/0 | Procedural mean [range]; +/−/0 |
| --- | --- | --- |
| A6R: balance change per 1,000 person-turns | −3.418257 [−9.863969, +6.086508]; 1/5/0 | −1.032714 [−4.726442, +3.975578]; 2/4/0 |
| D3R: native deaths per 1,000 person-turns | −0.410319 [−1.358905, +0.098063]; 1/4/1 | +0.282220 [−1.005215, +2.368725]; 3/3/0 |
| Joint SUP: service asset-turns per region-turn | +0.004455 [−0.001667, +0.013667]; 3/1/2 | −0.007240 [−0.038893, +0.020070]; 2/4/0 |

Results are mixed and materially adverse in places. Both balance primary
means are negative; procedural mortality rises and procedural joint-supply
service falls. Compared with A6R, FULL also records higher food shortfall in
all twelve worlds (mean +1,110.365 template / +1,254.741 procedural) and higher
recorded epidemic mortality in all twelve (+22.167 / +151.333). These are
separate outcome authorities, not counts to add to whole-world native deaths.
The A6 contrast combines several behavioral/information mechanisms; these
results do not replace the earlier fixed-enrollment finding with a claim that
wages themselves caused household credits to fall. Joint SUP cannot separate
timber procurement from harvest-cover effects.

## Measurement limits retained

FULL unknown migration causes total **5,270/6,195 template moves (85.0686%)**
and **21,956/22,338 procedural moves (98.2899%)**. These are pooled event shares,
distinct from the report's per-world mean shares. FULL bounded A6 row drops
are 776 template and 205,136 procedural; across all sixty cases they total
948,055. Work and war event drops are zero. Unknown personal work-cost
observations remain null (FULL 2,535 template / 9,593 procedural; all-arm total
61,076); they are not invented zeros or complete net-income observations.

Unknown causes change X1 classification as well as measurement. Public health
reads the T−1 classified displaced share and applies crowding
`1 + 0.25 × displaced_share`; reclassification can therefore reduce modeled
exposure without reducing physical displacement. FULL minus A6R combines
behavior and information with this exposure-proxy feedback. Lower X1 spells
or displaced person-turns establish neither a physical-displacement nor a
health benefit and do not isolate a pure choice effect. Unknown shares,
untruncated migration totals, X1 counts and physical outcomes must be read
together.

Famine- and war-cause harm fields are explicitly unrecorded in all sixty
cases. Template 786 has no timber capacity/slot, so forest stand remains null
in each of its five arms. Forest-harm comparisons consequently use five
template pairs and 32 sign assignments, explicitly reported as missing for
786; all three primaries still use six worlds and 64 assignments. No failed,
null, adverse or inactive world was replaced or silently treated as zero.

Compact source, raw and arithmetic receipts, output hashes and both rerunnable
independent scripts are in `review-cw6-held-independent/`. The retained initial
reviewer failure log concerns a checker assumption that rules were integer
`2`; the actual saved contract is string `"2"`. Source inspection corrected
the checker before approval (and confirmed timber `cash` is already in
milli-units). This was not a simulation failure. The original CW3 disk failure
and earlier integrated pilot failures remain separately preserved.

Reproduce the review, with retained raw first-world bundles available, using
the verified frozen source interpreter:

```sh
PYTHONPATH=/workspace/cw-screen-final/src /workspace/cw-evidence-native/bin/python docs/superpowers/audits/connected-world/review-cw6-held-independent/check-raw.py /workspace/evidence/cw6/held
python docs/superpowers/audits/connected-world/review-cw6-held-independent/check-arithmetic.py --directory /workspace/evidence/cw6/held
PYTHONPATH=/workspace/cw-screen-final/src /workspace/cw-evidence-native/bin/python /workspace/cw-screen-final/scripts/cw_integrated_screen.py check --screen CW6 --cohort held --metrics /workspace/evidence/cw6/held/metrics.jsonl
```

The evidence covers twelve held worlds and 120 turns, not the separately
restricted full 200-seed/procedural qualification gates. It supports no
default promotion. No paid narration, deployment, purchase, credential or
sharing action occurred during this review.
