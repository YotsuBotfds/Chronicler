# Python decision delivery — 2026-10-29

This explicit observer adapter starts from combined native integration
`e40108eddabaa86ba76b87cffb70522f8505c321`. It adds Python access to the
existing Stage 1/2 native frames and changes no Rust source, physical decision,
native event ordering, world option or CLI. It has no writer, callback, thread
or automatic observation history.

```python
from chronicler.decision_delivery import DecisionDeliveryObserver

observer = DecisionDeliveryObserver.attach(bridge, max_move_rows=16384)
source_turn = world.turn
normal_result = bridge.tick(world)  # the existing tick, once
readout = observer.read_latest(expected_source_turn=source_turn)
observer.close()
```

The default bridge has no observer attribute and makes no new delivery-native
calls or optional-module imports. Attachment requires all Stage 2 methods and
validates bounded exact integer configuration. Each native row cap is 1–65,536;
explicit stable IDs must be a sorted, unique list/tuple of at most 65,536 uint32
integers. `None`, an empty selection and an absent ID remain distinct.

Both ordinary bridge entry points invalidate the prior observation before
fallible preparation. Capture occurs only after the entire normal
`_process_tick_results` returns, using the original full native event batch
still local to that invocation. Native getters and adapter validation errors
then produce fixed unavailable reasons without replacing normal return values
or changing the world. Existing simulation/result-processing exceptions are
not caught or retried. Normal cancellation remains normal cancellation.

`read_latest` never calls Rust. It returns a frozen result containing the
unchanged five Arrow batches, bridge-local attempt sequence, actual source
turn/mode and bounded event-link counters. Repeated reads are non-draining.
Source turn alone cannot prove freshness after a failed same-turn invocation;
the per-attempt invalidation handles preparation and pre-Rust conversion
failures too. Private out-of-band simulator ticking/reconfiguration is outside
this attachment's ownership contract. Replacing its simulator invalidates it.

For captured applied rows, the adapter validates zero-based ordinals against
the full native event batch, including preceding nonmigration events. It
compares the copied ID, source/destination, source turn and migration driver.
It does not retain that full batch, consult final alive slots, reconstruct an
origin, or join to filtered Python migrations. A valid observation can refer
to an agent that later died or whose slot was reused.

One latest capture is retained. The default retained Arrow-buffer ceiling is
8 MiB, with a fixed 32 MiB maximum. This is checked after the bounded native
getters allocate and is not a peak-RSS guarantee. If the row payload exceeds
it, only validated headers that themselves fit may remain, with explicit
`retention_limit` status. This differs from a legitimate zero-row frame or
native truncation. No frame-wide Python row history or automatic serialization
is created. UInt32 f32 bits, nullable fields, validity and native order remain
unchanged, including infinity and signed zero.

Stage 1 and Stage 2 retain their separate completeness flags. Selected capped
prefixes are not random samples, independent agents or population rates.
Matching an applied event does not repair an unknown origin. Local observed
utility stages are not counterfactual effects. Capture success describes
normal bridge processing, not later Python phases or a complete world turn;
downstream studies still need their own completed-turn receipts.

Reset/close invalidate availability and request native disabling only for an
explicit attachment. A failed disable stays unavailable with `disable_failed`
across later ordinary ticks until close is retried; it never claims native
capture is off. Python attachment/configuration/cache/errors are excluded by
the bridge's checkpoint-derived state filter. Native configuration/frame were
already transient. A restore starts unattached and native-disabled; reattach
explicitly. The unchanged native schema fingerprint is not a binary-reuse grant.

The focused pure selection passed **76 cases in 0.44 seconds** under the
unchanged offline guard: zero native import attempts, factory calls or blocked
I/O. It covers both entry points/all three modes, same-turn failure/retry,
selection, schema/turn mismatches, full-event joins, limits, reporting faults,
close failure/retry and Python pickle exclusion. It is added as its own
110-second offline chunk. These are fake-bridge/Arrow checks, with no local
native import, pool or world execution.

Seven compiled bridge cases are authored for the next fresh combined remote CI:
all modes/entry points compare real native future state and ordinary Python
writeback, require actual move exposure in the hybrid fixture, and check actual
native checkpoint transience. They have **not** run locally. Source/peer review,
fresh combined native CI and any later scientific/performance gates remain
separate; no efficacy, default activation or speedup is claimed.
