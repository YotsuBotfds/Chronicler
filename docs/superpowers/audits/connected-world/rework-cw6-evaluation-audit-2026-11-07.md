# Historical CW6 recheck for the correctness and causal rework

The recorded adverse outcomes are reaffirmed. All sixty historical metric rows,
all ten retained first-world bundles and their Arrow sidecars agree with the
frozen definitions and controls. This audit ran no simulation, changed no old
evidence, spent no seed and changed no registry entry. It does not evaluate the
forthcoming correction or establish a pure A6 component effect.

Source inspected: main `2726bf449d0e4d581a72034000ee0861a58ee439` and the frozen
[CW6 protocol](../../progress/connected-world-evidence/CW6/held/preregistration-frozen.md),
[metrics](../../progress/connected-world-evidence/CW6/held/metrics.jsonl) and
[report](../../progress/connected-world-evidence/CW6/held/report.md). This is a
new readback, distinct from the [original independent held review](review-cw6-held-independent.md).
The compact [summary](rework-cw6-historical/summary.json),
[arithmetic](rework-cw6-historical/arithmetic.json),
[raw readback](rework-cw6-historical/raw-readback.json) and
[independently recomputed contrasts](rework-cw6-historical/contrasts.json)
retain the checks and per-world observations.

## What was verified

- Exactly five arms × twelve enrolled worlds, each once: template 781–786
  (eight regions/four initial civilizations), procedural 881–886 (32 regions/ten
  initial civilizations), all **120 turns**, not the rejected 200-turn pilot.
  All return codes are zero, strict extraction problems empty, and comparison
  enrollment is unconditional on mechanism activation.
- All six primary, 256 secondary and 88 fixed-harm report rows match the metric
  values, denominators, signs, means, ranges and descriptive sign-flip counts.
- Ten retained bundles cover 1,200 completed snapshots. Completed-turn dates,
  actual controls, native A1 components/typed closures and opening/closing
  continuity, D4 food/meal closure, timber cargo/escrow/prior-price dates and
  all three primary totals match. The largest observed native balance closure
  discrepancy is `2.2737367544323206e-13`, below the declared `1e-8` bound.
- Their untruncated Arrow migration, unknown-driver and native-death totals,
  source dates, sizes and SHA256 values match the recorded metrics. Bounded
  individual samples are not substituted for these totals.
- Actual simulation plus extraction was **1,467.4 seconds = 0.407611
  core-hours**, below the unchanged historical one-core-hour ceiling. The
  historical wall duration and pilot margin are distinct measurements.

The [source receipt](rework-cw6-historical/source-verification.json) verifies
that held freeze `5ec73003837b5149091593ffa411d33dd32e9491` differs from physical
runtime `eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac` in six documentation/pilot
receipt files only. All 56 Rust/build inputs match native source
`9e0017017245870affa0401714d14cddccf98ff7` and path/content digest
`38b21020673a028ce6bcd76e19fb3e0c01eed5893b89f1ce6ff6eda6cf8925a2`.
The retained import record identifies the historical artifact; its available
bytes were rehashed as
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
No native rebuild was used for this audit.

The historical runner, screen and preregistration hashes match the source
record. Metrics SHA256 is
`b8365bf868b7cfdfa88740304a669429be2bff52d1000c9f0cd7b039eb0fba45`;
report SHA256 is
`c6be63fb3e73288c48f3a1c7955777996ed4845cc2266781762394c7b91ef50b`.
No historical failure or null was rewritten, including the separate CW3
disk-full failure and the superseded diagnostic pilots.

## Adverse results, with an explicit sign

The following differences are **FULL minus A6R**. The generic historical fixed
harm table uses the opposite sign, A6R minus FULL. These conversions are
checked, not inferred from a headline.

| World | Food shortfall after relief, FULL−A6R | Recorded epidemic deaths, FULL−A6R |
| --- | ---: | ---: |
| template 781 | +1,135.161870 | +2 |
| template 782 | +1,465.045272 | +16 |
| template 783 | +977.392480 | +20 |
| template 784 | +672.279725 | +19 |
| template 785 | +1,865.920772 | +36 |
| template 786 | +546.388788 | +40 |
| procedural 881 | +2,210.834770 | +16 |
| procedural 882 | +2,299.555657 | +220 |
| procedural 883 | +1,117.719850 | +280 |
| procedural 884 | +975.215612 | +59 |
| procedural 885 | +475.258455 | +76 |
| procedural 886 | +449.863991 | +257 |

Mean food shortfall differences are **+1,110.364818 template** and
**+1,254.741389 procedural**. Mean epidemic-death differences are
**+22.166667** and **+151.333333**. Every difference is positive. Each of these
four six-world summaries has two of 64 absolute sign-flip means at least as
extreme as observed. That enumeration describes these paired worlds; it is
not qualification, a universal-effect claim or a reason to discard harms.

Food shortfall is the sum over region-turns of native demand multiplied by
`max(0, 1 − min(1, sufficiency_after_relief))`, from the food-accounting
authority. It is neither household cash expenditure nor a count of diagnosed
famine deaths. Epidemic deaths are the final cumulative
`epidemics.deaths_total` counter. The native-death primary is a separate A1
stable-id observation validated against the Arrow death events; these
quantities must not be added as independent mortality components.

Famine-cause and war-cause harm fields remain **unrecorded/null in all sixty
rows**, not zero. Forest stand is null in all five template-786 arms because
that world has no applicable timber capacity; forest harm uses five template
pairs while the primaries use all six.

## What the old contrast can and cannot identify

The old A6R control turns off several mechanisms together: personal migration
scores, native destination-information gating, work/training offer decisions
and personal trade destination choices. Source at the inspected main also:

1. Adds D3 movement rows to A6 rows, then installs an empty combined list in
   A6 `record_only` (`adaptive_livelihoods.before_agent_tick`). Thus old A6R
   suppresses configured D3 movement inputs too. Existing `shuffled` remaps
   the already combined rows, so it can redirect D3's remembered-home signal.
2. Replaces affected native move-driver attribution with unknown. X1 maps that
   driver to `other`; its cause-dependent spell/home logic can differ for the
   same physical relocation.
3. Lets public health consume the T−1 classified displaced share through its
   registered `read_frame`, adding `1 + 0.25 × displaced_share` susceptibility.
   Existing physical density and, when enabled, urban susceptibility terms
   remain in epidemiology separately. Public-health `cost_only` retains this
   extra crowding term; it suppresses care/sanitation effects, not crowding.

The T−1 contract is respected by that old consumer, but correct dating does
not make a motive-dependent exposure proxy physically justified. These source
paths require separate corrected contracts and adversarial tests. This audit
does not infer a motive for an unknown move or fabricate a displacement spell.

The contrast visibly changes both movement and its classification:

| Stratum | FULL migrations | A6R migrations | FULL classified displaced person-turns | A6R classified displaced person-turns |
| --- | ---: | ---: | ---: | ---: |
| template | 6,195 | 3,656 | 11,696 | 31,554 |
| procedural | 22,338 | 18,702 | 4,047 | 130,553 |

FULL unknown drivers total **5,270/6,195 = 85.0686%** template and
**21,956/22,338 = 98.2899%** procedural. These are pooled event shares.
The unweighted means of the six per-world unknown shares are **85.2715%**
and **98.3152%**; they are different statistics. Neither lower classified
displacement nor a lower added multiplier establishes fewer physical moves,
less displacement or better health. Holding other inputs fixed, a lower
share lowers this added exposure term, but nonlinear downstream dynamics
preclude inferring the sign of a correction's total effect.

The old adverse observations remain valid. Any interpretation of FULL−A6R
as a **pure own-experience/A6 choice effect** is superseded by this more
specific description of the implemented joint contrast. This does not
supersede CW1's fixed-enrollment wage finding or its null priced-out effect.
An adverse outcome by itself is not a software defect. Fresh matched controls
must evaluate the corrected source; the old held worlds cannot be reused for
tuning or a fresh held claim.

## Fresh-seed candidates and reproduction

The [candidate snapshot](rework-cw6-historical/seed-candidates.json) checked
48 available local/remote refs containing registries, with thirteen distinct
registry byte versions. Template 4101–4106 and procedural 4201–4206 had no
collision with any entry or restricted range at that check. This is a
historical candidate-only check: it **reserves and spends nothing** and is
not permission to reuse seeds after another lane claims them. The integration
owner must reconcile the latest registry and reserve before execution.

The [stdlib reproducer](rework-cw6-historical/audit.py) independently checks
all sixty frozen rows, key denominators/authorities, cause nulls and the
adverse world-level contrasts. It refuses altered historical metric bytes:

```sh
python docs/superpowers/audits/connected-world/rework-cw6-historical/audit.py \
  --metrics docs/superpowers/progress/connected-world-evidence/CW6/held/metrics.jsonl \
  --out /workspace/evidence/new-cw6-readback/contrasts.json
python docs/superpowers/audits/connected-world/review-cw6-held-independent/check-arithmetic.py \
  --directory docs/superpowers/progress/connected-world-evidence/CW6/held \
  --receipt /workspace/evidence/new-cw6-readback/arithmetic.json
```

For raw validation, use a **new audit directory** with symlinked copies of
the unchanged metrics/report and a `runs` link to the retained raw bundles,
then invoke the existing `check-raw.py` on that new directory. Its output is
written there, never over the original historical receipt. The evaluation
lane used `/workspace/evidence/cwr-evaluation/historical` this way and checked
all ten available first-world bundles. Raw availability after reclamation is
not promised; compact identities, source refs, scripts and commands are
committed. No new qualification or default-promotion result is claimed.
