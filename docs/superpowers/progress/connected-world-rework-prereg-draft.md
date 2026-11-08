# CWR1 correctness and causal mechanism screen

Status: FROZEN — reviewed CWR1 source, complete timing pilot and budget receipt below.

Compute ceiling: 2.0 core-hours

Primary outcomes: cwr_food, cwr_epidemic, cwr_crowding_interaction

This is a fresh bounded screen, not either restricted qualification gate. It
promotes no defaults and uses no narration API. The historical CW6 findings
remain recorded at their original 120-turn horizon and frozen source; see the
[new historical audit](../audits/connected-world/rework-cw6-evaluation-audit-2026-11-07.md).
Nothing in the new design retunes parameters to those held worlds or assumes
that an adverse outcome is a defect.

The integration owner must freeze this protocol only after the corrected
contracts, source/native identities, extractors and complete timing pilot pass
independent review. No held seed may be started before that freeze. The exact
source commit, imported extension hash, all commands and the timing projection
must be appended to this document before its status changes to FROZEN.

## Cohort, horizon and shared configuration

Reserved fresh cohort: template 4101–4106 (8 regions, four initial
civilizations) and procedural 4201–4206 (32 regions, ten initial civilizations).
The refreshed live audit found no collision across 52 available local/remote
registries (13 distinct versions) and restricted ranges. The append-only CWR1
reservation is recorded in scripts/seed_registry.json and
connected-world-rework-seed-reservation.json. Reservation spends no held seeds.
No held world may start while this protocol remains DRAFT. The only timing/schema pilot worlds are the existing shared
template 5 and procedural 19; they are never held.

All twelve arms use **120 turns**, hybrid simulation, campaigns, personal
health care, all-region household retail rules 2, the maintained infrastructure
and named paid-work chain, real timber/cargo/ration/restitution mechanisms,
institutions, public health, X1 and strict A1 observations. Physical resource
and money authorities, existing population/capacity and urban susceptibility
terms, RNG streams and all non-intervened settings remain the same.

Every arm retains the A6 feature with **rules 3**, including the personal
record-only controls. Turning the feature off entirely would remove its D3
movement dispatcher and is not the intended comparison. Rules 3 keeps active
D3 score contributions independently of personal A6 adapt/record-only mode;
saved rules 1/2 retain their historical behavior. No unknown move motive is
filled in. The existing uniform care coefficient remains unchanged and is
not pathogen-calibrated.

The maintained feature defaults remain A6 rules 2 and public-health
`legacy_displacement`. Rules 3 and `density_only` are explicit experimental
opt-ins in these arm flags; neither correction is promoted by this screen.

The executable arm flags are declared in `scripts/cw_rework_screen.py`.

| Arm | Personal A6 mode/channels | Added public-health crowding | Health effects | Retail regime |
| --- | --- | --- | --- | --- |
| RD | record_only / all | density_only | active | retail |
| AD | adapt / all | density_only | active | retail |
| RL | record_only / all | legacy_displacement | active | retail |
| AL | adapt / all | legacy_displacement | active | retail |
| MX | adapt / no_migration_experience | density_only | active | retail |
| IX | adapt / no_information | density_only | active | retail |
| WX | adapt / no_work | density_only | active | retail |
| TX | adapt / no_trade | density_only | active | retail |
| RPC | record_only / all | density_only | cost_only | retail |
| APC | adapt / all | density_only | cost_only | retail |
| RNR | record_only / all | density_only | active | no_relief |
| ANR | adapt / all | density_only | active | no_relief |

Twelve arms × twelve worlds = **144 held runs**. Every enrolled world enters
each applicable contrast, including worlds with zero mechanism activation.
No effect-dependent seed replacement, trimming, pilot-schedule enrollment or
post-treatment activation conditioning is allowed.

## Exactly what each intervention changes

`density_only` sets only the **additional public-health** multiplier to one.
It retains epidemiology's existing measured population/carrying-capacity
density and urban terms. X1's motive-classified spells remain observations,
not a housing/contact mechanism. Its separately dated unique recent-residence
arrival counts are diagnostics only; no new susceptibility effect is invented
from them. The `legacy_displacement` arm explicitly retains the old additional
`1 + 0.25 × classified_displaced_share` path under the same rules-3 source.
It is not an exact rerun of old CW6, whose rules-2 record-only mode also removed
D3 inputs.

The four `no_*` arms are **marginal deletions from the complete AD context**:

- `no_migration_experience` suppresses applied personal refusal/quick-departure
  penalties, retaining their would-be observations and active D3 inputs.
- `no_information` disables the native migration-destination information gate;
  would-be source masks remain diagnostic. This is specifically migration
  information. Own trade packets belong to the trade component below.
- `no_work` accepts new work/training offers and supplies no personal choice
  exclusions, while retaining would-decline observations, work/intake records
  and existing commitments.
- `no_trade` restores the unchanged trade destination planner: it removes both
  the personal packet gate and own failed-destination refusal, while continuing
  to record closed-shipment experience. It does not disable physical trade.

They are not additive isolated effects and do not identify all interactions.
The native receipt describes the combined installed input, not a causal
attribution of each realized move to a particular score. In rules 3,
record_only may legitimately have nonzero D3 input and a nonzero combined
native choice-change diagnostic.

Public-health `cost_only` retains real wages, farm time, patient food,
reports and guards; it suppresses the care CFR and sanitation benefits.
It retains the selected crowding basis. Quarantine closure/channel settings
remain fixed. Cost-retaining rules do not guarantee equal realized spending
after population, disease, advice and funding respond; actual costs and
service delivery are reported beside outcomes.

`no_relief` is an existing **joint food ownership/free-pool allocation regime**:
the titled harvest share changes from 0.9 to 1, and the extant free pool uses
L2's allocation regime without the retail means test. Existing commons and
public-granary releases can still supply free rations. The native mode-1
receipt must have zero retail-priority households and zero food sent through
that retail-priority branch; observed free rations remain recorded.
It does not create food, change the retail enrollment boundary or disable
titled trade. It is not a pure price intervention, an equal-spending control
or removal of commons or public-granary relief. `free_exchange` is deliberately
not used: it changes prices/income and is incompatible with titled trade.

The eight-turn development schema check at source `8de171fd` exposed the
earlier draft/extractor's incorrect assumption that this mode erased free
rations. Ten template-arm checks passed before RNR was rejected; the failed
output is preserved at `dev-schema-8de-v1`. The correction follows the existing
native `provisioning.rs` mode-1 implementation and its positive-free-pool
regression. No simulation physics or held outcome was changed to fit the
draft. Native population counts are also required explicitly: missing,
negative, fractional or Boolean counts fail extraction instead of silently
claiming zero unobserved household access. Missing public-grain observations
also fail rather than reporting zero releases.

## Primary and secondary comparisons

The three primaries, each evaluated separately in both strata, are:

1. `cwr_food`: **AD − RD** cumulative regional food-availability shortfall.
   Definition is unchanged from CW6: sum over region-turns of native demand
   times `max(0, 1 − min(1, sufficiency_after_relief))`.
2. `cwr_epidemic`: **AD − RD** cumulative recorded epidemic deaths from the
   existing epidemic authority, checked against every tick's care/death rows.
3. `cwr_crowding_interaction`: epidemic-death difference of differences
   **(AL − RL) − (AD − RD)**. This identifies the interaction of personal A6
   with the additional legacy X1 multiplier in this corrected source, rather
   than a pure movement motive, a clinical effect or an old-source replication.

Primary raw totals avoid presenting a post-treatment population denominator
as a complete welfare measure. Per-1,000-person-turn rates, final population
and population trajectories are supporting observations and are reported
alongside raw counts. A survival/population change can affect both raw totals
and their denominator; opposite signs must be retained and explained.

Prespecified secondary contrasts include:

- AL − RL, RL − RD and AL − AD, plus the food-shortfall interaction.
- MX/IX/WX/TX − AD, each a component deletion in the full context.
- APC − RPC, RPC − RD, APC − AD, and the interaction
  (AD − RD) − (APC − RPC).
- ANR − RNR, RNR − RD, ANR − AD, and the interaction
  (AD − RD) − (ANR − RNR).

The fixed harm panel includes population, treasury, household balances/Gini,
regional food shortfall, priced-out person/child-turns, epidemic mortality,
all migration and forest. Famine-cause and all-war-cause deaths remain
unrecorded unless a reviewed authority supplies them; they are not zero and
are not reconstructed by adding overlapping native/campaign/epidemic counts.

**Food availability is not household access.** The native sufficiency field
measures commons plus owned availability. Separately report actual retail
provisioning deficit, priced-out and offer-short deficits, rations, free
rations, paid money, replaced income and observation coverage. A populated
region without a provisioning observation makes the complete access measure
unknown; observed subtotals and missing counts remain visible. Report actual
native production/consumption and public releases, paid work/farm time, care
food, ration demand/consumption and trade deliveries rather than inferring a
cause from co-occurrence.

## Validation, missingness and uncertainty

Before held execution, constructed failures and the actual full pilot must
exercise the new extractor. It validates requested source modes/rules/channels,
complete turn ranges, seed/stratum/horizon, native A1 closure and continuity,
physical food/ration/cargo/escrow closures, finite cash/carry envelopes, prior
price dates, T−1 source dates and untruncated Arrow migration/death counts.
Record-only controls must not suppress active D3 inputs. Personal channel
activation and actual merged/clamped native inputs are checked where complete
component samples permit; truncated samples remain explicitly unverified,
not fabricated individual causal effects.

PH arrival diagnostics are checked against the preceding X1 frame. Ratios
remain null unless coverage and the full rolling twenty-write window are
complete. The observed-subset counts are not converted into a lower-bound
ratio or an invented displaced population. Births, if discussed, come from
native/A1 authorities, not X1's legacy first-seen `newborn_rows` label.
The neutral density-only added factor is a current-turn configuration;
legacy displacement's factor cites the prior frame. Their explicit
`crowding_source_turn` fields must preserve that distinction while all factual
arrival observations retain their T−1 date.

Report every world-level paired value, n, mean, min/max and positive/negative/
zero counts, separately by stratum. Enumerate all 64 paired sign flips for
each six-world contrast as descriptive information, not a significance test.
Also report an empirical paired-world 95% bootstrap interval using 10,000
resamples and fixed analysis seed 20261107. Resample whole worlds jointly
across their arms; never count individuals or region-turns as independent
replicates. At six worlds these intervals are unstable and describe the
empirical sample, not qualification or model/clinical validity. No result
threshold promotes a default or selects a favorable model.

Zero infection gives zero observed raw deaths, while ratios with zero
infectious-person-turn denominators remain undefined/null. Legitimate nulls,
sample caps, inactive mechanisms, adverse signs and failed/unrun cases are
retained. Invalid schemas are extraction failures, not favorable zeros.

## Timing, execution and freeze gates

Use one simulation process, `RAYON_NUM_THREADS=1`, and preserve the offline
110-second chunk limit. Reserve resources with the lead so native builds,
profiles and the held screen do not contend. Pilot all twelve arms at both
registered timing worlds (24 runs) on the final source, interpreter and native
artifact. Include both simulation and extraction in the projection and apply
the generic runner's fixed 1.5 margin before the two-core-hour cap.

If the complete pilot does not fit, do not start held seeds. Record and review
any pre-held budget/design amendment, preserve its failed timing gate and
freeze again. Do not change horizon, controls, outcomes or extractors in
response to held outcomes, and do not raise the cap after a held run starts.
Remaining runs after exhaustion are explicitly unrun, never replaced seeds.

Retain the frozen commit, imported source/extension paths and hashes, command
lines, runner/module/registry/preregistration identities, failures, timing,
strict checks, compact metrics and reports. Preserve at least the first world
of each stratum for all arms, plus event sidecars, for source-bound readback.
Enabled exact resume through migration, health, work, war and transactions,
both-reference feature-off identity, real browser journeys and declared-scale
before/after profiling are separate integration gates; a completed bounded
screen does not substitute for any of them.

## Executable commands, after integration and reservation

The code is in `scripts/cw_rework_screen.py`. Use the final verified native
environment and a new output directory. These commands do not authorize held
execution while this document is DRAFT:

```sh
PYTHONPATH=src python scripts/cw_rework_screen.py check --screen CWR1
PYTHONPATH=src RAYON_NUM_THREADS=1 python scripts/cw_rework_screen.py run OUT/pilot \
  --screen CWR1 --cohort pilot --jobs 1 --keep-first
PYTHONPATH=src python scripts/cw_rework_screen.py check --screen CWR1 \
  --cohort pilot --metrics OUT/pilot/metrics.jsonl
# Only after source/extension/pilot review and this protocol's FROZEN receipt:
PYTHONPATH=src RAYON_NUM_THREADS=1 python scripts/cw_rework_screen.py run OUT/held \
  --screen CWR1 --cohort held --jobs 1 --pilot OUT/pilot/metrics.jsonl --keep-first
PYTHONPATH=src python scripts/cw_rework_screen.py report OUT/held/metrics.jsonl --screen CWR1
PYTHONPATH=src python scripts/cw_rework_screen.py check --screen CWR1 \
  --cohort held --metrics OUT/held/metrics.jsonl
```

## Frozen source and complete-pilot receipt (2026-11-07)

The final simulation/runtime source is
`8792be88dd36ba4d7c22e480de6a19dd64ea1300`, a clean immutable checkout at
`/workspace/cwr-final-runtime`. Later docs-only freeze/integration commits
are distinct from this runtime reference. Maintained feature defaults remain
A6 rules 2 and PH `legacy_displacement`; all experimental arms retain their
explicit flags above. No control, outcome, horizon, cohort or simulation
parameter changed in response to pilot outcomes.

The independent core/source review, the native/bridge and adversarial
regressions, and the ten-case exact-output optimization admission approved
this runtime. The imported interpreter is `/workspace/cwr-native/bin/python`
(CPython 3.13.5). The compiled native SHA256 is
`b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd`;
all 57 unique Rust/Cargo/build inputs and the native crate pyproject matched
the fresh-build receipt (input digest
`f55df55d453ac37694410246c4a9728c56f3f6148f679fde8efc21ffd8775acf`).
The imported source/extension paths and hashes were verified before and
after the complete pilot.

Frozen evidence identities:

- Generic runner SHA256:
  `5ded5f3548bb6403b1df25e9d31e5c5ce638631aa5fd1b4fabdcfb8510b5cadb`.
- Screen/extractor SHA256:
  `f8409b1b76be49dbff968323f9eee2f65229e5c1280e0c349fe2e2a3927e4fef`.
- Registry cohort-content SHA256:
  `62ce5aa81170da9efa52c56340ef8719f78eae9dfe612459f798195efb3cc446`;
  append-only collision-free reservation commit `8de171fd`.
- Pilot source identity:
  `96f1efadb8e2a73158c0ba1a952b623f8235dd84d07f492c55503543cb9edea3`.
- Complete pilot metrics SHA256:
  `05e9e8d8fe3796604329a9d24eb8b94223f2391f462658d0f5d82cd7ba2e8d1e`.
- Published report SHA256:
  `a43804e38697f493c87ad56b3bd594d594c9e9119e42397a0a96de2a1b48d08d`.

The official pilot at
`/workspace/evidence/cwr-evaluation/pilot-8792be88-v1/` completed
**24/24 successful, strictly validated 120-turn cases**, all twelve arms on
shared timing worlds t5/p19. It ran one sequential simulation job with
Rayon, OpenBLAS, OMP and MKL thread counts all set to one. The exact launch,
check/report commands, retained nulls/harms, source and all raw bundles and
Arrow sidecars are preserved in the
[pilot evidence](../audits/connected-world/rework-cwr1-pilot/README.md).
The [independent stdlib audit](../audits/connected-world/rework-cwr1-independent/pilot-review-2026-11-07.md)
passed the exact matrix, identities, control implications, rates/nulls, planned
core/component/health/food contrast arithmetic and six rendered primary rows. The report's stdout was published byte-for-byte as
`report.md`; the original launcher receipt and its null report-hash field
remain unchanged, with a separate publication/hash receipt.

Measured simulation **484.7 s** plus extraction **68.5 s** totals
**553.2 s**. Six held worlds per stratum therefore project to
**0.922 core-hours**; the preregistered fixed **1.5** margin gives
**1.383 core-hours**, below the unchanged **2.0 core-hour** ceiling.
The actual fresh runner subprocess measured 553.267015 s of descendant CPU
and 556.096743 s wall. Peak 1,145,972 KiB is explicitly the maximum of a
single waited-for child/descendant, not simultaneous process-tree RSS.
No budget or timing amendment was needed.

The generic held runner must still verify this exact protocol hash, native,
source/module identities, registry-content hash, complete matching pilot and
live budget at execution. No held seed was spent by the pilot or this freeze.
The 120-turn, 12-world bounded held screen remains distinct from both
restricted qualification gates and from default promotion.
