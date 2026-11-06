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

## Boundaries and declared limits (slice A3-1)

- **Same-tick free use.** The tick's craft output enters the commons before
  title, so the people's draw and same-tick merchant departures can still take
  part of the firm's new output free when the commons does not already cover
  them (recorded per firm-turn as `free_use_upper_bound`; A3-2's native
  owned-output column ends it).
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
M1 readmitted cities, M2 the cost control, M3 the viewer, minors m1-m5), on
source `9c9d10f7` unless noted, native extension built from this branch
(`maturin develop --release --locked`, native venv `~/.venvs/native-a3`):
SHA-256 `2831bbd4953311b87cfa208c751f7745f9bf7740335ae8f39029b1b0c33c7630`
(the review fixes changed no Rust, so no rebuild); `check_python_env.py
--expect native` PASS. The Rust differs from `8abc1acb` only by the appended
purpose (plus one assertion inside its test module).

- **Focused offline tests**: `tests/test_money.py` (22) and
  `tests/test_workshop_economics.py` (25), with the ledger, payroll, workshops,
  feature-catalog, batch-manifest, witness and shard tests: all passed.
- **Witness**: provisional layer `cwa3` unchanged (no pinned file changed in
  the review fixes).
- **Bounded offline lane** (110-second limit kept): PASS, 64 chunks in 236.9 s;
  slowest chunk `systems-2` 28.1 s; `connected-world-a` 5.6 s (75 tests).
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
  tree and extension; the reference `8abc1acb` is also the current `main`): 9
  cases, 399 files compared, 0 differences. With the prerequisites on
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
  --wealth-accounting`: `hybrid_s42_long` PASS at all 19 resume points (two firms
  open at turn 52 and close idle; 6 resume points inside live firms; the ledger's
  continuity exact on 199 turns) and `proc32_hybrid_s11` PASS at 14 points
  (21-30: openings, input purchases, household sales; 33 and 35: live idle runs;
  36: an idle closure; 38: after); writing checkpoints changed nothing.
- **Viewer**: the full suite with `--maxWorkers=1`: 149 files, 1,470 tests
  passed; lint clean; production build succeeded.
- **Not run**: a held screen (CW2 is planned after A3-2, audit section 7), a
  browser journey, the 200-seed and procedural qualification gates
  (restricted), profiling at the declared scale, PR CI.

## Evidence (development worlds only; not a screen)

Development-only, 2026-11-06: source `9c9d10f7` (exported tree; the
plan-price rule after review; before re-check n1, which also counts turns that
operate and convert nothing toward idle, so firms in regions without raw stock
may close earlier than shown; not rerun), native extension `2831bbd4…` (this branch's
build); no preregistration, no held seed, no 7xx/8xx seed. One run per world
and mode, 200 turns, flags `--agents hybrid --grain-reserves
--public-grain-shipments --scholarship --techniques --academy-services
--workshops --workshop-payroll --workshop-economics --wealth-accounting` plus
the mode; procedural worlds add `--worldgen procedural --regions 32 --civs
10`. This describes activation, not an effect. Money in treasury units;
"survival" is turns from opening to closure (or to turn 199 for a firm still
open); "household sales" is the paid non-academy demand. Template runs took
7-9 s, procedural 16-19 s (4 shared cores under load). An earlier run of the
same matrix on `ed9c0972` (the tick-price rule the review rejected) is
superseded and kept only in the evidence directory.

| Mode | Worlds active / run | Firms opened | Closed idle / insolvent / city fell / open at 199 | Median survival of closed firms (template; procedural) | Operating firm-turns | Inputs paid | Inputs not charged (control) | Academy sales | Household sales | Owner capital paid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `market` | 13 / 13 | 92 (24 template, 68 procedural) | 62 / 0 / 13 / 17 | 85; 48 | 3,781 | 1,627.9 | 0 | 1,130 | 867.8 | 1,840 |
| `free_inputs` | 13 / 13 | 69 (27; 42) | 24 / 0 / 10 / 35 | 69; 60 | 5,199 | 0 | 4,792.4 | 1,269 | 841.5 | 1,380 |
| `academy_only` | 13 / 13 | 113 (29; 84) | 106 / 0 / 2 / 5 | 16; 18 | 2,055 | 1,800.6 | 0 | 1,602 | 0 | 2,260 |

Every one of the 39 runs: **nothing was converted unpaid** (`converted_unpaid`
0 on every receipt), **no city received a second firm** (every firm's
settlement id distinct; `opening_refused_closed_city` 0 because L1 never
readmitted one), every A1 ledger closure held on every observed turn (0
failures), no opening was refused for want of a price and the realm fallback
was never needed (each site's region had a positive raw price from before the
site operated), and no household was priced out (`priced_out_households` 0).
The input need firms could not pay for and left in the commons
(`unbought_need`) was 8,240.5 loads under `market`. Same-tick free use of firm
output (`free_use_upper_bound`) was 148.6 loads under `market`.

Reading (development-only):

- **Most firms close, but more slowly than the rejected tick-price rule
  suggested.** Under `market` 62 of 92 firms closed idle and 17 were still open
  at turn 199; none closed insolvent (wages are reserved before inputs, so a
  firm's crew shrinks with its cash instead of running arrears). Median
  survival of closed firms was 85 turns in template worlds and 48 in procedural
  ones.
- **The input charge shortens lives; it is not the whole story.** With every
  other rule identical, `free_inputs` firms closed idle 24 times (of 69) and 35
  were open at turn 199; their uncharged input cost was 4,792 units (they keep
  their cash and so buy more inputs each turn than `market` firms, which paid
  1,628).
- **Household demand matters to survival.** Without household customers
  (`academy_only`) firms close idle after a median 16-18 turns and new sites
  open at other cities (113 openings, each at a different city: no city is
  readmitted).
- Household sales were real paid demand in every world: 867.8 units under
  `market`, 43% of firms' sales (100% in worlds without academy purchases).

Per world (`t` template, `p` procedural):

| World | Mode | Firms opened | Survival median (turns) | Survival range | Ending (closed reason / open at 199) | Operating firm-turns | Inputs paid | Inputs not charged | Academy sales | Household sales | Household share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1 | market | 3 | 57 | 28-82 | city_fell 1, idle 2 | 132 | 44.7 | 0.0 | 0.0 | 33.51 | 1.00 |
| t1 | free_inputs | 3 | 87 | 13-152 | city_fell 1, open@199 2 | 211 | 0.0 | 188.3 | 34.0 | 38.93 | 0.53 |
| t1 | academy_only | 3 | 35 | 14-60 | idle 3 | 78 | 47.5 | 0.0 | 21.0 | 0.00 | 0.00 |
| t3 | market | 3 | 122 | 85-142 | city_fell 1, idle 2 | 287 | 82.4 | 0.0 | 44.0 | 71.32 | 0.62 |
| t3 | free_inputs | 4 | 63.0 | 6-178 | idle 3, open@199 1 | 254 | 0.0 | 206.7 | 8.0 | 41.58 | 0.84 |
| t3 | academy_only | 3 | 16 | 11-16 | idle 3 | 25 | 22.7 | 0.0 | 0.0 | 0.00 | - |
| t7 | market | 4 | 89.0 | 65-103 | idle 4 | 268 | 86.2 | 0.0 | 23.0 | 70.03 | 0.75 |
| t7 | free_inputs | 5 | 79 | 13-172 | city_fell 1, idle 2, open@199 2 | 393 | 0.0 | 486.8 | 30.0 | 78.68 | 0.72 |
| t7 | academy_only | 5 | 12 | 11-32 | idle 5 | 49 | 65.1 | 0.0 | 36.0 | 0.00 | 0.00 |
| t9 | market | 5 | 37 | 13-115 | idle 4, open@199 1 | 173 | 216.0 | 0.0 | 466.0 | 19.64 | 0.04 |
| t9 | free_inputs | 5 | 69 | 52-167 | city_fell 1, idle 2, open@199 2 | 349 | 0.0 | 338.5 | 329.0 | 28.81 | 0.08 |
| t9 | academy_only | 6 | 40.5 | 17-61 | idle 6 | 146 | 178.8 | 0.0 | 184.0 | 0.00 | 0.00 |
| t11 | market | 4 | 106.0 | 85-174 | city_fell 1, idle 3 | 322 | 50.4 | 0.0 | 0.0 | 62.73 | 1.00 |
| t11 | free_inputs | 5 | 103 | 24-143 | idle 2, open@199 3 | 407 | 0.0 | 151.5 | 215.0 | 38.16 | 0.15 |
| t11 | academy_only | 5 | 19 | 9-69 | city_fell 1, idle 4 | 92 | 35.4 | 0.0 | 287.0 | 0.00 | 0.00 |
| t23 | market | 3 | 113 | 85-178 | city_fell 1, idle 1, open@199 1 | 297 | 56.0 | 0.0 | 0.0 | 87.58 | 1.00 |
| t23 | free_inputs | 3 | 70 | 26-178 | city_fell 1, idle 1, open@199 1 | 237 | 0.0 | 127.6 | 0.0 | 35.57 | 1.00 |
| t23 | academy_only | 4 | 15.0 | 10-20 | idle 4 | 36 | 21.9 | 0.0 | 0.0 | 0.00 | - |
| t42 | market | 2 | 35.5 | 33-38 | idle 2 | 32 | 27.9 | 0.0 | 0.0 | 20.55 | 1.00 |
| t42 | free_inputs | 2 | 118.5 | 97-140 | idle 1, open@199 1 | 186 | 0.0 | 88.6 | 0.0 | 17.28 | 1.00 |
| t42 | academy_only | 3 | 13 | 13-55 | idle 3 | 44 | 27.7 | 0.0 | 0.0 | 0.00 | - |
| p7 | market | 14 | 29.5 | 10-168 | city_fell 3, idle 8, open@199 3 | 401 | 163.8 | 0.0 | 43.0 | 83.21 | 0.66 |
| p7 | free_inputs | 5 | 168 | 66-178 | city_fell 1, open@199 4 | 523 | 0.0 | 450.0 | 211.0 | 89.94 | 0.30 |
| p7 | academy_only | 13 | 18 | 10-143 | idle 13 | 287 | 282.6 | 0.0 | 253.0 | 0.00 | 0.00 |
| p11 | market | 11 | 32 | 5-101 | city_fell 2, idle 6, open@199 3 | 289 | 149.4 | 0.0 | 14.0 | 63.93 | 0.82 |
| p11 | free_inputs | 7 | 90 | 24-142 | city_fell 2, idle 2, open@199 3 | 410 | 0.0 | 353.2 | 28.0 | 57.92 | 0.67 |
| p11 | academy_only | 8 | 29.0 | 13-119 | idle 7, open@199 1 | 234 | 209.6 | 0.0 | 194.0 | 0.00 | 0.00 |
| p13 | market | 9 | 71 | 6-177 | idle 6, open@199 3 | 432 | 120.3 | 0.0 | 184.0 | 102.85 | 0.36 |
| p13 | free_inputs | 9 | 55 | 21-177 | idle 5, open@199 4 | 520 | 0.0 | 607.5 | 105.0 | 79.62 | 0.43 |
| p13 | academy_only | 19 | 16 | 9-62 | idle 17, open@199 2 | 290 | 220.6 | 0.0 | 107.0 | 0.00 | 0.00 |
| p17 | market | 10 | 42.0 | 4-142 | city_fell 1, idle 8, open@199 1 | 386 | 203.8 | 0.0 | 206.0 | 83.30 | 0.29 |
| p17 | free_inputs | 8 | 71.5 | 40-175 | city_fell 3, idle 1, open@199 4 | 558 | 0.0 | 571.8 | 159.0 | 95.81 | 0.38 |
| p17 | academy_only | 16 | 22.0 | 8-97 | city_fell 1, idle 14, open@199 1 | 326 | 239.3 | 0.0 | 185.0 | 0.00 | 0.00 |
| p21 | market | 9 | 38 | 6-144 | city_fell 2, idle 6, open@199 1 | 355 | 217.5 | 0.0 | 150.0 | 74.98 | 0.33 |
| p21 | free_inputs | 5 | 178 | 60-178 | idle 1, open@199 4 | 586 | 0.0 | 596.4 | 98.0 | 96.15 | 0.50 |
| p21 | academy_only | 12 | 22.0 | 13-109 | idle 11, open@199 1 | 289 | 285.6 | 0.0 | 335.0 | 0.00 | 0.00 |
| p31 | market | 15 | 38 | 5-147 | city_fell 1, idle 10, open@199 4 | 407 | 209.5 | 0.0 | 0.0 | 94.12 | 1.00 |
| p31 | free_inputs | 8 | 66.5 | 18-177 | idle 4, open@199 4 | 565 | 0.0 | 625.6 | 52.0 | 143.03 | 0.73 |
| p31 | academy_only | 16 | 14.5 | 8-33 | idle 16 | 159 | 163.7 | 0.0 | 0.0 | 0.00 | - |
