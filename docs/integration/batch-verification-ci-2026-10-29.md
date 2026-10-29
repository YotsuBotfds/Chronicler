# Batch verification CI qualification — 2026-10-29

Both exact validation sources below passed all six standard CI jobs.
This record preserves their separate source identities, test counts,
observed clocks and official artifact publication metadata. It does not
rerun tests, build a native extension or generate simulation worlds.

The [JSON companion](batch-verification-ci-2026-10-29.json) retains full
run/job identities, timestamps, selected step clocks, decoded-log hashes
and artifact names/digests/expiry timestamps. Raw logs remain external.

## Exact sources

- `e984be2adc2e6fdf27b4442b852a9e6789b6617b` on `lead/batch-validation-input-set-20261029`: [run 40801509650](https://github.com/YotsuBotfds/Chronicler/actions/runs/40801509650). Reject validation inputs added after their manifest was recorded.
- `ec85795e3d22f1419fe11f8cc40ff71c0541d3a5` on `lead/batch-manifest-reconciliation-20261029`: [run 40802848510](https://github.com/YotsuBotfds/Chronicler/actions/runs/40802848510). Reconcile declared cohort facts with actual bundle identity; preserve repeated-seed determinism.

The second source includes the `4a1d3f08` reviewed validation correction;
`ec85795e` adds only its CI workflow allowlist entry. Its Python package
tree is `5349b37f9be1e0708c1aa6cf53ea25fe967fc643`; both sources retain
Rust crate tree `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`.
Source changes affect validation admission. Simulation physics, the bundle
exporter and Rust code were not edited; manifests still record
their actual source identity. The frozen producer and main remain unchanged.

## Completed checks

Python cells list **parent passes / successful subtests / skips**.
Offline cells list **chunks; passes / skips**. Rust lists **passes /
ignored**, and viewer lists **tests / files**. Both viewer jobs passed
lint/build; each combined native requirement passed after native Python
and Rust. Overlapping lanes and sources are not summed as unique tests.

| Source | Native Python | No-Rust Python | Bounded offline | Rust | Viewer |
| --- | ---: | ---: | ---: | ---: | ---: |
| `e984be2a` | 8,039 / 526 / 6 | 7,725 / 526 / 306 | 32; 3,941 / 65 | 1,088 / 2 | 743 / 69 |
| `ec85795e` | 8,094 / 526 / 6 | 7,780 / 526 / 306 | 32; 3,996 / 65 | 1,088 / 2 | 743 / 69 |

The sidecar repair adds 12 parent cases relative to consolidated review
`1c5728b7` (run 40799038789): eleven pure inventory cases and one integration
case using the existing batch fixture. Reconciliation adds 55 pure cases.
Those exact increments appear in both full Python lanes and the offline
selection; skips/subtests remain unchanged. The preexisting input-inventory
fixture gained valid seed/horizon metadata while retaining its predicates.

The initial 52 reconciliation cases produced 40 failures and 12 passes on
frozen e984. Lead review then caught one diagnostic compatibility failure
at `eace086a` in the complete modified chunk (288 passed, one failed).
The preserved correction reports both the simulation contradiction and
the original short-run diagnostic; its original assertion was unchanged.
Two NUL-path cases and one dual-diagnostic case bring the selection to 55.
The final 55 focused and 292 complete-chunk checks passed before CI.
Original failed receipts and all archived accepted-bad-cohort fixtures
remain retained; no failure was converted into a pass by changing a gate.

## Observed clocks

| Source | Native job | Wheel step | Native test step | Native pytest | No-Rust job | No-Rust test step | No-Rust pytest |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `e984be2a` | 768 | 156 | 585 | 580.94 | 461 | 445 | 439.85 |
| `ec85795e` | 855 | 169 | 635 | 630.89 | 264 | 253 | 249.99 |

| Source | Offline job | Guarded runner step | Sum of printed chunks | Slowest chunk | Validation-tooling chunk |
| --- | ---: | ---: | ---: | --- | --- |
| `e984be2a` | 255 | 236 | 236.3 | systems-2: 40.2/110 | 237 passed; 10.3/110 |
| `ec85795e` | 212 | 196 | 195.8 | systems-2: 33.3/110 | 292 passed; 8.4/110 |

All clocks are wall seconds from one hosted run of each source. Job
clocks include setup/reporting; pytest and rounded chunk clocks exclude
different overhead. Rounded sums need not equal enclosing step timestamps.
The per-chunk limit stays 110 seconds. Source/test changes, cache state
and runner variability prevent treating these clocks as a speed benchmark.

## Published evidence

All eight artifacts were nonexpired and bound to their exact run/source
when observed. The following are **GitHub-reported ZIP digests**; this
readout did not download or independently rehash archive payloads.
They expire on 2026-11-12; exact timestamps are in JSON.

| Source / evidence | Artifact ID | ZIP bytes | GitHub SHA-256 |
| --- | ---: | ---: | --- |
| `e984be2a` python-no-rust | [12866607201](https://github.com/YotsuBotfds/Chronicler/actions/runs/40801509650/artifacts/12866607201) | 140,763 | `1611df1d8ecd0dd0b270643809ad2778b683883d51e90545f2ea1db0d4a4b3c6` |
| `e984be2a` python-offline | [12866078272](https://github.com/YotsuBotfds/Chronicler/actions/runs/40801509650/artifacts/12866078272) | 41,781 | `a925ea219a53b09805c260ac36e0c1e9bcd79e60a889629d159420872557571d` |
| `e984be2a` python-native | [12865968729](https://github.com/YotsuBotfds/Chronicler/actions/runs/40801509650/artifacts/12865968729) | 138,469 | `fea541fe40e72560e2fdf887abf27e6370449b6c109db71fd19e7b6b2e569479` |
| `e984be2a` rust | [12865748667](https://github.com/YotsuBotfds/Chronicler/actions/runs/40801509650/artifacts/12865748667) | 521 | `fc8675673b4fefd36353c3759ba5e795832fac0ab38f9117d40f45780147036e` |
| `ec85795e` python-native | [12867860561](https://github.com/YotsuBotfds/Chronicler/actions/runs/40802848510/artifacts/12867860561) | 139,580 | `1bd996c7b78bffe2fcfd99e494eb29781fa6b534ec2c25f32af31391fff59839` |
| `ec85795e` python-no-rust | [12867231226](https://github.com/YotsuBotfds/Chronicler/actions/runs/40802848510/artifacts/12867231226) | 139,979 | `e95a115738f68caea29be69e6c54c87a43b8ddc5390a716fae7e8089df868119` |
| `ec85795e` rust | [12866976647](https://github.com/YotsuBotfds/Chronicler/actions/runs/40802848510/artifacts/12866976647) | 520 | `495c280112b7cf0caa79a314e17174f0ca6338ac8f3bb1066530cb0fcef86f07` |
| `ec85795e` python-offline | [12866324684](https://github.com/YotsuBotfds/Chronicler/actions/runs/40802848510/artifacts/12866324684) | 41,860 | `0215c930a507a613e5ad579eacd3a41d1ebc44c82f248118aaf3d64eaa664f72` |

The native jobs built fresh wheels under their reported CI interpreter
and checked compiled-module/class availability before pytest. Their actual
binary identity receipts remain in the native artifacts and were not
separately inspected for this pack.

## Boundaries

Normal oracle readers check payload identity at their existing decode;
genuine repeated seeds in distinct files remain valid for determinism.
Valid cohort summaries and explicit legacy-unchecked admission retain
their behavior. No scientific method, threshold, independence policy or
default activation changed.

This CI record establishes no browser-session QA, full scientific gate,
natural optional-system efficacy or simulation speedup. The ongoing
full-gate comparison, saved-output identity, native composition and
forkserver studies retain their separate source/evidence boundaries.
Later documentation-only commits add no runtime qualification.

See the [sidecar-input repair](batch-validation-input-set-2026-10-29.md)
and [cohort reconciliation](batch-manifest-reconciliation-2026-10-29.md)
for the concrete behavior changes and retained failure history.
