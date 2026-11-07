# Independent review of the Connected World correctness rework

This review inspects the integration owner's actual X1/A6/C2 diff against main
`2726bf449d0e4d581a72034000ee0861a58ee439`, through `2e48ca32` and the pending
strict-default and clock refinements. The [source receipt](rework-core-independent-review-2026-11-07.json)
binds the actual reviewed bytes; later source changes require a delta review.
The reviewer authored control regressions but no production changes. The
physical-lifecycle and native tests were authored independently.

**Scoped source approval: no remaining semantic blocker identified at the
recorded hashes.** This does not qualify the model or replace pilot/schema,
held, profile, exact resume, feature-off identity or exact-head/main CI gates.
The screen and optional archive tools are outside this source approval.

## Correctness and authority

- `density_only` is an explicit corrected opt-in. It removes the unsupported
  extra multiplier derived from motive-classified spells, retaining existing
  epidemic population/capacity and urban-density terms. Identical physical
  trajectories therefore no longer have different exposure merely because a
  driver is unknown. No voluntary or unknown migrant is relabeled displaced.
- Existing new-enable defaults remain A6 rules 2 and public-health legacy
  displacement crowding. Saved JSON and pickle defaults remain legacy. Rules 3
  and density-only must be requested explicitly, respecting the user's
  no-default-promotion boundary. Actual fresh comparisons and profiles must
  state those flags rather than rely on implicit defaults.
- Current neutral configuration and prior observations have distinct clocks:
  the configured factor 1 is current, while X1 arrival/displacement facts and
  sanitation remain T−1. Exact-record provenance rejects a forged future
  neutral-factor date or a non-neutral value masquerading as that constant.
- X1 retains one Phase 10 writer and its original motive spell/home semantics.
  New arrival counts use the last observed residence change, including actual
  trip unwind relocations, once per living stable ID at its final residence.
  Ordinary travel and household relation changes do not create a new residence
  change; death and new stable IDs cannot inherit the old observation.
- Full-window coverage requires twenty consecutive fully covered writes.
  Refused/deferred rows, gaps, pool resets and old checkpoints reset that
  knowledge clock. Current complete headcount alone cannot reconstruct a
  missing historical movement. Incomplete shares remain null, not zero.
- The optional arrival field group is atomic, typed and bounded; regional sums
  close to totals. Missing old fields remain unknown, partial/malformed groups
  are refused, and positive new physical stock cannot be labeled recorded zero.
- Rules 3 installs D3 war inputs independently of personal A6 record/shuffle or
  component controls. It shuffles only personal penalties, then combines the
  fixed D3 targets under the same cap. Historical rules 1/2 retain historical
  behavior. D3 movement still needs the enabled A6 dispatcher; this is not a
  claim that D3-only configuration supplies movement inputs.

## Actual verification read or run by this reviewer

The current focused selection passed **104 tests**: adaptive controls,
residence exposure and connected-record provenance. It includes the unchanged
new-enable defaults plus explicit corrected opt-ins. Earlier independently
authored control tests also passed the official offline guard; the separate
initial audit retains that command and receipt.

The new `cwr1` inverse was replayed old→new and new→old over complete bytes:
**four files, six unique hunks**, parent and current SHA256 values matching,
restoring exactly main `2726bf44`. The only fixture addition is `cwr1`;
historical fixtures remain unchanged. The layer list appends rather than
rewrites the historical chain.

The actual completed standard Rust log contains **40 suites, 1,339 passed,
zero failed and two ignored manual timing benchmarks**. The three new native
physical invariants use the actual move application, household expansion and
pool kill/reuse authorities. They compare persisted pool bytes independently
of reason metadata. Full native lifecycle/restore execution is a separate
integration-owner receipt, not a test rerun performed by this reviewer.

## Separate viewer performance packet review

Pure formatter code `cf0925d9` was previously approved from its actual diff,
ten public-index tests and 156 exact string comparisons across six locales.
Performance packet `28a772a9` (same content as lane commit `817a73c2`) is also
approved independently of the correctness rework.

The reviewer recomputed all **160 median/range/paired-difference fields** from
**48 samples / 24 matched pairs**, checked unchanged dimensions and displayed
counts, rehashed all four actual raw inputs and 48 actual build assets, and
checked four locale complete-index/query equivalences. The index retains
190,555 observations and 3,279 entities; all pointers, row values and reading
states remain included in the complete digests. Actual elapsed 541.995 seconds
is below the fixed 900-second post-pilot budget.

The reported 74–78% long-history cold-panel improvement and 26–33% short-stress
improvement agree with the retained data. Slower file loads/selection and
mixed JS heap observations remain explicit. Renderer CPU excludes workers;
phone viewport measurements are not handset CPU emulation or hardware
qualification. No memory, wire-size or simulation-throughput improvement is
inferred from this pure formatting change.

One nonblocking provenance clarification was sent to the owner: the README's
first 3,669/4,352-ms diagnostic is not in the committed node-index repeat,
which records 4,114/4,870 ms and supports the same approximately 84% attribution.
Use the retained repeat or preserve the earlier receipt; no new timing run is
needed. Independent arithmetic/hash receipt:
`/workspace/evidence/rework-review/viewer-packet-review.json`.
