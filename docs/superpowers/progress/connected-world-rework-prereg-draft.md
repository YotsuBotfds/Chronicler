# CWR1 correctness and causal mechanism screen

Status: DRAFT — no CWR1 held execution is authorized by this draft.

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

Candidate fresh cohort: template 4101–4106 (8 regions, four initial
civilizations) and procedural 4201–4206 (32 regions, ten initial civilizations).
The candidate audit found no collision across 48 available local/remote
registries and restricted ranges. It is not a reservation. The lead must
reconcile the latest registry and commit the actual CWR1 reservation before
execution. The only timing/schema pilot worlds are the existing shared
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

`no_relief` is an existing **joint food ownership/commons-relief regime**:
the titled harvest share changes from 0.9 to 1 and free commons rations end.
It does not create food, change the retail enrollment boundary or disable
titled trade. It is not a pure price intervention, an equal-spending control
or removal of every public-granary relief path. `free_exchange` is deliberately
not used: it changes prices/income and is incompatible with titled trade.

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

Freeze receipt: **not yet available; no CWR1 held seed has been spent.**
