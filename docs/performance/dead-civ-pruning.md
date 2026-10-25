# Dead civilizations leave the history snapshots (bundle version 5)

Bundle version 6 ([bundle-v6.md](bundle-v6.md)) writes this pruned history
as changes between snapshots; decoded, it is the version-5 history below.

Branch `perf/prune-dead-civ-snapshots`, based on `integrate/wave-5` at
`7fbe8c0`. This changes the viewer bundle format only. The simulation, its RNG
draws, `state.json`, `chronicle.md`, the memories, `agent_events.arrow`, the
validation sidecars and the snapshots handed to `on_turn` callbacks are
unchanged. No Rust code changed.

## Problem

Civilization records are never removed, and secessions keep adding them. Every
version-4 `history[n]` snapshot carried every civilization that ever existed:
its `civ_stats` row, its `capitals` entry, and every pair it belongs to in
`relationships`, `per_pair_accuracy` and `perception_errors`. The pair tables
grow with the square of all civilizations ever founded.

`tests/test_bundle.py::TestBundleSize` (seed 1, 500 turns, 10 regions, 5 civs,
agents off, the default epidemiology, finance and diplomacy) founds 20 polities.
About 5.6 are alive in any turn. Its bundle was 37.45 MiB. Rows for civs dead
at that turn were 17.2 MiB of the 25.0 MiB those four fields took.

## What is pruned

A snapshot records a civilization when, in that snapshot:

- it holds a region (its row's `regions` is not empty), or
- an exile modifier names it (`original_civ_name`). A government in exile can
  be restored to its old land (`politics.check_restoration`, and the native
  restoration step, which also start from the exile modifiers), or
- it was live in the previous snapshot. So the snapshot in which a civilization
  dies, or in which its exile lapses, keeps its final row (`alive: false`), and
  charts can end its line there, or
- the snapshot is the first one in the history. That snapshot records every
  civilization.

Any other civilization is dead at that turn. Its `civ_stats` row, its `capitals`
entry and both directions of its pairs are left out of the snapshot. Rows are
matched by name, as the snapshot keys are. A civilization that is live again
(restored, or a later record that reuses the name) is recorded again from that
snapshot. In the simulation a pruned name does not come back: secession skips
every existing name, dead ones included, and restoration needs an exile
modifier, which keeps its civ recorded.

The rule is applied to the serialized history: in `bundle.assemble_bundle`, and
to the live-mode turn stream (`live.run_live`). The in-memory history is not
changed, so in-run curation and narration read exactly what they read before.
The code is in `src/chronicler/snapshot_pruning.py`.

Other snapshot fields that mention dead civilizations were checked on the
size-guard world (snapshots that mention one, of 500). They are not per-civ
rows, so they are kept:

| Field | Snapshots | Kept because |
| --- | --- | --- |
| `capitals` | 399 | pruned like `civ_stats` (keyed by civ) |
| `movements_summary` | 375 | `origin_civ` attributes a movement that still exists |
| `vassal_relations`, `federations`, `diplomacy.subjects` | 266 | the world still holds these records |
| `region_cultural_identity` | 108 | keyed by region |
| `proxy_wars`, `campaign.battles` | 5 | world records and battle history |

`finance.civs`, `diplomacy.pairs`, `contact` and `epidemics` already carry
living civilizations only. Procedural worlds already wrote the pair tables for
living civilizations only. For those worlds, only `civ_stats` and `capitals`
shrink.

## Restoring the omitted rows

When pruning landed, the omitted rows were not all copies of the final row:
`phase_production` paid every civilization record `economy // 5`, so a dead
civilization's treasury kept growing (on the subset gate batch, `treasury`
changed in 1,806 omitted rows and `federation_name` in 2). A follow-up
correction stops paying civilizations without regions; omitted rows are now
normally unchanged, and `pruned_civ_stats` still records any field that does
change.

The bundle's new top-level `pruned_civ_stats` records, for each civilization, its
omitted segments as change runs relative to its final row:

```json
{"Thornwall Confederacy": [{"from_turn": 44, "snapshots": 457,
                            "changes": {"treasury": [[457, 414, 20]]}}]}
```

The runs are `[count, first, step]`: integers in arithmetic progression, or a
constant when `step` is null. For the size-guard world this is 1,320 bytes.
`snapshot_pruning.restore_history` and `restore_bundle` rebuild the version-4
`civ_stats` exactly: values, number types and key order. A row whose set of
fields changes inside a segment is kept rather than encoded. The pair tables of
dead civilizations are not kept anywhere.

## Consumers

| Reader | Change |
| --- | --- |
| Validation (`validation_io._load_bundle`, all oracles) | restores `civ_stats` before building oracle inputs |
| `analytics.load_bundle_records` (batch reports, Batch Lab, `governance_metrics`) | restores |
| `main._run_narrate`, live `narrate_range` | restore, so re-narration reads the history the run held |
| `live._validate_legacy_live_bundle`, `_build_init_data_from_bundle` | pass `pruned_civ_stats` through |
| `scripts/epidemiology_stats.py`, `m_af1_compare.py`, `run_oracle_gate.py` | restore (they sum or compare over every civ) |
| `curator`, `narrative`, `finance_census.py`, `techniques_report.py`, `diplomacy_report.py`, `governance_metrics` | already skip missing or dead civs; tested on pruned and restored histories |
| `scripts/build_viewer_systems_fixture.py` | also keeps each snapshot that holds a dead civ's final row |
| `scripts/third_wave_controls.legacy_artifact_bytes` | accepts version 5; `pre_pruning=True` projects a bundle with nothing pruned back to version 3 |

Viewer (`viewer/src/lib/civRows.ts`):

- The civ inspector (`AppShell`) shows a civ's latest row at or before the
  scrubbed turn. It used to fall back to the end-of-run world state when a row
  was missing. It also gains a Status line: Active, Fallen, "Fallen (final
  record, turn N)" or "Not yet founded".
- `StatGraphs` and the `FactionDashboard` sparklines end a line where a civ's
  rows end. They used to draw 0, which dropped the line to zero. A civ that is
  not founded yet also has no line before its first row. The dashboard reads a
  dead civ's final row, so it shows "Absorbed" after the death; before this
  change a missing row read as alive.
- Era strips, the systems panels and live-mode turn accumulation already handle
  gaps. Tests cover all of these on pruned histories.

Bundles of version 4 and older load unchanged. A civilization present in every
snapshot reads the same through these helpers.

## Evidence

All runs were on Linux with Python 3.13.17, using the native extension built
from this tree (`maturin develop --release`). The gate, the size runs and the
fixture captures used `PYTHONHASHSEED=0`. The size-guard world ran as its test
does, without it. Base outputs came from an exported copy of `7fbe8c0`, and
branch gate outputs from an exported copy of the branch tree.

**Validation identity.** Subset gate: 20 seeds (42-61) x 200 turns, hybrid,
`--parallel 2`, new defaults.

- Base: gate PASS. Regression FAIL and determinism SKIP are informational, as
  on the base before this branch.
- Base bundles converted with `scripts/prune_dead_civ_snapshots.py convert` and
  re-validated: `validate_report_subset.json` is identical to the base report
  once the batch path is normalized (41,113 characters).
- Gate re-run on the branch: the report is identical apart from the batch path,
  and the comparator reports NO REGRESSION. Of 2,167 files:
  - each of the 20 bundles equals the conversion of the base bundle apart from
    `generated_at`, and restores the base `civ_stats` exactly;
  - the other 2,141 files are byte-identical (all 20 `state.json`, the
    chronicles, memories, agent events and validation sidecars);
  - `run_manifest.json` differs only in paths and in the baseline-comparison
    fields.
- Without the restore, the base validation code on the converted bundles
  changes 86 era values and 21 arc values. No oracle status changes. Era and
  arcs read dead civilizations' series through to the end of the run; with the
  restore they read the same series as before.

**State identity.** On the size-guard world, `state.json`, `chronicle.md` and
every memories file are byte-identical to the base, and the bundle equals the
conversion of the base bundle. The same holds for the golden workloads and for
the hybrid and procedural runs below (they write no `state.json`; their
chronicles, memories and agent events are identical).

**Sizes** (`chronicle_bundle.json`):

| World | Before | After | Civ rows per snapshot |
| --- | --- | --- | --- |
| Size guard: seed 1, 500 turns, 10 regions, 5 civs, agents off | 39,267,830 (37.45 MiB) | 21,274,336 (20.29 MiB), -45.8% | 13.21 -> 5.78 (5.57 alive) |
| Hybrid: seed 42, 500 turns, defaults | 13,114,796 (12.51 MiB) | 11,495,945 (10.96 MiB), -12.3% | 4.22 -> 3.04 (2.98 alive) |
| Procedural 48 x 10: seed 7, 500 turns, hybrid | 46,969,003 (44.79 MiB) | 45,518,987 (43.41 MiB), -3.1% | 10.35 -> 8.82 (8.79 alive) |
| Subset gate batch, 20 bundles | 118,767,131 | 111,360,469, -6.2% | |

The size guard is tightened from 40 to 21 MB. The 48 x 10 world founds only 11
polities and its pair tables were already living-only. Its largest snapshot
fields are now `civ_stats` (9.1 MiB), `diplomacy` (3.7), `perception_errors`
(2.1) and `ecology` (2.0).

**Fixtures.**

- `tests/fixtures/performance/corrected_artifacts_dead_civ_pruning_2026_10.json`
  rolls the artifact oracle forward as a format change. Only
  `chronicle_bundle.json` changes, in each of the single, standard and wide
  workloads: +22 bytes, from bundle version 5 and an empty `pruned_civ_stats`.
  No golden workload has a dead civilization. Each changed expectation is
  listed with its old and new hash. The turn oracle
  (`corrected_food_balance_2026_10.json`) and every other file, including
  `state.json`, are unchanged. The pre-pruning projection still reproduces the
  frozen `corrected_artifacts_food_balance_2026_10.json`.
- `viewer/src/__fixtures__/systems_bundle.json` was regenerated from the same
  documented run (procedural 48 x 10, seed 42, hybrid, 120 turns, all five
  systems). Restoring and trimming the new source bundle the old way
  reproduces the old fixture exactly, apart from `generated_at` and the
  version. It now also keeps turns 4, 19 and 20, which hold the final rows of
  Khorain Kingdom, Empire of Budun and Hiholdi Kingdom.

**Tests.**

| Lane | Base `7fbe8c0` | Branch |
| --- | --- | --- |
| `pytest -m "not slow" -n 2` (native build) | 5,759 passed, 3 skipped | 5,791 passed, 3 skipped |
| `pytest -m slow -n 2` | - | 11 passed, 3 skipped (the size guard at < 21 MB included) |
| No-Rust environment, `pytest -n 2`, no marker filter | 5,561 passed, 201 skipped (ledger) | 5,593 passed, 201 skipped |
| `scripts/run_python_oracle_checks.py` (PR #19 guard fix applied locally, not committed) | 1,771 passed, 8 skipped, 2 deselected | 1,803 passed, 8 skipped, 2 deselected; guard PASS, no native module loaded, no blocked I/O |
| Viewer `npm test` | 199 tests, 25 files | 210 tests, 27 files |
| Viewer `npm run lint`, `npm run build` | pass | pass (existing large-chunk warning) |

The 32 new Python cases are `tests/test_snapshot_pruning.py` (31, added to the
oracle lane) and the dormancy test that the roll-forward changes only the files
it declares.

**Browser.** Headless Chromium checked the production build with the version-5
size-guard bundle. Thornwall Confederacy's last row is at turn 43. At turns 38,
43, 44, 250 and 500 the inspector shows its recorded row, then its final row
with "Fallen (final record, turn 43)". The treasury shown is 394; the end-of-run
world state says 9,534. With the systems fixture, the Techniques era strip ends
Khorain Kingdom at its last row. A temporary, uncommitted harness rendered
`StatGraphs` and `FactionDashboard` with the same bundle: each of the 20 lines
starts and ends at its first and last row, as one unbroken path with no zero
drop. There were no console errors or warnings.

## Not done

- The full 200-seed x 500-turn gate was not run. The subset gate, the size
  worlds and the golden workloads show the simulation is unchanged.
- In-memory snapshots still compute the pair tables of dead civilizations,
  which costs CPU. Restricting that computation would change the `on_turn`
  snapshots and the turn oracle, so it is left for a separate change.
- Dead civilizations used to keep collecting income, and that treasury drift
  added inflection points to the era oracle (seed 42's 32 inflection turns
  fall to 7 without dead tails). The follow-up correction stops the income; on
  the subset gate it changes only dead civilizations' treasury and
  `last_income` (10 of 20 `state.json`), every oracle status and regression
  metric is unchanged, and one of 237 era collapses moves from "crisis only"
  to "own signal".
