# Titled trade: merchants buying owned food (A4-1, `--titled-trade`)

Connected-world program, slice A4-1. Default off; requires `--agents hybrid`
and `--household-retail` in mode `retail` or `no_relief` with retail rules
version 2 (`free_exchange` moves no money; `record_only` holds no food).
Design source: the A4 audit
([audit-a4-merchants-owned-cargo.md](../superpowers/audits/connected-world/audit-a4-merchants-owned-cargo.md),
section 5) with the lead's decisions in the plan of record (section 5.7).
Code: `src/chronicler/titled_trade.py` and `src/chronicler/titled_trade_state.py`;
seams in `household_retail.py` (`sell_to_merchant`, `consign`,
`turn_settlement`, the Phase 10 call) and the shared payment seam
`money.py` (pairwise bills). Native: `wealth_transfer::settle_pairs`, the work
category `trade` and the merchant planner skip (one batched build with A3-2,
[workshop economics](workshop-economics.md)). Tests:
`tests/test_titled_trade.py` (offline, chunk `connected-world-a`),
`tests/test_titled_trade_native.py` (compiled extension, native shard 0), the
pairwise cases in `tests/test_money.py`, Rust unit tests in
`wealth_transfer.rs`, `workshop_work.rs` and `merchant.rs`, and the viewer's
`titledTrade` reader and panel tests.

## What it changes

Before A4 a merchant carries only commons goods, paid by nobody, and earns a
model-created income whether or not it carried anything; under household
retail owned food never loads, so a retail-everywhere world moves almost no
food between regions (the audit measured 0 food delivered in 200 turns on one
development world). Under titled trade:

- a merchant **buys owners' surplus food** in a retail pilot region and pays
  each owner directly, by stable id;
- it holds **title and custody** of the cargo as one shipment with a stable id
  while it travels, one region a turn;
- the delivered cargo becomes the merchant's own **retail claim** at the
  destination, which households there buy through the existing settlement;
- while it carries, the merchant's **model income is withheld** (an exact
  per-turn receipt): its margins replace that income, they never stack on it.

## Switch, prerequisites and refusals

- `--titled-trade` (livelihoods switch, `BooleanOptionalAction`), inserted in
  `LIVELIHOODS_SWITCHES` after `workshop_economics` and before
  `wealth_accounting` (the ledger stays last). No modes in A4-1 (food only).
- Refused at startup outside `--agents hybrid`, without `--household-retail`,
  with retail in `free_exchange` or `record_only`, or with
  `--household-retail-rules 1`. A saved world with it on refuses a resume that
  ends retail, leaves hybrid or moves retail to an unsupported mode
  (`LivelihoodsRefusal`, one line) until `--no-titled-trade` is given; an exact
  resume refuses toggling it (`livelihoods_resume_conflicts`).
- Registered in `feature_catalog.REQUIREMENTS` (hybrid, household retail,
  retail mode `retail`/`no_relief`, retail rules `2`) and in
  `batch_manifest.SIMULATION_ARG_KEYS` (omitted while unset; witness layer
  `cwa4`).
- `--no-titled-trade` ends every live shipment `switched_off` with its cargo
  in the commons of the region it stands in, dated.

## Who pays whom

Money in milli-units (1000 = one unit of a person's wealth), food in
milli-food per retail good (grain, fish, salt, botanicals, exotic; 1000 = one
food unit = two rations), prices in milli-units per ration.

| Flow | Payer -> payee | When | Rule |
| --- | --- | --- | --- |
| Cargo purchase (`cargo_purchase`, native purpose 8) | merchant -> each selling owner, by stable id | Phase 10 (inside retail's frame) | one pairwise bill per shipment (batch = shipment id), validated whole against one fresh wealth read before anything moves; each owner paid `ceil(milli x price / ration)` at the origin's retail price this turn |
| Sale of delivered cargo | the destination's households -> the holder, by id | the next tick's provisioning (phase 0.7) | the existing native retail settlement (`food_purchase`, purpose 5); granaries may also buy it (`food_procurement`, purpose 6) |
| Withheld model income | none (no money moves) | the wealth phase of each turn the carrier is reserved | `extend_paid_work` share 1.0: the carrier's whole ordinary income is withheld, with a receipt row (id, share, income, deducted) |

There are **no tolls or fees**. Nothing is minted: the pairwise rows conserve
wealth (the payer loses exactly what the payees gain), and a credit an owner's
wealth ceiling refuses never leaves the merchant (recorded; an owner's offer is
capped by what its ceiling lets it be paid for, so it does not arise in
practice). `cargo_sale` (native purpose 9) is appended for later slices (A4-W
wares, A4-3 timber); A4-1 does not use it and the payment seam refuses it
(no ledger channel), fail-closed.

## Purchase rule

In each pilot origin (ascending region), each eligible carrier (ascending id)
may plan one shipment:

- **Eligible carrier:** an adult (20+) living Merchant resident in the origin,
  not on a native merchant trip, on no army roster, holding no live shipment,
  not a carrier whose shipment closed this turn, and with cash above a reserve
  of `RESERVE_RATIONS` (6) rations at the home price.
- **Owners' offer:** each owner's claim above its **fair-share reserve**
  `OWNER_KEEP` (1,000 milli-food, one turn's two rations), capped by what its
  wealth ceiling lets it be paid for; the merchant's own claim is never on
  offer. Owners sell passively, pro rata to their surplus (largest remainder,
  ties by id), at the price their neighbours paid this turn (a declared
  modelling choice, the granary-procurement precedent).
- **Destinations:** pilot regions with residents within `MAX_HOPS` (3) on this
  turn's agent merchant graph: the graph the native tick receives (diplomacy,
  wars, embargoes, maritime blockades and raid risk, cities cut off by siege or
  occupation), minus quarantine-closed edges (read without touching the
  quarantine receipt). Shortest path, ties to the lower region.
- **Price function:** `p(r, delta) = clamp(D_r / max(S_r + delta, 0.1), 0.5,
  3.0)`, retail's price band over the economy's post-trade food demand and
  supply this turn, read as if `delta` food units had moved; every shipment
  already heading to a market and every earlier plan of this phase counts
  against it (the native planner's tally rule).
- **Quantity:** the largest `q` whose last unit still earns `LOAD_MARGIN`
  (0.25, the native value): `p(d, +q) (1 - d) - p(o, -q) >= 0.25`, `d` being
  the transit decay of the origin pool's goods mix; capped by the path's cargo
  capacity (narrowest leg: land 2, river 5, sea 10 food units, the native
  caps), the owners' offer and the merchant's cash (after its reserve and a
  milli per owner for rounding). Below `MIN_CARGO` (10 milli-food) there is no
  trip. The destination with the largest margin wins (ties to the lower
  region).
- **Purchase:** the claims leave the origin pool pro rata to its goods
  composition (retail flow `sold_merchant`); the bill is quoted first (nothing
  moves when it is refused), then the claims are debited and the owners paid.

## Transport and the declared outcomes

A shipment dispatched in Phase 10 of turn T moves its first edge in Phase 10
of T+1 and arrives in Phase 10 of T+h (h hops); its carrier is reserved for
T+1 ... T+h. Each Phase 10, before purchases, every live shipment (ascending
id) is checked in this order, and exactly one thing happens:

| Situation | Outcome | Books |
| --- | --- | --- |
| The destination's controller changed since dispatch (conquest) | `returned`, cause `destination_conquered`: back to the origin at full value (the native unwind's rule) | the holder's claim at the origin (`returned_in`); the origin's commons if it left the pilot or the claims cap refuses |
| The destination left the retail pilot | `returned`, `destination_left_pilot` | as above |
| A quarantine closure cuts any edge of the remaining route | `returned`, `quarantine_closure` | as above |
| Another edge of the route is gone (war, embargo, blockade, siege) | replanned from where it stands (BFS within `MAX_HOPS`); with no path, `returned`, `route_lost` | as above |
| The next edge is open | it moves one edge; a sea lane with raid risk `r > 0` loses `floor(v x r)` of each good (the native expected loss, deterministic) | `sea_loss` |
| It reaches the destination | `delivered`: transit decay once, `floor(v x rate)` per good (native rates), the rest the holder's claim there (`consigned_in`) | the destination's commons if the claims cap refuses |
| The holder died (seen after each tick and at Phase 2) | `escheated`: the cargo goes to the commons of the region it stands in, recorded | `deposited`, reason `holder_died` |
| A rebuilt native pool | `pool_reset`, cargo to the commons where it stands | `deposited` |
| `--no-titled-trade` | `switched_off`, cargo to the commons where it stands | `deposited` |

Every shipment closes once, and its books close in integers:
`sum(cargo_open) = transit_decay + sea_loss + delivered + returned +
deposited`. "Region of death" is read as the region the cargo stands in: the
carrier stays home in the native pool (below), so its native home would
teleport the cargo.

**Carriers.** A carrier who migrates, changes occupation, enlists, goes on a
native trip or holds other work is **released**: no reservation, no withheld
income; the holder keeps title and the shipment continues. A reserved carrier
on a native trip after the tick is an invariant failure (raises): the native
planner skips `trade` holders.

**War.** War does not reach cargo in transit in A4-1: a shipment standing in
a besieged, occupied or just-conquered region loses nothing (counted,
`war_exempt_turns`). A4-2 applies the A5 war share there.

## Holders' sales

Delivered cargo is the holder's ordinary retail claim (it counts toward
`MAX_CLAIMS` and follows retail's lifecycle: sold, procured, decayed, war
losses, inheritance). Each Phase 10 titled trade reads retail's settlement of
the turn and attributes a holder's sales at a destination where it holds a
delivered lot: sold milli-food from the claim rows (drawn from the lot first),
and the money reproduced exactly from the region's payments split over its
sellers by sold food (largest remainder, ties by id, the native rule) when no
seller there hit the wealth ceiling; otherwise, or when the claim mixed the lot
with other food, the credit is marked approximate. Each lot is then clamped to
what the claim still holds. Granary purchases from holders are counted by id.

## Turn order (rows for the program's turn-order table)

| Order | Point | A4 action |
| --- | --- | --- |
| 1 | Phase 2, `reserve_first` (before every package plans work) | each live shipment's carrier re-checked and reserved under `trade` (whole turn); released carriers and dead holders handled |
| 2 | Phase 2 finish (after the economy tick, after payroll and the RS2/PL1/PL3 extends) | `extend_paid_work(turn, carriers, 1.0)` |
| 3 | tick 0.5 (wealth phase) | carriers' ordinary income withheld (receipt) |
| 4 | tick 0.7 | native provisioning sells holders' claims (purpose 5, credited by id) |
| 5 | tick 0.9 | the native merchant planner skips `trade` holders |
| 6 | after the tick (after retail's settlement) | the shared paid-work receipt read (exact rows); dead holders' cargo escheated |
| 7 | Phase 10: granary procurement (pinned seam) | granaries may buy holders' claims |
| 8 | Phase 10: retail's `phase10`, after its procurement credit and before its frame closes | holders' sales attributed; live shipments moved, returned or delivered; purchases planned and paid; A4's frame committed |
| 9 | Phase 10, last | the A1 ledger reads the money book, the withheld rows and the channels |

## Accounting (each raises when it fails)

- Shipment cargo closes (above); one terminal outcome per shipment; a
  shipment moves at most once a turn; ids are monotone and never reused.
- Retail's owned pool closes per region and owner with the new flow kinds
  (`sold_merchant` -1, `consigned_in` +1, `returned_in` +1); frames record them
  only when nonzero, so frames without titled trade keep their bytes.
- Money: per pairwise row `requested = sent = credited + refunded` (a limited
  payer row is a stale read and raises); the payer's loss is the credited sum;
  `(turn, cargo_purchase, shipment)` settles once in the book and in the native
  key log, across exact resumes.
- Every carrier-turn has one paid-work row at share 1.0.
- **A1 ledger** (`--wealth-accounting`): channel `cargo_purchase` (merchant ->
  owners, both in the household sector: in = out, located at the payees' and
  the payer's own regions; `payer_region` on the flow), closures "merchants
  debited = owners credited" and "owners credited = A4 purchase receipts";
  withheld package `titled_trade` matched row by row to A4's carriers and to
  A4's own exact total. The registries (`WEALTH_WRITERS`, `WEALTH_ROUTERS`
  `_native_pairs`, `MONEY_BILLS` `("titled_trade", "_buy")`,
  `MONEY_PURPOSE_CHANNELS`, `KNOWN_PURPOSES`, `money.MONEY_BOOKS`) fail closed.
  With A4 off and the ledger on, a ledger record differs from one built before
  A4 only in the declared lists `parameters.channels` (ends with
  `cargo_purchase`) and `parameters.withheld_packages` (ends with
  `titled_trade`); no row, closure or lifetime key appears.

## Record (`snapshot.livelihoods.titled_trade`)

```
{schema_version: 1, stage: "A4", goods: "food", source_turn,
 units: {food: "milli_food", money: "milli_units", price: "milli_per_ration", withheld: "wealth_units", milli: 1000},
 shipments: [live Shipment], closed: [last 32 Shipment], lots: [{holder, region, milli, shipments}],
 frame: null | {turn, dispatched: [{shipment, holder, origin, dest, path, milli, cargo, price_milli, paid,
                                     refunded, sellers, seller_rows: [[owner, milli, asked, paid]] (at most 16)}],
                events: [{shipment, event: moved | carrier_released | <outcome>, region, ...}],
                withheld: [{shipment, carrier, share, ordinary, deducted}], withheld_total,
                sales: [{holder, region, sold, cargo_sold, credited, exact}], plans: {...}, live},
 flows: null | [money flows of the source turn], counters, log, log_dropped, parameters}
```

A `Shipment` carries `id, holder, carrier, origin, dest, path, cursor,
controllers, status, dispatched_turn, last_moved_turn, cargo, cargo_open,
cost_milli, price_milli, sellers, losses, delivered, returned, deposited,
deposit_reason, outcome, cause, closed_turn, closed_region, released,
withheld, withheld_turns, war_exempt_turns, history`.

**Viewer:** `viewer/src/lib/titledTrade.ts` (types and a strict reader; the
pinned `types.ts` is not touched) keeps **absent**, **disabled** (a retail
record without this one), **malformed** (wrong shape, a cargo that does not
close, a closed shipment without exactly one declared outcome, a reused id, a
frame whose purchases do not equal their sellers' payments), **unobserved**
(`frame: null`, unknown, not zero) and **observed** (recorded zeros) apart.
`TitledTrade.tsx`, in the Livelihoods panel, shows shipments in transit (id,
holder, carrier or why it was released, route, position, cargo, what the
owners were paid, income withheld), the turn's purchases (owners -> merchant,
food, price, paid by id), outcomes with their causes, holders' sales, and a
lifetime funnel with the merchants' net money against the income withheld.
The household-retail reader accepts the three new flow kinds in its closure.

## Native change (one batched build with A3-2)

- `wealth_transfer.rs`: `PURPOSES` appends `cargo_purchase` (8) and
  `cargo_sale` (9) (append-only, nothing renumbered); `settle_pairs(pool,
  turn, purpose, batch, rows)`: pairwise purposes only; the whole call
  validated before any change (payer != payee, no repeated pair, no id both
  payer and payee, `0 < amount <= MAX_ROW_MILLIS`, key not in the log); per row
  ABSENT for a dead or unknown party, else `sent = min(amount, what the payer
  still holds)`, `credited = min(sent, the payee's room)`; each person's net
  change applied once after every row (no f32 drift between rows); no trip
  rule.
- `workshop_work.rs`: `RESERVATION_CATEGORIES` appends `trade` (4) and
  `trade_holders(pool, turn)`.
- `merchant.rs` (pinned): the planner skips this turn's `trade` holders (an
  empty set without such rows: bit-identical).
- `ffi/mod.rs` (pinned): `settle_pairs` and `work_reservation_categories`.
- No checkpoint layout change: reservations, the paid share and the key log are
  transient.

## Declared parameters (modelling choices, not calibrated)

| Name | Value | Meaning |
| --- | --- | --- |
| `OWNER_KEEP` | 1,000 milli-food | each owner's fair-share reserve, never sold |
| `RESERVE_RATIONS` | 6 | rations at the home price a carrier keeps in cash |
| `LOAD_MARGIN` | 0.25 | the price gap each unit must earn (native) |
| `MIN_CARGO` | 10 milli-food | the smallest trip (native) |
| `MAX_HOPS` | 3 | the longest planned route |
| cargo caps | land 2, river 5, sea 10 food units | per trip, narrowest leg (native) |
| `TRANSIT_DECAY` | grain 0.05, fish 0.08, salt 0, botanicals 0.04, exotic 0.06 | once, on arrival (native) |
| `MAX_SHIPMENTS` | 64 | live shipments world-wide |

## Declared limits (A4-1)

- Carriers stay home in the native pool (PL1's boundary): no packets,
  epidemic contact or food demand travel with them; titled shipments carry no
  trade-channel contact (C1/A4-2).
- Prices within `MAX_HOPS` are known at once (omniscient, as the native
  bootstrap without packets; A6 brings dated information).
- War does not reach cargo in transit (counted); A4-2 adds requisition and
  seizure through the A5/D4/C1 hooks.
- Trips to or from non-pilot regions stay legacy native commons trips with
  model income (the remaining model share, declared).
- Food only; timber (A4-3) and wares (A4-W, after A3-2) are later slices.
- Withheld income lowers a merchant's income in the native occupation and
  migration choices: carriers may switch occupation in transit (observed on a
  development world: released, title kept).
- Holders' sales are attributed by id (exact unless a claim mixes a lot with
  other food or a seller hit the ceiling: marked approximate).
- No toll exists: any toll must replace the model route income (owner's
  decision).

## Verification

On branch `claude/cw-a4-titled-trade` from `main` `8401aa74`, source `9c6c66ee`
(the code commit; later commits on the branch change tests and documents
only), native extension built once from this branch (`maturin develop
--release --locked`, native venv `~/.venvs/native-a4`): SHA-256
`2ba123ab259b98cb2b2e66edef4852015c40cbc73172a3b6d2d265d9c2aa950b`;
`check_python_env.py --expect native` PASS; `wealth_transfer_purposes()` ends
`wares_purchase, cargo_purchase, cargo_sale`, `work_reservation_categories()`
ends `trade`.

- **Witness**: one provisional layer `cwa4` against `main`'s bytes (parent
  `8401aa74`, the last layer after `cwa3`) over the five pinned paths changed
  (`batch_manifest.py` 2 hunks, `tests/test_batch_manifest.py` 1,
  `economy.rs` 7, `ffi/mod.rs` 7, `merchant.rs` 2; every hunk read: only this
  slice's changes): the witness modules 509 passed.
- **Feature-off identity** (`turn_speed_identity.py`, each side its own
  exported tree and extension): against the reference `8abc1acb` (`101a4cd5`),
  9 cases, 399 files, 0 differences. Against `main` `8401aa74` (extension
  `20e77f99`) with retail everywhere (`--grain-reserves
  --public-grain-shipments --food-allocation --household-retail
  --household-retail-boundary=all`) on `hybrid_s42` and `proc48_hybrid_s42`:
  the switch absent and the explicit `--no-titled-trade` each 2 cases, 205
  files, 0 differences.
- **A3-1 reproducibility** (workshop economics without the A3-2 rules) against
  `main` `8401aa74` with `--grain-reserves --public-grain-shipments
  --grain-storage --workshops --workshop-payroll --workshop-economics` on the
  same two cases: the rules option absent and the explicit
  `--workshop-economics-rules=1` each 205 files, 0 differences.
