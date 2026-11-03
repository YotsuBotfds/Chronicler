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

The nine successful jobs in
[run 41510735220](https://github.com/YotsuBotfds/Chronicler/actions/runs/41510735220)
were freshly re-read and bind exactly to the **starting** commit `63581a9a`.
They are not final integrated-head CI. No later result is implied here.

| Gate | Standing at this draft |
| --- | --- |
| Complete native Python and strict ownership/skip/subtest audit | Pending final integrated source |
| Complete no-native Python | Diagnostic running; source changed during run, so not immutable final evidence |
| Bounded offline Python chunks | Pending final integrated source |
| Viewer tests, lint and TypeScript/Vite build | Pending final integrated source |
| Actual desktop/mobile comparison and gallery browser checks | Pending final integrated source |
| Receiving-service and held evaluation | See their separate declarations/results; final integration pending |
| Nine-job GitHub CI | Pending exact final integrated head |
| Scientific 200-seed/default-promotion gate | Not run by this integration; no promotion claimed |

The final native lane must retain the existing fixed-module ownership,
historical-skip and successful-subtest seals. New modules require explicit
registration; a missing native import cannot be accepted as a new skipped
native test. The guarded offline lane remains a separate oracle, with its
110-second per-chunk limit and blocked native/network/subprocess access.

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
