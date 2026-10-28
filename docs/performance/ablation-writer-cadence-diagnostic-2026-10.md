# Ablation writer-cadence diagnostic, 2026-10-28

Do not adopt cadence suppression from this experiment. It preserved the compared
simulation values and native bytes, including genuine continuation, but failed
the stronger serialized-memory checkpoint contract. Its profiled periodic writer
cost was also small in this fixture. No production source or gate design changed.

## Frozen inputs and execution

The [registered protocol](ablation-writer-cadence-preregistration.md) preceded the
runs, including its genuine turn-40 continuation extension (`a519f818`).
The [diagnostic runner](../../scripts/profile_ablation_writer_cadence.py) used
an external immutable `--source-root`, existing source-owned CLI controls and
the actual `execute_run`; it generated no fresh parent and rebuilt no native code.

| Input | Identity |
| --- | --- |
| Frozen source | `d051d7c06b1a490841d148b8906bde22f2f5d0f0` |
| Python package digest | `c14bc2f0178139b58d778926e1f803597ee0856958b02da67882b851845c8129` |
| Native crate tree | `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c` |
| Installed receipt release | `fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317` |
| Genuine combined-system parent, completed 30 | `6d85be5c158b2bca4c8635bd8748c992ca0860c695e8a200f7dd40dd8bc3034d` |
| Runner SHA-256 | `80b129632dd4bbc05964e770c8a393ca2ff8a1e17917e50136f0d412ebfaa17b` |

Seed 42, 4 civilizations, 8 regions, hybrid agent mode and every saved feature
control were retained. The parent enables forecasts, health care, gatherings,
scientific claims and transaction receipts, together with the existing systems.
Each control applies the same `needs` decision ablation from source turn 30 and
completes 60. All source ticks 30–59, seeds `42 + source_turn`, and the sole
forced final settlement detection at source turn 59 matched.

Controls were ordinary full output/cadence 10, existing lean output/cadence 10,
and existing lean output/cadence 61. The last skips only intermediate legacy
state and memory rewrites; normal final memory saving, reflections, histories,
native sidecars and simulation calls remain. Correctness runs requested one
additional exact checkpoint at completed 40, after normal writers/reflections.
Each was then genuinely loaded and continued 40→60. Profile workers omitted the
observer and this extra checkpoint.

The completed nine-worker attempt ran 20:13:28–20:15:08 UTC. Two scholarship
workers and the lead's bounded offline lane shared the host. All nine workers
exited 0. Three focused observer tests passed in 0.06 s: excluded pending-field
detection, bounded-queue capacity/fail-closed types, and proof that inspecting a
memory cache does not encode its newly appended entries. These tests do not
substitute for the actual native trajectories.

## What matched, and what did not

All 30 direct boundaries matched in public world fields, including normally
excluded pending/raw fields; carried world extras; contact/hazard/artifact
signals; authoritative language/historiography state; bridge Python values;
native checkpoint bytes, including RNG; memory entries/reflections; complete
inherited history; chronicle/reflection records; pending injections; and economy
tracker values. Final values matched again after finalization. All three direct
controls also wrote identical raw/compressed agent events, four-field fork
receipts, 16 validation sidecars and four final memory files.

The comparisons use structural-value signatures and native byte hashes. They
do not establish arbitrary Python object type, alias, mapping-order or allocation
identity. In particular, the canonical observer groups some value-compatible
container/enum types; the actual memory pickle and native blobs are checked
separately. The observer never calls `MemoryStream.json_text()` or saves memory
files, which would contaminate the cache question.

Cadence 61 left only 559 memory-cache rows at turn 40; cadence 10 had 824.
At turn 50 these counts were 559 versus 1,056. Their actual memory-subgraph
pickle hashes differ at every completed boundary 40–59. At completed 60 the
mandatory final save reconciles the direct controls to 1,268 cache rows and the
same memory pickle hash. This is a concrete intermediate serialized-state
counterexample, not permission to discard the cache contract. Turn-40 native
sections match exactly; complete Python sections also contain retargeted output
paths, so their differing hashes alone are not attributed solely to memory.

All three genuine checkpoint continuations matched their direct runs' physical
values and native bytes at completed 41–60, final values and raw agent events.
Their cache contents and final memory files also match. Their raw memory pickle
hashes differ from the uninterrupted controls at all 20 continuation boundaries,
in **all** output modes. The exact Python sharing/type/serialization cause was
not localized; this is not a cadence-specific effect or a claim of arbitrary
pickle-byte continuation identity.

New continuation output directories omit four earlier source-turn-30 validation
JSON files (aggregate, community, graph and needs). Every common validation
sidecar matches byte for byte. This existing output-prefix behavior occurs in
all controls; no full historical sidecar-directory equivalence is claimed.

## Diagnostic call costs

Each cell is calls / cumulative cProfile seconds. These nested costs must not
be added indiscriminately. The profiler includes Chronicler imports and exact
restore; `execute_run` time starts later. It was disabled before evidence
observation, inventory, compression and readout work.

| Function | Full / cadence 10 | Lean / cadence 10 | Lean / cadence 61 |
| --- | ---: | ---: | ---: |
| Complete profile, seconds | 4.789 | 4.988 | 5.260 |
| `execute_run` | 1 / 3.279 | 1 / 3.433 | 1 / 4.000 |
| Main module import | 1 / 1.295 | 1 / 1.311 | 1 / 1.092 |
| Exact restore | 1 / 0.228 | 1 / 0.259 | 1 / 0.190 |
| Simulation turn wrapper | 30 / 2.186 | 30 / 2.928 | 30 / 3.447 |
| Periodic legacy state writer | 2 / 0.0228 | 2 / 0.0333 | 0 / 0 |
| Memory-stream writer | 3 / 0.0187 | 3 / 0.0218 | 1 / 0.0138 |
| Final validation-sidecar close | 1 / 0.0562 | 1 / 0.0535 | 1 / 0.0594 |
| Full viewer-bundle writer | 1 / 0.5120 | 0 / 0 | 0 / 0 |
| Grain-reserve tick | 30 / 0.0525 | 30 / 0.0598 | 30 / 0.0695 |
| Finance `_projections` | 123 / 0.00204 | 123 / 0.00160 | 123 / 0.00184 |
| Finance `_Book.__init__` | 33 / 0.00139 | 33 / 0.00128 | 33 / 0.00139 |
| Finance `transfer` | 0 / 0 | 0 / 0 | 0 / 0 |

The disjoint periodic state/memory writers comprise about 1.27%, 1.61% and 0.34%
of profiled `execute_run`, respectively. Cadence 61 omits 624,865 bytes of final
periodic-state artifacts in this fixture: `state.json` plus its two observational
sidecars. This is artifact footprint, not cumulative I/O or a speedup estimate.
With one profiled execution per control, shared scheduling and profiler overhead,
the elapsed differences are not a performance comparison.

The 123 projection calls comprise 30 grain-opening, 30 before-buy, 30 after-buy
and 33 book-construction calls. The entire grain tick was about 1.6–1.7% of
execution and projections below 0.07%; **no foreign treasury transfer occurred**.
This fixture provides no measured justification for a per-foreign-purchase book
optimization. A separate representative transfer-rich workload would be needed.

The lean import attribution through `bundle` includes about 1.004 s in the
required `models` module, plus Arrow/NumPy dependencies. Moving a bundle import
may simply move that cost to the next required importer. No avoidable import
saving, lazy-import implementation or persistent worker-pool benefit was shown.
A future persistent-worker study would require a separately registered global,
RNG, native, sidecar and cross-fork-order isolation proof.

## Evidence and retained failures

Evidence is outside Git at
`/workspace/chronicler-next-qualification-evidence/writer-cadence-d051-attempt-002`.
It contains the original parent header/digest, full source/runtime identity,
every exact command/exit/horizon, boundary signatures, turn-call records,
checkpoint-40 section hashes, output inventories, logs and three full pstats
files. The source and extension were verified unchanged around every worker.
The completed attempt occupies about 27 MiB; no copied Cargo target was created.

| Receipt | SHA-256 |
| --- | --- |
| `diagnostic.json` | `9bd59a425f914c3c671419eed8b6a56dc9dcbb23f778ff3aa586013e9e933274` |
| Separate derived `analysis.json` | `1b8f23ddb3ffa4b0099e8d411fc51ff5538023b26d90cf0e561feb5fa5932876` |
| Preserved attempt-001 failure receipt | `bf046e7e2a80e40d8c6347af0e56dfbfa6d92d596cddf7bb49b25b3b1b751132` |

The initial checkpoint inspection omitted `PYTHONHASHSEED=0`; exact loading
correctly refused it. The environment was corrected without a mismatch bypass.
Attempt 001 then stopped at its first observer boundary because the diagnostic
did not support `deque`. Its failure receipt/logs and partial outputs remain.
An additional parent-only preflight identified the slotted demand manager; both
observer encodings were added before launching attempt 002 in a new destination.
No failed evidence was overwritten or presented as a completed control.
