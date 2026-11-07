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
id) is checked in this order, and exactly one thing happens (a dead holder
and a released carrier are checked first, then the route):

| Situation | Outcome | Books |
| --- | --- | --- |
| The carrier was released: it migrated, changed occupation, enlisted, went on a native trip or holds other work (seen at Phase 2 `reserve_first` and again before each move) | `released_returned`, cause the release reason: halted and back to the origin at once at full value, under the same unwind rule (lead decision, review M3) | as `returned` below: the holder's claim at the origin (`returned_in`); the origin's commons if it left the pilot or the claims cap refuses |
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

**Commons deposits (review M1).** Every deposit (`escheated`, `pool_reset`,
`switched_off`, a refused claim) goes through retail's seam
`household_retail.deposit_commons`, which writes the region's commons and
marks the region in retail's books for the turn. A deposit made in Phase 2
before the economy tick (a pool reset, or a dead holder seen at
`reserve_first`) lands after the region batch was built; retail's
`prepare_phase2`, which runs after `reserve_first`, patches the marked
regions' commons columns into that batch, so the economy starts from commons
that hold the cargo (the same seam retail uses for its own closures).

**Carriers take no native decision while reserved** (lead decision after the
review's re-check). A carrier is natively idle at home, so before this rule it
took the native decisions every tick and could switch occupation or migrate
in transit (the reviewer measured 4.9% occupation switches and 7.3%
migrations per reserved carrier-turn on development worlds 9 and 1, close to
other idle merchants' 5.9% and 5.0%: the decisions read the region's
occupational balance and food pressure, not the withheld income). The tick
now passes the turn's `trade` holders to the decisions
(`DecisionOptions::trade_carriers`): they are skipped exactly as merchants on
a native trip (no migration, occupation switch, rebellion or loyalty change),
and household consolidation does not move them as a migrating spouse's
follower (as trip merchants). Region stats and population tallies still count
them; they still die (the cargo escheats), and they decide again from the
turn after their shipment closes (only live shipments' carriers are
reserved). Without titled trade the set is empty and nothing changes (the
identity runs below). **RNG:** the decisions draw from one stream per region
and turn (`ChaCha8`, stream = region, turn and the decision offset), each
deciding agent in slot order; a skipped carrier draws nothing, so in a
titled-trade run the later agents of its region take different draws that
turn. Runs without titled trade draw exactly as before.

**Releases.** A carrier who nevertheless migrates or changes occupation (not
through the native decisions: none was observed on development worlds 1 and
9 after the rule), enlists, goes on a native trip or holds other work is
**released**, and its shipment ends
`released_returned` at once: the cargo goes back to the origin at full value
(the unwind rule) and the holder keeps title there as a retail claim. No cargo
moves without a reserved carrier, and the holder's new ordinary income never
stacks with a margin (the shipment ends at the release, so no margin follows). A
reserved carrier on a native trip after the tick is an invariant failure
(raises): the native planner skips `trade` holders.

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
| 1 | Phase 2, `reserve_first` (before every package plans work) | each live shipment's carrier re-checked and reserved under `trade` (whole turn); a released carrier's shipment returned to the origin, a dead holder's cargo escheated (both deposits patched into the batch by retail's `prepare_phase2`) |
| 2 | Phase 2 finish (after the economy tick, after payroll and the RS2/PL1/PL3 extends) | `extend_paid_work(turn, carriers, 1.0)` |
| 3 | tick 0.5 (wealth phase) | carriers' ordinary income withheld (receipt) |
| 3a | tick decisions and household consolidation | `trade` holders take no decision and follow no migrating spouse (as merchants on a native trip) |
| 4 | tick 0.7 | native provisioning sells holders' claims (purpose 5, credited by id) |
| 5 | tick 0.9 | the native merchant planner skips `trade` holders |
| 6 | after the tick (after retail's settlement) | the shared paid-work receipt read (exact rows); dead holders' cargo escheated |
| 7 | Phase 10: granary procurement (pinned seam) | granaries may buy holders' claims |
| 8 | Phase 10: retail's `phase10`, after its procurement credit and before its frame closes | holders' sales attributed; carriers re-checked (a release returns the shipment); live shipments moved, returned or delivered; purchases planned and paid; A4's frame committed |
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
  key log, across exact resumes. The one-sided native `transfer` refuses the
  pairwise purposes 8 and 9: they are paid only through `settle_pairs`. A
  money book pickled before the pairwise fields existed loads with
  `payer_region` None (exact pickle restoration bypasses defaults, so the book
  models backfill missing fields) and checks as before.
- Every carrier-turn has one paid-work row at share 1.0.
- **A1 ledger** (`--wealth-accounting`): channel `cargo_purchase` (merchant ->
  owners, both in the household sector: in = out, located at the payees' and
  the payer's own regions; `payer_region` on the flow), and three closures:
  "merchants' measured wealth loss = owners' measured wealth gain (live pool)"
  and "owners' measured wealth gain = owners credited (payment seam)" compare
  wealth read from the live pool before and after each payment (each purchase
  row records `measured_payer_loss` and `measured_payees_gain`; f32 balances,
  so within `1e-4 + 1e-5` per person) with what the seam credited,
  independently of the receipts (review); "owners credited = A4 purchase
  receipts" ties the seam to A4's frame;
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
                                     refunded, sellers, seller_rows: [[owner, milli, asked, paid]] (at most 16),
                                     measured_payer_loss, measured_payees_gain}],
                events: [{shipment, event: moved | <outcome>, region, ...}],
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
(`frame: null`, unknown, not zero) and **observed** (recorded zeros) apart;
a `released_returned` shipment must name a release reason as its cause.
`TitledTrade.tsx`, in the Livelihoods panel, shows shipments in transit (id,
holder, carrier or why it was released, route, position, cargo, what the
owners were paid, income withheld), the turn's purchases (owners -> merchant,
food, price, paid by id), outcomes with their causes (a released carrier's
return with its reason), holders' sales, and a lifetime funnel (released and
returned shipments by reason) with the merchants' net money against the
income withheld.
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
  rule. The one-sided keyed `transfer` refuses purposes 8 and 9 (review).
- `workshop_work.rs`: `RESERVATION_CATEGORIES` appends `trade` (4) and
  `trade_holders(pool, turn)`.
- `merchant.rs` (pinned): the planner skips this turn's `trade` holders (an
  empty set without such rows: bit-identical).
- `ffi/mod.rs` (pinned): `settle_pairs`, `work_reservation_categories` and
  `economy_capabilities` (A3-2's startup check).
- `behavior.rs`, `tick.rs` (pinned) and `household.rs` (pinned; carrier rule,
  after the review): the tick passes `trade_holders(pool, turn)` to the
  decisions (`DecisionOptions::trade_carriers`, `None` when empty); a carrier
  is skipped like a merchant on a native trip and listed in
  `PendingDecisions::trade_carriers`, which household consolidation reads so
  it does not move the carrier as a spouse's follower.
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
- Carriers take no native decision while reserved (above), as merchants on a
  native trip; a carrier enlisted by a war roster or holding other work is
  still released and its shipment returns.
- Holders' sales are attributed by id (exact unless a claim mixes a lot with
  other food or a seller hit the ceiling: marked approximate).
- No toll exists: any toll must replace the model route income (owner's
  decision).

## Verification

### Carrier rule (2026-11-07, after the review's re-check)

The reviewer approved `d5ccd4d6` and found the release rate a modelling defect
inside a declared boundary; the lead's decision is the rule above (carriers
take no native decision while reserved). Code commit `9591e280`. Native
extension rebuilt twice for it (the first build left household consolidation
moving carriers as followers of a migrating spouse; the second exempts them as
trip merchants), `CARGO_INCREMENTAL=0 maturin develop --release --locked`, final
SHA-256 `43cbd22ac4e7e2c6a77e71781a884be5342f41aa4173ff6f43e0facf0f5e0eb0`
(the intermediate build `f55b18b6…` is superseded).

- **`cargo test --locked --no-fail-fast`** once, on the final Rust, without
  debug info: 1,325 tests in 40 targets passed (adds
  `titled_carriers_take_no_decision_while_reserved_and_an_empty_set_changes_nothing`:
  carriers make no migration, switch, rebellion or loyalty decision and are
  listed; an empty set leaves every decision and the stream unchanged); the
  target was deleted at once.
- **Identity** (head `9591e280`, extension `43cbd22a…`): feature-off against
  the reference `8abc1acb`, 9 cases, 399 files, 0 differences; against `main`
  `bac45cb5` (extension `20e77f99`) with retail everywhere, titled trade absent
  and `--no-titled-trade`, 205 files each, 0 differences; A3-1 (rules option
  absent and `=1`), 205 files each, 0 differences.
- **Witness**: `cwa4` regenerated against `main` `bac45cb5`, now eight pinned
  paths (adds `tick.rs` 3 hunks and `household.rs` 2 hunks); every hunk read;
  the witness modules 40 passed.
- **Native**: `tests/test_titled_trade_native.py` 8 passed. The new test runs
  template seed 1 for 200 turns and checks every reserved carrier-turn: no
  carrier changes occupation or region during a tick it is reserved for (a
  development probe without the ledger counted 165 and 547 reserved
  carrier-turns on seeds 1 and 9 and 0 changes, against 2 and 10 follower
  migrations on the first build), only that turn's
  carriers hold `trade`, former carriers change occupation or region again
  after their shipment closes, carriers still die and their cargo escheats,
  and no carrier is released. Exact resume equals the straight run with a
  shipment in transit at turns 52 (moving), 80 (its holder dies next tick) and
  85 (its route is lost on the last hop).
- **Development rerun** (below): 0 releases in 13 worlds.

### Review round (2026-11-07)

After the independent review (changes requested, no blocker: M1 commons
deposits in Phase 2, M2 the A3-2 capability guard and reconciliation, M3 the
lead's released-carrier rule, minors m1-m7 and the nits), on the branch after
merging `main` `bac45cb5` (PR #90; `66e1ec40`, PR #89, before it). Code commit
`3b82ca18`, merge `0f384a9b`. Native extension rebuilt once with every Rust
change (`CARGO_INCREMENTAL=0 maturin develop --release --locked`, native venv
`~/.venvs/native-a4`): SHA-256
`5ca9f24e865bb7b0feeba314099c5e4f045431b14d27d327b105fe4f00de28f4`;
`check_python_env.py --expect native` PASS; `economy_capabilities()` is
`[workshop_owned_crafts]`. `main` has no Rust change since `8401aa74`, so its
side uses extension `20e77f99`.

- **Witness**: `cwa4` regenerated against `main` `bac45cb5` as the last layer
  (`LAYERS` ends `"cwd2", "cwb2", "cwa4"`), now six pinned paths:
  `batch_manifest.py` 2 hunks, `tests/test_batch_manifest.py` 1, `economy.rs`
  7, `ffi/mod.rs` 7 (adds `economy_capabilities`), `merchant.rs` 2 and
  `src/chronicler/economy.py` 1 (keeps `workshop_owned_outflow`); every hunk
  read. The witness modules: 40 passed (53 subtests).
- **Feature-off identity** (`turn_speed_identity.py`, each side its own
  exported tree and extension; head = `0f384a9b`): against the reference
  `8abc1acb`, 9 cases, 399 files, 0 differences. Against `main` `bac45cb5`
  with retail everywhere on `hybrid_s42` and `proc48_hybrid_s42`: titled trade
  absent and the explicit `--no-titled-trade` each 205 files, 0 differences.
- **A3-1 reproducibility** against `main` `bac45cb5` (the A3 flags above, the
  same two cases): the rules option absent and `--workshop-economics-rules=1`
  each 205 files, 0 differences.
- **`cargo test --locked --no-fail-fast`** once, without debug info
  (`CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0`,
  `CARGO_INCREMENTAL=0`): 1,324 tests in 40 targets (762 library tests)
  passed, including `transfer` refusing purposes 8, 9 and 10; the target
  (939 MB) was deleted at once.
- **Offline**: `tests/test_titled_trade.py` 32 (adds a pool reset and a death
  inside Phase 2 that reach the batch, a migrated carrier and an occupation
  change in the tick that return the shipment, title kept, and a later carrier
  buying a surplus the first could not), `tests/test_money.py` 34 (adds an
  old-pickle book), `tests/test_workshop_economics.py` 37 (adds the A3-2
  stale-extension refusal at startup, resume and run time, the per-turn
  reconciliation, the closed-site column and the liquidation record). The
  feature-catalog and feature-matrix sentinels stand in for a current
  extension (A3-2's capability is the build's, not a catalog requirement).
- **Bounded offline lane** (110-second limit kept): PASS in 281.9 s, 70
  chunks, slowest `systems-2` 30.2 s; `connected-world-a` 6.1 s (131 tests).
- **Native** (real extension, 22 modules: titled trade, workshop economics,
  payroll, workshops, wealth accounting, the three retail modules,
  recovery skills, apprenticeship (both), attribution records, closure,
  quarantine (both), recovery crews, relocation, remittances, repair, timber
  stock and supply, watershed): 134 passed. `test_titled_trade_native.py`
  adds the M1 check on the real extension (a forced pool reset and a holder's
  death at `reserve_first` after the batch was built: the batch the economy
  receives equals the world's commons including the cargo, and differs from
  the batch as built) and the refused one-sided transfer; exact resume equals
  the straight run with a shipment in transit at turns 52 (moving), 55 (its
  carrier changes occupation: `released_returned`) and 59 (its holder dies).
  The A3-2 native test asserts that `reconcile_owned` ran on every turn with
  owned regions against `workshop_owned_outflow`.
- **Viewer**: the full suite (`--maxWorkers=2`): 163 files, 1,614 passed, 2
  skipped; lint clean; `tsc -b` and the production build succeeded.
- **Development activation** (below): rerun on this source.

### First pass

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
- **Rust** (in the `cargo test --locked` run below): `settle_pairs`
  (validation before mutation: purpose, payer = payee, repeated pair, an id on
  both sides, range, repeated or older key; the payer limited at its wealth;
  the payee's ceiling refused back to the payer; dead and unknown parties
  ABSENT; parties on a merchant trip paid; each net change applied once
  without f32 drift; conservation), the category list and `trade_holders`, and
  the planner skip (reserved merchants never planned; other turns' reservations
  and other categories leave the planner bit-identical).
- **Offline** (no native extension): `tests/test_titled_trade.py` (27: the
  registry, invalid combinations refused before any change, a saved world's
  refused resume, feature-off, surplus-only pro rata purchases at the local
  price paid by id, the margin bisection, no cash/no offer, title and custody
  exactly once through purchase, transit, delivery and sale with the holder
  credited by id, goods closure every turn, exact withholding of the carrier's
  income, each declared outcome once (conquest, death, quarantine closure, a
  lost route and a released carrier, pool reset, switch-off), sea loss and a
  refused claim, never-reused ids, repeated Phase 10/settlement and key
  refused, the ledger's identity and closures with and without A4, exact
  pickle/JSON round trips with a shipment in transit continuing identically,
  the dated record); `tests/test_money.py` (33, eleven for pairwise bills);
  with the ledger, retail, workshop, feature-catalog, feature-matrix,
  batch-manifest, shard and witness modules: 624 passed.
- **Native** (real extension): `tests/test_titled_trade_native.py` (template
  seed 1, retail everywhere, 80 turns, `CHRONICLER_CHECK_RESOURCES=1`: every
  pairwise payment checked against the live pool and its repeated key refused
  unchanged; every shipment's cargo closes; one outcome per shipment; every
  carrier-turn one receipt row at share 1.0; carriers never planned on native
  trips; every ledger closure held; exact resume equals the straight run at
  turns 52 (a shipment halfway along two hops), 55 (carriers in transit
  released the next turn) and 61 (the holder dies in the next tick)), with the
  workshop-economics, wealth-accounting, retail, recovery-skills,
  apprenticeship, relocation, remittance, timber-supply, closure, payroll,
  repair, recovery-crew and quarantine native modules: 121 tests, 120 passed
  and 1 failed (`test_workshop_payroll_native.py` used purpose code 9 as the
  unknown code; 9 is now `cargo_sale`: changed to 10, then passed).
- **Viewer**: the full suite with `--maxWorkers=2` on a loaded machine: 1,594
  passed, 2 skipped, 4 failed on the 5-second test timeout (two `AppShell` and
  two feature-option files); those four files rerun with `--maxWorkers=1`: 44
  passed. Lint clean; `tsc -b` and the production build succeeded.
- **`cargo test --locked`** (the passing run, `--no-fail-fast`): 762 library tests
  and all 40 targets passed (1,324 tests). It ran with
  `CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0` (no debug info; the
  same code): a first run with debug info filled the disk (the target reached
  8.2 GB with 8.3 GB free; the linker died with a bus error) and a second
  found two wrong assertions in the Rust tests (code 9, now `cargo_sale`, used
  as the unknown purpose; an older `settle_pairs` key of another batch expected
  refused), both fixed in the test module only (commit `3995c1ee`; the compiled
  extension is unchanged: no line outside `mod tests` moved).
- **Bounded offline lane** (110-second limit kept, default output directory,
  commit `f37308a9`): PASS in 326.1 s, 69 chunks, slowest `systems-2` 36.9 s;
  `connected-world-a` 7.2 s (121 tests).
- **Not run**: a held screen (CW5, template 771-776 and procedural 871-876,
  reserved), a `record_only` mode (not built in A4-1: a later control arm), a
  browser journey, `checkpoint_identity.py` all-switch cases (exact resume is
  covered by the native CLI tests above), the 200-seed and procedural
  qualification gates (restricted), profiling at the declared scale, PR CI.

## Evidence (development worlds only; not a screen)

### With the carrier rule (carriers take no decision while reserved)

Development-only, 2026-11-07: commit `9591e280`, extension `43cbd22a…`; the
same 13 worlds, flags and 200 turns as below, `CHRONICLER_CHECK_RESOURCES=1`
(no resource problem raised). Template runs took 9-10 s, procedural 23-31 s.

| World | Shipments | Delivered / returned / escheated / live at 199 | Routes (cross-civ shipments) | Food bought from owners (paid) | Delivered | Sold to buyers (credited) | Merchants' net money | Income withheld (carrier-turns) | Released and returned | Ledger closures failed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1 | 92 | 83 / 4 / 5 / 0 | 12 (65) | 83.94 (43.70) | 72.43 | 63.83 (73.92) | 30.22 | 3.655 (164) | 0 | 0 |
| t3 | 120 | 114 / 0 / 4 / 2 | 12 (81) | 161.99 (86.19) | 149.55 | 113.11 (116.32) | 30.13 | 2.905 (178) | 0 | 0 |
| t7 | 168 | 158 / 0 / 4 / 6 | 31 (145) | 194.46 (103.25) | 173.85 | 149.60 (168.47) | 65.22 | 7.863 (294) | 0 | 0 |
| t9 | 343 | 327 / 0 / 15 / 1 | 29 (99) | 450.03 (238.64) | 411.48 | 356.85 (385.54) | 146.90 | 36.152 (543) | 0 | 0 |
| t11 | 125 | 120 / 0 / 5 / 0 | 8 (65) | 106.06 (55.50) | 96.84 | 89.92 (132.39) | 76.89 | 8.053 (207) | 0 | 0 |
| t23 | 123 | 111 / 1 / 5 / 6 | 12 (123) | 194.23 (100.44) | 168.97 | 151.07 (204.54) | 104.10 | 1.717 (173) | 0 | 0 |
| t42 | 119 | 103 / 15 / 1 / 0 | 10 (35) | 137.02 (71.60) | 109.42 | 102.82 (116.16) | 44.55 | 0.496 (148) | 0 | 0 |
| p7 | 624 | 584 / 3 / 33 / 4 | 166 (556) | 854.58 (445.83) | 754.40 | 630.53 (850.60) | 404.77 | 47.168 (1,311) | 0 | 0 |
| p11 | 544 | 500 / 1 / 34 / 9 | 137 (481) | 680.88 (354.31) | 586.09 | 458.23 (567.23) | 212.92 | 49.571 (1,080) | 0 | 0 |
| p13 | 1,066 | 987 / 12 / 37 / 30 | 199 (913) | 1,494.54 (778.79) | 1,335.81 | 1,089.02 (1,416.23) | 637.44 | 110.122 (2,208) | 0 | 0 |
| p17 | 795 | 728 / 8 / 44 / 15 | 142 (623) | 1,095.55 (571.30) | 965.16 | 779.86 (953.52) | 382.21 | 68.210 (1,503) | 0 | 0 |
| p21 | 761 | 698 / 17 / 39 / 7 | 142 (695) | 1,042.97 (543.91) | 919.23 | 794.48 (1,141.21) | 597.30 | 62.418 (1,514) | 0 | 0 |
| p31 | 752 | 707 / 0 / 31 / 14 | 167 (584) | 1,112.66 (589.34) | 996.21 | 805.12 (995.43) | 406.08 | 119.426 (1,570) | 0 | 0 |
| all | 5,632 | 5,220 / 61 / 257 / 94 | 1,067 (4,465) | 7,608.91 (3,982.82) | 6,739.44 | 5,584.45 (7,121.55) | 3,138.74 | 517.755 (10,893) | 0 | 0 |

Reading (development-only):

- **No carrier was released** in 13 worlds (0 of 5,632 shipments; 1,521 of
  6,241 returned after a release under the previous rule, 711 releases that
  continued in the first pass). Shipments end by cause: 5,220 delivered
  (92.7%), 59 returned for a lost route and 2 for a conquered destination, 257
  escheated at the holder's death, 94 live at turn 199.
- **Merchants' margins exceed the withheld income**: buyers paid holders
  7,121.6 for titled cargo bought from owners for 3,982.8 (net +3,138.7, close
  to the first pass's +3,254.5), against 517.8 of model income withheld over
  10,893 carrier-turns. Development observation, not an effect estimate (CW5
  measures it).
- Of 7,608.9 food units bought, 6,739.4 were delivered as holders' claims,
  323.4 decayed in transit, 80.3 returned to origins and 332.2 went to commons
  (escheat or refused claims); every A1 ledger closure held.

### After the review (released carriers return)

Development-only, 2026-11-07: merge `0f384a9b` (review fixes, `main`
`bac45cb5`), extension `5ca9f24e…`; the same 13 worlds, flags and 200 turns as
the first-pass table below, `CHRONICLER_CHECK_RESOURCES=1` (no resource
problem raised). Template runs took 8-10 s, procedural 23-31 s.

| World | Shipments | Delivered / returned / escheated / live at 199 | Routes (cross-civ shipments) | Food bought from owners (paid) | Delivered | Sold to buyers (credited) | Merchants' net money | Income withheld (carrier-turns) | Released and returned | Ledger closures failed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1 | 114 | 75 / 1 / 7 / 2 | 13 (83) | 148.86 (81.55) | 93.72 | 80.72 (121.22) | 39.67 | 1.272 (192) | 29 | 0 |
| t3 | 123 | 104 / 0 / 1 / 0 | 12 (103) | 138.57 (72.93) | 115.89 | 88.63 (105.49) | 32.56 | 6.821 (183) | 18 | 0 |
| t7 | 172 | 121 / 3 / 3 / 3 | 23 (122) | 179.77 (93.04) | 127.37 | 109.72 (139.56) | 46.52 | 9.252 (252) | 42 | 0 |
| t9 | 336 | 260 / 0 / 14 / 4 | 26 (78) | 425.46 (218.98) | 308.82 | 264.21 (278.60) | 59.62 | 31.118 (538) | 58 | 0 |
| t11 | 151 | 114 / 0 / 2 / 0 | 15 (94) | 188.97 (96.59) | 143.68 | 130.02 (162.40) | 65.81 | 7.862 (242) | 35 | 0 |
| t23 | 107 | 85 / 0 / 8 / 1 | 14 (106) | 158.06 (84.11) | 119.55 | 106.75 (161.61) | 77.50 | 4.211 (155) | 13 | 0 |
| t42 | 135 | 110 / 6 / 2 / 0 | 11 (35) | 191.13 (98.02) | 155.41 | 136.80 (165.99) | 67.98 | 0.765 (168) | 17 | 0 |
| p7 | 711 | 491 / 2 / 31 / 12 | 177 (622) | 856.42 (450.17) | 580.25 | 476.76 (673.55) | 223.39 | 68.247 (1,418) | 175 | 0 |
| p11 | 660 | 471 / 1 / 25 / 12 | 131 (552) | 834.95 (428.22) | 555.00 | 464.37 (564.43) | 136.21 | 37.061 (1,113) | 151 | 0 |
| p13 | 1,137 | 736 / 2 / 45 / 28 | 237 (1,026) | 1,662.83 (858.38) | 1,073.74 | 889.04 (1,172.59) | 314.21 | 100.328 (2,127) | 326 | 0 |
| p17 | 1,016 | 690 / 8 / 37 / 18 | 201 (881) | 1,401.79 (741.41) | 929.56 | 742.52 (916.37) | 174.95 | 57.799 (1,830) | 263 | 0 |
| p21 | 796 | 540 / 15 / 26 / 17 | 129 (761) | 1,228.01 (635.70) | 812.28 | 688.36 (969.70) | 334.00 | 39.001 (1,493) | 198 | 0 |
| p31 | 783 | 533 / 15 / 28 / 11 | 161 (554) | 1,083.45 (559.75) | 713.84 | 596.22 (716.77) | 157.02 | 120.366 (1,437) | 196 | 0 |
| all | 6,241 | 4,330 / 53 / 229 / 108 | 1,150 (5,017) | 8,498.27 (4,418.82) | 5,729.11 | 4,774.11 (6,148.26) | 1,729.43 | 484.103 (11,148) | 1,521 | 0 |

Reading (development-only):

- **The release rule now ends one shipment in four**: 1,521 of 6,241
  shipments returned to their origin when their carrier left the trade in
  transit (every release is now a return), against 711 releases that
  continued unattended in the first pass. 2,013.5 food units went back to the
  holders' claims at the origins (route returns included); 4,330 shipments
  were delivered (5,243 in the first pass). Merchants bought more often
  (6,241 shipments against 5,634: a carrier is free again as soon as its
  shipment returns).
- **Margins still exceed the withheld income, by less**: merchants were paid
  6,148.3 by buyers for cargo bought for 4,418.8 (net +1,729.4; +3,254.5 in
  the first pass), against 484.1 of model income withheld over 11,148
  carrier-turns. A returned shipment earns no margin and its holder keeps the
  food as an ordinary claim at the origin.
- Returns other than releases: 51 `route_lost`, 2 `destination_conquered`;
  229 shipments escheated; every A1 ledger closure, including the two new
  measured closures, held on every observed turn.
- The releases came from the native decisions, which a reserved carrier then
  still took every tick (occupation switching reads the region's balance and
  food pressure, not the withheld income; the review's re-check). The rule
  that carriers take no decision while reserved replaced this (the rerun above).

All-on development run after the review, before the carrier rule (so it predates the rule that
carriers take no decision while reserved; template 7, titled trade with A3-2
owned output and the A3 academy flags): 145 shipments (116 delivered, 23
released and returned, 1 escheated, 5 live), 181.4 food bought for 97.1, net
money +53.5 against 1.2 withheld; 5 firms, 97.3 loads of owned output (free
use 0), 23.7 of household wares sales; every ledger closure held.

### First pass (before the review)

Development-only, 2026-11-07: source `9c6c66ee` (this branch), extension
`2ba123ab…`; no preregistration, no held seed, no 7xx/8xx/3xxx seed. One run
per world, 200 turns, `CHRONICLER_CHECK_RESOURCES=1` (no resource problem was
raised), flags `--agents hybrid --grain-reserves --public-grain-shipments
--food-allocation --household-retail --household-retail-boundary all
--titled-trade --wealth-accounting`; procedural worlds add `--worldgen
procedural --regions 32 --civs 10`. This describes activation, not an effect
(no arm without titled trade was compared). Template runs took 11-14 s,
procedural 32-38 s (4 shared cores under other lanes' load). Food in food
units; money in units of a person's wealth. "Net money" is what holders were
credited for selling delivered cargo less what they paid owners; "income
withheld" is the model merchant income the carriers did not receive while
carrying.

| World | Shipments | Delivered / returned / escheated / live at 199 | Routes (cross-civ shipments) | Food bought from owners (paid) | Delivered | Sold to buyers (credited) | Merchants' net money | Income withheld (carrier-turns) | Carriers released | Ledger closures failed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1 | 101 | 90 / 4 / 3 / 4 | 13 (72) | 138.21 (73.63) | 121.30 | 111.91 (181.97) | 108.34 | 1.782 (173) | 14 | 0 |
| t3 | 202 | 194 / 0 / 6 / 2 | 15 (156) | 231.21 (124.40) | 206.57 | 163.22 (198.17) | 73.77 | 12.113 (290) | 14 | 0 |
| t7 | 93 | 88 / 0 / 4 / 1 | 26 (80) | 95.17 (51.76) | 86.67 | 70.49 (98.49) | 46.73 | 6.967 (153) | 15 | 0 |
| t9 | 279 | 264 / 0 / 12 / 3 | 28 (68) | 344.14 (182.64) | 314.44 | 252.87 (278.81) | 96.17 | 24.189 (408) | 20 | 0 |
| t11 | 90 | 86 / 0 / 4 / 0 | 5 (42) | 90.29 (46.02) | 82.78 | 75.70 (91.21) | 45.19 | 1.672 (119) | 11 | 0 |
| t23 | 115 | 108 / 1 / 4 / 2 | 11 (115) | 174.26 (90.74) | 159.51 | 151.32 (228.98) | 138.24 | 1.519 (175) | 9 | 0 |
| t42 | 165 | 151 / 12 / 2 / 0 | 9 (36) | 219.21 (111.73) | 188.08 | 160.10 (195.04) | 83.31 | 0.429 (195) | 3 | 0 |
| p7 | 700 | 646 / 11 / 34 / 9 | 182 (565) | 938.70 (491.28) | 830.97 | 702.43 (980.03) | 488.75 | 67.245 (1,288) | 91 | 0 |
| p11 | 635 | 598 / 5 / 20 / 12 | 147 (551) | 875.04 (456.43) | 778.68 | 651.41 (781.87) | 325.44 | 46.046 (1,158) | 72 | 0 |
| p13 | 1,074 | 1,007 / 6 / 44 / 17 | 212 (956) | 1,577.44 (812.02) | 1,416.12 | 1,180.42 (1,490.23) | 678.21 | 92.263 (2,025) | 171 | 0 |
| p17 | 796 | 728 / 22 / 32 / 14 | 172 (687) | 1,107.93 (590.84) | 962.84 | 747.75 (915.57) | 324.73 | 74.143 (1,452) | 104 | 0 |
| p21 | 649 | 601 / 7 / 28 / 13 | 135 (572) | 958.49 (490.24) | 843.90 | 716.77 (947.38) | 457.14 | 56.536 (1,235) | 86 | 0 |
| p31 | 735 | 682 / 9 / 26 / 18 | 181 (596) | 1,049.62 (547.17) | 914.46 | 746.36 (935.59) | 388.43 | 127.851 (1,378) | 101 | 0 |
| all | 5,634 | 5,243 / 77 / 219 / 95 | 1,136 (4,496) | 7,799.72 (4,068.89) | 6,906.33 | 5,730.75 (7,323.35) | 3,254.45 | 512.755 (10,049) | 711 | 0 |

Reading (development-only):

- **Activation in every world** (13 of 13): owned food moved owner ->
  merchant -> buyers across regions, 80% of shipments between polities. Of
  7,799.7 food units bought from owners, 6,906.3 were delivered as holders'
  claims, 331.5 decayed in transit, 113.2 returned to origins, 302.6 went to
  commons (escheat or refused claims) and the rest was aboard at turn 199;
  holders sold 5,730.8 to the destinations' households (granaries bought from
  holders for 2.0 units credited; 0.54 of the sales credits were attribution
  approximations).
- **Every return but one was a lost route** (76 `route_lost`, 1
  `destination_conquered`); no quarantine closure arose (epidemics on, no
  `--quarantine-mode closure`). 219 shipments ended because their holder died
  in transit; war reached the regions shipments stood in on 24 shipment-turns
  (no loss in A4-1, counted).
- **Margins replaced the model income and exceeded it**: merchants were paid
  7,323.4 by buyers for cargo they bought for 4,068.9 (net +3,254.5), against
  512.8 of model income withheld over 10,049 carrier-turns. The merchants'
  model income is small under retail everywhere (native food trade nearly
  stops), so the withheld share is small. This is a development observation,
  not an effect estimate; the CW5 screen measures it against arms without
  titled trade.
- **Carriers left their trade in transit 711 times** (mostly occupation
  switches through the native decisions a reserved carrier still took),
  keeping title; the shipments continued (the rule the review replaced: see
  above).
- Every A1 ledger closure held on every observed turn; `cargo_purchase` in =
  out every turn.

An all-on development run (template 7, titled trade with A3-2 owned output
and the A3 academy flags): 166 shipments (161 delivered, 2 escheated), 190.7
food bought for 102.6, net money +89.4 against 7.8 withheld; 4 firms, 77.6
loads of owned output (free use 0), 25.0 of household wares sales; every
ledger closure held.
