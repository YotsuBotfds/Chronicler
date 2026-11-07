# Connected-world CW3b: preregistered held screen for infrastructure condition and repair (slice B3)

Status: FROZEN. Frozen by the lead on 2026-11-07 after independent review of the design, extractors and revisions (review record in the program's review notes); code at `dbfcd84ac802644f3c7ccf7c2bfba3ff9c661c1c`; pilot at `dbfcd84ac802644f3c7ccf7c2bfba3ff9c661c1c` (clean tree).

Written 2026-11-07 by the B3 lane on branch `claude/cw-b3-infrastructure` (main bac45cb5 merged;
B3 reviewed and approved at `10d73230`; the flow x condition integration at `c5593e81`, approved at
`453d307c`; the screen declared at `80966420` and revised before any freeze at `7364c643`; the
works' timber need connected to PL1 at `733e5e08`/`9daaec56`, the screen revised again at
`d5834d07`, and the review's fixes at `dbfcd84a`, on which the timing pilot below ran, clean tree;
the revisions are listed at the end). Native extension `20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca`
(`~/.venvs/native-a3`, built from main's Rust). No held seed (template 3501-3506, procedural
3601-3606) has been run. Code may change before the held run only to fix a defect, recorded as an
amendment below with a new pilot; no arm, outcome, region set or parameter changes in response to
held outcomes.

**The screen runs under PL1's real forest limits.** The works' timber comes only through PL1's
expeditions (a healthy forest within two hops that no other crew is cutting) and the stockpile, so
most of the works' timber requests are refused (`no_forest`, `forest_depleted`) and timber stalls
dominate the works; under L9 the works must also win their own envelope. **The L9 primaries are
therefore expected to measure mostly exposure (works opened) with little delivery: a null is a
null.** No code change after this freeze except a defect fix recorded as an amendment with a new
pilot.

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
  --grain-storage --repair-projects --timber-stock --timber-supply`. RS2 is a prerequisite of the
  repair modes and the repairs budget the works compete with. The timber stock (L3: a renewable,
  harvest-limited stock) and the timber supply (PL1: paid woodcutting expeditions feeding a store)
  give the works' materials a real supply, so the screen does not mostly measure timber starvation;
  their prerequisites (`--timber-supply` needs hybrid, `--repair-projects` and `--timber-stock`;
  `--timber-stock` an agent economy) are all in the base, so they alter no arm. PL1 serves RS2's
  needs first, then, in the repair arms (C, C_T), the open works' timber need under its own forest,
  crew, wage and reservation rules (integration page, section 5; revision 8); the delivered timber
  reaches the works through RS2's holds on the store. In R, W and W_T nothing of PL1 changes. Timber
  stalls stay a secondary. Every other switch at its default.
- **Arms** (root B):

  | Arm | Flags (added to the base) | Control | Role |
  | --- | --- | --- | --- |
  | B | `--local-budgets --maintenance-obligation` | — | the L9 + RS2 baseline without the switch |
  | R | B + `--infrastructure-condition --infrastructure-condition-mode record_only` | B | condition recorded, nothing changes (the measurement control; R - B is structurally 0) |
  | W | B + `--infrastructure-condition --infrastructure-condition-mode wear_only` | R | condition and service act, nothing repairs: every work refused (the underfunded counterfactual) |
  | C | B + `--infrastructure-condition` (repair) | W | works funded only through their own L9 proposal (irrigation works only: roads are not proposed and get no envelope) |
  | W_T | `--infrastructure-condition --infrastructure-condition-mode wear_only` | W | wear without L9 or the maintenance obligation |
  | C_T | `--infrastructure-condition` (repair) | W_T | works funded from the treasury alone (irrigation **and roads**) |

  The "works refused" counterfactual is `wear_only`: the switches allow it cleanly (the same wear,
  damage and consequences, no work opens), whereas refusing works inside the repair mode would need
  a new switch. W_T - W carries the removal of L9 (other services change too), so it is reported in
  the harm panel only, never as an effect of repair.

## Primary outcomes (arm - control on each world, after the pre-treatment snapshots)

Every primary reads only the snapshots after 28 (the pre-treatment snapshots are identical in the
two arms of a pair and would dilute it) and only worlds that pass the pre-treatment check in both
arms of the pair (below).

1. **`cw3b_service_l9`**: irrigation service maintained, C - W: the share of irrigation asset-turns
   (every serving or failed irrigation asset in every snapshot's record after 28) whose service
   `min(1, condition / 0.5)` is at least 0.5 (the gate at which irrigation still sets the native
   flag). Read from `condition_service`, which every mode records the same way.
2. **`cw3b_food_l9`**: food in the irrigated regions, C - W: the demand-weighted food shortfall share
   after relief (sum of demand x max(0, 1 - min(1, sufficiency after relief)) over sum of demand)
   over the snapshots after 28, in the regions holding an irrigation asset at snapshot 28.
3. **`cw3b_service_treasury`**: irrigation service maintained, C_T - W_T (the same measure as 1, the
   pair without L9).

**Snapshot 28** is the last pre-treatment snapshot: BUILD takes two turns, so an asset completes at
the earliest in turn 2; it wears 0.01 a turn, so its first wear work opens in Phase 10 of turn 27
and spends from turn 28, and no service is lost before 50 turns of wear; snapshot 28 records world
turn 27.

**Pre-treatment check (per world and arm, recorded):** at snapshot 28 no work has delivered work, no
work (open or closed, read from every record up to it, since the closed list keeps only 16) opened
by world turn 27, and every irrigation asset is at full service (`condition_service == 1`). The
irrigated-region set is recorded per arm (sorted region ids and a hash), and the report shows, per
world, each arm's check and whether C and W, and C_T and W_T, used the same set. **Rule:** a world
that fails the check in either arm of a pair is excluded from that pair's primaries (the reading is
missing, so the runner leaves the world out) and is reported, never imputed; it stays in the
full-trajectory secondaries. Passing the check in both arms implies the same set (the arms are
identical through snapshot 28); a world whose two arms nevertheless recorded different sets is
also excluded from that pair's primaries (the gated reading of the control is missing) and reported
in the pair table as "DIFFERENT SETS, excluded", and such a case would be a defect, fixed by
amendment.

**Activation (exposure, not success):** C and C_T are activated when a work opened on an irrigation
asset, whether or not it was ever funded or delivered work (delivered work is a secondary), so the
L9 primaries include worlds where the budget process never funds the works, which is the question.
W and W_T are activated when an irrigation asset-turn fell below full service; R when assets were
registered. A world with no irrigation asset is not activated for W, W_T, C and C_T (no extraction
failure).

## Secondary outcomes (shown, not primary)

Food in the irrigated regions C_T - W_T after snapshot 28 (**C_T also repairs roads, which C does
not**: the works' L9 proposal is irrigation-only, and roads without an envelope stall; so this
secondary mixes road repair into irrigation's effect); the full-trajectory versions of the three
primaries (every snapshot, every world); what wear alone costs (W - R: service, food); food met;
assets failed (C - W, C_T - W_T); works opened on irrigation assets, the works' delivered work (C,
C_T), L9 awards to the works' proposal (C), stall turns without an envelope and without timber (C,
C_T), the underfunded public works story count (C: works stalled 20 or more turns on an asset that
failed), the timber the woodcutters delivered (C), and the works' timber link: expeditions PL1
launched for the works' need (C, C_T), their woodcutter person-turns (C) and the works' need rows PL1
refused (C).

## Fixed harm panel (beside every comparison)

The runner's panel (population, treasury, food shortfall world-wide, out-migration, Gini, priced-out
and death rows "not recorded" where their system is off) for every arm against its control, and
these screen harms: **the L9 envelope displacement** (RS2 repair work delivered, C - W and C_T - W_T:
the integration page found the works' own proposal lowered RS2's and the works' delivery against
the pooled design, 53 -> 10 and 303 -> 191 work units on development worlds), **RS2's timber
displacement** (RS2 work-turns stalled without timber, C - W and C_T - W_T: forests and crews a
works' expedition still holds when RS2 next needs them; RS2 is served first within each turn),
**woodcutter time** (person-turns away from home over every expedition, C - W and C_T - W_T),
**farm time removed**
(the works' delivered work, C), **treasury** and **mean stability of living civs** at the end (C - W),
**coins destroyed** by the public-works sink (C, C_T), **food shortfall world-wide** and **population**
(C - W, C_T - W_T), the **timber stand** at the end (C - W), and R - B world food shortfall
(structurally 0: the record changes nothing).

## Activation (reported first, per world)

As defined above (exposure for C and C_T). B is not judged. A world where an arm did not act is "not
activated", never zero, and is left out of that arm's effect summaries (the runner's rule).

## Analysis plan

Per stratum: per-world values, mean, min/max, sign counts and the exact sign-flip enumeration of
the mean (the runner's report). The three primaries are read together: service maintained in each
pair, and food in the irrigated regions under L9. No pooling across strata, no significance test,
no adjustment of arms or outcomes after the held run. Harms are read beside every primary; a gain
in service bought with a world-wide food or population loss is reported as such.

## Compute ceiling (from the timing pilot)

Pilot at `dbfcd84a` (revision 9, clean tree), `--jobs 2`, 12 runs, 0 failed, every arm activated,
every world passing the pre-treatment check in every arm, each pair sharing its set (procedural
19's treasury pair has a larger set than its L9 pair, as those arms differ before snapshot 28), so
every pair is in the primaries; `check --screen CW3b --metrics ... --cohort pilot` passes (12 runs,
complete). 168 s of simulation and extraction (0.047 core-hours); per run, template 6.9-7.5 s and
procedural 17.2-19.7 s. The runner's projection for the held run (72 runs) is 0.280 core-hours,
x1.5 = 0.419, under the **ceiling of 0.50 core-hours** (the line above, read by the runner;
unchanged). Timber stalls dominate the works: arm C 1,232 (template 5) and 3,142 (procedural 19)
work-turns, C_T 1,307 and 2,445; PL1 launched 0 and 15 expeditions for the works in C (0 and 16 in
C_T) and refused 526 and 991 of the works' need rows in C. The works delivered 0 and 215.3 work
units in C and 36.9 and 372.6 in C_T. Pilot files: `connected-world-screens-cw3b/pilot/`
(`metrics.jsonl`, `source.txt`, `report.md`, copied from `/home/user/evidence/b3/cw3b/pilot3/`; a
documents-only change since `dbfcd84a`, so the runner's pilot check accepts them). Superseded
pilots (outside the repository): `d5834d07` (177 s, `--jobs 1`, projection 0.295 x1.5 = 0.442),
`7364c643` (165 s, `--jobs 2`, 0.275 x1.5 = 0.413) and `dda1be4b` (168 s).

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
- **Pilot worlds (never evidence):** arm C on template 5 (6 works stalled 20+ turns on failed assets)
  and procedural 19 (15 at `dbfcd84a`; 17 at `d5834d07`; 23 before revision 8), reproducible with
  `run OUT --screen CW3b --cohort pilot --arms C`.

## Pre-freeze revisions (before any freeze or held run; the lead's decisions on the delta review)

1. **Pre-treatment guard.** The first extractor read early war works from the last record's works and
   closed works only (closed keeps the last 16), so an early work closed before turn 200 was
   invisible. It now scans every record, and a direct snapshot-28 check (no delivery, no work opened
   by turn 27, every irrigation asset at full service) and the set's identity per arm are recorded;
   a world failing the check in either arm of a pair leaves that pair's primaries (reason: the
   primaries must compare pre-treatment-identical worlds).
2. **Activation is exposure.** C and C_T were activated by delivered work, a post-treatment success
   that would have dropped the worlds where L9 never funds the works from the L9 primaries; they are
   now activated when a work opened on an irrigation asset, and delivery is a secondary.
3. **No irrigation is not a failure.** A world without an irrigation asset reads None for the
   irrigation measures and is not activated, instead of failing the run.
4. **Primaries after snapshot 28.** The identical pre-treatment snapshots diluted the primaries; the
   full-trajectory versions are kept as secondaries.
5. **Roads in the treasury pair** are declared (C_T repairs roads, C does not).
6. **Timber supply in the base** (`--timber-stock --timber-supply`), so materials come from real
   supply rather than the screen measuring timber starvation (the development finding).
7. **Re-pilot** at the revised head, with the ceiling recomputed (below).
8. **The works' timber need enters PL1** (lead decision, 2026-11-07, after the `7364c643` pilot
   showed timber stalls dominating because PL1 served only RS2's needs). Reason: the owner's B3 text
   requires repair connected to real workers, materials and budgets through existing authorities,
   and a held screen that mostly measured a supply link B3 never made would waste the cohort. In the
   repair modes the open works' one-turn timber need enters PL1's planner after every RS2 need row
   of the turn, under PL1's forests, crews, wages and the one work reservation (no new labour
   authority, no free timber); `record_only`, `wear_only` and the switch off are unchanged (the
   identity record in the integration page). The screen gains secondaries (the works' expeditions,
   their woodcutter person-turns, refused need rows) and two harm rows (RS2 timber stalls and
   woodcutter time, each pair); the timber stall turns stay secondaries, RS2's delivery stays in the
   harm panel. Arms, primaries, cohort and parameters are unchanged; no constant was tuned. Re-pilot
   at `d5834d07`.
9. **The review's fixes** (delta review of `0187bfb5`, 2026-11-07), at `dbfcd84a`: (a) PL1 kept the
   store for every open work, so under L9 a road work (never funded) or a work in a region without
   a farmer held RS2's leftover store out of the stockpile; the store is now kept only where the
   works ask, by the need rows' own screen (a same-region test proves RS2 and PL1 equal the switch
   off). (b) PL1's `launched` counter stays RS2's and `launched_works` counts the works' launches
   (absent until one launches), so the screen's `pl1_launched` reads RS2's launches only and
   `pl1_works_launched` the works'. (c) The primaries are gated on the pair's irrigated-set identity
   too (above), so the report's "excluded" label is true. Re-pilot at `dbfcd84a` (above); the
   development re-measure moved only procedural 13 under L9 (integration page, section 8).

## Amendments

None.
