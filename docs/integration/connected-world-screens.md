# Connected-world screens: runner, seed registry, harm panel and matrix

Program tooling for the [connected-world program](../superpowers/roadmaps/connected-world-program.md)
(lane E1, 2026-11-06). Nothing here changes the simulation: `src/chronicler` simulation paths
and `chronicler-agents/` are untouched; `feature_catalog.py` gained two unused extensions
whose served output is byte-identical (section 5).

| File | What it is |
| --- | --- |
| `scripts/seed_registry.json` | Every recorded use of a seed number, per stratum, and the program's reservations |
| `scripts/screen_runner.py` | The generic run/report/check/`--resume` runner, parametrized by a `Screen` |
| `scripts/connected_world_screens.py` | CW1-CW6 (stubs: cohorts only, except CW4, declared by slice C1: [quarantine rules](quarantine-rules.md), preregistration `docs/superpowers/progress/connected-world-screens-cw4.md`, CW1, declared by slice S1: the wage and `paid_work` enrollment, a two-phase screen, preregistration `docs/superpowers/progress/connected-world-screens-cw1.md`, and CW3, declared by slice B2: the [watershed](watershed.md) in flow mode under upstream forest protection, procedural stratum only, preregistration `docs/superpowers/progress/connected-world-screens-cw3.md`) and the development-only `DEV` smoke screen |
| `scripts/feature_matrix.py` | The switch compatibility matrix, generated from `feature_catalog` |
| `viewer/src/lib/recordReading.ts` | The RL8 fix: absent, malformed, disabled and recorded-zero records told apart |
| `tests/test_screen_runner.py`, `tests/test_feature_matrix.py` | Offline tests (oracle chunk `connected-world-e`, native shard 0) |

## 1. The seed registry

`scripts/seed_registry.json` holds audit E section 5.3's historical cohorts, a few more found
by a repository search (M-AF1 template 1-200, the M53 probes' default starts, M58b 1-5, and
the brainstorm's illustrative seeds 213 and 847, status `never_run`), and the program's
reservations. Each entry has `id`, `source` (evidence), `use`, `stratum` (`template` or
`procedural`), `world` (shape), `seeds` (ints and inclusive `[low, high]` ranges), `turns` and
`status`; a reservation also has `program`, `cohort` (`held`, `pilot` or `reserve`) and
`screen`. Statuses:

| Status | Meaning |
| --- | --- |
| `run` | the cohort ran; never used again for a pilot or held cohort |
| `never_run` | named with no recorded run (or withdrawn); still excluded |
| `reserved` | assigned to a pending cohort of this program; only that cohort may use it |
| `restricted_gate` | the restricted 200-seed (template 42-241) or procedural (42-141) gate |
| `development` | inspected freely by the lanes; never held |

A seed collides with every entry of its stratum whatever the world size (conservative).
`unresolved` names two old runs whose start seed is not recorded (the removed
`m58b_convergence_gate.py` and `p4_validate.py`, 200 seeds each).

Program reservations (all `reserved`):

| Cohort | Template 8x4 | Procedural 32x10 |
| --- | --- | --- |
| Timing pilot, shared by every screen, never held | 5 | 19 |
| CW1: S1 accounting and wages (A1-A2) | 731-736 | 831-836 |
| CW2: S2 workshop economics, owned-stock lifecycle (A3, A5) | 741-746 | 841-846 |
| CW3: S3 watershed and infrastructure (B1-B3); declared by B2 on the procedural cohort only (the watershed refuses template worlds: 751-756 stay reserved, unused) | 751-756 | 851-856 |
| CW4: S3 quarantine and public health (C1) | 761-766 | 861-866 |
| CW5: S4 trade, forest-water, care, attribution, requisition | 771-776 | 871-876 |
| CW6: S5 adaptive decisions, cross-border organisation, war; integrated evaluation | 781-786 | 881-886 |
| Reserve (a held-run failure fix needs a new cohort; the lead assigns it) | 791-796 | 891-896 |

Before the registry was written, a scan of every tracked and untracked file (not `.venv` or
`node_modules`) for 731-799 or 831-899 used as a seed (a seed key or flag's value, a member of a
seed list or range, `range(...)` on a seed line) found only the brainstorm's illustrative
"Seed 847" and its hypothetical `--seed-range 1-1000` for a `--discover` command that does not
exist; the same scan finds the productive-recovery cohorts 701-726/801-826 everywhere they
are used. Template 5, the shared pilot, was also in the M-AF1 and M58b development batches:
`check` prints that as a note (a timing pilot is never held), not a refusal.

`python scripts/connected_world_screens.py registry` validates the registry and prints the
used, never-run-again, development and reserved sets per stratum.

**Recording a held run.** Where the record lives, plainly:

- At its start, a held (or reserve) run writes its record to `OUT/held-run.json` in its own
  output folder and appends it to the ledger of the clone it runs in,
  `output/held-runs/ledger.jsonl` (git ignores `output/`; every clone and worktree has its own).
  While that clone's ledger records the run, a new run of the cohort there is refused; resume the
  recorded run with `--resume`.
- Nothing outside that clone sees the run until `mark-run OUT --screen CWn` sets the cohort's
  registry entries to `run` with a `held_run` record (output folder, identity digest, start, rows,
  whether complete, reason) **and that registry change is committed and merged**. Run `mark-run`
  as soon as the run is finished or abandoned and commit it promptly, with the results; until
  then another clone could start the cohort again.
- A recovered or reclaimed container has an empty ledger. To resume there, restore the output
  folder (with its `held-run.json`, `source.txt` and `metrics.jsonl`) on the same source; the
  runner accepts the folder's own record when it names this run and writes it back to the
  ledger. Without the folder the run cannot be resumed; record what exists with `mark-run`.
- After `mark-run`, `check --screen CWn --metrics OUT/metrics.jsonl --cohort held` reports the
  cohort as recorded (a note) and checks the metrics; only starting a held run of a recorded
  cohort is refused.

**The reserve.** When a screen's held run failed or is incomplete, the lead records it first
(`mark-run`, which stores `complete: false`) and then runs the same screen on the reserve:
`run OUT --screen CWn --cohort reserve --reason "<why>" --pilot PILOT/metrics.jsonl`. It is
refused before that record exists and after a complete one. It needs what a held run needs
(frozen preregistration, ceiling, pilot); the reason goes into `source.txt`, `held-run.json`
and, through `mark-run`, the registry, which also names the screen on the reserve entries. The
reserve serves one screen once in the whole program.

**The shared pilot** reservation (template 5, procedural 19) stays `reserved` after use: a
timing pilot is never evidence, and every screen's pilot uses it. Never mark it `run`.

## 2. The runner

```sh
PY=<native interpreter matching the source>          # every program arm is hybrid
$PY scripts/connected_world_screens.py check --screen CW1|all
$PY scripts/connected_world_screens.py run OUT --screen CW1 --cohort pilot --jobs 2
$PY scripts/connected_world_screens.py report OUT/metrics.jsonl --screen CW1      # projected held core-hours
# the lead freezes the preregistration; then
$PY scripts/connected_world_screens.py run HELD --screen CW1 --cohort held --pilot OUT/metrics.jsonl --jobs 3
$PY scripts/connected_world_screens.py report HELD/metrics.jsonl --screen CW1 > HELD/report.md
$PY scripts/connected_world_screens.py check --screen CW1 --metrics HELD/metrics.jsonl --cohort held
$PY scripts/connected_world_screens.py mark-run HELD --screen CW1      # then commit scripts/seed_registry.json
# development worlds only (never evidence), e.g. to validate an extractor:
$PY scripts/connected_world_screens.py run DEV_OUT --screen CW1 --cohort dev --worlds t23,p31 --turns 20
```

The skeleton is lifted from `scripts/productive_recovery_screens.py` and
`scripts/livelihoods_screens.py` (`_run_env`, `source_identity`), which stay frozen as evidence
of their preregistrations; the runner imports neither and is not tied to
`LIVELIHOODS_SWITCHES`. What it enforces:

- **Seeds** (`check_seeds`, before every run and in `check`): a held cohort equals its own
  registry reservation and appears in no other entry, no gate range, not in 1000-1999, in no
  development world, is not listed twice and was not run. A pilot seed is registered as the
  shared pilot and shares its number only with other timing pilots (never a held or reserve
  cohort, a gate, the holdout range or a development world). `--cohort dev` takes only
  registered development worlds; `--turns` is allowed only there.
- **Readiness**: a stub (`ready=False`) refuses every run; `check` exits 2 for it. A ready
  screen needs arms forming a tree rooted at its root, every command line parsing with the
  real parser and accepted by the feature catalog (in each stratum its cohorts use, both when it
  declares none; the catalog's `procedural_world` setting is the world the command line resolves
  to, which the live surface cannot see), an activation rule, declared counters for
  every package counter it reads, and 2-3 primary outcomes whose controls lie on the arm's
  control chain.
- **Preregistration** (held and reserve runs): a `Status:` line reading FROZEN (not DRAFT),
  exactly one `Compute ceiling: X core-hours` line and one `Primary outcomes: id1, id2[, id3]`
  line naming exactly the screen's primaries.
- **Pilot** (held and reserve runs): `--pilot` gives the pilot's `metrics.jsonl`; its sibling
  `source.txt` must show the same extension, runner, screen module, registry content (the
  cohorts and seeds, without status and run records, so a `mark-run` keeps a pilot valid) and
  count of modified code files, its rows that identity, and its source revision may differ
  from this run's only outside the code (`src/`, `chronicler-agents/`, `scripts/` except the
  registry, `pyproject.toml`, `uv.lock`), as the freeze commit and a committed `mark-run` do.
- **Reuse**: only a held run is refused on a held cohort marked `run`; a reserve run and `check`
  accept one `mark-run` recorded; pilot and development runs never touch the held cohort and
  are not refused by it.
- **Compute ceiling** (held and reserve runs): the run is refused when the projection (mean
  pilot seconds per arm and stratum times the cohort's worlds) times 1.5 exceeds the ceiling.
  During the run a run starts only while the seconds used, the expected seconds of the runs in
  flight and its own expected seconds fit under the ceiling; a run's expected seconds are the
  larger of the pilot mean for its arm and stratum and the finished runs' mean for its stratum.
  The runs not started are listed in `source.txt` with the estimate that stopped them,
  reported as `not run`, and the exit code is 4. Residual risk: the first `--jobs` runs start
  on the pilot estimate alone, so runs far slower than the pilot can pass the ceiling by up to
  that first batch.
- **Packages**: in every snapshot that carries it, an enabled package's record is an object,
  dated (`source_turn` = turn - 1), in its mode, with declared, numeric counters; a package the
  arm does not enable records nothing.
- **Failures**: a missing or malformed outcome or harm makes the run rc 3 with the reasons;
  nothing missing reads as zero. A failed run's output folder is kept for diagnosis. Exit
  codes: 1 a simulation failed, 3 a missing outcome, 4 stopped at the ceiling.
- **Two-phase screens** (`Screen.derived`, S1 for CW1): an arm may need a file made from
  another arm's run on the same world. A `SR.Derived(name, source, placeholder, make)` names
  the source arm and the token the using arms' flags carry; `make(bundle, flags)` returns the
  file's bytes and a record of what it holds. The runner runs the source first, writes the
  file read-only to `OUT/derived/<name>-<world>.json`, and records its SHA-256 in the source's
  row (`derived`), `OUT/derived.jsonl`, `source.txt` (`derived <name> <world> (from arm X):
  sha256 ...`) and, for a held or reserve run, the ledger (entries with a `derived` key, which
  the conflict check skips), all before any user of the file starts. A user's command carries
  the file's path in place of the token; its row records the file and SHA-256 it ran on
  (`inputs`), and the runner hashes the file again before the run (a changed file fails the
  run, not run). A source that fails, or whose `make` refuses, fails its users on that world
  (rc 1, `not run: derived ... unavailable`). `--arms` with a user but not its source is
  refused unless `--resume` finds the file already recorded; a resumed run reads the recorded
  digests from the source rows. `check` requires distinct names and tokens, a source that is an
  arm and uses no derived file, and each token exactly once in each using arm.
- **Interactions and control activation**: `SR.Outcome(..., minus=(arm2, control2))` reads
  `(arm - control) - (arm2 - control2)` on each world (all four runs needed, both arms
  activated). `Screen.control_activation=True` also requires a non-root control to have acted,
  in the outcomes and the harm panel. `Screen.report(rows, strata)` adds the screen's own tables
  after the activation table (CW1: enrollment, wages and schedule replays per world).

**Identity.** `source.txt` starts with `source <rev>`, `dirty <n> tracked files`,
`dirty-code <n>` (modified tracked code files, the registry excluded), the imported
`chronicler`, the native extension path and SHA-256, the interpreter, and the SHA-256 of the
runner, of the screen module, of the registry file (provenance) and of the registry's cohorts
and seeds (`registry-content`), and for a held or reserve run of the preregistration; then one header per run or resume and, for those runs, the reason, the pilot
file's SHA-256, its projection, the ceiling and the expected seconds per arm and stratum. The
extractors live in the screen module, so its SHA-256 identifies them; a helper kept in another
file is neither hashed nor counted as dirty when untracked. Every
row carries the SHA-256 of those identity lines and the schema versions it read (bundle,
livelihoods container, each package record, each dated snapshot record). `--resume` runs only
the missing arm-world pairs, refuses any change of those lines (except the registry file's
full hash: another screen's `mark-run`), screen or cohort, and keeps the run's identity.

**Report.** Runs and failures, `INCOMPLETE ... not run` for every missing arm-world pair, the
identity digests and schema versions, then **activation per world before any effect**
(`activated`, `not activated`, `unknown`, `failed`, `not run`), then primary and secondary
outcomes world by world, then the harm panel beside every arm against its declared control
(and any other comparison an outcome declares), then run time per arm. A world where the arm
did not act is shown as `not activated`, never as a zero, and is left out of the summaries.
Uncertainty is descriptive only: per stratum mean, min/max, sign counts and, for an outcome
with a control, an exact enumeration of the paired sign flips (all 2^n sign assignments of the
per-world differences; with 6 worlds, 64), summarized by how many give a mean at least as far
from zero as the observed one and the range of those means. It is not a significance test; an
outcome of one arm alone shows `n/a (no control)`.

## 3. The fixed harm panel

`HARM_PANEL` in `screen_runner.py` is data shared by every screen, in this order. "Not
recorded" means the system that records it is off in the run; it is never read as zero.

| Key | Harm | Source in the bundle | When absent |
| --- | --- | --- | --- |
| `population` | population at the end, summed over civilizations | `history[-1].civ_stats[*].population` | malformed |
| `treasury` | treasury at the end, summed | `history[-1].civ_stats[*].treasury` | malformed |
| `food_shortfall` | food shortfall after relief over the run: demand x max(0, 1 - min(1, sufficiency after relief)) per region and turn | `history[*].food_accounting.regions[*]` | not recorded (no record, or a turn without an economy tick, transport `none`: unknown, not zero); malformed when the economy ticked without a native ledger |
| `priced_out_persons` | priced-out person-turns | `livelihoods.household_retail.regions[*].provisioning`, checked against the `priced_out_persons` counter | not recorded (retail off) |
| `priced_out_children` | priced-out child-turns | the same frames | not recorded (retail off) |
| `deaths_famine` | deaths by the famine authority | none: deaths are not recorded by cause | **requires slice extractor** (the slice that records deaths by authority) |
| `deaths_epidemic` | deaths by the epidemic authority | `history[*].epidemics.deaths_total` (last) | not recorded (epidemiology off) |
| `deaths_war` | deaths by the casualty authority | none outside the campaign layer | **requires slice extractor** (D3) |
| `out_migration` | agents moving between regions over the run | `history[*].migration` rows `[from, to, agents]` | not recorded (no agent pool) |
| `wealth_gini` | mean wealth Gini of living civilizations at the end | `history[-1].civ_stats[*].gini` | not recorded (no agent pool, where civ_stats holds a placeholder 0, or no living civilization) |
| `forest_stand` | standing timber over capacity at the end (a stock, not cover) | the last snapshot's `livelihoods.timber_stock.totals` | not recorded (timber stock off, no record at the end, or the last turn unobserved) |

A slice that adds the missing record supplies the extractor for its harm (a function from a
bundle to `{state, value, note}`) in `HARM_PANEL`; it does not drop or reorder harms.

## 4. How a slice adds its screen

1. In `scripts/connected_world_screens.py`, replace its stub with a `SR.Screen`: `base` (the
   flags every arm shares, with `--turns`), `arms` (`{arm: (flags, control)}`, one root),
   `packages` (`SR.Package(flag, snapshot path, counters_module, counters, mode_flag,
   default_mode)`), `outcomes` (`SR.Outcome(id, label, arm, control, read, primary)`, 2-3
   primary; `read(row)` reads `row["m"]`, `row["pk"]` or `SR.harm_value(row, key)`),
   `activation(bundle, flags) -> (True/False/None, evidence)`, `extract(bundle, flags) ->
   (measures, problems)` and `ready=True`. Keep the declared `pilot` and `held` cohorts. A
   screen whose arms replay another arm's recorded behaviour declares `derived` (CW1 is the
   example: arms C and D replay A's and B's pilot schedules).
2. Write `docs/superpowers/progress/connected-world-screens-cwN.md` with `Status: DRAFT`, the
   `Compute ceiling:` and `Primary outcomes:` lines, definitions, structural zeros versus
   unknowns and stopping rules (the productive-recovery checkpoint-3 preregistration is the
   model).
3. Add tests with constructed bundles for the extractor and activation; validate on development
   worlds with `--cohort dev`; run `check --screen CWn`.
4. Run the pilot, report the projection, have the lead freeze the preregistration, run the held
   cohort with `--pilot`, then `report`, `check --metrics` and `mark-run`. Retain
   `metrics.jsonl`, `report.md`, `source.txt` and `held-run.json` under
   `docs/superpowers/progress/connected-world-screens-cwN/` and commit the registry `mark-run`
   changed in the same commit.

## 5. The compatibility matrix

`PYTHONPATH=src python scripts/feature_matrix.py [--json OUT] [--markdown OUT]` (adapted from
audit E's prototype) evaluates the catalog per agent mode and per world: a template world and a
procedural one, which differ in the world-dependent settings (`WORLD_SETTINGS`: today
`procedural_world`, which `--watershed` requires; the other settings take their defaults). It
lists each switch's minimal selection, agent modes and worlds; every pair as valid, refused
with the catalog's reason, or *world-dependent* (valid in the worlds both switches allow,
refused in another: reported, not a problem; a refusal is expected only for an exclusive pair
or a pair with no common agent mode or world); every prerequisite drop, in a mode and world
the switch allows (each must be refused); and the all-enabled selection per agent mode and
world. It exits 1 on an accepted drop, an unexpected refusal, a refused all-enabled selection
or a one-sided exclusion. With B1 merged (2026-11-06): 25 switches, 300 pairs, none refused,
24 world-dependent (`--watershed` with each other switch: refused in a template world), 24
drops all refused, all-enabled accepted in every mode and world (template: off 2, demographics-
only and shadow 7, hybrid 24; procedural: one more each, `--watershed`; procedural hybrid: all
25). `tests/test_feature_matrix.py` also sends every all-enabled selection, on a template world
and on procedural development world 11, and every drop through `main._configure_run`.

`feature_catalog.py` can now represent the program's later switches: `FEATURE_GROUPS` (groups
after livelihoods for switches that are not livelihoods packages) and a `{"not": condition}`
requirement (`_excludes(other)`, declared by both switches of a mutually exclusive pair;
`exclusion_problems()` names a one-sided one). The viewer reads the `not` kind. Both are
unused (B1's `--watershed` is a livelihoods switch, in the Livelihoods group), so the served
catalog of every switch and setting 8abc1acb had (entries, requirements, settings and surface
fields, in order) is byte-identical to 8abc1acb's, which
`test_existing_catalog_output_is_byte_identical` checks against digests taken from the
unchanged module; it leaves out switches and settings added later (B1's `watershed` and
`procedural_world`), and `CATALOG_SCHEMA_VERSION` stays 1. See [feature options](feature-options.md).

## 6. Recorded limit RL8: absent versus malformed viewer records

Class: defect (viewer). `repairProjectsAt`, `timberStockAt`, `remittancesAt`,
`foodAllocationAt` and `granaryStorageAt` return null for an absent and a malformed record
alike. `viewer/src/lib/recordReading.ts` puts the presence test in front of each unchanged
reader and returns `disabled` (no snapshot of the run records the package), `absent` (on in
the run but not at this snapshot, or no livelihoods record: unknown, not zero), `malformed`
(the record or the livelihoods container was refused), `unobserved` (null frames: unknown, not
zero), `recorded_zero` or `recorded`, each with a note. The repair projects, timber stock,
remittances, food allocation and granary storage panels show the note and say "recorded,
nothing happened this turn" for a recorded zero; the livelihoods panel mounts its four
whenever the run records their package, so an absent record is reported instead of hidden.
L2 leaves out the regions household retail provisioned, so when retail provisioned a region
that turn (not in record-only mode) an empty food-allocation frame reads "no region outside household retail's regions was short
of food", never "no region was short of food". Tests: every state for the five readers (`recordReading.test.ts`) and the five panels
(`RecordStates.test.tsx`).

The granary storage panel `GranaryStorage.tsx` is pinned whole by the crisis-candidate source
witness (`new_files`), which projects through `before_livelihoods_sprint`; its edit (render
`readGranaryStorage` instead of `granaryStorageAt`'s null) is inverted by the reviewed
livelihoods layer `cwe1` (`tests/fixtures/livelihoods_cwe1_source_inverse.json`, appended to
`LAYERS`). `granaries.ts` and `Granaries.tsx` are unchanged.

## 7. Verification (2026-11-06, branch `claude/cw-e1-tooling`)

- `tests/test_screen_runner.py` (117) and `tests/test_feature_matrix.py` (17) pass under the
  offline guard; `tests/test_feature_catalog.py` and `tests/test_native_ci_shards.py` pass.
- A `DEV` smoke run on development world template 1 (10 turns, both arms, the reference native
  extension `101a4cd5...`) wrote identities, rows, activation and the harm panel; `report` and
  `check --metrics` passed.
- Viewer: `npx vitest run --maxWorkers=1` (148 files, 1524 passed, 2 skipped, under load 8.5), `npm run lint`,
  `npm run build` pass.
- After the independent review and its re-check (2026-11-06): M1, m1-m8, N1, N2 and n1,
  n3-n7 are fixed with tests (the reserve sequence runs with an identity that hashes the
  registry); a second `DEV` smoke run (template 1, 10 turns, 2 jobs) passed `check --metrics`.
- Not run: any pilot or held screen (every CW screen is a stub), native or Rust suites (no
  native change).
