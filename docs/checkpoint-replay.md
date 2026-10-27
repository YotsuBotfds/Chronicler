# Python off-mode checkpoint replay validator

The opt-in `chronicler.checkpoint_replay` module checks whether a particular
Python-only simulation continues identically after serialization. It compares
the entire persisted WorldState, event log, and tracked tech-focus deltas at
the checkpoint boundary and every resumed turn. A PASS applies to that tested
trace and the exact fingerprinted runtime.

Run from the repository with the development dependencies installed:

```sh
PYTHONPATH=src .venv/bin/python -m chronicler.checkpoint_replay \
  --seed 42 --civs 4 --regions 8 --turns 250 --split 13 \
  --output-dir output/replay-seed42
```

The output directory must have no existing `checkpoint.json` or `report.json`.
The command preserves source files and existing evidence even when its input
arguments are invalid. It writes a strict, atomic checkpoint envelope and a
JSON report. Exit codes are 0 for PASS, 1 for a detected divergence, and 2 for
invalid input, unsupported execution, or an I/O error. A failure report records
the first divergent turn and field path; each compared boundary has hashes of
the uninterrupted and resumed state.

`--turns` means additional turns, and `--split` means additional turns before
saving. `0 <= split < turns` ensures at least one resumed turn. `--state` accepts
a raw WorldState snapshot as a read-only initial condition. The snapshot's seed
and current turn determine subsequent randomness. Validation from that initial
condition makes no claim about its history before loading. Unknown fields,
ambiguous normalized dictionary keys, malformed JSON, duplicate keys,
non-finite values, and invalid UTF-8 fail clearly.

The envelope format is `chronicler-python-off-checkpoint`, version 1. It records
the WorldState schema hash, Python implementation/version, platform, dependency
versions, and a hash of the installed Chronicler Python sources. Loading requires
an exact match. Payload and focus-sidecar digests detect accidental corruption;
these are integrity checks, not signatures or an authenticity guarantee.

The validator uses deterministic ActionEngine selection, a no-op narrator, and
`world.seed + world.turn` as the turn seed. It passes no agent bridge, economy
tracker, ecology runtime, or politics runtime to `run_turn`. Production
`execute_run` can select native ecology/politics when those extensions are
installed; this tool intentionally does not validate that execution path.
Native off-mode, hybrid, shadow, and demographics-only continuation are
unsupported and rejected. Native master seed, internal turn, agent pool,
registries, household/merchant/packet state, bridge demand windows, and tracker
history are not exported as a complete resumable checkpoint by this tool.
Narration, memory streams, viewer history, sidecar history, injections, and
interactive callbacks are outside the comparison contract.

The only added serialization surface is a focus-delta sidecar, indexed by
civilization order. `apply_focus_effects` records the actual bonus after clamping
in `_focus_applied_deltas`; `remove_focus_effects` must reverse that amount.
Existing raw saves omit the attribute. For example, applying metallurgy at
military 99 adds only 1. Removing it yields 99 uninterrupted, but the raw save/
load fallback subtracts 15 and yields 85. The envelope preserves the precise
tracked value and validates its focus/stat names and integer structure. Active
focuses with missing tracking fail; historical bonuses are never inferred.

Resource-suspension keys may serialize as enum names in raw JSON and become
integers on load under the existing Region validator. Comparison uses enum
values and numeric key strings so this known, equivalent representation does
not cause a false divergence. Sequence order and all other persisted values
are compared exactly. Pending turn signals and residual agent-backed state are
rejected. Direct callers of `save_checkpoint` must supply a completed
Python-only turn boundary; the validator owns and enforces its execution path.

After integrating the mercenary disband correction, seed 42 with four
civilizations and eight regions has an empty-region stockpile bootstrap pending
at turn 12. This boundary returns ERROR and writes no checkpoint; turn 13
completes the bootstrap and is the tested positive boundary in the example.
Earlier split-12 traces below describe the original public-baseline lane, not
the integrated runtime. Source fingerprint changes require fresh checkpoints.

Existing `WorldState.save/load`, production CLI defaults, and simulation
mechanisms are unchanged. A raw production resume still has the limitations
described above. No native or hybrid support is implied. For exact
production checkpoints in every mode (2026-10), see
[`integration/checkpoint-continuation.md`](integration/checkpoint-continuation.md).

## Verification and transfer

The work is based only on public baseline
`edf72991cad58d6670b1f382c33d50d903a6054a` (including PR13), on branch
`checkpoint-replay-validator`. Private frozen `b665e198` science was not used.
The focused tests exercise uninterrupted/resumed traces, focus bonus reversal,
cross-process continuation with different Python hash seeds, strict contracts,
error reporting, and source/evidence preservation. Relevant existing model,
simulation, main, tech-focus, and atomic artifact tests also pass.

See `handoffs/checkpoint-replay-transfer.json` for file scope, commands, results,
reviewer dispositions, and the final trace evidence. Full local checkpoint and
report files live under `output/checkpoint-replay-final/`; the compact evidence
summary is tracked in `handoffs/checkpoint-replay-evidence.json`.
