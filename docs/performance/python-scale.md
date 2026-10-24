# Python whole-turn scale, October 2026

Branch `perf/python-scale`, based on `perf/rust-agent-scale` @ `1365242`
(integrate/wave-1 + feat/geography-2 + the Rust agent-scale work). "Base"
below is an export of that commit with its own native build (extension
sha256 `d746298d...`, the rust-agent-scale final build); "new" is this
branch with its own build (`70d53902...`).

After the Rust agent-scale work, a turn above ~50K agents was mostly
Python: the governance tick walked every agent into frozen records, the
bridge and the Phase 10 consumers decoded snapshot columns element by
element and looped over them, and several per-turn scans grew with history
or civ pairs. This branch makes those paths columnar. **Every output is
byte-identical** (proof below); there is no behavior change and no new
dependency (NumPy was already one).

Summary (real pipeline, hybrid, median of 6 measured turns; wall / process
CPU; base and new run as concurrent pairs):

| world | start agents | base turn | new turn | CPU speedup | Python part base -> new |
| --- | ---: | ---: | ---: | ---: | ---: |
| 12 regions, fast | 100,000 | 1.79 / 2.33 s | 0.58 / 0.94 s | 2.5x | 1.79 -> 0.38 s |
| 150 regions, fast | 100,000 | 2.23 / 2.30 s | 0.84 / 0.73 s | 3.2x | 1.90 -> 0.34 s |
| 150 regions, exact | 100,000 | 2.40 / 3.04 s | 0.86 / 1.35 s | 2.3x | 2.10 -> 0.41 s |
| 12 regions, exact | 100,000 | 6.94 / 11.3 s | 6.89 / 10.1 s | 1.1x | 1.55 -> 0.32 s |

("Python part" is whole-turn CPU minus the native agent tick's CPU; it also
contains the other native calls - economy, ecology, politics, snapshot
export.) The 12-region exact world remains bound by the native tick (exact
drift and first marriage scans in 40K-agent regions), which this branch
does not change.

**Practical scale** at or below 1 s per whole turn (alive agents,
power-law interpolation between the two nearest measurements; details in
"Scale curves"):

| world, mode | base (wall) | new (wall) | base (CPU) | new (CPU) |
| --- | ---: | ---: | ---: | ---: |
| 12 regions, exact | ~31K | ~36K | ~28K | ~33K |
| 12 regions, fast | ~57K | >= 138K (0.72 s at 138K; the u16 per-region cap stops this world at ~125K starting agents) | ~52K | ~123K |
| 150 regions, exact | ~44K | ~127K | ~42K | ~90K |
| 150 regions, fast | ~39K | ~187K | ~49K | ~153K |

The host was shared (load 5-10 from other agents' gates); wall time is what
a user waits for, process CPU (all threads) is the steadier number. The
rust-agent-scale document measured ~37K exact / ~67K fast whole-turn wall
in the 12-region world for the same base under lighter load.

## Where the time went (base)

py-spy of a base 50K-agent fast-mode turn (12-region template world, 57K
alive), share of the whole turn:

| part | share |
| --- | ---: |
| governance tick (`tick_governance`) | 41% |
| - elite metrics: per-agent `AgentEliteInput` records + `compute_elite_metrics` | 27% |
| - `_build_context`: 10 columns `to_pylist`, per-row civ grouping and belief tally | 10% |
| bridge post-processing (`_process_tick_results`) | 13% |
| - `_refresh_snapshot_metrics` (per-agent polity resolution, `to_pylist`) | 7% |
| - `_convert_events`, `_aggregate_events` (20-turn window rescans) | 6% |
| native agent tick | 10% |
| `AgentRows` column decodes (`to_pylist` -> tuples) for culture, religion, settlements, runner | 6% |
| culture profile, religion tallies (4 functions), pilgrimages, rosters/recruits, urban counts | ~17% |

cProfile agreed (governance 58% of the profiled turn; profiler overhead
inflates per-call Python). In the 150-region world (30 civs) recruit
selection added a full snapshot export and per-agent scan for every army
raised, and `reconstruct_economy_result` decoded six observability columns
once per region (O(regions^2)).

## Changes

All of them keep the existing row-by-row code as the path for batches that
are not plain numeric null-free Arrow columns (the native snapshot schema is
always numeric and non-null; tests and stand-in batches can have nulls), so
`None` handling is unchanged. Results are Python ints/floats/bools, never
NumPy scalars.

1. **Governance elite metrics** (`elite_metrics_columnar.py`,
   `governance_runtime.py`). `compute_civ_elite_counts` returns the counts,
   consumption index and EMP that the runtime reads, from one civ's columns.
   It applies the kernel's validation and rules: the wealth test
   `rank / n > threshold` is monotone in the rank, so it is one comparison
   with an order statistic (`np.partition`), LOWER (`<`) or UPPER (`<=`);
   candidates (wealthy, skilled merchant/scholar/priest, GP-backed) are
   ranked with one `lexsort` over the kernel's total order
   `(-wealth, kind, agent id, GP key rank)`; GreatPerson overlays are
   processed row by row exactly as in the kernel; the ratchet/EMP
   arithmetic is the kernel's Python expressions on Python numbers. The
   adapter groups rows per civ (stable radix sort), applies the same row
   conversions (`_unit`, non-finite wealth -> 0, unknown occupation ->
   farmer) and computes the absent-GP mean satisfaction with a
   left-to-right running sum (`cumsum`), the order of the old `+=` loop.
   MMP inputs go through `mmp_from_agent_arrays` (same sorted values and
   exact `fsum`). `--agents off` still uses the record kernel.
2. **Arrow decoding** (`columnar.py`). `pylist(column)` equals
   `column.to_pylist()` and goes through `to_numpy().tolist()` for
   null-free numeric/bool columns (same Python values, float32 widened
   exactly; ~20x faster than arro3's element-wise conversion). It replaces
   `to_pylist` on snapshot, event, region and economy batches in the bridge
   and consumers, and backs `AgentRows` decodes. `AgentRows.array(s)` serve
   cached read-only NumPy columns.
3. **Bridge** (`agent_bridge.py`). Snapshot metrics (displacement,
   polity ids, per-civ wealth groups) are NumPy with the same dict orders
   and the same per-civ float32 arrays in row order, so the Gini and NumPy
   statistics see identical inputs. Event records are built positionally.
   `_aggregate_events` tallies each event-window turn once while it stays in
   the window (it rescanned up to 20 turns every turn) and finds named actors
   through per-turn sorted agent ids.
4. **One export per turn.** The post-tick snapshot is handed to the Phase 10
   capture instead of exported again. The native `AgentSimulator` also keeps
   its last export (`snapshot_cache`) until a call that can change the pool:
   every `&mut self` Python method drops it, except `get_promotions`,
   `queue_targeted_deaths` and `tick_economy`, which only read the pool
   (audited). So the next turn's Phase 2 read, every army's recruit
   selection and region transfers reuse the batch while nothing changed.
5. **Phase 10 consumers.** Region/civ faith tallies (majority belief, civ
   faith, persecution, schisms, conversion priests), cultural profiles and
   per-region assimilation counts (a full scan per foreign region), faction
   belief distributions and priest counts, the runner's urban counts,
   recruit selection (`lexsort` on the same key), roster reconciliation and
   pilgrimages (lookup of the needed agents only). `ordered_counts`
   rebuilds `{key: Counter}` with the row loop's insertion orders, which
   `most_common` ties and dict iteration depend on; small key ranges use
   `bincount` + `minimum.at` instead of sorting.
6. **Economy.** `reconstruct_economy_result` decodes each observability
   column once instead of once per region.
7. **Benchmark.** `scripts/agent_scale_benchmark.py --profile-dir` writes a
   cProfile of each child's measured turns.

Measured and not changed:

* **Perception noise** (`intelligence._get_perceived_stat_with_accuracy`):
  one `random.Random(sha256(...))` per (observer, target, turn, stat). In a
  150-region, 30-civ hybrid run at default population it is ~12% of the run
  (2,150 calls per turn, ~10 us each, almost all in Mersenne Twister
  seeding). Keys never repeat within a turn, so memoization does not help,
  and every exact shortcut still has to run MT `init_by_array` per key;
  reducing it needs an RNG change (not output-identical). It grows with
  living civs squared.
* **Event records.** `AgentEventRecord` construction for every agent event
  (~9% of a 100K fast turn) is the floor of the current
  `world.agent_events_raw` design.
* **Settlement detection** (every 15 turns) still builds per-agent position
  tuples and density grids in Python; it shows up as a periodic spike, not
  in the median turn.

## Identity proof

Base export + base build against this branch + its build, CLI
`--simulate-only`, every file in the run directory hashed
(`chronicle_bundle.json` without `metadata.generated_at`). Runs used a
source snapshot of the branch so edits could not leak in mid-run.

| Check | Result |
| --- | --- |
| Default world, `--agents hybrid`, 200 turns, seeds 42 / 7 / 1234 | byte-identical (8 files each) |
| Procedural 64 regions x 16 civs, hybrid, 150 turns, seeds 42 / 7 | byte-identical (20 files each) |
| 12-region template world scaled to 20,000 starting agents, 30 turns: hybrid seeds 42 / 7, demographics-only seed 1234, in **exact and fast** modes | byte-identical (8 / 8 / 7 files, all six) |
| Default world: demographics-only 200 turns (seed 42), shadow 120 turns (seed 7), `--agents off` 200 turns (seed 42), hybrid `--no-governance` 120 turns (seed 42) | byte-identical (7 / 9 / 7 / 8 files) |
| Subset gate (`m53b_run_validation.py --profile subset --parallel 2`, 20 seeds x 200 turns, sidecars), base vs new | both `gate_status` PASS; 2,113 run files byte-identical (the 4 report files differ only in their output paths); `validation_compare`: NO REGRESSION, every metric delta 0.0 |

The default, procedural, scaled and extra sets were run again after the
native snapshot cache (the last change), with identical results. The
whole-turn curve runs below also reproduce identical alive counts.

## Scale curves

`scripts/agent_scale_benchmark.py`, seed 42, hybrid, region capacities and
starting populations scaled to the target, 2 warm-up + 6 measured turns,
medians. Base and new ran as concurrent pairs on the shared 4-core host
(another agent's 3-process gate ran throughout, load 5-9), so wall times
are noisy; process CPU is steadier.

### 12-region template world (4 civs)

| start | alive | native tick base / new (wall) | whole turn base (wall / CPU) | new (wall / CPU) | CPU speedup | Python part base -> new (CPU) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| exact 20,000 | 22,872 | 280 / 280 ms | 570 / 722 ms | 367 / 533 ms | 1.36x | 317 -> 103 ms |
| exact 50,000 | 57,394 | 1.87 / 1.92 s | 3.11 / 3.48 s | 2.16 / 2.95 s | 1.18x | 902 -> 323 ms |
| exact 100,000 | 114,786 | 5.04 / 6.55 s | 6.94 / 11.3 s | 6.89 / 10.1 s | 1.12x | 1,546 -> 319 ms |
| fast 20,000 | 22,989 | 77 / 75 ms | 404 / 360 ms | 141 / 137 ms | 2.62x | 286 -> 63 ms |
| fast 50,000 | 57,614 | 205 / 165 ms | 1.02 / 1.14 s | 348 / 424 ms | 2.69x | 910 -> 216 ms |
| fast 100,000 | 114,848 | 337 / 426 ms | 1.79 / 2.33 s | 581 / 936 ms | 2.49x | 1,792 -> 377 ms |

### 150-region procedural world (30 civs)

| start | alive | native tick base / new (wall) | whole turn base (wall / CPU) | new (wall / CPU) | CPU speedup | Python part base -> new (CPU) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| exact 20,000 | 22,391 | 66 / 55 ms | 555 / 554 ms | 215 / 256 ms | 2.17x | 480 -> 175 ms |
| exact 50,000 | 57,172 | 174 / 176 ms | 1.25 / 1.34 s | 389 / 578 ms | 2.32x | 1,063 -> 293 ms |
| exact 100,000 | 115,129 | 409 / 453 ms | 2.40 / 3.04 s | 863 / 1,352 ms | 2.25x | 2,099 -> 410 ms |
| fast 20,000 | 22,464 | 69 / 59 ms | 545 / 506 ms | 263 / 248 ms | 2.04x | 446 -> 187 ms |
| fast 50,000 | 57,152 | 200 / 211 ms | 1.56 / 1.16 s | 537 / 403 ms | 2.87x | 982 -> 225 ms |
| fast 100,000 | 115,146 | 331 / 416 ms | 2.23 / 2.30 s | 844 / 729 ms | 3.15x | 1,903 -> 335 ms |

### Larger worlds (new only)

Run one benchmark at a time (no paired base: base needs 2-3 s per turn
already at 115K):

| world, mode | start | alive | native tick (wall / CPU) | whole turn (wall / CPU) |
| --- | ---: | ---: | ---: | ---: |
| 12 regions, exact | 30,000 | 34,319 | 0.74 / 0.90 s | 0.90 / 1.09 s (paired run) |
| 12 regions, exact | 40,000 | 45,899 | 1.37 / 1.67 s | 1.53 / 1.86 s (paired run) |
| 12 regions, fast | 120,000 | 137,970 | 0.52 / 0.73 s | 0.72 / 1.13 s |
| 150 regions, exact | 130,000 | 149,741 | 0.67 / 1.46 s | 1.28 / 2.24 s |
| 150 regions, fast | 150,000 | 172,964 | 0.45 / 0.60 s | 0.91 / 1.15 s |
| 150 regions, fast | 200,000 | 230,898 | 0.61 / 0.97 s | 1.30 / 1.91 s |
| 150 regions, fast | 300,000 | 346,403 | 3.29 / 1.44 s | 5.52 / 2.71 s (paired run, contended) |

Interpolation for the practical-scale table: 12-region exact between 34K
and 46K (wall) / 23K and 34K (CPU); 12-region fast 115K-138K (CPU);
150-region exact 115K-150K (wall) / 57K-115K (CPU); 150-region fast
173K-231K (wall) / 115K-173K (CPU). Base: between its 23K and 57K points.

## Where the time goes now

py-spy of a new 100K-agent fast-mode turn, 150-region world (118K alive,
0.77 s wall / 0.83 s CPU per turn), share of the whole turn:

| part | share |
| --- | ---: |
| native agent tick | 36% |
| bridge post-processing | 19% |
| - snapshot metrics (per-civ Gini/median/std, groups) | 7% |
| - `AgentEventRecord` construction for every event | 6% |
| - event-window summaries | 3% |
| governance tick | 12% |
| actions and campaigns (war resolution, mobilization, recruit selection) | ~11% |
| settlement detection (a detection turn fell in the window) | 6% |
| religion, culture, other Phase 10 | ~5% |

No single Python hot spot remains; the snapshot export no longer shows up.
Next candidates: the event-record list (`world.agent_events_raw` holds one
Python object per agent event for the whole run), settlement detection
(per-agent tuples and dict grids every 15 turns), the per-civ wealth
statistics, and perception noise when many civs are alive (above).

## Tests

* `python -m pytest -q -m "not slow" -n 2` with this branch's native build:
  5,397 passed, 3 skipped (base: 5,277 passed, 3 skipped; 120 new tests).
* `cargo test --manifest-path chronicler-agents/Cargo.toml` (debug, no
  debuginfo, separate target directory): 874 passed, 0 failed, 2 ignored
  (the timing gate, unchanged).
* `scripts/run_python_oracle_checks.py` stops at
  `test_checkpoint_replay.py::test_uninterrupted_matches_every_resumed_turn`
  because `platform.platform()` spawns `uname -p` on this Linux host, which
  the offline guard forbids; the code involved is unchanged here and 965
  earlier tests passed.
* New tests:
  * `tests/test_elite_metrics_columnar.py`: every output of
    `compute_civ_elite_counts` bit-identical to `compute_elite_metrics` on
    1,000 randomized civs x all 8 convention combinations (ties, GP overlays
    present/absent/duplicate, thresholds 0..1); wealth qualifier sets
    against the kernel's sorted group scan; invalid inputs rejected.
  * `tests/test_governance_columnar.py`: the whole agent branch of the
    governance adapter (row grouping, belief shares, elite counts, MMP) against
    the old record-per-agent code kept as oracle, on synthetic snapshots
    with NaN/inf/-0.0/out-of-range values and null cells, and on a native
    snapshot; the running sum against sequential Python addition.
  * `tests/test_columnar_paths.py`: whole runs (hybrid default world,
    24-region procedural, a 25x scaled world, demographics-only, shadow) with
    every columnar path forced back to its row loop and the snapshot hand-off
    disabled give byte-identical artifacts; helpers against their loops
    (including dict insertion order); `pylist` against `to_pylist` for
    pyarrow and arro3 types; event-window summaries against the previous
    implementation (`tests/legacy_aggregate_events.py`, verbatim) over 30
    randomized turns; the Phase 10 hand-off equals a fresh export every
    turn; the native snapshot cache is kept by read-only calls and dropped by
    pool-changing ones.

## Reproduce

    # profiles (cProfile of the measured turns; py-spy record --subprocesses also works)
    python scripts/agent_scale_benchmark.py --targets 50000 --agent-scale-mode fast \
        --warmup 3 --turns 4 --profile-dir prof/
    # base vs new pairs
    python scripts/agent_scale_benchmark.py --targets 20000,50000,100000 --regions 150 --civs 30 \
        --agent-scale-mode fast --warmup 2 --turns 6 \
        --source-root <base export> --native-root <dir with the base chronicler_agents> --out base.json

The identity, gate-comparison and table scripts were scratch tooling (not
committed): each case ran as a CLI subprocess with `PYTHONPATH` pointing at
the tree (and, for base, its saved native package), and every artifact was
hashed as above.
