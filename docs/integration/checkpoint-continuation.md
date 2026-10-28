# Exact checkpoint continuation (2026-10)

Branch `feat/checkpoint-continuation` from `main` `db5eff4` (PR #53). An
external review listed exact save-and-resume as a capability investment:
long runs need a resume envelope that holds the agent pool, the random
streams, trips, registries and every other piece of native state. A known
gap from PR #51 was that a raw `WorldState.save` drops each civ's applied
tech-focus deltas (`_focus_applied_deltas`): a capped focus is active at
turns 33-63 of the wave-3 three-system world, where a raw save does not
resume exactly, and the resume tests were moved off those turns.

This branch inventories every piece of state that affects future turns
(section 2), adds a versioned resume envelope that captures all of it, with
native state written by Rust (sections 3-4), proves resume identity byte
for byte over a matrix of modes, worlds, switches and save turns
(section 6), and measures the cost (section 7). **A run without
`--checkpoint-every` is byte-identical to `main` and no slower** (section 8).
Old state files load as before, labelled as a legacy, non-exact resume.

Code: Rust `chronicler-agents/src/persist.rs` (new) and one
`persist_struct!` list per persisted struct in `pool.rs`, `region.rs`,
`named_characters.rs`, `formation.rs`, `tick.rs`, `ecology.rs`,
`ffi/batch.rs`, `spatial.rs`, `economy.rs`, `politics.rs`, `household.rs`,
`migration_drivers.rs`, `merchant.rs`, `knowledge.rs`, `movements.rs`,
`memory.rs`, `scale.rs`, `ffi/mod.rs`, `ffi/ecology_sim.rs`,
`ffi/politics_sim.rs`; Python `run_checkpoint.py` (new), `main.py`,
`agent_bridge.py`, `shadow.py`, `sidecar.py`, `artifact_io.py`,
`batch_manifest.py`. Scripts: `scripts/checkpoint_identity.py`,
`scripts/checkpoint_cost.py` (new). Tests:
`tests/test_run_checkpoint.py`, `tests/test_run_checkpoint_native.py`,
`chronicler-agents/tests/test_checkpoint_state.rs` (new),
`tests/test_wave3_combined.py`, `tests/test_wave3_techniques_combined.py`.

Every run below is Linux x86-64 (4 vCPU, shared with another agent's
validation gates), Python 3.13.17, `PYTHONHASHSEED=0`,
`RAYON_NUM_THREADS=1`, each arm in its own virtualenv with a release
extension built fresh (`maturin develop --release --locked`, its own
`CARGO_TARGET_DIR`; `chronicler_agents.chronicler_agents` verified as a
compiled extension with real `AgentSimulator`, `EcologySimulator` and
`PoliticsSimulator` classes). `main` `db5eff4` from an exported tree:
extension SHA-256 `ee58c01e...d8d4` (the bytes PR #53 recorded for its
merge). Branch: see section 9.

## 1. Usage

```sh
# Write an exact checkpoint every 25 turns (and on Ctrl-C), replacing
# checkpoint.ckpt beside the chronicle:
python -m chronicler.main --seed 7 --turns 500 --agents hybrid --simulate-only \
    --output out/chronicle.md --state out/state.json --checkpoint-every 25

# One file per checkpoint turn instead:
    --checkpoint-every 25 --checkpoint 'out/ckpt/turn_{turn:04d}.ckpt'

# Continue exactly; seed, length, mode and every switch come from the file:
python -m chronicler.main --resume out/checkpoint.ckpt --output out/chronicle.md --state out/state.json

# Extend a finished run (the final turn is checkpointed when it is a multiple):
python -m chronicler.main --resume out/checkpoint.ckpt --turns 1000 ...

# Inspect a checkpoint, and check it against this environment:
python -m chronicler.run_checkpoint out/checkpoint.ckpt --check
```

* `--checkpoint-every N` writes after every turn that is a multiple of N
  (the final turn included) and on the first Ctrl-C, after the turn
  completes. Off by default. Checkpoints are written after the turn's era
  reflection, state checkpoint and memory files, and read the run only.
* `--checkpoint PATH` (requires `--checkpoint-every`): the file, replaced
  atomically each time; `{turn}` or `{turn:04d}` in the path keeps one file
  per turn. Batch runs refuse it and write `checkpoint.ckpt` in each run's
  directory.
* `--resume FILE` reads the first bytes: a checkpoint resumes exactly; a
  state JSON file resumes as before (section 5). On an exact resume, an
  option left at its default takes the checkpoint's value; an option given
  with a different value (`--seed`, `--agents`, `--regions`, a switch, a
  tuning file, `--reflection-interval`, `--validation-sidecar`, ...) is
  refused with one line per conflict. `--turns` (default: the saved run's
  length), `--output`, `--state`, `--state-every` and the checkpoint options
  are free.
* `--resume-allow-mismatch` resumes a checkpoint of another build or
  environment (section 4). The run is labelled as not identical.
* Extending a finished run continues that run exactly, but is not a longer
  run from the start: a run's last turn forces settlement detection, which
  the longer run's same turn does not. A checkpoint before the last turn
  continues as the uninterrupted run (section 6).
* Python: `chronicler.run_checkpoint.save_world(path, world)` /
  `load_world(path)` give the same exactness to code that drives `run_turn`
  itself (the wave-3 tests); `write_checkpoint` / `read_checkpoint` take
  and return a whole `RunState`.

The resumed run writes into its `--output` directory. Every file it writes
is the file the uninterrupted run writes; the per-turn validation debug
files (`validation_summary/*_turn_NNN.json`) of turns up to the checkpoint
are written only by the run that played those turns. The consolidated
validation artifacts, the bundle, the state, memories, chronicle, shadow
log and agent events are complete.

## 2. Inventory: state that affects future turns

"Today" is `main`: a resume from the state JSON file (`--state-every`, the
final save, Ctrl-C) with the memory files beside it. *Saved*: in the state
file or its sidecars and restored by `WorldState.load`. *Rebuilt*:
recomputed identically from saved state. *Lost*: missing or reset, so the
resumed run can differ. Modes: O off (Python, with the native ecology and
politics runtimes when the extension is installed), D demographics-only,
S shadow, H hybrid. The exact checkpoint keeps every row (derived caches
are rebuilt, as marked).

### Python

| State | Modes | Affects | Today | Exact checkpoint |
| --- | --- | --- | --- | --- |
| `WorldState` model fields: regions, civs, relationships, events, named events, war, epidemics, finance, diplomacy, techniques, maritime, nomads, cities, guilds, scholarship, movements, settlements, tuning overrides, switches | all | everything | saved | pickled with the world |
| `world.agent_events_raw` (`Field(exclude=True)`) | S H | migration counts (history index), contact-ledger migrations, ecology, `agent_events.arrow` | lost (excluded from the file) | kept (compact codec, section 3) |
| `civ._focus_applied_deltas` | all | removing a capped tech focus | lost: the full modifier comes off (PR #51 gap) | kept |
| `world._prev_belief_distribution`, `_prev_priest_counts` | all | belief and clergy change signals | lost | kept |
| `world._treasury_tax_carry` | all | fractional tax carried between turns | lost | kept |
| `world._persecuted_regions` | all | persecution events | lost | kept |
| `world._settlement_source_turn`, `_settlement_transitions`, `_settlement_diagnostics`, `_settlement_offmode_logged` | all | settlement snapshot fields, transitions | lost | kept |
| `world._war_roster_sim` (the simulator an army roster was drafted from) | D S H | army rosters | lost: rosters re-drafted (by design for a new pool) | re-bound to the restored simulator (gap, section 5) |
| `world._economy_result`, `bridge._economy_result` | D S H | next turn's region batch and signals | lost | kept |
| `world._artifact_prestige_by_civ` | all | culture prestige | rebuilt each turn | kept |
| Transient signals: `_conquered_this_turn`, `_dead_agents_this_turn`, `_artifact_intents`, `_artifact_lifecycle_intents`, `_hazard_events`, `_contact_pending`, Region `_*_this_turn` | all | cleared or consumed within a turn | empty at a turn boundary | kept (empty) |
| Derived caches: `_region_map`, `_civ_map`, `_civ_index_map`, `_history_index`, `_active_trade_routes_cache`, `_active_trade_route_pairs_cache`, `_trade_route_cache_turn`, `_self_trade_civs_cache`, `_provenance_turn`, the contact-ledger, maritime, nomad and technique `_cache` slots | all | lookups | rebuilt | rebuilt (their pickles are empty) |
| Module caches: climate `_YEAR_CACHE`, `_CLUSTER_CACHE`, ecology `_HARVEST_NORMAL_CACHE` | all | pure functions of their keys | rebuilt | rebuilt |
| Historiography and languages slots | all (default on) | observational; bundle and state sidecars | saved (`state.historiography.json`, `state.languages.json`) | kept (their own JSON reducers) |
| Memory streams | all | era reflections, chronicle | saved at state-checkpoint turns before that turn's reflection: a reflection at the save turn is lost | kept as held after the turn |
| Run accumulators: snapshot history, chronicle entries, era reflections, the run's first turn, seed, scenario, pending injections | all | bundle history and counts, chronicle, epilogue, the turn seed | lost (history restarts at the resume turn; seed from the CLI) | kept |
| Agent bridge: `named_agents`, `gp_by_agent_id`, `dynasty_registry`, `_pending_dynasty_events`, `_origin_regions`, `_departure_turns`, `displacement_by_region`, `_gini_by_civ`, `_wealth_stats`, `_event_window` (20 turns of agent events), `_demand_manager`, `_movements_seeded`, the relationship, household, merchant-trip and knowledge stats histories (bundle metadata) | D S H | named characters, dynasties, exile returns, signals, Gini, event aggregation, demand shifts, movement seeding | lost: a new bridge (movement members re-seeded once from the world) | kept; `_window_stats_cache`, `_named_actor_memo`, `_post_tick_snapshot` dropped (identity-keyed or same-turn, rebuilt) |
| `EconomyTracker` (EMA history for shock detection) | D S H | economic shocks | lost | kept |
| Validation sidecar writer: relationship, memory-signature and needs rows, aggregates, community summaries, resource ledger, economy snapshots | D S H with `--validation-sidecar` | the consolidated `validation_*` files | lost: they hold only post-resume turns | kept (rows pickled as columns) |
| Economy sidecar summary | as above, turns >= 100 | `validation_economy_summary.json` | read back from the directory's files | built from this run's own snapshot texts (gap, section 5) |
| Shadow logger | S | `shadow.arrow` | lost: the file restarts | the logged columns kept; the file rewritten on resume |

### Native (`AgentSimulator` in D S H; `EcologySimulator`, `PoliticsSimulator` in O)

| State | Affects | Today | Exact checkpoint |
| --- | --- | --- | --- |
| Agent pool, 66 columns: ids, regions, origins, civ affinity, occupation, loyalty, satisfaction, 5 skills, age, displacement, life events, promotion progress, three personality traits, three cultural values, belief, both parents, wealth; 8 memory slots (type, source civ, turn, intensity, decay, gates, count, legacy); six needs; 8 relationship slots (target, sentiment, bond type, formed turn, count: spouses and households); synthesis budget; position x, y; settlement and movement ids; trip phase, destination, origin, good, cargo, turns, 16-hop path, path length and cursor, home region; 4 knowledge packets (type and hops, source region, turn, intensity, civ); arrived flag; alive flags; count; next id; free-slot stack | every agent outcome | lost: a new pool spawned from region populations (new ids, people, positions, families, trips, packets) | kept, every slot and the free-slot order |
| Random streams | all draws | no generator state is kept between ticks: every stream derives from the master seed, the turn and a stream id, so it is rebuilt | master seed and turn kept |
| `RegionState` x regions (61 fields) | ecology, economy, demographics | rebuilt: Python re-sends them each turn (`set_region_state`) | kept |
| Named-character registry (agent, role, civ, origin, born, promotion turn and trigger, parents, history) | promotions, characters | lost | kept |
| Spatial: grids, attractors, initialised flag, settlement grids, last diagnostics | drift, urban classification | rebuilt for a new pool | kept |
| Merchants: route graph (re-sent each tick), cargo per mode, shadow ledger (reserved, in transit, pending delivery per region and good), delivery buffer (debits, arrivals, return credits, diagnostics), trip stats and sea log | trips in flight, hybrid deliveries | lost | kept |
| Movements: table (re-sent each tick), re-seeding requests, stats, reforms, cover | movement membership | re-seeded from saved members | kept |
| Queues: war casualties for the next tick, movement leaders for the next promotion pass, promotion memories written at the next tick | deaths, leaders, memories | lost (non-empty at a turn boundary after a war or a promotion) | kept |
| Counters: kin-bond failures, formation, demographic debug, last tick deaths/births/alive, household stats with migration drivers, knowledge stats | bundle metadata, diagnostics | reset | kept |
| Configs: ecology, economy, politics, river topology, extraction switches, tick options (scale mode, sort profiling), hybrid economy mode, recompute context | every tick | rebuilt from tuning (the recompute context reset) | kept |
| `EcologySimulator` regions, config, river topology, recompute context (O) | off-mode ecology | regions re-sent each turn; context reset | kept |
| `PoliticsSimulator` config (O) | off-mode politics | rebuilt from tuning | kept |
| `get_snapshot()` cache | none (a pure function of the pool) | rebuilt | skipped (`persist_struct!` `skip`) |

Measured today (`main` behaviour, a legacy resume at turn 30 of 60, seed
42, compared with the uninterrupted run): off mode 6 of 9 files differ (the
bundle, chronicle and every memory file; the state file happens to match
in that world), demographics-only 9 of 9, shadow 11 of 11, hybrid with
validation sidecars 32 of 44 (state, bundle, agent events, every
consolidated and later per-turn validation file). The exact checkpoint at
the same turn: 0 of each.

## 3. The resume envelope

```text
MAGIC            20 bytes  b"\x89CHRONICLER-CKPT\r\n\x1a\n"
header length    u32 LE
header           JSON (sorted keys, no NaN)
sections         concatenated, each zlib (level 1)
```

Header: `format` (`chronicler-run-checkpoint`), `version` (1), `turn`,
`seed`, `start_turn` (the run's first turn), `num_turns`, `world` (name,
regions, civilizations, geography), `flags` (every simulation switch:
campaigns, mutual aid, fisheries, governance, contact ledger, epidemiology,
finance, diplomacy, techniques, maritime, agendas, nomads, cities,
movements, guilds, scholarship, historiography, languages), `run_config`
(agent mode, scale mode, sidecar and relationship-stats options, the
simulation and output arguments as the batch manifest records them, the
resume label and lineage), `exact`, `lineage`, `identity` and `sections`
(name, codec, offset, length, raw length, SHA-256 of the stored bytes).

Sections:

* `python`: one pickle (protocol 5) of the `RunState`: world, memory
  streams, history, chronicle entries, era reflections, pending injections,
  run origin, seed, length, agent bridge, ecology and politics runtimes,
  economy tracker, scenario and run configuration. One pickle keeps shared
  references shared (the bridge's great persons are the world's). Each
  native simulator is pickled as a reference to its own section. Agent
  event records pickle as their positional fields (half the bytes, twice as
  fast to load as the default slot state); the validation rows as columns.
* `native.agent.0`, or `native.ecology.0` and `native.politics.0`: the
  simulator's `checkpoint_state()`.

Native blob (`persist.rs`): magic `CHRNSTAT`, state version (u32, 1), kind
(1 agent, 2 ecology, 3 politics), the FNV-1a 64 fingerprint of the kind's
schema string, then every field in declaration order (little-endian
integers, floats as their bits, lengths as u64, maps in key order).
`persist_struct!` lists each struct's fields and destructures it without
`..`, so adding a field to any persisted struct fails to compile until it
is persisted or explicitly skipped as derived; `persist_enum!` matches
every variant. The schema string names every field and type
(`AgentSimulator{pool:AgentPool{ids:Vec<u32>,...`, from
`checkpoint_schema()`), so any layout change changes the fingerprint.
Decoding refuses another magic, version, kind or fingerprint, a truncated
blob and trailing bytes. Saving takes `&self`: it reads only.

Loading (`read_checkpoint`): the magic, header, version and section bounds;
each section's SHA-256 and raw length; the identity (section 4); the native
blobs restored by Rust; the pickle restored by a loader that constructs
only Chronicler classes (and the two slot reducers), a few standard
containers, paths and dates, and NumPy arrays. Checkpoints are trusted
local files like the rest of a run directory; the digests detect
corruption, not tampering. After loading, the war-roster marker is re-bound
to the restored simulator, and the sidecar writer and shadow logger are
pointed at the new output directory (the shadow file is rewritten from its
logged turns). The resumed run then skips world generation, scenario,
tuning, every switch and the runtime construction.

Dormant state stays out: a switched-off system's state is `None` and its
switch `False` in the header; a pure-Python off-mode checkpoint has no
native section. Nothing is added to the state file, the bundle or any
other output of a run that does not checkpoint.

## 4. Build identity and the override

The header's `identity`: the `chronicler` package digest (SHA-256 over the
running package's `.py` files) and Git revision when known; the native
extension's SHA-256 and size and each simulator's state layout
(`v1:<fingerprint>`); the interpreter (implementation, version, machine),
package versions (NumPy, SciPy, PyArrow, Pydantic, arro3, chronicler-agents),
the thread environment (OpenBLAS, OMP, MKL, Rayon and the rest the batch
manifest records) and, when no OpenBLAS/OMP thread count is set, the CPU
affinity count. An exact resume requires all of them to match: any
difference is refused, with one line per difference and the override named.

`--resume-allow-mismatch` loads anyway. Native state still needs the same
layout (a blob of another layout is refused by Rust: it cannot be decoded),
and a pickle from another source may fail to load if its classes changed.
The run's bundle gets `metadata.resume = {"kind": "checkpoint", "exact":
false, "turn": k, "mismatches": [...]}`, and its later checkpoints say
`"exact": false` and carry the label, so a run continued from them keeps
it. An exact resume adds nothing to the bundle (so it stays identical); a
resume of a run that was itself labelled carries the saved label over.

## 5. Legacy state files, and the gaps closed

`--resume state.json` loads exactly as on `main` (world from the file,
memory streams from `memories_*.json` beside it, a new bridge and
runtimes), prints a warning and labels the bundle `metadata.resume =
{"kind": "legacy-state", "exact": false, "turn": k}`. `execute_run` called
with `args.resume` naming a state file does the same; naming a checkpoint,
it resumes exactly. `WorldState.save`, the state file format and
`chronicler.checkpoint_replay` are unchanged.

Gaps found, each closed by the envelope or by a fix it needed:

1. **Tech-focus applied deltas** (PR #51): kept. `test_wave3_combined`'s
   three-system resume test saves again at its original turn 62 (the first
   turn from 30 with live epidemic, loan and treaty; a capped focus is
   active from 33 to 63) from an exact checkpoint; a new test shows the raw
   state file diverges there. The four-system test drops the raw-save
   condition (its save turn, 40 on seed 44, did not move).
2. **Every other private attribute** of the world, civs and regions, the
   excluded `agent_events_raw`, the bridge, the tracker and the native
   state: kept (section 2). No field or cache had to change.
3. **Economy sidecar summary**: `validation_economy_summary.json` was built
   by reading `validation_summary/economy_turn_*.json` back from the
   directory (snapshots every 10 turns from turn 100), so a resumed run's
   summary lacked the turns before the checkpoint. The writer now keeps
   each snapshot's text and builds the summary from this run's own
   snapshots, in file-name order (the same bytes for a run in a fresh
   directory; a directory that also held another run's economy files no
   longer mixes them in). Evidence: with only this fix undone, the
   identity script on `hybrid_s42_long` resumes exactly at 99 and differs
   in this one file at 105 and 150; with it, 0 differences.
4. **War-roster simulator marker**: `world._war_roster_sim` holds
   `id(bridge._sim)`; a restored simulator has another identity, so the
   first resumed turn would run the roster check meant for a new pool. The
   marker is re-bound on load when it named the saved simulator. This is a
   precaution: with the re-bind undone, resumes at 3, 5 and 8 of
   `hybrid_s42` (four armies in the field at turn 5) still matched, because the check
   keeps every roster whose agents are all alive, which an exactly
   restored pool satisfies; an army with an empty roster would be
   re-drafted.
5. **Shadow log**: `shadow.arrow` is an Arrow file written as the run goes;
   the logger now keeps each logged turn's columns, so a resumed run
   rewrites the earlier turns before its own.
6. **Run accumulators and labels**: history, chronicle entries, era
   reflections, the run's first turn (counts, epilogue, interestingness)
   and the seed come from the checkpoint.

Nothing found needed a simulation change.

## 6. Resume identity

`scripts/checkpoint_identity.py run OUT --case ... --jobs 2`: for each case
a run of N turns without checkpoints (`plain`), one with a checkpoint at
every turn (`straight`; checkpoints outside K deleted as they appear), and
for every k in K a CLI run resumed from the turn-k checkpoint
(`resume_k`, only `--resume`, `--output` and `--state` given). It compares
`plain` with `straight` and every `resume_k` with `straight`, byte for byte
(the bundle decoded without `generated_at`, as `scripts/cities_identity.py`;
expected absences: the checkpoints, and the per-turn validation files of
turns up to k).

Matrix on `714a3a3` (package digest `37afe44a...8afa`, extension
`99c1e1d5...e12f`), two processes at a time:

| Case | World, mode, switches | N | Resume turns | Files per resume | Differences | Checkpoint at N |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| `off_s42` | template 8 x 4, off, defaults | 60 | every turn 1-59 | 9 | 0 | 0.23 MB |
| `off_s7_scholarship` | template, off, `--scholarship` | 60 | 1-59 | 9 | 0 | 0.25 MB |
| `off_s42_minimal` | template, off, every default-on switch off | 40 | 1-39 | 7 | 0 | 0.06 MB |
| `hybrid_s42` | template, hybrid, validation sidecars | 60 | 1-59 | 20-40 | 0 | 0.45 MB |
| `hybrid_s7_scholarship` | template, hybrid, `--scholarship`, sidecars, relationship stats | 60 | 1-59 | 20-40 | 0 | 0.59 MB |
| `hybrid_s1234_fast` | template, hybrid, `--agent-scale-mode fast` | 40 | 1-39 | 10 | 0 | 0.25 MB |
| `demographics_s42` | template, demographics-only | 40 | 1-39 | 9 | 0 | 0.22 MB |
| `shadow_s42` | template, shadow (`shadow.arrow`) | 40 | 1-39 | 11 | 0 | 0.24 MB |
| `proc32_hybrid_s11` | procedural 32 x 8, hybrid, sidecars | 40 | 1-39 | 24-36 | 0 | 0.75 MB |
| `proc48_hybrid_s42_scholarship` | procedural 48 x 10, hybrid, `--scholarship` | 40 | 1-39 | 16 | 0 | 0.73 MB |
| `off_s42_long` | template, off | 300 | 21 (1, 2, 3, 5, 8, 13, 21, 34, 35, 40, 46, 55, 89, 99, 100, 101, 110, 144, 150, 233, 299) | 9 | 0 | 1.26 MB |
| `hybrid_s42_long` | template, hybrid, sidecars | 200 | 19 (as above to 144, and 199) | 21-107 | 0 | 1.18 MB |
| `hybrid_s7_long_scholarship` | template, hybrid, sidecars, `--scholarship` | 200 | 19 | 21-107 | 0 | 1.60 MB |
| `proc48_off_s7_long` | procedural 48 x 10, off | 200 | 19 | 15 | 0 | 3.01 MB |
| `proc48_hybrid_s42_long` | procedural 48 x 10, hybrid, sidecars | 150 | 20 (with 75 and 149) | 27-88 | 0 | 4.04 MB |
| `scaled22k_s42` | template 12 x 4 at 18,800 agents, hybrid, sidecars | 30 | 9 (1, 2, 3, 5, 8, 13, 15, 21, 29) | 20-28 | 0 | 6.07 MB |
| `scaled52k_s7` | template 12 x 4 at 43,700 agents, hybrid | 20 | 8 (1, 2, 3, 5, 8, 10, 13, 19) | 10 | 0 | 5.40 MB |

**17 cases, 585 resume points, 13,219 file comparisons, 0 differences.**
Writing checkpoints changed nothing in any case (`plain` against
`straight`: 579 files, 0 differences). The long cases' resume turns cover
the PR #51 span (34-46), the first economy snapshots (99-110) and the last
turn. After the last code commit (`1d9eca5`, section 9), a subset again:
`hybrid_s42_long` (9 points), `shadow_s42` (4), `off_s42` (5),
`scaled52k_s7` (2), 0 differences. The tests add in-process resumes of
every mode (section 9), a resumed run's own checkpoint resumed again, and
the wave-3 worlds (all systems on, `run_turn` driven) at their original
save turns.

## 7. Cost

`scripts/checkpoint_cost.py --target T --warmup 20 --repeat R`: the
12-region template world scaled as `scripts/turn_speed_identity.py`'s
`scaled22k` (18,800 starting agents, seed 42) and `scaled52k` (43,700,
seed 7), hybrid, the checkpoint at the end of turn 20 written R times and
read back each time (medians; wall clock on the shared host, load 7-10).

| World (alive at the checkpoint) | Size | Native section (raw) | Python section (raw) | Write | Read |
| --- | ---: | ---: | ---: | ---: | ---: |
| 22k, turn 20 (22,968) | 2.51 MB | 1.99 MB (7.14 MB) | 0.52 MB (3.24 MB) | 0.17 s | 0.18 s |
| 52k, turn 20 (44,725) | 5.40 MB | 4.19 MB (14.88 MB) | 1.20 MB (7.58 MB) | 0.42 s | 0.45 s |
| 22k with validation sidecars, turn 29 (23,836) | 5.98 MB | 2.31 MB (7.42 MB) | 3.68 MB (14.23 MB) | 0.61 s | 0.60 s |

Write stages at 52k: Rust state 13 ms, Python pickle 184 ms, zlib 203 ms,
header 1 ms, atomic write with fsync 13 ms; read: verify 2 ms, Rust
restore 72 ms, Python restore 377 ms. The native state is about 310-330
bytes per living agent raw (free slots included) and compresses 3.5x. The Python section is mostly the
run's agent events (every birth, death and migration so far: the bundle's
`agent_events.arrow` needs them), and with validation sidecars the
sidecar's rows; both grow with the run, as does the snapshot history.
zlib level 1 is kept: level 6 saves 10% of the bytes for 3.7x the time.
Against a turn's CPU (112 ms at 22k, 298 ms at 52k, section 8) a
checkpoint costs about 1.5 turns; every 25 turns adds about 6%. Measured
with `--checkpoint-every 4` (8 measured turns, two checkpoints): mean wall
per turn 22k 150 -> 217 ms, 52k 330 -> 484 ms; procedural 48 x 10 with
sidecars at turns 60-120, 85 -> 186 ms (15 checkpoints of 1.5-3.1 MB).
Growth over a run (from section 6): the template world off 0.20, 0.41,
0.84, 1.26 MB at turns 50, 100, 200, 300; hybrid with sidecars 0.38, 0.69,
0.94, 1.18 MB at 50-200; procedural 48 x 10 hybrid with sidecars 1.46,
2.52, 4.04 MB at 60, 100, 150.

Before keeping it this way: agent events pickled with their default slot
state took 6.95 MB raw and 146 ms at 22k (positional fields: 3.24 MB,
57 ms); with validation sidecars the sidecar's rows pickled as dicts
took a further 10.7 MB raw at that turn (now columns).

## 8. Runs without checkpoints

`scripts/turn_speed_identity.py run` (its 9 cases: off 300 turns x 2,
hybrid 200 x 3 (two with sidecars), procedural 48 x 10 hybrid 150 with
sidecars and off 200,
the 22k and 52k worlds), `main` `db5eff4` against the branch at
`1d9eca5`, then `compare`: **399 files, 0 differences** (bundles also
raw, only `generated_at` blanked). The same matrix with `--scholarship`
on both sides: 399 files, 0 differences. Shadow (200 turns, with
`shadow.arrow`), demographics-only (200) and shadow with `--scholarship`
and sidecars (200): 11, 9 and 112 files, 0 differences
(`scripts/cities_identity.py compare`).

Turn CPU (`scripts/turn_phase_profile.py --no-instrument`, three
interleaved rounds, the side going first alternating; medians of the
per-run medians; one rayon, OpenBLAS and OMP thread; load 7-10):

| World | `main` | Branch | Ratio |
| --- | ---: | ---: | ---: |
| 22k (20 warm-up, 8 measured) | 111.8 ms (109.9-112.5) | 112.8 ms (105.8-114.3) | 1.01 |
| 52k (20 + 8) | 298.4 ms (290.9-313.0) | 297.9 ms (291.1-305.0) | 1.00 |
| procedural 48 x 10, sidecars (60 + 60) | 64.0 ms (62.8-64.3) | 64.9 ms (63.4-67.1) | 1.01 |

Within the spread of the runs. Without `--checkpoint-every` the turn does
no new work: one configuration dict per run and, in shadow mode, the
logged turn's columns kept (a few integers per civilization).

## 9. Tests and commands

Commits: `6b6141b` (native state), `90daa0f` (envelope and CLI),
`714a3a3` (tests, wave-3), `1d9eca5` (reflection interval on resume,
identity check), then documentation. Branch extension (built once from
`6b6141b`'s Rust, unchanged since): SHA-256 `99c1e1d5...e12f`, checkpoint
layouts agent `30d4998cc5af035b`, ecology `9f0d2650bcd4fbba`, politics
`b1a710f3450f5015`.

```sh
# Builds (each its own venv and target directory, two cargo jobs):
CARGO_TARGET_DIR=<target-main> python -m maturin develop --release --locked \
    --manifest-path <main export>/chronicler-agents/Cargo.toml        # venv-main
CARGO_TARGET_DIR=<target-branch> python -m maturin develop --release --locked \
    --manifest-path chronicler-agents/Cargo.toml                      # venv-branch

# Rust: 1,051 passed, 0 failed, 2 ignored (36 test binaries; 7 new)
CARGO_PROFILE_TEST_DEBUG=0 cargo test --locked --manifest-path chronicler-agents/Cargo.toml -- --test-threads=2

# Python, native extension verified first (as .github/workflows/tests.yml):
python -m pytest -q -m "not slow"                                     # 6,598 passed, 3 skipped, 15 slow deselected, 526 subtests (385 s)

# Focused: 26 passed (20 pure Python, 6 native)
python -m pytest -q tests/test_run_checkpoint.py tests/test_run_checkpoint_native.py
# Wave-3: 21 passed, including the turn-62 resume and the raw-file divergence
python -m pytest -q tests/test_wave3_combined.py tests/test_wave3_techniques_combined.py

# Offline oracle lane: PASS in 101.5 s, 11 chunks (checkpoint chunk 20 passed, 6 native skipped)
python scripts/run_python_oracle_checks.py

# Resume identity (section 6) and runs without checkpoints (section 8):
python scripts/checkpoint_identity.py run OUT --jobs 2 --case ...
python scripts/turn_speed_identity.py run OUT_MAIN   # venv-main, main's script
python scripts/turn_speed_identity.py run OUT_BRANCH  # venv-branch
python scripts/turn_speed_identity.py compare OUT_MAIN OUT_BRANCH
python scripts/turn_speed_identity.py run OUT --cli-arg=--scholarship   # both sides
python scripts/turn_phase_profile.py --target 43700 --regions 12 --civs 4 --seed 7 \
    --warmup 20 --turns 8 --no-instrument
python scripts/checkpoint_cost.py --target 43700 --seed 7 --warmup 20 --repeat 5
```

New tests: `tests/test_run_checkpoint.py` (checkpointing changes no
output; resumes at 4 and 8 of 12, through `--resume`, with a caller's
different seed and interval, and from a resumed run's own checkpoint; the
capped focus deltas against a raw save; private attributes; a pure-Python
checkpoint has no native section and records its switches; corrupt,
truncated, foreign and future-version files refused; another build refused
and the override labelled; thread settings in the identity; the restricted
loader; the shadow log and sidecar rows round trip and the economy summary
keeps earlier snapshots; the CLI adopts the checkpoint's configuration,
refuses differing options and labels a state-file resume),
`tests/test_run_checkpoint_native.py` (resume identity in hybrid with
sidecars, demographics-only, shadow and off with the native runtimes;
simulator blobs round trip and refuse another simulator, truncation and
foreign bytes; the war-roster marker re-bound) and
`chronicler-agents/tests/test_checkpoint_state.rs` plus three unit tests
in `persist.rs` (a restored pool ticks on exactly as the uninterrupted one;
region states bit for bit, NaN and -0.0 included; distinct fingerprinted
layouts; refusals).

No validation gate and none of the 15 `slow` tests were run: outputs
without checkpoints are byte-identical
to `main`, and resume identity is the qualification.

## 10. Limits

* Narration is outside the contract, as for `checkpoint_replay`: the
  checkpoint holds no LLM client or narrator state; a local or API
  narrated run resumes its simulation exactly but not its prose. All
  identity runs are `--simulate-only`.
* A resumed run does not rewrite the per-turn validation debug files of
  turns up to the checkpoint (section 1).
* Checkpoint size grows with the run: the snapshot history and, in shadow
  and hybrid, every agent event of the run (`agent_events_raw`, which the
  bundle's `agent_events.arrow` needs) are in every checkpoint.
* Cross-build resumes (`--resume-allow-mismatch`) are best effort and never
  exact. Windows and macOS were not run; the identity check makes a
  checkpoint from another platform refuse by default (machine, interpreter
  and package versions).
* Batch, fork and interactive runs write checkpoints with
  `--checkpoint-every` (batch: in each run's directory); live runs do
  not. Only the single-run CLI and `execute_run` resume. (Superseded by
  section 11: live runs write checkpoints, a viewer can ask for one, and
  `--live --resume` continues any exact checkpoint as a live session.)

## 11. Live and interactive sessions (2026-10, `feat/live-checkpoints`, `fix/interactive-checkpoints`)

Branch `feat/live-checkpoints` from `main` `25854db`. A live session
(`--live`) writes the exact checkpoints of sections 1-4, a viewer can ask
for one at a turn boundary, and `--live --resume FILE` continues a
checkpoint as a live session whose outputs equal the uninterrupted
session's and whose viewers are sent the same history. No simulation code
changed (`execute_run` gained a turn-boundary hook that reads the run
only); outputs without checkpoints are byte-identical to `main`.

Code: `src/chronicler/live_checkpoints.py` (new: the live view and the
checkpoint control), `live.py` (the `checkpoint` message, the pause, the
resumed session), `main.py` (`execute_run(turn_boundary=...)`, `--live
--resume`), `run_checkpoint.py` (`RunState.live`). Viewer: the pause
panel's **Save checkpoint** (`InterventionPanel`, `useLiveConnection`).
Script: `scripts/checkpoint_identity.py` live cases. Tests:
`tests/test_live_checkpoints.py` (offline lane, chunk `live-checkpoints`),
`tests/test_live_checkpoints_native.py`, `tests/test_live_integration.py`
(sockets), `tests/live_session_harness.py` (a session without sockets).

### Usage

```sh
# A live session with an exact checkpoint every 10 turns, as a single run:
python -m chronicler.main --live --agents hybrid --simulate-only \
    --output out/chronicle.md --checkpoint-every 10

# In the viewer's pause panel: Save checkpoint. Any client of the session
# may send the message, while paused or while the run goes on:
{"type": "checkpoint"}

# Continue a checkpoint as a live session (a live, single or batch run's):
python -m chronicler.main --live --resume out/live_checkpoints/turn_0020.ckpt \
    --output out2/chronicle.md
```

### Protocol

* Client to server: `{"type": "checkpoint"}`, nothing else. A message
  with any other field (a path, a name, a turn) is refused.
* The server answers at once with `{"type": "checkpoint_requested",
  "paused": bool}`, or `{"type": "checkpoint_error", "message"}` in the
  lobby, during a batch, after the run, for another field, or when the
  connection's handshake does not carry this session's origin and token.
* The simulation then sends `{"type": "checkpoint_saved", "turn", "path",
  "bytes", "exact", "resume_hint"}` (`resume_hint` is `--live --resume
  PATH`), or `{"type": "checkpoint_error", "turn", "message"}` when the
  write failed; the run continues either way.
* When: while running, at the next turn boundary (the end of the current
  turn, after its own checkpoints and pause); while paused, at once (the
  pause polls every 50 ms). A request sent before a pause command is
  written before that command is applied. Requests waiting at one
  boundary make one file and one reply each.
* `paused.valid_commands` lists `checkpoint`. A resumed session's first
  pause has `reason: "resumed"`.
* The file: `<output dir>/live_checkpoints/turn_<turn:04d>.ckpt`, the
  output directory being `--output`'s. A second save at the same turn
  replaces it.

### Safety

* Only a client of this session asks: the handshake's origin and token
  checks are unchanged (a client without them never reaches the message
  handler; `tests/test_live_integration.py` shows the refusal), and the
  `checkpoint` message checks them again from the connection's own
  handshake request.
* The client names nothing. The server derives the file from the turn
  number, under the output directory; it refuses a `live_checkpoints`
  that is a link or resolves outside the output directory, and a target
  that is a link or a directory; the write is atomic (temporary file,
  rename, fsync), as for every checkpoint. At most one file per turn.
* The reply carries the server's path (the client is local and holds the
  session token). Paths on the command line (`--checkpoint PATH`) remain
  the operator's.
* Checkpoints are still trusted local files (section 3): the digests
  detect corruption, the restricted loader limits what a pickle builds.

### What a live checkpoint keeps

Everything of section 2, and `RunState.live`, the session's view: the
`init` message as first sent (JSON text), every `turn` message since (the
objects the server sent, never changed after they are queued), the
snapshot pruner (turn messages leave dead civs out; the pruner carries
which), the speed and the pause interval. A resumed session's server
starts from that view; turn messages are pruned as the uninterrupted
session prunes them.

Pause commands that change the world, `inject` and `set`, are recorded:
each is appended to `run_config["interventions"]` (`{"turn", "command",
...}`; in the header and the pickle, and carried by every later
checkpoint), and when a pause changed the run, that turn's scheduled
checkpoints (`--checkpoint-every`, `--checkpoint-turns`) are written again
after the pause, so they hold what the next turn starts from (an
injection waits in the pending list). A viewer's checkpoint holds the run
as it was when written: a command applied later in the same pause is not
in it (save again after it). A resume does not replay interventions of
later pauses; the viewer repeats them (the identity runs do). `fork` is
unchanged (a legacy state file). Not kept: the viewer's own state (its
timeline position, the `set` it applies to its copy of the last snapshot)
and narration (section 10).

The resumed session has no lobby. It takes the checkpoint's configuration
as `--resume` does (an option given with another value is refused;
`--turns`, the outputs, `--checkpoint-every` and `--pause-every` are free,
the pause interval defaulting to the saved session's), restores the
speed, sends a connecting viewer the saved view (with the new length when
`--turns` extends the run) and starts paused at the checkpoint's turn:
continue, intervene, checkpoint or quit (quitting there writes nothing).
A checkpoint written by a single or batch run resumes live too, exactly;
its view is rebuilt from the run's history (each turn's snapshot,
chronicle text, and the events and named events dated in it). On the
two runs checked (off 300 and hybrid with sidecars 200 turns, rebuilding
the view of their turn-200 live checkpoints) the rebuilt history,
chronicle, events and named events equal the live session's; the first
message's world is the checkpoint's own.

Other live changes: `--live --resume` takes exact checkpoints only (a
state file is refused; the lobby's `resume_state` is unchanged);
`--live-port 0` takes a free port, shown in the printed link; `--live
--simulate-only` makes no LLM calls, as a single run (before, era
reflections called the local LLM, so a session without one stopped at
turn 10); live checkpoints record the viewer's world (civs, regions,
`worldgen`, scenario) in `simulation_args`.

### Identity

`scripts/checkpoint_identity.py run OUT --jobs 2 --case live_hybrid_s42
--case live_proc32_hybrid_s11 --case live_off_s42`, run on `93de16a` and
again on `c467b8e` (the branch's source as merged): for each
case CLI sessions driven over the WebSocket protocol as a viewer drives
them (`start`, `continue` at every pause, the case's interventions and
checkpoint requests). `plain` saves nothing; `straight` writes a
checkpoint at every turn and asks for two (one while running, one while
paused); every `resume_k` is `--live --resume` of the turn-k checkpoint
and every `resume_live_k` of a viewer's checkpoint, repeating the
interventions of later pauses. Compared: every file (as section 6), and
what a viewer is sent: the view after each turn (the `init` message with
the turn messages applied, as the server keeps it), the `init` a viewer
connecting to the resumed session receives (against the uninterrupted
view at turn k), the server's own `init` at a reconnect during the last
pause, and the view after completion.

| Case | World, mode | Turns, pauses | Viewer | Resume points | Files per resume | Differences |
| --- | --- | --- | --- | ---: | ---: | ---: |
| `live_hybrid_s42` | template 8 x 4, hybrid, validation sidecars | 20, every 5 | save asked at 3 (written at 4, then 3); at pause 10 `set` military 90 and `inject` plague on the first civ, then save | 19 + 2 | 20-24 | 0 |
| `live_proc32_hybrid_s11` | procedural 32 x 8, hybrid, sidecars | 20, every 5 | save asked at 7 (written at 8, then 7), save at pause 15 | 19 + 2 | 24-28 | 0 |
| `live_off_s42` | template 8 x 4, off (native ecology and politics) | 20, every 5 | save asked at 2 (written at 4, then 2), save at pause 5 | 19 + 2 | 9 | 0 |

A save asked while running is written at the first boundary after the
request arrives, so its turn depends on timing (the two runs above).
**Each run: 3 cases, 63 resume points, 1,205 file comparisons, 0
differences; every view equal** (each resume: the views after turns k+1
to 20, the connect view, the reconnect view and the final view). Saving
changed nothing (`plain` against `straight`: 69 files, 0 differences,
views equal), interventions included.

In-process (`tests/live_session_harness.py`, no sockets) the tests run a
12-turn template 6 x 3 world, off with the Python oracle, pausing every 4
turns: resumed at 1, 4, 6 and 11 and from two viewer saves (one asked
while running, one at pause 8); with interventions, from the checkpoint
of their turn (not repeated) and from before it (repeated); from a save
at the resumed pause; from a single run's checkpoint; and extended to 16
turns. Natively, hybrid with sidecars and off with the native runtimes,
10 turns, resumed at 2, 5 (a viewer save) and 7.

No simulation change: `scripts/turn_speed_identity.py run` (its 9 cases)
with `main` `25854db` (exported tree, its own venv and script) against
the branch on `a2bd649` and on `c467b8e`, then `compare`: **399 files, 0
differences** each time (section 8). Both venvs were built from the
lockfile, each with a release extension built from its own tree; the
Rust tree is unchanged and both builds have SHA-256 `3da1ee1f...ad0b`.

Tests on `c467b8e` (Linux x86-64, 4 shared vCPU, Python 3.13.17): the
offline oracle lane PASS (15 chunks, 2,793 passed, 61 skipped; chunk
`live-checkpoints` 13 passed, 2 native skipped); the live, checkpoint and
origin/token suites with the release extension, 89 passed. Not-slow with
the extension on `9f52673` (the source differed from `c467b8e` by one
unused import): 6,824 passed, 3 skipped, 526 subtests. Viewer: 442 tests
(3 new), lint and build passed. No `cargo test` (Rust unchanged) and no
validation gate (no simulation change).

### Cost

The view is about a third to a half of a live checkpoint: off template
world 0.27, 0.56, 0.89 MB of 0.55, 1.09, 1.69 MB at turns 100, 200, 300;
hybrid with sidecars 0.31 and 0.47 MB of 0.88 and 1.39 MB at 100 and 200
(zlib level 1, as the rest). A session that never checkpoints keeps
references to the turn messages it sends (no copies) and one JSON text of
the first message, and polls the command queue every 50 ms while paused.

### Interactive sessions (2026-10-28, `fix/interactive-checkpoints`)

Branch `fix/interactive-checkpoints` from `main` `39d5ba0` (PR #65
merged). An `--interactive` session's pauses now keep exact checkpoints
as a live session's do. Before, a command typed at a pause changed the
run after that turn's checkpoint was written, and the checkpoint was
kept: a resume from it lacked the command. On `main`, the
off template world (seed 42, 8 x 4) with a stat set and an injection at
pause 10 and a checkpoint at every turn: a `--resume` of the turn-10
checkpoint differed in 4 of 9 files (bundle, state, historiography
sidecar, a memory stream); on the branch, 0.

* `inject` and `set` typed at a pause are recorded in
  `run_config["interventions"]`, as live records them (`{"turn",
  "command", ...}`), and that turn's scheduled checkpoints
  (`--checkpoint-every`, `--checkpoint-turns`) are written again after
  the pause, holding the changed stat and the queued injection.
* One code path: `PauseInterventions` (`live_checkpoints.py`) is the part
  of `LiveCheckpoints` that records interventions and tells `execute_run`
  to write the turn's checkpoints again; `LiveCheckpoints` extends it with
  the viewer's requests and view, and `run_interactive` passes one to
  `execute_run(turn_boundary=...)`. An interactive session's checkpoints
  carry no live view (`RunState.live` is None).
* `--interactive --resume FILE` continues an exact checkpoint (a single,
  batch, live or interactive run's) as an interactive session: the
  checkpoint's configuration as `--resume` adopts it (`--turns`, the
  outputs, the checkpoint options and `--pause-every` are free; the pause
  interval defaults, as in a new session, to the reflection interval), and
  a first pause at the checkpoint's turn ("Resumed at turn k"): continue,
  type commands (applied to the loaded run and recorded at turn k) or
  quit, which writes nothing. A state file is refused, as by `--live
  --resume`.
* Other commands: `fork` still writes a state file
  (`fork_save_t<turn>/`), which is not exact; its message now says so.
  `help`, refused commands and `continue` change nothing; `quit` ends the
  run after the turn's checkpoints are written again.
* As in live mode, a resume does not replay the commands of later pauses:
  they are typed again (the identity runs do).

`scripts/checkpoint_identity.py run OUT --jobs 2 --case
interactive_hybrid_s42 --case interactive_off_s42` on `68bc026`: CLI
sessions whose terminal is a pipe. `plain` writes no checkpoint,
`untouched` only continues, `straight` writes one at every turn; every
`resume_k` (k = 1..19) is `--interactive --resume` of the turn-k
checkpoint, continuing at the resumed pause and typing the lines of later
pauses again, and `single_10` a plain `--resume` of the turn-10
checkpoint. Compared as section 6 (expected absences there, and
`fork_save_t10/` in resumes from turn 10 on); the pauses each session
made are checked too.

| Case | World, mode | Turns, pauses | Lines typed | Resume points | Files per resume | Differences |
| --- | --- | --- | --- | ---: | ---: | ---: |
| `interactive_hybrid_s42` | template 8 x 4, hybrid, validation sidecars | 20, every 5 | 5: `set` treasury 250; 10: `set` military 90, `inject` plague, `fork`; 15: `help`, a `set` on an unknown civ (refused) | 19 + 1 | 20-31 | 0 |
| `interactive_off_s42` | template 8 x 4, off (native ecology and politics) | 20, every 5 | 10: `set` stability 20, `inject` rebellion | 19 + 1 | 9 | 0 |

**2 cases, 40 resume points, 687 file comparisons, 0 differences.**
Checkpointing changed nothing (`plain` against `straight`: 44 files, 0
differences); the lines change the run (22 and 4 files differ from
`untouched`); each rewritten checkpoint records its pause's commands
(hybrid: 1 at turn 5, 2 at turn 10; off: 2 at turn 10) and the
checkpoint of the turn before does not.

Tests: `tests/test_interactive_checkpoints.py` (offline lane, new chunk
`interactive-checkpoints` with the existing `tests/test_interactive.py`; a
scripted terminal, 12-turn template 6 x 3 world, pauses every 4): saving
changes nothing and the commands change the run; the turn-4 checkpoint
holds the stat, the pending injection and the record, turn 3's does not,
turn 8's carries both pauses' records; resumed interactively at 1, 3, 4,
5, 8 and 11 with later commands typed again; a plain `--resume` at 4 and
9; `--checkpoint-turns` written again; quit at the resumed pause writes
nothing; commands at the resumed pause equal a session that paused there;
`fork` changes nothing and says it is not exact; the CLI refuses a state
file, adopts a checkpoint's configuration, refuses a differing option and
keeps `--live` exclusive. `tests/test_interactive_checkpoints_native.py`:
hybrid with sidecars and off with the native runtimes, 10 turns, commands
at pause 5, resumed at 2, 5 and 7.

No simulation change: `scripts/turn_speed_identity.py run` (its 9 cases)
with `main` `39d5ba0` (exported tree, its own script) against the branch
on `072820e`, then `compare`: **399 files, 0 differences**. One venv
from the lockfile with a release extension built from the branch's Rust
tree, which equals `main`'s (SHA-256 `3da1ee1f...ad0b`, as section 11's
first builds). Tests (Linux x86-64, 4 shared vCPU, Python 3.13.17): the
offline oracle lane PASS (16 chunks, 2,821 passed, 63 skipped; chunk
`interactive-checkpoints` 28 passed, 2 native skipped); not-slow with the
extension on `072820e`: 6,834 passed, 3 skipped, 526 subtests (10 new);
viewer 444 tests (2 new), lint and build passed. No
`cargo test` (Rust unchanged), no validation gate.

### Browser QA of the pause panel (2026-10-28, `fix/interactive-checkpoints`)

`viewer/scripts/qa-live-checkpoint.mjs` (opt-in, not CI; `viewer/README.md`)
drives a running viewer in headless Chromium (Playwright from Node) against
live sessions it starts itself (`--live --live-port 0 --simulate-only`,
stopped by their PIDs). Linux, the viewer from the Vite dev server (port
5173) and from `vite preview` of the production build (4173).

1. Opens the link the session prints (`?ws=...&token=...`), fills the
   setup form (seed 42, 20 turns, 4 civilizations, 8 regions), clicks Run
   World and waits for "Paused at Turn 5" (turn shown `5 / 20`, chronicle
   rail turns 1-5, four civilization metric rows).
2. Clicks Save checkpoint: the panel shows "Checkpoint saved at turn 5:"
   with the server's path, `<output dir>/live_checkpoints/turn_0005.ckpt`
   (the file exists), and the hint `--live --resume <path>`, both inside
   the panel. Clicks Fork (path and hint inside the panel, the hint naming
   `--fork`), then Quit: the session exits 0.
3. Starts `--live --resume <path>` and opens its link: the viewer starts
   paused at turn 5 ("Paused at Turn 5", `5 / 20`) with the same chronicle
   rail and civilization metrics as in step 1. Continue runs on to "Paused
   at Turn 10" with turns 1-10 in the rail; Quit exits 0.
4. Meanwhile opens the resumed session with the first session's (stale)
   token and with no token: each viewer shows "Could not connect to the
   live server..." and no history; the session logs no error and goes on.
   (A wrong origin is refused in `tests/test_live_integration.py`.)

Found and fixed: the shell's setup form gave its Seed field no accessible
name (the first run could not fill it; labelled now, as the older
`SetupLobby` was); the saved path and the resume hint (and the fork path
and hint) ran past the panel's right edge when the path had no space or
hyphen, cutting off the file name (a run with such a path failed 1 of 18
checks; they now wrap anywhere); the live `forked` reply's hint, checked
next, named a `--load` option the CLI does not have (it now names
`--fork` with `--seed` and `--turns` and says the state file is not
exact). After the fixes, 20 of 20 checks on the dev server (off and
hybrid) and on the built viewer (off); screenshots and reports are kept
outside the repository. Seen and not changed: before a run, the setup
surface's timeline rail draws its five placeholder era labels on top of
each other (cosmetic, unrelated to checkpoints).

### Limits

* A viewer's checkpoint and a resumed session are as exact as section 4
  allows; `--resume-allow-mismatch` labels them as there.
* Live and interactive resumes do not replay the commands of later
  pauses; `fork` writes a state file, not an exact checkpoint.
* Windows and macOS were not run; browser QA in headless Chromium on
  Linux only (no other browser, no narrow viewport).
