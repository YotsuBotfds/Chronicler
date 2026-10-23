# Private integration wave, 2026-10-05

Seven independently reviewed changes are integrated locally on
`private/integration-20261005`, based exactly on
`edf72991cad58d6670b1f382c33d50d903a6054a`. No public push, merge, default
promotion, source-owner branch edit, or external artifact write was performed.
Fishery/mutual-aid, fertility, governance kernels, and private science baseline
`b665e198` are outside this wave.

## Source and integration identities

| Lane | Exact source commit | Integration commit |
| --- | --- | --- |
| Hostage intelligence | aa30fccfeac22949df63e1bf3abd1e1e1e33fd8e | bbd1c036dc24700015fdd1464bdf466252ef9397 |
| Tradition cooldowns | 61843da1f3e9e6a84af97cb6a9710004845a139d | 711a19df3c33bb71834d9d3fd983c5913a132c6e |
| Evidence admission CLI | ba9a4708ba007c78b845095eb169c93509b31b20 | 37a83e127df05a14e7963eaade393634516aba76 |
| Experiment inspector | 7c2fd7b580ff45f2e6758081186f423bfb704d15 | eef57198aba656c5e61efd7527d089850774232d |
| Exact snapshot performance | ee5612c943581d88a1cb0bc00c16919a23d6cd82 | d44945c40a4540291e194302d06f788ad7744ba0 |
| Python checkpoint replay | 2596335f97a680684d90defc1398dc6ab879e94b | 05b7559a618443a20b29ab9fe8b3aae503b758e0 |
| Mercenary disband | d758203c7f50046dddf3318fd0ba91087d899836 | 78430c02059a7fadab38dbd33594c4d4daf01cbd |

The source refs are preserved under `refs/integration-sources/*`. Every input
was read through Drive metadata, fetched as authenticated raw bytes with inline
base64 disabled, and downloaded into this executor using the returned file
reference. Whole-file SHA-256/size, safe archive paths, manifest member hashes,
source scopes, base prerequisites, and exact source commit objects were checked
before applying changes. The performance archive's 139 nested evidence members
were also checked. Admission and performance mail patches reconstruct the exact
supplied commit SHA with their author/committer date; new local bundles preserve
those authenticated objects. Supporting mercenary config/lock/conftest files
match the base and were not imported as changes.

All cherry-picks applied without conflicts. Git automatically combined the
hostage `compute_accuracy` correction and the performance noise-helper extraction
in `intelligence.py`. No manual conflict resolution was needed. Source code in
the integration matches the reviewed input bytes except this deliberate
composition of the two changes. Integration commits add tests, independently
captured corrected-state oracles, and checkpoint-boundary documentation.

## Exactness and expected behavior changes

The three reviewed corrections retain their scoped behavior: an alive active
hostage on the captor roster supplies one directional +0.3 contact source;
martial generals and diplomatic merchants become eligible after 18 elapsed
turns; expired hired mercenary companies disband instead of re-entering the hire
pool. The population/Gini/gate implementation from PR13 and the native subtree
remain byte-identical to the base. Production defaults and dependency/lock files
remain unchanged.

The pre-performance corrected baseline is
`423a67ce4a55dbce5ce131146736ac2bafdbab8e`: the four initial lanes plus the
mercenary correction. Its exact source hashes are pinned in
`tests/fixtures/performance/corrected_423a67c.json`. The original edf7299 and
intermediate eef5719 fixtures remain preserved. All 120 complete turn hashes,
ordered RNG primitive traces, and complete generated artifact files match this
corrected baseline exactly after performance integration. No output fields are
removed, rounded, or compared with tolerances. The harness sets the same
`generated_at` timestamp before generating both artifacts.

The single-civilization workload is fully byte-identical to public main. In the
standard and wide historical workloads, the hostage correction changes only
snapshot intelligence/perception fields; reverting that correction independently
restores the old snapshot and RNG oracles. A separate snapshot regression uses
actual capture, release, recapture, death, and synthetic capture, comparing the
optimized path to live accuracy recomputation across complete snapshots, RNG
traces, and output artifacts. No cached accuracy crosses a turn or callback.

## Validation and independent review

The available no-Rust Python suite passes: 3,082 non-slow tests and 47 subtests,
with 121 skips. The separate slow suite passes 5 tests with 5 skips; exact
commands and limits are recorded in the delivery evidence. The final focused contract run passes 183
tests; earlier broader lifecycle/admission/population/Gini checks and the full
suite cover the remaining integrated paths.

Viewer validation passes all 112 tests, TypeScript/build, lint, and Chromium
desktop/mobile QA. Browser checks include original-byte identity with BOM,
missing values and zeros, final-only stockpiles, source paths, region/time/event
filters, artifact reset, navigation, and live-stream exclusion/following. Vite's
existing bundle-size warning remains; no dependency/build configuration changes
were introduced.

Fresh integrated replay traces pass for seeds 1/42/73 through turn 250 with
splits 0/13/249: 488 resumed turns plus three checkpoint boundaries. Seed 42 at
turn 12 instead fails clearly because a real expansion has a pending stockpile
bootstrap. The API and CLI rejection tests preserve input state and write no
checkpoint. Turn 13 completes that bootstrap. The guard and CLI default split
remain unchanged; use the documented split-13 example for this seed. Source
fingerprints invalidate earlier checkpoints as intended.

A read-only independent reviewer approved the six-lane composition and then the
fresh seven-lane composition plus final oracle/replay/doc edits. The reviewer
independently verified input identities, 65 corrected-oracle source hashes,
120 exact snapshots/RNG/artifact comparisons, 360 final focused tests, and the
necessity of the pending-bootstrap rejection. Exact review scopes and file hashes
are preserved in the delivery receipts. Root remained the single writer.

No compiled native extension or Rust toolchain is available in this executor.
Native execution remains unverified here. Timing observations in the exactness
harness are single repetitions under local load and establish no new speedup
claim. The replay envelope supports only its documented Python off-mode path;
native, hybrid, shadow, demographics-only, and incomplete turn boundaries reject.
Admission CLI tests establish failure handling, not admission of any real
scientific experiment or cross-baseline equivalence.

## Draft publication plan

1. Independently verify the delivery archive SHA, member manifest, Git bundle,
   source refs, commit map, review receipts, and exact source/output fingerprints
   against the unchanged required base. Restore into a private checkout.
2. Run the repository's native CI lane with a verified freshly built extension,
   complete Python tests, and `cargo test`. Repeat relevant actual agent-backed
   lifecycle tests. Keep native continuation and speedups outside the claims.
3. Prepare one draft PR against public main describing the three corrected
   behaviors, opt-in admission/replay/inspector tooling, and exact snapshot
   optimization. Attach this evidence and explain the split-12 rejection and
   optional-native limitation. Preserve individual source identities and the
   integration test commits for review.
4. Request separate owner authorization for public push/PR creation and eventual
   merge/default promotion. If the target base has advanced, obtain explicit
   reconciliation approval and rerun the exact comparisons and independent
   review before publishing. This task performs none of those public actions.

The source/test/evidence delivery includes the original seven archives, verified
source refs, integration bundle/patch, changed-file snapshots, logs, exact raw
outputs/traces, replay envelopes/reports, browser screenshots, and hash manifests.
