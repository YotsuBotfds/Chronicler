# Turn speed, October 2026

Branch `perf/turn-speed`, from `main` `b3ad9a4` (PR #42), merged without
rebase with `c8f7eb4` (PR #43). Every change keeps every output byte:
`state.json`, its historiography and languages sidecars, memory streams,
`agent_events.arrow`, validation sidecars, chronicles, bundles and gate
reports are identical to `main`'s (proof below). No RNG draw, candidate set
or floating-point evaluation order changed.

## Summary

Process CPU per turn, mean of two paired runs of base `b3ad9a4` and head on
the same host, alternating, uninstrumented; wall in brackets. Agents is the
median alive over the measured turns.

| World | Agents | Base turn | Head turn | Speed-up | Whole process |
| --- | ---: | ---: | ---: | ---: | ---: |
| 12 regions scaled, 43,700 start | 53,300 | 1,717 ms (1,571) | 651 ms (676) | **2.64x** | 64.9 -> 28.5 s |
| 12 regions scaled, 18,800 start | 23,700 | 437 ms (405) | 206 ms (213) | **2.12x** | 15.6 -> 8.2 s |
| procedural 48 x 10, 300 turns | 630 | 129.9 ms (134.7) | 117.0 ms (121.3) | **1.11x** | 45.6 -> 39.4 s (1.16x) |
| default (gate) world, 500 turns | 175 | 43.5 ms (46.7) | 37.1 ms (39.0) | **1.17x** | 24.6 -> 20.7 s (1.19x) |

"Whole process" is the child's user + sys CPU from start to exit, including
imports, world generation, warm-up turns, the final saves and the bundle;
for the gate world that is what each of the 200 seeds of a full gate costs.
The scaled worlds gain most from the native drift (change 1) and the
OpenBLAS spin (change 3); the small worlds from serialization (2, 10, 11),
the politics bridge (4, 5) and schema reads (9).

Timing used `main` `b3ad9a4`. `main` then moved to `c8f7eb4` (PR #43: a
merchant-hub rule for worlds with 5+ living civs, gate tooling; no Rust
change); the branch was merged with it and identity re-checked against it
(below). The rule changes the procedural world's history, not its cost
structure.

## Method

* **CPU, not wall.** Another agent's procedural gate held 3 of the 4 cores
  throughout (load 2-6), so wall time is noisy. Turn and phase times are
  process CPU (`time.process_time`, every thread, so native rayon work and
  BLAS threads count); whole runs are `getrusage` of the child (user + sys).
  Hardware counters are not available: the VM exposes no CPU PMU
  (`/sys/bus/event_source/devices` has no `cpu`), so `perf stat -e
  instructions` cannot count, and `perf` is not installed.
* **Machine.** 4-core Xeon at 2.1 GHz (AVX-512 capable; the extension is
  built for the x86-64 baseline), Python 3.13.17, release extension built
  with `maturin develop --release --locked`.
* **Settings.** `RAYON_NUM_THREADS=1` (what batch and gate workers set),
  `PYTHONHASHSEED=0`, `OPENBLAS_THREAD_TIMEOUT` unset. Base is an export of
  `b3ad9a4` with its own native build (`c26d6cd2...bb99`); head is this
  branch (`a6d0de13...6d31`).
* **Worlds.**
  * *Gate world*: the CLI default (8 regions, 4 civs, about 175 agents),
    hybrid, validation sidecars, 500 turns: what the 200-seed gate runs.
  * *Procedural 48 x 10*: 48 regions, 10 civs, about 630 agents, hybrid,
    sidecars, 300 turns.
  * *22k and 52k*: the 12-region template world scaled to 18,800 and
    43,700 starting agents (`scripts/agent_scale_benchmark.py`'s scaling),
    about 23,700 and 53,300 alive; 20 warm-up and 8 measured turns.
* **Tools.** `scripts/turn_phase_profile.py` (new) wraps `run_turn_result`,
  the functions it calls two levels down, the snapshot builders of the main
  loop, every `AgentBridge` method and every native simulator method with
  process-CPU timers and books cyclic-GC pauses separately; exclusive times
  add up to the turn. The native tick was split with temporary per-phase
  process-CPU marks in a copy of `tick.rs` and `knowledge.rs` (not
  committed). py-spy 0.4.2 (`--nonblocking`, raw stacks) for drill-downs.
* **Identity.** `scripts/turn_speed_identity.py` (new) runs nine cases
  against a source tree and native build and compares every file:
  `--agents off` 300 turns (seeds 42, 7), hybrid 200 turns (42 and 7 with
  sidecars, 1234), procedural 48 x 10 hybrid with sidecars (150 turns,
  seed 42) and off (200 turns, seed 7), scaled 22k with sidecars (30 turns)
  and 52k (20 turns). Bundles are compared decoded and as raw bytes with
  only `generated_at` blanked. 395 files per run.

## Profile before (`main` `b3ad9a4`)

Exclusive process CPU per phase (`scripts/turn_phase_profile.py`, mean of
the measured turns; the wrappers add up to 18% to a turn, most in the
procedural world: compare the summary). `native.*` is a call into the
extension; `gc.gen2` the cyclic collector's full passes;
`main.write_state_checkpoint` the resumable checkpoint every 10 turns
(state JSON plus the historiography and languages sidecars).

**52k agents** (turn 1,921 ms instrumented)

| Phase | ms | Share |
| --- | ---: | ---: |
| `native.tick` (agent tick) | 1,343 | 69.9% |
| `governance_runtime.tick_governance` | 70.5 | 3.7% |
| `gc.gen2` | 57.3 | 3.0% |
| `ecology._tick_ecology_rust` (Python post-pass) | 39.0 | 2.0% |
| `native.get_snapshot` (3 exports) | 37.2 | 1.9% |
| `mutual_aid._populations` | 30.1 | 1.6% |
| `culture.apply_value_drift` | 28.3 | 1.5% |
| `bridge.aggregate_events` | 18.6 | 1.0% |
| `bridge.refresh_snapshot_metrics` | 13.5 | 0.7% |
| `contact_ledger._end_of_turn_inputs` | 13.2 | 0.7% |

The Python rows here are inflated by OpenBLAS threads spinning after the
Gini's threaded dot product (change 3): the same rows fell 2-7x when only
the spin was removed.

Native tick by phase (temporary per-phase marks, 1 rayon thread):

| Tick phase | 52k ms | Share of tick | 22k ms | Share of tick |
| --- | ---: | ---: | ---: | ---: |
| spatial drift | 1,057 | 83.8% | 226 | 74.7% |
| knowledge (propagation 36 / 20) | 50.6 | 4.0% | 20.0 | 6.6% |
| marriage | 39.0 | 3.1% | 8.5 | 2.8% |
| decisions | 25.0 | 2.0% | 13.6 | 4.5% |
| relationship drift | 19.0 | 1.5% | 8.2 | 2.7% |
| needs | 13.9 | 1.1% | 3.8 | 1.3% |
| household consolidation | 11.4 | 0.9% | 3.8 | 1.2% |
| everything else | 45 | 3.6% | 18 | 6.2% |

**22k agents** (turn 425 ms instrumented)

| Phase | ms | Share |
| --- | ---: | ---: |
| `native.tick` | 299.2 | 70.4% |
| `ecology._tick_ecology_rust` | 13.9 | 3.3% |
| `governance_runtime.tick_governance` | 13.8 | 3.3% |
| `native.get_snapshot` | 8.6 | 2.0% |
| `gc.gen2` | 7.7 | 1.8% |
| `politics.call_rust_politics` | 4.0 | 0.9% |
| `culture.apply_value_drift` | 3.9 | 0.9% |
| `mutual_aid._populations` | 3.6 | 0.8% |
| `contact_ledger._end_of_turn_inputs` | 3.5 | 0.8% |
| `bridge.refresh_snapshot_metrics` | 3.5 | 0.8% |

**Procedural 48 x 10** (turn 146.7 ms instrumented; flat)

| Phase | ms | Share |
| --- | ---: | ---: |
| `main.write_state_checkpoint` | 14.0 | 9.5% |
| `gc.gen2` (+ gen0/gen1 3.8) | 11.7 | 8.0% |
| `governance_runtime.tick_governance` | 10.4 | 7.1% |
| `bridge.write_sidecar_snapshot` | 5.1 | 3.5% |
| `native.tick` | 5.1 | 3.5% |
| `simulation.phase_action` | 4.3 | 3.0% |
| `agent_bridge.build_region_batch` | 3.4 | 2.3% |
| `politics.call_rust_politics` | 3.2 | 2.2% |
| `provenance._observe_one` | 2.8 | 1.9% |
| `main.get_perceived_stat_with_accuracy` | 2.2 | 1.5% |

**Gate world** (turn 47.0 ms instrumented; flat)

| Phase | ms | Share |
| --- | ---: | ---: |
| `main.write_state_checkpoint` | 4.91 | 10.4% |
| `governance_runtime.tick_governance` | 3.78 | 8.0% |
| `politics.call_rust_politics` | 2.50 | 5.3% |
| `native.tick` | 1.70 | 3.6% |
| `gc.gen2` | 1.62 | 3.4% |
| `agent_bridge.build_region_batch` | 1.31 | 2.8% |
| `bridge.refresh_snapshot_metrics` | 1.16 | 2.5% |
| `bridge.write_sidecar_snapshot` | 1.15 | 2.5% |
| `run_turn` (its own lines) | 1.03 | 2.2% |
| `simulation.phase_action` | 0.95 | 2.0% |

py-spy of the base gate run added: the checkpoint was 80% world JSON (the
events timeline through wrap serializers), the politics bridge 60% arro3
`to_pylist`, arro3 `batch.schema` reads 2.5% of the run, memory-stream saves
(pure-Python indented JSON) 1.2%.

## Changes

Each is one commit; identity was checked after each (395 files, 0
differences) and every Rust change against a base `scale_bench --hash` too.

Savings are CPU per turn measured right after each change, against the
state before it, in the world where the change matters most.

| # | Commit | Change | Saving |
| ---: | --- | --- | --- |
| 1 | `ed40e4e` | Native drift in lanes | 52k: drift 1,057 -> about 390 ms; native tick 1,264 -> 593 ms |
| 2 | `935393b` | `exclude_if` instead of wrap serializers | 500-turn state dump 80 -> 13 ms; gate run 27.4 -> 25.1 s |
| 3 | `65ff0b7` | Short OpenBLAS idle spin | 52k: turn 944 -> 646 ms CPU (963 -> 663 ms wall) |
| 4 | `be47a99` | Politics op batches through `pylist` | gate world: 1.4 -> 0.3 ms (with 5) |
| 5 | `1373ab1` | Read each op batch's schema once | gate world: `_batch_to_dict` 1.36 -> 0.44 ms |
| 6 | `ab553ca` | Knowledge propagation without per-packet HashMap | 52k: propagation 35.7 -> 28.4 ms |
| 7 | `abab14d` | `IdSlots` id -> slot table | 52k: relationship drift 19.0 -> 1.4, needs 13.9 -> 4.6, decisions 25.0 -> 17.9, knowledge (6 + 7) 50.6 -> 28.3 ms |
| 8 | `58f566b` | Fishery counts with `bincount` | 52k: ecology post-pass 19.4 -> 2.3 ms |
| 9 | `17b0b67` | `columnar.schema_names` | gate world: schema reads 2.5% -> 0.4% of run samples |
| 10 | `8011e3c` | Memory streams reuse entry JSON | 500-turn streams: 43 -> 3 ms a save |
| 11 | `50df0be` | `exclude_if` predicates as C callables | re-serializing 9 states: 0.19 -> 0.15 s |

### 1. Native drift: a cell's agents in lanes (`spatial.rs`)

Exact drift was 84% of the native tick at 52k and 75% at 22k. Every agent
computed a distance, a direction and a density term against every agent of
its 3 x 3 block (about 2,900 per agent at 52k, 152M pairs a turn), with an
unpredictable branch per neighbour. All agents of a cell share the block,
so `drift_lanes` reads each neighbour once for 8 agents: the distance,
direction and density terms vectorise across lanes (two SSE registers per
quantity, checked in the disassembly). Each lane computes exactly the
reference expressions. Where the reference skips a neighbour, a lane adds
`+0.0` to its density sums; a sum that starts at `+0.0` is never `-0.0`
(round to nearest gives `-0.0` only for `-0.0 + -0.0`), so adding `+0.0`
leaves it unchanged and the qualifying terms keep their order. Repulsion
neighbours (within 0.05, 13% of the block) are listed per lane in block
order and summed by the reference code. Fast mode and non-finite positions
keep the per-agent path. The attractor and finishing steps are shared
helpers, unchanged.

Tried and dropped: computing repulsion branch-free in the lanes as well (one
more division per pair: 268 against 236 ms a tick in `scale_bench` 50k),
and unchecked writes of the repulsion lists (no gain).

### 2. `exclude_if` instead of wrap serializers (`models.py`)

World state, regions, civs, relationships, events, conditions, vassal
relations, snapshots, causal links and chronicle entries dropped their
dormant or empty optional fields with model-level wrap serializers. A wrap
serializer makes pydantic build the model's whole output as Python objects
and serialize that again by inference, so every checkpoint, the final save
and the bundle went through Python dicts. Field-level `exclude_if` applies
the same rule inside the native serializer: a field is left out exactly
while it holds its empty value, in declaration order. pydantic gained
`exclude_if` in 2.12; the floor is raised from 2.0 (the lockfile already
pins 2.12.5).

### 3. Short OpenBLAS idle spin (`chronicler/__init__.py`)

NumPy's OpenBLAS splits dot products of 10,000 or more values across its
threads and leaves them spinning for 2^28 cycles (about 0.1 s) afterwards.
At 52k each civ has more than 10,000 agents, so `compute_gini`'s `np.dot`
started 3 spinning threads every turn: 200 dot products plus a 0.2 s sleep
took 3.7 s of CPU. On the loaded host the spinning threads also slowed the
turn itself. `chronicler` now sets `OPENBLAS_THREAD_TIMEOUT=16` (2^16
cycles) with `setdefault` before NumPy loads. The thread count and work
split are unchanged, so results are identical (same bits checked at 10k to
100k values); a user value is kept. Worlds whose civs stay below 10,000
agents are unaffected.

### 4, 5. Politics op batches (`politics_bridge.py`)

`call_rust_politics` converted each of the twelve returned op batches
column by column with arro3's element-wise `to_pylist`, and read the field
name of each column through `batch.schema`, which arro3 rebuilds on every
access (30 us for a 60-column batch). Empty batches now give empty lists,
the others go through `columnar.pylist` (same values and types) with the
names read once.

### 6. Knowledge propagation (`knowledge.rs`)

Propagation (85% of the knowledge phase) looked up every bond target's slot
for each of the sender's packets and kept the best bond per receiver in a
freshly allocated HashMap. The living bonds are now resolved once per
sender, and the best bond per receiver is kept in an 8-entry array (an
agent has at most 8 bonds). Receivers are visited in first-seen order
instead of the HashMap's order; that order reaches no result because each
receiver appears once per packet, each roll has its own stream, and the
commit sorts the buffer by receiver first (stable).

### 7. `IdSlots` (`pool.rs` and the phases using id maps)

Relationship drift rebuilt a BTreeMap of all living agents every tick and
searched it for every bond; the pre-decision, death, knowledge and needs
phases built SipHash maps of the same ids. Agent ids are handed out
sequentially, so `IdSlots` stores each live agent's slot in a `Vec` indexed
by id, built in ascending slot order as the maps were, with a HashMap
fallback when the largest id is far above the pool capacity. The helpers
take any `SlotLookup`, so callers and tests with their own HashMap are
unchanged.

### 8. Fishery counts (`experimental/fisheries.py`)

The fishery feedback (on by default) counted each region's agents and
farmers in a Python loop over every agent of a fresh snapshot. Null-free
numeric columns are now counted with `np.bincount` (the same Python ints);
other batches keep the loop.

### 9. `columnar.schema_names`

`AgentRows.has`, the snapshot column checks and the economy result reader
asked the same few batches for their column names many times a turn, each
time through arro3's `batch.schema`. `schema_names` returns a batch's names
as a tuple, read once per batch (the four most recent batches are kept;
Arrow batches are immutable).

### 10. Memory streams (`memory.py`)

Memory streams are rewritten with `json.dumps(indent=2)`, which uses the
pure-Python encoder, on every checkpoint turn, and they only grow. Each
entry's indented text is kept while the entry (the same object holding the
very same field objects) stays at its place in the list, and the file text
is assembled as the indenting encoder lays it out. A test compares the text
with `json.dumps` over growing, edited and shortened streams.

### 11. C-level `exclude_if` predicates (`models.py`)

The predicates of change 2 are `functools.partial` over `operator.is_` and
`operator.eq` with the empty value, so no Python frame runs per optional
field per serialized model (seven per event).

## After

The same instrumented runs on the branch head: the base top 10 with head
values, then the head's own leaders that were not in the base top 10.

**52k agents**: turn 1,921 -> 676 ms instrumented

| Phase | Base ms | Head ms | Head share |
| --- | ---: | ---: | ---: |
| `native.tick` | 1,343 | 529.4 | 78.3% |
| `governance_runtime.tick_governance` | 70.5 | 17.2 | 2.5% |
| `gc.gen2` | 57.3 | 16.2 | 2.4% |
| `ecology._tick_ecology_rust` | 39.0 | 2.1 | 0.3% |
| `native.get_snapshot` | 37.2 | 12.9 | 1.9% |
| `mutual_aid._populations` | 30.1 | 3.9 | 0.6% |
| `culture.apply_value_drift` | 28.3 | 5.0 | 0.7% |
| `bridge.aggregate_events` | 18.6 | 4.6 | 0.7% |
| `bridge.refresh_snapshot_metrics` | 13.5 | 7.0 | 1.0% |
| `contact_ledger._end_of_turn_inputs` | 13.2 | 4.2 | 0.6% |
| *new in head top 10:* `settlements.extract_clusters` | | 7.5 | 1.1% |

**22k agents**: turn 425 -> 215 ms instrumented

| Phase | Base ms | Head ms | Head share |
| --- | ---: | ---: | ---: |
| `native.tick` | 299.2 | 125.0 | 58.1% |
| `ecology._tick_ecology_rust` | 13.9 | 1.5 | 0.7% |
| `governance_runtime.tick_governance` | 13.8 | 10.8 | 5.0% |
| `native.get_snapshot` | 8.6 | 6.6 | 3.1% |
| `gc.gen2` | 7.7 | 8.1 | 3.8% |
| `politics.call_rust_politics` | 4.0 | 1.5 | 0.7% |
| `culture.apply_value_drift` | 3.9 | 2.4 | 1.1% |
| `mutual_aid._populations` | 3.6 | 1.9 | 0.9% |
| `contact_ledger._end_of_turn_inputs` | 3.5 | 2.0 | 0.9% |
| `bridge.refresh_snapshot_metrics` | 3.5 | 3.7 | 1.7% |
| *new in head top 10:* `settlements.extract_clusters` | | 2.6 | 1.2% |
| *new in head top 10:* `bridge.aggregate_events` | | 2.4 | 1.1% |

At 22k the Python rows fall much less than at 52k, where the OpenBLAS
spin had inflated them; their shares rise because the tick shrank.

**Procedural 48 x 10**: turn 146.7 -> 137.6 ms instrumented

| Phase | Base ms | Head ms | Head share |
| --- | ---: | ---: | ---: |
| `main.write_state_checkpoint` | 14.0 | 8.0 | 5.8% |
| `gc.gen2` | 11.7 | 7.1 | 5.2% |
| `governance_runtime.tick_governance` | 10.4 | 10.7 | 7.8% |
| `bridge.write_sidecar_snapshot` | 5.1 | 5.0 | 3.7% |
| `native.tick` | 5.1 | 4.6 | 3.3% |
| `simulation.phase_action` | 4.3 | 4.6 | 3.3% |
| `agent_bridge.build_region_batch` | 3.4 | 3.6 | 2.6% |
| `politics.call_rust_politics` | 3.2 | 2.1 | 1.5% |
| `provenance._observe_one` | 2.8 | 3.0 | 2.1% |
| `main.get_perceived_stat_with_accuracy` | 2.2 | 2.3 | 1.7% |
| *new in head top 10:* `action_engine.resolve_action` | | 2.3 | 1.7% |

**Gate world**: turn 47.0 -> 41.3 ms instrumented

| Phase | Base ms | Head ms | Head share |
| --- | ---: | ---: | ---: |
| `main.write_state_checkpoint` | 4.91 | 2.55 | 6.2% |
| `governance_runtime.tick_governance` | 3.78 | 3.76 | 9.1% |
| `politics.call_rust_politics` | 2.50 | 1.29 | 3.1% |
| `native.tick` | 1.70 | 1.54 | 3.7% |
| `gc.gen2` | 1.62 | 0.92 | 2.2% |
| `agent_bridge.build_region_batch` | 1.31 | 1.31 | 3.2% |
| `bridge.refresh_snapshot_metrics` | 1.16 | 1.04 | 2.5% |
| `bridge.write_sidecar_snapshot` | 1.15 | 1.18 | 2.9% |
| `run_turn` (its own lines) | 1.03 | 1.01 | 2.4% |
| `simulation.phase_action` | 0.95 | 0.96 | 2.3% |

Fewer Python objects per checkpoint (change 2) also shortened the full
collections (`gc.gen2`) in the small worlds.

Native tick by phase, base -> head (per-phase marks, 1 rayon thread, same
8 measured turns):

| Tick phase | 52k base | 52k head | 22k base | 22k head |
| --- | ---: | ---: | ---: | ---: |
| spatial drift | 1,057 | 345.6 | 225.7 | 71.7 |
| knowledge | 50.5 | 28.3 | 20.0 | 12.1 |
| marriage | 39.0 | 40.4 | 8.5 | 7.4 |
| decisions | 25.0 | 17.9 | 13.6 | 7.1 |
| relationship drift | 19.0 | 1.4 | 8.2 | 0.6 |
| needs | 13.9 | 4.6 | 3.8 | 2.1 |
| household consolidation | 11.4 | 10.9 | 3.8 | 3.4 |
| everything else | 45.1 | 38.2 | 18.5 | 15.7 |
| **tick** | **1,261** | **487** | **302** | **120** |

Drift is now 70.9% of the tick at 52k and 59.7% at 22k; second is marriage
at 52k (8.3%) and knowledge at 22k (10.1%).

## Identity

* **Every commit**: the nine-case matrix of `scripts/turn_speed_identity.py`
  against `b3ad9a4` with its own native build: 395 files (states,
  checkpoints, historiography and languages sidecars, memory streams,
  chronicles, `agent_events.arrow`, validation sidecars, bundles decoded and
  as raw bytes), 0 differences after each of the eleven commits.
* **Native changes** (1, 6, 7) also against a base `scale_bench --hash`
  (native only: FNV-1a digests of the final pool and of every tick's
  events): 50,000 agents pools
  `90a9442c5f681ffb`, events `22694ea955af4649`, and 20,000 agents
  `ff640acd723b0aec` / `062789fffb94bbdc`, equal on both builds. A new Rust
  test checks every agent's lane drift against the per-agent reference bit
  for bit in 16 random worlds of 5 to 1,500 agents, some with a dense knot
  inside the repulsion radius and at the zero-distance fallback, in lane
  groups of 1 to 8.
* **After merging `main` `c8f7eb4`** (PR #43, merge `f3f8c1d`): the matrix
  re-run against a `c8f7eb4` base (its Python sources with the base native
  build; PR #43 changes no Rust): 395 files, 0 differences.
* **Subset gate 42-61** (`scripts/m53b_run_validation.py --profile subset
  --parallel 1`, 20 seeds x 200 turns, hybrid, `RAYON_NUM_THREADS=1`), run
  once on the `c8f7eb4` base and once on the head: 2,204 files compared;
  every seed directory (states, sidecars, bundles, events, chronicles) and
  `summary.md` byte-identical; the three files that name their output
  directory (`validate_report_subset.json`, `gate_decision_subset.json`,
  `gate_summary_subset.md`) are identical once each run's root is replaced
  by a placeholder, as is `run_manifest.json`. Both gates PASS (arcs FAIL,
  artifacts PARTIAL, regression FAIL and determinism SKIP informational,
  the same on both). The full 200-seed gate was not run.
* **Golden fixtures** unchanged (`git diff` on `tests/fixtures` and the
  viewer fixtures is empty).

## Findings outside the changes

* **OpenBLAS thread count reaches results.** `compute_gini` uses `np.dot`;
  NumPy's OpenBLAS splits dot products of 10,000 or more values across its
  threads, and the last bits of the sum depend on the split (checked:
  `OPENBLAS_NUM_THREADS=1`, 2 and 4 give different bits at n = 13,000,
  30,000 and 100,000). A hybrid run whose civ has more than 10,000 agents
  is therefore not reproducible across machines with different core counts
  or thread settings. Not changed here (it would change outputs); a fixed
  summation order would fix it.
* **`--parallel 1` runs `cpu_count - 1` workers** (`batch.run_batch` treats
  a value of 1 as unset), so the subset gate above ran 3 workers.
* **`uv.lock` is stale**: its `requires-dist` lists 5 of the 9 runtime
  dependencies, and `uv lock --check` already failed on `main`. This branch
  only raises the pydantic floor there.

## Remaining hotspots

Large worlds (head, 52k; shares of the turn):

1. **Spatial drift, 51%** (346 ms, 71% of the tick). Now bound by the two
   divisions and the square root per pair and by the per-lane repulsion
   lists. The extension is built for the x86-64 baseline (SSE2): wider
   vectors would keep the bits (division and square root are correctly
   rounded) but need runtime dispatch; a reciprocal would change them.
   Testing the radius on squared distances before the square root needs a
   proof that it keeps exactly the same pairs in `f32`.
2. **Marriage, 6%** (40 ms). Not changed here.
3. **Knowledge propagation, 4%** (28 ms). The rest is mostly the per-pair
   ChaCha stream setup for the transmission roll.
4. **Python around the tick, about 22%**: governance 2.5%, cyclic GC 2.4%,
   the three snapshot exports 1.9%, settlement clustering 1.1%, snapshot
   metrics 1.0%.

Small worlds (gate and procedural): flat Python, no item above 10%:
governance (9.1% / 7.8%), the checkpoint (6.2% / 5.8%: state JSON with its
growing events timeline, and the two sidecars), cyclic GC (2.2% / 5.2%),
the validation sidecar (2.9% / 3.7%), region batches (3.2% / 2.6%),
politics (3.1% / 1.5%), the action phase and the provenance observer. GC tuning
(`gc.freeze` after world generation, higher thresholds) was measured but not
adopted: it is process-global and the whole-run gain was within noise.

## Tests

On the merged head (`b1f8d8e` sources plus this document; the Rust sources
are unchanged since `abab14d`), with the head extension
(`a6d0de13...6d31`) built by `maturin develop --release --locked` into the
same environment and its compiled module checked:

* `cargo test --locked` (debug info off), run at `abab14d`: 1,009 passed,
  0 failed, 2 ignored. New: `exact_lanes_are_bit_identical_to_reference`,
  `id_slots_match_the_id_map`.
* `pytest -m "not slow" -n 2`: 6,315 passed, 3 skipped, 526 subtests.
* `pytest -m slow -n 2`: 12 passed, 3 skipped.
* No-Rust lane (a clean environment without `chronicler_agents`,
  `pytest -n 2`): 6,082 passed, 237 skipped, 526 subtests.
* Oracle lane (`scripts/run_python_oracle_checks.py`): PASS in 103.6 s,
  2,317 passed, 36 skipped, in six chunks; the new `turn-speed` chunk holds
  `tests/test_turn_speed.py` (op batch conversion against `to_pylist` for
  pyarrow and arro3, the OpenBLAS default and a user's own value, fishery
  counts against the loop, `schema_names`, memory-stream text against
  `json.dumps` over growing, edited and shortened streams) and
  `tests/test_serialization_dormant_fields.py` (each model's omission rule).

## Reproduce

    # phase profile (base: --source-root <export> --native-root <dir with its chronicler_agents>)
    RAYON_NUM_THREADS=1 python scripts/turn_phase_profile.py --target 43700 --regions 12 --civs 4 \
        --warmup 20 --turns 8 --out prof.json
    RAYON_NUM_THREADS=1 python scripts/turn_phase_profile.py --warmup 0 --turns 500 \
        --cli-arg=--validation-sidecar --out gate.json
    # identity
    python scripts/turn_speed_identity.py run out/base --source-root <export> --native-root <native>
    python scripts/turn_speed_identity.py run out/head
    python scripts/turn_speed_identity.py compare out/base out/head
