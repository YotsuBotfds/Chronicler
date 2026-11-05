# Workshop payroll with an actual public customer (L6a, `--workshop-payroll`, default off)

Sprint 2 of the livelihoods/commons plan
([plan](../superpowers/roadmaps/livelihoods-commons-sprint2.md), lane "finance").
L6a builds a bounded, debt-free transactional layer around the actual L1 workshop
([workshops](workshops.md)). It is not a general finance rewrite. Household food
purchases (L6b) are a later wave and are not started here.

`--workshop-payroll` requires `--workshops` in operate mode (`--agents hybrid`).
Its customer is academy supply procurement, so sales need `--scholarship
--techniques --academy-services`. Without academies no firm ever opens and the run
is identical to `--workshops` alone (a native test checks this).

Modes (`--workshop-payroll-mode`):

| Mode | Sells | Pays wages | Replaces the crew's ordinary income share | Purpose |
| --- | --- | --- | --- | --- |
| `paid` (default) | yes | yes | yes | the mechanism |
| `unpaid_labor` | yes | no | yes | cost-retaining ablation: an unpaid job harms |
| `no_customer` | no | owed | yes | demand-collapse control: no receipts, so payroll pressure |

## Accounts and identities

Each operating L1 site may have one firm (`WorkshopPayrollState.firms`, keyed by the
L1 site id; at most four open, eight closed kept). A firm holds:

- **working cash**, in whole milli-units: 1000 milli-units are one treasury unit and
  one unit of native agent wealth. Domestic credit already treats one treasury unit
  as one wealth unit; this lane reuses that equivalence. Cash starts at 0 and is
  never negative: no borrowing, no rescue, and no firm or agent is ever placed in
  finance's civilization-borrower field.
- **owned wares**, in milli-loads;
- **wages owed** to named workers (stable native ids, at most 16 claims);
- **hours** (0.25–1) and a **crew cap** (1–8) for the next crew request;
- bounded lifetime **totals** and a 16-event dated **history**.

The firm belongs to the site. Like the L1B asset's arrears, it follows the site
through a change of controller. Region = index in `world.regions`; civilization =
index in `world.civilizations`; academy seat = index in `world.scholarship.seats`.

### Opening around an order

A firm opens when its site operates (L1B funded, built, crewed) and an academy has
an open order. An open order comes from last turn's procurement of an academy whose
ruler controls the site's region. That procurement must have been fully informed
(upkeep paid; counts, price and commitments known), must have left unmet need
(`min(learners, 8 × scholars) − held_after > 0`) and must have left budget for at
least one unit. Until then the site stays an L1B public workshop: no title, no
deduction, no wage (counter `operating_without_order`). Once open, a firm keeps
operating after its customer disappears. That is the demand-collapse path below.

### Title (pilot custodian rule)

The native economy puts this turn's craft output into the region's shared stock.
The same tick's wares use by the people, merchant departures, 1% wear and the stock
cap then draw on that stock. While the site operates, the whole region's craft
output is its crew's, because L1 replaces the region's craft ceiling with the
site's. After the successful tick the firm takes title to `min(output, uncommitted
region stock, inventory room)`. Uncommitted stock is stock minus merchant
commitments (`read_stockpile_commitments`, as academy procurement uses). Exactly
that quantity leaves `region.stockpile.goods["crafts"]` and enters the firm's
inventory, so wares are never counted twice. What the region's market used first
is not titled, and older shared stock never becomes the firm's. The native merchant
planner then sees the reduced stock, because `sync_regions` runs after Phase 2.

### Customer

The only existing public purchaser of crafts is academy supply procurement
(`learning_services.procure_learning_supplies`, byte-pinned, not edited). After
that Phase 10 procurement has run, the firm offers its wares to that turn's fully
informed academies of its region's ruler, in seat order:

- **need:** `min(learners, 8 × scholars) × 1 − held`, with `held` read after the
  academy's own market purchases and earlier deliveries;
- **price:** the craft price the academy's own procurement used;
- **budget:** the ruler's projected treasury (`_treasury_budget`, accumulator-aware).

A sale settles in whole treasury units. The ruler's treasury pays (`keep`) and the
firm's cash receives the same amount. The wares those units buy at that price,
rounded down to a milli-load, move from the firm's inventory into the academy's
material inventory (`held` and `purchased_total` rise together). Those units are
never more than the firm holds or the academy needs. Payment and delivery settle
together, so no refunds exist. Delivery within the realm is a declared
simplification: no transport time or loss. The academy's material balance still
reconciles.

### Wages replace the ordinary income share

Paid time is each crew member's scheduled diverted time: the L1 city share
`d = 1 − URBAN_FARM_LABOR[rank]` times the firm's hours. Hours reach the L1 planner
through `workshops._crew_terms`, which requests `d × hours` per person and the crew
cap. In Phase 2 finish the firm arms the native **paid-work income share**
(`AgentSimulator.install_paid_work`) for exactly those rows. Each row must already
hold a workshop reservation of at least that fraction in the shared work registry.
The next native wealth phase removes that share of each person's ordinary
occupational income and records the actual amount (`take_paid_work_receipt`).
Model-provided ordinary income is therefore replaced, never stacked under a wage.
The workshop receipt's `affected_ordinary_income_share` reports the share.

In Phase 10, after sales, each firm owes `WAGE_PER_WORK × share` per worker this turn
plus any earlier arrears. It pays from cash only, pro rata when short (largest
remainder, ties by id), with one `AgentSimulator.transfer_wealth` call per firm and
turn. Then:

- **Wealth ceiling.** What the ceiling refuses stays in the firm's cash. The receipt
  records it; it is not owed.
- **Death.** A worker who died receives nothing, and the claim lapses (`owed_lapsed`).
  Dead workers' claims lapse before cash is shared, so scarce cash is split pro rata among
  the living only (the living set is read once per turn from the native snapshot after
  the tick). A lead review on 2026-11-05 found the first landing shared cash with the
  dead and left a dead claim with a zero share owed; corrected with a regression test.
  A second review on the same day found that a firm liquidated in Phase 2 (its city fell)
  cached the pre-tick living set for the turn, so other firms' Phase 10 wages again shared
  scarce cash with workers who died in the tick. Phase 10 now reads the living afresh
  (`tests/test_livelihoods_work_authority.py`).
  Wages already paid are ordinary wealth and pass through native inheritance like
  any other wealth. No claim survives into an estate: estates of claims are not
  modeled.
- **Shortfall.** Unpaid wages stay owed (arrears) and are paid first from later cash.
- **Migration.** A worker who migrates stays owed by id. They leave next turn's crew
  only because the L1 planner no longer resolves them.

### Pressure, layoffs and closure

A turn that ends with wages owed is insolvent:

- **Hours.** They fall by `HOURS_STEP` for the next turn, down to `MIN_HOURS`.
- **Layoffs.** From the `LAYOFF_AFTER`-th insolvent turn in a row, the crew cap falls
  by `LAYOFF_STEP` (minimum 1).
- **Closure.** After `CLOSE_AFTER` insolvent turns in a row the firm closes. Its L1
  site then closes with the new reason `insolvent`, and the city is never
  readmitted.

A solvent turn whose cash covers the next turn's bill at one step better terms
restores one step of hours and one crew place. Cash above `RESERVE_TURNS` full wage
bills is distributed to the region's controller as a `keep` credit. In
`unpaid_labor` mode there is no wage bill, so there is no reserve.

**Liquidation at any closure** (insolvency, or the L1 site's city falling, vanishing
or changing region):

- the firm pays wages owed from cash, unless it already paid this turn;
- it writes off what remains owed;
- it returns its inventory to the region's market stock;
- it distributes its cash to the region's controller in whole units;
- it writes off the sub-unit remainder, or all of the cash when no civilization
  controls the region, to a named sink.

### Typed transfers and closure

Each turn's frame records the typed transfers (`state.money`, `state.materials`;
at most 512 of each, last turn only). Each has an id, phase, payer/payee or
source/destination account (kind, identity), amount, applied, residual and status.

- **Money:** `sale` (civ treasury → workshop cash), `wage` (workshop cash → agent
  wealth), `distribution` (workshop cash → civ treasury) and `write_off` (workshop
  cash → sink).
- **Materials:** `title` (region market → workshop inventory), `delivery` (workshop
  inventory → academy inventory), `wear` (workshop inventory → sink, `WARES_WEAR` =
  the native crafts storage rate) and `return` (workshop inventory → region market).

Every firm closes exactly in integers, and `check_firm` raises otherwise:

```
cash      = sales − wages applied − distributions − write-offs − stipends   (opening 0)
inventory = titled − delivered − worn − returned
per turn: cash_close = cash_open + sales − wages_paid − distributed − written_off − stipends
          inventory_close = inventory_open + titled − sold − worn − returned
```

`stipends` (RS1, [apprenticeship](apprenticeship.md)) is absent, and so zero, unless
`--apprenticeship` paid one: `pay_from_firm` pays apprentices from cash after the
turn's payroll pass under transfer purpose 2 (`apprentice_stipend`), records a typed
`stipend` money transfer (workshop cash → agent wealth), the firm's
`totals["stipends"]` and the receipt's optional `stipends` (with `cash_close` net of
it).

The f32 agent wealth receives `applied / 1000`. The books are exact in
milli-units; the native wealth matches them to f32 precision (a test checks within
2·10⁻⁵ per transfer).

## Native seams (shared; L7 reuses the transfer)

`chronicler-agents/src/wealth_transfer.rs`:

- **`AgentSimulator.transfer_wealth(turn, purpose, batch, rows)`**.
  - `rows` is `[(stable id, signed milli-units)]`. Credits are positive and debits
    negative.
  - It returns `[(id, requested, applied, residual, status)]`, with status 0 applied
    in full, 1 limited by the wealth ceiling (credit) or by the holder's wealth
    (debit), and 2 absent (dead or unknown id: nothing applied).
  - Per row, `applied + residual == requested`. A credit never raises wealth above
    `MAX_WEALTH`; a debit never takes it below zero.
  - Validation happens before mutation, all or none: unknown purpose, duplicate ids,
    `|amount| > 10¹²`.
  - Each `(turn, purpose, batch)` key applies once. A repeated key, or one for an
    earlier turn, is refused unchanged. The key log is transient and never
    checkpointed; Python records its own last settled turn (`last_payroll_turn`),
    which survives exact checkpoints.
  - Purposes are append-only (`wealth_transfer_purposes()`: `["workshop_wage"]`). L7
    appends its own and chooses its own batch keys.
  - The cached snapshot is dropped when wealth changed. No RNG.
- **`install_paid_work(turn, rows)`** arms `[(id, share)]`, share in (0, 1]. Each row
  must be a living id holding a work reservation of at least `share` for `turn`, and
  only one arming may be pending.
  - `cancel_paid_work()` drops an unconsumed arming.
  - `take_paid_work_receipt()` returns `(turn, [(id, share, ordinary income,
    deducted)])` once.
  - The native tick refuses an arming dated for another turn.
  - The wealth phase consumes the arming once, with stable-id guards against a
    reused slot. It applies the deduction after any teaching reservation and before
    the care observer's base-income copy (the teaching precedent). Unarmed turns are
    unchanged.

All three pool fields (`paid_work`, `paid_work_receipt`, `wealth_transfer_log`) are
`transient` in the persisted layout, so the checkpoint wire format and schema are
unchanged.

## Declared parameters (modeling choices, not calibrated)

| Name | Value | Meaning |
| --- | --- | --- |
| `WAGE_PER_WORK` | 500 milli-units | wage for one person's whole turn of paid time (0.5 treasury/wealth unit) |
| `INVENTORY_CAP` | 20 000 milli-loads | most wares one firm holds; title stops beyond it |
| `WARES_WEAR` | 0.01 / turn | wear of held wares (native crafts storage rate) |
| `HOURS_STEP`, `MIN_HOURS` | 0.25, 0.25 | hours cut per insolvent turn and floor |
| `LAYOFF_AFTER`, `LAYOFF_STEP` | 2, 2 | insolvent turns in a row before crew cuts, places cut per turn |
| `CLOSE_AFTER` | 6 | insolvent turns in a row that close the firm |
| `RESERVE_TURNS` | 4 | full wage bills kept before distributing cash to the owner |
| units | 1000 milli = 1 treasury unit = 1 wealth unit | equivalence domestic credit already uses |

Farmer ordinary income is about `0.3 × modifiers` a turn. A rank-2 crew member
(d = 0.3) therefore gives up about 0.09 and earns 0.15 when paid in full.

## Evidence

### Tests

- `tests/test_workshop_payroll.py` (offline, 15 tests, native stand-in). It covers:
  - sales funding wages, with every account closing and buyer, academy and treasury
    flows matching;
  - title bounded by output, uncommitted stock and the cap;
  - a site without an order staying a public workshop;
  - the no-customer chain: hours cut, then crew cut, then closure, with owed wages
    written off and wares returned;
  - unpaid labour harming the crew while sales are distributed to the owner;
  - paid against unpaid crew wealth;
  - a wealth-ceiling residual kept in cash, and a dead worker's claim lapsing;
  - partial fills paid first from later cash, and the pro-rata arithmetic;
  - conquest moving the customer and the owner while the firm keeps its books;
  - a city's fall liquidating the firm once;
  - a failed native arming moving nothing, and rollback cancelling an armed share;
  - once-per-turn settlement and exact pickle/JSON round trips continuing
    identically;
  - unchanged workshop requests without payroll;
  - dated snapshots, prerequisites and modes.
- `tests/test_workshop_payroll_native.py` (real extension, 4 tests). It covers:
  - a 90-turn seed-1 run in which every wage transfer is checked against the live
    pool's wealth before and after, the repeated key is refused unchanged, and every
    paid-work deduction equals share × ordinary income;
  - every firm and receipt closing, and the academy material balance residual 0;
  - payroll without an order equalling the run without payroll, history and final
    state alike;
  - exact checkpoint resume at turn 76 with open firms, giving identical history,
    world state and state file;
  - the transfer contract on a live pool: credit, ceiling, debit, absent, duplicate,
    purpose, replay and paid-work refusal outside a reservation.
- `cargo test --locked --lib wealth_transfer` (5 tests). These cover limits and
  residuals, keys, absent ids, reservation-bound arming, and the wealth phase
  consuming once with the next turn unchanged. The whole library: 680 passed.
- Viewer: `viewer/src/lib/workshopFinance.ts` and
  `viewer/src/components/systems/WorkshopFinance.tsx` are a strict reader that
  refuses records that do not close, and a component. 7 vitest tests; lint clean.
  The component is not yet mounted in the shared Livelihoods panel (lead-owned).

### Development runs

These are template seeds 1–3, 200 turns, one world each. The flags were `--agents
hybrid --grain-reserves --public-grain-shipments --scholarship --techniques
--academy-services --workshops`, plus the arm. This is a funnel description, not
evidence of an effect. Money is in treasury units.

| Arm | Seed | Firms | Operating site-turns | Firm-turns with customer | Sales paid (units) | Wages due / paid | Owed written off / lapsed | Ordinary income replaced | Crew net (wages − replaced) | Insolvent firm-turns / closures | Distributed to owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| paid | 1 | 2 | 137 | 150 | 33 (98) | 33.15 / 32.92 | 0 / 0.23 | 17.34 | +15.59 | 6 / 0 | 63 |
| unpaid_labor | 1 | 2 | 157 | 154 | 35 (68) | 0 / 0 | 0 / 0 | 21.74 | −21.74 | 0 / 0 | 68 |
| no_customer | 1 | 3 | 18 | 0 | 0 | 2.55 / 0 | 2.55 / 0 | 0.87 | −0.87 | 18 / 3 | 0 |
| paid | 3 | 3 | 60 | 62 | 11 (14) | 14.10 / 11.00 | 3.00 / 0.10 | 2.53 | +8.47 | 23 / 3 | 3 |
| unpaid_labor | 3 | 4 | 241 | 165 | 33 (125) | 0 / 0 | 0 / 0 | 33.49 | −33.49 | 0 / 0 | 125 |
| no_customer | 3 | 3 | 14 | 0 | 0 | 2.00 / 0 | 2.00 / 0 | 0.52 | −0.52 | 18 / 3 | 0 |

**Seed 2.** No academy appears, so no order exists and no firm opens in any arm. All
four arms, including `--workshops` alone, give the same world.

**Seed 1.**

- Firms opened at turn 70, around the region-1 academy's orders. The paid arm
  titled 34.9 loads and delivered 33.6; the unpaid arm titled 59.0 and delivered 45.6.
- Sales funded the wages, with the rest distributed back to the owner.
- In the paid arm the crew received about 1.9 times the ordinary income their
  workshop time replaced. In the unpaid arm they lost all of it.

**Seed 3.**

- Wares output was small (raw-input bound), so revenue could not carry the wage
  bill.
- All three paid firms went insolvent, cut hours and crew, and closed. Three units
  of wages were written off.
- Even so, the crew's net was positive.

**`no_customer` (both seeds).** Payroll pressure appeared at once:

- 18 insolvent firm-turns, then nine hours cuts and twelve layoffs;
- three closures within about six operating turns;
- every owed wage written off.

A matched-cohort wealth comparison was computed: the crew of the first firm turn,
traced across arms. Trajectories diverge after the first firm turn, and deaths and
migration shrink the cohort to one to six people, so it is too confounded to report
as an effect.

Not run: the held cohort (301–306, 401–406), interaction screens, a browser journey
and PR CI. Feature-off identity against the sprint-1 head and the 200-seed gate
were not run either.

## Limits and open work

- **Single customer.** The only customer is academy procurement of the same ruler.
  Where no academy exists there are no sales: seed 2 never opens a firm. A municipal
  or guild customer would need a new purchaser, not a relabeled sink.
- **Wage arrears.** Wages owed die with the worker. Estates of claims are not modeled.
- **Ordering.** The firm sells after academy procurement, so the academy buys from
  the shared market first. Title happens after the same tick's market use.
- **Book precision.** Books are exact in milli-units. Native wealth is f32.
- **Shared-file edits.** The witness layers for the pinned shared files edited here
  (`ffi/mod.rs`, `tick.rs`, `pool.rs`, `lib.rs`, `batch_manifest.py`) are the lead's.
  The sprint witness test fails until that layer exists.
- **Not wired in.** The new test modules need shard and CHUNKS enrollment, and the
  viewer component needs mounting.
