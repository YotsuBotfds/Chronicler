# Performance quick wins, October 2026

Branch `perf/quick-wins`, based on `837a44f` (`continuation/recovered-20261011`).
These changes make runs faster and do not change what the simulation computes.
A completed run writes byte-identical `state.json`, `chronicle.md`,
`memories_*.json`, `agent_events.arrow` and `chronicle_bundle.json` (apart from
its wall-clock `metadata.generated_at`). The RNG draw sequence is unchanged.
No Rust code changed. The only behavior change, and an intentional one, is when
intermediate checkpoints are written during a run (section 1). Final files are
unaffected.

The work follows a profiling study of default runs. It found that about half of
wall time was per-turn file writes, and that per-turn cost grew with run length
because several checks rescanned the whole event history every turn.

## Changes

### 1. Checkpoint cadence (`--state-every K`, default 10)

Before this change, `execute_run` rewrote `state.json` with `indent=2` after every
turn. The file reached 1.7 MB at 200 turns and 4.3 MB at 1000. Every memory
stream was also rewritten every turn.

- `state.json` is now written as a resumable checkpoint when `world.turn % K == 0`
  and before an interactive pause. The final state is still written after the
  loop by `WorldState.save` on every normal exit path, including early quits. Its
  bytes and indented format are unchanged.
- Intermediate checkpoints are compact JSON, written atomically through
  `artifact_io.atomic_write_text` (same-directory temp file, fsync, rename). A
  crash during a write can no longer truncate the previous checkpoint.
  `WorldState.load` reads either format into the same world.
- Memory streams are written at the same point of the turn as before (ahead of
  that turn's era reflection), on checkpoint turns, on the final turn, and on any
  turn where an `on_pause` or `quit_check` callback may end the run. The files
  on disk at those turns therefore match the old every-turn writer exactly, and
  a checkpointed state/memory pair resumes exactly like the old one.
- Ctrl-C while a turn is computing is deferred to the end of that turn. The
  completed turn is then checkpointed (state plus memories, as the every-turn
  writer would have left them) before `KeyboardInterrupt` is raised. A second
  Ctrl-C stops immediately. The deferral is installed only from the main thread
  and only over Python's default SIGINT handler, so interactive prompts, live
  mode threads and custom handlers are unaffected.
- `--state-every 1` restores the old every-turn checkpoint. A crash (an
  exception, not Ctrl-C) loses at most K-1 turns of progress.
- Hand-built `argparse.Namespace` callers without `state_every` get the default.

### 2. Incremental history indexes (`chronicler/history_index.py`)

`HistoryIndex` is a derived cache attached to `WorldState` as a private
attribute. It is never serialized, a deep copy gets an empty index, and it never
makes two worlds compare unequal. It keeps buckets over the append-only
`events_timeline`, `named_events` and `agent_events_raw` lists. Each query first
folds in only the entries appended since the previous query. If a list was
replaced, shortened or had its tail object swapped, the index rebuilds it from
scratch. A world loaded by `--resume` therefore starts empty and rebuilds to the
same answers. Buckets keep source-list order.

| Call site | Before | Now |
| --- | --- | --- |
| `movements._detect_schisms` | every named event scanned for each adherent pair at the divergence threshold | per-unordered-pair schism descriptions; keeps the substring test (`movement_1` still matches `[movement_10]`) |
| `named_events.generate_*_name` (7 sites) | `[ne.name for ne in named_events]` per name | set of names plus count, passed to `deduplicate_name` as a membership view that keeps the `(n)` fallback |
| `culture.check_cultural_victories` | two `any()` scans per civ/movement per turn | hegemony actor set; enlightenment descriptions |
| `factions.tick_factions` (per civ), `traditions.update_event_counts`, `main` `on_turn` and memory feed | `[e for e in events_timeline if e.turn == T]` | turn bucket |
| `simulation` arc classification (per great person) | full timeline passed to `classify_arc` | per-actor bucket (the identical ordered subset that `classify_arc` filters to) |
| `ecology._collect_army_arrived_mask` | all agent events every turn | per-turn migration bucket |
| `AgentBridge._process_promotions` | two full agent-event scans per skill promotion | per-agent migration/switch counts |

### 3. One rayon thread per parallel batch worker

`--batch --parallel` workers run `os.environ.setdefault("RAYON_NUM_THREADS", "1")`
as their pool initializer. Parallel batches already run one simulation per core,
and at the current agent counts (about 130 agents per turn on average in the
default hybrid run) extra rayon threads only oversubscribe the cores. A value
the user sets is kept. The native tick partitions work per region, with
per-region RNG streams and order-preserving collection, so results do not
depend on the thread count. The subset gate below runs with this setting.

### 4. Columnar agent-event conversion

`AgentBridge._convert_events` reads each Arrow column once with `to_pylist()`
instead of calling `column(name)[i].as_py()` per cell. It produces equal records
with equal value types for pyarrow and arro3 batches, with or without the
optional columns. Over 200 default hybrid turns its cost fell from 0.206 s to
0.041 s.

### Measured and not changed

- **Snapshot fetch caching.** Default hybrid runs fetch the agent snapshot 610
  times in 200 turns, for 0.07 s in total. The pool state differs between those
  points, so a cache would need mutation tracking across the bridge. That adds
  risk for no measurable gain, so it was not done.
- **`_refresh_snapshot_metrics` vectorization.** At about 130 agents the cost
  (0.3 s per 200 turns) is fixed per-call numpy work, not per-agent Python loops.
  It is not worth changing at current scale.
- **Remaining growth in long off-mode runs.** It now comes mainly from
  O(civs²) perception noise in the snapshot and action engine
  (`intelligence._get_perceived_stat_with_accuracy`, one seeded `random.Random`
  per call, with the civilization list growing through secession) and from
  checkpoint size. Neither is a history rescan. The first touches RNG
  construction and is left for separate review.

## Proof of identity

Reference outputs were recorded from the base tree before any change. Both
trees ran in the same virtualenv with the same native build; the base tree was
an export of `837a44f` selected with `PYTHONPATH`. Every file in each run
directory was hashed: `state.json`, `chronicle.md`, all `memories_*.json`,
`agent_events.arrow`, and `chronicle_bundle.json` minus
`metadata.generated_at`.

| Check | Result |
| --- | --- |
| `--agents off`, 500 turns, seeds 42 / 7 / 1234 (CLI, `--simulate-only`) | byte-identical (7 files each) |
| `--agents hybrid`, 300 turns, seeds 42 / 7 / 1234 | byte-identical (8 files each) |
| `--resume`: off seed 42 250 → 500; hybrid seed 7 150 → 300 (prefix run, then resume) | prefix and resumed runs byte-identical |
| Mid-run checkpoint: off seed 42 after turn 250 of 500; hybrid seed 7 after turn 150 of 300. Base every-turn indented file vs new compact checkpoint, each resumed by the CLI | loaded worlds equal, memory files byte-identical, full and resumed runs byte-identical |
| Hybrid seeds 42 / 7 / 1234 with `RAYON_NUM_THREADS=1` vs default-thread reference | byte-identical |
| `scripts/benchmark_headless.py` workloads (single, standard, wide; pure-Python lane, native import blocked) | artifacts, every per-turn snapshot hash (20/60/40 turns) and the ordered RNG primitive trace identical |
| Timing runs: hybrid 200 turns (2 pairs), off 1000 turns (3 pairs) | byte-identical |
| Subset gate (20 hybrid seeds × 200 turns, validation sidecars, `--parallel 2`, so rayon pinned to 1 thread) | 2,108 files byte-identical to the `837a44f` baseline batch (4 workers, default threads) |

Subset gate: `gate_status` PASS. `chronicler.validation_compare` against the
`837a44f` subset baseline report shows no oracle status changes, no new required
failures, and a 0.0 delta on all 12 metrics. The regression oracle FAIL
(`terminal_population_extinction`) and artifacts PARTIAL are the same as in the
baseline. Both predate this work. The full 200-seed gate was not run.

## Timings

CLI `python -m chronicler.main ... --simulate-only` (seed 42, 4 civs, 8
regions). Base and new were launched as a concurrent pair, so both saw the same
machine load. The machine was shared and heavily loaded (load average about 20
on 4 cores), so wall time is noisy. CPU is the child's user+sys time from
`wait4`, including native threads.

| Workload | Base CPU | New CPU | CPU speedup | Base wall | New wall |
| --- | ---: | ---: | ---: | ---: | ---: |
| hybrid, 200 turns (2 pairs) | 7.86 / 7.80 s | 4.25 / 4.30 s | 1.83x | 23.9 / 24.0 s | 13.8 / 13.8 s |
| off, 1000 turns (3 pairs) | 89.8 / 86.5 / 91.1 s | 31.0 / 29.4 / 31.0 s | 2.94x (median) | 246 / 136 / 210 s | 127 / 45 / 93 s |

The table below shows per-turn CPU time by window for off mode at 1000 turns
(in-process, with an `on_turn` probe). Base and new ran concurrently, and their
outputs were identical.

| Turns | 0-100 | 200-300 | 400-500 | 600-700 | 800-900 | 900-1000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base ms/turn | 16.1 | 28.7 | 60.8 | 92.5 | 152.8 | 259.0 |
| new ms/turn | 11.1 | 12.5 | 22.0 | 31.5 | 42.6 | 60.2 |

Per-turn CPU in the late window falls 4.3x. The remaining growth is described
under "Measured and not changed".

## Tests

`python -m pytest -q -m "not slow" -n 2` passes with 4997 tests and 3 skipped,
against 4954 passed and 3 skipped at base, with the native extension built.
The new tests are:

- `tests/test_history_index.py`: randomized interleaved appends and queries
  against the reference rescans; replaced, shortened, cleared and tail-rewritten
  lists; schism substring semantics; `_detect_schisms` against the old
  implementation; the name view in `deduplicate_name`, including the `(n)`
  fallback; no serialization, rebuild after save/load (resume), deep and
  shallow copies and equality; duck-typed and mock worlds; and a 70-turn run
  in which every index answer is checked against a full rescan as it happens.
- `tests/test_state_checkpoints.py`: CLI parsing and validation; exact
  checkpoint and memory-write turns for K=1/3/10, pause and quit callbacks;
  completed and early-quit artifacts identical for any K; a turn-8 checkpoint
  equal to the every-turn writer's files, resuming identically; Ctrl-C deferral
  writing the every-turn writer's turn-8 files (a reflection turn) and resuming
  identically; inertness off the main thread and over custom handlers; and
  compact atomic writes.
- `tests/test_convert_events_columnar.py`: columnar against per-row conversion
  for pyarrow and arro3 batches, including value types, optional columns,
  nulls and unknown codes.
- `tests/test_batch_worker_threads.py`: the default and user-override
  behavior of `RAYON_NUM_THREADS`, and that the pool uses the initializer.

## Reproduce

The comparison tooling is scratch tooling and is not committed. It runs each
case as a CLI subprocess against a chosen source tree (`PYTHONPATH`). It
hashes every artifact, excluding only `metadata.generated_at`, and launches
base and new as concurrent pairs for timings. `scripts/benchmark_headless.py`'s
`benchmark()` was run against both trees with `chronicler_agents` shadowed by a
package that raises `ImportError`, so the pure-Python lane was used. Generated
runs were kept outside the repository.
