# Maintenance obligation (PL3, `--maintenance-obligation`, default off)

Productive-recovery phase, package PL3
([phase plan](../superpowers/roadmaps/productive-recovery-phase.md), section 2,
"PL3"). Module `chronicler.maintenance_obligation`, state
`chronicler.maintenance_obligation_state`; L9 provider
`chronicler.maintenance_obligation:BUDGET_PROVIDER`. Nothing here is calibrated
or scientifically qualified.

Enable with `--local-budgets --repair-projects --maintenance-obligation` (L9
itself needs `--agents hybrid` and `--grain-reserves`).
`--maintenance-obligation-mode` chooses `reserve` (the default) or
`reserve_only`, the crowding-out control. A world that never enabled the
switch has no sub-state, snapshot key, checkpoint flag or manifest entry; the
appended provider then reserves nothing and L9's decisions are unchanged
(tested).

## Why

D3 found that with L9 the repairs envelope binds (`no_envelope` on 88-93% of
RS2 stalls), and that the cause is valuation, not the budget's size. L9 awards
an envelope only for a constituency's measured burden: an empty granary, or a
workshop still above the 0.5 operating gate, relieves nothing, so 64-67% of
repairs proposals are refused `no_support` (`repair_projects.budget_proposal`;
`local_budgets._bargain` and `_greedy`). L9 values maintenance only after
failure.

## Mechanism

**Decision (Phase 10 of turn T, for T+1).** L9's `_decide` reserves each
provider's `obligations` first. A provider with `capped_obligation` (this
package) then reserves after all of them, given the budget the civ would have
without it:

    budget_before = floor(envelope_share x max(0, projected - floor - other obligations - committed))
    reserved      = min(planned, floor(MAX_BUDGET_SHARE x budget_before))

`planned` is RS2's planned per-turn charges for the civ's open projects in
whole units: the cost of RS2's own full `repairs` proposal at the same dated
observations (`repair_projects.planned_cost`), so granary work is sized by the
per-turn cap, the remaining scope and the free timber, and workshop work by
the timber-supported crew, exactly as the proposal sizes it. A granary project
suspended for `no_people` is not planned. The reservation is recorded where
L9 records every obligation, `Decision.reserved["maintenance"]`, and reduces
the disposable treasury the budget is drawn from:
`budget = floor(envelope_share x (projected - floor - obligations - committed))`.

- **`reserve`.** RS2's `repairs` proposal asks only for the part beyond the
  reservation: cost `planned - reserved`, with its expected work and each
  constituency's relief scaled by the unreserved share (L9 already treats the
  proposal as divisible and pro rata). No proposal remains when the
  reservation covers the planned charges.
- **`reserve_only`.** The same reservation and therefore the same smaller
  budget for every bargained service; RS2 keeps its full proposal.

**Execution (Phase 2 of T+1).** RS2 spends within its limit
(`repair_projects._envelope`): in `reserve` mode the bargained envelope plus
the reservation (`maintenance_obligation.repairs_limit`), in `reserve_only` the
envelope alone. After RS2's single charge per civ, this package splits it:
the reservation pays first, the envelope the rest.

**Settlement (Phase 10 of T+1).** L9 settles the repairs envelope from RS2's
receipts as before, but with the envelope's own part: `spent = charged - used`
and `delivered = work x spent / charged` (`repair_projects.budget_settlement`,
which records `reservation_used` in the detail). L9's own closure
(`spent <= amount`) and its kept and deferred rules, deferral events and
grievance response therefore apply to the promise only. The reservation is an
obligation, not a promise: it has no sponsor, no venue and moves no grievance.

**Return.** The part of a reservation RS2 did not use (all of it in
`reserve_only`) is returned: those coins were never budgeted and never left
the treasury.

## Closure

Every civ with a reservation or a repair charge has one row per turn
(`ReservationUse`, checked when it is written):

    reserved == used + returned
    used + envelope_spent == charged          (RS2's whole-unit charge to the civ)
    envelope_spent <= envelope                (with an envelope)
    reserve_only: used == 0, returned == reserved

RS2's own check (`charged <= limit`) and the RS2 viewer reader's
(`charged <= envelope`) hold because RS2's receipts and ledger record the
limit as their `envelope` field in `reserve` mode; the split is in this
package's rows.

## Snapshot (`livelihoods.maintenance_obligation`, schema 1, stage `PL3`)

`{schema_version, stage, mode, source_turn, units, decisions, uses, counters,
parameters}`. `decisions` are the reservations decided in the source turn for
the next (`turn, civ, planned, budget_before, cap, reserved`); `uses` the
reservations used in the source turn (`turn, civ, reserved, envelope, charged,
used, returned, envelope_spent`). Each is `null` when that turn decided or
settled nothing (unknown, not zero). No viewer reader exists yet (PL5).

## Declared constants (uncalibrated)

| Name | Value | Meaning |
| --- | --- | --- |
| `MAX_BUDGET_SHARE` | 0.5 | largest share of the budget the civ would otherwise have that may be reserved |
| `GROUP` | `maintenance` | the L9 obligation key |

## Files and seams

- Owned: `maintenance_obligation.py`, `maintenance_obligation_state.py`, the tests.
- `local_budgets.py`, the obligations seam: the provider appended to
  `PROVIDERS`, and in `_decide` one loop that reads a provider's
  `capped_obligation` after every other obligation (`committed` is computed
  one line earlier; nothing else changes order).
- `repair_projects.py`: `_envelope` (the limit), `budget_proposal` (split into
  `_repairs_proposal`, `planned_cost` and the reservation adjustment) and
  `budget_settlement` (the envelope's part).

## Evidence

### Tests

`tests/test_maintenance_obligation.py` (offline, chunk `productive-recovery-pl3`):
the real L9 decision on the L9 test world with an open RS2 granary project
(L9 alone; the cap binding at half the budget; an uncapped reservation leaving
no proposal; `reserve_only` with the same reservation and the full proposal;
fixed shares; a `no_people` granary reserving nothing), and RS2's execution on
the recovery-crews test world (the reservation spent first and the envelope
settled for its part; `reserve_only` held to its envelope with the reservation
returned; a reservation without an envelope; an unspent reservation returned
when timber is short; closure refusals; a failed Phase 2; prerequisites;
feature-off identity of the decisions; exact pickle).

### Development screens (PL3 lane)

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

**RS2 correction.** `pre` against base: all 12 worlds have granary regions
that empty of farmers, so every RS2-on trajectory changes. In base the
correction left 700 (template) and 152 (procedural) asset-turns unopened
(`no_people`) and suspended open projects for 1,229 and 756 project-turns;
`pre` counted 6,061 / 9,534 stalled granary project-turns where base counts
5,371 / 9,455. Feature-off identity against `bec63b5b` held with RS2 off (template seed 11
and procedural seed 7, 60 turns, L9 on so the appended provider is consulted):
history, world state, `state.json` and `chronicle.md` equal.

**Budgets.** L9 alone (`l9`), `reserve` and `reserve_only`, natural and with
ample timber (ghost):

| Measure (template / procedural) | `l9` | `reserve` | `reserve_only` | ghost `l9` | ghost `reserve` | ghost `reserve_only` |
| --- | --- | --- | --- | --- | --- | --- |
| Repairs proposals; refused `no_support` | 1,211; 615 / 2,878; 1,335 | 190; 93 / 425; 349 | 1,167; 574 / 2,920; 1,400 | 3,536; 2,256 / 5,541; 3,283 | 551; 341 / 1,382; 822 | 3,238; 2,023 / 5,887; 3,456 |
| Repairs envelopes awarded (coins); spent | 970; 638 / 3,509; 2,798 | 44; 42 / 194; 175 | 1,019; 738 / 3,505; 2,811 | 5,523; 4,623 / 10,942; 9,836 | 234; 229 / 1,031; 957 | 5,278; 4,386 / 12,044; 10,635 |
| Reserved; used; returned (coins) | - | 1,048; 652; 396 / 3,094; 2,280; 814 | 2,855; 0; 2,855 / 7,552; 0; 7,552 | - | 6,406; 4,625; 1,781 / 11,885; 9,722; 2,163 | 16,389; 0; 16,389 / 29,769; 0; 29,769 |
| RS2 charged (coins) | 638 / 2,798 | 694 / 2,455 | 738 / 2,811 | 4,623 / 9,836 | 4,854 / 10,679 | 4,386 / 10,635 |
| Granary stalls, primary `no_envelope` | 214 / 452 | 31 / 94 | 246 / 487 | 2,162 / 3,345 | 283 / 840 | 1,877 / 3,990 |
| Mean granary condition | 0.279 / 0.355 | 0.307 / 0.372 | 0.287 / 0.362 | 0.586 / 0.707 | 0.688 / 0.784 | 0.586 / 0.708 |
| Other envelopes awarded: workshop; granary storage; relief (coins) | 3,447; 420; 42 / 3,156; 2,400; 329 | 3,039; 397; 67 / 3,150; 2,764; 366 | 3,615; 394; 55 / 2,982; 2,312; 426 | 4,584; 798; 217 / 3,844; 3,693; 539 | 4,243; 815; 226 / 4,678; 4,099; 477 | 4,860; 867; 196 / 3,567; 4,046; 480 |

Without L9 (the base column of [recovery-crews.md](recovery-crews.md)) mean
granary condition is 0.325 / 0.408, and 0.700 / 0.798 with ample timber.

- **The obligation removes most envelope stalls.** Primary `no_envelope`
  granary stalls fall by 86% / 79% naturally and 87% / 75% with ample timber,
  and granary condition recovers most of what L9 alone lost against no L9
  (ghost: 0.586 to 0.688 against 0.700; 0.707 to 0.784 against 0.798). Repairs
  proposals and `no_support` refusals fall because the reservation already
  covers the planned charges; what the bargained envelope still funds is small.
- **Timber still binds naturally**, so the reservation is small (1,048 /
  3,094 coins over 200 turns) and some of it is returned when the timber of the
  decision is not there at execution (396 / 814).
- **Crowding out is small.** `reserve_only` reserves more (its repairs spend
  only the envelope, so planned charges persist) and returns all of it; the
  budget each reservation removes from bargaining is a quarter of it
  (`envelope_share`), about 0.2% of the summed budgets, and the other services'
  awards move within the noise of diverging trajectories. Granary condition in
  `reserve_only` matches L9 alone (ghost 0.586 / 0.708), so the benefit in
  `reserve` is the reservation spent on repairs, not a side effect.

## Limits

- The reservation follows RS2's planned charges at the decision's free
  timber; with timber short (as in every natural screen) it is small.
- `MAX_BUDGET_SHARE` is declared, not calibrated.
- The reservation is not bargained, so it carries no political response: a
  reservation RS2 cannot use is returned silently (counted).
- Development worlds only; nothing here was run on held seeds or through the
  200-seed gate.
