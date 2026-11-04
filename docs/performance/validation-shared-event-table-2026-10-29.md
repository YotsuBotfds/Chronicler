# One event-table read per seed

The separate `lead/validation-shared-event-table-20261029` candidate starts
from exact `95f73a74`. `load_seed_runs` previously opened and read each
`agent_events.arrow` twice: once for counted events and again for deaths.
It now derives both views from one seed-local Arrow table. No table survives
in the returned run records, and no process or global cache is introduced.

Both standalone loader APIs remain independent readers. Their table-to-result
expressions are extracted unchanged, including row order, the first uncounted
event sentinel, unknown-name handling, integer conversion and earliest death
selection. Bundle-prefix evaluation, returned dictionary order and validation
admission remain unchanged. No oracle method, threshold, sample, source/native
identity rule, simulation or checkpoint changes.

## Local verification

Seventeen new actual-Arrow/scalar cases cover empty, missing and unavailable
inputs; mixed, unknown and null events; chunked tables; repeated and out-of-order
deaths; uint64 boundaries; corrupt/missing-column/null-death failures; independent
standalone calls; consecutive loads and distinct seeds. They require one actual
IPC open/read per seed while keeping direct standalone calls separate.

The complete affected validation selection passes **161 tests in 1.53 seconds**,
with zero skips, native modules, runtime-factory calls or blocked I/O. It uses
the existing local Python 3.13.5 and the unchanged offline guard. Its entire
retained fixture/receipt pack allocates 278,528 bytes. This is a scalar/Arrow
check; no World, native build, benchmark or scientific cohort ran locally.

The same new cases against the complete original `95f73a74` reader produce
**nine expected read-count failures and eight passes**. Golden result/error
assertions before those counts pass. The control retains the exact original
module and globals; all other production source matches `95f73a74`.

External evidence:
`/workspace/chronicler-recovered-evidence/validation-shared-event-table-qualification-20261029`.
Complete-suite receipt SHA-256:
`2f22838d5a57caf54e50e0be1dc3f26070a82cf41e68e65d9fea5aa44573c7aa`.
Original-source control receipt SHA-256:
`d57bd6861ca91e4d3e507fe4b1254850efdc6149f6611dbaf7f9c793a7153e58`.

## Performance and remaining scope

One complete Arrow read per seed is removed structurally. No current-head
wall-time, CPU or peak-RSS benefit is measured. Warm filesystem cache may
already satisfy the second read; this is not a physical disk-I/O claim.

The external triage plan fixes retained seeds 42, 43 and 44 in both template
and procedural batches for loader comparisons, followed by unchanged complete
saved-batch report/decision equality. It requires paired timing and identical
reports before a validator speed claim. Historical reports and failures stay
untouched. Remote combined CI, saved-input re-scoring and performance remain
pending; this Python-only change does not require a new Rust binary.
