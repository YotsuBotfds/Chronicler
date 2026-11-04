# Optional merchant transaction observations

This default-off substrate records native merchant mobility operations. It does
not create private cargo ownership, fees, insurance claims, firm borrowers or a
new cash settlement. See the [pre-registration](transaction-receipts-preregistration.md).

## Accounting and identity contract

Hybrid trips reserve shared regional stocks. `departed` means a gross origin
debit was queued; `arrived` means a gross destination credit was queued, before
the next goods economy applies transit decay and settles macro stocks. An
unwound transit trip queues a return credit. `sea_crossing` can carry the
existing native raid/seizure result; the recorder never draws again. Other
losses, including later transit decay, are outside this frame. Controllers and
merchant civilization are observed identities, not legal title. Shadow and
demographics-only modes use virtual cargo; rows say `virtual_shadow`.

The stable agent ID identifies the merchant. Only an observed reservation start
in a complete frame establishes a trajectory-local voyage ID:
`{namespace}:voyage:{merchant_id}:{start_turn}`. Imported mid-trip state has an
unknown voyage ID. Receipt IDs use semantic turn, stable agent, operation, leg
and good, never a per-log ordinal. A raid's loss ID is its receipt ID plus
`:loss:raid`. Namespace defaults to `seed:{seed}` and can be caller-supplied;
these are not globally unique IDs across unrelated runs/forks.

The journal retains only the latest bounded frame, active identity map,
processed turn/fingerprint and scalar cumulative counters. A repeated identical
frame is a no-op; a conflicting same-turn or reversed/future frame raises before
state mutation. Native getter reads do not drain. Native configuration and
buffers are transient: checkpoint bytes and schemas omit them even when enabled.
Python state in an exact native checkpoint restores the identity journal and
prepares native recording again before the next tick. A raw WorldState JSON save
preserves journal data but does not prove native pool identity. Fresh bridge
construction rejects any processed receipt journal; explicitly disabling receipts
discards it before a fresh pool can be seeded. Seed/turn/equal integer IDs are
insufficient. Exact checkpoint __setstate__ bypasses this fresh-pool guard.

A complete active set replaces the preceding observed-active map. Missing from
that set does not establish a cargo loss, death, conquest or settlement. Exact
conquest/death releases happen outside the instrumented mobility loops and are
not attributed here. A dropped frame, skipped source turn or unexecuted mobility
phase discards known continuity. Later observations remain unknown until a new
complete reservation start. Overflow cannot support inferred closures or any
financial use. Every row explicitly has `financial_eligible=false` and
`cargo_title_owner=null`.

## Runtime and snapshots

Explicit activation supports hybrid, shadow and demographics-only agents;
agent-off activation is rejected. Saved enabled state is dormant outside those
modes. The shared optional `WorldState.transaction_receipts` is omitted when
absent. No receipt history is added to default-off exports or native payloads.

`prepare_transaction_receipts(world, bridge)` runs before a native tick;
`capture_transaction_receipts(world, bridge)` runs only after success, before
Python postprocessing. Both also accept the native simulator directly when its
pool provenance is already established. Fresh AgentBridge construction calls
`validate_fresh_transaction_receipt_pool(world)` before seeding agents. Native
`configure_transaction_receipts(enabled, max_rows=4096)` applies a bound of
1..65,536 rows, and configuration survives graph replacement as a derived
simulator setting. The new read-only getter returns:

```
(source_turn | None, max_rows, dropped_rows, mobility_executed, Arrow rows)
```

`source_turn` is the turn passed to native `tick`. The phase is merchant
mobility, not end-of-tick survival: later death and return-home phases can still
change an agent. An executed zero-activity phase produces a complete empty
frame. A successful tick without a usable mobility graph/ledger/buffer produces
a dated frame with `mobility_executed=false`; this is incomplete capture.
Disabled/pre-first-recorded-tick has `source_turn=None`.

`snapshot_summary(world)` exports only when active and the frame's source turn
is `world.turn-1`. It includes phase, source turn, completeness, execution flag,
cap/drops, active/known-active counts, scalar counters and detached current-frame
rows. It does not export the active journal or accumulated frame history.
Names/controllers are frozen in their observed frame. Historical summaries do
not borrow current/final owner names or subsequent mutations.

Work is O(existing mobility loops + emitted rows), with no extra all-agent scan
per receipt. The final active observation uses the existing diagnostics scan;
all buffers and active mappings are bounded by the configured frame cap. This
is observability overhead, with no claimed performance gain.

## Verification scope

Focused Rust coverage includes reservation/departure/arrival, physical departure
shrink, cancellation before field reset, disruption return, full-probability
raid, virtual provenance, explicit overflow, and 16-turn enabled/off equality of
encoded pool, cargo ledger, delivery buffer and original merchant stats. Native
simulator configuration, graph configuration and frames are excluded from native
schema/payload serialization.

Python coverage includes stable observed-start identity, unknown imported
trips, semantic loss identity, same-turn return/new reservation, idempotent loss
reads, real World JSON omission/journal transport and raw-pool rejection, restored waiting identity,
malformed-frame atomicity, gaps/overflow, detached historical names and enabled
empty versus missing mobility capture. Fresh-wheel integration tests additionally
exercise all three modes, repeated reads, graph replacement and native/Python
exact continuation. Their execution status must be recorded for the actual
built source; an older wheel skips these tests and does not qualify FFI.

No full scientific gate for future metrology or insurance has been run or is
implied. Introducing inspection fees requires an explicit native private cash
payer/receiver contract; current merchant income is a regional delivered-margin
share, so assessing per-trip fees here would invent an account boundary.

## Dated focused evidence: 2026-10-28

The receipt Rust source was frozen at `79432d08`. One-job focused Rust execution
passed 7 receipt tests and 6 existing maritime tests; compilation took 32.60s.
The already-built debug cdylib was copied to a separate import directory; the
installed qualified health release was not replaced. Five fresh-debug FFI tests
passed alongside 26 Python tests in 10.20s. A later dedicated columnar-capture
regression brings the pure suite to 27 tests; the offline oracle guard also
passed all 27 in 0.22s with no native imports or blocked I/O.

The initial fresh-debug test exposed arro3 batch iteration yielding columns;
capture now decodes through the project's existing columnar helpers. The FFI
fixture explicitly provides stocked origins, a dear food destination and
connected intra-civ routes, and requires nonempty actual merchant observations.
It is a controlled market fixture, not a complete simulation study.

Against the previously installed health release, all three simulator schemas
and constructor payload bytes match. Default-off controls across six turns in
each of hybrid, shadow and demographics-only modes also match per-turn native
payload bytes, events, agent snapshots and WorldState JSON. These are 18
controlled native frames, separate from full-run/scientific gates.

- Health release extension SHA-256:
  `e7ec77283075cb9b817ad47490fc98a3e77685451bbcd4ce8f5b8bcad9db5867`.
- Receipt debug extension SHA-256:
  `8ca80c2790485c7bbd73cd5cb3b39d0fa8705e20f5315a23e7c63e855fe899ba`.
- Agent schema `dcf0c34097c88451`; ecology `4ab7f8c199b5e5f8`;
  politics `b1a710f3450f5015`.

The external evidence manifest records native source-file hashes, extension
hashes, state/schema hashes and comparison outputs under
`/workspace/chronicler-transaction-evidence`. At that debug stage no receipt
release wheel or full qualification gate had been run. Independent read-only
review found no further
blocker after the raw-state/fresh-pool identity guard was added.

The shared bridge now checks that guard before loading a fresh native pool and
prepares the recorder immediately before both native tick entrypoints. It
captures only successful ticks, before world postprocessing. Preparation also
runs while disabled so a previously enabled recorder is cleared. Five added
Python bridge regressions cover both paths, disabled configuration and failed
ticks; together with the health suite, 41 focused tests passed. These tests
check the wiring with a controlled simulator; the fresh-debug bridge execution
and release qualification remain separate checks.

After shared bridge hooks landed, the pure suite plus fresh-debug FFI and real
bridge selection passed 46 tests in 1.85s. The real bridge controls exercise
both `tick` and `tick_agents` in all three supported modes, capture before
postprocessing, disable/dormancy cleanup, raw processed WorldState rejection
before native loading, and exact RunState checkpoint continuation. The market
fixture now chooses an already populated dear-food destination, so real bridge
observations are nonempty immediately; an empty region has no market price.

## Isolated release evidence, 2026-10-28

A fresh receipt release wheel was subsequently built with one cargo job in a
separate copied warm dependency cache and installed into its own environment.
The release build took 4m 00s. No qualified health environment or frozen source
was replaced. Native crate tree
`a4703ef4e9a21b5dbb194d318536a46e6ca8b71c` is unchanged from the receipt Rust
freeze at `79432d08`; bridge-test source is `442f0b07`. The build uses the
existing release profile (`opt-level=3`, `codegen-units=1`, `lto=true`) and does
not include later merchant-tax branch changes.

The combined pure/FFI/actual-bridge receipt selection passed **46 tests in
0.80s** on this release extension. All three native simulator schemas and
constructor payload bytes match the preceding health release. Eighteen
per-turn default-off controls (six turns in each supported mode, using the
populated dear-food market fixture) also match native payload bytes, events,
agent snapshots and WorldState JSON.

- Wheel SHA-256:
  `bf7dbf627e61ab5333dd20b8940770840c9742413439975b3777fa73c77b4c1f`.
- Installed extension SHA-256:
  `fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317`.
- Interpreter: CPython 3.13.5, Linux x86-64; one Rayon/BLAS/OMP worker for
  focused checks. Schemas retain the fingerprints above.

External `release-manifest.json` and build/test/control logs are under
`/workspace/chronicler-transaction-evidence`; the isolated environment is
`/workspace/chronicler-receipts-venv`. These tests qualify the bounded receipt
mechanics/bridge boundary on this native source. Complete integration, full-run
checkpoint/output comparisons and scientific gates remain separately owned
and recorded by integration. This release evidence does not authorize financial
use of the observed cargo or turn it into private title/settlement.
