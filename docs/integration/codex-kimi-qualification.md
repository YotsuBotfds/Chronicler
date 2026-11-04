# Cloud continuation of the finalized Kimi handoff

The complete bundle restored `7a31e28418ddd2405079631cd86b221af483e614`.
The continuation branch is `dev/codex-kimi-qualification-20261031`. Ordinary
authorized Git publication restored that exact history, including the workflow;
the partial additive Kimi branch was preserved. `main` remains unchanged.

## First supported-runtime results and corrections

Locked Python 3.13.5 runs on the unchanged restored source found the same four
failures in both complete Python lanes:

| Lane | Passed parents | Failed parents | Skipped parents | Passed subtests |
| --- | ---: | ---: | ---: | ---: |
| No native extension | 8,797 | 4 | 362 | 623 |
| Real compiled native extension | 9,160 | 4 | 13 | 623 |

These first results remain failures. They are not passing qualification.

Two failures exposed a compatibility regression in the atomic-save conversion.
`WorldState.save` now restores its original directory probe, `OSError` fallback
and parent creation on the ordinary save path, before the retained atomic writer.
The existing assertions, atomic replacement, budget admission and sidecars remain
intact. The isolated fix passed 182 focused cases and five additional atomic
replacement-preservation cases; independent review found no concern.

The other two failures were stale main-source witnesses. Strict test-only
inverses now admit the exact reviewed atomic-write, admission-helper extraction
and live-interrupt changes. The historical care digest `2e17f965…`, default AST
digest `1a4c739c…`, other nine care pins and historical `BASE` remain unchanged.
The default digest's provenance is correctly labelled as `ff57bf26`, where it
was introduced, rather than its parent `44b9bdce`. Thirteen negative parent
cases reject unrelated body, location, predicate, call and writer changes.
No successful-subtest ownership or offline time limit changed. Independent
review verified byte-for-byte reconstruction of both historical main sources.

The combined three affected modules passed 120 parents and 61 subtests on
system Python 3.13.5. These focused results do not replace full fixed-source CI.

## Native, viewer and actual-run evidence

The restored native source was freshly built with locked maturin and Cargo
dependencies, official Rust 1.99.1 and Python 3.13.5. All three compiled
simulator classes were checked before native pytest. Rust execution passed
1,178 tests with two registered ignores, including
`test_restoration_skips_unresolved_original_identities`.

At the workflow floor, official Node 20.19.0/npm 10.8.2 passed `npm ci`, all
745 viewer tests, lint and production build. Chromium rendered a real native
hybrid eight-turn seed-42 bundle through Open Existing, verified all five regions
and the artifact hash, and navigated to the final turn without page/console
errors. Exact turn-4 resume matched six artifacts byte-for-byte and the decoded
bundle except `metadata.generated_at`. Changing `PYTHONHASHSEED` was refused
before any resumed artifact was written. These checks identify their restored
source; they are not a full checkpoint matrix or scientific qualification.

## Environment capability and reproducible qualification

The initial managed CPython distribution lacks `os.pidfd_open` and
`signal.pidfd_send_signal`. That explains seven extra cancellation-tool skips
in the first native run; only six skips match the native CI manifest. Do not
expand the manifest to accept the missing capability. System Python 3.13.5
provides both APIs and requires matching development headers and libpython for
Rust test linkage. The external environment installer must provision and verify
that complete interpreter; a same-version string alone is insufficient.

Environment configuration publication and fresh cloud-task restoration are
separate from local installation. They require the environment settings UI;
local installer files and repeat runs do not establish either state.

For the complete current-source CI lanes, dispatch the existing workflow:

```sh
gh workflow run tests.yml --repo YotsuBotfds/Chronicler \
  --ref dev/codex-kimi-qualification-20261031
```

Inspect the exact run's `head_sha` and all nine jobs, including the one current
wheel producer, both native module shards and their aggregate. Do not fabricate
GitHub producer identities for a local shard run or infer CI from a dev push.
Current results belong to the exact run linked in the delivery report and
[this branch's Actions history](https://github.com/YotsuBotfds/Chronicler/actions/workflows/tests.yml?query=branch%3Adev%2Fcodex-kimi-qualification-20261031).

## Scope retained

Long scientific campaigns and the complete checkpoint matrix remain unrun.
The ordinary matrix alone has 604 resume points; template and procedural
scientific profiles need their documented cohorts and compatible baselines.
Passing focused runs or CI does not establish scientific balance, performance
or cross-platform identity. No main merge, deployment, paid narration, new
credentials or optional-system activation is included.

Read-only experiment inventory found that viewer lender fixes, arc event-type
reuse, native tick indexing and region-partition reuse are already represented
through other integration history. Do not remerge their old branches. Public
grain, its diagnostic descendant and merchant tax remain separate, with their
own held evidence and economic/scientific gates. Preserve them for independent
review rather than expanding this remediation continuation into feature work.
