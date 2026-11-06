# Connected-world screens: runner, seed registry, harm panel and matrix

Program tooling for the [connected-world program](../superpowers/roadmaps/connected-world-program.md)
(lane E1, 2026-11-06). Nothing here changes the simulation: `src/chronicler` simulation paths
and `chronicler-agents/` are untouched; `feature_catalog.py` gained two unused extensions
whose served output is byte-identical (section 5).

| File | What it is |
| --- | --- |
| `scripts/seed_registry.json` | Every recorded use of a seed number, per stratum, and the program's reservations |
| `scripts/screen_runner.py` | The generic run/report/check/`--resume` runner, parametrized by a `Screen` |
| `scripts/connected_world_screens.py` | CW1-CW6 (stubs: cohorts only) and the development-only `DEV` smoke screen |
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
| CW3: S3 watershed and infrastructure (B1-B3) | 751-756 | 851-856 |
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
used, never-run-again, development and reserved sets per stratum. After a held run, change its
reservation's status to `run`; a later held run of the same cohort is then refused as reuse.

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
  real parser and accepted by the feature catalog, an activation rule, declared counters for
  every package counter it reads, and 2-3 primary outcomes whose controls lie on the arm's
  control chain.
- **Preregistration** (held runs): a `Status:` line reading FROZEN (not DRAFT), exactly one
  `Compute ceiling: X core-hours` line and one `Primary outcomes: id1, id2[, id3]` line naming
  exactly the screen's primaries.
- **Compute ceiling** (held runs): `--pilot` gives the pilot's metrics; the run is refused when
  the projection (mean pilot seconds per arm and stratum times the held worlds) times 1.5
  exceeds the ceiling. During the run no new run starts once the finished runs reach the
  ceiling; the rest are listed in `source.txt`, reported as `not run`, and the exit code is 4.
- **Packages**: an enabled package records a dated record (`source_turn` = turn - 1) in its
  mode with declared, numeric counters; a package the arm does not enable records nothing.
- **Failures**: a missing or malformed outcome or harm makes the run rc 3 with the reasons;
  nothing missing reads as zero. Exit codes: 1 a simulation failed, 3 a missing outcome, 4
  stopped at the ceiling.

**Identity.** `source.txt` starts with `source <rev>`, `dirty <n> tracked files`, the imported
`chronicler`, the native extension path and SHA-256, the interpreter, and the SHA-256 of the
runner (the extractor), of the screen module and of the registry; then one header per run or
resume and, for a held run, the pilot file's SHA-256, its projection and the ceiling. Every
row carries the SHA-256 of those identity lines and the schema versions it read (bundle,
livelihoods container, each package record, each dated snapshot record). `--resume` runs only
the missing arm-world pairs and refuses any change of those lines, screen or cohort.

**Report.** Runs and failures, `INCOMPLETE ... not run` for every missing arm-world pair, the
identity digests and schema versions, then **activation per world before any effect**
(`activated`, `not activated`, `unknown`, `failed`, `not run`), then primary and secondary
outcomes world by world, then the harm panel beside every declared comparison, then run time
per arm. A world where the arm did not act is shown as `not activated`, never as a zero, and is
left out of the summaries. Uncertainty is descriptive only: per stratum mean, min/max, sign
counts and the exact paired sign-flip distribution (all 2^n sign assignments of the per-world
differences; with 6 worlds, 64): how many assignments give a mean at least as far from zero as
the observed one, and the range of those means. It is not a significance test.

## 3. The fixed harm panel

`HARM_PANEL` in `screen_runner.py` is data shared by every screen, in this order. "Not
recorded" means the system that records it is off in the run; it is never read as zero.

| Key | Harm | Source in the bundle | When absent |
| --- | --- | --- | --- |
| `population` | population at the end, summed over civilizations | `history[-1].civ_stats[*].population` | malformed |
| `treasury` | treasury at the end, summed | `history[-1].civ_stats[*].treasury` | malformed |
| `food_shortfall` | food shortfall after relief over the run: demand x max(0, 1 - min(1, sufficiency after relief)) per region and turn | `history[*].food_accounting.regions[*]` | not recorded |
| `priced_out_persons` | priced-out person-turns | `livelihoods.household_retail.regions[*].provisioning`, checked against the `priced_out_persons` counter | not recorded (retail off) |
| `priced_out_children` | priced-out child-turns | the same frames | not recorded (retail off) |
| `deaths_famine` | deaths by the famine authority | none: deaths are not recorded by cause | **requires slice extractor** (the slice that records deaths by authority) |
| `deaths_epidemic` | deaths by the epidemic authority | `history[*].epidemics.deaths_total` (last) | not recorded (epidemiology off) |
| `deaths_war` | deaths by the casualty authority | none outside the campaign layer | **requires slice extractor** (D3) |
| `out_migration` | agents moving between regions over the run | `history[*].migration` rows `[from, to, agents]` | not recorded (no agent pool) |
| `wealth_gini` | mean wealth Gini of living civilizations at the end | `history[-1].civ_stats[*].gini` | not recorded (no living civilization) |
| `forest_stand` | standing timber over capacity at the end (a stock, not cover) | `livelihoods.timber_stock.totals` | not recorded (timber stock off) |

A slice that adds the missing record supplies the extractor for its harm (a function from a
bundle to `{state, value, note}`) in `HARM_PANEL`; it does not drop or reorder harms.

## 4. How a slice adds its screen

1. In `scripts/connected_world_screens.py`, replace its stub with a `SR.Screen`: `base` (the
   flags every arm shares, with `--turns`), `arms` (`{arm: (flags, control)}`, one root),
   `packages` (`SR.Package(flag, snapshot path, counters_module, counters, mode_flag,
   default_mode)`), `outcomes` (`SR.Outcome(id, label, arm, control, read, primary)`, 2-3
   primary; `read(row)` reads `row["m"]`, `row["pk"]` or `SR.harm_value(row, key)`),
   `activation(bundle, flags) -> (True/False/None, evidence)`, `extract(bundle, flags) ->
   (measures, problems)` and `ready=True`. Keep the declared `pilot` and `held` cohorts.
2. Write `docs/superpowers/progress/connected-world-screens-cwN.md` with `Status: DRAFT`, the
   `Compute ceiling:` and `Primary outcomes:` lines, definitions, structural zeros versus
   unknowns and stopping rules (the productive-recovery checkpoint-3 preregistration is the
   model).
3. Add tests with constructed bundles for the extractor and activation; validate on development
   worlds with `--cohort dev`; run `check --screen CWn`.
4. Run the pilot, report the projection, have the lead freeze the preregistration, run the held
   cohort with `--pilot`, then `report` and `check --metrics`. Retain `metrics.jsonl`,
   `report.md` and `source.txt` under `docs/superpowers/progress/connected-world-screens-cwN/`
   and set the reservation's status to `run` in the registry.

## 5. The compatibility matrix

`PYTHONPATH=src python scripts/feature_matrix.py [--json OUT] [--markdown OUT]` (adapted from
audit E's prototype) lists, from `feature_catalog.REQUIREMENTS`, each switch's minimal selection
and agent modes; every pair as valid or refused with the catalog's reason (a refusal is
expected only for an exclusive pair or a pair with no common agent mode); every prerequisite
drop (each must be refused); and the all-enabled selection per agent mode. It exits 1 on an
accepted drop, an unexpected refusal, a refused all-enabled selection or a one-sided
exclusion. On 2026-11-06: 24 switches, 276 pairs, none refused, 24 drops all refused,
all-enabled accepted in every mode (off: `--scholarship --clearing-protection`;
demographics-only and shadow: 7 switches; hybrid: all 24). `tests/test_feature_matrix.py`
also sends every all-enabled selection and every drop through `main._configure_run`.

`feature_catalog.py` can now represent the program's later switches: `FEATURE_GROUPS` (groups
after livelihoods for switches that are not livelihoods packages) and a `{"not": condition}`
requirement (`_excludes(other)`, declared by both switches of a mutually exclusive pair;
`exclusion_problems()` names a one-sided one). The viewer reads the `not` kind. Both are
unused, so the served catalog of every existing switch, the lobby message, `REQUIREMENTS` and
`CATALOG_SCHEMA_VERSION` (1) are byte-identical to 8abc1acb, which
`test_existing_catalog_output_is_byte_identical` checks against digests taken from the
unchanged module; `tests/test_feature_catalog.py` is unchanged. See
[feature options](feature-options.md).

## 6. Recorded limit RL8: absent versus malformed viewer records

Class: defect (viewer). `repairProjectsAt`, `timberStockAt`, `remittancesAt`,
`foodAllocationAt` and `granaryStorageAt` return null for an absent and a malformed record
alike. `viewer/src/lib/recordReading.ts` puts the presence test in front of each unchanged
reader and returns `disabled` (no snapshot of the run records the package), `absent` (on in
the run but not at this snapshot, or no livelihoods record: unknown, not zero), `malformed`
(the record or the livelihoods container was refused), `unobserved` (null frames: unknown, not
zero), `recorded_zero` or `recorded`, each with a note. The repair projects, timber stock,
remittances and food allocation panels show the note and say "recorded, nothing happened this
turn" for a recorded zero; the livelihoods panel mounts them whenever the run records their
package, so an absent record is reported instead of hidden. Tests: every state for the five
readers (`recordReading.test.ts`) and the four panels (`RecordStates.test.tsx`).

Left open: `granaries.ts`, `GranaryStorage.tsx` and its parent `Granaries.tsx` are pinned by the
crisis-candidate source witness, so the granary storage panel still renders its own "not
observed or unavailable" note; `readGranaryStorage` supplies the distinct state, and showing
it in that panel needs a reviewed exact-inverse layer (lead-owned).

## 7. Verification (2026-11-06, branch `claude/cw-e1-tooling`)

- `tests/test_screen_runner.py` (95) and `tests/test_feature_matrix.py` (16) pass under the
  offline guard; `tests/test_feature_catalog.py` and `tests/test_native_ci_shards.py` pass.
- A `DEV` smoke run on development world template 1 (10 turns, both arms, the reference native
  extension `101a4cd5...`) wrote identities, rows, activation and the harm panel; `report` and
  `check --metrics` passed.
- Viewer: `npm test -- --maxWorkers=2` (148 files, 1515 passed, 2 skipped), `npm run lint`,
  `npm run build` pass.
- Not run: any pilot or held screen (every CW screen is a stub), native or Rust suites (no
  native change).
