# Workshop economics and the shared payment seam (A3, `--workshop-economics`)

Connected-world program, slice A3-1. Default off; requires `--workshop-payroll`
(so `--workshops` in operate mode and `--agents hybrid`). Design source: the A3
workshop-economics audit (sections 4-5) and the A1-A2 audit's payment seam
(section 3.3), with the lead's decisions. Code: `src/chronicler/money.py` (the
seam), `src/chronicler/workshop_economics.py` and
`src/chronicler/workshop_economics_state.py`; seams in `workshops.py` and
`workshop_payroll.py`; ledger channels in `wealth_accounting.py`. Tests:
`tests/test_money.py`, `tests/test_workshop_economics.py` (offline, chunk
`connected-world-a`) and `tests/test_workshop_economics_native.py` (compiled
extension, native shard 0).

## What it changes

Under L6a ([workshop finance](workshop-finance.md)) a workshop firm opens around
an academy order, converts the commons' raw timber and ore for free, and sells
only to academies; firm-less L1 sites keep producing into the commons. Under
A3:

- a firm opens once with **owner capital** and is never rescued;
- it **pays for its inputs** at the economy's own price, to the ruler who owns
  the commons they come from;
- it sells to **academies and to the region's households** (by stable id,
  adults paying);
- a site **without a firm produces nothing**, and a firm that cannot pay for
  any input does not operate (no free-input production under the switch);
- firms close when insolvent or **idle**; nothing guarantees survival.

## Switch, modes and refusals

| Mode (`--workshop-economics-mode`) | Inputs | Customers | Role |
| --- | --- | --- | --- |
| `market` (default) | bought from the ruler at the tick's raw price | academies, then households | the mechanism |
| `free_inputs` | planned and recorded (`not_charged_milli`), not charged; production not bounded by cash | academies, then households | cost control: the input charge alone |
| `academy_only` | bought | academies only | demand control: no household customers |

Any payroll mode is accepted: `--workshop-payroll-mode no_customer` is the
constructed demand collapse (nothing is sold to anyone), `unpaid_labor` the
labour control.

- Refused at startup outside `--agents hybrid`, without `--workshop-payroll`
  or with workshops not in operate mode; a saved world with it on is refused
  on a resume that ends payroll until `--no-workshop-economics` is given.
- An exact resume refuses adding or dropping it or changing its mode
  (`livelihoods_resume_conflicts`). On a non-exact (legacy) resume,
  `--no-workshop-economics` ends it with a dated `switched_off` record; open
  firms then continue under L6a's rules.
- Registered in `feature_catalog.REQUIREMENTS` (`--agents hybrid`,
  `--workshop-payroll`) and in `batch_manifest.SIMULATION_ARG_KEYS` (both keys
  omitted while unset; provisional witness layer `cwa3`).
- Inserted in `LIVELIHOODS_SWITCHES` **before** `wealth_accounting` (the
  ledger stays last). It registers **no hooks of its own**: the module defines
  no function named like a livelihoods hook; the workshop and payroll seams
  call it, so its effects run at payroll's position. No random draws.

## Who pays whom

Money in milli-units (1000 = one treasury unit = one unit of a person's
wealth); wares and raw inputs in milli-loads.

| Flow | Payer -> payee | When | Rule |
| --- | --- | --- | --- |
| Starting capital (`firm_capital`) | ruler's treasury -> firm cash | Phase 10, once per firm | declared constant `CAPITAL` = 20 units; refused (and retried a later turn) when the projected treasury is short |
| Input purchase (`firm_input_purchase`) | firm cash -> ruler's treasury (owner of the commons); `unowned_commons` sink if nobody rules the region | after the successful tick (Phase 2 finish) | `ceil(used x price)`, never above the reservation; sub-unit amounts carried to the treasury (`money`) |
| Asset build, upkeep, repair | ruler's treasury -> public expenditure sink (L1, unchanged) | Phase 2 finish | recorded per site as the owner's **asset subsidy**, outside the firm's books |
| Academy sale | ruler's treasury -> firm cash (L6a, unchanged) | Phase 10 | as L6a |
| Household wares purchase (`wares_purchase`, native purpose 7) | households' wealth (adults) -> firm cash | Phase 10, after academy sales | one collection of keyed debit rows per firm and turn |
| Wages, arrears | firm cash -> crew (L6a, unchanged) | Phase 10 | as L6a |
| Distribution, liquidation | firm cash -> ruler's treasury / sink (L6a) | Phase 10 or at closure | reserve kept: `RESERVE_TURNS` x (full wage bill + full input bill at the last positive raw price) |

The only credits to households remain wages (and L6a's crew pay). Capital,
input purchases and household spending are transfers between named accounts;
nothing is minted into firm cash.

## The price rule

**Inputs: the region's post-trade price of raw materials as the native
economy computes it in the tick of the purchase** (`market_price_raw_material`,
the tick that converts the inputs; timber and ore share the `raw_material`
category). It is never clamped, smoothed or invented; it is rounded **up** to
whole milli-units per load, so the buyer never pays less than the economy's
price. Because the firm's ceiling enters the region's raw demand, the price
includes the firm's own demand.

The purchase is reserved before the tick and settled after it:

1. **Budget** (Phase 2, workshop seam): cash less wages owed, this turn's wage
   bill for the planned crew and a 2-milli slack (`INPUT_SLACK`, for the f32
   ceiling's rounding). A budget of zero or less: the site does not operate
   (`budget_exhausted`).
2. **Plan**: at the **last positive raw price the economy computed for the
   region** (persisted; a turn without raw demand prices raw at 0 and does not
   overwrite it), the budget buys `floor(budget x 1000 / plan price)`
   milli-loads; the ceiling becomes `min(K x W, that)`, and the crew request is
   sized to the workers those inputs occupy (at least one, the native
   planner's floor). Before any positive price has been seen in the region
   (no raw demand there yet, which is the case at every firm's first turn
   because a firm-less site has no ceiling) the firm plans its full crew's
   ceiling: **price discovery**.
3. **Settle** (after the successful tick, payroll's title seam): the inputs
   actually used (native `craft_input` timber + ore) cost `ceil(used x tick
   price)`. If that is within the budget the firm pays it. If it exceeds the
   budget (the tick's price rose above the plan, or price discovery), the firm
   pays the **whole budget** and takes title only to the **paid share** of the
   output (`floor(output x budget / cost)`); the unpaid share of the
   conversion stays in the commons it was made from (`unpaid_conversion_milli`).
   No input is free to the firm, and the firm never pays more than it
   reserved. A failed tick charges nothing (as every Phase 2 bill).

**Wares sold to households: this tick's post-trade craft price**
(`market_price_craft`), rounded up per load. A household that wants `q`
milli-loads pays `ceil(q x price / 1000)`.

## The `money.py` seam

`quote(world, bill, ...)` validates and computes without moving anything;
`pay(...)` validates the **whole** bill and then moves it once.

- Accounts: `civ_treasury` (civ index), `firm_cash` (firm id), `agent_wealth`
  (stable id), `sink` (declared names: `unowned_commons`, `credit_refused`).
- A bill is a payment (one payer, many payee lines) or a collection (many
  paying agents, one payee). Amounts are positive whole milli-units;
  counterparties are unique; a treasury debit is whole units; a purpose without
  a native code never moves agent wealth; a treasury paying agents is refused
  (those packages keep their own prepaid rules).
- Coverage before any move: a treasury's projected budget
  (`mutual_aid._treasury_budget`, accumulator-aware), a firm's cash, each paying
  agent's `floor(wealth x 1000)` from one fresh snapshot read. A short or absent
  payer refuses the bill whole: nothing moves and nothing settles.
- **Exactly once**: a settled `(turn, purpose, batch)` is refused again (the
  book's persisted `settled` keys, the native key log's rule), also across exact
  checkpoint resumes.
- **Residuals**: a credit the wealth ceiling refuses, or one to an absent id,
  returns to the payer (`return_to_payer`) unless the bill names a declared sink
  (`sink:<name>`), which then records it. A collection has no residual: lines
  are limited to what each payer holds, and a line the native transfer does not
  apply in full is an error.
- **Treasury credits** below a whole unit are held as a persisted carry per
  civilization and purpose and paid in whole units as they accumulate (nothing
  rounded away, nothing created).
- **Native purposes** are checked against `wealth_transfer_purposes()` before
  use: an extension without `wares_purchase` at code 7 is refused with a clear
  message.
- **Register**: every applied line is a typed `MoneyFlow` in the book's `flows`
  (the last settled turn); the A1 ledger reads them by purpose
  (`money.flows_for_turn`). Existing packages are **not** refactored onto the
  seam; it is registered in the ledger's payer registry
  (`WEALTH_WRITERS[("money", "transfer_wealth")]`).

## Turn order (rows for the program's turn-order table)

| Order | Point | A3 action |
| --- | --- | --- |
| 1 | Phase 2, `workshops.prepare_phase2` -> `_crew_terms` (payroll's `crew_terms`) | crew request sized to affordable inputs (firm-less sites request one person) |
| 2 | same, before the ceilings (`_firm_input_cap`) | budget and plan; a site with no firm or no budget does not operate; ceiling `min(K x W, capacity)` |
| 3 | native economy tick | unchanged (prices, conversion, the people's free draw) |
| 4 | Phase 2 finish: workshops, then payroll (`settle_inputs` before title; `charge_inputs` after) | title capped by the paid share; input purchase paid; asset subsidy recorded; this tick's prices observed |
| 5 | agent tick | the wealth phase withholds the crew's share (L6a, unchanged) |
| 6 | Phase 10, payroll `phase10` (after academy procurement) | academy sales; household sales; wages and arrears; wear; insolvency; `idle` closure; distribution above the reserve; then openings with capital; then the A3 frame |
| 7 | Phase 10, last hook | the A1 ledger reads the register (new channels) |

## Customers and demand

- **Academies**: L6a's rule, unchanged (fully informed procurement of the
  region's ruler, need, price and budget).
- **Households** (`market` only; not under payroll `no_customer`): every
  resident wants `0.01` wares a turn (`cities.CRAFT_DEMAND_PER_CAPITA`, the
  native demand the people draw free from the commons). After academy sales:
  - gap = residents x 10 milli-loads less the region's uncommitted commons wares
    (stock less merchant commitments); offer = `min(inventory, gap)`;
  - households are derived from the post-tick snapshot: an adult, plus the
    resident children whose first living adult parent (`parent_id_0`, then
    `parent_id_1`) is that adult; a child with no adult parent in the region is
    its own household and pays for itself; spouses are separate households
    (Python has no relationship read: declared);
  - the offer is split over households by members (largest remainder, ties by
    household key); a household buys `min(share, floor(cash x 1000 / price))`,
    cash being its payers' `floor(wealth x 1000)`; one that cannot buy its share
    is counted `priced_out`; payers are debited in ascending id order;
  - exactly the paid wares move from the firm's inventory into the region's
    commons. The next tick's free draw takes them **ahead of the firm's next
    output**: when households can pay the gap, the commons covers the next
    demand and the firm's new output is not drawn free (the paid sale
    **replaces** the free draw rather than stacking on it). What they cannot pay
    for is not bought and stays unsold.
- **Why nobody bought** (`customer_absent`, append-only): `no_inventory`,
  `no_controller`, `no_academy`, `academy_full`, `commons_covers`,
  `households_cannot_pay`, `depopulated` (residents down by a quarter over 10
  turns), `price_unknown`, `academy_only_mode`, `no_customer_mode`.

Demand collapse is natural and recorded: an epidemic or famine shrinks the
residents and so the gap (`depopulated`); a conquest moves the owner, the
academy customer and the input payee (the firm follows the site); a city's
fall liquidates the firm; imports or legacy wares cover demand
(`commons_covers`); timber exhaustion or high raw prices leave the firm without
inputs (`budget_exhausted`, then `idle`).

## Closure (no guaranteed survival)

- **Insolvent** (L6a): six turns in a row with wages owed. Under `market` the
  firm reserves this turn's wages before it buys inputs, so arrears are rare;
  under `free_inputs` the full crew is employed whatever the cash and arrears
  build as in L6a.
- **Idle** (new): six turns in a row in which the firm could not buy any input
  (`budget_exhausted`) or its owner did not fund the asset (`not_funded`), and
  sold nothing. A worn site waiting for repair or a site without an eligible
  crew waits without counting (repair and hiring are other systems' work).
- **City fell, city missing, region changed** (L6a).

Every closure liquidates as L6a (owed wages paid from cash where possible, the
rest written off, inventory returned to the commons, cash to the ruler, the
sub-unit remainder written off) and **closes the L1 site for good**: the city is
never readmitted, so a new firm cannot reopen there with fresh capital (no
rescue by another name).

## Accounting (each raises when it fails)

- L6a firm books, extended (absent keys read 0):
  `cash = capital + sales + household_sales - inputs - wages - distributed -
  written_off - stipends`, `inventory = titled - delivered - household_delivered
  - worn - returned`; the only credits are capital (once: A3 checks the firm's
  capital against its single opening payment) and sales.
- Payroll receipts: `cash_close = cash_open + capital + sales + household_sales
  - inputs - wages_paid - distributed - written_off - stipends`;
  `inventory_close = inventory_open + titled - sold - household_sold - worn -
  returned`.
- A3 receipts (after the payroll pass, before any RS1 stipend):
  `cash_close = cash_open + capital_in + academy_sales + households.paid -
  inputs.charged - wages_paid - distributed - written_off` and
  `inventory_close = inventory_open + titled - academy_sold - households.bought
  - worn - returned`, checked at commit.
- Inputs: `charged <= budget`; `title <= paid share`; a household line is applied
  in full or the bill is refused.
- **A1 ledger** (`--wealth-accounting`): the typed channel `wares_purchase`
  (households -> firm cash, located in the firm's region) keeps the agent-wealth
  identity `close - open = typed net / 1000 + native_model`; the treasury side
  gains `firm_economics` (present only while A3 is active, so ledger records
  without A3 are unchanged): capital from treasuries, inputs to treasuries
  (whole units and carry change) or to the sink, household sales, firm cash open
  and close, and the owner's asset subsidy (firm sites from the receipts,
  firm-less sites from the counter delta). Closures: households debited = firm
  credited; capital and input flows = the A3 receipts; inputs to treasuries =
  units x 1000 + carry change; the L6a firm-cash closure with capital, household
  sales and inputs.

## Records

`snapshot.livelihoods.workshop_economics` (stage `A3`, schema 1, dated by
`source_turn`):

```
{schema_version, stage: "A3", mode, source_turn,
 units: {money: "milli_treasury_units", wares: "milli_loads", price: "milli_per_load", milli: 1000},
 firms, closed: [{firm, region, opened_turn, capital, capital_payer, status, closed_turn, closed_reason,
                  idle_run, turns, operating_turns, last_operating_turn, totals}],
 prices: [{region, turn, raw, raw_milli, craft, craft_milli, plan_raw_milli, plan_turn}],
 receipts: null | [{turn, firm, region, owner, status, operating,
   inputs: null | {plan_price_milli, budget_milli, capacity_milli, crew, wage_bill_milli, no_input_reason,
                   price_discovery, price_milli, used_timber_milli, used_ore_milli, used_milli, cost_milli,
                   charged_milli, not_charged_milli, unpaid_conversion_milli, title_cap_milli, payee,
                   treasury_units},
   produced, titled, free_use_upper_bound, academy_sales, academy_sold,
   households: null | {residents, households, demand_milli, commons_milli, gap_milli, offered_milli,
                       price_milli, bought_milli, paid_milli, buying_households, priced_out_households,
                       payers, depopulated},
   customer_absent, capital_in, wages_due, wages_paid, owed_after, worn, returned, distributed,
   written_off, cash_open, cash_close, inventory_open, inventory_close, unsold_inventory,
   owner_asset_spend, idle_run, insolvent_run, event}],
 flows: null | [...money flows of the source turn...], book: {carry, sinks},
 counters, log, log_dropped, parameters}
```

L6a's payroll record keeps its shape; its money kinds gain `capital`,
`input_purchase` and `household_sale`, its material kinds
`household_delivery`, and its receipts the optional `capital`, `inputs`,
`household_sales` and `household_sold` (absent outside A3).

**Viewer**: `viewer/src/lib/workshopEconomics.ts` (types and a strict reader;
`types.ts` is pinned) keeps **absent** (no record), **disabled** (an L6a payroll
record without A3), **malformed** (wrong shape or books that do not close),
**unobserved** (`receipts: null`, unknown, not zero) and **observed** (recorded
zeros; an empty list is an observed turn without a firm) apart.
`WorkshopEconomics.tsx`, mounted in the Livelihoods panel, shows each firm's
cash and capital, inputs used and paid, academy and household sales (bought,
priced out), wages, arrears, unsold wares, the building subsidy, why nobody
bought and closure reasons, with a lifetime funnel. The L6a reader
(`workshopFinance.ts`) accepts the A3 kinds and fields in its exact closures.

## Native change

One appended transfer purpose, `wares_purchase` (code 7, after
`food_procurement`; append-only, nothing renumbered). Households pay through
debit rows of the existing keyed `transfer` (limited at zero, one key per firm
and turn); the firm's cash is a Python account. No new function, no checkpoint
layout change (the key log stays transient). The two Python tests that pin the
exact purpose list and the tests that expected code 7 to be refused now expect
the appended name and refuse 8.

## Declared parameters (modeling choices, not calibrated)

| Name | Value | Meaning |
| --- | --- | --- |
| `CAPITAL` | 20 000 milli (20 units) | the owner's one-time starting capital (about three turns of a full rank-2 crew's wages plus three turns of a full ceiling's inputs at about 1.1 a load) |
| `IDLE_CLOSE_AFTER` | 6 | idle turns in a row that close a firm |
| `IDLE_REASONS` | `budget_exhausted`, `not_funded` | what counts as idle |
| `INPUT_SLACK` | 2 milli | kept back from the input budget for the f32 ceiling |
| `WARES_PER_HEAD` | 10 milli-loads | each resident's wares demand (`CRAFT_DEMAND_PER_CAPITA`) |
| `ADULT_AGE` | 20 | payers are adults (native `AGE_ADULT`) |
| `DEPOPULATION_SHARE`, `DEPOPULATION_WINDOW` | 0.25, 10 turns | the `depopulated` reason |
| `K_RAW_PER_WORK`, `WAGE_PER_WORK`, `INVENTORY_CAP`, `WARES_WEAR`, hours, layoffs, `RESERVE_TURNS` | L1 and L6a values | unchanged |

## Boundaries and declared limits (slice A3-1)

- **Same-tick free use.** The tick's craft output enters the commons before
  title, so the people's draw and same-tick merchant departures can still take
  part of the firm's new output free when the commons does not already cover
  them (recorded per firm-turn as `free_use_upper_bound`; A3-2's native
  owned-output column ends it).
- Paid wares delivered to the commons can be loaded by merchants free (A4).
- Spouses buy as separate households; adults pay for their own resident
  children only.
- Sites without a firm produce nothing under the switch: L1B public production
  from free inputs is retired while A3 is on. Their crews (one person requested)
  are reserved but idle, as at any non-operating L1 site, and the ruler still
  pays the asset's upkeep (recorded as `asset_subsidy_idle_units`).
- Legacy city crafts outside site regions keep their free inputs and unnamed
  labour (an intentional boundary, audit W9).
- The starting capital is outside L9's envelopes (it is not an L9 service).
- Academies are still delivered realm-wide without transport (L6a).
- Firm inventory and cash are outside A5's owned-stock rules (siege, occupation,
  requisition): the firm keeps everything and follows the site through a
  conquest (A5/D4).
- Input payee is the commons owner (the ruler), not the producers by id (A3-3).

## The price-margin risk

Crafting is volume-neutral (one raw load makes one load of wares) and the
economy prices by scarcity (`demand / max(supply, 0.1)`). A firm's own ceiling
enters raw demand, while its output gluts its city's wares market. In firm
cities the raw price is therefore usually far above the wares price (the A3
audit measured wares above raw in 12.6% of operating site region-turns on one
development world), so a firm that pays for its inputs loses money on almost
every load and lives on its capital and on academy purchases. Under `market`
most firms are expected to close `idle`; the `free_inputs` control shows how
much of that is the input charge. This slice reports the result rather than
tuning it: a wares-value calibration or rules version is the owner's decision
(audit section 9, Q1), and merchant demand from scarce markets (A4) is the
other way out.

## Verification

Filled in from the runs of this slice (see the evidence section below).

## Evidence (development worlds only; not a screen)

See below.
