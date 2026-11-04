# Harvest target correction: development results

The [prelaunch registration](harvest-target-correction-development-2026-10-28.md)
was committed as `b62eed3f77ca38a35ea680a7dae7b4c659a3ec14` before launch.
Its exact bytes were supplied to the runner. The original negative-target
bundle and all 24 earlier study bundles were preserved.

Eight fixed executions completed: seeds 42–43, template 8-region/4-civilization
worlds, horizon 40, fork 4, one parent and normal/withheld/shuffled continuations
per seed. The durable supervisor recorded launch at `2026-10-28T20:10:41Z`,
completion at `20:11:14Z`, and exit 0. Its 33.10-second wall duration describes
this shared host, not a performance benchmark. One worker and thread caps of
one were used. Both registered resource/population debug options were enabled.
No rerun, replacement seed, numeric tuning or registration amendment was used.

## Mechanical evidence

- All eight executions reached turn 40. Source, package, native binary and
  external runner identities stayed unchanged and matched the registration.
- Actual schema-2 worker environments were captured before/after each run,
  remained stable and matched within all four paired contrasts. The parent
  environment was disclosed separately.
- All eight expansion audits scanned the complete recorded forecast history
  for completed turns 0–39: **0 errors, 0 warnings, no scan truncation**.
- All **446 recorded preparation rows**, including repeated parent/no-op
  trajectories, had finite nonnegative increments, matching granary receipts,
  targets at least their recorded baseline and correct baseline-plus-increment
  arithmetic at the registered tolerance. These rows are not independent trials.
- The strict comparator admitted **4 of 4** normal-versus-control contrasts
  for completed turns **4–39**, with no blockers. Both normal continuations
  matched their parent's exported final Python world. That no-op check does
  not certify the native pool or every output file.

The earlier seed-43 shuffled `harvest:2:0:6` preparation at source turn 32 was
absent from this trajectory. No recurrence was observed; this does not show
that the exact old failure opportunity was exercised. The new source and
binary contain other changes, so a difference from the original study cannot
be attributed solely to the target correction.

## Descriptive post-fork exposure

Parents repeat the normal trajectory and are excluded from this table. Grain
and funds are recorded purchases during warning periods, not attributable
excess spending. Every issued report in the table also closed in the window;
closed includes unscored outcomes.

| Seed | Arm | Issued | Delivered | Scored | Mean recorded Brier | Preparation rows | Positive payments | Grain bought | Funds paid |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 42 | normal | 17 | 17 | 16 | 0.209265 | 79 | 7 | 89.595867 | 15 |
| 42 | withheld | 16 | 0 | 14 | 0.174289 | 0 | 0 | 0 | 0 |
| 42 | shuffled | 18 | 18 | 16 | 0.227556 | 82 | 4 | 68.283678 | 11 |
| 43 | normal | 21 | 21 | 20 | 0.168844 | 67 | 9 | 112.391390 | 19 |
| 43 | withheld | 22 | 0 | 22 | 0.162192 | 0 | 0 | 0 | 0 |
| 43 | shuffled | 21 | 21 | 20 | 0.180890 | 72 | 13 | 145.289601 | 24 |

Withholding exercised the no-delivery/no-preparation mechanism. Shuffled arms
had fewer warning-period purchases than normal in seed 42 and more in seed 43.
Scores use differing report sets and policy-sensitive production/demand
outcomes; the observed values do not establish predictive skill, economic
benefit or an exogenous hazard. The two known repeated seeds remain development
evidence. No significance, efficacy, promotion or full milestone gate is claimed.

## Retained identities

Generated artifacts, per-run hashes, full audit reports, commands, environment
receipts, supervisor logs and comparator output are retained externally. No
private evidence paths or generated bundles are committed.

| Artifact | SHA-256 / commit |
| --- | --- |
| Registration bytes | `1b83ccc4d7424b5e1005e20b99ac85d1edf444c06da3962a9aa114b33aea6910` |
| Simulation | `d051d7c06b1a490841d148b8906bde22f2f5d0f0` |
| Python package digest | `c14bc2f0178139b58d778926e1f803597ee0856958b02da67882b851845c8129` |
| Native binary | `fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317` |
| External runner | `b2f691f6ce1b9b7dfc4245d9e1951104e09de68aabafee19a2e1e81c94abee61` |
| Completed experiment manifest | `fbbe04766fb6502e8bd8003bc6b6e111d6cd3139f6e7c4593762bbc4db817109` |
| Observer tooling commit | `461d0b7e` |
| Readout JSON | `57016036e413343edd163f9010c863ba52121e57285b121eeb620f8f8c0dfba8` |
| Strict comparison JSON | `10ee17892d2254fdc2b20b9d5a5d18aa8abb2745b424527062ff3f99a01a3130` |

The observer readout's unused `base_above_warning_cap` field does not establish
cap exposure; demand/cap exposure was not reconstructed. Acceptance uses only
the registered finite/nonnegative and recorded-target arithmetic checks above.
