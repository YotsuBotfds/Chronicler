# Bounded live what-if continuations

An authenticated viewer can prepare one exact paired continuation of the
currently paused live world. This supports exactly one existing interactive
control: `set <living civilization> stability <integer 1..100>`, followed by
1–20 additional turns. The original remains paused and is never used as either
arm. This is one paired trajectory, not a population causal estimate.

Start the live server with `PYTHONHASHSEED=0` and `--simulate-only`. The backend
checks both the environment and the interpreter's actual hash-randomization
flag; assigning the environment variable after startup does not qualify.
This first implementation requires POSIX process groups. Other seeds/platforms
refuse clearly rather than claiming exact continuation.

## Protocol and lifecycle

The existing origin/token authenticated WebSocket accepts:

```json
{"type":"what_if_prepare","request_id":"client-unique-id","civ":"Kethani Empire","value":65,"turns":5}
{"type":"what_if_run","request_id":"client-unique-id"}
{"type":"what_if_cancel","request_id":"client-unique-id"}
```

Preparation runs on the paused simulation thread. It validates the current
living civilization, saves through the existing exact-checkpoint binding into
a fresh server-generated UUID directory, verifies the envelope, all section
hashes, exactness, current source/native/package/thread compatibility, turn and
seed, and atomically persists a planned `manifest.json`. No process executes
until the separate run message arrives. State JSON, approximate checkpoints,
changed environments and corrupt sections refuse; no mismatch override exists.

`what_if_status` carries `request_id`, state (`prepared`, `running`, `complete`,
`cancelled`, `error`), and the manifest when a prepared job exists. Running
messages also carry `arm` (`baseline` or `intervention`). Errors carry `message`.
The manifest is version 1 and contains `source` (checkpoint identity, complete
checkpoint header, freshly read runtime identity), `mode`, `seed`, `start_turn`,
`end_turn`, `turns`, the control including `before`,
`semantics: "exact_checkpoint_pair"`, limits and resource bounds.

Run launches the two arms serially with the current interpreter and source path:
`--interactive --resume <common exact checkpoint> --simulate-only --turns END`.
Both inherit the same thread/hash environment, saved seed/configuration and
checkpoint. The baseline receives only `continue`; the other receives the
existing shlex-quoted `set ... stability ...` command, then `continue`. A final
exact checkpoint verifies the horizon/seed and full recorded intervention list.
Both actual output bundles must also reach the declared horizon and seed.

Completion emits `what_if_result` with `request_id`, `manifest`, and `baseline`
and `intervention`, each containing the decoded `bundle` and
`identity: {name, byteLength, sha256}`. Versioned `metadata.what_if` is written
into each actual bundle with the existing codec/atomic writer before hashing.
This intentionally changes exported bytes; no unchanged-byte claim is made.
The completed manifest also records both artifact identities and relative paths.

Repeated prepare/run requests replay existing state without launching duplicate
arms. One pair may be prepared/running at a time; eight request IDs are retained
per session. Preparing/running blocks other mutation commands and continuing the
original. Cancel and quit remain available. Cancel/shutdown joins the worker and
kills/waits the owned process group, including descendants. A failed baseline
prevents intervention launch. Latest status/result replay on reconnect; a
disconnection leaves the bounded owned job under server control.

Files remain in `<live output>/what_if/<server UUID>/`, including failed or
cancelled files and process logs. Client paths and arbitrary commands are not
accepted. Each arm is capped at 120 seconds, 2 MiB process log, 192 MiB output,
and a 16 MiB encoded/decoded bundle; exact checkpoint files are capped at
128 MiB. These are bounded local comparison tools, not a detached session or
generic execution platform.

## Focused evidence

The pure module covers strict controls, current-world admission, corrupt/state/
nonexact/incompatible checkpoint refusal, changed environment, durable prepare,
duplicate clicks, failed baseline, cancellation, pause mutation blocking,
shutdown, retained-job bounds, quoting and reconnect caches. It is registered
in the new `live-what-if` offline chunk, retaining every existing chunk/cap.

The separate process suite exercises real POSIX process groups and descendant
cleanup for cancel, server shutdown and timeout. Two tiny native hybrid pairs
cover changed and unchanged stability controls. They verify original world/
private/native bytes and Python/NumPy RNG preservation, the common checkpoint's
unchanged bytes, actual metadata identities, unchanged-arm determinism, and
baseline equality to the original uninterrupted continuation after it resumes.
No shared native rebuild, broader sweep or scientific qualification is implied.

On Linux/CPython 3.13.5, the focused live/interactive plus pure suites passed
79 tests, native ownership registration passed 210, the new guarded offline
selection passed 33 with no native imports/blocked I/O, and process/native
checks passed 5. The native binary SHA-256 was
`f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`,
against unchanged Rust tree `edb263686adb7ea5e23864146a5f7d0c5a163da4`.
External local evidence is under
`/workspace/shared/chronicler-world-lab-evidence/what-if-backend-20261102`.
Initial registration ordering/count failures and an overbroad guard invocation
that deliberately blocked an existing socket-start test are retained there;
the supported new offline selection includes only the pure module. Full native
CI, the full offline lane and viewer integration were not run by this backend
slice.
