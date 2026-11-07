# Connected-world CW5c: preregistered held screen for bounded epidemic care capacity (slice C2)

Status: DRAFT, revision 2, for the lead's review (not frozen; no held run is allowed until the lead marks this page FROZEN after an independent review of the code and this page)

Written 2026-11-07 by the C2 lane on branch `claude/cw-c2-care` (from `main` `bac45cb5`, PR #90).
Revision 1 was reviewed at `3e5ee44d` ("approve with changes"); revision 2 answers that review
(below). Native extension: the shared build of `main`'s Rust (`~/.venvs/native-a3`), SHA-256
`20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca`; this branch changes no Rust.
No held seed (template 3301-3306, procedural 3401-3406) has been run. Code may change before the
held run only to fix a defect, recorded as an amendment below with a new pilot; no arm, outcome,
definition or parameter changes in response to held outcomes.

Compute ceiling: 0.50 core-hours

Primary outcomes: cw5c_world_death_rate, cw5c_itt_cfr, cw5c_world_dpi

## Pre-freeze revisions (revision 2, before any held run)

Each with its reason (independent review of `3e5ee44d`, finding numbers in brackets; the lead's
decisions of 2026-11-07):

1. **Primaries replaced [M1].** Revision 1 had two primaries read on each arm's own covered
   region-turns. Coverage is about 1 by construction (Phase 2 sizes the carers from the same
   tick coverage is measured against), so those two mostly returned the declared constant, on a
   set the treatment changes (more covered region-turns under care), and deaths per new
   infection moves with an outbreak's phase. The primaries are now unconditioned or read on the
   cost-only arm's cells; the own-covered ratio is a mechanism check; reach and attenuation are
   reported.
2. **Care funded by one envelope per civ [m1]:** the per-region envelopes reserved at least one
   coin each (390 coins awarded against 74 paid on one development world). Awarded, executed and
   paid coins, and other services' coins, are in the harm panel.
3. **A wage bill is quoted at payment before any income is withheld [m2];** a refused bill pays
   and withholds nobody of that civ and gives no capacity. Refused bills are in the harm panel.
4. **Harm panel completed [m3, m6]:** EC wages, withheld income and refused bills; carer-turns
   held from drafting and academy teaching (registry holders are skipped by both: part of care's
   cost, in EC - E0); famine EF - EC; other services' coins EF - EC; migration EC - E0; care coins
   executed but unpaid.
5. **Extractor checks [m5]:** covered region-turns, wages, envelope coins and unpaid farm time
   against the lifetime counters; the tick's per-region deaths against `epidemics.deaths`.
6. **Compute ceiling 0.50 core-hours [n9].**

## Purpose and limits

C2 (`--epidemic-care`, [integration page](../../integration/epidemic-care.md)) lets each ruler
fund, from its L9 local budget, named carers (adult farmers who hold no other work) for the
regions with a reported outbreak; their farm time leaves farming, their income share is withheld
and replaced by a wage, and the patients they can serve, as dated capacity, multiply case
fatality at the **next** epidemic tick by `1 - 0.3 x coverage` (one floor with practised
medicine). The epidemic model still draws every death.

**The effect size is a declared constant** (0.3 at full coverage; coverage is about 1 wherever
care is staffed). The screen does not test whether nursing works. It measures **how much of the
constant survives** the dated chain (an outbreak reported at T is funded at Phase 10 of T, staffed
in Phase 2 of T + 1 and protected at the tick of T + 2), the budget (care competes in L9 with
relief and the other services) and the labour, **what that costs** (farm time, food, the budget it
takes from other services, treasury, stability, unrest, population), and whether the mechanism
does what it declares (the mechanism check).

- A bounded screen on default-off experimental source, not qualification. The 200-seed and
  procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.
- Six worlds per stratum support means, ranges, sign counts and the exact sign-flip
  enumeration, not significance tests.
- Hybrid worlds only (C2 refuses other modes). L9 (`--local-budgets`, with `--grain-reserves`)
  is in every arm, so the control funds the same other services from the same one budget.
- EF and EC are identical until care first changes a tick (`tests/test_epidemic_care_native.py`
  checks this on a development world); afterwards trajectories diverge, so every measure after
  the first effect is a property of the whole trajectory.
- Carers hold registry work, so that turn they are neither drafted by campaigns nor taught by
  academies. This is identical in EC and EF (EF - EC stays clean) and part of the cost in EC - E0.
- **Prediction (inferred, not tested here):** the world death rate and world deaths per
  infectious person-turn lower under EF than EC, by much less than 30 %: reach (the share of
  epidemic deaths in region-turns care can cover) is partial and care arrives two ticks after a
  report; the ITT fatality at EC's cells lower under EF; more food shortfall and famine under EF
  (more survivors to feed). A null result is a result.

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
- **Runner:** `scripts/connected_world_screens.py` on `scripts/screen_runner.py` (revision 2 adds
  `Outcome.pair`, a reading of both rows of one world, for primary 2). Command, once the lead
  freezes this page: `<native python> scripts/connected_world_screens.py run OUT --screen CW5c
  --cohort held --pilot docs/superpowers/progress/connected-world-screens-cw5c/pilot/metrics.jsonl
  --jobs 2`, then `report`, `check --metrics ... --cohort held` and `mark-run`.
- **Identity:** the pilot's `source.txt` (`connected-world-screens-cw5c/pilot/source.txt`, lines
  quoted under "Extractor validation"). A held run needs that screen module, runner and source
  byte for byte; any later change needs a new pilot and an amendment.

## Activation (reported per world before any effect)

- **EC, EF:** activated when care capacity reached an epidemic tick with infectious people at
  least once (a tick row with coverage > 0: a covered region-turn); unknown when the care record
  is missing.
- **E0:** the root (the runner does not judge it); it has no care by rule.
- `control_activation`: EF - EC needs both activated; a world where either did not act is shown
  as `not activated` and left out of that comparison's summaries, never counted as zero.
- Reported beside it per run: region-turns with a reported outbreak, envelopes, staffed region
  envelopes, carers named, region-turns with capacity, covered region-turns.

## Definitions

World turn w is recorded by the snapshot labelled w + 1 (`source_turn` w). Its care `tick` is the
epidemic tick of w, which applied the capacity of the carers named in Phase 2 of w - 1.

- **Cell:** a region-turn (w, j).
- **Infectious person-turns** of a cell: the tick's mean infectious people, the sum over
  pathogens of `burden x n` after the tick (`tick.regions[*].infectious_pt`, recorded for every
  infected region in both care arms, covered or not). **Deaths** of a cell: the region's epidemic
  deaths in that tick (`tick.regions[*].deaths`; they sum to `epidemics.deaths`, checked).
- **Fatality per infectious person-turn** over a set of cells: sum of deaths / sum of infectious
  person-turns (a pooled ratio). Its expectation is about `SUBSTEPS x recovery x case
  fatality`, so, unlike deaths per new infection, it does not move with an outbreak's phase. A
  cell the arm did not infect counts zero of both.
- **EC's covered cells:** the cells where EC's tick applied capacity with coverage > 0.
- **Person-turns:** `regional_population.counts` (end of turn), summed over regions and turns.
  **World death rate:** 1,000 x world epidemic deaths (`epidemics.deaths` summed; equal to the last
  `deaths_total`, checked) / world person-turns.
- **Continuing-outbreak region-turn** (every arm): a region with a reported outbreak
  (`epidemics.active`) at this snapshot and the one before.
- **Dearth / famine region-turns:** `food_accounting.regions[*].sufficiency_after_relief` below 1
  / below 0.6 (`ecology.FAMINE_SEVERE_SUFFICIENCY`).
- **L9 coins** to a service: the awards of every decision, by the service of the awarded
  proposal; "every other service" is all but `epidemic_care`. **Care coins executed:** the care
  envelopes C2 spent from (ledger `envelope_coins`); **unspent:** executed minus wages paid.
- **Farm time removed, wages, withheld income, refused bills, carer-turns:** sums of the care
  frames and ledgers, checked against the lifetime counters.

## Primary outcomes (EF - EC on each world)

1. `cw5c_world_death_rate`: world epidemic deaths per 1,000 world person-turns, whole run.
2. `cw5c_itt_cfr`: epidemic deaths per infectious person-turn over **EC's covered cells**, read at
   the same cells in both arms (intention to treat). Why: the cost-only arm makes the same budget
   and staffing decisions by the same rules (identical to EF until care first changes a tick) but
   carries no treatment effect, so its cells are not chosen by care's effect on EF's outbreaks;
   reading EF at those (turn, region) cells compares fatality where care was offered, whether or
   not EF covered exactly the same cells later. Per infectious person-turn rather than per new
   infection, for the phase reason above. It still reads only the covered part of the world (the
   mechanism's reach is reported separately).
3. `cw5c_world_dpi`: world epidemic deaths per infectious person-turn (all infected cells of the
   run), whole run: unconditioned, and free of the population denominator's own response.

## Mechanism check (reported per world; not evidence that care works)

The EF/EC ratio of fatality per infectious person-turn in **each arm's own** covered cells
(`covered_dpi`), beside EF's mean applied care factor in its covered cells (`combined /
techniques`, i.e. `1 - 0.3 x coverage` under the one floor) and its floored count. The ratio
should sit near the factor (integer death draws add noise). Outcomes `cw5c_mech_covered_dpi`
(EF - EC) and `cw5c_mech_factor` (EF), and the report's ratio table.

## Reach and attenuation (reported per world)

- **Reach:** the share of EC's epidemic deaths in EC's covered cells (`cw5c_reach`).
- **Implied maximum fall** of world deaths: reach x (1 - EF's mean applied factor), if care cut
  every covered death by that factor and nothing else changed.
- **Realized change:** (EF - EC) / EC of the world death rate. The report prints the three per
  world; attenuation is the gap between the implied maximum and the realized change.

## Secondary outcomes

| Id | Measure | Comparison |
| --- | --- | --- |
| `cw5c_world_deaths` | world epidemic deaths, count | EF - EC |
| `cw5c_world_death_rate_vs_none` | world epidemic deaths per 1,000 person-turns | EF - E0 |
| `cw5c_cost_world_death_rate` | world epidemic deaths per 1,000 person-turns (the cost's effect) | EC - E0 |
| `cw5c_continuing_deaths_per_case` | deaths per new infection in continuing-outbreak region-turns | EF - EC |
| `cw5c_continuing_deaths_per_case_vs_none` | the same | EF - E0 |
| `cw5c_covered_region_turns` | covered region-turns (selection) | EF - EC |
| `cw5c_mean_coverage` | mean coverage over region-turns with capacity | EF alone |
| `cw5c_mech_covered_dpi`, `cw5c_mech_factor`, `cw5c_reach` | mechanism check and reach (above) | EF - EC, EF, EC |

## Harm panel

The runner's fixed panel (population, treasury, food shortfall after relief, priced-out persons and
children (not recorded: household retail off), famine and war deaths ("requires slice extractor"),
epidemic deaths, out-migration, wealth Gini, forest stand (not recorded: timber stock off)) beside
each arm against its declared control (EF - EC, EC - E0); plus, as outcomes:

| Id | Harm | Comparison |
| --- | --- | --- |
| `cw5c_h_farm_time`, `_cost` | carer farm time removed (worker-turns) | EF, EC |
| `cw5c_h_carers_held`, `_cost` | carer-turns held from drafting and academy teaching | EF, EC |
| `cw5c_h_wages`, `_cost` | care wages paid (treasury units) | EF, EC |
| `cw5c_h_income_withheld`, `_cost` | carers' ordinary income withheld (wealth units) | EF, EC |
| `cw5c_h_unpaid_bills`, `_cost` | care wage bills refused at payment | EF, EC |
| `cw5c_h_food_shortfall` / `_cost` | food shortfall after relief over the run | EF - EC / EC - E0 |
| `cw5c_h_dearth`, `cw5c_h_famine` | dearth / famine region-turns | EC - E0 |
| `cw5c_h_dearth_care`, `cw5c_h_famine_care` | dearth / famine region-turns (more survivors to feed) | EF - EC |
| `cw5c_h_care_coins`, `_cost` | L9 coins awarded to care envelopes | EF, EC |
| `cw5c_h_care_coins_unspent` | care envelope coins executed but not paid out as wages | EC |
| `cw5c_h_other_coins` / `_care` | L9 coins awarded to every other service (displacement within the one budget) | EC - E0 / EF - EC |
| `cw5c_h_relief_coins` | L9 coins awarded to granary relief | EC - E0 |
| `cw5c_h_treasury` / `_care` | treasury at the end | EC - E0 / EF - EC |
| `cw5c_h_stability` / `_care` | mean civ stability over civ-turns | EC - E0 / EF - EC |
| `cw5c_h_unrest` / `_care` | mean city unrest over city-turns | EC - E0 / EF - EC |
| `cw5c_h_population` / `_cost` | population at the end | EF - EC / EC - E0 |
| `cw5c_h_migration` / `_cost` | agents moving between regions over the run | EF - EC / EC - E0 |

Households priced out are not measured (household retail is off in every arm).

**Structural zeros versus unknowns.** Care measures are `None` in E0 (not recorded), never zero. A
missing epidemics, local-budgets, regional-population or care record, a care record of another
mode, a tick, its regions or a frame that was not observed (null) in a care arm, a covered row
without deaths or infectious person-turns, tick deaths that differ from `epidemics.deaths`, a frame
sum that disagrees with its lifetime counter, or any capacity refused or left unconsumed (never
expected in a natural run) is a missing outcome: the run fails (rc 3) and is reported as failed.

## Analysis

Per stratum and outcome: each world's arm-minus-control value, the mean, range, sign counts and
the exact sign-flip enumeration over the activated worlds (`screen_runner` report), then the
mechanism and reach tables. The activation table comes first. No pooling across strata, no
significance test, no tuning; the pilot never enters the evidence. A primary is reported as a
direction only when its sign is the same in at least 5 of 6 activated worlds of a stratum
(otherwise "mixed" or "null"); the harms are reported beside it whatever their sign.

## Failure handling

- A run that fails (rc != 0 or a missing outcome) is reported as failed and left out of that
  world's comparisons; it is never rerun on the held cohort with changed code. An infrastructure
  failure (disk, killed process) may be resumed with `--resume` on the same source and identity.
- A defect found during the held run stops it; the fix is an amendment with a new pilot, and the
  held run starts again on the reserve cohort only if the lead assigns one (the held cohort is
  then recorded as used).
- The compute ceiling (0.50 core-hours) stops the run if reached.

## Extractor validation (pilot and development worlds, before any held run)

PENDING-PILOT

## C2 verification (commands and results)

PENDING-VERIFICATION
