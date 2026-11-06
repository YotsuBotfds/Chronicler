# Recovery crews (PL3, `--recovery-crews`, default off)

Productive-recovery phase, package PL3
([phase plan](../superpowers/roadmaps/productive-recovery-phase.md), section 2,
"PL3"). Module `chronicler.recovery_crews`, state
`chronicler.recovery_crews_state`; the crew sections of
`chronicler.repair_projects` call it. Nothing here is calibrated or
scientifically qualified.

Enable with `--agents hybrid --repair-projects --recovery-crews`.
`--recovery-crew-mode` chooses `paid` (the default) or `unpaid`, the control.
A world that never enabled the switch has no sub-state, snapshot key,
checkpoint flag or manifest entry, and RS2 runs exactly as without it.

## Why

Diagnosis D3 (plan section 1) found RS2's granary labour anonymous and unpaid:
95% of RS2's coins are granary material charges that leave the economy, and
the wage channels to households (L6a, RS2 workshop wages) are about 0.5% of
household food spending (D4). Workshop repair candidates had to be adult urban
farmers of the site's own city (about 3.3 per site, short on 70-78% of workshop
project-turns), and veterans rarely had an opening where they lived.

## Granary crews

**Before.** An open RS2 granary project writes its request into the native
`granary_work_requested` column. The native economy delivers
`min(request, farm labour)` farmer-equivalents and removes them from farming
(`economy.rs`: `headcount_labor = farmers x farm_labor_factor`, after rural
health work, then `delivered = min(requested, headcount_labor)`). Nobody is
named and nobody is paid; 2 coins per delivered unit (`COINS_PER_WORK`) are
charged to the controller's treasury and leave the economy.

**With crews.** RS2 first sizes the work it can fund and supply, as before:
`planned = min(GRANARY_WORK_PER_TURN, remaining scope, free timber, coins,
envelope)`. The crew is then named:

- **Who.** Living adults (age 20, native `AGE_ADULT`) whose occupation is
  farmer and who live in the granary's region, from the agent rows the economy
  reads. Excluded: anyone holding work this turn in the shared registry (L1
  crews, RS1 apprentices, L5 learners, RS2 workshop repairers planned earlier),
  rural health work (patients and carers of this turn's prepared rows), people
  on a merchant trip, the enlisted, and mentors RS1 seated.
- **Order.** RS3's priority veterans of the region first
  (`veteran_reintegration.priority_ids`, empty in `record_only`), then
  ascending stable id. Only farmers can be on a granary crew, because their
  time is farm labour.
- **How much.** Each member gives at most their own farm time: 1 for a rural
  farmer, `URBAN_FARM_LABOR[rank]` (0.8, 0.7 or 0.6) for an urban farmer of a
  city of the region, whose city has the rest; these are the shares the cities'
  `farm_labor_factor` already counts. Members are added until their farm time
  covers `planned`; the last one gives only the remainder. A share below
  `MIN_SHARE` (0.001) names nobody.
- **The native request** becomes `min(planned, crew farm time)`, f32-floored,
  and RS2 holds timber and plans coins only for it. Each member is reserved in
  the work registry under category `repair` for their share, all or none,
  before the native economy runs.

**Why the named crew and the aggregate removal agree.** The request never
exceeds what the named people farm, and they are part of the region's farm
labour: `farm labour = sum over all farmers of their farm time` (children,
people with other work, health losses and other crews included), and the
crew's farm time is a part of that sum. So `min(request, farm labour) =
request`: the native step delivers exactly the crew's work (to f32 rounding)
and removes exactly that much from farming. If it ever delivered less, each
member's worked share is scaled by `delivered / sum of shares`, never above
the reservation. Children and people already working elsewhere stay in the
native farm labour but are never on a crew.

**Fewer free farmers than the work.** The request shrinks to the crew, and
`no_labor` joins the RS2 receipt's limits (the timber and coins are not held
for work nobody can do). Only a real shortage counts: the receipt's `short`
is true when the free adult farmers ran out with at least `MIN_SHARE` of the
planned work left. A smaller remainder names nobody and counts as covered,
with no `no_labor`, no `granary_crew_short` and so no `work_short` settlement
of an L9 envelope (review C, 2026-11-06: it read as a shortage while free
farmers remained). With no free adult farmer at all the project stalls
`no_labor` and asks for nothing. Without crews the same region would have had
its work done by any farmers, children included, up to the farm labour; with
crews granary work can be lower where the free adult farmers are few.

**Withholding.** After the economy tick, each member's worked share is
installed with `extend_paid_work` (merged with RS2's workshop rows in one
install), so the next wealth phase withholds that share of their ordinary
income. The receipt reads the withheld income back from the shared paid-work
receipt (`income_replaced`).

**Pay (`paid`).** The coins RS2 charges for the delivered work,
`_coin_milli(delivered)` (2 coins per work unit, rounded up to the milli-unit,
the same number RS2 puts in its ledger), are paid to the members by stable id
through `AgentSimulator.transfer_wealth`, purpose 3 `repair_wage`, batch
`GRANARY_WAGE_BATCH` = 1 (RS2's workshop wages use batch 0 the same turn; a
key is applied once). They are split by worked share: floors, then the
remaining milli-units one each by the largest fractional part, then ascending
id. A wage the native wealth ceiling refuses stays a material sink, so the
treasury charge is the same in both modes.

**Control (`unpaid`).** The same crews, reservations, request, withheld share
and treasury charge; no transfer, and the whole coin cost leaves the economy as
before. `paid` against `unpaid` isolates the wage channel to households.

**Closure** (every receipt and civ ledger, checked when written; the strict
checks raise):

    coin_cost_milli == wages_milli + sunk_milli          (per receipt and civ)
    wages_milli + wage_residual_milli == wages_due_milli
    paid: wages_due_milli == coin_cost_milli (when work was delivered); unpaid: wages_due_milli == 0
    delivered <= requested <= planned;  0 <= worked <= share <= 1 per member

RS2's own receipts and ledger are unchanged in shape and closure: the granary
receipt keeps `crew = []` and no wage (the RS2 viewer reader requires it), its
`coin_cost_milli` is still the material charge, and the charge per civ is the
same. No money is created: the treasury pays `charged` as before, and of the
granary part, `wages_milli` reaches households and `sunk_milli` leaves.

## Workshop repair crews: the wider pool

RS2 drew a site's repair crew from the native crew planner: adult urban
farmers of the site's own city. With crews the pool is:

- every adult farmer resident in the site's region (rural, the site's city,
  other cities of the region), and
- every adult RS3 veteran resident there who is eligible under RS3's rules
  (open record, adult, within `ELIGIBLE_TURNS` of release, not on a roster,
  under the civ they served), of any non-enlisted occupation. Admission reads
  RS3's public `veteran_reintegration.eligible_ids(world, region)`, the same
  in both RS3 modes; `record_only` only removes the order (`priority_ids`).

The exclusions are those of the granary crews. The order is RS2's priority
list (qualified veterans, the qualified, veterans) and then ascending id, so
RS3 priority applies. Everything else is RS2's: at most `MAX_CREW` (4)
repairers, the site's diverted share `d` each, the qualified rate, the timber
and coin sizing, the wage `round(d x 500)` milli-units and the withheld share
`d` for every member.

Time accounting. An urban farmer of the site's city works time already
diverted from farming, as before. Any other farmer gives
`max(0, d - own diverted share)` of farm time (a rural farmer: `d`), which is
removed from the region's farm labour by lowering the `farm_labor_factor`
column (`factor -= removed / farmers`, applied before native health losses).
A veteran of another occupation gives time the economy does not count as
production; only the income share is withheld (a declared limit).

## API offered for woodcutting (PL1)

PL1 does not call this API today: it chooses its expedition crews with its
own rule. It is offered so that woodcutting can share the recovery-crew pool
(the lead may wire it at integration).

`recovery_crews.eligible_ids(world, region, kind, *, sim, snapshot=None,
priority=None) -> list[int]`: stable ids eligible now for a recovery crew of
`kind` (`"granary"`, `"workshop"` or `"woodcut"`) in `region`, in crew order.
Everyone listed is a living adult resident of the region holding no work this
turn, not on a trip, not enlisted and not a seated mentor. `granary`: adult
farmers. `workshop` and `woodcut`: adult farmers and, while `--recovery-crews`
is active, RS3's eligible veterans of any non-enlisted occupation. Order:
`priority` (default: the region's `priority_ids`), then ascending id. It only
reads; the caller reserves (`reserve_work`, all or none). Under
`repair_wage` RS2 workshop wages use transfer batch 0, granary crews 1 and
PL1's expeditions 2.

## Lifecycle and guards

1. Phase 2: the workshop seam names workshop repair crews (wider pool); RS2's
   `prepare_phase2` names and reserves each granary crew, sizes the request,
   lowers `farm_labor_factor` for non-city farm time and holds timber.
2. The native economy runs.
3. RS2's `finish_phase2` installs every paid share once, pays the workshop
   wages (batch 0) and the granary wages (batch 1), charges once, and stages
   one crew receipt per project; veterans who worked are noted
   `placed:repair` (granary crews with `site = None`).
4. The agent tick runs; the withheld income is read back.
5. Phase 10 commits the frame once (`last_settled_turn`) with its counters.

- A failed Phase 2 or agent tick commits no receipt and changes no counter
  (counters are staged with the frame); RS2 returns the timber and cancels the
  paid share. A turn left staged by a failed run is discarded and counted at
  the next turn (`turns_discarded`).
- Crews are re-planned from the live pool every turn: a member who dies,
  migrates or is drafted is simply not a candidate next turn. Deaths happen in
  the native tick, after the wages, so everyone paid was alive when they
  worked; drafts in Phase 5 skip registry holders.
- A rebuilt native pool (`on_pool_reset`) clears the frame, whose ids would
  name strangers; an exact checkpoint re-binds without a reset. Checkpoints are
  written at turn boundaries, when nothing is staged.

## Snapshot (`livelihoods.recovery_crews`, schema 1, stage `PL3`)

`{schema_version, stage, mode, source_turn, units, receipts, ledger,
rows_dropped, counters, parameters}`. `receipts` and `ledger` are the
completed source turn's (`null` when it had no settled Phase 2: unknown, not
zero). A receipt: `turn, pid, kind, region, payer, eligible,
eligible_site_city` (workshop: the eligible people who are urban farmers of
the site's city, the pool RS2 had), `planned, capacity, requested, delivered`
(granary), `members` (`agent_id, origin` of `site_city | urban_farmer |
rural_farmer | veteran`, `share, worked, farm_time, veteran, wage_due_milli,
wage_milli, wage_residual_milli, income_replaced`), `coin_cost_milli,
wages_due_milli, wages_milli, wage_residual_milli, sunk_milli,
farm_time_removed`. At most `MAX_FRAME_ROWS` (64) receipts per frame.

Viewer (PL5a): `viewer/src/lib/recoveryCrews.ts` (`readRecoveryCrews`) and the panel
`RecoveryCrews.tsx`. The reader checks the closure above for every receipt, member and
civ ledger (the ledger as the sum of the civ's granary crews while the frame is not
truncated), a person on at most one crew, farm time against the work done, and no wage in
`unpaid`. The panel shows wages paid against the coins that would otherwise be sunk.

## Declared constants (uncalibrated)

| Name | Value | Meaning |
| --- | --- | --- |
| `AGE_ADULT` | 20 | native adult age of crew members |
| `MIN_SHARE` | 0.001 | least share of a turn a granary crew names a person for |
| `GRANARY_WAGE_BATCH` | 1 | `transfer_wealth` batch of granary wages (purpose 3) |
| granary coins per work | 2 | grain storage's `COINS_PER_WORK`, unchanged |
| urban farm time | 0.8 / 0.7 / 0.6 | cities' `URBAN_FARM_LABOR` by rank, unchanged |

## Files and seams

- Owned: `recovery_crews.py`, `recovery_crews_state.py`, the tests.
- `repair_projects.py`, crew sections only (`before_crews`, the granary
  planning and the farm-time removal in `prepare_phase2`, the paid-share
  install, wages and receipts in `finish_phase2`); `_free_timber` and the
  timber holds are untouched.
- Registry (append-only): `livelihoods_state.LIVELIHOODS_SWITCHES` and field,
  `livelihoods` choices, arg keys, help and prerequisites, the choice field
  map, `feature_catalog.REQUIREMENTS`, `batch_manifest.SIMULATION_ARG_KEYS` and
  its omit-when-None tuple (pinned), `tests/test_batch_manifest.py` (pinned).

## Evidence

### Verification on this lane's source (2026-11-06)

- Focused offline: `PYTHONHASHSEED=0 python -m pytest -q tests/test_recovery_crews.py
  tests/test_maintenance_obligation.py`: 39 passed.
- Bounded offline lane (`scripts/run_python_oracle_checks.py`): it stops at the
  first failing chunk, a source witness of the pinned `batch_manifest.py`. Run
  to the end with a scratch copy that continues past failures: 55 of 61 chunks
  pass, 6,443 passed, 69 skipped, 7 failed; all 7 failures are the source
  witnesses (information, academy, household, crisis candidates, public grain
  shipments, livelihoods sprint x2) naming `src/chronicler/batch_manifest.py`,
  which wait for the lead's witness layer. Chunk `productive-recovery-pl3`:
  39 passed in 1.4 s of 110 s.
- Native (`~/.venvs/native-int`, extension `6c675042…`, `check_python_env.py
  --expect native` PASS, `PYTHONPATH=src`): `test_recovery_crews_native.py`,
  `test_repair_projects_native.py`, `test_veteran_reintegration_native.py`,
  `test_local_budgets_native.py`, `test_recovery_skills_native.py`,
  `test_livelihoods_closure_native.py`, `test_apprenticeship_native.py`,
  `test_livelihoods_work_authority_native.py`: 38 passed.
- `CHRONICLER_CHECK_RESOURCES=1` with every PL3 switch on (procedural 302,
  100 turns, the screen flags plus `--recovery-crews --local-budgets
  --maintenance-obligation`): completed.
- Feature-off identity against `bec63b5b`: see
  [maintenance-obligation.md](maintenance-obligation.md).

### Development screens

Development worlds only: template seeds 1, 3, 7, 9, 11, 23, 42 (8 regions,
4 civs) and procedural 32x10 seeds 7, 11, 13, 17, 31; 200 turns; native
extension `6c675042…`; `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1`; one process at a
time. Every arm used `--agents hybrid --simulate-only --grain-reserves
--public-grain-shipments --scholarship --techniques --academy-services
--grain-storage --workshops --repair-projects --apprenticeship
--veteran-reintegration` (`--apprenticeship` as in D3, so RS1 operating wear
gives workshop projects) plus the arm's flags. `pre` is the phase head
`bec63b5b` (exported with `git archive`) with the base flags; every other arm
is this lane. Sums over the worlds of each stratum (template / procedural).
Single worlds diverge once any spending differs, so these show where the
mechanisms act and what binds, not effect estimates. The "ghost" arms apply
D3's diagnostic in a scratch driver only (RS2 sees ample free timber; the
physical stock and the packed `stockpile_timber` column are restored after
RS2's Phase 2 and the returned timber removed after its settlement), to show
what binds once timber does not.

| Measure (template / procedural) | `pre` | base | `paid` | `unpaid` | ghost base | ghost `paid` |
| --- | --- | --- | --- | --- | --- | --- |
| Granary crew-turns (person-turns) | - | - | 651 (848) / 1,864 (2,680) | 564 (778) / 1,556 (2,490) | - | - |
| Granary wages to households (coins) | 0 | 0 | 815 / 3,070 | 0 (842 / 3,260 sunk) | 0 | 4,473 / 9,579 |
| RS2 workshop wages (coins) | 35 / 104 | 35 / 108 | 39 / 150 | 45 / 148 | | |
| Granary crew short of the planned work / no free adult farmer (turns) | - | - | 100 / 295; 94 / 323 | 352 / 361; 401 / 327 | - | 285 / 435; 52 / 100 |
| Income withheld for crew work (wealth) | 0 | 0 | 75 / 220 | 72 / 246 | | |
| Granary work delivered | 400 / 1,642 | 400 / 1,555 | 407 / 1,535 | 421 / 1,630 | 2,131 / 4,897 | 2,237 / 4,790 |
| Mean granary condition | 0.325 / 0.404 | 0.325 / 0.408 | 0.323 / 0.389 | 0.320 / 0.395 | 0.700 / 0.798 | 0.729 / 0.792 |
| Workshop repair: eligible per crew-turn, region pool / site-city part | - | - | 12.9 / 4.9; 10.2 / 2.9 | 10.2 / 3.1; 9.3 / 2.9 | | |
| Workshop crew members: site city / rural / veteran | - | - | 120 / 224 / 0; 343 / 879 / 42 | 104 / 266 / 2; 386 / 835 / 27 | | |
| Workshop stalls, primary `no_labor` / `no_timber` | 1,723 / 794; 1,757 / 761 | 1,712 / 806; 1,699 / 872 | 320 / 2,370; 219 / 2,009 | 281 / 2,455; 238 / 2,038 | 428 / -; 327 / - | 46 / -; 14 / - |
| Workshop work delivered | 34 / 102 | 34 / 105 | 40 / 157 | 44 / 159 | 245 / 277 | 334 / 387 |
| Mean workshop condition | 0.508 / 0.576 | 0.508 / 0.586 | 0.550 / 0.607 | 0.521 / 0.560 | 0.837 / 0.848 | 0.837 / 0.837 |
| RS3 `placed:repair` spells; people placed (any opening) | 6, 16 / 8, 28 | 6, 16 / 4, 27 | 16, 16 / 108, 84 | 21, 18 / 119, 84 | | |

- **Wages reach households.** Paid granary crews moved 815 (template) and
  3,070 (procedural) coins of granary charges to named farmers, against 35 and
  108 coins of RS2 workshop wages; with timber ample 4,473 and 9,579. In
  `unpaid` the same order of coins left the economy as a sink. The treasury
  charge is the granary cost in both modes (tested exactly offline; here the
  trajectories diverge after the first wage).
- **What binds granary crews.** Timber first, as in D1. Once timber is ample
  the crew is short of the planned work in 285 / 435 project-turns and absent
  in 52 / 100 (few free adult farmers in small regions), and granary work and
  condition stay close to the anonymous channel's (0.729 / 0.792 against
  0.700 / 0.798).
- **The wider workshop pool removes the labour limit.** Eligible people per
  workshop crew-turn rise from about 5 (template) and 3 (procedural) in the
  site's city to 13 and 10 in the region; primary `no_labor` workshop stalls
  fall from 1,712 to 320 and from 1,699 to 219 (ghost: 428 to 46, 327 to 14),
  and timber binds instead. Workshop work rises 34 to 40 and 105 to 157.
- **Veterans.** Repair placements of veterans rise from 6 to 16 (template) and
  4 to 108 (procedural); people placed in any opening from 27 to 84 in the
  procedural worlds (unchanged in template). 42 procedural workshop
  member-turns were veterans of non-farming occupations. RS3's own counts
  differ between arms because the trajectories do.

The budget arms (L9 alone, `reserve`, `reserve_only`) and the RS2 correction's
effect are in [maintenance-obligation.md](maintenance-obligation.md).

### Tests

- `tests/test_recovery_crews.py` (offline, chunk `productive-recovery-pl3`): a
  constructed world and a recording simulator whose storage channel delivers
  at most the farm labour (farmers x `farm_labor_factor`). Crews named,
  reserved (category 3) and withheld; wages equal the coins no longer sunk;
  `unpaid` has the identical charge, crews and withholding; the wage ceiling;
  no free adult farmer; registry holders, health work, trips and the enlisted
  excluded; veteran priority and the placement note; death, migration and
  enlistment between turns; controller change; failed economy and agent ticks;
  duplicate and stale receipts; pool reset; exact pickle; the wider workshop
  pool with veterans first and `record_only`; the farm-time removal; the
  woodcutting API; the RS2 `no_people` correction; prerequisites; feature off.
- `tests/test_recovery_crews_native.py` (real extension, shard 1): procedural
  32x10 seed 31, 60 turns, `CHRONICLER_CHECK_RESOURCES=1`: every granary crew
  member holds a category-3 reservation equal to their share and is a resident
  adult farmer; no registry conflicts; the native delivery equals the crew's
  request; every wage moves real wealth of a named person once (a repeated key
  is refused); wages equal the granary coins; every ledger closes; the
  `no_people` correction acts natively. Exact checkpoint resume at turn 39
  with an open granary project and a paid crew: history, world state and
  `state.json` are byte-identical.

## Limits

- Granary crews are farmers only: veterans of other occupations join workshop
  crews (and could join woodcutting through `eligible_ids`), not granary crews, because
  granary labour is farm labour.
- A non-farming veteran's repair time is not taken from any production; only
  their income share is withheld.
- RS2's L9 proposal still sizes granary work without the crew, so an envelope
  can promise work the free adult farmers cannot do (settled `work_short`).
- Granary wages are 2 coins per worked turn against RS2's workshop wage of 0.5;
  both are declared rates carried over from the packages, not calibrated.
- Development worlds only; nothing here was run on held seeds or through the
  200-seed gate.
