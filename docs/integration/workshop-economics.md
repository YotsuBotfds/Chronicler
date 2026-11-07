# Workshop economics and the shared payment seam (A3, `--workshop-economics`)

Connected-world program, slices A3-1 and A3-2 (owned output,
`--workshop-economics-rules 2`, section "A3-2" below). Default off; requires `--workshop-payroll`
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

- a firm opens once with **owner capital**; a city whose firm closed never gets
  another firm or capital;
- it **pays for its inputs before it converts them**, at the raw price the
  economy computed in an earlier tick, to the ruler who owns the commons they
  come from, and converts only what it paid for;
- it sells to **academies and to the region's households** (by stable id,
  adults paying);
- a site **without a firm produces nothing**, and a firm that cannot pay for
  any input does not operate (no production from unpaid inputs under the
  switch);
- firms close when insolvent or **idle**; nothing guarantees survival.

## Switch, modes and refusals

| Mode (`--workshop-economics-mode`) | Inputs | Customers | Role |
| --- | --- | --- | --- |
| `market` (default) | bought from the ruler at the plan price before conversion | academies, then households | the mechanism |
| `free_inputs` | the same budget, plan price, crew sizing and ceiling as `market`; the cost is recorded (`not_charged_milli`) and not taken | academies, then households | cost control: the input charge alone |
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
  omitted while unset; witness layer `cwa3`, parent `5108f8b9`, the last layer).
- Inserted in `LIVELIHOODS_SWITCHES` **before** `wealth_accounting` (the
  ledger stays last). It registers **no hooks of its own**: the module defines
  no function named like a livelihoods hook; the workshop and payroll seams
  call it, so its effects run at payroll's position. No random draws.

## Who pays whom

Money in milli-units (1000 = one treasury unit = one unit of a person's
wealth); wares and raw inputs in milli-loads.

| Flow | Payer -> payee | When | Rule |
| --- | --- | --- | --- |
| Starting capital (`firm_capital`) | ruler's treasury -> firm cash | Phase 10, once per firm | declared constant `CAPITAL` = 20 units; refused (and retried a later turn) when the projected treasury is short, when no input price exists for the site (`no_input_price`) or at a city whose firm closed (`closed_city`) |
| Input purchase (`firm_input_purchase`) | firm cash -> ruler's treasury (owner of the commons); `unowned_commons` sink if nobody rules the region | after the successful tick (Phase 2 finish) | `ceil(used x plan price)`, within the reservation by construction; sub-unit amounts carried to the treasury (`money`) |
| Asset build, upkeep, repair | ruler's treasury -> public expenditure sink (L1, unchanged) | Phase 2 finish | recorded per site as the owner's **asset subsidy**, outside the firm's books |
| Academy sale | ruler's treasury -> firm cash (L6a, unchanged) | Phase 10 | as L6a |
| Household wares purchase (`wares_purchase`, native purpose 7) | households' wealth (adults) -> firm cash | Phase 10, after academy sales | one collection of keyed debit rows per firm and turn |
| Wages, arrears | firm cash -> crew (L6a, unchanged) | Phase 10 | as L6a |
| Distribution, liquidation | firm cash -> ruler's treasury / sink (L6a) | Phase 10 or at closure | reserve kept: `RESERVE_TURNS` x (full wage bill + full input bill at the plan price) |

The only credits to households remain wages (and L6a's crew pay). Capital,
input purchases and household spending are transfers between named accounts;
nothing is minted into firm cash.

## The price rule (the lead's decision)

**Inputs: the plan price.** The most recent positive post-trade raw-material
price (`market_price_raw_material`; timber and ore share the `raw_material`
category) **that the native economy computed for the firm's region in an
earlier tick**, with its turn. If the region never had one (no raw demand
there since A3 began observing), the most recent positive one among the
regions of the region's ruler (latest turn, then lowest region index): this
fallback uses realm-wide knowledge, accepted as the ruler's knowledge of its
own realm (it never fired in the 13 development worlds). If
none exists, the firm cannot buy (`price_unknown`) and a site cannot open
(`no_input_price`). The price is never clamped, smoothed or invented; it is
rounded **up** to whole milli-units per load. The price the economy computes
in the purchase's own tick (which includes the purchase's demand at the 0.1
supply floor) is **never** charged; it is recorded beside each purchase as a
diagnostic (`tick_price_milli`). Every purchase records the plan price, its
turn, its source region and whether it came from the region or the realm.

**Paid before converted.** The purchase is reserved before the tick and paid
after it:

1. **Budget** (Phase 2, workshop seam): cash less wages owed, this turn's wage
   bill for the planned crew and a 2-milli slack (`INPUT_SLACK`, for the f32
   ceiling's rounding). A budget of zero or less, or no plan price: the site
   does not operate (`budget_exhausted`, `price_unknown`).
2. **Plan**: the budget buys `capacity = floor(budget x 1000 / plan price)`
   milli-loads; the region's craft ceiling becomes `min(K x W, capacity)` and the
   crew request is sized to the workers those inputs occupy (at least one, the
   native planner's floor). A firm that cannot pay for its crew's full need
   (`need_milli`) scales its production down to the paid inputs; the raw stock
   it does not buy stays in the commons and is never converted
   (`unbought_need_milli`).
3. **Pay** (after the successful tick): the native conversion never exceeds the
   ceiling, so the inputs actually used (native `craft_input` timber + ore) are
   at most the paid capacity (raised otherwise); the firm pays `ceil(used x plan
   price)`, which is within the reservation by construction. Nothing is
   converted unpaid (`converted_unpaid_milli` is always 0). A failed tick
   charges nothing (as every Phase 2 bill).

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
- Every receiving account (a firm id, a civilization index) is checked to exist,
  and the payer's coverage too, before any move: a treasury's projected budget
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
  (the last settled turn, at most 512 kept, `flows_dropped` counts the rest) and
  is added to the turn's exact `totals` per (purpose, account kinds, region),
  which the A1 ledger reads (`money.totals_for_turn`). Existing packages are
  **not** refactored onto the seam.
- **Registries (fail closed)**: every agent-wealth line goes through one router,
  `money._native_transfer`, declared in the ledger's `WEALTH_ROUTERS` with its
  two call sites in `WEALTH_WRITERS`; `MONEY_PURPOSE_CHANNELS` maps each purpose
  the seam may move agent wealth for to its ledger channel and `money` refuses
  any other at run time; `MONEY_BILLS` registers every caller of the seam with
  its literal purposes, and `tests/test_money.py` walks `src/` and fails on an
  unregistered, stale or non-literal caller.

## Turn order (rows for the program's turn-order table)

| Order | Point | A3 action |
| --- | --- | --- |
| 0 | Phase 2, `workshops.refresh_sites` (`_never_readmit`) | cities whose A3 firm closed are never readmitted |
| 1 | Phase 2, `workshops.prepare_phase2` -> `_crew_terms` (payroll's `crew_terms`) | crew request sized to the inputs the budget buys at the plan price (firm-less sites request one person) |
| 2 | same, before the ceilings (`_firm_input_cap`) | budget and plan; a site with no firm, no budget or no price does not operate; ceiling `min(K x W, capacity)` |
| 3 | native economy tick | unchanged (prices, conversion within the ceiling, the people's free draw) |
| 4 | Phase 2 finish: workshops, then payroll (`charge_inputs` after title) | input purchase paid at the plan price; asset subsidy recorded; this tick's prices observed for later plans |
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

- **Insolvent** (L6a): six turns in a row with wages owed. In every A3 mode the
  firm reserves this turn's wages (and wages owed) before it buys inputs, so
  natural arrears do not arise; the path stays for arrears carried in (tested
  with constructed claims).
- **Idle** (new): six turns in a row in which the firm converted and sold
  nothing: it could not operate for a reason in `IDLE_REASONS` - no budget
  (`budget_exhausted`), no plan price (`price_unknown`), an unfunded asset
  (`not_funded`) or no eligible crew (`no_crew`) - or it operated with no raw
  stock to convert (re-check n1: under payroll `unpaid_labor` such a firm owes
  no wage and would otherwise never run out of budget). A worn site waiting for repair waits without
  counting (repair is RS2's work).
- **City fell, city missing, region changed** (L6a).

Every closure liquidates as L6a (owed wages paid from cash where possible, the
rest written off, inventory returned to the commons, cash to the ruler, the
sub-unit remainder written off) and **closes the L1 site for good**. A3 keeps the
city's settlement id in its own persisted `closed_settlements` (L1 keeps only
eight closed sites, and before review M1 a ninth closure let L1 readmit the
oldest city under a new site id, which A3 then re-capitalized): L1 never
readmits those cities while A3 is active and an opening there is refused
(`closed_city`), so no city gets a second firm or a second capital.

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
- Inputs: `used x 1000 <= capacity` (paid before converted; raises otherwise),
  `charged = ceil(used x plan price) <= budget + slack`, `converted_unpaid = 0`;
  a household line is applied in full or the bill is refused.
- **A1 ledger** (`--wealth-accounting`): every purpose in
  `MONEY_PURPOSE_CHANNELS` is read generically with signs (agent payee in, agent
  payer out) from the seam's exact per-turn totals (`money.totals_for_turn`, never
  truncated, and keeping each treasury side's civilization, whole units and
  carry change: a turn with more than 512 payments is counted in full, per
  civilization too, and the drop is recorded as `firm_economics.flows_dropped`); the typed channel
  `wares_purchase` (households -> firm cash, located in the firm's region) keeps
  the agent-wealth identity `close - open = typed net / 1000 + native_model`; the treasury side
  gains `firm_economics` (present only while A3 is active): capital from treasuries, inputs to treasuries
  (whole units and carry change) or to the sink, household sales, firm cash open
  and close, and the owner's asset subsidy (firm sites from the receipts,
  firm-less sites from the counter delta). Closures: households debited = firm
  credited; capital and input flows = the A3 receipts; inputs to treasuries =
  units x 1000 + carry change; the L6a firm-cash closure with capital, household
  sales and inputs.
  With A3 off and the ledger on, a ledger record differs from one built before
  A3 in exactly one place: the declared channel list
  (`parameters.channels`) now ends with `wares_purchase`. No typed row,
  closure, `firm_economics` section or lifetime key for A3 appears (rows and
  lifetime keys are written only for active channels; A3's lifetime keys are
  appended after A1's, so the key order of A1's keys is unchanged). Feature-off
  identity (no ledger, no A3) is unaffected.

## Records

`snapshot.livelihoods.workshop_economics` (stage `A3`, schema 1, dated by
`source_turn`):

```
{schema_version, stage: "A3", mode, source_turn,
 units: {money: "milli_treasury_units", wares: "milli_loads", price: "milli_per_load", milli: 1000},
 firms, closed: [{firm, region, opened_turn, settlement_id, capital, capital_payer, status, closed_turn,
                  closed_reason, idle_run, turns, operating_turns, last_operating_turn, totals}],
 prices: [{region, turn, raw, raw_milli, craft, craft_milli, plan_raw_milli, plan_turn}],   # open sites' regions
 closed_settlements: [settlement ids whose firm closed],
 receipts: null | [{turn, firm, region, owner, status, operating,
   inputs: null | {plan_price_milli, plan_price_turn, plan_price_region, plan_price_source,
                   tick_price_milli, budget_milli, capacity_milli, need_milli, unbought_need_milli, crew,
                   wage_bill_milli, no_input_reason, used_timber_milli, used_ore_milli, used_milli, cost_milli,
                   charged_milli, not_charged_milli, converted_unpaid_milli, payee, treasury_units},
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
cash and capital, inputs used and paid with the plan price (its turn and
whether it came from the region or the realm), the need not bought (raw stock
left in the commons), academy and household sales (bought, priced out), wages,
arrears, unsold wares, the building subsidy, why nobody bought and closure
reasons, with a lifetime funnel. The reader refuses a receipt that converted
anything unpaid, used more than its plan price bought or charged other than the
cost at the plan price. The L6a reader
(`workshopFinance.ts`) accepts the A3 kinds and fields in its exact closures.

## Native change

A3-2 (batched with A4-1's native parts into one build): the optional
`workshop_owned_crafts` column (`economy::tick_economy_core_full`, parsed in
`ffi/mod.rs`; both files pinned, witness layer `cwa4`), transient, no
checkpoint layout change. A3-1:

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
| `IDLE_REASONS` | `budget_exhausted`, `price_unknown`, `not_funded`, `no_crew` | what counts as idle |
| `INPUT_SLACK` | 2 milli | kept back from the input budget for the f32 ceiling |
| `WARES_PER_HEAD` | 10 milli-loads | each resident's wares demand (`CRAFT_DEMAND_PER_CAPITA`) |
| `ADULT_AGE` | 20 | payers are adults (native `AGE_ADULT`) |
| `DEPOPULATION_SHARE`, `DEPOPULATION_WINDOW` | 0.25, 10 turns | the `depopulated` reason |
| `K_RAW_PER_WORK`, `WAGE_PER_WORK`, `INVENTORY_CAP`, `WARES_WEAR`, hours, layoffs, `RESERVE_TURNS` | L1 and L6a values | unchanged |

## A3-2: owned output (`--workshop-economics-rules 2`)

Rules version 2 removes the recorded limit "same-tick free use" (below): a
firm's output never passes through the commons, so it reaches anyone only by
sale. Version 1 (the default, and the version of every state saved before
A3-2) keeps A3-1 exactly; a state keeps its version (`rules_version`, omitted
while 1, so A3-1 dumps keep their bytes), and a conflicting
`--workshop-economics-rules` is refused at startup and on an exact resume. The
option requires `--workshop-economics`.

- **Native column.** The Phase 2 region batch carries the optional Float32
  column `workshop_owned_crafts`: each firm region's inventory at opening, in
  loads (null elsewhere; absent when no firm exists). In such a region the
  native economy crafts as before (same inputs, same ceiling, the output
  reported in `craft_output` and counted in production) but adds none of it to
  the commons stockpile: the people's free draw (step 3b) takes only the
  commons (imports, legacy city crafts elsewhere, wares households bought) and
  native merchants cannot load the firm's wares. The firm's inventory counts in
  the region's wares supply for prices, as retail's owned food counts in food
  prices. The conservation batch gains `workshop_owned_outflow` (the wares
  handed to firms) only when the column is present. Hybrid economy only; a
  negative or non-finite value is refused.
- **Title.** Payroll titles the whole output, `floor(output x 1000)`
  milli-loads, straight into the firm's inventory (material source
  `workshop_output`), never debiting the commons; `produced == titled` and
  `free_use_upper_bound == 0` on every receipt (raised otherwise), counted in
  `owned_output`.
- **No lost output.** One raw load makes one load of wares, so the firm's
  input capacity (and therefore its ceiling) is bounded by its inventory room
  (`INVENTORY_CAP - inventory`); a full inventory is a reason not to operate
  (`inventory_full`, counted idle). Wear keeps some room open, so a firm
  without customers keeps buying inputs to replace worn wares until its budget
  runs out.
- **Customers.** Households buy the gap the commons leaves; under version 2
  the commons hold none of the firm's output, so their purchases are the only
  way it reaches them. Academies as before. A merchant buying firm wares is
  A4's wares slice (A4-W), not this one.
- **Viewer.** The A3 reader accepts `rules_version: 2` and then refuses any
  receipt with free use or an untitled share; the panel says which rules the
  record follows and shows the output taken straight into inventory.

## Boundaries and declared limits (slice A3-1)

- **Same-tick free use** (rules version 1 only; removed by A3-2, which
  records `free_use_upper_bound` 0 by construction). The tick's craft output
  enters the commons before title, so the people's draw and same-tick merchant
  departures can still take part of the firm's new output free when the
  commons does not already cover them (recorded per firm-turn as
  `free_use_upper_bound`).
- Paid wares delivered to the commons can be loaded by merchants free (A4).
- Spouses buy as separate households; adults pay for their own resident
  children only; a child with no adult parent in the region pays from its own
  wealth; residents are counted by their snapshot region (one away on a trip
  still pays).
- The plan price follows the region's own most recent positive raw price,
  which includes the firm's demand of the earlier tick (the economy's price at
  the 0.1 supply floor can be high); prices are not clamped (the lead's
  decision).
- No natural wage arrears under A3 (wages are reserved before inputs); the
  insolvent path is reached only by arrears carried in.
- A3 receipts' `cash_close` is before any RS1 stipend (the L6a receipt records
  it); the asset subsidy is attributed to the Phase 10 controller and excludes
  RS2 repair spend on the asset.
- `--no-workshop-economics` on a legacy resume continues the firms under L6a's
  rules (free inputs again) rather than liquidating them.
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
most firms are expected to close `idle`; the `free_inputs` control (identical
but for the charge) shows how much of that is the input charge. This slice reports the result rather than
tuning it: a wares-value calibration or rules version is the owner's decision
(audit section 9, Q1), and merchant demand from scarce markets (A4) is the
other way out.

## Verification

After the independent review (changes requested: B1 the tick-price settlement,
M1 readmitted cities, M2 the cost control, M3 the viewer, minors m1-m5), its
re-check (n1-n3) and the merge of `main` after S1 (PR #86, `5108f8b9`), on
source `636202f9` unless noted, native extension built from this branch
(`maturin develop --release --locked`, native venv `~/.venvs/native-a3`):
SHA-256 `2831bbd4953311b87cfa208c751f7745f9bf7740335ae8f39029b1b0c33c7630`
(the review fixes changed no Rust, so no rebuild); `check_python_env.py
--expect native` PASS. The Rust differs from `8abc1acb` only by the appended
purpose (plus one assertion inside its test module).

- **Focused offline tests**: `tests/test_money.py` (22) and
  `tests/test_workshop_economics.py` (28), with the ledger, payroll, workshops,
  feature-catalog, batch-manifest, shard, retail and `main`'s feature-matrix,
  watershed, quarantine and screen-runner tests: 457 + 272 passed.
- **Witness**: one layer `cwa3` against `main`'s bytes (parent `5108f8b9`,
  last after `cws1`; 3 hunks, only the added manifest keys; no pinned Rust
  file): the witness modules 509 passed.
- **Bounded offline lane** (110-second limit kept, default output directory):
  PASS in 254.2 s; `connected-world-a` 5.8 s (78 tests).
- **Native tests** (real extension): `test_workshop_economics_native.py` (3:
  every transfer checked against the live pool and a repeated key refused;
  every charge `= max(1, ceil(used x plan price))` with the plan price from an
  earlier tick; conversion within the paid capacity; nothing converted unpaid;
  no craft output at firm-less sites; every ledger closure; exact resume inside
  an idle run before an idle closure and a city fall; exact resume at live
  trading firms under `free_inputs`) with the wealth-accounting, payroll,
  recovery-skills, retail, apprenticeship, relocation, remittance and closure
  native modules: 76 passed.
- **`cargo test --locked`** (before the review; no Rust change since): 743
  library tests and every integration target passed.
- **Feature-off identity** (`turn_speed_identity.py`, each side its own exported
  tree and extension): against the reference `8abc1acb` (`101a4cd5`), 9 cases,
  399 files compared, 0 differences. Against `main` `5108f8b9` (its tree with
  the reference extension: main has no Rust change) with the prerequisites on
  (`--grain-reserves --public-grain-shipments --grain-storage --workshops
  --workshop-payroll`) on `hybrid_s42` and `proc48_hybrid_s42`: the switch absent
  and the explicit `--no-workshop-economics` each 2 cases, 205 files, 0
  differences.
- **Enabled exact resume** (`checkpoint_identity.py` from the branch, extension
  `2831bbd4…`) with the checkpoint-3 chain (`--grain-reserves
  --public-grain-shipments --scholarship --techniques --academy-services
  --grain-storage --food-allocation --workshops --operating-wear
  --repair-projects --timber-stock --household-retail
  --household-retail-boundary=paid_work --timber-supply --recovery-crews
  --remittances`) plus `--workshop-payroll --workshop-economics
  --wealth-accounting`: `hybrid_s42_long` PASS at all 19 resume points (one of
  them inside a live firm) and `proc32_hybrid_s11` PASS at 18 points (20-33:
  openings, input purchases, household sales, idle runs; 34-37: idle runs and
  the two idle closures at 36 and 37); writing checkpoints changed nothing.
- **Viewer**: the full suite with `--maxWorkers=1`: 1,585 passed, 2 skipped;
  lint clean; production build succeeded.
- **After merging `main` `ae94bca6` (PR #87, C1b, which changed Rust)**: the
  native venv was rebuilt once (SHA-256
  `20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca`;
  `check_python_env.py --expect native` PASS; purposes end with
  `wares_purchase`); `cargo test --locked` 752 library tests and all 40 targets
  passed; layer `cwa3` rebuilt against `ae94bca6` as the last layer (after
  `cwc1b`; witness 509 passed); on `272e1498`: focused 533 passed, native 76
  passed, offline lane PASS in 332.6 s, feature-off identity against `8abc1acb`
  9 cases 399 files 0 differences, A3 absent and `--no-workshop-economics`
  against `main`'s tree (with this branch's extension, which differs from
  main's Rust only by the appended purpose) 205 files 0 differences each, exact
  resume `proc32_hybrid_s11` PASS at 8 live-firm points (21, 24, 27: openings;
  30-35: trading and idle runs; 36, 37: idle closures).
- **Not run**: a held screen (CW2 is planned after A3-2, audit section 7), a
  browser journey, the 200-seed and procedural qualification gates
  (restricted), profiling at the declared scale, PR CI.

### A3-2 (owned output), with A4-1 in one native build

Branch `claude/cw-a4-titled-trade` from `main` `8401aa74`, code commit
`9c6c66ee`, extension SHA-256 `2ba123ab259b98cb2b2e66edef4852015c40cbc73172a3b6d2d265d9c2aa950b`
(the full record is in [titled-trade.md](titled-trade.md), "Verification").

- **A3-1 reproducibility**: workshop economics without the rules option, and
  with the explicit `--workshop-economics-rules=1`, against `main` `8401aa74`
  (its own tree and extension `20e77f99`) with `--grain-reserves
  --public-grain-shipments --grain-storage --workshops --workshop-payroll
  --workshop-economics` on `hybrid_s42` and `proc48_hybrid_s42`: 205 files,
  0 differences each.
- **Rust**: `economy::workshop_owned_tests` (no column or a null row is
  bit-identical to the plain call; a firm's output never enters the commons,
  is counted in production and the outflow, and its stock is priced; a
  negative inventory is refused).
- **Offline**: `tests/test_workshop_economics.py` (33, five for A3-2: rules 1
  keeps A3-1's batch and bytes and a conflicting rules value is refused; the
  option requires workshop economics; the output never enters the commons and
  is titled whole; output reaches households only by sale; the ceiling stays
  within the inventory room).
- **Native** (`tests/test_workshop_economics_native.py`, template seed 1, 122
  turns, `CHRONICLER_CHECK_RESOURCES=1`): every operating receipt has
  `produced == titled == floor(native craft output x 1000)`, free use 0, no
  title basis (nothing taken from the commons) and a ceiling within the room;
  every ledger closure held; exact resume at turn 60 (live, producing firms)
  equals the straight run.

## Evidence (development worlds only; not a screen)

Development-only, 2026-11-06: source `636202f9` (exported tree: main after S1
merged in, the plan-price rule after review and the re-check n1-n3 fixes),
native extension `2831bbd4…` (this branch's build); no preregistration, no
held seed, no 7xx/8xx seed. One run per world and mode, 200 turns, flags
`--agents hybrid --grain-reserves --public-grain-shipments --scholarship
--techniques --academy-services --workshops --workshop-payroll
--workshop-economics --wealth-accounting` plus the mode; procedural worlds add
`--worldgen procedural --regions 32 --civs 10`. This describes activation, not
an effect. Money in treasury units; "survival" is turns from opening to
closure (or to turn 199 for a firm still open); "household sales" is the paid
non-academy demand. Template runs took 7-9 s, procedural 16-19 s (4 shared
cores under load). Earlier runs of the same matrix (`ed9c0972`, the tick-price
rule the review rejected; `9c9d10f7`, before n1 and the merge) are superseded
and kept only in the evidence directory.

| Mode | Worlds active / run | Firms opened | Closed idle / insolvent / city fell / open at 199 | Median survival of closed firms (template; procedural) | Operating firm-turns | Inputs paid | Inputs not charged (control) | Academy sales | Household sales | Owner capital paid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `market` | 13 / 13 | 102 (25 template, 77 procedural) | 70 / 0 / 13 / 19 | 82; 39 | 3,663 | 1,589.4 | 0 | 982 | 868.2 | 2,040 |
| `free_inputs` | 13 / 13 | 78 (28; 50) | 41 / 0 / 11 / 26 | 68; 60 | 4,400 | 0 | 4,286.4 | 1,194 | 783.5 | 1,560 |
| `academy_only` | 13 / 13 | 113 (29; 84) | 111 / 0 / 2 / 0 | 16; 15.5 | 1,777 | 1,641.6 | 0 | 1,547 | 0 | 2,260 |

Every one of the 39 runs: **nothing was converted unpaid** (`converted_unpaid`
0 on every receipt), **no city received a second firm** (every firm's
settlement id distinct; `opening_refused_closed_city` 0 because L1 never
readmitted one), every A1 ledger closure held on every observed turn (0
failures), no opening was refused for want of a price and the realm fallback
was never needed (each site's region had a positive raw price from before the
site operated), and no household was priced out (`priced_out_households` 0).
The input need firms could not pay for and left in the commons
(`unbought_need`) was 7,732.4 loads under `market`. Same-tick free use of firm
output (`free_use_upper_bound`) was 138.1 loads under `market`.

Reading (development-only):

- **Most firms close.** Under `market` 70 of 102 firms closed idle and 19 were
  still open at turn 199; none closed insolvent (wages are reserved before
  inputs, so a firm's crew shrinks with its cash instead of running arrears).
  Median survival of closed firms was 82 turns in template worlds and 39 in
  procedural ones.
- **The input charge shortens lives; it is not the whole story.** With every
  other rule identical, `free_inputs` firms closed idle 41 times (of 78) and 26
  were open at turn 199; their uncharged input cost was 4,286 units (they keep
  their cash and so buy more inputs each turn than `market` firms, which paid
  1,589).
- **Household demand matters to survival.** Without household customers
  (`academy_only`) firms close idle after a median 15.5-16 turns and new sites
  open at other cities (113 openings, each at a different city: no city is
  readmitted).
- Household sales were real paid demand in every world: 868.2 units under
  `market`, 47% of firms' sales (100% in worlds without academy purchases).

Per world (`t` template, `p` procedural):

| World | Mode | Firms opened | Survival median (turns) | Survival range | Ending (closed reason / open at 199) | Operating firm-turns | Inputs paid | Inputs not charged | Academy sales | Household sales | Household share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1 | market | 3 | 57 | 28-82 | city_fell 1, idle 2 | 132 | 44.7 | 0.0 | 0.0 | 33.51 | 1.00 |
| t1 | free_inputs | 3 | 46 | 13-60 | idle 2, open@199 1 | 93 | 0.0 | 97.3 | 21.0 | 19.94 | 0.49 |
| t1 | academy_only | 3 | 19 | 14-35 | idle 3 | 47 | 37.7 | 0.0 | 15.0 | 0.00 | 0.00 |
| t3 | market | 4 | 103.5 | 13-141 | city_fell 1, idle 2, open@199 1 | 298 | 86.9 | 0.0 | 44.0 | 72.34 | 0.62 |
| t3 | free_inputs | 5 | 31 | 6-101 | idle 4, open@199 1 | 200 | 0.0 | 128.5 | 8.0 | 35.04 | 0.81 |
| t3 | academy_only | 3 | 16 | 11-16 | idle 3 | 25 | 22.7 | 0.0 | 0.0 | 0.00 | - |
| t7 | market | 4 | 89.0 | 65-99 | idle 4 | 268 | 86.2 | 0.0 | 23.0 | 70.03 | 0.75 |
| t7 | free_inputs | 5 | 78 | 13-172 | city_fell 1, idle 2, open@199 2 | 393 | 0.0 | 486.8 | 30.0 | 78.68 | 0.72 |
| t7 | academy_only | 5 | 12 | 11-32 | idle 5 | 49 | 65.1 | 0.0 | 36.0 | 0.00 | 0.00 |
| t9 | market | 5 | 37 | 7-115 | idle 5 | 167 | 211.8 | 0.0 | 466.0 | 19.64 | 0.04 |
| t9 | free_inputs | 5 | 69 | 8-120 | idle 5 | 266 | 0.0 | 272.0 | 317.0 | 27.04 | 0.08 |
| t9 | academy_only | 6 | 40.5 | 17-61 | idle 6 | 146 | 178.8 | 0.0 | 184.0 | 0.00 | 0.00 |
| t11 | market | 4 | 98.5 | 75-129 | city_fell 1, idle 3 | 271 | 50.4 | 0.0 | 0.0 | 62.73 | 1.00 |
| t11 | free_inputs | 5 | 60 | 22-94 | idle 5 | 237 | 0.0 | 127.5 | 215.0 | 37.68 | 0.15 |
| t11 | academy_only | 5 | 19 | 9-69 | city_fell 1, idle 4 | 92 | 35.4 | 0.0 | 287.0 | 0.00 | 0.00 |
| t23 | market | 3 | 113 | 85-178 | city_fell 1, idle 1, open@199 1 | 297 | 56.0 | 0.0 | 0.0 | 87.58 | 1.00 |
| t23 | free_inputs | 3 | 70 | 26-178 | city_fell 1, idle 1, open@199 1 | 237 | 0.0 | 127.6 | 0.0 | 35.57 | 1.00 |
| t23 | academy_only | 4 | 15.0 | 10-20 | idle 4 | 36 | 21.9 | 0.0 | 0.0 | 0.00 | - |
| t42 | market | 2 | 35.5 | 33-38 | idle 2 | 32 | 27.9 | 0.0 | 0.0 | 20.55 | 1.00 |
| t42 | free_inputs | 2 | 40.5 | 13-68 | idle 2 | 55 | 0.0 | 88.6 | 0.0 | 17.28 | 1.00 |
| t42 | academy_only | 3 | 13 | 13-35 | idle 3 | 35 | 27.6 | 0.0 | 0.0 | 0.00 | - |
| p7 | market | 14 | 29.0 | 12-168 | city_fell 3, idle 8, open@199 3 | 400 | 166.1 | 0.0 | 43.0 | 82.88 | 0.66 |
| p7 | free_inputs | 5 | 168 | 66-178 | city_fell 1, open@199 4 | 523 | 0.0 | 450.0 | 211.0 | 89.94 | 0.30 |
| p7 | academy_only | 15 | 13 | 3-64 | city_fell 1, idle 14 | 175 | 174.7 | 0.0 | 71.0 | 0.00 | 0.00 |
| p11 | market | 11 | 32 | 5-101 | city_fell 2, idle 6, open@199 3 | 289 | 149.4 | 0.0 | 14.0 | 63.93 | 0.82 |
| p11 | free_inputs | 10 | 35.5 | 4-142 | city_fell 2, idle 4, open@199 4 | 380 | 0.0 | 414.5 | 44.0 | 62.46 | 0.59 |
| p11 | academy_only | 6 | 27.0 | 13-104 | idle 6 | 186 | 194.2 | 0.0 | 191.0 | 0.00 | 0.00 |
| p13 | market | 13 | 25 | 9-174 | city_fell 1, idle 11, open@199 1 | 408 | 178.1 | 0.0 | 186.0 | 103.31 | 0.36 |
| p13 | free_inputs | 10 | 48.0 | 11-177 | idle 6, open@199 4 | 514 | 0.0 | 575.9 | 108.0 | 80.68 | 0.43 |
| p13 | academy_only | 20 | 13.0 | 6-49 | idle 20 | 238 | 196.2 | 0.0 | 105.0 | 0.00 | 0.00 |
| p17 | market | 12 | 26.5 | 1-151 | idle 9, open@199 3 | 374 | 201.3 | 0.0 | 202.0 | 83.24 | 0.29 |
| p17 | free_inputs | 9 | 70 | 8-175 | city_fell 3, idle 2, open@199 4 | 554 | 0.0 | 573.7 | 159.0 | 94.75 | 0.37 |
| p17 | academy_only | 15 | 20 | 6-100 | idle 15 | 342 | 276.4 | 0.0 | 337.0 | 0.00 | 0.00 |
| p21 | market | 12 | 39.0 | 0-103 | city_fell 2, idle 6, open@199 4 | 334 | 128.4 | 0.0 | 4.0 | 82.02 | 0.95 |
| p21 | free_inputs | 8 | 64.0 | 6-140 | city_fell 3, idle 4, open@199 1 | 390 | 0.0 | 366.4 | 34.0 | 59.71 | 0.64 |
| p21 | academy_only | 12 | 24.5 | 6-70 | idle 12 | 247 | 247.2 | 0.0 | 321.0 | 0.00 | 0.00 |
| p31 | market | 15 | 33 | 5-148 | city_fell 1, idle 11, open@199 3 | 393 | 202.3 | 0.0 | 0.0 | 86.43 | 1.00 |
| p31 | free_inputs | 8 | 65.5 | 18-177 | idle 4, open@199 4 | 558 | 0.0 | 577.6 | 47.0 | 144.71 | 0.75 |
| p31 | academy_only | 16 | 14.5 | 8-33 | idle 16 | 159 | 163.7 | 0.0 | 0.0 | 0.00 | - |

### A3-2 against A3-1 (development worlds only; not a screen)

Development-only, 2026-11-07: source `9c6c66ee` (branch
`claude/cw-a4-titled-trade`), extension `2ba123ab…`; the same 13 worlds, flags
and 200 turns as the table above in `market` mode, with and without
`--workshop-economics-rules 2`, `CHRONICLER_CHECK_RESOURCES=1` (no resource
problem raised). The rules-1 arm on this source reproduces the `market` row
above exactly (102 firms, 3,663 operating firm-turns, 1,589.41 inputs, 982
academy, 868.19 household sales, 138.1 loads of free use). Template runs took
9-10 s, procedural 23-26 s. Wares in loads, money in treasury units.

| Rules | Firms opened | Open at 199 / closed idle / other | Operating firm-turns | Produced | Titled | Free use (upper bound) | Household sales (wares delivered) | Academy sales | Inputs paid | Ledger closures failed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 (A3-1) | 102 | 19 / 70 / 13 | 3,663 | 2,371.07 | 2,232.95 | 138.12 | 868.19 (1,419.23) | 982 | 1,589.41 | 0 |
| 2 (A3-2) | 103 | 11 / 84 / 8 | 2,604 | 1,755.50 | 1,755.50 | 0.00 | 352.66 (1,272.11) | 1,084 | 1,345.45 | 0 |

Per world (rules 2): t1 3 firms, 49.2 loads owned, household sales 10.54;
t3 3, 91.8, 27.53; t7 5, 93.1, 24.01; t9 5, 222.2, 15.54 (academy 541);
t11 5, 177.1, 25.60 (academy 406); t23 3, 112.8, 41.77; t42 4, 30.4, 6.03;
p7 13, 161.5, 29.57; p11 10, 92.2, 20.65; p13 12, 227.6, 55.04; p17 14, 190.9,
40.22; p21 10, 127.3, 23.66; p31 16, 179.5, 32.48. No household was priced out
in either arm.

Reading (development-only):

- **No same-tick free use under rules 2**: every operating firm-turn titled its
  whole output (1,755.5 loads), and the people used none of it before a sale;
  under rules 1 the bound was 138.1 loads.
- **Households bought 10% fewer wares but paid 59% less**: 1,272.1 loads for
  352.7 units against 1,419.2 for 868.2. Rules 2 counts the firm's own stock in
  the wares supply that sets the price (as retail counts owned food), so the
  price households paid per load fell from about 0.61 to 0.28. With less
  revenue, firms operated 29% fewer turns, more closed idle (84 against 70) and
  fewer were open at turn 199 (11 against 19). This is reported as found, not
  tuned: the price rule (whether a firm's stock should depress its own price)
  is a modelling choice for the lead and owner, alongside the A3 audit's
  price-margin risk above.
- Every A1 ledger closure held on every observed turn in both arms.
