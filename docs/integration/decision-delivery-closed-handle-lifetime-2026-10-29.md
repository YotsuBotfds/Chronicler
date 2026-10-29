# Release an old simulator after observer cleanup

This Python-only follow-up starts from `95f73a74`, the combined candidate whose
[six-job CI run](https://github.com/YotsuBotfds/Chronicler/actions/runs/40821282241)
passed. That parent result remains scoped to its exact source.

A retained closed observer handle previously kept a strong reference to its
simulator. After the bridge replaced that simulator, retaining the handle also
kept the old native pool alive. Successful cleanup now drops that reference.
A stale handle likewise releases it when a newer attachment owns the same
simulator. Failed disabling retains the reference so the existing explicit
retry still works. Source-turn/status metadata and idempotent close remain.

Two weak-reference/GC regressions fail on the parent, then pass with this
two-line correction. The complete affected guarded file passes **82 tests in
0.42 seconds**, including the existing failed-close, stale-owner and bridge
cleanup contracts. The guard records no native imports, runtime factory calls
or blocked I/O. Both original failures are retained outside Git.

These are genuine Python object-lifetime tests with inert simulator doubles.
No local native pool, world, rebuild, performance study or new complete CI run
was used. Rust, the active tick/capture paths and workflow are unchanged; the
parent's compiled tests and binary identity are retained as parent evidence.
This does not supply a new whole-world or scientific qualification.
