# Consistency follow-ups (2026-10)

Branch `fix/consistency-followups` from `main` `22c021b` (PR #47), brought
to `dae4ba5` (PR #48) before any baseline was taken, so every before/after
comparison here is against `dae4ba5`. Narration, the viewer, validation
tooling, the batch runner and tests; simulation output is byte-identical
([Identity](#identity)). Each item was reproduced on `dae4ba5` with a test
before it was fixed; all five reproduced.

| Item | Reproduced on `dae4ba5` |
| --- | --- |
| 1. Account losses dated after the narrated moment | Yes: a turn-10 moment's prompt said `lost (archive sacked, turn 300); no account survives`, its mechanical chronicle `No account from the B chronicles survives: ... (turn 300)` |
| 2. Viewer panels with end-of-run values | Yes, 11 leaks in the shell, Cities, Movements and Languages (below) |
| 3. Cohort oracle counts the snapshot turn | Yes: two seeds whose community members act only on the snapshot turn PASS |
| 4. `--parallel 1` starts `cpu_count - 1` workers | Yes: a pool of 7 at 8 cores |
| 5. Nine tests fail under `pytest -n 2` | Yes: `execnet` `DumpError` on `object`, `PosixPath`, `tuple_iterator`, `mock._patch` subTest parameters |

## 1. In-world accounts as of the moment

### The defect

`historiography.AccountIndex` reads the bundle's `historiography` field,
which is exported after the run: an account's `lost_turn` is its final
loss. `prompt_block` (the narrator's IN-WORLD ACCOUNTS block) and `passage`
(the mechanical "In their own words") told a copy lost at turn 300 as lost
in a moment at turn 10, for every chronicler, and left it out of the voices
quoted. The `lost` divergence that orders the moment's events came from the
final losses too.

### The fix

`AccountIndex.as_of(AsOf)` is the index as the record knows it at a point
(`historical_context.AsOf`, PR #45's convention):

* a copy whose loss is dated after the point still stands there
  (`lost_turn` and `lost_cause` are None), so it is quoted as a voice;
* an archive's losses dated after the point are left out;
* an event's divergence is that of its accounts then: recomputed with
  `divergence()` whenever a loss was undone (exact: the bundle lists every
  account of an event with a lost copy, since a lost account is never
  `plain` and an event with a lost and a surviving copy is contested; only
  the `lost` kind depends on losses). A later loss adds no `lost`; a later
  loss of every copy does not remove one;
* accounts dated after the point are left out (a listed event never has
  any).

The view of the last loss's turn or later equals the index. Rows are
derived per event on first use. `HistoricalRecord` takes the index
(`accounts=`) and each `HistoricalView` carries it as of its point
(`view.accounts`). `NarrativeEngine` builds the record with the index; the
prompt, the mechanical chronicle and both mechanical fallbacks (batch API
and sequential) read the moment's view, `AsOf.after(last turn)`. Future
information stays in the labelled AFTER and LATER CONSEQUENCES sections.
The curator's contested bonus (`contested_bonus`, which chooses moments and
puts nothing in a prompt) still uses the final divergence, as the curator's
other scores use final characters.

### How prompts change

A saved 500-turn hybrid bundle (template seed 42, bundle version 6, 627
notable accounts of which 231 lost, SHA-256 `63899f98cd3ce741...`),
re-narrated with `--narrate ... --narrator mechanical` by `dae4ba5` and by
this branch (`scripts/narration_prompts.py capture`):

* prompts: 41 of 50 change, only inside the IN-WORLD ACCOUNTS block; loss
  lines dated after the moment 95 -> 0 (of 99; the other 4 are dated by
  then). A copy lost later is now quoted, with its biases, instead of
  "lost (archive ..., turn N)";
* mechanical chronicle: 38 of 50 entries change (the passage's voices);
  loss notes dated after the moment 9 -> 0; each entry's account ids are
  unchanged; gap summaries and metadata identical.

With an LLM narrator the prose follows these prompts. No simulation output
changes.

## 2. The viewer at the scrubbed turn

PR #45 made the civilization views read the history row at the snapshot.
The other panels and inspectors of the production shell (`App` renders
`AppShell` only) were audited for values that fall back to the end-of-run
world state, or to any later record, while scrubbing back. The scrubber's
turn T shows snapshot T; dated records (events, losses, foundings) are shown
from their own turn, as the event log does.

### Fixed (each failed on `dae4ba5`)

| Where | Leak on `dae4ba5` | Now |
| --- | --- | --- |
| Shell, before the first snapshot (a resumed run's history starts late) | The first, later snapshot stood in: civ chips, rankings, values, controllers | No snapshot: civs "Unavailable" (status, leader, era, metrics), no controllers, no world-state relationships. The world state is the present only for a bundle without history (a live session before turn 1). `civRows.snapshotPositionAt` is -1 there |
| Map, chronicle markers | The first 8 named events of the run, future ones included | Those recorded by the turn |
| Map, technique layer | Every technique of the run offered, later inventions included | Those practised by the turn |
| Region inspector, terrain | Final terrain | Terrain at the turn from the dated `terrain_transition` events; "Unavailable" if a later one cannot be read |
| Event inspector | An event pinned at a later turn stayed described after scrubbing back (inspector header, type, description, accounts) | "Unavailable", "Not yet recorded at turn T" |
| Event inspector, "Led to" | Every consequence, later ones included | Those recorded by the turn |
| Event inspector, in-world accounts (historiography) | Final losses, final `lost` divergence | As known at the turn (`accountsAsOf`, as item 1) |
| Chronicle feed | A narrated moment (or gap summary) from its first turn, telling turns not yet reached | Once its last turn has passed |
| Cities tab, selected city | Final peaks and the later fall ("fell at turn 165" at turn 150); a later city as the default focus | Peaks by the turn from its rows, the fall once it fell, "Not yet founded at turn T" before; the default focus is a city known by then (`cities.cityRecordAt`) |
| Movements tab, selected movement | "Whole record" (final peak, demands, martyrs, last leader) and the later end, labelled "after turn T"; a later movement as the default focus | Peak, demands, martyrs and leader by the turn from its rows and dated moments, the end once it ended, "Not yet founded" before; no later default focus (`movements.movementRecordAt`) |
| Languages section | Every language of the run with its final status, the endonym's final form, the final sound inventory and all sound changes; etymology forms after the turn; a word chosen later kept its etymology | Languages born by the turn, status then (extinct from `last_spoken`), endonym as the language named the people then, changes by then, the inventory only when no later (non-prehistoric) change may have altered it, forms up to the turn, no etymology before the word was coined |

`nativeNameAt` at the last turn equals the export's `native` for all 7
languages of the 500-turn bundle above.

### Checked, unchanged

* Systems tabs Epidemics, Food, Wars, Finance, Diplomacy, Techniques,
  Maritime, Nomads, Agendas (great persons' vows), Governance, Contact and
  the guild columns of Cities: tiles and tables from the snapshot, event
  lists up to the turn; names by index from the world (identity), ports
  from the fixed sea-zone geometry.
* Learning (scholarship): already as of the turn (`seatRecordAt`,
  `seatHistory`).
* Map layers Food, Epidemics, Wars, Migration, Sea and their fills: the
  snapshot, raids of the completed turn, the migration window ending at the
  snapshot; trade links: the snapshot's relationships and trade routes;
  the Region systems detail: the snapshot.
* Civilization views and inspector (PR #45); civ values and goal are set at
  world generation and do not change; region resources are set at setup.
* Event log: events up to the turn.
* Whole-run timelines with a current-turn marker, by design: the timeline
  rail (era bands, narrated spans, named-event ticks) and the systems tabs'
  turn strips and charts.
* Run-level metadata: the interestingness score in the header and the
  campaign validation ribbon.
* The region history inspector: an explicit turn window; the final
  stockpile is a separate, labelled observation.
* Character and religion: the viewer has no character, dynasty or religion
  panel; the character surface opens the techniques, agendas, governance
  and diplomacy tabs (above); faith names come from the belief registry.
* The legacy `Layout`, `TerritoryMap`, `FactionDashboard`, `StatGraphs`
  and `ChroniclePanel` are not rendered by `App` (tests only).

### Not fixed

* Map node size: the final carrying capacity. The bundle does not record
  capacity per turn; terrain transitions change it (+20 forest to plains,
  -10 plains to forest, clamped), which cannot be undone exactly.
* A language extinct, revived and extinct again: the record keeps only the
  latest extinction, so it shows living before that one.
* No browser QA (jsdom tests only).

Entry chunk (`npm run build`): 788,040 -> 791,168 bytes (Vite 788.04 ->
791.17 kB; gzip 231,989 -> 232,954 bytes); CSS 50,636 -> 51,113 bytes
(Tailwind's source scan).

## 3. Cohort oracle method 2

> Superseded as the gate's method by cohort method 3
> ([`oracle-followups.md`](oracle-followups.md) section 1): each member
> against its matched control while both live. `run_cohort_oracle(...,
> method_version=2)` re-scores method 2 exactly.

### The defect

`run_cohort_oracle` counted, for a turn-t graph and needs snapshot, the
migrations and rebellions of turns t .. t+19. Those sidecars are written at
the end of turn t's agent processing (`agent_bridge._write_sidecar_snapshot`
after the tick), as the needs oracle's are (`validation-integrity.md` §1).
In the native tick (`tick.rs`) the decisions apply first: migrants are moved
(`set_region`: the matched region is the new one), rebels' autonomy rises;
then the turn's memory intents are written (`write_all_memories`, including
`Migration` memories dated t), and bonds form from post-move positions.
`detect_communities` groups agents by bonds and memory signatures
(event type, turn, valence), so a turn-t action can shape the community and
its matching and then be counted as its outcome. Two seeds whose community
members rebel only on the snapshot turn PASS (`seeds_with_expected_direction`
2 of 2); without those rebellions they FAIL.

### The fix

Method 2 (`COHORT_ORACLE_METHOD_VERSION = 2`) counts turns t+1 .. t+20,
eligible when t + 20 < total turns (a run of N turns ticks turns 0 .. N-1);
communities, matching, both behaviours, criteria and thresholds are method
1's. Its results add `method_version: 2`, `outcome_window_start_offset: 1`
and `outcome_window_turns: 20`; `run_cohort_oracle(runs, method_version=1)`
re-scores method 1 with its bytes (no new keys). The comparator reads the
method version of every oracle, so cohort 1 against 2 is
`rebaseline_required` and never a new or resolved failure
(`test_compare_cohort_method_1_against_method_2_requires_rebaselining`). No
threshold changed.

### Method 1 against method 2 on retained sidecars

Oracle code only (`scripts/rescore_cohort_oracle.py`). The cohort oracle
reads relationship and memory sidecars, which the 48 needs sidecar sets of
`validation-integrity.md` do not hold (only `agent_events.arrow` and
`validation_needs.arrow`): none of them can be cohort-scored. Every other
directory on this machine with the four sidecars was re-scored:

| Set | Seeds x turns | Method 1 | Method 2 |
| --- | --- | --- | --- |
| `perf` subset (an earlier perf branch; bundles pruned, sidecars read alone with 200 turns; their hashes equal those recorded for the run its report scored) | 20 x 200 | PASS, 20 / 20 seeds (12 required), median effect 1.025; equals the report's cohort result field for field | PASS, 20 / 20, median 1.095 |
| `diplomacy` gate-on seed 42 | 1 x 200 | PASS, 0.434 | PASS, 0.643 |
| `epidemiology` seed 42 on | 1 x 200 | PASS, 0.693 | PASS, 0.551 |
| `gp-agendas` hybrid 42 | 1 x 200 | PASS, 0.831 | PASS, 1.028 |
| `narration` identity, procedural 11 | 1 x 150 | PASS, 0.625 | PASS, 0.633 |
| `narration` identity, template 7 | 1 x 200 | PASS, 0.981 | PASS, 0.958 |
| `narration` identity2, procedural 11 | 1 x 150 | PASS, 0.617 | PASS, 0.570 |
| `narration` identity2, template 7 | 1 x 200 | PASS, 0.895 | PASS, 0.875 |
| `perf-turn` CLI run | 1 x 200 | PASS, 0.897 | PASS, 0.889 |
| `perf-turn` 500-turn run | 1 x 500 | PASS, 1.883 | PASS, 1.883 |

(The narration identity directories hold base and new copies of each run;
the copies score identically and are listed once.) Every verdict holds
under method 2. A 20-seed batch of another branch's gate (population
entities, 42-61 x 200) was removed by its owner before it could be read;
its later batches were in progress and were not read.

### Live template subset

So few 20-seed sets were retained, and that one from older code (its
worlds' agents die out by turns 150-200), that a template subset gate was
run on this branch (the `dae4ba5` simulation; [Identity](#identity)):
`scripts/m53b_run_validation.py --profile subset --parallel 2` into a new
output root, 42-61 x 200, hybrid, release extension `735558c9...a489` built
fresh from this tree (compiled `AgentSimulator`, `EcologySimulator`,
`PoliticsSimulator` checked). Gate PASS, batch manifest verified; needs
method 4 +0.175 (+0.097), 14 of 20 seeds; every other oracle PASS
(determinism SKIP, as in every subset).

| Method | Cohort | Seeds with the expected direction | Median strongest effect |
| --- | --- | --- | --- |
| 1 (re-scored on the batch) | PASS | 20 / 20 (12 required) | 1.347 |
| 2 (the gate's report; the re-score equals it field for field) | PASS | 20 / 20 | 1.285 |

Per seed (method 1 -> 2): the chosen snapshot changes in 7 of 20 seeds;
the strongest effect changes by a median of +0.036 (-0.317 to +0.573);
seeds whose community migrates less 13 -> 14, rebels more 15 -> 13. On the
`perf` subset: snapshot changes 3 of 20, median change +0.000 (-0.226 to
+0.487), migrating less 14 -> 16, rebelling more 9 -> 7. The oracle's
verdicts do not move: each seed needs only one of the two expected
directions with an effect above 0.10, and the medians stay near 1. The
predictor was observed after the actions it counted, so method 2 is the
measurement; at these effect sizes the same-turn actions did not decide
it.

## 4. `--parallel N` is N workers

`run_batch` sized the pool `args.parallel if isinstance(args.parallel, int)
and args.parallel > 1 else max(1, cpu_count() - 1)`, so `--parallel 1`
(argparse `type=int, nargs="?", const=-1`) got the automatic size, as did a
Batch Lab worker count of 1 and the gate runner's `--parallel 1` (it passes
its count through). `batch.parallel_workers`: an explicit count N >= 1 is N
workers; a bare `--parallel` (const -1) or Batch Lab's `parallel: true`
without a worker count is `cpu_count - 1`, at least 1; None and 0 stay
sequential, as before. Each seed runs deterministically in one worker, so
results do not depend on the count ([Identity](#identity)). The CLI and gate
runner help texts say so.

## 5. pytest-xdist and subTest parameters

pytest-xdist sends every subtest report to the controller through
`execnet`, which serializes the subTest's keyword parameters
(`dataclasses.asdict` turns dataclasses into dicts, but leaves other
objects). Nine tests in five suites passed `object()`, `Path`, iterators,
`mock.patch` objects or a `str` subclass. They now pass the value's `repr`,
the path's name or the patched attribute's name; every assertion is
unchanged. Under `-n 2` the eleven subTest suites give 238 passed and 526
subtests (`dae4ba5`: 9 failed, 229 passed, 460 subtests); the five files
pass in one process (146).

## Identity

No-Rust venv (Python 3.13.17, `uv sync --frozen`), `PYTHONHASHSEED=0`,
`dae4ba5`'s exported `src` on `PYTHONPATH` against this branch.

* `scripts/turn_speed_identity.py` cases `off_s42`, `off_s7`,
  `proc48_off_s7`: 33 files, 0 differences (bundles decoded without
  `generated_at` and raw with it blanked).
* Batch `--seed-range 42-45 --turns 150 --agents off --simulate-only`:
  `dae4ba5` with `--parallel 1` (3 workers), this branch with `--parallel 1`
  (1 worker) and this branch sequential: 38 files each, only
  `batch_manifest.json` differs (timestamps, source identity, the raw
  bundle hashes that include `generated_at`, and `parallel_requested`).

* With the release extension `735558c9...a489` (built fresh from this
  tree; no Rust change on this branch) used by both sides, cases
  `hybrid_s42`, `hybrid_s7`, `proc48_hybrid_s42`: 311 files, 0
  differences.
* Narration: the re-narrated bundle above changes only its prompts' and
  mechanical entries' account passages; gap summaries and metadata are
  identical.

344 files compared, 0 differences. Golden fixtures are unchanged.

## Tests

Linux, Python 3.13.17, the no-Rust venv (`uv sync --frozen`, plus
pytest-xdist), `PYTHONHASHSEED=0`; Node 22.22.0.

* Focused: `python -m pytest -q tests/test_historical_parity.py
  tests/test_validate.py tests/test_validation_compare.py
  tests/test_validation_gate.py tests/test_batch.py
  tests/test_batch_manifest.py tests/test_batch_websocket.py
  tests/test_m53b_run_validation.py`: 329 passed. New: `TestAccountsAsOf`
  (5), the cohort window, eligibility, version and same-turn tests (11
  cases, and the sampled-turns test for both methods), the comparator's
  cohort re-baselining, `TestParallelWorkers` (8), the Batch Lab worker
  count (3) and the gate runner's count (3).
* Narration, history, live, bundle and viewer-adjacent: `python -m pytest
  -q -n 2 -m "not slow"` over `test_historiography`, `test_languages`,
  `test_narrative`, `test_narration_context`, `test_curator`,
  `test_batch_narration`, `test_chronicle`, `test_scholarship`,
  `test_causal_provenance`, `test_historical_parity`,
  `test_historical_parity_processes`, `test_live`, `test_live_integration`,
  `test_bundle`, `test_bundle_codec`, `test_viewer_snapshot_fields`,
  `test_main`: 445 passed, 7 skipped.
* `python scripts/run_python_oracle_checks.py`: PASS in 104.6 s, 2,537
  passed, 38 skipped (narration chunk 144, validation-tooling 105).
* `python -m pytest -q -n 2 -m "not slow"`: 6,265 passed, 232 skipped, 526
  subtests, 0 failed (no native extension: native suites skip).
* Viewer: `npm ci`, `npm test -- --maxWorkers=2` 382 passed in 46 files
  (`dae4ba5`: 363 in 45), `npm run lint`, `npm run build` pass. The 21 new
  or changed viewer tests fail against `dae4ba5`'s viewer source.

## Not run, open

* Not run: a full template or procedural gate with cohort method 2 (the
  procedural subset either); `pytest -m slow`; `cargo test` (no Rust
  change); native Python suites (the full run above had no extension); no
  LLM narration; no browser QA.
* The retained cohort evidence is thin: one 20-seed set from older code,
  nine single runs and the live subset. Comparisons against reports scored
  with cohort method 1 are flagged for re-baselining; re-score the baseline
  batch with `run_cohort_oracle(..., method_version=2)` (or
  `scripts/rescore_cohort_oracle.py`) to compare.
* The curator's contested bonus reads the final losses (moment selection
  only).
* Viewer: map node size (final carrying capacity); a language revived after
  an earlier extinction.
* `docs/CONTINUATION.md` still lists the overview snapshot selector's
  first-row fallback and the final-state overview fields as product gaps;
  both are fixed here.
