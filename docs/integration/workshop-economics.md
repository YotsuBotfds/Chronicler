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

All on 2026-11-06, source `ed9c0972` unless noted, native extension built from
this branch (`maturin develop --release --locked`, native venv
`~/.venvs/native-a3`): SHA-256
`2831bbd4953311b87cfa208c751f7745f9bf7740335ae8f39029b1b0c33c7630`;
`check_python_env.py --expect native` PASS. The Rust differs from `8abc1acb`
only by the appended purpose (a later commit changed one assertion inside the
Rust test module, which the built extension does not contain).

- **Focused offline tests**: `tests/test_money.py` (19), `tests/test_workshop_economics.py`
  (20), with `tests/test_wealth_accounting.py`, `test_workshop_payroll.py`,
  `test_feature_catalog.py`, `test_batch_manifest.py`,
  `test_livelihoods_sprint_witness.py` and `test_native_ci_shards.py`: 358 passed.
- **Witness**: provisional layer `cwa3` (parent `fee5de7f`, 3 hunks, only the
  added keys); the witness modules of the playbook: 509 passed.
- **Bounded offline lane** (`run_python_oracle_checks.py`, 110-second limit
  kept): PASS, 64 chunks in 257.6 s; slowest chunk `systems-2` 32.9 s;
  `connected-world-a` 3.9 s (67 tests).
- **Native tests** (real extension): `test_workshop_economics_native.py` (3:
  every transfer checked against the live pool before and after and a repeated
  key refused, input charges against native `craft_input` x the tick price,
  no craft output at firm-less sites, every ledger closure, exact resume at
  turn 116 before two idle closures and a city fall, exact resume at turn 76
  inside wage arrears before an insolvent closure) with the wealth-accounting,
  payroll, recovery-skills, retail, apprenticeship, relocation, remittance and
  closure native modules: 76 passed.
- **`cargo test --locked`**: 743 library tests and every integration target
  passed.
- **Feature-off identity** (`turn_speed_identity.py`, each side its own
  exported tree and extension; the preceding integrated `main` is the
  reference `8abc1acb`): 9 cases, 399 files compared, 0 differences (head 73 s).
  With the prerequisites on (`--grain-reserves --public-grain-shipments
  --grain-storage --workshops --workshop-payroll`) on `hybrid_s42` and
  `proc48_hybrid_s42`: the switch absent and the explicit
  `--no-workshop-economics` each 2 cases, 205 files, 0 differences against the
  reference. The appended native purpose changes no output.
- **Enabled exact resume**: `checkpoint_identity.py` (run from the branch with `PYTHONPATH`
on its `src`, extension `2831bbd4…`) with the checkpoint-3 chain
(`--grain-reserves --public-grain-shipments --scholarship --techniques
--academy-services --grain-storage --food-allocation --workshops
--operating-wear --repair-projects --timber-stock --household-retail
--household-retail-boundary=paid_work --timber-supply --recovery-crews
--remittances`) plus `--workshop-payroll --workshop-economics
--wealth-accounting`: `hybrid_s42_long` PASS at all 19 resume points (two firms
open at turn 52, one closes idle at 59, the other runs to 199: 8 resume points
inside a live firm; the ledger's continuity exact on 199 turns, no closure
failed) and `proc32_hybrid_s11` PASS at 10 chosen points (21: the opening turn;
22-30: firms buying inputs and selling to households; 33 and 35: live idle
runs; 36: the turn three firms close idle; 38: after); writing checkpoints
changed nothing in either case.
- **Viewer**: the new reader, component and L6a-reader tests 13 passed; the
  full suite 1,462 passed with 5 timeouts at 5 s under a load average of 7-9 on
  4 shared cores, all 5 (4 files, 112 tests) passing on a serial rerun; lint
  clean; production build succeeded.
- **Not run**: a held screen (CW2 is planned after A3-2, audit section 7), a
  browser journey, the 200-seed and procedural qualification gates
  (restricted), profiling at the declared scale, PR CI.

## Evidence (development worlds only; not a screen)

Development-only, 2026-11-06: source `ed9c0972` (exported tree), native
extension `2831bbd4…` (this branch's build); no preregistration, no held seed,
no 7xx/8xx seed. One run per world and mode, 200 turns, flags `--agents hybrid
--grain-reserves --public-grain-shipments --scholarship --techniques
--academy-services --workshops --workshop-payroll --workshop-economics
--wealth-accounting` plus the mode; procedural worlds add `--worldgen
procedural --regions 32 --civs 10`. This describes activation, not an effect.
Money in treasury units; "survival" is turns from opening to closure (or to
turn 199 for a firm still open); "household sales" is the paid non-academy
demand. Template 7 x 3 runs took 7-9 s each, procedural 6 x 3 took 17-19 s
each (4 shared cores under load).

| Mode | Worlds active / run | Firms opened | Closed idle / insolvent / city fell / open at 199 | Median survival of closed firms (template; procedural) | Operating firm-turns | Inputs paid | Inputs not charged (control) | Academy sales | Household sales | Owner capital paid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `market` | 13 / 13 | 141 (28 template, 113 procedural) | 99 / 0 / 22 / 20 | 70; 19 | 3,059 | 2,153.1 | 0 | 755 | 573.7 | 2,820 |
| `free_inputs` | 13 / 13 | 91 (27; 64) | 5 / 43 / 14 / 29 | 27.5; 39 | 4,440 | 0 | 28,050.4 | 861 | 641.6 | 1,820 |
| `academy_only` | 13 / 13 | 180 (27; 153) | 165 / 0 / 4 / 11 | 14; 14 | 1,543 | 2,629.8 | 0 | 729 | 0 | 3,600 |

Every one of the 39 runs: every A1 ledger closure held on every observed turn
(0 failures), and no household was priced out (`priced_out_households` 0: at the
craft prices the economy computed, a resident's 0.01 load costs a few
milli-units). Same-tick free use of firm output (`free_use_upper_bound`) was
43.6 / 71.2 loads (market, template / procedural); the paid-share rule left
96.9 / 137.7 loads of conversion in the commons (price discovery and tick
prices above the plan).

Reading (development-only):

- **Most firms close.** Under `market` 99 of 141 firms closed idle (their input
  budget ran out); none closed insolvent, because a firm reserves this turn's
  wages before it buys inputs, so its crew shrinks with its cash instead of
  running arrears. The 22 city-fell closures are conquest and city loss.
- **The input charge is what kills them** (the price-margin risk): with inputs
  free the same worlds' firms convert far more and would have owed 28,050 units
  at the tick's raw prices (13x what `market` firms actually paid, because
  `market` firms' production is bounded by what they can pay); firms there run
  wages into arrears and close insolvent (43) or survive to turn 199 (29).
- **Household demand matters to survival.** Without household customers
  (`academy_only`) firms close idle after a median 14 turns in both world kinds,
  and their sites are replaced by new ones (180 openings, each with fresh
  capital at a new city; a closed city is never readmitted).
- Household sales were real paid demand in every world (573.7 units under
  `market`), 43% of firms' sales (100% in worlds without academy purchases).

Per world (`t` template, `p` procedural):

| World | Mode | Firms opened | Survival median (turns) | Survival range | Ending (closed reason / open at 199) | Operating firm-turns | Inputs paid (units) | Academy sales | Household sales (paid non-academy demand) | Household share | Ledger closures failed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1 | market | 3 | 70 | 22-87 | city_fell 1, idle 2 | 122 | 51.1 | 0.0 | 28.45 | 1.00 | 0 |
| t1 | free_inputs | 3 | 103 | 57-152 | city_fell 1, open@199 2 | 251 | 0.0 | 28.0 | 50.61 | 0.64 | 0 |
| t1 | academy_only | 3 | 15 | 14-28 | idle 3 | 32 | 41.2 | 6.0 | 0.00 | 0.00 | 0 |
| t3 | market | 4 | 98.0 | 55-115 | city_fell 2, idle 2 | 234 | 55.5 | 0.0 | 63.17 | 1.00 | 0 |
| t3 | free_inputs | 3 | 49 | 20-163 | insolvent 2, open@199 1 | 188 | 0.0 | 0.0 | 31.19 | 1.00 | 0 |
| t3 | academy_only | 3 | 16 | 12-18 | idle 3 | 27 | 23.5 | 0.0 | 0.00 | - | 0 |
| t7 | market | 4 | 50.5 | 27-117 | city_fell 1, idle 3 | 152 | 68.0 | 0.0 | 35.28 | 1.00 | 0 |
| t7 | free_inputs | 4 | 64.5 | 12-172 | insolvent 4 | 280 | 0.0 | 4.0 | 37.73 | 0.90 | 0 |
| t7 | academy_only | 5 | 11 | 10-13 | idle 4, open@199 1 | 23 | 57.4 | 5.0 | 0.00 | 0.00 | 0 |
| t9 | market | 5 | 36 | 13-126 | idle 3, open@199 2 | 196 | 143.8 | 334.0 | 13.41 | 0.04 | 0 |
| t9 | free_inputs | 5 | 93 | 26-134 | city_fell 2, insolvent 3 | 338 | 0.0 | 291.0 | 27.42 | 0.09 | 0 |
| t9 | academy_only | 5 | 30 | 16-70 | city_fell 1, idle 4 | 100 | 116.7 | 112.0 | 0.00 | 0.00 | 0 |
| t11 | market | 5 | 89 | 39-144 | city_fell 1, idle 4 | 290 | 65.7 | 224.0 | 57.35 | 0.20 | 0 |
| t11 | free_inputs | 5 | 27 | 13-99 | city_fell 1, insolvent 3, open@199 1 | 149 | 0.0 | 174.0 | 10.14 | 0.06 | 0 |
| t11 | academy_only | 4 | 13.5 | 8-21 | idle 4 | 26 | 27.2 | 0.0 | 0.00 | - | 0 |
| t23 | market | 4 | 68.5 | 40-113 | city_fell 2, idle 2 | 207 | 41.1 | 0.0 | 53.74 | 1.00 | 0 |
| t23 | free_inputs | 3 | 24 | 21-25 | insolvent 3 | 69 | 0.0 | 0.0 | 4.83 | 1.00 | 0 |
| t23 | academy_only | 4 | 13.5 | 11-32 | idle 4 | 40 | 26.0 | 0.0 | 0.00 | - | 0 |
| t42 | market | 3 | 53 | 16-98 | idle 2, open@199 1 | 139 | 81.4 | 57.0 | 20.86 | 0.27 | 0 |
| t42 | free_inputs | 4 | 68.5 | 3-162 | idle 1, open@199 3 | 220 | 0.0 | 0.0 | 45.20 | 1.00 | 0 |
| t42 | academy_only | 3 | 8 | 7-13 | idle 3 | 8 | 47.8 | 0.0 | 0.00 | - | 0 |
| p7 | market | 20 | 20.5 | 10-96 | city_fell 4, idle 13, open@199 3 | 303 | 234.9 | 112.0 | 30.27 | 0.21 | 0 |
| p7 | free_inputs | 10 | 60.5 | 18-140 | city_fell 3, idle 1, insolvent 3, open@199 3 | 452 | 0.0 | 60.0 | 75.80 | 0.56 | 0 |
| p7 | academy_only | 29 | 14 | 3-85 | idle 26, open@199 3 | 264 | 433.4 | 173.0 | 0.00 | 0.00 | 0 |
| p11 | market | 17 | 11 | 6-62 | city_fell 1, idle 13, open@199 3 | 165 | 299.3 | 12.0 | 30.35 | 0.72 | 0 |
| p11 | free_inputs | 9 | 58 | 8-126 | city_fell 1, idle 1, insolvent 3, open@199 4 | 441 | 0.0 | 11.0 | 31.87 | 0.74 | 0 |
| p11 | academy_only | 10 | 16.5 | 7-55 | city_fell 1, idle 9 | 105 | 112.8 | 23.0 | 0.00 | 0.00 | 0 |
| p13 | market | 15 | 21 | 0-177 | idle 12, open@199 3 | 321 | 221.8 | 1.0 | 81.14 | 0.99 | 0 |
| p13 | free_inputs | 13 | 22 | 8-153 | city_fell 2, idle 1, insolvent 7, open@199 3 | 498 | 0.0 | 10.0 | 78.12 | 0.89 | 0 |
| p13 | academy_only | 26 | 14.5 | 2-101 | city_fell 1, idle 23, open@199 2 | 267 | 420.5 | 179.0 | 0.00 | 0.00 | 0 |
| p17 | market | 20 | 16.0 | 7-160 | city_fell 3, idle 14, open@199 3 | 333 | 315.3 | 8.0 | 61.29 | 0.88 | 0 |
| p17 | free_inputs | 11 | 33 | 7-136 | city_fell 3, insolvent 4, open@199 4 | 454 | 0.0 | 189.0 | 60.36 | 0.24 | 0 |
| p17 | academy_only | 32 | 12.0 | 5-45 | idle 31, open@199 1 | 248 | 547.6 | 134.0 | 0.00 | 0.00 | 0 |
| p21 | market | 14 | 39.5 | 10-127 | city_fell 4, idle 8, open@199 2 | 351 | 142.1 | 7.0 | 58.46 | 0.89 | 0 |
| p21 | free_inputs | 8 | 86.0 | 25-178 | idle 1, insolvent 3, open@199 4 | 521 | 0.0 | 93.0 | 90.46 | 0.49 | 0 |
| p21 | academy_only | 19 | 19 | 8-53 | idle 19 | 206 | 261.0 | 97.0 | 0.00 | 0.00 | 0 |
| p31 | market | 27 | 18 | 2-69 | city_fell 3, idle 21, open@199 3 | 246 | 433.1 | 0.0 | 39.94 | 1.00 | 0 |
| p31 | free_inputs | 13 | 46 | 25-93 | city_fell 1, insolvent 8, open@199 4 | 579 | 0.0 | 1.0 | 97.88 | 0.99 | 0 |
| p31 | academy_only | 37 | 10 | 0-41 | city_fell 1, idle 32, open@199 4 | 197 | 514.6 | 0.0 | 0.00 | - | 0 |
