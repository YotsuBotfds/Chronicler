# Bounded live what-if continuations

An authenticated viewer can prepare one exact paired continuation of the
currently paused live world. Two literal controls are supported: `set <living civilization> stability
<integer 1..100>` and `set @world grain_reserves.shortfall_priority 0|1`,
followed by1–20 additional turns. The latter requires hybrid mode and already
enabled granaries. It changes procurement ordering within existing passes; it
does not enable a system, create goods or money, or guarantee better outcomes. The original remains paused and is never used as either
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
{"type":"what_if_prepare","request_id":"another-unique-id","control":"granary_shortfall_priority","value":1,"turns":5}
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
The manifest is version1 for stability and version2 for the global policy;
policy interventions add `scope:"world"`, `civ:"@world"` and
`stat:"grain_reserves.shortfall_priority"`. Both contain `source` (checkpoint identity, complete
checkpoint header, freshly read runtime identity), `mode`, `seed`, `start_turn`,
`end_turn`, `turns`, the control including `before`,
`semantics: "exact_checkpoint_pair"`, limits and resource bounds.

Run launches the two arms serially with the current interpreter and source path:
`--interactive --resume <common exact checkpoint> --simulate-only --turns END`.
Both inherit the same thread/hash environment, saved seed/configuration and
checkpoint. The baseline receives only `continue`; the other receives the
existing whitelisted shlex-quoted `set` command, then `continue`. Selecting
the already-effective value is a genuine no-op, including missing/default-zero
priority representation; it does not insert a zero override. A final
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

## Saved plans and exact references

The same panel imports/exports a version1 `chronicler-what-if-recipe`. It records
seed, mode, start/end/horizon, supported control, complete common-checkpoint
identity, source/runtime/settings fingerprints and optional output identities.
Exported display settings and artifact names are whitelisted; raw paths,
headers, credentials and private bookmark notes are excluded. Existing comparison
JSON/Markdown exports also sanitize nested provenance and settings.

Import fills the form and sends no command. Explicit preparation must pass
source/checkpoint/runtime/configuration/control checks before Run is enabled.
Malformed recipes and incompatible seed/mode/start leave the current form and
world available. Cancel remains available after a refused prepared match.

The reference is byte-bound, stricter than loader-compatible continuation. A
restart with retargeted output or presentation/lineage can change checkpoint
bytes; an identical seed and turn cannot prove equal state. On a complete
prepared mismatch, **Use this prepared checkpoint as a new case** explicitly
adopts the displayed current point. It keeps the imported reference visible,
sends no command and requires a separate Run. A new preparation invalidates
adoption. Exports then identify the actual new point; the original file stays
unchanged. This action does not establish reproduction or equivalent state.

Current-source browser evidence uses the regenerated seed42 example under
`/workspace/shared/chronicler-exploration-example-59d1de84`, Python package
`64f0c573f16800434e2ca572ddf95efc56ac567b088c7c876c8f56b89a9ddba0`,
compiled native SHA256 `f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`.
Actual schema2 preparation, recipe download, Cancel/import with no message,
strict same-pause reprepare, duplicate-click single Run, both native arms,
per-entity results and sanitized completed export passed. The original remained
paused at8. Receipts/screenshots: `chronicler-multiwave-evidence/browser`.

A zero-turn resumed Quit can end the server without a `completed` message or new
output. The viewer stops terminal reconnects, exits its pause dialog and retains
recorded history. It explicitly reports that no completed file was announced;
unreceived comparison results remain unconfirmed. Ordinary connection loss still
reconnects, and terminal intent is scoped to its exact socket.
