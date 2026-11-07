# Connected-world CW5c: preregistered held screen for bounded epidemic care capacity (slice C2)

Status: DRAFT for the lead's review (not frozen; no held run is allowed until the lead marks this page FROZEN after an independent review of the code and this page)

Written 2026-11-07 by the C2 lane on branch `claude/cw-c2-care` (from `main` `bac45cb5`, PR #90).
C2 at `fdb3128c` (mechanism, tests, layer `cwc2`, docs; the clean saved-world refusal at
`fd85d8a7`), viewer at `0686b40b`, the screen and its cohort declared at `8f855a29` (city unrest
added at `d472bbff`); the pilot below ran on `e4150456`, clean tree. Native extension: the shared build of `main`'s Rust
(`~/.venvs/native-a3`), SHA-256 `20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca`;
this branch changes no Rust. No held seed (template 3301-3306, procedural 3401-3406) has been
run. Code may change before the held run only to fix a defect, recorded as an amendment below
with a new pilot; no arm, outcome, definition or parameter changes in response to held outcomes.

Compute ceiling: 0.75 core-hours

Primary outcomes: cw5c_covered_cfr, cw5c_world_death_rate, cw5c_covered_death_rate

## Purpose and limits

C2 (`--epidemic-care`, [integration page](../../integration/epidemic-care.md)) lets each ruler
fund, from its L9 local budget, named carers (adult farmers who hold no other work) for a region
with a reported outbreak; their farm time leaves farming, their income share is withheld and
replaced by a wage, and the patients they can serve, as dated capacity, multiply case fatality at
the **next** epidemic tick by `1 - 0.3 x coverage` (one floor with practised medicine). The
epidemic model still draws every death. CW5c asks: does care change realized fatality and
epidemic mortality against the same carers, wages and farm time with no effect on fatality
(`cost_only`), and what does it cost (farm time, food, the budget it takes from other services,
treasury, stability, population)?

- A bounded screen on default-off experimental source, not qualification. The 200-seed and
  procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.
- Six worlds per stratum support means, ranges, sign counts and the exact sign-flip
  enumeration, not significance tests.
- Hybrid worlds only (C2 refuses other modes). L9 (`--local-budgets`, with `--grain-reserves`)
  is in every arm, so the control funds the same other services from the same one budget.
- EF and EC are identical until care first changes a tick (`tests/test_epidemic_care_native.py`
  checks this on a development world); afterwards trajectories diverge, so every measure after
  the first effect is a property of the whole trajectory, not a mechanism estimate. Primaries 1
  and 3 are read on each arm's **own** covered region-turns (a selection: which regions are
  covered follows each arm's outbreaks and budgets); primary 2 conditions on nothing. The
  continuing-outbreak secondaries are defined the same way in every arm, E0 included.
- The effect size is a declared modelling constant (0.3 at full coverage); the screen measures
  how much of it survives the dated chain (an outbreak reported at T is funded at Phase 10 of T,
  staffed in Phase 2 of T + 1 and protected at the tick of T + 2), the budget and the labour, and
  what it costs. **Prediction (inferred, not tested here):** lower deaths per new infection in
  covered region-turns under EF than EC; the world death rate lower but smaller, because care
  acts two ticks after a report and only where L9 funds it; more food shortfall under EF (more
  survivors to feed). A null result is a result.

## Units, cohorts and source

- **Units:** worlds (seeds). Every arm runs once on every world and is compared with its declared
  control on the same world, per stratum: template (8 regions, 4 civs) and procedural (32 regions,
  10 civs, `--worldgen procedural --regions 32 --civs 10`).
- **Held cohort (new, reserved for CW5c):** template 3301-3306, procedural 3401-3406
  (`scripts/seed_registry.json` entries `cw5c-held-t` and `cw5c-held-p`, status `reserved`).
  A repository search (`git grep` for each number as a seed: seed keys, `--seed` values, seed
  lists and ranges) found them nowhere as seeds (the only hits were treasury values in earlier
  metrics files and a source line range), and `check --screen CW5c` (the runner's `check_seeds`:
  the registry reservation, no other entry, no gate range, not 1000-1999, no development world,
  no duplicate, not run) passes. **Timing pilot:** the shared pilot, template 5 and procedural 19
  (never evidence).
- **Base flags (every arm):** `--turns 200 --agents hybrid --simulate-only --grain-reserves
  --local-budgets`; epidemiology and the contact ledger at their defaults (on for new worlds);
  `--local-budget-mode bargained` (default); every other switch at its default.
- **Arms** (one control chain EF -> EC -> E0; root E0):

  | Arm | Flags | Control |
  | --- | --- | --- |
  | E0 | none (epidemics with L9, no care) | root |
  | EC | `--epidemic-care --epidemic-care-mode cost_only` (the same carers, farm time, withheld income and wages; no effect on fatality) | E0 |
  | EF | `--epidemic-care` (mode `care`) | EC |

  A no-L9 reference is not run: it would measure L9 itself, not care.
- **Runner:** `scripts/connected_world_screens.py` on `scripts/screen_runner.py`. Command, once
  the lead freezes this page: `<native python> scripts/connected_world_screens.py run OUT --screen
  CW5c --cohort held --pilot docs/superpowers/progress/connected-world-screens-cw5c/pilot/metrics.jsonl
  --jobs 2`, then `report`, `check --metrics ... --cohort held` and `mark-run`.
- **Identity** (the extractor lives in the screen module): the pilot's `source.txt`
  (`connected-world-screens-cw5c/pilot/source.txt`): source `e4150456`, dirty 0;
  `scripts/connected_world_screens.py` SHA-256
  `6e54ee3ae52da70a90b224e72f73ed1f91f73187754db603e88088e54fb5bad9`; `scripts/screen_runner.py`
  `3463b5cb7bb46a96634e7cade8e76ca097005740f6f631e1ff852ab5181651b5`; registry content
  `fa4731ea0d40d3dc7b6c29521f51df4199c68454fcb04196b8e9b054033a3b59`; native `20e77f99…`. A held run
  needs this screen module byte for byte; any later change to it (or to the simulation source)
  needs a new pilot and an amendment.

## Activation (reported per world before any effect)

- **EC, EF:** activated when care capacity reached an epidemic tick with infectious people at
  least once (a tick row with coverage > 0: a covered region-turn); unknown when the care record
  is missing.
- **E0:** the root (the runner does not judge it); it has no care by rule.
- `control_activation`: EF - EC needs both activated; a world where either did not act is shown
  as `not activated` and left out of that comparison's summaries, never counted as zero.
- Reported beside it per run: snapshots and region-turns with a reported outbreak, envelopes,
  staffed envelopes, carers named, region-turns with capacity.

## Definitions

World turn w is recorded by the snapshot labelled w + 1 (`source_turn` w). Its care `tick` is the
epidemic tick of w, which applied the capacity of the carers named in Phase 2 of w - 1.

- **Covered region-turn** (EC, EF): a row of `livelihoods.epidemic_care.tick.applied` with
  coverage > 0 (capacity dated w - 1 met infectious people of the last tick). Its deaths are the
  region's epidemic deaths in that tick (all pathogens) and its new infections the region's new
  infections in that tick (`deaths`, `cases`, recorded after the tick; never null in a valid run).
- **Deaths per new infection** over a set of region-turns: the pooled ratio sum of deaths / sum of
  new infections (None without new infections).
- **Person-turns** of a region-turn: `regional_population.counts[region]` of the same snapshot
  (end of turn); world person-turns sum every region. **Death rate:** 1,000 x deaths / person-turns.
- **World epidemic deaths:** `epidemics.deaths` summed over snapshots (checked to equal the last
  `deaths_total`).
- **Continuing-outbreak region-turn** (every arm): a region with a reported outbreak
  (`epidemics.active`) at this snapshot and the one before; deaths and new infections are the
  region's reported rows of this snapshot.
- **Dearth / famine region-turns:** `food_accounting.regions[*].sufficiency_after_relief` below 1
  / below 0.6 (`ecology.FAMINE_SEVERE_SUFFICIENCY`).
- **L9 coins** to a service: the awards of every decision (`local_budgets.decisions[*].awards`),
  by the service of the awarded proposal; "every other service" is all but `epidemic_care`.
- **Farm time removed, wages, withheld income:** sums of the care frames (`farm_time_removed`,
  `wages_paid_milli / 1000`, carers' `income_withheld`), checked against the lifetime counters.

## Primary outcomes (EF - EC on each world)

1. `cw5c_covered_cfr`: deaths per new infection in covered region-turns (each arm's own).
2. `cw5c_world_death_rate`: world epidemic deaths per 1,000 world person-turns, whole run.
3. `cw5c_covered_death_rate`: epidemic deaths per 1,000 person-turns of covered region-turns
   (each arm's own).

## Secondary outcomes

| Id | Measure | Comparison |
| --- | --- | --- |
| `cw5c_itt_cfr` | deaths per new infection in continuing-outbreak region-turns (no conditioning on care) | EF - EC |
| `cw5c_itt_cfr_vs_none` | the same | EF - E0 |
| `cw5c_world_deaths` | world epidemic deaths, count | EF - EC |
| `cw5c_world_death_rate_vs_none` | world epidemic deaths per 1,000 person-turns | EF - E0 |
| `cw5c_cost_world_death_rate` | world epidemic deaths per 1,000 person-turns (the cost's effect) | EC - E0 |
| `cw5c_covered_region_turns` | covered region-turns (selection) | EF - EC |
| `cw5c_mean_coverage` | mean coverage over region-turns with capacity | EF alone |

## Harm panel

The runner's fixed panel (population, treasury, food shortfall after relief, priced-out persons and
children (not recorded: household retail off), famine and war deaths ("requires slice extractor"),
epidemic deaths, out-migration, wealth Gini, forest stand (not recorded: timber stock off)) beside
each arm against its declared control (EF - EC, EC - E0); plus, as secondary outcomes:

| Id | Harm | Comparison | Source |
| --- | --- | --- | --- |
| `cw5c_h_farm_time`, `cw5c_h_farm_time_cost` | carer farm time removed (worker-turns) | EF alone, EC alone | care frames |
| `cw5c_h_wages` | care wages paid (treasury units) | EF alone | care frames |
| `cw5c_h_income_withheld` | carers' ordinary income withheld (wealth units) | EF alone | care frames (paid-work receipt) |
| `cw5c_h_food_shortfall` / `_cost` | food shortfall after relief over the run | EF - EC / EC - E0 | harm panel |
| `cw5c_h_dearth`, `cw5c_h_famine` | dearth / famine region-turns | EC - E0 | food accounting |
| `cw5c_h_dearth_care` | dearth region-turns | EF - EC | food accounting |
| `cw5c_h_care_coins` | L9 coins awarded to care envelopes | EF alone | L9 decisions |
| `cw5c_h_other_coins` | L9 coins awarded to every other service (displacement within the one budget) | EC - E0 | L9 decisions |
| `cw5c_h_relief_coins` | L9 coins awarded to granary relief | EC - E0 | L9 decisions |
| `cw5c_h_treasury` / `_care` | treasury at the end | EC - E0 / EF - EC | harm panel |
| `cw5c_h_stability` / `_care` | mean civ stability over civ-turns | EC - E0 / EF - EC | `civ_stats` |
| `cw5c_h_population` / `_cost` | population at the end | EF - EC / EC - E0 | harm panel |
| `cw5c_h_migration` | agents moving between regions over the run | EF - EC | harm panel |

Households priced out are not measured (household retail is off in every arm: structurally not
recorded). Unrest: L9's own grievance response is in every arm; no separate unrest measure.

**Structural zeros versus unknowns.** Care measures are `None` in E0 (not recorded), never zero. A
missing epidemics, local-budgets, regional-population or care record, a care record of another
mode, a tick or frame that was not observed (null) in a care arm, a covered row without deaths or
new infections, a frame sum that disagrees with its lifetime counter, or any capacity refused at a
tick (stale or future: never expected in a natural run) is a missing outcome: the run fails
(rc 3) and is reported as failed.

## Analysis

Per stratum and outcome: each world's arm-minus-control value, the mean, range, sign counts and
the exact sign-flip enumeration over the activated worlds (`screen_runner` report). The
activation table comes first. No pooling across strata, no significance test, no tuning; the
pilot never enters the evidence. A primary is reported as a direction only when its sign is the
same in at least 5 of 6 activated worlds of a stratum (otherwise "mixed" or "null"); the harms are
reported beside it whatever their sign.

## Failure handling

- A run that fails (rc != 0 or a missing outcome) is reported as failed and left out of that
  world's comparisons; it is never rerun on the held cohort with changed code. An infrastructure
  failure (disk, killed process) may be resumed with `--resume` on the same source and identity.
- A defect found during the held run stops it; the fix is an amendment with a new pilot, and the
  held run starts again on the reserve cohort only if the lead assigns one (the held cohort is
  then recorded as used).
- The compute ceiling (0.75 core-hours) stops the run if reached.

## Extractor validation (pilot and development worlds, before any held run)

- **Timing pilot** (template 5, procedural 19; the runner deleted its bundles):
  `connected-world-screens-cw5c/pilot/` (metrics, report, source): 6 runs, 0 failed, 153 s of
  simulation and extraction (0.042 core-hours), 78 s wall on 2 jobs, under heavy shared load
  (load average 7-9 on 4 cores: other lanes' native build and identity runs). Seconds per run: E0
  p 39.5, t 9.6; EC p 40.2, t 11.0; EF p 33.0, t 11.5. Projection for the held run (36 runs): 0.255
  core-hours, x1.5 = 0.382; **ceiling 0.75** (about 2.9 x the projection: an earlier run of the
  same pilot under lighter load took 0.029 core-hours, so the projection itself varies about 1.5 x
  with the container's load).
- **The same pilot with bundles kept** (`--keep-first`, `/home/user/evidence/c2/cw5c/pilot-kept`;
  identical metrics, deterministic) and **development worlds** template 1 and 42, procedural 7 and
  13 (`--cohort dev --keep-first`, 200 turns, all three arms): an independent checker outside the
  repository (`/home/user/evidence/c2/cw5c/validate/validate_cw5c.py`, reading the raw bundles,
  never importing the screen module) recomputes the world death rate (and that per-turn deaths
  sum to `deaths_total`), L9 coins by service, and in care arms: every snapshot's record, mode and
  date; that each tick applies exactly the capacity the previous snapshot left (dated w - 1, same
  patients); coverage, the factor applied and the factor it would apply; deaths bounded by the
  world's; nothing refused; carers unique per turn; care time, farm time, patients and the wage
  rule; wages within the envelope; every frame spends an open care envelope of the previous
  snapshot (same commitment, amount, region and turn); the wage ledger's closure on the
  treasury; the covered region-turns, deaths per new infection and covered death rate against the
  extractor's values and the lifetime counter. Results: see "Validation results" below.
- `tests/test_cw5c_screen.py` covers the arms, the pooled ratios, continuing-outbreak
  region-turns, hunger and stability, activation per arm, and missing or inconsistent records.

## Validation results

- Pilot with bundles kept (source `e4150456`, clean; the same measures as the official pilot,
  wall time apart): **58,441 checks, 0 failures** (EC and EF activated on both worlds:
  procedural 19 EC 1,643 / EF 2,059 covered region-turns, template 5 EC 149 / EF 88).
- Development worlds template 1 and 42, procedural 7 and 13, all three arms (source `8f855a29`,
  the screen module before city unrest was added; the checker covers every other measure):
  12 runs, 0 failed; **114,384 checks, 0 failures**. EC and EF activated on all four worlds
  (132-2,008 covered region-turns per run). Development worlds are inspected freely and are never
  evidence; their outcome values are not reported here.
- `check --screen CW5c`: seeds OK, extractor, packages, 3 arms and 31 outcomes (3 primary): OK.

## C2 verification (commands and results)

All on this branch; native runs with `~/.venvs/native-a3` (extension `20e77f99...`, built from
`main`'s Rust; `check_python_env.py --expect native` PASS); the offline lane with the worktree's
`.venv` (`--expect no-native` PASS).

- **Focused tests:** `tests/test_epidemic_care.py` 39 passed offline and under the native venv;
  `tests/test_epidemic_care_native.py` 5 passed native (5 skipped offline): natural runs, `cost_only`
  identical to `care` until care first changes a tick, exact resume during an outbreak with carers
  and pending capacity, no double booking beside health care and PL3 crews, an explicit
  `--no-epidemic-care` on a new world changes nothing; `tests/test_cw5c_screen.py` 6 passed.
- **Affected suites under the native venv** (catalog, matrix, A1 ledger and native ledger, seam,
  manifest, D2 and native D2, C1 and native C1, screen runner, shards, L9 and native L9,
  epidemiology, A3 and native A3, PL3, health care, sprint witness, retail): 840 passed.
- **Offline lane** `python scripts/run_python_oracle_checks.py` on `120d8c46`: PASS, 71 chunks in
  264.1 s (an earlier run during development: 316.9 s); the new chunk `connected-world-c2` (45 tests)
  1.3 s of 110 s; slowest chunk `systems-2` 29.3 s.
- **Witness suites** (sprint with layer `cwc2` last, restoration, scenarios, information x2,
  academy, household mobility, crisis, food accounting, grain release, public grain shipments,
  regional population, health care policy, practice observer x2, native shards, preflight): 574
  passed, 61 subtests. `refactor_preflight.py --git-diff origin/main`: the only enforced source
  witnesses are `batch_manifest.py` and its test, both covered by `cwc2` (current digests match).
- **Feature-off identity** (`scripts/turn_speed_identity.py`, each side its own `git archive`
  source tree, the same extension): head (`fd85d8a7` source) against the original reference
  `8abc1acb` outputs: **9 cases, 399 files, 0 differences**; against the preceding `main`
  `bac45cb5`: **9 cases, 399 files, 0 differences** (and `bac45cb5` against `8abc1acb`: 0);
  with `--no-epidemiology` against the reference's `--no-epidemiology` outputs: **9 cases, 399
  files, 0 differences**. With L9 on (`--grain-reserves --local-budgets`, the four hybrid cases)
  head against `bac45cb5`: **4 cases, 327 files, 0 differences** (the appended provider changes no
  L9 decision while C2 is off). With `--wealth-accounting` (hybrid 42) head against `bac45cb5`:
  one declared difference, the A1 record's `parameters.channels` label list gains `care_wage`
  (12 channels, was 11); nothing else in 111 files differs.
- **Enabled exact resume** (`scripts/checkpoint_identity.py run --case hybrid_s42
  --cli-arg=--grain-reserves --cli-arg=--local-budgets --cli-arg=--epidemic-care`): **PASS, 59
  resume points, 21 files each, 0 differences**; writing checkpoints changes nothing (45 files).
  23 of the resume points (turns 14, 34-39, 41-46, 50-59) fall during a reported outbreak with
  carers named and capacity pending for the next tick.
- **Refusals:** a duplicate keyed wage bill is refused by the seam's book before any move, a
  second settlement or plan in one turn and a plan of another turn are refused, a stale or future
  capacity row is refused at the tick (`tests/test_epidemic_care.py`); a legacy state-file resume
  of a C2 world with `--agents off` exits with one line, `Error: --epidemic-care requires --agents
  hybrid; this world has it on: pass --no-epidemic-care to end it`, rc 1; in hybrid it continues
  (the rebuilt pool drops the frame's ids, the dated capacity stays).
- **Viewer** (`viewer/`, `npm test -- --maxWorkers=1`, on `f28ffabd`): 163 files, 1,612 passed, 2
  skipped; `npm run lint` clean; `npm run build` passes (after the type fix at `f6ce8727`).
- **Not run:** the 200-seed and procedural qualification gates (restricted); the CW5c held cohort
  (awaits the freeze); `cargo` builds and Rust tests (no Rust change); browser journeys of the care
  panel.
