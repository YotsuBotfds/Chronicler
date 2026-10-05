# Tier 1 profiling-method review

Reviewed public baseline `edf7299` (PR #13 included) on 2026-10-05. Private `b665e198` excluded. Read-only source/profile review; no simulation workloads, feature changes, native builds, pushes, uploads, or paid services performed. Existing unrelated `uv.lock` modification left untouched.

## Finding and bounded recommendation

Approve reuse of the existing exact `_acc_cache` values only in `main.execute_run`'s immediately following snapshot `perception_errors` construction. Extract the existing deterministic perception arithmetic/RNG block into a private helper accepting accuracy. Keep public `get_perceived_stat` recomputing current accuracy and delegating to the helper, preserving all other callers.

The interval from cache completion (`main.py:354`) through `perception_errors` (`main.py:432`) contains reads, snapshot construction, collection copies, serialization, and pure `get_climate_phase`. It contains no simulation phase, external callback, or mutations to controllers, relationships, federation/vassal/war membership, active focus, observer faction influence, great persons, or grudges. `CivSnapshot` receives `civ.factions.model_copy(deep=True)`; `FactionState._ensure_clergy` therefore cannot mutate the observer's original faction data. `get_dominant_faction` is a pure `max` lookup. Accuracy queries can seed transient trade-route/region caches but do not alter their authoritative inputs or consume random draws.

Preserve these details literally: accuracy-zero early return, direct `getattr` of current target stat, `int((1.0 - accuracy) * 20)` arithmetic order, noise-range-zero early return, seed string `seed:observer:target:turn:stat`, SHA256 first eight digest bytes interpreted little-endian, fresh `random.Random(seed_int)`, one `gauss` call, integer conversion, clipping/clamping order, and default `max_value=100`. Snapshot observer/target/stat iteration and filtering must stay in their present order. Never retain this accuracy cache across a phase, turn, or callback.

## Existing profiling evidence

`output/performance/cli-baseline.prof` contains 60 turns / four civilizations. cProfile reports 1,420,830 calls (1,381,521 primitive), 2.090 seconds total. These are instrumented observations, not uninstrumented benchmark results.

| Function | Calls | Cumulative seconds |
| --- | ---: | ---: |
| `execute_run` | 1 | 0.8678 |
| `run_turn` | 60 | 0.4499 |
| `get_perceived_stat` | 2,985 | 0.1039 |
| `compute_accuracy` | 3,991 | 0.0734 |
| `has_active_trade_route` | 3,987 | 0.0322 |
| `get_active_trade_route_pairs` | 3,987 | 0.0275 |
| `shares_adjacent_region` | 3,987 | 0.0138 |
| `WorldState.save` | 61 | 0.0956 |
| `MemoryStream.save` | 240 | 0.0699 |

Startup is substantial: bundle import takes 0.9887 cumulative seconds, imports generally 1.280 seconds, and `builtins.compile` takes 0.6937 own seconds. Import cumulative entries overlap and must not be summed. Baseline profile startup includes source compilation; it does not establish a stable CLI speedup comparison. The narrow accepted change benefits snapshot collection, not `run_turn` itself. Kernel timing should remain flat, serving as a control for accidental mechanism changes.

Other possible hotspots are out of this change's scope. Region lookup in `shares_adjacent_region` uses repeated linear scans, but substituting `region_map` would need explicit first-versus-last duplicate-name semantics and map invalidation review. Trade pair reads intentionally return copies; eliminating them must preserve ownership and invalidation. Saving state every turn is documented crash recovery and cannot be skipped as a performance shortcut. No arithmetic precision or RNG reduction is acceptable.

## Bounded benchmark and equivalence design

Use the same `.venv/bin/python`, source baseline, arguments, environment, and filesystem class for baseline/candidate. Record Python/dependency versions and verify the native extension remains unavailable: `agents=off` alone does not guarantee Python ecology/politics when a native extension is present. Rust results are unavailable here and cannot be inferred from Python measurements.

Use three fixed bounded workloads: small one-civilization, standard four-civilization/twelve-region, and wide eight-civilization/twenty-four-region, with explicit seeds and turn counts captured in the harness manifest. Keep first repeats modest; do not expand to mass seed sweeps. One warm-up plus at least five measured repeats per selected workload is enough for initial median/dispersion reporting; increase only for unresolved timing noise. Alternate baseline/candidate order to limit system drift.

Measure separate boundaries:

1. Warm headless kernel: imports/world generation outside timing; new world for each run; one fresh `ActionEngine(world)` per turn; seed `seed + turn_num`; narrator returns empty text; `agent_bridge`, ecology runtime, and politics runtime are all `None`; final-turn `force_settlement_detection` matches CLI. Time only the turn loop. Run this without profiling, tracing, hashing, or tracemalloc.
2. Warm `execute_run`: include snapshots, memory/state writes, reflection logic with dummy clients, and bundle serialization. Use `simulate_only=True`, `agents='off'`, local dummy clients, and a dedicated isolated output/state directory per run. This is the expected improvement boundary.
3. Fresh-process CLI: `.venv/bin/python -m chronicler.main --simulate-only --agents off --seed <seed> --turns <turns> --civs <civs> --regions <regions> --output <isolated>/chronicle.md --state <isolated>/state.json`. Pass `--state` explicitly because its default otherwise writes shared `output/state.json`. Pre-warm `.pyc` equally for both source copies; record first-start timing separately if desired.

Run equivalence separately from timing. Compare complete terminal serialized state bytes, chronicle bytes, memory-file bytes, complete bundle bytes with only `metadata.generated_at` fixed to an identical value, and all returned run-result fields except the deliberately different output directory. Preserve all float representations and list/key insertion order; use neither tolerances nor broad metadata stripping. Compare per-turn snapshot bytes/hash, ordered events and named events, plus final state; terminal checks alone could hide divergent intermediate snapshots.

Instrument primitive `Random.seed`, `Random.random`, and `Random.getrandbits` calls in equivalence-only runs, preserving original delegation and call order. Cover world generation too, since it consumes draws. Record arguments and returned primitives using exact float hex encodings where appropriate. Compare trace order/count/content between baseline/candidate. Random tracing does not prove every semantic by itself, but combined with exact outputs it detects removed, reordered, or changed deterministic draws. Run cProfile and tracemalloc in distinct diagnostic runs; neither belongs in speedup measurements.

After helper extraction, target meaningful existing `test_intelligence` coverage (zero contact, exact/noisy perception, bounds, deterministic repeat), `test_main` simulate-only/off-mode coverage, and focused helper boundary equivalence where missing. Report measured median, range or dispersion, call-count reduction, peak traced Python memory separately, and exact equivalence outcome. Small/one-civ should incur negligible/no benefit; claim speedups only at boundaries with measured improvement. Keep checkpoints/RNG checks visible even if timing results are noisy.

## Remaining limits

This report reviews the proposed source boundary and existing profiling evidence. It does not certify an unimplemented diff or claim measured speedup. Rust/native and hybrid-agent behavior remain unmeasured in this environment. No blocker to the narrow snapshot-only implementation was identified.
