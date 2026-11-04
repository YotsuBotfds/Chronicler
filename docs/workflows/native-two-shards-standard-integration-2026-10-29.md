# Standard native CI shard integration proposal — 2026-10-29

This source-only proposal moves the root-qualified V2 native workflow into
standard `Tests`. It starts from `7dcb240277aa8d61275d6f805cdf0f54976b62b0`;
the isolated nine-job run [40863008464](https://github.com/YotsuBotfds/Chronicler/actions/runs/40863008464)
passed. Standard integration has not been pushed or run. Main is unchanged.

## Graph and migration

The six existing visible checks remain `Python bounded offline`, `Python no-Rust`,
`Python native execution`, `Rust`, `Python native` and `Viewer`. The native
execution check becomes the exact-once aggregate. One builder and two native
module shards make nine actual jobs. The aggregate requires builder and matrix
success and reconciles both receipts/JUnits; `Python native` then requires that
aggregate and Rust success. Failure, cancellation or missing evidence blocks it.

The existing standard triggers/permissions and the offline, no-Rust, Rust and
Viewer job bodies stay byte-identical. Builder/consumer/aggregate bodies reuse
the qualified V2 template, removing only its closed-branch job guards and changing
the aggregate's visible name. The original closed qualification workflows and
templates remain unchanged, with exact branch/path triggers disjoint from the
standard push branches. Ordinary feature pushes do not start an extra shard
workflow. No dispatch, dependency, cache, runtime or native policy is added.

`scripts/native_ci_shards.py`, the assignment manifest and native wheel reader
remain unchanged. One fresh source-bound builder wheel is verified before each
consumer installs it, with current-producer source/package/native checks before
and after the suite. Each consumer performs full default collection, preserves
pytest order in its owned modules, and has private temp/cache/evidence paths.
There is no xdist, reseeding, path selection, skip change or shortened deadline.

The artifact layout changes from the single native Python result/wheel pair to
builder, two shard receipts/JUnits/logs and aggregate artifacts. Alongside offline,
no-Rust, Rust and the two wrapper preflights, that is nine expected artifact ZIPs;
the two tiny preflight counts remain separate from full-suite counts. Downstream
readers must use this layout rather than treating either shard as a complete run.

## Maintaining the exact partition

The registered module assignment is source-scoped: 160/140 modules, six exact
native skip nodes and 526 successful subtest reports in the qualified proposal.
Adding/removing a test module requires an explicit assignment update; missing,
duplicate or unknown modules fail before build/selection. Added tests inside a
registered module join full collection automatically. Intentional skip identities
or subtest multiplicity changes require reviewed registration and contract updates.
Repeated subtest display labels remain separate reports; the bounded labels are
lossy diagnostics, never raw scientific inputs or identity evidence.

The historical `cbf6e368` workflow fixture preserves the original isolated
prototype's contracts. Direct current-workflow tests separately verify the actual
graph, barriers, full-selection delegation, wheel publication and trigger sets.
The four independent job bodies and current header are compared byte for byte.
Revert this integration as one unit if restoring the old standard native lane;
the historical qualification branches/workflows remain available for provenance.

## Validation and limits

128 focused offline workflow/wheel/shard contracts pass with zero skips, native
imports, runtime factory calls or blocked I/O. Unfiltered lint passes all six
actual/template workflows. The first local run preserved 127 passes and one
new-contract failure: it omitted the unchanged historical manual-dispatch entry;
only that expected metadata was corrected. These checks execute no real
full-suite collection, World, native import, build, network call or hosted job.
The first failed isolated
prototype `847f164c` remains failed: raw bytes/nonfinite diagnostic labels prevented
receipt publication despite passing cases. V2 fixes only that display boundary.

The isolated V2 timings are observations on that producer, not controlled speedup
evidence for standard integration. This proposal grants no runtime adoption,
main merge, scientific outcome, whole-world/RNG identity or performance claim.
Root review of the exact source is required before publication/qualification.
