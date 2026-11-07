# Connected-world CW3: preregistered held screen for the watershed in flow mode under upstream forest protection (slice B2)

Status: FROZEN at `a83af3f3ef89e63c365a1953f701353c656535c4` (the screen module, extractor, runner, seed registry and simulation source as amended by Amendment 1; the timing pilot below ran on it, clean tree), with this page frozen as amended by Amendment 1 (2026-11-07, before any held run); the lead reviewed the screen (first frozen at `d02e3416`), accepted the runner change and gave the go-ahead for the held run after Amendment 1.

Written 2026-11-07 by the B2 lane on branch `claude/cw-b2-flow` (from `main` `ae94bca6` merged;
the watershed `flow` mode as approved at the re-check, with its two minors fixed at `538ad09e`).
Native extension: the shared build of `main` `ae94bca6`'s Rust (this branch's Rust is the same),
SHA-256 `e724072d7888888ede86acccb8db745c219c445fd47644ec9abe8ed5493e865b`. No held seed
(procedural 851-856) has been run. Code may change before the held run only to fix a defect,
recorded as an amendment below with a new pilot; no arm, outcome, window or parameter changes in
response to held outcomes.

Compute ceiling: 0.40 core-hours

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
- Arms (root R; controls form the chains F_CP -> F_CPc -> F -> R and R_CP -> R; F_CPc added by
  Amendment 1):

| Arm | Flags | Control |
| --- | --- | --- |
| R | `--watershed --watershed-mode record_only` (the old index; the account records only) | (root) |
| F | `--watershed --watershed-mode flow` (the account owns the index) | R |
| R_CP | R + `--clearing-protection` (mode `enforced`) | R |
| F_CPc | F + `--clearing-protection --clearing-protection-mode cost_only` (the same adoption, planning and warden charges as F_CP; protection sends nothing, so no cover is kept) | F |
| F_CP | F + `--clearing-protection` | F_CPc |

  The primaries compare F_CP with F (an ancestor on its control chain); the runner's harm panel
  shows each arm against its declared control (F_CP - F_CPc, F_CPc - F, F - R, R_CP - R), and the
  screen declares F_CP - F harm rows beside them.

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
- **F_CPc** (Amendment 1): flow as for F, and protections were paid for clearing they would have
  stopped (`cover_would_keep > 0`) while keeping none (`cover_not_cleared = 0`).

A world where an arm did not act is reported as `not activated` and left out of that arm's
comparisons, never read as zero.

## Definitions

Region sets of the primaries: **fixed before treatment and identical in every arm of a world**
(confirmed by Amendment 1). They come from the static drainage graph alone
(`watershed.graph.down`, built at enable from the world's saved procedural geography and never
changed), not from regions any arm protected or from anything that diverged later:

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
  protected regions (post-treatment and arm-dependent; secondary only); there is no counterpart in
  an arm without protection.
- **Candidate set at enable time** (protection arms; Amendment 1): clearing protection's first
  planning (turn 0): the regions it adopted then, and those eligible then but over the
  civilization's limit or unaffordable. The state before that planning is the same in every arm,
  so the set is pre-treatment and the same in R_CP, F_CPc and F_CP (checked on all eight
  development worlds); arms without protection carry no clearing-protection record, so it cannot
  define the primaries' F_CP - F sets. It defines the F_CP - F_CPc secondaries below it:
  `cand_water_below`, `cand_food_shortfall_below` (the regions downstream of a candidate).

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
- Amendment 1, protection apart from its cost: F_CP - F_CPc on downstream water and food (the
  graph's sets), water and food below the turn-0 candidate set, upstream water, upstream cover and
  droughts; the cost alone, F_CPc - F, on downstream food and water and the treasury; the cover
  F_CPc would have kept (F_CPc alone). Secondaries, never primaries.

## Harm panel

The runner's fixed panel beside every arm against its control (F - R, R_CP - R, F_CPc - F,
F_CP - F_CPc):
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

Amendment 1 re-validation (source `a83af3f3`'s screen module on the worktree, the same eight
worlds, five arms): 40 runs, 0 failed, every outcome extracted, `check --metrics ... --cohort dev`
passes; F_CPc activated on all 8 worlds (paid protections would have kept 3.3-7.0 cover, kept
none); the 32 rows of R, F, R_CP and F_CP equal the first validation's in every measure (0
differences); the turn-0 candidate set is identical in R_CP, F_CPc and F_CP on every world (6-10
regions; 1-5 regions below them).

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

`run PILOT --screen CW3 --cohort pilot --jobs 2` on `a83af3f3` (Amendment 1; clean tree;
`source.txt`: dirty 0, dirty-code 0): 5 runs, 0 failed, every outcome extracted (`check --metrics
... --cohort pilot` passes); 119 s of simulation and extraction. Mean seconds per run: R 25.2,
F 28.5, R_CP 22.0, F_CPc 22.5, F_CP 20.8. F, R_CP, F_CPc and F_CP activated. **Projected held run:
0.198 core-hours for 30 runs** (x1.5 = 0.297). The pilot's `metrics.jsonl`, `source.txt` and
`report.md` are retained in `connected-world-screens-cw3/pilot/` (the held run's `--pilot`;
they replace the first pilot on `d02e3416`, 4 arms, 0.158 core-hours for 24 runs, which the
fifth arm made stale). The report prints the pilot's outcomes; they were not read for any
decision.

## Budget and stopping rules

- **Compute ceiling 0.40 core-hours** (the line above, read by the runner: the amended pilot's
  projection 0.198 x 2, under the 2.0 cap; was 0.32 before Amendment 1); run with `--jobs 2`
  because other lanes share the 4 cores. The runner refuses a held run whose pilot projection
  x 1.5 (0.297) exceeds the ceiling and starts no run
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

**Amendment 1 (2026-11-07, before any held run; the lead's review).**

1. *The primaries' downstream set is fixed before treatment and identical in every arm.* It was
   already: the extractor takes downstream (and upstream) regions from the static drainage graph
   only, never from an arm's protections or from anything that diverged. The page now says so.
   Clearing protection's candidate set at enable time (turn 0) is pre-treatment too and the same
   in every protection arm (verified on the eight development worlds: R_CP, F_CPc and F_CP give the
   identical set on each), but arms without protection carry no clearing-protection record, so it
   cannot define the F_CP - F primaries; it defines the new F_CP - F_CPc secondaries. The selection
   outcomes below each arm's own protected regions stay F_CP-alone secondaries.
2. *A cost-only arm separates protection's effect on forest and water from its treasury cost.* Arm
   F_CPc (flow, clearing protection in its `cost_only` mode: the same adoption, planning and
   charges, nothing protected) with the chain F_CP -> F_CPc -> F -> R; F_CP - F_CPc and F_CPc - F are
   secondaries (listed above); the three primaries, their arms and controls are unchanged.
   Activation and the validity check for F_CPc are added (it must keep no cover).
3. Re-validated on the development worlds (40 runs, 0 failed, every outcome extracted, F_CPc
   activated on 8 of 8; the R, F, R_CP and F_CP runs reproduce the first validation exactly), and
   the timing pilot re-run on the amended source (the fifth arm raised the projection from 0.158
   to 0.198 core-hours); the ceiling follows (0.40 core-hours).

Development reading (never evidence; it changes nothing preregistered): the cost alone moved the
downstream water index about as much as protection did (F_CPc - F −0.0014, 7 of 8 negative;
F_CP - F_CPc −0.0008, 4 of 8), so the primary F_CP - F mixes protection with the trajectory its
warden charges set off; the F_CP - F_CPc secondaries separate them.

**Erratum and notes on the frozen text (2026-11-07, after the held run; the frozen sentences are
left as written).**

- "No held seed (procedural 851-856) has been run" (the header) describes the time of the freeze.
- The arms table's "the same adoption, planning and warden charges as F_CP" and Amendment 1's
  "separates protection's effect on forest and water from its treasury cost" describe the rules.
  The realized bills differ: F_CP charged 1.7–5.1 times F_CPc's on the held worlds and 2.6–4.6
  times on the development worlds (protections that keep cover last longer and are charged more;
  clearing-protection.md, endogenous cost). The screen module's labels "cost held equal" and "the
  cost alone" (frozen) carry the same caveat, and so does the development reading just above
  ("the F_CP - F_CPc secondaries separate them": they do not hold the bill equal).

## Results (held run, 2026-11-07)

Procedural 851-856, 200 turns, five arms, `run HELD --screen CW3 --cohort held --pilot
connected-world-screens-cw3/pilot/metrics.jsonl --jobs 2` on `b9170bef` (the frozen source plus
this page's Amendment 1 commit; clean tree). The template cohort 751-756 was never run: `mark-run`
recorded it as `never_run`, unused by design (CW3 declares no template cohort), and the procedural
cohort as `run` (incomplete, below). Retained in `connected-world-screens-cw3/held/`:
`metrics.jsonl`, `source.txt`, `held-run.json`, `report.md`, `check.txt`.

Registry side effect, corrected (independent check, item C5): recording the template reservation
as unused first appended text to its `use` field, which the registry-content hash covers, so the
content hash changed from `a703a850` to `95e3bdea` for one commit (unlike a complete mark-run). The
runner now writes that note to a run-record field, `unused` (reason, output folder, time), which
the content hash excludes like `status` and `held_run`; the entry's `use` is restored and the
registry content is again `a703a850`, the value CW3's held run, its pilot and every other
screen's recorded identities used. No run was repeated; CW1's, CW4's and CW4b's retained metrics
still check complete (`check --metrics ... --cohort held`), and CW3's checks with its one recorded
failure.

**Identity.** Source `b9170bef9729c81a0063a9395c6e9085c61ed0fe`, dirty 0, dirty-code 0; native
extension SHA-256 `e724072d7888888ede86acccb8db745c219c445fd47644ec9abe8ed5493e865b` (the shared
build of `main` `ae94bca6`'s Rust); runner `bd443414…`, screen module `ca65e38d…`, registry
content `a703a850…`, preregistration `f834f8ef…`; run identity digest `4b61577c…`. The pilot's
identity matches (its source `a83af3f3` differs only in documentation (this page and the retained
pilot files; no code path)).

**Runs and failures.** 30 runs, **1 failed: F_CP on procedural 851**, rc 1, before its bundle was
written: `ArtifactIOError ... [Errno 28] No space left on device` (the shared machine's disk filled
during the run; 7.9 GB free when checked after it). The failure is environmental, not a model
failure. Per the stopping rules it is reported, not replaced: the runner counts a failed row as
done, so `--resume` does not rerun it, and no row was edited. Every comparison that needs F_CP on
851 is `failed` there and computed on the 5 other worlds; everything else uses 6. `check --metrics
... --cohort held` reports this one failure (exit 1) and nothing else; missing outcomes 0.

**Compute.** 1148 s of simulation and extraction, 0.319 core-hours, under the 0.40 ceiling (no run
stopped by it); runs averaged 35-42 s against the pilot's 21-29 s (a loaded machine).

### Activation and validity (before any effect)

- Activation: F 6 of 6, R_CP 6 of 6, F_CPc 6 of 6, F_CP 5 of 6 (851 failed). R is the root.
- Validity, every completed run of every arm (a breach would have been a problem, rc 3; there were
  none): the water account closes in every snapshot (worst relative residual in F_CP 7.7e-16 to
  2.0e-15), the flow arms' index used equals the derived index, capped at recorded cap changes,
  within 5.2e-5 (worst 5.0e-5, the native rounding), every record is in its arm's mode and dated,
  and the cost-only arm kept no cover (it would have kept 4.5-6.9). No water was created.

### Primary outcomes (F_CP - F; procedural; 851 failed)

| Outcome | 852 | 853 | 854 | 855 | 856 | Mean [min, max] | > 0 / < 0 | Sign-flip (of 32) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cw3_ds_water_flow`: downstream water index | +0.00077 | −0.00748 | −0.00642 | −0.00368 | +0.00139 | −0.00309 [−0.00748, +0.00139] | 2 / 3 | 8 as extreme; means ±0.00395 |
| `cw3_ds_food_flow`: downstream food shortfall share | +0.0239 | +0.0031 | −0.0114 | +0.0060 | +0.0140 | +0.0071 [−0.0114, +0.0239] | 4 / 1 | 10 as extreme; means ±0.0117 |
| `cw3_ds_water_interaction`: (F_CP - F) - (R_CP - R), downstream water | +0.0427 | −0.0191 | −0.0029 | −0.0141 | +0.0051 | +0.0024 [−0.0191, +0.0427] | 2 / 3 | 28 as extreme; means ±0.0168 |

Reading (descriptive only; not significance tests): on five worlds, protection under flow left the
downstream water index slightly lower on average with mixed signs (2 up, 3 down; a quarter of the
sign assignments are as extreme), and downstream food shortfall slightly higher (4 of 5; 10 of 32
assignments as extreme); the interaction is near zero with mixed signs (28 of 32 as extreme): no
downstream effect specific to flow is visible. None of the three is distinguishable from the
sign-flip spread on these worlds.

### Secondary outcomes (means [min, max], sign counts, sign-flip as extreme)

| Outcome | Mean [min, max] | > 0 / < 0 / = 0 | Sign-flip |
| --- | --- | --- | --- |
| Downstream water, R_CP - R (old index; 6 worlds) | −0.0025 [−0.0419, +0.0124] | 3 / 3 / 0 | 58/64 |
| Downstream food shortfall share, R_CP - R | −0.0103 [−0.0239, +0.0028] | 2 / 4 / 0 | 8/64 |
| Downstream food shortfall share, interaction | +0.0157 [−0.0129, +0.0406] | 4 / 1 / 0 | 8/32 |
| Downstream water, F - R (flow itself; 6) | +0.051 [−0.009, +0.098] | 5 / 1 / 0 | 4/64 |
| Downstream food shortfall share, F - R | −0.026 [−0.043, −0.009] | 0 / 6 / 0 | 2/64 |
| Upstream food shortfall share, F_CP - F | +0.0053 [−0.0188, +0.0299] | 3 / 2 / 0 | 18/32 |
| Upstream water, F_CP - F | −0.0009 [−0.0064, +0.0014] | 3 / 2 / 0 | 28/32 |
| All regions' food shortfall share, F_CP - F | +0.0075 [−0.0009, +0.0188] | 4 / 1 / 0 | 4/32 |
| Account flood events (those that acted, and downstream onsets), F_CP - F | +0.6 [0, +2] | 2 / 0 / 3 | 16/32 |
| Downstream mean min(1, sufficiency), F_CP - F | −0.0071 [−0.0239, +0.0114] | 1 / 4 / 0 | 10/32 |
| Droughts declared, F_CP - F (downstream) | +1.2 [−5, +10] (+0.4 [−3, +4]) | 3 / 2 / 0 (2 / 1 / 2) | 24/32 (24/32) |
| Coastal floods, F_CP - F | 0 | 0 / 0 / 5 | 32/32 |
| Upstream mean cover at the end, F_CP - F | +0.014 [−0.020, +0.045] | 4 / 1 / 0 | 8/32 |
| **Protection apart from its cost** (Amendment 1): downstream water, F_CP - F_CPc | −0.0018 [−0.0045, +0.0020] | 1 / 4 / 0 | 6/32 |
| Downstream food shortfall share, F_CP - F_CPc | −0.0156 [−0.0674, +0.0061] | 2 / 3 / 0 | 12/32 |
| Water below the turn-0 candidates, F_CP - F_CPc | −0.0029 [−0.0126, +0.0070] | 2 / 3 / 0 | 14/32 |
| Food shortfall share below the candidates, F_CP - F_CPc | +0.0025 [−0.0601, +0.1289] | 1 / 4 / 0 | 32/32 |
| Upstream water, F_CP - F_CPc | −0.0012 [−0.0041, +0.0005] | 1 / 4 / 0 | 6/32 |
| Upstream cover at the end, F_CP - F_CPc | +0.032 [−0.085, +0.142] | 3 / 2 / 0 | 16/32 |
| Droughts declared, F_CP - F_CPc | +0.4 [−1, +2] | 2 / 1 / 2 | 24/32 |
| **The cost alone**: downstream food shortfall share, F_CPc - F (6) | +0.0209 [+0.0064, +0.0560] | 6 / 0 / 0 | 2/64 |
| Downstream water, F_CPc - F | −0.0013 [−0.0057, +0.0053] | 1 / 5 / 0 | 26/64 |
| Treasury at the end, F_CPc - F | +57 [−3618, +3512] | 3 / 3 / 0 | 62/64 |

F_CP alone: river floods superseded 0-8 (mean 2.6); cover kept 10.6-25.6 (mean 18.7); warden pay
charged 1057-2561 (mean 1869); 6-10 regions below a protected region; selection (below F_CP's own
protections, no counterpart): food shortfall share 0.041-0.119, water index 0.606-0.723.

Reading (secondaries; descriptive): running flow rather than record_only (F − R, a comparison of
two water models, not an intervention) gave a higher downstream water index on 5 of 6 worlds,
consistent with the known wet bias, and a lower downstream food shortfall on all 6 (2 of 64
assignments as extreme). Cost-only protection (F_CPc − F: the same rules, charges of 446–691 coins
per world, no cover kept) raised downstream food shortfall on all 6 worlds (2 of 64 as extreme).
The cost-only arm did not reproduce F_CP's bill: protections that keep cover last longer and are
charged more, and F_CP paid 1.7–5.1 times F_CPc's warden pay on the same worlds
(clearing-protection.md, endogenous cost). F_CP − F_CPc therefore contrasts kept cover together
with a larger bill, not cover at equal cost. It moved downstream water slightly down (4 of 5, 6 of
32) and food shortfall down on average with mixed signs (2 up, 3 down), the mean resting on
procedural 854 (−0.067; the other four average −0.003). The secondaries suggest that the rise in
downstream food shortfall does not need kept cover, since it appears without any. They do not
split F_CP − F into a cover part and a cost part, and the end treasury shows no consistent
difference that would mark the pathway.

### Harm panel (each arm against its declared control, and F_CP - F)

| Comparison | Population at the end | Treasury at the end | Food shortfall after relief (world) | Epidemic deaths | Agents migrating | Wealth Gini at the end |
| --- | --- | --- | --- | --- | --- | --- |
| F - R (6) | −36 [−258, +161], 3/3 | −582 [−3789, +552], 2/4 | −1461 [−2527, +117], 1/5 | +108 [−149, +247], 5/1 | −651 [−1983, +737], 1/5 | +0.025 [−0.091, +0.197], 4/2 |
| R_CP - R (6) | −2 [−90, +218], 2/4 | +253 [−5106, +3428], 4/2 | −235 [−1904, +1601], 2/4 | −18 [−194, +101], 4/2 | −553 [−1794, +352], 2/4 | +0.017 [−0.120, +0.148], 3/3 |
| F_CPc - F (6) | +39 [−173, +310], 2/4 | +57 [−3618, +3512], 3/3 | +1697 [+115, +6385], 6/0 | −66 [−354, +90], 3/3 | +1172 [−1605, +3802], 5/1 | +0.018 [−0.163, +0.148], 4/2 |
| F_CP - F_CPc (5) | +2 [−282, +238], 3/2 | −58 [−1932, +1315], 3/2 | −1159 [−7088, +829], 3/2 | +4 [−203, +231], 3/2 | −1090 [−5578, +1122], 1/4 | −0.078 [−0.355, +0.072], 1/4 |
| F_CP - F (5) | +80 [−11, +196], 4/1 | +734 [−1066, +2706], 3/2 | +774 [−703, +2039], 4/1 | −77 [−194, +19], 2/3 | +91 [−1776, +2236], 2/3 | −0.024 [−0.237, +0.220], 1/4 |

Nulls as nulls: priced-out persons and children and the timber stand are `not recorded` in every arm
(household retail and the timber stock are off); deaths by famine and by war `require a slice
extractor`. Values are mean [min, max] and > 0 / < 0 counts; the full rows, per world, with the
sign-flip distributions, are in `held/report.md`.

Harm reading (descriptive): F_CP − F raised world food shortfall on 4 of 5 worlds (+774, 6 of 32)
and population on 4 of 5 (+80); cost-only protection raised world food shortfall on all 6 (+1697,
2 of 64) and migration on 5 of 6; flow itself raised epidemic deaths on 5 of 6 (+108, 8 of 64) and
lowered world food shortfall on 5 of 6. The other cells are mixed.

### Supplementary (deterministic completion after an infrastructure failure)

**Not part of the result.** The frozen result above stands on five worlds; this is a sensitivity
line only (the lead's decision, 2026-11-07). The failed run, F_CP on procedural 851, failed on
the shared machine's full disk during another lane's build, before its bundle was written; the
simulation is deterministic (the development re-validation reproduced 32 earlier rows exactly). It was re-run once, exactly and alone (nothing else was re-run), on
a `git archive` of the frozen held source `b9170bef`, with the same shared native extension
(SHA-256 `e724072d7888888ede86acccb8db745c219c445fd47644ec9abe8ed5493e865b`, verified), the
runner's own `run_one` (the same command line, environment and extractor) and the same identity
checks, into a separate output directory (disk free before: 12 GB). Its identity lines equal the
held run's in every line (source, dirty 0 / 0, native, interpreter, runner `bd443414…`, screen
module `ca65e38d…`, registry `a18c129d…` and content `a703a850…`, preregistration `f834f8ef…`)
except the `chronicler` path, which names the archive's copy of the same source. The `source` and
`dirty` lines are written by the driver, since an archive carries no git metadata. The archive's
`src/`, `scripts/`, `chronicler-agents/` and `pyproject.toml` are byte-identical to `b9170bef`'s
tree. Because the path line differs, the row's identity digest is `c814f9e8…`, not the held
run's `4b61577c…`. The run: rc 0,
activated (200 settled flow turns, index gap 5.0e-5; 1,762 protected region-turns kept 26.18
cover), every outcome extracted, closure 1.5e-15 relative. Retained in
`connected-world-screens-cw3/supplementary/` (`source.txt`, `metrics.jsonl`,
`six_world_primaries.json`, the driver `run_supp.py`).

Six-world primaries with it (sensitivity only; 851's values: water +0.0059, food shortfall
+0.0101, interaction −0.0066):

| Primary (6 worlds) | Mean [min, max] | > 0 / < 0 | Sign-flip (of 64) | Frozen 5-world result |
| --- | --- | --- | --- | --- |
| `cw3_ds_water_flow` | −0.0016 [−0.0075, +0.0059] | 3 / 3 | 32 as extreme | −0.0031, 2 / 3, 8 of 32 |
| `cw3_ds_food_flow` | +0.0076 [−0.0114, +0.0239] | 5 / 1 | 12 as extreme | +0.0071, 4 / 1, 10 of 32 |
| `cw3_ds_water_interaction` | +0.0009 [−0.0191, +0.0427] | 2 / 4 | 60 as extreme | +0.0024, 2 / 3, 28 of 32 |

The sixth world leaves the reading unchanged: no clear downstream water effect of protection under
flow, a small rise in downstream food shortfall, no flow-specific interaction.

### What CW3 shows (and does not)

On these procedural worlds (five for every comparison with F_CP; the sixth, completed
afterwards, is a sensitivity line only), funded upstream forest protection did not produce a clear
downstream effect under flow: the downstream water index moved down by a few thousandths on
average with mixed signs, the downstream food shortfall rose slightly, and nothing in the
interaction marks the effect as specific to flow. The water account created no water. In a
secondary, cost-only protection, which kept no cover and paid about a third of F_CP's warden pay,
also raised downstream food shortfall (on all six worlds). The rise therefore does not need kept
cover, but the cost arm does not hold the bill equal and cannot apportion F_CP's food change
between cover and cost. One
F_CP run failed for lack of disk; the primaries rest on five worlds. A bounded screen, not
qualification; the watershed's known wet bias and its forest-loss-only floods (watershed.md) apply.
No other held run will be rerun; the one supplementary completion of F_CP on 851 is reported
above as sensitivity only.
