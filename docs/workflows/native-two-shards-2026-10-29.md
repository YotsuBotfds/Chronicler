# Dormant native module sharding prototype

This separate source child of qualified `cbf6e368` leaves
`.github/workflows/tests.yml`, production code, dependencies and native sources
unchanged. It has not collected or executed the real full suite, built/loaded a
native wheel, dispatched CI, or established serial-versus-sharded RNG parity.
The template is inert at `docs/workflows/native-two-shards.yml.in`; future
installation at `.github/workflows/native-two-shards.yml` on the explicitly
registered qualification branch requires independent source review and approval.

The retained cbf run `40841527996` attributed 523.300 seconds to native test
cases. Its native job took 751 seconds, including a 175-second wheel build and
548-second full-test step; no-Rust took 384 seconds. The fixed historical
299-module assignment packs 159/140 modules into 261.65 seconds of saved case
attribution each. These are old observations and arithmetic, **not** measured
parallel runtimes or a controlled speedup. Additional setup, two full collections,
transfers, scheduling and aggregation can offset the opportunity. Any future
unsharded comparison has its own separate runner cost.

The checked-in manifest preserves those 299 historical assignments and explicitly
adds `tests/test_native_ci_shards.py` to shard 0 (160/140 files). The original
4269/4088 parent counts remain labeled historical, not future execution claims.
New, missing or duplicate default test modules refuse admission until their
assignment is updated visibly; no naming rule silently excludes future tests.
The source-bound qualification also registers the exact six historical native
skip node IDs and 526 successful subtests. Intentional changes to those contracts
must update the manifest. The added pure module contributes no real subtests.

`native_ci_shards.py` performs full default pytest collection in each consumer,
then filters whole modules in the original relative item order. It keeps every
actual selected parent setup/call/teardown report and every ordered subtest
report, including repeated identical contexts. Collection skips/errors, unowned
reports, missing/duplicate phases, late reorder, skipped assertions, unexpected
skips or lost/changed subtest counts cannot produce an aggregate pass. Parent
pass/skip counts and successful subtests remain separate; JUnit bytes, exact
ordered nodes, skipped nodes and totals must reconcile with the report stream.

One fresh builder retains the same-source whole wheel, its installed-native
member match and real Agent/Ecology/Politics class checks through the unchanged
`native_wheel_receipt` helper. Before installation, each consumer verifies the
whole wheel bytes, source/tree/manifest and same run/attempt. Before and after
tests it verifies the compiled native bytes/classes, Python and all installed
package identities (except explicit builder-only maturin). Both consumers must
present identical full collection and identity; their selected parents must be
disjoint and exactly cover it. These are same-pipeline content bindings, not an
independent GitHub job attestation, reproducible-build or scientific reuse proof.

The dormant template preserves the original full offline, no-Rust, Rust and
Viewer jobs, including their existing selections/limits. The original native
wrapper preflight and fresh release build precede both consumers. The matrix has
`fail-fast: false`; aggregation and the native/Rust summary require the builder
and **both** consumers to succeed. Missing or failed children cannot be replaced
by an aggregate count or a successful builder.

Each consumer uses a separate fresh hosted runner. Its first shell step creates
and exports private TMPDIR, PD/R007/Q009 evidence directories before Python
starts; pytest cache and basetemp also stay private. Full checkout/helper files
remain available to both consumers. There is no xdist, RNG reseed, fixture-output
reuse, competing suite on one runner or historical wheel reuse. Whole modules
preserve the existing module/class fixture scopes. Separate processes can still
change cross-module global RNG/cache state; real qualification must expose such
failures without weakening assertions or blanket reseeding.

Only small fake collection/report/XML/metadata fixtures run locally under the
unchanged offline guard. The first 69-case source passed. The first unfiltered
lint rejected `runner.temp` at job-level env; that exact template/log is retained.
Private directory exports moved to the first shell step using `$GITHUB_ENV`, and
unfiltered lint passed. Expanded source-bound skip/subtest contracts subsequently
passed 72 cases. The final source, including repository-root import scope and
private-path contracts, passed **75 cases / 0 skips** in 0.20 seconds (1.270 seconds
whole child) under the unchanged 110-second offline guard. Native imports,
runtime factories and blocked IO remained zero. Its receipt is
`pure-003/receipt.json`, SHA256
`5b4fd4bf22e6c6a5cd09ad7758fe5267f6a7948765c35684124f0abb8de47fe3`.
These synthetic passes grant neither full native qualification nor activation.

Evidence is external under
`/tmp/chronicler-review-evidence/native-two-shard-prototype-20261029/`.
The fixed assignment came from the preserved
`ci-critical-path-cbf-20261029/provisional-native-two-shard-plan.json` (SHA256
`0d4f05d3b53f5290f2cba3e6f6f4888a29de098cd0de6060f71a9f38a70d59cb`).
Rejected codec/matcher experiments and the separately qualified live-test fix
remain on their own refs, outside this source child.
