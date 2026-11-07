# Connected-world CW3b: preregistered held screen for infrastructure condition and repair (slice B3)

Status: DRAFT (not frozen; the lead reviews the screen and freezes this page before any held run)

Written 2026-11-07 by the B3 lane on branch `claude/cw-b3-infrastructure` (main bac45cb5 merged;
B3 reviewed and approved at `10d73230`; the flow x condition integration at `c5593e81`; the screen
declared at `80966420` and its region set fixed at `dda1be4b`, on which the timing pilot below ran,
clean tree). Native extension `20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca`
(`~/.venvs/native-a3`, built from main's Rust). No held seed (template 3501-3506, procedural
3601-3606) has been run. Code may change before the held run only to fix a defect, recorded as an
amendment below with a new pilot; no arm, outcome, region set or parameter changes in response to
held outcomes.

Compute ceiling: 0.50 core-hours

Primary outcomes: cw3b_service_l9, cw3b_food_l9, cw3b_service_treasury

## Question

`--infrastructure-condition` (docs/integration/infrastructure-condition.md) gives irrigation works
and roads a condition that wears, fails and is repaired by works paid from the treasury, under L9
through their own proposal. CW3b asks: **does funded repair keep irrigation serving, and does that
keep food in irrigated regions, against the same wear with every work refused?** Separately under
L9 (the works must win their own envelope) and under the treasury alone (the works are paid when
the treasury can), so the screen shows both whether repair works when it is funded and whether the
budget process funds it. And what does it cost: the repairs budget RS2 also draws on, farm time,
treasury, coins destroyed by the public-works sink, food and population world-wide?

- A bounded screen on default-off experimental source, not qualification: the 200-seed and
  procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.
- Six worlds per stratum support means, ranges, sign counts and the exact sign-flip enumeration,
  not significance tests. A null result is a result.
- **Prediction (inferred from development worlds, never evidence):** service maintained is higher
  under repair in both pairs and clearly higher under the treasury pair (works are funded far more
  often without L9: the development activation in the integration page, section 8); the food
  effect in the irrigated regions is small and of uncertain sign (the irrigation bonus is 10% of
  the arable ceiling, and repair takes farm time). Trajectories diverge from the first work that
  spends or the first service lost, so every measure after that is a property of the whole
  trajectory, not a mechanism estimate.

## Units, cohorts and source

- **Units:** worlds (seeds). Every arm runs once on every world and is compared with its declared
  control on the same world, per stratum: template (8 regions, 4 civs) and procedural (32 regions,
  10 civs, `--worldgen procedural --regions 32 --civs 10`), 200 turns, `--agents hybrid`.
- **Held cohort (new, reserved for CW3b):** template 3501-3506, procedural 3601-3606
  (`scripts/seed_registry.json` entries `cw3b-held-t` and `cw3b-held-p`, status `reserved`).
  Checked: no registry entry of either stratum holds any of them (the collision rule: a seed
  collides with every entry of its stratum whatever the world size); a targeted repository scan
  (seed keys, `--seed` values, seed lists and ranges in Python, Markdown, shell and YAML) found
  none; and `check --screen CW3b` (the runner's `check_seeds`: the registry reservation, no other
  entry, no gate range, not 1000-1999, no development world, no duplicate, not run) passes.
  Registering the cohort changes the registry content hash (cohorts and seeds) from `a703a850...`
  to `3b505087...`: `tests/test_screen_runner.py` proves CW3b's two entries are the only change
  since the recorded identities; an earlier screen's `--resume` (CW3's incomplete held run) would
  now be refused by the runner's identity check.
- **Timing pilot:** the shared pilot, template 5 and procedural 19 (never evidence).
- **Base flags (every arm):** `--turns 200 --agents hybrid --simulate-only --grain-reserves
  --grain-storage --repair-projects` (RS2 is a prerequisite of the repair modes and the repairs
  budget the works compete with); every other switch at its default.
- **Arms** (root B):

  | Arm | Flags (added to the base) | Control | Role |
  | --- | --- | --- | --- |
  | B | `--local-budgets --maintenance-obligation` | — | the L9 + RS2 baseline without the switch |
  | R | B + `--infrastructure-condition --infrastructure-condition-mode record_only` | B | condition recorded, nothing changes (the measurement control; R - B is structurally 0) |
  | W | B + `--infrastructure-condition --infrastructure-condition-mode wear_only` | R | condition and service act, nothing repairs: every work refused (the underfunded counterfactual) |
  | C | B + `--infrastructure-condition` (repair) | W | works funded through their own L9 proposal |
  | W_T | `--infrastructure-condition --infrastructure-condition-mode wear_only` | W | wear without L9 or the maintenance obligation |
  | C_T | `--infrastructure-condition` (repair) | W_T | works funded from the treasury alone |

  The "works refused" counterfactual is `wear_only`: the switches allow it cleanly (the same wear,
  damage and consequences, no work opens), whereas refusing works inside the repair mode would need
  a new switch. W_T - W carries the removal of L9 (other services change too), so it is reported in
  the harm panel only, never as an effect of repair.

## Primary outcomes (arm - control on each world)

1. **`cw3b_service_l9`**: irrigation service maintained, C - W: the share of irrigation asset-turns
   (every serving or failed irrigation asset in every snapshot's record) whose service
   `min(1, condition / 0.5)` is at least 0.5 (the gate at which irrigation still sets the native
   flag). Read from `condition_service`, which every mode records the same way.
2. **`cw3b_food_l9`**: food in the irrigated regions, C - W: the demand-weighted food shortfall share
   after relief (sum of demand x max(0, 1 - min(1, sufficiency after relief)) over sum of demand)
   over every snapshot, in the regions holding an irrigation asset at snapshot 28. Snapshot 28 is
   the last pre-treatment snapshot: BUILD takes two turns, so an asset completes at the earliest in
   turn 2; it wears 0.01 a turn, so its first wear work opens in Phase 10 of turn 27 and spends
   from turn 28, and no service is lost before 50 turns of wear; snapshot 28 records world turn 27.
   A war-damage work opened before then is counted (`early_war_works`; 0 in the pilot).
3. **`cw3b_service_treasury`**: irrigation service maintained, C_T - W_T (the same measure as 1, the
   pair without L9).

## Secondary outcomes (shown, not primary)

Food in the irrigated regions C_T - W_T; what wear alone costs (W - R: service, food); food met;
assets failed (C - W, C_T - W_T); the works' delivered work (C, C_T), L9 awards to the works'
proposal (C), stall turns without an envelope and without timber (C), and the underfunded public
works story count (C: works stalled 20 or more turns on an asset that failed).

## Fixed harm panel (beside every comparison)

The runner's panel (population, treasury, food shortfall world-wide, out-migration, Gini, priced-out
and death rows "not recorded" where their system is off) for every arm against its control, and
these screen harms: **the L9 envelope displacement** (RS2 repair work delivered, C - W and C_T - W_T:
the integration page found the works' own proposal lowered RS2's and the works' delivery against
the pooled design, 53 -> 10 and 303 -> 191 work units on development worlds), **farm time removed**
(the works' delivered work, C), **treasury** and **mean stability of living civs** at the end (C - W),
**coins destroyed** by the public-works sink (C, C_T), **food shortfall world-wide** and **population**
(C - W, C_T - W_T), and R - B world food shortfall (structurally 0: the record changes nothing).

## Activation (reported first, per world)

R: assets registered. W, W_T: an irrigation asset-turn below full service. C, C_T: the works
delivered work. B is not judged. A world where an arm did not act is "not activated", never zero,
and is left out of that arm's effect summaries (the runner's rule). The pilot activated every arm on
both pilot worlds.

## Analysis plan

Per stratum: per-world values, mean, min/max, sign counts and the exact sign-flip enumeration of
the mean (the runner's report). The three primaries are read together: service maintained in each
pair, and food in the irrigated regions under L9. No pooling across strata, no significance test,
no adjustment of arms or outcomes after the held run. Harms are read beside every primary; a gain
in service bought with a world-wide food or population loss is reported as such.

## Compute ceiling (from the timing pilot)

Pilot at `dda1be4b` (clean tree), `--jobs 2`, 12 runs, 168 s of simulation and extraction
(0.047 core-hours); per run, template 7.1-7.8 s and procedural 18.5-22.3 s. The runner's projection
for the held run (72 runs) is 0.280 core-hours, x1.5 = 0.421, under the **ceiling of 0.50
core-hours** (the line above, read by the runner). Pilot evidence: `/home/user/evidence/b3/cw3b/`
(`pilot/metrics.jsonl`, `pilot/source.txt`, `pilot-report.txt`; outside the repository).

## Failure handling

A missing or malformed outcome or harm makes the run a visible failure (rc 3, reasons named); a run
that crashes is not run (rc 1) and is reported, never imputed. A failure that is a code defect is
fixed by amendment with a new pilot before any rerun; a held run interrupted by the environment is
resumed with `--resume` (the runner refuses any identity change but another screen's `mark-run`).
A failure on a held world is fixed on the reserve cohort only with the lead's assignment.

## The viewer's failed or underfunded public-works story (Program B5)

The Livelihoods panel's "Underfunded public works" section shows the run's most stalled work, with
its stall causes, funding and the asset's failure. Worlds that show one:

- **Development world (the viewer's fixture):** template seed 11, 200 turns, repair with L9:

      PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 python -m chronicler.main --seed 11 --turns 200 --agents hybrid \
        --simulate-only --grain-reserves --grain-storage --repair-projects --local-budgets \
        --maintenance-obligation --infrastructure-condition --output OUT/chronicle.md --state OUT/state.json

  Its works never win an envelope and never progress; six irrigation and road assets fail by turn
  190 (`viewer/src/__fixtures__/infrastructure_records.json` keeps 12 of its snapshots).
- **Pilot worlds (never evidence):** arm C on template 5 (7 works stalled 20+ turns on failed assets)
  and procedural 19 (23), reproducible with `run OUT --screen CW3b --cohort pilot --arms C`.

## Amendments

None.
