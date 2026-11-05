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

DEVSCREENS

## Limits

- The reservation follows RS2's planned charges at the decision's free
  timber; with timber short (as in every natural screen) it is small.
- `MAX_BUDGET_SHARE` is declared, not calibrated.
- The reservation is not bargained, so it carries no political response: a
  reservation RS2 cannot use is returned silently (counted).
- Development worlds only; nothing here was run on held seeds or through the
  200-seed gate.
