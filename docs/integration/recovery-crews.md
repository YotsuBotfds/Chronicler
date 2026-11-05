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
for work nobody can do). With no free adult farmer at all the project stalls
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
  under the civ they served), of any non-enlisted occupation. Admission uses
  RS3's eligibility in both RS3 modes; `record_only` only removes the order.

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

## API for woodcutting (PL1)

`recovery_crews.eligible_ids(world, region, kind, *, sim, snapshot=None,
priority=None) -> list[int]`: stable ids eligible now for a recovery crew of
`kind` (`"granary"`, `"workshop"` or `"woodcut"`) in `region`, in crew order.
Everyone listed is a living adult resident of the region holding no work this
turn, not on a trip, not enlisted and not a seated mentor. `granary`: adult
farmers. `workshop` and `woodcut`: adult farmers and, while `--recovery-crews`
is active, RS3's eligible veterans of any non-enlisted occupation. Order:
`priority` (default: the region's `priority_ids`), then ascending id. It only
reads; the caller reserves (`reserve_work`, all or none). PL1 wages under
`repair_wage` need a transfer batch other than 0 (RS2 workshops) and 1
(granary crews).

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

No viewer reader exists yet (PL5).

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

See the evidence section of [maintenance-obligation.md](maintenance-obligation.md)
for the shared development screens, and below for the tests.

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
  crews (and woodcutting through `eligible_ids`), not granary crews, because
  granary labour is farm labour.
- A non-farming veteran's repair time is not taken from any production; only
  their income share is withheld.
- RS2's L9 proposal still sizes granary work without the crew, so an envelope
  can promise work the free adult farmers cannot do (settled `work_short`).
- Granary wages are 2 coins per worked turn against RS2's workshop wage of 0.5;
  both are declared rates carried over from the packages, not calibrated.
- Development worlds only; nothing here was run on held seeds or through the
  200-seed gate.
