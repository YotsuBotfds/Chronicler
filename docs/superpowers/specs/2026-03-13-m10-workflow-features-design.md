# M10: Workflow Features — Design Spec

> Batch runs, interestingness ranking, forking, and intervention hooks.

**Depends on:** M7 (Simulation Depth) — interestingness scoring needs richer events.

**Architecture:** Four new flat modules (`batch.py`, `interestingness.py`, `fork.py`, `interactive.py`) plus a shared `types.py` for cross-module dataclasses. No abstraction layer — each module owns its workflow independently. `main.py` gains a dispatch layer that routes to the right module based on CLI flags.

**Refactor in `main.py`:** Extract the core run logic (world gen → turn loop → compile chronicle → write output) into a callable function:

```python
def _execute_run(
    args,
    world: WorldState | None = None,        # None = generate fresh; set for fork/resume
    memories: dict[str, MemoryStream] | None = None,  # None = create fresh; set for fork/resume
    on_pause: Callable[[WorldState, dict[str, MemoryStream], list], None] | None = None,
    pause_every: int | None = None,
    pending_injections: list[tuple[str, str]] | None = None,  # mutable list shared with on_pause callback
) -> RunResult
```

The existing `run_chronicle()` becomes a thin wrapper. Batch, fork, and interactive all call `_execute_run` with different setup and teardown. The `pending_injections` list is a mutable shared object: the `on_pause` callback appends to it, and `_execute_run()` drains it at the start of each turn (before calling `run_turn()`). Injections are processed by `_execute_run()` directly, not inside `run_turn()` — this keeps `run_turn()` pure and unchanged.

---

## M10a: Batch Runner

**New module:** `src/chronicler/batch.py`

### CLI Interface

```
chronicler --batch N [--parallel [WORKERS]] --seed BASE --turns T [--scenario path.yaml] [other flags]
```

- `--batch N` — Run N chronicles with seeds `BASE` through `BASE + N - 1`.
- `--parallel [WORKERS]` — Optional worker count. Bare `--parallel` defaults to `cpu_count - 1`. Mutually exclusive with `--llm-actions` (argparse mutual exclusion group) to prevent multiple processes hammering LM Studio.
- All other flags apply uniformly to every run in the batch.

### Output Structure

```
output/batch_{base_seed}/
  seed_{base_seed+0}/chronicle.md
  seed_{base_seed+0}/state.json
  seed_{base_seed+0}/memories_{sanitized_civ_name}.json  (one per civ)
  seed_{base_seed+1}/chronicle.md
  seed_{base_seed+1}/state.json
  seed_{base_seed+1}/memories_{sanitized_civ_name}.json
  ...
  summary.md
```

### Module Internals

- `run_batch(args) -> Path` — Top-level entry point. Creates the batch directory, builds a list of per-run arg copies (each with its own seed and output dir), dispatches either sequentially or via `multiprocessing.Pool`.
- `_run_single(args) -> RunResult` — Wrapper that calls `_execute_run()`. Returns a `RunResult` with aggregate stats only (not the full WorldState — avoids holding N states in memory simultaneously for large batches).
- `_write_summary(batch_dir, results: list[RunResult], scenario_config: ScenarioConfig | None)` — Generates `summary.md` sorted by interestingness score. Columns: rank, seed, score, boring civs, top-line stats (dominant faction, wars, collapses, tech advancements).

### RunResult Dataclass

Lives in `src/chronicler/types.py` (shared between `batch.py`, `interestingness.py`, `fork.py`):

```python
@dataclass
class RunResult:
    seed: int
    output_dir: Path
    war_count: int              # events with event_type == "war"
    collapse_count: int         # events with event_type == "collapse"
    named_event_count: int      # len(world.named_events)
    distinct_action_count: int  # unique action types across all civs
    reflection_count: int       # total era reflections generated
    tech_advancement_count: int # events with event_type == "tech_advancement"
    max_stat_swing: float       # variance of final total stats across all civs
    action_distribution: dict[str, dict[str, int]]  # civ_name -> {action_type: count}
    dominant_faction: str       # highest total stats at run end
    total_turns: int
    boring_civs: list[str]      # civs that picked the same action >60% of the time
```

**Data sources for RunResult fields:**
- `war_count`, `collapse_count`, `tech_advancement_count`: Counted from the events timeline accumulated during the turn loop (filtering by `event_type`).
- `named_event_count`: `len(world.named_events)` at run end.
- `reflection_count`: Total era reflections generated. Note: all reflections are currently created with `importance=10` in `MemoryStream.add_reflection()`, so there is no meaningful distinction between "high importance" and "all" reflections. The field counts all reflections.
- `distinct_action_count`: Derived from `action_distribution` (count of unique keys across all civs).
- `action_distribution`: Built from `Civilization.action_counts` (cumulative per-civ action counters maintained by `simulation.py`), NOT from `WorldState.action_history` (which only stores the last 5 actions per civ).
- `max_stat_swing`: Variance of the set `{total_stat_civ1, total_stat_civ2, ...}` at run end, where `total_stat = population + military + economy + culture + stability`. Measures outcome differentiation — a run where all civs converge scores 0, a run with one dominant empire and several collapsed factions scores high.
- `dominant_faction`: Civ with highest total stat sum at run end.
- `boring_civs`: Populated by `find_boring_civs()`, which checks each civ's `action_distribution` for any single action >60%.

`_execute_run()` computes these aggregate stats internally and returns only the `RunResult`. Full state is on disk in `state.json`.

### Parallel Implementation

Sequential by default. When `--parallel` is passed:
- Uses `multiprocessing.Pool(workers)`.
- Each worker gets an independent copy of args with its own seed, output dir, and RNG.
- `--parallel` and `--llm-actions` are in a mutual exclusion group. If both are passed, argparse errors out with a clear message: "Cannot use --parallel with --llm-actions (parallel LLM calls create unpredictable latency and resource contention on local inference servers)."
- Future note: if `--parallel` and `--llm-actions` are ever relaxed, each worker will need its own LLM client instances.

---

## M10b: Interestingness Scoring

**New module:** `src/chronicler/interestingness.py`

### Scoring Function

```python
def score_run(result: RunResult, weights: dict[str, float] | None = None) -> float
```

Takes a `RunResult` and optional custom weights. Returns a single float score.

### Default Weights (Hardcoded Fallback)

Canonical weight keys match `RunResult` field names. These are the keys used in scenario YAML, in `score_run()`, and in validation:

| Weight Key | Default | RunResult Field |
|---|---|---|
| `war_count` | 3 | `war_count` |
| `collapse_count` | 5 | `collapse_count` |
| `named_event_count` | 1 | `named_event_count` |
| `distinct_action_count` | 1 | `distinct_action_count` |
| `reflection_count` | 2 | `reflection_count` |
| `tech_advancement_count` | 2 | `tech_advancement_count` |
| `max_stat_swing` | 1 | `max_stat_swing` |

### Scenario-Level Weight Overrides

`ScenarioConfig` gains a new optional field:

```python
interestingness_weights: dict[str, float] | None = None
```

Keys must be valid metric names (matching the default weight table above). The scoring function merges scenario weights over defaults — scenario weights replace matching keys, unspecified keys keep defaults. Validation: keys must be in the set of valid metric names; invalid keys raise `ValueError` during scenario loading.

Example in scenario YAML:
```yaml
interestingness_weights:
  collapse_count: 8
  tech_advancement_count: 0
  war_count: 1
```

### Max Stat Swing Definition

Variance of final total stats across all civilizations, where total stat = population + military + economy + culture + stability. Measures outcome differentiation. A run where all civs converge to identical stats scores 0. A run with one dominant empire and several collapsed factions scores high.

### Boring-Civ Detection

```python
def find_boring_civs(result: RunResult, threshold: float = 0.6) -> list[str]
```

Checks each civ's `action_distribution` independently. A civ is "boring" if any single action type accounts for more than 60% of its total actions. Returns a list of boring civ names (empty if none).

The `boring_civs` field on `RunResult` is populated by calling `find_boring_civs()` inside `_execute_run()`.

In `summary.md`, boring civs are reported per-run with the offending action: `Boring: Farmer Co-ops (develop 72%)`.

---

## M10c: Fork Mode

**New module:** `src/chronicler/fork.py`

### CLI Interface

```
chronicler --fork output/seed_42/state.json --seed 999 --turns 50 [--scenario path.yaml]
```

- `--fork PATH` — Path to a saved `state.json`. Loads WorldState at whatever turn it was saved.
- `--seed` — New RNG seed for the forked future. Required with `--fork`.
- `--turns` — Additional turns to run from the fork point. Required with `--fork`.
- `--scenario` — Optional. Pass explicitly if the parent run used a scenario (for narrative style and event flavor). Not auto-detected. Note: `event_probabilities` are already persisted in `WorldState` and survive the fork automatically. However, `event_flavor` and `narrative_style` live on `ScenarioConfig` and are passed to `NarrativeEngine` — without `--scenario`, the forked run loses flavor and style while keeping probability overrides. If the fork state directory contains scenario-derived artifacts (e.g., non-default event probabilities) but no `--scenario` is passed, print a warning: "Note: forking without --scenario; event flavor and narrative style from the parent run will not be applied."
- Mutually exclusive with: `--batch`, `--interactive`, `--resume`.

### Module Internals

```python
def run_fork(args) -> RunResult
```

1. Load `WorldState` from the fork path via `WorldState.load()`.
2. Load memory stream files (`memories_{sanitized_civ_name}.json`) from the same directory as the fork state file.
3. Set `world.seed = new_seed`, re-initialize RNG.
4. Create output directory: `output/fork_{parent_seed}_t{fork_turn}_s{new_seed}/`.
5. Call `_execute_run()` with `start_turn = world.turn`, loaded state, and loaded memory streams.
6. Return `RunResult`.

### Chronicle Provenance

The forked chronicle starts with a header before the first entry:

```markdown
> Forked from seed 42 at turn 47. New seed: 999.
```

The fork produces a clean chronicle document — no parent history carried over. Parent chronicle is a separate file. To read the full history, read the parent chronicle up to the fork turn, then switch to the fork file.

### Memory Stream Carry-Forward

Fork carries WorldState and all memory streams (entries + reflections). Civs "remember" everything up to the fork point, so post-fork era reflections have full context.

Memory streams do NOT carry forward chronicle entries — those are narrative output, not simulation state.

### Memory Stream Persistence (New Requirement)

Currently `MemoryStream` objects are in-memory only. Fork mode (and resume robustness) require persistence:

- Add `MemoryStream.save(path)` and `MemoryStream.load(path)` — serialize entries and reflections to JSON.
- File format: one file per civ, `memories_{sanitized_civ_name}.json`, containing a JSON object with `civilization_name`, `entries` (list of `MemoryEntry` dicts), and `reflections` (list of `MemoryEntry` dicts). Civ names are sanitized for filenames: lowercased, spaces replaced with underscores, non-alphanumeric characters (except underscores) stripped. E.g., "Kethani Empire" → `memories_kethani_empire.json`.
- **Save frequency:** Every turn, alongside `state.json`. Memory stream files are small (each entry is a sentence + turn number + importance score). Even a 500-turn, 5-civ run produces memory files in the low hundreds of KB. The I/O cost is negligible compared to LLM calls.
- This enables fork-from-any-turn without warnings or data loss.

### Fork vs Resume

| | `--resume` | `--fork` |
|---|---|---|
| Purpose | Continue same timeline after crash/pause | Explore alternate future |
| Seed | Same as original | New seed required |
| Chronicle | Appends to existing | Fresh document with provenance header |
| Memory streams | Loaded, continue accumulating | Loaded, continue accumulating |
| Output directory | Same as original | New directory |

---

## M10d: Intervention Hooks

**New module:** `src/chronicler/interactive.py`

### CLI Interface

```
chronicler --interactive [--pause-every N] --seed 42 --turns 100 [--scenario path.yaml]
```

- `--interactive` — Enable era-boundary pauses with command prompt.
- `--pause-every N` — Pause interval in turns. Defaults to `reflection_interval` (which defaults to 10).
- Mutually exclusive with: `--batch`, `--fork`.

### Pause Mechanism

`_execute_run()` accepts optional interactive parameters (see signature in Architecture section):
- `on_pause` callback — called at pause boundaries (`turn % pause_every == 0`)
- `pause_every` — interval in turns
- `pending_injections` — mutable list shared between callback and turn loop

The `on_pause` callback receives `(world, memories, pending_injections)`. It owns the input loop — stays at the prompt until the user types `continue` or `quit`, mutating WorldState directly for `set` commands and appending to `pending_injections` for `inject`. Returns `True` to continue or `False` if the user typed `quit`.

### State Summary at Pause

Printed to stdout as formatted text:

```
=== Turn 50 / 100 | Era: CLASSICAL ===

Faction Standings:
  Kethani Empire    — pop:8 mil:6 eco:7 cul:9 stb:5 tre:22 | Leader: Ashkari III (scholarly)
  Dorrathi Clans    — pop:6 mil:9 eco:4 cul:3 stb:7 tre:15 | Leader: Gorren (aggressive)

Relationships:
  Kethani ↔ Dorrathi: HOSTILE

Recent Events (last 5 turns):
  T48: The Siege of Thornwood (Dorrathi attacked Kethani in Thornwood)
  T49: Dorrathi advanced to CLASSICAL era
  T50: Plague struck Kethani Empire (severity 5)

Active Conditions:
  Plague on Kethani Empire — severity 5, 3 turns remaining
```

### Commands

| Command | Syntax | Effect |
|---|---|---|
| `continue` | `continue` | Resume simulation until next pause boundary. |
| `inject` | `inject <event_type> "<target_civ>"` | Queue a forced event for next turn. Event fires at the start of the next turn before the normal phase pipeline, going through the same handlers as natural events. |
| `set` | `set "<civ_name>" <stat> <value>` | Immediately mutate a civ's stat. Validated: stat must be one of `population`, `military`, `economy`, `culture`, `stability`, `treasury`. Value bounds-checked (1-10 for core stats matching `Civilization` model constraints, 0+ for treasury). |
| `fork` | `fork` | Save current state + memory streams to `output/fork_save_t{turn}/`. Print the path. Continue the current run (save-point only, does not branch execution). |
| `quit` | `quit` | Compile chronicle from entries so far, write output, exit. Chronicle ends with: `> Chronicle ended early at turn {turn} of {total_turns}.` |
| `help` | `help` | Print command list with syntax and valid event types. |

### Valid Injectable Event Types

The internal event type names from `DEFAULT_EVENT_PROBABILITIES`:

- `drought`, `plague`, `earthquake` (environment events)
- `religious_movement`, `discovery`, `leader_death`, `rebellion`, `migration`, `cultural_renaissance`, `border_incident` (non-environment events)

The `help` command prints this full list. No friendly-name mapping — these are the same names scenario authors use in YAML.

### Injection Queue

`inject` does not execute the event immediately. It adds a `(event_type, target_civ_name)` tuple to a `pending_injections` list (the mutable list shared with `_execute_run()` via the `pending_injections` parameter). At the start of the next turn (before the environment phase), `_execute_run()` drains the list and fires each injection through the standard event effect handlers. Multiple injections can be queued at a single pause.

**Target resolution:** Injected events affect *only* the named civ, overriding the normal random selection. For environment events (`drought`, `plague`, `earthquake`) that normally affect `max(1, len(civs) // 2)` civilizations, injection narrows the effect to the single specified target. This is an intentional deviation — the point of `inject` is precise, directed intervention.

### Command Parsing

Simple `input(">>> ")` loop in `interactive.py`. Split on whitespace, respecting quoted strings for civ names. Match first token to command table. On parse error (unknown command, invalid event type, civ not found, stat out of bounds), print a clear error message and re-prompt. Never crash on bad input.

---

## Cross-Cutting Concerns

### CLI Mutual Exclusions

| Flag | Mutually Exclusive With |
|---|---|
| `--batch` | `--fork`, `--interactive`, `--resume` |
| `--fork` | `--batch`, `--interactive`, `--resume` |
| `--interactive` | `--batch`, `--fork`, `--resume` |
| `--parallel` | `--llm-actions` |
| `--resume` | `--batch`, `--fork` |

These are enforced via argparse mutual exclusion groups or custom validation in the argument parsing stage.

### Memory Stream Persistence Impact

Adding `MemoryStream.save()`/`.load()` and saving every turn changes the existing run behavior: single runs and resume mode now also persist memory streams. This is a strict improvement — resume mode currently loses memory context, which produces incoherent era reflections when resuming mid-run. The fix is a side effect of fork mode's requirements.

### Test Criteria

- **Batch:** `--batch 3` produces 3 output directories with correct seeds. Summary file exists and is sorted by score. Parallel mode completes without errors.
- **Interestingness:** Score function returns expected values for known inputs. Scenario weight overrides merge correctly. Boring-civ detection identifies civs with >60% same action.
- **Fork:** Fork loads state + memory streams from a prior run. Chronicle starts fresh with provenance header. Memory streams carry forward (post-fork reflections reference pre-fork events).
- **Interactive:** `continue` resumes. `inject` queues and fires events. `set` modifies stats with bounds checking. `fork` saves state. `quit` compiles partial chronicle. Invalid input prints error, does not crash.

### New Files

| File | Purpose |
|---|---|
| `src/chronicler/types.py` | `RunResult` dataclass (shared across batch, interestingness, fork) |
| `src/chronicler/batch.py` | Batch runner: sequential and parallel dispatch |
| `src/chronicler/interestingness.py` | `score_run()`, `find_boring_civs()`, default weights |
| `src/chronicler/fork.py` | Fork runner: state + memory loading, provenance header |
| `src/chronicler/interactive.py` | Interactive pause loop: state summary, command parsing, injection queue |

### Modified Files

| File | Changes |
|---|---|
| `src/chronicler/main.py` | Extract `_execute_run()`, add CLI flags, dispatch to batch/fork/interactive |
| `src/chronicler/memory.py` | Add `MemoryStream.save(path)` / `MemoryStream.load(path)` |
| `src/chronicler/scenario.py` | Add `interestingness_weights` field to `ScenarioConfig`, validation |
| `src/chronicler/models.py` | No changes expected — WorldState persistence already works |
