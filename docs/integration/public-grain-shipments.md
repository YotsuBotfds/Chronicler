# Public grain shipments: current-source fixture resolution

This isolated composition starts at `061594a0`, importing only the default-off
shipment feature from `b9e3fb11`, with the existing shortage-first option intact.
There is no Rust or tuning change and no merge of held ancestry. The original
passive diagnostic controller and its historical-wheel workflow are not activated.

`--grain-reserves --public-grain-shipments` requires an agent-backed goods
economy. Foreign procurement uses direct permitted merchant edges: payment and
market withdrawal occur in Phase 10 of T, detached paid cargo arrives in Phase
10 of T+1, and it can first feed people at the existing Phase 2 opening of T+2.
Domestic purchases retain immediate delivery. Disabling new shipments drains
paid cargo; disabling granaries while paid cargo is pending refuses. State,
receipts, forecasts and accounting distinguish paid commitments from edible
stocks. Orders retain their payer, seller, destination and keeper identities.
The existing caps and rollback/invalid-input rules are unchanged from the held
candidate; there is no economic-rule correction in this resolution.

## Why the original fixture failed

The preserved historical Tests run [41055186919](https://github.com/YotsuBotfds/Chronicler/actions/runs/41055186919)
failed before its restore assertions: no pending order was found at pauses 1..7.
Its economic gate values were not saved. The older diagnostic later refused its
resource observer; that result supplies no completed economic trace.

The decoded original native shard-0 job log (job `124062349006`) was also
retrieved read-only and retained externally. It reports two failures: the
pending-order fixture and `test_the_manifest_records_the_cohort_and_identity`,
with 4,774 passes and four skips. The latter is a separate test bookkeeping
error: its expected key set forgot that an unspecified shipment switch is
omitted to preserve old manifest shapes. This composition explicitly excludes
both unspecified opt-in keys in that assertion; production manifest behavior
is unchanged from the held feature. Neither failure is evidence of a restore
implementation bug.

The current-source composition reproduces the original assertion failure with
its original seed 42, eight regions, four civilizations, eight turns, market
stocks, empty public granaries, treasuries and neutral relationships. A separate
passive trace reads Phase 10 locals without replacing any economic producer.
At turn 0 buyer 2 has budget 46 and targets 50/24. Source 3 initially offers
33.95342159 grain at price 0.05217147219, worth more than one coin. Its own ruler
buys 19.16756338 grain for its domestic granary first. The remaining 14.78585821
is worth about 0.7714 coin. Source 7's remaining offer is worth about 0.3005;
source 0's about 0.0025. The unchanged integer payment calculation floors each
to zero and skips it. Direct routes, positive deficits and buyer cash are
present; later foreign surplus dwindles. Every evaluated foreign payment in
all eight turns is zero. The regression also checks the final state has no
pending cargo or dispatch, closing the old unobserved final-turn gap.

This identifies a fixture precondition error: abundant initial market stocks
did not guarantee an affordable foreign offer **after domestic procurement**.
It provides no evidence of a restore, routing, payment or product correctness
bug. The trace values describe this fresh composition; they are not invented
measurements of the historical hosted run.

## Explicit fixture correction

The positive checkpoint case now gives each initially owned foreign public
granary 500 finite grain before the first ledger begins. All original market
stocks, treasury, seed, relationships, horizon, real producers and positive-path
assertions remain. These constructed opening public stocks prevent the sellers'
domestic refill from consuming the affordable export offer. Ordinary production
procurement must create the pending order; no dispatch or economy result is
fabricated. The original empty-public-stock conditions run separately as a
native zero-dispatch regression, including the payment gate diagnosis.

The positive case observes the actual StatAccumulator debit/credit, earliest
pending live pause, exact World/native payload at load, one dispatch and one
T+1 arrival without a second payment, complete resumed artifacts/live views,
and final native bytes. `CHRONICLER_CHECK_RESOURCES=1` is active in both native
fixture cases. The existing pure mechanics case retains the T+2 release proof.

## Source and verification boundary

Historical shipment inverse JSON remains byte-exact (SHA-256
`f4f5ddc678c4968bea7e42d61a4aa8d3223f19cb7d134c05174a064c55b58af4`). A new
composition inverse binds every source edit to complete `061594a0` parent bytes.
The historical care pins and default-main AST digest are unchanged: exact
shipment entry-site inverses precede their existing projections. Predicate,
location, extra-effect and parser mutations refuse. The new module has an
explicit native owner and its own bounded offline chunk; old owners, skips,
subreport expectations and 110-second chunk limits stay fixed.

On Linux CPython 3.13.5, `PYTHONPATH` was verified to select this worktree. The
three exported native classes are actual compiled aliases. The shared binary
SHA-256 is `f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`;
its build's Rust tree and this composition's unchanged Rust tree both equal
`edb263686adb7ea5e23864146a5f7d0c5a163da4`. Historical shipment Rust tree
`aa32b8e3...` differs by a later politics restoration guard, so this is current
composed evidence, not exact historical-native reproduction. No shared binary
was rebuilt or replaced.

Focused verification passed 620 tests in 20.30 seconds, including both native
fixtures, shipment rollback/conservation/identity/cap/invalid-order cases,
receipts, forecasts, finance, live checkpoints, source witnesses, CLI, sidecar
and manifests. Three additional checks passed for the immutable historical
witness and existing Python/native corruption/truncation refusals. The guarded
new offline chunk passed 92 cases without skips or native modules loaded; two
native import attempts were blocked by the guard.

Against archived `061594a0`, two real eight-turn hybrid comparisons (unspecified
shipment flag and explicit off) each matched all 25 ordinary artifacts, final
native bytes, live views and global RNG, given equal initial harness RNG.
Only bundle `generated_at` is excluded from artifact comparison. Resource
accounting was enabled in all arms. This is bounded dormant-feature parity,
not a population, efficacy, scale or timing qualification.

Evidence remains external under
`/workspace/shared/chronicler-next-development-evidence/shipment`: original
fixture/kernel copies and hashes, `original-negative.log`,
`historical-native-shard-0-124062349006.log`, `committed-focused.log/xml`,
`economic-gates.json`, `native-identity.json`, `final-focused.log/xml`,
`corruption-and-immutable-witness.log`, `guard-public-grain-shipments-final.json`,
and `disabled-controlled-parity-report.json`. Earlier preparation negatives
remain: one archive request named a nonexistent tracked `tests/__init__.py`,
one observer launcher lacked the test-root import path, the first composed
source inverse still expected its older parent, the batch key-set test omitted
the new unspecified flag, and an uncontrolled process-global RNG comparison
used unequal initial RNG states. None is silently counted as a pass.

Full offline/native suites, fresh hosted CI, scientific/balance campaigns and
performance qualification remain unrun for this composition. The feature stays
default off and awaits integration review.

## Viewer connection follow-up

The optional Granaries snapshot panel now distinguishes stored grain, paid cargo
in transit, net dispatches and arrivals. Shipment rows show the recorded market,
destination, payer, seller and original dispatch payment; an arrival is never a
second payment or evidence of food eaten. Immediate purchases stay separate.
Old snapshots without nested shipment records retain their existing UI, and
missing/stale/future shipment frames are unknown rather than zero. Shipment
receipt events use simulation turn + 1 as their visible snapshot clock, including
provenance, so an arrival cannot appear one snapshot early.

The existing Transactions inspector accepts a dispatch's zero immediate receipt
and retains its actual payment; a focused test confirms this. Its older table
does not expose the extended committed-net/due-date/delivery fields. The new
Granaries panel supplies the cargo view without expanding that inspector.

Focused viewer checks pass 59 tests, app TypeScript checking and lint of the
changed viewer files. No full viewer suite or production build was run for this
follow-up, and no Python/native/economic source changed. Evidence is external in
`viewer-shipment-focused.log`, `viewer-shipment-typecheck.log` and
`viewer-shipment-lint.log` alongside the native milestone evidence above.

The newer saved-world summary and its loader-validation dependency are absent
from this branch's parent. A three-line integration patch against the existing
root helper is preserved externally as `saved-world-summary-shipments.patch`,
with its exact parent-file hash. It recognizes nested recorded shipments and
currently accepting orders; it does not label draining cargo as new-order
activation. The root helper and frozen root viewer build were not edited here.
