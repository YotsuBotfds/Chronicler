> Copied on 2026-11-09 from the implementer's scratch report (`scratchpad/identity/sd-COR-7/BASELINE.md`). Scratch paths below are not durable; the integrated-head check is in [the ledger](../streamline-and-deepen-ledger.md).

# COR-7 baseline: delete the Rust politics step 11 (option B)

Date: 2026-11-08 (runs on 2026-11-09 UTC). Branch `sd/COR-7` from `sd/COR-6` (`677e537`).
Class: correction, option B (owner go-ahead 2026-11-08, decision record
`docs/superpowers/progress/streamline-and-deepen-decisions.md`). Expected result:
byte-identical Python output.

| Commit | Content |
|---|---|
| `03d4894` | `chronicler-agents/src/politics.rs`: remove `step_forced_collapse` and its call, header and entry-point docs say 10 steps; doc comment on the kept `CivOpType::StripToFirstRegion`. `ffi/politics_sim.rs`: two doc comments 11-step to 10-step. `chronicler-agents/tests/test_politics.rs`: step-11 tests replaced (see below). |
| `79aae4b` | `tests/test_politics_parity.py`, `tests/test_politics_bridge.py`: forced-collapse tests now assert the Rust pass emits no step 11. |

Kept unchanged: `CivOpType::StripToFirstRegion` and its `ffi/batch.rs` code 4, enum
declaration order, the `op[0] != 11` filter in `simulation.py` and in
`tests/test_politics_bridge.py`, the Python oracle fallback, the Python collapse in
`simulation.py` (after `apply_asabiya_dynamics`, severity-scaled), `apply_politics_ops`
handling of op code 4.

## Identities

| Side | Source | Native extension (sha256) |
|---|---|---|
| Before | `scratchpad/identity/sd-COR-6` (sd/COR-6 after-outputs, all 9 cases present) | `natives/sd-COR-6`, `59663c67744e52891bac8e20cac1562019fbef03440fa301a3f89624a8ea0bf2` |
| Start sanity | worktree at `677e537`, off_s42 + hybrid_s42 into `scratchpad/cor7/start` | same before native |
| After | `scratchpad/identity/sd-COR-7`, worktree at `79aae4b` | `natives/sd-COR-7`: `maturin develop --release --locked` of this branch into `venvs/w2-c1`, `6b4909d7baaaf45f827318c410f49dd7c7bca80365bcc157d85b29155c7a627c`; `check_python_env.py --expect native` PASS (compiled AgentSimulator, EcologySimulator, PoliticsSimulator) |

Toolchain: rustc/cargo 1.97.0, CPython 3.13.18. Runner:
`~/.venvs/chronicler-native/bin/python scripts/turn_speed_identity.py run/compare`.

## Start sanity (before any edit)

`compare identity/sd-COR-6 (off_s42, hybrid_s42) cor7/start`: 2 cases, 120 files, **0 differences**.

## After vs before: all 9 cases

`compare identity/sd-COR-6 identity/sd-COR-7`: **9 cases, 399 files compared, 0 differences.**

Field diff (`scratchpad/cor7/summarise.py`: per-file sha256 with `generated_at` blanked,
events_timeline multiset by (turn, type, actors, description), collapse counts):

| case | files | differing | events | added | removed | collapse before | collapse after |
|---|---|---|---|---|---|---|---|
| off_s42 | 9 | 0 | 3929 | 0 | 0 | 0 | 0 |
| off_s7 | 9 | 0 | 2949 | 0 | 0 | 0 | 0 |
| hybrid_s42 | 111 | 0 | 2739 | 0 | 0 | 0 | 0 |
| hybrid_s7 | 111 | 0 | 4085 | 0 | 0 | 0 | 0 |
| hybrid_s1234 | 10 | 0 | 2943 | 0 | 0 | 0 | 0 |
| proc48_hybrid_s42 | 92 | 0 | 8198 | 0 | 0 | 0 | 0 |
| proc48_off_s7 | 15 | 0 | 6792 | 0 | 0 | 0 | 0 |
| scaled22k_s42 | 32 | 0 | 497 | 0 | 0 | 0 | 0 |
| scaled52k_s7 | 10 | 0 | 472 | 0 | 0 | 0 | 0 |

## Did the deleted code run? (coverage of the identity)

Probe `scratchpad/cor7/probe_step11.py` wraps `chronicler.politics.call_rust_politics`
and counts ops with step 11 (`scratchpad/cor7/probe.sh`, same CLI args, env and seeds as
the identity cases).

- Identity cases (7 non-scaled cases, before native): Rust step 11 fired on **0** turns
  in every case (1550 Rust politics calls). After native: 0 step-11 ops, max step 10.
- Extra scan, before native, 200 turns, seeds 1-6 and 8-13, off and hybrid (24 runs):
  step 11 fired **0** times. The Rust collapse condition (asabiya < 0.1 and stability
  <= 20 on the pre-aggregation scalar) is rare in ordinary runs, so the identity matrix
  alone does not exercise the deleted path.
- Forced exercise (`COR7_FORCE=1`): the probe sets every multi-region civ to
  asabiya 0.05 and stability <= 15 on the Rust input every 10th turn (same mutation on
  both sides). Before native: step 11 fired on 20 turns per run, 197 (off_s42), 235
  (off_s7), 316 (hybrid_s42), 319 (hybrid_s7) step-11 ops (off_s42: 38 strip civ ops,
  45 region ops, 76 civ effects, 38 event triggers). After native: 0. `compare
  scan/force_before scan/force_after`: 4 cases, 42 files, 4 differences, all
  `probe.json` (the probe's own step-11 counts); every simulation output is identical.
  The Python collapse fired once (hybrid_s7) on both sides.

## Interpretation

No differences. This is exactly the expected result for option B: Python dropped every
Rust step-11 op (`apply_politics_ops(world, [op for op in ops if op[0] != 11])`) and
nothing after step 11 read the Rust `live_civs`/`live_regions` mutations (step 11 was the
last step and the result is returned straight after). The forced runs show the deleted
ops were emitted and discarded with no effect on output. Python's post-aggregation,
severity-scaled collapse stays authoritative.

## Tests

- `cargo check --locked`: no warnings. `cargo test --locked` (whole crate): 1340 passed,
  0 failed, 0 warnings. `cargo test --test test_politics`: 54 passed.
- `.venv/bin/python -m pytest tests/test_politics.py tests/test_politics_bridge.py tests/test_politics_parity.py -q`
  (no native): 204 passed, 53 skipped.
- Same plus `tests/test_politics_hash_parity.py` with the COR-7 native (`venvs/w2-c1`,
  `PYTHONPATH=src`): 268 passed.
- Rewritten tests against the old sd-COR-6 native: 6 failed (they detect step 11), so
  they discriminate.
- `tests/test_native_ci_shards.py`: 210 passed (no module added, moved or removed).

Not run: full oracle lane (lead runs it), 200-seed gate, paired seed batch (not needed:
no output difference).
