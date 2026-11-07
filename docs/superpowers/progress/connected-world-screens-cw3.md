# Connected-world CW3: preregistered held screen for the watershed in flow mode under upstream forest protection (slice B2)

Status: FROZEN at `d02e341637462a7e42a67aac476f10fd3da58fd9` (the screen module, extractor, runner, seed registry and simulation source; the timing pilot below ran on it, clean tree), pending the lead's review. No held run before the lead's go-ahead.

Written 2026-11-07 by the B2 lane on branch `claude/cw-b2-flow` (from `main` `ae94bca6` merged;
the watershed `flow` mode as approved at the re-check, with its two minors fixed at `538ad09e`).
Native extension: the shared build of `main` `ae94bca6`'s Rust (this branch's Rust is the same),
SHA-256 `e724072d7888888ede86acccb8db745c219c445fd47644ec9abe8ed5493e865b`. No held seed
(procedural 851-856) has been run. Code may change before the held run only to fix a defect,
recorded as an amendment below with a new pilot; no arm, outcome, window or parameter changes in
response to held outcomes.

Compute ceiling: 0.32 core-hours

Primary outcomes: cw3_ds_water_flow, cw3_ds_food_flow, cw3_ds_water_interaction

## Purpose and limits

B2 lets the watershed account own the water index (`--watershed-mode flow`,
docs/integration/watershed.md): upstream storage, transpiration and withdrawals now decide how
much water reaches a region downstream, which the old index (`record_only`, where the native
climate terms and the deforestation cascade write the index) does only through the cascade. CW3
asks: **does an upstream intervention change downstream outcomes under flow without creating
resources?** The intervention is funded forest protection against population-driven clearing
(`--clearing-protection`, as configured by its existing switch: mode `enforced`, at most 2
protected regions per civilization, docs/integration/clearing-protection.md). Protection keeps
upstream cover; under flow, cover raises a region's storage capacity and its transpiration, so
the water passed downstream can change; under the old index, protection matters downstream only
where it keeps cover above the cascade's 0.2.

- A bounded screen on default-off experimental source, not qualification. The 200-seed and
  procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.
- Six worlds support means, ranges, sign counts and the exact sign-flip enumeration (64
  assignments), not significance tests.
- **Procedural stratum only.** The watershed refuses template worlds (they have no elevation, so
  no drainage), so CW3 uses its procedural cohort 851-856; its template reservation 751-756
  stays reserved and unused (the screen declares no template cohort; the registry is unchanged).
  The shared pilot is procedural 19 only.
- Hybrid worlds, 32 regions x 10 civilizations, 200 turns.
- **Known model properties the results inherit** (watershed.md, sections 3 and 8): the derived
  index runs wetter than the old index in regions with upstream inflow (+0.05 at 32x10, up to
  +0.15 in single worlds), which is part of every `F - R` contrast; precipitation has no weather
  variability, so account floods come only from storage released by upstream forest loss
  (wildfire or clearing) and are rare (0-3 per world in 200 development turns); the drought phase
  sits at its physical limits. Three constants were fitted on the development worlds 7, 11, 13,
  17, 21, 31, 302 and 303; the held cohort is outside that set.
- Trajectories diverge once an arm acts (protection changes treasuries, cover, food and
  migration), so every measure is a property of the whole trajectory, not a mechanism estimate.
- **Prediction (inferred from development worlds, never evidence):** under flow, protection
  slightly lowers the downstream water index (more upstream transpiration and storage), and the
  downstream effect is smaller or of the other sign under the old index, where protection can
  only avoid the cascade.

## Units, cohorts and source

- Unit: one world (seed); each arm runs the same world. Procedural held 851-856; the shared
  timing pilot procedural 19 (never held). The registry's CW3 reservations are unchanged.
- Turns: 200; snapshot s records world turn s - 1 (`source_turn = s - 1` in every package record).
- Base (every arm): `--turns 200 --agents hybrid --simulate-only`, with the runner's
  `--worldgen procedural --regions 32 --civs 10`.
- Arms (root R; controls form the chain F_CP -> F -> R and R_CP -> R):

| Arm | Flags | Control |
| --- | --- | --- |
| R | `--watershed --watershed-mode record_only` (the old index; the account records only) | (root) |
| F | `--watershed --watershed-mode flow` (the account owns the index) | R |
| R_CP | R + `--clearing-protection` (mode `enforced`) | R |
| F_CP | F + `--clearing-protection` | F |

- Source: the runner `scripts/screen_runner.py`, the screen module
  `scripts/connected_world_screens.py` (CW3's arms, activation, extractor and outcomes), the seed
  registry, all identified by SHA-256 in each run's `source.txt`.

## Activation (reported per world before any effect)

`cw3_activation(bundle, flags)`; the root R is not judged.

- **F**: settled `flow` records exist and in every settled turn the index the simulation used
  equals the derived index (or the derived index capped at a recorded terrain cap change) within
  5.2e-5 (the native write-back's 4-decimal rounding plus the record's).
- **R_CP**: clearing protection kept cover: `cover_not_cleared > 0` in its last record's counters.
- **F_CP**: both.

A world where an arm did not act is reported as `not activated` and left out of that arm's
comparisons, never read as zero.

## Definitions

Region sets, fixed by the drainage graph (`watershed.graph.down`, identical in every arm of a
world because it is built from the world's saved procedural geography):

- **Downstream regions**: every region that receives inflow from at least one region.
- **Upstream regions**: every region that drains into a region (not to the sea, a sink or a lake).

A region can be both. Measures (`cw3_extract`):

- **Water index used** (`water_downstream`, `water_upstream`, `water_all`): the mean over settled
  turns and the set's regions of the watershed record's `regions.index_observed` (the index the
  simulation used after Phase 9; rounded to 6 decimals).
- **Food shortfall share after relief** (`food_shortfall_downstream`, `_upstream`, `_all`): over
  every snapshot with a food account and the set's regions with demand,
  `sum(demand x max(0, 1 - min(1, sufficiency after relief))) / sum(demand)`
  (`food_accounting.regions[*].native.demand`, `sufficiency_after_relief`); the harm panel's food
  shortfall, as a share of demand and restricted to the set. `food_met_*`: the demand-weighted
  mean of `min(1, sufficiency after relief)`.
- **Floods and droughts by cause**: account flood events (`floods_started`; `flood_consequences`
  and `flood_consequences_withheld` in flow), onsets in downstream regions, droughts declared
  (all and downstream), coastal floods (the separate disaster authority: events "Flooding
  devastates ..."), river floods of the old check (record_only) and superseded ones (flow).
- **Forest**: mean forest cover of upstream regions and of all regions at the end (the stand
  proxy; the timber stock is off, so the harm panel's stand reads `not recorded`).
- **Protection** (CP arms): adoptions, protected region-turns, cover kept, warden pay charged,
  the regions protected, those with a downstream region and the regions below them.
- **Selection** (F_CP alone): food shortfall share and water index of the regions below F_CP's own
  protected regions; there is no counterpart in an arm without protection.

**Validity checks (no resources created; a breach is a problem that fails the run, rc 3, never a
value):** in every snapshot of every arm the water account's cumulative closure residual is at
most 1e-9 of the opening storage plus cumulative precipitation (`closure_worst_relative`); in
flow arms the index used equals the derived index (capped at cap changes) within 5.2e-5
(`index_gap_worst`); every watershed record is in the arm's mode and dated s - 1; a clearing
protection record appears exactly in the CP arms. Both residuals are also reported (F_CP alone).

Structural `None` (not recorded): flow-only counters in R arms, protection measures and selection
outside the CP arms. A missing measure (no food account, no watershed record) is a problem, never
a zero.

## Primary outcomes (F_CP - F on each world, and the interaction)

1. `cw3_ds_water_flow`: downstream water index used, F_CP - F (protection's downstream effect on
   water under flow: the channel).
2. `cw3_ds_food_flow`: downstream food shortfall share after relief, F_CP - F (the welfare
   question).
3. `cw3_ds_water_interaction`: downstream water index used, (F_CP - F) - (R_CP - R): the part of
   protection's downstream water effect that exists only with flow.

**Why these** (refining the lead's suggestion with the development worlds, which are never
evidence): the lead proposed the downstream food sufficiency F_CP - F, the same contrast under the
old index or the interaction, and closure as a validity check. On the eight development worlds
(below) the downstream water index is where protection acts under flow most consistently (7 of 8
worlds negative), while downstream food is noisier (6 of 8 positive shortfall, range −0.017 to
+0.033); food stays primary because it is the welfare outcome the question asks about. The
interaction is on water, the quantity both regimes write, because the old-index contrast
(R_CP - R) varies widely in food (−0.035 to +0.071). Downstream regions are defined by the graph,
not by each arm's own protections: a set taken from F_CP's protections has no counterpart in F
(the selection outcomes report it for F_CP alone). Closure is a validity check, not an outcome.

## Secondary outcomes

- The old-index contrasts R_CP - R (downstream water, downstream food), the food interaction, and
  flow itself, F - R (downstream water and food).
- Downstream demand-weighted `min(1, sufficiency)` (F_CP - F).
- Upstream versus downstream: upstream food shortfall share and water index, all regions' food
  shortfall share (F_CP - F).
- Floods and droughts by cause: account flood events and those that acted, downstream onsets,
  droughts declared (all and downstream), coastal floods (F_CP - F); river floods superseded
  (F_CP alone).
- Forest: upstream mean cover at the end (F_CP - F); cover kept and warden pay charged, regions
  below protected regions (F_CP alone).
- Selection (F_CP alone): food shortfall share and water index below F_CP's own protected regions.
- Validity residuals (F_CP alone).

## Harm panel

The runner's fixed panel beside every arm against its control (F - R, R_CP - R, F_CP - F):
population and treasury at the end, food shortfall after relief over the run, epidemic deaths,
agents migrating between regions, the wealth Gini at the end; priced-out persons and children,
and the timber stand, read `not recorded` (household retail and the timber stock are off); deaths
by famine and by war need slice extractors (`requires slice extractor`). The screen also declares
F_CP - F rows for the world food shortfall, population, treasury and migration.

## Extractor validation (development worlds only, before the pilot)

Development runs of all four arms on the procedural development worlds 7, 11, 13, 17, 21, 31,
302 and 303, `--cohort dev`, 200 turns, `--jobs 2` (source: the worktree before the screen's
commit; the extractor is the committed one): 32 runs, 0 failed, every outcome extracted, `check
--metrics ... --cohort dev` passes. F, R_CP and F_CP activated on all 8 worlds. Validity: the worst
closure residual was 2.5e-15 relative; the worst index gap 5.0e-5 (the native rounding).

An independent recomputation from a re-run bundle (procedural 11, F_CP, the runner's command and
environment, not importing the screen module) matched the extractor: downstream water from the
snapshots' `ecology` water 0.639590727 against 0.639590727 (the record's 6-decimal rounding);
the world food shortfall 2614.218 equal to the harm panel's value, and its share 0.07108972
equal to `food_shortfall_all`.

`tests/test_cw3_screen.py` (oracle chunk `connected-world-b`, native shard 0) covers the arms,
primaries and interaction, the region sets and measures, flow and protection activation
(including the capped index at a cap change and a gap that fails), the validity problems
(closure, gap, wrong mode, a protection record without the switch) and missing records as
problems. `check --screen CW3` passes.

Development outcomes (8 worlds, never evidence; mean [min, max], sign counts, sign-flip):

| Outcome | Mean [min, max] | > 0 / < 0 | Sign-flip |
| --- | --- | --- | --- |
| Downstream water, F_CP - F (primary 1) | −0.0022 [−0.0069, +0.0005] | 1 / 7 | 6/256 |
| Downstream food shortfall share, F_CP - F (primary 2) | +0.0086 [−0.0168, +0.0327] | 6 / 2 | 44/256 |
| Downstream water, (F_CP - F) - (R_CP - R) (primary 3) | −0.0052 [−0.0425, +0.0091] | 4 / 4 | 134/256 |
| Downstream water, R_CP - R | +0.0030 [−0.0094, +0.0416] | 4 / 4 | 224/256 |
| Downstream food shortfall share, R_CP - R | −0.0009 [−0.0349, +0.0711] | 2 / 6 | 244/256 |
| Downstream water, F - R (flow itself) | +0.056 [+0.006, +0.130] | 8 / 0 | 2/256 |
| Downstream food shortfall share, F - R | −0.025 [−0.055, +0.008] | 1 / 7 | 4/256 |
| Upstream water, F_CP - F | −0.0045 [−0.0102, +0.0032] | 2 / 6 | 12/256 |
| Upstream mean cover at the end, F_CP - F | +0.11 [+0.03, +0.24] | 8 / 0 | 2/256 |
| Droughts declared, F_CP - F | +2.75 [+1, +6] | 8 / 0 | 2/256 |

## Timing pilot (the shared pilot, on the frozen source)

`run PILOT --screen CW3 --cohort pilot --jobs 2` on `d02e3416` (clean tree; `source.txt`: dirty
0, dirty-code 0): 4 runs, 0 failed, every outcome extracted (`check --metrics ... --cohort pilot`
passes); 95 s of simulation and extraction. Mean seconds per run: R 21.5, F 23.0, R_CP 25.3,
F_CP 25.0. F, R_CP and F_CP activated. **Projected held run: 0.158 core-hours for 24 runs**
(x1.5 = 0.237). The pilot's `metrics.jsonl`, `source.txt` and `report.md` are retained in
`connected-world-screens-cw3/pilot/` (the held run's `--pilot`). The report prints the pilot's
outcomes; they were not read for any decision.

## Budget and stopping rules

- **Compute ceiling 0.32 core-hours** (the line above, read by the runner: the pilot projection
  x 2, under the 2.0 cap); run with `--jobs 2` because other lanes share the 4 cores. The runner
  refuses a held run whose pilot projection x 1.5 (0.237) exceeds the ceiling and starts no run
  that would pass it; runs not started are reported as `not run` (exit code 4), never as zeros.
  Raising the ceiling needs the lead's amendment before any held outcome is read.
- At most 2 GiB of transient disk; raw run outputs are deleted after extraction.
- A failed run is reported as failed with its reason and is not replaced by another seed; a
  held-run failure that needs new worlds uses the program reserve through the lead
  (`--cohort reserve`).
- After the held run: `report` (retained with `metrics.jsonl`, `source.txt`, `held-run.json`
  under `docs/superpowers/progress/connected-world-screens-cw3/`), `check --metrics`, and
  `mark-run`, whose registry change is committed with the results.

## Amendments

None.

## Results

No held run (awaiting the lead's review and go-ahead).
