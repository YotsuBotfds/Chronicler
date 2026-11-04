# Crisis integration qualification — 2026-11-03

This is a bounded release record, not approval to merge, deploy, promote default
features or claim scientific efficacy. The integration starts at
`63581a9a1a1297396ce2227ac2683aeefd5ad8a3`; this initial record was prepared from
`6e33a4490e36e2e6407a4dbef8e735a452891cb4`. The original workspace, other
branches and private backups were preserved. Inaccessible work from the earlier
cloud task is not claimed recovered.

## Build and packaging evidence

Fresh source builds use Python **3.13.5**, Rust **1.99.1**
(`58cf8f9c3 2026-10-13`) and maturin **1.16.0**. The initial and integration
commits above have identical Python package and native source trees:

| Input | Git tree |
| --- | --- |
| `src/chronicler` | `b3ccf346a25e0c7beacbc4e59e81c8bafcf8ec17` |
| `chronicler-agents` | `543df3bb74804c71cf16046a7cac8f43ea9bfe45` |

`uv lock --check` passed. The Python wheel was built with `uv build --wheel`,
installed into a fresh environment and exercised outside the checkout. The
native wheel was freshly built with `maturin build --release --locked` and an
isolated Cargo target directory; no shared wheel or existing environment was
replaced. The compiled `chronicler_agents.chronicler_agents` submodule and the
three real classes `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator`
were verified after installation.

The local build's native source tree stayed fixed, while the checkout advanced
to documentation checkpoint `5bdb783d`. This local receipt binds the native
tree and binary, not an immutable whole-checkout producer commit. The frozen
qualification below separately verifies source identity; GitHub's builder and
consumer receipts must establish the final exact-head CI provenance.

| Artifact | SHA-256 |
| --- | --- |
| `chronicler-0.1.0-py3-none-any.whl` | `96d5fad09bc54c713dea3c646c22d0d78788cf26f69c0fc9bf3034490a848898` |
| `chronicler_agents-0.1.0-cp313-cp313-manylinux_2_34_x86_64.whl` | `095dd62906c75bf00e38b451ac4ab575cd446331a91f1cc0b307d34ced3b0f19` |
| Installed native `.so` | `d15cb4c3f7e71778ce9127688486aba85a01459c344dcbb3dfd8e3331e824b8d` |

The installed Python wheel passed `chronicler --help` and a seed-42, four-turn
`--agents off --simulate-only` run with default feature settings. The run
completed and wrote a viewable bundle. The installed Python/native wheels also
completed a separate 20-turn, eight-region/four-civilization hybrid run with
these explicit options:

```text
--grain-reserves --grain-storage --grain-storage-policy maintain
--grain-storage-work-budget 1 --household-mobility-liquid-requirement 10
--scholarship --techniques --academy-services --contact-ledger
--harvest-forecasts --harvest-report-delay 2 --health-care
--transaction-receipts --simulate-only
```

That run proves configuration, execution and serialization with those controls
enabled. It does not prove every optional mechanism was exercised or establish
their benefit. No narration service was called and no default setting changed.
The installed-wheel checks cover runtime packaging; repository-only scenario
helpers are exercised separately from the source checkout.

## Rust and local environment correction

`cargo test --locked --manifest-path chronicler-agents/Cargo.toml --quiet`
passed **1,203 tests, two ignored** across 37 test groups. The first attempt
failed at link time because this environment provides
`libpython3.13.so.1.0` without the unversioned `libpython3.13.so` name expected
by the linker. The successful retry used a scratch-only symlink to that same
installed library and `LIBRARY_PATH` pointing to it. Source, shared environments
and system library directories were unchanged. Both logs are retained; the
initial environmental failure is not counted as a passing attempt.

The existing unused `best_migration_target_for_agent` warning remains. This
build is Linux x86-64 evidence; no new Windows, macOS or other-CPU binary
qualification is claimed.

## Security and dependency observations

The bounded source review confirmed the existing localhost WebSocket binding,
viewer-origin allowlist and constant-time session-token comparison, plus the
what-if checkpoint path, symlink and size checks. Tracked-filename inspection
found no `.env`, credential/private-key, database or exact-checkpoint artifacts.
A credential-pattern scan of tracked non-test source found no matches. These
checks do not constitute a comprehensive history or vulnerability audit.

`npm audit --package-lock-only --json` reported **12 moderate development
dependency findings, zero high/critical**. The underlying advisory is
[minimatch globparts amplification](https://github.com/advisories/GHSA-g3hv-75wg-m249),
with effects propagated through the lint toolchain. The separate
`npm audit --package-lock-only --omit=dev --json` reported **zero production
dependency findings**. No dependency versions were changed: npm's suggested
remediation includes a semver-major `typescript-eslint` downgrade and an
unavailable automatic fix for one lint plugin, so blind `npm audit fix` is
not suitable evidence of a safe correction. The development advisory remains
a documented limitation for review.

## Final integration gates

The initial frozen local qualification source is
`9d01c8d8a769fb934818f091a6d1d3930b8cb1d6`. The complete native failure below
led to a separate repaired, clean detached source at
`d6026b43582cc4e0d85ccc64d5a7adc0099caf58`. Both Python and native runtime
trees still match the build inputs above. Final
documentation may advance separately; the PR's exact final-head CI must still
be read before merge approval.

The nine successful jobs in
[run 41510735220](https://github.com/YotsuBotfds/Chronicler/actions/runs/41510735220)
were freshly re-read and bind exactly to the **starting** commit `63581a9a`.
They are not final integrated-head CI.

The intermediate `9d01c8d8` also passed all nine Tests jobs in
[run 41721377854](https://github.com/YotsuBotfds/Chronicler/actions/runs/41721377854).
Its green sharded CI did not override the failing unsharded local native
result below; that cross-module pollution still required correction and a
complete rerun.

| Gate | Standing at this draft |
| --- | --- |
| Complete native Python | Repaired frozen `d6026b43`: 9,742 passed, six unchanged registered skips, 623 successful subtests; zero failures/errors, 640.41s |
| Complete no-native Python | Repaired frozen `d6026b43`: 9,308 passed, 402 skipped, 623 successful subtests; zero failures/errors, 397.48s. Earlier `9d01c8d8` also passed separately in 416.16s |
| Bounded offline Python chunks | Frozen `9d01c8d8`: all 55 chunks passed; 5,771 cases plus 97 subtests, 69 skipped / two deselected, 235.47s |
| Viewer tests, lint and TypeScript/Vite build | After the Finance clock correction, 1,175 tests / 108 files, zero skips; lint and build passed at `93334a1c3307cb9e5f54d3d3e8d6e25663ab6ee9`, viewer tree `be79d9c1b5848765fd6abe04e147be301942ef07` |
| Actual desktop/mobile comparison and gallery browser checks | Chromium 154, 1,440px and 390px; actual receiving bundles, gallery, dated services, unknown observations and private-path-free export passed |
| Held evaluation | Twelve integrated trajectories replayed with identical initial witnesses, metrics, coverage, per-turn regional distributions and scored-report evidence; see declared scope below |
| Nine-job GitHub CI | Final verdict is the [PR69 head/check list](https://github.com/YotsuBotfds/Chronicler/pull/69/checks), not the historical runs above; final-source CI had not run at this document capture |
| Scientific 200-seed/default-promotion gate | Not run by this integration; no promotion claimed |

The earlier 1,171-test viewer check started at `db51b8ea` and ended at
`5bac0804`; its viewer tree `2bf683b7` stayed unchanged. Desktop/mobile
viewport and keyboard-scroll checks had
no page errors or document overflow. Missing food observations remained
**Not recorded**, and absent native delivery remained **Not observed** even
when requested work was zero. Six additional debt-inspector browser cases
cover the actual native debt export and explicitly labelled constructed UI
edges at both widths. Those edges are display tests, not simulation outcomes.
Physical devices, assistive technology and a full accessibility certification
were not tested.

Independent review subsequently found the Finance summary's inconsistent
source/completed-tick boundary. Its bounded correction and four added tests
passed the complete 1,175-test viewer gate above. A separate Finance browser
check used source `44c760c9`; its Finance component SHA-256
`28185885816ee38286541a4a7ffbfb9e16641488e85e477332ee6f8673b0894d`
matches the later qualified source. The gallery browser run was not repeated
after this change: only the Finance component and its existing system-panel
test file changed since that run. This is combined evidence from matching
component sources, not a claim of a new whole-viewer browser session.

The held replay ran from clean `db51b8ea` with the native hash above. Its six
matched pairs use seeds 202, 303 and 404 for the declared care and forecast
families; they reproduce the first run's recorded results, including neutral
and adverse outcomes. That is a small held evaluation, not a general policy
ranking or a held test of every crisis mechanism. Separate source-bound
transport and academy examples were audited, then all four arms resumed
exactly: world, history, native state, Python/NumPy RNG and interventions
matched. Their full initial histories remained intact. See the
[scenario admissions](crisis-scenarios.md),
[receiving-service reproduction](receiving-service-resupply.md),
[held declaration](crisis-held-evaluation-2026-11-03.md) and
[held results](crisis-held-results-2026-11-03.md) for the actual admissions and
limitations.

The initial **unfrozen** no-native diagnostic returned 9,297 passed, 401
skipped, 623 successful subtests and two failures in 453.65 seconds. One failure
caught the forecast walkthrough changing a historically pinned source file;
the other caught the newly registered held module missing from the explicit
partition test's additions/count. A subsequent broader guarded source check
also caught the gallery changing the pinned comparison component. The source
corrections use separately reviewed exact inverse layers with whole-file and
parent digest admission plus mutation refusals; the historical fixtures stay
unchanged. Module additions retain the original 300-module ownership digest,
six historical native skips and 623-subtest seal. The failed logs remain
retained; this diagnostic is not final immutable test evidence.

The first complete **unsharded native** run on frozen `9d01c8d8` later reported
9,724 passed, 18 failures, six historical skips and 623 successful subtests.
That failure remains retained, independently of any green sharded CI. Test
module/import and thread-environment pollution was identified and corrected
in three existing test files. The import probes now restore both `sys.modules`
entries and package attributes to their exact original objects. The merchant
test previously changed an environment variable after Rayon's global pool
could already be initialized; that did not establish a real thread change and
also discarded the caller's setting. It now runs fresh CLI children requesting
one/four workers, binds the native binary and checkpoint environment, requires
20 real merchant observation rows, and compares complete history, world,
events and native final-state sections while preserving the parent's environment.
Ordered before/after victim checks pass (25 native/import cases, nine pure
import probes and 48 thread/continuation victims). The subsequent complete
repaired native run passed as recorded above. Its supervisor verified unchanged
source/runtime identity and the actual compiled binary before and after. The
six skipped node IDs match the canonical registry exactly, with the unchanged
623 successful-subtest seal. No production runtime identity check, native
fixture, skip seal or simulation behavior was relaxed.

The repaired native result SHA-256 is
`1b98d1620efdab1a8953dce7f5db0d67b52ab5124a2bdd2b3155078e9bcc6024`;
its pytest log SHA-256 is
`f15016a0266908fcd9bad2fb70d7f8839d837453053d4f70afdbe7851aea7704`.
The native and no-native retained log/JUnit hashes were independently recomputed
and matched their supervisor results. Final CI's producer/consumer and
exact-once shard-ownership audit remain separate from this unsharded local pass.

The final native lane must retain the existing fixed-module ownership,
historical-skip and successful-subtest seals. New modules require explicit
registration; a missing native import cannot be accepted as a new skipped
native test. The guarded offline lane remains a separate oracle, with its
110-second per-chunk limit and blocked native/network/subprocess access.

The no-native supervisor verified native absence and identical source/runtime
identities before and after the complete run. Its result SHA-256 is
`2d4bb96b2aeb8d68b567f5481abe61b7ff5bf93d2b086b769524f8f3da54c290`;
the complete pytest log SHA-256 is
`a5c9be68b69de29193af805dc9e3c25e95f1530918105425e1702dbbc58baf75`.
The offline run loaded no native modules, blocked 394 native-import attempts
and recorded no blocked IO attempts. Its slowest chunk took 34.13 seconds,
within the unchanged 110-second limit. Both lanes retained the existing
Pydantic warning from an intentional invalid-input test. Offline skips and
explicit exclusions do not qualify the full native or POSIX/socket/subprocess
lanes; the complete no-native lane remains distinct.

The later CI failure is a separate provenance issue:
[native shard 0 in run 41723818009](https://github.com/YotsuBotfds/Chronicler/actions/runs/41723818009/job/126224612758)
refused the wheel **before pytest**, when the floating Python setup selected
3.13.18 for the builder and 3.13.17 for a consumer during a patch rollout. The
consumer's strict identity check was preserved. The subsequent workflow repair
pins all three native producer/consumer setup steps to CPython 3.13.17, with a
regression in an existing test module. Those workflow/test changes and later
wording corrections are outside the frozen `d6026b43` local-suite identity;
exact final-head CI must qualify them. The Finance source is already included
in `d6026b43` and has its separate viewer/browser evidence above. A receiving-case
label was also corrected to two suspended economy phases (counter sequence
2, 1, 0), without changing the input, countdown, model timing or observed runs.

Build/test artifacts and private evidence remain outside Git, initially under
`/workspace/scratch/`: `chronicler-native-build-receipt.json`,
`chronicler-release-wheels/`, `chronicler-python-wheels/`,
`chronicler-wheel-smoke/`, `chronicler-wheel-native-smoke/`,
`release-rust.log`, `release-rust-retry.log`, `release-no-native.log/xml`,
`release-npm-audit.json` and `release-npm-audit-production.json`. These are
session locations, not a claim of durable remote artifact publication or fresh
environment recovery. The release handoff must state the final commit, exact
CI result, retained evidence and remaining limitations before Tate decides
whether to merge.

Integrated scenario/browser evidence is retained separately as
`crisis-final-viewer-receipt.json`, `crisis-final-ui-browser.json`,
`chronicler-final-finance-viewer-receipt.json`, `debt-browser/report.json`,
`debt-browser/finance-clock-report.json`,
`crisis-held-integrated-replay-receipt-20261103.json`,
`integration-crisis-example-audit-20261103.json` and
`integration-crisis-replay-receipt-20261103.json` under the same scratch root.
The frozen no-native supervisor's request, result, JUnit and log are in
`chronicler-repaired-no-native-20261103/`, with the earlier `9d01c8d8` pass
retained in `chronicler-final-no-native-qualification/`; the offline receipt, per-chunk
guards/logs and summary are in `chronicler-final-offline-9d01c8d8/`.
The complete repaired native result, JUnit and log are in
`chronicler-repaired-native-20261103/`; its failed `9d01c8d8` predecessor remains
retained separately. This document records completed local checks and pending
exact final-head CI at publication time; consult the final PR check suite for
that later decision.
